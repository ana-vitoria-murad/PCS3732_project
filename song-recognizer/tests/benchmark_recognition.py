#!/usr/bin/env python3

"""Run repeatable recognition cases against all registered songs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.audio_test_utils import (
    DEFAULT_POSITIONS,
    SONGS,
    apply_condition,
    load_excerpt,
    make_unknown_audio_cases,
    recognize_samples,
    validate_fixtures,
)


AVAILABLE_CONDITIONS = ("clean", "noise", "echo")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test multiple excerpts and deterministic audio conditions "
            "against the production fingerprint database."
        )
    )

    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=AVAILABLE_CONDITIONS,
        default=list(AVAILABLE_CONDITIONS),
        help="Audio conditions to test (default: all).",
    )
    parser.add_argument(
        "--positions",
        nargs="+",
        type=float,
        default=list(DEFAULT_POSITIONS),
        help=(
            "Relative positions from 0 to 1 used to select excerpts "
            "(default: 0.2 0.5 0.8)."
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optionally save detailed results as JSON.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every case instead of failures only.",
    )
    parser.add_argument(
        "--skip-unknown",
        action="store_true",
        help="Do not run synthetic unknown-audio rejection cases.",
    )
    parser.add_argument(
        "--strict-unknown",
        action="store_true",
        help=(
            "Return a failure status when synthetic unknown audio is "
            "incorrectly identified."
        ),
    )

    return parser.parse_args()


def run_benchmark(
    conditions: list[str],
    positions: list[float],
    verbose: bool,
) -> list[dict]:
    validate_fixtures()

    for position in positions:
        if not 0.0 <= position <= 1.0:
            raise ValueError(
                f"Position {position} is outside the range 0 to 1."
            )

    results = []

    print(
        f"Running {len(SONGS) * len(positions) * len(conditions)} "
        "recognition cases..."
    )

    for song in SONGS:
        for position_index, position in enumerate(positions):
            clean_audio = load_excerpt(song, position=position)

            for condition_index, condition in enumerate(conditions):
                seed = (
                    song.song_id * 10_000
                    + position_index * 100
                    + condition_index
                )
                audio = apply_condition(
                    clean_audio,
                    condition=condition,
                    seed=seed,
                )

                started = time.perf_counter()
                match = recognize_samples(audio)
                elapsed = time.perf_counter() - started
                passed = match.song_id == song.song_id

                case = {
                    "case_type": "registered",
                    "expected_song_id": song.song_id,
                    "expected_title": song.title,
                    "position": position,
                    "condition": condition,
                    "matched_song_id": match.song_id,
                    "matched_title": match.title,
                    "votes": match.votes,
                    "landmarks": match.landmarks,
                    "fingerprints": match.fingerprints,
                    "elapsed_seconds": round(elapsed, 4),
                    "passed": passed,
                }
                results.append(case)

                if verbose or not passed:
                    status = "PASS" if passed else "FAIL"
                    matched_title = match.title or "no match"
                    print(
                        f"[{status}] {song.title} | {condition} | "
                        f"position={position:.2f} | "
                        f"matched={matched_title} | "
                        f"votes={match.votes} | {elapsed:.3f}s"
                    )

    return results


def run_unknown_cases(verbose: bool) -> list[dict]:
    results = []

    for name, audio in make_unknown_audio_cases().items():
        started = time.perf_counter()
        match = recognize_samples(audio)
        elapsed = time.perf_counter() - started
        passed = match.song_id is None

        case = {
            "case_type": "unknown",
            "expected_title": None,
            "condition": name,
            "matched_song_id": match.song_id,
            "matched_title": match.title,
            "votes": match.votes,
            "landmarks": match.landmarks,
            "fingerprints": match.fingerprints,
            "elapsed_seconds": round(elapsed, 4),
            "passed": passed,
        }
        results.append(case)

        if verbose or not passed:
            status = "PASS" if passed else "KNOWN LIMITATION"
            matched_title = match.title or "no match"
            print(
                f"[{status}] unknown: {name} | "
                f"matched={matched_title} | "
                f"votes={match.votes} | {elapsed:.3f}s"
            )

    return results


def print_summary(
    registered_results: list[dict],
    unknown_results: list[dict],
) -> None:
    grouped = defaultdict(list)

    for result in registered_results:
        grouped[result["condition"]].append(result)

    print()
    print("Summary")
    print("-" * 62)
    print(
        f"{'Condition':<14} {'Correct':<12} "
        f"{'Average time':<14} {'Average votes':<14}"
    )
    print("-" * 62)

    for condition, cases in grouped.items():
        correct = sum(case["passed"] for case in cases)
        average_time = sum(
            case["elapsed_seconds"] for case in cases
        ) / len(cases)
        average_votes = sum(
            case["votes"] for case in cases
        ) / len(cases)

        print(
            f"{condition:<14} {f'{correct}/{len(cases)}':<12} "
            f"{f'{average_time:.3f}s':<14} "
            f"{average_votes:<14.1f}"
        )

    total_correct = sum(
        case["passed"] for case in registered_results
    )
    print("-" * 62)
    print(
        f"Registered songs: {total_correct}/"
        f"{len(registered_results)} correct"
    )

    if unknown_results:
        rejected = sum(case["passed"] for case in unknown_results)
        print(
            f"Unknown audio: {rejected}/{len(unknown_results)} rejected"
        )


def main() -> int:
    args = parse_arguments()

    registered_results = run_benchmark(
        conditions=args.conditions,
        positions=args.positions,
        verbose=args.verbose,
    )
    unknown_results = (
        []
        if args.skip_unknown
        else run_unknown_cases(verbose=args.verbose)
    )
    print_summary(registered_results, unknown_results)

    results = registered_results + unknown_results

    if args.json_output:
        args.json_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.json_output.write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Detailed JSON: {args.json_output}")

    registered_passed = all(
        result["passed"] for result in registered_results
    )
    unknown_passed = all(
        result["passed"] for result in unknown_results
    )

    if args.strict_unknown:
        return 0 if registered_passed and unknown_passed else 1

    return 0 if registered_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
