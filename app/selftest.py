"""Selbsttest der kompletten Pipeline ohne echtes Video:
TTS erzeugt deutschen Testsatz -> Whisper transkribiert ihn -> Argos uebersetzt.
Laedt beim ersten Lauf die Modelle herunter.
"""
import sys
import numpy as np
import engine

SATZ = "Guten Tag, dies ist ein Test der lokalen Übersetzungssoftware."

def main():
    tts = engine.TextToSpeech()
    print("1) Sprachausgabe (Piper, laedt ggf. deutsche Stimme ~65 MB)...")
    wav, rate = tts.synthesize(SATZ, "de")
    print(f"   OK: {len(wav)/rate:.1f} s Audio bei {rate} Hz")
    engine.save_wav("selftest_de.wav", wav, rate)

    print("2) Spracherkennung (Whisper 'base', laedt ggf. Modell ~145 MB)...")
    stt = engine.SpeechToText(model_size="base")
    # auf 16 kHz bringen
    if rate != engine.SAMPLE_RATE:
        idx = np.linspace(0, len(wav) - 1, int(len(wav) * engine.SAMPLE_RATE / rate)).astype(int)
        wav16 = wav[idx]
    else:
        wav16 = wav
    text, lang = stt.transcribe(wav16)
    print(f"   Erkannt ({lang}): {text}")

    print("3) Uebersetzung de->en (Argos, laedt ggf. Paket ~100 MB)...")
    tr = engine.Translator()
    uebersetzt = tr.translate(text, "de", "en")
    print(f"   Uebersetzt: {uebersetzt}")

    print("4) Englische Vertonung (laedt ggf. englische Stimme ~65 MB)...")
    wav_en, rate_en = tts.synthesize(uebersetzt, "en")
    engine.save_wav("selftest_en.wav", wav_en, rate_en)
    print(f"   OK: {len(wav_en)/rate_en:.1f} s Audio -> selftest_en.wav")
    print("SELBSTTEST ERFOLGREICH")

if __name__ == "__main__":
    sys.exit(main())
