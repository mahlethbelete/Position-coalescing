import glob
import sys
from collections import Counter, defaultdict

import pandas as pd

from find_duplicates import OUT_COLUMNS, bucket_pairs
from src.keys import description_key, text_key, titles_similar

LOG_COLUMNS = ['user_id', 'observed_ts', 'position_id', 'tier', 'ambiguous_candidates']
EXAMPLES_PER_CATEGORY = 3


def months_apart(first, second):
    return abs((first.year - second.year) * 12 + first.month - second.month)


def gap_bucket(months):
    for limit, label in ((12, '1 to 12'), (24, '13 to 24'), (60, '25 to 60')):
        if months <= limit:
            return label
    return 'over 60'


def classify(a_rows, b_rows, log_user, a_id, b_id):
    created_b = b_rows['asof_ts'].min()
    before = a_rows[a_rows['asof_ts'] < created_b]
    if before.empty:
        return 'created in the same snapshot', None
    first = b_rows.sort_values('asof_ts').iloc[0]
    companies = {text_key(value) for value in before['company_raw']} - {None}
    titles = {text_key(value) for value in before['title_raw']} - {None}
    descs = {description_key(value) for value in before['description']} - {None}
    company, title, desc = text_key(first['company_raw']), text_key(first['title_raw']), description_key(first['description'])
    same_company = company in companies
    same_title = title in titles
    similar_title = any(titles_similar(title, other) for other in titles)
    shared_desc = desc is not None and desc in descs
    a_start, b_start = before.sort_values('asof_ts').iloc[-1]['startdate'], first['startdate']
    created = log_user[(log_user['position_id'] == b_id) & (log_user['tier'] == 'new position')]
    ambiguous = int(created['ambiguous_candidates'].max()) if len(created) else 0
    steps = sorted(log_user['observed_ts'].unique())
    seen_a = set(log_user[(log_user['position_id'] == a_id) & (log_user['tier'] != 'collapsed duplicate')]['observed_ts'])
    index = steps.index(pd.Timestamp(created_b)) if pd.Timestamp(created_b) in steps else None
    a_seen_just_before = index is not None and index > 0 and steps[index - 1] in seen_a

    if not shared_desc:
        return 'description not shared when the later position was created', None
    if ambiguous:
        return 'blocked by ambiguity (more than one candidate)', None
    if pd.isna(a_start) or pd.isna(b_start):
        return ('start missing, company or title shared, same description' if same_company or same_title
                else 'start missing, nothing else shared'), None
    months = months_apart(a_start, b_start)
    if months == 0:
        return ('same start, same description: engine should have matched' if same_company or same_title or similar_title
                else 'same start, same description, company and title both changed'), None
    if months <= 12:
        if same_company and same_title:
            return ('start edit within 12 months, but old position not seen in the previous snapshot' if not a_seen_just_before
                    else 'start edit within 12 months, same company and title: engine should have matched'), None
        if same_company and similar_title:
            return 'start edit within 12 months, same company, similar title', None
        return 'start edit within 12 months, company or title changed', None
    if same_company and same_title:
        return 'start differs over 12 months, same company and title', months
    return 'start differs over 12 months, company or title changed', months


def main():
    out_dir = sys.argv[1]
    counts, examples, gaps = Counter(), defaultdict(list), Counter()
    by_shape = defaultdict(Counter)
    for part in sorted(glob.glob(f'{out_dir}/part_*.parquet')):
        log_part = part.replace(f'{out_dir}/part_', f'{out_dir}/_logs/match_log_part_')
        _, pairs = bucket_pairs(part, log_part)
        if not pairs:
            continue
        users = {pair[0]['user_id'] for pair in pairs}
        output = pd.read_parquet(part, columns=OUT_COLUMNS)
        output = output[output['user_id'].isin(users)]
        log = pd.read_parquet(log_part, columns=LOG_COLUMNS)
        log = log[log['user_id'].isin(users)]
        for first, second, kind in pairs:
            user = first['user_id']
            rows = output[output['user_id'] == user]
            one = rows[rows['position_id'] == first['position_id']]
            two = rows[rows['position_id'] == second['position_id']]
            if one['asof_ts'].min() > two['asof_ts'].min():
                one, two, first, second = two, one, second, first
            category, months = classify(one, two, log[log['user_id'] == user], first['position_id'], second['position_id'])
            counts[category] += 1
            by_shape[category][kind[1]] += 1
            if months:
                gaps[gap_bucket(months)] += 1
            if len(examples[category]) < EXAMPLES_PER_CATEGORY:
                examples[category].append((first, second))
    print(f'Pairs analysed: {sum(counts.values()):,}\n')
    for category, count in counts.most_common():
        print(f'{count:6,}  {category}   {dict(by_shape[category])}')
    print('\nStart gap in months, same company and title, start differs over 12 months:')
    for label in ('13 to 24', '25 to 60', 'over 60'):
        print(f'  {label}: {gaps[label]:,}')
    for category, items in examples.items():
        print(f'\n== {category}')
        for first, second in items:
            for row in (first, second):
                print(' ', row['user_id'], '|', row['company_raw'], '|', row['title_raw'], '|',
                      str(row['startdate'])[:10], '| first seen', str(row['asof_ts'])[:10])
            print()


if __name__ == '__main__':
    main()