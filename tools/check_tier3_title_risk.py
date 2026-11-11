import sys
import glob
import re
import pandas as pd

def normalize_words(text):
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return {w for w in words if len(w) > 2}

def initials(text):
    words = re.findall(r"[a-zA-Z]+", text)
    return "".join(w[0] for w in words).lower()

def is_initials_pair(a, b):
    ia, ib = initials(a), initials(b)
    if not ia or not ib:
        return False
    return ia == b.lower().replace(" ", "") or ib == a.lower().replace(" ", "")

def bucket(old, new):
    old_words, new_words = normalize_words(old), normalize_words(new)
    if old_words & new_words:
        return "shared word"
    if is_initials_pair(old, new):
        return "initials match"
    return "no overlap"

def main(out_dir):
    outputs = [
        pd.read_parquet(f, columns=["asof_ts", "position_id", "title_raw"])
        for f in sorted(glob.glob(f"{out_dir}/part_*.parquet"))
    ]
    output = pd.concat(outputs, ignore_index=True).sort_values(["position_id", "asof_ts"])
    output["prev_title"] = output.groupby("position_id")["title_raw"].shift(1)

    logs = [
        pd.read_parquet(f, columns=["observed_ts", "position_id", "tier"])
        for f in sorted(glob.glob(f"{out_dir}/_logs/match_log_part_*.parquet"))
    ]
    log = pd.concat(logs, ignore_index=True)
    log = log[log["tier"] == "url + start"].dropna(subset=["position_id"])
    log["position_id"] = log["position_id"].astype("int64")

    merged = output.merge(
        log, left_on=["position_id", "asof_ts"], right_on=["position_id", "observed_ts"]
    )
    merged = merged.dropna(subset=["prev_title", "title_raw"])
    merged = merged[merged["prev_title"] != merged["title_raw"]]
    merged["bucket"] = merged.apply(lambda r: bucket(r["prev_title"], r["title_raw"]), axis=1)

    print(f"tier 'url + start' matches with a title change: {len(merged):,}")
    print(merged["bucket"].value_counts())

    no_overlap = merged[merged["bucket"] == "no overlap"]
    sample = no_overlap.sample(min(302, len(no_overlap)), random_state=0)
    print("\nsample of no overlap cases:")
    print(sample[["prev_title", "title_raw"]].to_string(index=False))

if __name__ == "__main__":
    main(sys.argv[1])