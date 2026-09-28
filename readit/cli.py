"""Screen one deck from the command line.

    python -m readit.cli screen evals/decks/<deck>.pdf           # memo as text
    python -m readit.cli screen evals/decks/<deck>.pdf --html    # memo as a page, out/<deck>.html
    python -m readit.cli screen evals/decks/<deck>.pdf --json    # extraction, flags and score
"""
import argparse
import json
import sys
import webbrowser
from pathlib import Path

import yaml
from dotenv import load_dotenv

from readit import ingest, extract as extract_mod, flags as flags_mod, score as score_mod, memo


def load_thesis(path="thesis.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf8"))


def screen(deck_path: str, thesis_path: str, model: str, as_json: bool, as_html: bool = False) -> int:
    load_dotenv()
    thesis = load_thesis(thesis_path)
    deck = ingest.load(deck_path)
    extraction = extract_mod.extract(deck, model=model)
    fl = flags_mod.find_flags(deck, extraction, thesis)
    sc = score_mod.score(extraction, thesis, fl)
    if as_json:
        print(json.dumps({"extraction": extraction,
                          "flags": [f.__dict__ for f in fl],
                          "score": sc.__dict__}, indent=2, ensure_ascii=False))
    elif as_html:
        # Same memo, as a page where every page number opens the deck at that
        # page. Written to out/ (gitignored) next to nothing that gets committed.
        from readit import memo_html
        out = Path("out") / f"{Path(deck_path).stem}.html"
        memo_html.write(extraction, fl, sc, deck_path, out, model)
        print(f"written: {out}")
        webbrowser.open(out.resolve().as_uri())
    else:
        print(memo.render(extraction, fl, sc))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="readit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("screen", help="screen one deck")
    s.add_argument("deck")
    s.add_argument("--thesis", default="thesis.yaml")
    s.add_argument("--model", default=extract_mod.MODEL)
    s.add_argument("--json", action="store_true")
    s.add_argument("--html", action="store_true",
                   help="write the memo to out/<deck>.html and open it in the browser")
    a = ap.parse_args(argv)
    if a.cmd == "screen":
        return screen(a.deck, a.thesis, a.model, a.json, a.html)
    return 1


if __name__ == "__main__":
    sys.exit(main())
