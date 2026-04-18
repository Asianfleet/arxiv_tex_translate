"""
ArXiv 兼容入口。
"""

from __future__ import annotations

from src.project import download_arxiv_source


def _resolve_legacy_option(option_name: str, explicit_value):
    if explicit_value not in (None, ""):
        return explicit_value
    try:
        from src.utils import get_conf

        return get_conf(option_name)
    except Exception:
        return None


def arxiv_download(txt, allow_cache=True, cache_dir=None, proxies=None):
    """
    兼容旧接口，内部委托到新的 project 层实现。
    """
    return download_arxiv_source(
        txt,
        cache_dir=_resolve_legacy_option("ARXIV_CACHE_DIR", cache_dir),
        allow_cache=allow_cache,
        proxies=_resolve_legacy_option("proxies", proxies),
    )
