import sys

import pyarrow.compute as pc
import pyarrow.dataset as ds

dataset = ds.dataset(sys.argv[1], format='parquet')
total = dataset.count_rows()
print('Rows:', f'{total:,}')

for name in dataset.schema.names:
    column = dataset.to_table(columns=[name]).column(name)
    missing = column.null_count
    if str(column.type) in ('string', 'large_string'):
        trimmed = pc.utf8_trim_whitespace(column)
        missing += pc.sum(pc.equal(trimmed, '').fill_null(False)).as_py() or 0
    print(f'{name:24} missing: {missing / total:6.1%}')

users = dataset.to_table(columns=['user_id']).column('user_id').value_counts().to_pylist()
sizes = sorted(item['counts'] for item in users)
print('Users:', f'{len(sizes):,}')
for label, share in [('median', 0.5), ('p99', 0.99), ('p99.9', 0.999)]:
    print(f'Rows per user {label}:', sizes[int(len(sizes) * share)])
print('Rows per user max:', sizes[-1])
print('Users with over 1000 rows:', sum(size > 1000 for size in sizes))