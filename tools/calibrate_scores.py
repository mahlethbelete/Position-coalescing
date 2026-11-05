import glob
import random
import sys
from collections import Counter, defaultdict
from types import SimpleNamespace

import pandas as pd

from src.keys import description_key, text_key, url_key
from src.score import best_candidate

COLUMNS = ['asof_ts', 'user_id', 'company_raw', 'company_linkedin_url', 'title_raw', 'description', 'startdate', 'position_id']
THRESHOLDS = [0.7, 0.8, 0.9]
MARGINS = [0.05, 0.1, 0.2]
SEED = 7


def profile(rows):
    position = SimpleNamespace(position_id=int(rows['position_id'].iloc[0]), companies=set(), titles=set(), urls=set(),
                               descs=set(), start=None)
    for record in rows.itertuples():
        position.companies.add(text_key(record.company_raw))
        position.titles.add(text_key(record.title_raw))
        position.urls.add(url_key(record.company_linkedin_url))
        position.descs.add(description_key(record.description))
        position.start = None if pd.isna(record.startdate) else record.startdate
    for name in ('companies', 'titles', 'urls', 'descs'):
        setattr(position, name, getattr(position, name) - {None})
    return position


def observation(position, kind):
    row = {'company_key': next(iter(position.companies), None), 'title_key': next(iter(position.titles), None),
           'url_key': next(iter(position.urls), None), 'desc_key': next(iter(position.descs), None), 'start': position.start}
    if kind == 'start blank':
        row['start'] = None
    elif kind == 'company blank':
        row['company_key'], row['url_key'] = None, None
    elif kind == 'title blank':
        row['title_key'] = None
    elif kind == 'title typo' and row['title_key']:
        row['title_key'] = row['title_key'][:-1] + 'x'
    elif kind == 'start shifted 2 months' and row['start'] is not None:
        row['start'] = row['start'] + pd.DateOffset(months=2)
    elif kind == 'description blank':
        row['desc_key'] = None
    return row


KINDS = ['unchanged', 'start blank', 'company blank', 'title blank', 'title typo', 'start shifted 2 months', 'description blank']
GROUPS = ['same company and title sibling', 'same company sibling', 'no sibling']
MAX_USERS = 6000
PARTS = 30


def group_of(target, positions):
    others = [p for p in positions if p is not target]
    if any(p.companies & target.companies and p.titles & target.titles for p in others):
        return GROUPS[0]
    if any(p.companies & target.companies for p in others):
        return GROUPS[1]
    return GROUPS[2]


def decide(scored, threshold, margin):
    if not scored or scored[0][0] < threshold:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
        return None
    return scored[0][1]


def main():
    out_dir = sys.argv[1]
    random.seed(SEED)
    parts = sorted(glob.glob(f'{out_dir}/part_*.parquet'))
    results, totals = defaultdict(list), Counter()
    users_done = 0
    for part in random.sample(parts, min(PARTS, len(parts))):
        frame = pd.read_parquet(part, columns=COLUMNS)
        for user_id, rows in frame.groupby('user_id'):
            positions = [profile(group) for _, group in rows.groupby('position_id')]
            if len(positions) < 2:
                continue
            for target in positions:
                group = group_of(target, positions)
                totals[group] += 1
                if group == GROUPS[2] and totals[group] > 3000:
                    continue
                for kind in KINDS:
                    _, scored = best_candidate(observation(target, kind), positions, 0.0, 0.0)
                    scored = [(value, position.position_id) for value, _, position in scored]
                    for threshold in THRESHOLDS:
                        for margin in MARGINS:
                            chosen = decide(scored, threshold, margin)
                            results[(group, kind, threshold, margin)].append(
                                None if chosen is None else chosen == target.position_id)
            users_done += 1
            if users_done >= MAX_USERS:
                break
        if users_done >= MAX_USERS:
            break
    print(f'Users: {users_done:,} | targets per group: {dict(totals)}')
    print('group | kind | threshold | margin | n | decided % | wrong among decided | correct among decided %')
    for key in sorted(results, key=lambda k: (GROUPS.index(k[0]), KINDS.index(k[1]), k[2], k[3])):
        values = results[key]
        decided = [v for v in values if v is not None]
        wrong = len(decided) - sum(decided)
        precision = 100 * sum(decided) / len(decided) if decided else float('nan')
        print(f'{key[0]:32} | {key[1]:24} | {key[2]:.1f} | {key[3]:.2f} | {len(values):6,} | '
              f'{100 * len(decided) / len(values):5.1f} | {wrong:5,} | {precision:6.2f}')


if __name__ == '__main__':
    main()