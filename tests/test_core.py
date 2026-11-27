"""Offline unit tests: evaluation metrics, the brand acceptance simulator and creator utility.

No API calls. The app and scripts import each other as top-level modules, so their folders go on sys.path.
"""
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(HERE, "..", "deal_darwin_dataset")
sys.path.insert(0, os.path.join(DATASET, "scripts"))
sys.path.insert(0, os.path.join(DATASET, "app"))

import common  # noqa: E402
import evaluate  # noqa: E402
import evidence  # noqa: E402

GRID = list(common.iter_grid())


# --- evaluation metrics -----------------------------------------------------
def test_rank_averages_ties():
    assert evaluate.rank([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_perfect_and_inverse():
    assert evaluate.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert evaluate.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_constant_input_is_zero():
    assert evaluate.spearman([1, 1, 1], [1, 2, 3]) == 0.0


def test_auc_perfect_random_and_undefined():
    assert evaluate.auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert evaluate.auc([1, 0], [0.5, 0.5]) == 0.5
    assert math.isnan(evaluate.auc([1, 1], [0.3, 0.4]))


# --- brand acceptance simulator ---------------------------------------------
def test_grid_size_matches_cartesian_product():
    expected = math.prod(len(v) for v in common.GRID.values())
    assert len(GRID) == expected


@pytest.mark.parametrize("brand", list(common.BRANDS))
def test_brand_eval_probabilities_and_red_lines(brand):
    for o in GRID:
        e = common.brand_eval(brand, o)
        assert 0.0 <= e["p_accept"] <= 1.0
        if e["red_lines"]:
            assert e["accept"] == 0
            assert e["p_accept"] == common.RED_P
        else:
            assert e["accept"] == int(e["p_accept"] >= 0.5)


# --- creator utility --------------------------------------------------------
@pytest.mark.parametrize("persona", list(common.PERSONAS))
def test_creator_utility_bounds_and_red_lines(persona):
    for o in GRID:
        u = common.creator_utility(persona, o)
        assert 0.0 <= u <= 1.0 + 1e-9
        if common.creator_red_lines(persona, o):
            assert u == 0.0


@pytest.mark.parametrize("persona", list(common.PERSONAS))
def test_higher_fee_never_lowers_utility(persona):
    base = dict(usage_months=6, excl_months=0, net_days=30, kill_pct=25, revisions=2)
    fees = sorted(common.GRID["fee_mult"])
    utils = [common.creator_utility(persona, {**base, "fee_mult": f}) for f in fees]
    assert utils == sorted(utils)


# --- evidence tab reads only files on disk ----------------------------------
def test_evidence_has_all_sections():
    ev = evidence.evidence()
    assert set(ev) == {"extraction", "counters", "creative", "cost"}
