@echo off
setlocal
cd /d "%~dp0"
set OMP_NUM_THREADS=4
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 (echo Install 64-bit Python 3.11 or 3.12 with Tkinter.&pause&exit /b 1)
)
.venv\Scripts\python.exe -c "import numpy,cv2,PIL,tkinterdnd2; from importlib.metadata import version; assert version('tkinterdnd2') == '0.7.0'" >nul 2>&1
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (echo Dependency installation failed.&pause&exit /b 1)
)
.venv\Scripts\python.exe -m stable_shift
if errorlevel 1 pause
