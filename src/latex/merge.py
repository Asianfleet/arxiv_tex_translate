from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

INPUT_PATTERN = re.compile(r"\\input\{([^{}]+)\}")
ABSTRACT_BEGIN_PATTERN = re.compile(r"\\begin\{abstract\}", re.DOTALL)
ABSTRACT_MACRO_PATTERN = re.compile(r"\\abstract\s*\{", re.DOTALL)
DOCUMENTCLASS_PATTERN = re.compile(r"(\\documentclass)(\[[^\]]*\])?(\{[^}]+\})")
CTEX_PACKAGE_PATTERN = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{ctex\}")

UNEXPECTED_MAIN_TEX_WORDS = [
    r"\LaTeX",
    "manuscript",
    "Guidelines",
    "font",
    "citations",
    "rejected",
    "blind review",
    "reviewers",
]
EXPECTED_MAIN_TEX_WORDS = [r"\input", r"\ref", r"\cite"]

DEFAULT_ABSTRACT_BLOCK = (
    "\\begin{abstract}\n"
    "The GPT-Academic program cannot find abstract section in this paper.\n"
    "\\end{abstract}"
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _strip_inline_comment(line: str) -> str:
    for index, char in enumerate(line):
        if char != "%":
            continue
        backslash_count = 0
        probe = index - 1
        while probe >= 0 and line[probe] == "\\":
            backslash_count += 1
            probe -= 1
        if backslash_count % 2 == 0:
            return line[:index]
    return line


def remove_comments(tex: str) -> str:
    kept_lines = []
    for line in tex.splitlines():
        if line.lstrip().startswith("%"):
            continue
        kept_lines.append(_strip_inline_comment(line))
    return "\n".join(kept_lines)


def find_main_tex_file(file_manifest: Iterable[str | Path]) -> Path:
    candidates: list[Path] = []
    for tex_file in (Path(item) for item in file_manifest):
        if tex_file.name.startswith("merge"):
            continue
        if r"\documentclass" in _read_text(tex_file):
            candidates.append(tex_file)

    if not candidates:
        raise RuntimeError("无法找到一个主Tex文件（包含documentclass关键字）")
    if len(candidates) == 1:
        return candidates[0]

    def score(tex_file: Path) -> int:
        tex = remove_comments(_read_text(tex_file))
        total = 0
        for word in UNEXPECTED_MAIN_TEX_WORDS:
            if word in tex:
                total -= 1
        for word in EXPECTED_MAIN_TEX_WORDS:
            if word in tex:
                total += 1
        return total

    return max(candidates, key=score)


def find_tex_file_ignore_case(path: str | Path) -> Path | None:
    candidate = Path(path)
    if candidate.is_file():
        return candidate

    candidates = [candidate]
    if candidate.suffix.lower() != ".tex":
        candidates.append(candidate.with_suffix(".tex"))

    for exact in candidates:
        if exact.is_file():
            return exact

    parent = candidate.parent
    if not parent.exists():
        return None

    target_names = {item.name.lower() for item in candidates}
    for child in parent.iterdir():
        if child.name.lower() in target_names:
            return child
    return None


def _resolve_input_path(project_root: Path, current_dir: Path, raw_target: str) -> Path | None:
    for base_dir in (current_dir, project_root):
        resolved = find_tex_file_ignore_case(base_dir / raw_target)
        if resolved is not None:
            return resolved
    return None


def _merge_tex_content(project_root: Path, tex: str, current_dir: Path) -> str:
    merged = remove_comments(tex)
    matches = list(INPUT_PATTERN.finditer(merged))
    for match in reversed(matches):
        raw_target = match.group(1).strip()
        target_file = _resolve_input_path(project_root, current_dir, raw_target)
        if target_file is None:
            raise RuntimeError(f"找不到{raw_target}，Tex源文件缺失！")
        child = _merge_tex_content(project_root, _read_text(target_file), target_file.parent)
        merged = merged[: match.start()] + child + merged[match.end() :]
    return merged


def merge_project_tex(project_root: str | Path, main_tex: str | Path) -> str:
    root = Path(project_root)
    main_path = Path(main_tex)
    if not main_path.is_absolute() and not main_path.exists():
        main_path = root / main_path
    return _merge_tex_content(root, _read_text(main_path), main_path.parent)


def _ensure_documentclass_options(tex: str) -> str:
    match = DOCUMENTCLASS_PATTERN.search(tex)
    if match is None:
        raise RuntimeError("Cannot find documentclass statement!")

    command, options_group, class_group = match.groups()
    options: list[str] = []
    if options_group:
        options = [item.strip() for item in options_group[1:-1].split(",") if item.strip()]
    if "fontset=windows" not in options:
        options.append("fontset=windows")
    if "UTF8" not in options:
        options.append("UTF8")
    replacement = f"{command}[{','.join(options)}]{class_group}"
    return tex[: match.start()] + replacement + tex[match.end() :]


def insert_abstract(tex: str) -> str:
    for anchor in (r"\maketitle", r"\begin{document}"):
        index = tex.find(anchor)
        if index < 0:
            continue
        line_end = tex.find("\n", index)
        if line_end < 0:
            line_end = len(tex)
        insertion = f"\n\n{DEFAULT_ABSTRACT_BLOCK}\n\n"
        return tex[: line_end + 1] + insertion + tex[line_end + 1 :]
    return tex


def ensure_zh_preamble(tex: str) -> str:
    updated = _ensure_documentclass_options(tex)

    documentclass_match = DOCUMENTCLASS_PATTERN.search(updated)
    if documentclass_match is None:
        raise RuntimeError("Cannot find documentclass statement!")

    inserts: list[str] = []
    if CTEX_PACKAGE_PATTERN.search(updated) is None:
        inserts.append(r"\usepackage{ctex}")
    if "{url}" not in updated:
        inserts.append(r"\usepackage{url}")
    if inserts:
        insertion = "\n".join(inserts) + "\n"
        updated = updated[: documentclass_match.end()] + "\n" + insertion + updated[documentclass_match.end() :]

    has_abstract = bool(ABSTRACT_BEGIN_PATTERN.search(updated) or ABSTRACT_MACRO_PATTERN.search(updated))
    if not has_abstract:
        updated = insert_abstract(updated)
    return updated


def merge_tex_files(project_folder: str | Path, main_file: str, mode: str | None) -> str:
    merged = _merge_tex_content(Path(project_folder), main_file, Path(project_folder))
    merged = remove_comments(merged)
    if mode == "translate_zh":
        merged = ensure_zh_preamble(merged)
    return merged
