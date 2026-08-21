@echo off
setlocal
cd /d "%~dp0"

REM Launch AnyDoc2MD from source using its own virtual environment (.venv),
REM so it never depends on whatever "python" happens to be on the PATH.
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"

REM First run: create the virtual environment and install dependencies.
if not exist "%VENV_PYW%" (
    echo Setting up AnyDoc2MD for first use...
    echo Creating virtual environment in .venv ...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist "%VENV_PY%" (
        echo.
        echo ERROR: Could not create the virtual environment.
        echo Make sure Python 3.10+ is installed and on your PATH.
        pause
        exit /b 1
    )
    echo Installing dependencies ^(this can take a few minutes^)...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Dependency installation failed. See the messages above.
        pause
        exit /b 1
    )
)

REM Launch the GUI with no console window.
start "" "%VENV_PYW%" -m anydoc2md
endlocal
