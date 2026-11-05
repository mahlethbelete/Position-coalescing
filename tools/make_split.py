import sys
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

source, share = sys.argv[1], float(sys.argv[2])
old_dir, new_dir = Path('split_old'), Path('split_new')
for folder in (old_dir, new_dir):
    folder.mkdir(exist_ok=True)
    for stale in folder.glob('*.parquet'):
        stale.unlink()

dataset = ds.dataset(source, format='parquet')
counts = pc.value_counts(dataset.to_table(columns=['observed_ts']).column('observed_ts')).to_pylist()
counts.sort(key=lambda item: item['values'])
total = sum(item['counts'] for item in counts)
newest, cutoff = 0, counts[-1]['values']
for item in reversed(counts):
    if newest + item['counts'] > share * total and newest > 0:
        break
    newest += item['counts']
    cutoff = item['values']

schema = dataset.schema
writers = {'old': pq.ParquetWriter(old_dir / 'part_0.parquet', schema),
           'new': pq.ParquetWriter(new_dir / 'part_0.parquet', schema)}
rows = {'old': 0, 'new': 0}
field = ds.field('observed_ts')
for name, rule in (('old', field < cutoff), ('new', field >= cutoff)):
    for batch in dataset.scanner(filter=rule, batch_size=500_000).to_batches():
        writers[name].write_batch(batch)
        rows[name] += batch.num_rows
for writer in writers.values():
    writer.close()
print('Cutoff:', cutoff, '| old rows:', f"{rows['old']:,}", '| new rows:', f"{rows['new']:,}")