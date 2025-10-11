"""
eye_cursor.py
Eye-tracking -> cursor control (simple, webcam-based)
Uses MediaPipe Face Mesh to find eye region, finds pupil center by image processing,
calibrates with 4 screen points, maps pupil position to screen coords, moves cursor with smoothing.

Notes:
- Give camera a few seconds to auto-expose at start.
- Calibrate in a well-lit environment (no strong glare on glasses).
"""

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
import time
from collections import deque

# ---------- Config / tuning params ----------
CAMERA_ID = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# smoothing
SMOOTHING_ALPHA = 0.10   # 0 = no smoothing, 1 = very slow smoothing

# pupil detection parameters
THRESH_BLOCKSIZE = 11
THRESH_C = 5
MIN_PUPIL_AREA = 20

# calibration points (relative screen coords)
# order: top-left, top-right, bottom-right, bottom-left
screen_w, screen_h = pyautogui.size()
CALIB_DST = np.array([
    [0 + 50, 0 + 50],
    [screen_w - 50, 0 + 50],
    [screen_w - 50, screen_h - 50],
    [0 + 50, screen_h - 50],
], dtype=np.float32)

CALIB_PROMPTS = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"]
CALIB_SECONDS = 1.0  # seconds to look at each point while recording

# ---------- MediaPipe setup ----------
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False,
                                  max_num_faces=1,
                                  refine_landmarks=True,  # gives iris landmarks if available
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

# landmark indices (MediaPipe FaceMesh)
# we will use four landmarks per eye to create a tight bounding box
LEFT_EYE_LANDMARKS = {
    "left_corner": 33,   # outer
    "right_corner": 133, # inner
    "top": 159,
    "bottom": 145
}
RIGHT_EYE_LANDMARKS = {
    "left_corner": 362,  # inner for right eye
    "right_corner": 263, # outer for right eye
    "top": 386,
    "bottom": 374
}


def landmarks_to_point(landmark, frame_w, frame_h):
    return np.array([int(landmark.x * frame_w), int(landmark.y * frame_h)], dtype=np.int32)


def extract_eye_roi(img_gray, lm_coords):
    """Return cropped eye ROI and top-left corner coordinates (x,y) on full frame."""
    xs = [p[0] for p in lm_coords]
    ys = [p[1] for p in lm_coords]
    x_min, x_max = max(min(xs) - 6, 0), min(max(xs) + 6, img_gray.shape[1] - 1)
    y_min, y_max = max(min(ys) - 6, 0), min(max(ys) + 6, img_gray.shape[0] - 1)
    roi = img_gray[y_min:y_max, x_min:x_max]
    return roi, (x_min, y_min)


