import datetime as dt

import pandas as pd
import pyarrow.parquet as pq

from src.clean import clean
from src.match import OUTPUT_COLUMNS, coalesce
from src.pipeline import main
from tests.test_match import case_a_rows, case_b_rows, COLUMNS


def make_input(tmp_path):
    rows = []
    for user in range(1, 41):
        source = case_a_rows() if user % 2 else case_b_rows()
        for row in source:
            rows.append([row[0], user] + row[2:])
    df = pd.DataFrame(rows, columns=COLUMNS)
    input_dir = tmp_path / 'input'
    input_dir.mkdir()
    for part in range(3):
        df.iloc[part::3].to_parquet(input_dir / f'file_{part}.parquet', index=False)
    return df, input_dir


def test_pipeline_matches_the_in_memory_result(tmp_path, monkeypatch):
    df, input_dir = make_input(tmp_path)
    output_dir = tmp_path / 'output'
    monkeypatch.setenv('INPUT_DIR', str(input_dir))
    monkeypatch.setenv('OUTPUT_DIR', str(output_dir))
    monkeypatch.setenv('WORKERS', '2')
    monkeypatch.setenv('TARGET_BUCKET_ROWS', '20')
    main()

    parts = sorted(output_dir.glob('part_*.parquet'))
    assert len(parts) > 1
    result = pd.concat([pq.read_table(p).to_pandas() for p in parts], ignore_index=True)
    assert list(result.columns) == OUTPUT_COLUMNS
    assert not result.duplicated(['position_id', 'asof_ts']).any()

    good, _, _ = clean(df)
    expected = coalesce(good)[0]
    order = ['user_id', 'asof_ts', 'position_id']
    pd.testing.assert_frame_equal(
        result.sort_values(order).reset_index(drop=True),
        expected.sort_values(order).reset_index(drop=True),
        check_dtype=False)
    assert not (output_dir / '_logs').exists()


def test_logs_are_written_only_when_asked(tmp_path, monkeypatch):
    _, input_dir = make_input(tmp_path)
    output_dir = tmp_path / 'output'
    monkeypatch.setenv('INPUT_DIR', str(input_dir))
    monkeypatch.setenv('OUTPUT_DIR', str(output_dir))
    monkeypatch.setenv('WORKERS', '1')
    monkeypatch.setenv('WRITE_LOGS', '1')
    main()
    assert list((output_dir / '_logs').glob('match_log_*.parquet'))

def test_all_null_column_in_first_file_does_not_crash(tmp_path, monkeypatch):
    df, input_dir = make_input(tmp_path)
    for old in input_dir.glob('*.parquet'):
        old.unlink()
    df.iloc[:5].assign(enddate=None).to_parquet(input_dir / 'a_first.parquet', index=False)
    df.iloc[5:].to_parquet(input_dir / 'b_rest.parquet', index=False)
    output_dir = tmp_path / 'output'
    monkeypatch.setenv('INPUT_DIR', str(input_dir))
    monkeypatch.setenv('OUTPUT_DIR', str(output_dir))
    monkeypatch.setenv('WORKERS', '1')
    main()
    result = pd.concat([pq.read_table(p).to_pandas() for p in output_dir.glob('part_*.parquet')])
    assert result['enddate'].notna().any()