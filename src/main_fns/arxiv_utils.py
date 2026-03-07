"""
ArXiv工具模块 - 处理ArXiv论文的下载和解析。
"""

import os
import tarfile
from loguru import logger

from src.utils import get_conf, extract_archive

pj = os.path.join
ARXIV_CACHE_DIR = get_conf("ARXIV_CACHE_DIR")


def arxiv_download(txt, allow_cache=True):
    """
    下载arxiv论文的LaTeX源码。

    支持输入arxiv ID、arxiv链接或PDF链接。会自动尝试下载源码tar包，
    并解压到缓存目录。

    Args:
        txt: arxiv编号、链接或路径
        allow_cache: 是否允许使用缓存

    Returns:
        tuple: (解压目录路径或PDF路径, arxiv_id)
    """
    import requests

    def is_float(s):
        """检查字符串是否可以转换为浮点数。"""
        try:
            float(s)
            return True
        except ValueError:
            return False

    if txt.startswith('https://arxiv.org/pdf/'):
        arxiv_id = txt.split('/')[-1]
        txt = arxiv_id.split('v')[0]

    if ('.' in txt) and ('/' not in txt) and is_float(txt):
        txt = 'https://arxiv.org/abs/' + txt.strip()
    if ('.' in txt) and ('/' not in txt) and is_float(txt[:10]):
        txt = 'https://arxiv.org/abs/' + txt[:10]

    if not txt.startswith('https://arxiv.org'):
        return txt, None

    logger.info(f"检测到arxiv文档连接: {txt}")

    url_ = txt
    if not txt.startswith('https://arxiv.org/abs/'):
        logger.error(f"解析arxiv网址失败: {url_}")
        return None, None

    arxiv_id = url_.split('/abs/')[-1]
    if 'v' in arxiv_id: arxiv_id = arxiv_id[:10]

    translation_dir = pj(ARXIV_CACHE_DIR, arxiv_id, 'translation')
    target_file = pj(translation_dir, 'translate_zh.pdf')
    if os.path.exists(target_file) and allow_cache:
        logger.info(f"检测到缓存翻译: {target_file}")
        return target_file, arxiv_id

    extract_dst = pj(ARXIV_CACHE_DIR, arxiv_id, 'extract')
    translation_dir = pj(ARXIV_CACHE_DIR, arxiv_id, 'e-print')
    dst = pj(translation_dir, arxiv_id + '.tar')
    os.makedirs(translation_dir, exist_ok=True)

    def fix_url_and_download():
        """尝试不同的URL格式下载arxiv源码。"""
        for url_tar in [url_.replace('/abs/', '/src/'), url_.replace('/abs/', '/e-print/')]:
            proxies = get_conf('proxies')
            r = requests.get(url_tar, proxies=proxies)
            if r.status_code == 200:
                with open(dst, 'wb+') as f:
                    f.write(r.content)
                return True
        return False

    if os.path.exists(dst) and allow_cache:
        logger.info(f"调用缓存 {arxiv_id}")
        success = True
    else:
        logger.info(f"开始下载 {arxiv_id}")
        success = fix_url_and_download()
        logger.info(f"下载完成 {arxiv_id}")

    if not success:
        logger.error(f"下载失败 {arxiv_id}")
        raise tarfile.ReadError(f"论文下载失败 {arxiv_id}")

    try:
        extract_archive(file_path=dst, dest_dir=extract_dst)
    except tarfile.ReadError:
        os.remove(dst)
        raise tarfile.ReadError(f"论文下载失败")
    return extract_dst, arxiv_id
