import glob
import sys
from collections import Counter

import pandas as pd

from src.keys import text_key

SUFFIXES = {'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation', 'plc', 'gmbh', 'llp', 'lp'}
COLUMNS = ['asof_ts', 'user_id', 'company_raw', 'title_raw', 'startdate', 'position_id']
EXAMPLES = 20


def strip_suffix(key):
    if key is None:
        return None
    words = key.split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return ' '.join(words)


def main():
    out_dir = sys.argv[1]
    positions, groups, involved, examples = 0, Counter(), 0, []
    parts = sorted(glob.glob(f'{out_dir}/part_*.parquet'))
    if not parts:
        raise SystemExit('No part files found.')
    for part in parts:
        output = pd.read_parquet(part, columns=COLUMNS)
        latest = output.sort_values('asof_ts').drop_duplicates(['user_id', 'position_id'], keep='last').copy()
        positions += len(latest)
        latest['company_key'] = latest['company_raw'].map(text_key)
        latest['title_key'] = latest['title_raw'].map(text_key)
        latest['stripped'] = latest['company_key'].map(strip_suffix)
        latest = latest.dropna(subset=['stripped', 'title_key'])
        for label, subset in (('same start', latest[latest['startdate'].notna()]),
                              ('a start missing', latest[latest['startdate'].isna()])):
            keys = ['user_id', 'stripped', 'title_key'] + (['startdate'] if label == 'same start' else [])
            for _, group in subset.groupby(keys):
                if group['position_id'].nunique() > 1 and group['company_key'].nunique() > 1:
                    groups[label] += 1
                    involved += group['position_id'].nunique()
                    if len(examples) < EXAMPLES:
                        examples.append((label, group))
    print(f'Positions checked: {positions:,}\n')
    print('Groups of different positions of one user whose company differs only by a legal suffix')
    print('and whose title is the same:')
    for label in ('same start', 'a start missing'):
        print(f'    {label}: {groups[label]:,} groups')
    print(f'Positions involved: {involved:,} ({involved / positions:.3%} of all positions)\n')
    print(f'First {len(examples)} groups (read them yourself):')
    for label, group in examples:
        print(f'  [{label}]')
        for row in group.itertuples():
            print(f'    user {row.user_id} | {row.company_raw} | {row.title_raw} | {str(row.startdate)[:10]}')


if __name__ == '__main__':
    main()