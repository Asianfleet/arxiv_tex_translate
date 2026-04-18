"""
项目工作区准备工具。
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import time

from loguru import logger


pj = os.path.join
_SKIPPED_PROJECT_DIRS = {"outputs", "logs", "workfolder"}


def gen_time_str() -> str:
    """
    生成当前时间字符串，兼容旧目录命名格式。
    """
    return time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())


def resolve_cache_dir(cache_dir: str | os.PathLike[str] | None = None) -> str:
    """
    解析缓存根目录。
    """
    if cache_dir in (None, ""):
        cache_dir = os.environ.get("ARXIV_CACHE_DIR", "arxiv_cache")
    return os.path.abspath(os.fspath(cache_dir))


def _validate_run_id(run_id, cache_dir: str | os.PathLike[str] | None = None):
    run_id_text = os.fspath(run_id)
    normalized_run_id = run_id_text.replace("\\", "/")
    if not normalized_run_id:
        return None
    if normalized_run_id.startswith("/") or re.match(r"^[A-Za-z]:/", normalized_run_id):
        raise ValueError(f"非法 run_id: {run_id_text}")
    parts = [part for part in normalized_run_id.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError(f"非法 run_id: {run_id_text}")
    cache_root = resolve_cache_dir(cache_dir)
    run_root = os.path.abspath(os.path.join(cache_root, *parts))
    if os.path.commonpath([cache_root, run_root]) != cache_root:
        raise ValueError(f"非法 run_id: {run_id_text}")
    return run_root


def get_run_root(run_id, cache_dir: str | os.PathLike[str] | None = None):
    """
    根据运行 ID 获取本次任务根目录。
    """
    if not run_id:
        return None
    return _validate_run_id(run_id, cache_dir=cache_dir)


def ensure_run_dirs(run_id, cache_dir: str | os.PathLike[str] | None = None):
    """
    为本次任务创建 run_root、outputs 和 logs 目录。
    """
    run_root = get_run_root(run_id, cache_dir=cache_dir)
    if not run_root:
        return None, None, None
    outputs_dir = pj(run_root, "outputs")
    logs_dir = pj(run_root, "logs")
    os.makedirs(outputs_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    return run_root, outputs_dir, logs_dir


def _copy_project_dir(local_path, run_root):
    for item in glob.glob(pj(str(local_path), "*")):
        name = os.path.basename(item)
        if name in _SKIPPED_PROJECT_DIRS:
            continue
        target = pj(run_root, name)
        if os.path.isdir(item):
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def prepare_local_project(local_path, cache_dir: str | os.PathLike[str] | None = None):
    """
    为本地输入创建缓存目录，并复制源文件或源目录。
    """
    local_path = os.fspath(local_path)
    timestamp = gen_time_str()
    run_id = pj("local_cache", timestamp)
    run_root, _, _ = ensure_run_dirs(run_id, cache_dir=cache_dir)

    if os.path.isfile(local_path):
        shutil.copy2(local_path, pj(run_root, os.path.basename(local_path)))
        return run_root, run_id

    if os.path.isdir(local_path):
        _copy_project_dir(local_path, run_root)
        return run_root, run_id

    raise FileNotFoundError(f"找不到本地项目或无法处理: {local_path}")


def setup_run_logger(logs_dir):
    """
    为单次任务追加文件日志。
    """
    if not logs_dir:
        return None, None
    log_path = pj(logs_dir, f"run-{gen_time_str()}.log")
    sink_id = logger.add(log_path, encoding="utf-8")
    return sink_id, log_path
