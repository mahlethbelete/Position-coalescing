import pandas as pd

from src.keys import is_placeholder

TEXT_COLUMNS = ["company_raw", "title_raw", "location_raw", "description"]
EARLIEST_DATE = pd.Timestamp("1950-01-01")
MAX_END_AHEAD = pd.DateOffset(years=5)
SNAPSHOT_KEYS = ["user_id", "observed_ts"]


def standardize_columns(df):
    if "company_website" in df.columns and "company_linkedin_url" not in df.columns:
        df = df.rename(columns={"company_website": "company_linkedin_url"})
    return df


def to_dates(series):
    return pd.to_datetime(series, errors="coerce")


def text_is_filled(series):
    text = series.astype("string").str.strip()
    filled = (text.notna() & (text != "")).fillna(False).astype(bool)
    short = filled & (text.str.len() <= 30).fillna(False).astype(bool)
    placeholders = {value for value in text[short].unique() if is_placeholder(value)}
    return filled & ~text.isin(placeholders).fillna(False).astype(bool)


def bad_row_flags(df):
    observed = to_dates(df["observed_ts"])
    start = to_dates(df["startdate"])
    end = to_dates(df["enddate"])
    start_given = df["startdate"].notna()
    end_given = df["enddate"].notna()
    useful = pd.concat([text_is_filled(df[column]) for column in TEXT_COLUMNS], axis=1)
    useful["start"] = start_given
    useful["end"] = end_given
    flags = pd.DataFrame(
        {
            "unreadable observed_ts": observed.isna(),
            "unreadable date": (start_given & start.isna()) | (end_given & end.isna()),
            "end before start": start.notna() & end.notna() & (end < start),
            "date before 1950": (start < EARLIEST_DATE) | (end < EARLIEST_DATE),
            "end over 5 years after snapshot": end > observed + MAX_END_AHEAD,
            "start after snapshot": start > observed,
            "no useful field": ~useful.any(axis=1),
        }
    )
    return flags, observed, start, end


def clean(df):
    df = standardize_columns(df).reset_index(drop=True)
    flags, observed, start, end = bad_row_flags(df)
    bad = flags.any(axis=1)

    names = flags.columns.to_numpy()
    reasons = ["; ".join(names[row]) for row in flags[bad].to_numpy()]
    dropped_rows = df[bad].assign(reason=reasons)

    good = df[~bad].copy()
    good["observed_dt"] = observed[~bad]
    good["start_dt"] = start[~bad]
    good["end_dt"] = end[~bad]

    kept = good[SNAPSHOT_KEYS].drop_duplicates().assign(kept=True)
    seen = (
        df.groupby(SNAPSHOT_KEYS, dropna=False)
        .size()
        .rename("rows_in_input")
        .reset_index()
    )
    seen = seen.merge(kept, on=SNAPSHOT_KEYS, how="left")
    dropped_snapshots = (
        seen[seen["kept"].isna()]
        .drop(columns="kept")
        .assign(reason="no valid rows left")
    )

    return good, dropped_rows, dropped_snapshots
