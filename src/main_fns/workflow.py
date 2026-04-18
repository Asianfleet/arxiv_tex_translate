"""
工作流模块 - 保留旧入口，并委托到新的工作流实现。
"""

from dataclasses import dataclass, field

from loguru import logger

from src.workflow import run_translation_workflow


@dataclass(slots=True)
class LegacyLLMConfig:
    api_key_env: str = ""
    api_key: str = ""
    llm_url: str = ""
    temperature: float = 1.0
    top_p: float = 1.0


@dataclass(slots=True)
class LegacyWorkflowConfig:
    arxiv_cache_dir: str = "arxiv_cache"
    model: str = ""
    advanced_arg: str = ""
    default_worker_num: int = 8
    proxies: dict | str | None = None
    llm: LegacyLLMConfig = field(default_factory=LegacyLLMConfig)


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
    logger.info("开始执行 Latex 翻译中文并重新编译 PDF 流程...")

    config = LegacyWorkflowConfig(
        arxiv_cache_dir=plugin_kwargs.get("arxiv_cache_dir", "arxiv_cache"),
        model=llm_kwargs.get("llm_model", llm_kwargs.get("model", "")),
        advanced_arg=plugin_kwargs.get("advanced_arg", ""),
        default_worker_num=llm_kwargs.get("default_worker_num", plugin_kwargs.get("default_worker_num", 8)),
        proxies=llm_kwargs.get("proxies", plugin_kwargs.get("proxies")),
        llm=LegacyLLMConfig(
            api_key_env=llm_kwargs.get("api_key_env", ""),
            api_key=llm_kwargs.get("api_key", ""),
            llm_url=llm_kwargs.get("llm_url", ""),
            temperature=llm_kwargs.get("temperature", 1.0),
            top_p=llm_kwargs.get("top_p", 1.0),
        ),
    )
    try:
        result = run_translation_workflow(txt, config)
    except Exception as exc:
        logger.error(f"工作流执行失败: {exc}")
        return False
    return bool(result["success"])
