import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@contextmanager
def _case_dir(case_name: str):
    case_dir = Path("tests") / "_tmp_latex_merge" / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield case_dir
    finally:
        if case_dir.exists():
            shutil.rmtree(case_dir)


def test_find_main_tex_file_ignores_merge_and_scores_body_features():
    from src.latex.merge import find_main_tex_file

    with _case_dir("find_main") as case_dir:
        merge_file = _write(
            case_dir / "merge_main.tex",
            r"\documentclass{article}" "\n" r"\begin{document}merged\end{document}",
        )
        template_file = _write(
            case_dir / "template.tex",
            (
                r"\documentclass{article}"
                "\n"
                r"\begin{document}"
                "\n"
                r"\LaTeX manuscript Guidelines for reviewers and blind review citations"
                "\n"
                r"\end{document}"
            ),
        )
        main_file = _write(
            case_dir / "main.tex",
            (
                r"\documentclass{article}"
                "\n"
                r"\input{sections/intro}"
                "\n"
                r"See \ref{sec:intro} and \cite{demo}."
            ),
        )

        selected = find_main_tex_file([merge_file, template_file, main_file])

        assert selected == main_file


def test_remove_comments_preserves_escaped_percent():
    from src.latex.merge import remove_comments

    content = "\n".join(
        [
            "% drop me",
            "value % inline comment",
            r"keep \% percent",
            "  % drop me too",
            "plain",
        ]
    )

    expected = "\n".join(["value ", r"keep \% percent", "plain"])

    assert remove_comments(content) == expected


def test_remove_comments_distinguishes_even_and_odd_backslashes_before_percent():
    from src.latex.merge import remove_comments

    content = "\n".join(
        [
            r"two slashes \\% trim this comment",
            r"three slashes \\\% keep escaped percent",
        ]
    )

    expected = "\n".join(
        [
            r"two slashes \\",
            r"three slashes \\\% keep escaped percent",
        ]
    )

    assert remove_comments(content) == expected


def test_find_tex_file_ignore_case_resolves_missing_suffix():
    from src.latex.merge import find_tex_file_ignore_case

    with _case_dir("find_tex") as case_dir:
        target = _write(case_dir / "Sections" / "Intro.tex", "content")

        resolved = find_tex_file_ignore_case(case_dir / "Sections" / "Intro")

        assert resolved == target


def test_merge_project_tex_expands_recursive_inputs_and_removes_comments():
    from src.latex.merge import merge_project_tex, merge_tex_files

    with _case_dir("merge_project") as case_dir:
        _write(case_dir / "sections" / "nested.tex", "Nested text % hidden\n")
        _write(
            case_dir / "sections" / "intro.tex",
            "Intro line\n% remove this line\n\\input{sections/nested}\n",
        )
        main_file = _write(
            case_dir / "main.tex",
            (
                r"\documentclass{article}"
                "\n"
                "% remove this comment line\n"
                r"\begin{document}"
                "\n"
                r"\input{sections/intro}"
                "\n"
                r"\end{document}"
            ),
        )

        merged = merge_project_tex(case_dir, main_file)

        assert "Intro line" in merged
        assert "Nested text " in merged
        assert "% hidden" not in merged
        assert r"\input{sections/intro}" not in merged

        merged_plain = merge_tex_files(case_dir, main_file.read_text(encoding="utf-8"), "proofread")

        assert merged_plain == merged


def test_merge_project_tex_raises_for_missing_input():
    from src.latex.merge import merge_project_tex

    with _case_dir("missing_input") as case_dir:
        main_file = _write(
            case_dir / "main.tex",
            r"\documentclass{article}" "\n" r"\begin{document}" "\n" r"\input{missing}" "\n" r"\end{document}",
        )

        with pytest.raises(RuntimeError, match="missing"):
            merge_project_tex(case_dir, main_file)


def test_merge_tex_files_translate_zh_injects_preamble_and_default_abstract():
    from src.latex.merge import merge_tex_files

    with _case_dir("translate_zh") as case_dir:
        main = (
            r"\documentclass{article}"
            "\n"
            r"\title{Demo}"
            "\n"
            r"\begin{document}"
            "\n"
            r"\maketitle"
            "\n"
            "Body\n"
            r"\end{document}"
        )

        merged = merge_tex_files(case_dir, main, "translate_zh")

        assert r"\documentclass[fontset=windows,UTF8]{article}" in merged
        assert r"\usepackage{ctex}" in merged
        assert r"\usepackage{url}" in merged
        assert merged.index(r"\usepackage{ctex}") > merged.index(r"\documentclass[fontset=windows,UTF8]{article}")
        assert merged.index(r"\begin{abstract}") > merged.index(r"\maketitle")


def test_ensure_zh_preamble_respects_existing_abstract_and_insert_abstract_wrapper():
    from src.latex.merge import ensure_zh_preamble, insert_abstract

    with_existing_abstract = (
        r"\documentclass[twocolumn]{article}"
        "\n"
        r"\usepackage{url}"
        "\n"
        r"\begin{document}"
        "\n"
        r"\begin{abstract}Ready\end{abstract}"
        "\n"
        "Body\n"
        r"\end{document}"
    )

    ensured = ensure_zh_preamble(with_existing_abstract)

    assert r"\documentclass[twocolumn,fontset=windows,UTF8]{article}" in ensured
    assert ensured.count(r"\usepackage{url}") == 1
    assert ensured.count(r"\begin{abstract}") == 1

    no_abstract = (
        r"\documentclass{article}"
        "\n"
        r"\begin{document}"
        "\n"
        "Body\n"
        r"\end{document}"
    )
    inserted = insert_abstract(no_abstract)

    assert inserted.index(r"\begin{abstract}") > inserted.index(r"\begin{document}")


@pytest.mark.parametrize(
    "existing_ctex_line",
    [
        r"\usepackage[scheme=plain]{ctex}",
        r"\RequirePackage{ctex}",
    ],
)
def test_ensure_zh_preamble_detects_existing_ctex_variants(existing_ctex_line):
    from src.latex.merge import ensure_zh_preamble

    tex = (
        r"\documentclass{article}"
        "\n"
        + existing_ctex_line
        + "\n"
        + r"\begin{document}"
        + "\n"
        + "Body\n"
        + r"\end{document}"
    )

    ensured = ensure_zh_preamble(tex)

    assert ensured.count("ctex") == 1
    assert ensured.count(r"\usepackage{ctex}") == 0
