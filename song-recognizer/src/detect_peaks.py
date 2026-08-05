#!/usr/bin/env python3

"""Detect spectral landmarks in a saved spectrogram."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

# Allows image generation on a headless Raspberry Pi.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import maximum_filter


DEFAULT_MINIMUM_FREQUENCY = 80.0
DEFAULT_MAXIMUM_FREQUENCY = 7_000.0
DEFAULT_MINIMUM_DB = -35.0

# Neighborhood radii measured in spectrogram bins.
DEFAULT_FREQUENCY_RADIUS = 15
DEFAULT_TIME_RADIUS = 9

# Prevents very dense noisy sections from dominating.
DEFAULT_MAX_PEAKS_PER_SECOND = 30


def load_spectrogram(
    input_path: Path,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    int,
    int,
    int,
    int,
]:
    """Load and validate spectrogram data from an NPZ file."""

    if not input_path.exists():
        raise FileNotFoundError(
            f"Spectrogram file not found: {input_path}"
        )

    required_keys = {
        "frequencies",
        "times",
        "spectrogram_db",
        "sample_rate",
        "window_size",
        "hop_size",
        "fft_size",
    }

    with np.load(input_path) as data:
        missing_keys = required_keys.difference(data.files)

        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ValueError(
                f"The NPZ file is missing these arrays: {missing}"
            )

        frequencies = data["frequencies"].astype(
            np.float32,
            copy=True,
        )
        times = data["times"].astype(
            np.float32,
            copy=True,
        )
        spectrogram_db = data["spectrogram_db"].astype(
            np.float32,
            copy=True,
        )

        sample_rate = int(data["sample_rate"])
        window_size = int(data["window_size"])
        hop_size = int(data["hop_size"])
        fft_size = int(data["fft_size"])

    if frequencies.ndim != 1:
        raise ValueError("The frequency array must be one-dimensional.")

    if times.ndim != 1:
        raise ValueError("The time array must be one-dimensional.")

    if spectrogram_db.ndim != 2:
        raise ValueError("The spectrogram must be two-dimensional.")

    expected_shape = (frequencies.size, times.size)

    if spectrogram_db.shape != expected_shape:
        raise ValueError(
            f"Spectrogram shape {spectrogram_db.shape} does not "
            f"match frequency/time dimensions {expected_shape}."
        )

    if not np.all(np.isfinite(spectrogram_db)):
        raise ValueError(
            "The spectrogram contains NaN or infinite values."
        )

    return (
        frequencies,
        times,
        spectrogram_db,
        sample_rate,
        window_size,
        hop_size,
        fft_size,
    )


def detect_local_maxima(
    spectrogram_db: np.ndarray,
    frequencies: np.ndarray,
    times: np.ndarray,
    minimum_frequency: float,
    maximum_frequency: float,
    minimum_db: float,
    frequency_radius: int,
    time_radius: int,
    max_peaks_per_second: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Detect strong local maxima in a spectrogram.

    Returns:
        frequency_bin_indices
        time_bin_indices
        peak_magnitudes_db
    """

    if frequency_radius < 1:
        raise ValueError("frequency_radius must be at least 1.")

    if time_radius < 1:
        raise ValueError("time_radius must be at least 1.")

    if maximum_frequency <= minimum_frequency:
        raise ValueError(
            "maximum_frequency must exceed minimum_frequency."
        )

    if max_peaks_per_second < 1:
        raise ValueError(
            "max_peaks_per_second must be at least 1."
        )

    frequency_mask = (
        (frequencies >= minimum_frequency)
        & (frequencies <= maximum_frequency)
    )

    if not np.any(frequency_mask):
        raise ValueError(
            "No spectrogram frequencies fall inside the requested "
            "frequency range."
        )

    # Values outside the desired frequency range can never become peaks.
    working_spectrogram = np.where(
        frequency_mask[:, np.newaxis],
        spectrogram_db,
        -np.inf,
    )

    neighborhood_size = (
        2 * frequency_radius + 1,
        2 * time_radius + 1,
    )

    neighborhood_maximum = maximum_filter(
        working_spectrogram,
        size=neighborhood_size,
        mode="constant",
        cval=-np.inf,
    )

    candidate_mask = (
        np.isfinite(working_spectrogram)
        & (working_spectrogram >= minimum_db)
        & (working_spectrogram == neighborhood_maximum)
    )

    candidate_indices = np.argwhere(candidate_mask)

    if candidate_indices.size == 0:
        return (
            np.empty(0, dtype=np.int32),
            np.empty(0, dtype=np.int32),
            np.empty(0, dtype=np.float32),
        )

    candidate_frequency_bins = candidate_indices[:, 0]
    candidate_time_bins = candidate_indices[:, 1]

    candidate_magnitudes = working_spectrogram[
        candidate_frequency_bins,
        candidate_time_bins,
    ]

    # Process strongest candidates first.
    strongest_first = np.argsort(candidate_magnitudes)[::-1]

    blocked = np.zeros(
        spectrogram_db.shape,
        dtype=bool,
    )

    selected_frequency_bins: list[int] = []
    selected_time_bins: list[int] = []
    selected_magnitudes: list[float] = []

    peaks_per_time_window: dict[int, int] = {}

    starting_time = float(times[0]) if times.size else 0.0

    for candidate_position in strongest_first:
        frequency_bin = int(
            candidate_frequency_bins[candidate_position]
        )
        time_bin = int(
            candidate_time_bins[candidate_position]
        )
        magnitude = float(
            candidate_magnitudes[candidate_position]
        )

        if blocked[frequency_bin, time_bin]:
            continue

        peak_time = float(times[time_bin])

        # Use one-second windows to keep peak density reasonably uniform.
        one_second_window = int(
            np.floor(peak_time - starting_time)
        )

        current_window_count = peaks_per_time_window.get(
            one_second_window,
            0,
        )

        if current_window_count >= max_peaks_per_second:
            continue

        selected_frequency_bins.append(frequency_bin)
        selected_time_bins.append(time_bin)
        selected_magnitudes.append(magnitude)

        peaks_per_time_window[one_second_window] = (
            current_window_count + 1
        )

        # Suppress candidates too close to the selected peak.
        frequency_start = max(
            0,
            frequency_bin - frequency_radius,
        )
        frequency_end = min(
            spectrogram_db.shape[0],
            frequency_bin + frequency_radius + 1,
        )

        time_start = max(
            0,
            time_bin - time_radius,
        )
        time_end = min(
            spectrogram_db.shape[1],
            time_bin + time_radius + 1,
        )

        blocked[
            frequency_start:frequency_end,
            time_start:time_end,
        ] = True

    frequency_bins_array = np.asarray(
        selected_frequency_bins,
        dtype=np.int32,
    )
    time_bins_array = np.asarray(
        selected_time_bins,
        dtype=np.int32,
    )
    magnitudes_array = np.asarray(
        selected_magnitudes,
        dtype=np.float32,
    )

    # Store landmarks in chronological order.
    chronological_order = np.lexsort(
        (
            frequency_bins_array,
            time_bins_array,
        )
    )

    return (
        frequency_bins_array[chronological_order],
        time_bins_array[chronological_order],
        magnitudes_array[chronological_order],
    )


