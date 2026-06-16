@echo off
echo ============================================
echo  Instalador - Estreito de Ormuz Blockchain
echo ============================================
echo.

REM Tenta py launcher (instalado com Python do site oficial)
py --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [OK] Python encontrado via py launcher
    py -m pip install flask requests
    goto :fim
)

REM Tenta python
python --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [OK] Python encontrado via python
    python -m pip install flask requests
    goto :fim
)

REM Tenta python3
python3 --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [OK] Python encontrado via python3
    python3 -m pip install flask requests
    goto :fim
)

echo [ERRO] Python nao encontrado!
echo.
echo Instale o Python em: https://www.python.org/downloads/
echo IMPORTANTE: marque "Add Python to PATH" na instalacao!
echo.
pause
exit /b 1

:fim
echo.
echo [OK] Dependencias instaladas com sucesso!
echo.
pause
