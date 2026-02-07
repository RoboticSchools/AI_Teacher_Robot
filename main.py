import sys
import os
import json
import traceback
import random
import time

# --- Third-Party Imports ---
import pygame
from google import genai
from elevenlabs.client import ElevenLabs
import speech_recognition as sr
import cvzone
try:
    from cvzone.HandTrackingModule import HandDetector
except ImportError:
    pass # Handle in worker

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, 
    QLineEdit, QComboBox, QPushButton, QFrame, 
    QHBoxLayout, QGridLayout, QTextEdit
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer
)
from PyQt5.QtGui import (
    QFont, QTextCursor, QPixmap
)

# --- Raspberry Pi / I2C Imports ---
try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
except ImportError:
    print("Warning: Adafruit libraries not found. Servo control will be simulated.")
    board = None
    busio = None
    PCA9685 = None


# ==================================================================================
#                                 CONFIGURATION
# ==================================================================================

# --- API Keys & Models ---
GOOGLE_API_KEY = "AIzaSyC3GFskFLvl65qnR5bF5jTdcwjm_rN0P7c"
GOOGLE_MODEL_NAME = "gemini-2.5-flash-lite"

ELEVENLABS_API_KEY = "sk_165278989925f27cf4d479aae4a75c1bf6ec34e8f1214b25"
ELEVENLABS_VOICE_ID = "TX3LPaxmHKxFdv7VOQHJ"
ELEVENLABS_MODEL_ID = "eleven_v3"

# ==================================================================================
#                                 AI PROMPTS (EDIT HERE)
# ==================================================================================

def GET_LEARNING_PROMPT(topic, language, name, grade, word_limit):
    return (f"Analyze request: Topic='{topic}', Language='{language}', Name='{name}'. "
            f"TASK: Explain this topic to a {grade} student strictly in {language}. "
            f"RULES: "
            f"1. OUTPUT MUST BE IN {language} ONLY. Text must be max {word_limit}"
            f"2. Start by greeting {name} happily in {language}. "
            f"3. Style: Super cool, fun, Gen Z vibe. "
            f"4. Math & Science: Show exact formulas & numbers. "
            f"5. STRICTLY DO NOT use markdown (bold/italic).")

def GET_QUIZ_PROMPT(topic, grade, language, num_questions):
    return (f"Generate a quiz about '{topic}' for a {grade} student in {language}. "
            f"Create exactly {num_questions} multiple-choice questions. "
            f"Output ONLY a raw JSON array. "
            f"STRICT FORMAT RULES: "
            f"1. No markdown (no ```json or ```). "
            f"2. No introductory text or explanations. "
            f"3. Valid JSON Array format: [{{...}}, {{...}}] "
            f"Structure: [{{\"question\": \"Question text\", \"options\": [\"Option A\", \"Option B\", \"Option C\", \"Option D\"], \"answer\": 0}}, ...] "
            f"where 'answer' is the integer index (0, 1, 2, or 3) of the correct option.")

def GET_DOUBT_PROMPT(subject, topic, summary_context, text, language):
    return (f"Context: Subject {subject}, Topic {topic}.\n"
            f"Lesson Summary: {summary_context}...\n"
            f"Student Question: {text}.\n"
            f"TASK: Answer the question based on the Lesson Summary above.\n"
            f"RULES:\n"
            f"1. OUTPUT MUST BE IN {language} ONLY.\n"
            f"2. Answer MUST be less than 30 words.")

# --- Global Client Initialization ---
client = genai.Client(api_key=GOOGLE_API_KEY)


# ==================================================================================
#                                 SERVO CONTROLLER
# ==================================================================================

class ServoController:
    """
    Manages PCA9685 Servo control for the robotic hands.
    Simulates movement if hardware is not detected.
    """
    def __init__(self):
        self.pca = None
        self.RIGHT_HAND = 0
        self.LEFT_HAND = 1
        
        # Servo calibration
        self.SERVO_MIN_US = 500
        self.SERVO_MAX_US = 2500
        self.PWM_PERIOD_US = 20000

        try:
            if board and busio and PCA9685:
                # Initialize I2C and PCA9685
                i2c = busio.I2C(board.SCL, board.SDA)
                self.pca = PCA9685(i2c)
                self.pca.frequency = 50
                print("Servo Controller Initialized (PCA9685).")
                self.reset_all()
        except Exception as e:
            print(f"Error initializing ServoController: {e}")
            self.pca = None

    def set_servo_angle(self, channel, angle):
        """Sets the servo at the specified channel to the given angle (0-180)."""
        if not self.pca:
            return

        angle = max(0, min(180, angle)) 
        pulse_us = self.SERVO_MIN_US + (angle / 180) * (self.SERVO_MAX_US - self.SERVO_MIN_US)
        duty_cycle = int((pulse_us / self.PWM_PERIOD_US) * 65535)
        
        try:
            self.pca.channels[channel].duty_cycle = duty_cycle
        except Exception as e:
            print(f"Error setting servo {channel}: {e}")

    def right_hand(self, angle):
        self.set_servo_angle(self.RIGHT_HAND, angle)

    def left_hand(self, angle):
        self.set_servo_angle(self.LEFT_HAND, angle)
    
    def reset_all(self):
        """Resets both hands to their default down position."""
        self.right_hand(0)
        self.left_hand(180)

    # ---------------- ANIMATIONS ----------------

    def greeting_crisscross(self):
        """Performs a criss-cross wave animation."""
        print("Servo: Greeting Animation")
        if not self.pca: return
        
        QApplication.processEvents()
        
        for _ in range(2):
            for angle in range(40, 121, 2):
                self.right_hand(angle)
                self.left_hand(angle)
                time.sleep(0.02)
                QApplication.processEvents()

            for angle in range(120, 39, -2):
                self.right_hand(angle)
                self.left_hand(angle)
                time.sleep(0.02)
                QApplication.processEvents()

        self.reset_all()

    def quiz_ready_pose(self):
        """Moves both hands to 90 degrees."""
        print("Servo: Quiz Ready Pose (90)")
        if not self.pca: return
        self.right_hand(90)
        self.left_hand(90)

    def correct_answer_gesture(self):
        """Performs a happy up-down wave animation."""
        print("Servo: Correct Answer Gesture")
        if not self.pca: return
        
        QApplication.processEvents()
        
        for angle in range(40, 121, 2):
            self.right_hand(angle)
            self.left_hand(angle)
            time.sleep(0.02)
            QApplication.processEvents()
        
        for angle in range(120, 39, -2):
            self.right_hand(angle)
            self.left_hand(angle)
            time.sleep(0.02)
            QApplication.processEvents()
        
        self.quiz_ready_pose()

    def wrong_answer_gesture(self):
        """Raises both hands to 180 degrees in a 'surrender' or 'oops' gesture."""
        print("Servo: Wrong Answer Gesture")
        if not self.pca: return
        
        self.right_hand(180)
        self.left_hand(180)
        time.sleep(0.6)
        QApplication.processEvents()
        
        self.right_hand(90)
        self.left_hand(90)
        time.sleep(0.4)
        QApplication.processEvents()
        
        self.quiz_ready_pose()

    def cleanup(self):
        """Resets servos and deinitializes the PCA9685 connection."""
        if self.pca:
            self.reset_all()
            try:
                self.pca.deinit()
            except:
                pass


# ==================================================================================
#                                 WORKER THREADS
# ==================================================================================

class AIWorker(QThread):
    """
    Handles interactions with the Google Generative AI API for content generation.
    """
    text_received = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, model, prompt):
        super().__init__()
        self.model = model
        self.prompt = prompt

    def run(self):
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=self.prompt,
            )
            if response.text:
                self.text_received.emit(response.text)
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                self.text_received.emit("Error: Gemini API Quota Exceeded. Try again later.")
            elif "API key" in err or "401" in err:
                 self.text_received.emit("Error: Invalid Gemini API Key.")
            else:
                 self.text_received.emit("Error: Failed to generate content.")
        finally:
            self.finished.emit()


