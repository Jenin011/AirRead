import sys
import os
import threading
import time
from datetime import datetime
import logging
import traceback

# Setup a log file next to the script
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'voicetotext.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'), logging.StreamHandler()]
)

try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QTextEdit,
        QLabel,
        QFileDialog,
        QMessageBox,
    )
    from PyQt5.QtGui import QFont, QTextCursor
except Exception as e:
    logging.exception('Failed to import PyQt5')
    print('PyQt5 is required to run the desktop GUI. Install with: pip install PyQt5')
    raise

try:
    import speech_recognition as sr
except Exception:
    logging.exception('Failed to import speech_recognition')
    raise

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except Exception:
    logging.exception('Failed to import reportlab')
    raise

try:
    from spellchecker import SpellChecker
except Exception:
    logging.exception('Failed to import spellchecker')
    raise

# Text-to-speech (optional)
try:
    import pyttsx3
except Exception:
    pyttsx3 = None


class VoiceToTextWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice to Text - Desktop")
        self.setGeometry(150, 100, 800, 600)

        self.recognizer = sr.Recognizer()
        self.spell = SpellChecker()  # English spell checker
        self.is_listening = False    # for continuous dictation
        
        # Text-to-speech variables
        self.tts_engine = None
        self.tts_thread = None
        self.is_speaking = False
        self.is_paused = False
        self.current_word_index = 0
        self.words = []
        self.speech_rate = 150  # words per minute

        self._init_ui()
        self._apply_styles()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        title = QLabel("Voice to Text → PDF")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel(
            "Record once or start dictation, then use Auto Correct and save as PDF."
        )
        subtitle.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "Recognized text will appear here. You can also type or edit manually."
        )
        self.text_edit.setFont(QFont("Segoe UI", 11))
        main_layout.addWidget(self.text_edit, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_record = QPushButton("🎙 Record Once")
        self.btn_record.clicked.connect(self.record_voice)
        btn_layout.addWidget(self.btn_record)

        self.btn_start_cont = QPushButton("▶ Start Dictation")
        self.btn_start_cont.clicked.connect(self.start_continuous_dictation)
        btn_layout.addWidget(self.btn_start_cont)

        self.btn_stop_cont = QPushButton("⏹ Stop Dictation")
        self.btn_stop_cont.clicked.connect(self.stop_continuous_dictation)
        btn_layout.addWidget(self.btn_stop_cont)

        self.btn_clear = QPushButton("Clear Text")
        self.btn_clear.clicked.connect(self.text_edit.clear)
        btn_layout.addWidget(self.btn_clear)

        self.btn_autocorrect = QPushButton("Auto Correct (English)")
        self.btn_autocorrect.clicked.connect(self.auto_correct_text)
        btn_layout.addWidget(self.btn_autocorrect)

        self.btn_save_pdf = QPushButton("Save as PDF")
        self.btn_save_pdf.clicked.connect(self.save_as_pdf)
        btn_layout.addWidget(self.btn_save_pdf)

        main_layout.addLayout(btn_layout)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #f5f7fb; }
            QTextEdit {
                background: #ffffff;
                border: 1px solid #d0d7e2;
                border-radius: 6px;
                padding: 8px;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d0d7e2;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #eef2fb;
            }
            QLabel {
                color: #333333;
            }
            """
        )

    def _show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)

    def _show_info(self, message: str):
        QMessageBox.information(self, "Info", message)

    def record_voice(self):
        self.status_label.setText("Adjusting for noise and listening... Speak now.")
        self.repaint()

        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                audio = self.recognizer.listen(
                    source,
                    timeout=5,
                    phrase_time_limit=12,
                )
        except sr.WaitTimeoutError:
            self.status_label.setText("No speech detected (timeout). Try again.")
            return
        except OSError as e:
            self.status_label.setText("")
            self._show_error(
                f"Microphone error: {e}\n\nCheck Windows microphone permissions and device."
            )
            return

        self.status_label.setText("Recognizing speech...")
        self.repaint()

        try:
            text = self.recognizer.recognize_google(audio, language="en-US")
            if text:
                self._append_text_with_paragraph_logic(text)
                self.status_label.setText("Recognition success.")
            else:
                self.status_label.setText("Nothing recognized.")
        except sr.UnknownValueError:
            self.status_label.setText("")
            self._show_info("Could not understand the audio. Please try again.")
        except sr.RequestError as e:
            self.status_label.setText("")
            self._show_error(f"Speech recognition service error: {e}")

    def start_continuous_dictation(self):
        if self.is_listening:
            self._show_info("Already listening.")
            return
        self.is_listening = True
        self.status_label.setText("Continuous dictation started. Speak in short sentences.")
        t = threading.Thread(target=self._continuous_listen_loop, daemon=True)
        t.start()

    def stop_continuous_dictation(self):
        if not self.is_listening:
            return
        self.is_listening = False
        self.status_label.setText("Continuous dictation stopped.")

    def _continuous_listen_loop(self):
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                while self.is_listening:
                    try:
                        QTimer.singleShot(0, lambda: self.status_label.setText("Listening... Speak now"))
                        audio = self.recognizer.listen(
                            source,
                            timeout=5,
                            phrase_time_limit=10,
                        )
                    except sr.WaitTimeoutError:
                        # Don't continue immediately, give a small delay
                        time.sleep(0.1)
                        continue
                    except OSError as e:
                        self.is_listening = False
                        QTimer.singleShot(0, lambda: self.status_label.setText(f"Mic error: {e}"))
                        break

                    try:
                        QTimer.singleShot(0, lambda: self.status_label.setText("Recognizing..."))
                        text = self.recognizer.recognize_google(audio, language="en-US")
                        if text:
                            QTimer.singleShot(0, lambda t=text: self.status_label.setText(f"Recognized: '{t}'"))
                            QTimer.singleShot(0, lambda t=text: self._append_text_with_paragraph_logic(t))
                        else:
                            QTimer.singleShot(0, lambda: self.status_label.setText("Nothing recognized"))
                    except sr.UnknownValueError:
                        QTimer.singleShot(0, lambda: self.status_label.setText("Could not understand audio"))
                        continue
                    except sr.RequestError as e:
                        self.is_listening = False
                        QTimer.singleShot(0, lambda: self.status_label.setText(f"Service error: {e}"))
                        break
                    
                    # Small delay between listening cycles
                    time.sleep(0.5)
        finally:
            self.is_listening = False
            QTimer.singleShot(0, lambda: self.status_label.setText("Continuous dictation stopped"))

    def _append_text_with_paragraph_logic(self, text: str):
        if not text:
            return

        # Capitalize first letter of the text
        text = text[0].upper() + text[1:] if text else text
        
        existing = self.text_edit.toPlainText()
        word_count = len(text.split())

        if not existing.strip():
            self.text_edit.setPlainText(text)
        else:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.End)
            self.text_edit.setTextCursor(cursor)
            
            current = self.text_edit.toPlainText()
            if word_count < 10:  # Short chunk → continue same paragraph
                if not current.endswith((" ", "\n")):
                    # Add space if needed
                    self.text_edit.insertPlainText(" ")
                else:
                    # Check if we're at the start of a new sentence
                    if current.strip().endswith(('.', '!', '?')):
                        text = text[0].upper() + text[1:] if text else text
                self.text_edit.insertPlainText(text)
            else:  # Long chunk → new paragraph
                # Ensure the first letter is capitalized for new paragraphs
                text = text[0].upper() + text[1:] if text else text
                self.text_edit.append("")
                self.text_edit.append(text)

    def auto_correct_text(self):
        text = self.text_edit.toPlainText()
        if not text.strip():
            self._show_info("Nothing to correct. Please record or type some text first.")
            return

        corrected_lines = []
        for line in text.splitlines():
            words = line.split()
            corrected_words = []
            for w in words:
                prefix = ""
                suffix = ""
                while w and not w[0].isalnum():
                    prefix += w[0]
                    w = w[1:]
                while w and not w[-1].isalnum():
                    suffix = w[-1] + suffix
                    w = w[:-1]

                if w:
                    corrected_word = self.spell.correction(w)
                else:
                    corrected_word = ""

                corrected_words.append(prefix + corrected_word + suffix)
            corrected_lines.append(" ".join(corrected_words))

        self.text_edit.setPlainText("\n".join(corrected_lines))
        self.status_label.setText("Auto-correction applied (English).")

    def save_as_pdf(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            self._show_info("Text is empty. Please record or type something first.")
            return

        default_name = f"voice_notes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF",
            default_name,
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not path:
            return

        try:
            self._export_text_to_pdf(text, path)
            self._show_info(f"Saved PDF to:\n{path}")
        except Exception as e:
            self._show_error(f"Failed to save PDF: {e}")

    @staticmethod
    def _export_text_to_pdf(text: str, out_path: str):
        root, ext = os.path.splitext(out_path)
        if ext.lower() != ".pdf":
            out_path = root + ".pdf"

        c = canvas.Canvas(out_path, pagesize=A4)
        width, height = A4

        margin = 50
        max_width = width - 2 * margin
        line_height = 14
        y = height - margin

        c.setFont("Helvetica", 11)

        for line in text.splitlines():
            while line:
                if c.stringWidth(line, "Helvetica", 11) <= max_width:
                    c.drawString(margin, y, line)
                    y -= line_height
                    break
                cut = len(line)
                while c.stringWidth(line[:cut], "Helvetica", 11) > max_width and cut > 0:
                    cut -= 1
                space_pos = line.rfind(" ", 0, cut)
                if space_pos != -1:
                    piece = line[:space_pos]
                    line = line[space_pos + 1 :]
                else:
                    piece = line[:cut]
                    line = line[cut:]
                c.drawString(margin, y, piece)
                y -= line_height

                if y < margin:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - margin

            if y < margin:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - margin

        c.showPage()
        c.save()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    win = VoiceToTextWindow()
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        logging.info('Starting VoiceToText application')
        main()
    except Exception as e:
        # Log full traceback to file
        logging.exception('Unhandled exception in voicetotext')
        tb = traceback.format_exc()
        # Attempt to show a GUI error dialog if possible
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, 'VoiceToText Error', 'An unexpected error occurred. See voicetext.log for details.')
        except Exception:
            pass
        print('An unexpected error occurred. See voicetext.log for details.')
        sys.exit(1)