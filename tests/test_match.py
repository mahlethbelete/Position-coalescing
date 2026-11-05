import datetime as dt

import pandas as pd

from src.clean import clean
from src.match import coalesce

COLUMNS = ['observed_ts', 'user_id', 'company_raw', 'company_website', 'title_raw',
           'location_raw', 'description', 'startdate', 'enddate', 'order_in_profile']
RL_URL = 'linkedin.com/company/revelio-labs'
NYU_URL = 'linkedin.com/company/nyu'


def d(text):
    return dt.date.fromisoformat(text)


def run(rows):
    good, _, _ = clean(pd.DataFrame(rows, columns=COLUMNS))
    return coalesce(good)


def case_a_rows():
    return [
        [d('2026-09-16'), 1, 'Revelio Labs', RL_URL, 'Machine Learning Engineer', 'New York, NY', 'Making workforce data more accurate', d('2026-08-01'), None, 0],
        [d('2026-09-01'), 1, 'Revelio Labs', RL_URL, 'Machine Learning Engineer', 'New York, NY', 'Making workforce data more accurate', d('2026-08-01'), None, 0],
        [d('2026-09-01'), 1, 'NYU', NYU_URL, 'Research Assistant', 'New York, NY', 'Research on various NLP models', d('2025-09-01'), d('2026-08-01'), 1],
        [d('2026-07-19'), 1, 'NYU', NYU_URL, 'Research Assistant', 'New York, NY', 'Wrapping up NLP research', d('2025-09-01'), None, 0],
        [d('2026-07-19'), 1, 'NYU', NYU_URL, 'TA', 'NYC', 'TA for data science 101', d('2024-09-01'), d('2025-06-01'), 1],
    ]


def case_b_rows():
    rows = case_a_rows()
    rows[0] = [d('2026-09-16'), 1, 'RL', RL_URL, 'MLE', 'New York, NY', None, d('2026-08-01'), None, 0]
    rows[1] = [d('2026-09-01'), 1, 'Revelio Labs', RL_URL, 'Machine Learning Engineer', 'New York, NY', 'Making workforce data more accurate', d('2026-08-01'), None, 0]
    return rows


def ids_by_title(out):
    return out.groupby('title_raw')['position_id'].nunique().to_dict()


def test_case_a_deleted_positions_are_carried_forward():
    out, _, _ = run(case_a_rows())
    counts = out.groupby('asof_ts').size().to_dict()
    assert counts == {d('2026-07-19'): 2, d('2026-09-01'): 3, d('2026-09-16'): 3}
    assert out['position_id'].nunique() == 3
    assert not out.duplicated(['position_id', 'asof_ts']).any()
    last = out[out['asof_ts'] == d('2026-09-16')].set_index('title_raw')
    assert last.loc['Research Assistant', 'description'] == 'Research on various NLP models'
    assert last.loc['Research Assistant', 'enddate'] == d('2026-08-01')
    assert last.loc['TA', 'description'] == 'TA for data science 101'


def test_case_a_never_uses_the_future():
    out, _, _ = run(case_a_rows())
    first = out[(out['asof_ts'] == d('2026-07-19')) & (out['title_raw'] == 'Research Assistant')]
    assert first['description'].iloc[0] == 'Wrapping up NLP research'
    assert pd.isna(first['enddate'].iloc[0])


def test_case_b_edited_position_is_not_duplicated_and_description_is_kept():
    out, matches, changes = run(case_b_rows())
    assert out['position_id'].nunique() == 3
    last = out[(out['asof_ts'] == d('2026-09-16')) & (out['company_raw'] == 'RL')]
    assert len(last) == 1
    assert last['title_raw'].iloc[0] == 'MLE'
    assert last['description'].iloc[0] == 'Making workforce data more accurate'
    assert 'url + start' in set(matches['tier'])
    kept = changes[(changes['field'] == 'description') & (changes['resolution'] == 'blank, kept old')]
    assert len(kept) == 1


