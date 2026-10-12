@echo off
chcp 65001 >nul
title Actualizar la Academia
cd /d "%~dp0"
git pull --ff-only || (echo No se pudo actualizar: revisa que tengas Git y conexion. & pause & exit /b)
rem Detiene la Academia que esta corriendo (sin wmic, que Windows 11 ya no trae) y la vuelve a abrir
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*servidor.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
start "" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Academia.vbs"
echo Actualizada y reiniciada. Tus datos no se tocaron.
pause
