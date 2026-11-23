# 파일명 : DisasterTV_AI_Call.py
# Update - 2026년 11월 23일 : OpenCV 960x540 재생 복원 + 제어 패널 연동, 파일 입력
# Update - 2026년 11월 23일 : USB 목록 ffmpeg+인덱스 탐색 개선(DSHOW 이름 열기 제거)
# Update - 2026년 11월 23일 : 비디오 입력 선택 UI(USB/RTMP/OBS), 제어 패널, 긴급검증 최신 프레임 적용
# Update - 2026년 11월 21일 : 긴급 재난경보에서 송출 화면 캡쳐 타이밍 수정 (7초후 +> 12초후)
# Update - 2026년 1월 6일 : 테스트 모드 추가 - 'm' 키 입력 시 CAP 수신 + 티커 확인 시뮬레이션하여 AI 호출 테스트
# Update - 2024년 10월 22일 : CAP이 없을때 티커 low 카운트 멈추도록 수정
# Update - 2024년 10월 23일 : RTMP로 오디오 받아서 동시에 플레이 하도록 코드 추가
# Update - 2024년 10월 24일 : 여전히 재난자막 못잡았어.  GPT-4o 모델/ systen contents를 정정함
# Update - 2024년 10월 28일 : 재난 자막 확인 여부에 대한 구분 1) 자막이 없으면 붉은 선, 2) 송출대상인지 확인 3)송출대상 미송출에 대한 음성 안내 4) audio on/off 토글기능
# Update - 2024년 11월 14일 : API 답변 누락메시지와 자막 불일치 메시지 구분
# Update - 2024년 11월 28일 : 회사 API 키로 변경하고, API 호출방식도 PC 시스템 환경변수에서 키를 가져오는 최신 버전으로 수정함.
# Update - 2024년 12월 10일 : 카카오톡 알림 기능 추가 send_post_request(message)
# Update - 2024년 12월 13일 : 중복재난과 긴급재난 복합 발령 상황 테스트
# Update - 2025년 1월 6일 :  System Alive 톡을 만들었고, 이로서 시스템이 안정적으로 동작하는지 확인할 수 있게 함.
# Update - 2025년 1월 15일 : 입력 비디오 소스에 따라서 화면 사이즈가 달라지는 거 대응, 모든 소스를 960x540으로 변환하여 처리토록 보완
# Update - 2025년 2월 5일 : Resource 파일 통합, 긴급재난 경보 테스트 보강
# Update - 2025년 4월 10일 : 정파시간 오작동 개선 / yaml 파일정리
# # default.yml : 연구개발 테스트 운영 서버 기준으로 설정함.
# # Override.ml : 재난센터 서버 또는 코드 개발 서버 기준으로 필요시 수정함.
# Update - 2026년 1월 6일 : 재난센터 OS 업그레이드, API 키 변경 재설치시 문제 해결(API 호출 오류 시 세부 로그 추가)

import os
import numpy as np
import time
import cv2
import pytesseract
import winsound
import threading
import yaml
import queue  # Queue import
import requests
import json  # json 파싱을 위해 import 필요
import base64
import xml.etree.ElementTree as ET
try:
    import logging
except Exception:
    # optional helper module missing on this system; provide a minimal fallback
    class _DummyLoggguswing:
        def __getattr__(self, name):
            def _noop(*args, **kwargs):
                return None
            return _noop

    loggguswing = _DummyLoggguswing()

from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from datetime import datetime, timedelta  # 추가
from PIL import Image, ImageDraw, ImageFont
try:
    from ffpyplayer.player import MediaPlayer  # 오디오 플레이어 라이브러리
    _FFPLAYER_AVAILABLE = True
except Exception:
    MediaPlayer = None
    _FFPLAYER_AVAILABLE = False
try:
    from openai import OpenAI
    from openai import (
        AuthenticationError,
        RateLimitError,
        APIConnectionError,
        APIStatusError,
        APIError,
    )
    _OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    AuthenticationError = None
    RateLimitError = None
    APIConnectionError = None
    APIStatusError = None
    APIError = None
    _OPENAI_AVAILABLE = False
import schedule  # Scheduled tasks

APP_VERSION = "V-261123-ui13"
DISPLAY_WIDTH = 960
DISPLAY_HEIGHT = 540
UI_MAX_WIDTH = 1000
UI_PREVIEW_W = 608
UI_PREVIEW_H = 342
UI_PREFS_PATH = "./Watcher_ui_prefs.yml"
DEFAULT_YML = "./Default.yml"
OVERRIDE_YML = "./Override.yml"

OPERATOR_PIPELINE_STEPS = (
    ("cap_recv", "① CAP 수신"),
    ("queue", "② 송출 대기열"),
    ("monitor", "③ 방송 화면 감시"),
    ("ticker_on", "④ 재난 티커 감지"),
    ("ai", "⑤ 자막 AI 검증"),
    ("capture", "⑥ 화면 캡처 저장"),
    ("complete", "⑦ 송출 확인"),
)
_pipeline_status_ko = {
    "idle": "대기",
    "wait": "대기 중",
    "active": "진행",
    "ok": "완료",
    "warn": "주의",
    "fail": "실패",
}

# Configure Tesseract executable and tessdata directory when available
# This helps pytesseract find the correct `tesseract.exe` and language data (e.g., kor.traineddata)
_tesseract_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
_tess_found = False
for _p in _tesseract_paths:
    if os.path.exists(_p):
        pytesseract.pytesseract.tesseract_cmd = _p
        _tessdata_dir = os.path.join(os.path.dirname(_p), "tessdata")
        if os.path.isdir(_tessdata_dir):
            # TESSDATA_PREFIX should point to the tessdata folder
            os.environ.setdefault("TESSDATA_PREFIX", _tessdata_dir)
        _tess_found = True
        break
if not _tess_found:
    try:
        logging.warning(
            "Tesseract executable not found in expected locations. "
            "If OCR fails, set pytesseract.pytesseract.tesseract_cmd to your tesseract.exe path "
            "and ensure TESSDATA_PREFIX points to the tessdata folder containing kor.traineddata."
        )
    except Exception:
        pass

def refresh_user_env_from_registry(names=("OPENAI_API_KEY",)):
    """IDE/Cursor 세션의 구 env보다 Windows 사용자(HKCU) 환경변수를 우선."""
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment"
        ) as env_key:
            for var in names:
                try:
                    value, _ = winreg.QueryValueEx(env_key, var)
                except OSError:
                    continue
                if value is not None and str(value).strip():
                    os.environ[var] = str(value).strip()
    except Exception:
        pass


refresh_user_env_from_registry(("OPENAI_API_KEY",))

if _OPENAI_AVAILABLE and OpenAI is not None:
    try:
        client = OpenAI()
    except Exception as e:
        try:
            logging.exception(f"Failed to instantiate OpenAI client: {e}")
        except Exception:
            pass
        client = None
else:
    class _DummyOpenAI:
        def __getattr__(self, name):
            raise RuntimeError("OpenAI client not available in this environment")

    client = _DummyOpenAI()

# 전역 변수
list_json_cap = []  # CAP 데이터를 리스트로 관리
list_json_emergency = []  # CAP 데이터를 리스트로 관리
cap_priority = 0  # CAP 데이터를 리스트로 관리
terminate_program = False  # 프로그램 종료 플래그
audio_on = False  # 오디오 재생 상태

# ffpyplayer가 없을 때를 대비한 플레이어 초기값
player = None

# 캡 데이터를 수신한 시간 및 송출 여부 추적을 위한 변수
received_caps = []  # Received CAP messages
transmitted_caps = []  # Transmitted CAP messages
report_reset_time = datetime.now()

# Queue 생성
speak_queue = queue.Queue()
ui_command_queue = queue.Queue()

latest_frame = None
video_input_lock = threading.Lock()
video_reconnect_event = threading.Event()
video_input_settings = {
    "kind": "usb",
    "usb_index": 0,
    "usb_label": "",
    "rtmp_url": "",
    "obs_url": "",
    "file_path": "",
    "media_folder": "",
    "usb_device_name": "",
}
ui_status_text = "대기 중"
ui_frame_lock = threading.Lock()
ui_display_bgr = None
ui_root = None
operator_pipeline_lock = threading.Lock()
operator_pipeline = {}
ui_pipeline_refresh_cb = None
fullscreen_state = {"win": None, "canvas": None, "photo": None}
_apply_video_save_prefs = None


def init_operator_pipeline():
    with operator_pipeline_lock:
        operator_pipeline.clear()
        for sid, label in OPERATOR_PIPELINE_STEPS:
            operator_pipeline[sid] = {
                "label": label,
                "status": "idle",
                "detail": "",
                "updated": "",
            }


def pipeline_update(step_id, status, detail=""):
    with operator_pipeline_lock:
        if step_id not in operator_pipeline:
            return
        operator_pipeline[step_id]["status"] = status
        operator_pipeline[step_id]["detail"] = (detail or "")[:160]
        operator_pipeline[step_id]["updated"] = datetime.now().strftime("%H:%M:%S")
    if ui_root is not None and ui_pipeline_refresh_cb is not None:
        try:
            ui_root.after(0, ui_pipeline_refresh_cb)
        except Exception:
            pass


def pipeline_set_monitoring_active(detail="방송 영상 연결됨"):
    pipeline_update("monitor", "active", detail)


def pipeline_reset_after_complete():
    for sid in ("cap_recv", "queue", "ticker_on", "ai", "capture", "complete"):
        pipeline_update(sid, "idle", "")
    pipeline_update("monitor", "active", "다음 CAP 대기")


