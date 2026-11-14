"""Shared definitions for the Deal Darwin synthetic dataset.

Everything here is fictional. Brands, creators and contracts are invented.
The brand acceptance simulator below is the ground truth for offer labels.
"""
import csv
import itertools
import json
import math
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SEED = 255

USAGE_PERPETUAL = 999   # sentinel: perpetual usage rights
REV_UNLIMITED = 99      # sentinel: unlimited revisions

K = 2.0                       # logistic steepness
B0 = math.log(4) / K          # bias: an offer exactly at the brand's norms gets p = 0.80
RED_P = 0.02                  # probability assigned when a red line is crossed


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def path(*parts):
    return os.path.join(ROOT, *parts)


# --------------------------------------------------------------------------
# Brands (fictional). "norms" = standard terms. "red" = hard limits that are
# stated in plain language in each brand's playbook PDF. "weights" = how much
# each term matters to the brand when it weighs a package as a whole.
# --------------------------------------------------------------------------
BRANDS = {
    "northwind": dict(
        id="northwind",
        name="Northwind Athletics",
        legal="Northwind Athletics, Inc.",
        sector="Athletic footwear and apparel",
        city="Portland, OR",
        category_text="athletic footwear and apparel",
        norms=dict(usage_months=12, excl_months=3, net_days=30, kill_pct=25, revisions=2),
        weights=dict(fee=1.0, usage=0.8, excl=0.5, pay=0.3, kill=0.3, rev=0.3),
        red=dict(max_fee_mult=1.3, min_usage=6, min_excl=3, min_net=30, max_kill=25, min_rev=2),
        priority_order="fee, usage rights, exclusivity, then payment timing, kill fee and revisions",
        about=("Northwind Athletics makes running shoes and training apparel for everyday runners "
               "and student athletes. Our partnerships team works with creators between 10,000 and "
               "150,000 followers and runs about forty creator campaigns a year."),
    ),
    "vela": dict(
        id="vela",
        name="Vela Beauty",
        legal="Vela Beauty Collective LLC",
        sector="Direct-to-consumer skincare and beauty",
        city="Los Angeles, CA",
        category_text="beauty, skincare and personal care",
        norms=dict(usage_months=12, excl_months=6, net_days=45, kill_pct=15, revisions=3),
        weights=dict(fee=0.7, usage=1.2, excl=0.9, pay=0.2, kill=0.3, rev=0.4),
        red=dict(max_fee_mult=1.5, min_usage=6, min_excl=3, min_net=30, max_kill=25, min_rev=2),
        priority_order="usage rights, exclusivity, fee, then revisions, kill fee and payment timing",
        about=("Vela Beauty sells skincare and cosmetics online. Most of our spend goes into paid "
               "social ads built on creator content, so usage rights and category exclusivity "
               "matter more to us than almost anything else."),
    ),
    "kettle": dict(
        id="kettle",
        name="Kettle & Co",
        legal="Kettle and Company Foods, Inc.",
        sector="Packaged snacks and drinks (early-stage startup)",
        city="Austin, TX",
        category_text="packaged snacks and drinks",
        norms=dict(usage_months=6, excl_months=0, net_days=15, kill_pct=10, revisions=2),
        weights=dict(fee=1.4, usage=0.4, excl=0.3, pay=0.8, kill=0.5, rev=0.2),
        red=dict(max_fee_mult=1.15, min_usage=3, min_excl=0, min_net=15, max_kill=25, min_rev=1),
        priority_order="fee, payment timing, kill fee, then usage rights, exclusivity and revisions",
        about=("Kettle & Co is a small snack startup with a tight creator budget. We pay quickly, "
               "ask for modest usage rights and do not require exclusivity, but we cannot stretch "
               "far on fee."),
    ),
}

BRAND_ORDER = ["northwind", "vela", "kettle"]

