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


# Typographic variants that are the same character to a reader and a different
# one to `in`. A deck writes Qualtrics-curly-apostrophe, a model types the
# straight one, and a perfectly good quote is scored as invented.
PUNCT = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
         "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u2212": "-"}


def _flat(s: str) -> str:
    for a, b in PUNCT.items():
        s = s.replace(a, b)
    return " ".join(s.split()).lower()


def _value_on_page(value, page: str) -> bool:
    """Is the reported value itself somewhere on this page, in any spelling?"""
    if isinstance(value, list):
        if not value:
            return False
        return sum(1 for v in value if _flat(str(v)) in page) / len(value) >= 0.6
    if isinstance(value, (int, float)):
        v = float(value)
        forms = {str(int(v)) if v.is_integer() else str(v), f"{v:,.0f}"}
        for div, suf in ((1e9, "b"), (1e6, "m"), (1e3, "k")):
            if v >= div:
                q = v / div
                forms.add((str(int(q)) if q.is_integer() else f"{q:g}") + suf)
        return any(f.lower() in page for f in forms)
    t = _flat(str(value))
    if t in page:
        return True
    toks = [x for x in t.split() if len(x) > 1]
    return bool(toks) and sum(1 for x in toks if x in page) / len(toks) >= 0.6


def quote_status(quote: str, value, page_text: str) -> str:
    """verbatim | rearranged | absent.

    `absent` is the only one that means the model made something up, and it is
    what the hallucination rate counts.

    pdfplumber reads a page line by line across its full width, not box by box.
    A slide of metric tiles -- big number over small label, three tiles side by
    side -- therefore comes out as all three numbers on one line and all three
    labels on the next. hypt's "$ 700k" and "ARR" sit in the same tile, but in
    the text layer "$ 700k" is followed by the next tile's "$ 30'000". Scoring
    that as a hallucination is how this harness reported 53.8% on a run that
    invented nothing at all.

    So `rearranged` requires two things at once: every word of the quote is on
    the page, AND the value being reported is on the page. Its weakness, stated
    rather than hidden: a quote that recombines words genuinely present on the
    page would pass. That is why it is counted and shown separately instead of
    being folded into the good column, and why the verbatim count is the one to
    watch over time.
    """
    q, page = _flat(quote or ""), _flat(page_text or "")
    if not q:
        return "absent"
    if q in page:
        return "verbatim"
    toks = [t for t in q.split() if len(t) > 1]
    if toks and all(t in page for t in toks) and _value_on_page(value, page):
        return "rearranged"
    return "absent"


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
    verbatim: int = 0         # quote found on the page exactly as written
    rearranged: list[str] = dc_field(default_factory=list)  # words all present, order not
    flags_expected: int = 0
    flags_found: int = 0
    flags_produced: int = 0
    flags_not_in_key: list[str] = dc_field(default_factory=list)
    by_kind: dict = dc_field(default_factory=dict)   # kind -> [found, expected]


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
                st = quote_status(quote, got, deck.page_text(page_no))
                if st == "verbatim":
                    r.verbatim += 1
                elif st == "rearranged":
                    r.rearranged.append(name)
                else:
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
    r.flags_produced = len(produced)

    # Recall alone rewards flagging everything. These are the flags the run
    # produced that the answer key does not ask for. NOT the same as wrong: the
    # key is one reader's list of what matters in a deck, not an exhaustive one.
    # Read them by hand. A run that doubles recall and triples this has not
    # improved, it has got louder.
    wanted = {(e.get("kind"), e.get("field")) for e in expected}
    r.flags_not_in_key = sorted(f"{k}:{f}" for (k, f) in produced - wanted)

    # Per kind, so a gain in one kind cannot hide behind the total.
    for e in expected:
        k = e.get("kind")
        slot = r.by_kind.setdefault(k, [0, 0])
        slot[1] += 1
        if (k, e.get("field")) in produced:
            slot[0] += 1
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
    kinds: dict = {}
    for r in results:
        for k, (found, exp) in r.by_kind.items():
            slot = kinds.setdefault(k, [0, 0])
            slot[0] += found
            slot[1] += exp
    return {
        "decks": len(results),
        "fields_present": present,
        "field_accuracy": round(correct / present, 3) if present else None,
        "fields_with_value": valued,
        "quotes_checkable": checkable,
        "quotes_unverifiable": unverifiable,
        "quotes_verbatim": sum(r.verbatim for r in results),
        "quotes_rearranged": sum(len(r.rearranged) for r in results),
        "hallucination_rate": round(halluc / checkable, 3) if checkable else None,
        "hallucinated_fields": halluc,
        "flag_recall": round(ff / fe, 3) if fe else None,
        "flag_recall_by_kind": {k: f"{f}/{e}" for k, (f, e) in sorted(kinds.items())},
        "flags_produced": sum(r.flags_produced for r in results),
        "flags_not_in_key": sum(len(r.flags_not_in_key) for r in results),
    }
