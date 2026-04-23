@echo off
TITLE HedgedLock Bot - Build Executable
CLS

ECHO ========================================================
ECHO   HedgedLock Bot - Build Executable
ECHO ========================================================
ECHO.

:: Check for Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Python is not installed.
    ECHO Please install Python from https://python.org/
    PAUSE
    EXIT /B
)
ECHO [OK] Python found.

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
ECHO ========================================================
ECHO   Step 1: Install Dependencies
ECHO ========================================================
ECHO.

pip install pyinstaller cryptography dnspython --quiet
IF %ERRORLEVEL% NEQ 0 (
    ECHO [WARNING] Some packages may have failed to install
)
ECHO [OK] Build tools installed.

:: Install all requirements
pip install -r requirements.txt --quiet
pip install -r server\requirements.txt --quiet
ECHO [OK] Python dependencies installed.

ECHO.
ECHO ========================================================
ECHO   Step 2: Build React Dashboard
ECHO ========================================================
ECHO.

cd client
call npm install
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Failed to install npm dependencies
    cd ..
    PAUSE
    EXIT /B
)

call npm run build
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] React build failed
    cd ..
    PAUSE
    EXIT /B
)
cd ..
ECHO [OK] React dashboard built.

ECHO.
ECHO ========================================================
ECHO   Step 3: Encrypt Config
ECHO ========================================================
ECHO.

IF EXIST "server\.env.enc" (
    ECHO [INFO] .env.enc already exists. Skipping encryption.
) ELSE (
    IF EXIST "server\.env" (
        python encrypt_env.py
    ) ELSE (
        ECHO [WARNING] No .env file found. Create one before distribution.
    )
)

ECHO.
ECHO ========================================================
ECHO   Step 4: Build HedgedLockBot.exe
ECHO ========================================================
ECHO.

pyinstaller dashboard.spec --noconfirm
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Build failed!
    PAUSE
    EXIT /B
)
ECHO [OK] HedgedLockBot.exe built.

ECHO.
ECHO ========================================================
ECHO   Step 5: Prepare Distribution
ECHO ========================================================
ECHO.

:: Create dist folder structure
IF NOT EXIST "dist\release" mkdir dist\release

:: Copy executable
copy dist\HedgedLockBot.exe dist\release\HedgedLockBot.exe >nul

:: Copy encrypted config
IF EXIST "server\.env.enc" (
    copy server\.env.enc dist\release\.env.enc >nul
    ECHO [OK] Encrypted config copied.
)

ECHO.
ECHO ========================================================
ECHO   BUILD COMPLETE!
ECHO ========================================================
ECHO.
ECHO Distribution folder: dist\release\
ECHO.
ECHO Contents:
ECHO   - HedgedLockBot.exe   (Main application)
ECHO   - .env.enc            (Encrypted config)
ECHO.
ECHO To use:
ECHO   1. Copy 'dist\release' folder to target machine
ECHO   2. Double-click HedgedLockBot.exe
ECHO   3. Browser opens automatically to dashboard
ECHO.
ECHO ========================================================
ECHO.

PAUSE
