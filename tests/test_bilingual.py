import importlib


def test_merge_bilingual_caption_keeps_english_and_colored_chinese():
    from src.latex.bilingual import merge_bilingual_caption

    merged = merge_bilingual_caption("Figure 1", "图 1")

    assert "Figure 1" in merged
    assert "图 1" in merged
    assert r"\color{bilingualzhcolor}" in merged
    assert "[翻译]" in merged


def test_generate_bilingual_tex_wraps_both_languages_in_minimal_document():
    from src.latex.bilingual import generate_bilingual_tex

    english_tex = (
        r"\documentclass{article}"
        "\n"
        r"\begin{document}"
        "\n"
        "English body"
        "\n"
        r"\end{document}"
    )
    chinese_tex = (
        r"\documentclass{article}"
        "\n"
        r"\begin{document}"
        "\n"
        "中文内容"
        "\n"
        r"\end{document}"
    )

    bilingual_tex = generate_bilingual_tex(english_tex, chinese_tex)

    assert r"\usepackage{ctex}" in bilingual_tex
    assert "English body" in bilingual_tex
    assert "中文内容" in bilingual_tex
    assert r"\begin{document}" in bilingual_tex
    assert r"\end{document}" in bilingual_tex


def test_generate_bilingual_tex_does_not_nest_source_document_wrappers():
    from src.latex.bilingual import generate_bilingual_tex

    english_tex = (
        r"\documentclass{article}"
        "\n"
        r"\begin{document}"
        "\n"
        "English body"
        "\n"
        r"\end{document}"
    )
    chinese_tex = (
        r"\documentclass{article}"
        "\n"
        r"\begin{document}"
        "\n"
        "中文内容"
        "\n"
        r"\end{document}"
    )

    bilingual_tex = generate_bilingual_tex(english_tex, chinese_tex)

    assert bilingual_tex.count(r"\documentclass") == 1
    assert bilingual_tex.count(r"\begin{document}") == 1
    assert bilingual_tex.count(r"\end{document}") == 1


def test_latex_package_exports_bilingual_helpers():
    latex_pkg = importlib.import_module("src.latex")
    bilingual = importlib.import_module("src.latex.bilingual")

    assert latex_pkg.merge_bilingual_caption is bilingual.merge_bilingual_caption
    assert latex_pkg.generate_bilingual_tex is bilingual.generate_bilingual_tex
    assert "merge_bilingual_caption" in latex_pkg.__all__
    assert "generate_bilingual_tex" in latex_pkg.__all__
