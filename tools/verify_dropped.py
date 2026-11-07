import sys
import pandas as pd
import pyarrow.dataset as ds

out, inp = sys.argv[1], sys.argv[2]

keys = ["user_id", "observed_ts"]
src = (
    ds.dataset(inp, format="parquet")
    .to_table(columns=keys)
    .to_pandas()
    .drop_duplicates()
)
done = (
    ds.dataset(out, format="parquet")
    .to_table(columns=["user_id", "asof_ts"])
    .to_pandas()
)
done = done.rename(columns={"asof_ts": "observed_ts"}).drop_duplicates()

import glob

parts = glob.glob(out + "/_logs/dropped_snapshots_part_*.parquet")
log = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)

merged = src.merge(done, on=keys, how="left", indicator=True)
missing = merged[merged["_merge"] == "left_only"][keys]

print("Input snapshots:", len(src))
print("Missing from output:", len(missing))
print("Dropped snapshots log rows:", len(log))
print("Log columns:", list(log.columns))
if "observed_ts" in log.columns:
    both = missing.merge(
        log[keys].drop_duplicates(), on=keys, how="outer", indicator=True
    )
    print(both["_merge"].value_counts().to_string())
print(log.head(5).to_string())
