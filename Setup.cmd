@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Orcish Dragonwilds Helper - setup
set "PY=.venv\Scripts\python.exe"
set "ACTION=%~1"
if not "%ACTION%"=="" goto dispatch

:menu
cls
echo.
echo   ORCISH DRAGONWILDS HELPER  -  setup and maintenance
echo   ------------------------------------
echo   1  Install / repair / update     first run, and after copying a new version
echo   2  Enable GPU (DirectML)         optional; switches the OCR runtime
echo   3  Back to CPU runtime           undo 2
echo   4  Start once in SAFE mode       defaults, learned data not loaded
echo   5  Run self-tests
echo   6  Clean up old files            backups, old zips, caches - shows what first
echo   Q  Quit
echo.
set "ACTION="
set /p "ACTION=  Choose: "
if "%ACTION%"=="1" set "ACTION=install"
if "%ACTION%"=="2" set "ACTION=gpu"
if "%ACTION%"=="3" set "ACTION=cpu"
if "%ACTION%"=="4" set "ACTION=safe"
if "%ACTION%"=="5" set "ACTION=test"
if "%ACTION%"=="6" set "ACTION=clean"
if /i "%ACTION%"=="q" exit /b 0

:dispatch
if /i "%ACTION%"=="install" goto install
if /i "%ACTION%"=="gpu" goto gpu
if /i "%ACTION%"=="cpu" goto cpu
if /i "%ACTION%"=="safe" goto safe
if /i "%ACTION%"=="test" goto test
if /i "%ACTION%"=="clean" goto clean
echo Unknown option "%ACTION%". Use: Setup.cmd [install^|gpu^|cpu^|safe^|test^|clean]
goto end_fail

:install
where py >nul 2>nul
if errorlevel 1 goto nopython
py -3.12 -c "import sys; assert sys.maxsize > 2**32" >nul 2>nul
if errorlevel 1 goto nopython
if not exist "%PY%" py -3.12 -m venv .venv
if errorlevel 1 goto failed
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto failed
"%PY%" -m pip install -r src\requirements.txt
if errorlevel 1 goto failed
rem Keep the GPU runtime if it was chosen before (requirements reinstall the CPU one).
if exist "data\runtime-gpu.flag" call :use_gpu
if errorlevel 1 goto failed
"%PY%" src\orcpresser\maintenance.py migrate
"%PY%" src\orcpresser\maintenance.py runtime
echo.
echo   Ready. Start Orcish Dragonwilds Helper with Run.cmd.
goto end_ok

:gpu
if not exist "%PY%" goto noinstall
call :use_gpu
if errorlevel 1 goto failed
if not exist data mkdir data
echo gpu> "data\runtime-gpu.flag"
"%PY%" src\orcpresser\maintenance.py runtime
echo   Enable "GPU - DirectML" in the app (AUTO PRESSER tab, section 03).
goto end_ok

:use_gpu
"%PY%" -m pip uninstall -y onnxruntime >nul 2>nul
"%PY%" -m pip install --force-reinstall --no-deps "onnxruntime-directml>=1.17,<2"
if errorlevel 1 exit /b 1
"%PY%" -c "import onnxruntime as o; assert 'DmlExecutionProvider' in o.get_available_providers()"
exit /b %errorlevel%

:cpu
if not exist "%PY%" goto noinstall
"%PY%" -m pip uninstall -y onnxruntime-directml onnxruntime
"%PY%" -m pip install onnxruntime
if errorlevel 1 goto failed
if exist "data\runtime-gpu.flag" del "data\runtime-gpu.flag"
"%PY%" src\orcpresser\maintenance.py runtime
goto end_ok

:safe
if not exist "%PY%" goto noinstall
set ORC_SAFE=1
"%PY%" src\orcpresser\app.py
goto end_ok

:test
if not exist "%PY%" goto noinstall
"%PY%" src\orcpresser\maintenance.py test
if errorlevel 1 goto failed
goto end_ok

:clean
if not exist "%PY%" goto noinstall
"%PY%" src\orcpresser\maintenance.py clean
goto end_ok

:nopython
echo   Install Python 3.12 64-bit from python.org (with the Python launcher and Tcl/Tk), then run Setup.cmd again.
goto end_fail
:noinstall
echo   Not installed yet: run Setup.cmd and choose 1 first.
goto end_fail
:failed
echo.
echo   Something failed - read the messages above. Running option 1 again usually repairs it.
goto end_fail

:end_ok
if "%~1"=="" pause
exit /b 0
:end_fail
if "%~1"=="" pause
exit /b 1
