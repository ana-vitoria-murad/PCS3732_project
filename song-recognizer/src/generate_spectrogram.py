#!/usr/bin/env python3

"""Generate and save a log-magnitude spectrogram from a WAV file."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import stft

from audio_utils import load_and_preprocess_audio


DEFAULT_SAMPLE_RATE = 16_000

DEFAULT_WINDOW_SIZE = 1_024

DEFAULT_HOP_SIZE = 256

DEFAULT_FFT_SIZE = 2_048

DEFAULT_MIN_DB = -80.0
EPSILON = 1e-12


def compute_spectrogram(
    audio: np.ndarray,
    sample_rate: int,
    window_size: int = DEFAULT_WINDOW_SIZE,
    hop_size: int = DEFAULT_HOP_SIZE,
    fft_size: int = DEFAULT_FFT_SIZE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute a normalized log-magnitude STFT spectrogram.

    Returns:
        frequencies:
            Frequency value of each spectrogram row.

        times:
            Time value of each spectrogram column.

        spectrogram_db:
            Magnitude in decibels, relative to the strongest bin.
            Its maximum value is 0 dB.
    """

    if audio.ndim != 1:
        raise ValueError("The STFT input must be a mono signal.")

    if audio.size < window_size:
        raise ValueError(
            f"The recording has only {audio.size} samples, "
            f"but the window size is {window_size}."
        )

    if hop_size <= 0:
        raise ValueError("The hop size must be positive.")

    if hop_size > window_size:
        raise ValueError(
            "The hop size cannot be larger than the window size."
        )

    if fft_size < window_size:
        raise ValueError(
            "The FFT size cannot be smaller than the window size."
        )

    overlap = window_size - hop_size

    frequencies, times, complex_spectrogram = stft(
        audio,
        fs=sample_rate,
        window="hann",
        nperseg=window_size,
        noverlap=overlap,
        nfft=fft_size,
        detrend=False,
        return_onesided=True,
        boundary=None,
        padded=False,
    )

    magnitude = np.abs(complex_spectrogram).astype(np.float32)

    maximum_magnitude = float(np.max(magnitude))

    if maximum_magnitude <= EPSILON:
        raise ValueError(
            "The recording appears to be silent; "
            "its spectrogram contains no measurable energy."
        )

    spectrogram_db = 20.0 * np.log10(
        np.maximum(magnitude, EPSILON)
    )

    spectrogram_db -= np.max(spectrogram_db)

    return (
        frequencies.astype(np.float32),
        times.astype(np.float32),
        spectrogram_db.astype(np.float32),
    )


def save_spectrogram_data(
    output_path: Path,
    frequencies: np.ndarray,
    times: np.ndarray,
    spectrogram_db: np.ndarray,
    sample_rate: int,
    window_size: int,
    hop_size: int,
    fft_size: int,
) -> None:
    """Save the spectrogram arrays for later peak detection."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(
        output_path,
        frequencies=frequencies,
        times=times,
        spectrogram_db=spectrogram_db,
        sample_rate=np.int32(sample_rate),
        window_size=np.int32(window_size),
        hop_size=np.int32(hop_size),
        fft_size=np.int32(fft_size),
    )


def plot_spectrogram(
    output_path: Path,
    frequencies: np.ndarray,
    times: np.ndarray,
    spectrogram_db: np.ndarray,
    title: str,
    maximum_frequency: float,
    minimum_db: float,
) -> None:
    """Save the spectrogram as a PNG image."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(12, 5))

    image = axis.pcolormesh(
        times,
        frequencies,
        spectrogram_db,
        shading="auto",
        cmap="magma",
        vmin=minimum_db,
        vmax=0.0,
    )

    axis.set_title(title)
    axis.set_xlabel("Time [seconds]")
    axis.set_ylabel("Frequency [Hz]")
    axis.set_ylim(0, maximum_frequency)

    colorbar = figure.colorbar(image, ax=axis)
    colorbar.set_label("Relative magnitude [dB]")

    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load a WAV file, preprocess it, and generate "
            "a log-magnitude spectrogram."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input WAV recording.",
    )

    parser.add_argument(
        "--plot",
        type=Path,
        default=Path("plots/spectrogram.png"),
        help="Output PNG plot.",
    )

    parser.add_argument(
        "--data",
        type=Path,
        default=Path("database/query_spectrogram.npz"),
        help="Output compressed NumPy spectrogram data.",
    )

    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help="Target audio sampling rate.",
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=DEFAULT_WINDOW_SIZE,
        help="Number of samples per STFT window.",
    )

    parser.add_argument(
        "--hop-size",
        type=int,
        default=DEFAULT_HOP_SIZE,
        help="Samples between consecutive STFT windows.",
    )

    parser.add_argument(
        "--fft-size",
        type=int,
        default=DEFAULT_FFT_SIZE,
        help="FFT size.",
    )

    parser.add_argument(
        "--maximum-frequency",
        type=float,
        default=8_000.0,
        help="Highest frequency displayed in the plot.",
    )

    parser.add_argument(
        "--minimum-db",
        type=float,
        default=DEFAULT_MIN_DB,
        help="Lowest decibel level displayed in the plot.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    if args.sample_rate <= 0:
        raise ValueError("--sample-rate must be positive.")

    if args.maximum_frequency <= 0:
        raise ValueError("--maximum-frequency must be positive.")

    maximum_allowed_frequency = args.sample_rate / 2.0

    if args.maximum_frequency > maximum_allowed_frequency:
        print(
            f"Maximum plot frequency reduced from "
            f"{args.maximum_frequency:.1f} Hz to "
            f"{maximum_allowed_frequency:.1f} Hz."
        )

        args.maximum_frequency = maximum_allowed_frequency

    sample_rate, audio = load_and_preprocess_audio(
        input_path=args.input,
        target_sample_rate=args.sample_rate,
        normalize=True,
    )

    frequencies, times, spectrogram_db = compute_spectrogram(
        audio=audio,
        sample_rate=sample_rate,
        window_size=args.window_size,
        hop_size=args.hop_size,
        fft_size=args.fft_size,
    )

    save_spectrogram_data(
        output_path=args.data,
        frequencies=frequencies,
        times=times,
        spectrogram_db=spectrogram_db,
        sample_rate=sample_rate,
        window_size=args.window_size,
        hop_size=args.hop_size,
        fft_size=args.fft_size,
    )

    plot_spectrogram(
        output_path=args.plot,
        frequencies=frequencies,
        times=times,
        spectrogram_db=spectrogram_db,
        title=f"Spectrogram: {args.input.name}",
        maximum_frequency=args.maximum_frequency,
        minimum_db=args.minimum_db,
    )

    frequency_spacing = (
        frequencies[1] - frequencies[0]
        if frequencies.size > 1
        else 0.0
    )

    time_spacing = (
        times[1] - times[0]
        if times.size > 1
        else 0.0
    )

    print()
    print("Spectrogram:")
    print(f"  Frequency bins:       {frequencies.size}")
    print(f"  Time frames:          {times.size}")
    print(f"  Matrix shape:         {spectrogram_db.shape}")
    print(f"  Frequency spacing:    {frequency_spacing:.3f} Hz")
    print(f"  Time spacing:         {time_spacing:.6f} seconds")
    print(f"  Minimum magnitude:    {spectrogram_db.min():.2f} dB")
    print(f"  Maximum magnitude:    {spectrogram_db.max():.2f} dB")
    print()
    print(f"Spectrogram image:      {args.plot}")
    print(f"Spectrogram data:       {args.data}")


if __name__ == "__main__":
    main()