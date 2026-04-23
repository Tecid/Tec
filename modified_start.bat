@echo off
ECHO [TRACE] Before cd server
cd server
ECHO [TRACE] After cd server
ECHO [TRACE] Environment variables:
set PATH
ECHO [TRACE] Calling python app.py...
python app.py
ECHO [TRACE] Python returned %ERRORLEVEL%
