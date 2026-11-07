import hashlib
import re
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher


@lru_cache(maxsize=200_000)
def text_key(value):
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize('NFKC', value).lower()
    text = re.sub(r"[.'’`]", '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' '.join(text.split()) or None

LEGAL_SUFFIXES = {'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation', 'plc', 'gmbh', 'llp', 'lp'}


@lru_cache(maxsize=200_000)
def company_key(value):
    key = text_key(value)
    if key is None:
        return None
    words = key.split()
    while len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return ' '.join(words)


def url_key(value):
    if not isinstance(value, str):
        return None
    return value.strip().lower().rstrip('/') or None


def titles_similar(first, second, threshold=0.7):
    if first is None or second is None:
        return False
    if first.startswith(second) or second.startswith(first):
        return True
    return SequenceMatcher(None, first, second).ratio() >= threshold


@lru_cache(maxsize=200_000)
def repair_text(value):
    if not isinstance(value, str) or value.isascii():
        return value
    for encoding in ('cp1252', 'latin1'):
        try:
            return value.encode(encoding).decode('utf8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return value


MIN_DESCRIPTION_LENGTH = 40


def description_key(text):
    if not isinstance(text, str):
        return None
    normalized = ' '.join(text.lower().split())
    if len(normalized) < MIN_DESCRIPTION_LENGTH:
        return None
    return int.from_bytes(hashlib.blake2b(normalized.encode(), digest_size=8).digest(), 'big')