import sys
import time
import threading
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QPushButton,
    QSlider, QLabel, QFileDialog, QToolBar
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QIcon, QKeySequence, QAction

from play_audio import (
    play,
    get_audio_duration_ffmpeg,
    extract_cover_art,
    get_metadata
)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(HERE, "sample.mp3")
DEFAULT_COVER = os.path.join(HERE, "default.png")
PLAY_IMG = os.path.join(HERE, "play.png")
PAUSE_IMG = os.path.join(HERE, "pause.png")

def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds or 0))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

class PlayerThread(threading.Thread):
    def __init__(self, file_path: str, start_ts: float = 0.0):
        super().__init__(daemon=True)
        self.file_path = file_path
        self.start_ts = float(start_ts or 0.0)
        self.proc = None
        self._stop_requested = threading.Event()

    def run(self):
        try:
            result = play(self.file_path, self.start_ts)
            self.proc = result[0] if isinstance(result, (tuple, list)) else result

            while self.proc is not None and self.proc.poll() is None and not self._stop_requested.is_set():
                time.sleep(0.1)

            if self._stop_requested.is_set() and self.proc is not None and self.proc.poll() is None:
                try:
                    self.proc.terminate()
                    time.sleep(0.1)
                    if self.proc.poll() is None:
                        self.proc.kill()
                except Exception:
                    pass
        except Exception:
            print("Uh Oh!")

    def stop(self, timeout: float = 1.0):
        self._stop_requested.set()
        if self.proc is not None and getattr(self.proc, "poll", lambda: 1)() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.join(timeout=timeout)
        if self.is_alive():
            try:
                if self.proc is not None and getattr(self.proc, "poll", lambda: 1)() is None:
                    self.proc.kill()
            except Exception:
                pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Player")
        self.set_centered_geometry(520, 380)

        # Playback state
        self.file_path = DEFAULT_FILE
        self.player_thread = None
        self.ts_start = 0.0 
        self.last_play_clock = None
        self.status = "Paused"

        self.duration = get_audio_duration_ffmpeg(self.file_path)
        self.metadata = get_metadata(self.file_path)
        self.cover_path = extract_cover_art(self.file_path) or DEFAULT_COVER

        self._build_ui()
        self._create_toolbar()
        self._setup_shortcuts()

        self.timer = QTimer(self)
        self.timer.setInterval(300)  # ms
        self.timer.timeout.connect(self._update_ui)

        self._is_seeking = False

    # ----------------     UI      ----------------

    def _build_ui(self):
        root = QVBoxLayout()

        # Title
        title_text = self.metadata.get("title") or Path(self.file_path).stem
        artist_text = self.metadata.get("artist") or ""
        self.header = QLabel(f"{title_text} — {artist_text}", alignment=Qt.AlignmentFlag.AlignCenter)
        self.header.setFixedHeight(28)
        root.addWidget(self.header)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(256, 256)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_cover_pixmap()

        cover_container = QHBoxLayout()
        cover_container.addStretch()
        cover_container.addWidget(self.cover_label)
        cover_container.addStretch()
        root.addLayout(cover_container)

        row = QHBoxLayout()
        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setFixedWidth(90)
        row.addWidget(self.elapsed_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(0, int(self.duration)))
        self.slider.setSingleStep(1)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        row.addWidget(self.slider)

        self.total_label = QLabel(format_time(self.duration))
        self.total_label.setFixedWidth(90)
        row.addWidget(self.total_label)

        root.addLayout(row)

        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon(PLAY_IMG))
        self.play_button.setIconSize(QSize(48, 48))
        self.play_button.clicked.connect(self.toggle_play_pause)
        root.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignCenter)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

    def _update_cover_pixmap(self):
        if self.cover_path and os.path.exists(self.cover_path):
            pix = QPixmap(self.cover_path).scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
        else:
            pix = QPixmap(DEFAULT_COVER).scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
        self.cover_label.setPixmap(pix)

    # ----------------       Toolbar       ----------------

    def _create_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        open_act = QAction("Open", self)
        open_act.setShortcut(QKeySequence("Ctrl+O"))
        open_act.triggered.connect(self.open_file_dialog)
        toolbar.addAction(open_act)

        toolbar.addSeparator()

        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        toolbar.addAction(quit_act)

    def _setup_shortcuts(self):
        play_pause_act = QAction(self)
        play_pause_act.setShortcut(QKeySequence(Qt.Key.Key_Space))
        play_pause_act.triggered.connect(self.toggle_play_pause)
        self.addAction(play_pause_act)

    # ---------------- File open / load ----------------

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Audio File", "",
                                                   "Audio Files (*.mp3 *.wav *.flac *.m4a *.aac)")
        if file_path:
            self.load_new_track(file_path)

    def load_new_track(self, new_path: str):
        if self.player_thread:
            self.player_thread.stop()
            self.player_thread = None

        self.file_path = new_path
        self.duration = get_audio_duration_ffmpeg(self.file_path)
        self.metadata = get_metadata(self.file_path)
        self.cover_path = extract_cover_art(self.file_path) or DEFAULT_COVER

        title_text = self.metadata.get("title") or Path(self.file_path).stem
        artist_text = self.metadata.get("artist") or ""
        self.header.setText(f"{title_text} — {artist_text}")

        self._update_cover_pixmap()

        self.slider.setRange(0, max(0, int(self.duration)))
        self.slider.setValue(0)
        self.elapsed_label.setText("00:00:00")
        self.total_label.setText(format_time(self.duration))

        self.ts_start = 0.0
        self.last_play_clock = None
        self.status = "Paused"
        self.play_button.setIcon(QIcon(PLAY_IMG))
        self.timer.stop()

    # ---------------- Play / Pause / Seek logic ----------------

    def toggle_play_pause(self):
        if not self.file_path:
            return
        if self.status == "Paused":
            self.start_play()
        else:
            self.pause_play()

    def start_play(self):
        if self.player_thread and self.player_thread.proc and self.player_thread.proc.poll() is None:
            return

        if self.last_play_clock is None:
            if self.slider.value() > 0:
                self.ts_start = float(self.slider.value())

        self.player_thread = PlayerThread(self.file_path, self.ts_start)
        self.player_thread.start()
        self.last_play_clock = time.time()
        self.timer.start()
        self.status = "Playing"
        self.play_button.setIcon(QIcon(PAUSE_IMG))

    def pause_play(self):
        if self.last_play_clock is not None:
            elapsed = (time.time() - self.last_play_clock) + self.ts_start
            self.ts_start = max(0.0, float(elapsed))

        if self.player_thread:
            self.player_thread.stop()
            self.player_thread = None

        self.last_play_clock = None
        self.timer.stop()
        self.status = "Paused"
        self.play_button.setIcon(QIcon(PLAY_IMG))
        self.elapsed_label.setText(format_time(self.ts_start))
        try:
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.ts_start))
        finally:
            self.slider.blockSignals(False)

    # ----------------     Slider      ----------------

    def _on_slider_pressed(self):
        self._is_seeking = True
        self.timer.stop()
        if self.last_play_clock is not None:
            elapsed = (time.time() - self.last_play_clock) + self.ts_start
            self.ts_start = max(0.0, float(elapsed))
        if self.player_thread:
            self.player_thread.stop()
            self.player_thread = None
        self.last_play_clock = None
        self.status = "Paused"
        self.play_button.setIcon(QIcon(PLAY_IMG))

    def _on_slider_released(self):
        new_ts = float(self.slider.value())
        self.ts_start = new_ts
        self._is_seeking = False
        self.start_play()

    # ----------------      UI update       ----------------

    def _update_ui(self):
        if self._is_seeking:
            return
        if self.last_play_clock is None:
            return
        elapsed = (time.time() - self.last_play_clock) + self.ts_start
        if self.duration > 0 and elapsed >= self.duration:
            elapsed = self.duration
            self.pause_play()
        self.elapsed_label.setText(format_time(elapsed))
        try:
            self.slider.blockSignals(True)
            self.slider.setValue(int(elapsed))
        finally:
            self.slider.blockSignals(False)

    # ---------------- Window geometry & cleanup ----------------

    def set_centered_geometry(self, w: int, h: int):
        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry((screen.width() - w) // 2, (screen.height() - h) // 2, w, h)

    def closeEvent(self, event):
        if self.player_thread:
            self.player_thread.stop()
            self.player_thread = None
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
