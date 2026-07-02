"""Headless-Test des Live-Modus: spielt selftest_de.wav ueber die Lautsprecher ab,
waehrend die Loopback-Erfassung mithoert -> prueft Segmentierung + Pipeline.
"""
import sys
import threading
import time
import wave

import numpy as np
import sounddevice as sd

import audio as audio_mod
import engine


def main():
    loops = audio_mod.list_loopback_sources()
    print("Loopback-Quellen:", loops)
    if not loops:
        print("FEHLER: keine Loopback-Quelle")
        return 1
    # Standard-Ausgabegeraet ermitteln und passende Loopback-Quelle waehlen
    default_out = sd.query_devices(kind="output")["name"]
    print("Standard-Ausgabe:", default_out)
    src = next((l for l in loops if l.split("(")[0].strip() in default_out
                or default_out.split("(")[0].strip() in l), loops[0])
    print("Gewaehlte Loopback-Quelle:", src)

    rec = audio_mod.UtteranceRecorder(loopback_name=src)
    rec.start()
    time.sleep(1.0)

    with wave.open("selftest_de.wav", "rb") as wf:
        rate = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    wav = data.astype(np.float32) / 32768.0
    print(f"Spiele {len(wav)/rate:.1f} s Testaudio ab...")

    levels = []
    def monitor():
        for _ in range(80):
            levels.append(rec.level)
            time.sleep(0.1)
    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    sd.play(wav, rate, blocking=True)
    print("Wiedergabe fertig, warte auf Segmentierung...")
    time.sleep(2.5)
    rec.stop()
    print(f"Max. Pegel waehrend Wiedergabe: {max(levels):.4f} (Schwelle: {rec.silence_threshold})")

    try:
        utt = rec.utterances.get_nowait()
    except Exception:
        print("FEHLER: keine Aeusserung erkannt!")
        return 1
    print(f"Aeusserung erkannt: {len(utt)/engine.SAMPLE_RATE:.1f} s")

    stt = engine.SpeechToText(model_size="base")
    text, lang = stt.transcribe(utt, language="de")
    print(f"Erkannt ({lang}): {text}")
    tr = engine.Translator()
    print("Uebersetzt:", tr.translate(text, "de", "en"))
    print("LIVETEST ERFOLGREICH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
