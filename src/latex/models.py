from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SpanKind(StrEnum):
    PREAMBLE = "preamble"
    COMMAND = "command"
    ENVIRONMENT = "environment"
    MATH = "math"
    CAPTION = "caption"
    ABSTRACT = "abstract"
    TEXT = "text"


@dataclass(slots=True)
class LatexSpan:
    start: int
    end: int
    kind: SpanKind
    translatable: bool
    reason: str
    priority: int = 0


@dataclass(slots=True)
class Segment:
    index: int
    kind: SpanKind
    source_text: str
    translatable: bool
    line_start: int
    line_end: int
    reason: str
    start: int = 0
    end: int = 0


@dataclass(slots=True)
class DocumentPlan:
    merged_tex: str
    spans: list[LatexSpan] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    title: str = "unknown"
    abstract: str = "unknown"
