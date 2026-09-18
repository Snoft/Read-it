"""Read one deck's extraction next to its label, in a human format.

    python evals/review.py bryter          # compare against the label
    python evals/review.py bryter --raw    # just show what came out

This is the iteration loop: run it, find one wrong field, change one sentence
in PROMPT, run it again. Uses the cache, so repeats are free.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from dotenv import load_dotenv

from readit import ingest, extract as extract_mod
from evals.metrics import FREE_TEXT, NUMERIC, _eq

ROOT = Path(__file__).resolve().parent.parent
G, R, Y, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def fmt(field: str, f: dict) -> str:
    if not isinstance(f, dict):
        return str(f)
    v = f.get("value")
    if v in (None, [], ""):
        st = f.get("status")
        if st == "redacted":
            return f"{Y}REDACTED in the deck{OFF}"
        if st == "absent":
            return f"{DIM}(never mentioned){OFF}"
        return f"{DIM}(not stated){OFF}"
    if isinstance(v, list):
        return ", ".join(v)
    bits = [f"{v:,}" if isinstance(v, (int, float)) else str(v)]
    for k in ("unit", "period", "as_of"):
        if f.get(k):
            bits.append(str(f[k]))
    return " ".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("label", help="label filename without .json, e.g. bryter")
    ap.add_argument("--model", default=extract_mod.MODEL)
    ap.add_argument("--raw", action="store_true", help="skip the comparison")
    a = ap.parse_args()
    load_dotenv()

    lp = ROOT / "evals" / "labels" / f"{a.label}.json"
    if not lp.exists():
        print(f"no label at {lp}")
        return 1
    label = json.loads(lp.read_text(encoding="utf8"))

    deck = ingest.load(ROOT / "evals" / "decks" / label["_deck"])
    got = extract_mod.extract(deck, model=a.model)

    print(f"\n{'=' * 78}\n{label['_deck']}   ({len(deck.pages)} pages, "
          f"{sum(1 for p in deck.pages if p.is_graphic)} sent as images)\n{'=' * 78}")
    print(f"company   {got.get('company')}"
          + (f"   {DIM}label: {label['company']}{OFF}" if not a.raw and got.get("company") != label["company"] else ""))
    print()

    gf, lf = got.get("fields", {}), label.get("fields", {})
    right = total = halluc = 0

    for name in lf:
        g = gf.get(name) or {}
        shown = fmt(name, g)
        prov = g.get("provenance") or {}
        quote = (prov.get("source_quote") or "").replace("\n", " ").strip()
        has_value = (g.get("value") not in (None, [], ""))

        # hallucination check: a value must be quotable from its page
        # A quote can only be checked against a page that HAS a text layer.
        # Graphic pages went to the model as images, so there is nothing to
        # match against and flagging them would be noise, not signal.
        bad_quote = False
        page_no = prov.get("page", 0)
        page = next((p for p in deck.pages if p.number == page_no), None)
        checkable = page is not None and not page.is_graphic
        if has_value and checkable:
            if not quote or quote.lower() not in deck.page_text(page_no).lower():
                bad_quote = True
                halluc += 1

        if a.raw:
            mark = " "
        elif name in FREE_TEXT:
            mark = f"{Y}~{OFF}"
        else:
            want = lf[name].get("value")
            if want in (None, [], "") and not has_value:
                mark, right, total = f"{G}+{OFF}", right + 1, total + 1
            elif want in (None, [], ""):
                mark, total = f"{R}x{OFF}", total + 1
            else:
                ok = _eq(name, g.get("value"), want)
                mark, total = (f"{G}+{OFF}" if ok else f"{R}x{OFF}"), total + 1
                right += ok

        print(f" {mark} {name:12} {shown}")
        if not a.raw and not isinstance(mark, str) or (not a.raw and R in str(mark)):
            print(f"      {DIM}label: {fmt(name, lf[name])}{OFF}")
        if quote:
            tag = f"{R}NO QUOTE MATCH{OFF} " if bad_quote else ""
            print(f"      {DIM}{tag}p{prov.get('page')}: \"{quote[:90]}\"{OFF}")

    if not a.raw:
        print(f"\n{right}/{total} scored fields match "
              f"({DIM}one_liner excluded, free text{OFF}), {halluc} unquotable")
        print(f"{DIM}quotes are only checkable on text pages; image pages are not counted either way{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
