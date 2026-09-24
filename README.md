# Readit

Deck in, screening memo out.

Readit reads a startup pitch deck and returns a one-page screening memo: the
fields it could extract, **the source sentence behind every number**, what the
deck never says, and a fit score against a written investment thesis.

```bash
pip install -r requirements.txt
cp .env.example .env          # add your key
python -m readit.cli screen evals/decks/<deck>.pdf
python evals/review.py bryter   # extraction next to its label, field by field
```

Built in a week with Claude as a pair — see *How this was built* below for
who did what. It runs on the command line, further info in the sections below.

## Why every value carries its source

As hallucinations are not fully avoidable (yet), sources were added to the
model's outputs. Every value carries the page number and the sentence it came
from, so a reader can check any figure in two seconds instead of trusting it.
Absent is treated as a valid, useful answer rather than something to fill in.

This proved its worth while building. The tool reported one deck's stage as
"Series B", and the attached quote — *"2023 → Series B $25M"* — made it
immediately clear where that came from: a roadmap slide of rounds the company
planned to raise later, not the round it was actually asking for. Without the
quote it would have been an unexplained wrong answer instead of a five-second
diagnosis.

## Three values, not two

Metrics carry a `status` of `stated`, `redacted` or `absent`. This became
necessary because many decks are atypical: figures are blacked out, blurred or
marked as redacted rather than simply missing. A redacted revenue slide and a
deck that never mentions revenue call for opposite responses — chase it, or
accept there may be nothing to chase — and collapsing both into null loses that.

## What it flags

Two kinds. **Absences**, e.g. *"There is no revenue figure anywhere in 23
slides"*, and **contradictions**: two figures in the same deck that cannot both
be true, each with its page and its quote. Wunderlist claims 500,000 daily
active users on the metrics slide and charts 450k two slides later; that is the
sharpest question in the memo and the deck does not reconcile it.

Contradictions are found inside the extraction call, not in a second pass over
the deck. The model that read page 5 is the one that should notice page 7
disagrees with it, and a second call would re-read all the same pages for double
the cost. The risk is that asking for one more thing costs attention on the
fields themselves, so the table below carries field accuracy before and after,
not only the flag recall that went up.

To avoid false positives the whole pass is kept conservative rather than clever:
a wrong flag costs more trust than three missed ones. The rule in the prompt
spends more words on what is *not* a contradiction — total against paying users,
one country against worldwide, one year against another — than on what is.

## Quality

Measured, not asserted. Eight hand-labelled decks in `evals/labels/`.

```bash
python evals/run_eval.py --model claude-sonnet-5
python evals/run_eval.py --model claude-opus-5-5
python evals/run_eval.py --model claude-haiku-4-5-20251001
```

| Model | Field accuracy | Quotes verbatim | Hallucination rate | Flag recall | $ / deck |
|---|---|---|---|---|---|
| claude-opus-5-5 | **0.789** (30/38) | **13/13** | 0.000 | 0.488 | 0.094 |
| claude-sonnet-5 | **0.789** (30/38) | 9/13 | 0.000 | **0.512** | 0.056 |
| claude-haiku-4.5 | 0.711 (27/38) | 9/12 | 0.000 | 0.465 | **0.021** |

38 labelled field values across 8 decks. 46 values returned, of which **13 can
be checked** against a page with a text layer and 33 cannot, because they were
quoted off pages that went to the model as images.

### The newer model did not win, and that is the result

Opus 5.5 and Sonnet 5 return **exactly the same field accuracy, 30 of 38**, and
Opus costs 1.7x more per deck. Thirty-eight values cannot separate two models
that tie, and the flag-recall gap between them is literally one flag. Reporting
this as "the new model is better" would be reading noise.

**One difference is not noise.** Opus reproduced all 13 checkable quotes
character for character. Sonnet managed 9 of 13 and Haiku 9 of 12; the rest were
accurate but rearranged — every word on the page, in the order the slide's text
boxes came out rather than the order the model wrote them. For a tool whose
entire promise is *check this figure in two seconds*, a quote you can `Ctrl+F` is
worth something. It does not move the hallucination rate, which is zero for all
three.

