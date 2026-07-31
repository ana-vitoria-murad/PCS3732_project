#!/usr/bin/env python3

from pathlib import Path
import argparse
import hashlib
import numpy as np


DEFAULT_MIN_DELTA_TIME = 0.1
DEFAULT_MAX_DELTA_TIME = 2.0
DEFAULT_MAX_TARGETS = 5


def load_peaks(path: Path):

    with np.load(path) as data:

        return (
            data["times_seconds"],
            data["frequencies_hz"],
        )


def create_hash(
    anchor_freq,
    target_freq,
    delta_time,
):
    """
    Create a compact fingerprint hash.
    """

    delta_ms = int(round(delta_time * 1000))

    key = (
        f"{int(anchor_freq)}|"
        f"{int(target_freq)}|"
        f"{delta_ms}"
    )

    digest = hashlib.sha1(
        key.encode()
    ).hexdigest()

    return digest[:20]


def generate_fingerprints(
    times,
    frequencies,
    min_delta_time,
    max_delta_time,
    max_targets,
):

    hashes = []
    anchor_times = []

    total_peaks = len(times)

    for anchor_index in range(total_peaks):

        anchor_time = times[anchor_index]
        anchor_freq = frequencies[anchor_index]

        targets_added = 0

        for target_index in range(
            anchor_index + 1,
            total_peaks,
        ):

            target_time = times[target_index]

            delta_time = (
                target_time - anchor_time
            )

            if delta_time < min_delta_time:
                continue

            if delta_time > max_delta_time:
                break

            target_freq = frequencies[target_index]

            fingerprint_hash = create_hash(
                anchor_freq,
                target_freq,
                delta_time,
            )

            hashes.append(fingerprint_hash)
            anchor_times.append(anchor_time)

            targets_added += 1

            if targets_added >= max_targets:
                break

    return (
        np.asarray(hashes),
        np.asarray(anchor_times),
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "input",
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "database/query_fingerprints.npz"
        ),
    )

    parser.add_argument(
        "--min-delta-time",
        type=float,
        default=DEFAULT_MIN_DELTA_TIME,
    )

    parser.add_argument(
        "--max-delta-time",
        type=float,
        default=DEFAULT_MAX_DELTA_TIME,
    )

    parser.add_argument(
        "--max-targets",
        type=int,
        default=DEFAULT_MAX_TARGETS,
    )

    args = parser.parse_args()

    times, frequencies = load_peaks(
        args.input
    )

    hashes, anchor_times = (
        generate_fingerprints(
            times,
            frequencies,
            args.min_delta_time,
            args.max_delta_time,
            args.max_targets,
        )
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.savez_compressed(
        args.output,
        hashes=hashes,
        anchor_times=anchor_times,
    )

    print()
    print(
        f"Landmarks: {len(times)}"
    )
    print(
        f"Fingerprints: {len(hashes)}"
    )
    print()

    print("First 10 fingerprints:")

    for h, t in zip(
        hashes[:10],
        anchor_times[:10],
    ):
        print(
            f"{t:8.3f}s  {h}"
        )

    print()
    print(
        f"Saved: {args.output}"
    )


if __name__ == "__main__":
    main()
