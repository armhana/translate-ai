"""Web-Server: macht den Übersetzer für alle Geräte im WLAN nutzbar
(Windows-Browser, iPhone/Safari, Android/Chrome — als PWA installierbar).

Start:  Start-Server.bat   oder   venv\\Scripts\\python.exe app\\web_server.py
Dann am Handy/Browser öffnen:  http://<PC-IP>:8710

Die KI läuft vollständig auf diesem PC; Inhalte verlassen das lokale Netz nicht.
"""
import os
import shutil
import socket
import threading
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


def _verarbeite(job_id, video_path, ziel, eigene_stimme, quell=None):
    job = jobs[job_id]
    try:
        job["schritt"] = "Transkribiere (Whisper)…"
        text, quelle = stt.transcribe_file(video_path, language=quell)
        job["transkript"] = text
        if quelle != ziel:
            job["schritt"] = f"Übersetze {quelle} → {ziel}…"
            text_t = translator.translate(text, quelle, ziel)
        else:
            text_t = text  # gleiche Sprache: Neuvertonung entfernt den Akzent
        job["uebersetzung"] = text_t

        if eigene_stimme and clone.available():
            job["schritt"] = "Erzeuge Stimmprofil & spreche in eigener Stimme (dauert)…"
            sample = engine.extract_voice_sample(
                video_path, os.path.join(JOBS_DIR, f"{job_id}_profil.wav"))
            xtts_lang = {"zh": "zh-cn"}.get(ziel, ziel)
            wav, rate = clone.synthesize(text_t, xtts_lang, sample)
        else:
            job["schritt"] = "Erzeuge Sprachausgabe (neutrale Stimme)…"
            wav, rate = tts.synthesize(text_t, ziel)

        audio_path = os.path.join(JOBS_DIR, f"{job_id}.wav")
        engine.save_wav(audio_path, wav, rate)

        job["schritt"] = "Baue Video mit neuer Tonspur…"
        video_out = os.path.join(JOBS_DIR, f"{job_id}.mp4")
        engine.mux_video_with_audio(video_path, audio_path, video_out)

        job["status"] = "fertig"
        job["schritt"] = "Fertig."
    except Exception as e:
        job["status"] = "fehler"
        job["fehler"] = str(e)


@app.post("/api/auftrag")
async def auftrag(video: UploadFile, zielsprache: str = Form(...),
                  eigene_stimme: bool = Form(False)):
    job_id = uuid.uuid4().hex[:12]
    video_path = os.path.join(JOBS_DIR, f"{job_id}_eingabe.mp4")
    with open(video_path, "wb") as fh:
        shutil.copyfileobj(video.file, fh)
    jobs[job_id] = {"status": "laeuft", "schritt": "In Warteschlange…",
                    "transkript": "", "uebersetzung": "", "fehler": ""}
    threading.Thread(target=_verarbeite,
                     args=(job_id, video_path, zielsprache, eigene_stimme),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"status": "unbekannt"}, status_code=404)
    return job


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