def load_ui_prefs():
    if not os.path.isfile(UI_PREFS_PATH):
        return {}
    try:
        with open(UI_PREFS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_ui_prefs_from_video_settings(settings):
    try:
        data = load_ui_prefs()
        data["video_input"] = {
            k: settings.get(k)
            for k in (
                "kind",
                "usb_index",
                "usb_label",
                "rtmp_url",
                "obs_url",
                "file_path",
                "media_folder",
                "usb_device_name",
            )
        }
        with open(UI_PREFS_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        try:
            logger.warning(f"[UI]> 설정 저장 실패: {e}")
        except Exception:
            pass


def apply_ui_prefs_to_video_settings():
    prefs = load_ui_prefs()
    vi = prefs.get("video_input")
    if not isinstance(vi, dict):
        return
    with video_input_lock:
        for key in video_input_settings:
            if key in vi and vi[key] is not None and vi[key] != "":
                video_input_settings[key] = vi[key]
        if "kind" not in vi and vi.get("usb_index") is not None:
            video_input_settings["kind"] = "usb"
        if video_input_settings.get("kind") not in ("usb", "file"):
            video_input_settings["kind"] = "usb"


def request_app_shutdown(from_video=False):
    """백그라운드 쓰레드 종료 + Tk mainloop 탈출."""
    global terminate_program
    terminate_program = True
    video_reconnect_event.set()
    try:
        speak_queue.put_nowait("EXIT")
    except Exception:
        pass
    root = ui_root
    if root is not None:
        try:
            root.after(0, root.quit)
        except Exception:
            pass
    if from_video:
        try:
            logger.error("[VID]> 비디오 감시 예외 — 프로그램 종료 요청")
        except Exception:
            pass


def push_ui_display_frame(frame):
    global ui_display_bgr
    with ui_frame_lock:
        ui_display_bgr = frame.copy()


def blank_display_frame():
    return np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)


def imread_unicode(path):
    """Windows 한글 경로 등 cv2.imread 실패 대비."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return cv2.imread(path)


def open_video_file_unicode(path):
    """한글/공백 경로 동영상 열기."""
    path = os.path.normpath(path)
    for api in (cv2.CAP_FFMPEG, cv2.CAP_ANY):
        cap = cv2.VideoCapture(path, api)
        if cap is not None and cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return cap
            cap.release()
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024):
            short = buf.value
            cap = cv2.VideoCapture(short, cv2.CAP_FFMPEG)
            if cap.isOpened():
                return cap
    except Exception:
        pass
    cap = cv2.VideoCapture(path)
    return cap if cap.isOpened() else None


IMAGE_FILE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
MEDIA_VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mkv",
    ".mov",
    ".wmv",
    ".m4v",
    ".webm",
    ".flv",
    ".mpeg",
    ".mpg",
}
MEDIA_PLAYABLE_EXTENSIONS = IMAGE_FILE_EXTENSIONS | MEDIA_VIDEO_EXTENSIONS


def list_playable_media_in_folder(folder):
    if not folder or not os.path.isdir(folder):
        return []
    paths = []
    try:
        names = sorted(os.listdir(folder), key=lambda s: s.lower())
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_PLAYABLE_EXTENSIONS:
                continue
            full = os.path.join(folder, name)
            if os.path.isfile(full):
                paths.append(full)
    except OSError:
        pass
    return paths
# logging.basicConfig(level=logging.WARNING)


# 로그 설정 함수
def setup_logger(log_path, log_filename, max_log_size, backup_count=2):
    # 로그 디렉토리가 없으면 생성
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    log_file = os.path.join(log_path, log_filename)

    # RotatingFileHandler 설정
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_log_size, backupCount=backup_count, encoding="utf-8"
    )

    # 터미널 출력을 위한 stream_handler 설정
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )

    # 파일 기록을 위한  file_handler 설정
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)

    # 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # 로그 레벨 설정
    logger.addHandler(file_handler)  # 파일 핸들러 추가
    logger.addHandler(stream_handler)  # 터미널 핸들러 추가

    # 🎯 새로운 touch 메서드 추가
    def touch(msg):
        """마지막 줄이 'Heart : ...' 이면 업데이트, 아니면 추가"""
        try:
            with open(log_file, "r+", encoding="utf-8") as f:
                lines = f.readlines()
                if (
                    lines and "Heart :" in lines[-1]
                ):  # 마지막 줄이 'Heart :' 관련 로그라면
                    f.seek(0)
                    f.writelines(lines[:-1])  # 마지막 줄 삭제
                    f.truncate()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(msg)  # 새 로그 추가
        except Exception as e:
            logger.error(f"Logger touch failed: {e}")

    logger.touch = touch  # logger에 새로운 touch 메서드 추가
    return logger


# Function to schedule for daily reporting
def report_caps(config):
    global report_reset_time, transmitted_caps
    # logger.info(f"** Alive Monitoring ===> Check..")
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(days=1)

    transmitted_caps_sorted = sorted(transmitted_caps, key=lambda x: x[1])
    report_duration_text = f"기간 : {report_reset_time.strftime('%m-%d %H:%M')} ~  {current_time.strftime('%m-%d %H:%M')}   \n송출 건수 {len(transmitted_caps_sorted)}건\n"

    report_message = (
        f"재난자막 송출 시스템 Alive Check\n"
        f"{report_duration_text}"
        # 송출 자막 시간순으로 출력
        + "\n".join(
            [
                f"- {item[1].strftime('%m-%d %H:%M:%S')} | {item[0]['event']}"
                for item in transmitted_caps_sorted
            ]
        )
        + "\n"
    )

    # 프린터 내용 출력
    logger.info(report_message)
    # send_post_request 함수에 전달
    send_post_request(config, report_message, daily=1)

    # 수신된 CAP과 송출된 CAP 데이터 삭제
    received_caps.clear()  # 수신된 CAP 데이터 초기화
    transmitted_caps.clear()  # 송출된 CAP 데이터 초기화
    report_reset_time = datetime.now()


def schedule_1min(config):
    def job():
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.touch(f"{current_time} - Heart : Alive Checked!!")

    schedule.every(1).minutes.do(job)
    # schedule.every().day.at("21:00").do(job)
    while not terminate_program:
        schedule.run_pending()  # 스케줄러에 등록된 작업들을 확인하고 실행합니다.
        time.sleep(10)  # 1초마다 확인합니다.
    logger.info(f"[1분 Alive]> 쓰레드를 종료합니다.")


def schedule_daily(config):
    def job():
        # report_reset_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report_caps(config=config)

    logger.info("\n")
    logger.info("** Alive Monitoring Started..")
    schedule.every().day.at("09:00").do(job)
    # schedule.every().day.at("21:00").do(job)
    while not terminate_program:
        schedule.run_pending()  # 스케줄러에 등록된 작업들을 확인하고 실행합니다.
        time.sleep(2)  # 1초마다 확인합니다.
    logger.info(f"[Daily Report]> 쓰레드를 종료합니다.")


def send_post_request(config, message, daily):
    if config["kakao_on"]:
        # API URL 및 헤더
        if daily == 1:
            api_url = "https://kmeas2024.com/api/alert_kbsPSAC"  # Daily Report 주소
        else:

            api_url = "https://kmeas2024.com/api/alert_kbsPSNC"  # 시스템 알람 주소

        headers = {
            "Content-Type": "application/json",
            "authorization": "KBS BTRI 68110001",
        }

        # 요청에 포함할 데이터
        payload = {"type": "text", "message": message}

        try:
            # POST 요청
            response = requests.post(api_url, json=payload, headers=headers)
        except requests.RequestException as e:
            logger.error(f"카카오 톡 메시지 발송 주소: {api_url}")
            logger.error(f"카카오 톡 메시지 발송 오류: {e}")
            return None

        # 응답 확인
        if response.status_code == 200:
            if daily == 1:
                logger.info(f"카카오 Alive 톡 메시지 발송 : Success: {api_url}")
            else:
                logger.info(
                    f"카카오 재난방송 미송출 톡 메시지 발송 : Success: {api_url}"
                )
            return response.json()
        logger.error(
            f"카카오 톡 실패 :  Failed with status code: {response.status_code}"
        )
        logger.info(response.text)
        return None


# 스피커 아웃을 담당하는 함수 (독립적인 스레드로 실행)
def speak_out():
    # pyttsx3 초기화 시 comtypes 등 외부 라이브러리 문제로 실패할 수 있음
    engine = None
    tts_enabled = False
    try:
        # lazy import to avoid import-time comtypes errors on some systems
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 200)
        tts_enabled = True
    except Exception as e:
        try:
            logger.error(f"[SPEAK]> TTS 초기화 실패: {e}")
        except Exception:
            print(f"[SPEAK]> TTS 초기화 실패: {e}")

    global terminate_program

    while not terminate_program:
        try:
            # Queue에서 데이터 대기 및 타임아웃 설정
            text = speak_queue.get(timeout=0.5)  # 0.5초마다 큐를 확인
            if text == "EXIT":  # 종료 신호 처리
                break
            # 경보음 및 텍스트 방송
            winsound.Beep(1000, 500)  # 주파수 1000 Hz, 지속 시간 500 ms
            time.sleep(0.5)  # 경보음과 텍스트 사이의 딜레이
            if tts_enabled and engine is not None:
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as e:
                    logger.error(f"[SPEAK]> TTS 재생 오류: {e}")
            else:
                # TTS가 불가능한 환경에서는 로그로 대체
                logger.info(f"[SPEAK]> TTS 미사용, 메시지: {text}")
            speak_queue.task_done()  # 작업 완료 표시
        except queue.Empty:  # 타임아웃으로 인한 예외
            pass  # Queue가 비어있는 경우 대기 없이 넘어감
        except Exception as e:
            logger.error(f"[SPEAK]> 스피커 아웃 중 오류: {e}")
    # 종료 시 엔진 종료
    if engine is not None:
        try:
            engine.stop()
        except Exception:
            pass
    logger.info(f"[스피커 출력]> 쓰레드를 종료합니다.")


# config.yml 로드 함수
def read_config(base_yml, override_yml):

    # A.yml (기본값) 로드
    with open(base_yml, "r", encoding="utf-8") as file:
        base_config = yaml.safe_load(file)

    # B.yml (변경값)이 존재하는지 확인
    if os.path.exists(override_yml):
        with open(override_yml, "r", encoding="utf-8") as file:
            override_config = yaml.safe_load(file)
        # 기본값을 변경값으로 덮어쓰기 (B.yml 값이 있으면 덮어씀)
        base_config.update(override_config)

    return base_config


def prog_state_logger(current_time, emergency_tx_endtime):
    logger.info(f"[STATE]> 현재 시스템 변수 모니터링")
    if list_json_cap:
        logger.info(f"[STATE]> 송출대기 재난 메시지 {len(list_json_cap)} 개")
        json_cap = list_json_cap[0]
    for i, cap_data in enumerate(list_json_cap):
        logger.info(f"[STATE]> {i} 번째 재난메시자")

        if cap_data:
            logger.info(
                f"--------------송출대기 재난 유형'EventCode': {cap_data['EventCode']}"
            )
            logger.info(
                f"--------------송출대기 재난 유형 headline {cap_data['headline']} "
            )
            logger.info(f"--------------송출대기 재난 유형'sent': {cap_data['sent']}")
            logger.info(
                f"--------------송출대기 재난 유형'Broadcastflag': {cap_data['Broadcastflag']}"
            )
            logger.info(
                f"--------------송출대기 재난 유형'emergency': {cap_data['emergency']}"
            )
            logger.info(
                f"--------------시간 변수 : 현재 = {current_time.strftime('%m-%d %H:%M:%S')}  긴급경보 종료시간 = {emergency_tx_endtime.strftime('%m-%d %H:%M:%S')}"
            )
            #            logger.info(f"--------------송출대기 재난 유형'source': {cap_data['source']}")
            logger.info("---------------------------------")
    if list_json_emergency:
        logger.info(f"[STATE]> 송출대기 긴급 메시지 {len(list_json_emergency)} 개")
        json_cap = list_json_emergency[0]


def parse_cap_file(file_path, config):
    ns = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
    tree = ET.parse(file_path)
    root = tree.getroot()

    # 필요한 정보 추출
    identifier = root.find("cap:identifier", ns).text
    sent = root.find("cap:sent", ns).text
    source = root.find("cap:source", ns).text
    event = root.find(".//cap:event", ns).text
    for eventCode in root.findall(".//cap:eventCode", ns):
        value_name = eventCode.find("cap:valueName", ns).text
        if value_name == "KR.eventCode":
            EventCode = eventCode.find("cap:value", ns).text
    headline = root.find(".//cap:headline", ns).text
    broadcast_text = None
    broadcast_flag = None
    Priority = None
    Magnitude = None  # 지진인 경우에만 존재함

    for parameter in root.findall(".//cap:parameter", ns):
        value_name = parameter.find("cap:valueName", ns).text
        if value_name == "BroadcastText.ko-KR":
            broadcast_text = parameter.find("cap:value", ns).text
        elif value_name == "Broadcastflag":
            broadcast_flag = parameter.find("cap:value", ns).text
        elif value_name == "Priority":
            Priority = parameter.find("cap:value", ns).text
        elif value_name == "Magnitude":
            Magnitude = parameter.find("cap:value", ns).text

    if EventCode in config["emergency_event_code"]:
        emergency = True
    else:
        emergency = False
    json_cap = {
        "identifier": identifier,
        "sent": sent,
        "source": source,
        "event": event,
        "EventCode": EventCode,
        "headline": headline,
        "BroadcastText.ko-KR": broadcast_text,
        "Broadcastflag": broadcast_flag,
        "Magnitude": Magnitude,
        "Priority": Priority,
        "emergency": emergency,
    }
    return json_cap


def delete_old_files(directory, days_old):
    now = time.time()
    cutoff = now - (days_old * 86400)  # 86400 seconds in a day
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            file_mod_time = os.path.getmtime(file_path)
            if file_mod_time < cutoff:
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.info(f"Error deleting file {file_path}: {e}")


# Function to save frame as PNG
def save_frame_as_png(frame, path=".", filename="saved_frame.png"):
    # Create the full file path
    full_path = f"{path}/{filename}"
    cv2.imwrite(full_path, frame)
    delete_old_files(path, 14)


# 프레임에 CAP 정보를 오버레이하고 저장
def save_frame_with_info(frame, json_cap, config, real_warnning):
    pipeline_update(
        "capture",
        "active",
        f"저장 중 {json_cap.get('EventCode', '')}",
    )
    font = ImageFont.truetype("malgun.ttf", 17)
    text_color = (255, 255, 255)  # White color
    shadow_color = (0, 0, 0)  # Black shadow
    img_full_pil = Image.fromarray(frame)
    draw_full = ImageDraw.Draw(img_full_pil)

    # CAP 정보 오버레이
    draw_full.text((10, 10), f"수신시각 : {json_cap['sent']}", shadow_color, font=font)
    draw_full.text((8, 8), f"수신시각 : {json_cap['sent']}", text_color, font=font)
    draw_full.text(
        (10, 30), f"재난 유형 : {json_cap['event']}", shadow_color, font=font
    )
    draw_full.text((8, 28), f"재난 유형 : {json_cap['event']}", text_color, font=font)
    draw_full.text(
        (10, 70), f"헤드라인 : {json_cap['headline']}", shadow_color, font=font
    )
    draw_full.text((8, 68), f"헤드라인 : {json_cap['headline']}", text_color, font=font)

    img_cv2 = np.array(img_full_pil)

    # real_warning이 False인 경우 전체 이미지에 블랙 박스 추가
    if not real_warnning:
        img_height, img_width = img_cv2.shape[:2]
        thickness = 2
        color = (200, 0, 255)  # 블랙
        img_cv2 = cv2.rectangle(
            img_cv2, (0, 0), (img_width - 1, img_height - 1), color, thickness
        )

    # 실제 저장 경로
    if os.path.exists(config["path_capture"]):
        timestamp = datetime.now().strftime("%H%M%S")
        file_name = os.path.join(
            config["path_capture"], f"{json_cap['identifier']}_{timestamp}.png"
        )
        file_name = os.path.normpath(file_name)
        success = cv2.imwrite(file_name, img_cv2)
        if success:
            pipeline_update("capture", "ok", os.path.basename(file_name))
            logger.info(
                f"[SAV-{len(list_json_cap)}]> 실제 경로에 화면 저장됨 : {file_name}"
            )
        else:
            logger.info(
                f"[SAV-{len(list_json_cap)}]> 실제 경로에 파일 저장 실패 : {file_name}"
            )
        delete_old_files(
            config["path_capture"], config["capture_stay"]
        )  # 경로에 config['capture_stay']일 지난 파일 삭제

    # 백업 저장 경로
    if os.path.exists(config["path_capture2"]):
        timestamp = datetime.now().strftime("%m%d%H%M%S")
        file_name2 = os.path.join(config["path_capture2"], f"{timestamp}.png")
        file_name2 = os.path.normpath(file_name2)
        success = cv2.imwrite(file_name2, img_cv2)
        # if success:
        #     logger.info(f"[SAV-{len(list_json_cap)}]> 백업 경로에 화면 저장됨 : {file_name2}")
        # else:
        #     logger.info(f"[SAV-{len(list_json_cap)}]> 백업 경로에 파일 저장 실패 : {file_name2}")
        # delete_old_files(config['path_capture2'], config['capture_stay']) # 경로에 config['capture_stay']일 지난 파일 삭제


# kbs_mandatory.json 파일 로드 함수
import urllib.request


def load_warnning_level_kbs(path):
    if path.startswith("http://") or path.startswith("https://"):
        # Handle URL
        with urllib.request.urlopen(path) as response:
            return json.load(response)
    else:
        # Handle local file
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


# 새로운 재난 메시지가 도착했는지 감시
def cap_monitor(config):
    global list_json_cap, list_json_emergency, terminate_program
    path_cap = config["path_cap"]
    print(f"{config['real_warnning_json_path']}")
    # warnning_level_kbs = load_warnning_level_kbs(config["real_warnning_json_path"]  )  # kbs_mandatory.json에서 이벤트 정보 로드

    # 마지막으로 처리한 파일의 생성 시간을 기록 (처음에는 0으로 설정)
    last_processed_time = time.time()

    while not terminate_program:  # 프로그램 종료 체크
        # 현재 폴더 내의 XML 파일 목록을 가져오고, 각 파일의 생성 시간을 확인
        cap_files = [f for f in os.listdir(path_cap) if f.endswith(".xml")]

        for file_name in cap_files:
            file_path = os.path.join(path_cap, file_name)
            file_creation_time = os.path.getctime(file_path)  # 파일 생성 시간 가져오기

            # 파일 생성 시간이 마지막 처리한 시간 이후인 경우만 처리
            if file_creation_time > last_processed_time:
                json_cap = parse_cap_file(
                    file_path, config
                )  # CAP 내용만 json으로 추출함.
                warnning_level_kbs = load_warnning_level_kbs(
                    config["real_warnning_json_path"]
                )  # kbs_mandatory.json에서 이벤트 정보 로드

                event_code = json_cap["EventCode"]
                current_warnning_level_kbs = warnning_level_kbs.get(event_code)
                json_cap["is_mandatory"] = current_warnning_level_kbs["is_mandatory"]
                if config["CAP_process_mandatory_only"]:
                    cap_check = json_cap and json_cap["is_mandatory"]
                else:
                    cap_check = json_cap
                # print(f" { current_warnning_level_kbs }  / event_code ={event_code} / cap_check ={cap_check}  ")

                if cap_check:
                    logger.info("")

                    # 긴급 재난이 수신된 경우 기존 메시지를 지우고 새로운 긴급 메시지만 유지
                    # 긴급 재난인 event_cod 8종 : 'FEW', 'EQW', 'EQI', 'EEW', 'CPW', 'CDC', 'CCW', 'CAW
                    # if event_code == 'EQW' and json_cap['Priority'] == '4':
                    if json_cap["emergency"] == True:
                        speak_text = f" {event_code}.  ** 긴급 재난경보 "
                        logger.info(f"[CAP-{ len(list_json_cap)}]-긴급> {speak_text}")
                        list_json_emergency.append(json_cap)
                        pipeline_update(
                            "cap_recv",
                            "ok",
                            f"긴급 CAP {event_code} {json_cap.get('event', '')}",
                        )
                        pipeline_update("queue", "active", "긴급 재난 대기열")
                    else:
                        list_json_cap.append(json_cap)
                        pipeline_update(
                            "cap_recv",
                            "ok",
                            f"{event_code} {json_cap.get('event', '')}",
                        )
                        pipeline_update(
                            "queue",
                            "active",
                            f"대기 {len(list_json_cap)}건 · {event_code}",
                        )
                        speak_text = f"{json_cap['event'].encode('utf-8').decode()}"
                        # 재난 메시지가 mandatory_events에 있을 경우 송출 여부 확인
                        if current_warnning_level_kbs["is_mandatory"]:
                            logger.info(
                                f"[CAP-{ len(list_json_cap)}]-CAP수신 - 의무 송출> {speak_text}"
                            )
                        elif not current_warnning_level_kbs["is_mandatory"]:
                            logger.info(
                                f"[CAP-{ len(list_json_cap)}]-CAP수신 - 자율송출> {speak_text}"
                            )
                        else:
                            logger.info(
                                f"[CAP-{ len(list_json_cap)}]-CAP수신 - 미확인 코드> {speak_text}"
                            )
                else:
                    speak_text = f"{event_code}. 송출대상이 아닙니다. "
                    logger.info(f"[CAP]-> CAP수신 - 미송출 {speak_text} ")
                speak_queue.put(f"{event_code}")
                # speak_queue.put(speak_text)  # Queue에 텍스트 데이터 추가

                # 마지막 처리된 파일의 생성 시간을 갱신
                last_processed_time = file_creation_time
                # else:
                #    logger.info(f"[CAP]> Old 파일 무시함")
                # 기존 코드에서 json_cap 수신 후
                current_time = datetime.now()
                received_caps.append((json_cap, current_time))
        time.sleep(1)
    logger.info(f"[CAP]> 쓰레드를 종료합니다.")


# OpenAI API 오류 처리 및 로깅 함수
def handle_openai_error(error, context="", logger=None):
    """
    OpenAI API 오류를 4가지 유형으로 분류하고 로그에 기록합니다.
    
    오류 유형:
    1. 인증 오류 (401) - API 키 문제, 잘못된 키, 만료된 키
    2. 네트워크/연결 오류 - 네트워크 문제, 타임아웃, 연결 실패
    3. API 제한/할당량 오류 (429) - Rate limit, Quota exceeded
    4. 기타 API 오류 (400, 403, 404, 500 등) - 잘못된 요청, 권한, 리소스 없음, 서버 오류
    
    Args:
        error: 발생한 예외 객체
        context: 오류 발생 컨텍스트 (함수명 등)
        logger: 로거 객체
    """
    if logger is None:
        try:
            logger = logging.getLogger()
        except:
            return
    
    error_type = "알 수 없는 오류"
    error_category = "기타 오류"
    error_details = str(error)
    status_code = None
    
    # OpenAI 라이브러리 오류 타입 확인
    if _OPENAI_AVAILABLE:
        # 1. 인증 오류 (401) - API 키 문제
        if isinstance(error, AuthenticationError) or (hasattr(error, 'status_code') and error.status_code == 401):
            error_type = "인증 오류 (Authentication Error)"
            error_category = "인증 오류"
            error_details = f"API 키가 잘못되었거나 만료되었습니다. 상태 코드: 401"
            if hasattr(error, 'body') and error.body:
                if isinstance(error.body, dict) and 'error' in error.body:
                    error_details += f" | 상세: {error.body.get('error', {}).get('message', '')}"
            logger.error(
                f"[OPENAI-ERROR-1] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
            )
            logger.error(
                f"[OPENAI-ERROR-1] 해결 방법: 1) OpenAI 플랫폼(https://platform.openai.com/account/api-keys)에서 API 키 확인 "
                f"2) 환경변수 OPENAI_API_KEY 확인 3) API 키가 만료되지 않았는지 확인"
            )
            return error_category
        
        # 2. 네트워크/연결 오류
        elif isinstance(error, APIConnectionError) or "connection" in str(error).lower() or "timeout" in str(error).lower():
            error_type = "네트워크/연결 오류 (Connection Error)"
            error_category = "네트워크 오류"
            error_details = f"OpenAI API 서버에 연결할 수 없습니다. 네트워크 문제 또는 타임아웃이 발생했습니다."
            if hasattr(error, '__cause__') and error.__cause__:
                error_details += f" | 원인: {str(error.__cause__)}"
            logger.error(
                f"[OPENAI-ERROR-2] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
            )
            logger.error(
                f"[OPENAI-ERROR-2] 해결 방법: 1) 네트워크 연결 확인 2) 방화벽 설정 확인 3) 잠시 후 재시도"
            )
            return error_category
        
        # 3. API 제한/할당량 오류 (429)
        elif isinstance(error, RateLimitError) or (hasattr(error, 'status_code') and error.status_code == 429):
            error_type = "API 제한/할당량 오류 (Rate Limit Error)"
            error_category = "할당량 오류"
            error_details = f"API 호출 한도에 도달했습니다. 상태 코드: 429"
            if hasattr(error, 'body') and error.body:
                if isinstance(error.body, dict) and 'error' in error.body:
                    error_details += f" | 상세: {error.body.get('error', {}).get('message', '')}"
            logger.error(
                f"[OPENAI-ERROR-3] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
            )
            logger.error(
                f"[OPENAI-ERROR-3] 해결 방법: 1) API 사용량 확인 2) 요청 간격 조정 3) OpenAI 플랫폼에서 할당량 확인"
            )
            return error_category
        
        # 4. 기타 API 오류 (400, 403, 404, 500 등)
        elif isinstance(error, APIStatusError) or (hasattr(error, 'status_code') and error.status_code):
            status_code = getattr(error, 'status_code', None)
            if status_code:
                if status_code == 400:
                    error_type = "잘못된 요청 오류 (Bad Request)"
                elif status_code == 403:
                    error_type = "권한 거부 오류 (Permission Denied)"
                elif status_code == 404:
                    error_type = "리소스 없음 오류 (Not Found)"
                elif status_code >= 500:
                    error_type = "서버 내부 오류 (Internal Server Error)"
                else:
                    error_type = f"API 상태 오류 (Status Code: {status_code})"
            else:
                error_type = "API 상태 오류 (API Status Error)"
            
            error_category = "기타 API 오류"
            error_details = f"API 요청 처리 중 오류가 발생했습니다."
            if status_code:
                error_details += f" 상태 코드: {status_code}"
            if hasattr(error, 'body') and error.body:
                if isinstance(error.body, dict) and 'error' in error.body:
                    error_details += f" | 상세: {error.body.get('error', {}).get('message', '')}"
            logger.error(
                f"[OPENAI-ERROR-4] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
            )
            logger.error(
                f"[OPENAI-ERROR-4] 해결 방법: 1) 요청 파라미터 확인 2) OpenAI 서비스 상태 확인 3) 잠시 후 재시도"
            )
            return error_category
    
    # OpenAI 라이브러리 오류가 아닌 경우
    error_str = str(error).lower()
    if "401" in error_str or "authentication" in error_str or "invalid_api_key" in error_str:
        error_type = "인증 오류 (Authentication Error)"
        error_category = "인증 오류"
        logger.error(
            f"[OPENAI-ERROR-1] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
        )
        return error_category
    elif "429" in error_str or "rate limit" in error_str or "quota" in error_str:
        error_type = "API 제한/할당량 오류 (Rate Limit Error)"
        error_category = "할당량 오류"
        logger.error(
            f"[OPENAI-ERROR-3] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
        )
        return error_category
    elif "connection" in error_str or "timeout" in error_str or "network" in error_str:
        error_type = "네트워크/연결 오류 (Connection Error)"
        error_category = "네트워크 오류"
        logger.error(
            f"[OPENAI-ERROR-2] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
        )
        return error_category
    else:
        error_type = "알 수 없는 오류 (Unknown Error)"
        error_category = "기타 오류"
        logger.error(
            f"[OPENAI-ERROR-4] {error_type} | {error_category} | 컨텍스트: {context} | {error_details}"
        )
        return error_category


# 자막 AI 확인 함수: 이미지에서 자막을 추출하고, GPT-4 모델을 사용하여 원본 자막과 일치 여부 확인
# ?? 241202 : 긴급 재난에서 화면에 재난 정보고 송출된느지 확인하는 방법 구현 필요
def subtitle_check_AI(frame, config):
    global list_json_cap, transmitted_caps  # 전역변수 list_json_cap 사용
    matched_index = None  # 일치하는 요소의 인덱스 저장
    gpt_result = None  # GPT-4 응답 저장

    try:
        if list_json_cap:
            cap0 = list_json_cap[0]
            pipeline_update(
                "ai",
                "active",
                f"{cap0.get('EventCode', '')} GPT 비교 중",
            )
        # logger.info(f"AI 자막 감시 시작")
        # 자막이 흐를때 까지 지연시간
        # time.sleep(config['delay_subtitle'])

        # 1. 자막 이미지 캡쳐 (자막 위치에서)
        # logger.info(f"[GPT]> 자막 영역 캡쳐 저장")

        pos_subtitle = config["position_subtitle"]
        subtitle_img = frame[
            pos_subtitle[0][1] : pos_subtitle[1][1], pos_subtitle[0][0] : pos_subtitle[1][0]
        ]

        # 2. OCR 처리: 이미지를 텍스트로 변환
        subtitle_text = pytesseract.image_to_string(subtitle_img, lang="kor")
        # logger.info(f"[GPT]> 자막 인식 결과: {subtitle_text}")

        # 자막 이미지 저장 (옵션, 디버그 용도)
        cv2.imwrite(config["subtitle_temp_image"], subtitle_img)
        # 3. list_json_cap의 각 요소와 비교
        for i, cap_data in enumerate(list_json_cap):
            subtitle_origin = cap_data["BroadcastText.ko-KR"]

            logger.info(f"[GPT-{len(list_json_cap)}]> API 호출 시작 - 재난유형: {cap_data.get('event', 'Unknown')}")
            try:
                # Guard: ensure OpenAI client is initialized
                if client is None or not hasattr(client, "chat"):
                    logger.error(f"[GPT-{len(list_json_cap)}]> OpenAI client not initialized; skipping API call for event: {cap_data.get('event', 'Unknown')}")
                    continue
                # Guard: ensure OpenAI client is initialized
                if client is None or not hasattr(client, "chat"):
                    logger.error(f"[GPT-{len(list_json_cap)}]> OpenAI client not initialized; skipping API call.")
                    return None
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "A, B 두문장을 비교하는데, B는 이미지에서 문자를 인식하는 과정에 일부 문자 인식 오류가 있을 수 있음을 감안하여, B가 A 문장 중에 일부로 판단되면 True, 그렇지 않으면 False로 답해줘",
                        },
                        {
                            "role": "user",
                            "content": f"A: {subtitle_origin}\n B: {subtitle_text}",
                        },
                    ],
                )
                logger.info(f"[GPT-{len(list_json_cap)}]> API 호출 완료 - 재난유형: {cap_data.get('event', 'Unknown')}")
            except Exception as api_error:
                # OpenAI API 오류 처리 및 로깅
                logger.error(f"[GPT-{len(list_json_cap)}]> API 호출 중 예외 발생 - 재난유형: {cap_data.get('event', 'Unknown')}")
                handle_openai_error(api_error, context=f"subtitle_check_AI - 재난유형: {cap_data.get('event', 'Unknown')}", logger=logger)
                return None

            try:
                gpt_response = completion.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"[GPT-{len(list_json_cap)}]> 재난 메시지와 방송 자막 비교 중 응답 파싱 오류 발생: {e}")
                logger.error(f"[GPT-{len(list_json_cap)}]> completion 객체: {completion}")
                return None

            logger.info(
                f"[GPT-{len(list_json_cap)}]> AI {i}번째 재난[ {cap_data['event'].encode('utf-8').decode()}] 메시지 비교 결과 = {gpt_response} | {subtitle_text}"
            )

            if gpt_response.lower() == "true":
                pipeline_update("ai", "ok", "자막 일치")
                # 자막이 일치하면 프레임을 저장
                save_frame_with_info(frame, cap_data, config, True)
                # logger.info(f"재난자막 방송 확인 / 남은 CAP 메시지 : {len(list_json_cap)}개 ")  # 디버깅용 출력
                # send_post_request(config, f"방금 {cap_data['EventCode']} {cap_data['headline']} 재난방송이 송출 확인되었습니다.", 0)
                gpt_result = True
                current_time = datetime.now()
                transmitted_caps.append((cap_data, current_time))
                list_json_cap.pop(i)
                pipeline_update(
                    "complete",
                    "ok",
                    f"송출 확인 {cap_data.get('EventCode', '')}",
                )
                threading.Timer(2.5, pipeline_reset_after_complete).start()
                return gpt_result
            else:
                pipeline_update("ai", "warn", "자막 불일치 — 재시도 가능")
                logger.info(f"[GPT-{len(list_json_cap)}]> 자막 불일치")
                gpt_result = False
        return gpt_result
    except Exception as e:
        # 스레드에서 발생한 모든 예외를 로깅
        logger.error(f"[GPT]> subtitle_check_AI 함수 실행 중 예외 발생: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[GPT]> 예외 상세 정보:\n{traceback.format_exc()}")
        return None


def frame_encode(frame):
    _, buffer = cv2.imencode(".jpg", frame)
    base64_image = base64.b64encode(buffer).decode("utf-8")
    return f"data:image/jpeg;base64,{base64_image}"


# 이미지 파일을 Base64로 인코딩하는 함수
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# 자막 AI 확인 함수: 이미지에서 자막을 추출하고, GPT-4 모델을 사용하여 원본 자막과 일치 여부 확인
# ?? 241202 : 긴급 재난에서 화면에 재난 정보 송출되는지 확인하는 방법 구현 필요
def emergency_check_AI(frame, config, emergency_cap):

    time.sleep(config["delay_Emergency_subtitle"])
    global latest_frame
    check_frame = latest_frame.copy() if latest_frame is not None else frame
    # 1. 자막 이미지 캡쳐 (긴급재난 메시지 영역은 일반 자막과 다름)
    pos_subtitle = config["position_emergency_subtitle"]
    subtitle_img_capture = check_frame[
        pos_subtitle[0][1] : pos_subtitle[1][1], pos_subtitle[0][0] : pos_subtitle[1][0]
    ]
    # 자막 이미지 저장 (옵션, 디버그 용도)
    cv2.imwrite(config["subtitle_temp_image"], subtitle_img_capture)
    # logger.info(f"[EMG-{len(list_json_cap)}]> 긴급 재난 메시지 영역 캡쳐 저장")

    # 2. list_json_cap에서 재난 메시지 내용 가져오고
    subtitle_origin = emergency_cap["BroadcastText.ko-KR"]
    #    subtitle_img = frame_encode(subtitle_img_capture)
    subtitle_img = encode_image(config["subtitle_temp_image"])

    try:
        completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "너는 방송 화면 이미지에 텍스트를 인식하고 이해할 수 있는 전문가야. 질문 답변은 단답형으로 True 또는 False로만 답해주세요.",
            },
            {
                "role": "user",
                "content": [
                    f"첨부 이미지 속에 다음의 재난 메시지 <{subtitle_origin}>가 내용상 포함되었다고 판단되는가?",
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{subtitle_img}"  # Base64로 인코딩된 이미지
                        },
                    },
                ],
            },
        ],
    )
    except Exception as api_error:
        # OpenAI API 오류 처리 및 로깅
        handle_openai_error(api_error, context=f"emergency_check_AI - 재난유형: {emergency_cap.get('event', 'Unknown')}", logger=logger)
        return None

    # 결과 처리
    try:
        responses = completion.choices[0].message.content.split("\n")
    except Exception as e:
        logger.error(f"[GPT]> 방송화면에서 긴급재난 메시지 확인 중 응답 파싱 오류 발생: {e}")
        return None

    gpt_response = responses[0].strip().lower()  # True or False
    gpt_text = (
        responses[1].strip() if len(responses) > 1 else "No explanation provided."
    )
    # gpt_reason = responses[2].strip() if len(responses) > 1 else "No explanation provided."
    # logger.info(f"[EMG-{len(list_json_cap)}]> AI 재난[ {emergency_cap['event'].encode('utf-8').decode()}] 긴급재난 메시지 체크 결과 = {gpt_response}")

    if gpt_response.lower() == "true":
        save_frame_with_info(check_frame, emergency_cap, config, True)
        logger.info(f"[EMG]> 긴급재난 송출 확인")
        # 자막이 일치하면 프레임을 저장
        # logger.info(f"재난자막 방송 확인 / 남은 CAP 메시지 : {len(list_json_cap)}개 ")  # 디버깅용 출력
    elif gpt_response.lower() == "false":
        save_frame_with_info(check_frame, emergency_cap, config, False)
        logger.info(f"[EMG]> 긴급재난 송출 미확인")
        send_post_request(
            config,
            f"{emergency_cap['EventCode']} **WARNNING** 긴급재난 자막 미확인. 점검바람. **WARNNING**",
            0,
        )
    return None


def compare_ticker_similarity(ticker_img, ticker_ref, debug=False):
    """
    두 이미지의 형상과 색상 유사도를 판단하는 함수.
    단색 이미지에 대해 오탐을 방지하고, 유사할수록 1에 가까운 유사도 값을 반환합니다.
    Parameters:
        ticker_img: 비교할 이미지 (numpy array)
        ticker_ref: 기준 이미지 (numpy array)
        debug: True일 경우 중간값 출력

    Returns:
        similarity (float): 0~1 사이. 1에 가까울수록 유사
    """
    # 1. 이미지 크기 맞추기
    if ticker_img.shape != ticker_ref.shape:
        ticker_img = cv2.resize(ticker_img, (ticker_ref.shape[1], ticker_ref.shape[0]))

    # 2. 회색조로 변환
    img_gray = cv2.cvtColor(ticker_img, cv2.COLOR_BGR2GRAY)
    ref_gray = cv2.cvtColor(ticker_ref, cv2.COLOR_BGR2GRAY)
    # 3. 표준편차로 단색 여부 확인
    std_img = np.std(img_gray)
    std_ref = np.std(ref_gray)

    # 단색 혹은 색 변화 거의 없음 → 유사하다고 판단하지 않음
    if std_img < 1:
        if debug:
            print(
                f"[DEBUG] 단색 이미지 감지: std_img={std_img:.2f}, std_ref={std_ref:.2f}"
            )
        return 0.0  # 유사하지 않다고 간주
    # 4. 템플릿 매칭 (차이 기반)
    res = cv2.matchTemplate(img_gray, ref_gray, cv2.TM_SQDIFF_NORMED)
    min_val, _, _, _ = cv2.minMaxLoc(res)
    # 5. 유사도 환산 (작을수록 유사하므로 1에서 빼기)
    similarity = 1 - min_val
    # if debug:
    #    print(
    #        f"[DEBUG] matchTemplate min_val={min_val:.4f}, similarity={similarity:.4f}"
    #    )

    return similarity


# CAP 파일을 수신한 후 비디오를 저장하는 함수
def save_video(config, tv):
    video_path = config["video_path"]  # 비디오 입력 경로
    out = cv2.VideoCapture(video_path)  # 비디오 캡처 객체 생성

    # 비디오 저장 설정
    frame_width = int(tv.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(tv.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # 코덱 설정
    output_file = os.path.join(
        config["video_save_path"],
        f"captured_video_{time.strftime('%Y%m%d_%H%M%S')}.mp4",
    )
    out = cv2.VideoWriter(output_file, fourcc, 30.0, (frame_width, frame_height))

    start_time = time.time()

    while (time.time() - start_time) < 20:  # 180초(3분) 동안 저장
        ret, frame = tv.read()
        if not ret:
            break
        out.write(frame)  # 프레임을 비디오 파일에 기록

    # tv.release()
    out.release()
    logger.info(f"[SAV]> 비디오 저장 완료: {output_file}")


def init_video_input_settings(config):
    raw = config.get("video_path")
    settings = {
        "kind": "usb",
        "usb_index": 0,
        "usb_label": "USB 카메라 #0",
        "rtmp_url": "",
        "obs_url": config.get(
            "video_path_obs", "rtmp://127.0.0.1:1935/live"
        ),
        "file_path": "",
        "media_folder": "",
    }
    mode = str(config.get("video_input_mode", "")).lower().strip()
    if mode in ("usb", "file"):
        settings["kind"] = mode
    if isinstance(raw, int):
        settings["kind"] = "usb"
        settings["usb_index"] = raw
        settings["usb_label"] = f"USB 카메라 #{raw}"
    elif isinstance(raw, str) and raw.isdigit():
        settings["kind"] = "usb"
        settings["usb_index"] = int(raw)
        settings["usb_label"] = f"USB 카메라 #{raw}"
    elif isinstance(raw, str):
        if os.path.isfile(raw):
            settings["kind"] = "file"
            settings["file_path"] = raw
            settings["media_folder"] = os.path.dirname(raw)
        elif os.path.isdir(raw):
            settings["kind"] = "file"
            settings["media_folder"] = raw
        else:
            settings["rtmp_url"] = raw
            if raw.startswith("rtmp"):
                settings["kind"] = "usb"
    if settings.get("kind") == "usb":
        names = list_dshow_video_device_names()
        idx = int(settings.get("usb_index", 0))
        if names and 0 <= idx < len(names) and _usb_device_excluded(names[idx]):
            for dev in enumerate_usb_video_devices(
                int(config.get("usb_scan_max_index", 8)), probe=False
            ):
                settings["usb_index"] = dev["index"]
                settings["usb_label"] = dev["label"]
                settings["usb_device_name"] = dev.get("name", "")
                break
    return settings


def sync_config_video_path(config, settings):
    kind = settings.get("kind", "rtmp")
    if kind == "usb":
        config["video_path"] = int(settings["usb_index"])
    elif kind == "obs":
        config["video_path"] = settings.get("obs_url") or settings.get("rtmp_url")
    elif kind == "file":
        config["video_path"] = settings.get("file_path", "")
    else:
        config["video_path"] = settings.get("rtmp_url", "")


def fit_frame_to_target(frame, target_width, target_height):
    """16:9(960x540) 출력. 크롭 없이 전체 화면 유지 — 세로 기준 맞춘 뒤 가로를 16:9까지 늘림."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return None
    if w == target_width and h == target_height:
        return frame
    target_ar = target_width / float(target_height)
    src_ar = w / float(h)
    if abs(src_ar - target_ar) < 1e-3:
        return cv2.resize(
            frame,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA,
        )
    # 4:3 등 16:9보다 좁은 화면: 높이 전부 살리고 가로만 늘려 맞춤 (상하 잘림 없음)
    if src_ar < target_ar:
        scaled_h = target_height
        scaled_w = max(1, int(round(w * (target_height / float(h)))))
        mid = cv2.resize(
            frame, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA
        )
        return cv2.resize(
            mid,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA,
        )
    # 16:9보다 넓은 화면: 가로 전부 유지하고 세로를 늘려 맞춤 (좌우 잘림 없음)
    scaled_w = target_width
    scaled_h = max(1, int(round(h * (target_width / float(w)))))
    mid = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
    return cv2.resize(
        mid, (target_width, target_height), interpolation=cv2.INTER_AREA
    )


class VideoSourceAdapter:
    """USB/RTMP/파일(이미지·동영상) 공통 read() 인터페이스."""

    def __init__(self):
        self._cap = None
        self._mode = "live"
        self._still = None
        self._tw = 960
        self._th = 540
        self.description = ""

    def open_from_settings(self, settings, target_width=960, target_height=540):
        self.release()
        self._tw, self._th = target_width, target_height
        kind = settings.get("kind", "rtmp")
        if kind == "file":
            path = (settings.get("file_path") or "").strip()
            if not path or not os.path.isfile(path):
                return False
            ext = os.path.splitext(path)[1].lower()
            if ext in IMAGE_FILE_EXTENSIONS:
                raw = imread_unicode(path)
                if raw is None:
                    logger.error(f"[VID]> 이미지 읽기 실패: {path}")
                    return False
                self._still = fit_frame_to_target(raw, target_width, target_height)
                self._mode = "image"
                self.description = f"이미지 {os.path.basename(path)}"
                return True
            self._cap = open_video_file_unicode(path)
            if self._cap is None or not self._cap.isOpened():
                logger.error(f"[VID]> 동영상 열기 실패: {path}")
                return False
            self._mode = "video"
            self.description = f"동영상 {os.path.basename(path)}"
            return True
        vid, desc = open_video_capture_from_settings(settings)
        if vid is None or not vid.isOpened():
            if vid is not None:
                vid.release()
            return False
        if kind == "usb":
            try:
                if not configure_live_capture(vid, target_width, target_height):
                    try:
                        vid.release()
                    except Exception:
                        pass
                    return False
            except Exception as e:
                logger.warning(f"[VID]> USB 설정 중 예외: {e}")
                try:
                    vid.release()
                except Exception:
                    pass
                return False
        self._cap = vid
        self._mode = "live"
        self.description = desc
        return True

    def isOpened(self):
        if self._mode == "image":
            return self._still is not None
        return self._cap is not None and self._cap.isOpened()

    def read(self):
        if self._mode == "image":
            return True, self._still.copy()
        if self._cap is None:
            return False, None
        ret, frame = _safe_capture_read(self._cap)
        if not ret and self._mode == "video":
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = _safe_capture_read(self._cap)
        if not ret or frame is None:
            return False, None
        frame = fit_frame_to_target(frame, self._tw, self._th)
        return True, frame

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self._tw)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self._th)
        if self._cap is not None:
            return self._cap.get(prop)
        return 0.0

    def release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self._still = None


