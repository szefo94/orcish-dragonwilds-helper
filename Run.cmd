@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto bootstrap
if not exist "data\setup-ready.flag" goto bootstrap
goto ready
:bootstrap
(
 echo First run: preparing the local environment...
 call "%~dp0Setup.cmd" install
 if errorlevel 1 (
  echo Setup did not finish. Install Python 3.12 64-bit with the Python launcher and Tcl/Tk, then run Run.cmd again.
  pause
  exit /b 1
 )
)
:ready
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
