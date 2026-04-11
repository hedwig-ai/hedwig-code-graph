"""Lightweight language detection using Unicode script analysis.

No external dependencies — uses Unicode character ranges to classify text
as English-only or multilingual. This determines which embedding model
to use for text nodes.

Strategy: Sample text nodes, count characters by script, classify:
- >90% Latin+ASCII → English ("en")
- Otherwise → multilingual ("multilingual")
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Unicode ranges for non-Latin scripts commonly found in code documentation
_CJK_RANGE = re.compile(
    r"[\u3000-\u9fff\uf900-\ufaff\U00020000-\U0002a6df"
    r"\uac00-\ud7af"  # Korean Hangul
    r"\u3040-\u309f\u30a0-\u30ff"  # Japanese Hiragana + Katakana
    r"]"
)
_CYRILLIC_RANGE = re.compile(r"[\u0400-\u04ff]")
_ARABIC_RANGE = re.compile(r"[\u0600-\u06ff]")
_DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097f]")
_THAI_RANGE = re.compile(r"[\u0e00-\u0e7f]")

# Characters to ignore when counting (whitespace, digits, punctuation, code symbols)
_IGNORE = re.compile(r"[\s\d\x00-\x2f\x3a-\x40\x5b-\x60\x7b-\x7f]")


def _count_scripts(text: str) -> dict[str, int]:
    """Count characters by script category."""
    counts: dict[str, int] = {"latin": 0, "cjk": 0, "cyrillic": 0, "other": 0}
    for ch in text:
        if _IGNORE.match(ch):
            continue
        if _CJK_RANGE.match(ch):
            counts["cjk"] += 1
        elif _CYRILLIC_RANGE.match(ch):
            counts["cyrillic"] += 1
        elif _ARABIC_RANGE.match(ch):
            counts["other"] += 1
        elif _DEVANAGARI_RANGE.match(ch):
            counts["other"] += 1
        elif _THAI_RANGE.match(ch):
            counts["other"] += 1
        elif ord(ch) < 0x0250:  # Basic Latin + Latin Extended
            counts["latin"] += 1
        else:
            counts["other"] += 1
    return counts


def detect_language(texts: list[str], threshold: float = 0.90) -> str:
    """Detect whether texts are English-only or multilingual.

    Samples up to 200 texts and analyzes Unicode script distribution.

    Args:
        texts: List of text strings to analyze.
        threshold: Fraction of Latin characters required to classify as "en".

    Returns:
        "en" if texts are predominantly English/Latin, "multilingual" otherwise.
    """
    if not texts:
        return "en"

    # Sample up to 200 texts for efficiency
    import random
    sample = texts if len(texts) <= 200 else random.sample(texts, 200)

    combined = " ".join(sample)
    counts = _count_scripts(combined)
    total = sum(counts.values())

    if total == 0:
        return "en"

    latin_ratio = counts["latin"] / total
    non_latin = counts["cjk"] + counts["cyrillic"] + counts["other"]

    logger.debug(
        "Language detection: %d chars, latin=%.1f%%, cjk=%d, cyrillic=%d, other=%d",
        total, latin_ratio * 100, counts["cjk"], counts["cyrillic"], counts["other"],
    )

    if latin_ratio >= threshold and non_latin < 10:
        return "en"
    return "multilingual"
