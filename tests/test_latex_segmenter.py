from pathlib import Path
import shutil

from src.latex.models import SpanKind
from src.latex.segmenter import LatexSegmenter, plan_latex_document


def _case_dir(case_name: str) -> Path:
    case_dir = Path("tests") / "_tmp_latex_segmenter" / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def test_latex_segmenter_build_plan_splits_caption_text_and_inline_math():
    tex = r"\begin{figure}\caption{Speed $v = x < y$ result.}\end{figure}"
    case_dir = _case_dir("debug_log")

    try:
        plan = LatexSegmenter().build_plan(tex, case_dir)

        caption_segments = [segment for segment in plan.segments if segment.kind is SpanKind.CAPTION]
        math_segments = [segment for segment in plan.segments if segment.kind is SpanKind.MATH]

        assert plan.merged_tex == tex
        assert any(segment.source_text == "Speed " and segment.translatable is True for segment in caption_segments)
        assert any(segment.source_text == " result." and segment.translatable is True for segment in caption_segments)
        assert len(math_segments) == 1
        assert math_segments[0].source_text == "$v = x < y$"
        assert math_segments[0].translatable is False
        assert math_segments[0].reason == "inline math"
        assert math_segments[0].start == tex.index("$v")
        assert math_segments[0].end == tex.index("$ result") + 1

        debug_path = case_dir / "debug_log.html"
        debug_html = debug_path.read_text(encoding="utf-8")
        assert "reason=inline math" in debug_html
        assert "kind=math" in debug_html
        assert f"start={math_segments[0].start}" in debug_html
        assert f"end={math_segments[0].end}" in debug_html
        assert "$v = x &lt; y$" in debug_html
    finally:
        shutil.rmtree(case_dir)


def test_plan_latex_document_is_thin_wrapper_for_default_segmenter():
    tex = "Plain text only."

    direct_plan = LatexSegmenter().build_plan(tex)
    wrapped_plan = plan_latex_document(tex)

    assert wrapped_plan == direct_plan


def test_latex_segmenter_build_plan_uses_absolute_line_numbers():
    tex = "\n".join(
        [
            "Intro text.",
            "Before math.",
            "Equation $x",
            "+ y$ done.",
            r"\caption{Caption on line five.}",
        ]
    )

    plan = LatexSegmenter().build_plan(tex)

    math_segment = next(segment for segment in plan.segments if segment.kind is SpanKind.MATH)
    caption_segment = next(segment for segment in plan.segments if segment.source_text == "Caption on line five.")

    assert math_segment.line_start == 3
    assert math_segment.line_end == 4
    assert caption_segment.line_start == 5
    assert caption_segment.line_end == 5


def test_latex_segmenter_build_plan_merges_adjacent_plain_text_fragments():
    tex = "Plain text only.\nStill plain."

    plan = LatexSegmenter().build_plan(tex)

    assert len(plan.segments) == 1
    assert plan.segments[0].source_text == tex
    assert plan.segments[0].kind is SpanKind.TEXT
    assert plan.segments[0].translatable is True
    assert plan.segments[0].start == 0
    assert plan.segments[0].end == len(tex)


def test_latex_segmenter_build_plan_splits_adjacent_inline_math_spans():
    tex = r"\caption{Pair $x$$y$ done}"

    plan = LatexSegmenter().build_plan(tex)

    math_segments = [segment for segment in plan.segments if segment.kind is SpanKind.MATH]
    caption_segments = [segment for segment in plan.segments if segment.kind is SpanKind.CAPTION]

    assert [segment.source_text for segment in math_segments] == [r"$x$", r"$y$"]
    assert all(segment.translatable is False for segment in math_segments)
    assert any(segment.source_text == "Pair " for segment in caption_segments)
    assert any(segment.source_text == " done" for segment in caption_segments)


def test_latex_segmenter_build_plan_splits_bracket_display_math_inside_caption():
    tex = r"\caption{before \[x<y\] after}"

    plan = LatexSegmenter().build_plan(tex)

    math_segments = [segment for segment in plan.segments if segment.kind is SpanKind.MATH]
    caption_segments = [segment for segment in plan.segments if segment.kind is SpanKind.CAPTION]

    assert len(math_segments) == 1
    assert math_segments[0].source_text == r"\[x<y\]"
    assert math_segments[0].translatable is False
    assert math_segments[0].reason == "display math"
    assert any(segment.source_text == "before " for segment in caption_segments)
    assert any(segment.source_text == " after" for segment in caption_segments)
