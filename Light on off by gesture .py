import cv2
import mediapipe as mp

mp_face = mp.solutions.face_detection
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

face_detection = mp_face.FaceDetection(min_detection_confidence=0.5)
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)

lights = [0, 0, 0, 0, 0]

def count_fingers(hand_landmarks):
    count = 0
    landmarks = hand_landmarks.landmark

    # Thumb (x comparison, left-to-right hand assumption)
    if landmarks[4].x < landmarks[3].x:
        count += 1

    # Fingers (index to pinky)
    for tip in [8, 12, 16, 20]:
        if landmarks[tip].y < landmarks[tip - 2].y:
            count += 1

    return count

def draw_lights(frame, lights):
    for i in range(5):
        color = (0, 255, 0) if lights[i] else (0, 0, 255)
        cv2.circle(frame, (50 + i * 100, 50), 30, color, -1)
        cv2.putText(frame, f"L{i+1}", (35 + i * 100, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

cap = cv2.VideoCapture(0)

while True:
    success, frame = cap.read()
    if not success:
        break

    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    face_result = face_detection.process(rgb_frame)
    face_detected = face_result.detections is not None

    if face_detected:
        for detection in face_result.detections:
            mp_drawing.draw_detection(frame, detection)

        hand_result = hands.process(rgb_frame)
        if hand_result.multi_hand_landmarks:
            for hand_landmarks in hand_result.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                finger_count = count_fingers(hand_landmarks)

                for i in range(5):
                    lights[i] = 1 if i < finger_count else 0
    else:
        lights = [0, 0, 0, 0, 0]

    draw_lights(frame, lights)
    cv2.imshow("Virtual Light Control", frame)

    if cv2.waitKey(1) & 0xFF == 27:  # ESC to exit
        break

cap.release()
cv2.destroyAllWindows()
