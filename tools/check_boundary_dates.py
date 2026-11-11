import sys
import glob
import pandas as pd

DISPLAY_COLUMNS = ["user_id", "company_raw", "title_raw", "startdate", "enddate", "observed_ts"]

def main(input_dir):
    files = sorted(glob.glob(f"{input_dir}/**/*.parquet", recursive=True))

    end_hits = []
    start_hits = []

    for path in files:
        df = pd.read_parquet(path, columns=DISPLAY_COLUMNS)
        observed = pd.to_datetime(df["observed_ts"], errors="coerce")
        start = pd.to_datetime(df["startdate"], errors="coerce")
        end = pd.to_datetime(df["enddate"], errors="coerce")

        end_days = (end - observed).dt.days
        start_days = (start - observed).dt.days

        end_mask = (end_days > 3 * 365) & (end_days <= 5 * 365)
        start_mask = start_days > 7

        if end_mask.any():
            subset = df[end_mask].copy()
            subset["end_days_ahead"] = end_days[end_mask]
            end_hits.append(subset)

        if start_mask.any():
            subset = df[start_mask].copy()
            subset["start_days_ahead"] = start_days[start_mask]
            start_hits.append(subset)

    end_df = pd.concat(end_hits, ignore_index=True) if end_hits else pd.DataFrame(columns=DISPLAY_COLUMNS)
    start_df = pd.concat(start_hits, ignore_index=True) if start_hits else pd.DataFrame(columns=DISPLAY_COLUMNS)

    end_unique = end_df.drop_duplicates(subset=["user_id", "company_raw", "enddate"])
    start_unique = start_df.drop_duplicates(subset=["user_id", "company_raw", "startdate"])

    print(f"enddate 3 to 5 years ahead: {len(end_df)} rows, {len(end_unique)} unique cases")
    print(f"startdate future: {len(start_df)} rows, {len(start_unique)} unique cases")

    target_users = set(end_unique["user_id"]).union(start_unique["user_id"])

    later_rows = []
    for path in files:
        df = pd.read_parquet(path, columns=DISPLAY_COLUMNS)
        later_rows.append(df[df["user_id"].isin(target_users)])

    history_df = pd.concat(later_rows, ignore_index=True).sort_values(["user_id", "observed_ts"])

    print("\n=== enddate 3 to 5 years ahead cases, with later history ===")
    for _, row in end_unique.head(10).iterrows():
        user_id, company, flagged_observed = row["user_id"], row["company_raw"], row["observed_ts"]
        print(f"\nuser {user_id}, company {company}, flagged enddate {row['enddate']}, {row['end_days_ahead']} days ahead, seen at {flagged_observed}")
        later = history_df[(history_df["user_id"] == user_id) & (history_df["observed_ts"] > flagged_observed) & (history_df["company_raw"] == company)]
        print(later[["title_raw", "startdate", "enddate", "observed_ts"]].drop_duplicates().to_string(index=False))

    print("\n\n=== all future startdate cases, with later history ===")
    for _, row in start_unique.iterrows():
        user_id, company, flagged_observed = row["user_id"], row["company_raw"], row["observed_ts"]
        print(f"\nuser {user_id}, company {company}, flagged startdate {row['startdate']}, {row['start_days_ahead']} days ahead, seen at {flagged_observed}")
        later = history_df[(history_df["user_id"] == user_id) & (history_df["observed_ts"] > flagged_observed) & (history_df["company_raw"] == company)]
        print(later[["title_raw", "startdate", "enddate", "observed_ts"]].drop_duplicates().to_string(index=False))

if __name__ == "__main__":
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "assignment"
    main(input_dir)