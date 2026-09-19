@echo off
REM Double-click to start knode (server + browser)
cd /d "%~dp0"
python knode.py %*
if errorlevel 1 pause
