import glob
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.keys import text_key, titles_similar

TIERS = ('company + start', 'url + start')
EXAMPLES = 20


def title_change_kind(old, new):
    old_key, new_key = text_key(old), text_key(new)
    if old_key == new_key:
        return 'same after cleaning'
    if titles_similar(old_key, new_key):
        return 'similar title'
    return 'different title'


def main():
    out_dir = sys.argv[1]
    matched, kinds, examples = Counter(), Counter(), []
    log_paths = sorted(glob.glob(f'{out_dir}/_logs/match_log_part_*.parquet'))
    if not log_paths:
        raise SystemExit('No match logs found. Use an output folder made with WRITE_LOGS=1.')
    for log_path in log_paths:
        change_path = log_path.replace('match_log_', 'change_log_')
        matches = pd.read_parquet(log_path, columns=['user_id', 'observed_ts', 'position_id', 'tier'])
        matches = matches[matches['tier'].isin(TIERS)].dropna(subset=['position_id'])
        for tier, count in matches['tier'].value_counts().items():
            matched[tier] += int(count)
        changes = pd.read_parquet(change_path, columns=['user_id', 'asof_ts', 'position_id', 'field',
                                                          'old_value', 'new_value', 'resolution'])
        changes = changes[(changes['field'] == 'title_raw') & (changes['resolution'] == 'newest wins')]
        if matches.empty or changes.empty:
            continue
        matches = matches.assign(ts=pd.to_datetime(matches['observed_ts']),
                                  position_id=matches['position_id'].astype('int64'))
        changes = changes.assign(ts=pd.to_datetime(changes['asof_ts']),
                                  position_id=changes['position_id'].astype('int64'))
        joined = matches[['user_id', 'ts', 'position_id', 'tier']].merge(
            changes[['user_id', 'ts', 'position_id', 'old_value', 'new_value']],
            on=['user_id', 'ts', 'position_id'])
        for row in joined.itertuples():
            kind = title_change_kind(row.old_value, row.new_value)
            kinds[(row.tier, kind)] += 1
            if kind == 'different title' and len(examples) < EXAMPLES:
                examples.append(row)

    print('Rows matched by tiers that ignore the title, and what happened to the title:\n')
    for tier in TIERS:
        total = matched[tier]
        print(f'{tier}: {total:,} matched rows')
        for kind in ('same after cleaning', 'similar title', 'different title'):
            count = kinds[(tier, kind)]
            share = count / total if total else 0
            print(f'    {kind}: {count:,} ({share:.2%} of matched rows)')
        unchanged = total - sum(kinds[(tier, kind)] for kind in ('same after cleaning', 'similar title', 'different title'))
        print(f'    title not changed: {unchanged:,}\n')
    print(f'First {len(examples)} rows with a different title (read them yourself):')
    for row in examples:
        print(f'  user {row.user_id} | position {row.position_id} | {row.tier} | {str(row.ts)[:10]}')
        print(f'      old: {row.old_value}')
        print(f'      new: {row.new_value}')


if __name__ == '__main__':
    main()