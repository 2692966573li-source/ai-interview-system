@echo off
title AI Interview System Launcher

REM Double-click launcher: Windows opens .ps1 in Notepad by default,
REM so this .bat forwards the call to the real PowerShell script.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_project.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Please read the error message above.
  pause
)
