@echo off
:: release.bat — Gera executavel do jogo para distribuicao
::
:: Uso:
::   release.bat                          Windows (pasta com todos os arquivos)
::   release.bat --onefile                Windows (executavel unico)
::   release.bat --linux                  Windows + Linux (pasta)
::   release.bat --linux --linux-onefile  Windows + Linux (onefile)
::   release.bat --linux-only             So Linux (pasta)
::   release.bat --linux-only --linux-onefile  So Linux (onefile)
::   release.bat --clean                  Apaga build anterior antes de compilar

cd /d "%~dp0"

echo.
echo === UnderWorldHero - Build de Release ===
echo.

.venv\Scripts\python build_nuitka.py %*

if %errorlevel% neq 0 (
    echo.
    echo ERRO: Build falhou. Verifique os erros acima.
    pause
    exit /b 1
)

echo.
pause
