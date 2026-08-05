#!/usr/bin/env python3

"""Record audio, generate fingerprints and recognize the song."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DATABASE_DIR = PROJECT_ROOT / "database"
RECORDINGS_DIR = PROJECT_ROOT / "recordings"
PLOTS_DIR = PROJECT_ROOT / "plots"

DEFAULT_DATABASE = DATABASE_DIR / "songs.db"


def run_command(command: list[str]) -> None:
    """Execute a command and stop when it fails."""

    print()
    print("$", " ".join(command))
    subprocess.run(command, check=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record a song excerpt and identify it "
            "using the local database."
        )
    )

    parser.add_argument(
        "--device",
        default="plughw:2,0",
        help="ALSA device, such as default or plughw:2,0.",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=8,
        help="Recording duration in seconds.",
    )

    parser.add_argument(
        "--channels",
        type=int,
        choices=(1, 2),
        default=1,
        help="Microphone channel count.",
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="SQLite song database.",
    )

    parser.add_argument(
        "--input",
        type=Path,
        help=(
            "Use an existing WAV file instead of recording "
            "from the microphone."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    query_wav = RECORDINGS_DIR / "query.wav"
    spectrogram_path = DATABASE_DIR / "query_spectrogram.npz"
    peaks_path = DATABASE_DIR / "query_peaks.npz"
    fingerprints_path = DATABASE_DIR / "query_fingerprints.npz"

    if args.input is None:
        run_command(
            [
                sys.executable,
                str(SRC_DIR / "record.py"),
                "--device",
                args.device,
                "--duration",
                str(args.duration),
                "--sample-rate",
                "16000",
                "--channels",
                str(args.channels),
                "--output",
                str(query_wav),
            ]
        )
    else:
        query_wav = args.input.expanduser().resolve()

        if not query_wav.exists():
            raise FileNotFoundError(
                f"Input audio not found: {query_wav}"
            )

    run_command(
        [
            sys.executable,
            str(SRC_DIR / "generate_spectrogram.py"),
            str(query_wav),
            "--plot",
            str(PLOTS_DIR / "query_spectrogram.png"),
            "--data",
            str(spectrogram_path),
        ]
    )

    run_command(
        [
            sys.executable,
            str(SRC_DIR / "detect_peaks.py"),
            str(spectrogram_path),
            "--plot",
            str(PLOTS_DIR / "query_landmarks.png"),
            "--output",
            str(peaks_path),
        ]
    )

    run_command(
        [
            sys.executable,
            str(SRC_DIR / "generate_fingerprints.py"),
            str(peaks_path),
            "--output",
            str(fingerprints_path),
        ]
    )

    print()
    print("=" * 60)
    print("RECOGNITION RESULT")
    print("=" * 60)

    run_command(
        [
            sys.executable,
            str(SRC_DIR / "match_song.py"),
            str(fingerprints_path),
            "--database",
            str(args.database.expanduser().resolve()),
        ]
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(
            f"\nError: command failed with code {error.returncode}.",
            file=sys.stderr,
        )
        raise SystemExit(error.returncode)
    except Exception as error:
        print(f"\nError: {error}", file=sys.stderr)
        raise SystemExit(1)