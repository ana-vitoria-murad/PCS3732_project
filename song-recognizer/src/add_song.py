#!/usr/bin/env python3

"""Add a complete song to the local fingerprint database."""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
import shutil

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DATABASE_DIR = PROJECT_ROOT / "database"
REFERENCE_DIR = PROJECT_ROOT / "reference_songs"
PLOTS_DIR = PROJECT_ROOT / "plots"

DEFAULT_DATABASE = DATABASE_DIR / "songs.db"
COVERS_DIR = (
    PROJECT_ROOT
    / "src"
    / "interface"
    / "static"
    / "covers"
)


def slugify(text: str) -> str:
    """Convert a title into a safe filename."""

    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "song"


def run_command(command: list[str]) -> None:
    """Run a command and stop if it fails."""

    print()
    print("$", " ".join(command))
    subprocess.run(command, check=True)


def create_database_schema(connection: sqlite3.Connection) -> None:
    """Create the required database tables when they do not exist."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT,
            cover_file TEXT
        );

        CREATE TABLE IF NOT EXISTS fingerprints (
            hash TEXT NOT NULL,
            song_id INTEGER NOT NULL,
            offset REAL NOT NULL,
            FOREIGN KEY(song_id) REFERENCES songs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_fingerprint_hash
        ON fingerprints(hash);

        CREATE INDEX IF NOT EXISTS idx_fingerprint_song
        ON fingerprints(song_id);
        """
    )


def normalize_audio(
    source: Path,
    destination: Path,
) -> None:
    """Convert MP3, WAV or another ffmpeg-supported format to mono WAV."""

    destination.parent.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
    )


def generate_song_artifacts(
    wav_path: Path,
    slug: str,
) -> Path:
    """Generate spectrogram, peaks and fingerprints."""

    spectrogram_path = DATABASE_DIR / f"{slug}_spectrogram.npz"
    peaks_path = DATABASE_DIR / f"{slug}_peaks.npz"
    fingerprints_path = DATABASE_DIR / f"{slug}_fingerprints.npz"

    spectrogram_plot = PLOTS_DIR / f"{slug}_spectrogram.png"
    landmarks_plot = PLOTS_DIR / f"{slug}_landmarks.png"

    run_command(
        [
            sys.executable,
            str(SRC_DIR / "generate_spectrogram.py"),
            str(wav_path),
            "--plot",
            str(spectrogram_plot),
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
            str(landmarks_plot),
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

    return fingerprints_path


def insert_song(
    database_path: Path,
    title: str,
    artist: str,
    album: str | None,
    cover_file: str | None,
    fingerprints_path: Path,
    replace: bool,
):
    """Insert song metadata and fingerprints into SQLite."""

    with np.load(fingerprints_path) as data:
        hashes = data["hashes"]
        anchor_times = data["anchor_times"]

    if len(hashes) == 0:
        raise RuntimeError("No fingerprints were generated.")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        create_database_schema(connection)

        existing = connection.execute(
            """
            SELECT id
            FROM songs
            WHERE lower(title) = lower(?)
              AND lower(artist) = lower(?)
            """,
            (title, artist),
        ).fetchone()

        if existing is not None:
            existing_song_id = int(existing[0])

            if not replace:
                raise RuntimeError(
                    "This song is already in the database. "
                    "Use --replace to rebuild it."
                )

            connection.execute(
                "DELETE FROM fingerprints WHERE song_id = ?",
                (existing_song_id,),
            )

            connection.execute(
                """
                UPDATE songs
                SET title = ?,
                    artist = ?,
                    album = ?,
                    cover_file = ?
                WHERE id = ?
                """,
                (
                    title,
                    artist,
                    album,
                    cover_file,
                    existing_song_id,
                ),
            )

            song_id = existing_song_id

        else:
            cursor = connection.execute(
                """
                INSERT INTO songs(
                    title,
                    artist,
                    album,
                    cover_file
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    title,
                    artist,
                    album,
                    cover_file,
                ),
            )

            song_id = int(cursor.lastrowid)

        rows = [
            (
                str(hash_value),
                song_id,
                float(anchor_time),
            )
            for hash_value, anchor_time in zip(
                hashes,
                anchor_times,
            )
        ]

        connection.executemany(
            """
            INSERT INTO fingerprints(hash, song_id, offset)
            VALUES (?, ?, ?)
            """,
            rows,
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return song_id, len(rows)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process and add a complete song to the database."
    )

    parser.add_argument(
        "audio_file",
        type=Path,
        help="MP3, WAV or another audio file supported by ffmpeg.",
    )

    parser.add_argument(
        "--title",
        required=True,
        help="Song title.",
    )

    parser.add_argument(
        "--artist",
        required=True,
        help="Artist name.",
    )

    parser.add_argument(
        "--album",
        default=None,
        help="Album name.",
    )

    parser.add_argument(
        "--cover",
        type=Path,
        default=None,
        help="Local cover image file.",
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="SQLite database path.",
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the song if it is already registered.",
    )

    return parser.parse_args()

def save_cover(
    source: Path | None,
    slug: str,
) -> str | None:

    if source is None:
        return None

    source = source.expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"Cover image not found: {source}"
        )

    allowed_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }

    extension = source.suffix.lower()

    if extension not in allowed_extensions:
        raise ValueError(
            "Cover must be JPG, PNG or WEBP."
        )

    COVERS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"{slug}{extension}"
    )

    destination = (
        COVERS_DIR / filename
    )

    shutil.copy2(
        source,
        destination,
    )

    return filename


def main() -> None:
    args = parse_arguments()

    source_path = args.audio_file.expanduser().resolve()
    database_path = args.database.expanduser().resolve()

    if not source_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {source_path}"
        )

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    slug = slugify(f"{args.artist}_{args.title}")
    normalized_wav = REFERENCE_DIR / f"{slug}.wav"

    print("=" * 60)
    print("ADDING SONG")
    print("=" * 60)
    print(f"Title:    {args.title}")
    print(f"Artist:   {args.artist}")
    print(f"Source:   {source_path}")
    print(f"Database: {database_path}")

    normalize_audio(
        source=source_path,
        destination=normalized_wav,
    )

    fingerprints_path = generate_song_artifacts(
        wav_path=normalized_wav,
        slug=slug,
    )

    cover_file = save_cover(
        source=args.cover,
        slug=slug,
    )

    song_id, fingerprint_count = insert_song(
        database_path=database_path,
        title=args.title,
        artist=args.artist,
        album=args.album,
        cover_file=cover_file,
        fingerprints_path=fingerprints_path,
        replace=args.replace,
    )

    print()
    print("=" * 60)
    print("SONG ADDED SUCCESSFULLY")
    print("=" * 60)
    print(f"Song ID:      {song_id}")
    print(f"Title:        {args.title}")
    print(f"Artist:       {args.artist}")
    print(f"Fingerprints: {fingerprint_count}")
    print(f"Normalized:   {normalized_wav}")


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
