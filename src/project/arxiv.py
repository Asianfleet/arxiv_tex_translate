"""
arXiv 输入归一化与下载工具。
"""

from __future__ import annotations

import re
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from loguru import logger

from src.project.workspace import resolve_cache_dir


_VERSION_SUFFIX = re.compile(r"v\d+$")
_MODERN_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_LEGACY_ID = re.compile(r"^[a-z-]+(?:\.[a-z-]+)*/\d{7}(?:v\d+)?$", re.IGNORECASE)


def _strip_version(arxiv_id):
    return _VERSION_SUFFIX.sub("", arxiv_id)


def _clean_pdf_id(arxiv_id):
    if arxiv_id.endswith(".pdf"):
        arxiv_id = arxiv_id[:-4]
    return _strip_version(arxiv_id)


def _is_bare_arxiv_id(value):
    return bool(_MODERN_ID.match(value) or _LEGACY_ID.match(value))


def normalize_arxiv_input(value):
    """
    将 arXiv ID、abs URL 或 pdf URL 归一化为 abs URL 与 arXiv ID。

    非 arXiv 输入会原样返回，并将 arxiv_id 置为 None，便于旧调用方继续
    把本地路径传入同一入口。
    """
    text = str(value).strip()
    if _is_bare_arxiv_id(text):
        arxiv_id = _strip_version(text)
        return f"https://arxiv.org/abs/{arxiv_id}", arxiv_id

    parsed = urlparse(text)
    if parsed.netloc != "arxiv.org":
        return text, None

    if parsed.path.startswith("/abs/"):
        arxiv_id = _strip_version(parsed.path.removeprefix("/abs/"))
        if not _is_bare_arxiv_id(arxiv_id):
            return text, None
        return f"https://arxiv.org/abs/{arxiv_id}", arxiv_id

    if parsed.path.startswith("/pdf/"):
        arxiv_id = _clean_pdf_id(parsed.path.removeprefix("/pdf/"))
        if not _is_bare_arxiv_id(arxiv_id):
            return text, None
        return f"https://arxiv.org/abs/{arxiv_id}", arxiv_id

    return text, None


def extract_archive(file_path, dest_dir) -> None:
    """
    解压 tar/zip 压缩包。
    """
    archive_path = Path(file_path)
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r") as tar:
            tar.extractall(path=destination)
        return

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(destination)
        return

    raise ValueError(f"Unknown archive format: {archive_path}")


def resolve_extracted_project_root(project_folder):
    """
    尝试下降到真正包含 tex 文件的根目录。
    """
    current = Path(project_folder)
    while current.is_dir():
        if any(current.glob("*.tex")):
            return current

        child_dirs = [child for child in current.iterdir() if child.is_dir()]
        if len(child_dirs) != 1:
            return current

        next_dir = child_dirs[0]
        if not next_dir.name.endswith(".extract") and not any(next_dir.rglob("*.tex")):
            return current
        current = next_dir

    return Path(project_folder)


def _download_source_archive(abs_url: str, archive_path: Path, proxies):
    candidate_urls = [
        abs_url.replace("/abs/", "/src/"),
        abs_url.replace("/abs/", "/e-print/"),
    ]
    for candidate_url in candidate_urls:
        response = requests.get(candidate_url, proxies=proxies, timeout=120)
        if response.status_code != 200:
            continue
        archive_path.write_bytes(response.content)
        return True
    return False


def download_arxiv_source(
    value,
    *,
    cache_dir: str | Path | None = None,
    allow_cache: bool = True,
    proxies=None,
):
    """
    下载 arXiv 源码并解压到缓存目录。

    返回 `(解压目录路径或缓存 PDF 路径, arxiv_id)`。
    """
    normalized_value, arxiv_id = normalize_arxiv_input(value)
    if arxiv_id is None:
        return value, None

    logger.info(f"检测到 arXiv 文档链接: {normalized_value}")
    if not normalized_value.startswith("https://arxiv.org/abs/"):
        logger.error(f"解析 arXiv 网址失败: {normalized_value}")
        return None, None

    cache_root = Path(resolve_cache_dir(cache_dir))
    translation_dir = cache_root / arxiv_id / "translation"
    cached_pdf = translation_dir / "translate_zh.pdf"
    if allow_cache and cached_pdf.exists():
        logger.info(f"检测到缓存翻译: {cached_pdf}")
        return cached_pdf, arxiv_id

    extract_dir = cache_root / arxiv_id / "extract"
    if allow_cache and extract_dir.exists() and any(extract_dir.iterdir()):
        logger.info(f"检测到缓存源码: {extract_dir}")
        return extract_dir, arxiv_id

    eprint_dir = cache_root / arxiv_id / "e-print"
    archive_path = eprint_dir / f"{arxiv_id}.tar"
    eprint_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.exists() and allow_cache:
        logger.info(f"调用缓存 {arxiv_id}")
        success = True
    else:
        logger.info(f"开始下载 {arxiv_id}")
        success = _download_source_archive(normalized_value, archive_path, proxies=proxies)
        logger.info(f"下载完成 {arxiv_id}")

    if not success:
        logger.error(f"下载失败 {arxiv_id}")
        raise tarfile.ReadError(f"论文下载失败 {arxiv_id}")

    try:
        extract_archive(file_path=archive_path, dest_dir=extract_dir)
    except tarfile.ReadError:
        archive_path.unlink(missing_ok=True)
        raise tarfile.ReadError("论文下载失败")

    return extract_dir, arxiv_id
