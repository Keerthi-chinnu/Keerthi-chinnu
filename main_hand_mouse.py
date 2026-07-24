import cv2
import time
import math
import numpy as np
import pyautogui
import mediapipe as mp
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from HandTrackingModule import HandDetector

# ====================== Camera Setup ======================
wCam, hCam = 640, 480
cap = cv2.VideoCapture(0)
cap.set(3, wCam)
cap.set(4, hCam)

# ====================== Hand Detector ======================
detector = HandDetector(maxHands=1, detectionCon=0.85, trackCon=0.8)

# ====================== Audio Setup ======================
import comtypes
from comtypes import CLSCTX_ALL, CLSCTX_INPROC_SERVER, CoCreateInstance
from ctypes import cast, POINTER
from pycaw.pycaw import IAudioEndpointVolume, IMMDeviceEnumerator

CLSID_MMDeviceEnumerator = comtypes.GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
device_enumerator = CoCreateInstance(
    CLSID_MMDeviceEnumerator,
    IMMDeviceEnumerator,
    CLSCTX_INPROC_SERVER
)
endpoint = device_enumerator.GetDefaultAudioEndpoint(0, 1)  # 0=eRender, 1=eMultimedia
interface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))

volRange = volume.GetVolumeRange()
minVol, maxVol = volRange[0], volRange[1]
vol = 0
volBar = 400
volPer = 0

# ====================== Misc Setup ======================
tipIds = [4, 8, 12, 16, 20]
mode = 'N'
active = 0

pyautogui.FAILSAFE = False
SMOOTHING_FACTOR = 0.25
prev_cursor_x, prev_cursor_y = 0, 0

def putText(text, loc=(250, 450), color=(0, 255, 255)):
    cv2.putText(img, str(text), loc, cv2.FONT_HERSHEY_COMPLEX_SMALL, 3, color, 3)

