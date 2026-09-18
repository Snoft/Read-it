"""Day 6. Upload a deck, get the memo. FastAPI + one template, no JS build step.

    uvicorn deploy.app:app --reload    then http://localhost:8000
"""
import tempfile
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse

from readit import ingest, extract as extract_mod, flags as flags_mod, score as score_mod, memo

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
THESIS = yaml.safe_load((ROOT / "thesis.yaml").read_text(encoding="utf8"))

app = FastAPI(title="Readit")

PAGE = """<!doctype html><meta charset=utf-8><title>Readit</title>
<style>body{font:16px/1.6 Garamond,Georgia,serif;max-width:44rem;margin:3rem auto;padding:0 1rem}
pre{white-space:pre-wrap}form{margin:2rem 0}</style>
<h1>Readit</h1><p>Deck in, screening memo out. Every number quoted with its page.</p>
<form method=post action=/screen enctype=multipart/form-data>
<input type=file name=file accept=application/pdf required> <button>Screen</button></form>
{body}"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE.format(body="")


@app.post("/screen", response_class=HTMLResponse)
async def run(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    deck = ingest.load(path)
    extraction = extract_mod.extract(deck)
    fl = flags_mod.find_flags(deck, extraction, THESIS)
    sc = score_mod.score(extraction, THESIS, fl)
    return PAGE.format(body="<pre>" + memo.render(extraction, fl, sc) + "</pre>")
