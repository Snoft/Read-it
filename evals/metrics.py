"""Scoring the screener, not the startup. This is the file the README table comes from.

Three numbers, and the second is the one that will get you the interview:

    field_accuracy      right / (fields the label says are present)
    hallucination_rate  fields with a value whose source_quote is NOT in the page
    flag_recall         expected_flags the run actually produced
"""
import unicodedata
from dataclasses import dataclass, field as dc_field

NUMERIC = {"revenue", "growth", "users", "round_size", "valuation"}
TOLERANCE = 0.02  # 2% on numbers, so 300k vs 299,900 is not a miss

# Free prose cannot be scored by string equality. "Professional service
# automation" and "lets professional service experts automate their expertise
# without coding" are the same answer, and marking one wrong would make the
# accuracy figure meaningless. These fields are still checked for hallucination
# (a value must carry a quote); they are just excluded from the accuracy count.
FREE_TEXT = {"one_liner"}


@dataclass
class Result:
    deck: str
    correct: int = 0
    present: int = 0
    wrong: list[str] = dc_field(default_factory=list)
    hallucinated: list[str] = dc_field(default_factory=list)
    valued: int = 0
    checkable: int = 0        # values whose page has a text layer to verify against
    unverifiable: int = 0     # values quoted from a page that went in as an image
    flags_expected: int = 0
    flags_found: int = 0


def _norm(x) -> str:
    """Søndergaard and Sondergaard are the same person.

    Labels get typed by hand and lose their diacritics; the model reads them off
    the slide correctly. Marking that a miss would punish the more accurate
    answer, so names are compared with accents stripped and case folded.
    """
    # NFKD decomposes e-acute into e + accent, but NOT o-slash, ae or eszett:
    # those are single codepoints with no decomposition, so "ignore" would DELETE
    # them and turn Søndergaard into Sndergaard. Fold them by hand first.
    x = str(x)
    for a, b in (("ø", "o"), ("Ø", "O"), ("æ", "ae"), ("Æ", "Ae"),
                 ("ß", "ss"), ("đ", "d"), ("Đ", "D"), ("ł", "l"), ("Ł", "L")):
        x = x.replace(a, b)
    s = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _eq(name: str, got, want) -> bool:
    if want is None:
        return got is None
    if isinstance(want, list):
        g = {_norm(x) for x in (got or [])}
        w = {_norm(x) for x in want}
        return bool(w) and len(g & w) / len(w) >= 0.6
    if name in NUMERIC:
        try:
            got_f, want_f = float(got), float(want)
        except (TypeError, ValueError):
            return False
        return abs(got_f - want_f) <= abs(want_f) * TOLERANCE
    return _norm(got or "") == _norm(want)


def grade(extraction: dict, label: dict, deck, flags: list | None = None) -> Result:
    r = Result(deck=label.get("_deck", "?"))
    got_fields = extraction.get("fields", {})

    for name, want_f in label.get("fields", {}).items():
        want = want_f.get("value")
        got_f = got_fields.get(name) or {}
        got = got_f.get("value")

        # Hallucination: a value whose quote is not actually on the page.
        #
        # This can only be tested where the page HAS a text layer. Pages that went
        # to the model as images have no text to match against, so a failed match
        # there means "cannot tell", not "invented". Counting those as
        # hallucinations put the rate at 92% when the true figure was unknown.
        if got not in (None, [], ""):
            r.valued += 1
            prov = got_f.get("provenance") or {}
            quote = (prov.get("source_quote") or "").strip()
            page_no = prov.get("page", 0)
            page = next((p for p in deck.pages if p.number == page_no), None)
            if page is None or page.is_graphic:
                r.unverifiable += 1
            else:
                r.checkable += 1
                if not quote or quote.lower() not in deck.page_text(page_no).lower():
                    r.hallucinated.append(name)

        if name in FREE_TEXT:
            continue  # see FREE_TEXT above: judged by eye, not by ==
        if want in (None, [], ""):
            continue  # label says absent: not counted in accuracy
        r.present += 1
        if _eq(name, got, want):
            r.correct += 1
        else:
            r.wrong.append(f"{name}: got {got!r}, label {want!r}")

    expected = label.get("expected_flags", [])
    r.flags_expected = len(expected)
    produced = {(getattr(f, "kind", None), getattr(f, "field", None)) for f in (flags or [])}
    r.flags_found = sum(1 for e in expected if (e.get("kind"), e.get("field")) in produced)
    return r


def summarise(results: list[Result]) -> dict:
    present = sum(r.present for r in results)
    correct = sum(r.correct for r in results)
    valued = sum(r.valued for r in results)
    checkable = sum(r.checkable for r in results)
    unverifiable = sum(r.unverifiable for r in results)
    halluc = sum(len(r.hallucinated) for r in results)
    fe = sum(r.flags_expected for r in results)
    ff = sum(r.flags_found for r in results)
    return {
        "decks": len(results),
        "fields_present": present,
        "field_accuracy": round(correct / present, 3) if present else None,
        "fields_with_value": valued,
        "quotes_checkable": checkable,
        "quotes_unverifiable": unverifiable,
        "hallucination_rate": round(halluc / checkable, 3) if checkable else None,
        "hallucinated_fields": halluc,
        "flag_recall": round(ff / fe, 3) if fe else None,
    }
