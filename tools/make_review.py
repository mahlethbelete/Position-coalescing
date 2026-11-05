import glob
import random
import sys

import pandas as pd

COLUMNS = ['user_id', 'asof_ts', 'position_id', 'company_raw', 'title_raw', 'startdate']
BUCKETS = 10
PER_BUCKET = 2
MIN_POSITIONS, MAX_POSITIONS = 3, 20

HEADER = """HOW TO REVIEW
Each user below lists their positions (P followed by 4 digits). Under each position are the values the engine
saw for it over time, with the dates it was shown.
For every user, count two kinds of mistakes and write them on the VERDICT line:
  1. Wrong merge: one position that mixes two different real jobs.
  2. Duplicate: two positions that are really the same job.
Everything else counts as correct. At the end, add up the positions you reviewed and the mistakes.
"""


def show(value):
    return '' if pd.isna(value) else str(value)[:40]


def day(value):
    return '' if pd.isna(value) else str(value)[:10]


def describe(user_id, rows):
    groups = rows.groupby('position_id')
    lines = [f'USER {user_id} | {groups.ngroups} positions | {rows["asof_ts"].nunique()} snapshots']
    for position_id, group in sorted(groups, key=lambda item: item[1]['asof_ts'].min()):
        group = group.sort_values('asof_ts')
        lines.append(f'  P{str(position_id)[-4:]} shown {day(group["asof_ts"].min())} to {day(group["asof_ts"].max())}')
        runs = []
        for company, title, start, stamp in zip(group['company_raw'], group['title_raw'],
                                                group['startdate'], group['asof_ts']):
            key = (show(company), show(title), day(start))
            if runs and runs[-1][0] == key:
                runs[-1][2] = stamp
            else:
                runs.append([key, stamp, stamp])
        for (company, title, start), first, last in runs:
            lines.append(f'      {company} | {title} | start {start} | {day(first)} to {day(last)}')
    lines.append('  VERDICT: wrong merges __   duplicate positions __')
    return '\n'.join(lines), groups.ngroups


def is_tricky(rows):
    latest = rows.sort_values('asof_ts').drop_duplicates('position_id', keep='last')
    shared_company = latest['company_raw'].fillna('').str.lower().duplicated(keep=False) & latest['company_raw'].notna()
    edited = rows.drop_duplicates(['position_id', 'company_raw', 'title_raw', 'startdate']).groupby('position_id').size() > 1
    return bool(shared_company.any() or edited.any())


def main():
    out_dir, seed = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 11
    rng = random.Random(seed)
    parts = sorted(glob.glob(f'{out_dir}/part_*.parquet'))
    chosen = rng.sample(parts, min(BUCKETS, len(parts)))
    random_blocks, tricky_blocks, positions = [], [], 0
    for part in chosen:
        frame = pd.read_parquet(part, columns=COLUMNS)
        sizes = frame.groupby('user_id')['position_id'].nunique()
        users = sizes[(sizes >= MIN_POSITIONS) & (sizes <= MAX_POSITIONS)].index.tolist()
        rng.shuffle(users)
        picked_random, picked_tricky = 0, 0
        for user in users:
            rows = frame[frame['user_id'] == user]
            if picked_random < PER_BUCKET and not is_tricky(rows):
                block, count = describe(user, rows)
                random_blocks.append(block)
                positions += count
                picked_random += 1
            elif picked_tricky < PER_BUCKET and is_tricky(rows):
                block, count = describe(user, rows)
                tricky_blocks.append(block)
                positions += count
                picked_tricky += 1
            if picked_random == PER_BUCKET and picked_tricky == PER_BUCKET:
                break
    text = [HEADER, f'PLAIN USERS ({len(random_blocks)})', ''] + random_blocks
    text += ['', f'TRICKY USERS: same company twice or edited values ({len(tricky_blocks)})', ''] + tricky_blocks
    with open('review_sample.txt', 'w') as handle:
        handle.write('\n\n'.join(text))
    print('Users:', len(random_blocks) + len(tricky_blocks), '| positions to review:', positions)


if __name__ == '__main__':
    main()