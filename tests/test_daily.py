import datetime as dt
import random

import pandas as pd
import pyarrow.parquet as pq

from src.clean import clean
from src.match import coalesce
from src.pipeline import main
from tests.test_match import COLUMNS


def build_history(users=30, snapshots=6, seed=3):
    rng = random.Random(seed)
    rows = []
    for user in range(1, users + 1):
        jobs = [(f'Company {rng.randint(1, 4)}', f'Title {rng.randint(1, 5)}',
                 dt.date(2010 + rng.randint(0, 10), rng.randint(1, 9), 1),
                 f'Long description of the work done by user {user} on job {j} at this company')
                for j in range(3)]
        for step in range(snapshots):
            stamp = dt.date(2024, 1, 1) + dt.timedelta(days=30 * step)
            for order, (company, title, start, description) in enumerate(jobs):
                if rng.random() < 0.2:
                    continue
                title = title.upper() if rng.random() < 0.2 else title
                description = None if rng.random() < 0.1 else description
                start = None if rng.random() < 0.1 else start
                rows.append([stamp, user, company, None, title, None, description, start, None, order])
    return pd.DataFrame(rows, columns=COLUMNS)


def write_input(df, directory):
    directory.mkdir(exist_ok=True)
    for old in directory.glob('*.parquet'):
        old.unlink()
    for part in range(2):
        df.iloc[part::2].to_parquet(directory / f'file_{part}.parquet', index=False)


def run_main(monkeypatch, input_dir, output_dir, logs=False):
    monkeypatch.setenv('INPUT_DIR', str(input_dir))
    monkeypatch.setenv('OUTPUT_DIR', str(output_dir))
    monkeypatch.setenv('WORKERS', '2')
    monkeypatch.setenv('TARGET_BUCKET_ROWS', '60')
    monkeypatch.setenv('WRITE_LOGS', '1' if logs else '0')
    main()


def read_output(output_dir):
    parts = sorted(output_dir.glob('part_*.parquet'))
    return pd.concat([pq.read_table(p).to_pandas() for p in parts], ignore_index=True)


def split_history():
    full = build_history()
    cutoff = dt.date(2024, 1, 1) + dt.timedelta(days=30 * 4)
    first = full[full['observed_ts'] < cutoff]
    later = full[(full['observed_ts'] >= cutoff) & (full['user_id'] % 2 == 0)]
    return first, later, pd.concat([first, later], ignore_index=True)


def test_initial_run_plus_daily_update_equals_one_full_run(tmp_path, monkeypatch):
    first, later, combined = split_history()
    output_dir = tmp_path / 'output'
    write_input(first, tmp_path / 'day0')
    run_main(monkeypatch, tmp_path / 'day0', output_dir)
    write_input(later, tmp_path / 'day1')
    run_main(monkeypatch, tmp_path / 'day1', output_dir)

    result = read_output(output_dir)
    assert not result.duplicated(['position_id', 'asof_ts']).any()
    good, _, _ = clean(combined)
    expected = coalesce(good)[0]
    order = ['user_id', 'asof_ts', 'position_id']
    pd.testing.assert_frame_equal(
        result.sort_values(order).reset_index(drop=True),
        expected.sort_values(order).reset_index(drop=True),
        check_dtype=False)


def test_daily_update_only_rewrites_buckets_with_new_data(tmp_path, monkeypatch):
    first, later, _ = split_history()
    output_dir = tmp_path / 'output'
    write_input(first, tmp_path / 'day0')
    run_main(monkeypatch, tmp_path / 'day0', output_dir)
    few = later[later['user_id'] == 2]
    write_input(few, tmp_path / 'day1')
    run_main(monkeypatch, tmp_path / 'day1', output_dir)
    state_dir = output_dir / '_state'
    new_files = list(state_dir.glob('state_*_r0001.pkl'))
    all_files = list(state_dir.glob('state_*.pkl'))
    assert len(new_files) == 1
    assert len(all_files) > 1
    assert len(list(output_dir.glob('part_*_r0001.parquet'))) == 1


def test_running_the_same_input_again_adds_nothing(tmp_path, monkeypatch):
    first, later, _ = split_history()
    output_dir = tmp_path / 'output'
    write_input(first, tmp_path / 'day0')
    run_main(monkeypatch, tmp_path / 'day0', output_dir)
    before = read_output(output_dir)
    run_main(monkeypatch, tmp_path / 'day0', output_dir, logs=True)
    assert len(read_output(output_dir)) == len(before)
    late = pd.concat([pq.read_table(p).to_pandas()
                      for p in (output_dir / '_logs').glob('dropped_snapshots_*.parquet')])
    assert (late['reason'] == 'older than the last processed snapshot').all()
    assert len(late) > 0


def test_a_failed_daily_run_is_discarded_and_can_be_repeated(tmp_path, monkeypatch):
    first, later, combined = split_history()
    output_dir = tmp_path / 'output'
    write_input(first, tmp_path / 'day0')
    run_main(monkeypatch, tmp_path / 'day0', output_dir)
    orphan = output_dir / 'part_0000_r0001.parquet'
    orphan.write_bytes(b'left over from a crashed run')
    (output_dir / '_state' / 'state_0000_r0001.pkl').write_bytes(b'left over')
    write_input(later, tmp_path / 'day1')
    run_main(monkeypatch, tmp_path / 'day1', output_dir)
    result = read_output(output_dir)
    good, _, _ = clean(combined)
    assert len(result) == len(coalesce(good)[0])