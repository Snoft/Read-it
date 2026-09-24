"""Deck -> structured fields, every value carrying the sentence it came from.

The API plumbing below is boilerplate. THE PROMPT IS THE PROJECT. It is the part
you will be asked about, and the part that moves the eval numbers.
"""
import json

from anthropic import Anthropic
from dotenv import load_dotenv

from readit.cache import cached
from readit.ingest import Deck

MODEL = "claude-sonnet-5"
MAX_PAGES = 30          # decks longer than this get truncated; say so in the README
MAX_TOKENS = 8000

# Dollars per million tokens, in / out. Checked against the pricing page on
# 24 Sep 2026. Only used to put a cost on the eval run; if a price moves, the
# old results files keep the number they were computed with.
PRICES = {
    "claude-opus-5-5":           (4.0, 20.0),
    "claude-sonnet-5":           (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0,  5.0),
}

# Opus 5.5 always thinks, the thinking is billed as output, and it counts
# against max_tokens. 8000 is enough for the tool call alone but not for the
# thinking in front of it, so that model gets more room.
MAX_TOKENS_BY_MODEL = {"claude-opus-5-5": 24000}


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price = PRICES.get(model)
    if not price:
        return 0.0
    return tokens_in / 1e6 * price[0] + tokens_out / 1e6 * price[1]

_client = None


def client() -> Anthropic:
    """Built on first use, not at import.

    Anthropic() reads ANTHROPIC_API_KEY from the environment the moment it is
    constructed. At import time load_dotenv() has not run yet, so a module-level
    client is born without a key and every call fails with a confusing auth
    error. Constructing it lazily makes the order of imports irrelevant.
    """
    global _client
    if _client is None:
        load_dotenv()
        _client = Anthropic()
    return _client


# ---------------------------------------------------------------- the schema
# Deliberately flat and inline rather than loaded from schema/extraction_schema.json:
# the API wants one self-contained schema, and $ref indirection makes failures
# much harder to read. Keep the two in step by hand; there are only twelve fields.

def _prov():
    return {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "page number the value came from"},
            "source_quote": {"type": "string", "description": "the exact words on that page, copied character for character"},
        },
        "required": ["page", "source_quote"],
    }


def _text_field(desc):
    return {"type": "object", "description": desc,
            "properties": {"value": {"type": ["string", "null"]},
                           "confidence": {"type": "number"},
                           "provenance": _prov()},
            "required": ["value", "confidence"]}


def _list_field(desc):
    return {"type": "object", "description": desc,
            "properties": {"value": {"type": "array", "items": {"type": "string"}},
                           "confidence": {"type": "number"},
                           "provenance": _prov()},
            "required": ["value", "confidence"]}


def _metric(desc):
    return {"type": "object", "description": desc,
            "properties": {"status": {
                               "type": "string",
                               "enum": ["stated", "redacted", "absent"],
                               "description": (
                                   "stated: the deck gives the figure and you have read it. "
                                   "redacted: the deck has a slide for this figure but the number "
                                   "is blacked out, blurred, greyed or replaced with XXX, so it "
                                   "exists and is being withheld. "
                                   "absent: the deck never raises this figure at all. "
                                   "Redacted and absent mean opposite things to a reader: the first "
                                   "says ask for the unredacted version, the second says there may be "
                                   "nothing to ask for. Never use stated for a number you inferred."),
                           },
                           "value": {"type": ["number", "null"], "description": "the bare number, fully expanded: 300k is 300000. null unless status is stated"},
                           "unit": {"type": ["string", "null"], "description": "EUR, USD, percent, count"},
                           "period": {"type": ["string", "null"], "description": "ARR, MRR, FY2025, QoQ"},
                           "as_of": {"type": ["string", "null"], "description": "the date or quarter the figure describes"},
                           "confidence": {"type": "number"},
                           "provenance": _prov()},
            "required": ["value", "confidence", "status"]}


def _claim():
    """One side of a contradiction: what the deck says, where, in its own words."""
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "the figure as the deck writes it, e.g. '500,000 daily active users'"},
            "page": {"type": "integer"},
            "source_quote": {"type": "string", "description": "the exact words on that page, copied character for character"},
        },
        "required": ["text", "page", "source_quote"],
    }


def _contradiction():
    return {
        "type": "object",
        "properties": {
            "about": {
                "type": "string",
                "enum": ["revenue", "growth", "users", "customers", "round_size",
                         "valuation", "founders", "market", "metrics"],
                "description": ("which field the two figures belong to. Use metrics for "
                                "operational numbers that are none of the others, such as "
                                "a reduction in hospital visits or a conversion rate."),
            },
            "quantity": {"type": "string", "description": "what both figures claim to measure, in the deck's own words"},
            "first": _claim(),
            "second": _claim(),
            "note": {"type": "string", "description": "one sentence naming both figures and where they sit, that a reader can put to the founder"},
        },
        "required": ["about", "quantity", "first", "second", "note"],
    }


