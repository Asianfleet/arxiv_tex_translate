from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def config_factory(workflow_case_dir):
    def _create_config(data: dict) -> Path:
        config_path = workflow_case_dir / "config.json"
        config_path.write_text(json.dumps(data), encoding="utf-8")
        return config_path

    return _create_config


def test_run_translation_workflow_writes_expected_outputs(sample_project_dir, fake_config):
    from src.workflow import run_translation_workflow

    result = run_translation_workflow(
        str(sample_project_dir),
        fake_config,
        translator_outputs={"Hello world.": "你好，世界。"},
        skip_compile=True,
    )

    project_folder = Path(result["project_folder"])

    assert result["success"] is True
    assert Path(result["outputs_dir"]).exists()
    assert (project_folder / "merge.tex").exists()
    assert (project_folder / "merge_translate_zh.tex").exists()
    assert (project_folder / "merge_bilingual.tex").exists()
    assert (project_folder / "debug_log.html").exists()
    assert "你好，世界。" in (project_folder / "merge_translate_zh.tex").read_text(encoding="utf-8")


def test_run_translation_workflow_returns_cached_pdf_from_arxiv_download(monkeypatch, workflow_case_dir, fake_config):
    from src import workflow as workflow_module

    cached_pdf = Path(fake_config.arxiv_cache_dir) / "1234.5678" / "translation" / "translate_zh.pdf"
    cached_pdf.parent.mkdir(parents=True, exist_ok=True)
    cached_pdf.write_bytes(b"%PDF-1.4\n")

    captured = {}

    def fake_arxiv_download(input_value, allow_cache=True):
        captured["input_value"] = input_value
        captured["allow_cache"] = allow_cache
        return str(cached_pdf), "1234.5678"

    monkeypatch.setattr(
        workflow_module,
        "download_arxiv_source",
        lambda input_value, cache_dir, allow_cache=True, proxies=None: fake_arxiv_download(input_value, allow_cache),
    )

    result = workflow_module.run_translation_workflow("1234.5678", fake_config, skip_compile=True)

    assert captured == {"input_value": "1234.5678", "allow_cache": True}
    assert result == {
        "project_folder": str(Path(fake_config.arxiv_cache_dir) / "1234.5678" / "workfolder"),
        "outputs_dir": str(Path(fake_config.arxiv_cache_dir) / "1234.5678" / "outputs"),
        "success": True,
    }


def test_run_translation_workflow_uses_arxiv_id_root_and_syncs_legacy_outputs(
    monkeypatch,
    sample_project_dir,
    fake_config,
):
    from src import workflow as workflow_module

    captured = {}

    def fake_arxiv_download(input_value, allow_cache=True):
        captured["input_value"] = input_value
        captured["allow_cache"] = allow_cache
        return str(sample_project_dir), "2401.00001"

    def fake_compile_latex_project(workfolder, main_name, bilingual_name=None):
        workfolder = Path(workfolder)
        (workfolder / f"{main_name}.pdf").write_bytes(b"%PDF-1.4 zh\n")
        (workfolder / f"{bilingual_name}.pdf").write_bytes(b"%PDF-1.4 bilingual\n")
        return True

    monkeypatch.setattr(
        workflow_module,
        "download_arxiv_source",
        lambda input_value, cache_dir, allow_cache=True, proxies=None: fake_arxiv_download(input_value, allow_cache),
    )
    monkeypatch.setattr(workflow_module, "compile_latex_project", fake_compile_latex_project)

    result = workflow_module.run_translation_workflow(
        "2401.00001",
        fake_config,
        translator_outputs={"Hello world.": "你好，世界。"},
        skip_compile=False,
    )

    arxiv_root = Path(fake_config.arxiv_cache_dir) / "2401.00001"

    assert captured == {"input_value": "2401.00001", "allow_cache": True}
    assert result["project_folder"] == str(arxiv_root / "workfolder")
    assert result["outputs_dir"] == str(arxiv_root / "outputs")
    assert (arxiv_root / "translation" / "translate_zh.pdf").exists()
    assert (arxiv_root / "translation" / "merge_bilingual.pdf").exists()
    assert "local_cache" not in result["project_folder"]


def test_main_cli_uses_new_workflow_entry(monkeypatch, config_factory):
    import main as main_module

    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv": "demo-input",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    monkeypatch.setattr(main_module.sys, "argv", ["main.py", "--config", str(config_path)])

    captured = {}

    def fake_run_translation_workflow(input_value, config, **kwargs):
        captured["input_value"] = input_value
        captured["config"] = config
        return {
            "project_folder": "unused",
            "outputs_dir": "unused",
            "success": True,
        }

    monkeypatch.setattr(main_module, "run_translation_workflow", fake_run_translation_workflow)

    main_module.main()

    assert captured["input_value"] == "demo-input"
    assert captured["config"].arxiv == "demo-input"


def test_run_translation_workflow_reads_api_key_from_api_key_env(
    monkeypatch,
    sample_project_dir,
    fake_config,
):
    from src import workflow as workflow_module

    fake_config.llm.api_key = ""
    fake_config.llm.api_key_env = "WORKFLOW_ONLY_API_KEY"
    monkeypatch.setenv("WORKFLOW_ONLY_API_KEY", "env-secret")

    captured = {}

    def fake_translate_segments(client, model, fragments, more_requirement="", temperature=1.0, top_p=1.0, proxies=None, max_workers=8):
        captured["api_key"] = client.api_key
        captured["model"] = model
        captured["max_workers"] = max_workers
        outputs = []
        for fragment in fragments:
            outputs.append(fragment.replace("Hello world.", "你好，世界。"))
        return outputs

    monkeypatch.setattr(workflow_module, "translate_segments", fake_translate_segments)

    result = workflow_module.run_translation_workflow(
        str(sample_project_dir),
        fake_config,
        skip_compile=True,
    )

    translated_tex = Path(result["project_folder"]) / "merge_translate_zh.tex"

    assert captured == {
        "api_key": "env-secret",
        "model": "qwen-plus",
        "max_workers": fake_config.default_worker_num,
    }
    assert "你好，世界。" in translated_tex.read_text(encoding="utf-8")
