# Live-Übersetzer (lokal & offline)

Stand-alone-Übersetzungssoftware in Python. Alle KI-Modelle laufen lokal auf diesem
Rechner — nach dem einmaligen Modell-Download ist keine Internetverbindung mehr nötig.

## Installation (neuer Rechner)

1. [Python 3.12](https://www.python.org/downloads/) installieren („Add python.exe
   to PATH" ankreuzen)
2. Dieses Repository klonen oder als ZIP herunterladen
3. **Installieren.bat** doppelklicken — richtet die Python-Umgebung ein und lädt
   alle KI-Modelle (mehrere GB, einmalig)

`venv/`, `models/` und `tools/` liegen bewusst **nicht** im Repository: GitHub
lehnt Dateien über 100 MB ab, und eine virtuelle Python-Umgebung ist ohnehin an
den Rechner gebunden, auf dem sie erzeugt wurde. Das Installationsskript stellt
alles reproduzierbar wieder her.

## Starten

Doppelklick auf **Start.bat** (oder: `venv\Scripts\python.exe app\main.py` für
Fehlermeldungen in der Konsole).

## Modi

### 1. Video / Datei
Videodatei wählen → transkribieren → übersetzen → vertonen → speichern.
Die Zielsprache wird automatisch aus der Systemsprache vorbelegt.

- **Eigene Stimme (Standard):** Häkchen „Meine eigene Stimme verwenden" — die App
  erstellt aus dem Video ein lokales Stimmprofil (XTTS-v2) und spricht die
  Übersetzung in **Ihrer** Stimme. Achtung: XTTS-Lizenz erlaubt nur
  **nicht-kommerzielle** Nutzung; Erzeugung dauert auf CPU mehrere Minuten.
- **Akzent entfernen:** Zielsprache = gesprochene Sprache (z. B. Deutsch→Deutsch).
- **Player:** ▶ Play / ⏸ Pause / ⏹ Stopp / ⏪ 10 s / 10 s ⏩ zum Anhören der Vertonung.
- **„Video mit neuer Tonspur speichern":** Bild bleibt unverändert, nur der Ton
  wird ersetzt (MP4).

### Einwilligung (DSGVO)
Beim ersten Start erscheint ein Einwilligungsdialog (Art. 6 DSGVO) — ohne aktive
Zustimmung startet die App nicht. Alle Daten werden ausschließlich lokal
verarbeitet. Widerruf jederzeit über den Button „Datenschutz" unten rechts.
Vor jedem Start des Live-Modus wird zusätzlich die Einwilligung aller
Gesprächsteilnehmer abgefragt.

### 2. Live: Gespräch & Anruf
Beide Richtungen parallel:
- **Mein Mikrofon** → wird in die Partnersprache übersetzt
- **Partner-Ton (Loopback)** = Systemton (Teams/Zoom/Video) → wird in meine Sprache
  übersetzt und auf meinen Kopfhörer ausgegeben

**Anruf-Modus (Teams/Zoom):** Zusätzlich braucht es das kostenlose
[VB-Audio Virtual Cable](https://vb-audio.com/Cable/) (Installation erfordert
Adminrechte → ggf. IT fragen). Dann:
1. In der App: „Ausgabe an Partner" = *CABLE Input*
2. In Teams/Zoom: Mikrofon = *CABLE Output*
3. Partner hört die übersetzte Stimme statt/neben der eigenen.

Ohne virtuelles Kabel funktioniert die Richtung „Partner → ich" trotzdem
(Loopback-Quelle wählen, z. B. das Headset).

## Rechtlicher Hinweis
Die Verarbeitung von Telefonaten/Gesprächen setzt die **Einwilligung aller
Beteiligten** voraus (§ 201 StGB — Vertraulichkeit des Wortes).

## Technik
- **Spracherkennung:** faster-whisper (OpenAI Whisper, lokal; „small" für Dateien,
  „base" für Live wegen Geschwindigkeit)
- **Übersetzung:** Argos Translate (lokal; Sprachpakete werden beim ersten Gebrauch
  einer Sprachrichtung einmalig heruntergeladen)
- **Sprachausgabe:** Piper (neuronale Stimmen, lokal; Fallback: Windows-SAPI)
- Modelle liegen unter `models\`, die Python-Umgebung unter `venv\`.
- Läuft unverändert auch unter Linux (dort `python3 app/main.py`; Loopback via
  PulseAudio-Monitor-Quellen). **iOS ist mit Python nicht machbar** — dafür wäre
  eine native Swift-App nötig; außerdem erlaubt iOS keinen Zugriff auf Anrufton.

## Bekannte Grenzen
- Simultanübersetzung hat systembedingt 2–5 s Versatz pro Satz.
- Die Stimme ist eine neutrale synthetische Stimme, nicht die geklonte eigene.
- Native Handy-Telefonate (SIM) können nicht abgegriffen werden — nur Anrufe, die
  über den PC laufen.
