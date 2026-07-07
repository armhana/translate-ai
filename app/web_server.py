"""Web-Server: macht den Übersetzer für alle Geräte im WLAN nutzbar
(Windows-Browser, iPhone/Safari, Android/Chrome — als PWA installierbar).

Start:  Start-Server.bat   oder   venv\\Scripts\\python.exe app\\web_server.py
Dann am Handy/Browser öffnen:  http://<PC-IP>:8710

Die KI läuft vollständig auf diesem PC; Inhalte verlassen das lokale Netz nicht.
"""
import json
import os
import shutil
import socket
import threading
import time
import uuid

from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import engine

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DIR = os.path.join(BASE, "jobs")
WEB_DIR = os.path.join(BASE, "web")
os.makedirs(JOBS_DIR, exist_ok=True)

app = FastAPI(title="Live-Übersetzer")

# Auf schwacher Hardware (z.B. Raspberry Pi): WHISPER_MODELL=base setzen
stt = engine.SpeechToText(model_size=os.environ.get("WHISPER_MODELL", "small"))
translator = engine.Translator()
tts = engine.TextToSpeech()
clone = engine.VoiceCloneTTS()

jobs = {}  # id -> {status, schritt, transkript, uebersetzung, fehler}


def _speichere_job(job_id):
    """Auftrag auf Platte sichern — Korrekturen funktionieren so auch nach
    einem Server-Neustart."""
    try:
        with open(os.path.join(JOBS_DIR, f"{job_id}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(jobs[job_id], fh)
    except Exception:
        pass


def _hole_job(job_id):
    """Auftrag aus Speicher oder von Platte holen."""
    if job_id in jobs:
        return jobs[job_id]
    try:
        with open(os.path.join(JOBS_DIR, f"{job_id}.json"), encoding="utf-8") as fh:
            jobs[job_id] = json.load(fh)
        return jobs[job_id]
    except Exception:
        return None


def _repariere_unterbrochene_jobs():
    """Beim Serverstart: Auftraege, die beim letzten Lauf mitten in der
    Verarbeitung abgebrochen wurden, klar als Fehler markieren — sonst
    stehen sie fuer immer auf 'laeuft'."""
    for name in os.listdir(JOBS_DIR):
        if not name.endswith(".json"):
            continue
        path = os.path.join(JOBS_DIR, name)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("status") == "laeuft":
                data["status"] = "fehler"
                data["fehler"] = ("Verarbeitung wurde unterbrochen (Server-Neustart). "
                                  "Bitte erneut starten.")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh)
        except Exception:
            pass


_repariere_unterbrochene_jobs()


def _warmup():
    """Whisper beim Serverstart laden — der erste Auftrag zahlt sonst die
    Ladezeit obendrauf. Laeuft wie alle KI-Arbeit im dedizierten KI-Thread."""
    try:
        stt.warmup()
    except Exception:
        pass  # Warmup darf nie den Serverstart verhindern


threading.Thread(target=_warmup, daemon=True).start()


def _fortschritt_helfer(job):
    """Liefert eine Funktion, die Fortschritt (0-100) und Restzeit setzt."""
    start = time.time()

    def setze(prozent):
        p = max(1, min(99, int(prozent)))
        job["fortschritt"] = p
        if p >= 5:
            verstrichen = time.time() - start
            job["rest_sekunden"] = int(verstrichen * (100 - p) / p)
    return setze


def _verarbeite(job_id, video_path, ziel, eigene_stimme, bild_stufe="aus",
                quell=None):
    job = jobs[job_id]
    fortschritt = _fortschritt_helfer(job)
    # Phasen-Anteile: mit eigener Stimme dominiert die XTTS-Synthese
    t_span = 15 if eigene_stimme else 70   # Transkription bis hierhin
    tts_bis = 95
    try:
        hat_video = engine.has_video_stream(video_path)
        job["hat_video"] = hat_video

        # Bildverbesserung (ffmpeg) parallel zur Transkription (Whisper) —
        # beides ist CPU-lastig, aber ffmpeg und ctranslate2 teilen sich
        # die Kerne besser, als nacheinander zu warten.
        video_quelle_fuer_bild = video_path
        enhance_fehler = []
        enhance_thread = None
        if bild_stufe in ("dezent", "beauty") and hat_video:
            besser = os.path.join(JOBS_DIR, f"{job_id}_besser.mp4")

            def _enhance():
                try:
                    engine.enhance_video(video_path, besser, stufe=bild_stufe)
                except Exception as e:
                    enhance_fehler.append(e)

            enhance_thread = threading.Thread(target=_enhance, daemon=True)
            enhance_thread.start()
            video_quelle_fuer_bild = besser

        job["schritt"] = "Transkribiere (Whisper)…"
        dauer = engine.media_duration(video_path)

        def bei_segment(start_s, ende_s, _txt):
            if dauer > 0:
                fortschritt(1 + (ende_s / dauer) * (t_span - 1))

        text, quelle = stt.transcribe_file(video_path, language=quell,
                                           on_segment=bei_segment)
        job["transkript"] = text
        fortschritt(t_span)
        if quelle != ziel:
            job["schritt"] = f"Übersetze {quelle} → {ziel}…"
            text_t = translator.translate(text, quelle, ziel)
        else:
            text_t = text  # gleiche Sprache: Neuvertonung entfernt den Akzent
        job["uebersetzung"] = text_t
        fortschritt(t_span + 5)

        if eigene_stimme and clone.available():
            job["schritt"] = "Erzeuge Stimmprofil & spreche in eigener Stimme (dauert)…"
            sample = engine.extract_voice_sample(
                video_path, os.path.join(JOBS_DIR, f"{job_id}_profil.wav"))
            xtts_lang = {"zh": "zh-cn"}.get(ziel, ziel)

            def bei_satz(i, n):
                job["schritt"] = f"Spreche in eigener Stimme — Satz {i} von {n}…"
                fortschritt(t_span + 5 + (i / n) * (tts_bis - t_span - 5))

            wav, rate = clone.synthesize(text_t, xtts_lang, sample,
                                         on_progress=bei_satz)
        else:
            job["schritt"] = "Erzeuge Sprachausgabe (neutrale Stimme)…"
            wav, rate = tts.synthesize(text_t, ziel)
        fortschritt(tts_bis)

        audio_path = os.path.join(JOBS_DIR, f"{job_id}.wav")
        engine.save_wav(audio_path, wav, rate)

        if enhance_thread is not None:
            job["schritt"] = "Warte auf Bildverbesserung…"
            enhance_thread.join()
            if enhance_fehler:
                raise enhance_fehler[0]

        if hat_video:
            job["schritt"] = "Baue Video mit neuer Tonspur…"
            video_out = os.path.join(JOBS_DIR, f"{job_id}.mp4")
            engine.mux_video_with_audio(video_quelle_fuer_bild, audio_path, video_out)

        job["status"] = "fertig"
        job["schritt"] = "Fertig."
        job["fortschritt"] = 100
        job["rest_sekunden"] = 0
    except Exception as e:
        job["status"] = "fehler"
        job["fehler"] = str(e)
    _speichere_job(job_id)


@app.post("/api/auftrag")
async def auftrag(video: UploadFile, zielsprache: str = Form(...),
                  eigene_stimme: bool = Form(False),
                  bild_verbessern: str = Form("aus")):
    # Stufen: aus | dezent | beauty ("true" alter Clients = dezent)
    bild_stufe = {"true": "dezent", "false": "aus"}.get(
        bild_verbessern.lower(), bild_verbessern.lower())
    job_id = uuid.uuid4().hex[:12]
    video_path = os.path.join(JOBS_DIR, f"{job_id}_eingabe.mp4")
    with open(video_path, "wb") as fh:
        shutil.copyfileobj(video.file, fh)
    jobs[job_id] = {"status": "laeuft", "schritt": "In Warteschlange…",
                    "transkript": "", "uebersetzung": "", "fehler": "",
                    "_video": video_path, "_ziel": zielsprache,
                    "_eigene_stimme": eigene_stimme}
    _speichere_job(job_id)
    threading.Thread(target=_verarbeite,
                     args=(job_id, video_path, zielsprache, eigene_stimme,
                           bild_stufe),
                     daemon=True).start()
    return {"job_id": job_id}


def _neu_vertonen(job_id, text):
    """Korrigierten Text neu vertonen und Video neu bauen (Video/Stimmprofil
    werden wiederverwendet — deutlich schneller als ein kompletter Durchlauf)."""
    job = jobs[job_id]
    fortschritt = _fortschritt_helfer(job)
    try:
        ziel = job["_ziel"]
        profil = os.path.join(JOBS_DIR, f"{job_id}_profil.wav")
        if job["_eigene_stimme"] and clone.available():
            if not os.path.exists(profil):
                job["schritt"] = "Erzeuge Stimmprofil…"
                engine.extract_voice_sample(job["_video"], profil)
            job["schritt"] = "Spreche korrigierten Text in eigener Stimme…"
            xtts_lang = {"zh": "zh-cn"}.get(ziel, ziel)

            def bei_satz(i, n):
                job["schritt"] = f"Spreche korrigierten Text — Satz {i} von {n}…"
                fortschritt(5 + (i / n) * 85)

            wav, rate = clone.synthesize(text, xtts_lang, profil,
                                         on_progress=bei_satz)
        else:
            job["schritt"] = "Spreche korrigierten Text (neutrale Stimme)…"
            wav, rate = tts.synthesize(text, ziel)
        fortschritt(92)
        audio_path = os.path.join(JOBS_DIR, f"{job_id}.wav")
        engine.save_wav(audio_path, wav, rate)

        if engine.has_video_stream(job["_video"]):
            job["schritt"] = "Baue Video neu…"
            besser = os.path.join(JOBS_DIR, f"{job_id}_besser.mp4")
            quelle = besser if os.path.exists(besser) else job["_video"]
            engine.mux_video_with_audio(quelle, audio_path,
                                        os.path.join(JOBS_DIR, f"{job_id}.mp4"))
        job["uebersetzung"] = text
        job["status"] = "fertig"
        job["schritt"] = "Fertig (mit Korrektur neu vertont)."
        job["fortschritt"] = 100
        job["rest_sekunden"] = 0
    except Exception as e:
        job["status"] = "fehler"
        job["fehler"] = str(e)
    _speichere_job(job_id)


@app.post("/api/neu_vertonen/{job_id}")
async def neu_vertonen(job_id: str, text: str = Form(...)):
    job = _hole_job(job_id)
    if not job or not job.get("_video") or not os.path.exists(job["_video"]):
        return JSONResponse(
            {"fehler": "Auftrag nicht mehr vorhanden — bitte Video erneut hochladen."},
            status_code=404)
    if not text.strip():
        return JSONResponse({"fehler": "Text ist leer"}, status_code=400)
    job["status"] = "laeuft"
    job["schritt"] = "Neu vertonen…"
    threading.Thread(target=_neu_vertonen, args=(job_id, text.strip()),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = _hole_job(job_id)
    if not job:
        return JSONResponse({"status": "unbekannt",
                             "fehler": "Auftrag nicht mehr vorhanden — bitte Video erneut hochladen."},
                            status_code=404)
    return {k: v for k, v in job.items() if not k.startswith("_")}


@app.get("/api/audio/{job_id}")
def audio(job_id: str):
    path = os.path.join(JOBS_DIR, f"{job_id}.wav")
    if not os.path.exists(path):
        return JSONResponse({"fehler": "nicht fertig"}, status_code=404)
    return FileResponse(path, media_type="audio/wav",
                        filename="uebersetzung.wav")


@app.get("/api/video/{job_id}")
def video(job_id: str):
    path = os.path.join(JOBS_DIR, f"{job_id}.mp4")
    if not os.path.exists(path):
        return JSONResponse({"fehler": "nicht fertig"}, status_code=404)
    return FileResponse(path, media_type="video/mp4",
                        filename="uebersetzung.mp4")


# Web-Oberfläche (PWA) unter / ausliefern
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def lokale_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    import uvicorn
    print()
    print("=" * 60)
    print("  Live-Übersetzer läuft. Auf Handy/Browser öffnen:")
    print(f"  http://{lokale_ip()}:8710")
    print("  (Gerät muss im selben WLAN sein)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8710, log_level="warning")
