import glob
import sys

import pandas as pd

out_dir, user_id = sys.argv[1], int(sys.argv[2])
filters = [('user_id', '==', user_id)]
output = pd.concat([pd.read_parquet(p, filters=filters) for p in sorted(glob.glob(f'{out_dir}/part_*.parquet'))])
log = pd.concat([pd.read_parquet(p, filters=filters) for p in sorted(glob.glob(f'{out_dir}/_logs/match_log_part_*.parquet'))])
log = log[log['position_id'].notna()].astype({'position_id': 'int64'})

rows = log.merge(output, left_on=['user_id', 'observed_ts', 'position_id'],
                 right_on=['user_id', 'asof_ts', 'position_id'], how='left')
rows['id'] = rows['position_id'].astype(str).str[-4:]
rows['company'] = rows['company_raw'].fillna('').str[:24]
rows['title'] = rows['title_raw'].fillna('').str[:30]
rows['desc'] = rows['description'].fillna('').str[:12]
view = rows.sort_values(['observed_ts', 'id'])[
    ['observed_ts', 'id', 'company', 'title', 'startdate', 'desc', 'tier', 'ambiguous_candidates']]
print(view.to_string(index=False))