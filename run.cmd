@echo off
rem Double-click or run from a terminal. Extra args are passed on, e.g.  run.cmd -NoBrowser
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
if errorlevel 1 pause
