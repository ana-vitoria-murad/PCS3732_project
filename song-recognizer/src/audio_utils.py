#!/usr/bin/env python3

"""Common audio loading and preprocessing functions."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


TARGET_SAMPLE_RATE = 16_000
EPSILON = 1e-12


def convert_samples_to_float(audio: np.ndarray) -> np.ndarray:
    """
    Convert PCM audio samples to float32.

    The returned samples are normally within approximately [-1.0, 1.0].
    """

    if audio.size == 0:
        raise ValueError("The audio file contains no samples.")

    if audio.dtype == np.uint8:
        # Unsigned 8-bit WAV uses 128 as its zero level.
        return (audio.astype(np.float32) - 128.0) / 128.0

    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)
        scale = float(max(abs(info.min), info.max))

        return audio.astype(np.float32) / scale

    if np.issubdtype(audio.dtype, np.floating):
        return audio.astype(np.float32)

    raise TypeError(f"Unsupported audio data type: {audio.dtype}")


def convert_to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert mono, stereo, or multichannel audio to one channel."""

    if audio.ndim == 1:
        return audio

    if audio.ndim == 2:
        return np.mean(audio, axis=1, dtype=np.float32)

    raise ValueError(
        f"Expected a one- or two-dimensional audio array, "
        f"but received shape {audio.shape}."
    )


def remove_invalid_samples(audio: np.ndarray) -> np.ndarray:
    """Replace NaN and infinite samples with zero."""

    return np.nan_to_num(
        audio,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    ).astype(np.float32)


def remove_dc_offset(audio: np.ndarray) -> np.ndarray:
    """
    Remove the average signal level.

    Ideally, a silent audio signal should be centered around zero.
    """

    if audio.size == 0:
        return audio

    return audio - np.mean(audio, dtype=np.float64)


def resample_audio(
    audio: np.ndarray,
    original_sample_rate: int,
    target_sample_rate: int,
) -> np.ndarray:
    """Resample an audio signal using polyphase filtering."""

    if original_sample_rate <= 0:
        raise ValueError("The original sample rate must be positive.")

    if target_sample_rate <= 0:
        raise ValueError("The target sample rate must be positive.")

    if original_sample_rate == target_sample_rate:
        return audio.astype(np.float32, copy=False)

    common_divisor = math.gcd(
        original_sample_rate,
        target_sample_rate,
    )

    up_factor = target_sample_rate // common_divisor
    down_factor = original_sample_rate // common_divisor

    resampled = resample_poly(
        audio,
        up=up_factor,
        down=down_factor,
    )

    return resampled.astype(np.float32)


def normalize_audio(
    audio: np.ndarray,
    target_peak: float = 0.98,
) -> np.ndarray:
    """Normalize the signal without changing its relative shape."""

    if not 0.0 < target_peak <= 1.0:
        raise ValueError("target_peak must be between 0 and 1.")

    if audio.size == 0:
        return audio

    peak = float(np.max(np.abs(audio)))

    if peak < EPSILON:
        return audio.astype(np.float32, copy=False)

    normalized = audio * (target_peak / peak)

    return normalized.astype(np.float32)


def load_and_preprocess_audio(
    input_path: Path,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
    normalize: bool = True,
) -> tuple[int, np.ndarray]:
    """
    Load a WAV file and apply the complete preprocessing pipeline.

    Returns:
        A tuple containing:
        - target sampling rate
        - mono float32 audio signal
    """

    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")

    original_sample_rate, original_audio = wavfile.read(input_path)

    print("Input audio:")
    print(f"  Path:                 {input_path}")
    print(f"  Original sample rate: {original_sample_rate} Hz")
    print(f"  Original shape:       {original_audio.shape}")
    print(f"  Original data type:   {original_audio.dtype}")

    audio = convert_samples_to_float(original_audio)
    audio = convert_to_mono(audio)
    audio = remove_invalid_samples(audio)
    audio = remove_dc_offset(audio)

    audio = resample_audio(
        audio=audio,
        original_sample_rate=original_sample_rate,
        target_sample_rate=target_sample_rate,
    )

    if normalize:
        audio = normalize_audio(audio)

    duration = audio.size / target_sample_rate
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = (
        float(np.sqrt(np.mean(np.square(audio))))
        if audio.size
        else 0.0
    )

    print()
    print("Processed audio:")
    print(f"  Sample rate:          {target_sample_rate} Hz")
    print(f"  Samples:              {audio.size}")
    print(f"  Duration:             {duration:.3f} seconds")
    print(f"  Peak amplitude:       {peak:.6f}")
    print(f"  RMS amplitude:        {rms:.6f}")
    print(f"  Output data type:     {audio.dtype}")

    return target_sample_rate, audio