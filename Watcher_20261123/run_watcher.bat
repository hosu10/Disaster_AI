@echo off
chcp 65001 >nul
cd /d "C:\CGMS\Watcher_20261123" || exit /b 1
if not exist "venv\Scripts\python.exe" (
    echo venv 없음 — install_ops_test.bat 실행
    exit /b 1
)
call venv\Scripts\activate.bat
python DisasterTV_AI_Call.py