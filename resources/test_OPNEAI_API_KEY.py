# 파일명: test_openai_api.py
# OpenAI API 호출 테스트 코드
# DisasterTV_AI.py에서 사용하는 OpenAI API 기능을 테스트합니다.

import os
import sys
import base64
import cv2
import numpy as np
from openai import OpenAI
from datetime import datetime
import getpass

# 색상 출력을 위한 ANSI 코드
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(message):
    print(f"{Colors.GREEN}[OK] {message}{Colors.RESET}")

def print_error(message):
    print(f"{Colors.RED}[ERROR] {message}{Colors.RESET}")

def print_info(message):
    print(f"{Colors.BLUE}[INFO] {message}{Colors.RESET}")

def print_warning(message):
    print(f"{Colors.YELLOW}[WARN] {message}{Colors.RESET}")

def print_header(message):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

# 테스트 1: OpenAI 클라이언트 초기화 및 API 키 확인
def test_api_key(api_key_param=None):
    """
    API 키를 확인하고 클라이언트를 초기화합니다.
    
    Args:
        api_key_param: 직접 전달된 API 키 (환경변수보다 우선)
    
    Returns:
        OpenAI 클라이언트 객체 또는 None
    """
    print_header("테스트 1: OpenAI API 키 확인")
    
    try:
        # 직접 전달된 API 키가 있으면 우선 사용
        api_key = api_key_param
        
        # 환경변수에서 API 키 확인 (직접 전달된 키가 없을 경우)
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print_warning("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
            print_info("시스템 환경변수에서 API 키를 확인합니다...")
            # Windows 환경변수 확인
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
                api_key = winreg.QueryValueEx(key, "OPENAI_API_KEY")[0]
                winreg.CloseKey(key)
                if api_key:
                    print_success("시스템 환경변수에서 API 키를 찾았습니다.")
            except:
                pass
        
        if not api_key:
            print_error("API 키를 찾을 수 없습니다.")
            print_info("다음 방법 중 하나를 사용하세요:")
            print_info("  1) 환경변수 OPENAI_API_KEY 설정")
            print_info("  2) 명령줄에서 --api-key 옵션 사용")
            print_info("  3) 인터랙티브 모드로 키 입력 (--interactive 옵션)")
            return None
        
        # API 키 형식 확인 (sk-로 시작하는지)
        if api_key.startswith("sk-"):
            print_success(f"API 키 형식 확인 완료 (길이: {len(api_key)}자)")
        else:
            print_warning("API 키 형식이 예상과 다릅니다 (sk-로 시작하지 않음)")
        
        # API 키 값 출력 (마스킹 처리)
        if len(api_key) > 20:
            masked_key = api_key[:10] + "*" * (len(api_key) - 20) + api_key[-10:]
            print_info(f"API 키 (마스킹): {masked_key}")
        else:
            print_info(f"API 키: {api_key}")
        
        # 전체 API 키 값 출력 (디버깅용)
        print_info(f"API 키 전체 값: {api_key}")
        
        # 클라이언트 초기화 (API 키를 직접 전달)
        client = OpenAI(api_key=api_key)
        print_success("OpenAI 클라이언트 초기화 완료")
        
        # 실제 API 호출을 통한 키 검증
        print_info("API 키 유효성 검증 중...")
        try:
            # 간단한 API 호출로 키 검증
            test_completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": "test"}
                ],
                max_tokens=5
            )
            print_success("API 키 유효성 검증 완료 - 정상 동작합니다")
            return client
        except Exception as api_error:
            error_str = str(api_error)
            if "401" in error_str or "invalid_api_key" in error_str.lower() or "authentication" in error_str.lower():
                print_error("API 키 인증 실패 - 잘못된 키이거나 만료된 키입니다")
                print_info("다음 사항을 확인해주세요:")
                print_info("  1. OpenAI 플랫폼(https://platform.openai.com/account/api-keys)에서 API 키 확인")
                print_info("  2. API 키가 만료되지 않았는지 확인")
                print_info("  3. 환경변수 OPENAI_API_KEY가 올바르게 설정되었는지 확인")
                return None
            else:
                print_warning(f"API 키 검증 중 예상치 못한 오류: {api_error}")
                print_info("네트워크 문제일 수 있습니다. 계속 진행합니다...")
                return client
        
    except Exception as e:
        print_error(f"API 키 확인 중 오류 발생: {e}")
        return None

