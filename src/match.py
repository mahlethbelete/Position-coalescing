import hashlib
from itertools import groupby
from dataclasses import dataclass, field

import pandas as pd

from src.keys import (
    company_key,
    description_key,
    repair_text,
    text_key,
    titles_similar,
    url_key,
)

VALUE_FIELDS = [
    "company_raw",
    "company_linkedin_url",
    "title_raw",
    "location_raw",
    "description",
    "startdate",
    "enddate",
]
TEXT_FIELDS = ["company_raw", "title_raw", "location_raw", "description"]
RECORD_COLUMNS = VALUE_FIELDS + ["start_dt", "observed_ts", "user_id"]
MAX_START_EDIT_MONTHS = 12
LATE_REASON = "older than the last processed snapshot"
LATE_COLUMNS = ["user_id", "observed_ts", "rows_in_input", "reason"]
OUTPUT_COLUMNS = [
    "asof_ts",
    "user_id",
    "company_raw",
    "company_linkedin_url",
    "title_raw",
    "location_raw",
    "description",
    "startdate",
    "enddate",
    "position_id",
]
MATCH_COLUMNS = [
    "user_id",
    "observed_ts",
    "row_id",
    "position_id",
    "tier",
    "ambiguous_candidates",
]
CHANGE_COLUMNS = [
    "user_id",
    "asof_ts",
    "position_id",
    "field",
    "old_value",
    "new_value",
    "resolution",
]


@dataclass
class Position:
    position_id: int
    values: dict
    start: object
    companies: set = field(default_factory=set)
    titles: set = field(default_factory=set)
    pairs: set = field(default_factory=set)
    urls: set = field(default_factory=set)
    current: tuple = (None, None)
    created: int = 0
    descs: set = field(default_factory=set)
    last_seen: int = -1


class UserIndex:
    def __init__(self):
        self.positions = []
        self.by_pair, self.by_company, self.by_url, self.by_start, self.by_desc = (
            {},
            {},
            {},
            {},
            {},
        )
        self.by_title = {}
        self.snapshots, self.last_ts = 0, None

    def add(self, position, row):
        self.positions.append(position)
        if position.start is not None:
            self.by_start.setdefault(position.start, {})[
                position.position_id
            ] = position
        self.learn(position, row)

    def learn(self, position, row):
        position_id = position.position_id
        company, title, url = row["company_key"], row["title_key"], row["url_key"]
        if company and company not in position.companies:
            position.companies.add(company)
            self.by_company.setdefault(company, {})[position_id] = position
        if title and title not in position.titles:
            position.titles.add(title)
            self.by_title.setdefault(title, {})[position_id] = position
        if company and title and (company, title) not in position.pairs:
            position.pairs.add((company, title))
            self.by_pair.setdefault((company, title), {})[position_id] = position
        if url and url not in position.urls:
            position.urls.add(url)
            self.by_url.setdefault(url, {})[position_id] = position
        desc = row["desc_key"]
        if desc and desc not in position.descs:
            position.descs.add(desc)
            self.by_desc.setdefault(desc, {})[position_id] = position

    def set_start(self, position, start):
        if position.start is not None:
            self.by_start[position.start].pop(position.position_id, None)
        position.start = start
        self.by_start.setdefault(start, {})[position.position_id] = position

    def knows_company(self, row):
        return row["company_key"] in self.by_company or row["url_key"] in self.by_url


def is_blank(value):
    if isinstance(value, str):
        return value.strip() == ""
    if value is None or value is pd.NaT:
        return True
    if isinstance(value, float):
        return value != value
    return pd.isna(value)


def same_start(row, position):
    return (
        row["start"] is not None
        and position.start is not None
        and row["start"] == position.start
    )


def matches_newest_values(row, position):
    return same_start(row, position) and position.current == (
        row["company_key"],
        row["title_key"],
    )


def narrow_candidates(row, found):
    exact = [position for position in found if matches_newest_values(row, position)]
    if len(exact) == 1:
        return exact
    if len(exact) > 1:
        return [min(exact, key=lambda position: position.created)]
    return found


def by_company_title_start(row, position):
    return (
        same_start(row, position)
        and (row["company_key"], row["title_key"]) in position.pairs
    )