def list_dshow_video_device_names():
    """DirectShow 비디오 장치 이름 목록(ffmpeg). 인덱스 순서와 대체로 일치."""
    names = []
    try:
        import subprocess

        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-list_devices",
                "true",
                "-f",
                "dshow",
                "-i",
                "dummy",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            errors="replace",
        )
        text = (proc.stderr or "") + (proc.stdout or "")
        for line in text.splitlines():
            stripped = line.strip()
            if "Alternative name" in stripped:
                continue
            if '(video)' not in stripped or '"' not in stripped:
                continue
            start = stripped.find('"')
            end = stripped.rfind('"')
            if end > start:
                names.append(stripped[start + 1 : end])
    except Exception as e:
        try:
            logger.info(f"[VID]> ffmpeg 장치 목록 조회 실패: {e}")
        except Exception:
            pass
    return names


def try_open_usb_capture(usb_index, device_name=None):
    """USB 열기: 인덱스 우선(이름 경고 감소), 실패 시 장치명."""
    idx = int(usb_index)
    cap, backend = try_open_usb_by_index(idx)
    if cap is not None:
        ret, _ = _safe_capture_read(cap)
        if ret:
            return cap, backend
        cap.release()
    names = list_dshow_video_device_names()
    for name in (device_name, names[idx] if 0 <= idx < len(names) else None):
        if not name or not isinstance(name, str):
            continue
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(name, backend)
            if cap is not None and cap.isOpened():
                ret, _ = _safe_capture_read(cap)
                if ret:
                    return cap, backend
                cap.release()
    cap, backend = try_open_usb_by_index(usb_index)
    return cap, backend


