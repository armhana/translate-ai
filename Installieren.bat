@echo off
rem ============================================================
rem  Live-Uebersetzer: Einmalige Einrichtung auf einem neuen PC
rem  Voraussetzung: Python 3.12 (python.org, "Add to PATH" aktivieren)
rem  Erzeugt venv/, laedt Bibliotheken, FFmpeg-DLLs und das
rem  Stimmklon-Modell. Dauer je nach Netz 15-60 Minuten.
rem ============================================================
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden. Bitte Python 3.12 von python.org installieren.
    pause & exit /b 1
)

echo [1/5] Virtuelle Python-Umgebung anlegen...
python -m venv venv || (echo venv-Anlage fehlgeschlagen & pause & exit /b 1)
venv\Scripts\python -m pip install --upgrade pip

echo [2/5] Bibliotheken installieren (mehrere GB, bitte warten)...
venv\Scripts\pip install --retries 10 -r requirements.txt || (echo pip fehlgeschlagen & pause & exit /b 1)

echo [3/5] FFmpeg-DLLs laden (fuer das Stimmklon-Modul)...
if not exist tools mkdir tools
curl -L -C - --retry 20 --retry-all-errors -o tools\ffmpeg-shared.zip https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl-shared.zip
tar -xf tools\ffmpeg-shared.zip -C tools
copy /Y tools\ffmpeg-master-latest-win64-gpl-shared\bin\*.dll venv\Lib\site-packages\torchcodec\ >nul

echo [4/5] Stimmklon-Modell XTTS-v2 laden (1,9 GB, mit Fortsetzung bei Abbruch)...
set "DEST=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2"
if not exist "%DEST%" mkdir "%DEST%"
for %%f in (config.json vocab.json hash.md5 speakers_xtts.pth) do (
    curl -sL -C - --retry 20 --retry-all-errors -o "%DEST%\%%f" "https://huggingface.co/coqui/XTTS-v2/resolve/v2.0.3/%%f"
)
:modelloop
curl -L -C - --retry 20 --retry-all-errors -o "%DEST%\model.pth" "https://huggingface.co/coqui/XTTS-v2/resolve/v2.0.3/model.pth"
if errorlevel 1 (
    echo Download unterbrochen, setze fort...
    timeout /t 3 >nul
    goto modelloop
)

echo [5/5] Fertig! App starten mit Start.bat
echo Hinweis: Whisper-, Argos- und Piper-Modelle laedt die App beim
echo ersten Gebrauch der jeweiligen Funktion automatisch nach.
pause
