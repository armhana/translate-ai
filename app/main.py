"""EchoMe — Stand-alone-App (Windows/Linux).

Drei Modi:
  1. Video/Datei:   Videodatei transkribieren, übersetzen, vertonen, als WAV speichern.
  2. Gesprächsmodus: Mikrofon live übersetzen (z.B. Gespräch mit Kopfhörer) —
                     beide Richtungen: eigene Stimme und Systemton des Partners.
  3. Anruf-Modus:    wie Gesprächsmodus, Ausgabe der eigenen Übersetzung auf ein
                     virtuelles Kabel, damit der Partner im Call sie hört.

Hinweis: Die Verarbeitung von Gesprächen setzt die Einwilligung aller Beteiligten
voraus (§ 201 StGB).
"""
import json
import locale
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import audio as audio_mod
import engine

APP_TITLE = "EchoMe (lokal & offline)"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "einstellungen.json")

DATENSCHUTZ_TEXT = (
    "Einwilligung zur Datenverarbeitung (Art. 6 Abs. 1 lit. a DSGVO)\n\n"
    "Diese Anwendung verarbeitet Audio- und Videodaten ausschließlich LOKAL auf "
    "diesem Gerät. Es werden keine Inhalte an Server oder Dritte übertragen. "
    "Eine Internetverbindung wird nur für den einmaligen Download von KI-Modellen "
    "genutzt (dabei werden keine Ihrer Inhalte übermittelt).\n\n"
    "Verarbeitete Daten: Sprachaufnahmen (Mikrofon), Systemton, Videodateien, "
    "daraus erzeugte Transkripte, Übersetzungen und Sprachausgaben sowie — bei "
    "aktivierter Funktion 'Eigene Stimme' — ein Stimmprofil aus Ihrem Video.\n"
    "Zweck: Übersetzung und Neuvertonung.\n"
    "Speicherung: nur die Dateien, die Sie selbst aktiv speichern.\n\n"
    "Beim Live-Modus gilt zusätzlich: Die Verarbeitung der Stimme von "
    "Gesprächspartnern erfordert deren vorherige Einwilligung (§ 201 StGB, "
    "Art. 6/7 DSGVO). Sie bestätigen diese vor jedem Start des Live-Modus.\n\n"
    "Sie können diese Einwilligung jederzeit über den Button 'Datenschutz' "
    "widerrufen; die App beendet sich dann."
)

LANGS = [
    ("de", "Deutsch"), ("en", "Englisch"), ("fr", "Französisch"),
    ("es", "Spanisch"), ("it", "Italienisch"), ("pt", "Portugiesisch"),
    ("nl", "Niederländisch"), ("pl", "Polnisch"), ("ru", "Russisch"),
    ("tr", "Türkisch"), ("zh", "Chinesisch"),
]


def system_language():
    """Zielsprache aus der Geräte-/Systemsprache ableiten."""
    loc = locale.getdefaultlocale()[0] or "en_US"
    code = loc.split("_")[0].lower()
    return code if code in dict(LANGS) else "en"


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


