@echo off
REM Abre o dashboard local (Streamlit) no navegador.

setlocal
cd /d "%~dp0.."

set "UV=%APPDATA%\Python\Python314\Scripts\uv.exe"
if not exist "%UV%" set "UV=uv"

"%UV%" run streamlit run src\senado_sentinel\dashboard\app.py
