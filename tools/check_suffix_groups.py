import glob
import random
import sys
from collections import Counter

import pandas as pd

from src.keys import description_key, text_key, url_key

SUFFIXES = {'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation', 'plc', 'gmbh', 'llp', 'lp'}
COLUMNS = ['asof_ts', 'user_id', 'company_raw', 'company_linkedin_url', 'title_raw', 'description',
           'startdate', 'position_id']
RANDOM_EXAMPLES = 40
RISKY_EXAMPLES = 15


def desc_text(value):
    key = description_key(value)
    return None if key is None else str(key)


def strip_suffix(key):
    if key is None:
        return None
    words = key.split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return ' '.join(words)


def has(value):
    return isinstance(value, str) and value != ''


def url_category(rows):
    urls = {row['url_key'] for row in rows if has(row['url_key'])}
    if len(urls) > 1:
        return 'different URLs'
    if len(urls) == 1:
        return 'same URL' if all(has(row['url_key']) for row in rows) else 'one URL, other missing'
    return 'no URL'


def description_category(rows):
    descs = {row['desc_key'] for row in rows if has(row['desc_key'])}
    if len(descs) > 1:
        return 'different descriptions'
    if len(descs) == 1:
        return 'same description' if all(has(row['desc_key']) for row in rows) else 'one description, other missing'
    return 'no usable description'


def find_groups(part):
    output = pd.read_parquet(part, columns=COLUMNS)
    latest = output.sort_values('asof_ts').drop_duplicates(['user_id', 'position_id'], keep='last').copy()
    total = len(latest)
    latest['company_key'] = latest['company_raw'].map(text_key)
    latest['title_key'] = latest['title_raw'].map(text_key)
    latest['stripped'] = latest['company_key'].map(strip_suffix)
    latest['url_key'] = latest['company_linkedin_url'].map(url_key)
    latest['desc_key'] = latest['description'].map(desc_text)
    latest = latest.dropna(subset=['stripped', 'title_key'])
    found = []
    for label, subset in (('same start', latest[latest['startdate'].notna()]),
                          ('both start missing', latest[latest['startdate'].isna()])):
        keys = ['user_id', 'stripped', 'title_key'] + (['startdate'] if label == 'same start' else [])
        for _, group in subset.groupby(keys):
            if group['position_id'].nunique() > 1 and group['company_key'].nunique() > 1:
                found.append((label, group.to_dict('records')))
    return total, found


def show(label, rows):
    print(f'  [{label} | {url_category(rows)} | {description_category(rows)}]')
    for row in rows:
        description = row['description'][:50].replace('\n', ' ') if isinstance(row['description'], str) else ''
        print(f"    user {row['user_id']} | {row['company_raw']} | {row['title_raw']} | "
              f"{str(row['startdate'])[:10]} | {row['company_linkedin_url'] if has(row['company_linkedin_url']) else 'no URL'} | {description}")


def main():
    out_dir = sys.argv[1]
    parts = sorted(glob.glob(f'{out_dir}/part_*.parquet'))
    if not parts:
        raise SystemExit('No part files found.')
    positions, groups = 0, []
    for part in parts:
        total, found = find_groups(part)
        positions += total
        groups += found

    table = Counter((url_category(rows), description_category(rows)) for _, rows in groups)
    by_url = Counter(url_category(rows) for _, rows in groups)
    print(f'Positions checked: {positions:,}')
    print(f'Suffix groups: {len(groups):,}\n')
    print('By URL:')
    for name, count in by_url.most_common():
        print(f'    {name}: {count:,} ({count / len(groups):.1%})')
    print('\nBy URL and description:')
    for (url_name, desc_name), count in sorted(table.items(), key=lambda item: -item[1]):
        print(f'    {url_name} | {desc_name}: {count:,}')

    risky = [group for group in groups if url_category(group[1]) == 'different URLs']
    print(f'\nGroups with different URLs (the danger signal), first {min(RISKY_EXAMPLES, len(risky))} of {len(risky):,}:')
    for label, rows in risky[:RISKY_EXAMPLES]:
        show(label, rows)

    sample = random.Random(1).sample(groups, min(RANDOM_EXAMPLES, len(groups)))
    print(f'\nRandom sample of {len(sample)} groups (judge each one yourself: same job, different job, unsure):')
    for label, rows in sample:
        show(label, rows)


if __name__ == '__main__':
    main()