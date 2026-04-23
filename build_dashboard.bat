@echo off
TITLE Hedged Lock Bot - Build Dashboard
CLS

ECHO ========================================================
ECHO   Building React Dashboard for Distribution
ECHO ========================================================
ECHO.

:: Check for Node.js
node --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Node.js is not installed.
    ECHO Please install Node.js from https://nodejs.org/
    PAUSE
    EXIT /B
)

ECHO [OK] Node.js found.
ECHO.

:: Navigate to client directory
cd client

:: Install dependencies
ECHO [1/2] Installing npm dependencies...
npm install
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Failed to install npm dependencies.
    PAUSE
    EXIT /B
)

:: Build
ECHO [2/2] Building production bundle...
npm run build
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Build failed.
    PAUSE
    EXIT /B
)

cd ..

ECHO.
ECHO ========================================================
ECHO   Build Complete!
ECHO   The dashboard is now in client\dist\
ECHO   You can now distribute this folder without Node.js
ECHO ========================================================
ECHO.

PAUSE
