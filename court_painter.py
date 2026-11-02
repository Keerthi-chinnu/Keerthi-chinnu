#!/usr/bin/env python3
"""
Autonomous Precision Court & Floor Border Painter Robot
======================================================
Hardware:
  - Raspberry Pi 3 Model B (Pi 3-B)
  - Pi Camera Module (CSI) with real-time OpenCV line / chalk tracking
  - 2x TB6612FNG Dual H-Bridge Motor Drivers (controlling 4 DC gearmotors)
  - 4 Omnidirectional / Mecanum Wheels (3-DOF Holonomic: Vx, Vy, Omega)
  - MPU-6050 6-Axis IMU (I2C: SDA=GPIO2, SCL=GPIO3) for precision heading lock
  - 1-Channel 5V Relay controlling 12V Diaphragm Paint Pump
  - MP1495 Step-Down Buck Converter (Battery -> 5.0V stable for Pi logic)
  - LM2576 Step-Down Buck Converter (Battery -> Regulated Motor Power VM)

Precision Painting Features:
  • Omnidirectional Holonomic Drive: Decoupled translation & rotation!
  • Gyro-locked heading PID loop: Keeps robot strictly facing court direction.
  • Vision lateral strafe PID loop: Pi Camera detects line deviation and gently
    strafes sideways (Vy) WITHOUT yawing or twisting the robot, maintaining
    crystal-sharp, uniform line width (50mm / 2 inches).
  • Preset court geometry automation (Tennis Singles/Doubles, Pickleball, Badminton, Basketball, Custom).
  • Precision 90-degree corner pivots with closed-loop gyro feedback.
  • Modern Web Dashboard (port 8080) with live camera reticle, telemetry,
    8-way omnidirectional jog, pump purge/test, and instant E-STOP.
"""

import os
import sys
import time
import math
import io
import json
import threading
from datetime import datetime
from flask import Flask, Response, request, jsonify, render_template_string

# ── Third-party Libraries (with graceful hardware fallbacks) ─────────────────
try:
    import smbus2
    HAS_SMBUS = True
except ImportError:
    try:
        import smbus as smbus2
        HAS_SMBUS = True
    except ImportError:
        HAS_SMBUS = False
        print("[WARN] smbus2/smbus not found. IMU running in simulation mode.")

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    print("[WARN] OpenCV / NumPy not found. Vision processing disabled.")

# Try PiCamera2 first (Bullseye/Bookworm), then fallback to standard cv2.VideoCapture
HAS_PICAM2 = False
try:
    from picamera2 import Picamera2
    HAS_PICAM2 = True
except ImportError:
    pass

# GPIO library selection (RPi.GPIO)
try:
    import RPi.GPIO as GPIO
    HAS_RPI_GPIO = True
except ImportError:
    HAS_RPI_GPIO = False
    print("[WARN] RPi.GPIO not found. Running in hardware simulation mode.")


# ==============================================================================
# PIN ASSIGNMENTS & HARDWARE CONFIGURATION
# ==============================================================================
CONFIG = {
    # ── MPU-6050 IMU (I2C Bus 1) ──
    "IMU_I2C_BUS": 1,
    "IMU_ADDR": 0x68,
    "IMU_SAMPLE_HZ": 100,

    # ── 12V Diaphragm Pump Relay ──
    "PIN_RELAY_PUMP": 26,     # GPIO26 (Pin 37)
    "RELAY_ACTIVE_LOW": True, # Most 5V relay modules trigger LOW (0V)

    # ── Motor Driver 1 (TB6612FNG #1 — Front-Left & Rear-Left) ──
    "DRIVER1_STBY": 4,        # GPIO4  (Pin 7)
    "DRIVER1_PWMA": 12,       # GPIO12 (Pin 32, Hardware PWM0) - FL Motor
    "DRIVER1_AIN1": 5,        # GPIO5  (Pin 29)
    "DRIVER1_AIN2": 6,        # GPIO6  (Pin 31)
    "DRIVER1_PWMB": 13,       # GPIO13 (Pin 33, Hardware PWM1) - RL Motor
    "DRIVER1_BIN1": 19,       # GPIO19 (Pin 35)
    "DRIVER1_BIN2": 20,       # GPIO20 (Pin 38)

    # ── Motor Driver 2 (TB6612FNG #2 — Front-Right & Rear-Right) ──
    "DRIVER2_STBY": 16,       # GPIO16 (Pin 36)
    "DRIVER2_PWMA": 18,       # GPIO18 (Pin 12, Hardware PWM0) - FR Motor
    "DRIVER2_AIN1": 22,       # GPIO22 (Pin 15)
    "DRIVER2_AIN2": 23,       # GPIO23 (Pin 16)
    "DRIVER2_PWMB": 17,       # GPIO17 (Pin 11)                - RR Motor
    "DRIVER2_BIN1": 27,       # GPIO27 (Pin 13)
    "DRIVER2_BIN2": 24,       # GPIO24 (Pin 18)

    # ── Motor Direction Polarity Inversion (Set True to invert any motor) ──
    "INVERT_FL": False,
    "INVERT_FR": False,
    "INVERT_RL": False,
    "INVERT_RR": False,

    # ── Motion & Control Defaults ──
    "PWM_FREQUENCY": 1000,    # 1 kHz motor PWM
    "BASE_PAINT_SPEED": 40.0, # Baseline forward speed (0-100%) during painting
    "CRUISE_SPEED": 50.0,     # Speed during non-painting navigation
    "PIVOT_SPEED": 35.0,      # Speed during 90-degree corner rotations
    "STRAFE_SPEED": 45.0,     # Speed during manual lateral strafe

    # ── IMU Heading PID Controller (Rotational Yaw Omega) ──
    "PID_HEADING": {
        "kp": 2.5,
        "ki": 0.05,
        "kd": 0.35,
        "max_correction": 35.0  # Max % omega rotational adjustment
    },

    # ── Vision Line Tracking PID (Lateral Strafe Vy) ──
    "PID_VISION": {
        "kp": 28.0,
        "ki": 0.50,
        "kd": 4.50,
        "max_strafe": 30.0      # Max % lateral strafe speed
    },

    # ── Linear Velocity Calibration (Meters per second at BASE_PAINT_SPEED) ──
    "METERS_PER_SECOND": 0.22,
    "WEB_PORT": 8080
}


