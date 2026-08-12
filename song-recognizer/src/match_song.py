#!/usr/bin/env python3

import sqlite3
import argparse
import numpy as np
from collections import Counter


def load_query_fingerprints(path):

    with np.load(path) as data:

        return (
            data["hashes"],
            data["anchor_times"],
        )


def lookup_matches(
    db_path,
    hashes,
    query_times,
):

    conn = sqlite3.connect(db_path)

    cur = conn.cursor()

    votes = Counter()

    total_hits = 0

    for hash_value, query_time in zip(
        hashes,
        query_times,
    ):

        cur.execute(
            """
            SELECT song_id, offset
            FROM fingerprints
            WHERE hash = ?
            """,
            (str(hash_value),)
        )

        rows = cur.fetchall()

        total_hits += len(rows)

        for song_id, song_offset in rows:

            delta = round(
                song_offset - query_time,
                1
            )

            votes[
                (song_id, delta)
            ] += 1

    conn.close()

    return votes, total_hits


def get_song_info(
    db_path,
    song_id,
):

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            title,
            artist,
            album,
            cover_file
        FROM songs
        WHERE id = ?
        """,
        (song_id,)
    )

    result = cur.fetchone()

    conn.close()

    return result


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "query_fingerprints"
    )

    parser.add_argument(
        "--database",
        default="database/songs.db"
    )

    args = parser.parse_args()

    hashes, query_times = (
        load_query_fingerprints(
            args.query_fingerprints
        )
    )

    votes, total_hits = (
        lookup_matches(
            args.database,
            hashes,
            query_times,
        )
    )

    if not votes:

        print()
        print(
            "No matching fingerprints found."
        )
        print()

        return

    (
        best_song_id,
        best_offset
    ), best_vote_count = (
        votes.most_common(1)[0]
    )

    title, artist = get_song_info(
        args.database,
        best_song_id,
    )

    confidence = (
        100.0
        * best_vote_count
        / max(total_hits, 1)
    )

    print()
    print("MATCH FOUND")
    print()

    print(
        f"Song: {title}"
    )

    print(
        f"Artist: {artist}"
    )

    print(
        f"Votes: {best_vote_count}"
    )

    print(
        f"Offset: {best_offset:.1f} s"
    )

    print(
        f"Confidence: "
        f"{confidence:.1f}%"
    )

    print()


if __name__ == "__main__":
    main()
