from __future__ import annotations

import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fakes import FakeConfig


@contextmanager
def _case_dir(case_name: str):
    case_dir = Path("tests") / "_tmp_workflow_smoke" / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield case_dir
    finally:
        if case_dir.exists():
            shutil.rmtree(case_dir)


@pytest.fixture
def workflow_case_dir() -> Path:
    with _case_dir("case") as case_dir:
        yield case_dir


@pytest.fixture
def sample_project_dir(workflow_case_dir: Path) -> Path:
    source = Path("tests/fixtures/sample_project")
    target = workflow_case_dir / "sample_project"
    shutil.copytree(source, target)
    return target


@pytest.fixture
def fake_config(workflow_case_dir: Path) -> FakeConfig:
    return FakeConfig(arxiv_cache_dir=str(workflow_case_dir / "arxiv_cache"))