# ==============================================================================
# 1. MPU-6050 6-DOF SENSOR DRIVER & GYRO HEADING INTEGRATOR
# ==============================================================================
class MPU6050:
    """
    MPU-6050 Accelerometer + Gyroscope Driver with background thread
    integrating Z-axis yaw with drift compensation and digital filtering.
    """
    PWR_MGMT_1   = 0x6B
    SMPLRT_DIV   = 0x19
    CONFIG_REG   = 0x1A
    GYRO_CONFIG  = 0x1B
    ACCEL_CONFIG = 0x1C
    ACCEL_XOUT_H = 0x3B
    GYRO_ZOUT_H  = 0x47

    def __init__(self, bus_num=1, address=0x68):
        self.bus_num = bus_num
        self.address = address
        self.bus = None
        self.yaw = 0.0            # Integrated heading in degrees
        self.yaw_rate = 0.0       # deg/s
        self.gyro_z_offset = 0.0  # Drift calibration offset
        self.is_calibrated = False
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        if HAS_SMBUS:
            try:
                self.bus = smbus2.SMBus(self.bus_num)
                self._init_sensor()
                print(f"[IMU] MPU-6050 connected on I2C bus {bus_num} at 0x{address:02X}")
            except Exception as e:
                print(f"[IMU] Error initializing MPU-6050: {e}")
                self.bus = None

    def _init_sensor(self):
        # Wake up MPU-6050 (clear sleep bit)
        self.bus.write_byte_data(self.address, self.PWR_MGMT_1, 0x00)
        time.sleep(0.05)
        # Set DLPF (Digital Low Pass Filter) to ~42Hz bandwidth for smooth gyro
        self.bus.write_byte_data(self.address, self.CONFIG_REG, 0x03)
        # Sample rate divider: 1kHz / (1 + 9) = 100Hz
        self.bus.write_byte_data(self.address, self.SMPLRT_DIV, 0x09)
        # Gyro full scale range: +/- 250 deg/s (131 LSB / deg/s)
        self.bus.write_byte_data(self.address, self.GYRO_CONFIG, 0x00)
        # Accel full scale range: +/- 2g (16384 LSB / g)
        self.bus.write_byte_data(self.address, self.ACCEL_CONFIG, 0x00)

    def _read_word_2c(self, reg):
        if not self.bus:
            return 0
        try:
            high = self.bus.read_byte_data(self.address, reg)
            low = self.bus.read_byte_data(self.address, reg + 1)
            val = (high << 8) + low
            if val >= 0x8000:
                return -((65535 - val) + 1)
            return val
        except Exception:
            return 0

    def calibrate(self, num_samples=300):
        """Calibrates gyro zero-rate offset while the robot is stationary."""
        print("[IMU] Calibrating MPU-6050 Gyroscope... KEEP ROBOT COMPLETELY STILL.")
        if not self.bus:
            self.gyro_z_offset = 0.0
            self.is_calibrated = True
            return

        total_gz = 0.0
        for _ in range(num_samples):
            raw_gz = self._read_word_2c(self.GYRO_ZOUT_H)
            total_gz += (raw_gz / 131.0)
            time.sleep(0.005)

        self.gyro_z_offset = total_gz / num_samples
        self.is_calibrated = True
        self.reset_yaw(0.0)
        print(f"[IMU] Calibration complete! Gyro Z-offset: {self.gyro_z_offset:.4f} °/s")

    def reset_yaw(self, angle=0.0):
        with self.lock:
            self.yaw = angle

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._integration_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _integration_loop(self):
        dt = 1.0 / CONFIG["IMU_SAMPLE_HZ"]
        last_time = time.time()
        while self.running:
            now = time.time()
            elapsed = now - last_time
            last_time = now

            if self.bus:
                raw_gz = self._read_word_2c(self.GYRO_ZOUT_H)
                gz_dps = (raw_gz / 131.0) - self.gyro_z_offset
                # Deadband filter to prevent micro-vibration drift accumulation
                if abs(gz_dps) < 0.15:
                    gz_dps = 0.0
                self.yaw_rate = gz_dps
                with self.lock:
                    self.yaw += gz_dps * elapsed
            time.sleep(dt)

    def get_heading(self):
        with self.lock:
            return self.yaw


# ==============================================================================
# 2. ACTUATION: DUAL TB6612FNG MOTOR DRIVERS & 12V PUMP RELAY
# ==============================================================================
class TB6612Motor:
    """Controls a single DC motor channel on the TB6612FNG."""
    def __init__(self, pwm_pin, in1_pin, in2_pin):
        self.pwm_pin = pwm_pin
        self.in1_pin = in1_pin
        self.in2_pin = in2_pin
        self.pwm_obj = None

        if HAS_RPI_GPIO:
            GPIO.setup(self.pwm_pin, GPIO.OUT)
            GPIO.setup(self.in1_pin, GPIO.OUT)
            GPIO.setup(self.in2_pin, GPIO.OUT)
            self.pwm_obj = GPIO.PWM(self.pwm_pin, CONFIG["PWM_FREQUENCY"])
            self.pwm_obj.start(0)

    def drive(self, speed):
        """Speed from -100 (full reverse) to +100 (full forward)."""
        speed = max(-100.0, min(100.0, speed))
        duty = abs(speed)

        if not HAS_RPI_GPIO:
            return

        if speed > 1.0:
            GPIO.output(self.in1_pin, GPIO.HIGH)
            GPIO.output(self.in2_pin, GPIO.LOW)
            self.pwm_obj.ChangeDutyCycle(duty)
        elif speed < -1.0:
            GPIO.output(self.in1_pin, GPIO.LOW)
            GPIO.output(self.in2_pin, GPIO.HIGH)
            self.pwm_obj.ChangeDutyCycle(duty)
        else:
            # Coast / passive stop
            GPIO.output(self.in1_pin, GPIO.LOW)
            GPIO.output(self.in2_pin, GPIO.LOW)
            self.pwm_obj.ChangeDutyCycle(0)

    def brake(self):
        """Active dynamic short brake (stops motor instantaneously)."""
        if HAS_RPI_GPIO:
            GPIO.output(self.in1_pin, GPIO.HIGH)
            GPIO.output(self.in2_pin, GPIO.HIGH)
            self.pwm_obj.ChangeDutyCycle(100)


