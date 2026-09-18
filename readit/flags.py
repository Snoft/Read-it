"""What the deck does NOT say, and what it says without support.

Extraction is a commodity. "There is no revenue figure anywhere in 23 slides"
is the sentence that saves a reader ten minutes, and this file produces it.

Contradiction detection is deliberately NOT here. Three decks in the set
contradict themselves, so the test cases exist, but a false contradiction costs
more trust than three missed ones and doing it properly needs more than a day.
That decision is recorded in the README rather than hidden as an omission.
"""
from dataclasses import dataclass

from readit.ingest import Deck


@dataclass
class Flag:
    kind: str        # missing | redacted | unsupported | thesis_gap
    field: str | None
    message: str     # one plain sentence a reader can act on
    pages: list[int]
    severity: str    # low | medium | high


# ---------------------------------------------------------------- YOUR CALL
# Which absences actually matter, how loudly, and in what words.
# This table is the opinion of the tool. Everything below it is plumbing.
#
#   field: (severity, sentence shown when the deck never states it)

WANTED = {
    "revenue":    ("high",   "No revenue figure anywhere in the deck."),
    "round_size": ("high",   "The deck never says how much is being raised."),
    "founders":   ("high",   "No founder or team member is named."),
    "stage":      ("medium", "No round or stage is named."),
    "traction":   ("medium", "No traction metric at all: no revenue, no users, no customers."),
    "location":   ("low",    "No location stated, so geography cannot be checked against the thesis."),
    "deck_date":  ("low",    "The deck is undated, so its age is unknown."),
    "investors":  ("low",    "No existing investors named."),
}

# Any one of these counts as traction, so the composite flag above only fires
# when the deck offers none of them.
TRACTION = ("revenue", "users", "customers")

# --------------------------------------------------------------- plumbing


def _f(extraction: dict, name: str) -> dict:
    return (extraction.get("fields") or {}).get(name) or {}


def _empty(field: dict) -> bool:
    return field.get("value") in (None, [], "")


def _page(field: dict) -> list[int]:
    p = (field.get("provenance") or {}).get("page")
    return [p] if p else []


def find_flags(deck: Deck, extraction: dict, thesis: dict) -> list[Flag]:
    flags: list[Flag] = []

    for name, (severity, message) in WANTED.items():
        if name == "traction":
            continue                      # composite, handled below
        f = _f(extraction, name)
        if not _empty(f):
            continue

        # A blacked-out figure is not a missing one. The deck HAS the number and
        # is withholding it, so the action is to ask rather than to pass. This is
        # the whole reason `status` exists as three values instead of two.
        if f.get("status") == "redacted":
            flags.append(Flag("redacted", name,
                              f"{name.replace('_', ' ').capitalize()} is present in the deck but redacted. "
                              f"Ask for the unredacted version.",
                              _page(f), "medium"))
        else:
            flags.append(Flag("missing", name, message, [], severity))

    # traction: only complain when the deck offers nothing at all
    if all(_empty(_f(extraction, n)) for n in TRACTION):
        sev, msg = WANTED["traction"]
        flags.append(Flag("missing", "traction", msg, [], sev))

    flags.extend(_unsupported(extraction))
    return flags


def _unsupported(extraction: dict) -> list[Flag]:
    """Claims with nothing underneath them.

    Conservative on purpose: only fires on patterns that are unambiguous. A
    wrong flag here reads as the tool not understanding the deck, and a reader
    who catches one stops trusting the whole column.
    """
    out: list[Flag] = []

    # "3x growth" with no revenue and no user count is a rate with no base.
    growth = _f(extraction, "growth")
    if not _empty(growth) and _empty(_f(extraction, "revenue")) and _empty(_f(extraction, "users")):
        out.append(Flag("unsupported", "growth",
                        "A growth figure is given with no revenue or user count behind it, "
                        "so there is no base to grow from.",
                        _page(growth), "medium"))

    # A valuation with no round size: what is being sold at that price?
    val, rnd = _f(extraction, "valuation"), _f(extraction, "round_size")
    if not _empty(val) and _empty(rnd) and rnd.get("status") != "redacted":
        out.append(Flag("unsupported", "valuation",
                        "A valuation is stated without the round size, so the stake on offer is unclear.",
                        _page(val), "low"))

    return out
