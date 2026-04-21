from __future__ import annotations

import re
from pathlib import Path


DOCUMENT_PATTERN = re.compile(
    r"(?P<preamble>.*)\\begin\{document\}(?P<body>.*)\\end\{document\}",
    re.DOTALL,
)
LEADING_MAKETITLE_PATTERN = re.compile(r"^\s*\\maketitle\b\s*", re.DOTALL)


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


def _split_document(tex: str) -> tuple[str, str]:
    match = DOCUMENT_PATTERN.search(tex)
    if match is None:
        return "", tex.strip()
    return match.group("preamble").strip(), match.group("body").strip()


def _ensure_package(preamble: str, package_name: str) -> str:
    package_pattern = re.compile(rf"\\usepackage(?:\[[^\]]*\])?\{{{re.escape(package_name)}\}}")
    if package_pattern.search(preamble):
        return preamble
    return preamble.rstrip() + "\n" + rf"\usepackage{{{package_name}}}"


def _build_bilingual_preamble(source_preamble: str) -> str:
    preamble = source_preamble.strip()
    if not preamble:
        preamble = r"\documentclass[fontset=windows,UTF8]{article}"
    preamble = _ensure_package(preamble, "ctex")
    preamble = _ensure_package(preamble, "xcolor")
    if r"\definecolor{bilingualzhcolor}" not in preamble:
        preamble = preamble.rstrip() + "\n" + r"\definecolor{bilingualzhcolor}{RGB}{128,128,128}"
    return preamble


def _strip_leading_maketitle(body: str) -> str:
    return LEADING_MAKETITLE_PATTERN.sub("", body, count=1)


def generate_bilingual_tex(english_tex: str, chinese_tex: str) -> str:
    english_preamble, english_body = _split_document(english_tex)
    _chinese_preamble, chinese_body = _split_document(chinese_tex)
    preamble = _build_bilingual_preamble(english_preamble)
    chinese_body = _strip_leading_maketitle(chinese_body)

    return (
        preamble
        + "\n"
        + r"\begin{document}"
        + "\n"
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
