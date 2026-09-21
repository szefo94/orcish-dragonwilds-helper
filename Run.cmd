@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo First run Setup.cmd and choose 1 ^(Install^).
 pause
 exit /b 1
)
".venv\Scripts\python.exe" src\orcpresser\app.py
if errorlevel 1 pause
