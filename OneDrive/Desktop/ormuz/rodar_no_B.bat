@echo off
echo ============================================
echo  NO B - Conectar a outro no existente
echo ============================================
echo.
set /p IP_A="Digite o IP do Computador A (ex: 192.168.1.10): "
echo.
echo Conectando ao no A em http://%IP_A%:5000 ...
echo.
py node/app.py --port 5000 --peers http://%IP_A%:5000 --automine 2>nul || python node/app.py --port 5000 --peers http://%IP_A%:5000 --automine 2>nul || python3 node/app.py --port 5000 --peers http://%IP_A%:5000 --automine
pause
