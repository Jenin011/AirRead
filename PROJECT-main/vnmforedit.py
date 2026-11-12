#!/usr/bin/env python3
"""
Hand Gesture Controlled PDF Reader (Abstracted + Alerts)
- Camera feed is hidden
- Gestures control PDF
- Alerts (QMessageBox) are shown when gesture is detected
"""

import sys
import cv2
import mediapipe as mp
import fitz  # PyMuPDF
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

import time
from collections import deque


class GestureDetector(QThread):
    """Gesture detection thread (background only)"""
    gesture_signal = pyqtSignal(str)
    frame_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.running = False
        self.cap = None

        # MediaPipe setup
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )

        # Gesture variables
        self.prev_x = None
        self.prev_distance = None
        # swipe threshold (pixels) - more reliable threshold
        self.gesture_threshold = 60  # Balanced threshold
        # pinch / distance-change threshold (pixels) - more reliable threshold
        self.zoom_threshold = 25  # Balanced threshold

        # --- simplified swipe detection params ---
        # keep recent palm positions (pixels) and timestamps
        self.x_history = deque(maxlen=5)
        self.y_history = deque(maxlen=5)
        self.t_history = deque(maxlen=5)
        # number of frames required to consider a swipe
        self.swipe_frames = 4  # Stable detection
        # vertical tolerance (pixels) - ignore swipes with large vertical motion
        self.vertical_tol = 100  # Reasonable tolerance
        # cooldown between swipe gestures (s) - prevent rapid fire
        self.gesture_cooldown = 0.5  # Balanced cooldown
        self.last_gesture_time = 0.0
        # minimum average velocity (pixels/sec) to qualify as swipe
        self.min_swipe_velocity = 150.0  # Balanced velocity
        # -------------------------------------

        # distance history for stable pinch detection
        self.dist_history = deque(maxlen=4)  # Reduced from 6
        self.zoom_frames = 2  # Reduced from 3 for faster zoom detection
        # how much palm motion (px) to allow while still considering pinch
        self.palm_motion_block = max(20, int(self.gesture_threshold / 2))  # Reduced from 30

    # allow main thread to change sensitivity while detector runs
    @pyqtSlot(int)
    def set_swipe_threshold(self, val):
        self.gesture_threshold = int(val)

    @pyqtSlot(int)
    def set_swipe_frames(self, val):
        # smaller = quicker detection, larger = more stable
        self.swipe_frames = max(2, int(val))

    @pyqtSlot(int)
    def set_zoom_threshold(self, val):
        self.zoom_threshold = int(val)

    def run(self):
        # Try multiple camera indices to find available camera
        camera_found = False
        for camera_index in range(3):  # Try cameras 0, 1, 2
            self.cap = cv2.VideoCapture(camera_index)
            if self.cap.isOpened():
                # Test if we can actually read a frame
                ret, test_frame = self.cap.read()
                if ret and test_frame is not None:
                    print(f"✅ Camera {camera_index} initialized successfully")
                    camera_found = True
                    break
                else:
                    print(f"⚠️ Camera {camera_index} opened but not capturing frames")
                    self.cap.release()
            else:
                print(f"❌ Camera {camera_index} failed to open")
                self.cap.release()
        
        if not camera_found:
            print("❌ No working cameras found!")
            self.running = False
            return

        self.running = True
        print("📹 Camera detection complete - starting gesture recognition")

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            # Flip for mirror effect
            frame = cv2.flip(frame, 1)
            # emit raw BGR frame for preview (copy to avoid race)
            try:
                self.frame_signal.emit(frame.copy())
            except Exception:
                pass
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Detect hands
            results = self.hands.process(rgb_frame)

            if results.multi_hand_landmarks:
                num_hands = len(results.multi_hand_landmarks)

                if num_hands == 1:
                    # Single hand - swipe and zoom gestures
                    hand = results.multi_hand_landmarks[0]
                    wrist = hand.landmark[0]
                    thumb_tip = hand.landmark[4]
                    index_tip = hand.landmark[8]

                    # Use a simple palm center (wrist + middle_mcp) for more stable tracking
                    mid_mcp = hand.landmark[9]
                    width = frame.shape[1]
                    height = frame.shape[0]
                    palm_x = int(((wrist.x + mid_mcp.x) / 2.0) * width)
                    palm_y = int(((wrist.y + mid_mcp.y) / 2.0) * height)

                    # append history for swipe analysis
                    now = time.time()
                    self.x_history.append(palm_x)
                    self.y_history.append(palm_y)
                    self.t_history.append(now)

                    # Distance between thumb and index finger (pinch)
                    thumb_x = int(thumb_tip.x * frame.shape[1])
                    thumb_y = int(thumb_tip.y * frame.shape[0])
                    index_x = int(index_tip.x * frame.shape[1])
                    index_y = int(index_tip.y * frame.shape[0])

                    finger_distance = np.sqrt((thumb_x - index_x) ** 2 + (thumb_y - index_y) ** 2)

                    # Improved zoom gesture detection
                    self.dist_history.append(finger_distance)
                    
                    if len(self.dist_history) >= self.zoom_frames:
                        if self.prev_distance is not None:
                            # Calculate average distance change for stability
                            dist_change = finger_distance - self.prev_distance
                            
                            # More reliable zoom detection
                            if abs(dist_change) > self.zoom_threshold:
                                if dist_change > 0:
                                    # Fingers getting APART = Zoom OUT
                                    print(f"Zoom OUT detected: change={dist_change:.1f}")
                                    self.gesture_signal.emit("zoom_out")
                                else:
                                    # Fingers getting CLOSER = Zoom IN
                                    print(f"Zoom IN detected: change={dist_change:.1f}")
                                    self.gesture_signal.emit("zoom_in")
                                self.prev_distance = finger_distance
                                # Clear distance history to prevent multiple triggers
                                self.dist_history.clear()
                        else:
                            self.prev_distance = finger_distance

                    # Simplified swipe detection
                    if len(self.x_history) >= self.swipe_frames:
                        xs = np.array(self.x_history)
                        ys = np.array(self.y_history)
                        dx = xs[-1] - xs[0]
                        dy = ys[-1] - ys[0]
                        now = time.time()
                        
                        # Simple and reliable swipe detection
                        if (abs(dx) > self.gesture_threshold
                                and abs(dy) < self.vertical_tol
                                and now - self.last_gesture_time > self.gesture_cooldown):
                            if dx > 0:
                                print(f"Swipe RIGHT detected: dx={dx:.1f}, dy={dy:.1f}")
                                self.gesture_signal.emit("next")
                            else:
                                print(f"Swipe LEFT detected: dx={dx:.1f}, dy={dy:.1f}")
                                self.gesture_signal.emit("prev")
                            self.last_gesture_time = now
                            # clear history to avoid duplicate detection
                            self.x_history.clear()
                            self.y_history.clear()
                            self.t_history.clear()
                    # keep previous distance for pinch fallback
                    self.prev_distance = finger_distance

                elif num_hands == 2:
                    # Two hands - check for open hands gesture to reset zoom
                    hand1 = results.multi_hand_landmarks[0]
                    hand2 = results.multi_hand_landmarks[1]
                    
                    # Check if both hands are open (all fingers extended)
                    def is_hand_open(hand_landmarks):
                        # Check if fingertips are above their corresponding MCP joints
                        thumb_tip = hand_landmarks.landmark[4]
                        index_tip = hand_landmarks.landmark[8]
                        middle_tip = hand_landmarks.landmark[12]
                        ring_tip = hand_landmarks.landmark[16]
                        pinky_tip = hand_landmarks.landmark[20]
                        
                        index_mcp = hand_landmarks.landmark[5]
                        middle_mcp = hand_landmarks.landmark[9]
                        ring_mcp = hand_landmarks.landmark[13]
                        pinky_mcp = hand_landmarks.landmark[17]
                        
                        # All fingertips should be above (lower y) their MCP joints for open hand
                        # For thumb, check if it's extended (approximate check using wrist)
                        wrist = hand_landmarks.landmark[0]
                        thumb_extended = thumb_tip.y < wrist.y - 0.05
                        
                        return (thumb_extended and
                                index_tip.y < index_mcp.y and
                                middle_tip.y < middle_mcp.y and
                                ring_tip.y < ring_mcp.y and
                                pinky_tip.y < pinky_mcp.y)
                    
                    # Check if both hands are open and stable
                    if is_hand_open(hand1) and is_hand_open(hand2):
                        # Check if hands have been open for a moment (stable detection)
                        if not hasattr(self, 'open_hands_start_time') or self.open_hands_start_time is None:
                            self.open_hands_start_time = time.time()
                        elif time.time() - self.open_hands_start_time > 1.0:  # Hold for 1 second
                            # Reset zoom to normal level
                            self.gesture_signal.emit("reset_zoom")
                            self.open_hands_start_time = None  # Reset to prevent multiple triggers
                    else:
                        # Reset open hands timer if hands are not open
                        if hasattr(self, 'open_hands_start_time'):
                            self.open_hands_start_time = None
            else:
                self.prev_x = None
                self.prev_distance = None
                # clear histories when hand not present
                self.x_history.clear()
                self.y_history.clear()
                self.t_history.clear()

            self.msleep(30)  # ~33 FPS for smoother detection (reduced from 50ms)

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        self.quit()
        self.wait()