class QuizWorker(QThread):
    """
    Handles generation of quiz questions using Google Generative AI to return structured JSON.
    """
    data_received = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, model, topic, grade, language, num_questions):
        super().__init__()
        self.model = model
        self.topic = topic
        self.grade = grade
        self.language = language
        self.num_questions = num_questions

    def run(self):
        try:
            prompt = GET_QUIZ_PROMPT(self.topic, self.grade, self.language, self.num_questions)
            
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            
            content = response.text
            
            # Clean up potential markdown code blocks
            if "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            elif "```" in content:
                content = content.replace("```", "")
                
            quiz_data = json.loads(content.strip())
            self.data_received.emit(quiz_data)
            
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                 self.error_occurred.emit("Error: Gemini Quota Exceeded.")
            else:
                 self.error_occurred.emit("Error: Failed to generate quiz.")


class VoiceWorker(QThread):
    """
    Handles Text-to-Speech conversion using the ElevenLabs API.
    """
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, text, output_file="output.mp3"):
        super().__init__()
        self.text = text
        self.output_file = output_file

    def run(self):
        try:
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            audio_generator = client.text_to_speech.convert(
                text=self.text,
                voice_id=ELEVENLABS_VOICE_ID,
                model_id=ELEVENLABS_MODEL_ID,
                output_format="mp3_44100_128",
            )
            
            with open(self.output_file, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)
            
            self.finished.emit()
        except Exception as e:
            err = str(e)
            if "401" in err or "API key" in err:
                self.error_occurred.emit("Error: Invalid ElevenLabs API Key.")
            elif "quota" in err.lower():
                 self.error_occurred.emit("Error: ElevenLabs Quota Exceeded.")
            else:
                 self.error_occurred.emit("Error: Audio generation failed.")


class ListenWorker(QThread):
    """
    Handles Voice Recognition (Listening) in a background thread.
    """
    text_recognized = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    stopped = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.is_running = True
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 2.0 # Wait 2 seconds of silence

    def run(self):
        try:
            with sr.Microphone() as source:
                # Adjust for ambient noise once
                self.recognizer.adjust_for_ambient_noise(source)
                
                while self.is_running:
                    try:
                        # Listen with a timeout so we can check self.is_running
                        # phrase_time_limit removed to rely on pause_threshold
                        audio = self.recognizer.listen(source, timeout=5)
                        text = self.recognizer.recognize_google(audio)
                        self.text_recognized.emit(text)
                    except sr.WaitTimeoutError:
                        continue # loop back and check is_running
                    except sr.UnknownValueError:
                        continue # Just didn't understand, listnen again
                    except sr.RequestError as e:
                        self.error_occurred.emit(f"API Error: {e}")
                    except Exception as e:
                        if self.is_running: # If stopped, ignore stream close errors
                             self.error_occurred.emit(str(e))
        except OSError:
            self.error_occurred.emit("Microphone not available (PyAudio/PortAudio missing).")
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.stopped.emit()

    def stop(self):
        try:
            self.is_running = False
        except Exception as e:
            print(f"Error stopping ListenWorker: {e}")


# ==================================================================================
#                                 GESTURE WORKER
# ==================================================================================

class GestureWorker(QThread):
    """
    Handles Camera and Hand Gesture Recognition in a background thread.
    Supports Picamera2 (Pi) and OpenCV (Mac/PC).
    """
    gesture_signal = pyqtSignal(str)  # "OPEN_DOUBT", "CLOSE_DOUBT"

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.detector = None
        self.camera_type = None
        self.cap = None
        self.picam2 = None

    def run(self):
        # Initialize Hand Detector
        try:
            from cvzone.HandTrackingModule import HandDetector
            self.detector = HandDetector(detectionCon=0.5, maxHands=1)
        except ImportError:
            print("GestureWorker: cvzone/mediapipe not installed.")
            return

        # Initialize Camera (Try Picamera2 first)
        try:
            from picamera2 import Picamera2
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            self.camera_type = "PICAM"
            print("GestureWorker: Picamera2 started.")
        except (ImportError, Exception):
            # Fallback to OpenCV
            # print(f"GestureWorker: Picamera2 not found. Applying fallback...")
            try:
                import cv2
                self.cap = cv2.VideoCapture(0) # Index 0 for default camera
                self.cap.set(3, 640)
                self.cap.set(4, 480)
                self.camera_type = "CV2"
                print("GestureWorker: OpenCV Camera started.")
            except ImportError:
                print("GestureWorker: OpenCV not installed.")
                return
            except Exception as e:
                print(f"GestureWorker: OpenCV Error: {e}")
                return

        last_detect_time = 0
        cooldown = 1.0

        while self.is_running:
            try:
                img = None
                if self.camera_type == "PICAM":
                    img = self.picam2.capture_array()
                elif self.camera_type == "CV2":
                    import cv2
                    success, img = self.cap.read()
                    if not success:
                        time.sleep(0.1)
                        continue
                
                if img is None:
                    time.sleep(0.1)
                    continue

                # Detect Hands
                hands, _ = self.detector.findHands(img, draw=False)  # No draw needed

                if hands:
                    hand = hands[0]
                    fingers = self.detector.fingersUp(hand)
                    
                    current_time = time.time()
                    if current_time - last_detect_time > cooldown:
                        # 1. Open Doubt: [1, 1, 1, 1, 1]
                        if fingers == [1, 1, 1, 1, 1]:
                            self.gesture_signal.emit("OPEN_DOUBT")
                            last_detect_time = current_time
                            print("Gesture: OPEN_DOUBT")
                        
                        # 2. Close Doubt: [0, 1, 1, 0, 0]
                        elif fingers == [0, 1, 1, 0, 0]:
                            self.gesture_signal.emit("CLOSE_DOUBT")
                            last_detect_time = current_time
                            print("Gesture: CLOSE_DOUBT")
                        
                        # 3. Toggle Admin (New Feature): [0, 1, 1, 1, 0]
                        elif fingers == [0, 1, 1, 1, 0]:
                            self.gesture_signal.emit("TOGGLE_ADMIN")
                            last_detect_time = current_time
                            print("Gesture: TOGGLE_ADMIN")
                            
                time.sleep(0.05) # Small sleep to save CPU
                
            except Exception as e:
                print(f"GestureWorker Loop Error: {e}")
                time.sleep(1)

        # Cleanup
        if self.camera_type == "PICAM" and self.picam2:
            self.picam2.stop()
            print("GestureWorker: Picamera Stopped.")
        elif self.camera_type == "CV2" and self.cap:
            self.cap.release()
            print("GestureWorker: OpenCV Camera Stopped.")

    def stop(self):
        self.is_running = False
        self.wait()


class StartupWorker(QThread):
    """
    Checks and generates all required audio files on startup.
    """
    progress_update = pyqtSignal(str)
    finished = pyqtSignal()

    def run(self):
        closing_phrases = [
            "Alright, let me know if you have any doubts. See ya!",
            "Great! Happy learning. Bye!",
            "Okay, closing this section. Have fun!",
        ]
        opening_phrases = [
            "I'm listening. What is your doubt?",
            "Go ahead, I'm all ears.",
            "Ask me anything about this topic.",
        ]
        win_phrases = [
            "Woohoo! That is correct! Awesome job.",
            "Haha! You got it right! Well done.",
            "Yippee! Spot on! You actually know this.",
            "Hurray! Correct answer! Keep it up.",
            "Aha! Great! You are doing amazing."
        ]
        lose_phrases = [
            "Oh no! Oops! That is incorrect.",
            "Hmm... Not quite right. Try again next time.",
            "Aww... That's wrong. You can do better.",
            "Uh oh. Incorrect. But don't give up!",
            "Ouch. Missed it! Pay closer attention."
        ]

        tasks = []
        for i, p in enumerate(closing_phrases): tasks.append((p, f"sounds/closing_{i}.mp3"))
        for i, p in enumerate(opening_phrases): tasks.append((p, f"sounds/opening_{i}.mp3"))
        for i, p in enumerate(win_phrases): tasks.append((p, f"sounds/win_exp_{i}.mp3"))
        for i, p in enumerate(lose_phrases): tasks.append((p, f"sounds/lose_exp_{i}.mp3"))

        try:
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            
            for text, filename in tasks:
                if not os.path.exists(filename) or os.path.getsize(filename) < 100:
                    self.progress_update.emit(f"Generating: {filename}...")
                    try:
                        audio_generator = client.text_to_speech.convert(
                            text=text,
                            voice_id=ELEVENLABS_VOICE_ID,
                            model_id=ELEVENLABS_MODEL_ID,
                            output_format="mp3_44100_128",
                        )
                        
                        # Atomic write
                        temp_file = filename + ".part"
                        with open(temp_file, "wb") as f:
                            for chunk in audio_generator:
                                f.write(chunk)
                        
                        if os.path.exists(filename):
                            os.remove(filename)
                        os.rename(temp_file, filename)
                        
                    except Exception as e:
                        print(f"Error generating {filename}: {e}")
                else:
                    self.progress_update.emit(f"Verified: {filename}")
        except Exception as e:
            print(f"Startup Worker Error: {e}")
        
        self.finished.emit()


