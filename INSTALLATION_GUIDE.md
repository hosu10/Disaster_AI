# DisasterTV_AI 신규 PC 설치 가이드

## 📋 필수 사전 요구사항

### 1. 운영체제
- **Windows 10 이상** (코드에서 Windows 전용 기능 사용: `winsound`, `pyttsx3`)

### 2. Python 설치
- **Python 3.12 이상** 권장
- 설치 파일: `resources/python-3.12.9-amd64.exe` (있는 경우)
- 또는 [Python 공식 사이트](https://www.python.org/downloads/)에서 다운로드
- 설치 시 **"Add Python to PATH"** 옵션 체크 필수

### 3. 시스템 환경 변수 설정

#### OpenAI API 키 설정 (필수)
```cmd
# Windows 환경 변수 설정 방법:
# 1. 제어판 > 시스템 > 고급 시스템 설정 > 환경 변수
# 2. 시스템 변수 또는 사용자 변수에 추가:
변수 이름: OPENAI_API_KEY
변수 값: [OpenAI API 키]
```

**확인 방법:**
```cmd
# 명령 프롬프트에서 확인
echo %OPENAI_API_KEY%
```

또는 `resources/test_openAI_API_key.py` 실행하여 확인

---

## 📦 필수 소프트웨어 설치

### 1. Tesseract OCR (필수)
- **설치 파일**: `resources/tesseract-ocr-w64-setup-5.4.0.20240519-1-ga5ff320e.exe`
- 또는 [Tesseract GitHub](https://github.com/UB-Mannheim/tesseract/wiki)에서 다운로드
- **설치 경로**: `C:\Program Files\Tesseract-OCR\` (기본 경로 권장)
- **한국어 언어팩 설치 필수**: 설치 시 "Korean" 언어팩 선택

**설치 확인:**
```cmd
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

### 2. FFmpeg (선택사항 - 오디오 재생 시 필요)
- RTMP 스트림의 오디오 재생이 필요한 경우 설치
- [FFmpeg 공식 사이트](https://ffmpeg.org/download.html)에서 다운로드
- 설치 후 시스템 PATH에 추가

---

## 📁 디렉토리 구조 생성

### 필수 디렉토리 생성
```cmd
# 프로젝트 루트 디렉토리에서 실행
mkdir captures
mkdir temp
mkdir resources
```

### 운영 환경 디렉토리 (Override.yml에서 설정)
```cmd
# CAP 파일 수신 경로
mkdir C:\CGMS\file\cap

# 캡쳐 이미지 저장 경로
mkdir C:\CGMS\captures
```

---

## 🐍 Python 패키지 설치

### 1. 가상 환경 생성 (권장)
```cmd
python -m venv venv
venv\Scripts\activate
```

### 2. 필수 패키지 설치
```cmd
pip install -r requirements.txt
```

**주요 패키지:**
- opencv-python (비디오 처리)
- pytesseract (OCR)
- openai (GPT API)
- pyttsx3 (음성 출력)
- ffpyplayer (오디오 재생)
- schedule (스케줄링)
- PyYAML (설정 파일)
- pillow (이미지 처리)

---

## ⚙️ 설정 파일 구성

### 1. Default.yml 확인
- 기본 설정 파일이 이미 존재함
- 대부분의 설정은 기본값으로 동작

### 2. Override.yml 생성/수정 (환경별 설정)
```yaml
# Override.yml 예시
# 1. 카카오 채널 알림 설정
kakao_on: True  # 또는 False

# 2. 비디오 입력 경로 설정
video_path: 0  # 웹캠 사용 시
# video_path: "rtmp://10.30.17.108:1935/live/kbs"  # RTMP 스트림 사용 시

# 3. CAP 파일 수신 경로
path_cap: "C:/CGMS/file/cap/"  # 운영 환경
# path_cap: "./cap"  # 개발 환경

# 4. 캡쳐 이미지 저장 경로
path_capture: "C:/CGMS/captures"  # 운영 환경
path_capture2: "./captures"  # 개발 환경

# 5. Tesseract 경로 (기본값과 다를 경우)
# pytesseract_path: "C:/Program Files/Tesseract-OCR/tesseract.exe"
```

---

## 📄 필수 리소스 파일 확인

### resources 폴더에 필요한 파일들:
- ✅ `malgun.ttf` - 한글 폰트 파일 (이미지에 텍스트 그리기용)
- ✅ `ticker_org.png` - 티커 참조 이미지
- ✅ `kbs_mandatory.json` - 재난 코드 정의 파일 (선택사항, URL에서 자동 로드 가능)

**확인 방법:**
```cmd
dir resources\malgun.ttf
dir resources\ticker_org.png
```

---

## 🔧 환경별 설정 체크리스트

### 개발/테스트 환경
- [ ] `Override.yml`에서 `video_path: 0` (웹캠)
- [ ] `path_cap: "./cap"` (로컬 경로)
- [ ] `path_capture: "./captures"` (로컬 경로)
- [ ] `kakao_on: False` (알림 비활성화)

### 운영 환경
- [ ] `Override.yml`에서 `video_path: "rtmp://..."` (RTMP 스트림)
- [ ] `path_cap: "C:/CGMS/file/cap/"` (운영 경로)
- [ ] `path_capture: "C:/CGMS/captures"` (운영 경로)
- [ ] `kakao_on: True` (알림 활성화)
- [ ] CAP 파일 수신 시스템과 연동 확인

---

## ✅ 설치 확인 및 테스트

### 1. 환경 변수 확인
```cmd
python resources\test_openAI_API_key.py
```

### 2. Tesseract 확인
```cmd
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

### 3. 필수 패키지 확인
```cmd
python -c "import cv2, pytesseract, openai, pyttsx3, yaml; print('All packages OK')"
```

### 4. 프로그램 실행 테스트
```cmd
python DisasterTV_AI.py
```

**예상 동작:**
- 로그 파일 생성: `resources/disaster_log.log`
- 비디오 소스 연결 시도
- CAP 파일 모니터링 시작
- 'q' 키로 종료 가능

---

## 🚨 문제 해결

### 1. OpenAI API 키 오류
```
Error: OpenAI API key not found
```
**해결:** 환경 변수 `OPENAI_API_KEY` 설정 확인

### 2. Tesseract 경로 오류
```
TesseractNotFoundError
```
**해결:** 
- Tesseract 설치 확인
- `Override.yml`에서 `pytesseract_path` 경로 확인

### 3. 비디오 소스 연결 실패
```
[VID]> 비디오 소스 연결에 실패했습니다
```
**해결:**
- `video_path` 설정 확인 (0 = 웹캠, RTMP URL = 스트림)
- 웹캠이 연결되어 있는지 확인
- RTMP 스트림 URL이 유효한지 확인

### 4. 폰트 파일 오류
```
OSError: cannot open resource
```
**해결:** `resources/malgun.ttf` 파일 존재 확인

### 5. CAP 파일 경로 오류
```
FileNotFoundError: [WinError 3] 시스템이 지정된 경로를 찾을 수 없습니다
```
**해결:** `path_cap` 디렉토리 생성 확인

---

## 📝 추가 참고사항

### 로그 파일 위치
- 기본 경로: `resources/disaster_log.log`
- 최대 크기: 1024 KB (설정 가능)
- 백업 파일: `disaster_log.log.1`, `disaster_log.log.2`

### 네트워크 요구사항
- 인터넷 연결 필수 (OpenAI API, 재난 코드 정보 다운로드)
- KBS Science 서버 접근: `http://science.kbs.co.kr/EDBS/edbs_code.json`
- 카카오톡 알림 사용 시: `https://kmeas2024.com/api/alert_kbsPSAC`

### 성능 권장사항
- CPU: 멀티코어 권장 (비디오 처리)
- RAM: 최소 4GB 이상
- 디스크: 캡쳐 이미지 저장 공간 확보

---

## 📞 지원

설치 중 문제가 발생하면:
1. 로그 파일 확인: `resources/disaster_log.log`
2. 환경 변수 설정 확인
3. 필수 디렉토리 생성 확인
4. Python 패키지 버전 확인


