from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Sequence

from .models import DocumentPlan
from .sanitize import sanitize_translation


def _count_translatable_segments(plan: DocumentPlan) -> int:
    return sum(1 for segment in plan.segments if segment.translatable)


def _validate_translation_count(plan: DocumentPlan, translations: Sequence[str]) -> None:
    expected = _count_translatable_segments(plan)
    actual = len(translations)
    if actual != expected:
        raise ValueError(
            f"translation 数量不匹配：期望 {expected} 条可翻译 segment 译文，实际收到 {actual} 条。"
        )


def _build_disclaimer(model_name: str, temperature: float) -> str:
    escaped_model = model_name.replace("_", r"\_")
    return (
        "\n"
        r"{\small\textbf{免责声明：} 当前大语言模型: "
        f"{escaped_model}"
        f"，温度: {temperature}。"
        "}\n"
    )


@dataclass(slots=True)
class RenderedSegment:
    translation_index: int
    line_start: int
    line_end: int
    start_offset: int


@dataclass(slots=True)
class RenderedDocument:
    tex: str
    translatable_segments: list[RenderedSegment]


def _compute_line_end(line_start: int, text: str) -> int:
    line_end = line_start + text.count("\n")
    if text.endswith("\n"):
        line_end -= 1
    return line_end


def _find_disclaimer_insert_index(rendered_tex: str) -> int:
    end_abstract = rendered_tex.find(r"\end{abstract}")
    if end_abstract >= 0:
        return end_abstract

    macro_match = re.search(r"\\abstract\s*\{", rendered_tex)
    if not macro_match:
        return 0

    depth = 1
    index = macro_match.end()
    while index < len(rendered_tex):
        char = rendered_tex[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return 0


def _render_document(
    plan: DocumentPlan,
    translations: Sequence[str],
    model_name: str,
    temperature: float,
    *,
    raw_translation_indexes: frozenset[int] = frozenset(),
) -> RenderedDocument:
    _validate_translation_count(plan, translations)

    parts: list[str] = []
    translatable_segments: list[RenderedSegment] = []
    offset = 0
    line_number = 1
    translation_index = 0

    for segment in plan.segments:
        if segment.translatable:
            if translation_index in raw_translation_indexes:
                segment_text = segment.source_text
            else:
                segment_text = sanitize_translation(
                    translations[translation_index],
                    segment.source_text,
                )
            translatable_segments.append(
                RenderedSegment(
                    translation_index=translation_index,
                    line_start=line_number,
                    line_end=_compute_line_end(line_number, segment_text),
                    start_offset=offset,
                )
            )
            translation_index += 1
        else:
            segment_text = segment.source_text

        parts.append(segment_text)
        offset += len(segment_text)
        line_number += segment_text.count("\n")

    rendered_tex = "".join(parts)
    disclaimer = _build_disclaimer(model_name, temperature)
    insert_index = _find_disclaimer_insert_index(rendered_tex)
    inserted_line_count = disclaimer.count("\n")

    if inserted_line_count:
        for rendered_segment in translatable_segments:
            if rendered_segment.start_offset >= insert_index:
                rendered_segment.line_start += inserted_line_count
                rendered_segment.line_end += inserted_line_count

    final_tex = rendered_tex[:insert_index] + disclaimer + rendered_tex[insert_index:]
    return RenderedDocument(tex=final_tex, translatable_segments=translatable_segments)


def render_translated_tex(
    plan: DocumentPlan,
    translations: Sequence[str],
    model_name: str,
    temperature: float,
) -> str:
    return _render_document(plan, translations, model_name, temperature).tex
