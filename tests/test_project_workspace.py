import io
import shutil
import tarfile
import uuid
from pathlib import Path

import pytest


def _make_case_dir(case_name):
    case_dir = Path("tests") / "_tmp_project_workspace" / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def test_normalize_arxiv_input_converts_bare_id_to_abs_url():
    from src.project.arxiv import normalize_arxiv_input

    normalized_url, arxiv_id = normalize_arxiv_input("1812.10695")

    assert normalized_url == "https://arxiv.org/abs/1812.10695"
    assert arxiv_id == "1812.10695"


@pytest.mark.parametrize(
    ("raw_value", "expected_id"),
    [
        ("cond-mat.soft/0301001", "cond-mat.soft/0301001"),
        ("physics.optics/0601001v2", "physics.optics/0601001"),
    ],
)
def test_normalize_arxiv_input_supports_legacy_bare_ids(raw_value, expected_id):
    from src.project.arxiv import normalize_arxiv_input

    normalized_url, arxiv_id = normalize_arxiv_input(raw_value)

    assert normalized_url == f"https://arxiv.org/abs/{expected_id}"
    assert arxiv_id == expected_id


def test_normalize_arxiv_input_passthroughs_non_arxiv_value():
    from src.project.arxiv import normalize_arxiv_input

    normalized_url, arxiv_id = normalize_arxiv_input("C:/papers/demo/main.tex")

    assert normalized_url == "C:/papers/demo/main.tex"
    assert arxiv_id is None


@pytest.mark.parametrize(
    ("raw_value", "expected_id"),
    [
        ("https://arxiv.org/abs/1812.10695v3", "1812.10695"),
        ("https://arxiv.org/pdf/physics.optics/0601001v2.pdf", "physics.optics/0601001"),
    ],
)
def test_normalize_arxiv_input_normalizes_versions_in_urls(raw_value, expected_id):
    from src.project.arxiv import normalize_arxiv_input

    normalized_url, arxiv_id = normalize_arxiv_input(raw_value)

    assert normalized_url == f"https://arxiv.org/abs/{expected_id}"
    assert arxiv_id == expected_id


@pytest.mark.parametrize(
    "raw_value",
    [
        "https://arxiv.org/abs/../../etc/passwd",
        "https://arxiv.org/pdf/C:/Windows/system32/drivers/etc/hosts.pdf",
        "https://arxiv.org/pdf/../secrets.txt",
    ],
)
def test_normalize_arxiv_input_rejects_malicious_arxiv_urls(raw_value):
    from src.project.arxiv import normalize_arxiv_input

    normalized_url, arxiv_id = normalize_arxiv_input(raw_value)

    assert normalized_url == raw_value
    assert arxiv_id is None


def test_prepare_local_project_skips_run_directories(monkeypatch):
    from src.project import workspace

    case_dir = _make_case_dir("prepare_local_project")
    source = case_dir / "source"
    source.mkdir()
    (source / "main.tex").write_text("content", encoding="utf-8")
    for skipped_name in ("outputs", "logs", "workfolder"):
        skipped_dir = source / skipped_name
        skipped_dir.mkdir()
        (skipped_dir / "stale.txt").write_text("skip", encoding="utf-8")

    monkeypatch.setattr(workspace, "gen_time_str", lambda: "2026-04-18-12-00-00")

    project_dir, run_id = workspace.prepare_local_project(source, cache_dir=case_dir / "cache")

    assert run_id == str(Path("local_cache") / "2026-04-18-12-00-00")
    assert (Path(project_dir) / "main.tex").exists()
    assert not (Path(project_dir) / "outputs" / "stale.txt").exists()
    assert not (Path(project_dir) / "logs" / "stale.txt").exists()
    assert not (Path(project_dir) / "workfolder").exists()
    shutil.rmtree(case_dir)


