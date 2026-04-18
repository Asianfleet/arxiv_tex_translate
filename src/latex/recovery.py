from __future__ import annotations

import re
from collections.abc import Sequence

from .models import DocumentPlan
from .render import _render_document, _validate_translation_count


def extract_buggy_lines(log_text: str, tex_name: str) -> list[int]:
    pattern = re.compile(rf"{re.escape(tex_name)}:(\d{{1,5}}):")
    return sorted({int(line) for line in pattern.findall(log_text)})


def recover_rendered_tex(
    plan: DocumentPlan,
    translations: Sequence[str],
    buggy_lines: Sequence[int],
    model_name: str,
    temperature: float,
    window: int = 5,
) -> str:
    _validate_translation_count(plan, translations)

    rendered_document = _render_document(plan, translations, model_name, temperature)
    raw_translation_indexes: set[int] = set()
    for rendered_segment in rendered_document.translatable_segments:
        if any(
            rendered_segment.line_start - window <= line <= rendered_segment.line_end + window
            for line in buggy_lines
        ):
            raw_translation_indexes.add(rendered_segment.translation_index)

    return _render_document(
        plan,
        translations,
        model_name,
        temperature,
        raw_translation_indexes=frozenset(raw_translation_indexes),
    ).tex
