"""Integration tests for the in-memory recognition pipeline."""

from __future__ import annotations

import unittest

import numpy as np

from tests.audio_test_utils import (
    SAMPLE_RATE,
    SONGS,
    add_background_noise,
    load_excerpt,
    make_unknown_audio_cases,
    recognize_samples,
    validate_fixtures,
)


class AudioPipelineTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        validate_fixtures()

    def test_every_song_is_recognized_from_a_clean_excerpt(self):

        for song in SONGS:
            with self.subTest(song=song.title):
                audio = load_excerpt(song, position=0.5)
                result = recognize_samples(audio)

                self.assertEqual(song.song_id, result.song_id)
                self.assertEqual(song.title, result.title)
                self.assertGreater(result.votes, 0)
                self.assertGreater(result.fingerprints, 0)

    def test_seeded_noise_is_repeatable(self):

        audio = load_excerpt(SONGS[0], position=0.5)

        first = add_background_noise(audio, seed=1234)
        second = add_background_noise(audio, seed=1234)
        different = add_background_noise(audio, seed=5678)

        np.testing.assert_array_equal(first, second)
        self.assertFalse(np.array_equal(first, different))

    def test_silence_is_rejected_before_matching(self):

        silence = np.zeros(
            8 * SAMPLE_RATE,
            dtype=np.float32,
        )

        with self.assertRaisesRegex(
            ValueError,
            "silent",
        ):
            recognize_samples(silence)

    @unittest.expectedFailure
    def test_unknown_noise_is_not_identified_as_a_song(self):
        """Documents RF07 until a match acceptance threshold is added."""

        noise = make_unknown_audio_cases()["white noise"]
        result = recognize_samples(noise)

        self.assertIsNone(result.song_id)


if __name__ == "__main__":
    unittest.main()
