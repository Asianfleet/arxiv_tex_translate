from __future__ import annotations

import re
import shutil
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

BIBDATA_PATTERN = re.compile(r"\\bibdata\{([^}]*)\}")


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


def _reuse_existing_bbl(work_dir: Path, main_name: str) -> bool:
    aux_path = work_dir / f"{main_name}.aux"
    if not aux_path.exists():
        return False

    aux_text = aux_path.read_text(encoding="utf-8", errors="ignore")
    match = BIBDATA_PATTERN.search(aux_text)
    if match is None:
        return False

    bib_names = [name.strip() for name in match.group(1).split(",") if name.strip()]
    if not bib_names:
        return False

    if any((work_dir / f"{name}.bib").exists() for name in bib_names):
        return False

    target_bbl = work_dir / f"{main_name}.bbl"
    for name in bib_names:
        source_bbl = work_dir / f"{name}.bbl"
        if source_bbl.exists():
            shutil.copy2(source_bbl, target_bbl)
            return True
    return False


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
        if not _reuse_existing_bbl(work_dir, main_name):
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