class OmniRobotDrivetrain:
    """
    4-Motor Omnidirectional / Mecanum Holonomic Drivetrain using two TB6612FNG drivers.
    Allows independent simultaneous control of:
      - Longitudinal translation Vx (Forward / Reverse)
      - Lateral translation Vy (Strafe Right / Strafe Left)
      - Rotational yaw rate Omega (Clockwise / Counter-Clockwise)

    Standard 4-Wheel Mecanum Kinematics (X-pattern roller layout on ground):
      V_FL = Vx + Vy + Omega
      V_FR = Vx - Vy - Omega
      V_RL = Vx - Vy + Omega
      V_RR = Vx + Vy - Omega
    """
    def __init__(self):
        if HAS_RPI_GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # Standby pins must be held HIGH to enable TB6612 chips
            GPIO.setup(CONFIG["DRIVER1_STBY"], GPIO.OUT)
            GPIO.setup(CONFIG["DRIVER2_STBY"], GPIO.OUT)
            GPIO.output(CONFIG["DRIVER1_STBY"], GPIO.HIGH)
            GPIO.output(CONFIG["DRIVER2_STBY"], GPIO.HIGH)

        # Initialize individual motors
        self.motor_fl = TB6612Motor(CONFIG["DRIVER1_PWMA"], CONFIG["DRIVER1_AIN1"], CONFIG["DRIVER1_AIN2"])
        self.motor_rl = TB6612Motor(CONFIG["DRIVER1_PWMB"], CONFIG["DRIVER1_BIN1"], CONFIG["DRIVER1_BIN2"])
        self.motor_fr = TB6612Motor(CONFIG["DRIVER2_PWMA"], CONFIG["DRIVER2_AIN1"], CONFIG["DRIVER2_AIN2"])
        self.motor_rr = TB6612Motor(CONFIG["DRIVER2_PWMB"], CONFIG["DRIVER2_BIN1"], CONFIG["DRIVER2_BIN2"])

        self.speeds = {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}
        self.current_cmd = {"vx": 0.0, "vy": 0.0, "omega": 0.0}

    def drive_vector(self, vx, vy, omega):
        """
        Holonomic drive command:
          vx:    Forward (+)/Backward (-) [-100 to 100]
          vy:    Strafe Right (+)/Strafe Left (-) [-100 to 100]
          omega: Turn Clockwise (+)/Turn Counter-Clockwise (-) [-100 to 100]
        """
        self.current_cmd = {"vx": vx, "vy": vy, "omega": omega}

        # Mecanum / 4-Wheel Omni Kinematic Formulation
        fl = vx + vy + omega
        fr = vx - vy - omega
        rl = vx - vy + omega
        rr = vx + vy - omega

        # Apply motor polarity inversions if configured
        if CONFIG.get("INVERT_FL", False): fl = -fl
        if CONFIG.get("INVERT_FR", False): fr = -fr
        if CONFIG.get("INVERT_RL", False): rl = -rl
        if CONFIG.get("INVERT_RR", False): rr = -rr

        # Normalize if any wheel duty exceeds 100% to preserve vector trajectory
        max_req = max(abs(fl), abs(fr), abs(rl), abs(rr))
        if max_req > 100.0:
            scale = 100.0 / max_req
            fl *= scale
            fr *= scale
            rl *= scale
            rr *= scale

        self.speeds = {"fl": round(fl, 1), "fr": round(fr, 1), "rl": round(rl, 1), "rr": round(rr, 1)}

        self.motor_fl.drive(fl)
        self.motor_fr.drive(fr)
        self.motor_rl.drive(rl)
        self.motor_rr.drive(rr)

    def set_wheel_speeds(self, fl, fr, rl, rr):
        """Direct low-level control of each individual wheel (-100 to +100)."""
        self.speeds = {"fl": fl, "fr": fr, "rl": rl, "rr": rr}
        self.motor_fl.drive(fl)
        self.motor_fr.drive(fr)
        self.motor_rl.drive(rl)
        self.motor_rr.drive(rr)

    def stop(self):
        """Passive coast stop."""
        self.drive_vector(0, 0, 0)

    def brake(self):
        """Active dynamic short-brake on all 4 motors."""
        self.current_cmd = {"vx": 0.0, "vy": 0.0, "omega": 0.0}
        self.speeds = {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}
        self.motor_fl.brake()
        self.motor_fr.brake()
        self.motor_rl.brake()
        self.motor_rr.brake()