def test_job_that_disappears_and_returns_keeps_its_id():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Other', None, 'Analyst', None, None, d('2021-01-01'), None, 0],
        [d('2026-03-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2
    assert out[out['company_raw'] == 'Acme']['position_id'].nunique() == 1


def test_rehire_with_a_different_start_date_is_a_new_position():
    rows = [
        [d('2026-01-01'), 1, 'ExxonMobil', None, 'Assistant', None, None, d('1985-07-01'), d('1996-08-01'), 0],
        [d('2026-02-01'), 1, 'ExxonMobil', None, 'Assistant', None, None, d('1985-07-01'), d('1996-08-01'), 0],
        [d('2026-02-01'), 1, 'ExxonMobil', None, 'Assistant', None, None, d('2001-06-01'), d('2006-07-01'), 1],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2


def test_cosmetic_changes_match():
    rows = [
        [d('2026-01-01'), 1, 'US Army', None, 'Staff Sergeant', None, None, d('1982-01-01'), None, 0],
        [d('2026-02-01'), 1, 'U.S. Army ', None, 'staff  sergeant', None, None, d('1982-01-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 1


def test_same_start_and_similar_title_catches_a_rename_but_a_different_title_does_not():
    rows = [
        [d('2026-01-01'), 1, 'Oracle', None, 'Senior Consultant', None, None, d('2017-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Oracle Financial Services Software Limited', None, 'Senior Consultant', None, None, d('2017-01-01'), None, 0],
        [d('2026-01-01'), 2, 'Orange and Vision TV', None, 'Senior Producer', None, None, d('2003-01-01'), None, 0],
        [d('2026-02-01'), 2, 'The Walt Disney Company', None, 'Producer | Director', None, None, d('2003-01-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out[out['user_id'] == 1]['position_id'].nunique() == 1
    assert out[out['user_id'] == 2]['position_id'].nunique() == 2


def test_company_only_row_matches_only_when_one_known_position():
    one = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Acme', None, None, None, None, None, None, 0],
    ]
    out, matches, _ = run(one)
    assert out['position_id'].nunique() == 1
    two = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', None, 'Manager', None, None, d('2022-01-01'), None, 1],
        [d('2026-02-01'), 1, 'Acme', None, None, None, None, None, None, 0],
    ]
    out, matches, _ = run(two)
    assert out['position_id'].nunique() == 2
    assert matches['ambiguous_candidates'].max() == 2
    assert 'ignored, adds nothing' in set(matches['tier'])


def test_thin_row_for_an_unknown_company_creates_a_position():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Other', None, None, None, None, None, None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2


def test_thin_rows_do_not_pile_up_ghost_positions():
    base = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', None, 'Manager', None, None, d('2022-01-01'), None, 1],
    ]
    thin = [[d(f'2026-0{m}-01'), 1, 'Acme', None, None, None, None, None, None, 0] for m in range(2, 6)]
    out, _, _ = run(base + thin)
    assert out['position_id'].nunique() == 2


def test_same_job_listed_twice_under_two_company_names_stays_one_position():
    rows = [
        [d('2026-01-01'), 1, 'The Hunger Cafe Brasserie', None, 'Sous Chef', None, None, d('2022-02-01'), None, 0],
        [d('2026-02-01'), 1, 'The Hunger', None, 'Sous Chef', None, None, d('2022-02-01'), None, 0],
        [d('2026-03-01'), 1, 'The Hunger Cafe Brasserie', None, 'Sous Chef', None, None, d('2022-02-01'), None, 0],
        [d('2026-03-01'), 1, 'The Hunger', None, 'Sous Chef', None, None, d('2022-02-01'), None, 1],
    ]
    out, matches, _ = run(rows)
    assert out['position_id'].nunique() == 1
    assert len(out) == 3
    assert 'collapsed duplicate' in set(matches['tier'])


def test_garbled_text_is_repaired_and_does_not_overwrite_good_text():
    good_name = 'İstanbul Yiyecek İçecek Grubu'
    garbled = good_name.encode('utf8').decode('cp1252')
    rows = [
        [d('2026-01-01'), 1, good_name, 'linkedin.com/company/x', 'Stajer', None, None, d('2019-06-01'), None, 0],
        [d('2026-02-01'), 1, garbled, 'linkedin.com/company/x', 'Stajer', None, None, d('2019-06-01'), None, 0],
    ]
    out, _, changes = run(rows)
    assert out['position_id'].nunique() == 1
    assert set(out['company_raw']) == {good_name}
    repaired = changes[changes['resolution'] == 'repaired encoding']
    assert repaired['old_value'].iloc[0] == garbled


def test_duplicate_rows_in_one_snapshot_collapse():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', 'Boston', 'Built things', d('2020-01-01'), None, 1],
    ]
    out, matches, _ = run(rows)
    assert len(out) == 1
    assert out['description'].iloc[0] == 'Built things'
    assert 'collapsed duplicate' in set(matches['tier'])


def test_position_ids_are_stable_between_runs():
    first, _, _ = run(case_a_rows())
    second, _, _ = run(case_a_rows())
    assert first['position_id'].tolist() == second['position_id'].tolist()


def test_row_with_only_company_and_url_does_not_create_a_ghost():
    base = [
        [d('2026-01-01'), 1, 'Acme', RL_URL, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', RL_URL, 'Manager', None, None, d('2022-01-01'), None, 1],
        [d('2026-02-01'), 1, 'Acme', RL_URL, None, None, None, None, None, 0],
    ]
    out, matches, _ = run(base)
    assert out['position_id'].nunique() == 2
    assert 'ignored, adds nothing' in set(matches['tier'])


def test_row_with_only_a_url_matches_the_single_position_at_that_url():
    rows = [
        [d('2026-01-01'), 1, 'Acme', RL_URL, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Acme Corporation', RL_URL, None, None, None, None, None, 0],
    ]
    out, matches, _ = run(rows)
    assert out['position_id'].nunique() == 1
    assert 'company only, one known position' in set(matches['tier'])


def test_row_without_a_title_that_fits_two_positions_is_ignored():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Engineer', None, None, d('2020-01-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', None, 'Manager', None, None, d('2020-01-01'), None, 1],
        [d('2026-02-01'), 1, 'Acme', None, None, None, None, d('2020-01-01'), None, 0],
    ]
    out, matches, _ = run(rows)
    assert out['position_id'].nunique() == 2
    assert 'ignored, adds nothing' in set(matches['tier'])


def test_row_that_matches_newest_values_wins_when_two_rows_claim_one_position():
    rows = [
        [d('2026-01-01'), 1, 'DXC', None, 'Senior Assistant', None, None, d('2022-05-01'), None, 0],
        [d('2026-03-01'), 1, 'DXC', None, 'Infrastructure Analyst', None, None, d('2022-05-01'), None, 0],
        [d('2026-09-01'), 1, 'DXC', None, 'Senior Assistant', None, None, d('2022-05-01'), None, 0],
        [d('2026-09-01'), 1, 'DXC', None, 'Infrastructure Analyst', None, None, d('2022-05-01'), None, 1],
        [d('2026-10-01'), 1, 'DXC', None, 'Senior Assistant', None, None, d('2022-05-01'), None, 0],
        [d('2026-10-01'), 1, 'DXC', None, 'Infrastructure Analyst', None, None, d('2022-05-01'), None, 1],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2
    last = out[out['asof_ts'] == d('2026-10-01')]
    assert len(last) == 2


def test_indistinguishable_copies_do_not_create_more_copies():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, None, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Acme', None, 'Analyst', None, None, d('2020-01-01'), None, 0],
        [d('2026-03-01'), 1, 'Acme', None, 'Analyst', None, None, d('2020-01-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 1


LONG = 'Responsible for planning and delivering large infrastructure programs across the region'


def test_start_date_edit_with_same_description_stays_one_position():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-06-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 1
    assert out.iloc[-1]['startdate'] == d('2020-06-01')


def test_start_date_far_apart_is_a_new_position_even_with_same_description():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2015-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-06-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2


def test_start_edit_needs_the_old_position_in_the_previous_snapshot():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Other Co', None, 'Cook', None, None, d('2019-01-01'), None, 0],
        [d('2026-03-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-06-01'), None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 3


def test_blank_start_with_same_description_and_company_matches_after_a_title_change():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Other Co', None, 'Cook', None, None, d('2019-01-01'), None, 0],
        [d('2026-03-01'), 1, 'Acme', None, 'Senior Analyst', None, LONG, None, None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2


def test_two_rows_with_the_same_description_are_not_merged():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-01-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', None, 'Manager', None, LONG, d('2021-01-01'), None, 1],
        [d('2026-02-01'), 1, 'Acme', None, 'Analyst', None, LONG, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, 'Acme', None, 'Manager', None, LONG, d('2021-01-01'), None, 1],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2


def test_rows_with_only_a_title_do_not_pile_up_new_positions():
    rows = [[d(f'2026-0{month}-01'), 1, None, None, 'Dozentin', None, None, None, None, 0] for month in range(1, 6)]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 1


def test_a_title_only_row_does_not_join_a_position_that_has_a_company():
    rows = [
        [d('2026-01-01'), 1, 'Uni X', None, 'Dozentin', None, None, d('2020-01-01'), None, 0],
        [d('2026-02-01'), 1, None, None, 'Dozentin', None, None, None, None, 0],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 2


def test_same_job_listed_twice_with_and_without_a_start_date_is_one_position():
    rows = [
        [d('2026-01-01'), 1, 'IIP', None, 'Director de proyectos', None, None, d('2022-03-01'), None, 0],
        [d('2026-02-01'), 1, 'IIP', None, 'Director de proyectos', None, None, d('2022-03-01'), None, 0],
        [d('2026-02-01'), 1, 'IIP', None, 'Director de proyectos', None, None, None, None, 1],
    ]
    out, matches, _ = run(rows)
    assert out['position_id'].nunique() == 1
    assert 'collapsed duplicate' in set(matches['tier'])


def test_two_dated_rehires_and_a_blank_start_row_are_not_collapsed_by_guessing():
    rows = [
        [d('2026-01-01'), 1, 'IIP', None, 'Analyst', None, None, d('2015-01-01'), None, 0],
        [d('2026-01-01'), 1, 'IIP', None, 'Analyst', None, None, d('2020-01-01'), None, 1],
        [d('2026-01-01'), 1, 'IIP', None, 'Analyst', None, None, None, None, 2],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 3


def test_blank_title_row_collapses_into_the_one_titled_row_with_same_company_and_start():
    rows = [
        [d('2026-01-01'), 1, 'CommunicationX', None, 'IT Berater', None, None, d('2015-07-01'), None, 0],
        [d('2026-02-01'), 1, 'CommunicationX', None, 'IT Berater', None, None, d('2015-07-01'), None, 0],
        [d('2026-02-01'), 1, 'CommunicationX', None, None, None, None, d('2015-07-01'), None, 1],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 1


def test_blank_title_row_is_not_collapsed_when_two_titles_share_company_and_start():
    rows = [
        [d('2026-01-01'), 1, 'Acme', None, 'Analyst', None, None, d('2015-07-01'), None, 0],
        [d('2026-01-01'), 1, 'Acme', None, 'Manager', None, None, d('2015-07-01'), None, 1],
        [d('2026-01-01'), 1, 'Acme', None, None, None, None, d('2015-07-01'), None, 2],
    ]
    out, _, _ = run(rows)
    assert out['position_id'].nunique() == 3