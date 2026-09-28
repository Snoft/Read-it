"""Disk cache for model calls.

The key is a hash of every argument. An argument that is the path of an existing
file is hashed by the file's bytes rather than its name, so a renamed deck still
hits the cache and an edited one does not. Anything that changes the result has
to be an argument for this to be correct, which is why extract._call takes the
prompt and the serialised tool schema.

    from readit.cache import cached

    @cached
    def _call(deck_path, model, prompt, tool_json, blocks_json) -> dict: ...

Entries live in evals/.cache/ (gitignored). Delete the folder to re-run everything.
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
