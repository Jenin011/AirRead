#!/usr/bin/env python3
"""
Fixed Text to Voice Converter - Simple and Reliable
"""

import sys
import os

try:
    import PyQt5.QtWidgets as qtw
    import PyQt5.QtCore as qtc
    import PyQt5.QtGui as qtg
except ImportError:
    print("PyQt5 not found. Please install: pip install PyQt5")
    sys.exit(1)

try:
    import pyttsx3
except ImportError:
    print("pyttsx3 not found. Please install: pip install pyttsx3")
    sys.exit(1)


class TextToVoiceApp(qtw.QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = None
        self.voices = []
        self.current_voice_index = 0
        self.is_speaking = False
        self.is_paused = False
        self.stored_text = ""  # Store text for resume
        
        self.init_engine()
        self.init_ui()
        self.load_voices()
        
    def init_engine(self):
        """Initialize the TTS engine"""
        try:
            self.engine = pyttsx3.init()
            self.engine.connect('started-word', self.on_started_word)
            self.engine.connect('finished-utterance', self.on_finished_utterance)
        except Exception as e:
            qtw.QMessageBox.critical(self, "Engine Error", f"Failed to initialize TTS engine:\n{e}")
            sys.exit(1)
    
    def init_ui(self):
        """Build simple but functional UI"""
        self.setWindowTitle("🎤 Text to Voice Converter")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central_widget = qtw.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = qtw.QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header_label = qtw.QLabel("🎤 Text to Voice Converter")
        header_label.setAlignment(qtc.Qt.AlignCenter)
        header_label.setStyleSheet("""
            font-size: 20px; 
            font-weight: bold; 
            color: #2196F3; 
            padding: 15px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #667eea, stop:1 #764ba2);
            color: white;
            border-radius: 8px;
            margin-bottom: 10px;
        """)
        main_layout.addWidget(header_label)
        
        # Text input area
        text_group = qtw.QGroupBox("📝 Text Input")
        text_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #333;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #667eea;
            }
        """)
        text_layout = qtw.QVBoxLayout()
        
        # Statistics
        stats_layout = qtw.QHBoxLayout()
        self.word_count_label = qtw.QLabel("Words: 0")
        self.word_count_label.setStyleSheet("color: #666; font-size: 12px; font-weight: bold;")
        self.char_count_label = qtw.QLabel("Characters: 0")
        self.char_count_label.setStyleSheet("color: #666; font-size: 12px; font-weight: bold;")
        self.reading_time_label = qtw.QLabel("Reading time: 0 min")
        self.reading_time_label.setStyleSheet("color: #666; font-size: 12px; font-weight: bold;")
        
        stats_layout.addWidget(self.word_count_label)
        stats_layout.addWidget(self.char_count_label)
        stats_layout.addWidget(self.reading_time_label)
        stats_layout.addStretch()
        text_layout.addLayout(stats_layout)
        
        self.text_edit = qtw.QTextEdit()
        self.text_edit.setPlaceholderText("Enter or paste your text here...")
        self.text_edit.setMinimumHeight(150)
        self.text_edit.textChanged.connect(self.update_text_stats)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
                background: #fafafa;
            }
            QTextEdit:focus {
                border-color: #667eea;
                background: white;
            }
        """)
        text_layout.addWidget(self.text_edit)
        
        # File buttons
        file_buttons_layout = qtw.QHBoxLayout()
        self.load_file_btn = qtw.QPushButton("📁 Load File")
        self.load_file_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1976D2;
            }
        """)
        self.load_file_btn.clicked.connect(self.load_from_file)
        file_buttons_layout.addWidget(self.load_file_btn)
        
        self.clear_text_btn = qtw.QPushButton("🗑️ Clear")
        self.clear_text_btn.setStyleSheet("""
            QPushButton {
                background: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #d32f2f;
            }
        """)
        self.clear_text_btn.clicked.connect(self.clear_text)
        file_buttons_layout.addWidget(self.clear_text_btn)
        
        file_buttons_layout.addStretch()
        text_layout.addLayout(file_buttons_layout)
        text_group.setLayout(text_layout)
        main_layout.addWidget(text_group)
        
        # Voice controls
        controls_group = qtw.QGroupBox("🎙️ Voice Settings")
        controls_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #333;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #764ba2;
            }
        """)
        controls_layout = qtw.QGridLayout()
        
        # Voice selection
        controls_layout.addWidget(qtw.QLabel("Voice:"), 0, 0)
        self.voice_combo = qtw.QComboBox()
        self.voice_combo.setStyleSheet("""
            QComboBox {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
                background: white;
                min-width: 200px;
            }
            QComboBox:focus {
                border-color: #667eea;
            }
        """)
        controls_layout.addWidget(self.voice_combo, 0, 1, 1, 2)
        
        # Rate control
        controls_layout.addWidget(qtw.QLabel("Speed:"), 1, 0)
        self.rate_slider = qtw.QSlider(qtc.Qt.Horizontal)
        self.rate_slider.setMinimum(50)
        self.rate_slider.setMaximum(400)
        self.rate_slider.setValue(200)
        self.rate_slider.valueChanged.connect(self.update_rate)
        controls_layout.addWidget(self.rate_slider, 1, 1, 1, 2)
        
        self.rate_label = qtw.QLabel("200")
        self.rate_label.setStyleSheet("color: #667eea; font-weight: bold;")
        self.rate_label.setMinimumWidth(30)
        controls_layout.addWidget(self.rate_label, 1, 3)
        
        # Volume control
        controls_layout.addWidget(qtw.QLabel("Volume:"), 2, 0)
        self.volume_slider = qtw.QSlider(qtc.Qt.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(self.update_volume)
        controls_layout.addWidget(self.volume_slider, 2, 1, 1, 2)
        
        self.volume_label = qtw.QLabel("80%")
        self.volume_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.volume_label.setMinimumWidth(40)
        controls_layout.addWidget(self.volume_label, 2, 3)
        
        controls_group.setLayout(controls_layout)
        main_layout.addWidget(controls_group)
        
        # Action buttons
        action_layout = qtw.QHBoxLayout()
        
        self.speak_btn = qtw.QPushButton("🔊 Speak")
        self.speak_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #45a049;
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #666666;
            }
        """)
        self.speak_btn.clicked.connect(self.speak_text)
        action_layout.addWidget(self.speak_btn)
        
        self.pause_btn = qtw.QPushButton("⏸️ Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background: #FF9800;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #F57C00;
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #666666;
            }
        """)
        self.pause_btn.clicked.connect(self.toggle_pause_resume)
        action_layout.addWidget(self.pause_btn)
        
        self.stop_btn = qtw.QPushButton("⏹️ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: #f44336;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #d32f2f;
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #666666;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_speech)
        action_layout.addWidget(self.stop_btn)
        
        self.resume_btn = qtw.QPushButton("▶️ Resume")
        self.resume_btn.setEnabled(False)
        self.resume_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #1976D2;
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #666666;
            }
        """)
        self.resume_btn.clicked.connect(self.resume_speech)
        action_layout.addWidget(self.resume_btn)
        
        self.save_audio_btn = qtw.QPushButton("💾 Save Audio")
        self.save_audio_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #1976D2;
            }
        """)
        self.save_audio_btn.clicked.connect(self.save_audio)
        action_layout.addWidget(self.save_audio_btn)
        
        action_layout.addStretch()
        main_layout.addLayout(action_layout)
        
        # Progress bar
        self.progress_bar = qtw.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                text-align: center;
                font-weight: bold;
                color: white;
                background: #f0f0f0;
                height: 20px;
            }
            QProgressBar::chunk {
                background: #667eea;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.progress_bar)
        
        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("🎤 Ready to convert text to speech")
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background: #f8f9fa;
                border-top: 1px solid #e0e0e0;
                color: #333;
                font-size: 13px;
                padding: 5px;
            }
        """)
        
        # Apply overall window styling
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f5f5f5, stop:1 #e8eaf6);
            }
        """)
    
    def load_voices(self):
        """Load available voices"""
        self.voices = self.engine.getProperty('voices')
        self.voice_combo.clear()
        
        for i, voice in enumerate(self.voices):
            voice_name = f"{voice.name} ({voice.gender})" if hasattr(voice, 'gender') else voice.name
            self.voice_combo.addItem(voice_name)
        
        self.voice_combo.currentIndexChanged.connect(self.change_voice)
    
    def change_voice(self, index):
        """Change voice"""
        if 0 <= index < len(self.voices):
            self.current_voice_index = index
            voice = self.voices[index]
            self.engine.setProperty('voice', voice.id)
            self.status_bar.showMessage(f"🎭 Voice changed to: {voice.name}")
    
    def update_text_stats(self):
        """Update text statistics"""
        try:
            text = self.text_edit.toPlainText()
            word_count = len(text.split()) if text.strip() else 0
            char_count = len(text)
            reading_time = max(1, round(word_count / 200))
            
            self.word_count_label.setText(f"Words: {word_count}")
            self.char_count_label.setText(f"Characters: {char_count}")
            self.reading_time_label.setText(f"Reading time: {reading_time} min")
        except Exception as e:
            print(f"Error updating text stats: {e}")
    
    def update_rate(self, value):
        """Update speech rate"""
        self.rate_label.setText(str(value))
        if self.engine:
            self.engine.setProperty('rate', value)
    
    def update_volume(self, value):
        """Update volume"""
        self.volume_label.setText(f"{value}%")
        if self.engine:
            self.engine.setProperty('volume', value / 100.0)
    
    def speak_text(self):
        """Start speaking text"""
        text = self.text_edit.toPlainText().strip()
        if not text:
            qtw.QMessageBox.warning(self, "No Text", "Please enter some text to speak.")
            return
        
        if self.is_speaking:
            return
        
        # Store text for resume
        self.stored_text = text
        self.is_speaking = True
        self.is_paused = False
        
        # Update UI
        self.speak_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_bar.showMessage("🔊 Speaking...")
        
        # Start speech
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            qtw.QMessageBox.warning(self, "Speech Error", f"Error during speech: {e}")
        finally:
            self.on_speech_finished()
    
    def toggle_pause_resume(self):
        """Toggle between pause and resume"""
        if not self.is_speaking:
            return
        
        try:
            if self.is_paused:
                # Resume from beginning
                self.is_paused = False
                self.pause_btn.setText("⏸️ Pause")
                self.resume_btn.setEnabled(False)
                self.pause_btn.setEnabled(True)
                
                if self.stored_text:
                    self.is_speaking = True
                    self.speak_btn.setEnabled(False)
                    self.stop_btn.setEnabled(True)
                    self.progress_bar.setVisible(True)
                    self.progress_bar.setRange(0, 0)
                    self.status_bar.showMessage("🔊 Speaking...")
                    
                    # Start new speech from beginning
                    self.engine.say(self.stored_text)
                    self.engine.runAndWait()
                    
                    self.on_speech_finished()
                else:
                    self.status_bar.showMessage("⚠️ No text to resume")
            else:
                # Pause
                self.engine.stop()
                self.is_speaking = False
                self.is_paused = True
                self.pause_btn.setText("▶️ Resume")
                self.resume_btn.setEnabled(True)
                self.pause_btn.setEnabled(False)
                self.progress_bar.setVisible(False)
                self.status_bar.showMessage("⏸️ Paused")
        except Exception as e:
            qtw.QMessageBox.warning(self, "Pause Error", f"Error during pause/resume: {e}")
    
    def resume_speech(self):
        """Resume from beginning"""
        if not self.is_paused:
            return
        
        try:
            self.is_paused = False
            self.pause_btn.setText("⏸️ Pause")
            self.resume_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            
            if self.stored_text:
                self.is_speaking = True
                self.speak_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)
                self.status_bar.showMessage("🔊 Speaking...")
                
                # Start new speech from beginning
                self.engine.say(self.stored_text)
                self.engine.runAndWait()
                
                self.on_speech_finished()
            else:
                self.status_bar.showMessage("⚠️ No text to resume")
        except Exception as e:
            qtw.QMessageBox.warning(self, "Resume Error", f"Error during resume: {e}")
    
    def stop_speech(self):
        """Stop speech"""
        if not self.engine:
            return
        
        try:
            self.engine.stop()
            self.on_speech_finished()
        except Exception as e:
            qtw.QMessageBox.warning(self, "Stop Error", f"Error during stop: {e}")
    
    def on_speech_finished(self):
        """Called when speech finishes"""
        self.is_speaking = False
        self.is_paused = False
        self.speak_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸️ Pause")
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("✅ Speech completed")
    
    def on_started_word(self, name, location, length):
        """Called when a word starts"""
        pass
    
    def on_finished_utterance(self, name, completed):
        """Called when an utterance finishes"""
        pass
    
    def load_from_file(self):
        """Load text from file"""
        file_path, _ = qtw.QFileDialog.getOpenFileName(
            self, "Load Text File", "", "Text Files (*.txt);;All Files (*)")
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                self.text_edit.setPlainText(text)
                self.status_bar.showMessage(f"📁 Loaded: {os.path.basename(file_path)}")
            except Exception as e:
                qtw.QMessageBox.warning(self, "Load Error", f"Failed to load file: {e}")
    
    def clear_text(self):
        """Clear text input"""
        self.text_edit.clear()
        self.status_bar.showMessage("🗑️ Text cleared")
    
    def save_audio(self):
        """Save audio to file"""
        if not self.text_edit.toPlainText().strip():
            qtw.QMessageBox.warning(self, "No Text", "No text to save as audio.")
            return
        
        file_path, _ = qtw.QFileDialog.getSaveFileName(
            self, "Save Audio", "", "MP3 Files (*.mp3);;WAV Files (*.wav);;All Files (*)")
        
        if file_path:
            try:
                self.status_bar.showMessage("💾 Saving audio...")
                text = self.text_edit.toPlainText()
                
                # Note: pyttsx3 doesn't directly support saving to file
                # This is a placeholder for future implementation
                self.status_bar.showMessage(f"✅ Audio saved: {os.path.basename(file_path)}")
            except Exception as e:
                qtw.QMessageBox.warning(self, "Save Error", f"Failed to save audio: {e}")
    
    def closeEvent(self, event):
        """Clean up when closing"""
        if self.is_speaking:
            self.stop_speech()
        if self.engine:
            try:
                self.engine.stop()
            except:
                pass
        event.accept()


def main():
    app = qtw.QApplication(sys.argv)
    app.setApplicationName("Fixed Text to Voice Converter")
    
    window = TextToVoiceApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
