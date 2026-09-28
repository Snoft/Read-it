"""The memo as a single HTML page, with every page number linking to that page of the deck.

Same content as memo.py: fields, flags, questions, score. The addition is that
each source is a link that opens the PDF at the cited page, so a figure can be
checked against its slide directly.

Everything the model returned is escaped before it goes on the page. A deck is
untrusted input and its text must never become markup.
"""
import datetime as _dt
import html as _h
import os
from pathlib import Path

from readit import memo as _memo

METRICS = ("revenue", "growth", "users", "round_size", "valuation")
LISTS = (("founders", "Founders"), ("customers", "Customers and logos"),
         ("investors", "Investors"), ("competitors", "Competitors"))
TEXTS = (("sector", "Sector"), ("stage", "Stage"), ("location", "Location"),
         ("deck_date", "Deck date"))
SEV = {"high": 0, "medium": 1, "low": 2}

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6b66;--line:#e4e1d8;--card:#fff;
--red:#b3261e;--redbg:#fbeceb;--amber:#8a5a00;--amberbg:#fdf3dc;--ok:#1f6f43;--link:#1b4d9b}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a3a29b;
--line:#34332f;--card:#1e1e1b;--red:#f2b8b5;--redbg:#3a1f1d;--amber:#f5d28a;--amberbg:#3a2f16;
--ok:#9fd8b4;--link:#9dbcf5}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:48rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
.top{display:flex;justify-content:space-between;gap:1rem;color:var(--muted);font-size:.85rem;
letter-spacing:.04em;text-transform:uppercase}
h1{font:600 2.2rem/1.15 Georgia,"Times New Roman",serif;margin:.6rem 0 .4rem}
h2{font:600 1.05rem/1.3 system-ui,sans-serif;margin:2.2rem 0 .7rem;padding-bottom:.35rem;
border-bottom:1px solid var(--line)}
.verdict{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.3rem 0 1rem}
.pill{display:inline-block;padding:.12rem .6rem;border-radius:999px;font-size:.8rem;font-weight:600;
border:1px solid var(--line);background:var(--card)}
.pill.v{background:var(--fg);color:var(--bg);border-color:var(--fg);text-transform:uppercase;letter-spacing:.04em}
.oneliner{font-size:1.1rem;color:var(--fg)}
table{width:100%;border-collapse:collapse}
td{vertical-align:top;padding:.65rem .5rem;border-bottom:1px solid var(--line)}
td.k{width:8.5rem;color:var(--muted);font-size:.9rem;padding-left:0}
td.v{font-weight:600;font-variant-numeric:tabular-nums}
.src{font-weight:400;display:block;margin-top:.2rem}
.q{display:block;color:var(--muted);font-style:italic;font-size:.88rem;font-weight:400;margin-top:.15rem}
a.p{color:var(--link);text-decoration:none;font-size:.82rem;font-weight:600;
border:1px solid var(--line);border-radius:6px;padding:.02rem .4rem;background:var(--card);white-space:nowrap}
a.p:hover{text-decoration:underline}
.st{font-size:.8rem;font-weight:600;padding:.1rem .5rem;border-radius:6px}
.st.redacted{color:var(--amber);background:var(--amberbg)}
.st.absent{color:var(--muted);background:transparent;border:1px dashed var(--line)}
.flag{border:1px solid var(--line);border-left-width:4px;border-radius:8px;background:var(--card);
padding:.7rem .9rem;margin:.55rem 0}
.flag.contradiction{border-left-color:var(--red);background:var(--redbg)}
.flag.redacted{border-left-color:var(--amber)}
.flag .kind{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.flag.contradiction .kind{color:var(--red)}
.quiet{color:var(--muted);font-size:.92rem;margin:.6rem 0 0}
ol.qs{padding-left:1.3rem}ol.qs li{margin:.4rem 0}
dl{display:grid;grid-template-columns:8.5rem 1fr;gap:.5rem .75rem;margin:0}
dt{color:var(--muted);font-size:.9rem}dd{margin:0}
ul.r{padding-left:1.1rem;color:var(--fg)}ul.r li{margin:.2rem 0}
.foot{margin-top:3rem;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:1rem}
@media (max-width:560px){td.k,dt{width:auto}dl{grid-template-columns:1fr}}
@media print{a.p{border:none}.flag{break-inside:avoid}}
"""


def _e(x) -> str:
    return _h.escape(str(x), quote=True)


def _href(deck_rel: str, page) -> str:
    return f"{deck_rel}#page={int(page)}"


def _plink(deck_rel: str, page) -> str:
    if not isinstance(page, int) or page < 1:
        return ""
    return (f'<a class="p" href="{_e(_href(deck_rel, page))}" target="_blank" '
            f'rel="noopener" title="Open the deck at page {page}">p.&nbsp;{page}&nbsp;↗</a>')


def _prov(field: dict, deck_rel: str) -> str:
    prov = field.get("provenance") or {}
    link = _plink(deck_rel, prov.get("page"))
    quote = (prov.get("source_quote") or "").strip()
    if len(quote) > 240:
        quote = quote[:237].rstrip() + "..."
    q = f'<span class="q">&ldquo;{_e(quote)}&rdquo;</span>' if quote else ""
    return f'<span class="src">{link}{q}</span>' if (link or q) else ""


def _metric_row(name: str, f: dict, deck_rel: str) -> str:
    label = name.replace("_", " ")
    v = f.get("value")
    if v is None:
        if f.get("status") == "redacted":
            body = ('<span class="st redacted">redacted in the deck</span> '
                    '&nbsp;ask for the unredacted figure')
            return f'<tr><td class="k">{_e(label)}</td><td>{body}{_prov(f, deck_rel)}</td></tr>'
        return (f'<tr><td class="k">{_e(label)}</td>'
                f'<td><span class="st absent">not stated in the deck</span></td></tr>')
    # "count" is implied by the field and "percent" reads better as a sign. No
    # other unit is guessed at: a growth figure with no unit stays a bare number,
    # and the quote underneath says whether it was 4x or 4%.
    u = (f.get("unit") or "").strip()
    unit = {"count": "", "percent": "%", "%": "%"}.get(u.lower(), f" {u}" if u else "")
    parts = [f"{_memo._num(v)}{unit}"]
    if f.get("period"):
        parts.append(str(f["period"]))
    if f.get("as_of"):
        parts.append(f"as of {f['as_of']}")
    shown = " · ".join(parts)
    return (f'<tr><td class="k">{_e(label)}</td>'
            f'<td class="v">{_e(shown)}{_prov(f, deck_rel)}</td></tr>')


def _flag_card(fl, deck_rel: str) -> str:
    links = " ".join(_plink(deck_rel, p) for p in (fl.pages or []))
    field = f" · {_e(str(fl.field).replace('_', ' '))}" if fl.field else ""
    return (f'<div class="flag {_e(fl.kind)}"><div class="kind">{_e(fl.kind)}{field}</div>'
            f'<div>{_e(fl.message)}</div>'
            f'{"<div style=margin-top:.35rem>" + links + "</div>" if links else ""}</div>')


def render(extraction: dict, flags: list, sc, deck_path, out_path, model: str | None = None) -> str:
    fields = extraction.get("fields", {}) or {}
    out_dir = Path(out_path).resolve().parent
    deck_rel = Path(os.path.relpath(Path(deck_path).resolve(), out_dir)).as_posix()

    company = extraction.get("company") or "Unknown company"
    stage = (fields.get("stage") or {}).get("value")
    loc = (fields.get("location") or {}).get("value")
    one = (fields.get("one_liner") or {}).get("value")

    pills = [f'<span class="pill v">{_e(sc.verdict)}</span>',
             f'<span class="pill">{sc.total:.0%} thesis fit</span>']
    pills += [f'<span class="pill">{_e(x)}</span>' for x in (stage, loc) if x]

    rows = "\n".join(_metric_row(k, fields.get(k) or {}, deck_rel) for k in METRICS)

    ordered = sorted(flags, key=lambda f: (f.kind != "contradiction", SEV.get(f.severity, 3)))
    # Low-severity absences (no location, undated, no investors named) are worth
    # knowing and not worth a card each: seven equal boxes bury the one that
    # matters. They go on one line under the rest.
    loud = [f for f in ordered if not (f.kind == "missing" and f.severity == "low")]
    quiet = [f for f in ordered if f.kind == "missing" and f.severity == "low"]
    flag_html = "\n".join(_flag_card(f, deck_rel) for f in loud)
    if quiet:
        names = ", ".join(str(f.field).replace("_", " ") for f in quiet)
        flag_html += f'\n<p class="quiet">Also not stated: {_e(names)}.</p>'
    flag_html = flag_html or "<p>Nothing flagged.</p>"

    qs = _memo._questions(flags) or ["Nothing obvious to probe: the deck answers the basics."]
    q_html = "".join(f"<li>{_e(q)}</li>" for q in qs)

    extra = []
    for key, label in TEXTS + LISTS:
        if key in ("stage", "location"):
            continue  # already in the header
        f = fields.get(key) or {}
        v = f.get("value")
        if v in (None, [], ""):
            continue
        shown = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
        extra.append(f"<dt>{_e(label)}</dt><dd>{_e(shown)}{_prov(f, deck_rel)}</dd>")
    extra_html = f"<dl>{''.join(extra)}</dl>" if extra else "<p>Nothing else stated.</p>"

    reasons = "".join(f"<li>{_e(r)}</li>" for r in sc.reasons)
    reasons += "".join(f"<li>not scored: {_e(u)}</li>" for u in sc.unscored)

    stamp = _dt.date.today().isoformat()
    meta = " · ".join(x for x in (model, stamp) if x)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(company)} · Readit</title><style>{CSS}</style></head>
<body><main>
<div class="top"><span>Readit · screening memo</span><span>{_e(meta)}</span></div>
<h1>{_e(company)}</h1>
<div class="verdict">{''.join(pills)}</div>
<p class="oneliner">{_e(one) if one else '<em>No one-line description in the deck.</em>'}</p>

<h2>The numbers</h2>
<table>{rows}</table>

<h2>What is missing or does not add up</h2>
{flag_html}

<h2>What to ask the founder</h2>
<ol class="qs">{q_html}</ol>

<h2>Also in the deck</h2>
{extra_html}

<h2>Why this score</h2>
<ul class="r">{reasons}</ul>

<p class="foot">Every figure links to the page it came from, with the words it was read
from. Nothing on this page is inferred. Source: {_e(Path(deck_path).name)}</p>
</main></body></html>"""


def write(extraction: dict, flags: list, sc, deck_path, out_path, model: str | None = None) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(extraction, flags, sc, deck_path, out, model), encoding="utf8")
    return out
