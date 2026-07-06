# Live-Übersetzer auf dem Raspberry Pi 4 (8 GB)

Der Pi übernimmt die Server-Rolle: Er läuft dauerhaft und lautlos, alle Geräte
im Heimnetz (iPhone/Safari, Android/Chrome, PC-Browser) nutzen dieselbe
Web-Oberfläche. Die KI läuft vollständig lokal auf dem Pi — keine Cloud.

## Voraussetzungen

- Raspberry Pi 4 Model B mit 8 GB (4 GB geht knapp, 8 GB empfohlen)
- **Raspberry Pi OS 64-bit** (wichtig — die KI-Pakete brauchen ARM64)
- Netzwerk (LAN-Kabel empfohlen, WLAN geht)
- ~3 GB frei auf der SD-Karte; eine schnelle SD-Karte (A2) oder SSD hilft spürbar

## Installation

```bash
git clone https://github.com/armhana/translate.git
cd translate
bash pi/installieren-pi.sh
```

Das Skript installiert Systempakete (ffmpeg u. a.), richtet die
Python-Umgebung ein, lädt das Whisper-Modell vor und registriert einen
**Autostart-Dienst** — der Übersetzer startet ab dann bei jedem Einschalten
des Pi automatisch.

## Vom iPhone aufrufen

Im Safari öffnen (Pi und iPhone im selben Netz):

```
http://raspberrypi.local:8710      (Standard-Hostname)
http://<IP-des-Pi>:8710            (alternativ, IP zeigt das Skript an)
```

Dann *Teilen → Zum Home-Bildschirm* — die Oberfläche liegt danach als
App-Symbol auf dem iPhone.

## Unterschiede zur PC-Version

| | PC (Windows) | Raspberry Pi 4 |
|---|---|---|
| Spracherkennung | Whisper „small" | Whisper „base" (schneller Standard; per `WHISPER_MODELL=small` im Dienst änderbar) |
| Eigene Stimme (XTTS) | ✅ | ❌ — auf dem Pi um ein Vielfaches zu langsam; es spricht die neutrale Piper-Stimme |
| Tempo (1 Min. Video) | ~1–3 Min. | grob ~5–15 Min. — der Pi ist kein Rechenmonster |
| Betrieb | bei Bedarf starten | läuft dauerhaft als Dienst |

## Dienst verwalten

```bash
sudo systemctl status uebersetzer    # Läuft er?
sudo systemctl restart uebersetzer   # Neu starten
journalctl -u uebersetzer -f         # Log ansehen
```

## Hinweis

Dieses Setup wurde auf einem Windows-PC entwickelt; die Pi-Installation
selbst konnte dort nicht ausgeführt werden. Die verwendeten Pakete
(faster-whisper/ctranslate2, Argos, Piper, FastAPI) bieten offizielle
ARM64-Unterstützung — Piper stammt sogar aus dem Raspberry-Pi-Umfeld.
Falls beim ersten Lauf etwas hakt: `journalctl -u uebersetzer -f` zeigt die
Ursache.
