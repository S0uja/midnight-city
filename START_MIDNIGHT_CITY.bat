@echo off
setlocal EnableExtensions
cd /d "%~dp0"
py -3 "%~dp0START_MIDNIGHT_CITY.py"
if errorlevel 1 goto :fallback
goto :end
:fallback
python "%~dp0START_MIDNIGHT_CITY.py"
:end
echo.
echo MIDNIGHT CITY V25 has stopped.
pause
endlocal
