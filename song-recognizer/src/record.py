#!/usr/bin/env python3

"""Record a WAV file using ALSA's arecord command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_DURATION = 8
DEFAULT_CHANNELS = 1
DEFAULT_DEVICE = "default"


def record_audio(
    output_path: Path,
    device: str,
    duration: int,
    sample_rate: int,
    channels: int,
) -> None:
    """Record PCM audio to a WAV file."""

    if duration <= 0:
        raise ValueError("Duration must be greater than zero.")

    if sample_rate <= 0:
        raise ValueError("Sample rate must be greater than zero.")

    if channels not in (1, 2):
        raise ValueError("Channels must be either 1 or 2.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "arecord",
        "-q",
        "-D",
        device,
        "-t",
        "wav",
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        str(channels),
        "-d",
        str(duration),
        str(output_path),
    ]

    print("Recording configuration:")
    print(f"  Device:      {device}")
    print(f"  Duration:    {duration} seconds")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Channels:    {channels}")
    print(f"  Output:      {output_path}")
    print()
    print("Recording...")

    try:
        subprocess.run(
            command,
            check=True,
            timeout=duration + 10,
        )
    except FileNotFoundError:
        print(
            "Error: arecord was not found. Install it with "
            "'sudo apt install alsa-utils'.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except subprocess.TimeoutExpired:
        print("Error: audio recording timed out.", file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        print(
            f"Error: arecord failed with exit code {error.returncode}.",
            file=sys.stderr,
        )
        print(
            "Check the device with 'arecord -l' and verify the "
            "--device argument.",
            file=sys.stderr,
        )
        raise SystemExit(error.returncode)

    if not output_path.exists() or output_path.stat().st_size <= 44:
        print("Error: no valid WAV file was created.", file=sys.stderr)
        raise SystemExit(1)

    size_kb = output_path.stat().st_size / 1024

    print("Recording complete.")
    print(f"File size: {size_kb:.1f} KB")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a WAV excerpt for song recognition."
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("recordings/query.wav"),
        help="Output WAV file.",
    )

    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help="ALSA capture device, such as default or plughw:1,0.",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help="Recording duration in seconds.",
    )

    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help="Sampling rate in Hz.",
    )

    parser.add_argument(
        "--channels",
        type=int,
        default=DEFAULT_CHANNELS,
        choices=(1, 2),
        help="Number of input channels.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    record_audio(
        output_path=args.output,
        device=args.device,
        duration=args.duration,
        sample_rate=args.sample_rate,
        channels=args.channels,
    )


if __name__ == "__main__":
    main()