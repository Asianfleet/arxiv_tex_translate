from __future__ import annotations

import re
from pathlib import Path


DOCUMENT_BODY_PATTERN = re.compile(
    r"\\begin\{document\}(?P<body>.*)\\end\{document\}",
    re.DOTALL,
)


def merge_bilingual_caption(
    english: str,
    chinese: str,
    zh_color: str = "bilingualzhcolor",
) -> str:
    english_text = " ".join(english.split()).strip()
    chinese_text = " ".join(chinese.split()).strip()
    if english_text and chinese_text:
        return (
            f"{english_text} \\quad \\quad "
            + "{"
            + f"\\color{{{zh_color}}}"
            + "[翻译] "
            + chinese_text
            + "}"
        )
    if chinese_text:
        return "{" + f"\\color{{{zh_color}}}" + chinese_text + "}"
    return english_text


def _extract_document_body(tex: str) -> str:
    match = DOCUMENT_BODY_PATTERN.search(tex)
    if match is None:
        return tex.strip()
    return match.group("body").strip()


def generate_bilingual_tex(english_tex: str, chinese_tex: str) -> str:
    english_body = _extract_document_body(english_tex)
    chinese_body = _extract_document_body(chinese_tex)

    return (
        r"\documentclass[fontset=windows,UTF8]{article}"
        "\n"
        r"\usepackage{ctex}"
        "\n"
        r"\usepackage{xcolor}"
        "\n"
        r"\definecolor{bilingualzhcolor}{RGB}{128,128,128}"
        "\n"
        r"\begin{document}"
        "\n"
        + english_body
        + "\n\n"
        + r"\begingroup\color{bilingualzhcolor}"
        + "\n"
        + chinese_body
        + "\n"
        + r"\par\endgroup"
        + "\n"
        + r"\end{document}"
    )


def write_bilingual_tex(
    output_path: str | Path,
    english_tex: str,
    chinese_tex: str,
) -> Path:
    target = Path(output_path)
    target.write_text(generate_bilingual_tex(english_tex, chinese_tex), encoding="utf-8")
    return target
