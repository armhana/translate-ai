"""KI-Pipeline: Spracherkennung (Whisper), Uebersetzung (Argos), Sprachausgabe (Piper/SAPI).

Alles laeuft lokal/offline, nachdem die Modelle einmalig heruntergeladen wurden.
"""
import io
import os
import threading
import wave

# Firmen-Proxy mit TLS-Inspektion: Windows-Zertifikatspeicher fuer alle
# HTTPS-Downloads (Modelle) verwenden, sonst scheitern sie an SSL-Fehlern.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import numpy as np

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

SAMPLE_RATE = 16000  # Whisper erwartet 16 kHz mono


class SpeechToText:
    """faster-whisper, lazy geladen, threadsicher."""

    def __init__(self, model_size="small"):
        self.model_size = model_size
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size, device="cpu", compute_type="int8",
                download_root=os.path.join(MODELS_DIR, "whisper"),
            )
        return self._model

    def transcribe(self, audio: np.ndarray, language=None):
        """audio: float32 mono 16 kHz. Gibt (text, erkannte_sprache) zurueck."""
        model = self._ensure_model()
        with self._lock:
            segments, info = model.transcribe(
                audio, language=language, vad_filter=True, beam_size=5,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
        return text, info.language

    def transcribe_file(self, path, language=None, on_segment=None):
        """Transkribiert eine Video-/Audiodatei (Dekodierung uebernimmt PyAV)."""
        model = self._ensure_model()
        with self._lock:
            segments, info = model.transcribe(path, language=language, vad_filter=True)
            parts = []
            for s in segments:
                parts.append(s.text.strip())
                if on_segment:
                    on_segment(s.start, s.end, s.text.strip())
        return " ".join(parts).strip(), info.language


class Translator:
    """Argos Translate, offline. Sprachpakete werden bei Bedarf einmalig geladen."""

    def __init__(self):
        self._installed = set()
        self._lock = threading.Lock()

    def _ensure_pair(self, src, tgt):
        key = (src, tgt)
        if key in self._installed:
            return True
        with self._lock:
            if key in self._installed:
                return True
            import argostranslate.package
            import argostranslate.translate
            installed = argostranslate.translate.get_installed_languages()
            codes = {l.code for l in installed}
            if src in codes and tgt in codes:
                src_lang = next(l for l in installed if l.code == src)
                if any(t.to_lang.code == tgt for t in src_lang.translations_from):
                    self._installed.add(key)
                    return True
            # Paket fehlt: einmalig herunterladen (braucht Internet)
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            pkg = next((p for p in available if p.from_code == src and p.to_code == tgt), None)
            if pkg is None:
                return False
            argostranslate.package.install_from_path(pkg.download())
            self._installed.add(key)
            return True

    def translate(self, text, src, tgt):
        if not text or src == tgt:
            return text
        if not self._ensure_pair(src, tgt):
            raise RuntimeError(f"Kein Uebersetzungspaket fuer {src}->{tgt} verfuegbar")
        import argostranslate.translate
        return argostranslate.translate.translate(text, src, tgt)


# Piper-Stimmen je Sprache (werden bei Bedarf von HuggingFace geladen, danach offline)
PIPER_VOICES = {
    "de": "de_DE-thorsten-medium",
    "en": "en_US-lessac-medium",
    "fr": "fr_FR-siwis-medium",
    "es": "es_ES-davefx-medium",
    "it": "it_IT-riccardo-x_low",
    "pt": "pt_BR-faber-medium",
    "nl": "nl_BE-nathalie-medium",
    "pl": "pl_PL-darkman-medium",
    "ru": "ru_RU-irina-medium",
    "tr": "tr_TR-fettah-medium",
    "zh": "zh_CN-huayan-medium",
}


class TextToSpeech:
    """Piper (neuronale Stimme, offline). Fallback: Windows-SAPI via pyttsx3."""

    def __init__(self):
        self._piper_voices = {}
        self._lock = threading.Lock()
        self._piper_ok = None

    def _piper_available(self):
        if self._piper_ok is None:
            try:
                import piper  # noqa: F401
                self._piper_ok = True
            except Exception:
                self._piper_ok = False
        return self._piper_ok

    def _get_piper_voice(self, lang):
        name = PIPER_VOICES.get(lang, PIPER_VOICES["en"])
        if name in self._piper_voices:
            return self._piper_voices[name]
        with self._lock:
            if name in self._piper_voices:
                return self._piper_voices[name]
            from piper import PiperVoice
            voice_dir = os.path.join(MODELS_DIR, "piper")
            os.makedirs(voice_dir, exist_ok=True)
            onnx_path = os.path.join(voice_dir, f"{name}.onnx")
            if not (os.path.exists(onnx_path) and os.path.exists(onnx_path + ".json")):
                self._download_piper_voice(name, voice_dir)
            voice = PiperVoice.load(onnx_path)
            self._piper_voices[name] = voice
            return voice

    @staticmethod
    def _download_piper_voice(name, voice_dir):
        """Einmaliger Download einer Piper-Stimme von HuggingFace."""
        import urllib.request
        lang_code = name.split("-")[0]           # z.B. de_DE
        short = lang_code.split("_")[0]          # z.B. de
        base = (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            f"{short}/{lang_code}/{name.split('-')[1]}/{name.split('-')[2]}"
        )
        for ext in (".onnx", ".onnx.json"):
            url = f"{base}/{name}{ext}"
            dest = os.path.join(voice_dir, f"{name}{ext}")
            if os.path.exists(dest) and ext == ".onnx":
                continue  # grosse Datei bereits vorhanden
            tmp = dest + ".part"
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, dest)  # nur vollstaendige Downloads uebernehmen

    def synthesize(self, text, lang):
        """Gibt (float32-Array, Samplerate) zurueck."""
        if not text:
            return np.zeros(0, dtype=np.float32), SAMPLE_RATE
        if self._piper_available():
            try:
                return self._synth_piper(text, lang)
            except Exception:
                pass
        return self._synth_sapi(text, lang)

    def _synth_piper(self, text, lang):
        voice = self._get_piper_voice(lang)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return data.astype(np.float32) / 32768.0, rate

    def _synth_sapi(self, text, lang):
        """Fallback: Windows-Bordstimme ueber pyttsx3, in WAV-Datei gerendert."""
        import tempfile
        import pyttsx3
        eng = pyttsx3.init()
        # Passende Sprachstimme suchen (Windows-Voice-IDs enthalten z.B. "de-DE")
        want = f"{lang.lower()}-"
        for v in eng.getProperty("voices"):
            haystack = f"{v.id} {v.name}".lower()
            if want in haystack or f"_{lang.lower()}" in haystack:
                eng.setProperty("voice", v.id)
                break
        tmp = os.path.join(tempfile.gettempdir(), "uebersetzer_tts.wav")
        eng.save_to_file(text, tmp)
        eng.runAndWait()
        with wave.open(tmp, "rb") as wf:
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            channels = wf.getnchannels()
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)
        return data, rate


