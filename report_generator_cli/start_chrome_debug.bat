@echo off
echo.
echo [INFO] Iniciando una instancia de Chrome para Selenium...
echo [INFO] Perfil de usuario en: "%~dp0chrome_profile"
echo [INFO] Puerto de depuracion: 9222
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0chrome_profile"
echo [INFO] No cierres esta ventana de comandos para mantener el proceso activo.