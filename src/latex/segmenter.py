from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable

from .models import DocumentPlan, LatexSpan, Segment, SpanKind
from .parser import LatexStructureParser

MATH_PRIORITY = 200


class LatexSegmenter:
    def build_plan(self, tex: str, debug_dir: str | Path | None = None) -> DocumentPlan:
        parser_spans = LatexStructureParser().collect_spans(tex)
        spans = _dedupe_spans([*parser_spans, *_collect_math_spans(tex)])
        segments = _build_segments(tex, spans)
        plan = DocumentPlan(merged_tex=tex, spans=spans, segments=segments)
        if debug_dir is not None:
            write_debug_log(plan, Path(debug_dir) / "debug_log.html")
        return plan


def plan_latex_document(tex: str, debug_log_path: str | Path | None = None) -> DocumentPlan:
    if debug_log_path is None:
        return LatexSegmenter().build_plan(tex)
    debug_path = Path(debug_log_path)
    if debug_path.suffix:
        plan = LatexSegmenter().build_plan(tex)
        write_debug_log(plan, debug_path)
        return plan
    return LatexSegmenter().build_plan(tex, debug_path)


def write_debug_log(plan: DocumentPlan, debug_log_path: str | Path) -> None:
    path = Path(debug_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        "<!doctype html>",
        '<html lang="en">',
        "<head><meta charset=\"utf-8\"><title>LaTeX Segment Debug Log</title></head>",
        "<body>",
        "<h1>LaTeX Segment Debug Log</h1>",
    ]
    for segment in plan.segments:
        rows.append(
            "<section>"
            f"<h2>segment #{segment.index}</h2>"
            f"<p>kind={html.escape(segment.kind.value)} "
            f"translatable={segment.translatable} "
            f"start={segment.start} "
            f"end={segment.end} "
            f"lines={segment.line_start}-{segment.line_end} "
            f"reason={html.escape(segment.reason)}</p>"
            f"<pre>{html.escape(segment.source_text)}</pre>"
            "</section>"
        )
    rows.extend(["</body>", "</html>"])
    path.write_text("\n".join(rows), encoding="utf-8")


def _build_segments(tex: str, spans: list[LatexSpan]) -> list[Segment]:
    boundaries = _collect_boundaries(tex, spans)
    segments: list[Segment] = []
    for start, end in zip(boundaries, boundaries[1:]):
        if start == end:
            continue
        span = _select_span(spans, start, end)
        segment = _make_segment(len(segments), tex, start, end, span)
        if _can_merge(segments[-1], segment) if segments else False:
            segments[-1] = _merge_segment(segments[-1], segment, tex)
        else:
            segments.append(segment)
    return [_replace_index(segment, index) for index, segment in enumerate(segments)]


def _collect_boundaries(tex: str, spans: list[LatexSpan]) -> list[int]:
    boundaries = {0, len(tex)}
    for span in spans:
        boundaries.add(max(0, min(len(tex), span.start)))
        boundaries.add(max(0, min(len(tex), span.end)))
    return sorted(boundaries)


def _select_span(spans: list[LatexSpan], start: int, end: int) -> LatexSpan | None:
    covering = [span for span in spans if span.start <= start and end <= span.end]
    if not covering:
        return None
    return max(covering, key=lambda span: (span.priority, span.end - span.start))


def _make_segment(index: int, tex: str, start: int, end: int, span: LatexSpan | None) -> Segment:
    if span is None:
        kind = SpanKind.TEXT
        translatable = True
        reason = "plain text"
    else:
        kind = span.kind
        translatable = span.translatable
        reason = span.reason
    return Segment(
        index=index,
        start=start,
        end=end,
        kind=kind,
        source_text=tex[start:end],
        translatable=translatable,
        line_start=_line_number_at(tex, start),
        line_end=_line_number_at(tex, end - 1),
        reason=reason,
    )


def _can_merge(left: Segment, right: Segment) -> bool:
    return (
        left.end == right.start
        and left.kind is not SpanKind.MATH
        and left.kind is right.kind
        and left.translatable == right.translatable
        and left.reason == right.reason
    )


def _merge_segment(left: Segment, right: Segment, tex: str) -> Segment:
    return Segment(
        index=left.index,
        start=left.start,
        end=right.end,
        kind=left.kind,
        source_text=tex[left.start : right.end],
        translatable=left.translatable,
        line_start=left.line_start,
        line_end=right.line_end,
        reason=left.reason,
    )


def _replace_index(segment: Segment, index: int) -> Segment:
    return Segment(
        index=index,
        start=segment.start,
        end=segment.end,
        kind=segment.kind,
        source_text=segment.source_text,
        translatable=segment.translatable,
        line_start=segment.line_start,
        line_end=segment.line_end,
        reason=segment.reason,
    )


def _line_number_at(tex: str, offset: int) -> int:
    clamped = max(0, min(len(tex), offset))
    return tex.count("\n", 0, clamped) + 1


def _dedupe_spans(spans: Iterable[LatexSpan]) -> list[LatexSpan]:
    unique: list[LatexSpan] = []
    seen: set[tuple[int, int, SpanKind, bool, str, int]] = set()
    for span in spans:
        if span.start >= span.end:
            continue
        key = (span.start, span.end, span.kind, span.translatable, span.reason, span.priority)
        if key in seen:
            continue
        seen.add(key)
        unique.append(span)
    return sorted(unique, key=lambda span: (span.start, span.end, span.priority))


def _collect_math_spans(tex: str) -> list[LatexSpan]:
    spans: list[LatexSpan] = []
    index = 0
    while index < len(tex):
        if _is_escaped(tex, index):
            index += 1
            continue
        if tex.startswith("$$", index):
            end = _find_unescaped_token(tex, "$$", index + 2)
            if end != -1:
                spans.append(_make_math_span(index, end + 2, "display math"))
                index = end + 2
                continue
        if tex[index] == "$":
            end = _find_inline_dollar(tex, index + 1)
            if end != -1:
                spans.append(_make_math_span(index, end + 1, "inline math"))
                index = end + 1
                continue
        if tex.startswith(r"\[", index):
            end = _find_unescaped_token(tex, r"\]", index + 2)
            if end != -1:
                spans.append(_make_math_span(index, end + 2, "display math"))
                index = end + 2
                continue
        if tex.startswith(r"\(", index):
            end = _find_unescaped_token(tex, r"\)", index + 2)
            if end != -1:
                spans.append(_make_math_span(index, end + 2, "inline math"))
                index = end + 2
                continue
        index += 1
    return spans


def _make_math_span(start: int, end: int, reason: str) -> LatexSpan:
    return LatexSpan(
        start=start,
        end=end,
        kind=SpanKind.MATH,
        translatable=False,
        reason=reason,
        priority=MATH_PRIORITY,
    )


def _find_inline_dollar(tex: str, start: int) -> int:
    index = start
    while index < len(tex):
        if tex[index] == "$" and not _is_escaped(tex, index) and not _is_previous_char_unescaped_dollar(tex, index):
            return index
        index += 1
    return -1


def _find_unescaped_token(tex: str, token: str, start: int) -> int:
    index = tex.find(token, start)
    while index != -1:
        if not _is_escaped(tex, index):
            return index
        index = tex.find(token, index + len(token))
    return -1


def _is_escaped(tex: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and tex[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _is_previous_char_unescaped_dollar(tex: str, index: int) -> bool:
    return index > 0 and tex[index - 1] == "$" and not _is_escaped(tex, index - 1)
