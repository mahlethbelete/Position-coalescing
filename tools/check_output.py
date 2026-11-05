import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

output_dir, input_dir = Path(sys.argv[1]), Path(sys.argv[2])

tables = [pq.read_table(f, columns=['user_id', 'observed_ts']) for f in sorted(input_dir.rglob('*.parquet'))]
input_snapshots = pa.concat_tables(tables).group_by(['user_id', 'observed_ts']).aggregate([]).num_rows
del tables

rows = positions = snapshots = duplicates = 0
for part in sorted(output_dir.glob('part_*.parquet')):
    frame = pq.read_table(part).to_pandas()
    rows += len(frame)
    positions += frame['position_id'].nunique()
    snapshots += len(frame[['user_id', 'asof_ts']].drop_duplicates())
    duplicates += int(frame.duplicated(['position_id', 'asof_ts']).sum())

print('Input snapshots:', f'{input_snapshots:,}')
print('Output snapshots:', f'{snapshots:,}', '| not in output:', f'{input_snapshots - snapshots:,}')
print('Output rows:', f'{rows:,}', '| Positions:', f'{positions:,}')
print('Duplicate (position_id, asof_ts) keys:', duplicates)