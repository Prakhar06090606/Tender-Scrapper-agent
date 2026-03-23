@echo off
title Tender Agent Backend
cd /d "%~dp0"
call venv\Scripts\activate
echo Starting Tender Agent...
py run.py
pause