**Haiku is the one with a real gap**, and it is not in the headline number
either: on Rokoko it found 8 of 16 customer logos where the other two found all
16, and it misreads proper nouns off slide images — Bryter's "Mike Chalfen" came
back as "Mike Chaifen", "Michael Mitterlehner" as "Michael Mittendorfer". For a
tool whose output is largely names, that is disqualifying at a fifth of the
price.

**So: run it on Sonnet 5.** Reach for Opus when the provenance has to be
literally quotable, or on decks harder than these.

### Where the flags still fail

Recall is 0.51 at best, and the summary now breaks it down by kind so a gain in
one cannot hide behind the total:

| Flag kind | opus | sonnet | haiku | in the key |
|---|---|---|---|---|
| missing | 21 | 21 | 19 | 28 |
| contradiction | 0 | 1 | 1 | 3 |
| unsupported | 0 | 0 | 0 | 11 |
| unverified | 0 | 0 | 0 | 1 |

**Eleven of the 43 expected flags are unsupported market claims** — *"$30bn
SAM"* with no derivation, *"category leader"* with no share data — and all three
models catch none of them. That is not a prompt problem. There is no market
field in the schema for such a claim to hang on, so the flagging pass never sees
it. It is the single biggest gap and the next honest piece of work after OCR.

**Contradictions: 1 of 3, and no false ones.** All three runs find Wunderlist's
500,000 daily active users against the 450k charted two slides later. None finds
Heal's or Rokoko's, both of which went in as images end to end. Across all 24
deck-runs the tool produced **zero contradiction flags that the answer key does
not ask for** — the conservative prompt bought precision at the cost of recall,
which is the trade this file argues for everywhere else.

### Recall alone is a metric you can game

Flagging everything scores perfect recall. So the run also counts the flags it
produced that the key does **not** ask for: 20 of 41 on Opus and Sonnet, 21 of
41 on Haiku. That is not a false-positive count — the key is one reader's list
of what matters in a deck, not an exhaustive one — and reading them by hand is
the point.

One of them is the tool being right and the key being wrong. On Rokoko it
reports `redacted: revenue`; the key asks for `missing: revenue`. The key's own
note reads *"the ARR chart and the full financial projections table are all
overlaid with 'Redacted'"* — which is the distinction `status` exists to make.
The label is what needs changing, not the tool.

### What the answer key actually is

The labels were drafted by a larger model reading the decks without a schema and
without time pressure, then reviewed and corrected by hand. So the accuracy
figure measures agreement between a constrained extractor and an unconstrained
one, filtered through a human — not correctness against ground truth.

Reviewing mattered. One label was outright wrong: `langfuse` had `round_size`
set to the $4M **total raised to date**, which is not the round being raised.
The extractor returned null, correctly, because of a rule about funding-history
slides — so a rule in the prompt caught an error in its own answer key.

Free text (`one_liner`) is excluded from the accuracy count, because two correct
one-line descriptions of the same company rarely match as strings. Names are
compared with accents folded, so a label typed as "Sondergaard" does not mark
"Søndergaard" wrong.

### What the eight remaining misses are

Eight wrong fields on the Sonnet run. Read one at a time, **two are real**:

- **`hypt.investors`: returned empty, the deck names seven** (Venpace, SixThirty,
  Core Angels, Gateway Ventures, SICTIC, NCA, Swisspreneur). The `investors`
  description spends its words on what does *not* count — press logos, customers,
  advisors — and apparently talked the model out of the ones that do.
- **`hypt.location`: null, and the answer is on the slide.** Haiku found
  Switzerland on the same page. A plain miss.

**Three are `sector`, and all three are arguments rather than errors.** Is hypt
fintech or B2B SaaS? Rokoko deeptech or SaaS? Wunderlist consumer or SaaS?
Reasonable people differ on every one, and one-word `sector` forces a single
answer where the honest one is two tags. Three of eight misses landing on one
field is the field telling you it is badly specified.

**Two are the scorer, not the extractor.**

- `stage`: `"Seed Extension"` against a label of `"seed extension round"`. Same
  answer, one trailing noun, exact string comparison on a half-open vocabulary.
