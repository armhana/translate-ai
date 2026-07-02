@echo off
rem Live-Uebersetzer starten (ohne Konsolenfenster waere pythonw, mit Konsole python)
cd /d "%~dp0app"
"%~dp0venv\Scripts\pythonw.exe" main.py
