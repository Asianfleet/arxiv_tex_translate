import pytest

from src.latex.models import DocumentPlan, Segment, SpanKind


def _segment(
    index: int,
    source_text: str,
    *,
    translatable: bool,
    line_start: int,
    line_end: int,
    kind: SpanKind = SpanKind.TEXT,
) -> Segment:
    return Segment(
        index=index,
        kind=kind,
        source_text=source_text,
        translatable=translatable,
        line_start=line_start,
        line_end=line_end,
        reason="test",
    )


def _plan(*segments: Segment) -> DocumentPlan:
    return DocumentPlan(
        merged_tex="".join(segment.source_text for segment in segments),
        segments=list(segments),
    )


def _line_number_for(text: str, needle: str) -> int:
    index = text.index(needle)
    return text[:index].count("\n") + 1


def test_sanitize_translation_falls_back_on_traceback_marker():
    from src.latex.sanitize import sanitize_translation

    original = "Original text."
    translated = "[Local Message]\nTraceback\nbroken"

    assert sanitize_translation(translated, original) == original


def test_sanitize_translation_escapes_percent_and_removes_command_space():
    from src.latex.sanitize import sanitize_translation

    sanitized = sanitize_translation(r"Rate is 50% and \textbf {value}.", "Original")

    assert sanitized == r"Rate is 50\% and \textbf{value}."


def test_sanitize_translation_falls_back_when_begin_count_changes():
    from src.latex.sanitize import sanitize_translation

    original = r"\begin{itemize}item\end{itemize}"
    translated = "plain text"

    assert sanitize_translation(translated, original) == original


def test_render_translated_tex_inserts_disclaimer_before_first_abstract_end():
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, r"\begin{abstract}", translatable=False, line_start=1, line_end=1),
        _segment(1, "Original abstract 100%.", translatable=True, line_start=2, line_end=2),
        _segment(2, r"\end{abstract}", translatable=False, line_start=3, line_end=3),
        _segment(3, "\n", translatable=False, line_start=4, line_end=4),
        _segment(4, "Original body.", translatable=True, line_start=5, line_end=5),
    )

    rendered = render_translated_tex(
        plan,
        translations=["Translated abstract 50%.", "Translated body."],
        model_name="gpt_5_mini",
        temperature=0.3,
    )

    abstract_end = rendered.index(r"\end{abstract}")
    disclaimer = rendered[:abstract_end]
    assert "Translated abstract 50\\%." in rendered
    assert "当前大语言模型: gpt\\_5\\_mini" in disclaimer
    assert "温度: 0.3" in disclaimer
    assert rendered.index("Translated body.") > abstract_end


def test_render_translated_tex_inserts_disclaimer_inside_abstract_macro_with_space():
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, r"\abstract {", translatable=False, line_start=1, line_end=1),
        _segment(1, "Original abstract.", translatable=True, line_start=1, line_end=1),
        _segment(2, "}", translatable=False, line_start=1, line_end=1),
        _segment(3, "\nBody", translatable=False, line_start=2, line_end=2),
    )

    rendered = render_translated_tex(
        plan,
        translations=["Translated abstract."],
        model_name="gpt_5_macro",
        temperature=0.4,
    )

    assert rendered.startswith(r"\abstract {")
    disclaimer_index = rendered.index("当前大语言模型: gpt\\_5\\_macro")
    assert disclaimer_index > rendered.index(r"\abstract {")
    assert disclaimer_index < rendered.rindex("}")


def test_render_translated_tex_raises_on_translation_count_mismatch():
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, "A", translatable=True, line_start=1, line_end=1),
        _segment(1, "B", translatable=True, line_start=2, line_end=2),
    )

    with pytest.raises(ValueError, match="translation"):
        render_translated_tex(plan, ["only one"], "gpt_5", 0.2)


def test_render_translated_tex_keeps_non_translatable_segments_without_consuming_index():
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, "HEAD-", translatable=False, line_start=1, line_end=1),
        _segment(1, "alpha", translatable=True, line_start=2, line_end=2),
        _segment(2, "-MID-", translatable=False, line_start=3, line_end=3),
        _segment(3, "beta", translatable=True, line_start=4, line_end=4),
    )

    rendered = render_translated_tex(plan, ["译文一", "译文二"], "model_name", 0.5)

    assert "HEAD-译文一-MID-译文二" in rendered


