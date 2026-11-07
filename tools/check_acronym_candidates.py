import glob
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.keys import text_key, titles_similar

STOPWORDS = {
    "of",
    "the",
    "and",
    "for",
    "a",
    "an",
    "at",
    "inc",
    "llc",
    "ltd",
    "corp",
    "co",
}
EXAMPLES_PER_BUCKET = 5


def acronym(company_raw):
    text = text_key(company_raw)
    if text is None:
        return None
    words = [word for word in text.split() if word not in STOPWORDS]
    if len(words) < 2:
        return None
    return "".join(word[0] for word in words)


def is_short_token(company_raw):
    text = text_key(company_raw)
    return (
        text is not None and " " not in text and 2 <= len(text) <= 6 and text.isalpha()
    )


def has_url(value):
    return isinstance(value, str) and value.strip() != ""


def load_output(out_dir):
    columns = [
        "user_id",
        "asof_ts",
        "position_id",
        "company_raw",
        "company_linkedin_url",
        "title_raw",
        "startdate",
    ]
    parts = sorted(glob.glob(f"{out_dir}/part_*.parquet"))
    frames = [pd.read_parquet(part, columns=columns) for part in parts]
    return pd.concat(frames, ignore_index=True)


def first_appearance(output):
    first = output.sort_values("asof_ts").drop_duplicates(
        ["user_id", "position_id"], keep="first"
    )
    return first.sort_values(["user_id", "asof_ts"])


def find_candidates(out_dir):
    first = first_appearance(load_output(out_dir))
    counts, examples = Counter(), []
    examples_per = Counter()

    for user_id, rows in first.groupby("user_id"):
        rows = rows.to_dict("records")
        for i, later in enumerate(rows):
            if has_url(later["company_linkedin_url"]):
                continue
            if not is_short_token(later["company_raw"]):
                continue
            later_key = text_key(later["company_raw"])
            for earlier in rows[:i]:
                if acronym(earlier["company_raw"]) != later_key:
                    continue
                same_start = (
                    pd.notna(earlier["startdate"])
                    and pd.notna(later["startdate"])
                    and earlier["startdate"] == later["startdate"]
                )
                similar_title = titles_similar(
                    text_key(earlier["title_raw"]), text_key(later["title_raw"])
                )
                bucket = (
                    "same start"
                    if same_start
                    else ("similar title" if similar_title else "no corroboration")
                )
                counts[bucket] += 1
                if examples_per[bucket] < EXAMPLES_PER_BUCKET:
                    examples.append((bucket, earlier, later))
                    examples_per[bucket] += 1

    print(f"Candidate acronym pairs: {sum(counts.values()):,}\n")
    for bucket, count in counts.most_common():
        print(f"{count:6,}  {bucket}")
    print()
    for bucket, earlier, later in examples:
        print(f"== {bucket}")
        print(
            " earlier:",
            earlier["user_id"],
            "|",
            earlier["company_raw"],
            "|",
            earlier["title_raw"],
            "|",
            earlier["startdate"],
        )
        print(
            " later  :",
            later["user_id"],
            "|",
            later["company_raw"],
            "|",
            later["title_raw"],
            "|",
            later["startdate"],
        )
        print()


if __name__ == "__main__":
    find_candidates(sys.argv[1])
