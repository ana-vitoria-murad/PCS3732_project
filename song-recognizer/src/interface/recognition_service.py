from __future__ import annotations

import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import wave
from enum import Enum
from pathlib import Path
import time

import numpy as np

from src.match_song import (
    get_song_info,
    load_query_fingerprints,
    lookup_matches,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SRC_DIR = PROJECT_ROOT / "src"
DATABASE_DIR = PROJECT_ROOT / "database"
RECORDINGS_DIR = PROJECT_ROOT / "recordings"
PLOTS_DIR = PROJECT_ROOT / "plots"

DATABASE_PATH = DATABASE_DIR / "songs.db"


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    PROCESSING = "processing"
    MATCHED = "matched"
    NO_MATCH = "no_match"
    ERROR = "error"


class RecognitionService:

    def __init__(
        self,
        device: str = "plughw:2,0",
        channels: int = 1,
        sample_rate: int = 16000,
    ):
        self.device = device
        self.channels = channels
        self.sample_rate = sample_rate

        self.state = State.IDLE

        self.result = None
        self.error = None

        self._process = None
        self._segments: list[Path] = []

        self._lock = threading.RLock()

        RECORDINGS_DIR.mkdir(exist_ok=True)
        DATABASE_DIR.mkdir(exist_ok=True)
        PLOTS_DIR.mkdir(exist_ok=True)

    # -------------------------------------------------------
    # PUBLIC STATE
    # -------------------------------------------------------

    def get_state(self):
        with self._lock:
            return {
                "state": self.state.value,
                "result": self.result,
                "error": self.error,
            }

    # -------------------------------------------------------
    # RECORDING
    # -------------------------------------------------------

    def start_or_resume(self):

        with self._lock:

            if self.state == State.PROCESSING:
                raise RuntimeError(
                    "Recognition is currently processing."
                )

            if self.state in {
                State.IDLE,
                State.MATCHED,
                State.NO_MATCH,
                State.ERROR,
            }:
                self._clear_session()

            if self.state == State.RECORDING:
                return

            self._start_segment()

            self.state = State.RECORDING
            self.error = None

    def pause(self):

        with self._lock:

            if self.state != State.RECORDING:
                return

            self._stop_current_segment()

            self.state = State.PAUSED

    def cancel(self):

        with self._lock:

            if self._process is not None:
                self._stop_current_segment()

            self._clear_session()

            self.state = State.IDLE

    def submit(self):

        with self._lock:

            if self.state not in {
                State.RECORDING,
                State.PAUSED,
            }:
                raise RuntimeError(
                    "There is no recording to submit."
                )

            if self.state == State.RECORDING:
                self._stop_current_segment()

            if not self._segments:
                raise RuntimeError(
                    "No audio was recorded."
                )

            self.state = State.PROCESSING

        worker = threading.Thread(
            target=self._process_recording,
            daemon=True,
        )

        worker.start()

    # -------------------------------------------------------
    # INTERNAL RECORDING
    # -------------------------------------------------------

    def _start_segment(self):

        segment_number = len(self._segments)

        segment_path = (
            RECORDINGS_DIR
            / f"query_segment_{segment_number}.wav"
        )

        command = [
            "arecord",
            "-D",
            self.device,
            "-t",
            "wav",
            "-f",
            "S16_LE",
            "-r",
            str(self.sample_rate),
            "-c",
            str(self.channels),
            str(segment_path),
        ]

        print()
        print("[AUDIO] Starting recording")
        print(f"[AUDIO] Device:   {self.device}")
        print(f"[AUDIO] Channels: {self.channels}")
        print(f"[AUDIO] Rate:     {self.sample_rate}")
        print(f"[AUDIO] Output:   {segment_path}")
        print(
            "[AUDIO] Command:",
            " ".join(command),
        )

        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Give arecord a moment to initialize.
        time.sleep(0.3)

        # If the process already exited, recording failed.
        if self._process.poll() is not None:

            stderr = (
                self._process.stderr.read()
                if self._process.stderr
                else ""
            )

            self._process = None

            raise RuntimeError(
                "arecord failed to start:\n"
                + stderr.strip()
            )

        self._segments.append(
            segment_path
        )

        print(
            f"[AUDIO] Recording started "
            f"(PID {self._process.pid})"
        )

    def _stop_current_segment(self):

        if self._process is None:
            return

        print(
            f"[AUDIO] Stopping recording "
            f"(PID {self._process.pid})..."
        )

        if self._process.poll() is None:

            self._process.send_signal(
                signal.SIGINT
            )

            try:
                self._process.wait(
                    timeout=3
                )

            except subprocess.TimeoutExpired:

                print(
                    "[AUDIO] arecord did not stop "
                    "after SIGINT. Terminating..."
                )

                self._process.terminate()

                self._process.wait(
                    timeout=2
                )

        self._process = None

        if self._segments:

            latest = self._segments[-1]

            if latest.exists():

                size = latest.stat().st_size

                print(
                    f"[AUDIO] Recording saved: "
                    f"{latest}"
                )

                print(
                    f"[AUDIO] File size: "
                    f"{size / 1024:.1f} KB"
                )

            else:

                print(
                    "[AUDIO] WARNING: "
                    "recording file was not created!"
                )

    def _clear_session(self):

        self.result = None
        self.error = None

        for segment in self._segments:
            segment.unlink(missing_ok=True)

        self._segments.clear()

    # -------------------------------------------------------
    # AUDIO MERGING
    # -------------------------------------------------------

    def _merge_segments(self, output: Path):

        if len(self._segments) == 1:
            shutil.copyfile(
                self._segments[0],
                output,
            )
            return

        with wave.open(
            str(self._segments[0]),
            "rb",
        ) as first:

            parameters = first.getparams()

        with wave.open(
            str(output),
            "wb",
        ) as destination:

            destination.setparams(parameters)

            for segment in self._segments:

                with wave.open(
                    str(segment),
                    "rb",
                ) as source:

                    if (
                        source.getnchannels()
                        != parameters.nchannels
                        or source.getframerate()
                        != parameters.framerate
                        or source.getsampwidth()
                        != parameters.sampwidth
                    ):
                        raise RuntimeError(
                            "Recorded segments have incompatible formats."
                        )

                    destination.writeframes(
                        source.readframes(
                            source.getnframes()
                        )
                    )

    # -------------------------------------------------------
    # RECOGNITION PIPELINE
    # -------------------------------------------------------

    def _run(self, command):

        subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
        )

    def _process_recording(self):

        try:

            query_wav = (
                RECORDINGS_DIR / "query.wav"
            )

            spectrogram = (
                DATABASE_DIR /
                "query_spectrogram.npz"
            )

            peaks = (
                DATABASE_DIR /
                "query_peaks.npz"
            )

            fingerprints = (
                DATABASE_DIR /
                "query_fingerprints.npz"
            )

            self._merge_segments(query_wav)

            # Spectrogram

            self._run([
                sys.executable,
                str(
                    SRC_DIR /
                    "generate_spectrogram.py"
                ),
                str(query_wav),
                "--plot",
                str(
                    PLOTS_DIR /
                    "query_spectrogram.png"
                ),
                "--data",
                str(spectrogram),
            ])

            # Peaks

            self._run([
                sys.executable,
                str(
                    SRC_DIR /
                    "detect_peaks.py"
                ),
                str(spectrogram),
                "--plot",
                str(
                    PLOTS_DIR /
                    "query_landmarks.png"
                ),
                "--output",
                str(peaks),
            ])

            # Fingerprints

            self._run([
                sys.executable,
                str(
                    SRC_DIR /
                    "generate_fingerprints.py"
                ),
                str(peaks),
                "--output",
                str(fingerprints),
            ])

            result = self._match(
                fingerprints
            )

            with self._lock:

                if result is None:
                    self.state = State.NO_MATCH
                    self.result = None
                else:
                    self.state = State.MATCHED
                    self.result = result

        except Exception as exc:

            with self._lock:

                self.state = State.ERROR
                self.error = str(exc)

    # -------------------------------------------------------
    # MATCHER
    # -------------------------------------------------------

    def _match(self, fingerprint_path):

        hashes, query_times = (
            load_query_fingerprints(
                fingerprint_path
            )
        )

        votes, total_hits = lookup_matches(
            DATABASE_PATH,
            hashes,
            query_times,
        )

        if not votes:
            return None

        (
            best_song_id,
            best_offset,
        ), best_votes = votes.most_common(1)[0]

        song = get_song_info(
            DATABASE_PATH,
            best_song_id,
        )

        if song is None:
            return None

        title, artist = song

        confidence = (
            100.0
            * best_votes
            / max(total_hits, 1)
        )

        return {
            "song_id": best_song_id,
            "title": title,
            "artist": artist,
            "votes": best_votes,
            "offset": round(
                float(best_offset),
                1,
            ),
            "confidence": round(
                confidence,
                1,
            ),
        }

