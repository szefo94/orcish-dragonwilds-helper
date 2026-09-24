@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo First run Setup.cmd and choose 1 ^(Install^).
 pause
 exit /b 1
)
if not exist "data" mkdir "data"
>>"data\launcher.log" echo [%date% %time%] START python app
".venv\Scripts\python.exe" -X faulthandler src\orcpresser\app.py
set "code=!errorlevel!"
>>"data\launcher.log" echo [%date% %time%] EXIT code=!code!
if not "!code!"=="0" (
 echo.
 echo Helper exited unexpectedly with code !code!.
 echo See data\orcpresser.log, data\orcpresser-crash.log and data\launcher.log.
 pause
)
exit /b !code!