TOOL = {
    "name": "record_extraction",
    "description": "Record what this pitch deck states. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "company name AS THE DECK SPELLS IT, not as the filename does"},
            "fields": {
                "type": "object",
                "properties": {
                    "one_liner":   _text_field("what the company does, in one line, taken from the deck"),
                    "deck_date":   _text_field(
                        "the date THIS DECK states for itself: a date on the cover, in a footer, "
                        "in a running header, or an 'as of <month year>' line. Format it as the deck "
                        "writes it. This is NOT the founding date of the company, NOT the date of a "
                        "funding round, NOT a copyright line such as '(c) 2020', and NOT the newest "
                        "year appearing on a timeline or roadmap chart. Most decks never date "
                        "themselves: if it is not stated, null. An inferred date is worse than none, "
                        "because the whole purpose of this field is telling a reader how stale the "
                        "deck is."),
                    "sector":      _text_field("one lowercase word: saas, fintech, healthtech, deeptech, marketplace, consumer, edtech, proptech"),
                    "stage":       _text_field("funding stage or round name, e.g. pre-seed, seed, series a, strategic, bridge. Decks often show a funding history or a roadmap of rounds they plan to raise later, those are not the current raise. If several rounds appear, take the one being asked for now. If you cannot tell which is current, null."),
                    "location":    _text_field("HQ city or country, only if the deck states it"),
                    "founders":    _list_field("people the deck presents as founders or the team, by name"),
                    "revenue":     _metric("revenue, ARR or MRR"),
                    "growth":      _metric("a growth rate or multiple"),
                    "users":       _metric("users, customers, downloads or similar count"),
                    "round_size":  _metric("how much is being raised"),
                    "valuation":   _metric("pre- or post-money valuation"),
                    "customers":   _list_field("customers named or shown as logos"),
                    "competitors": _list_field("competitors named as companies, not as categories"),
                    "investors":   _list_field(
                        "funds, angel networks and individual people the deck names as ALREADY "
                        "INVESTED in this company, usually under a heading like 'Investors' or "
                        "'Backed by'. Named individual angels count. Do NOT include: press or media "
                        "logos, customer logos under headings like 'Trusted by', partners or "
                        "suppliers, accelerators, or advisors and board members unless the deck "
                        "states that they invested. If no investors are named, empty list.")
                },
                "required": ["one_liner", "deck_date", "sector", "stage", "location", "founders",
                             "revenue", "growth", "users", "round_size", "valuation",
                             "customers", "competitors", "investors"],
            },
            "contradictions": {
                "type": "array",
                "items": _contradiction(),
                "description": ("pairs of figures in THIS deck that cannot both be true. "
                                "Empty list is the normal answer. See rule 7."),
            },
        },
        "required": ["company", "fields", "contradictions"],
    },
}


# ------------------------------------------------------------------ YOUR BIT
# Everything above is scaffolding. This is the file's actual content.
#
# Improve it by reading eval failures, not by guessing. Run the eval, look at
# what came out wrong, add one sentence aimed at that failure, run again.
# Keep the versions you tried and what each changed: that history IS the
# interview answer.

PROMPT = """You are reading a startup pitch deck for an investor who will check every number you report.

Answer by calling the record_extraction tool, exactly once. Everything you have
to report goes in that call; do not reply in prose.

Rules, in order of importance:

1. Never write a value the deck does not state. An absent field is a useful,
   correct answer: value null, confidence 0. A guess is worse than a blank,
   because the investor will act on it.

2. Every non-null value carries provenance: the page number, and source_quote
   copied exactly from that page. If you cannot quote it, you cannot report it.

3. Do not infer. If the founders have German names and the deck never states a
   location, location is null. If investors are listed but no round is named,
   stage is null.

4. Numbers keep their parts separate. "EUR 300k ARR as of Q2 2025" is
   value 300000, unit EUR, period ARR, as_of "Q2 2025". Never fold the unit
   into the number, and expand abbreviations: 300k is 300000, 1.5m is 1500000.

5. Confidence is how sure you are the deck says this, not how good the company
   looks. A number you read clearly on a slide is 0.9 even if it is a bad number.

6. The filename is not part of the deck. It often carries a company name, a
   round size or a date that the slides themselves never state. Read only what
   is on the pages.

7. Contradictions are reported only when the deck gives two figures for the same
   quantity that cannot both be true, and you can quote both. Figures that
   measure different things are not contradictions: total users against paying
   users, one country against worldwide, one year against another, a number you
   read off a chart against a headline. If you need a sentence explaining how
   both might still be true, it is not a contradiction. An empty list is the
   normal and expected answer. A wrong contradiction costs the reader more trust
   than three missed ones.

Report only the company's own facts. Market size, competitor revenue and
industry statistics are not this company's numbers.
"""


