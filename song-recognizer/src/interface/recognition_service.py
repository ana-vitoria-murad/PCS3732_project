from __future__ import annotations

import os
import signal
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


class ExecutionCancelled(Exception):
    """Raised internally when the current recognition run is cancelled."""


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
        self._run_id = 0
        self._active_process = None

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

            self._run_id += 1
            run_id = self._run_id
            self.state = State.RECORDING

        print()
        print("[AUDIO] Starting 8-second recording...")

        thread = threading.Thread(
            target=self._record,
            args=(run_id,),
            daemon=True,
        )

        thread.start()

    def _record(self, run_id):

        query_wav = (
            RECORDINGS_DIR / "query.wav"
        )

        try:

            with self._lock:

                self._ensure_current(run_id)

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

            self._run(
                command,
                run_id,
            )

            self._ensure_current(run_id)

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
                self._ensure_current(run_id)
                self.state = State.READY

        except ExecutionCancelled:

            print("[AUDIO] Recording cancelled.")

        except Exception as exc:

            print(
                "[AUDIO] Recording failed:",
                exc,
            )

            with self._lock:

                if run_id != self._run_id:
                    return

                self.state = State.ERROR
                self.error = str(exc)

    # --------------------------------------------------
    # CANCEL / RESET
    # --------------------------------------------------

    def cancel(self):

        with self._lock:

            self._run_id += 1
            self.result = None
            self.error = None
            self.state = State.IDLE

            process = self._active_process

            if process is not None:
                self._stop_process(process)

        print("[AUDIO] Execution interrupted and session reset.")

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
            run_id = self._run_id

        print()
        print("[MATCH] Processing recording...")

        thread = threading.Thread(
            target=self._process_recording,
            args=(run_id,),
            daemon=True,
        )

        thread.start()

    # --------------------------------------------------
    # PROCESSING
    # --------------------------------------------------

    def _ensure_current(self, run_id):

        with self._lock:

            if run_id != self._run_id:
                raise ExecutionCancelled

    def _is_cancelled(self, run_id):

        with self._lock:
            return run_id != self._run_id

    @staticmethod
    def _stop_process(process):

        if process.poll() is not None:
            return

        try:
            os.killpg(
                os.getpgid(process.pid),
                signal.SIGTERM,
            )
        except ProcessLookupError:
            return

        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(
                    os.getpgid(process.pid),
                    signal.SIGKILL,
                )
            except ProcessLookupError:
                pass

    def _run(self, command, run_id):

        print()
        print(
            "[PIPELINE]",
            " ".join(command),
        )

        with self._lock:

            self._ensure_current(run_id)

            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                start_new_session=True,
            )

            self._active_process = process

        try:
            return_code = process.wait()
        finally:
            with self._lock:

                if self._active_process is process:
                    self._active_process = None

        self._ensure_current(run_id)

        if return_code:
            raise subprocess.CalledProcessError(
                return_code,
                command,
            )

    def _process_recording(self, run_id):

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
            ], run_id)

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
            ], run_id)

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
            ], run_id)

            result = self._match(
                fingerprints,
                run_id,
            )

            with self._lock:

                self._ensure_current(run_id)

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

        except ExecutionCancelled:

            print("[MATCH] Processing cancelled.")

        except Exception as exc:

            print(
                "[MATCH] Processing failed:",
                exc,
            )

            with self._lock:

                if run_id != self._run_id:
                    return

                self.state = State.ERROR
                self.error = str(exc)

    # --------------------------------------------------
    # MATCHING
    # --------------------------------------------------

    def _match(
        self,
        fingerprint_path,
        run_id,
    ):

        hashes, query_times = (
            load_query_fingerprints(
                fingerprint_path
            )
        )

        self._ensure_current(run_id)

        votes, _ = (
            lookup_matches(
                DATABASE_PATH,
                hashes,
                query_times,
                should_cancel=lambda: self._is_cancelled(
                    run_id
                ),
            )
        )

        self._ensure_current(run_id)

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

        self._ensure_current(run_id)

        if song is None:
            return None

        title, artist, album, cover_file = song

        return {
            "song_id": best_song_id,
            "title": title,
            "artist": artist,
            "album": album,
            "cover_file": cover_file,
            "votes": best_votes,
            "offset": round(
                float(best_offset),
                1,
            ),
        }