def find_pupil_center(eye_roi):
    """Simple pupil finding: adaptive threshold, choose largest dark contour, return center in roi coords."""
    if eye_roi.size == 0:
        return None

    # Equalize + blur to help
    roi = cv2.equalizeHist(eye_roi)
    roi = cv2.GaussianBlur(roi, (5, 5), 0)

    # adaptive threshold to separate dark pupil
    th = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, THRESH_BLOCKSIZE, THRESH_C)

    # morphological opening to remove small noise
    kernel = np.ones((3, 3), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # choose contour with largest area
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_PUPIL_AREA:
            continue
        M = cv2.moments(cnt)
        if M.get("m00", 0) == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        return (cx, cy), th  # return also thresholded image for debug
    return None


def calibrate(camera):
    """Ask user to look at CALIB_PROMPTS points on the screen; return perspective transform mapping."""
    print("Calibration will start in 2 seconds. Please make sure you are seated and looking at the screen.")
    time.sleep(2.0)
    src_pts = []

    for i, prompt in enumerate(CALIB_PROMPTS):
        print(f"Look at {prompt} corner and hold still... ({CALIB_SECONDS}s)")
        # show simple on-screen visual cue (draw a black window at location) - use pyautogui to display a dot
        x, y = CALIB_DST[i].astype(int)
        # move a small black dot window by drawing a small OpenCV window with white background and a circle? Simpler: just pause and let user look.
        t0 = time.time()
        samples = []
        while time.time() - t0 < CALIB_SECONDS:
            ret, frame = camera.read()
            if not ret:
                continue
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(frame_rgb)
            if not results.multi_face_landmarks:
                cv2.putText(frame, "Face not found", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.imshow("Calibration", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
                continue

            mesh = results.multi_face_landmarks[0]
            # pick left eye by default (works for one face)
            # use landmarks to get eye ROI
            lm_coords = []
            for key in LEFT_EYE_LANDMARKS.values():
                lm_coords.append(landmarks_to_point(mesh.landmark[key], FRAME_WIDTH, FRAME_HEIGHT))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi, (ox, oy) = extract_eye_roi(gray, lm_coords)
            pupil = find_pupil_center(roi)
            if pupil:
                (cx, cy), _ = pupil
                # convert to full-frame coords
                full_x, full_y = cx + ox, cy + oy
                samples.append([full_x, full_y])
            cv2.imshow("Calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break
        # average samples for this point
        if len(samples) == 0:
            print("Warning: no pupil data captured for this calibration point. Try again.")
            avg = np.array([FRAME_WIDTH // 2, FRAME_HEIGHT // 2], dtype=np.float32)
        else:
            avg = np.mean(samples, axis=0)
        print(f"Captured calibration source point: {avg}")
        src_pts.append(avg)

    cv2.destroyWindow("Calibration")
    src = np.array(src_pts, dtype=np.float32)
    # compute perspective transform from src (pupil-space in camera frame) to dst (screen coords)
    if src.shape[0] == 4:
        M = cv2.getPerspectiveTransform(src, CALIB_DST)
        print("Calibration transform computed.")
        return M
    else:
        print("Calibration failed (not enough points).")
        return None


def map_pupil_to_screen(pupil_pt, M):
    """Apply perspective transform M to pupil point to get screen coordinates."""
    src_pt = np.array([[pupil_pt]], dtype=np.float32)  # shape (1,1,2)
    dst_pt = cv2.perspectiveTransform(src_pt, M)
    x, y = dst_pt[0][0]
    # clip to screen
    x = min(max(0, x), screen_w - 1)
    y = min(max(0, y), screen_h - 1)
    return int(x), int(y)


def main():
    cap = cv2.VideoCapture(CAMERA_ID)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    if not cap.isOpened():
        print("Cannot open camera. Exiting.")
        return

    # Calibration
    M = calibrate(cap)
    if M is None:
        print("Calibration failed. Exiting.")
        cap.release()
        return

    last_mouse = np.array(pyautogui.position(), dtype=np.float32)
    smoothed = last_mouse.copy()

    print("Starting main loop. Press ESC to quit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(frame_rgb)

        display = frame.copy()
        pupil_center_full = None

        if results.multi_face_landmarks:
            mesh = results.multi_face_landmarks[0]

            # choose which eye to use (left eye in this example)
            lm_coords = []
            for key in LEFT_EYE_LANDMARKS.values():
                lm_coords.append(landmarks_to_point(mesh.landmark[key], FRAME_WIDTH, FRAME_HEIGHT))

            # draw box for debug
            xs = [p[0] for p in lm_coords]; ys = [p[1] for p in lm_coords]
            x_min, x_max = max(min(xs) - 6, 0), min(max(xs) + 6, FRAME_WIDTH - 1)
            y_min, y_max = max(min(ys) - 6, 0), min(max(ys) + 6, FRAME_HEIGHT - 1)
            cv2.rectangle(display, (x_min, y_min), (x_max, y_max), (0, 255, 0), 1)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            roi, (ox, oy) = extract_eye_roi(gray, lm_coords)
            pupil = find_pupil_center(roi)
            if pupil:
                (cx, cy), debug_th = pupil
                pupil_center_full = (cx + ox, cy + oy)
                # draw pupil on display
                cv2.circle(display, (pupil_center_full[0], pupil_center_full[1]), 3, (0, 0, 255), -1)

                # map to screen and move cursor
                screen_x, screen_y = map_pupil_to_screen(pupil_center_full, M)
                target = np.array([screen_x, screen_y], dtype=np.float32)

                # smoothing
                smoothed[:] = (1.0 - SMOOTHING_ALPHA) * smoothed + SMOOTHING_ALPHA * target

                # move mouse (pyautogui uses ints)
                pyautogui.moveTo(int(smoothed[0]), int(smoothed[1]), _pause=False)

                # For debug text
                cv2.putText(display, f"Screen: {int(smoothed[0])},{int(smoothed[1])}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        cv2.imshow("Eye Cursor (press ESC to quit)", display)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