USB_DEVICE_NAME_EXCLUDE = ("ndi",)


def _usb_device_excluded(name):
    n = (name or "").lower()
    return any(token in n for token in USB_DEVICE_NAME_EXCLUDE)


def _safe_capture_read(cap):
    """read()가 손상 프레임으로 Assertion을 내지 않도록 보호."""
    if cap is None or not cap.isOpened():
        return False, None
    try:
        ret, frame = cap.read()
    except (cv2.error, RuntimeError, SystemError) as e:
        try:
            logger.warning(f"[VID]> VideoCapture.read 오류: {e}")
        except Exception:
            pass
        return False, None
    except Exception:
        return False, None
    if not ret or frame is None:
        return False, None
    if getattr(frame, "size", 0) <= 0 or len(frame.shape) < 2:
        return False, None
    return True, frame


def _warmup_capture(cap, n=3):
    ok = 0
    for _ in range(n):
        ret, _ = _safe_capture_read(cap)
        if ret:
            ok += 1
    return ok > 0


def configure_live_capture(cap, width=960, height=540):
    """USB: 버퍼만 줄임. 화면 크기는 read()에서 fit_frame_to_target 처리."""
    del width, height
    if cap is None or not cap.isOpened():
        return False
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    try:
        return _warmup_capture(cap, 1)
    except Exception as e:
        try:
            logger.warning(f"[VID]> USB 워밍업 실패(무시): {e}")
        except Exception:
            pass
        return True


