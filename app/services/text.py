from __future__ import annotations

import math
import re
from collections import Counter


WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def lexical_similarity(left: str, right: str) -> float:
    left_counts = Counter(tokenize(left))
    right_counts = Counter(tokenize(right))
    if not left_counts or not right_counts:
        return 0.0
    common = set(left_counts) & set(right_counts)
    dot = sum(left_counts[t] * right_counts[t] for t in common)
    left_norm = math.sqrt(sum(v * v for v in left_counts.values()))
    right_norm = math.sqrt(sum(v * v for v in right_counts.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def normalize_value(value: str) -> str:
    return value.strip().lower().replace("degrees", "").replace("degree", "").replace("celsius", "").strip()


def numeric_value(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None

