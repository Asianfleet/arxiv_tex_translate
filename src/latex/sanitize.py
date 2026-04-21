from __future__ import annotations

import re


_UNESCAPED_PERCENT_RE = re.compile(r"(?<!\\)%")
_UNESCAPED_AMPERSAND_RE = re.compile(r"(?<!\\)&")
_COMMAND_BRACE_SPACE_RE = re.compile(r"(\\[A-Za-z@]+)\s+\{")
_LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z@]+")


def sanitize_translation(translated: str, original: str) -> str:
    sanitized = _UNESCAPED_PERCENT_RE.sub(r"\\%", translated)
    sanitized = _COMMAND_BRACE_SPACE_RE.sub(r"\1{", sanitized)

    if "[Local Message]" in sanitized and "Traceback" in sanitized:
        return original

    if sanitized.count(r"\begin") != original.count(r"\begin"):
        return original

    if _LATEX_COMMAND_RE.findall(sanitized) != _LATEX_COMMAND_RE.findall(original):
        return original

    original_alignment_markers = _UNESCAPED_AMPERSAND_RE.findall(original)
    if original_alignment_markers:
        return original

    if len(_UNESCAPED_AMPERSAND_RE.findall(sanitized)) != len(original_alignment_markers):
        return original

    return sanitized
