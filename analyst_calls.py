#!/usr/bin/env python3
"""Canonical helpers shared by the scorecard / buy-table / ticker scripts.

One source of truth for two things that used to be defined (inconsistently) in
three places:
  - is_buy(action)  — does an analyst action count as a BUY?
  - is_sell(action) — does it count as a SELL/exit (used to close a position)?
  - norm_key(name)  — collapse a stock name so spelling variants match
                      ("NetWeb"/"Netweb", "Anant Raj"/"Anantraj").
  - alias_keys(name) — norm_key variants incl. parenthetical forms, so
                      "NCC (Nagarjuna Construction)" also matches "NCC".

Matching is TOKEN-based (whole words), not substring, so "Ladder up" no longer
counts as a buy just because it contains "add".
"""
import re

# A call is a BUY if it mentions one of these and none of the blockers below.
BUY_WORDS = {"buy", "add", "accumulate"}
# Blockers: hold/wait are not entries; sell-side words mean it isn't a fresh buy.
# (Note: "switch" is intentionally NOT a blocker — "Buy / switch into" is a buy,
#  while "Sell / switch out" is already blocked by "sell".)
BLOCK_WORDS = {"hold", "wait", "avoid", "sell", "reduce", "book"}
# A call is a SELL/exit when it mentions one of these. ("exit" is deliberately
# excluded: in practice it only appears inside hold-y labels like
# "Hold (exit on rally)", which shouldn't force-close a position.)
SELL_WORDS = {"sell", "reduce", "book"}


def _tokens(action: str) -> set[str]:
    """Lower-cased alphabetic tokens of an action label."""
    return set(re.findall(r"[a-z]+", (action or "").lower()))


def is_buy(action: str) -> bool:
    """True for buy-intent calls incl. variants ('Buy on dips', 'Add on dips',
    'Buy/Add', 'Buy (long term)', 'Accumulate on dips', 'Buy / switch into'),
    excluding hold/wait/avoid/sell hybrids ('Hold/Add', 'Wait/Buy after result')."""
    t = _tokens(action)
    return bool(t & BUY_WORDS) and not (t & BLOCK_WORDS)


def is_sell(action: str) -> bool:
    """True for exit calls — Sell / Reduce / Book Profit / Exit."""
    return bool(_tokens(action) & SELL_WORDS)


def norm_key(name: str) -> str:
    """Normalise a stock name so 'Anant Raj' == 'Anantraj' across runs."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def alias_keys(name: str) -> list[str]:
    """Candidate norm-keys for a name: the full name, the name with any
    parenthetical stripped, and each parenthetical's own content. Lets
    'Larsen & Toubro (L&T)' match 'Larsen & Toubro' and 'Naukri (Info Edge)'
    match 'Info Edge (Naukri)' (via the parenthetical/stripped forms)."""
    keys = [norm_key(name)]
    stripped = re.sub(r"\([^)]*\)", " ", name or "")
    for cand in [stripped] + re.findall(r"\(([^)]*)\)", name or ""):
        k = norm_key(cand)
        if k and k not in keys:
            keys.append(k)
    return keys