def try_open_usb_by_index(usb_index):
    idx = int(usb_index)
    backends = (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY)
    for backend in backends:
        cap = cv2.VideoCapture(idx, backend)
        if cap is not None and cap.isOpened():
            ret, _ = _safe_capture_read(cap)
            if ret:
                return cap, backend
        if cap is not None:
            cap.release()
    return None, None


def enumerate_usb_video_devices(max_index=8, probe=False):
    """USB 목록: ffmpeg 이름·인덱스만 (재생 중 장치 점유 시에도 목록 표시)."""
    names = list_dshow_video_device_names()
    devices = []
    limit = min(len(names), max_index + 1) if names else max_index + 1
    for idx in range(limit):
        dev_name = names[idx] if idx < len(names) else f"USB 카메라 #{idx}"
        if _usb_device_excluded(dev_name):
            continue
        devices.append(
            {
                "index": idx,
                "name": dev_name,
                "label": f"[{idx}] {dev_name}",
            }
        )
    if not devices and not names:
        for idx in range(max_index + 1):
            devices.append(
                {
                    "index": idx,
                    "name": f"USB #{idx}",
                    "label": f"[{idx}] USB 카메라 #{idx}",
                }
            )
    if probe:
        for dev in devices:
            cap, _ = try_open_usb_capture(dev["index"], dev.get("name"))
            if cap is None:
                dev["label"] += " (미응답)"
            else:
                cap.release()
    try:
        logger.info(
            f"[VID]> USB 장치 목록 {len(devices)}개: "
            + ", ".join(d["label"] for d in devices[:8])
            + (" ..." if len(devices) > 8 else "")
        )
    except Exception:
        pass
    return devices


def open_video_capture_from_settings(settings):
    kind = settings.get("kind", "rtmp")
    vid = None
    desc = ""
    if kind == "usb":
        usb_index = settings.get("usb_index", 0)
        if isinstance(usb_index, str) and usb_index.startswith("name:"):
            dev_name = usb_index[5:]
            names = list_dshow_video_device_names()
            if dev_name in names:
                usb_index = names.index(dev_name)
            else:
                usb_index = 0
        dev_name = settings.get("usb_device_name") or ""
        vid, _backend = try_open_usb_capture(usb_index, dev_name or None)
        desc = settings.get("usb_label") or dev_name or f"USB #{usb_index}"
        if vid is None:
            desc = f"USB #{usb_index} (열기 실패)"
    elif kind == "obs":
        url = settings.get("obs_url") or settings.get("rtmp_url", "")
        vid = cv2.VideoCapture(url)
        desc = f"OBS {url}"
    elif kind == "rtmp":
        url = settings.get("rtmp_url", "")
        if not url:
            return None, "RTMP (주소 없음)"
        vid = cv2.VideoCapture(url)
        desc = f"RTMP {url}"
    else:
        url = settings.get("rtmp_url", "")
        vid = cv2.VideoCapture(url) if url else None
        desc = f"RTMP {url}" if url else "미설정"
    return vid, desc


def connect_video_with_retries(
    settings, max_tries=8, wait_sec=5, target_width=960, target_height=540
):
    if settings.get("kind") == "file":
        source = VideoSourceAdapter()
        try:
            opened = source.open_from_settings(
                settings, target_width, target_height
            )
        except Exception as e:
            logger.error(f"[VID]> 파일 소스 열기 예외: {e}")
            opened = False
        if opened:
            logger.info(f"[VID]> 입력 소스: {source.description}")
            return source
        logger.error(
            f"[VID]> 파일 소스 열기 실패: {settings.get('file_path', '')}"
        )
        return None
    for attempt in range(max_tries):
        logger.info(
            f"[VID]> 비디오소스 연결 재시도 중... ({attempt + 1}/{max_tries})"
        )
        source = VideoSourceAdapter()
        try:
            opened = source.open_from_settings(
                settings, target_width, target_height
            )
        except Exception as e:
            logger.error(f"[VID]> 소스 열기 예외: {e}")
            opened = False
        if opened:
            logger.info(f"[VID]> 입력 소스: {source.description}")
            return source
        source.release()
        time.sleep(wait_sec)
    return None


def process_ui_commands(frame, config, state, emergency_tx_endtime):
    """UI·키보드 공통 명령 처리. state는 monitor 루프 지역 상태 dict."""
    global audio_on, terminate_program, list_json_cap, player
    while True:
        try:
            cmd = ui_command_queue.get_nowait()
        except queue.Empty:
            break
        if cmd == "quit":
            request_app_shutdown()
        elif isinstance(cmd, tuple) and cmd[0] == "test_mode_cap":
            run_test_mode_ai_from_cap_file(frame, config, state, cmd[1])
        elif cmd == "test_mode":
            run_test_mode_ai(frame, config, state)
        elif cmd == "report":
            prog_state_logger(datetime.now(), emergency_tx_endtime)
            report_caps(config)