- `founders`: the extractor returned Pascal Sollberger, Tobias Wegmüller and
  Roger Ellenberger. The label holds the same three people with their roles baked
  into the strings — `"Pascal Sollberger (Co-CEO)"` — so set overlap scores zero
  on a perfect answer. The label format is wrong, not the extraction.

**One is a genuine miss on a hard page:** `Heal.users`, where the deck states
200,000 house calls and the extractor returned null. Heal went in as 23 images
with no text layer at all.

So the honest reading of 0.789 is: **two extraction faults, one hard-page miss,
three disputes about a field that should not be single-valued, and two scoring
artifacts.** Fixing the scorer and splitting `sector` would move the number
without the tool getting any better, which is worth knowing before anyone quotes
it.

### Where the hallucination rate comes from

Pitch decks are almost entirely graphics, so **72% of the provenance in this run
cannot be verified by the harness at all**. Most decks need OCR and cannot be
read as text, so a quote on an image page can only be judged "cannot tell", not
"invented".

An earlier version of the harness counted every unverifiable quote as a
hallucination and reported a rate of 92%. That number was meaningless, and the
fix was to separate "wrong" from "cannot tell" rather than let a scary figure
stand. OCR is the next real piece of work on this project.

**The same harness was wrong a second time, in the same direction.** The check
was `quote.lower() in page_text.lower()` — an exact substring. Two things break
that, and neither is the model lying:

- **Line breaks.** A quote running across two lines on the slide has a newline
  in the text layer and a space in the model's answer. Three of the seven
  flagged values were that and nothing else.
- **Slide layout.** A slide is a grid of separate text boxes, and pdfplumber
  emits them in its own order. hypt's metrics slide reads `$ 700k ARR` to a
  human; the text layer has `$ 700k` in one box and `ARR` in another with half a
  slide in between. The quote is accurate and the substring test fails.

A quote now counts as supported if it is on the page verbatim, or if **every
word of it is on the page and the value being reported is on the page too**.
Only what fails both is a hallucination. Its weakness, stated rather than
hidden: a quote that recombines words genuinely on the page would pass, so the
verbatim count is reported separately and is the one to watch.

Checked by hand against the cached runs afterwards, every flagged value turned
out to be real text on the real page. **Neither model invented a single one of
the values the harness can check.** That is a much narrower claim than it
sounds: only 13 of 46 values are checkable at all, and the other 33 came off
image pages where nothing can be verified. The honest sentence is *"of the
values I can check, none were invented, and I can only check a quarter of
them"* — which is exactly why OCR is item 1 below and not item 4.

## Problems that come up with many decks

- **Filenames don't represent.** Juno's deck is called `Juno_s_4M_pitch_deck...`
  and never states a round size anywhere inside. langfuse's filename carries a
  date the deck does not. The prompt now says the filename is not part of the
  document.
- **Decks do not date themselves.** One of eight carries a date (Rokoko, in a
  running header). This is why `deck_date` is usually null, and why an evergreen
  holder has to record the date a deck *arrived* rather than hoping to read it.
- **The company name can disagree with the file.** Tinder's deck brands itself
  Match Box.
- **Logo walls are ambiguous.** Press coverage, customers, partners and
  investors all appear as grids of logos under different headings, and telling
  them apart is most of what `investors` and `customers` have to get right.

## How this was built

Written over a week, working with Claude as a pair. Being exact about that,
because the division of labour is the point rather than a disclaimer.

**Claude wrote most of the code and much of this document.** The ingestion,
scoring, memo rendering, CLI, cache and eval harness are largely its work, as is
the first draft of the extraction prompt.

**The design decisions are mine, and they are what make this specific to a family
office rather than a generic deck parser:**

- `status` as three values — stated, redacted, absent — because a blacked-out
  revenue slide and a deck that never mentions revenue call for opposite
  responses from a reader. This came from noticing Rokoko's redactions.
- The `investors` and `deck_date` fields, because who else is already in is a
  primary screen for an evergreen holder, and a deck's age changes what its
  stage means.
