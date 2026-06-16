@echo off
echo ============================================
echo  NO C - Conectar a dois nos existentes
echo ============================================
echo.
set /p IP_A="Digite o IP do Computador A: "
set /p IP_B="Digite o IP do Computador B: "
echo.
echo Conectando aos nos A e B...
echo.
py node/app.py --port 5000 --peers http://%IP_A%:5000 http://%IP_B%:5000 --automine 2>nul || python node/app.py --port 5000 --peers http://%IP_A%:5000 http://%IP_B%:5000 --automine 2>nul || python3 node/app.py --port 5000 --peers http://%IP_A%:5000 http://%IP_B%:5000 --automine
pause
