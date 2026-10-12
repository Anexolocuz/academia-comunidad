@echo off
chcp 65001 >nul
title Instalador de la Academia
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (where python >nul 2>nul && (set PY=python) || set PY=)
if "%PY%"=="" (
  echo No encontre Python. Instalando Python 3.12 con winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Cierra esta ventana y vuelve a abrir INSTALAR.bat para continuar.
  pause
  exit /b
)
%PY% instalar.py %*
pause
