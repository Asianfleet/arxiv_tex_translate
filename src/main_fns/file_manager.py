"""
文件管理兼容入口。
"""

from __future__ import annotations

import os
import shutil
import time

from src.project import (
    archive_compiled_pdfs as _archive_compiled_pdfs,
    ensure_run_dirs as _ensure_run_dirs,
    gen_time_str,
    get_run_root as _get_run_root,
    prepare_local_project as _prepare_local_project,
    resolve_extracted_project_root,
    setup_run_logger,
)


pj = os.path.join


def _resolve_legacy_cache_dir(cache_dir=None):
    if cache_dir not in (None, ""):
        return cache_dir
    try:
        from src.utils import get_conf

        return get_conf("ARXIV_CACHE_DIR")
    except Exception:
        return None


def _get_log_folder(plugin_name="default"):
    folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", plugin_name)
    os.makedirs(folder, exist_ok=True)
    return folder


def get_run_root(run_id, cache_dir=None):
    return _get_run_root(run_id, cache_dir=_resolve_legacy_cache_dir(cache_dir))


def ensure_run_dirs(run_id, cache_dir=None):
    return _ensure_run_dirs(run_id, cache_dir=_resolve_legacy_cache_dir(cache_dir))


def prepare_local_project(local_path, cache_dir=None):
    return _prepare_local_project(local_path, cache_dir=_resolve_legacy_cache_dir(cache_dir))


def archive_compiled_pdfs(work_folder, outputs_dir):
    return _archive_compiled_pdfs(work_folder, outputs_dir)


def move_project(project_folder, arxiv_id=None, cache_dir=None):
    """
    将项目复制到新的工作目录，兼容旧接口。
    """
    time.sleep(2)
    if arxiv_id is not None:
        new_workfolder = pj(get_run_root(arxiv_id, cache_dir=cache_dir), "workfolder")
    else:
        new_workfolder = f"{_get_log_folder()}/{gen_time_str()}"

    shutil.rmtree(new_workfolder, ignore_errors=True)

    top_level_items = [pj(project_folder, name) for name in os.listdir(project_folder)]
    top_level_tex_files = [item for item in top_level_items if item.endswith(".tex")]
    non_macos_items = [item for item in top_level_items if os.path.basename(item) != "__MACOSX"]
    if not top_level_tex_files and len(non_macos_items) == 1 and os.path.isdir(non_macos_items[0]):
        project_folder = non_macos_items[0]

    top_level_ignored_names = {"workfolder", "outputs", "logs"}

    def _ignore_top_level_only(current_dir, names):
        if os.path.normpath(current_dir) != os.path.normpath(project_folder):
            return []
        return [name for name in names if name in top_level_ignored_names]

    shutil.copytree(
        src=project_folder,
        dst=new_workfolder,
        ignore=_ignore_top_level_only,
    )
    return new_workfolder


def descend_to_extracted_folder_if_exist(project_folder):
    """
    兼容旧接口，返回真正包含 tex 的工程根目录。
    """
    return str(resolve_extracted_project_root(project_folder))
