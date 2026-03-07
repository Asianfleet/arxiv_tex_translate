"""
主函数模块 - 包含ArXiv LaTeX翻译工具的核心工作流函数。
"""

from .prompts import switch_prompt
from .file_manager import (
    move_project,
    get_run_root,
    ensure_run_dirs,
    archive_compiled_pdfs,
    prepare_local_project,
    setup_run_logger,
    descend_to_extracted_folder_if_exist,
)
from .arxiv_utils import arxiv_download
from .workflow import Latex_to_CN_PDF

__all__ = [
    "switch_prompt",
    "move_project",
    "get_run_root",
    "ensure_run_dirs",
    "archive_compiled_pdfs",
    "prepare_local_project",
    "setup_run_logger",
    "descend_to_extracted_folder_if_exist",
    "arxiv_download",
    "Latex_to_CN_PDF",
]