def by_company_start(row, position):
    return same_start(row, position) and row["company_key"] in position.companies


def by_url_start(row, position):
    return same_start(row, position) and row["url_key"] in position.urls


def by_company_title_missing_start(row, position):
    one_missing = row["start"] is None or position.start is None
    return one_missing and (row["company_key"], row["title_key"]) in position.pairs


def by_start_similar_title(row, position):
    return same_start(row, position) and any(
        titles_similar(row["title_key"], title) for title in position.titles
    )


def months_apart(first, second):
    return abs((first.year - second.year) * 12 + first.month - second.month)


def by_description_same_start(row, position):
    return same_start(row, position) and row["desc_key"] in position.descs


def by_description_missing_start(row, position):
    one_missing = row["start"] is None or position.start is None
    shares = (
        row["company_key"] in position.companies
        or row["url_key"] in position.urls
        or row["title_key"] in position.titles
    )
    return one_missing and row["desc_key"] in position.descs and shares


def by_description_start_edit(row, position):
    both = row["start"] is not None and position.start is not None
    return (
        both
        and row["start"] != position.start
        and months_apart(row["start"], position.start) <= MAX_START_EDIT_MONTHS
        and (row["company_key"], row["title_key"]) in position.pairs
        and row["desc_key"] in position.descs
        and position.last_seen == row["step"] - 1
    )


def by_title_only(row, position):
    row_has_only_title = (
        row["company_key"] is None and row["url_key"] is None and row["start"] is None
    )
    return row_has_only_title and not position.companies and not position.urls


def by_company_only(row, position):
    has_nothing_else = row["title_key"] is None and row["start"] is None
    return has_nothing_else and (
        row["company_key"] in position.companies or row["url_key"] in position.urls
    )


def near_pair(row, index):
    return index.by_pair.get((row["company_key"], row["title_key"]), {}).values()


def near_company(row, index):
    return index.by_company.get(row["company_key"], {}).values()


def near_url(row, index):
    return index.by_url.get(row["url_key"], {}).values()


def near_title(row, index):
    return index.by_title.get(row["title_key"], {}).values()


def near_description(row, index):
    return index.by_desc.get(row["desc_key"], {}).values()


def near_start(row, index):
    return index.by_start.get(row["start"], {}).values()


def near_company_or_url(row, index):
    return {
        **index.by_company.get(row["company_key"], {}),
        **index.by_url.get(row["url_key"], {}),
    }.values()


TIERS = [
    ("company + title + start", near_pair, by_company_title_start, False),
    ("company + start", near_company, by_company_start, False),
    ("url + start", near_url, by_url_start, False),
    (
        "company + title, a start missing",
        near_pair,
        by_company_title_missing_start,
        False,
    ),
    ("same start + similar title", near_start, by_start_similar_title, False),
    (
        "same start + same description",
        near_description,
        by_description_same_start,
        False,
    ),
    (
        "start missing + same description",
        near_description,
        by_description_missing_start,
        False,
    ),
    (
        "start edited + same description",
        near_description,
        by_description_start_edit,
        False,
    ),
    ("title only, no company or start", near_title, by_title_only, False),
    ("company only, one known position", near_company_or_url, by_company_only, True),
]


def prepare_rows(records):
    rows = []
    for record in records:
        values, repairs = {}, []
        for name in VALUE_FIELDS:
            value = None if is_blank(record[name]) else record[name]
            if name in TEXT_FIELDS and value is not None:
                fixed = repair_text(value)
                if fixed != value:
                    repairs.append((name, value, fixed))
                    value = fixed
            values[name] = value
        start = record["start_dt"]
        rows.append(
            {
                "i": record["row_id"],
                "values": values,
                "repairs": repairs,
                "company_key": company_key(values["company_raw"]),
                "title_key": text_key(values["title_raw"]),
                "url_key": url_key(values["company_linkedin_url"]),
                "desc_key": description_key(values["description"]),
                "start": None if pd.isna(start) else start,
                "completeness": sum(value is not None for value in values.values()),
            }
        )
    return rows


def adds_nothing(row, index, ambiguous):
    if row["title_key"] is not None:
        return False
    if ambiguous.get(row["i"], 0) > 0:
        return True
    return row["start"] is None and index.knows_company(row)


