import cv2

def check_video_devices():
    print("\n🔍 사용 가능한 비디오 장치 검색 중 (DSHOW 백엔드)...")
    available_devices = []
    
    # 0~9번 인덱스 검색
    for i in range(10):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            available_devices.append({
                'index': i,
                'width': width,
                'height': height,
                'fps': fps
            })
            print(f"✅ [인덱스 {i}] 발견: {width}x{height} @ {fps} FPS")
            cap.release()
            
    if not available_devices:
        print("❌ 사용 가능한 비디오 장치를 찾을 수 없습니다.")
        return

    # 사용자 입력 받기
    print("\n" + "="*30)
    try:
        choice = input("👉 연결할 카메라 인덱스 번호를 입력하세요 (취소: Enter): ")
        if not choice:
            return
        
        device_idx = int(choice)
        
        # 선택한 장치 열기
        cap = cv2.VideoCapture(device_idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"❌ 인덱스 {device_idx} 장치를 열 수 없습니다.")
            return

        print(f"\n📺 인덱스 {device_idx} 연결 성공! 영상을 재생합니다.")
        print("💡 종료하려면 영상 창에서 'q' 키를 누르세요.")

        while True:
            ret, frame = cap.read()
            if not ret:
                print("❌ 프레임을 읽을 수 없습니다.")
                break

            # 화면에 인덱스 정보 표시
            cv2.putText(frame, f"Device Index: {device_idx}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            cv2.imshow(f"Camera Test - Index {device_idx}", frame)

            # 'q' 키를 누르면 종료
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        print("\n👋 모니터링을 종료합니다.")

    except ValueError:
        print("❌ 유효한 숫자를 입력해주세요.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    check_video_devices()