# ==================================================================================
#                                 MAIN GUI CLASS
# ==================================================================================

class TeacherGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # --- State Variables ---
        self.is_learning_mode = False
        self.pending_text = ""
        self.current_topic = ""
        self.current_subject = ""
        self.worker = None 
        self.is_first_chunk = False
        
        # --- Quiz State ---
        self.quiz_data = []
        self.current_question_index = 0
        self.score = 0
        self.quiz_worker = None
        self.is_quiz_mode = False
        
        # --- Voice/Audio State ---
        pygame.mixer.init()
        self.is_audio_paused = False
        self.is_audio_generating = False
        self.last_generated_audio_text = ""
        self.voice_worker = None
        
        # --- Doubt/Listening State ---
        self.listen_worker = None
        self.is_listening_active = False
        self.doubt_ai_worker = None
        
        # Audio check timer
        self.audio_timer = QTimer()
        self.audio_timer.setInterval(500)
        self.audio_timer.timeout.connect(self.check_audio_status)
        
        # Blinking Dot timer
        self.blink_timer = QTimer()
        self.blink_timer.setInterval(500)
        self.blink_timer.timeout.connect(self.toggle_recording_indicator)
        self.blink_state = False
        
        # --- Servo Controller ---
        self.servos = ServoController()
        
        # --- Gesture Controller ---
        self.gesture_worker = GestureWorker()
        self.gesture_worker.gesture_signal.connect(self.handle_gesture)
        self.gesture_worker.start()

        # --- UI Initialization ---
        self.setWindowTitle("AI Personalized Teacher Robot")
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5) 
        self.main_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        # Build UI Components
        self.setup_loading_screen()
        self.setup_title()
        self.setup_form_card()
        self.setup_result_area()
        self.setup_start_button()
        self.setup_status_label()
        
        # Hide main content initially
        self.top_bar_widget.hide()
        self.card_frame.hide()
        self.start_btn.hide()
        
        # Apply Global Styles
        self.apply_styles()

    # --------------------------------------------------------------------------
    #                               UI SETUP METHODS
    # --------------------------------------------------------------------------
    
    def setup_loading_screen(self):
        self.loading_container = QWidget()
        layout = QVBoxLayout(self.loading_container)
        layout.setAlignment(Qt.AlignCenter)
        
        self.loading_label = QLabel("AI Teacher is Loading...")
        self.loading_label.setStyleSheet("font-size: 32px; font-weight: bold; color: white;")
        layout.addWidget(self.loading_label, alignment=Qt.AlignCenter)
        
        self.loading_sub = QLabel("Checking audio assets...")
        self.loading_sub.setStyleSheet("font-size: 18px; color: #dfe6e9; margin-top: 10px;")
        layout.addWidget(self.loading_sub, alignment=Qt.AlignCenter)
        
        layout.addStretch(2)
        
        # Add to main layout with stretch to fill screen
        self.main_layout.addWidget(self.loading_container, stretch=1)

    def create_logo_widget(self):
        """Creates a standardized white rounded box for the logo."""
        container = QFrame()
        container.setFixedSize(120, 60) 
        container.setStyleSheet("""
            background-color: white;
            border-radius: 10px; 
        """)
        
        # Use a Grid Layout to center perfectly
        layout = QGridLayout(container)
        layout.setContentsMargins(1, 1, 1, 1) # No margins to maximize size
        layout.setAlignment(Qt.AlignCenter)
        
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter) 
        
        if os.path.exists("assets/logo.png"):
            pix = QPixmap("assets/logo.png")
            # Scale to fit the ENTIRE container (110x50)
            scaled_pix = pix.scaled(100, 45, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl.setPixmap(scaled_pix) 
        else:
            lbl.setText("LOGO")
            lbl.setStyleSheet("color: #2D3436; font-weight: bold; font-size: 14px;")
            
        layout.addWidget(lbl)
        return container
    
    def on_app_start(self):
        """Called after window is shown"""
        self.startup_worker = StartupWorker()
        self.startup_worker.progress_update.connect(self.on_loading_update)
        self.startup_worker.finished.connect(self.on_loading_finished)
        self.startup_worker.start()

    def on_loading_update(self, msg):
        self.loading_sub.setText(msg)

    def on_loading_finished(self):
        self.loading_container.hide()
        
        # Show Main UI
        self.top_bar_widget.show()
        self.card_frame.show()
        self.start_btn.show()
        
        # Trigger Greeting
        QTimer.singleShot(500, self.servos.greeting_crisscross)





    def setup_title(self):
        # Create a top bar widget for Logo + Title
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(30, 0, 30, 0) # Margins
        
        # 1. Spacer (Left) - To balance logo on Right
        # We add a dummy widget of same approx width as logo to ensure title is perfectly centered
        dummy = QLabel()
        dummy.setFixedWidth(120) 
        top_bar_layout.addWidget(dummy)
        
        top_bar_layout.addStretch() # Spacer 1
        
        # 2. Title (Center)
        self.title_label = QLabel("AI Personalized Teacher Robot")
        self.title_label.setObjectName("MainTitle") 
        self.title_label.setAlignment(Qt.AlignCenter)
        top_bar_layout.addWidget(self.title_label)
        
        # 3. Spacer (Right)
        top_bar_layout.addStretch() # Spacer 2
        
        # 4. Logo (Right)
        # Wrap logo in a styled container
        self.logo_container = self.create_logo_widget()
        top_bar_layout.addWidget(self.logo_container)
        
        self.main_layout.addWidget(top_bar)
        self.main_layout.addSpacing(10)

        
        self.top_bar_widget = top_bar # Save reference to hide/show entirely


    def setup_form_card(self):
        self.card_frame = QFrame()
        self.card_frame.setFixedSize(600, 380) 
        self.card_frame.setObjectName("CardFrame")
        
        self.card_layout = QGridLayout(self.card_frame)
        self.card_layout.setContentsMargins(30, 30, 30, 30)
        self.card_layout.setSpacing(10)
        self.card_layout.setColumnStretch(1, 1) 

        # Form Helpers
        def add_input_row(label_text, row):
            lbl = QLabel(label_text)
            lbl.setObjectName("InputLabel")
            self.card_layout.addWidget(lbl, row, 0, alignment=Qt.AlignLeft)
            return lbl

        # Name Input
        add_input_row("Name", 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter your name")
        self.name_input.setText("Muni") 
        self.name_input.setFixedHeight(42)
        self.card_layout.addWidget(self.name_input, 0, 1)

        # Grade Input
        add_input_row("Grade", 1)
        self.grade_combo = QComboBox()
        self.grade_combo.setPlaceholderText("Select your grade")
        self.grade_combo.addItems([f"Grade {i}" for i in range(1, 13)])
        self.grade_combo.setCurrentText("Grade 10") 
        self.grade_combo.setFixedHeight(42)
        self.card_layout.addWidget(self.grade_combo, 1, 1)

        # Subject Input
        add_input_row("Subject", 2)
        self.subject_combo = QComboBox()
        self.subject_combo.setPlaceholderText("Select subject")
        self.subject_combo.addItems([
            "Mathematics", "Science", "English", "History", 
            "Geography", "Computer Science", "Physics", "Chemistry"
        ])
        self.subject_combo.setCurrentText("Science") 
        self.subject_combo.setFixedHeight(42)
        self.card_layout.addWidget(self.subject_combo, 2, 1)

        # Topic Input
        add_input_row("Topic", 3)
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Enter topic name")
        self.topic_input.setText("Photo Synthesis") 
        self.topic_input.setFixedHeight(42)
        self.card_layout.addWidget(self.topic_input, 3, 1)

        # Language Input
        add_input_row("Language", 4)
        self.language_combo = QComboBox()
        self.language_combo.setPlaceholderText("Select language")
        self.language_combo.addItems(["English", "Hindi", "Telugu", "Tamil", "Kannada"])
        self.language_combo.setCurrentText("English") 
        self.language_combo.setFixedHeight(42)
        self.card_layout.addWidget(self.language_combo, 4, 1)

        self.main_layout.addWidget(self.card_frame, alignment=Qt.AlignCenter)
        # self.main_layout.addSpacing(5)

    def setup_start_button(self):
        # Container for Button + API Dropdowns
        self.start_btn_container = QWidget()
        layout = QHBoxLayout(self.start_btn_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        # Gemini Model Dropdown (Left of Google Key)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.5-flash-lite", "gemini-2.5-flash"])
        self.model_combo.setFixedSize(160, 40)
        self.model_combo.currentIndexChanged.connect(self.update_api_keys)
        self.model_combo.hide()
        layout.addWidget(self.model_combo)

        # Google API Dropdown (Left)
        self.google_keys_map = {
            "Muni_Gemini": "AIzaSyDAWYS2MqljKuWDbB40BfcubiK1miUvhBw",
            "T3_Gemini": "AIzaSyCMPGP0kLNe5ShmDfDI0WEhTYXj3X053RU",
            "T4_Gemini": "AIzaSyDeni84S72i4_g0tt3g7Df30R31qYfu9r8",
            "T8_Gemini": "AIzaSyCZI-9Qk1EotpNz8a9Cfr4UgqRSWti2UC0",
            "T9_Gemini": "AIzaSyCW2_Fj88tr_A5JGYyGdBSwinP23Y-MqGA",

        }
        self.google_key_combo = QComboBox()
        self.google_key_combo.addItems(list(self.google_keys_map.keys()))
        self.google_key_combo.setFixedSize(160, 40)
        self.google_key_combo.currentIndexChanged.connect(self.update_api_keys)
        self.google_key_combo.hide()
        layout.addWidget(self.google_key_combo)

        # Start Button (Center)
        self.start_btn = QPushButton("Start Learning")
        self.start_btn.setFixedSize(180, 46)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_btn)
        
        # ElevenLabs API Dropdown (Right)
        self.eleven_keys_map = {
            "Muni_11Labs": "sk_165278989925f27cf4d479aae4a75c1bf6ec34e8f1214b25"
        }
        self.eleven_key_combo = QComboBox()
        self.eleven_key_combo.addItems(list(self.eleven_keys_map.keys()))
        self.eleven_key_combo.setFixedSize(160, 40)
        self.eleven_key_combo.currentIndexChanged.connect(self.update_api_keys)
        self.eleven_key_combo.hide()
        layout.addWidget(self.eleven_key_combo)

        # Word Limit Dropdown (Right of ElevenLabs)
        self.word_limit_combo = QComboBox()
        self.word_limit_combo.addItems(["50 words", "100 words", "200 words", "300 words", "500 words", "700 words", "1000 words"])
        self.word_limit_combo.setCurrentText("100 words")
        self.word_limit_combo.setFixedSize(160, 40)
        self.word_limit_combo.hide()
        layout.addWidget(self.word_limit_combo)

        self.main_layout.addWidget(self.start_btn_container, alignment=Qt.AlignCenter)

    def update_api_keys(self):
        global GOOGLE_API_KEY, ELEVENLABS_API_KEY, client, GOOGLE_MODEL_NAME
        
        # Update Model
        GOOGLE_MODEL_NAME = self.model_combo.currentText()
        print(f"Switched Model to: {GOOGLE_MODEL_NAME}")
        
        g_name = self.google_key_combo.currentText()
        if g_name in self.google_keys_map:
            GOOGLE_API_KEY = self.google_keys_map[g_name]
            # Re-init Google Client
            client = genai.Client(api_key=GOOGLE_API_KEY)
            print(f"Switched Google API to: {g_name}")

        e_name = self.eleven_key_combo.currentText()
        if e_name in self.eleven_keys_map:
            ELEVENLABS_API_KEY = self.eleven_keys_map[e_name]
            print(f"Switched ElevenLabs API to: {e_name}")

    def toggle_admin_panel(self):
        # Only allow toggling if we are on the Setup Screen (card_frame is visible)
        if not self.card_frame.isVisible():
            self.google_key_combo.hide()
            self.eleven_key_combo.hide()
            self.word_limit_combo.hide()
            self.model_combo.hide()
            return

        # Toggle visibility of dropdowns
        is_visible = self.google_key_combo.isVisible()
        self.google_key_combo.setVisible(not is_visible)
        self.eleven_key_combo.setVisible(not is_visible)
        self.word_limit_combo.setVisible(not is_visible)
        self.model_combo.setVisible(not is_visible)
        msg = "d: ON" if not is_visible else "d: OFF"
        print(f"Admin Panels {msg}")

    def setup_status_label(self):
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setVisible(False)
        self.main_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

    def setup_result_area(self):
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(0, 20, 0, 0)
        self.result_layout.setSpacing(10)

        # Header Widget (Back | Listen | Title | Doubt | Quiz)
        header_widget = QWidget()
        self.header_layout = QHBoxLayout(header_widget)
        self.header_layout.setContentsMargins(60, 0, 60, 5)

        # 1. Left Controls (Back + Voice)
        left_container = QWidget()
        left_container.setFixedWidth(260)
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        self.back_btn = QPushButton("← Back")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setFixedSize(100, 40)
        self.back_btn.clicked.connect(self.on_back_clicked)
        self.back_btn.setObjectName("BackButton")
        left_layout.addWidget(self.back_btn, alignment=Qt.AlignVCenter)

        self.voice_btn = QPushButton("🔊 Listen")
        self.voice_btn.setFixedSize(110, 40)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.clicked.connect(self.on_voice_clicked)
        left_layout.addWidget(self.voice_btn, alignment=Qt.AlignVCenter)
        
        left_layout.addStretch() # Push buttons left
        self.header_layout.addWidget(left_container)

        self.header_layout.addStretch()

        # 3. Learning Title
        self.learn_title_label = QLabel("")
        self.learn_title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF;")
        self.learn_title_label.setAlignment(Qt.AlignCenter)
        self.header_layout.addWidget(self.learn_title_label, alignment=Qt.AlignCenter)

        self.header_layout.addStretch()

        # Right Controls (Doubt + Quiz)
        right_container = QWidget()
        right_container.setFixedWidth(260)
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0,0,0,0)
        right_layout.setSpacing(10)
        
        right_layout.addStretch()

        # 4. Doubt Button
        self.doubt_btn = QPushButton("Ask Doubt")
        self.doubt_btn.setFixedSize(120, 40)
        self.doubt_btn.setCursor(Qt.PointingHandCursor)
        self.doubt_btn.clicked.connect(self.on_doubt_clicked)
        self.doubt_btn.hide()
        right_layout.addWidget(self.doubt_btn, alignment=Qt.AlignVCenter)

        # 5. Quiz Button
        self.quiz_btn = QPushButton("Quiz Time!")
        self.quiz_btn.setFixedSize(120, 40)
        self.quiz_btn.setCursor(Qt.PointingHandCursor)
        self.quiz_btn.clicked.connect(self.on_quiz_clicked)
        self.quiz_btn.hide()
        right_layout.addWidget(self.quiz_btn, alignment=Qt.AlignVCenter)

        # 6. Secondary LOGO (For Sections 3 & 4) - Hidden by default
        self.header_logo_container = self.create_logo_widget()
        self.header_logo = self.header_logo_container.findChild(QLabel) # Get ref to the label inside
        self.header_logo_container.hide() # Hide container initially
        right_layout.addWidget(self.header_logo_container, alignment=Qt.AlignVCenter)

        
        self.header_layout.addWidget(right_container)

        
        self.result_layout.addWidget(header_widget)


        self.content_widget = QWidget()
        content_layout = QHBoxLayout(self.content_widget)
        # Main Content Spacing
        content_layout.setContentsMargins(30, 20, 30, 30)
        content_layout.setSpacing(20)

        # A. Summary Area
        # Wrap in container to match Doubt Section structure exactly
        self.summary_widget = QWidget()
        self.summary_widget.setStyleSheet("background-color: #FFFFFF; border-radius: 12px; border: 1px solid #dfe6e9;")
        summary_layout = QVBoxLayout(self.summary_widget)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        
        self.result_area = QTextEdit()
        self.result_area.setPlaceholderText("AI Teacher response will appear here...")
        self.result_area.setReadOnly(True)
        # Transparent to match Doubt Chat style
        self.result_area.setStyleSheet("""
            QTextEdit {
                border: none;
                background-color: transparent;
                padding: 25px;
                font-size: 15px;
                color: #2D3436;
            }
        """)
        self.result_area.document().setDocumentMargin(0)
        summary_layout.addWidget(self.result_area)

        content_layout.addWidget(self.summary_widget, stretch=2)

        # B. Doubt Panel
        self.doubt_widget = QWidget()
        # Removed FixedWidth for responsive layout
        self.doubt_widget.setStyleSheet("background-color: #FFFFFF; border-radius: 12px; border: 1px solid #dfe6e9;")
        doubt_layout = QVBoxLayout(self.doubt_widget)
        doubt_layout.setContentsMargins(0, 0, 0, 0)
        
        self.doubt_chat = QTextEdit()
        self.doubt_chat.setReadOnly(True)
        self.doubt_chat.setPlaceholderText("Listening for doubts...")
        # Exact match to result_area style
        self.doubt_chat.setStyleSheet("""
            QTextEdit {
                border: none; 
                background-color: transparent; 
                padding: 25px; /* Internal Padding (ADJUST HERE) */
                font-size: 15px;
                color: #2D3436;
            }
        """)
        self.doubt_chat.document().setDocumentMargin(0)
        doubt_layout.addWidget(self.doubt_chat)
        
        self.doubt_widget.hide()
        content_layout.addWidget(self.doubt_widget, stretch=1)

        self.result_layout.addWidget(self.content_widget)

        # Add Quiz Setup (Hidden by default)
        self.setup_quiz_ui()
        self.result_layout.addWidget(self.quiz_setup_widget)

        self.result_container.hide() 
        self.main_layout.addWidget(self.result_container)

    def setup_quiz_ui(self):
        # --- QUIZ SETUP SCREEN ---
        self.quiz_setup_widget = QWidget()
        layout = QVBoxLayout(self.quiz_setup_widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 40, 0, 0)
        layout.setSpacing(30) 

        # Question Selection Card
        self.quiz_card = QFrame()
        self.quiz_card.setFixedWidth(500)
        self.quiz_card.setStyleSheet("""
            background-color: white;
            border-radius: 16px;
            border: 1px solid #E0E0E0;
        """)
        
        card_layout = QVBoxLayout(self.quiz_card)
        card_layout.setContentsMargins(40, 50, 40, 50)
        card_layout.setSpacing(30)
        card_layout.setAlignment(Qt.AlignCenter)

        lbl = QLabel("How many questions?")
        lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #2D3436; border: none;")
        card_layout.addWidget(lbl, alignment=Qt.AlignCenter)

        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setSpacing(20)
        row_layout.setAlignment(Qt.AlignCenter)

        self.q_num_combo = QComboBox()
        self.q_num_combo.addItems(["5", "10", "15", "20"])
        self.q_num_combo.setFixedSize(120, 45)
        self.q_num_combo.setStyleSheet("""
            QComboBox {
                background-color: #dfe6e9;
                border: none;
                border-radius: 8px;
                padding-left: 15px;
                font-size: 16px;
                color: #2d3436;
            }
            QComboBox::drop-down { border: 0px; }
        """)
        row_layout.addWidget(self.q_num_combo)

        self.start_quiz_btn = QPushButton("Start Quiz")
        self.start_quiz_btn.setFixedSize(150, 45)
        self.start_quiz_btn.setCursor(Qt.PointingHandCursor)
        self.start_quiz_btn.clicked.connect(self.on_start_quiz_clicked)
        self.start_quiz_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #4A6CF7, stop:1 #8A4FFF);
                color: white;
                font-weight: bold;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #5A7CF8, stop:1 #9A5FFF);
            }
        """)
        row_layout.addWidget(self.start_quiz_btn)

        card_layout.addWidget(row_widget)

        layout.addWidget(self.quiz_card, alignment=Qt.AlignCenter)
        
        self.quiz_loading_lbl = QLabel("")
        self.quiz_loading_lbl.setStyleSheet("color: #4A6CF7; font-size: 15px; font-weight: bold;")
        layout.addWidget(self.quiz_loading_lbl, alignment=Qt.AlignCenter)
        
        layout.addStretch()
        self.quiz_setup_widget.hide()
        
        # --- ACTIVE QUIZ SCREEN ---
        self.quiz_active_container = QWidget()
        wrapper_layout = QVBoxLayout(self.quiz_active_container)
        wrapper_layout.setContentsMargins(0, 40, 0, 0)
        
        # Center Row for Horizontal Alignment
        center_row = QHBoxLayout()
        center_row.addStretch()
        
        # Unified Quiz Card
        self.quiz_section_card = QWidget()
        self.quiz_section_card.setFixedWidth(900)
        self.quiz_section_card.setStyleSheet("background-color: #FFFFFF; border-radius: 16px; border: none;")
        
        center_row.addWidget(self.quiz_section_card)
        center_row.addStretch()
        
        wrapper_layout.addLayout(center_row)
        wrapper_layout.addStretch()
        
        # Inner Layout (Redirect active_layout to Card)
        active_layout = QVBoxLayout(self.quiz_section_card)
        active_layout.setContentsMargins(30, 30, 30, 30)
        active_layout.setSpacing(20)

        self.progress_label = QLabel("Question 1/5")
        self.progress_label.setStyleSheet("font-size: 18px; color: #636e72; font-weight: bold;")
        active_layout.addWidget(self.progress_label, alignment=Qt.AlignCenter)

        self.question_label = QLabel("Question text...")
        self.question_label.setWordWrap(True)
        self.question_label.setAlignment(Qt.AlignCenter)
        self.question_label.setStyleSheet("""
            background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #4A6CF7, stop:1 #8A4FFF);
            color: white;
            font-size: 15px;
            font-weight: bold;
            border-radius: 15px;
            padding: 20px;
            margin: 10px 0px;
        """)
        active_layout.addWidget(self.question_label)

        # Options Grid
        options_widget = QWidget()
        self.options_layout = QGridLayout(options_widget)
        self.options_layout.setSpacing(15)
        self.option_buttons = []
        for i in range(4):
            btn = QPushButton(f"Option {i+1}")
            btn.setFixedHeight(60)
            btn.setStyleSheet("""
                QPushButton { 
                    background-color: white; 
                    border: 2px solid #dfe6e9; 
                    border-radius: 12px; 
                    font-size: 15px; 
                    color: #2d3436; 
                    text-align: left; 
                    padding-left: 20px; 
                } 
                QPushButton:hover { 
                    border-color: #4A6CF7; 
                    background-color: #f1f2f6; 
                }
            """)
            btn.clicked.connect(lambda checked, idx=i: self.check_answer(idx))
            self.options_layout.addWidget(btn, i // 2, i % 2)
            self.option_buttons.append(btn)
        
        active_layout.addWidget(options_widget)

        
        self.result_layout.addWidget(self.quiz_active_container) 
        self.quiz_active_container.hide()

        # --- QUIZ RESULTS SCREEN ---
        self.quiz_result_container = QWidget()
        res_layout = QVBoxLayout(self.quiz_result_container)
        res_layout.setAlignment(Qt.AlignCenter)
        
        res_layout.addStretch()

        self.score_label = QLabel("Score: 0/0")
        self.score_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #4A6CF7;")
        res_layout.addWidget(self.score_label, alignment=Qt.AlignCenter)
        
        self.msg_label = QLabel("Great Job!")
        self.msg_label.setStyleSheet("font-size: 24px; color: #2D3436; margin-top: 10px;")
        res_layout.addWidget(self.msg_label, alignment=Qt.AlignCenter)
        
        res_layout.addStretch()
        
        self.quiz_result_container.hide()
        self.result_layout.addWidget(self.quiz_result_container)

    def apply_styles(self):
        """Applies global CSS stylesheet to the application."""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4A6CF7, stop:0.4 #4A6CF7, stop:0.401 #F5F6FA, stop:1 #F5F6FA);
            }
            
            QWidget {
                font-family: 'JetBrains Mono', 'monospace';
                font-size: 15px;
            }

            QLabel {
                color: #2D3436;
            }
            QLabel#MainTitle {
                font-size: 28px;
                font-weight: bold;
                color: #FFFFFF;
                margin-bottom: 0px;
                margin-top: 10px;
            }
            QLabel#InputLabel {
                font-size: 15px;
                font-weight: bold;
                color: #555;
                margin-top: 5px;
            }

            QFrame#CardFrame {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #E0E0E0;
            }
            

            
            QLineEdit {
                background-color: #FAFAFA;
                border: 2px solid #E0E0E0;
                border-radius: 8px;
                padding: 0 15px;
                font-size: 15px;
                color: #333;
            }
            QLineEdit:focus {
                border: 2px solid #4A6CF7;
                background-color: #FFF;
            }

            QComboBox {
                background-color: #FAFAFA;
                border-radius: 8px;
                padding: 0 15px;
                font-size: 15px;
                color: #333;
                border: 2px solid #E0E0E0;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #333333;
                selection-background-color: #4A6CF7;
                selection-color: white;
                border: 1px solid #E0E0E0;
                outline: 0px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #4A6CF7;
                color: white;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #4A6CF7;
                color: white;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left-width: 0px;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background-color: transparent;
            }
            
            /* -- Header Buttons Styles -- */

            
            QPushButton {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #4A6CF7, stop:1 #8A4FFF);
                color: white;
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
                border: 1px solid white;
            }
            QPushButton:hover {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #5A7CF8, stop:1 #9A5FFF);
            }
            QPushButton:pressed {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #3A5CE6, stop:1 #7A3FEE);
            }
        """)


    # --------------------------------------------------------------------------
    #                             EVENT HANDLERS
    # --------------------------------------------------------------------------

    def on_start_clicked(self):
        try:
            name = self.name_input.text().strip()
            grade = self.grade_combo.currentText()
            subject = self.subject_combo.currentText()
            language = self.language_combo.currentText()
            topic = self.topic_input.text().strip()

            if not name or not grade or not subject or not language or not topic:
                self.status_label.setText("Please fill in all fields.")
                self.status_label.setStyleSheet("color: #FF4D4D; font-size: 14px;")
                self.status_label.setVisible(True)
                return

            self.start_btn.setEnabled(False) 

            self.current_topic = topic
            self.current_subject = subject

            self.pending_text = ""
            self.is_learning_mode = False
            self.is_first_chunk = True
            self.result_area.clear()
            self.doubt_chat.clear() # Clear doubt chat on new topic

            if self.worker and self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()

            word_limit = self.word_limit_combo.currentText()
            prompt = GET_LEARNING_PROMPT(topic, language, name, grade, word_limit)

            self.worker = AIWorker(model=GOOGLE_MODEL_NAME, prompt=prompt)
            self.worker.text_received.connect(self.update_text_area)
            self.worker.finished.connect(self.on_generation_finished)
            self.worker.start()

            self.activate_learning_view()
            
        except Exception as e:
            print(f"Error in on_start_clicked: {e}")
            self.start_btn.setEnabled(True)
            traceback.print_exc()

    def on_generation_finished(self):
        """Scrolls back to the top when AI is done."""
        if self.is_learning_mode:
            self.result_area.moveCursor(QTextCursor.Start)
            self.result_area.ensureCursorVisible()
            self.quiz_btn.show() 
            self.doubt_btn.show() # Show Doubt Button

    def on_back_clicked(self):
        self.stop_audio()
        self.close_doubt_session() # Close doubt if open
        
        # Navigation Logic within Quiz Mode
        if self.is_quiz_mode:
            # If in Active Quiz or Results -> Go back to Setup
            if self.quiz_active_container.isVisible() or self.quiz_result_container.isVisible():
                self.quiz_active_container.hide()
                self.quiz_result_container.hide()
                self.quiz_setup_widget.show()
                self.start_quiz_btn.setEnabled(True) 
                return

            # If in Setup -> Go back to Summary
            if self.quiz_setup_widget.isVisible():
                self.is_quiz_mode = False
                self.quiz_setup_widget.hide()
                self.content_widget.show() # Show content container (Summary + Doubt)
                self.result_area.show()
                self.doubt_widget.setVisible(self.is_listening_active) # Show if doubt was active
                self.quiz_btn.show()
                self.doubt_btn.show()
                self.voice_btn.show() 
                
                self.header_logo_container.hide() # Hide Logo in Section 2 (Returning from Quiz)

                
                # Section 2 Pose: Right 0, Left 180
                self.servos.right_hand(0)
                self.servos.left_hand(180)
                
                return 

        # Normal Back to Form logic
        self.result_container.hide()
        self.servos.reset_all() # Reset hands to 0 when leaving sections 3/4
        self.is_learning_mode = False
        self.pending_text = ""
        
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        
        self.top_bar_widget.show() # Show Main Header (with Logo)
        # self.title_label.show() # Inside top_bar_widget now
        # self.title_label.setText("AI Personalized Teacher Robot")
        
        self.card_frame.show()
        self.start_btn.show()

        self.start_btn.setEnabled(True)

    # --- Quiz Handlers ---

    def on_quiz_clicked(self):
        self.servos.quiz_ready_pose() # Section 3: Hands 90
        self.stop_audio()
        self.close_doubt_session() # Close doubt session when entering quiz
        
        self.voice_btn.hide() # Hide Listen Button
        self.doubt_btn.hide() # Hide Doubt Button
        
        self.is_quiz_mode = True
        
        self.content_widget.hide() # Hide entire content container
        self.quiz_btn.hide()
        self.quiz_setup_widget.show()
        self.content_widget.hide() # Hide entire content container
        self.quiz_btn.hide()
        self.quiz_setup_widget.show()
        self.header_logo_container.show() # Show Logo in Section 3



    def on_start_quiz_clicked(self):
        num = int(self.q_num_combo.currentText())
        self.quiz_loading_lbl.setText("Generating Questions... Please wait.")
        self.start_quiz_btn.setEnabled(False)
        
        topic = self.current_topic
        grade = self.grade_combo.currentText()
        lang = self.language_combo.currentText()
        
        self.quiz_worker = QuizWorker(GOOGLE_MODEL_NAME, topic, grade, lang, num)
        self.quiz_worker.data_received.connect(self.on_quiz_ready)
        self.quiz_worker.start()

    def on_quiz_ready(self, data):
        self.quiz_data = data
        self.current_question_index = 0
        self.score = 0
        self.quiz_loading_lbl.setText("")
        self.quiz_setup_widget.hide()
        self.show_question()

    def show_question(self):
        self.quiz_active_container.show()
        q_data = self.quiz_data[self.current_question_index]
        
        self.progress_label.setText(f"Question {self.current_question_index + 1}/{len(self.quiz_data)}")
        self.question_label.setText(q_data['question'])
        
        options = q_data['options']
        for i, btn in enumerate(self.option_buttons):
            btn.setText(options[i])
            # Reset style
            btn.setStyleSheet("""
                QPushButton { 
                    background-color: white; 
                    border: 2px solid #dfe6e9; 
                    border-radius: 12px; 
                    font-size: 15px; 
                    color: #2d3436; 
                    text-align: left; 
                    padding-left: 20px; 
                } 
                QPushButton:hover { 
                    border-color: #4A6CF7; 
                    background-color: #f1f2f6; 
                }
            """)
            btn.setEnabled(True)

    def check_answer(self, user_idx):
        correct_idx = self.quiz_data[self.current_question_index]['answer']
        
        for btn in self.option_buttons:
            btn.setEnabled(False)
            
        # Highlight Correct
        self.option_buttons[correct_idx].setStyleSheet("""
            QPushButton { 
                background-color: #00b894; 
                border: 2px solid #00b894; 
                border-radius: 12px; 
                font-size: 15px; 
                color: white; 
                text-align: left; 
                padding-left: 20px; 
            }
        """)

        # Highlight Wrong if selected
        if user_idx != correct_idx:
            self.option_buttons[user_idx].setStyleSheet("""
                QPushButton { 
                    background-color: #d63031; 
                    border: 2px solid #d63031; 
                    border-radius: 12px; 
                    font-size: 15px; 
                    color: white; 
                    text-align: left; 
                    padding-left: 20px; 
                }
            """)
        # Audio Selection Logic
        audio_file = None
        files_list = []
        if user_idx == correct_idx:
            # Score increment moved here for clarity, though it was already done logic-wise
            self.score += 1
            files_list = [os.path.join('sounds', f) for f in os.listdir('sounds') if f.startswith('win_exp_') and f.endswith('.mp3') and os.path.getsize(os.path.join('sounds', f)) > 100]
        else:
            files_list = [os.path.join('sounds', f) for f in os.listdir('sounds') if f.startswith('lose_exp_') and f.endswith('.mp3') and os.path.getsize(os.path.join('sounds', f)) > 100]
            
        if files_list:
            audio_file = random.choice(files_list)

        # 1. START AUDIO (Non-blocking playback)
        audio_started = False
        if audio_file:
             self.play_audio_file(audio_file)
             audio_started = True

        # 2. RUN SERVO ANIMATION (Blocking but pumps events)
        if user_idx == correct_idx:
            self.servos.correct_answer_gesture()
        else:
            self.servos.wrong_answer_gesture()
        
        # 3. WAIT FOR AUDIO TO FINISH
        if audio_started:
             # Timer to check audio done
             self.quiz_wait_timer = QTimer()
             self.quiz_wait_timer.setInterval(100)
             self.quiz_wait_timer.timeout.connect(self.check_quiz_audio_finished)
             self.quiz_wait_timer.start()
        else:
             # No audio, proceed immediately
             QTimer.singleShot(500, self.next_question)

    def check_quiz_audio_finished(self):
        if not pygame.mixer.music.get_busy():
            self.quiz_wait_timer.stop()
            self.next_question()

    def next_question(self):
        self.current_question_index += 1
        if self.current_question_index < len(self.quiz_data):
            self.show_question()
        else:
            self.show_results()

    def show_results(self):
        self.quiz_active_container.hide()
        self.quiz_result_container.show()
        total = len(self.quiz_data)
        self.score_label.setText(f"Score: {self.score}/{total}")
        
        percentage = (self.score / total) * 100
        if percentage >= 80:
            self.msg_label.setText("Excellent! You're a master.")
        elif percentage >= 50:
            self.msg_label.setText("Good job! Keep practicing.")
        else:
            self.msg_label.setText("Don't give up! Try again.")

    # --- Voice Handlers (Main Summary) ---

    def on_voice_clicked(self):
        if self.is_audio_generating:
             return

        # 1. If audio is PLAYING, we PAUSE
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self.is_audio_paused = True
            self.voice_btn.setText("▶ Resume")
            return

        # 2. If audio is PAUSED, we UNPAUSE
        if self.is_audio_paused:
            pygame.mixer.music.unpause()
            self.is_audio_paused = False
            self.voice_btn.setText("⏸ Pause")
            return

        # 3. If nothing is happening, we GENERATE or PLAY NEW
        current_text = self.result_area.toPlainText()
        if not current_text:
            return

        # Check if we already have the file for this exact text
        if self.last_generated_audio_text == current_text and os.path.exists("sounds/output.mp3"):
             self.play_audio_file("sounds/output.mp3")
        else:
             self.voice_btn.setText("Generating...")
             self.is_audio_generating = True
             self.voice_worker = VoiceWorker(current_text, "sounds/output.mp3")
             self.voice_worker.finished.connect(self.on_audio_generated)
             self.voice_worker.error_occurred.connect(self.on_audio_error)
             self.voice_worker.start()

    def on_audio_generated(self):
        self.is_audio_generating = False
        self.last_generated_audio_text = self.result_area.toPlainText()
        self.play_audio_file("sounds/output.mp3")
        
    def on_audio_error(self, err):
        self.is_audio_generating = False
        self.voice_btn.setText("🔊 Error")
        print(f"Audio Error: {err}")

    # --- Doubt & Listening Handlers ---

    def handle_gesture(self, action):
        """Handles signals from the GestureWorker."""
        if action == "OPEN_DOUBT":
            # Only activate if in Learning View (Summary) and Doubt is NOT already open
            if self.is_learning_mode and not self.is_listening_active:
                
                # If audio is playing, PAUSE it (as requested)
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.pause()
                    self.is_audio_paused = True
                    self.voice_btn.setText("▶ Resume")
                
                # Start the session
                self.play_random_opening_sound()
        
        elif action == "CLOSE_DOUBT":
             # Only close if Doubt IS currently active
             if self.is_listening_active:
                 self.play_random_closing_sound()
        
        elif action == "TOGGLE_ADMIN":
            self.toggle_admin_panel()


    def on_doubt_clicked(self):
        # Toggle Logic
        if self.is_listening_active:
            self.play_random_closing_sound()
        else:
            self.play_random_opening_sound()
    
    def play_random_opening_sound(self):
        # Pause main audio if playing
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self.is_audio_paused = True
            self.voice_btn.setText("▶ Resume")

        opening_phrases = [
            "I'm listening. What is your doubt?",
            "Go ahead, I'm all ears.",
            "Ask me anything about this topic.",
        ]
        msg = random.choice(opening_phrases)
        msg_index = opening_phrases.index(msg)
        filename = f"sounds/opening_{msg_index}.mp3"
        
        # We need to show the doubt widget immediately so the user knows something is happening
        self.doubt_widget.show()
        self.doubt_chat.clear()
        self.doubt_chat.append(f"<b>AI:</b> {msg}")
        
        if os.path.exists(filename):
            self.play_audio_and_listen(filename)
        else:
             # Fallback
            self.voice_worker = VoiceWorker(msg, filename)
            self.voice_worker.finished.connect(lambda: self.play_audio_and_listen(filename))
            self.voice_worker.start()

    def play_audio_and_listen(self, filename):
        self.play_audio_file(filename)
        
        # Ensure any old timer is stopped
        if hasattr(self, 'opening_timer') and self.opening_timer.isActive():
            self.opening_timer.stop()
            
        # Start a periodic timer to check every 500ms if audio is done
        self.opening_timer = QTimer()
        self.opening_timer.setInterval(500) 
        self.opening_timer.timeout.connect(self.check_opening_finished_and_listen)
        self.opening_timer.start()

    def check_opening_finished_and_listen(self):
         # If mixer is NOT busy, it means audio finished
         if not pygame.mixer.music.get_busy():
            self.opening_timer.stop() # Stop checking
            self.start_doubt_session() # NOW we start listening

    def start_doubt_session(self):
        # self.doubt_chat.clear() # Already cleared in play_random_opening_sound
        # self.stop_audio() # Already paused
        self.is_listening_active = True
        self.doubt_widget.show()
        
        # Visuals
        self.blink_timer.start()
        
        # Start Listen Thread
        self.doubt_chat.append("\nListening...")
        self.start_listening_worker()
        
    def start_listening_worker(self):
        if self.listen_worker and self.listen_worker.isRunning():
             return

        self.listen_worker = ListenWorker()
        self.listen_worker.text_recognized.connect(self.handle_parsed_doubt)
        self.listen_worker.error_occurred.connect(lambda e: self.doubt_chat.append(f"<br><span style='color: #FF4D4D;'>Error: {e}</span>"))
        self.listen_worker.start()

    def close_doubt_session(self):
        # Stop Audio immediately
        self.stop_audio()
        
        # Stop any pending resume timers
        if hasattr(self, 'resume_timer') and self.resume_timer.isActive():
            self.resume_timer.stop()
        
        # Stop any pending close timers
        if hasattr(self, 'close_timer') and self.close_timer.isActive():
            self.close_timer.stop()
        
        # Stop any pending opening timers
        if hasattr(self, 'opening_timer') and self.opening_timer.isActive():
            self.opening_timer.stop()

        # Properly stop and cleanup listen worker
        if self.listen_worker:
            self.listen_worker.stop()
            self.listen_worker.wait(2000)  # Wait up to 2 seconds for thread to finish
            self.listen_worker = None
        
        # Cleanup doubt AI worker
        if self.doubt_ai_worker and self.doubt_ai_worker.isRunning():
            self.doubt_ai_worker.wait(1000)
            self.doubt_ai_worker = None
        
        self.is_listening_active = False
        self.doubt_widget.hide()
        self.blink_timer.stop()
        
        # Reset Button Style
        self.doubt_btn.setText("Ask Doubt")
        self.doubt_btn.setStyleSheet("""
             QPushButton {
                background-color: #636e72;
                color: white;
                font-weight: bold;
                border-radius: 10px;
            }
             QPushButton:hover { background-color: #2d3436; }
        """)

    def handle_parsed_doubt(self, text):
        clean_text = text.lower().strip()
        
        # Check for stop commands
        stop_keywords = ["no doubt", "no doubts"]
        if any(keyword in clean_text for keyword in stop_keywords):
            self.play_random_closing_sound()
            return
            
        # STOP LISTENING while API processes
        if self.listen_worker:
            self.listen_worker.stop()

        self.doubt_chat.append(f"\n<span style='color: #4A6CF7;'><b>You:</b> {text}</span>")
        
        # Generate Response
        summary_context = self.result_area.toPlainText()[:2000] # Provide ample context
        language = self.language_combo.currentText()
        prompt = GET_DOUBT_PROMPT(self.current_subject, self.current_topic, summary_context, text, language)
                  
        self.doubt_ai_worker = AIWorker(GOOGLE_MODEL_NAME, prompt)
        self.doubt_ai_worker.text_received.connect(self.display_doubt_response)
        self.doubt_ai_worker.start()

    def display_doubt_response(self, text):
        if "Error:" in text:
             # Add explicit line break spacing for errors
             self.doubt_chat.append(f"<br><b>AI:</b> <span style='color: #FF4D4D;'>{text}</span><br>")
        else:
             self.doubt_chat.append(f"\n<b>AI:</b> {text}\n")
        # Auto-play Audio for Doubt
        self.play_doubt_audio_response(text)

    def play_doubt_audio_response(self, text):
        if text:
             self.voice_worker = VoiceWorker(text, "sounds/doubt_output.mp3")
             self.voice_worker.finished.connect(lambda: self.play_audio_and_resume("sounds/doubt_output.mp3"))
             self.voice_worker.start()

    def play_audio_and_resume(self, filename):
        self.play_audio_file(filename)
        # Start checking for audio finish to resume listening
        self.resume_timer = QTimer()
        self.resume_timer.setInterval(1000)
        self.resume_timer.timeout.connect(self.check_audio_finished_and_listen)
        self.resume_timer.start()

    def check_audio_finished_and_listen(self):
        if not pygame.mixer.music.get_busy():
            self.resume_timer.stop()
            if self.is_listening_active:
                self.doubt_chat.append("\nListening...")
                self.start_listening_worker()

    def play_audio_and_close(self, filename):
        self.play_audio_file(filename)
        # Wait for audio to finish then hide via timer
        self.close_timer = QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.setInterval(2500) # Avg length of closing audio
        self.close_timer.timeout.connect(self.close_doubt_session)
        self.close_timer.start()

    def play_random_closing_sound(self):
        """Selects a random closing phrase and plays it before closing."""
        closing_phrases = [
            "Alright, let me know if you have any doubts. See ya!",
            "Great! Happy learning. Bye!",
            "Okay, closing this section. Have fun!",
        ]
        msg = random.choice(closing_phrases)
        msg_index = closing_phrases.index(msg)
        filename = f"sounds/closing_{msg_index}.mp3"
        
        self.doubt_chat.append(f"\n<b>AI:</b> {msg}")

        # Stop listening worker first so we don't pick up the PC's own audio
        if self.listen_worker: self.listen_worker.stop()

        if os.path.exists(filename):
            self.play_audio_and_close(filename)
        else:
            # Fallback if file missing (should be there from startup)
            self.voice_worker = VoiceWorker(msg, filename)
            self.voice_worker.finished.connect(lambda: self.play_audio_and_close(filename))
            self.voice_worker.start()
    def play_audio_and_close(self, filename):
        self.play_audio_file(filename)
        
        # Ensure any old timer is stopped
        if hasattr(self, 'close_timer') and self.close_timer.isActive():
            self.close_timer.stop()
            
        # Start a periodic timer to check every 500ms if audio is done
        self.close_timer = QTimer()
        self.close_timer.setInterval(500) 
        self.close_timer.timeout.connect(self.check_audio_finished_and_close)
        self.close_timer.start()

    def check_audio_finished_and_close(self):
         # If mixer is NOT busy, it means audio finished
         if not pygame.mixer.music.get_busy():
            self.close_timer.stop() # Stop checking
            self.close_doubt_session() # Now safely close


    def toggle_recording_indicator(self):
        self.blink_state = not self.blink_state
        color = "#00b894" if self.blink_state else "#636e72" # Green <-> Grey
        self.doubt_btn.setStyleSheet(f"""
             QPushButton {{
                background-color: {color};
                color: white;
                font-weight: bold;
                border-radius: 10px;
            }}
        """)

    # --------------------------------------------------------------------------
    #                             LOGIC & HELPERS
    # --------------------------------------------------------------------------

    def activate_learning_view(self):
        self.card_frame.hide()
        self.start_btn.hide()
        # Force hide admin dropdowns when leaving setup
        self.google_key_combo.hide()
        self.eleven_key_combo.hide()
        self.word_limit_combo.hide()
        self.model_combo.hide()

        self.status_label.hide()
        
        self.top_bar_widget.hide() # Hide Section 1 Header
        self.learn_title_label.setText(f"{self.current_topic} ({self.current_subject})")
        
        self.result_container.show()
        self.result_container.show()
        self.header_logo_container.hide() # Ensure Logo is Hidden in Section 2


        # Section 2 Pose: Right 0, Left 180
        self.servos.right_hand(0)
        self.servos.left_hand(180)

        self.result_area.setText("Your AI Teacher is creating personalized content for you...")
        self.is_learning_mode = True
        
        self.quiz_btn.hide() 
        self.doubt_btn.hide() # Hide until content ready

    def update_text_area(self, text):
        clean_text = text.replace('*', '').replace('#', '').replace('`', '')
        
        if self.is_first_chunk:
             self.result_area.clear()
             self.is_first_chunk = False

        cursor = self.result_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if "Error:" in clean_text:
             # Strip whitespace and apply red styling without extra leading newlines
             cursor.insertHtml(f"<span style='color: #FF4D4D;'>{clean_text.strip()}</span><br>")
        else:
             cursor.insertText(clean_text)

        self.result_area.setTextCursor(cursor)
        self.result_area.ensureCursorVisible()

    def play_audio_file(self, filename):
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            
            # Update UI based on which file it is
            if filename == "sounds/output.mp3":
                self.voice_btn.setText("⏸ Pause")
                self.audio_timer.start()
        except Exception as e:
            print(f"Play Error: {e}")

    def stop_audio(self):
        """Stops any playing audio and resets state."""
        if pygame.mixer.music.get_busy() or self.is_audio_paused:
            pygame.mixer.music.stop()
        self.is_audio_paused = False
        self.audio_timer.stop()
        self.voice_btn.setText("🔊 Listen")

    def check_audio_status(self):
        """Checks if audio has finished playing to reset UI."""
        if not pygame.mixer.music.get_busy() and not self.is_audio_paused:
            self.voice_btn.setText("🔊 Listen")
            self.audio_timer.stop()
    
    def closeEvent(self, event):
        """Cleanup on app exit."""
        try:
            # Stop all audio
            self.stop_audio()
            
            # Close doubt session properly
            self.close_doubt_session()
            
            # Stop all timers
            if hasattr(self, 'audio_timer'):
                self.audio_timer.stop()
            if hasattr(self, 'blink_timer'):
                self.blink_timer.stop()
            if hasattr(self, 'quiz_wait_timer') and hasattr(self.quiz_wait_timer, 'isActive') and self.quiz_wait_timer.isActive():
                self.quiz_wait_timer.stop()
            
            # Stop and cleanup all workers
            if self.worker and self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(1000)
            
            if self.quiz_worker and self.quiz_worker.isRunning():
                self.quiz_worker.terminate()
                self.quiz_worker.wait(1000)
            
            if self.voice_worker and self.voice_worker.isRunning():
                self.voice_worker.wait(1000)
            
            # Stop gesture worker
            if self.gesture_worker and self.gesture_worker.isRunning():
                self.gesture_worker.stop()
                self.gesture_worker.wait(2000)
            
            # Cleanup servos
            self.servos.cleanup()
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            event.accept()

# ==================================================================================
#                                 MAIN EXECUTION
# ==================================================================================

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Optional: Load custom fonts here if needed
    
    window = TeacherGUI()
    window.showFullScreen()
    
    # Trigger Startup Animation
    QTimer.singleShot(500, window.on_app_start) # Small delay to ensure UI is ready
    
    sys.exit(app.exec_())