def completeness(row):
    return row["completeness"]


def collapse_duplicates(rows):
    dated = {}
    for row in rows:
        if row["start"] is not None and row["company_key"] and row["title_key"]:
            dated.setdefault((row["company_key"], row["title_key"]), set()).add(
                row["start"]
            )
    titled = {}
    for row in rows:
        if row["start"] is not None and row["company_key"] and row["title_key"]:
            titled.setdefault((row["company_key"], row["start"]), set()).add(
                row["title_key"]
            )
    groups, order = {}, []
    for row in rows:
        if row["company_key"] or row["title_key"]:
            start, title = row["start"], row["title_key"]
            twins = dated.get((row["company_key"], title), ())
            if start is None and len(twins) == 1:
                start = next(iter(twins))
            if title is None and start is not None and row["company_key"]:
                titles = titled.get((row["company_key"], start), ())
                if len(titles) == 1:
                    title = next(iter(titles))
            key = (row["company_key"], title, start)
        else:
            key = ("single", row["i"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    kept, collapsed = [], []
    for key in order:
        survivor = max(
            groups[key], key=lambda row: (row["start"] is not None, completeness(row))
        )
        kept.append(survivor)
        collapsed += [(row, survivor) for row in groups[key] if row is not survivor]
    return kept, collapsed


def same_job(rows):
    first = rows[0]
    return first["title_key"] is not None and all(
        row["title_key"] == first["title_key"] and row["start"] == first["start"]
        for row in rows
    )


def run_tier(name, near, predicate, scope_all, rows, index, assigned, taken, ambiguous):
    free_rows = [row for row in rows if row["i"] not in assigned]
    if not free_rows:
        return
    candidates, claimed_by, by_id = {}, {}, {}
    for row in free_rows:
        found = [
            p
            for p in near(row, index)
            if (scope_all or p.position_id not in taken) and predicate(row, p)
        ]
        if len(found) > 1:
            found = narrow_candidates(row, found)
        candidates[row["i"]] = found
        for position in found:
            claimed_by.setdefault(position.position_id, []).append(row)
            by_id[position.position_id] = position

    def mark_ambiguous(claimers):
        for row in claimers:
            ambiguous[row["i"]] = max(
                ambiguous.get(row["i"], 0), len(candidates[row["i"]]), 2
            )

    for position_id, claimers in claimed_by.items():
        only_this = all(len(candidates[row["i"]]) == 1 for row in claimers)
        if position_id in taken or not only_this:
            mark_ambiguous(claimers)
            continue
        if len(claimers) > 1 and not same_job(claimers):
            exact = [
                row
                for row in claimers
                if matches_newest_values(row, by_id[position_id])
            ]
            if len(exact) != 1:
                mark_ambiguous(claimers)
                continue
            for row in claimers:
                if row is not exact[0]:
                    candidates[row["i"]] = []
            claimers = exact
        winner = max(claimers, key=completeness)
        assigned[winner["i"]] = (by_id[position_id], name)
        for row in claimers:
            if row is not winner:
                assigned[row["i"]] = (by_id[position_id], "collapsed duplicate")
        taken.add(position_id)


def apply_row(position, row, index, user_id, ts, changes):
    for name in VALUE_FIELDS:
        old, new = position.values[name], row["values"][name]
        if new is None and old is not None:
            resolution = "blank, kept old"
        elif new is not None and old is None:
            resolution = "filled"
        elif new is not None and old != new:
            resolution = "newest wins"
        else:
            continue
        changes.append(
            {
                "user_id": user_id,
                "asof_ts": ts,
                "position_id": position.position_id,
                "field": name,
                "old_value": str(old),
                "new_value": str(new),
                "resolution": resolution,
            }
        )
        if new is not None:
            position.values[name] = new
    if row["start"] is not None and row["start"] != position.start:
        index.set_start(position, row["start"])
    index.learn(position, row)
    if row["company_key"] and row["title_key"]:
        position.current = (row["company_key"], row["title_key"])


def new_position(user_id, ts, row, count):
    text = (
        f"{user_id}|{ts}|{row['company_key']}|{row['title_key']}|{row['start']}|{count}"
    )
    position_id = (
        int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big")
        >> 1
    )
    return Position(
        position_id,
        dict(row["values"]),
        row["start"],
        current=(row["company_key"], row["title_key"]),
        created=count,
    )


def coalesce_user(user_id, records, index):
    output, matches, changes, late = [], [], [], []
    for ts, snapshot in groupby(records, key=lambda record: record["observed_ts"]):
        if index.last_ts is not None and ts <= index.last_ts:
            late.append([user_id, ts, len(list(snapshot)), LATE_REASON])
            continue
        step = index.snapshots
        rows, collapsed = collapse_duplicates(prepare_rows(list(snapshot)))
        for row in rows:
            row["step"] = step
        assigned, taken, ambiguous = {}, set(), {}
        for name, near, predicate, scope_all in TIERS:
            run_tier(
                name,
                near,
                predicate,
                scope_all,
                rows,
                index,
                assigned,
                taken,
                ambiguous,
            )

        position_of = {}
        for row in rows:
            if row["i"] in assigned:
                position, tier = assigned[row["i"]]
                if tier != "collapsed duplicate":
                    apply_row(position, row, index, user_id, ts, changes)
            elif adds_nothing(row, index, ambiguous):
                matches.append(
                    [
                        user_id,
                        ts,
                        row["i"],
                        None,
                        "ignored, adds nothing",
                        ambiguous.get(row["i"], 0),
                    ]
                )
                continue
            else:
                position, tier = (
                    new_position(user_id, ts, row, len(index.positions)),
                    "new position",
                )
                index.add(position, row)
            position.last_seen = step
            position_of[row["i"]] = position.position_id
            for name, original, fixed in row["repairs"]:
                changes.append(
                    {
                        "user_id": user_id,
                        "asof_ts": ts,
                        "position_id": position.position_id,
                        "field": name,
                        "old_value": original,
                        "new_value": fixed,
                        "resolution": "repaired encoding",
                    }
                )
            matches.append(
                [
                    user_id,
                    ts,
                    row["i"],
                    position.position_id,
                    tier,
                    ambiguous.get(row["i"], 0),
                ]
            )
        for row, survivor in collapsed:
            matches.append(
                [
                    user_id,
                    ts,
                    row["i"],
                    position_of.get(survivor["i"]),
                    "collapsed duplicate",
                    0,
                ]
            )

        for position in index.positions:
            output.append(
                {
                    "asof_ts": ts,
                    "user_id": user_id,
                    **position.values,
                    "position_id": position.position_id,
                }
            )
        index.snapshots += 1
        index.last_ts = ts
    return output, matches, changes, late


def to_records(good):
    ordered = good.sort_values(
        ["user_id", "observed_dt", "order_in_profile"], kind="stable"
    )
    frame = ordered[RECORD_COLUMNS]
    columns = [frame[name].tolist() for name in RECORD_COLUMNS]
    records = [dict(zip(RECORD_COLUMNS, values)) for values in zip(*columns)]
    for record, row_id in zip(records, ordered.index):
        record["row_id"] = row_id
    return records


def coalesce_with_state(good, states):
    output, matches, changes, late = [], [], [], []
    for user_id, user_records in groupby(
        to_records(good), key=lambda record: record["user_id"]
    ):
        index = states.get(user_id) or UserIndex()
        user_output, user_matches, user_changes, user_late = coalesce_user(
            user_id, list(user_records), index
        )
        states[user_id] = index
        output += user_output
        matches += user_matches
        changes += user_changes
        late += user_late
    match_log = pd.DataFrame(matches, columns=MATCH_COLUMNS, dtype=object)
    match_log["position_id"] = pd.array(
        match_log["position_id"].tolist(), dtype="Int64"
    )
    match_log = match_log.astype({"row_id": "int64", "ambiguous_candidates": "int64"})
    return (
        pd.DataFrame(output, columns=OUTPUT_COLUMNS),
        match_log,
        pd.DataFrame(changes, columns=CHANGE_COLUMNS),
        pd.DataFrame(late, columns=LATE_COLUMNS),
    )


def coalesce(good):
    output, match_log, change_log, _ = coalesce_with_state(good, {})
    return output, match_log, change_log
