"""
输出归档工具。
"""

import os
import shutil


pj = os.path.join


def archive_compiled_pdfs(work_folder, outputs_dir):
    """
    将编译产出的核心 PDF 归档到 outputs 目录。
    """
    if not work_folder or not outputs_dir:
        return
    os.makedirs(outputs_dir, exist_ok=True)
    for pdf_name in ["merge.pdf", "merge_translate_zh.pdf", "merge_bilingual.pdf"]:
        src = pj(work_folder, pdf_name)
        if os.path.exists(src):
            shutil.copy2(src, pj(outputs_dir, pdf_name))
