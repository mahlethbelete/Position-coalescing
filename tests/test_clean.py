import datetime as dt

import pandas as pd

from src.clean import clean

COLUMNS = ['observed_ts', 'user_id', 'company_raw', 'company_website', 'title_raw',
           'location_raw', 'description', 'startdate', 'enddate', 'order_in_profile']


def make(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


def row(ts, user, company='Acme', title='Engineer', start=dt.date(2020, 1, 1), end=None, order=0, description=None):
    return [ts, user, company, None, title, None, description, start, end, order]


def test_good_rows_pass_and_originals_are_untouched():
    df = make([row(dt.date(2026, 9, 1), 1, end=dt.date(2021, 1, 1))])
    good, dropped_rows, dropped_snapshots = clean(df)
    assert len(good) == 1 and dropped_rows.empty and dropped_snapshots.empty
    assert good['startdate'].iloc[0] == dt.date(2020, 1, 1)
    assert 'company_linkedin_url' in good.columns


def test_bad_row_dropped_but_snapshot_kept():
    df = make([
        row(dt.date(2026, 9, 1), 1),
        row(dt.date(2026, 9, 1), 1, title='Intern', start=dt.date(2020, 5, 1), end=dt.date(2019, 1, 1), order=1),
    ])
    good, dropped_rows, dropped_snapshots = clean(df)
    assert list(good['title_raw']) == ['Engineer']
    assert list(dropped_rows['reason']) == ['end before start']
    assert dropped_rows['title_raw'].iloc[0] == 'Intern'
    assert dropped_snapshots.empty


def test_snapshot_dropped_when_no_valid_row_left():
    df = make([
        row(dt.date(2026, 9, 1), 1),
        row(dt.date(2026, 9, 2), 1, start=dt.date(1900, 1, 1)),
    ])
    good, dropped_rows, dropped_snapshots = clean(df)
    assert list(good['observed_ts']) == [dt.date(2026, 9, 1)]
    assert list(dropped_snapshots['observed_ts']) == [dt.date(2026, 9, 2)]
    assert list(dropped_snapshots['rows_in_input']) == [1]
    assert list(dropped_rows['reason']) == ['date before 1950']


def test_empty_and_blank_rows_are_dropped():
    df = make([
        row(dt.date(2026, 9, 1), 1),
        [dt.date(2026, 9, 1), 1, None, None, None, None, None, None, None, 1],
        [dt.date(2026, 9, 1), 1, ' ', None, '', None, None, None, None, 2],
    ])
    good, dropped_rows, _ = clean(df)
    assert len(good) == 1
    assert set(dropped_rows['reason']) == {'no useful field'}


def test_unreadable_and_far_future_dates():
    df = make([
        row(dt.date(2026, 9, 1), 1),
        row(dt.date(2026, 9, 1), 1, title='A', start=dt.date(1383, 3, 1), order=1),
        row(dt.date(2026, 9, 1), 1, title='B', end=dt.date(2096, 6, 1), order=2),
    ])
    good, dropped_rows, _ = clean(df)
    assert list(good['title_raw']) == ['Engineer']
    reasons = dict(zip(dropped_rows['title_raw'], dropped_rows['reason']))
    assert reasons['A'] in ('unreadable date', 'date before 1950')
    assert reasons['B'] == 'end over 5 years after snapshot'


def test_several_reasons_are_all_logged():
    df = make([
        row(dt.date(2026, 9, 1), 1),
        row(dt.date(2026, 9, 1), 1, title='C', start=dt.date(1940, 1, 1), end=dt.date(1930, 1, 1), order=1),
    ])
    _, dropped_rows, _ = clean(df)
    assert dropped_rows['reason'].iloc[0] == 'end before start; date before 1950'