def save_peaks(
    output_path: Path,
    frequency_bins: np.ndarray,
    time_bins: np.ndarray,
    magnitudes_db: np.ndarray,
    frequencies: np.ndarray,
    times: np.ndarray,
    source_spectrogram: Path,
    minimum_frequency: float,
    maximum_frequency: float,
    minimum_db: float,
    frequency_radius: int,
    time_radius: int,
    max_peaks_per_second: int,
) -> None:
    """Save detected landmarks for fingerprint generation."""

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.savez_compressed(
        output_path,
        frequency_bin_indices=frequency_bins,
        time_bin_indices=time_bins,
        frequencies_hz=frequencies[frequency_bins],
        times_seconds=times[time_bins],
        magnitudes_db=magnitudes_db,
        source_spectrogram=np.asarray(
            str(source_spectrogram)
        ),
        minimum_frequency=np.float32(minimum_frequency),
        maximum_frequency=np.float32(maximum_frequency),
        minimum_db=np.float32(minimum_db),
        frequency_radius=np.int32(frequency_radius),
        time_radius=np.int32(time_radius),
        max_peaks_per_second=np.int32(
            max_peaks_per_second
        ),
    )


def plot_constellation(
    output_path: Path,
    frequencies: np.ndarray,
    times: np.ndarray,
    spectrogram_db: np.ndarray,
    frequency_bins: np.ndarray,
    time_bins: np.ndarray,
    minimum_frequency: float,
    maximum_frequency: float,
    minimum_display_db: float = -80.0,
) -> None:
    """Plot the spectrogram with detected landmarks."""

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    figure, axis = plt.subplots(
        figsize=(12, 6)
    )

    image = axis.pcolormesh(
        times,
        frequencies,
        spectrogram_db,
        shading="auto",
        cmap="magma",
        vmin=minimum_display_db,
        vmax=0.0,
    )

    if frequency_bins.size:
        axis.scatter(
            times[time_bins],
            frequencies[frequency_bins],
            s=20,
            facecolors="none",
            edgecolors="cyan",
            linewidths=0.8,
            label=f"Landmarks ({frequency_bins.size})",
        )

        axis.legend(loc="upper right")

    axis.set_title(
        "Spectral landmark constellation"
    )
    axis.set_xlabel("Time [seconds]")
    axis.set_ylabel("Frequency [Hz]")
    axis.set_ylim(
        minimum_frequency,
        maximum_frequency,
    )

    colorbar = figure.colorbar(
        image,
        ax=axis,
    )
    colorbar.set_label(
        "Relative magnitude [dB]"
    )

    figure.tight_layout()
    figure.savefig(
        output_path,
        dpi=150,
    )
    plt.close(figure)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect local spectral peaks and create "
            "a time-frequency constellation map."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input spectrogram NPZ file.",
    )

    parser.add_argument(
        "--plot",
        type=Path,
        default=Path(
            "plots/query_landmarks.png"
        ),
        help="Output constellation-map PNG.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "database/query_peaks.npz"
        ),
        help="Output landmark NPZ file.",
    )

    parser.add_argument(
        "--minimum-frequency",
        type=float,
        default=DEFAULT_MINIMUM_FREQUENCY,
        help="Lowest frequency considered.",
    )

    parser.add_argument(
        "--maximum-frequency",
        type=float,
        default=DEFAULT_MAXIMUM_FREQUENCY,
        help="Highest frequency considered.",
    )

    parser.add_argument(
        "--minimum-db",
        type=float,
        default=DEFAULT_MINIMUM_DB,
        help=(
            "Minimum relative spectrogram magnitude "
            "required for a peak."
        ),
    )

    parser.add_argument(
        "--frequency-radius",
        type=int,
        default=DEFAULT_FREQUENCY_RADIUS,
        help=(
            "Local-maximum neighborhood radius "
            "along the frequency axis, in bins."
        ),
    )

    parser.add_argument(
        "--time-radius",
        type=int,
        default=DEFAULT_TIME_RADIUS,
        help=(
            "Local-maximum neighborhood radius "
            "along the time axis, in frames."
        ),
    )

    parser.add_argument(
        "--max-peaks-per-second",
        type=int,
        default=DEFAULT_MAX_PEAKS_PER_SECOND,
        help=(
            "Maximum number of accepted landmarks "
            "in each one-second interval."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    (
        frequencies,
        times,
        spectrogram_db,
        sample_rate,
        window_size,
        hop_size,
        fft_size,
    ) = load_spectrogram(args.input)

    available_maximum_frequency = float(
        frequencies[-1]
    )

    if args.maximum_frequency > available_maximum_frequency:
        print(
            "Maximum frequency reduced from "
            f"{args.maximum_frequency:.1f} Hz to "
            f"{available_maximum_frequency:.1f} Hz."
        )
        args.maximum_frequency = (
            available_maximum_frequency
        )

    (
        frequency_bins,
        time_bins,
        magnitudes_db,
    ) = detect_local_maxima(
        spectrogram_db=spectrogram_db,
        frequencies=frequencies,
        times=times,
        minimum_frequency=args.minimum_frequency,
        maximum_frequency=args.maximum_frequency,
        minimum_db=args.minimum_db,
        frequency_radius=args.frequency_radius,
        time_radius=args.time_radius,
        max_peaks_per_second=args.max_peaks_per_second,
    )

    if frequency_bins.size == 0:
        raise RuntimeError(
            "No landmarks were detected. Try lowering "
            "--minimum-db, for example from -35 to -45."
        )

    save_peaks(
        output_path=args.output,
        frequency_bins=frequency_bins,
        time_bins=time_bins,
        magnitudes_db=magnitudes_db,
        frequencies=frequencies,
        times=times,
        source_spectrogram=args.input,
        minimum_frequency=args.minimum_frequency,
        maximum_frequency=args.maximum_frequency,
        minimum_db=args.minimum_db,
        frequency_radius=args.frequency_radius,
        time_radius=args.time_radius,
        max_peaks_per_second=args.max_peaks_per_second,
    )

    plot_constellation(
        output_path=args.plot,
        frequencies=frequencies,
        times=times,
        spectrogram_db=spectrogram_db,
        frequency_bins=frequency_bins,
        time_bins=time_bins,
        minimum_frequency=args.minimum_frequency,
        maximum_frequency=args.maximum_frequency,
    )

    if times.size > 1:
        frame_spacing = float(
            np.median(np.diff(times))
        )
        duration = float(
            times[-1] - times[0] + frame_spacing
        )
    else:
        duration = 0.0

    peak_density = (
        frequency_bins.size / duration
        if duration > 0
        else 0.0
    )

    print("Spectrogram configuration:")
    print(f"  Sample rate:          {sample_rate} Hz")
    print(f"  Window size:          {window_size}")
    print(f"  Hop size:             {hop_size}")
    print(f"  FFT size:             {fft_size}")

    print()
    print("Landmark configuration:")
    print(
        f"  Frequency range:      "
        f"{args.minimum_frequency:.1f}–"
        f"{args.maximum_frequency:.1f} Hz"
    )
    print(f"  Minimum level:        {args.minimum_db:.1f} dB")
    print(
        f"  Neighborhood radius: "
        f"{args.frequency_radius} frequency bins, "
        f"{args.time_radius} time frames"
    )

    print()
    print("Detection result:")
    print(f"  Landmarks detected:   {frequency_bins.size}")
    print(f"  Recording duration:   {duration:.3f} seconds")
    print(f"  Landmark density:     {peak_density:.2f} peaks/s")
    print(f"  Strongest landmark:   {magnitudes_db.max():.2f} dB")
    print(f"  Weakest landmark:     {magnitudes_db.min():.2f} dB")
    print()
    print(f"  Constellation image:  {args.plot}")
    print(f"  Landmark data:        {args.output}")


if __name__ == "__main__":
    main()