# 테스트 2: 텍스트 비교 API 테스트 (subtitle_check_AI와 유사)
def test_text_comparison(client):
    print_header("테스트 2: 텍스트 비교 API 테스트")
    
    if not client:
        print_error("클라이언트가 초기화되지 않았습니다.")
        return False
    
    test_cases = [
        {
            "name": "일치하는 경우",
            "original": "서울특별시 강남구에서 지진이 발생했습니다. 안전한 곳으로 대피하세요.",
            "recognized": "서울특별시 강남구에서 지진이 발생했습니다"
        },
        {
            "name": "부분 일치하는 경우",
            "original": "경기도 수원시에서 산불이 발생했습니다. 신고하세요.",
            "recognized": "경기도 수원시에서 산불 발생"
        },
        {
            "name": "불일치하는 경우",
            "original": "서울특별시 강남구에서 지진이 발생했습니다.",
            "recognized": "오늘 날씨는 맑습니다."
        }
    ]
    
    success_count = 0
    for i, test_case in enumerate(test_cases, 1):
        print_info(f"\n[{i}/{len(test_cases)}] {test_case['name']}")
        print(f"  원본 텍스트: {test_case['original']}")
        print(f"  인식 텍스트: {test_case['recognized']}")
        
        try:
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "A, B 두문장을 비교하는데, B는 이미지에서 문자를 인식하는 과정에 일부 문자 인식 오류가 있을 수 있음을 감안하여, B가 A 문장 중에 일부로 판단되면 True, 그렇지 않으면 False로 답해줘",
                    },
                    {
                        "role": "user",
                        "content": f"A: {test_case['original']}\n B: {test_case['recognized']}",
                    },
                ],
            )
            
            gpt_response = completion.choices[0].message.content.strip()
            print(f"  API 응답: {gpt_response}")
            
            if gpt_response.lower() in ["true", "false"]:
                print_success(f"응답 형식 정상: {gpt_response}")
                success_count += 1
            else:
                print_warning(f"응답 형식이 예상과 다릅니다: {gpt_response}")
                
        except Exception as e:
            print_error(f"API 호출 실패: {e}")
    
    print(f"\n{Colors.BOLD}결과: {success_count}/{len(test_cases)} 테스트 통과{Colors.RESET}")
    return success_count == len(test_cases)