def test_prepare_local_project_keeps_nested_named_directories(monkeypatch):
    from src.project import workspace

    case_dir = _make_case_dir("prepare_local_project_nested")
    source = case_dir / "source"
    nested_outputs = source / "chapter1" / "outputs"
    nested_logs = source / "chapter1" / "logs"
    nested_workfolder = source / "chapter1" / "workfolder"
    nested_outputs.mkdir(parents=True)
    nested_logs.mkdir(parents=True)
    nested_workfolder.mkdir(parents=True)
    (source / "main.tex").write_text("content", encoding="utf-8")
    (nested_outputs / "keep.txt").write_text("keep", encoding="utf-8")
    (nested_logs / "keep.txt").write_text("keep", encoding="utf-8")
    (nested_workfolder / "keep.txt").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(workspace, "gen_time_str", lambda: "2026-04-18-12-00-01")

    project_dir, _ = workspace.prepare_local_project(source, cache_dir=case_dir / "cache")

    assert (Path(project_dir) / "chapter1" / "outputs" / "keep.txt").exists()
    assert (Path(project_dir) / "chapter1" / "logs" / "keep.txt").exists()
    assert (Path(project_dir) / "chapter1" / "workfolder" / "keep.txt").exists()
    shutil.rmtree(case_dir)


def test_copy_project_to_workfolder_skips_only_top_level_runtime_dirs():
    from src.project.workspace import copy_project_to_workfolder

    case_dir = _make_case_dir("copy_project_to_workfolder")
    source = case_dir / "source"
    source.mkdir()
    (source / "main.tex").write_text("content", encoding="utf-8")
    for skipped_name in ("outputs", "logs", "workfolder"):
        skipped_dir = source / skipped_name
        skipped_dir.mkdir()
        (skipped_dir / "top.txt").write_text("skip", encoding="utf-8")
    for nested_name in ("outputs", "logs", "workfolder"):
        nested_dir = source / "chapter1" / nested_name
        nested_dir.mkdir(parents=True)
        (nested_dir / "keep.txt").write_text("keep", encoding="utf-8")

    destination = case_dir / "destination"
    copy_project_to_workfolder(source, destination)

    assert not (destination / "outputs" / "top.txt").exists()
    assert not (destination / "logs" / "top.txt").exists()
    assert not (destination / "workfolder" / "top.txt").exists()
    assert (destination / "chapter1" / "outputs" / "keep.txt").exists()
    assert (destination / "chapter1" / "logs" / "keep.txt").exists()
    assert (destination / "chapter1" / "workfolder" / "keep.txt").exists()
    shutil.rmtree(case_dir)


def test_ensure_run_dirs_creates_standard_directories(monkeypatch):
    from src.project.workspace import ensure_run_dirs

    case_dir = _make_case_dir("ensure_run_dirs")
    run_root, outputs_dir, logs_dir = ensure_run_dirs("local_cache/demo", cache_dir=case_dir / "cache")

    assert Path(run_root).is_dir()
    assert Path(outputs_dir).is_dir()
    assert Path(logs_dir).is_dir()
    assert Path(outputs_dir) == Path(run_root) / "outputs"
    assert Path(logs_dir) == Path(run_root) / "logs"
    shutil.rmtree(case_dir)


@pytest.mark.parametrize(
    "run_id",
    [
        "../escape",
        "local_cache/../escape",
        "/absolute/path",
        "C:/absolute/path",
    ],
)
def test_ensure_run_dirs_rejects_invalid_run_id(monkeypatch, run_id):
    from src.project.workspace import ensure_run_dirs

    case_dir = _make_case_dir("ensure_run_dirs_invalid")
    with pytest.raises(ValueError, match="run_id"):
        ensure_run_dirs(run_id, cache_dir=case_dir / "cache")

    shutil.rmtree(case_dir)


def test_extract_archive_extracts_tar_with_nested_directory_files():
    from src.project.arxiv import extract_archive

    case_dir = Path("tests") / "_tmp_project_workspace" / f"extract_archive_nested_files_{uuid.uuid4().hex}"
    case_dir.mkdir(parents=True, exist_ok=False)
    archive_path = case_dir / "sample.tar"
    destination = case_dir / "extract"
    file_content = b"hello tar"

    with tarfile.open(archive_path, "w") as tar:
        directory = tarfile.TarInfo("figures")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o775
        tar.addfile(directory)

        nested_file = tarfile.TarInfo("figures/questions.png")
        nested_file.size = len(file_content)
        nested_file.mode = 0o664
        tar.addfile(nested_file, io.BytesIO(file_content))

    extract_archive(archive_path, destination)

    extracted_file = destination / "figures" / "questions.png"
    assert extracted_file.read_bytes() == file_content
    shutil.rmtree(case_dir)