class PaintActuator:
    """Controls the 12V Diaphragm Paint Pump via the Single-Channel Relay."""
    def __init__(self):
        self.pin = CONFIG["PIN_RELAY_PUMP"]
        self.active_low = CONFIG["RELAY_ACTIVE_LOW"]
        self.is_pumping = False

        if HAS_RPI_GPIO:
            GPIO.setup(self.pin, GPIO.OUT)
            # Default to OFF
            off_state = GPIO.HIGH if self.active_low else GPIO.LOW
            GPIO.output(self.pin, off_state)

    def start_paint(self):
        self.is_pumping = True
        if HAS_RPI_GPIO:
            on_state = GPIO.LOW if self.active_low else GPIO.HIGH
            GPIO.output(self.pin, on_state)
        print("[PUMP] Paint Spray: ACTIVATED (Relay ON)")

    def stop_paint(self):
        self.is_pumping = False
        if HAS_RPI_GPIO:
            off_state = GPIO.HIGH if self.active_low else GPIO.LOW
            GPIO.output(self.pin, off_state)
        print("[PUMP] Paint Spray: DEACTIVATED (Relay OFF)")

    def toggle(self):
        if self.is_pumping:
            self.stop_paint()
        else:
            self.start_paint()
        return self.is_pumping


# ==============================================================================
# 3. PID CONTROLLER FOR PRECISION CLOSED-LOOP NAVIGATION
# ==============================================================================
class PIDController:
    """PID controller with anti-windup clamping and derivative filtering."""
    def __init__(self, kp, ki, kd, output_limits=(-30.0, 30.0)):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.min_out, self.max_out = output_limits
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = time.time()

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = time.time()

    def update(self, error):
        now = time.time()
        dt = max(1e-3, now - self.prev_time)
        self.prev_time = now

        # Integral with anti-windup clamping
        self.integral += error * dt
        self.integral = max(-50.0, min(50.0, self.integral))

        # Derivative
        derivative = (error - self.prev_error) / dt
        self.prev_error = error

        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)
        return max(self.min_out, min(self.max_out, output))


