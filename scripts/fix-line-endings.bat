@echo off
REM Ensure we are in the project root
cd /d "%~dp0.."

REM fix-line-endings.bat
REM Converts all text files to Unix (LF) line endings for Docker compatibility
REM Run this on Windows before building Docker images

echo === Fixing Line Endings for Docker ===
echo.

REM Check if dos2unix is available
where dos2unix >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] dos2unix not found!
    echo.
    echo Install it with:
    echo   choco install dos2unix
    echo   OR
    echo   winget install dos2unix
    echo.
    pause
    exit /b 1
)

echo Converting shell scripts...
dos2unix -q scripts\*.sh
dos2unix -q simulator\*.py
dos2unix -q simulator\*.yml
dos2unix -q simulator\*.yaml
dos2unix -q Dockerfile
dos2unix -q docker-compose.yml
dos2unix -q traffic_matrix_generator\*.py
dos2unix -q traffic_matrix_generator\*.sh

echo.
echo === Line Endings Fixed ===
echo Files are now ready for Docker on Windows
echo.
pause
