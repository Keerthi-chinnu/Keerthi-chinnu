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

            # ✅ MIRRORED X for natural movement
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

class HandDetector:
    def __init__(self, mode=False, maxHands=1, detectionCon=1, trackCon=1):
        self.mode = mode
        self.maxHands = maxHands
        self.detectionCon = detectionCon
        self.trackCon = trackCon

        self.mpHands = mp.solutions.hands
        self.hands = self.mpHands.Hands(static_image_mode=self.mode,
                                        max_num_hands=self.maxHands,
                                        min_detection_confidence=self.detectionCon,
                                        min_tracking_confidence=self.trackCon)
        self.mpDraw = mp.solutions.drawing_utils

    def find_hands(self, img, draw=True):
        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(imgRGB)

        if self.results.multi_hand_landmarks:
            for handLms in self.results.multi_hand_landmarks:
                if draw:
                    self.mpDraw.draw_landmarks(img, handLms, self.mpHands.HAND_CONNECTIONS)
        return img

    def find_position(self, img, handNo=0, draw=True):
        lmList = []
        if self.results.multi_hand_landmarks:
            myHand = self.results.multi_hand_landmarks[handNo]
            h, w, c = img.shape
            for id, lm in enumerate(myHand.landmark):
                cx, cy = int(lm.x * w), int(lm.y * h)
                lmList.append([id, cx, cy])
                if draw:
                    cv2.circle(img, (cx, cy), 5, (255, 0, 255), cv2.FILLED)

        return lmList