def default_test_cap_dict():
    return {
        "identifier": "TEST-TEST-20260106-TEST_1",
        "sent": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "source": "테스트",
        "event": "테스트재난",
        "EventCode": "TEST",
        "headline": "테스트 재난 경보",
        "BroadcastText.ko-KR": (
            "테스트 재난 메시지입니다. 방송 화면에 자막이 표시되는지 확인합니다."
        ),
        "Broadcastflag": "Y",
        "Magnitude": None,
        "Priority": "3",
        "emergency": False,
        "is_mandatory": True,
    }


def load_test_cap_from_config(config):
    """Override.yml test_cap_fixture: CAP XML 또는 CAP JSON 경로."""
    path = (config.get("test_cap_fixture") or "").strip()
    if not path or not os.path.isfile(path):
        return default_test_cap_dict()
    try:
        low = path.lower()
        if low.endswith(".xml"):
            cap = parse_cap_file(path, config)
            cap.setdefault("is_mandatory", True)
            logger.info(f"[TEST-MODE]> test_cap_fixture XML: {path}")
            return cap
        if low.endswith(".json"):
            with open(path, encoding="utf-8") as f:
                cap = json.load(f)
            if isinstance(cap, dict):
                cap.setdefault("is_mandatory", True)
                logger.info(f"[TEST-MODE]> test_cap_fixture JSON: {path}")
                return cap
    except Exception as e:
        logger.error(f"[TEST-MODE]> test_cap_fixture 로드 실패 ({path}): {e}")
    return default_test_cap_dict()


def run_test_mode_ai(frame, config, state, cap_override=None):
    global list_json_cap
    logger.info(f"[TEST-MODE]> 테스트 모드 시작")
    queue_backup = None
    if cap_override is not None:
        queue_backup = list(list_json_cap)
        list_json_cap.clear()
        list_json_cap.append(cap_override)
        logger.info(
            f"[TEST-MODE]> 지정 CAP 사용: {cap_override.get('EventCode')} "
            f"/ {cap_override.get('event')}"
        )
    elif not list_json_cap:
        test_cap_data = load_test_cap_from_config(config)
        list_json_cap.append(test_cap_data)
        logger.info(f"[TEST-MODE]> 테스트용 CAP 추가: {test_cap_data['event']}")
    else:
        cap0 = list_json_cap[0]
        logger.info(
            f"[TEST-MODE]> 송출 대기 CAP 사용 (선택 불가·첫 번째): "
            f"{cap0.get('EventCode')} / {cap0.get('event')}"
        )

    def _ai_job():
        try:
            subtitle_check_AI(frame, config)
        finally:
            if queue_backup is not None:
                list_json_cap.clear()
                list_json_cap.extend(queue_backup)

    state["subtitle_processed"] = False
    state["ticker_state_duration"] = config["delay_subtitle"] + 1
    state["time_ticker_state_change"] = time.time() - state["ticker_state_duration"]
    subtitle_thread = threading.Thread(target=_ai_job)
    subtitle_thread.start()
    logger.info(
        f"[TEST-MODE]> 재난 AI 호출 : {list_json_cap[0]['event'].encode('utf-8').decode()}"
    )
    timestamp = datetime.now().strftime("%H%M%S")
    save_frame_as_png(frame, "./temp", f"test_ai_check_{timestamp}.png")


def run_test_mode_ai_from_cap_file(frame, config, state, cap_path):
    try:
        if cap_path.lower().endswith(".xml"):
            cap = parse_cap_file(cap_path, config)
        elif cap_path.lower().endswith(".json"):
            with open(cap_path, encoding="utf-8") as f:
                cap = json.load(f)
        else:
            logger.error("[TEST-MODE]> CAP 파일은 .xml 또는 .json 이어야 합니다.")
            return
        cap.setdefault("is_mandatory", True)
        run_test_mode_ai(frame, config, state, cap_override=cap)
    except Exception as e:
        logger.error(f"[TEST-MODE]> CAP 파일 처리 실패: {e}")


def toggle_monitor_audio(config):
    global audio_on, player
    vpath = config.get("video_path")
    if vpath == 0 or vpath == "0":
        logger.info("[VID]> USB 입력에서는 오디오 토글이 지원되지 않습니다.")
        return
    if config.get("ffmpeg_enable") != 1:
        logger.info("[VID]> ffmpeg_enable=0 이면 오디오 토글을 사용할 수 없습니다.")
        return
    audio_on = not audio_on
    if player is not None:
        try:
            player.set_pause(not audio_on)
        except Exception:
            logger.warning("Failed to toggle player pause")
    logger.info(f"[VID]> Audio Out {audio_on}")


def open_config_editor(parent, config):
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox

    win = tk.Toplevel(parent)
    win.title("설정 파일 편집")
    win.geometry("880x560")
    win.configure(bg="#141414")
    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True, padx=8, pady=8)
    editors = {}
    for label, path, editable in (
        ("Override.yml (저장)", OVERRIDE_YML, True),
        ("Default.yml (참고)", DEFAULT_YML, False),
    ):
        fr = ttk.Frame(nb)
        nb.add(fr, text=label)
        txt = scrolledtext.ScrolledText(
            fr, wrap="none", font=("Consolas", 10), undo=True
        )
        txt.pack(fill="both", expand=True)
        try:
            with open(path, encoding="utf-8") as f:
                txt.insert("1.0", f.read())
        except Exception as e:
            txt.insert("1.0", f"# load error: {e}\n")
        if not editable:
            txt.configure(state="disabled")
        editors[path] = txt

    def save_override():
        try:
            with open(OVERRIDE_YML, "w", encoding="utf-8") as f:
                f.write(editors[OVERRIDE_YML].get("1.0", "end-1c"))
            fresh = read_config(DEFAULT_YML, OVERRIDE_YML)
            config.clear()
            config.update(fresh)
            messagebox.showinfo("저장", "Override.yml 저장 완료")
        except Exception as e:
            messagebox.showerror("저장 실패", str(e))

    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Button(bar, text="Override 저장", command=save_override).pack(side="left")
    ttk.Button(bar, text="닫기", command=win.destroy).pack(side="right")


