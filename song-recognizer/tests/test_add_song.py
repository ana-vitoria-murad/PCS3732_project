"""Tests for adding and replacing database songs."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from add_song import insert_song  # noqa: E402


class AddSongTests(unittest.TestCase):

    def test_replace_preserves_song_id(self):

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            database = directory / "songs.db"
            first_fingerprints = directory / "first.npz"
            replacement_fingerprints = directory / "replacement.npz"

            np.savez_compressed(
                first_fingerprints,
                hashes=np.asarray(["first", "second"]),
                anchor_times=np.asarray([0.1, 0.2]),
            )
            np.savez_compressed(
                replacement_fingerprints,
                hashes=np.asarray(["replacement"]),
                anchor_times=np.asarray([0.3]),
            )

            original_id, _ = insert_song(
                database_path=database,
                title="Test Song",
                artist="Test Artist",
                album="Old Album",
                cover_file="old.jpg",
                fingerprints_path=first_fingerprints,
                replace=False,
            )
            replacement_id, fingerprint_count = insert_song(
                database_path=database,
                title="Test Song",
                artist="Test Artist",
                album="New Album",
                cover_file="new.jpg",
                fingerprints_path=replacement_fingerprints,
                replace=True,
            )

            self.assertEqual(original_id, replacement_id)
            self.assertEqual(1, fingerprint_count)

            with sqlite3.connect(database) as connection:
                song = connection.execute(
                    """
                    SELECT id, album, cover_file
                    FROM songs
                    """
                ).fetchone()
                fingerprints = connection.execute(
                    """
                    SELECT hash, song_id, offset
                    FROM fingerprints
                    """
                ).fetchall()

            self.assertEqual(
                (original_id, "New Album", "new.jpg"),
                song,
            )
            self.assertEqual(
                [("replacement", original_id, 0.3)],
                fingerprints,
            )


if __name__ == "__main__":
    unittest.main()
