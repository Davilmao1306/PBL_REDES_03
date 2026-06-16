@echo off
echo ============================================
echo  NO A - Primeiro no (sem peers)
echo ============================================
echo.
echo Descobrindo seu IP...
ipconfig | findstr /i "IPv4"
echo.
echo Anote o IP acima e informe aos outros computadores!
echo.

py node/app.py --port 5000 --automine 2>nul || python node/app.py --port 5000 --automine 2>nul || python3 node/app.py --port 5000 --automine
pause
