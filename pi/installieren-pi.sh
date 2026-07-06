#!/bin/bash
# ============================================================
#  Live-Uebersetzer auf dem Raspberry Pi einrichten
#  Getestet gedacht fuer: Pi 4 Model B (8 GB), Raspberry Pi OS 64-bit
#  Aufruf:   bash pi/installieren-pi.sh   (im geklonten Repo-Ordner)
# ============================================================
set -e
cd "$(dirname "$0")/.."

echo "[1/4] Systempakete (ffmpeg, Python-venv, PortAudio)..."
sudo apt update
sudo apt install -y python3-venv python3-dev ffmpeg libportaudio2

echo "[2/4] Python-Umgebung..."
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install --retries 10 -r pi/requirements-pi.txt

echo "[3/4] Whisper-Basismodell vorladen (145 MB)..."
venv/bin/python - <<'EOF'
from faster_whisper import WhisperModel
import os
WhisperModel("base", device="cpu", compute_type="int8",
             download_root=os.path.join("models", "whisper"))
print("Whisper base bereit.")
EOF

echo "[4/4] Autostart-Dienst einrichten (startet bei jedem Boot)..."
sudo tee /etc/systemd/system/uebersetzer.service >/dev/null <<EOF
[Unit]
Description=Live-Uebersetzer Web-Server
After=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)/app
Environment=WHISPER_MODELL=base
ExecStart=$(pwd)/venv/bin/python web_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now uebersetzer.service

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=============================================================="
echo "  Fertig! Der Uebersetzer laeuft jetzt dauerhaft auf diesem Pi."
echo "  Am iPhone/Android/PC im selben Netz oeffnen:"
echo "      http://$IP:8710"
echo "  oder  http://$(hostname).local:8710   (iPhone/Safari)"
echo "  Status pruefen:  sudo systemctl status uebersetzer"
echo "=============================================================="
