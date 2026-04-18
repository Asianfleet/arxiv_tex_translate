import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _case_dir(case_name: str):
    case_dir = Path("tests") / "_tmp_latex_compiler" / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield case_dir
    finally:
        if case_dir.exists():
            shutil.rmtree(case_dir)


def test_choose_latex_engine_switches_to_xelatex_for_unicode_packages():
    from src.latex.compiler import choose_latex_engine

    tex_path = Path("tests") / "_tmp_latex_compiler" / "main.tex"

    assert choose_latex_engine(r"\usepackage{fontspec}", tex_path) == "xelatex"
    assert choose_latex_engine(r"\documentclass{article}", tex_path) == "pdflatex"


def test_choose_latex_engine_switches_to_xelatex_for_magic_comments():
    from src.latex.compiler import choose_latex_engine

    tex_path = Path("tests") / "_tmp_latex_compiler" / "main.tex"

    assert choose_latex_engine("% !TeX program = xelatex\n" + r"\documentclass{article}", tex_path) == "xelatex"
    assert choose_latex_engine("% !TEX TS-program = xelatex\n" + r"\documentclass{article}", tex_path) == "xelatex"


def test_run_compile_uses_subprocess_argument_list_and_returns_bool(monkeypatch):
    from src.latex.compiler import run_compile

    recorded = {}

    def fake_run(command, cwd, check, stdout, stderr, timeout):
        recorded["command"] = command
        recorded["cwd"] = cwd
        recorded["check"] = check
        recorded["stdout"] = stdout
        recorded["stderr"] = stderr
        recorded["timeout"] = timeout
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("src.latex.compiler.subprocess.run", fake_run)

    with _case_dir("run_compile_success") as case_dir:
        assert run_compile(["pdflatex", "main.tex"], case_dir) is True
    assert recorded["command"] == ["pdflatex", "main.tex"]
    assert recorded["cwd"] == case_dir
    assert recorded["check"] is False
    assert recorded["stdout"] == subprocess.DEVNULL
    assert recorded["stderr"] == subprocess.DEVNULL


def test_run_compile_returns_false_for_failures(monkeypatch):
    from src.latex.compiler import run_compile

    def raise_missing(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    def raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["pdflatex"], timeout=30)

    def return_failure(*_args, **_kwargs):
        return subprocess.CompletedProcess(["pdflatex"], 1)

    monkeypatch.setattr("src.latex.compiler.subprocess.run", raise_missing)
    with _case_dir("run_compile_missing") as case_dir:
        assert run_compile(["pdflatex", "main.tex"], case_dir) is False

    monkeypatch.setattr("src.latex.compiler.subprocess.run", raise_timeout)
    with _case_dir("run_compile_timeout") as case_dir:
        assert run_compile(["pdflatex", "main.tex"], case_dir) is False

    monkeypatch.setattr("src.latex.compiler.subprocess.run", return_failure)
    with _case_dir("run_compile_failure") as case_dir:
        assert run_compile(["pdflatex", "main.tex"], case_dir) is False


def test_compile_latex_project_runs_main_bibtex_and_bilingual(monkeypatch):
    from src.latex.compiler import compile_latex_project

    with _case_dir("compile_project") as case_dir:
        main_tex = case_dir / "main.tex"
        bilingual_tex = case_dir / "main_bilingual.tex"
        main_tex.write_text(
            r"\documentclass{article}" "\n" r"\usepackage{fontspec}" "\n" r"\begin{document}Hi\end{document}",
            encoding="utf-8",
        )
        bilingual_tex.write_text(
            r"\documentclass{article}" "\n" r"\begin{document}双语\end{document}",
            encoding="utf-8",
        )

        commands: list[list[str]] = []

        def fake_run_compile(command: list[str], cwd: Path) -> bool:
            commands.append(command)
            if command[0] == "xelatex" and command[-1] == "main.tex":
                (cwd / "main.aux").write_text("", encoding="utf-8")
                if sum(1 for item in commands if item[0] == "xelatex" and item[-1] == "main.tex") >= 3:
                    (cwd / "main.pdf").write_text("pdf", encoding="utf-8")
            if command[0] == "pdflatex" and command[-1] == "main_bilingual.tex":
                (cwd / "main_bilingual.pdf").write_text("pdf", encoding="utf-8")
            return True

        monkeypatch.setattr("src.latex.compiler.run_compile", fake_run_compile)

        assert compile_latex_project(case_dir, "main", bilingual_name="main_bilingual") is True
        assert commands[0] == ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        assert ["bibtex", "main"] in commands
        assert commands.count(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]) == 3
        assert ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main_bilingual.tex"] in commands


def test_compile_latex_project_chooses_bilingual_engine_from_bilingual_tex(monkeypatch):
    from src.latex.compiler import compile_latex_project

    with _case_dir("compile_project_bilingual_engine") as case_dir:
        (case_dir / "main.tex").write_text(
            r"\documentclass{article}" "\n" r"\begin{document}Hi\end{document}",
            encoding="utf-8",
        )
        (case_dir / "main_bilingual.tex").write_text(
            r"\documentclass{article}" "\n" r"\usepackage{fontspec}" "\n" r"\begin{document}双语\end{document}",
            encoding="utf-8",
        )

        commands: list[list[str]] = []

        def fake_run_compile(command: list[str], cwd: Path) -> bool:
            commands.append(command)
            if command[0] == "pdflatex" and command[-1] == "main.tex":
                (cwd / "main.pdf").write_text("pdf", encoding="utf-8")
            return True

        monkeypatch.setattr("src.latex.compiler.run_compile", fake_run_compile)

        assert compile_latex_project(case_dir, "main", bilingual_name="main_bilingual") is True
        assert ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"] in commands
        assert ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main_bilingual.tex"] in commands


def test_compile_latex_project_returns_false_when_main_pdf_is_missing(monkeypatch):
    from src.latex.compiler import compile_latex_project

    with _case_dir("compile_project_missing_pdf") as case_dir:
        (case_dir / "main.tex").write_text(
            r"\documentclass{article}" "\n" r"\begin{document}Hi\end{document}",
            encoding="utf-8",
        )

        commands: list[list[str]] = []

        def fake_run_compile(command: list[str], cwd: Path) -> bool:
            commands.append(command)
            return True

        monkeypatch.setattr("src.latex.compiler.run_compile", fake_run_compile)

        assert compile_latex_project(case_dir, "main") is False
        assert commands == [["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]]