# --------------------------------------------------------------------------
# Creators (fictional) and creator preference personas
# --------------------------------------------------------------------------
CREATORS = {
    "maya_okafor": dict(name="Maya Okafor", handle="@mayamoves", niche="Track and field student-athlete",
                        platform="Instagram", followers=41200, baseline_fee=4000,
                        package="3 Instagram Reels + 2 Story sets",
                        address="48 Linden Way, San Jose, CA 95112"),
    "priya_nair": dict(name="Priya Nair", handle="@priyaglows", niche="Beauty and skincare",
                       platform="Instagram", followers=88500, baseline_fee=6000,
                       package="2 Reels + 1 carousel + 3 Story frames",
                       address="915 Harbor Street, Oakland, CA 94607"),
    "jordan_lee": dict(name="Jordan Lee", handle="@jordaneats", niche="Food and snacks",
                       platform="TikTok", followers=23700, baseline_fee=2500,
                       package="2 TikToks + 1 Reel",
                       address="22 Cedar Court, Sacramento, CA 95814"),
    "diego_ramirez": dict(name="Diego Ramirez", handle="@diegoruns", niche="Running and lifestyle",
                          platform="Instagram", followers=31900, baseline_fee=3200,
                          package="2 Reels + 3 Story frames",
                          address="310 Mission Avenue, Santa Cruz, CA 95060"),
}

PERSONAS = {
    "rights_protective": dict(fee=0.20, usage=0.30, excl=0.20, pay=0.10, kill=0.10, rev=0.10),
    "cash_first": dict(fee=0.40, usage=0.10, excl=0.05, pay=0.25, kill=0.10, rev=0.10),
    "balanced": dict(fee=0.25, usage=0.20, excl=0.15, pay=0.15, kill=0.15, rev=0.10),
}

GRID = dict(
    fee_mult=[0.9, 1.0, 1.15, 1.3, 1.5],
    usage_months=[3, 6, 12, 24, USAGE_PERPETUAL],
    excl_months=[0, 3, 6, 12],
    net_days=[15, 30, 45, 60, 90],
    kill_pct=[0, 10, 25, 50],
    revisions=[1, 2, 4, REV_UNLIMITED],
)
OFFER_KEYS = list(GRID.keys())


def iter_grid():
    for combo in itertools.product(*[GRID[k] for k in OFFER_KEYS]):
        yield dict(zip(OFFER_KEYS, combo))


# --------------------------------------------------------------------------
# Brand acceptance simulator
# --------------------------------------------------------------------------
def brand_eval(brand_id, o):
    """Return the simulated brand's reaction to offer o (a dict with OFFER_KEYS)."""
    b = BRANDS[brand_id]
    n, w, r = b["norms"], b["weights"], b["red"]
    usage = 60 if o["usage_months"] >= USAGE_PERPETUAL else o["usage_months"]
    rev = 8 if o["revisions"] >= REV_UNLIMITED else o["revisions"]
    s = {
        "fee": clip((1.0 - o["fee_mult"]) / 0.3, -1.0, 1.0),
        "usage": clip((usage - n["usage_months"]) / 12.0, -1.0, 2.0),
        "excl": clip((o["excl_months"] - n["excl_months"]) / 6.0, -1.0, 2.0),
        "pay": clip((o["net_days"] - n["net_days"]) / 30.0, -1.0, 2.0),
        "kill": clip((n["kill_pct"] - o["kill_pct"]) / 25.0, -1.0, 1.0),
        "rev": clip((rev - n["revisions"]) / 2.0, -1.0, 2.0),
    }
    margin = sum(w[k] * s[k] for k in s)  # positive = package favours the brand
    reds = []
    if r["max_fee_mult"] is not None and o["fee_mult"] > r["max_fee_mult"] + 1e-9:
        reds.append("fee")
    if usage < r["min_usage"]:
        reds.append("usage")
    if o["excl_months"] < r["min_excl"]:
        reds.append("exclusivity")
    if o["net_days"] < r["min_net"]:
        reds.append("payment")
    if o["kill_pct"] > r["max_kill"]:
        reds.append("kill_fee")
    if o["revisions"] < r["min_rev"]:
        reds.append("revisions")
    p = RED_P if reds else sigmoid(K * (margin + B0))
    return dict(p_accept=round(p, 4), accept=int((not reds) and p >= 0.5),
                red_lines="|".join(reds), margin=round(margin, 4))


