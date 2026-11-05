import cProfile
import pstats
import sys

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

from src.clean import clean
from src.match import coalesce_with_state
from src.pipeline import bucket_ids

BITS = 7
BUCKET = 0
TOP = 25


def load_bucket(input_dir):
    pieces = []
    for file in sorted(Path(input_dir).rglob('*.parquet')):
        for batch in pq.ParquetFile(file).iter_batches(batch_size=500_000):
            table = pa.Table.from_batches([batch])
            ids = bucket_ids(table.column('user_id').to_numpy(), BITS)
            pieces.append(table.filter(pa.array(ids == BUCKET)))
    return pa.concat_tables(pieces).to_pandas()


def main():
    df = load_bucket(sys.argv[1])
    print(f'Rows in bucket {BUCKET}: {len(df):,}')
    profiler = cProfile.Profile()
    profiler.enable()
    good, _, _ = clean(df)
    coalesce_with_state(good, {})
    profiler.disable()
    stats = pstats.Stats(profiler).sort_stats('tottime')
    stats.print_stats(TOP)


if __name__ == '__main__':
    main()