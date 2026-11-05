import json
import math
import multiprocessing
import os
import pickle
import resource
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.clean import clean
from src.match import OUTPUT_COLUMNS, coalesce_with_state

TARGET_BUCKET_ROWS = 150_000
MAX_DEFAULT_WORKERS = 4
MAX_BUCKET_BITS = 8
BATCH_ROWS = 500_000
STATE_DIR = '_state'
META_FILE = 'meta.json'
GOLDEN_RATIO = np.uint64(0x9E3779B97F4A7C15)


def bucket_ids(user_ids, bits):
    hashed = user_ids.astype(np.uint64) * GOLDEN_RATIO
    return (hashed >> np.uint64(64 - bits)).astype(np.int64)


def count_bits(total_rows, target_rows):
    wanted = max(1, math.ceil(total_rows / target_rows))
    return min(MAX_BUCKET_BITS, max(1, math.ceil(math.log2(wanted))))


def split_into_buckets(files, scratch, bits):
    schema = pq.ParquetFile(files[0]).schema_arrow
    writers = {}
    try:
        for file in files:
            for batch in pq.ParquetFile(file).iter_batches(batch_size=BATCH_ROWS):
                table = pa.Table.from_batches([batch]).select(schema.names).cast(schema)
                ids = bucket_ids(table.column('user_id').to_numpy(), bits)
                for bucket in np.unique(ids):
                    if bucket not in writers:
                        writers[bucket] = pq.ParquetWriter(scratch / f'bucket_{bucket:04d}.parquet', schema)
                    writers[bucket].write_table(table.filter(pa.array(ids == bucket)))
    finally:
        for writer in writers.values():
            writer.close()
    return schema


def output_schema(input_schema):
    url_name = 'company_linkedin_url' if 'company_linkedin_url' in input_schema.names else 'company_website'
    source = {'asof_ts': 'observed_ts', 'company_linkedin_url': url_name}
    fields = []
    for name in OUTPUT_COLUMNS:
        if name == 'position_id':
            fields.append(pa.field(name, pa.int64()))
        else:
            fields.append(pa.field(name, input_schema.field(source.get(name, name)).type))
    return pa.schema(fields)


def write_atomic(table, target):
    temporary = target.with_suffix('.tmp')
    pq.write_table(table, temporary)
    os.replace(temporary, target)


def state_files(state_dir, bucket):
    found = [(int(path.stem.rsplit('_r', 1)[1]), path) for path in state_dir.glob(f'state_{bucket:04d}_r*.pkl')]
    return sorted(found)


def load_state(state_dir, bucket, before_run):
    older = [item for item in state_files(state_dir, bucket) if item[0] < before_run]
    if not older:
        return {}
    with open(older[-1][1], 'rb') as handle:
        return pickle.load(handle)


def write_state(states, state_dir, bucket, run):
    target = state_dir / f'state_{bucket:04d}_r{run:04d}.pkl'
    temporary = target.with_suffix('.tmp')
    with open(temporary, 'wb') as handle:
        pickle.dump(states, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temporary, target)


def process_bucket(path, output_dir, out_schema, write_logs, run):
    df = pq.read_table(path).to_pandas()
    if df.empty:
        return 0, 0, 0, 0.0
    bucket = int(path.stem.split('_')[1])
    state_dir = output_dir / STATE_DIR
    states = load_state(state_dir, bucket, run)
    good, dropped_rows, dropped_snapshots = clean(df)
    output, matches, changes, late = coalesce_with_state(good, states)
    if len(late):
        dropped_snapshots = pd.concat([dropped_snapshots, late], ignore_index=True)
    name = path.stem.replace('bucket', 'part') + (f'_r{run:04d}' if run else '')
    if len(output):
        write_atomic(pa.Table.from_pandas(output, schema=out_schema, preserve_index=False),
                     output_dir / f'{name}.parquet')
    if write_logs:
        log_dir = output_dir / '_logs'
        log_dir.mkdir(exist_ok=True)
        logs = {'dropped_rows': dropped_rows, 'dropped_snapshots': dropped_snapshots,
                'match_log': matches, 'change_log': changes}
        for log_name, frame in logs.items():
            write_atomic(pa.Table.from_pandas(frame, preserve_index=False), log_dir / f'{log_name}_{name}.parquet')
    saving = time.time()
    write_state(states, state_dir, bucket, run)
    state_seconds = time.time() - saving
    return len(df), len(output), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024, state_seconds


