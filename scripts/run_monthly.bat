@echo off
REM Executa o pipeline mensal completo (update -> detect -> report) e sai com
REM codigo de erro se falhar, para o Windows Task Scheduler registrar a falha.
REM
REM Para agendar (rodar uma vez, ajustando o caminho se necessario):
REM   schtasks /Create /SC MONTHLY /D 5 /TN "VigiaPublico_Mensal" /TR "\"%~dp0run_monthly.bat\"" /ST 03:00
REM
REM Isso agenda para todo dia 5 do mes, as 03:00, processando o mes anterior
REM (ja completo). Ajuste /D e /ST conforme preferir.

setlocal
cd /d "%~dp0.."

set "UV=%APPDATA%\Python\Python314\Scripts\uv.exe"
if not exist "%UV%" set "UV=uv"

"%UV%" run python -m vigia_publico.cli run-all
set EXITCODE=%ERRORLEVEL%

if not %EXITCODE%==0 (
    echo [run_monthly.bat] Pipeline falhou com codigo %EXITCODE% - veja logs\vigia_publico.log
)

exit /b %EXITCODE%