class VoiceCloneTTS:
    """Spricht Text in der EIGENEN Stimme des Nutzers (XTTS-v2, lokal).

    Referenz ist ein kurzer Sprachausschnitt (z.B. aus dem eigenen Video).
    Lizenzhinweis: Coqui Public Model License — nur nicht-kommerzielle Nutzung.
    """

    def __init__(self):
        self._tts = None
        self._lock = threading.Lock()

    def available(self):
        try:
            import TTS  # noqa: F401  (Paket coqui-tts)
            return True
        except ImportError:
            return False

    def _ensure_model(self):
        if self._tts is None:
            os.environ.setdefault("COQUI_TOS_AGREED", "1")
            # torchaudio>=2.9 laedt Audio ueber torchcodec, dessen DLLs unter
            # Windows unzuverlaessig laden. Wir brauchen nur WAV-Referenzen:
            # torchaudio.load auf soundfile umleiten.
            import soundfile
            import torch
            import torchaudio

            def _sf_load(path, *args, **kwargs):
                data, sr = soundfile.read(str(path), dtype="float32", always_2d=True)
                return torch.from_numpy(data.T), sr

            torchaudio.load = _sf_load
            from TTS.api import TTS as CoquiTTS
            self._tts = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2")
        return self._tts

    def synthesize(self, text, lang, speaker_wav_path):
        """Gibt (float32-Array, Samplerate) in der geklonten Stimme zurueck."""
        with self._lock:
            tts = self._ensure_model()
            wav = tts.tts(text=text, speaker_wav=speaker_wav_path, language=lang)
        return np.asarray(wav, dtype=np.float32), 24000  # XTTS liefert 24 kHz


def extract_voice_sample(media_path, out_wav, max_seconds=25):
    """Schneidet die ersten Sprech-Sekunden aus einem Video als Stimmreferenz."""
    import av
    container = av.open(media_path)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks = []
    total = 0
    for frame in container.decode(audio=0):
        for f in resampler.resample(frame):
            arr = f.to_ndarray().flatten().astype(np.float32) / 32768.0
            chunks.append(arr)
            total += len(arr)
        if total >= max_seconds * SAMPLE_RATE:
            break
    container.close()
    audio = np.concatenate(chunks)[: max_seconds * SAMPLE_RATE]
    save_wav(out_wav, audio, SAMPLE_RATE)
    return out_wav


def mux_video_with_audio(video_path, audio_wav, out_path):
    """Originalvideo (Bild unveraendert) mit neuer Tonspur als MP4 speichern."""
    import shutil
    import subprocess
    # System-ffmpeg bevorzugen (Raspberry Pi/Linux), sonst mitgeliefertes Binary
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-i", video_path, "-i", audio_wav,
           "-map", "0:v", "-map", "1:a", "-c:v", "copy",
           "-c:a", "aac", "-shortest", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler: {result.stderr[-400:]}")
    return out_path


def save_wav(path, audio: np.ndarray, rate: int):
    """float32-Audio als 16-bit-WAV speichern."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
