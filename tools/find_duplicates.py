import glob
import sys
from collections import Counter

import pandas as pd

MIN_LENGTH = 40
OUT_COLUMNS = [
    "asof_ts",
    "user_id",
    "company_raw",
    "title_raw",
    "description",
    "startdate",
    "position_id",
]


def description_key(series):
    return (
        series.fillna("").str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    )


def start_kind(first, second):
    if pd.isna(first["startdate"]) or pd.isna(second["startdate"]):
        return "start missing"
    return (
        "same start" if first["startdate"] == second["startdate"] else "start differs"
    )


def shape(seen_a, seen_b, rank):
    if max(seen_a) > min(seen_b) and max(seen_b) > min(seen_a):
        return "interleaved"
    early, late = (seen_a, seen_b) if max(seen_a) < min(seen_b) else (seen_b, seen_a)
    return "swap" if rank[max(early)] + 1 == rank[min(late)] else "gap"


def bucket_pairs(output_part, log_part):
    output = pd.read_parquet(output_part, columns=OUT_COLUMNS)
    log = pd.read_parquet(
        log_part, columns=["user_id", "observed_ts", "position_id", "tier"]
    )
    ranks = {
        user: {ts: i for i, ts in enumerate(sorted(group.unique()))}
        for user, group in log.groupby("user_id")["observed_ts"]
    }
    log = log[log["position_id"].notna() & (log["tier"] != "collapsed duplicate")]
    log["position_id"] = log["position_id"].astype("int64")
    seen = log.groupby(["user_id", "position_id"])["observed_ts"].agg(frozenset)

    latest = (
        output.sort_values("asof_ts")
        .drop_duplicates(["user_id", "position_id"], keep="last")
        .copy()
    )
    latest["desc_key"] = description_key(latest["description"])
    latest = latest[latest["desc_key"].str.len() >= MIN_LENGTH]

    pairs = []
    for _, group in latest.groupby(["user_id", "desc_key"]):
        rows = group.to_dict("records")
        for i, first in enumerate(rows):
            for second in rows[i + 1 :]:
                seen_a = seen.get((first["user_id"], first["position_id"]), frozenset())
                seen_b = seen.get(
                    (second["user_id"], second["position_id"]), frozenset()
                )
                if seen_a.isdisjoint(seen_b):
                    kind = (
                        start_kind(first, second),
                        shape(seen_a, seen_b, ranks[first["user_id"]]),
                    )
                    pairs.append((first, second, kind))
    return len(output.drop_duplicates(["user_id", "position_id"])), pairs


def main():
    out_dir = sys.argv[1]
    total, kinds, examples = 0, Counter(), []
    for part in sorted(glob.glob(f"{out_dir}/part_*.parquet")):
        log_part = part.replace(f"{out_dir}/part_", f"{out_dir}/_logs/match_log_part_")
        positions, pairs = bucket_pairs(part, log_part)
        total += positions
        for first, second, kind in pairs:
            kinds[kind] += 1
            if kind == ("start differs", "swap") and len(examples) < 6:
                examples.append((first, second))
    print("Positions:", f"{total:,}")
    print("Possible duplicate pairs:", f"{sum(kinds.values()):,}")
    for (start, how), count in sorted(kinds.items()):
        print(f"  {start:14} | {how:12} | {count:,}")
    for first, second in examples:
        for row in (first, second):
            print(
                row["user_id"],
                "|",
                row["company_raw"],
                "|",
                row["title_raw"],
                "|",
                row["startdate"],
            )
        print()


if __name__ == "__main__":
    main()