# ---------------------------------------------------------------- the call

def _blocks(deck: Deck) -> list[dict]:
    """Text pages as text, graphic pages as images, each tagged with its number."""
    out = []
    for page in deck.pages[:MAX_PAGES]:
        if page.image_b64:
            out.append({"type": "text", "text": f"[page {page.number}]"})
            out.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": page.image_b64}})
        else:
            out.append({"type": "text", "text": f"[page {page.number}]\n{page.text}"})
    return out


def _tool_block(resp):
    """Select by type, never by position: on a thinking model the first block is
    a thinking block, so resp.content[0] is not the answer."""
    for block in resp.content:
        if block.type == "tool_use":
            return block
    return None


def _said(resp) -> str:
    return " ".join(b.text for b in resp.content if b.type == "text").strip()


@cached
def _call(deck_path: str, model: str, prompt: str, tool_json: str, blocks_json: str) -> dict:
    """tool_json is in the signature purely so it lands in the cache key.

    The schema descriptions steer the model as much as PROMPT does, so a run
    with edited descriptions must be a cache miss. Leaving it out means editing
    a description, re-running, seeing the old answer, and concluding the edit
    did nothing."""
    blocks = json.loads(blocks_json)
    # tool_choice is "auto", not {"type": "tool", ...}: Opus 5.5 rejects forced
    # tool use with a 400. The documented replacement is strict tool use, which
    # this schema cannot take as written -- strict allows 16 union-typed
    # parameters and the schema has 25, because every optional value is
    # ["string", "null"]. Reworking nullability is the real fix and it is a
    # schema decision, not a call-site one.
    kw = dict(model=model,
              max_tokens=MAX_TOKENS_BY_MODEL.get(model, MAX_TOKENS),
              system=prompt,
              tools=[TOOL],
              tool_choice={"type": "auto"})

    def ask(messages):
        # Streamed, not to show output as it arrives but because the SDK refuses
        # a non-streaming request whose max_tokens implies it could run past ten
        # minutes. On a thinking model with 24000 tokens that is every call, and
        # the first Opus 5.5 run died on it. get_final_message() hands back the
        # same Message the non-streaming call returned.
        with client().messages.stream(messages=messages, **kw) as stream:
            return stream.get_final_message()

    resp = ask([{"role": "user", "content": blocks}])
    tin, tout = resp.usage.input_tokens, resp.usage.output_tokens
    tool, retries = _tool_block(resp), 0

    if tool is None:
        # Asking for the tool is not the same as forcing it, so "the model
        # answered in prose" is a live failure mode again rather than a
        # theoretical one: Opus 5.5 did exactly this on Wunderlist, wrote a
        # perfectly good summary, and returned nothing the pipeline could use.
        # One retry, handing the model its own prose back and asking it to put
        # the same reading through the tool. Retries are counted and reported,
        # because a run that needed three of them is not the same result as a
        # run that needed none.
        retries = 1
        resp2 = ask([
            {"role": "user", "content": blocks},
            {"role": "assistant", "content": _said(resp) or "(no text)"},
            {"role": "user", "content":
                "You answered in prose instead of calling the tool. Record that "
                "same reading now by calling record_extraction. Do not reply in "
                "prose."},
        ])
        tin += resp2.usage.input_tokens
        tout += resp2.usage.output_tokens
        tool = _tool_block(resp2)
        resp = resp2

    if tool is None:
        raise RuntimeError(
            f"model did not call the tool, even after a retry; "
            f"stop_reason={resp.stop_reason}; said: {_said(resp)[:200]!r}")

    return {"extraction": tool.input,
            "usage": {"in": tin, "out": tout,
                      "usd": round(cost(model, tin, tout), 4),
                      "retries": retries}}


def extract(deck: Deck, model: str = MODEL, with_usage: bool = False) -> dict:
    blocks_json = json.dumps(_blocks(deck))
    images = sum(1 for p in deck.pages[:MAX_PAGES] if p.image_b64)
    mb = len(blocks_json) / 1_048_576
    if mb > 3:
        # A big deck uploads for a minute or more with nothing on screen, which
        # looks exactly like a hang. Say so before going quiet.
        print(f"   {deck.path.name}: uploading {mb:.1f} MB ({images} page images), this takes a moment...")
    result = _call(str(deck.path), model, PROMPT, json.dumps(TOOL, sort_keys=True), blocks_json)
    u = result.get("usage", {})
    retry = "  (retried: answered in prose first)" if u.get("retries") else ""
    print(f"   {deck.path.name}: {u.get('in', '?')} in / {u.get('out', '?')} out"
          f" / ${u.get('usd', 0):.4f}{retry}")
    if with_usage:
        return result["extraction"], u
    return result["extraction"]
