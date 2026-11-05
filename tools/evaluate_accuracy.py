import random
import sys

import pandas as pd
import pyarrow.dataset as ds

from src.clean import clean, standardize_columns
from src.keys import text_key
from src.match import coalesce

USERS = 2000
SNAPSHOTS = 6
SEED = 7
KEEP_CHANCE = 0.8
KEY = ["company_raw", "title_raw", "startdate"]
COLUMNS = [
    "user_id",
    "company_raw",
    "company_website",
    "title_raw",
    "location_raw",
    "description",
    "startdate",
    "enddate",
    "observed_ts",
]


def load_base_jobs(input_dir, rng):
    dataset = ds.dataset(input_dir, format="parquet")
    names = dataset.schema.names
    columns = [
        c
        for c in COLUMNS
        if c in names or (c == "company_website" and "company_linkedin_url" in names)
    ]
    columns = [
        (
            c
            if c != "company_website"
            else (
                "company_website"
                if "company_website" in names
                else "company_linkedin_url"
            )
        )
        for c in columns
    ]
    users = dataset.to_table(columns=["user_id"]).column("user_id").unique().to_pylist()
    chosen = rng.sample(users, min(USERS, len(users)))
    table = dataset.to_table(columns=columns, filter=ds.field("user_id").isin(chosen))
    df = standardize_columns(table.to_pandas())
    df = df[df["observed_ts"] == df.groupby("user_id")["observed_ts"].transform("max")]
    df = df.drop_duplicates(["user_id"] + KEY)
    df = df.dropna(subset=KEY)
    counts = df.groupby("user_id").size()
    return df[df["user_id"].isin(counts[counts >= 2].index)]


def damage(job, rng):
    job, flags = dict(job), []
    if rng.random() < 0.3:
        job["title_raw"] = (
            job["title_raw"].upper() if rng.random() < 0.5 else job["title_raw"] + "."
        )
        flags.append("title case")
    if rng.random() < 0.15:
        job["company_raw"] = job["company_raw"] + " Inc"
        flags.append("company Inc")
    if rng.random() < 0.1:
        job["title_raw"] = "Senior " + job["title_raw"]
        flags.append("title Senior")
    if rng.random() < 0.2:
        job["description"] = None
    if rng.random() < 0.2:
        job["location_raw"] = None
    if rng.random() < 0.1:
        job["startdate"] = None
        flags.append("start blank")
    job["flags"] = ",".join(flags)
    return job


def build_histories(base, rng):
    rows = []
    for user_id, jobs in base.groupby("user_id"):
        jobs = jobs.to_dict("records")
        for step in range(SNAPSHOTS):
            stamp = pd.Timestamp("2024-01-01") + pd.DateOffset(months=step)
            chosen = [
                (truth, job)
                for truth, job in enumerate(jobs)
                if rng.random() < KEEP_CHANCE
            ]
            if not chosen:
                chosen = [(0, jobs[0])]
            rng.shuffle(chosen)
            for order, (truth, job) in enumerate(chosen):
                row = damage(job, rng)
                row.update(
                    user_id=user_id,
                    observed_ts=stamp,
                    order_in_profile=order,
                    truth=truth,
                    base_key=(text_key(job["company_raw"]), str(job["startdate"])),
                )
                rows.append(row)
    return pd.DataFrame(rows)


def pairs(counts):
    return int((counts * (counts - 1) // 2).sum())


def report(log, label):
    both = pairs(log.groupby(["user_id", "position_id", "truth"]).size())
    predicted = pairs(log.groupby(["user_id", "position_id"]).size())
    actual = pairs(log.groupby(["user_id", "truth"]).size())
    print(
        label,
        "| rows:",
        len(log),
        "| precision:",
        round(both / predicted, 4),
        "| recall:",
        round(both / actual, 4),
    )


def score(good, match_log):
    log = match_log.dropna(subset=["position_id"]).drop_duplicates(["row_id"]).copy()
    for name in ["truth", "user_id", "base_key", "flags"]:
        log[name] = good.loc[log["row_id"], name].to_numpy()
    print("Ignored rows:", len(good) - len(log))
    report(log, "ALL users")

    shared = log.groupby(["user_id", "base_key"])["truth"].nunique()
    shared_users = set(shared[shared > 1].index.get_level_values("user_id"))
    report(
        log[~log["user_id"].isin(shared_users)],
        "Users with no two jobs sharing company and start",
    )
    print(
        "Users where two true jobs share company and start:",
        len(shared_users),
        "of",
        log["user_id"].nunique(),
    )

    merged = log.groupby(["user_id", "position_id"]).agg(
        truths=("truth", "nunique"), keys=("base_key", "nunique")
    )
    merged = merged[merged["truths"] > 1]
    print(
        "Merged ids:",
        len(merged),
        "| explained by shared company and start:",
        int((merged["keys"] < merged["truths"]).sum()),
        "| other:",
        int((merged["keys"] >= merged["truths"]).sum()),
    )

    main_id = log.groupby(["user_id", "truth"])["position_id"].agg(
        lambda s: s.value_counts().index[0]
    )
    log = log.join(main_id.rename("main_id"), on=["user_id", "truth"])
    stray = log[log["position_id"] != log["main_id"]]
    print("Rows that left their true job (caused a split):", len(stray))
    print(stray["flags"].replace("", "no damage").value_counts().head(8).to_string())
    only = stray[stray["flags"] == "start blank"].head(4)
    for _, bad in only.iterrows():
        mates = log[(log["user_id"] == bad["user_id"]) & (log["truth"] == bad["truth"])]
        view = good.loc[
            mates["row_id"], ["observed_dt", "company_raw", "title_raw", "startdate"]
        ]
        view["position_id"] = mates["position_id"].to_numpy()
        print(view.sort_values("observed_dt").to_string(), "\n")


def main():
    input_dir = sys.argv[1]
    rng = random.Random(SEED)
    base = load_base_jobs(input_dir, rng)
    print("Users:", base["user_id"].nunique(), "| base jobs:", len(base))
    synthetic = build_histories(base, rng).reset_index(drop=True)
    good, dropped_rows, dropped_snapshots = clean(synthetic)
    print(
        "Synthetic rows:", len(synthetic), "| dropped by cleaning:", len(dropped_rows)
    )
    output, match_log, change_log = coalesce(good)
    score(good, match_log)


if __name__ == "__main__":
    main()
