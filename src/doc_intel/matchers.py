"""Normalisers, matchers and outcome classification for the CUAD evals.

Every field goes through the same three steps:
  1. normalise the extracted value and the ground-truth value to the same shape
  2. decide whether each side is "absent"
  3. classify the pair as TP / FP / FN / TN
"""
from __future__ import annotations

import ast
import re
from datetime import date

import pandas as pd


# --------------------------------------------------------------------------
# Absence
# --------------------------------------------------------------------------
def is_absent(value) -> bool:
    """One definition of 'not in the contract' for every field type."""
    if value is None or value is False:
        return True
    if isinstance(value, (str, set, frozenset, list, tuple, dict)):
        return len(value) == 0
    try:
        return bool(pd.isna(value))  # NaN, NaT, pd.NA
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Normalisers: raw value -> comparable value (or None / empty when absent)
# --------------------------------------------------------------------------
def norm_date(value) -> date | str | None:
    """Full dates become datetime.date. Partial dates such as '03/[]/1999'
    stay as a string, so they are 'present' but never equal a full date."""
    if is_absent(value):
        return None
    text = str(value).strip()
    try:
        return pd.to_datetime(text).date()
    except (ValueError, TypeError):
        return text


_LAW_NOISE = re.compile(r"\b(the|state|province|commonwealth|laws?|of)\b")


def norm_law(value) -> frozenset[str]:
    """'England, United Kingdom; Wales, United Kingdom' -> {'england', 'wales'}
    'England and Wales' -> {'england', 'wales'};  'Ontario, Canada' -> {'ontario'}

    ASSUMPTION: the label separates jurisdictions with ';' and writes each one
    as 'Place, Country'. Print a few raw values to confirm before trusting it.
    """
    if is_absent(value):
        return frozenset()
    places = set()
    for entry in re.split(r";|\band\b|&|\bor\b", str(value).lower()):
        place = entry.split(",")[0]  # drop the country suffix
        place = _LAW_NOISE.sub(" ", place)
        place = re.sub(r"[^\w\s]", "", place)
        place = " ".join(place.split())
        if place:
            places.add(place)
    return frozenset(places)


_TRUE = {"yes", "true", "1", "y", "t"}
_FALSE = {"no", "false", "0", "n", "f"}


def norm_bool(value) -> bool:
    """Raises on anything unexpected instead of quietly returning False."""
    if is_absent(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"Unexpected boolean label: {value!r}")


def _clean_party(name: str) -> str:
    name = re.sub(r"\(.*?\)", " ", str(name))  # drop inline aliases: (“Chase”)
    name = re.sub(r"[^\w\s]", "", name.lower())
    return " ".join(name.split())


def norm_parties(value) -> frozenset[str]:
    """Accepts a real list (from the extraction JSON) or the string form of a
    Python list (the raw 'Parties' column in master_clauses.csv)."""
    if is_absent(value):
        return frozenset()
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
    else:
        text = str(value).strip()
        if text.startswith("["):
            items = ast.literal_eval(text)  # handles apostrophes and commas safely
        else:
            items = text.split(";")  # never split on ',' -- 'Chase Bank USA, N.A.'
    return frozenset(c for c in (_clean_party(i) for i in items) if c)


def norm_text(value) -> str:
    if is_absent(value):
        return ""
    return " ".join(str(value).lower().split())


# --------------------------------------------------------------------------
# Matchers: both sides are present and normalised -- are they the same?
# --------------------------------------------------------------------------
def exact(ext, truth) -> bool:
    return ext == truth


def loose_text(ext: str, truth: str) -> bool:
    """Temporary matcher for renewal_term until the schema is structured."""
    return ext in truth or truth in ext


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
def classify(ext, truth, matches=exact) -> list[str]:
    """Outcome(s) for one single-valued field in one contract.
    A wrong value is BOTH a false positive and a false negative."""
    ext_present, truth_present = not is_absent(ext), not is_absent(truth)
    if not ext_present and not truth_present:
        return ["TN"]
    if ext_present and not truth_present:
        return ["FP"]
    if truth_present and not ext_present:
        return ["FN"]
    return ["TP"] if matches(ext, truth) else ["FP", "FN"]


def classify_set(ext: frozenset, truth: frozenset) -> list[str]:
    """Outcome(s) for a multi-valued field, scored per item:
    each shared item is a TP, each extra an FP, each missed an FN."""
    if not ext and not truth:
        return ["TN"]
    return (
        ["TP"] * len(ext & truth)
        + ["FP"] * len(ext - truth)
        + ["FN"] * len(truth - ext)
    )