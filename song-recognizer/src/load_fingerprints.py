import sqlite3
import numpy as np
import sys

song_id = int(sys.argv[1])
npz_file = sys.argv[2]

conn = sqlite3.connect(
    "database/songs.db"
)

cur = conn.cursor()

with np.load(npz_file) as data:

    hashes = data["hashes"]
    offsets = data["anchor_times"]

    rows = [
        (
            str(h),
            song_id,
            float(t)
        )
        for h, t in zip(
            hashes,
            offsets
        )
    ]

cur.executemany(
    """
    INSERT INTO fingerprints
    (hash, song_id, offset)
    VALUES (?, ?, ?)
    """,
    rows
)

conn.commit()

print(
    f"Inserted {len(rows)} fingerprints"
)

conn.close()
