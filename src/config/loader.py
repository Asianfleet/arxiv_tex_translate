import json
import os
from numbers import Integral, Real
from pathlib import Path

from .models import AppConfig, LLMConfig, RunOptions


class ConfigError(RuntimeError):
    pass


DEFAULT_CONFIG = {
    "arxiv": "",
    "model": "qwen-plus",
    "advanced_arg": "",
    "api_key_env": "",
    "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "arxiv_cache_dir": "arxiv_cache",
    "default_worker_num": 8,
    "proxies": None,
    "temperature": 1.0,
    "top_p": 1.0,
}


def load_app_config(
    config_path: str | os.PathLike[str] = "config.json",
    overrides: RunOptions | None = None,
) -> AppConfig:
    merged = dict(DEFAULT_CONFIG)
    merged.update(_load_file_config(config_path))
    _apply_environment_overrides(merged)
    _apply_run_options(merged, overrides)

    api_key_env = _coerce_str(merged.get("api_key_env", ""), "api_key_env").strip()
    if not api_key_env:
        raise ConfigError("配置文件缺少 `api_key_env`，请指定保存真实 API Key 的环境变量名。")

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise ConfigError(
            f"环境变量 `{api_key_env}` 未设置或为空，无法读取真实 API Key。"
        )

    try:
        llm_config = LLMConfig(
            api_key_env=api_key_env,
            api_key=api_key,
            llm_url=_coerce_str(merged["llm_url"], "llm_url"),
            temperature=_coerce_float(merged["temperature"], "temperature"),
            top_p=_coerce_float(merged["top_p"], "top_p"),
        )

        return AppConfig(
            arxiv=_coerce_str(merged["arxiv"], "arxiv"),
            model=_coerce_str(merged["model"], "model"),
            advanced_arg=_coerce_str(merged["advanced_arg"], "advanced_arg"),
            llm=llm_config,
            arxiv_cache_dir=_coerce_str(merged["arxiv_cache_dir"], "arxiv_cache_dir"),
            default_worker_num=_coerce_int(merged["default_worker_num"], "default_worker_num"),
            proxies=_coerce_optional_str(merged["proxies"], "proxies"),
        )
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"配置解析失败：{exc}") from exc


def _load_file_config(config_path: str | os.PathLike[str]) -> dict:
    path = Path(config_path)
    if not path.exists():
        return {}

    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"配置文件不是有效的 UTF-8 文本：{path}") from exc
    except OSError as exc:
        raise ConfigError(f"读取配置文件失败：{path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是有效的 JSON：{path}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是 JSON 对象：{path}")

    if "api_key" in data:
        raise ConfigError(
            "配置文件中已禁止使用 `api_key` 字段，请改用 `api_key_env` 指向环境变量名。"
        )

    return data


def _apply_environment_overrides(config: dict) -> None:
    env_mappings = {
        "OPENAI_BASE_URL": "llm_url",
        "ARXIV_CACHE_DIR": "arxiv_cache_dir",
    }
    for env_var, config_key in env_mappings.items():
        env_value = os.environ.get(env_var)
        if env_value:
            config[config_key] = env_value


def _apply_run_options(config: dict, overrides: RunOptions | None) -> None:
    if overrides is None:
        return

    if overrides.arxiv not in (None, ""):
        config["arxiv"] = overrides.arxiv
    if overrides.model not in (None, ""):
        config["model"] = overrides.model
    if overrides.advanced_arg not in (None, ""):
        config["advanced_arg"] = overrides.advanced_arg


def _coerce_str(value, field_name: str) -> str:
    if isinstance(value, str):
        return value
    raise ConfigError(f"配置项 `{field_name}` 必须是字符串。")


def _coerce_optional_str(value, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ConfigError(f"配置项 `{field_name}` 必须是字符串或 null。")


def _coerce_float(value, field_name: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"配置项 `{field_name}` 必须是数字。")
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ConfigError(f"配置项 `{field_name}` 必须是数字。") from exc
    raise ConfigError(f"配置项 `{field_name}` 必须是数字。")


def _coerce_int(value, field_name: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"配置项 `{field_name}` 必须是整数。")
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigError(f"配置项 `{field_name}` 必须是整数。") from exc
    raise ConfigError(f"配置项 `{field_name}` 必须是整数。")
