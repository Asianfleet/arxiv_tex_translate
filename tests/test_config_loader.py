import json
import importlib
import sys
from pathlib import Path

import pytest

from src.config.loader import ConfigError, load_app_config
from src.config.models import RunOptions
from src.utils import get_conf, load_config


@pytest.fixture
def config_factory(request):
    base_dir = Path(__file__).with_name("tmp_config_loader_cases")
    paths: list[Path] = []

    def write_config(data: dict) -> Path:
        base_dir.mkdir(exist_ok=True)
        config_path = base_dir / f"{request.node.name}.json"
        config_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        paths.append(config_path)
        return config_path

    yield write_config

    for path in paths:
        path.unlink(missing_ok=True)
    if base_dir.exists():
        base_dir.rmdir()


def test_load_app_config_reads_api_key_from_custom_env(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "model": "test-model",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    config = load_app_config(config_path)

    assert config.llm.api_key == "secret-token"
    assert config.llm.api_key_env == "MY_TRANSLATOR_KEY"
    assert config.model == "test-model"


def test_load_app_config_rejects_legacy_api_key_field(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key": "legacy-secret",
            "api_key_env": "MY_TRANSLATOR_KEY",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    with pytest.raises(ConfigError, match="api_key"):
        load_app_config(config_path)


def test_load_app_config_requires_configured_env_var(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MISSING_TRANSLATOR_KEY",
        },
    )
    monkeypatch.delenv("MISSING_TRANSLATOR_KEY", raising=False)

    with pytest.raises(ConfigError, match="MISSING_TRANSLATOR_KEY"):
        load_app_config(config_path)


def test_load_app_config_applies_run_options_overrides(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "model": "config-model",
            "advanced_arg": "from-config",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    config = load_app_config(
        config_path,
        overrides=RunOptions(
            arxiv="2401.00001",
            model="override-model",
            advanced_arg="from-cli",
        ),
    )

    assert config.arxiv == "2401.00001"
    assert config.model == "override-model"
    assert config.advanced_arg == "from-cli"


def test_empty_string_override_does_not_replace_config_value(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv": "2401.11111",
            "model": "config-model",
            "advanced_arg": "from-config",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    config = load_app_config(
        config_path,
        overrides=RunOptions(arxiv="", model="", advanced_arg=""),
    )

    assert config.arxiv == "2401.11111"
    assert config.model == "config-model"
    assert config.advanced_arg == "from-config"


def test_utils_load_config_exposes_legacy_api_key_accessor(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    load_config(str(config_path))

    assert get_conf("API_KEY") == "secret-token"


def test_old_module_reads_updated_config_after_import(config_factory, monkeypatch):
    file_manager = importlib.import_module("src.main_fns.file_manager")
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv_cache_dir": "custom_cache_dir",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    load_config(str(config_path))

    assert Path(file_manager.get_run_root("demo-paper")).parts[-2:] == (
        "custom_cache_dir",
        "demo-paper",
    )


def test_load_app_config_wraps_invalid_json_as_config_error(config_factory, monkeypatch):
    config_path = config_factory({"api_key_env": "MY_TRANSLATOR_KEY"})
    config_path.write_text("{bad json", encoding="utf-8")
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    with pytest.raises(ConfigError, match="JSON"):
        load_app_config(config_path)


def test_load_app_config_wraps_invalid_encoding_as_config_error(config_factory):
    config_path = config_factory({})
    config_path.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(ConfigError, match="UTF-8"):
        load_app_config(config_path)


def test_load_app_config_wraps_invalid_number_as_config_error(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "temperature": "bad-number",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    with pytest.raises(ConfigError, match="temperature"):
        load_app_config(config_path)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("default_worker_num", 1.5),
        ("default_worker_num", True),
        ("temperature", True),
    ],
)
def test_load_app_config_rejects_invalid_numeric_boundary_types(
    config_factory,
    monkeypatch,
    field_name,
    field_value,
):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            field_name: field_value,
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    with pytest.raises(ConfigError, match=field_name):
        load_app_config(config_path)


def test_main_exits_with_status_one_on_config_error(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key": "legacy-secret",
            "api_key_env": "MY_TRANSLATOR_KEY",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])
    main_module = importlib.import_module("main")

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("api_key_env", None),
        ("model", False),
    ],
)
def test_load_app_config_rejects_invalid_string_fields(
    config_factory,
    monkeypatch,
    field_name,
    field_value,
):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            field_name: field_value,
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")

    with pytest.raises(ConfigError, match=field_name):
        load_app_config(config_path)
