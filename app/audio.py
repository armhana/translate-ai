"""Audio-Ein-/Ausgabe: Geraeteliste, Mikrofon-Streams mit Sprechpausen-Erkennung,
Loopback-Aufnahme des Systemtons (Gespraechspartner in Teams/Zoom) und Wiedergabe.
"""
import queue
import threading

import numpy as np
import sounddevice as sd

from engine import SAMPLE_RATE

# Gesetzt, solange die App selbst Audio abspielt. Die Loopback-Erfassung pausiert
# dann, damit die eigene Sprachausgabe nicht erneut uebersetzt wird (Echo-Schleife).
PLAYBACK_ACTIVE = threading.Event()
_playback_count = 0
_playback_lock = threading.Lock()


def _playback_begin():
    global _playback_count
    with _playback_lock:
        _playback_count += 1
        PLAYBACK_ACTIVE.set()


def _playback_end():
    global _playback_count
    with _playback_lock:
        _playback_count = max(0, _playback_count - 1)
        if _playback_count == 0:
            PLAYBACK_ACTIVE.clear()


def list_input_devices():
    """[(index, name)] aller Aufnahmegeraete."""
    devices = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            devices.append((i, d["name"]))
    return devices


def list_output_devices():
    """[(index, name)] aller Wiedergabegeraete."""
    devices = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            devices.append((i, d["name"]))
    return devices


def list_loopback_sources():
    """Systemton-Quellen (was der Gespraechspartner sagt) via WASAPI-Loopback."""
    try:
        import soundcard as sc
        return [m.name for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    except Exception:
        return []


class UtteranceRecorder:
    """Nimmt von einem Geraet auf und liefert ganze Aeusserungen:
    Audio wird gesammelt, bis eine Sprechpause (Stille) erkannt wird,
    dann landet der Abschnitt als float32-Array in der Queue.
    """

    def __init__(self, device_index=None, loopback_name=None,
                 silence_threshold=0.01, silence_seconds=0.8, max_seconds=15):
        self.device_index = device_index
        self.loopback_name = loopback_name  # gesetzt => Systemton statt Mikrofon
        self.silence_threshold = silence_threshold
        self.silence_seconds = silence_seconds
        self.max_seconds = max_seconds
        self.utterances = queue.Queue()
        self.level = 0.0  # aktueller Pegel fuer die GUI
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self.error = None
        target = self._run_loopback if self.loopback_name else self._run_mic
        self._thread = threading.Thread(target=self._guarded, args=(target,), daemon=True)
        self._thread.start()

    def _guarded(self, target):
        """Thread-Fehler nicht verschlucken, sondern fuer die GUI festhalten."""
        try:
            target()
        except Exception as e:
            self.error = e

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    # ---- gemeinsame Segmentierungslogik ----
    def _segment_loop(self, read_block):
        """read_block() liefert je Aufruf einen float32-Mono-Block bei 16 kHz."""
        buffer = []
        silent_blocks = 0
        voiced = False
        block_dur = 0.05
        silence_blocks_needed = int(self.silence_seconds / block_dur)
        max_blocks = int(self.max_seconds / block_dur)

        while not self._stop.is_set():
            block = read_block()
            if block is None:
                continue
            if self.loopback_name and PLAYBACK_ACTIVE.is_set():
                # Eigene Sprachausgabe laeuft: nicht mithoeren, laufende Aufnahme verwerfen
                buffer, voiced, silent_blocks = [], False, 0
                continue
            rms = float(np.sqrt(np.mean(block ** 2))) if block.size else 0.0
            self.level = rms
            is_voice = rms > self.silence_threshold
            if is_voice:
                voiced = True
                silent_blocks = 0
            elif voiced:
                silent_blocks += 1
            if voiced:
                buffer.append(block)
            end_of_utterance = voiced and (
                silent_blocks >= silence_blocks_needed or len(buffer) >= max_blocks
            )
            if end_of_utterance:
                audio = np.concatenate(buffer)
                buffer, voiced, silent_blocks = [], False, 0
                if audio.size > SAMPLE_RATE // 2:  # kuerzer als 0,5 s: ignorieren
                    self.utterances.put(audio)

    def _run_mic(self):
        blocksize = int(SAMPLE_RATE * 0.05)
        q = queue.Queue()

        def callback(indata, frames, time_info, status):
            q.put(indata[:, 0].copy())

        def read_block():
            try:
                return q.get(timeout=0.2)
            except queue.Empty:
                return None

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            device=self.device_index, blocksize=blocksize,
                            callback=callback):
            self._segment_loop(read_block)

    def _run_loopback(self):
        # soundcard nutzt Windows-COM: muss in jedem neuen Thread initialisiert werden,
        # sonst RuntimeError 0x800401f0 (CoInitialize has not been called).
        import ctypes
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0)
        except Exception:
            pass
        import soundcard as sc
        mic = next(m for m in sc.all_microphones(include_loopback=True)
                   if m.name == self.loopback_name)
        native_rate = 48000
        blocksize = int(native_rate * 0.05)
        step = native_rate // SAMPLE_RATE  # 48k -> 16k: jeden 3. Wert nehmen

        with mic.recorder(samplerate=native_rate, channels=1, blocksize=blocksize) as rec:
            def read_block():
                data = rec.record(numframes=blocksize)[:, 0]
                return data[::step].astype(np.float32)
            self._segment_loop(read_block)


