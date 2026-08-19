"""Shared deterministic audio fixtures for recognition tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import wavfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DATABASE_PATH = PROJECT_ROOT / "database" / "songs.db"
REFERENCE_DIR = PROJECT_ROOT / "reference_songs"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from audio_utils import (  # noqa: E402
    convert_samples_to_float,
    convert_to_mono,
    normalize_audio,
    remove_dc_offset,
    remove_invalid_samples,
    resample_audio,
)
from detect_peaks import (  # noqa: E402
    DEFAULT_FREQUENCY_RADIUS,
    DEFAULT_MAXIMUM_FREQUENCY,
    DEFAULT_MAX_PEAKS_PER_SECOND,
    DEFAULT_MINIMUM_DB,
    DEFAULT_MINIMUM_FREQUENCY,
    DEFAULT_TIME_RADIUS,
    detect_local_maxima,
)
from generate_fingerprints import (  # noqa: E402
    DEFAULT_MAX_DELTA_TIME,
    DEFAULT_MAX_TARGETS,
    DEFAULT_MIN_DELTA_TIME,
    generate_fingerprints,
)
from generate_spectrogram import (  # noqa: E402
    DEFAULT_FFT_SIZE,
    DEFAULT_HOP_SIZE,
    DEFAULT_WINDOW_SIZE,
    compute_spectrogram,
)
from match_song import get_song_info, lookup_matches  # noqa: E402


SAMPLE_RATE = 16_000
CLIP_DURATION_SECONDS = 8.0
DEFAULT_POSITIONS = (0.2, 0.5, 0.8)


@dataclass(frozen=True)
class SongFixture:
    song_id: int
    title: str
    filename: str

    @property
    def path(self) -> Path:
        return REFERENCE_DIR / self.filename


@dataclass(frozen=True)
class MatchResult:
    song_id: int | None
    title: str | None
    votes: int
    offset: float | None
    landmarks: int
    fingerprints: int


SONGS = (
    SongFixture(
        1,
        "Espresso",
        "sabrina_carpenter_espresso.wav",
    ),
    SongFixture(
        2,
        "One True Love",
        "one_true_love.wav",
    ),
    SongFixture(
        3,
        "I'm a Believer",
        "smash_mouth_i_m_believer.wav",
    ),
    SongFixture(
        4,
        "I Can See You",
        "taylor_swift_i_can_see_you.wav",
    ),
    SongFixture(
        5,
        "I Think We're Alone Now",
        "tiffany_i_think_were_alone_now.wav",
    ),
    SongFixture(
        6,
        "Faint",
        "linkin_park_faint.wav",
    ),
    SongFixture(
        7,
        "Never gonna give you up",
        "rick_astley_never_gonna_give_you_up.wav",
    ),
    SongFixture(
        8,
        "Femininomenon",
        "chappell_roan_femininomenon.wav",
    ),
    SongFixture(
        9,
        "Miku",
        "hatsune_miku_miku.wav",
    ),
    SongFixture(
        10,
        "Alas",
        "karol_sevilla_alas.wav",
    ),
    SongFixture(
        11,
        "Claroscuro",
        "valentina_zenere_claroscuro.wav",
    ),
)


def validate_fixtures() -> None:
    """Ensure that fixture metadata agrees with the live database."""

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Recognition database not found: {DATABASE_PATH}"
        )

    for song in SONGS:
        if not song.path.exists():
            raise FileNotFoundError(
                f"Reference audio not found: {song.path}"
            )

        database_song = get_song_info(
            DATABASE_PATH,
            song.song_id,
        )

        if database_song is None:
            raise AssertionError(
                f"Song ID {song.song_id} is absent from the database."
            )

        database_title = database_song[0]

        if database_title != song.title:
            raise AssertionError(
                f"Song ID {song.song_id} is '{database_title}' in the "
                f"database, but the test expects '{song.title}'."
            )


def load_excerpt(
    song: SongFixture,
    position: float,
    duration_seconds: float = CLIP_DURATION_SECONDS,
) -> np.ndarray:
    """Load a hop-aligned mono excerpt from a reference WAV file."""

    if not 0.0 <= position <= 1.0:
        raise ValueError("position must be between 0 and 1.")

    original_rate, original_audio = wavfile.read(
        song.path,
        mmap=True,
    )

    requested_samples = int(
        round(duration_seconds * original_rate)
    )

    if original_audio.shape[0] < requested_samples:
        raise ValueError(
            f"{song.path.name} is shorter than {duration_seconds}s."
        )

    maximum_start = original_audio.shape[0] - requested_samples
    start_sample = int(maximum_start * position)

    # The reference database uses the same STFT hop. Alignment makes clean
    # digital excerpts repeatable while augmented variants still perturb it.
    start_sample -= start_sample % DEFAULT_HOP_SIZE
    end_sample = start_sample + requested_samples

    audio = np.array(
        original_audio[start_sample:end_sample],
        copy=True,
    )

    audio = convert_samples_to_float(audio)
    audio = convert_to_mono(audio)
    audio = remove_invalid_samples(audio)
    audio = remove_dc_offset(audio)
    audio = resample_audio(
        audio,
        original_sample_rate=original_rate,
        target_sample_rate=SAMPLE_RATE,
    )

    return normalize_audio(audio)


def add_background_noise(
    audio: np.ndarray,
    seed: int,
    signal_to_noise_db: float = 20.0,
) -> np.ndarray:
    """Add repeatable white noise at a requested signal-to-noise ratio."""

    generator = np.random.default_rng(seed)
    noise = generator.standard_normal(audio.size).astype(np.float32)

    signal_rms = float(np.sqrt(np.mean(np.square(audio))))
    noise_rms = float(np.sqrt(np.mean(np.square(noise))))

    target_noise_rms = signal_rms / (
        10.0 ** (signal_to_noise_db / 20.0)
    )

    noisy_audio = audio + noise * (
        target_noise_rms / max(noise_rms, 1e-12)
    )

    return normalize_audio(noisy_audio)


def add_echo(
    audio: np.ndarray,
    delay_seconds: float = 0.065,
    strength: float = 0.25,
) -> np.ndarray:
    """Add a small deterministic echo similar to room reflection."""

    delay_samples = int(round(delay_seconds * SAMPLE_RATE))

    echoed_audio = audio.astype(np.float32, copy=True)
    echoed_audio[delay_samples:] += (
        strength * audio[:-delay_samples]
    )

    return normalize_audio(echoed_audio)


def apply_condition(
    audio: np.ndarray,
    condition: str,
    seed: int,
) -> np.ndarray:
    """Apply one named deterministic test condition."""

    if condition == "clean":
        return audio.copy()

    if condition == "noise":
        return add_background_noise(audio, seed=seed)

    if condition == "echo":
        return add_echo(audio)

    raise ValueError(f"Unknown audio condition: {condition}")


def make_unknown_audio_cases() -> dict[str, np.ndarray]:
    """Create repeatable signals that do not represent registered songs."""

    sample_count = int(CLIP_DURATION_SECONDS * SAMPLE_RATE)
    sample_positions = np.arange(
        sample_count,
        dtype=np.float32,
    )
    generator = np.random.default_rng(2026)

    white_noise = generator.standard_normal(
        sample_count
    ).astype(np.float32)

    single_tone = np.sin(
        2.0 * np.pi * 440.0 * sample_positions / SAMPLE_RATE
    ).astype(np.float32)

    chord = sum(
        np.sin(
            2.0 * np.pi * frequency * sample_positions / SAMPLE_RATE
        )
        for frequency in (261.63, 329.63, 392.0)
    ).astype(np.float32)

    return {
        "white noise": normalize_audio(white_noise),
        "440 Hz tone": normalize_audio(single_tone),
        "synthetic chord": normalize_audio(chord),
    }


def recognize_samples(audio: np.ndarray) -> MatchResult:
    """Run the production recognition algorithm entirely in memory."""

    frequencies, times, spectrogram_db = compute_spectrogram(
        audio=audio,
        sample_rate=SAMPLE_RATE,
        window_size=DEFAULT_WINDOW_SIZE,
        hop_size=DEFAULT_HOP_SIZE,
        fft_size=DEFAULT_FFT_SIZE,
    )

    frequency_bins, time_bins, _ = detect_local_maxima(
        spectrogram_db=spectrogram_db,
        frequencies=frequencies,
        times=times,
        minimum_frequency=DEFAULT_MINIMUM_FREQUENCY,
        maximum_frequency=DEFAULT_MAXIMUM_FREQUENCY,
        minimum_db=DEFAULT_MINIMUM_DB,
        frequency_radius=DEFAULT_FREQUENCY_RADIUS,
        time_radius=DEFAULT_TIME_RADIUS,
        max_peaks_per_second=DEFAULT_MAX_PEAKS_PER_SECOND,
    )

    peak_times = times[time_bins]
    peak_frequencies = frequencies[frequency_bins]

    hashes, anchor_times = generate_fingerprints(
        times=peak_times,
        frequencies=peak_frequencies,
        min_delta_time=DEFAULT_MIN_DELTA_TIME,
        max_delta_time=DEFAULT_MAX_DELTA_TIME,
        max_targets=DEFAULT_MAX_TARGETS,
    )

    votes, _ = lookup_matches(
        DATABASE_PATH,
        hashes,
        anchor_times,
    )

    if not votes:
        return MatchResult(
            song_id=None,
            title=None,
            votes=0,
            offset=None,
            landmarks=int(frequency_bins.size),
            fingerprints=int(hashes.size),
        )

    (song_id, offset), vote_count = votes.most_common(1)[0]
    song = get_song_info(DATABASE_PATH, song_id)

    return MatchResult(
        song_id=int(song_id),
        title=song[0] if song else None,
        votes=int(vote_count),
        offset=float(offset),
        landmarks=int(frequency_bins.size),
        fingerprints=int(hashes.size),
    )
