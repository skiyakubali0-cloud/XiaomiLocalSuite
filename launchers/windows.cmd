@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0.." || exit /b 1
set "PYTHONDONTWRITEBYTECODE=1"
if defined XLS_PYTHON goto override
py -3 "%~dp0..\launch.py" --check >nul 2>&1
if not errorlevel 1 goto py
python "%~dp0..\launch.py" --check >nul 2>&1
if not errorlevel 1 goto python
echo Python 3.11+ with Tk 8.6+ is required. Set XLS_PYTHON to its executable path. 1>&2
exit /b 1
:override
"%XLS_PYTHON%" "%~dp0..\launch.py" %*
exit /b %errorlevel%
:py
py -3 "%~dp0..\launch.py" %*
exit /b %errorlevel%
:python
python "%~dp0..\launch.py" %*
exit /b %errorlevel%
