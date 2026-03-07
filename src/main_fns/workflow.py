"""
工作流模块 - 包含LaTeX翻译和PDF编译的核心工作流。
"""

import os
import glob
import tarfile
from functools import partial
from loguru import logger

from src.latex_fns.latex_actions import latex_decomp_and_translate, CompileLatex
from .file_manager import (
    ensure_run_dirs,
    setup_run_logger,
    archive_compiled_pdfs,
    prepare_local_project,
    descend_to_extracted_folder_if_exist,
    move_project,
)
from .arxiv_utils import arxiv_download
from .prompts import switch_prompt

pj = os.path.join


def Latex_to_CN_PDF(txt, llm_kwargs, plugin_kwargs):
    """
    将LaTeX论文翻译成中文并重新编译为PDF。

    该函数执行完整的工作流程：
    1. 下载arxiv论文LaTeX源码（如果是arxiv链接）
    2. 精细分解LaTeX文件，识别需要翻译的部分
    3. 使用GPT多线程翻译文本
    4. 编译生成中文PDF

    Args:
        txt: arxiv编号、链接或本地项目路径
        llm_kwargs: LLM模型参数字典
        plugin_kwargs: 插件参数字典，可包含advanced_arg额外提示词

    Returns:
        bool: 翻译和编译是否成功
    """
    logger.info("开始执行 Latex翻译中文并重新编译PDF 流程...")

    more_req = plugin_kwargs.get("advanced_arg", "")
    no_cache = ("--no-cache" in more_req)
    if no_cache: more_req = more_req.replace("--no-cache", "").strip()
    allow_cache = not no_cache
    _switch_prompt_ = partial(switch_prompt, more_requirement=more_req)

    sink_id = None
    run_root = None
    outputs_dir = None
    logs_dir = None
    log_path = None
    project_folder = None
    try:
        try:
            txt, arxiv_id = arxiv_download(txt, allow_cache)
        except tarfile.ReadError:
            logger.error("无法自动下载该论文的Latex源码。")
            return False

        if not txt:
            return False

        if txt.endswith('.pdf'):
            run_root, outputs_dir, logs_dir = ensure_run_dirs(arxiv_id)
            sink_id, log_path = setup_run_logger(logs_dir)
            project_folder = pj(run_root, 'workfolder') if run_root else None
            archive_compiled_pdfs(project_folder, outputs_dir)
            logger.warning(f"发现已经存在翻译好的PDF文档: {txt}")
            if log_path:
                logger.info(f"本次命令行日志已保存到: {log_path}")
            return True

        if not os.path.exists(txt):
            logger.error(f"找不到本地项目或无法处理: {txt}")
            return False

        if arxiv_id is None:
            project_source, run_id = prepare_local_project(txt)
        else:
            project_source, run_id = txt, arxiv_id

        run_root, outputs_dir, logs_dir = ensure_run_dirs(run_id)
        sink_id, log_path = setup_run_logger(logs_dir)

        file_manifest = [f for f in glob.glob(f'{project_source}/**/*.tex', recursive=True)]
        if len(file_manifest) == 0:
            logger.error(f"找不到任何.tex文件: {txt}")
            return False

        project_source = descend_to_extracted_folder_if_exist(project_source)
        project_folder = move_project(project_source, run_id)

        if not os.path.exists(project_folder + '/merge_translate_zh.tex'):
            # 同步调用，不再使用 yield
            latex_decomp_and_translate(file_manifest, project_folder, llm_kwargs, plugin_kwargs,
                           mode='translate_zh', switch_prompt=_switch_prompt_)

        success = CompileLatex(main_file_original='merge',
                         main_file_modified='merge_translate_zh', mode='translate_zh',
                         work_folder_original=project_folder, work_folder_modified=project_folder,
                         work_folder=project_folder, bilingual_file='merge_bilingual')

        archive_compiled_pdfs(project_folder, outputs_dir)

        if success:
            logger.info(f"成功啦！结果已保存在 {project_folder}")
        else:
            logger.error(f"PDF生成失败。请到 {project_folder} 查看错误日志。")

        if log_path:
            logger.info(f"本次命令行日志已保存到: {log_path}")
        return success
    finally:
        if sink_id is not None:
            logger.remove(sink_id)
