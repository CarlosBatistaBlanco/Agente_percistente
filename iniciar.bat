@echo off
REM Inicia el agente. Para que arranque solo con Windows, pon un acceso directo a este
REM archivo en:  Win+R  ->  shell:startup
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
if not exist .env copy .env.example .env
start "" http://127.0.0.1:5000
.venv\Scripts\python agente.py
pause
