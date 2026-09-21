@echo off
rem Applies the newest OrcPresser_<version>.zip found in this folder (see src\orcpresser\updater.py).
rem Everything runs inside one parenthesized block: cmd reads the whole block before running it,
rem so the updater can safely replace this very file.
(
 setlocal
 cd /d "%~dp0"
 title Orcish Dragonwilds Helper - update
 if not exist ".venv\Scripts\python.exe" (
  echo Not installed yet: run Setup.cmd and choose 1 first.
 ) else (
  ".venv\Scripts\python.exe" src\orcpresser\updater.py %*
 )
 pause
 exit /b
)
