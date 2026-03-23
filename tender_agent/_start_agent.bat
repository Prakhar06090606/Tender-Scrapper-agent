@echo off
cd /d "C:/Program Files (x86)/Edubild/tender_agent"
call "C:\Program Files (x86)\Edubild\tender_agent\venv\Scripts\activate.bat"
py run.py >> "C:\Program Files (x86)\Edubild\tender_agent\agent.log" 2>&1