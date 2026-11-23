@echo off
chcp 65001 >nul
setlocal
set "INSTALL_DIR=C:\CGMS\Watcher_20261123"
cd /d "%INSTALL_DIR%" || (echo 경로 없음: %INSTALL_DIR% & exit /b 1)
if not exist ".git" (echo git 저장소 아님 — install_ops_test.bat 먼저 실행 & exit /b 1)
git pull origin main
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
python -m py_compile DisasterTV_AI_Call.py
echo 업데이트 완료.
endlocal