from __future__ import annotations

import re
import subprocess
from pathlib import Path


XELATEX_MAGIC_COMMENT_PATTERN = re.compile(
    r"^\s*%\s*!\s*tex\s+(?:program|ts-program)\s*=\s*xelatex\b",
    re.IGNORECASE | re.MULTILINE,
)

XELATEX_MARKERS = (
    "fontspec",
    "xecjk",
    "xetex",
    "unicode-math",
    "xltxtra",
    "xunicode",
)


def choose_latex_engine(tex: str, tex_path: Path) -> str:
    del tex_path
    if XELATEX_MAGIC_COMMENT_PATTERN.search(tex):
        return "xelatex"
    lowered = tex.lower()
    if any(marker in lowered for marker in XELATEX_MARKERS):
        return "xelatex"
    return "pdflatex"


def run_compile(command: list[str], cwd: Path) -> bool:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _latex_command(engine: str, tex_name: str) -> list[str]:
    return [engine, "-interaction=nonstopmode", "-halt-on-error", f"{tex_name}.tex"]


def compile_latex_project(
    work_folder: Path,
    main_name: str,
    bilingual_name: str | None = None,
) -> bool:
    work_dir = Path(work_folder)
    main_tex_path = work_dir / f"{main_name}.tex"
    tex = main_tex_path.read_text(encoding="utf-8", errors="ignore")
    engine = choose_latex_engine(tex, main_tex_path)

    if not run_compile(_latex_command(engine, main_name), work_dir):
        return False

    if (work_dir / f"{main_name}.aux").exists():
        run_compile(["bibtex", main_name], work_dir)
        run_compile(_latex_command(engine, main_name), work_dir)
        run_compile(_latex_command(engine, main_name), work_dir)

    if bilingual_name:
        bilingual_tex_path = work_dir / f"{bilingual_name}.tex"
        if bilingual_tex_path.exists():
            bilingual_tex = bilingual_tex_path.read_text(encoding="utf-8", errors="ignore")
            bilingual_engine = choose_latex_engine(bilingual_tex, bilingual_tex_path)
            run_compile(_latex_command(bilingual_engine, bilingual_name), work_dir)

    return (work_dir / f"{main_name}.pdf").exists()
