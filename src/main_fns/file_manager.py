"""
文件管理模块 - 处理项目目录、缓存、日志等文件操作。
"""

import os
import glob
import time
import shutil
from loguru import logger

from src.utils import get_conf, get_log_folder, gen_time_str

pj = os.path.join
ARXIV_CACHE_DIR = get_conf("ARXIV_CACHE_DIR")


def move_project(project_folder, arxiv_id=None):
    """
    将项目移动到新的工作文件夹。

    Args:
        project_folder: 原始项目文件夹路径
        arxiv_id: 可选的arxiv论文ID，用于确定目标文件夹

    Returns:
        新的工作文件夹路径
    """
    time.sleep(2)  # avoid time string conflict
    if arxiv_id is not None:
        new_workfolder = pj(ARXIV_CACHE_DIR, arxiv_id, 'workfolder')
    else:
        new_workfolder = f'{get_log_folder()}/{gen_time_str()}'
    try:
        shutil.rmtree(new_workfolder)
    except:
        pass

    items = glob.glob(pj(project_folder, '*'))
    items = [item for item in items if os.path.basename(item) != '__MACOSX']
    if len(glob.glob(pj(project_folder, '*.tex'))) == 0 and len(items) == 1:
        if os.path.isdir(items[0]): project_folder = items[0]

    shutil.copytree(
        src=project_folder,
        dst=new_workfolder,
        ignore=shutil.ignore_patterns('workfolder', 'outputs', 'logs')
    )
    return new_workfolder


def get_run_root(run_id):
    """
    根据运行ID获取本次任务的根目录。

    Args:
        run_id: arxiv编号或 local_cache 下的相对路径

    Returns:
        str | None: 运行根目录
    """
    if not run_id:
        return None
    return pj(ARXIV_CACHE_DIR, run_id)


def ensure_run_dirs(run_id):
    """
    为本次任务创建标准输出目录。

    Args:
        run_id: arxiv编号或 local_cache 下的相对路径

    Returns:
        tuple: (run_root, outputs_dir, logs_dir)
    """
    run_root = get_run_root(run_id)
    if not run_root:
        return None, None, None
    outputs_dir = pj(run_root, 'outputs')
    logs_dir = pj(run_root, 'logs')
    os.makedirs(outputs_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    return run_root, outputs_dir, logs_dir


def archive_compiled_pdfs(work_folder, outputs_dir):
    """
    将编译产出的核心PDF归档到 outputs 目录。

    Args:
        work_folder: workfolder 目录
        outputs_dir: outputs 目录
    """
    if not work_folder or not outputs_dir:
        return
    for pdf_name in ['merge.pdf', 'merge_translate_zh.pdf', 'merge_bilingual.pdf']:
        src = pj(work_folder, pdf_name)
        if os.path.exists(src):
            shutil.copy2(src, pj(outputs_dir, pdf_name))


def prepare_local_project(local_path):
    """
    为本地输入创建缓存目录，并复制源文件或源目录。

    Args:
        local_path: 本地tex文件路径或目录路径

    Returns:
        tuple: (缓存后的项目目录, run_id)
    """
    timestamp = gen_time_str()
    run_id = os.path.join('local_cache', timestamp)
    run_root, _, _ = ensure_run_dirs(run_id)

    if os.path.isfile(local_path):
        shutil.copy2(local_path, pj(run_root, os.path.basename(local_path)))
        return run_root, run_id

    if os.path.isdir(local_path):
        for item in glob.glob(pj(local_path, '*')):
            name = os.path.basename(item)
            if name in {'workfolder', 'outputs', 'logs'}:
                continue
            target = pj(run_root, name)
            if os.path.isdir(item):
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        return run_root, run_id

    raise FileNotFoundError(f"找不到本地项目或无法处理: {local_path}")


def setup_run_logger(logs_dir):
    """
    为单次任务追加文件日志。

    Args:
        logs_dir: 任务日志目录

    Returns:
        tuple: (sink_id, log_path)
    """
    if not logs_dir:
        return None, None
    log_path = pj(logs_dir, f'run-{gen_time_str()}.log')
    sink_id = logger.add(log_path, encoding='utf-8')
    return sink_id, log_path


def descend_to_extracted_folder_if_exist(project_folder):
    """
    如果存在已解压的文件夹，则进入该文件夹，否则返回原始文件夹。

    参数:
    - project_folder: 指定文件夹路径的字符串。

    返回:
    - 指向已解压文件夹的路径字符串，如果没有解压文件夹则返回原始文件夹路径。
    """
    maybe_dir = [f for f in glob.glob(f'{project_folder}/*') if os.path.isdir(f)]
    if len(maybe_dir) == 0: return project_folder
    if maybe_dir[0].endswith('.extract'): return maybe_dir[0]
    return project_folder
