@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "UV_VENV_DIR=%SCRIPT_DIR%rag_qa\.venv"
set "UV_PYTHON=%UV_VENV_DIR%\Scripts\python.exe"
set "UV_ACTIVATE_BAT=%UV_VENV_DIR%\Scripts\activate.bat"

if not exist "%UV_PYTHON%" (
	echo.
	echo uv virtual environment interpreter not found: %UV_PYTHON%
	echo Please create/install dependencies in rag_qa\.venv first
	set "EXIT_CODE=1"
	goto :launcher_end
)

if exist "%UV_ACTIVATE_BAT%" (
	call "%UV_ACTIVATE_BAT%"
)

set "EDURAG_PYTHON_EXE=%UV_PYTHON%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_edurag.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
	echo.
	echo Launcher failed with exit code %EXIT_CODE%.
	echo Press any key to close this window.
	pause >nul
)

:launcher_end
endlocal
exit /b %EXIT_CODE%
