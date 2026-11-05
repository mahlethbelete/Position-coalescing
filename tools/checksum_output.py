import glob
import sys

import pandas as pd

rows, total = 0, 0
for path in sorted(glob.glob(f'{sys.argv[1]}/part_*.parquet')):
    frame = pd.read_parquet(path)
    hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    total = (total + int(hashes.sum(dtype='uint64'))) % (1 << 64)
    rows += len(frame)
print('Rows:', f'{rows:,}', '| Checksum:', total)