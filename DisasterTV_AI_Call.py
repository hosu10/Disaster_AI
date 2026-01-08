# 파일명 : DisasterTV_AI_Call.py
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
                    else:
                        list_json_cap.append(json_cap)
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
                # 자막이 일치하면 프레임을 저장
                save_frame_with_info(frame, cap_data, config, True)
                # logger.info(f"재난자막 방송 확인 / 남은 CAP 메시지 : {len(list_json_cap)}개 ")  # 디버깅용 출력
                # send_post_request(config, f"방금 {cap_data['EventCode']} {cap_data['headline']} 재난방송이 송출 확인되었습니다.", 0)
                gpt_result = True
                current_time = datetime.now()
                transmitted_caps.append((cap_data, current_time))
                list_json_cap.pop(i)
                return gpt_result
            else:
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
    # 1. 자막 이미지 캡쳐 (긴급재난 메시지 영역은 일반 자막과 다름)
    pos_subtitle = config["position_emergency_subtitle"]
    subtitle_img_capture = frame[
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
        save_frame_with_info(frame, emergency_cap, config, True)
        logger.info(f"[EMG]> 긴급재난 송출 확인")
        # 자막이 일치하면 프레임을 저장
        # logger.info(f"재난자막 방송 확인 / 남은 CAP 메시지 : {len(list_json_cap)}개 ")  # 디버깅용 출력
    elif gpt_response.lower() == "false":
        save_frame_with_info(frame, emergency_cap, config, False)
        logger.info(f"[EMG]> 긴급재난 송출 미확인")
        send_post_request(
            config,
            f"{emergency_cap['EventCode']} **WARNNING** 긴급재난 자막 미확인. 점검바람. **WARNNING**",
            0,
        )
    return None


import cv2
import numpy as np


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


# 비디오 모니터링 쓰레드에서 자막 AI 쓰레드를 호출하는 예시
def video_monitor(config):
    global list_json_cap, list_json_emergency, terminate_program, audio_on, transmitted_caps
    video_path = config["video_path"]
    # video_path = 0
    # RTMP 연결 시도
    vid = None
    tries = 0
    max_tries = 8
    time_last_ticker_on = time.time()
    time_last_ticker_off = time.time()

    while not (vid and vid.isOpened()) and tries < max_tries:
        logger.info(f"[VID]> 비디오소스 연결 재시도 중...")
        if config["video_path"] == 0:
            vid = cv2.VideoCapture(video_path, cv2.CAP_DSHOW)
        else:
            vid = cv2.VideoCapture(video_path)
        # vid = cv2.VideoCapture(video_path, cv2.CAP_MSMF)
        # vid = cv2.VideoCapture(video_path)
        tries += 1
        time.sleep(5)  # 3초마다 확인합니다.

    # 비디오 소스가 열리면 해상도 출력
    if vid.isOpened():
        width = vid.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = vid.get(cv2.CAP_PROP_FRAME_HEIGHT)
        logger.info(f"입력 소스비디오 화면 크기 - 가로: {width}, 세로: {height}")
    else:
        logger.info(f"[VID]> RTMP 연결에 실패했습니다. 프로그램을 종료합니다.")
        terminate_program = True
        return
    logger.info(f"[VID]> 채널에 접속되었습니다.")

    target_width, target_height = 960, 540

    #    logger.info(f"** {time.strftime('%m-%d %H:%M:%S')}> 긴급 재난경 발령 ")
    if config["video_path"] != 0 and config["ffmpeg_enable"] == 1:
        if _FFPLAYER_AVAILABLE and MediaPlayer is not None:
            try:
                player = MediaPlayer(video_path)
                player.set_pause(False)  # 오디오 재생
            except Exception as e:
                logger.warning(f"ffpyplayer failed to start audio player: {e}")
                player = None
        else:
            logger.warning("ffpyplayer not available; audio disabled")
            player = None

    # 티커 참조 이미지 로드 (resources 폴더에서)
    ticker_ref_path = config["ticker_reference"]
    ticker_ref = cv2.imread(ticker_ref_path)
    if ticker_ref is None:
        logger.error(f"[VID]> 티커 참조 이미지를 로드할 수 없습니다: {ticker_ref_path}")
        logger.error(f"[VID]> 파일이 존재하는지 확인하고, resources 폴더에 이미지 파일을 배치하세요.")
        terminate_program = True
        return
    logger.info(f"[VID]> 티커 참조 이미지 로드 완료: {ticker_ref_path}")
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
    if width != target_width or height != target_height:
        logger.info(
            f"입력 비디오: {width}x{height}, 출력 비디오: {target_width}x{target_height}"
        )
        logger.info("화면 크기를 변환되었습니다.")

    # 프로그램 전체 메인 반복문
    while not terminate_program:
        ret, frame = vid.read()
        if not ret:
            break

        # 화면 크기 변환
        if width != target_width or height != target_height:
            target_frame = cv2.resize(frame, (target_width, target_height))
            frame = target_frame
        # val = player.get_frame()

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
            save_video(config, vid)
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

        # 영상 모니터링 화면에 표시
        cv2.imshow("KBS TV-Alert Watcher: V-250401", frame)

        # 'q' 키로 프로그램 종료
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            terminate_program = True
            break
        elif key == ord("b"):
            prog_state_logger(datetime.now(), emergency_tx_endtime)
            report_caps(config)
        elif key == ord("m"):
            # 테스트 모드: CAP 수신 + 티커 확인된 것처럼 가정하여 AI 호출
            logger.info(f"[TEST-MODE]> 테스트 모드 시작 - 'm' 키 입력 감지")
            
            # list_json_cap이 비어있으면 테스트용 CAP 데이터 추가
            if not list_json_cap:
                # 테스트용 CAP 데이터 생성 (기본값)
                test_cap_data = {
                    "identifier": "TEST-TEST-20260106-TEST_1",
                    "sent": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                    "source": "테스트",
                    "event": "테스트재난",
                    "EventCode": "TEST",
                    "headline": "테스트 재난 경보",
                    "BroadcastText.ko-KR": "테스트 재난 메시지입니다. 방송 화면에 자막이 표시되는지 확인합니다.",
                    "Broadcastflag": "Y",
                    "Magnitude": None,
                    "Priority": "3",
                    "emergency": False,
                    "is_mandatory": True
                }
                list_json_cap.append(test_cap_data)
                logger.info(f"[TEST-MODE]> 테스트용 CAP 데이터 추가: {test_cap_data['event']}")
            
            # 티커 상태를 True로 가정하고, ticker_state_duration을 delay_subtitle보다 크게 설정
            # subtitle_processed를 False로 설정하여 AI 호출 가능하게 함
            subtitle_processed = False
            ticker_state_duration = config["delay_subtitle"] + 1  # delay_subtitle보다 크게 설정
            time_ticker_state_change = time.time() - ticker_state_duration  # 과거 시점으로 설정
            
            logger.info(f"[TEST-MODE]> 티커 상태 시뮬레이션: ticker_state=True, duration={ticker_state_duration:.2f}초")
            logger.info(f"[TEST-MODE]> 현재 프레임으로 AI 호출 시작")
            
            # 자막 AI 확인 쓰레드 시작
            subtitle_thread = threading.Thread(
                target=subtitle_check_AI, args=(frame, config)
            )
            subtitle_thread.start()
            logger.info(
                f"[TEST-MODE]> 재난 AI 호출 (테스트 모드) : {list_json_cap[0]['event'].encode('utf-8').decode()}"
            )
            
            # AI 자막 확인을 위한 이미지 저장
            timestamp = datetime.now().strftime("%H%M%S")
            file_name = f"test_ai_check_{timestamp}.png"
            save_frame_as_png(frame, "./temp", file_name)
            logger.info(f"[TEST-MODE]> 테스트 화면 파일저장 경로: {file_name}")
            
        elif (
            key == ord("a")
            and config["video_path"] != 0
            and config["ffmpeg_enable"] == 1
        ):
            # 오디오 on/off 토글
            audio_on = not audio_on
            if audio_on:
                if player is not None:
                    try:
                        player.set_pause(False)  # 오디오 재생
                    except Exception:
                        logger.warning("Failed to unpause player; player unavailable")
                else:
                    logger.info("Audio requested but player is not available")
            else:
                if player is not None:
                    try:
                        player.set_pause(True)  # 오디오 일시 정지 (mute 효과)
                    except Exception:
                        logger.warning("Failed to pause player; player unavailable")
                else:
                    logger.info("Audio mute requested but player is not available")
            logger.info(f"[VID-{len(list_json_cap)}]> Audio Out {audio_on}")

    vid.release()
    cv2.destroyAllWindows()
    logger.info(f"[TV 화면 감시]> 쓰레드를 종료합니다.")


# 메인 프로그램
def main():
    global logger

    config = read_config("./Default.yml", "./Override.yml")
    pytesseract.pytesseract.tesseract_cmd = config["pytesseract_path"]

    # 설정한 디렉토리와 파일명으로 로거 초기화
    log_path = config["log_path"]
    log_filename = config["log_filename"]
    max_log_size = config["max_log_size"] * 1024
    logger = setup_logger(log_path, log_filename, max_log_size, 2)

    # 예시로 로그 기록하기

    # schedule_tasks()
    alive_daily_thread = threading.Thread(target=schedule_daily, args=(config,))
    alive_1min_thread = threading.Thread(target=schedule_1min, args=(config,))
    cap_thread = threading.Thread(target=cap_monitor, args=(config,))
    speak_thread = threading.Thread(target=speak_out, daemon=True)
    video_thread = threading.Thread(target=video_monitor, args=(config,))

    alive_daily_thread.start()
    alive_1min_thread.start()
    cap_thread.start()
    speak_thread.start()
    video_thread.start()

    alive_daily_thread.join()
    alive_1min_thread.join()
    cap_thread.join()
    speak_thread.join()
    video_thread.join()


if __name__ == "__main__":
    main()