# 테스트 3: 이미지 분석 API 테스트 (emergency_check_AI와 유사)
def test_image_analysis(client):
    print_header("테스트 3: 이미지 분석 API 테스트")
    
    if not client:
        print_error("클라이언트가 초기화되지 않았습니다.")
        return False
    
    # 테스트용 이미지 생성
    test_image_path = "test_image_temp.png"
    
    try:
        # 간단한 테스트 이미지 생성 (텍스트가 포함된 이미지)
        img = np.ones((200, 600, 3), dtype=np.uint8) * 255  # 흰색 배경
        cv2.putText(img, "재난 경보", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
        cv2.putText(img, "지진 발생", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        cv2.imwrite(test_image_path, img)
        print_success(f"테스트 이미지 생성 완료: {test_image_path}")
        
        # 이미지를 Base64로 인코딩
        with open(test_image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
        
        test_cases = [
            {
                "name": "이미지에 포함된 텍스트",
                "search_text": "재난 경보",
                "expected": True
            },
            {
                "name": "이미지에 포함된 텍스트 (부분)",
                "search_text": "지진",
                "expected": True
            },
            {
                "name": "이미지에 없는 텍스트",
                "search_text": "태풍 경보",
                "expected": False
            }
        ]
        
        success_count = 0
        for i, test_case in enumerate(test_cases, 1):
            print_info(f"\n[{i}/{len(test_cases)}] {test_case['name']}")
            print(f"  검색 텍스트: {test_case['search_text']}")
            
            try:
                completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "너는 방송 화면 이미지에 텍스트를 인식하고 이해할 수 있는 전문가야. 질문 답변은 단답형으로 True 또는 False로만 답해줘.",
                        },
                        {
                            "role": "user",
                            "content": [
                                f"첨부 이미지 속에 다음의 재난 메시지 <{test_case['search_text']}>가 내용상 포함되었다고 판단되는가?",
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{encoded_image}"
                                    },
                                },
                            ],
                        },
                    ],
                )
                
                gpt_response = completion.choices[0].message.content.strip().lower()
                print(f"  API 응답: {gpt_response}")
                
                # 응답이 True/False인지 확인
                if gpt_response in ["true", "false"]:
                    print_success(f"응답 형식 정상: {gpt_response}")
                    success_count += 1
                else:
                    print_warning(f"응답 형식이 예상과 다릅니다: {gpt_response}")
                    
            except Exception as e:
                print_error(f"API 호출 실패: {e}")
                import traceback
                traceback.print_exc()
        
        # 임시 파일 삭제
        if os.path.exists(test_image_path):
            os.remove(test_image_path)
            print_info(f"임시 파일 삭제: {test_image_path}")
        
        print(f"\n{Colors.BOLD}결과: {success_count}/{len(test_cases)} 테스트 통과{Colors.RESET}")
        return success_count == len(test_cases)
        
    except Exception as e:
        print_error(f"이미지 분석 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

# 테스트 4: 실제 이미지 파일을 사용한 테스트
def test_with_real_image(client, image_path=None):
    print_header("테스트 4: 실제 이미지 파일 테스트")
    
    if not client:
        print_error("클라이언트가 초기화되지 않았습니다.")
        return False
    
    # 이미지 경로 확인
    if not image_path:
        # 기본 경로 확인
        possible_paths = [
            "resources/subtitle_temp_image.jpg",
            "subtitle_temp_image.jpg",
            "test_image.png"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                image_path = path
                break
    
    if not image_path or not os.path.exists(image_path):
        print_warning("테스트용 이미지 파일을 찾을 수 없습니다.")
        print_info("이미지 경로를 인자로 전달하거나, 다음 경로에 이미지를 배치하세요:")
        for path in ["resources/subtitle_temp_image.jpg", "subtitle_temp_image.jpg"]:
            print(f"  - {path}")
        return False
    
    print_info(f"이미지 파일 사용: {image_path}")
    
    try:
        # 이미지를 Base64로 인코딩
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
        
        print_success("이미지 인코딩 완료")
        
        # 이미지 분석 요청
        search_text = "재난 경보"
        print_info(f"검색 텍스트: {search_text}")
        
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "너는 방송 화면 이미지에 텍스트를 인식하고 이해할 수 있는 전문가야. 질문 답변은 단답형으로 True 또는 False로만 답해줘.",
                },
                {
                    "role": "user",
                    "content": [
                        f"첨부 이미지 속에 다음의 재난 메시지 <{search_text}>가 내용상 포함되었다고 판단되는가?",
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            },
                        },
                    ],
                },
            ],
        )
        
        gpt_response = completion.choices[0].message.content.strip()
        print_success(f"API 응답: {gpt_response}")
        
        return True
        
    except Exception as e:
        print_error(f"실제 이미지 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

# 테스트 5: API 응답 시간 측정
def test_api_response_time(client):
    print_header("테스트 5: API 응답 시간 측정")
    
    if not client:
        print_error("클라이언트가 초기화되지 않았습니다.")
        return False
    
    test_count = 3
    response_times = []
    
    print_info(f"{test_count}회 API 호출을 수행하여 응답 시간을 측정합니다...")
    
    for i in range(test_count):
        try:
            start_time = datetime.now()
            
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "너는 방송 화면 이미지에 텍스트를 인식하고 이해할 수 있는 전문가야. 질문 답변은 단답형으로 True 또는 False로만 답해줘.",
                    },
                    {
                        "role": "user",
                        "content": "테스트 메시지입니다.",
                    },
                ],
            )
            
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds()
            response_times.append(response_time)
            
            print_success(f"[{i+1}/{test_count}] 응답 시간: {response_time:.2f}초")
            
        except Exception as e:
            print_error(f"[{i+1}/{test_count}] API 호출 실패: {e}")
    
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        
        print(f"\n{Colors.BOLD}응답 시간 통계:{Colors.RESET}")
        print(f"  평균: {avg_time:.2f}초")
        print(f"  최소: {min_time:.2f}초")
        print(f"  최대: {max_time:.2f}초")
        
        return True
    
    return False