def test_extract_buggy_lines_returns_sorted_unique_matches_for_target_tex():
    from src.latex.recovery import extract_buggy_lines

    log_text = "\n".join(
        [
            "merge_translate_zh.tex:18: Undefined control sequence.",
            "other.tex:7: ignored",
            "merge_translate_zh.tex:12: Missing $ inserted.",
            "merge_translate_zh.tex:18: repeated",
        ]
    )

    assert extract_buggy_lines(log_text, "merge_translate_zh.tex") == [12, 18]


def test_recover_rendered_tex_rolls_back_segments_near_buggy_lines_only():
    from src.latex.recovery import recover_rendered_tex
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, "P-\n", translatable=False, line_start=1, line_end=1),
        _segment(1, "Orig A", translatable=True, line_start=10, line_end=12),
        _segment(2, "\n-X-\n", translatable=False, line_start=13, line_end=13),
        _segment(3, "Orig B", translatable=True, line_start=30, line_end=32),
        _segment(4, "\n-Y-\n", translatable=False, line_start=33, line_end=33),
        _segment(5, "Orig C", translatable=True, line_start=40, line_end=42),
    )
    translations = ["译文A", "译文B", "译文C"]
    rendered_target = render_translated_tex(plan, translations, "gpt_5_model", 0.7)
    buggy_line = _line_number_for(rendered_target, "译文B")

    rendered = recover_rendered_tex(
        plan,
        translations=translations,
        buggy_lines=[buggy_line],
        model_name="gpt_5_model",
        temperature=0.7,
        window=0,
    )

    assert "P-\n译文A\n-X-\nOrig B\n-Y-\n译文C" in rendered
    assert "当前大语言模型: gpt\\_5\\_model" in rendered


def test_recover_rendered_tex_uses_rendered_line_numbers_after_newline_and_disclaimer_shifts():
    from src.latex.recovery import recover_rendered_tex
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, "\\begin{abstract}\n", translatable=False, line_start=1, line_end=1),
        _segment(1, "Original abstract.", translatable=True, line_start=2, line_end=2),
        _segment(2, "\n\\end{abstract}\n", translatable=False, line_start=3, line_end=4),
        _segment(3, "Body one.", translatable=True, line_start=5, line_end=5),
        _segment(4, "\n", translatable=False, line_start=6, line_end=6),
        _segment(5, "Body two.", translatable=True, line_start=7, line_end=7),
    )
    translations = ["摘要第一行\n摘要第二行", "正文一\n多一行\n再一行", "正文二"]

    rendered = render_translated_tex(plan, translations, "gpt_5_shift", 0.6)
    buggy_line = _line_number_for(rendered, "正文二")

    recovered = recover_rendered_tex(
        plan,
        translations=translations,
        buggy_lines=[buggy_line],
        model_name="gpt_5_shift",
        temperature=0.6,
        window=0,
    )

    assert "正文一\n多一行\n再一行" in recovered
    assert "Body two." in recovered
    assert "正文二" not in recovered


def test_recover_rendered_tex_restores_exact_original_without_sanitize_changes():
    from src.latex.recovery import recover_rendered_tex
    from src.latex.render import render_translated_tex

    original = r"Rate 50% and \textbf {raw}"
    plan = _plan(
        _segment(0, original, translatable=True, line_start=1, line_end=1),
    )
    rendered_target = render_translated_tex(plan, ["译文"], "gpt_5_exact", 0.2)
    buggy_line = _line_number_for(rendered_target, "译文")

    recovered = recover_rendered_tex(
        plan,
        translations=["译文"],
        buggy_lines=[buggy_line],
        model_name="gpt_5_exact",
        temperature=0.2,
        window=0,
    )

    assert original in recovered
    assert r"Rate 50\% and \textbf{raw}" not in recovered


def test_recover_rendered_tex_does_not_overmatch_previous_segment_with_trailing_newline():
    from src.latex.recovery import recover_rendered_tex
    from src.latex.render import render_translated_tex

    plan = _plan(
        _segment(0, "A", translatable=True, line_start=1, line_end=1),
        _segment(1, "", translatable=False, line_start=2, line_end=2),
        _segment(2, "B", translatable=True, line_start=2, line_end=2),
    )
    translations = ["前一段\n", "后一段"]
    rendered_target = render_translated_tex(plan, translations, "gpt_5_tail", 0.1)
    buggy_line = _line_number_for(rendered_target, "后一段")

    recovered = recover_rendered_tex(
        plan,
        translations=translations,
        buggy_lines=[buggy_line],
        model_name="gpt_5_tail",
        temperature=0.1,
        window=0,
    )

    assert "前一段\n" in recovered
    assert "后一段" not in recovered
    assert "B" in recovered
