@echo off
cd /d "%~dp0"
set AI_DEVICE=cuda
".venv311\Scripts\python.exe" main.py web
pause