class SeekablePlayer:
    """Audio-Player mit Play/Pause/Stopp und Spulen (fuer den Video-Tab)."""

    def __init__(self):
        self.audio = np.zeros(0, dtype=np.float32)
        self.rate = SAMPLE_RATE
        self.pos = 0
        self.playing = False
        self._stream = None
        self._lock = threading.Lock()

    def load(self, audio: np.ndarray, rate: int):
        self.stop()
        with self._lock:
            self.audio = audio.astype(np.float32)
            self.rate = rate
            self.pos = 0

    def _ensure_stream(self):
        if self._stream is None:
            def callback(outdata, frames, time_info, status):
                with self._lock:
                    if not self.playing:
                        outdata.fill(0)
                        return
                    end = min(self.pos + frames, len(self.audio))
                    chunk = self.audio[self.pos:end]
                    outdata[:len(chunk), 0] = chunk
                    outdata[len(chunk):, 0] = 0
                    self.pos = end
                    if self.pos >= len(self.audio):
                        self.playing = False
            self._stream = sd.OutputStream(samplerate=self.rate, channels=1,
                                           dtype="float32", callback=callback)
            self._stream.start()

    def play(self):
        if not len(self.audio):
            return
        with self._lock:
            if self.pos >= len(self.audio):
                self.pos = 0
        self._ensure_stream()
        self.playing = True

    def pause(self):
        self.playing = False

    def stop(self):
        self.playing = False
        with self._lock:
            self.pos = 0
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def seek(self, seconds):
        """Relativ spulen, z.B. seek(-10) oder seek(+10)."""
        with self._lock:
            self.pos = int(min(max(0, self.pos + seconds * self.rate), len(self.audio)))

    def position(self):
        """(aktuelle Sekunde, Gesamtsekunden)"""
        with self._lock:
            return self.pos / self.rate, len(self.audio) / self.rate


class Player:
    """Serielle Wiedergabe-Warteschlange auf ein bestimmtes Ausgabegeraet."""

    def __init__(self, device_index=None):
        self.device_index = device_index
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def play(self, audio: np.ndarray, rate: int):
        self._q.put((audio, rate))

    def stop(self):
        self._stop.set()
        self._q.put(None)

    def _run(self):
        while not self._stop.is_set():
            item = self._q.get()
            if item is None:
                break
            audio, rate = item
            _playback_begin()
            try:
                sd.play(audio, rate, device=self.device_index, blocking=True)
            except Exception:
                pass
            finally:
                _playback_end()
