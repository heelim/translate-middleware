"""Korean language detection utilities."""

import re

HANGUL_PATTERN = re.compile(r"[\uAC00-\uD7A3]")
KOREAN_THRESHOLD = 0.3


def contains_korean(text: str) -> bool:
    if not text:
        return False
    korean_chars = len(HANGUL_PATTERN.findall(text))
    total_chars = len([c for c in text if c.isalpha()])
    if total_chars == 0:
        return False
    return (korean_chars / total_chars) > KOREAN_THRESHOLD


def detect_korean_ratio(text: str) -> float:
    if not text:
        return 0.0
    korean_chars = len(HANGUL_PATTERN.findall(text))
    total_chars = len([c for c in text if c.isalpha()])
    if total_chars == 0:
        return 0.0
    return korean_chars / total_chars
