@echo off
TITLE Hedged Lock Bot - Setup & Start
CLS

ECHO ========================================================
ECHO   HEDGED LOCK BOT - LAUNCHER
ECHO   Version 6.0 with Dashboard
ECHO ========================================================
ECHO.

:: Find Absolute Python Path (suppress errors from Windows Store alias)
for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_CMD=%%I"
IF NOT DEFINED PYTHON_CMD (
    ECHO [ERROR] Python is not installed or not in PATH.
    ECHO.
    ECHO Please install Python from https://www.python.org/downloads/
    ECHO Make sure to check "Add Python to PATH" during installation.
    ECHO.
    PAUSE
    EXIT /B
)

ECHO [OK] Python found at: "%PYTHON_CMD%"
ECHO.

:: Install Python dependencies
ECHO [1/3] Installing Python dependencies...
"%PYTHON_CMD%" -m pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Failed to install Python dependencies.
    PAUSE
    EXIT /B
)
ECHO [OK] Python dependencies installed.
ECHO.

:: Check for Node.js (only needed for building, not running)
node --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    ECHO [OK] Node.js found.
    
    :: Check if client/dist exists
    IF NOT EXIST "client\dist\index.html" (
        ECHO [2/3] Building React dashboard...
        cd client
        npm install
        npm run build
        cd ..
        ECHO [OK] Dashboard built.
    ) ELSE (
        ECHO [2/3] Dashboard already built, skipping...
    )
) ELSE (
    ECHO [WARNING] Node.js not found. 
    ECHO Dashboard must be pre-built. Checking...
    IF NOT EXIST "client\dist\index.html" (
        ECHO [ERROR] Dashboard not built and Node.js not available.
        ECHO Please install Node.js or use a pre-built package.
        PAUSE
        EXIT /B
    )
    ECHO [OK] Using pre-built dashboard.
)
ECHO.

:: Check for .env file
IF NOT EXIST "server\.env" (
    ECHO [3/3] Creating .env configuration...
    COPY "server\.env.example" "server\.env"
    ECHO.
    ECHO [IMPORTANT] Please edit server\.env with your database URL!
    ECHO Opening .env file...
    notepad "server\.env"
    ECHO.
    ECHO After editing, press any key to continue...
    PAUSE
)

:: Kill any existing process on port 5000 to avoid conflicts
ECHO [CLEANUP] Checking for existing processes on port 5000...
for /f "tokens=5" %%A in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    ECHO [CLEANUP] Killing process %%A on port 5000...
    taskkill /PID %%A /F >nul 2>&1
)
ECHO [OK] Port 5000 is clear.

ECHO.
ECHO ========================================================
ECHO   Starting Dashboard Server...
ECHO   Open http://localhost:5000 in your browser
ECHO ========================================================
ECHO.

:: Start the server
cd server
"%PYTHON_CMD%" app.py

PAUSE
