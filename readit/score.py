"""Thesis fit score. Done for you, and deliberately dull.

A score is only useful if the reasons come with it, so this returns both and the
memo prints the reasons underneath. Weights live in thesis.yaml.
"""
from dataclasses import dataclass, field as dc_field


@dataclass
class Score:
    total: float                              # 0..1
    reasons: list[str] = dc_field(default_factory=list)
    unscored: list[str] = dc_field(default_factory=list)  # no data, not scored as zero

    @property
    def verdict(self) -> str:
        if self.total >= 0.7:
            return "worth a call"
        if self.total >= 0.45:
            return "worth a second look"
        return "pass for now"


def _val(extraction: dict, name: str):
    f = extraction.get("fields", {}).get(name) or {}
    return f.get("value")


def _match(value, prefs: list, oks: list) -> tuple[float, str]:
    if value is None:
        return (None, "not stated")
    hay = " ".join(value).lower() if isinstance(value, list) else str(value).lower()
    for p in prefs:
        if p.lower() in hay:
            return (1.0, f"matches preferred ({p})")
    for o in oks:
        if o.lower() in hay:
            return (0.5, f"acceptable ({o})")
    return (0.0, "outside the thesis")


def score(extraction: dict, thesis: dict, flags: list | None = None) -> Score:
    flags = flags or []
    parts, reasons, unscored = [], [], []

    for key, fieldname in (("geography", "location"), ("stage", "stage"), ("sectors", "sector")):
        block = thesis.get(key, {})
        w = float(block.get("weight", 0))
        s, why = _match(_val(extraction, fieldname), block.get("preferred", []), block.get("acceptable", []))
        if s is None:
            unscored.append(f"{key}: not stated in the deck")
            continue
        parts.append((w, s))
        reasons.append(f"{key}: {why}")

    # team and traction are judged on flags rather than on a value match:
    # what is missing says more here than what is present.
    for key in ("team", "traction"):
        w = float(thesis.get(key, {}).get("weight", 0))
        hits = [f for f in flags if getattr(f, "field", None) in _FIELDS[key]]
        penalty = min(1.0, 0.34 * len(hits))
        parts.append((w, 1.0 - penalty))
        reasons.append(
            f"{key}: clean" if not hits else f"{key}: {len(hits)} flag(s) against it"
        )

    hard = [f for f in flags if getattr(f, "severity", "") == "high"]
    total = sum(w * s for w, s in parts) / (sum(w for w, _ in parts) or 1)
    if hard:
        total *= 0.5
        reasons.append(f"halved: {len(hard)} hard flag(s)")

    return Score(total=round(total, 3), reasons=reasons, unscored=unscored)


_FIELDS = {
    "team": {"founders", "team"},
    "traction": {"revenue", "growth", "users", "customers"},
}