# API 키를 인터랙티브하게 입력받는 함수
def get_api_key_interactive():
    """사용자로부터 API 키를 안전하게 입력받습니다."""
    print("\n" + "="*60)
    print("API 키 직접 입력 모드")
    print("="*60)
    print_info("환경변수를 설정하지 않고 직접 API 키를 입력할 수 있습니다.")
    print_info("입력한 키는 이 세션에만 사용되며 저장되지 않습니다.")
    print()
    
    try:
        # getpass를 사용하여 입력 시 화면에 표시되지 않도록 함
        api_key = getpass.getpass("OpenAI API 키를 입력하세요 (입력값은 화면에 표시되지 않습니다): ")
        
        if not api_key or not api_key.strip():
            print_error("API 키가 입력되지 않았습니다.")
            return None
        
        api_key = api_key.strip()
        
        # 기본 형식 확인
        if not api_key.startswith("sk-"):
            print_warning("API 키 형식이 예상과 다릅니다 (sk-로 시작하지 않음)")
            response = input("계속하시겠습니까? (y/n): ").strip().lower()
            if response != 'y':
                return None
        
        print_success("API 키가 입력되었습니다.")
        return api_key
        
    except KeyboardInterrupt:
        print_error("\n입력이 취소되었습니다.")
        return None
    except Exception as e:
        print_error(f"입력 중 오류 발생: {e}")
        return None

# 메인 테스트 함수
def main():
    print_header("OpenAI API 테스트 시작")
    print_info(f"테스트 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 명령줄 인자 파싱
    api_key_param = None
    image_path_arg = None
    interactive_mode = False
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--api-key" or arg == "-k":
            if i + 1 < len(sys.argv):
                api_key_param = sys.argv[i + 1]
                i += 2
            else:
                print_error("--api-key 옵션 뒤에 API 키를 입력해주세요.")
                return 1
        elif arg == "--interactive" or arg == "-i":
            interactive_mode = True
            i += 1
        elif arg.startswith("-"):
            print_warning(f"알 수 없는 옵션: {arg}")
            i += 1
        else:
            # 이미지 경로로 간주
            image_path_arg = arg
            i += 1
    
    # 인터랙티브 모드 처리
    if interactive_mode and not api_key_param:
        api_key_param = get_api_key_interactive()
        if not api_key_param:
            return 1
    
    # 테스트 결과 저장
    results = {}
    
    # 테스트 1: API 키 확인
    client = test_api_key(api_key_param=api_key_param)
    results["api_key"] = client is not None
    
    if not client:
        print_error("\nAPI 키 확인 실패로 인해 테스트를 중단합니다.")
        return
    
    # 테스트 2: 텍스트 비교
    results["text_comparison"] = test_text_comparison(client)
    
    # 테스트 3: 이미지 분석
    results["image_analysis"] = test_image_analysis(client)
    
    # 테스트 4: 실제 이미지 파일 테스트 (선택적)
    if image_path_arg:
        results["real_image"] = test_with_real_image(client, image_path_arg)
    else:
        results["real_image"] = test_with_real_image(client)
    
    # 테스트 5: 응답 시간 측정
    results["response_time"] = test_api_response_time(client)
    
    # 최종 결과 출력
    print_header("테스트 결과 요약")
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    for test_name, result in results.items():
        status = "[OK] 통과" if result else "[FAIL] 실패"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status}{Colors.RESET} - {test_name}")
    
    print(f"\n{Colors.BOLD}총 {passed_tests}/{total_tests} 테스트 통과{Colors.RESET}")
    
    if passed_tests == total_tests:
        print_success("\n모든 테스트가 성공적으로 완료되었습니다!")
        return 0
    else:
        print_error(f"\n{total_tests - passed_tests}개의 테스트가 실패했습니다.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_error("\n\n테스트가 사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print_error(f"\n예상치 못한 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

