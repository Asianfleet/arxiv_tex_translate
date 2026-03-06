import os
import sys
import glob
import requests
import time
import tarfile
import shutil
from functools import partial
from loguru import logger

from src.utils import get_conf, get_log_folder, gen_time_str, extract_archive
from src.latex_fns.latex_actions import LatexDetailedDecompositionAndTransform, CompileLatex

ARXIV_CACHE_DIR = get_conf("ARXIV_CACHE_DIR")
pj = os.path.join

def switch_prompt(pfg, mode, more_requirement):
    """
    根据处理模式切换GPT提示词。

    Args:
        pfg: LatexPaperFileGroup实例，包含文件内容
        mode: 处理模式，'proofread_en'英文校对或'translate_zh'翻译中文
        more_requirement: 额外的提示词要求

    Returns:
        tuple: (输入文本数组, 系统提示词数组)
    """
    n_split = len(pfg.sp_file_contents)
    if mode == 'proofread_en':
        inputs_array = [r"Below is a section from an academic paper, proofread this section." +
                        r"Do not modify any latex command such as \section, \cite, \begin, \item and equations. " + more_requirement +
                        r"Answer me only with the revised text:" +
                        f"\n\n{frag}" for frag in pfg.sp_file_contents]
        sys_prompt_array = ["You are a professional academic paper writer." for _ in range(n_split)]
    elif mode == 'translate_zh':
        inputs_array = [
            r"Below is a section from an English academic paper, translate it into Chinese. " + more_requirement +
            r"Do not modify any latex command such as \section, \cite, \begin, \item and equations. " +
            r"Answer me only with the translated text:" +
            f"\n\n{frag}" for frag in pfg.sp_file_contents]
        sys_prompt_array = ["You are a professional translator." for _ in range(n_split)]
    else:
        assert False, "未知指令"
    return inputs_array, sys_prompt_array

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

    shutil.copytree(src=project_folder, dst=new_workfolder)
    return new_workfolder

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

def LatexTranslateChineseAndRecompilePDF(txt, llm_kwargs, plugin_kwargs):
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

    try:
        txt, arxiv_id = arxiv_download(txt, allow_cache)
    except tarfile.ReadError as e:
        logger.error("无法自动下载该论文的Latex源码。")
        return False

    if not txt:
        return False

    if txt.endswith('.pdf'):
        logger.warning(f"发现已经存在翻译好的PDF文档: {txt}")
        return True

    if os.path.exists(txt):
        project_folder = txt
    else:
        logger.error(f"找不到本地项目或无法处理: {txt}")
        return False

    file_manifest = [f for f in glob.glob(f'{project_folder}/**/*.tex', recursive=True)]
    if len(file_manifest) == 0:
        logger.error(f"找不到任何.tex文件: {txt}")
        return False

    project_folder = descend_to_extracted_folder_if_exist(project_folder)
    project_folder = move_project(project_folder, arxiv_id)

    if not os.path.exists(project_folder + '/merge_translate_zh.tex'):
        # 同步调用，不再使用 yield
        LatexDetailedDecompositionAndTransform(file_manifest, project_folder, llm_kwargs, plugin_kwargs,
                       mode='translate_zh', switch_prompt=_switch_prompt_)

    success = CompileLatex(main_file_original='merge',
                     main_file_modified='merge_translate_zh', mode='translate_zh',
                     work_folder_original=project_folder, work_folder_modified=project_folder,
                     work_folder=project_folder, bilingual_file='merge_bilingual_zh')

    if success:
        logger.info(f"成功啦！结果已保存在 {project_folder}")
    else:
        logger.error(f"PDF生成失败。请到 {project_folder} 查看错误日志。")

    return success

if __name__ == "__main__":
    """命令行入口点，支持 JSON 配置文件。"""
    import argparse

    parser = argparse.ArgumentParser(description="Arxiv Latex 翻译与编译 (Standalone)")
    parser.add_argument("--config", type=str, default="config.json", help="配置文件路径 (JSON格式)")
    parser.add_argument("--arxiv", type=str, help="arxiv编号或网址，如 1812.10695（覆盖配置文件）")
    parser.add_argument("--model", type=str, help="LLM 模型（覆盖配置文件）")
    parser.add_argument("--advanced_arg", type=str, help="额外的翻译提示词（覆盖配置文件）")
    args = parser.parse_args()

    # 加载配置文件
    from src.utils import load_config, CONFIG
    load_config(args.config)

    # 命令行参数优先于配置文件
    arxiv_id = args.arxiv if args.arxiv else CONFIG.get("arxiv")
    model = args.model if args.model else CONFIG.get("model")
    advanced_arg = args.advanced_arg if args.advanced_arg else CONFIG.get("advanced_arg")

    if not arxiv_id:
        logger.error("必须提供 arxiv 编号或网址。请在 config.json 中设置 'arxiv' 或使用 --arxiv 参数。")
        parser.print_help()
        sys.exit(1)

    llm_kwargs = {
        "api_key": get_conf("API_KEY"),
        "llm_model": model,
        "temperature": CONFIG.get("temperature", 1.0),
        "top_p": CONFIG.get("top_p", 1.0),
    }

    plugin_kwargs = {
        "advanced_arg": advanced_arg
    }

    LatexTranslateChineseAndRecompilePDF(arxiv_id, llm_kwargs, plugin_kwargs)