def run_number(path):
    return int(path.stem.rsplit('_r', 1)[1].split('_')[0])


def prepare_output(output_dir):
    state_dir = output_dir / STATE_DIR
    meta_path = state_dir / META_FILE
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        run = meta['runs'] + 1
        for orphan in output_dir.glob('part_*_r*.parquet'):
            if run_number(orphan) >= run:
                orphan.unlink()
        for orphan in state_dir.glob('state_*_r*.pkl'):
            if run_number(orphan) >= run:
                orphan.unlink()
        return meta['bits'], run
    for stale in output_dir.glob('part_*.parquet'):
        stale.unlink()
    shutil.rmtree(output_dir / '_logs', ignore_errors=True)
    shutil.rmtree(state_dir, ignore_errors=True)
    state_dir.mkdir()
    return None, 0


def commit_run(output_dir, bits, run, buckets):
    state_dir = output_dir / STATE_DIR
    meta_path = state_dir / META_FILE
    temporary = meta_path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'bits': bits, 'runs': run}))
    os.replace(temporary, meta_path)
    for bucket_path in buckets:
        for number, old in state_files(state_dir, int(bucket_path.stem.split('_')[1]))[:-1]:
            old.unlink()


def main():
    input_dir = Path(os.environ.get('INPUT_DIR', '/input'))
    output_dir = Path(os.environ.get('OUTPUT_DIR', '/output'))
    workers = int(os.environ.get('WORKERS', min(MAX_DEFAULT_WORKERS, len(os.sched_getaffinity(0)))))
    target_rows = int(os.environ.get('TARGET_BUCKET_ROWS', TARGET_BUCKET_ROWS))
    write_logs = os.environ.get('WRITE_LOGS', '0') == '1'

    files = sorted(input_dir.rglob('*.parquet'))
    if not files:
        raise SystemExit(f'No parquet files found in {input_dir}')
    output_dir.mkdir(parents=True, exist_ok=True)
    bits, run = prepare_output(output_dir)

    started = time.time()
    total_rows = sum(pq.ParquetFile(file).metadata.num_rows for file in files)
    if bits is None:
        bits = count_bits(total_rows, target_rows)
    scratch = Path(tempfile.mkdtemp(prefix='buckets_', dir=os.environ.get('SCRATCH_DIR')))
    try:
        schema = split_into_buckets(files, scratch, bits)
        split_seconds = time.time() - started
        buckets = sorted(scratch.glob('bucket_*.parquet'), key=lambda p: p.stat().st_size, reverse=True)
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
            results = list(pool.map(process_bucket, buckets, repeat(output_dir),
                                    repeat(output_schema(schema)), repeat(write_logs), repeat(run)))
        commit_run(output_dir, bits, run, buckets)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    rows_in = sum(r[0] for r in results)
    rows_out = sum(r[1] for r in results)
    peak_mb = max(r[2] for r in results)
    state_seconds = sum(r[3] for r in results)
    mode = 'initial run' if run == 0 else f'daily update {run}'
    print(f'Mode: {mode} | Input rows: {rows_in:,} | Output rows: {rows_out:,} | Buckets: {1 << bits} | Workers: {workers}')
    print(f'Split seconds: {split_seconds:.1f} | Total seconds: {time.time() - started:.1f} | Peak worker memory: {peak_mb:,} MB | State writing: {state_seconds:.1f} s (all workers)')