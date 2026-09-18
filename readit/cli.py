"""python -m readit.cli screen evals/decks/acme.pdf"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from readit import ingest, extract as extract_mod, flags as flags_mod, score as score_mod, memo


def load_thesis(path="thesis.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf8"))


def screen(deck_path: str, thesis_path: str, model: str, as_json: bool) -> int:
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
    a = ap.parse_args(argv)
    if a.cmd == "screen":
        return screen(a.deck, a.thesis, a.model, a.json)
    return 1


if __name__ == "__main__":
    sys.exit(main())
