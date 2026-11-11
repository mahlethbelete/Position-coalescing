import sys
from pathlib import Path
import pandas as pd

files = sorted(Path(sys.argv[1]).rglob('*.parquet'))
cols = ['observed_ts', 'user_id', 'company_raw', 'title_raw', 'startdate', 'enddate', 'order_in_profile']
parts = []
for f in files:
    df = pd.read_parquet(f, columns=cols)
    obs = pd.to_datetime(df['observed_ts'], errors='coerce')
    start = pd.to_datetime(df['startdate'], errors='coerce')
    parts.append(df[start > obs + pd.Timedelta(days=365)].assign(days_ahead=(start - obs).dt.days))
far = pd.concat(parts)
pd.set_option('display.width', 250)
print(far.to_string(index=False))

# every snapshot of the same user and company, to see whether the start date later changes
users = set(far['user_id'])
history = pd.concat(pd.read_parquet(f, columns=cols).query('user_id in @users') for f in files)
history = history[history['company_raw'].isin(far['company_raw'])]
print(history.sort_values(['user_id', 'observed_ts']).to_string(index=False))