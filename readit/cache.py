"""Disk cache for model calls, so iterating does not re-buy the same answer.

Key it on everything that changes the result: the deck bytes, the model, and
your prompt. Change the prompt and the key changes, so you get a fresh call
without having to remember to clear anything.

    from readit.cache import cached

    @cached
    def _call(deck_path: str, model: str, prompt: str) -> dict:
        ...the actual API call...

Delete evals/.cache/ to force everything to re-run.
"""
import functools
import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "evals" / ".cache"


def _key(args, kwargs) -> str:
    h = hashlib.sha256()
    for a in list(args) + [kwargs[k] for k in sorted(kwargs)]:
        if isinstance(a, (str, Path)) and Path(str(a)).is_file():
            h.update(Path(str(a)).read_bytes())   # the deck itself, not its name
        else:
            h.update(repr(a).encode())
    return h.hexdigest()[:20]


def cached(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / f"{fn.__name__}-{_key(args, kwargs)}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf8"))
        result = fn(*args, **kwargs)
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf8")
        return result
    return wrapper
