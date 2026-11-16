"""Shared checks: does a cited block actually contain a number?"""

import json
import re
from functools import lru_cache
from pathlib import Path

from .fields import within_tolerance

ROOT = Path(__file__).resolve().parent.parent
NUM = re.compile(r"\(?-?\$?\s?\d[\d,]*\.?\d*\)?")
# A block may state money in thousands, millions or billions; values are in millions.
SCALES = (1.0, 1e-3, 1e3)


@lru_cache(maxsize=None)
def blocks(ticker: str) -> dict[str, str]:
    p = ROOT / "prepared" / ticker / "blocks.json"
    return {b["id"]: b["text"] for b in json.loads(p.read_text())} if p.exists() else {}


def numbers_in(text: str) -> list[float]:
    out = []
    for tok in NUM.findall(text):
        neg = tok.startswith("(") and tok.endswith(")") or tok.lstrip("($ ").startswith("-")
        digits = re.sub(r"[^\d.]", "", tok)
        if not digits or digits == ".":
            continue
        try:
            v = float(digits.rstrip("."))
        except ValueError:
            continue
        out.append(-v if neg else v)
    return out


def matches(kind: str, value: float, n: float, scales=None) -> bool:
    if scales is None:
        scales = SCALES if kind == "money_mm" else (1.0,)
    return any(within_tolerance(kind, value, n * s) or within_tolerance(kind, abs(value), abs(n * s))
               for s in scales)


def block_contains(ticker: str, block_id: str | None, kind: str, value: float | None) -> bool:
    if value is None or not block_id:
        return False
    text = blocks(ticker).get(str(block_id).strip("[] "))
    if text is None:
        return False
    return any(matches(kind, value, n) for n in numbers_in(text))


def find_value(ticker: str, kind: str, value: float) -> list[str]:
    """All block ids whose text shows the value as written (no unit rescaling); used to
    diagnose retrieval errors, so it must not match by coincidence of scale."""
    return [bid for bid, text in blocks(ticker).items()
            if any(matches(kind, value, n, scales=(1.0,)) for n in numbers_in(text))]
