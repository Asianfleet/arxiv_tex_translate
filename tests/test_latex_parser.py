import importlib

import pytest

from src.latex import merge_project_tex
from src.latex.models import LatexSpan, Segment, SpanKind
from src.latex.parser import LatexStructureParser


def test_collect_spans_finds_abstract_environment_and_caption():
    parser = LatexStructureParser()
    tex = (
        r"\begin{abstract}This abstract text.\end{abstract}"
        "\n"
        r"\begin{figure}"
        "\n"
        r"\caption{Figure caption text.}"
        "\n"
        r"\end{figure}"
    )

    spans = parser.collect_spans(tex)

    abstract_spans = [span for span in spans if span.kind is SpanKind.ABSTRACT]
    caption_spans = [span for span in spans if span.kind is SpanKind.CAPTION]

    assert len(abstract_spans) == 1
    assert tex[abstract_spans[0].start : abstract_spans[0].end] == "This abstract text."
    assert abstract_spans[0].translatable is True
    assert len(caption_spans) == 1
    assert tex[caption_spans[0].start : caption_spans[0].end] == "Figure caption text."
    assert caption_spans[0].translatable is True


def test_collect_spans_finds_captionof_and_abstract_macro():
    parser = LatexStructureParser()
    tex = (
        r"\abstract{Macro abstract text.}"
        "\n"
        r"\captionof{table}{Table caption text.}"
    )

    spans = parser.collect_spans(tex)

    abstract_spans = [span for span in spans if span.kind is SpanKind.ABSTRACT]
    caption_spans = [span for span in spans if span.kind is SpanKind.CAPTION]

    assert len(abstract_spans) == 1
    assert tex[abstract_spans[0].start : abstract_spans[0].end] == "Macro abstract text."
    assert len(caption_spans) == 1
    assert tex[caption_spans[0].start : caption_spans[0].end] == "Table caption text."


def test_collect_spans_falls_back_when_latexwalker_raises(monkeypatch):
    parser = LatexStructureParser()
    tex = r"\section{Intro}"

    class BrokenWalker:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_latex_nodes(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("src.latex.parser.LatexWalker", BrokenWalker)

    spans = parser.collect_spans(tex)

    assert any(
        span.kind is SpanKind.COMMAND
        and tex[span.start : span.end] == r"\section{Intro}"
        and span.translatable is False
        for span in spans
    )


def test_collect_spans_prefers_latexwalker_success_path(monkeypatch):
    parser = LatexStructureParser()
    tex = r"\caption{Figure caption text.}"
    sentinel = LatexSpan(9, 29, SpanKind.CAPTION, True, "walker sentinel", priority=1)

    class WorkingWalker:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_latex_nodes(self, *args, **kwargs):
            return ([], 0, len(tex))

    monkeypatch.setattr("src.latex.parser.LatexWalker", WorkingWalker)
    monkeypatch.setattr(parser, "_collect_with_latexwalker", lambda value: [sentinel] if value == tex else [])

    def fail_fallback(_value):
        raise AssertionError("fallback should not be called on success path")

    monkeypatch.setattr(parser, "_collect_with_fallback", fail_fallback)

    assert parser.collect_spans(tex) == [sentinel]


def test_collect_spans_real_latexwalker_handles_macro_arguments_without_fallback(monkeypatch):
    parser = LatexStructureParser()
    tex = r"\section[Short]{Long Title}"

    def fail_fallback(_value):
        raise AssertionError("fallback should not be called when LatexWalker succeeds")

    monkeypatch.setattr(parser, "_collect_with_fallback", fail_fallback)

    spans = parser.collect_spans(tex)

    assert any(
        span.kind is SpanKind.COMMAND
        and tex[span.start : span.end] == tex
        and span.translatable is False
        for span in spans
    )


def test_collect_spans_fallback_handles_command_with_optional_argument(monkeypatch):
    parser = LatexStructureParser()
    tex = r"\section[Short]{Long Title}"

    class BrokenWalker:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_latex_nodes(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("src.latex.parser.LatexWalker", BrokenWalker)

    spans = parser.collect_spans(tex)

    assert any(
        span.kind is SpanKind.COMMAND
        and tex[span.start : span.end] == tex
        and span.translatable is False
        for span in spans
    )


def test_segment_matches_task5_schema_with_start_end_fields():
    field_names = list(Segment.__dataclass_fields__)

    assert field_names == [
        "index",
        "kind",
        "source_text",
        "translatable",
        "line_start",
        "line_end",
        "reason",
        "start",
        "end",
    ]
    assert Segment.__dataclass_fields__["start"].default == 0
    assert Segment.__dataclass_fields__["end"].default == 0


def test_latex_package_exports_parser_models_and_existing_merge_api():
    latex_pkg = importlib.import_module("src.latex")

    assert latex_pkg.merge_project_tex is merge_project_tex
    assert latex_pkg.LatexStructureParser is LatexStructureParser
    assert latex_pkg.LatexSegmenter is not None
    assert latex_pkg.plan_latex_document is not None
    assert latex_pkg.SpanKind is SpanKind
    assert "merge_project_tex" in latex_pkg.__all__
    assert "LatexStructureParser" in latex_pkg.__all__
    assert "LatexSegmenter" in latex_pkg.__all__
    assert "plan_latex_document" in latex_pkg.__all__
    assert "SpanKind" in latex_pkg.__all__
