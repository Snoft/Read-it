"""One page a human reads in ninety seconds. Done for you."""
from readit.score import Score

TEMPLATE = """# {company}

**{verdict}** ({score:.0%} thesis fit){stage}{location}

{one_liner}

## The numbers
{numbers}

## What is missing or does not add up
{flags}

## What to ask the founder
{questions}

## Why this score
{reasons}
---
*Every figure above is quoted from the deck with its page. Nothing is inferred.*
"""


def _num(v) -> str:
    """No scientific notation on a page a human reads."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _fmt_metric(name: str, f: dict) -> str:
    v = f.get("value")
    if v is None:
        # "withheld" and "never mentioned" are different findings, and the
        # reader acts differently on each, so the memo must not flatten them.
        if f.get("status") == "redacted":
            page = (f.get("provenance") or {}).get("page")
            return f"- **{name}:** redacted in the deck" + (f" [p{page}]" if page else "") + " — ask for the unredacted version"
        return f"- **{name}:** not stated in the deck"
    unit = f.get("unit") or ""
    period = f" {f['period']}" if f.get("period") else ""
    as_of = f" (as of {f['as_of']})" if f.get("as_of") else ""
    prov = f.get("provenance") or {}
    page = f" [p{prov['page']}]" if prov.get("page") else ""
    return f"- **{name}:** {_num(v)} {unit}{period}{as_of}{page}".replace("  ", " ").rstrip()


# A flag says what is wrong with the deck. A question is what you put to a human
# because of it. They are not the same sentence, and printing the first as the
# second made the memo look like it had not thought about the reader.
ASK = {
    "revenue":    "What is your current revenue, and as of when?",
    "round_size": "How much are you raising, and at what valuation?",
    "stage":      "What round is this, and who is leading it?",
    "founders":   "Who is on the founding team, and what did each of you do before?",
    "traction":   "What evidence do you have that anyone wants this yet?",
    "users":      "How many users or customers do you have today?",
    "growth":     "Growth from what base, over what period?",
    "valuation":  "What valuation are you asking for, and how did you arrive at it?",
    "location":   "Where is the company based and incorporated?",
    "deck_date":  "When was this deck put together, and what has changed since?",
    "investors":  "Who is already invested, and are they following on?",
    "customers":  "Which customers are paying, as opposed to piloting?",
}


def _questions(flags: list, limit: int = 3) -> list[str]:
    """Highest severity first, deduplicated, at most `limit`."""
    order = {"high": 0, "medium": 1, "low": 2}
    seen, out = set(), []
    for f in sorted(flags, key=lambda f: order.get(f.severity, 3)):
        if f.kind == "redacted":
            q = f"Can you share the unredacted {str(f.field).replace('_', ' ')} figure?"
        else:
            q = ASK.get(f.field)
        if q and q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= limit:
            break
    return out


def render(extraction: dict, flags: list, sc: Score, questions: list[str] | None = None) -> str:
    fields = extraction.get("fields", {})
    metrics = [k for k in ("revenue", "growth", "users", "round_size", "valuation") if k in fields]
    numbers = "\n".join(_fmt_metric(k.replace("_", " "), fields[k]) for k in metrics) or "- nothing quantitative in the deck"

    if flags:
        flag_lines = "\n".join(
            f"- **{f.kind}**{' · ' + f.field if f.field else ''}: {f.message}"
            f"{' [p' + ', p'.join(map(str, f.pages)) + ']' if f.pages else ''}"
            for f in sorted(flags, key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f.severity, 3))
        )
    else:
        flag_lines = "- nothing flagged"

    qs = questions or _questions(flags) or ["Nothing obvious to probe: the deck answers the basics."]

    stage = f" · {fields.get('stage', {}).get('value')}" if fields.get("stage", {}).get("value") else ""
    loc = f" · {fields.get('location', {}).get('value')}" if fields.get("location", {}).get("value") else ""

    return TEMPLATE.format(
        company=extraction.get("company", "Unknown"),
        verdict=sc.verdict.upper(),
        score=sc.total,
        stage=stage,
        location=loc,
        one_liner=fields.get("one_liner", {}).get("value") or "_no one-line description in the deck_",
        numbers=numbers,
        flags=flag_lines,
        questions="\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1)),
        reasons="\n".join(f"- {r}" for r in sc.reasons + [f"not scored: {u}" for u in sc.unscored]),
    )