class ConsentDialog(tk.Toplevel):
    """DSGVO-Einwilligungsdialog: ohne aktive Zustimmung startet die App nicht."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Einwilligung erforderlich")
        self.accepted = False
        self.transient(parent)
        try:
            self.wait_visibility()   # grab_set schlaegt auf unsichtbarem Fenster fehl
            self.grab_set()
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self._decline)
        txt = tk.Text(self, wrap="word", width=86, height=22, padx=12, pady=12)
        txt.insert("1.0", DATENSCHUTZ_TEXT)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        row = ttk.Frame(self); row.pack(pady=10)
        ttk.Button(row, text="Ich stimme zu", command=self._accept).pack(side="left", padx=8)
        ttk.Button(row, text="Ablehnen (App beenden)", command=self._decline).pack(side="left", padx=8)

    def _accept(self):
        self.accepted = True
        self.destroy()

    def _decline(self):
        self.accepted = False
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        # Fenster an den Bildschirm anpassen — sonst liegt die Statusleiste
        # auf kleinen Displays unsichtbar unterhalb des Bildschirmrands
        breite = min(1020, self.winfo_screenwidth() - 40)
        hoehe = min(860, self.winfo_screenheight() - 90)
        self.geometry(f"{breite}x{hoehe}+10+10")
        self.minsize(760, 560)
        try:
            import sv_ttk
            sv_ttk.set_theme("light")
        except ImportError:
            ttk.Style().theme_use("clam")
        self.option_add("*Font", ("Segoe UI", 10))
        self._style_texts = []
        self.stt = engine.SpeechToText(model_size="small")
        # Live: kleineres Modell + greedy decoding (beam=1) für minimale Latenz
        self.stt_live = engine.SpeechToText(model_size="base", beam_size=1)
        self.translator = engine.Translator()
        self.tts = engine.TextToSpeech()
        self.clone_tts = engine.VoiceCloneTTS()
        self.live_threads = []
        self.recorders = []
        self.players = {}
        self.live_running = False
        self.player = audio_mod.SeekablePlayer()
        self.current_audio = None  # (np-Array, Rate) der letzten Vertonung

        self._build_ui()
        self.after(50, self._require_consent)

    # ------------------------------------------------------- Einwilligung --
    def _require_consent(self):
        cfg = load_config()
        if cfg.get("einwilligung"):
            return
        dlg = ConsentDialog(self)
        self.wait_window(dlg)
        if not dlg.accepted:
            self.destroy()
            return
        cfg["einwilligung"] = {"erteilt": True,
                               "zeitpunkt": time.strftime("%Y-%m-%d %H:%M:%S")}
        save_config(cfg)

    def _show_privacy(self):
        if messagebox.askyesno("Datenschutz",
                               DATENSCHUTZ_TEXT + "\n\nEinwilligung WIDERRUFEN und App beenden?"):
            cfg = load_config()
            cfg.pop("einwilligung", None)
            save_config(cfg)
            self.destroy()

    # ------------------------------------------------------------------ UI --
    def _make_text(self, parent, height):
        """Einheitlich gestaltetes Textfeld mit Rahmen."""
        txt = tk.Text(parent, height=height, wrap="word", relief="flat",
                      font=("Segoe UI", 10), padx=10, pady=8,
                      background="#ffffff", highlightthickness=1,
                      highlightbackground="#d0d4dc", highlightcolor="#0067c0")
        return txt

    def _build_ui(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=16, pady=(14, 4))
        ttk.Label(header, text="🌐 EchoMe",
                  font=("Segoe UI Semibold", 17)).pack(side="left")
        ttk.Label(header, text="   lokal · offline · DSGVO-konform",
                  font=("Segoe UI", 10), foreground="#6b7280").pack(side="left", pady=(6, 0))

        # Statusleiste ZUERST am Boden verankern: so bekommt sie garantiert
        # Platz und wird nie vom unteren Bildschirmrand abgeschnitten
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        self.status = tk.StringVar(value="Bereit. Beim ersten Lauf werden KI-Modelle einmalig geladen.")
        ttk.Label(bottom, textvariable=self.status, anchor="w",
                  font=("Segoe UI Semibold", 10),
                  foreground="#1d4ed8").pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Datenschutz", command=self._show_privacy).pack(side="right")

        note = ttk.Notebook(self)
        note.pack(fill="both", expand=True, padx=12, pady=8)

        self.tab_video = ttk.Frame(note, padding=10)
        self.tab_live = ttk.Frame(note, padding=10)
        note.add(self.tab_video, text="  🎬  Video / Datei  ")
        note.add(self.tab_live, text="  🎙  Live: Gespräch & Anruf  ")

        self._build_video_tab()
        self._build_live_tab()


    def _lang_combo(self, parent, var):
        cb = ttk.Combobox(parent, state="readonly", width=16,
                          values=[f"{n} ({c})" for c, n in LANGS])
        idx = [c for c, _ in LANGS].index(var.get())
        cb.current(idx)
        cb.bind("<<ComboboxSelected>>",
                lambda e: var.set(LANGS[cb.current()][0]))
        return cb

    # ---------------------------------------------------------- Video-Tab --
    def _build_video_tab(self):
        f = self.tab_video
        row = ttk.Frame(f); row.pack(fill="x", pady=(4, 8))
        ttk.Button(row, text="📂 Videodatei wählen…", command=self._pick_video).pack(side="left")
        self.video_path = tk.StringVar()
        ttk.Label(row, textvariable=self.video_path,
                  foreground="#6b7280").pack(side="left", padx=10)

        row2 = ttk.Frame(f); row2.pack(fill="x", pady=(0, 8))
        ttk.Label(row2, text="Zielsprache:").pack(side="left")
        self.video_tgt = tk.StringVar(value=system_language())
        self._lang_combo(row2, self.video_tgt).pack(side="left", padx=8)
        ttk.Label(row2, text="(automatisch aus Systemsprache erkannt)",
                  foreground="#6b7280").pack(side="left")
        self.btn_video_go = ttk.Button(row2, text="① Transkribieren + Übersetzen",
                                       style="Accent.TButton", command=self._run_video)
        self.btn_video_go.pack(side="right")

        # Bedienzeilen von UNTEN verankern und VOR den Textfeldern packen
        # (frueher gepackte Widgets haben Platz-Prioritaet): bei kleinen
        # Fenstern schrumpfen die Textfelder, nie die Knöpfe.
        row4 = ttk.Frame(f); row4.pack(side="bottom", fill="x", pady=(0, 4))
        row3b = ttk.Frame(f); row3b.pack(side="bottom", fill="x", pady=(0, 8))
        row3 = ttk.Frame(f); row3.pack(side="bottom", fill="x", pady=8)
        rowv = ttk.Frame(f); rowv.pack(side="bottom", fill="x", pady=(2, 0))

        ttk.Label(f, text="Transkript (Original)",
                  font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(4, 2))
        self.txt_orig = self._make_text(f, 4)
        self.txt_orig.pack(fill="both", expand=True, pady=(0, 8))
        ttk.Label(f, text="Übersetzung — dieser Text wird gesprochen, Fehler hier korrigieren",
                  font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(0, 2))
        self.txt_trans = self._make_text(f, 4)
        self.txt_trans.pack(fill="both", expand=True, pady=(0, 6))

        self.use_own_voice = tk.BooleanVar(value=True)
        ttk.Checkbutton(rowv, variable=self.use_own_voice,
                        text="Meine eigene Stimme verwenden (lokales Stimmprofil aus dem Video; "
                             "nur nicht-kommerzielle Nutzung)").pack(side="left")
        ttk.Button(row3, text="② Vertonung erzeugen", style="Accent.TButton",
                   command=self._make_audio).pack(side="left")
        ttk.Separator(row3, orient="vertical").pack(side="left", fill="y", padx=14)
        ttk.Button(row3, text="⏪ 10 s", width=8,
                   command=lambda: self.player.seek(-10)).pack(side="left", padx=2)
        self.btn_play = ttk.Button(row3, text="▶ Play", width=9, command=self._player_toggle)
        self.btn_play.pack(side="left", padx=2)
        ttk.Button(row3, text="⏹ Stopp", width=9, command=self._player_stop).pack(side="left", padx=2)
        ttk.Button(row3, text="10 s ⏩", width=8,
                   command=lambda: self.player.seek(+10)).pack(side="left", padx=2)
        self.pos_label = tk.StringVar(value="0:00 / 0:00")
        ttk.Label(row3, textvariable=self.pos_label, width=13,
                  foreground="#6b7280").pack(side="left", padx=8)

        ttk.Label(row3b, text="🔊 Wiedergabe über:").pack(side="left", padx=(0, 6))
        self.cb_video_out = ttk.Combobox(row3b, state="readonly", width=52)
        self._video_outputs = audio_mod.list_output_devices()
        self.cb_video_out["values"] = [f"{i}: {n}" for i, n in self._video_outputs]
        # Windows-Standardgeraet per Namensvergleich vorwaehlen (der MME-Name
        # ist gekappt, daher Praefix-Vergleich mit dem vollen WASAPI-Namen)
        try:
            import sounddevice as sd
            def_name = sd.query_devices(kind="output")["name"]
        except Exception:
            def_name = ""
        for pos, (_, n) in enumerate(self._video_outputs):
            if n.startswith(def_name) or (def_name and def_name.startswith(n)):
                self.cb_video_out.current(pos)
                break
        else:
            if self._video_outputs:
                self.cb_video_out.current(0)
        self.cb_video_out.pack(side="left")
        self.cb_video_out.bind("<<ComboboxSelected>>", self._video_out_changed)
        ttk.Button(row3b, text="🔔 Testton", command=self._testton).pack(side="left", padx=8)

        ttk.Button(row4, text="③ 💾 Video mit neuer Tonspur speichern…", style="Accent.TButton",
                   command=self._save_video).pack(side="left")
        ttk.Button(row4, text="Audio speichern (MP3/WAV/M4A)…", command=self._save_translation).pack(side="left", padx=8)
        ttk.Button(row4, text="Text speichern…", command=self._save_text).pack(side="left")
        self._tick_player()

    def _pick_video(self):
        p = filedialog.askopenfilename(filetypes=[
            ("Video/Audio", "*.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.m4a"),
            ("Alle Dateien", "*.*")])
        if p:
            self.video_path.set(p)

    def _run_video(self):
        path = self.video_path.get()
        if not path:
            # Kein Video? Dann eingetippten/eingefuegten Text uebersetzen
            # (z.B. Sprachmemo-Abschrift, Notiz) — Vertonung wie gewohnt.
            text = self.txt_orig.get("1.0", "end").strip()
            if not text:
                messagebox.showwarning(APP_TITLE,
                    "Bitte eine Datei wählen ODER Text in das Feld "
                    "'Transkript (Original)' einfügen.")
                return
            self.btn_video_go.config(state="disabled")
            threading.Thread(target=self._text_worker, args=(text,), daemon=True).start()
            return
        self.btn_video_go.config(state="disabled")
        threading.Thread(target=self._video_worker, args=(path,), daemon=True).start()

    def _text_worker(self, text):
        """Nur-Text-Auftrag: uebersetzen; Vertonung danach wie gewohnt
        (eigene Stimme braucht allerdings eine Videodatei als Stimmprobe)."""
        try:
            import locale as _loc
            src_lang = (_loc.getdefaultlocale()[0] or "de")[:2]
            tgt = self.video_tgt.get()
            if src_lang != tgt:
                self._set_status(f"Übersetze Text {src_lang} → {tgt}…")
                text_t = self.translator.translate(text, src_lang, tgt)
            else:
                text_t = text
            self._set_text(self.txt_trans, text_t)
            self._set_status("Text übersetzt — '② Vertonung erzeugen' zum Vorlesen "
                             "(eigene Stimme braucht eine Videodatei als Stimmprobe).")
        except Exception as e:
            self._set_status(f"Fehler: {e}")
        finally:
            self.btn_video_go.config(state="normal")

    def _video_worker(self, path):
        try:
            self._set_status("Transkribiere… (erster Lauf lädt das Whisper-Modell, ~490 MB)")
            dauer = engine.media_duration(path)

            def bei_segment(start_s, ende_s, _txt):
                if dauer > 0:
                    self._set_status(f"Transkribiere… {min(99, int(ende_s / dauer * 100))} %")

            text, src = self.stt.transcribe_file(path, on_segment=bei_segment)
            self._set_text(self.txt_orig, text)
            tgt = self.video_tgt.get()
            if src != tgt:
                self._set_status(f"Übersetze {src} → {tgt}…")
                text_t = self.translator.translate(text, src, tgt)
            else:
                text_t = text  # gleiche Sprache: Neuvertonung entfernt den Akzent
            self._set_text(self.txt_trans, text_t)
            self._set_status("Fertig. Über 'Übersetzung anhören' oder 'Als WAV speichern' ausgeben.")
        except Exception as e:
            self._set_status(f"Fehler: {e}")
        finally:
            self.btn_video_go.config(state="normal")

    def _make_audio(self, autoplay=False, start_fraction=None):
        """Vertonung erzeugen: eigene Stimme (geklont) oder neutrale Stimme.

        start_fraction (0..1): Wiedergabe nach dem Erzeugen an dieser
        Textstelle beginnen (z.B. Cursorposition nach einer Korrektur).
        """
        text = self.txt_trans.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "Keine Übersetzung vorhanden — erst Schritt 'Transkribieren + Übersetzen' ausführen.")
            return
        own = self.use_own_voice.get()
        if own and not self.clone_tts.available():
            messagebox.showwarning(APP_TITLE, "Stimmen-Klon-Modul (coqui-tts) ist nicht installiert — nutze neutrale Stimme.")
            own = False
        if own and not self.video_path.get():
            messagebox.showwarning(APP_TITLE, "Für die eigene Stimme wird das Video als Stimmreferenz gebraucht — bitte Videodatei wählen.")
            return
        geraet = self._aktives_ausgabegeraet()
        wanted_own = self.use_own_voice.get()  # Haekchen-Stand zum Zeitpunkt der Erzeugung

        def worker():
            try:
                tgt = self.video_tgt.get()
                if own:
                    self._set_status("Erzeuge Stimmprofil aus dem Video…")
                    sample = engine.extract_voice_sample(
                        self.video_path.get(),
                        os.path.join(engine.MODELS_DIR, "stimmprofil.wav"))
                    self._set_status("Spreche in Ihrer Stimme… (erster Lauf lädt XTTS ~1,9 GB; "
                                     "die Erzeugung dauert auf CPU mehrere Minuten)")
                    xtts_lang = {"zh": "zh-cn"}.get(tgt, tgt)

                    def bei_satz(i, n):
                        self._set_status(f"Spreche in Ihrer Stimme — Satz {i} von {n} "
                                         f"({int(i / n * 100)} %)…")

                    wav, rate = self.clone_tts.synthesize(text, xtts_lang, sample,
                                                          on_progress=bei_satz)
                else:
                    self._set_status("Erzeuge Sprachausgabe (neutrale Stimme)…")
                    wav, rate = self.tts.synthesize(text, tgt)
                self.current_audio = (wav, rate)
                # merken, welcher Text MIT welcher Stimmeinstellung gesprochen wurde
                self.current_audio_text = text
                self.current_audio_eigene = wanted_own
                self.player.load(wav, rate)
                if start_fraction:
                    # An der Korrekturstelle fortsetzen (2 s Vorlauf)
                    self.player.pos = max(0, int(len(wav) * start_fraction - 2 * rate))
                stimme = "eigene Stimme" if own else "neutrale Stimme"
                if autoplay:
                    self.player.play()
                    self._set_status(f"Vertonung ({stimme}) erzeugt — Wiedergabe über: {geraet}")
                else:
                    self._set_status(f"Vertonung fertig ({stimme}) — mit ▶ Play anhören oder speichern.")
            except Exception as e:
                self._set_status(f"Fehler bei der Vertonung: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _testton(self):
        """Piepton auf das gewählte Gerät — prüft den Tonweg ohne KI."""
        auswahl = self.cb_video_out.get()
        idx = int(auswahl.split(":")[0]) if ":" in auswahl else None

        def worker():
            try:
                weg = audio_mod.spiele_testton(idx)
                self._set_status(f"🔔 Testton abgespielt über: {weg}. "
                                 f"Nichts gehört? Lautstärke/Gerät in Windows prüfen.")
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    APP_TITLE, f"Kein Tonweg funktioniert:\n{e}\n\n"
                    "Bitte Windows-Lautstärkemixer und Standardgerät prüfen."))
        threading.Thread(target=worker, daemon=True).start()

    def _video_out_changed(self, event=None):
        """Wiedergabegeraet fuer den Video-Tab wechseln."""
        auswahl = self.cb_video_out.get()
        if not auswahl:
            return
        idx = int(auswahl.split(":")[0])
        self.player.set_device(idx)
        self._set_status(f"Wiedergabe-Gerät: {auswahl.split(':', 1)[1].strip()}")

    def _aktives_ausgabegeraet(self):
        auswahl = self.cb_video_out.get()
        return auswahl.split(":", 1)[1].strip() if ":" in auswahl else "Standard"

    def _player_toggle(self):
        text = self.txt_trans.get("1.0", "end").strip()
        # Text ODER Stimmeinstellung nach der letzten Vertonung geändert?
        # Dann automatisch neu vertonen — nie eine veraltete Fassung abspielen.
        veraltet = (text != getattr(self, "current_audio_text", None) or
                    self.use_own_voice.get() != getattr(self, "current_audio_eigene", None))
        if text and veraltet:
            # Cursorposition im Text -> Wiedergabe startet an der Korrekturstelle
            cursor_chars = len(self.txt_trans.get("1.0", tk.INSERT))
            fraction = min(1.0, cursor_chars / len(text)) if text else 0
            self._make_audio(autoplay=True, start_fraction=fraction)
            return
        if self.current_audio is None:
            messagebox.showinfo(APP_TITLE, "Erst 'Vertonung erzeugen' ausführen.")
            return
        if self.player.playing:
            self.player.pause()
        else:
            try:
                self.player.play()
                self._set_status(f"Wiedergabe läuft — über: {self._aktives_ausgabegeraet()}")
            except Exception as e:
                messagebox.showerror(APP_TITLE,
                    f"Wiedergabe fehlgeschlagen:\n{e}\n\n"
                    "Tipp: '🔔 Testton' probieren und ggf. anderes Ausgabegerät wählen.")

    def _player_stop(self):
        self.player.pause()
        self.player.seek(-10**9)

    def _tick_player(self):
        cur, total = self.player.position()
        self.pos_label.set(f"{int(cur)//60}:{int(cur)%60:02d} / {int(total)//60}:{int(total)%60:02d}")
        self.btn_play.config(text="⏸ Pause" if self.player.playing else "▶ Play")
        self.after(250, self._tick_player)

    def _audio_ist_aktuell(self):
        """Stimmt die erzeugte Vertonung noch mit dem (ggf. korrigierten) Text überein?"""
        if self.current_audio is None:
            messagebox.showinfo(APP_TITLE, "Erst 'Vertonung erzeugen' ausführen.")
            return False
        text = self.txt_trans.get("1.0", "end").strip()
        if text != getattr(self, "current_audio_text", None):
            messagebox.showinfo(APP_TITLE,
                "Der Text wurde geändert. Bitte zuerst '② Vertonung erzeugen' klicken, "
                "damit die Korrektur auch gesprochen wird.")
            return False
        if self.use_own_voice.get() != getattr(self, "current_audio_eigene", None):
            messagebox.showinfo(APP_TITLE,
                "Die Stimmeinstellung wurde geändert. Bitte zuerst '② Vertonung erzeugen' "
                "klicken, damit die gewünschte Stimme verwendet wird.")
            return False
        return True

    def _save_video(self):
        if not self._audio_ist_aktuell():
            return
        if not self.video_path.get():
            messagebox.showinfo(APP_TITLE, "Kein Originalvideo gewählt.")
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4-Video", "*.mp4"), ("MKV-Video", "*.mkv"),
                       ("MOV-Video", "*.mov")])
        if not dest:
            return
        def worker():
            try:
                self._set_status("Baue Video mit neuer Tonspur…")
                wav, rate = self.current_audio
                tmp = os.path.join(engine.MODELS_DIR, "tonspur_tmp.wav")
                engine.save_wav(tmp, wav, rate)
                engine.mux_video_with_audio(self.video_path.get(), tmp, dest)
                self._set_status(f"Video gespeichert: {dest}")
            except Exception as e:
                self._set_status(f"Fehler beim Video-Export: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _save_translation(self):
        if not self._audio_ist_aktuell():
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3-Audio", "*.mp3"), ("WAV-Audio", "*.wav"),
                       ("M4A-Audio", "*.m4a"), ("OGG-Audio", "*.ogg")])
        if not dest:
            return

        def worker():
            try:
                wav, rate = self.current_audio
                if dest.lower().endswith(".wav"):
                    engine.save_wav(dest, wav, rate)
                else:
                    import tempfile
                    tmp = os.path.join(tempfile.gettempdir(), "uebersetzer_export.wav")
                    engine.save_wav(tmp, wav, rate)
                    engine.convert_audio(tmp, dest)
                self._set_status(f"Gespeichert: {dest}")
            except Exception as e:
                self._set_status(f"Fehler beim Speichern: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _save_text(self):
        text = self.txt_trans.get("1.0", "end").strip()
        if not text:
            return
        dest = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Text", "*.txt")])
        if dest:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(text)
            self._set_status(f"Gespeichert: {dest}")

    # ----------------------------------------------------------- Live-Tab --
    def _build_live_tab(self):
        f = self.tab_live
        info = ("Beide Richtungen laufen parallel: Ihre Stimme wird in die Partnersprache "
                "übersetzt, der Systemton (Teams/Zoom/Video) zurück in Ihre Sprache. "
                "Anruf-Modus: als 'Ausgabe an Partner' das virtuelle Kabel wählen und dieses "
                "im Call als Mikrofon einstellen.")
        ttk.Label(f, text=info, wraplength=940, justify="left",
                  foreground="#6b7280").pack(anchor="w", pady=(2, 8))

        grid = ttk.LabelFrame(f, text=" Sprachen & Audiogeräte ", padding=10)
        grid.pack(fill="x")

        ttk.Label(grid, text="Meine Sprache:").grid(row=0, column=0, sticky="w", pady=3)
        self.live_my_lang = tk.StringVar(value=system_language())
        self._lang_combo(grid, self.live_my_lang).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(grid, text="Partnersprache:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.live_their_lang = tk.StringVar(value="en")
        self._lang_combo(grid, self.live_their_lang).grid(row=0, column=3, sticky="w", padx=6)


        ttk.Label(grid, text="Mein Mikrofon:").grid(row=1, column=0, sticky="w", pady=3)
        self.cb_mic = ttk.Combobox(grid, state="readonly", width=42)
        self.cb_mic.grid(row=1, column=1, columnspan=3, sticky="w", padx=6)

        ttk.Label(grid, text="Partner-Ton (Loopback):").grid(row=2, column=0, sticky="w", pady=3)
        self.cb_loop = ttk.Combobox(grid, state="readonly", width=42)
        self.cb_loop.grid(row=2, column=1, columnspan=3, sticky="w", padx=6)

        ttk.Label(grid, text="Ausgabe an mich (Kopfhörer):").grid(row=3, column=0, sticky="w", pady=3)
        self.cb_out_me = ttk.Combobox(grid, state="readonly", width=42)
        self.cb_out_me.grid(row=3, column=1, columnspan=3, sticky="w", padx=6)

        ttk.Label(grid, text="Ausgabe an Partner (virt. Kabel):").grid(row=4, column=0, sticky="w", pady=3)
        self.cb_out_them = ttk.Combobox(grid, state="readonly", width=42)
        self.cb_out_them.grid(row=4, column=1, columnspan=3, sticky="w", padx=6)

        row = ttk.Frame(f); row.pack(fill="x", pady=10)
        self.btn_live = ttk.Button(row, text="▶  Live-Übersetzung starten",
                                   style="Accent.TButton", command=self._toggle_live)
        self.btn_live.pack(side="left")
        ttk.Button(row, text="🔄 Geräte aktualisieren",
                   command=self._refresh_devices).pack(side="left", padx=10)
        ttk.Label(row, text="Erkennung:").pack(side="left", padx=(14, 4))
        self.cb_quality = ttk.Combobox(row, state="readonly", width=15,
                                       values=["base (schnell)", "small (genauer)"])
        self.cb_quality.current(0)
        self.cb_quality.pack(side="left")
        ttk.Label(row, text="Mikrofon-Pegel:").pack(side="left", padx=(20, 6))
        self.level_bar = ttk.Progressbar(row, length=180, maximum=0.2)
        self.level_bar.pack(side="left", pady=2)

        ttk.Label(f, text="Protokoll",
                  font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(4, 2))
        self.txt_log = self._make_text(f, 14)
        self.txt_log.config(state="disabled", background="#f8f9fb",
                            font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, pady=(0, 4))

        self._refresh_devices()

    def _refresh_devices(self):
        self.inputs = audio_mod.list_input_devices()
        self.outputs = audio_mod.list_output_devices()
        self.loops = audio_mod.list_loopback_sources()
        self.cb_mic["values"] = [f"{i}: {n}" for i, n in self.inputs]
        self.cb_out_me["values"] = [f"{i}: {n}" for i, n in self.outputs]
        self.cb_out_them["values"] = ["(keine — Partner hört mich nicht übersetzt)"] + \
                                     [f"{i}: {n}" for i, n in self.outputs]
        self.cb_loop["values"] = ["(keine — Partner wird nicht übersetzt)"] + self.loops
        # Windows-Standardgeraete per Namensvergleich vorauswaehlen (MME-Name
        # ist gekappt, daher Praefix-Vergleich mit vollem WASAPI-Namen)
        import sounddevice as sd
        def default_name(kind):
            try:
                return sd.query_devices(kind=kind)["name"]
            except Exception:
                return ""
        def select_default(cb, devices, name):
            if not cb["values"]:
                return
            for pos, (_, n) in enumerate(devices):
                if n.startswith(name) or (name and name.startswith(n)):
                    cb.current(pos)
                    return
            cb.current(0)
        select_default(self.cb_mic, self.inputs, default_name("input"))
        select_default(self.cb_out_me, self.outputs, default_name("output"))
        self.cb_out_them.current(0)
        # Loopback: Quelle passend zum Standard-Ausgabegeraet vorauswaehlen
        self.cb_loop.current(0)
        try:
            out_name = default_name("output")
            for pos, name in enumerate(self.loops):
                praefix = name.split("(")[0].strip()
                if praefix and (praefix in out_name or name.startswith(out_name)):
                    self.cb_loop.current(pos + 1)  # +1 wegen "(keine)"-Eintrag
                    break
        except Exception:
            pass

    def _toggle_live(self):
        if self.live_running:
            self._stop_live()
        else:
            self._start_live()

    def _start_live(self):
        if not messagebox.askyesno(
                "Einwilligung der Gesprächsteilnehmer",
                "Der Live-Modus verarbeitet auch die Stimme Ihrer Gesprächspartner.\n\n"
                "Bestätigen Sie, dass ALLE Beteiligten der Verarbeitung durch diese "
                "Anwendung zugestimmt haben (§ 201 StGB, Art. 6 DSGVO)?"):
            return
        if not self.cb_mic.get():
            messagebox.showwarning(APP_TITLE, "Kein Mikrofon gewählt.")
            return
        mic_idx = int(self.cb_mic.get().split(":")[0])
        out_me_idx = int(self.cb_out_me.get().split(":")[0])
        out_them = self.cb_out_them.get()
        out_them_idx = int(out_them.split(":")[0]) if not out_them.startswith("(") else None
        loop_name = None if self.cb_loop.get().startswith("(") else self.cb_loop.get()

        my, their = self.live_my_lang.get(), self.live_their_lang.get()
        model = "small" if "small" in self.cb_quality.get() else "base"
        if self.stt_live.model_size != model:
            self.stt_live = engine.SpeechToText(model_size=model, beam_size=1)

        # Modelle im Hintergrund vorwaermen, damit schon der erste Satz
        # ohne Modell-Ladepause uebersetzt wird
        def warmup():
            try:
                self.stt_live.warmup()
                self.translator._ensure_pair(my, their)
                self.translator._ensure_pair(their, my)
            except Exception:
                pass
        threading.Thread(target=warmup, daemon=True).start()
        self.live_running = True
        self.btn_live.config(text="■ Stoppen")
        self._log(f"Gestartet. Ich: {my} → Partner: {their} (Modell: {model}).")
        self._log("Beim ersten Satz werden Erkennungs-/Übersetzungsmodelle geladen — "
                  "der erste Durchlauf kann daher deutlich länger dauern.")

        self.players = {"me": audio_mod.Player(out_me_idx)}
        if out_them_idx is not None:
            self.players["them"] = audio_mod.Player(out_them_idx)

        # Richtung 1: mein Mikrofon -> Partnersprache
        rec_mic = audio_mod.UtteranceRecorder(device_index=mic_idx)
        rec_mic.start()
        self.recorders = [rec_mic]
        t1 = threading.Thread(target=self._direction_worker,
                              args=(rec_mic, my, their, "them", "Ich"), daemon=True)
        t1.start()
        self.live_threads = [t1]

        # Richtung 2: Systemton (Partner) -> meine Sprache
        if loop_name:
            rec_loop = audio_mod.UtteranceRecorder(loopback_name=loop_name)
            rec_loop.start()
            self.recorders.append(rec_loop)
            t2 = threading.Thread(target=self._direction_worker,
                                  args=(rec_loop, their, my, "me", "Partner"), daemon=True)
            t2.start()
            self.live_threads.append(t2)

        self._watch_recorders()

    def _watch_recorders(self):
        """Pegelanzeige aktualisieren und Thread-Fehler der Rekorder sichtbar machen."""
        if not self.live_running:
            self.level_bar["value"] = 0
            return
        if self.recorders:
            self.level_bar["value"] = min(0.2, self.recorders[0].level)
            for r in self.recorders:
                err = getattr(r, "error", None)
                if err is not None:
                    quelle = "Loopback" if r.loopback_name else "Mikrofon"
                    self._log(f"FEHLER in der {quelle}-Aufnahme: {err}")
                    r.error = None
        self.after(100, self._watch_recorders)

    def _stop_live(self):
        self.live_running = False
        for r in self.recorders:
            r.stop()
        for p in self.players.values():
            p.stop()
        self.recorders, self.players = [], {}
        self.btn_live.config(text="▶ Live-Übersetzung starten")
        self._log("Gestoppt.")

    def _direction_worker(self, recorder, src, tgt, player_key, label):
        """Nimmt Äußerungen entgegen, übersetzt und spricht sie aus."""
        import queue as q
        while self.live_running:
            try:
                utt = recorder.utterances.get(timeout=0.3)
            except q.Empty:
                continue
            try:
                text, _ = self.stt_live.transcribe(utt, language=src)
                if not text:
                    continue
                text_t = self.translator.translate(text, src, tgt)
                self._log(f"{label} ({src}): {text}\n   → ({tgt}): {text_t}")
                wav, rate = self.tts.synthesize(text_t, tgt)
                player = self.players.get(player_key) or self.players.get("me")
                if player:
                    player.play(wav, rate)
            except Exception as e:
                self._log(f"Fehler ({label}): {e}")

    # -------------------------------------------------------------- Utils --
    def _set_status(self, msg):
        self.after(0, lambda: self.status.set(msg))

    def _set_text(self, widget, text):
        def do():
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
        self.after(0, do)

    def _log(self, msg):
        def do():
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", msg + "\n")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
        self.after(0, do)


def _enable_dpi_awareness():
    """Scharfe Darstellung auf skalierten Windows-Displays."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    App().mainloop()
