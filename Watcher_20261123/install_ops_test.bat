@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM ============================================================
REM  Watcher_20261123 — 운영 PC 최초 설치 / 설치 테스트
REM  대상 경로: C:\CGMS\Watcher_20261123
REM ============================================================

set "REPO_URL=https://github.com/hosu10/Disaster_AI.git"
set "BRANCH=main"
set "INSTALL_DIR=C:\CGMS\Watcher_20261123"
set "ERR=0"

echo.
echo [1/6] 설치 경로: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" || (echo mkdir 실패 & exit /b 1)
)

cd /d "%INSTALL_DIR%" || (echo cd 실패 & exit /b 1)

echo.
echo [2/6] GitHub에서 소스 받기...
where git >nul 2>&1
if errorlevel 1 (
    echo Git이 설치되어 있지 않습니다. https://git-scm.com/ 설치 후 다시 실행하세요.
    exit /b 1
)

if exist ".git" (
    echo 기존 저장소 — git pull ...
    git fetch origin %BRANCH%
    git reset --hard origin/%BRANCH%
) else (
    if exist "DisasterTV_AI_Call.py" (
        echo 경고: INSTALL_DIR에 파일이 있으나 .git 없음. 상위에서 수동 복사하거나 빈 폴더로 재실행하세요.
        set "ERR=1"
    ) else (
        git clone --branch %BRANCH% --depth 1 %REPO_URL% .
    )
)

if not exist "DisasterTV_AI_Call.py" (
    echo DisasterTV_AI_Call.py 없음 — 클론/경로 확인.
    exit /b 1
)

echo.
echo [3/6] Python / venv 확인...
where py >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python 3.11+ 설치 필요.
        exit /b 1
    )
    set "PY=python"
)

if not exist "venv\Scripts\python.exe" (
    echo 가상환경 생성 중...
    %PY% -m venv venv || exit /b 1
)

echo.
echo [4/6] 패키지 설치 (requirements.txt)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 set "ERR=1"

echo.
echo [5/6] 문법 검사 ...
python -m py_compile DisasterTV_AI_Call.py
if errorlevel 1 set "ERR=1"

echo.
echo [6/6] OPENAI_API_KEY 확인 (값은 출력하지 않음)...
python -c "import os; k=os.getenv('OPENAI_API_KEY','').strip(); print('OPENAI_API_KEY:', 'OK' if k else 'MISSING — 사용자 환경변수 설정 후 터미널 재시작')"

if not exist "Override.yml" (
    echo Override.yml 없음 — Default.yml 만 사용됩니다.
)

echo.
if "%ERR%"=="1" (
    echo === 설치 테스트 일부 실패 ===
) else (
    echo === 설치 테스트 완료 ===
)

set /p RUN=Watcher 실행 테스트할까요? (Y/N): 
if /I "%RUN%"=="Y" (
    echo 실행: DisasterTV_AI_Call.py
    python DisasterTV_AI_Call.py
)

endlocal
exit /b %ERR%