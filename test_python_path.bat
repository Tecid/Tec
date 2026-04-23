@echo off
for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)"') do set "PYTHON_CMD=%%I"
echo Found python at: "%PYTHON_CMD%"
"%PYTHON_CMD%" --version