# ==============================================================================
# 4. COMPUTER VISION: PI CAMERA & REAL-TIME COURT LINE DETECTOR
# ==============================================================================
class VisionSystem:
    """
    Captures live frames from the Pi Camera and performs:
      1. Perspective ROI extraction (surface right in front of paint nozzle)
      2. HSV masking for white chalk / existing court boundary line
      3. Centroid calculation to detect lateral line offset (-1.0 to +1.0)
      4. HUD annotation overlay for the live web stream
    """
    def __init__(self):
        self.camera = None
        self.running = False
        self.latest_jpeg = None
        self.line_offset = 0.0     # Normalized offset from frame center (-1.0 to +1.0)
        self.line_detected = False
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_and_process, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _init_camera(self):
        if HAS_PICAM2:
            try:
                cam = Picamera2()
                config = cam.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})
                cam.configure(config)
                cam.start()
                print("[VISION] Pi Camera initialized with Picamera2 (640x480)")
                return cam, "picam2"
            except Exception as e:
                print(f"[VISION] Picamera2 init failed: {e}. Trying cv2.VideoCapture...")

        if HAS_OPENCV:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                print("[VISION] OpenCV VideoCapture(0) opened.")
                return cap, "opencv"

        return None, "none"

    def _capture_and_process(self):
        cam, cam_type = self._init_camera()

        while self.running:
            frame = None
            if cam_type == "picam2":
                try:
                    rgb_array = cam.capture_array()
                    frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR) if HAS_OPENCV else None
                except Exception:
                    time.sleep(0.05)
                    continue
            elif cam_type == "opencv" and cam is not None:
                ret, frame = cam.read()
                if not ret:
                    time.sleep(0.05)
                    continue
            else:
                # Mock synthetic frame if no camera is plugged in
                frame = np.zeros((480, 640, 3), dtype=np.uint8) if HAS_OPENCV else None
                if frame is not None:
                    # Draw mock synthetic court line
                    cv2.line(frame, (320, 0), (320, 480), (255, 255, 255), 18)
                    cv2.putText(frame, "SIMULATED CAMERA FEED", (180, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 200), 2)
                time.sleep(0.04)

            if frame is not None and HAS_OPENCV:
                processed_frame, detected, offset = self._process_frame(frame)
                ret, jpeg = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ret:
                    with self.lock:
                        self.latest_jpeg = jpeg.tobytes()
                        self.line_detected = detected
                        self.line_offset = offset
            else:
                time.sleep(0.05)

        if cam_type == "picam2" and cam:
            try:
                cam.stop()
            except Exception:
                pass
        elif cam_type == "opencv" and cam:
            cam.release()

    def _process_frame(self, frame):
        """Extracts court line lateral deviation via image moments."""
        h, w, _ = frame.shape
        # Focus on Region of Interest (lower 45% of the frame directly ahead of robot)
        roi_top = int(h * 0.55)
        roi = frame[roi_top:h, 0:w]

        # Convert to HSV to isolate bright white or yellow chalk/tape lines
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # White court line mask: low saturation, high value
        lower_white = np.array([0, 0, 180])
        upper_white = np.array([180, 60, 255])
        mask = cv2.inRange(hsv, lower_white, upper_white)

        # Morphological filtering to clean floor noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Calculate moments
        M = cv2.moments(mask)
        line_detected = False
        offset = 0.0

        center_x = w // 2
        if M["m00"] > 1000:  # Valid line blob detected
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"]) + roi_top
            line_detected = True
            # Normalized offset: -1.0 (far left) to +1.0 (far right)
            offset = (cx - center_x) / (w / 2.0)

            # Visual overlay
            cv2.circle(frame, (cx, cy), 8, (0, 0, 255), -1)
            cv2.line(frame, (center_x, cy), (cx, cy), (0, 255, 255), 2)

        # Draw HUD center reticle & ROI box
        cv2.line(frame, (center_x, 0), (center_x, h), (0, 255, 0), 1)
        cv2.rectangle(frame, (0, roi_top), (w, h), (255, 200, 0), 1)

        # Overlay status text
        status_txt = f"OMNI LINE LOCK: {'TRACKING' if line_detected else 'SEARCHING'} | LATERAL OFFSET: {offset:+.2f}"
        color = (0, 255, 0) if line_detected else (0, 165, 255)
        cv2.putText(frame, status_txt, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        return frame, line_detected, offset

    def get_frame(self):
        with self.lock:
            return self.latest_jpeg


# ==============================================================================
# 5. AUTONOMOUS MISSION PLANNER & STATE MACHINE
# ==============================================================================
class CourtPaintingBot:
    """
    Central Coordinator managing navigation, state machine, sensor fusion,
    omnidirectional closed-loop straight-line painting, and cornering maneuvers.
    """
    # Standard court boundary dimensions in meters
    COURT_PRESETS = {
        "tennis_single": {
            "name": "Tennis Singles Perimeter",
            "segments": [
                {"action": "paint", "dist_m": 23.77}, # Sideline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 8.23},  # Baseline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 23.77}, # Sideline 2
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 8.23},  # Baseline 2
                {"action": "turn",  "deg": 90.0}
            ]
        },
        "tennis_double": {
            "name": "Tennis Doubles Perimeter",
            "segments": [
                {"action": "paint", "dist_m": 23.77}, # Sideline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 10.97}, # Baseline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 23.77}, # Sideline 2
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 10.97}, # Baseline 2
                {"action": "turn",  "deg": 90.0}
            ]
        },
        "pickleball": {
            "name": "Pickleball Court Perimeter",
            "segments": [
                {"action": "paint", "dist_m": 13.41}, # Sideline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 6.10},  # Baseline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 13.41}, # Sideline 2
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 6.10},  # Baseline 2
                {"action": "turn",  "deg": 90.0}
            ]
        },
        "badminton_court": {
            "name": "Badminton Doubles Perimeter",
            "segments": [
                {"action": "paint", "dist_m": 13.40},
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 6.10},
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 13.40},
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 6.10},
                {"action": "turn",  "deg": 90.0}
            ]
        },
        "basketball_border": {
            "name": "Basketball Full Court Perimeter",
            "segments": [
                {"action": "paint", "dist_m": 28.00}, # Sideline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 15.00}, # Endline 1
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 28.00}, # Sideline 2
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 15.00}, # Endline 2
                {"action": "turn",  "deg": 90.0}
            ]
        },
        "test_square": {
            "name": "Calibration Square (2.0m x 2.0m)",
            "segments": [
                {"action": "paint", "dist_m": 2.0},
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 2.0},
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 2.0},
                {"action": "turn",  "deg": 90.0},
                {"action": "paint", "dist_m": 2.0},
                {"action": "turn",  "deg": 90.0}
            ]
        }
    }

    def __init__(self):
        self.drivetrain = OmniRobotDrivetrain()
        self.pump = PaintActuator()
        self.imu = MPU6050(bus_num=CONFIG["IMU_I2C_BUS"], address=CONFIG["IMU_ADDR"])
        self.vision = VisionSystem()

        # PID Controllers
        hp = CONFIG["PID_HEADING"]
        self.pid_heading = PIDController(hp["kp"], hp["ki"], hp["kd"],
                                         (-hp["max_correction"], hp["max_correction"]))

        vp = CONFIG["PID_VISION"]
        self.pid_vision = PIDController(vp["kp"], vp["ki"], vp["kd"],
                                        (-vp["max_strafe"], vp["max_strafe"]))

        # State Variables
        self.state = "IDLE"  # IDLE, CALIBRATING, AUTO_PAINTING, MANUAL, EMERGENCY_STOP
        self.target_heading = 0.0
        self.current_mission = None
        self.mission_thread = None
        self.abort_requested = False
        self.mission_progress = ""

    def start_hardware(self):
        """Starts background sensor threads and performs initial IMU calibration."""
        self.imu.start()
        self.vision.start()
        print("[ROBOT] Hardware subsystems online. Starting initial IMU calibration...")
        time.sleep(0.5)
        self.imu.calibrate(num_samples=250)

    def emergency_stop(self):
        """Immediate hard stop for all motors and pump relay."""
        self.abort_requested = True
        self.state = "EMERGENCY_STOP"
        self.pump.stop_paint()
        self.drivetrain.brake()
        print("[EMERGENCY STOP] All motors braked and pump relay disengaged!")

    def set_manual_drive(self, vx, vy, omega):
        """Allows direct omnidirectional teleoperation from web UI."""
        if self.state in ["AUTO_PAINTING"]:
            return False
        self.state = "MANUAL"
        self.drivetrain.drive_vector(vx, vy, omega)
        return True

    def paint_straight_vector(self, distance_meters, speed=None, use_vision=True):
        """
        Navigates along the court line for distance_meters while spraying paint.
        Dual-loop precision control:
          1. Rotational loop (MPU-6050 Gyro PID): Keeps heading rigidly locked to target_heading (omega).
          2. Lateral loop (Pi Camera Vision PID): Translates sideways (vy strafe) to eliminate line error
             WITHOUT changing heading or forward velocity!
        """
        if speed is None:
            speed = CONFIG["BASE_PAINT_SPEED"]

        duration = distance_meters / CONFIG["METERS_PER_SECOND"]
        start_time = time.time()

        self.pid_heading.reset()
        self.pid_vision.reset()
        locked_heading = self.target_heading

        print(f"[PAINT] Starting omni line vector: {distance_meters:.2f}m @ {speed:.1f}% forward speed. Locked Heading: {locked_heading:.1f}°")
        self.pump.start_paint()

        while (time.time() - start_time) < duration:
            if self.abort_requested:
                break

            # 1. Heading gyro closed-loop (corrects rotational yaw)
            current_heading = self.imu.get_heading()
            heading_error = locked_heading - current_heading
            # Output is omega (rotation correction)
            omega_correction = -self.pid_heading.update(heading_error)

            # 2. Camera vision closed-loop (corrects lateral deviation via strafing!)
            strafe_vy = 0.0
            if use_vision and self.vision.line_detected:
                # line_offset is -1.0 (line is to left) to +1.0 (line is to right)
                # To center the line: if line is to the right (+), robot must strafe right (+)
                strafe_vy = self.pid_vision.update(self.vision.line_offset)

            # Drive holonomically: Vx = forward speed, Vy = strafe correction, Omega = gyro heading lock
            self.drivetrain.drive_vector(vx=speed, vy=strafe_vy, omega=omega_correction)
            time.sleep(0.02)  # 50 Hz control loop

        # Finished vector: cut spray immediately and active-brake
        self.pump.stop_paint()
        self.drivetrain.brake()
        time.sleep(0.3)

    def pivot_turn(self, relative_degrees):
        """
        Executes precision in-place pivot using IMU gyro feedback.
        Positive = Turn Right / Clockwise, Negative = Turn Left / Counter-Clockwise.
        """
        self.pump.stop_paint()
        turn_speed = CONFIG["PIVOT_SPEED"]
        target = self.target_heading + relative_degrees
        self.target_heading = target

        print(f"[TURN] Pivoting {relative_degrees:+.1f}° to Target Heading: {target:.1f}°")

        timeout = time.time() + 8.0  # 8s safety timeout
        tolerance = 0.8  # within 0.8 degree accuracy

        while time.time() < timeout:
            if self.abort_requested:
                break

            current = self.imu.get_heading()
            diff = target - current

            if abs(diff) <= tolerance:
                break

            # Proportional speed ramp down to eliminate overshoot
            factor = max(0.40, min(1.0, abs(diff) / 25.0))
            p_speed = turn_speed * factor

            if diff > 0:
                # Rotate CW (Omega > 0)
                self.drivetrain.drive_vector(vx=0, vy=0, omega=p_speed)
            else:
                # Rotate CCW (Omega < 0)
                self.drivetrain.drive_vector(vx=0, vy=0, omega=-p_speed)

            time.sleep(0.01)

        self.drivetrain.brake()
        time.sleep(0.4)
        print(f"[TURN] Pivot complete. Final Heading: {self.imu.get_heading():.2f}°")

    def run_court_mission(self, preset_key):
        """Executes a full multi-segment court border autonomous sequence."""
        if preset_key not in self.COURT_PRESETS:
            print(f"[ERROR] Unknown preset: {preset_key}")
            return

        self.abort_requested = False
        self.state = "AUTO_PAINTING"
        preset = self.COURT_PRESETS[preset_key]
        self.current_mission = preset["name"]
        print(f"[MISSION] Executing Court Preset: {preset['name']}")

        self.imu.reset_yaw(0.0)
        self.target_heading = 0.0

        for idx, step in enumerate(preset["segments"]):
            if self.abort_requested:
                print("[MISSION] Aborted by operator.")
                break

            self.mission_progress = f"Step {idx+1}/{len(preset['segments'])}: {step['action'].upper()}"

            if step["action"] == "paint":
                self.paint_straight_vector(step["dist_m"])
            elif step["action"] == "turn":
                self.pivot_turn(step["deg"])

            time.sleep(0.5)

        self.pump.stop_paint()
        self.drivetrain.stop()
        self.state = "IDLE"
        self.mission_progress = "Mission Finished"
        print("[MISSION] Court sequence finished successfully.")

    def trigger_mission_async(self, preset_key):
        if self.state == "AUTO_PAINTING":
            return False
        self.mission_thread = threading.Thread(target=self.run_court_mission, args=(preset_key,), daemon=True)
        self.mission_thread.start()
        return True


