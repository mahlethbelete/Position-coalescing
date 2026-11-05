from difflib import SequenceMatcher

WEIGHTS = {'company': 0.30, 'title': 0.30, 'start': 0.25, 'description': 0.15}
MIN_EVIDENCE = 0.55
MAX_START_GAP_MONTHS = 12


def months_apart(first, second):
    return abs((first.year - second.year) * 12 + first.month - second.month)


def text_similarity(value, options):
    if value is None or not options:
        return None
    return max(1.0 if value == option else SequenceMatcher(None, value, option).ratio() for option in options)


def company_similarity(row, position):
    if row['url_key'] is not None and row['url_key'] in position.urls:
        return 1.0
    return text_similarity(row['company_key'], position.companies)


def start_similarity(row, position):
    if row['start'] is None or position.start is None:
        return None
    gap = months_apart(row['start'], position.start)
    if gap > MAX_START_GAP_MONTHS:
        return False
    return 1.0 - gap / (MAX_START_GAP_MONTHS + 1)


def description_similarity(row, position):
    if row['desc_key'] is not None and row['desc_key'] in position.descs:
        return 1.0
    return None


def score(row, position):
    start = start_similarity(row, position)
    if start is False:
        return None
    parts = {'company': company_similarity(row, position), 'title': text_similarity(row['title_key'], position.titles),
             'start': start, 'description': description_similarity(row, position)}
    present = {name: value for name, value in parts.items() if value is not None}
    weight = sum(WEIGHTS[name] for name in present)
    if weight < MIN_EVIDENCE:
        return None
    return sum(WEIGHTS[name] * value for name, value in present.items()) / weight


def best_candidate(row, candidates, threshold, margin):
    scored = []
    for position in candidates:
        value = score(row, position)
        if value is not None:
            scored.append((value, position.position_id, position))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored or scored[0][0] < threshold:
        return None, scored
    if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
        return None, scored
    return scored[0][2], scored