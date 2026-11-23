# Watcher_20261123 — 운영 PC 설치·테스트

## 저장소
- GitHub: `https://github.com/hosu10/Disaster_AI.git`
- 운영 설치 경로(권장): `C:\CGMS\Watcher_20261123`

## 사전 준비 (운영 PC)
1. **Git for Windows** 설치
2. **Python 3.11+** 설치 (`py` 또는 `python` PATH 등록)
3. Windows 사용자 환경변수 **`OPENAI_API_KEY`** 등록 후 **터미널 재시작**
4. (선택) Tesseract, ffmpeg — `Default.yml` / `Override.yml` 경로 확인

## 절차 A — 최초 설치·테스트 (배치 권장)
1. 이 폴더의 `install_ops_test.bat` **관리자 권한 불필요**, 더블클릭 또는 cmd에서 실행
2. 스크립트가 `C:\CGMS\Watcher_20261123` 에 클론/갱신 → venv → `pip install` → 문법 검사 수행
3. 끝에서 `Y` 입력 시 `DisasterTV_AI_Call.py` 실행 (UI 확인)
4. `Override.yml` 을 운영 경로(CAP, captures 등)에 맞게 수정 (UI 「설정 편집」 또는 메모장)

## 절차 B — 이미 설치된 PC 업데이트만
1. `update_from_github.bat` 실행 → `git pull` + 의존성 갱신
2. `run_watcher.bat` 로 실행

## 절차 C — 개발 PC에서 GitHub 반영
```powershell
cd C:\CGMS\Watcher
git add DisasterTV_AI_Call.py Default.yml Watcher_20261123
git status
git commit -m "Watcher UI12: 운영 배포 패키지 Watcher_20261123"
git push origin main
```

## 운영 실행
- 테스트/개발 진입점: `DisasterTV_AI_Call.py`
- 기존 운영이 `DisasterTV_AI.py` 복사본이면, 동일 내용으로 복사해 사용

## 문제 해결
| 증상 | 확인 |
|------|------|
| OpenAI 401 | 사용자 환경변수 `OPENAI_API_KEY`, PC 재로그인 |
| OpenAI 429 | 플랫폼 사용량·결제 한도 |
| USB 안 잡힘 | OBS 등 카메라 점유 해제, USB 탭에서 장치 선택 |
| libpng warning | 무시 가능 (티커 PNG 프로파일) |