# ====================== Main Loop ======================
pTime = 0
while True:
    success, img = cap.read()
    if not success:
        print("Failed to capture frame from camera.")
        break

    # Detect hand landmarks
    img = detector.find_hands(img)
    lmList = detector.find_position(img, draw=False)
    fingers = []

    # If hand detected, calculate finger states
    if len(lmList) != 0:
        # Thumb
        thumbOpen = lmList[tipIds[0]][1] > lmList[tipIds[0] - 1][1]
        if thumbOpen:
            fingers.append(1 if lmList[tipIds[0]][1] >= lmList[tipIds[0] - 1][1] else 0)
        else:
            fingers.append(1 if lmList[tipIds[0]][1] <= lmList[tipIds[0] - 1][1] else 0)

        # Other 4 fingers
        for id in range(1, 5):
            fingers.append(1 if lmList[tipIds[id]][2] < lmList[tipIds[id] - 2][2] else 0)

        # Mode selection (only when inactive)
        if fingers == [0, 0, 0, 0, 0] and active == 0:
            mode = 'N'
        elif (fingers == [0, 1, 0, 0, 0] or fingers == [0, 1, 1, 0, 0]) and active == 0:
            mode = 'Scroll'
            active = 1
        elif fingers == [1, 1, 0, 0, 0] and active == 0:
            mode = 'Volume'
            active = 1
        elif fingers == [1, 1, 1, 1, 1] and active == 0:
            mode = 'Cursor'
            active = 1

    else:
        fingers = []
        mode = 'N'
        active = 0

    # ====================== Cursor Mode ======================
    if mode == 'Cursor' and len(fingers) > 0:
        putText('Cursor')

        if fingers[1:] == [0, 0, 0, 0]:
            active = 0
            mode = 'N'
        else:
            x1, y1 = lmList[8][1], lmList[8][2]
            screenWidth, screenHeight = pyautogui.size()

            # Mirrored X for natural movement
            X = int(np.interp(x1, [110, 620], [screenWidth - 1, 0]))
            Y = int(np.interp(y1, [20, 350], [0, screenHeight - 1]))

            X = int(SMOOTHING_FACTOR * X + (1 - SMOOTHING_FACTOR) * prev_cursor_x)
            Y = int(SMOOTHING_FACTOR * Y + (1 - SMOOTHING_FACTOR) * prev_cursor_y)

            prev_cursor_x, prev_cursor_y = X, Y
            pyautogui.moveTo(X, Y)

            # ==================== LEFT CLICK (Thumb + Index) ====================
            thumb_x, thumb_y = lmList[4][1], lmList[4][2]
            index_x, index_y = lmList[8][1], lmList[8][2]
            thumb_index_dist = math.hypot(thumb_x - index_x, thumb_y - index_y)
            if thumb_index_dist < 60:
                cv2.circle(img, (index_x, index_y), 10, (0, 255, 0), cv2.FILLED)
                pyautogui.click()

            # ==================== RIGHT CLICK (Thumb + Pinky) ====================
            pinky_x, pinky_y = lmList[20][1], lmList[20][2]
            thumb_pinky_dist = math.hypot(thumb_x - pinky_x, thumb_y - pinky_y)
            if thumb_pinky_dist < 70:
                cv2.circle(img, (pinky_x, pinky_y), 10, (255, 0, 0), cv2.FILLED)
                pyautogui.rightClick()

    # ====================== Volume Mode ======================
    if mode == 'Volume' and len(fingers) > 0:
        putText('Volume')

        if fingers[1:] == [0, 0, 0, 0]:
            active = 0
            mode = 'N'
        else:
            thumb_x, thumb_y = lmList[4][1], lmList[4][2]
            index_x, index_y = lmList[8][1], lmList[8][2]

            cx, cy = (thumb_x + index_x) // 2, (thumb_y + index_y) // 2

            # Pinky acts as a "lock" switch: closed pinky = freeze volume changes
            pinky_open = fingers[4] == 1

            if pinky_open:
                line_color = (255, 0, 255)   # normal color = actively adjusting
            else:
                line_color = (0, 0, 255)     # red = locked, not adjusting

            cv2.circle(img, (thumb_x, thumb_y), 10, line_color, cv2.FILLED)
            cv2.circle(img, (index_x, index_y), 10, line_color, cv2.FILLED)
            cv2.line(img, (thumb_x, thumb_y), (index_x, index_y), line_color, 3)
            cv2.circle(img, (cx, cy), 8, line_color, cv2.FILLED)

            length = math.hypot(index_x - thumb_x, index_y - thumb_y)

            if pinky_open:
                # Pinky raised -> allow volume to change
                vol = np.interp(length, [20, 200], [minVol, maxVol])
                volBar = np.interp(length, [20, 200], [400, 150])
                volPer = np.interp(length, [20, 200], [0, 100])
                volume.SetMasterVolumeLevel(vol, None)

                if length < 25:
                    cv2.circle(img, (cx, cy), 8, (0, 255, 0), cv2.FILLED)
            else:
                # Pinky closed -> locked, show status text, skip volume update
                putText('LOCKED', loc=(250, 100), color=(0, 0, 255))

    # ====================== Volume Bar Display ======================
    if mode == 'Volume':
        cv2.rectangle(img, (50, 150), (85, 400), (255, 0, 0), 3)
        cv2.rectangle(img, (50, int(volBar)), (85, 400), (255, 0, 0), cv2.FILLED)
        cv2.putText(img, f'{int(volPer)} %', (40, 450), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 0, 0), 3)

    # ====================== FPS Display ======================
    cTime = time.time()
    fps = 100 / ((cTime + 1) - pTime)
    pTime = cTime
    cv2.putText(img, f'FPS:{int(fps)}', (480, 50), cv2.FONT_ITALIC, 1, (255, 0, 0), 2)

    # ====================== Show Frame ======================
    cv2.imshow('Hand LiveFeed', img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ====================== Cleanup ======================
cap.release()
cv2.destroyAllWindows()