- The rule that funding-history and roadmap slides are not the current raise.
  That rule then caught an error in my own answer key: a label had recorded
  langfuse's total-raised-to-date as its round size, and the extractor was right
  to return null.
- Catching that the drafted labels flagged contradictions too aggressively, and
  that `sector` was conflating business model with industry.

## Design notes

- **No agent framework.** One call with the whole deck against one tool schema is
  easier to read and debug than a graph, and nothing here needs one.
- **The tool is asked for, not forced.** The call used
  `tool_choice={"type": "tool"}` until Opus 5.5, which rejects forced tool use
  with a 400. The documented replacement is strict tool use, and this schema
  cannot take it as written: strict allows 16 union-typed parameters and the
  schema has 25, because every optional value is `["string", "null"]`. Making
  those optional-instead-of-nullable is the honest fix and it is a schema
  decision, so for now the call uses `tool_choice: auto` with the prompt naming
  the tool.
- **One retry when the model answers in prose.** Asking for a tool is not
  forcing it, so a failure mode that forced tool use had closed is open again.
  It is not theoretical: Opus 5.5 did it on Wunderlist, wrote a good summary in
  prose and returned nothing the pipeline could use. The retry hands the model
  its own prose back and asks for the same reading through the tool. Retries are
  counted in the run summary, because a run that needed three is not the same
  result as a run that needed none.
- **No vector database.** The corpus is one deck plus a thesis file. Retrieval
  over eight documents is a `for` loop; reaching for RAG here would be
  decoration.
- **Graphic pages go in as images.** Most decks are almost entirely graphics, so
  pages with a thin text layer are rasterised and everything else stays text.
  In this set that means **96 of 120 pages went in as images**, and six of the
  eight decks went in with no text at all. All 24 text pages belong to two decks,
  hypt (11 of 12) and langfuse (13 of 15) — which is why every checkable quote in
  the table below comes from those two, and why the hallucination rate is
  measured on so few values.
- **The thesis is data, not code** (`thesis.yaml`), so the tool works for a
  different mandate without touching the source.
- **Rules live in the schema where a schema can hold them.** `status` is an
  `enum`, not a sentence asking nicely for one of three values. Field guidance
  sits in each field's description rather than in one long prompt.
- **Model calls are cached on disk**, keyed on the deck bytes, the model, the
  prompt and the schema — so iterating on a description is a cache miss, but
  re-running an unchanged pipeline is free.

## Next, in order

1. **OCR the rasterised pages**, so quoted provenance becomes checkable on the
   72% of values that currently cannot be verified. This is the single change
   that would make the headline metric mean something.
2. **A `market_claims` field**, so the eleven unsupported market claims in the
   answer key have somewhere to land. Right now the flagging pass cannot see
   them at all and scores 0 of 11 on every model — the largest single gap in
   flag recall, and a schema gap rather than a prompt one.
3. **Strict tool use**, which means reworking nullability in the schema so the
   union count drops below 16. That would move schema conformance from "the
   model complied" to "the decoder could not have done otherwise."
4. **JPEG instead of PNG for page images.** Bryter uploads 5.3 MB as PNG; JPEG
   at quality 80 would be several times smaller for no visible loss on a slide,
   cutting cost and latency across every run.
5. **A `founded` field, and multi-tag `sector`.** Company age is stated far more
   often than a deck date, and one sector label per company is demonstrably too
   few.
6. **More decks, chosen for difficulty** rather than count — scans, German-language
   decks, decks with dense financial tables.
7. **Deploy it** behind the existing FastAPI wrapper so it can be used without a
   terminal.

## Layout

```
readit/ingest.py    deck -> pages of text, images for graphic pages
readit/extract.py   pages -> structured fields with provenance
readit/flags.py     what the deck does not say
readit/score.py     thesis fit, with reasons
readit/memo.py      the one page a human reads
readit/cache.py     disk cache for model calls
evals/review.py     one deck, extraction against label
evals/run_eval.py   all decks, the numbers above
deploy/             FastAPI wrapper, written but not deployed
```

## Data

Public decks only. Nothing confidential, and nothing a founder shared with me
in private.
