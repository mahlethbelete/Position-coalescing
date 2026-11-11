import sys
import glob
import pandas as pd

DISPLAY_COLUMNS = [
    "user_id",
    "company_raw",
    "title_raw",
    "startdate",
    "enddate",
    "observed_ts",
]


def main(input_dir):
    files = sorted(glob.glob(f"{input_dir}/**/*.parquet", recursive=True))

    future_rows = []
    for path in files:
        df = pd.read_parquet(path, columns=DISPLAY_COLUMNS)
        observed = pd.to_datetime(df["observed_ts"], errors="coerce")
        start = pd.to_datetime(df["startdate"], errors="coerce")
        end = pd.to_datetime(df["enddate"], errors="coerce")

        end_days = (end - observed).dt.days
        start_days = (start - observed).dt.days

        mask = (end_days > 30) | (start_days > 7)
        if mask.any():
            subset = df[mask].copy()
            subset["end_days_ahead"] = end_days[mask]
            subset["start_days_ahead"] = start_days[mask]
            future_rows.append(subset)

    future_df = pd.concat(future_rows, ignore_index=True)
    print(f"\ncollected {len(future_df)} future dated rows for inspection")

    sample = future_df.sample(min(15, len(future_df)), random_state=0)
    print("\nsample rows:")
    print(
        sample[DISPLAY_COLUMNS + ["start_days_ahead", "end_days_ahead"]].to_string(
            index=False
        )
    )

    sample_users = sample["user_id"].unique().tolist()

    histories = []
    for path in files:
        df = pd.read_parquet(path, columns=DISPLAY_COLUMNS)
        histories.append(df[df["user_id"].isin(sample_users)])

    history_df = pd.concat(histories, ignore_index=True).sort_values(
        ["user_id", "observed_ts"]
    )

    for user_id in sample_users:
        print(f"\nfull history for user {user_id}:")
        rows = history_df[history_df["user_id"] == user_id]
        print(
            rows[
                ["company_raw", "title_raw", "startdate", "enddate", "observed_ts"]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "assignment"
    main(input_dir)
