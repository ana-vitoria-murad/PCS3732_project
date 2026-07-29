#!/usr/bin/env python3

"""Inspect a WAV recording and save its waveform plot."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile


def convert_to_float(audio: np.ndarray) -> np.ndarray:
    """Convert integer or floating-point audio to float32 in [-1, 1]."""

    if np.issubdtype(audio.dtype, np.integer):
        information = np.iinfo(audio.dtype)
        scale = max(abs(information.min), information.max)
        return audio.astype(np.float32) / float(scale)

    return audio.astype(np.float32)


def convert_to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert stereo or multichannel audio to mono."""

    if audio.ndim == 1:
        return audio

    return np.mean(audio, axis=1)


def inspect_audio(input_path: Path, plot_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")

    sample_rate, original_audio = wavfile.read(input_path)

    audio = convert_to_float(original_audio)
    mono_audio = convert_to_mono(audio)

    if mono_audio.size == 0:
        raise ValueError("The audio file contains no samples.")

    duration = mono_audio.size / sample_rate
    peak = float(np.max(np.abs(mono_audio)))
    rms = float(np.sqrt(np.mean(np.square(mono_audio))))

    clipping_threshold = 0.99
    clipping_percentage = (
        np.count_nonzero(np.abs(mono_audio) >= clipping_threshold)
        / mono_audio.size
        * 100
    )

    times = np.arange(mono_audio.size) / sample_rate

    print(f"File:                 {input_path}")
    print(f"Original data type:   {original_audio.dtype}")
    print(f"Original shape:       {original_audio.shape}")
    print(f"Sample rate:          {sample_rate} Hz")
    print(f"Duration:             {duration:.3f} seconds")
    print(f"Peak amplitude:       {peak:.4f}")
    print(f"RMS amplitude:        {rms:.4f}")
    print(f"Clipped samples:      {clipping_percentage:.4f}%")

    if rms < 0.005:
        print("Warning: the signal is extremely quiet.")

    if peak < 0.05:
        print("Warning: the microphone level may be too low.")

    if clipping_percentage > 0.1:
        print("Warning: the signal may be clipping. Reduce microphone gain.")

    plot_path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(11, 4))
    plt.plot(times, mono_audio, linewidth=0.5)
    plt.xlabel("Time [seconds]")
    plt.ylabel("Normalized amplitude")
    plt.title(f"Recorded waveform: {input_path.name}")
    plt.ylim(-1.05, 1.05)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()

    print(f"Waveform saved to:    {plot_path}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a recorded WAV file."
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input WAV file.",
    )

    parser.add_argument(
        "--plot",
        type=Path,
        default=Path("plots/waveform.png"),
        help="Output waveform image.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    inspect_audio(args.input, args.plot)


if __name__ == "__main__":
    main()