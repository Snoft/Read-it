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
who did what. It runs on command line, further info on the sections below.

## Why every value carries its source

As hallucinations are not fully avoidable (yet), sources were added to the model's outputs. 
Every value carries the page number and the sentence it came from. Untraceable values will
be counted as hallucinations and absent values seens as valid useful answers.

This design proves to be highly valuable, e.g. when the tool reported a decks stage as "Series B"
with the attached quote "2023 → Series B $25M" it was instantly clear the tool made an outdated error.
This can be fixed by further rules and tests on those sources. 

## Three values, not two

Metrics carry a `status` of `stated`, `redacted` or `absent`. This has become necessary as many decks are 
atypical with censoured, absent or as redacted marked values. This proved to improve results with such decks
dramatically. 

## What it flags

For now only simple flags e.g. *"There is no revenue figure anywhere in 23 slides"*
To avoid false positives (flags) it is kept simple and not too strict. Work in progress. 


## Quality

Measured, not asserted. Eight hand-labelled decks in `evals/labels/`.

```bash
python evals/run_eval.py
python evals/run_eval.py --model claude-haiku-4-5-20251001   # comparison run
```

| Model | Field accuracy | Hallucination rate | Flag recall |
|---|---|---|---|
| claude-sonnet-5 | **0.737** | **0.231** | 0.488 |
| claude-haiku-4.5 | 0.684 | 0.385 | 0.488 |

38 labelled field values across 8 decks. 46 values returned, of which **13 could
be checked** against a page with a text layer and 33 could not (see below).

**The comparison has a clear answer, and it is not about accuracy.** Haiku is a
fraction of the price and scores five points lower on fieldsand hallucinates 67% more. 
It misreads proper nouns off images and doesn't find the logos.
On Rokoko it found 8 of 16 customer logos; sonnet found all 16.
**Run this on sonnet or better.**

### What made claude sonnet 5 only 0.737 accurate?

Eight misses on the sonnet run, and only one is an extraction fault:

- **One real model error.** Heal lists Paul Jacobs as "Chairman & Founding
  Investor". The extractor read "Founding", put him in `founders`, and left
  `investors` empty. One sentence in the founders description would fix it.
- **Three are bad labels, not bad extraction.** `hypt` is labelled
  `sector: "b2b saas"` — mixing business model with sector, the exact confusion
  the schema is meant to prevent. `"Strategic round"` versus `"strategic"` and
  `"seed extension round"` versus `"Seed Extension"` are the same answer with a
  trailing noun; exact string comparison on a semi-open vocabulary is too strict
  a test, and two of the eight misses are only that.
- **Two are genuine disagreements.** Is Juno a marketplace or SaaS? Is Wunderlist
  consumer or SaaS? Reasonable people differ, which says single-label `sector`
  is a weak field. A real version would allow several tags.
- **One is a true miss.** Sonnet returned null for hypt's location; haiku found
  "Switzerland" on the same slide.

  Most of these are discussable ambigous results and a further notice about it's ambigouity
  could fix part of the problem.

### Where the hallucination rate comes from

Pitch decks are almost entirely graphics, so **72% of the provenance in this run cannot be
verified by the harness at all**. As most of the decks simply need OCR and cannot be read as
normal text more is marked as hallucination than what's actually the case.

## Problems that come up with many decks

- **Filenames dont represent.** Juno's deck is called `Juno_s_4M_pitch_deck...` and never
  states a round size anywhere inside. langfuse's filename carries a date the
  deck does not. The prompt now says the filename is not part of the document.
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

- **No agent framework.** One call with the whole deck under a forced schema is
  easier to read and debug than a graph, and nothing here needs one.
- **No vector database.** The corpus is one deck plus a thesis file. Retrieval
  over seven documents is a `for` loop; reaching for RAG here would be
  decoration.
- **Graphic pages go in as images.** Most decks are almost entirely graphics, so
  pages with a thin text layer are rasterised and everything else stays text.
  Every deck in this set went in fully as images.
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
2. **Contradiction detection** in `flags.py`, with the Wunderlist 500k/450k
   discrepancy as the first test case.
3. **JPEG instead of PNG for page images.** Bryter uploads 5.3 MB as PNG; JPEG
   at quality 80 would be several times smaller for no visible loss on a slide,
   cutting cost and latency across every run.
4. **A `founded` field, and multi-tag `sector`.** Company age is stated far more
   often than a deck date, and one sector label per company is demonstrably too
   few.
5. **More decks, chosen for difficulty** rather than count — scans, German-language
   decks, decks with dense financial tables.
6. **Deploy it** behind the existing FastAPI wrapper so it can be used without a
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
