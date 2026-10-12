"""Run with:  pytest evals/   -- every case here is a value seen in run_v1."""
from datetime import date

import pytest

from doc_intel.matchers import (
    classify, classify_set, is_absent, loose_text,
    norm_bool, norm_date, norm_law, norm_parties,
)


@pytest.mark.parametrize("value", [None, float("nan"), "", [], set(), frozenset(), False])
def test_absent(value):
    assert is_absent(value)


@pytest.mark.parametrize("value", ["x", True, 0, date(2007, 4, 6), frozenset({"a"})])
def test_present(value):
    assert not is_absent(value)


# --- the bug that inflated TP: False/False is a true negative ---
def test_bool_both_false_is_tn():
    assert classify(norm_bool(False), norm_bool("No")) == ["TN"]


def test_bool_outcomes():
    assert classify(norm_bool(True), norm_bool("Yes")) == ["TP"]
    assert classify(norm_bool(False), norm_bool("Yes")) == ["FN"]
    assert classify(norm_bool(True), norm_bool("No")) == ["FP"]


def test_bool_rejects_surprises():
    with pytest.raises(ValueError):
        norm_bool("maybe")


def test_wrong_value_is_fp_and_fn():
    assert classify(norm_law("Illinois"), norm_law("New York")) == ["FP", "FN"]


def test_dates():
    assert norm_date("April 6, 2007") == norm_date("2007-04-06") == date(2007, 4, 6)
    assert classify(norm_date("1999-09-30"), norm_date(float("nan"))) == ["FP"]
    # blank day in the contract: an invented full date must not match
    assert classify(norm_date("1999-03-01"), norm_date("03/[]/1999")) == ["FP", "FN"]


def test_governing_law():
    assert norm_law("State of Delaware") == norm_law("Delaware")
    assert norm_law("Ontario") == norm_law("Ontario, Canada")
    assert norm_law("England and Wales") == norm_law("England, United Kingdom; Wales, United Kingdom")
    assert norm_law("New York") == frozenset({"new york"})
    # Ebix: two jurisdictions in the label, one extracted -> still wrong
    assert classify(norm_law("Illinois"), norm_law("Illinois; New York")) == ["FP", "FN"]


def test_parties():
    truth = norm_parties("""['Chase Bank USA, N.A. (?Chase?)', 'you as an "Affiliate"']""")
    ext = norm_parties(["Chase Bank USA, N.A.", 'you as an "Affiliate"'])
    assert truth == ext == frozenset({"chase bank usa na", "you as an affiliate"})
    assert norm_parties("['O\\'Brien Ltd']") == frozenset({"obrien ltd"})


def test_parties_scored_per_item():
    ext = frozenset({"ishipcom inc", "mail boxes etc usa inc"})
    truth = frozenset({"ishipcom inc", "mail boxes etc usa inc", "mbe"})
    assert sorted(classify_set(ext, truth)) == ["FN", "TP", "TP"]
    assert classify_set(frozenset(), frozenset()) == ["TN"]


def test_renewal_loose():
    assert classify("", "") == ["TN"]
    assert classify("successive 1 year", "successive 1 year", loose_text) == ["TP"]
    assert classify("renews for twelve months", "successive 1 year", loose_text) == ["FP", "FN"]