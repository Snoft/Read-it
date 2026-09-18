"""python evals/run_eval.py            -> the table that goes in the README
   python evals/run_eval.py --model gpt-4.1   -> the comparison run

Reads every evals/labels/*.json, finds the deck it names in evals/decks/,
runs the pipeline, prints the summary and writes evals/results-<model>.json.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from dotenv import load_dotenv

from readit import ingest, extract as extract_mod, flags as flags_mod
from evals import metrics

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=extract_mod.MODEL)
    ap.add_argument("--only", help="substring filter on label filename")
    a = ap.parse_args()
    load_dotenv()

    thesis = yaml.safe_load((ROOT / "thesis.yaml").read_text(encoding="utf8"))
    labels = sorted((ROOT / "evals" / "labels").glob("*.json"))
    if a.only:
        labels = [p for p in labels if a.only in p.name]
    if not labels:
        print("No labels in evals/labels/. Copy label_template.json and fill it in first.")
        return 1

    results, failures = [], []
    for lp in labels:
        label = json.loads(lp.read_text(encoding="utf8"))
        deck_path = ROOT / "evals" / "decks" / label["_deck"]
        if not deck_path.exists():
            failures.append(f"{lp.name}: deck {label['_deck']} not found")
            continue
        try:
            deck = ingest.load(deck_path)
            extraction = extract_mod.extract(deck, model=a.model)
            fl = flags_mod.find_flags(deck, extraction, thesis)
            results.append(metrics.grade(extraction, label, deck, fl))
            print(f"  ok   {label['_deck']}")
        except NotImplementedError as e:
            failures.append(f"{lp.name}: {e}")
        except Exception as e:  # a crash on one deck must not lose the run
            failures.append(f"{lp.name}: {type(e).__name__}: {e}")
            print(f"  FAIL {label['_deck']}: {e}")

    if not results:
        print("\nNothing scored.")
        for f in failures:
            print("  -", f)
        return 1

    summary = metrics.summarise(results)
    print("\n" + "-" * 52)
    print(f"model: {a.model}")
    for k, v in summary.items():
        print(f"{k:>22}: {v}")
    print("-" * 52)

    print("\nWorst misses (fix these, do not tune the prompt blindly):")
    for r in sorted(results, key=lambda r: len(r.wrong), reverse=True)[:5]:
        for w in r.wrong[:3]:
            print(f"  {r.deck}: {w}")
    if any(r.hallucinated for r in results):
        print("\nHallucinated (value with no quote on the page):")
        for r in results:
            for h in r.hallucinated:
                print(f"  {r.deck}: {h}")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)

    out = ROOT / "evals" / f"results-{a.model}.json"
    out.write_text(json.dumps(
        {"model": a.model, "summary": summary,
         "per_deck": [r.__dict__ for r in results], "failures": failures},
        indent=2, ensure_ascii=False), encoding="utf8")
    print(f"\nwritten: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