class SimplePDFReader(QMainWindow):
    """Main PDF reader"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hand Gesture PDF Reader (Abstracted + Alerts)")
        self.setGeometry(100, 100, 1200, 800)

        # PDF state
        self.pdf_doc = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_level = 1.0
        self.gesture_detector = None

        self.init_ui()

    def init_ui(self):
        # Apply modern dark theme like home page
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #050505, stop:1 #000000);
                color: #ffffff;
            }
            QWidget {
                background: transparent;
                color: #ffffff;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.1), stop:1 rgba(255,255,255,0.05));
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 20px;
                padding: 10px 20px;
                font-weight: 600;
                color: #ffffff;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.2), stop:1 rgba(255,255,255,0.1));
                border: 1px solid rgba(255,255,255,0.4);
                transform: translateY(-2px);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.15), stop:1 rgba(255,255,255,0.08));
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                color: #666666;
            }
            QScrollArea {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
            }
            QLabel {
                color: #ffffff;
                background: transparent;
            }
            QGroupBox {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 12px;
                font-weight: 600;
                color: #ffffff;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QSlider::groove:horizontal {
                border: 1px solid rgba(255,255,255,0.2);
                height: 8px;
                background: rgba(255,255,255,0.1);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #00f6ff, stop:1 #a855f7);
                border: 2px solid rgba(255,255,255,0.8);
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSpinBox {
                background: rgba(255,255,255,0.1);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 8px;
                padding: 5px;
                color: #ffffff;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: rgba(255,255,255,0.1);
                border: none;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: rgba(255,255,255,0.2);
            }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- PDF Viewer ---
        pdf_widget = QWidget()
        pdf_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 16px;
            }
        """)
        pdf_layout = QVBoxLayout(pdf_widget)
        pdf_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("📄 PDF READER")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: 700;
                color: #ffffff;
                padding: 10px 0;
                border-bottom: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00f6ff, stop:1 #a855f7);
                margin-bottom: 15px;
            }
        """)
        pdf_layout.addWidget(title_label)

        controls = QHBoxLayout()
        
        self.load_btn = QPushButton("📁 Load PDF")
        self.load_btn.clicked.connect(self.load_pdf)

        self.prev_btn = QPushButton("⬅ Previous")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)

        self.next_btn = QPushButton("Next ➡")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)

        self.zoom_in_btn = QPushButton("🔍+ Zoom In")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_in_btn.setEnabled(False)

        self.zoom_out_btn = QPushButton("🔍- Zoom Out")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_out_btn.setEnabled(False)

        self.page_info = QLabel("No PDF loaded")
        self.page_info.setStyleSheet("""
            QLabel {
                background: rgba(0,246,255,0.1);
                border: 1px solid rgba(0,246,255,0.3);
                border-radius: 15px;
                padding: 8px 15px;
                font-weight: 600;
            }
        """)
        
        self.zoom_info = QLabel("Zoom: 100%")
        self.zoom_info.setStyleSheet("""
            QLabel {
                background: rgba(168,85,247,0.1);
                border: 1px solid rgba(168,85,247,0.3);
                border-radius: 15px;
                padding: 8px 15px;
                font-weight: 600;
            }
        """)

        controls.addWidget(self.load_btn)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.zoom_in_btn)
        controls.addWidget(self.zoom_out_btn)
        controls.addStretch()
        controls.addWidget(self.page_info)
        controls.addWidget(self.zoom_info)

        self.pdf_scroll = QScrollArea()
        self.pdf_label = QLabel("Load a PDF file to start")
        self.pdf_label.setAlignment(Qt.AlignCenter)
        self.pdf_label.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,0.02);
                border: 2px dashed rgba(255,255,255,0.2);
                border-radius: 12px;
                font-size: 16px;
                color: #aaaaaa;
                min-height: 600px;
            }
        """)
        self.pdf_label.setMinimumSize(700, 600)
        self.pdf_scroll.setWidget(self.pdf_label)
        self.pdf_scroll.setWidgetResizable(True)

        pdf_layout.addLayout(controls)
        pdf_layout.addWidget(self.pdf_scroll)

        # --- Gesture Control Panel ---
        gesture_widget = QWidget()
        gesture_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 16px;
            }
        """)
        gesture_layout = QVBoxLayout(gesture_widget)
        gesture_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        gesture_title = QLabel("🎯 GESTURE CONTROLS")
        gesture_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: 700;
                color: #ffffff;
                padding: 10px 0;
                border-bottom: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00f6ff, stop:1 #a855f7);
                margin-bottom: 15px;
            }
        """)
        gesture_layout.addWidget(gesture_title)

        # Camera controls
        camera_widget = QWidget()
        camera_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                padding: 15px;
            }
        """)
        camera_layout = QVBoxLayout(camera_widget)
        
        camera_label = QLabel("📹 Camera")
        camera_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #00f6ff;
                margin-bottom: 10px;
            }
        """)
        camera_layout.addWidget(camera_label)

        self.start_camera_btn = QPushButton("🎥 Start Camera")
        self.start_camera_btn.clicked.connect(self.start_camera)
        self.start_camera_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #10b981, stop:1 #06b6d4);
                border: none;
                border-radius: 20px;
                padding: 12px 20px;
                font-weight: 600;
                color: #ffffff;
            }
        """)

        self.stop_camera_btn = QPushButton("⏹ Stop Camera")
        self.stop_camera_btn.clicked.connect(self.stop_camera)
        self.stop_camera_btn.setEnabled(False)
        self.stop_camera_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef4444, stop:1 #dc2626);
                border: none;
                border-radius: 20px;
                padding: 12px 20px;
                font-weight: 600;
                color: #ffffff;
            }
        """)

        camera_controls = QHBoxLayout()
        camera_controls.addWidget(self.start_camera_btn)
        camera_controls.addWidget(self.stop_camera_btn)
        camera_layout.addLayout(camera_controls)

        # Camera preview
        self.camera_label = QLabel("Camera preview")
        self.camera_label.setFixedSize(320, 180)
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,0.3);
                border: 2px dashed rgba(255,255,255,0.2);
                border-radius: 8px;
                color: #666666;
            }
        """)
        camera_layout.addWidget(self.camera_label)

        gesture_layout.addWidget(camera_widget)

        # Instructions
        instructions_widget = QWidget()
        instructions_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                padding: 15px;
            }
        """)
        instructions_layout = QVBoxLayout(instructions_widget)
        
        instructions_title = QLabel("👋 Gesture Guide")
        instructions_title.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #a855f7;
                margin-bottom: 10px;
            }
        """)
        instructions_layout.addWidget(instructions_title)
        
        instructions = QLabel("• Swipe Left/Right → Previous/Next Page\n• Pinch (thumb+index) → Zoom In/Out")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("""
            QLabel {
                color: #cccccc;
                line-height: 1.6;
                padding: 10px;
                background: rgba(255,255,255,0.02);
                border-radius: 8px;
            }
        """)
        instructions_layout.addWidget(instructions)
        
        gesture_layout.addWidget(instructions_widget)

        # --- Sensitivity controls ---
        sensitivity_widget = QWidget()
        sensitivity_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                padding: 15px;
            }
        """)
        sensitivity_layout = QVBoxLayout(sensitivity_widget)
        
        sensitivity_title = QLabel("⚙️ Sensitivity Settings")
        sensitivity_title.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #00f6ff;
                margin-bottom: 15px;
            }
        """)
        sensitivity_layout.addWidget(sensitivity_title)

        # Swipe sensitivity
        swipe_widget = QWidget()
        swipe_layout = QVBoxLayout(swipe_widget)
        
        swipe_label = QLabel("🔄 Swipe Threshold")
        swipe_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 5px;
            }
        """)
        swipe_layout.addWidget(swipe_label)

        self.swipe_slider = QSlider(Qt.Horizontal)
        self.swipe_slider.setRange(20, 300)
        self.swipe_slider.setValue(80)
        self.swipe_spin = QSpinBox()
        self.swipe_spin.setRange(20, 300)
        self.swipe_spin.setValue(80)
        self.swipe_slider.valueChanged.connect(self.swipe_spin.setValue)
        self.swipe_spin.valueChanged.connect(self.swipe_slider.setValue)
        self.swipe_slider.valueChanged.connect(self.on_swipe_sensitivity_changed)

        swipe_controls = QHBoxLayout()
        swipe_controls.addWidget(self.swipe_slider)
        swipe_controls.addWidget(self.swipe_spin)
        swipe_layout.addLayout(swipe_controls)
        sensitivity_layout.addWidget(swipe_widget)

        # Pinch sensitivity
        pinch_widget = QWidget()
        pinch_layout = QVBoxLayout(pinch_widget)
        
        pinch_label = QLabel("🔍 Pinch Threshold")
        pinch_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 5px;
            }
        """)
        pinch_layout.addWidget(pinch_label)

        self.pinch_slider = QSlider(Qt.Horizontal)
        self.pinch_slider.setRange(5, 150)
        self.pinch_slider.setValue(30)
        self.pinch_spin = QSpinBox()
        self.pinch_spin.setRange(5, 150)
        self.pinch_spin.setValue(30)
        self.pinch_slider.valueChanged.connect(self.pinch_spin.setValue)
        self.pinch_spin.valueChanged.connect(self.pinch_slider.setValue)
        self.pinch_slider.valueChanged.connect(self.on_pinch_sensitivity_changed)

        pinch_controls = QHBoxLayout()
        pinch_controls.addWidget(self.pinch_slider)
        pinch_controls.addWidget(self.pinch_spin)
        pinch_layout.addLayout(pinch_controls)
        sensitivity_layout.addWidget(pinch_widget)

        # Swipe frames
        frames_widget = QWidget()
        frames_layout = QVBoxLayout(frames_widget)
        
        frames_label = QLabel("📊 Swipe Frames")
        frames_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 5px;
            }
        """)
        frames_layout.addWidget(frames_label)

        self.frames_slider = QSlider(Qt.Horizontal)
        self.frames_slider.setRange(2, 10)
        self.frames_slider.setValue(3)
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(2, 10)
        self.frames_spin.setValue(3)
        self.frames_slider.valueChanged.connect(self.frames_spin.setValue)
        self.frames_spin.valueChanged.connect(self.frames_slider.setValue)
        # Swipe frames slider removed - no longer connected to missing function

        frames_controls = QHBoxLayout()
        frames_controls.addWidget(self.frames_slider)
        frames_controls.addWidget(self.frames_spin)
        frames_layout.addLayout(frames_controls)
        sensitivity_layout.addWidget(frames_widget)
        
        gesture_layout.addWidget(sensitivity_widget)
        gesture_layout.addStretch()

        layout.addWidget(pdf_widget, 2)
        layout.addWidget(gesture_widget, 1)

        # Status bar
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background: rgba(0,0,0,0.5);
                color: #ffffff;
                border-top: 1px solid rgba(255,255,255,0.1);
                padding: 5px;
            }
        """)
        self.statusBar().showMessage("🚀 Ready - Load a PDF and start camera for gesture control")

    # --- PDF Functions ---
    def load_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if file_path:
            try:
                self.pdf_doc = fitz.open(file_path)
                self.total_pages = len(self.pdf_doc)
                self.current_page = 0
                self.zoom_level = 1.0
                self.display_page()
                self.update_controls()
                self.statusBar().showMessage(f"Loaded PDF: {self.total_pages} pages")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load PDF: {e}")

    def display_page(self):
        if not self.pdf_doc:
            return
        try:
            page = self.pdf_doc[self.current_page]
            pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom_level, self.zoom_level))
            # Try different image formats if PPM doesn't work
            try:
                img_data = pix.tobytes("ppm")
            except:
                img_data = pix.tobytes("png")

            qimg = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(qimg)

            self.pdf_label.setPixmap(pixmap)
            self.pdf_label.setScaledContents(False)
        except Exception as e:
            print(f"Error displaying page: {e}")
            print(f"PDF doc: {self.pdf_doc}")
            print(f"Current page: {self.current_page}")
            print(f"Total pages: {self.total_pages}")
            print(f"Zoom level: {self.zoom_level}")
            import traceback
            traceback.print_exc()

    def update_controls(self):
        if self.pdf_doc:
            self.prev_btn.setEnabled(self.current_page > 0)
            self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
            self.zoom_in_btn.setEnabled(True)
            self.zoom_out_btn.setEnabled(True)
            self.page_info.setText(f"Page {self.current_page + 1} of {self.total_pages}")
            self.zoom_info.setText(f"Zoom: {int(self.zoom_level * 100)}%")
        else:
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.zoom_in_btn.setEnabled(False)
            self.zoom_out_btn.setEnabled(False)
            self.page_info.setText("No PDF loaded")
            self.zoom_info.setText("Zoom: 100%")

    def prev_page(self):
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self.display_page()
            self.update_controls()

    def next_page(self):
        if self.pdf_doc and self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.display_page()
            self.update_controls()

    def zoom_in(self):
        if self.pdf_doc:
            self.zoom_level = min(3.0, self.zoom_level + 0.25)
            self.display_page()
            self.update_controls()

    def zoom_out(self):
        if self.pdf_doc:
            self.zoom_level = max(0.5, self.zoom_level - 0.25)
            self.display_page()
            self.update_controls()

    # --- Camera & Gesture ---
    def start_camera(self):
        try:
            print("Starting camera...")
            self.camera_label.setText("🔄 Initializing camera...")
            self.statusBar().showMessage("Starting camera...")
            
            # Create gesture detector
            self.gesture_detector = GestureDetector()
            self.gesture_detector.gesture_signal.connect(self.handle_gesture)
            # receive frames and update preview
            self.gesture_detector.frame_signal.connect(self.update_camera_view)
            # apply current sensitivity settings to detector
            self.gesture_detector.set_swipe_threshold(self.swipe_slider.value())
            self.gesture_detector.set_zoom_threshold(self.pinch_slider.value())
            self.gesture_detector.set_swipe_frames(self.frames_slider.value())
            
            # Start the detector thread
            self.gesture_detector.start()
            
            # Wait a moment for camera to initialize
            import time
            time.sleep(2)  # Increased wait time for better initialization
            
            # Check if camera is actually working
            if self.gesture_detector.cap and self.gesture_detector.cap.isOpened():
                # Test if we can actually read a frame
                ret, test_frame = self.gesture_detector.cap.read()
                if ret and test_frame is not None:
                    self.start_camera_btn.setEnabled(False)
                    self.stop_camera_btn.setEnabled(True)
                    self.camera_label.setText("📹 Camera is running - gestures active")
                    self.statusBar().showMessage("Camera started successfully - gestures active", 3000)
                    print("✅ Camera started successfully and is working!")
                else:
                    self.camera_label.setText("❌ Camera not responding")
                    self.statusBar().showMessage("Camera connected but not capturing frames", 5000)
                    print("⚠️ Camera connected but not capturing frames")
            else:
                self.camera_label.setText("❌ Camera failed to start")
                self.statusBar().showMessage("Camera failed - check permissions and connections", 5000)
                print("❌ Camera failed to start!")
                
        except Exception as e:
            print(f"❌ Camera start error: {e}")
            self.camera_label.setText("❌ Camera Error")
            self.statusBar().showMessage("Camera error occurred - check permissions", 5000)
            # Don't show popup error to avoid disrupting user experience

    def stop_camera(self):
        if self.gesture_detector:
            # disconnect preview signal and stop detector
            try:
                self.gesture_detector.frame_signal.disconnect(self.update_camera_view)
            except Exception:
                pass
            self.gesture_detector.stop()
            self.gesture_detector = None

        self.start_camera_btn.setEnabled(True)
        self.stop_camera_btn.setEnabled(False)
        self.camera_label.setText("Camera stopped")
        self.statusBar().showMessage("Camera stopped")

    def handle_gesture(self, gesture):
        """Handle detected gestures silently without alerts"""
        if gesture == "next":
            self.next_page()
            self.statusBar().showMessage("👉 Next Page", 2000)
        elif gesture == "prev":
            self.prev_page()
            self.statusBar().showMessage("👈 Previous Page", 2000)
        elif gesture == "zoom_in":
            self.zoom_in()
            self.statusBar().showMessage("🔍 Zoom In", 2000)
        elif gesture == "zoom_out":
            self.zoom_out()
            self.statusBar().showMessage("🔎 Zoom Out", 2000)
        elif gesture == "reset_zoom":
            self.reset_zoom()
            self.statusBar().showMessage("🔄 Reset Zoom to Normal", 2000)

    def reset_zoom(self):
        """Reset zoom to normal level (1.0)"""
        if self.pdf_doc is not None:
            self.zoom_level = 1.0
            self.display_page()
            self.update_controls()
            self.statusBar().showMessage("Zoom reset to normal level", 2000)

    def closeEvent(self, event):
        if self.gesture_detector:
            self.gesture_detector.stop()
        if self.pdf_doc:
            self.pdf_doc.close()
        event.accept()

    def update_camera_view(self, frame):
        """Show BGR numpy frame on camera_label (thread-safe via signal)."""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.camera_label.setPixmap(pix)
        except Exception:
            pass

    def on_swipe_sensitivity_changed(self, value):
        if hasattr(self, "gesture_detector") and self.gesture_detector:
            try:
                self.gesture_detector.set_swipe_threshold(value)
            except Exception:
                pass
        self.statusBar().showMessage(f"Swipe threshold set to {value}px", 1500)

    def on_pinch_sensitivity_changed(self, value):
        if hasattr(self, "gesture_detector") and self.gesture_detector:
            try:
                self.gesture_detector.set_zoom_threshold(value)
            except Exception:
                pass
        self.statusBar().showMessage(f"Pinch threshold set to {value}px", 1500)
 


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    try:
        import cv2, mediapipe, fitz
    except ImportError:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Missing Dependencies")
        msg.setText("Please install required packages:")
        msg.setInformativeText("pip install opencv-python mediapipe PyMuPDF PyQt5")
        msg.exec_()
        return

    window = SimplePDFReader()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