# ==============================================================================
# 6. FLASK WEB SERVER & TELEMETRY STREAMING UI
# ==============================================================================
app = Flask(__name__)
robot = CourtPaintingBot()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OmniCourt Pi — Precision Court Border Painter</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 38, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #00f2fe;
      --accent-grad: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
      --accent-paint: #ff007f;
      --accent-paint-grad: linear-gradient(135deg, #ff0844 0%, #ffb199 100%);
      --success: #00e676;
      --danger: #ff1744;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', sans-serif;
      min-height: 100vh;
      padding: 1.5rem;
      background-image: radial-gradient(circle at 15% 15%, rgba(0, 242, 254, 0.08), transparent 35%),
                        radial-gradient(circle at 85% 85%, rgba(255, 8, 68, 0.08), transparent 35%);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--card-border);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .brand-logo {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      background: var(--accent-grad);
      display: grid;
      place-items: center;
      font-weight: 800;
      color: #000;
      font-size: 1.2rem;
    }
    .brand h1 { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.5px; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
    }
    .badge.active { background: rgba(0, 230, 118, 0.12); color: var(--success); border-color: rgba(0, 230, 118, 0.3); }
    .badge.painting { background: rgba(255, 0, 127, 0.18); color: #ff4081; border-color: rgba(255, 0, 127, 0.4); animation: pulse 1.5s infinite; }
    
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

    .grid {
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 1.5rem;
    }
    @media (max-width: 980px) { .grid { grid-template-columns: 1fr; } }

    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.25rem;
      box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
    .card-title {
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      margin-bottom: 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .stream-container {
      position: relative;
      width: 100%;
      height: 380px;
      background: #000;
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .stream-container img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }

    .telemetry-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.75rem;
      margin-top: 1rem;
    }
    .stat-box {
      background: rgba(0,0,0,0.25);
      border-radius: 10px;
      padding: 0.75rem;
      text-align: center;
      border: 1px solid rgba(255,255,255,0.04);
    }
    .stat-label { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }
    .stat-val { font-family: 'JetBrains Mono', monospace; font-size: 1.15rem; font-weight: 600; color: var(--accent); margin-top: 0.2rem; }

    .btn {
      cursor: pointer;
      border: none;
      border-radius: 10px;
      padding: 0.85rem 1rem;
      font-size: 0.85rem;
      font-weight: 600;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.15s ease;
      background: rgba(255,255,255,0.07);
      color: var(--text);
      border: 1px solid var(--card-border);
      user-select: none;
    }
    .btn:hover { background: rgba(255,255,255,0.12); transform: translateY(-1px); }
    .btn:active { transform: translateY(1px); }
    .btn-primary { background: var(--accent-grad); color: #000; border: none; font-weight: 700; }
    .btn-paint { background: var(--accent-paint-grad); color: #fff; font-weight: 700; border: none; }
    .btn-danger { background: var(--danger); color: #fff; border: none; }

    /* Omnidirectional 3x3 D-Pad with Corner Diagonals */
    .omni-pad {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.45rem;
      max-width: 280px;
      margin: 0.5rem auto;
    }
    .omni-pad .btn {
      padding: 0.9rem 0;
      font-size: 1.1rem;
      font-family: 'JetBrains Mono', monospace;
    }

    .rotate-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.5rem;
      max-width: 280px;
      margin: 0.4rem auto;
    }
    
    .select-box {
      width: 100%;
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      padding: 0.75rem;
      font-size: 0.9rem;
      margin-bottom: 0.75rem;
      outline: none;
    }
  </style>
</head>
<body>

  <div class="header">
    <div class="brand">
      <div class="brand-logo">OP</div>
      <div>
        <h1>OmniCourt Precision Painter</h1>
        <p style="font-size:0.75rem; color:var(--text-muted)">RPi 3-B • 4x Omni Wheels • Dual TB6612 • MPU-6050 Closed-Loop • 12V Diaphragm Pump</p>
      </div>
    </div>
    <div>
      <span id="badge-status" class="badge active">SYS: READY</span>
      <span id="badge-pump" class="badge">PUMP: OFF</span>
    </div>
  </div>

  <div class="grid">
    <!-- Camera Stream & Live Reticle -->
    <div class="card">
      <div class="card-title">
        <span>Pi Camera Real-Time Line Reticle</span>
        <span style="font-size: 0.75rem; font-family: 'JetBrains Mono', monospace;" id="fps-counter">30 FPS</span>
      </div>
      <div class="stream-container">
        <img src="/video_feed" alt="Pi Camera Stream">
      </div>
      <div class="telemetry-row">
        <div class="stat-box">
          <div class="stat-label">Heading (Yaw)</div>
          <div class="stat-val" id="val-yaw">0.0°</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Target Heading</div>
          <div class="stat-val" id="val-target-yaw">0.0°</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Lateral Line Offset</div>
          <div class="stat-val" id="val-line-off">0.00</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Mission Progress</div>
          <div class="stat-val" style="font-size:0.8rem;" id="val-progress">IDLE</div>
        </div>
      </div>
      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:0.5rem; margin-top:0.6rem; font-size:0.75rem; font-family:'JetBrains Mono', monospace; text-align:center;">
        <div style="background:rgba(255,255,255,0.03); padding:0.3rem; border-radius:6px;">FL: <span id="pwm-fl">0%</span></div>
        <div style="background:rgba(255,255,255,0.03); padding:0.3rem; border-radius:6px;">FR: <span id="pwm-fr">0%</span></div>
        <div style="background:rgba(255,255,255,0.03); padding:0.3rem; border-radius:6px;">RL: <span id="pwm-rl">0%</span></div>
        <div style="background:rgba(255,255,255,0.03); padding:0.3rem; border-radius:6px;">RR: <span id="pwm-rr">0%</span></div>
      </div>
    </div>

    <!-- Controls, Autonomous Missions, & Jog -->
    <div style="display:flex; flex-direction:column; gap:1.5rem;">
      
      <!-- Preset Missions -->
      <div class="card">
        <div class="card-title">Autonomous Court Automation</div>
        <label style="font-size:0.75rem; color:var(--text-muted); display:block; margin-bottom:0.3rem;">Select Official Court Dimension:</label>
        <select id="court-select" class="select-box">
          <option value="tennis_single">Tennis Singles Perimeter (23.77m x 8.23m)</option>
          <option value="tennis_double">Tennis Doubles Perimeter (23.77m x 10.97m)</option>
          <option value="pickleball">Pickleball Court Perimeter (13.41m x 6.10m)</option>
          <option value="badminton_court">Badminton Doubles Perimeter (13.40m x 6.10m)</option>
          <option value="basketball_border">Basketball Full Perimeter (28.00m x 15.00m)</option>
          <option value="test_square">Calibration Square (2.00m x 2.00m)</option>
        </select>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.75rem;">
          <button class="btn btn-primary" onclick="startMission()">Start Autonomous Run</button>
          <button class="btn btn-danger" onclick="emergencyStop()">E-STOP / BRAKE</button>
        </div>
      </div>

      <!-- Omnidirectional Manual Teleop & Diagnostics -->
      <div class="card">
        <div class="card-title">Omnidirectional Holonomic Jog</div>
        
        <!-- 3x3 Omnidirectional Translation Pad -->
        <div class="omni-pad">
          <button class="btn" title="Forward-Left Strafe" onmousedown="drive(35, -35, 0)" onmouseup="drive(0, 0, 0)">◤</button>
          <button class="btn" title="Forward" onmousedown="drive(50, 0, 0)" onmouseup="drive(0, 0, 0)">▲</button>
          <button class="btn" title="Forward-Right Strafe" onmousedown="drive(35, 35, 0)" onmouseup="drive(0, 0, 0)">◥</button>
          
          <button class="btn" title="Strafe Left" onmousedown="drive(0, -45, 0)" onmouseup="drive(0, 0, 0)">◄◄</button>
          <button class="btn btn-danger" title="Active Brake" onclick="drive(0, 0, 0)">■</button>
          <button class="btn" title="Strafe Right" onmousedown="drive(0, 45, 0)" onmouseup="drive(0, 0, 0)">►►</button>
          
          <button class="btn" title="Backward-Left Strafe" onmousedown="drive(-35, -35, 0)" onmouseup="drive(0, 0, 0)">◣</button>
          <button class="btn" title="Backward" onmousedown="drive(-50, 0, 0)" onmouseup="drive(0, 0, 0)">▼</button>
          <button class="btn" title="Backward-Right Strafe" onmousedown="drive(-35, 35, 0)" onmouseup="drive(0, 0, 0)">◢</button>
        </div>

        <!-- In-Place Rotation Buttons -->
        <div class="rotate-row">
          <button class="btn" onmousedown="drive(0, 0, -35)" onmouseup="drive(0, 0, 0)">⟲ Rotate CCW</button>
          <button class="btn" onmousedown="drive(0, 0, 35)" onmouseup="drive(0, 0, 0)">⟳ Rotate CW</button>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.75rem; margin-top:0.75rem;">
          <button id="pump-btn" class="btn btn-paint" onclick="togglePump()">Toggle 12V Pump</button>
          <button class="btn" onclick="calibrateIMU()">Zero Gyro Drift</button>
        </div>
      </div>

    </div>
  </div>

  <script>
    function updateTelemetry() {
      fetch('/api/telemetry')
        .then(r => r.json())
        .then(data => {
          document.getElementById('val-yaw').innerText = data.yaw.toFixed(1) + '°';
          document.getElementById('val-target-yaw').innerText = data.target_heading.toFixed(1) + '°';
          document.getElementById('val-line-off').innerText = data.line_offset.toFixed(2);
          document.getElementById('val-progress').innerText = data.progress || data.state;
          
          if (data.speeds) {
            document.getElementById('pwm-fl').innerText = data.speeds.fl + '%';
            document.getElementById('pwm-fr').innerText = data.speeds.fr + '%';
            document.getElementById('pwm-rl').innerText = data.speeds.rl + '%';
            document.getElementById('pwm-rr').innerText = data.speeds.rr + '%';
          }

          const pBadge = document.getElementById('badge-pump');
          if (data.is_pumping) {
            pBadge.className = 'badge painting';
            pBadge.innerText = 'PUMP: SPRAYING';
          } else {
            pBadge.className = 'badge';
            pBadge.innerText = 'PUMP: OFF';
          }

          const sBadge = document.getElementById('badge-status');
          sBadge.innerText = 'STATE: ' + data.state;
        })
        .catch(console.error);
    }
    setInterval(updateTelemetry, 150);

    function drive(vx, vy, omega) {
      fetch('/api/drive_omni', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({vx: vx, vy: vy, omega: omega})
      });
    }

    function togglePump() {
      fetch('/api/pump/toggle', {method: 'POST'});
    }

    function startMission() {
      const select = document.getElementById('court-select').value;
      if (confirm('Start autonomous precision painting for: ' + select + '? Verify perimeter is clear!')) {
        fetch('/api/mission/start', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({preset: select})
        });
      }
    }

    function emergencyStop() {
      fetch('/api/emergency_stop', {method: 'POST'});
    }

    function calibrateIMU() {
      if (confirm('Keep the painter robot stationary for 2 seconds while zeroing gyro offset.')) {
        fetch('/api/imu/calibrate', {method: 'POST'})
          .then(r => r.json())
          .then(data => alert(data.message));
      }
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


def generate_frames():
    """MJPEG streaming generator."""
    while True:
        frame_bytes = robot.vision.get_frame()
        if frame_bytes is None:
            time.sleep(0.05)
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/api/telemetry")
def get_telemetry():
    return jsonify({
        "state": robot.state,
        "yaw": robot.imu.get_heading(),
        "target_heading": robot.target_heading,
        "is_pumping": robot.pump.is_pumping,
        "line_detected": robot.vision.line_detected,
        "line_offset": robot.vision.line_offset,
        "speeds": robot.drivetrain.speeds,
        "progress": robot.mission_progress
    })


@app.route("/api/drive_omni", methods=["POST"])
def manual_drive_omni():
    data = request.get_json() or {}
    vx = float(data.get("vx", 0.0))
    vy = float(data.get("vy", 0.0))
    omega = float(data.get("omega", 0.0))
    robot.set_manual_drive(vx, vy, omega)
    return jsonify({"status": "ok"})


@app.route("/api/pump/toggle", methods=["POST"])
def toggle_pump_api():
    new_state = robot.pump.toggle()
    return jsonify({"is_pumping": new_state})


@app.route("/api/mission/start", methods=["POST"])
def start_mission_api():
    data = request.get_json() or {}
    preset = data.get("preset", "test_square")
    success = robot.trigger_mission_async(preset)
    return jsonify({"success": success})


@app.route("/api/emergency_stop", methods=["POST"])
def stop_api():
    robot.emergency_stop()
    return jsonify({"status": "emergency_stop_triggered"})


@app.route("/api/imu/calibrate", methods=["POST"])
def calibrate_imu_api():
    robot.imu.calibrate(num_samples=250)
    return jsonify({"message": "IMU Gyro drift calibration complete."})


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    print("=" * 75)
    print("   OmniCourt Pi — Autonomous Precision Line & Border Painting Robot")
    print("=" * 75)
    print("Initializing hardware subsystems (IMU, Pi Cam, Dual TB6612, 12V Relay)...")
    robot.start_hardware()

    port = CONFIG["WEB_PORT"]
    print(f"\n[SERVER] Web control dashboard accessible at http://0.0.0.0:{port}")
    print(f"[READY] Press Ctrl+C in terminal or hit E-STOP in Web UI to abort.\n")

    try:
        app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Terminating painter operations safely...")
    finally:
        robot.emergency_stop()
        robot.imu.stop()
        robot.vision.stop()
        if HAS_RPI_GPIO:
            GPIO.cleanup()
        print("[SHUTDOWN] Cleanup finished.")
