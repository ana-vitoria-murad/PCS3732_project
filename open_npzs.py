import numpy as np

with np.load('./song-recognizer/database/query_fingerprints.npz') as data:
    print("Arrays in file:", data.files)

with np.load('./song-recognizer/database/query_peaks.npz') as data:
    print("Arrays in file:", data.files)

with np.load('./song-recognizer/database/query_spectogram.npz') as data:
    print("Arrays in file:", data.files)