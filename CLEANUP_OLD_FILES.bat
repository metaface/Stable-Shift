@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m tools.tidy_legacy_files --apply
) else (
    py -3 -m tools.tidy_legacy_files --apply
)
pause