# --------------------------------------------------------------------------
# Creator utility (what the creator gains from an offer, 0..1)
# --------------------------------------------------------------------------
def g_fee(m):
    return clip((m - 0.9) / 0.6, 0.0, 1.0)


def g_usage(m):
    return 0.0 if m >= USAGE_PERPETUAL else clip(1 - math.log2(max(m, 3) / 3.0) / 3.0, 0.05, 1.0)


def g_excl(m):
    return clip(1 - m / 12.0, 0.0, 1.0)


def g_pay(n):
    return clip(1 - (n - 15) / 75.0, 0.0, 1.0)


def g_kill(k):
    return clip(k / 50.0, 0.0, 1.0)


def g_rev(r):
    return 0.0 if r >= REV_UNLIMITED else clip(1 - (r - 1) / 3.0, 0.0, 1.0)


PERSONA_LIMITS = {
    "rights_protective": dict(max_usage=12, max_excl=6, max_rev=4, min_kill=10),
    "cash_first": dict(min_fee=1.0, max_net=45, max_usage=24, max_rev=4, min_kill=10),
    "balanced": dict(max_usage=24, max_excl=12, max_net=60, max_rev=4, min_kill=10),
}


def creator_red_lines(persona, o):
    """Terms this creator persona would walk away from. An offer that crosses one has utility 0."""
    lim = PERSONA_LIMITS[persona]
    out = []
    if "min_fee" in lim and o["fee_mult"] < lim["min_fee"] - 1e-9:
        out.append("fee")
    if "max_usage" in lim and o["usage_months"] > lim["max_usage"]:
        out.append("usage")
    if "max_excl" in lim and o["excl_months"] > lim["max_excl"]:
        out.append("exclusivity")
    if "max_net" in lim and o["net_days"] > lim["max_net"]:
        out.append("payment")
    if "max_rev" in lim and o["revisions"] > lim["max_rev"]:
        out.append("revisions")
    if "min_kill" in lim and o["kill_pct"] < lim["min_kill"]:
        out.append("kill_fee")
    return out


def creator_utility(persona, o):
    if creator_red_lines(persona, o):
        return 0.0
    w = PERSONAS[persona]
    return round(w["fee"] * g_fee(o["fee_mult"]) + w["usage"] * g_usage(o["usage_months"])
                 + w["excl"] * g_excl(o["excl_months"]) + w["pay"] * g_pay(o["net_days"])
                 + w["kill"] * g_kill(o["kill_pct"]) + w["rev"] * g_rev(o["revisions"]), 4)


def expected_value(brand_id, persona, o):
    e = brand_eval(brand_id, o)
    u = creator_utility(persona, o)
    return round(e["p_accept"] * u, 4), e, u


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def usage_text(m):
    return "perpetual" if m >= USAGE_PERPETUAL else f"{m} months"


def rev_text(r):
    return "unlimited" if r >= REV_UNLIMITED else f"{r} round" + ("" if r == 1 else "s")


def offer_text(o):
    excl = "none" if o["excl_months"] == 0 else f"{o['excl_months']} months"
    return (f"Fee: {round(o['fee_mult'] * 100)}% of the creator's standard rate; "
            f"usage rights: {usage_text(o['usage_months'])}; exclusivity: {excl}; "
            f"payment: net-{o['net_days']}; kill fee: {o['kill_pct']}%; "
            f"revisions: {rev_text(o['revisions'])}.")


def write_csv(filename, rows, fieldnames=None):
    if not rows:
        raise ValueError("no rows for " + filename)
    fieldnames = fieldnames or list(rows[0].keys())
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=fieldnames)
        wr.writeheader()
        wr.writerows(rows)


def read_csv(filename):
    with open(filename, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_json(filename, obj):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
