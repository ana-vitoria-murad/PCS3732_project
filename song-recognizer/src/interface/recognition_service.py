from __future__ import annotations

import subprocess
import sys
import threading
from enum import Enum
from pathlib import Path

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

RECORDING_DURATION = 8


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    READY = "ready"
    PROCESSING = "processing"
    MATCHED = "matched"
    NO_MATCH = "no_match"
    ERROR = "error"


class RecognitionService:

    def __init__(
        self,
        device="default",
        channels=1,
        sample_rate=16000,
    ):

        self.device = device
        self.channels = channels
        self.sample_rate = sample_rate

        self.state = State.IDLE
        self.result = None
        self.error = None

        self._lock = threading.RLock()

        RECORDINGS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        DATABASE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        PLOTS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------
    # STATE
    # --------------------------------------------------

    def get_state(self):

        with self._lock:

            return {
                "state": self.state.value,
                "result": self.result,
                "error": self.error,
            }

    # --------------------------------------------------
    # RECORD
    # --------------------------------------------------

    def start_or_resume(self):

        with self._lock:

            if self.state in {
                State.RECORDING,
                State.PROCESSING,
            }:
                return

            self.result = None
            self.error = None

            self.state = State.RECORDING

        print()
        print("[AUDIO] Starting 8-second recording...")

        thread = threading.Thread(
            target=self._record,
            daemon=True,
        )

        thread.start()

    def _record(self):

        query_wav = (
            RECORDINGS_DIR / "query.wav"
        )

        try:

            query_wav.unlink(
                missing_ok=True
            )

            command = [
                sys.executable,
                str(SRC_DIR / "record.py"),
                "--device",
                self.device,
                "--duration",
                str(RECORDING_DURATION),
                "--sample-rate",
                str(self.sample_rate),
                "--channels",
                str(self.channels),
                "--output",
                str(query_wav),
            ]

            print(
                "[AUDIO] Command:",
                " ".join(command),
            )

            subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                check=True,
            )

            if not query_wav.exists():
                raise RuntimeError(
                    "Recording file was not created."
                )

            print()
            print("[AUDIO] Recording complete.")
            print(
                f"[AUDIO] File: {query_wav}"
            )

            print(
                f"[AUDIO] Size: "
                f"{query_wav.stat().st_size / 1024:.1f} KB"
            )

            with self._lock:
                self.state = State.READY

        except Exception as exc:

            print(
                "[AUDIO] Recording failed:",
                exc,
            )

            with self._lock:
                self.state = State.ERROR
                self.error = str(exc)

    # --------------------------------------------------
    # PAUSE
    # --------------------------------------------------

    def pause(self):

        print(
            "[AUDIO] Pause ignored: "
            "recording has a fixed duration of 8 seconds."
        )

    # --------------------------------------------------
    # CANCEL / RESET
    # --------------------------------------------------

    def cancel(self):

        with self._lock:

            if self.state == State.RECORDING:
                print(
                    "[AUDIO] Recording cannot be cancelled "
                    "during the fixed 8-second capture."
                )

                return

            self.result = None
            self.error = None
            self.state = State.IDLE

        print("[AUDIO] Session reset.")

    # --------------------------------------------------
    # SUBMIT
    # --------------------------------------------------

    def submit(self):

        with self._lock:

            if self.state != State.READY:

                print(
                    "[AUDIO] Cannot submit. "
                    "Wait for the 8-second recording to finish."
                )

                return

            self.state = State.PROCESSING

        print()
        print("[MATCH] Processing recording...")

        thread = threading.Thread(
            target=self._process_recording,
            daemon=True,
        )

        thread.start()

    # --------------------------------------------------
    # PROCESSING
    # --------------------------------------------------

    def _run(self, command):

        print()
        print(
            "[PIPELINE]",
            " ".join(command),
        )

        subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
        )

    def _process_recording(self):

        try:

            query_wav = (
                RECORDINGS_DIR /
                "query.wav"
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

                    self.state = (
                        State.NO_MATCH
                    )

                    self.result = None

                else:

                    self.state = (
                        State.MATCHED
                    )

                    self.result = result

        except Exception as exc:

            print(
                "[MATCH] Processing failed:",
                exc,
            )

            with self._lock:

                self.state = State.ERROR
                self.error = str(exc)

    # --------------------------------------------------
    # MATCHING
    # --------------------------------------------------

    def _match(
        self,
        fingerprint_path,
    ):

        hashes, query_times = (
            load_query_fingerprints(
                fingerprint_path
            )
        )

        votes, total_hits = (
            lookup_matches(
                DATABASE_PATH,
                hashes,
                query_times,
            )
        )

        if not votes:
            return None

        (
            best_song_id,
            best_offset,
        ), best_votes = (
            votes.most_common(1)[0]
        )

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