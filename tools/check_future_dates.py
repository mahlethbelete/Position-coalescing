import sys
import glob
import pandas as pd

def report(name, days):
    total = len(days)
    print(f"\n{name}: {total} rows with a future date")
    if total == 0:
        return
    bins = [
        ("0 to 7 days", (days >= 0) & (days <= 7)),
        ("8 to 30 days", (days > 7) & (days <= 30)),
        ("31 to 365 days", (days > 30) & (days <= 365)),
        ("1 to 5 years", (days > 365) & (days <= 5 * 365)),
        ("more than 5 years", days > 5 * 365),
    ]
    for label, mask in bins:
        print(f"  {label}: {mask.sum()}")
    print(f"  max days ahead: {days.max()}")

def main(input_dir):
    files = sorted(glob.glob(f"{input_dir}/**/*.parquet", recursive=True))
    print(f"found {len(files)} files")

    start_parts = []
    end_parts = []

    for path in files:
        df = pd.read_parquet(path, columns=["observed_ts", "startdate", "enddate"])
        observed = pd.to_datetime(df["observed_ts"], errors="coerce")
        start = pd.to_datetime(df["startdate"], errors="coerce")
        end = pd.to_datetime(df["enddate"], errors="coerce")

        start_diff = (start - observed).dt.days
        end_diff = (end - observed).dt.days

        start_parts.append(start_diff[start_diff > 0])
        end_parts.append(end_diff[end_diff > 0])

    start_future = pd.concat(start_parts) if start_parts else pd.Series(dtype=float)
    end_future = pd.concat(end_parts) if end_parts else pd.Series(dtype=float)

    report("startdate", start_future)
    report("enddate", end_future)

if __name__ == "__main__":
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "assignment"
    main(input_dir)