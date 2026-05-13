"""Code block and technical term preservation for translation."""

import re
from dataclasses import dataclass, field


MARKER_PATTERN = re.compile(r"\x00MEDIATOR_CODE_MARKER_(\d+)\x00")


@dataclass
class PreservationResult:
    preserved: dict[int, str] = field(default_factory=dict)
    processed_text: str = ""


def preserve_code_blocks(text: str) -> PreservationResult:
    result = PreservationResult()
    pattern = re.compile(r"(```[\s\S]*?```|`[^`]+`|\$[^\s]+|\b\w+\s*\([^\)]*\)\s*\{[^\}]*\})")

    def replacer(match: re.Match) -> str:
        idx = len(result.preserved)
        result.preserved[idx] = match.group(0)
        return f"\x00MEDIATOR_CODE_MARKER_{idx}\x00"

    result.processed_text = pattern.sub(replacer, text)
    return result


def restore_code_blocks(text: str, preserved: dict[int, str]) -> str:
    def replacer(match: re.Match) -> str:
        idx = int(match.group(1))
        return preserved.get(idx, match.group(0))

    return MARKER_PATTERN.sub(replacer, text)


PRESERVE_PATTERNS = [
    (re.compile(r"```[\s\S]*?```"), True),
    (re.compile(r"`[^`]+`"), True),
    (re.compile(r"\$\w+"), False),
    (re.compile(r"\b\w+\.\w+\s*\([^\)]*\)\s*;"), False),
    (re.compile(r"\b(import|from)\s+\w+"), False),
    (re.compile(r"\b\w+\s*=\s*\{[^}]+\}"), False),
    (re.compile(r"\{\{[^}]+\}\}"), False),
]


def should_preserve_token(token: str) -> bool:
    for pattern, _ in PRESERVE_PATTERNS:
        if pattern.search(token):
            return True
    return False