def run_watcher_single_window(config):
    """1024 이하 폭 운영 UI: 방송 미리보기 + CAP→캡처 절차 패널."""
    import tkinter as tk
    from tkinter import ttk, filedialog
    from PIL import Image, ImageTk

    global terminate_program, ui_status_text, ui_display_bgr, ui_root
    global ui_pipeline_refresh_cb, fullscreen_state, _apply_video_save_prefs

    init_operator_pipeline()
    pipeline_update("monitor", "wait", "비디오 소스 대기")

    BG = "#0c0c0c"
    PANEL = "#161616"
    BORDER = "#2a2a2a"
    FG = "#e8e8e8"
    STATUS_FG = {
        "idle": "#666666",
        "wait": "#888888",
        "active": "#4da6ff",
        "ok": "#5dcc5d",
        "warn": "#e6b422",
        "fail": "#e05555",
    }

    root = tk.Tk()
    ui_root = root
    root.title(f"KBS TV-Alert Watcher — {APP_VERSION}")
    root.configure(bg=BG)
    root.geometry(f"{UI_MAX_WIDTH}x720")
    root.minsize(880, 640)
    root.maxsize(UI_MAX_WIDTH + 4, 2000)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TLabelframe", background=BG, foreground=FG)
    style.configure("TLabelframe.Label", background=BG, foreground=FG)
    style.configure("TButton", background=PANEL, foreground=FG)
    style.configure("TEntry", fieldbackground="#1e1e1e", foreground=FG)
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=PANEL, foreground=FG, padding=(8, 4))
    style.map("TNotebook.Tab", background=[("selected", "#2a2a2a")])

    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=8, pady=6)

    left = tk.Frame(body, bg=BG)
    left.pack(side="left", fill="y")
    right = tk.Frame(body, bg=BG, width=372)
    right.pack(side="right", fill="both", expand=True, padx=(8, 0))
    right.pack_propagate(False)

    monitor = tk.Frame(left, bg=BORDER, bd=1, relief=tk.SOLID)
    monitor.pack()
    video_canvas = tk.Canvas(
        monitor,
        width=UI_PREVIEW_W,
        height=UI_PREVIEW_H,
        bg="#000000",
        highlightthickness=0,
    )
    video_canvas.pack()
    video_canvas._photo = None
    ui_display_bgr = blank_display_frame()

    vid_btn_row = tk.Frame(left, bg=BG)
    vid_btn_row.pack(fill="x", pady=4)
    status_var = tk.StringVar(value=ui_status_text)
    tk.Label(
        vid_btn_row,
        textvariable=status_var,
        bg=BG,
        fg="#9a9a9a",
        font=("Malgun Gothic", 8),
        wraplength=UI_PREVIEW_W,
        justify="left",
    ).pack(side="left", fill="x", expand=True)

    def open_fullscreen_view():
        if fullscreen_state.get("win") is not None:
            return
        win = tk.Toplevel(root)
        win.attributes("-fullscreen", True)
        win.configure(bg="#000000")
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        fcanvas = tk.Canvas(
            win, width=sw, height=sh, bg="#000000", highlightthickness=0
        )
        fcanvas.pack(fill="both", expand=True)
        fullscreen_state["win"] = win
        fullscreen_state["canvas"] = fcanvas
        fullscreen_state["photo"] = None

        def close_fs(_e=None):
            try:
                win.destroy()
            except Exception:
                pass
            fullscreen_state["win"] = None
            fullscreen_state["canvas"] = None

        win.bind("<Escape>", close_fs)
        win.protocol("WM_DELETE_WINDOW", close_fs)

    ttk.Button(vid_btn_row, text="전체 화면 (Esc)", command=open_fullscreen_view).pack(
        side="right"
    )

    proc_frame = ttk.LabelFrame(right, text="CAP → 방송 → 캡처 절차")
    proc_frame.pack(fill="both", expand=True)
    pipeline_rows = {}

    def refresh_pipeline_ui():
        with operator_pipeline_lock:
            snap = {
                sid: dict(operator_pipeline.get(sid, {}))
                for sid, _ in OPERATOR_PIPELINE_STEPS
            }
        for sid, _label in OPERATOR_PIPELINE_STEPS:
            row = pipeline_rows.get(sid)
            if not row:
                continue
            info = snap.get(sid, {})
            st = info.get("status", "idle")
            row["state"].configure(
                text=_pipeline_status_ko.get(st, st),
                fg=STATUS_FG.get(st, FG),
            )
            detail = info.get("detail") or "—"
            time_s = info.get("updated") or ""
            row["detail"].configure(text=f"{detail}" + (f"  ({time_s})" if time_s else ""))

    ui_pipeline_refresh_cb = refresh_pipeline_ui

    for sid, label in OPERATOR_PIPELINE_STEPS:
        row_f = tk.Frame(proc_frame, bg=BG)
        row_f.pack(fill="x", padx=6, pady=2)
        tk.Label(
            row_f, text=label, width=16, anchor="w", bg=BG, fg=FG, font=("Malgun Gothic", 9)
        ).pack(side="left")
        st_lbl = tk.Label(
            row_f, text="대기", width=6, anchor="w", bg=BG, fg="#666", font=("Malgun Gothic", 9, "bold")
        )
        st_lbl.pack(side="left")
        det_lbl = tk.Label(
            row_f, text="—", anchor="w", bg=BG, fg="#aaa", font=("Malgun Gothic", 8), wraplength=200, justify="left"
        )
        det_lbl.pack(side="left", fill="x", expand=True)
        pipeline_rows[sid] = {"state": st_lbl, "detail": det_lbl}

    cap_info = tk.StringVar(value="대기 CAP 없음")
    ttk.Label(proc_frame, text="현재 대기", font=("Malgun Gothic", 8)).pack(anchor="w", padx=6, pady=(8, 0))
    tk.Label(
        proc_frame,
        textvariable=cap_info,
        bg=BG,
        fg="#ccc",
        wraplength=340,
        justify="left",
        font=("Malgun Gothic", 9),
    ).pack(anchor="w", padx=6, pady=(0, 6))

    def refresh_cap_summary():
        if list_json_cap:
            c0 = list_json_cap[0]
            cap_info.set(
                f"{c0.get('EventCode', '')} · {c0.get('event', '')}\n"
                f"{(c0.get('headline') or '')[:80]}"
            )
        elif list_json_emergency:
            c0 = list_json_emergency[0]
            cap_info.set(f"긴급 {c0.get('EventCode', '')} · {c0.get('event', '')}")
        else:
            cap_info.set("대기 CAP 없음")

    def paint_frame_on_canvas(canvas, frame_bgr, tw, th):
        if frame_bgr.shape[1] != DISPLAY_WIDTH or frame_bgr.shape[0] != DISPLAY_HEIGHT:
            frame_bgr = cv2.resize(frame_bgr, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
        show = cv2.resize(frame_bgr, (tw, th))
        rgb = cv2.cvtColor(np.ascontiguousarray(show), cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb, mode="RGB")
        photo = ImageTk.PhotoImage(image=pil)
        canvas.delete("vframe")
        canvas.create_image(0, 0, anchor=tk.NW, image=photo, tags="vframe")
        canvas._photo = photo
        return photo

    def update_video_preview():
        if terminate_program:
            return
        with ui_frame_lock:
            frame = (
                ui_display_bgr.copy()
                if ui_display_bgr is not None
                else blank_display_frame()
            )
        paint_frame_on_canvas(video_canvas, frame, UI_PREVIEW_W, UI_PREVIEW_H)
        fcv = fullscreen_state.get("canvas")
        fwin = fullscreen_state.get("win")
        if fcv is not None and fwin:
            sw = max(fcv.winfo_width(), 64)
            sh = max(fcv.winfo_height(), 64)
            if sw < 300:
                sw, sh = fwin.winfo_screenwidth(), fwin.winfo_screenheight()
            fs_show = cv2.resize(frame, (sw, sh))
            rgb_fs = cv2.cvtColor(np.ascontiguousarray(fs_show), cv2.COLOR_BGR2RGB)
            pil_fs = Image.fromarray(rgb_fs, mode="RGB")
            photo_fs = ImageTk.PhotoImage(image=pil_fs)
            fcv.delete("vframe")
            fcv.create_image(0, 0, anchor=tk.NW, image=photo_fs, tags="vframe")
            fcv._photo = photo_fs
        try:
            status_var.set(ui_status_text)
        except Exception:
            pass
        refresh_pipeline_ui()
        refresh_cap_summary()
        if not terminate_program:
            root.after(33, update_video_preview)

    input_note = ttk.Notebook(root)
    input_note.pack(fill="x", padx=8, pady=4)
    _init_kind = video_input_settings.get("kind", "usb")
    if _init_kind not in ("usb", "file"):
        _init_kind = "usb"
    kind_var = tk.StringVar(value=_init_kind)

    tab_usb = ttk.Frame(input_note, padding=6)
    tab_file = ttk.Frame(input_note, padding=6)
    input_note.add(tab_usb, text="USB")
    input_note.add(tab_file, text="파일폴더")

    ttk.Label(tab_usb, text="USB (NDI 제외) · 선택 시 자동 연결").pack(anchor="w")
    usb_list = tk.Listbox(
        tab_usb, height=4, bg="#1a1a1a", fg=FG, selectbackground="#404040"
    )
    usb_list.pack(fill="x", pady=4)
    usb_devices = []

    def refresh_usb():
        usb_list.delete(0, tk.END)
        usb_devices.clear()
        max_idx = int(config.get("usb_scan_max_index", 8))
        for dev in enumerate_usb_video_devices(max_idx, probe=False):
            usb_devices.append(dev)
            usb_list.insert(tk.END, dev["label"])
        sel = video_input_settings.get("usb_index", 0)
        for i, dev in enumerate(usb_devices):
            if dev["index"] == sel:
                usb_list.selection_set(i)
                usb_list.see(i)
                break

    ttk.Button(tab_usb, text="USB 새로고침", command=refresh_usb).pack(anchor="w")

    saved_fp = (video_input_settings.get("file_path") or "").strip()
    saved_folder = (video_input_settings.get("media_folder") or "").strip()
    if not saved_folder and saved_fp and os.path.isfile(saved_fp):
        saved_folder = os.path.dirname(saved_fp)
    folder_var = tk.StringVar(value=saved_folder)
    file_var = tk.StringVar(value=saved_fp)
    media_paths = []

    ttk.Label(tab_file, text="미디어 폴더 · 더블클릭으로 재생").pack(anchor="w")
    folder_row = ttk.Frame(tab_file)
    folder_row.pack(fill="x", pady=2)
    folder_entry = ttk.Entry(folder_row, textvariable=folder_var)
    folder_entry.pack(side="left", fill="x", expand=True)

    media_list = tk.Listbox(
        tab_file,
        height=6,
        bg="#1a1a1a",
        fg=FG,
        selectbackground="#404040",
        selectforeground="#ffffff",
    )
    media_list.pack(fill="both", expand=True, pady=4)

    def refresh_media_list(select_path=None):
        media_list.delete(0, tk.END)
        media_paths.clear()
        folder = folder_var.get().strip()
        for path in list_playable_media_in_folder(folder):
            media_paths.append(path)
            media_list.insert(tk.END, os.path.basename(path))
        pick = select_path or file_var.get().strip()
        if pick and pick in media_paths:
            idx = media_paths.index(pick)
            media_list.selection_set(idx)
            media_list.see(idx)

    def browse_media_folder():
        initial = folder_var.get().strip() or os.path.expanduser("~")
        folder = filedialog.askdirectory(title="미디어 폴더 선택", initialdir=initial)
        if not folder:
            return
        folder_var.set(folder)
        kind_var.set("file")
        refresh_media_list()
        if media_paths:
            file_var.set(media_paths[0])
        schedule_auto_apply()

    ttk.Button(folder_row, text="폴더 선택", command=browse_media_folder).pack(
        side="left", padx=(6, 0)
    )

    def on_media_double_click(_event=None):
        sel = media_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(media_paths):
            return
        file_var.set(media_paths[idx])
        kind_var.set("file")
        schedule_auto_apply()

    media_list.bind("<Double-Button-1>", on_media_double_click)

    _tab_by_kind = {"usb": 0, "file": 1}
    _kind_by_tab = {v: k for k, v in _tab_by_kind.items()}

    def on_tab_selected(_event=None):
        idx = input_note.index(input_note.select())
        kind = _kind_by_tab.get(idx)
        if kind:
            kind_var.set(kind)
        schedule_auto_apply()

    def sync_tab_from_kind(*_):
        kind = kind_var.get()
        idx = _tab_by_kind.get(kind, 0)
        if input_note.index(input_note.select()) != idx:
            input_note.select(idx)

    input_note.bind("<<NotebookTabChanged>>", on_tab_selected)
    kind_var.trace_add("write", sync_tab_from_kind)

    _debounce_id = [None]

    def apply_video_source():
        global ui_status_text
        kind = kind_var.get()
        with video_input_lock:
            video_input_settings["kind"] = kind
            if kind == "usb":
                sel = usb_list.curselection()
                if not sel:
                    return
                dev = usb_devices[sel[0]]
                video_input_settings["usb_index"] = dev["index"]
                video_input_settings["usb_label"] = dev["label"]
                video_input_settings["usb_device_name"] = dev.get("name", "")
            elif kind == "file":
                path = file_var.get().strip()
                if not path or not os.path.isfile(path):
                    status_var.set("폴더에서 파일을 더블클릭하세요.")
                    return
                video_input_settings["file_path"] = path
                video_input_settings["media_folder"] = folder_var.get().strip()
            sync_config_video_path(config, video_input_settings)
            save_ui_prefs_from_video_settings(dict(video_input_settings))
        video_reconnect_event.set()
        ui_status_text = f"자동 연결: {kind}"
        status_var.set(ui_status_text)

    def schedule_auto_apply(*_):
        if _debounce_id[0] is not None:
            root.after_cancel(_debounce_id[0])
        _debounce_id[0] = root.after(450, apply_video_source)

    _apply_video_save_prefs = apply_video_source
    kind_var.trace_add("write", schedule_auto_apply)
    file_var.trace_add("write", schedule_auto_apply)
    usb_list.bind("<<ListboxSelect>>", lambda _e: schedule_auto_apply())

    ctl = ttk.LabelFrame(root, text="제어")
    ctl.pack(fill="x", padx=8, pady=(0, 8))
    btn_row = ttk.Frame(ctl)
    btn_row.pack(fill="x", padx=6, pady=6)

    def pick_cap_xml_for_ai_test():
        path = filedialog.askopenfilename(
            title="AI 테스트 CAP",
            filetypes=[("CAP", "*.xml"), ("JSON", "*.json")],
            initialdir=config.get("path_cap", "."),
        )
        if path:
            ui_command_queue.put(("test_mode_cap", path))

    for label, cmd in (
        ("리포트 (b)", "report"),
        ("AI 테스트 (m)", "test_mode"),
        ("CAP 파일 AI", "test_mode_cap_ui"),
        ("설정 편집", "config_edit_ui"),
        ("종료 (q)", "quit"),
    ):
        if cmd == "test_mode_cap_ui":
            ttk.Button(btn_row, text=label, command=pick_cap_xml_for_ai_test).pack(
                side="left", padx=3
            )
        elif cmd == "config_edit_ui":
            ttk.Button(
                btn_row, text=label, command=lambda: open_config_editor(root, config)
            ).pack(side="left", padx=3)
        else:
            ttk.Button(
                btn_row,
                text=label,
                command=lambda c=cmd: ui_command_queue.put(c),
            ).pack(side="left", padx=3)

    ttk.Label(
        ctl,
        text="비디오: 탭·목록·URL 변경 시 자동 연결 · 설정은 Watcher_ui_prefs.yml 저장",
        font=("Malgun Gothic", 8),
    ).pack(anchor="w", padx=8, pady=(0, 6))

    def on_key(event):
        keys = {"q": "quit", "b": "report", "m": "test_mode"}
        k = event.keysym.lower()
        if k in keys:
            ui_command_queue.put(keys[k])

    root.bind("<KeyPress>", on_key)

    def on_close():
        with video_input_lock:
            save_ui_prefs_from_video_settings(dict(video_input_settings))
        request_app_shutdown()

    root.protocol("WM_DELETE_WINDOW", on_close)
    sync_tab_from_kind()
    refresh_usb()
    refresh_media_list(file_var.get().strip() or None)
    refresh_pipeline_ui()
    update_video_preview()
    root.after(600, apply_video_source)
    root.mainloop()
    ui_pipeline_refresh_cb = None
    try:
        root.destroy()
    except Exception:
        pass

# 비디오 모니터링 쓰레드에서 자막 AI 쓰레드를 호출하는 예시
def video_monitor(config):
    try:
        _video_monitor_body(config)
    except Exception as e:
        logger.error(f"[VID]> video_monitor 예외: {e}")
        request_app_shutdown(from_video=True)
    finally:
        logger.info(f"[TV 화면 감시]> 쓰레드를 종료합니다.")


def _video_monitor_body(config):
    global list_json_cap, list_json_emergency, terminate_program, audio_on, transmitted_caps
    global latest_frame, player, ui_status_text

    target_width, target_height = DISPLAY_WIDTH, DISPLAY_HEIGHT

    time_last_ticker_on = time.time()
    time_last_ticker_off = time.time()

    ticker_ref_path = config["ticker_reference"]
    ticker_ref = imread_unicode(ticker_ref_path)
    if ticker_ref is None:
        logger.error(f"[VID]> 티커 참조 이미지를 로드할 수 없습니다: {ticker_ref_path}")
        logger.error(f"[VID]> 파일이 존재하는지 확인하고, resources 폴더에 이미지 파일을 배치하세요.")
        terminate_program = True
        return
    logger.info(f"[VID]> 티커 참조 이미지 로드 완료: {ticker_ref_path}")
    push_ui_display_frame(blank_display_frame())
    pos_tick = config["position_tick"]  # 티커 감지 영역 설정
    ticker_width = 1
    ambiguity_ticker = 0
    previous_ticker_state = False  # 이전 재난 티커 상태
    ticker_state = False  # 현재 재난 티커 상태
    prev_len_list_json_cap = 0
    prev_len_list_json_emergency = 0
    emergency_tx_endtime = datetime.now()

    # 변수 초기화
    def monitor_state_init(config):
        subtitle_processed = False
        ticker_state_duration = 0  # 재난티커 상태가 변경된 이후 시간(초)
        time_ticker_state_change = time.time()  # 재난티커 상태가 변경된 이후 시점
        ticker_color = (50, 50, 50)  # 기본 검정색
        return (
            subtitle_processed,
            ticker_state_duration,
            time_ticker_state_change,
            ticker_color,
        )

    (
        subtitle_processed,
        ticker_state_duration,
        time_ticker_state_change,
        ticker_color,
    ) = monitor_state_init(config)

    source = None
    width, height = target_width, target_height

    while not terminate_program:
        with video_input_lock:
            settings = dict(video_input_settings)
        sync_config_video_path(config, settings)
        try:
            source = connect_video_with_retries(
                settings, target_width=target_width, target_height=target_height
            )
        except Exception as e:
            logger.error(f"[VID]> 연결 처리 예외 (프로그램 유지): {e}")
            source = None
        if source is None:
            ui_status_text = "연결 실패 — 소스를 확인 후 다시 [연결 적용]"
            logger.info("[VID]> 비디오 연결 실패 (프로그램 유지, 재시도 대기)")
            push_ui_display_frame(blank_display_frame())
            video_reconnect_event.clear()
            deadline = time.time() + 2.0
            while time.time() < deadline and not terminate_program:
                if video_reconnect_event.is_set():
                    break
                time.sleep(0.05)
            continue
        ui_status_text = source.description or "연결됨"
        width = int(source.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(source.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"입력 소스비디오 화면 크기 - 가로: {width}, 세로: {height}")
        logger.info("[VID]> 채널에 접속되었습니다.")
        pipeline_set_monitoring_active(source.description or "연결됨")
        if width != target_width or height != target_height:
            logger.info(
                f"입력 비디오: {width}x{height}, 출력 비디오: {target_width}x{target_height}"
            )
            logger.info("화면 크기를 변환되었습니다.")

        video_path = config["video_path"]
        player = None
        use_stream_audio = isinstance(video_path, str) and str(video_path).startswith(
            "rtmp"
        )
        if use_stream_audio and config.get("ffmpeg_enable") == 1:
            if _FFPLAYER_AVAILABLE and MediaPlayer is not None:
                try:
                    player = MediaPlayer(video_path)
                    player.set_pause(False)
                except Exception as e:
                    logger.warning(f"ffpyplayer failed to start audio player: {e}")
                    player = None
            else:
                logger.warning("ffpyplayer not available; audio disabled")

        while not terminate_program and not video_reconnect_event.is_set():
            ret, frame = source.read()
            if not ret:
                break

            latest_frame = frame.copy()
            if settings.get("kind") == "file":
                time.sleep(1 / 30)

            loop_state = {
                "subtitle_processed": subtitle_processed,
                "ticker_state_duration": ticker_state_duration,
                "time_ticker_state_change": time_ticker_state_change,
            }
            process_ui_commands(frame, config, loop_state, emergency_tx_endtime)
            if terminate_program:
                break
            subtitle_processed = loop_state["subtitle_processed"]
            ticker_state_duration = loop_state["ticker_state_duration"]
            time_ticker_state_change = loop_state["time_ticker_state_change"]

            # L1)  긴급 재난이 있는지 확인하고, 긴급재난이 있으면 현재 재난송출을 중단하고, 긴급재난에 대응한 체크 시작
            if list_json_emergency:
                logger.info(
                    f"[VID-{len(list_json_cap)}]> 긴급 재난 : {list_json_emergency[0]['EventCode']}"
                )
                (
                    subtitle_processed,
                    ticker_state_duration,
                    time_ticker_state_change,
                    ticker_color,
                ) = monitor_state_init(config)
                emergency_cap = list_json_emergency[0]
                subtitle_thread = threading.Thread(
                    target=emergency_check_AI, args=(frame, config, emergency_cap)
                )
                subtitle_thread.start()

                emergency_tx_endtime = datetime.now() + timedelta(
                    seconds=config["emergency_tx_duration"]
                )

                # 송출 완료 시 : 송출된 CAP을 기록함.
                current_time = datetime.now()
                transmitted_caps.append((list_json_emergency[0], current_time))
                list_json_emergency.pop(0)

            # L2) 일반 재난 처리
            # L2-1) 새로운 재난 메시지가 수신되면 3분간 비디오를 저장하는 쓰레드 호출
            if config["save_video"] == True and len(list_json_cap) > prev_len_list_json_cap:
                save_video(config, source)
                prev_len_list_json_cap = len(list_json_cap)

            # L2-2) 재난 티커 체크 :ticker_state(티커여부)와 ambiguity_ticker(불확실성 상태) 관리
            ticker_img = frame[
                pos_tick[0][1] : pos_tick[1][1], pos_tick[0][0] : pos_tick[1][0]
            ]
            similarity = compare_ticker_similarity(ticker_img, ticker_ref, debug=False)

            print(
                f"** Ticker[{ticker_state}-{ticker_state_duration :3.2f}]  similarity = {similarity:1.2f} ",
                end="\r",
            )
            # save_frame_as_png(ticker_img, "./temp",  "ticker_ref.png")

            # Check if similarity is 1 and save the frame
            if similarity == 1:
                timestamp = datetime.now().strftime("%H%M%S")
                file_name = f"similary_{timestamp}.png"
                save_frame_as_png(frame, "./temp", file_name)

            if similarity < config["ticker_False_threshold"]:
                ticker_state = False
            elif similarity > config["ticker_True_threshold"]:
                ticker_state = True
            else:
                ambiguity_ticker = ambiguity_ticker + 1
                if ambiguity_ticker % 30 == 0:
                    logger.info(
                        f"[VID-{len(list_json_cap)}]>누적 Ambiguity ticker count: {ambiguity_ticker}"
                    )

            # L2-3) 티커 상태 변화 체크, ticker_state_duration(티커상태 지속 시간) 변수 관리
            # if list_json_cap and ticker_state != previous_ticker_state :
            if ticker_state != previous_ticker_state:
                time_ticker_state_change = time.time()
                if ticker_state == True:
                    if list_json_cap:
                        pipeline_update(
                            "ticker_on",
                            "active",
                            f"티커 ON · {list_json_cap[0].get('EventCode', '')}",
                        )
                    logger.info(
                        f"[VID]-{len(list_json_cap)}> 재난 티커 {ticker_state} | 유사도 {similarity:1.2f}|  Ticker Off 지속 시간 {(time_ticker_state_change - time_last_ticker_off) :3.2f}초"
                    )
                    time_last_ticker_on = time.time()
                else:
                    # logger.info(f"[VID]> 재난 티커 {ticker_state} | 유사도 {similarity:1.2f} | Tick 지속 시간 {ticker_state_duration}초")
                    logger.info(
                        f"[VID]-{len(list_json_cap)}> 재난 티커 {ticker_state} | 유사도 {similarity:1.2f}|  Ticker On 지속 시간 {(time_ticker_state_change - time_last_ticker_on) :3.2f}초"
                    )
                    time_last_ticker_off = time.time()
                previous_ticker_state = ticker_state
            # elif  not list_json_cap :
            #    time_ticker_state_change = time.time()
            ticker_state_duration = time.time() - time_ticker_state_change

            # L2-4 일반 재난 경보 처리 :재난티커 확인후 10초되에 AI 내용 검증 이후 처리
            if list_json_cap:
                # 재난 자막 시작 직후 1초 이상 감지 => 자막 AI 확인 쓰레드 실행
                # AI 에서 현재 대기중인 재난에 해당하는 경우 : list_json_cap이 존재하지 않아 이 영역에 들어오지 않음.
                # AI 에서 현재 대기중인 재난에 해당하지 않는 경우 : 2차 송출에서 다시 시도함
                if (
                    ticker_state == True
                    and ticker_state_duration > config["delay_subtitle"]
                    and subtitle_processed == False
                ):
                    # logger.info(f"AI 쓰레드 호출 current_json_cap_len = {current_json_cap_len}")
                    subtitle_processed = True  # 쓰레드가 이미 실행되지 않았다면 실행
                    ticker_color = (125, 0, 125)  # 티커가 감지되면 빨간색
                    ticker_width = 2
                    # 자막 AI 확인 쓰레드 시작
                    subtitle_thread = threading.Thread(
                        target=subtitle_check_AI, args=(frame, config)
                    )
                    subtitle_thread.start()
                    logger.info(
                        f"[VID-{len(list_json_cap)}]> 재난 AI 호출 : {list_json_cap[0]['event'].encode('utf-8').decode()}"
                    )

                    # AI 자막 불일치를 체크하기 위한 이미지 저장
                    timestamp = datetime.now().strftime("%H%M%S")
                    file_name = f"ai_check_{timestamp}.png"
                    save_frame_as_png(frame, "./temp", file_name)
                    logger.info(
                        f"[VID-{len(list_json_cap)}]> 자막 화면 파일저장 경로 {file_name} "
                    )

                # 일정시간  이상 티커가 감지되지 않으면
                elif (
                    ticker_state == False
                    and ticker_state_duration > config["ticker_off_init_duration"]
                    and datetime.now() > emergency_tx_endtime
                ):
                    # if list_json_cap[0]['Broadcastflag'] :
                    speak_text = f"송출해야 할 재난자막 방송이 누락되었습니다."
                    logger.info(
                        f"[VID-{len(list_json_cap)}]> **WARNNING** {speak_text} **WARNNING**"
                    )
                    speak_queue.put(speak_text)  # Queue에 텍스트 데이터 추가
                    send_post_request(
                        config,
                        f"{list_json_cap[0]['EventCode']} **WARNNING** {speak_text} **WARNNING**",
                        0,
                    )

                    logger.info(
                        f"[VID-{len(list_json_cap)}]> 재난 티커가 { config['ticker_off_init_duration']}초 이상 없어 버퍼 초기화됨"
                    )
                    # 재난이 없다고 판단한 상황에서 화면도 캡쳐해 봅니다. (임시)
                    save_frame_with_info(frame, list_json_cap[0], config, False)
                    list_json_cap.clear()
                    (
                        subtitle_processed,
                        ticker_state_duration,
                        time_ticker_state_change,
                        ticker_color,
                    ) = monitor_state_init(config)
                    ticker_width = 2

                # 티커가 사라지면 (유사도가 낮아짐) 자막 감지 상태 초기화
                elif (
                    ticker_state == False
                    and ticker_state_duration > 1
                    and subtitle_processed == True
                ):
                    # logger.info(f"[VID]> 재난 티커 없음 =>")
                    subtitle_processed = False  # 쓰레드를 다시 시작할 수 있게 함
            else:
                time_ticker_state_change = time.time()

            ticker_width = len(list_json_cap) + 1
            if len(list_json_cap) == 0:
                ticker_color = (50, 50, 50)  # 세 개의 재난 메시지가 있으면 블랙
            elif len(list_json_cap) == 1:
                ticker_color = (0, 255, 0)  # 한 개의 재난 메시지가 있으면 초록색
            elif len(list_json_cap) == 2:
                ticker_color = (255, 0, 0)  # 두 개의 재난 메시지가 있으면 블루색
            else:
                ticker_color = (0, 0, 255)  # 세 개의 재난 메시지가 있으면 레드색

            # L3) 화면 표출부 처리
            # 티커 감지 영역 표시
            cv2.rectangle(
                frame,
                (pos_tick[0][0] - 2, pos_tick[0][1] - 2),
                (pos_tick[1][0] + 2, pos_tick[1][1] + 2),
                ticker_color,
                ticker_width,
            )

            push_ui_display_frame(np.ascontiguousarray(frame))
            time.sleep(1 / 30)

            if video_reconnect_event.is_set():
                break

        if source is not None:
            source.release()
            source = None
        player = None
        if video_reconnect_event.is_set() and not terminate_program:
            logger.info("[VID]> 비디오 입력 변경 — 재연결합니다.")
        video_reconnect_event.clear()


# 메인 프로그램
def main():
    global logger, video_input_settings, terminate_program

    config = read_config("./Default.yml", "./Override.yml")
    pytesseract.pytesseract.tesseract_cmd = config["pytesseract_path"]

    # 설정한 디렉토리와 파일명으로 로거 초기화
    log_path = config["log_path"]
    log_filename = config["log_filename"]
    max_log_size = config["max_log_size"] * 1024
    logger = setup_logger(log_path, log_filename, max_log_size, 2)

    video_input_settings = init_video_input_settings(config)
    apply_ui_prefs_to_video_settings()
    sync_config_video_path(config, video_input_settings)
    init_operator_pipeline()

    alive_daily_thread = threading.Thread(target=schedule_daily, args=(config,))
    alive_1min_thread = threading.Thread(target=schedule_1min, args=(config,))
    cap_thread = threading.Thread(target=cap_monitor, args=(config,))
    speak_thread = threading.Thread(target=speak_out, daemon=True)
    video_thread = threading.Thread(target=video_monitor, args=(config,), daemon=True)

    alive_daily_thread.start()
    alive_1min_thread.start()
    cap_thread.start()
    speak_thread.start()
    video_thread.start()
    time.sleep(0.3)

    try:
        run_watcher_single_window(config)
    finally:
        request_app_shutdown()
    video_thread.join(timeout=8)
    cap_thread.join(timeout=5)
    speak_thread.join(timeout=3)
    alive_daily_thread.join(timeout=5)
    alive_1min_thread.join(timeout=5)
    try:
        if ui_root is not None:
            ui_root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
