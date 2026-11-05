import glob
import sys

import pandas as pd

NEW_TIERS = ['same start + same description', 'start missing + same description',
             'start edited + same description']
SAMPLE_PER_TIER = 4

out_dir = sys.argv[1]
counts = pd.Series(dtype='int64')
for path in sorted(glob.glob(f'{out_dir}/_logs/match_log_part_*.parquet')):
    counts = counts.add(pd.read_parquet(path, columns=['tier'])['tier'].value_counts(), fill_value=0)
print(counts.astype('int64').sort_values(ascending=False).to_string(), '\n')

logs = sorted(glob.glob(f'{out_dir}/_logs/match_log_part_*.parquet'))
best, best_hits = logs[0], -1
for path in logs[:40]:
    hits = pd.read_parquet(path, columns=['tier'])['tier'].isin(NEW_TIERS).sum()
    if hits > best_hits:
        best, best_hits = path, hits
    if hits >= SAMPLE_PER_TIER * len(NEW_TIERS):
        break
log = pd.read_parquet(best)
output = pd.read_parquet(best.replace('/_logs/match_log_part_', '/part_'))

for tier in NEW_TIERS:
    print('==', tier)
    for _, hit in log[log['tier'] == tier].head(SAMPLE_PER_TIER).iterrows():
        rows = output[(output['user_id'] == hit['user_id']) & (output['position_id'] == hit['position_id'])]
        rows = rows.sort_values('asof_ts')
        now = rows[rows['asof_ts'] == hit['observed_ts']]
        before = rows[rows['asof_ts'] < hit['observed_ts']].tail(1)
        view = pd.concat([before.assign(when='before'), now.assign(when='now')])
        view['desc'] = view['description'].fillna('').str[:30]
        print(view[['when', 'asof_ts', 'company_raw', 'title_raw', 'startdate', 'desc']].to_string(index=False), '\n')