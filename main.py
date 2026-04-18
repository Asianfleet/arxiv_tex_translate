"""
ArXiv LaTeX 翻译与编译工具 - 命令行入口

该脚本提供ArXiv论文LaTeX源码的自动下载、中文翻译和PDF编译功能。
"""

import sys
from loguru import logger

from src.config import ConfigError, RunOptions, load_app_config


def main():
    """命令行入口点，支持 JSON 配置文件。"""
    import argparse

    parser = argparse.ArgumentParser(description="Arxiv Latex 翻译与编译 (Standalone)")
    parser.add_argument("--config", type=str, default="config.json", help="配置文件路径 (JSON格式)")
    parser.add_argument("--arxiv", type=str, help="arxiv编号或网址，如 1812.10695（覆盖配置文件）")
    parser.add_argument("--model", type=str, help="LLM 模型（覆盖配置文件）")
    parser.add_argument("--advanced_arg", type=str, help="额外的翻译提示词（覆盖配置文件）")
    args = parser.parse_args()

    run_options = RunOptions(
        arxiv=args.arxiv,
        model=args.model,
        advanced_arg=args.advanced_arg,
    )

    try:
        app_config = load_app_config(args.config, overrides=run_options)
    except ConfigError as exc:
        logger.error(str(exc))
        sys.exit(1)

    arxiv_id = app_config.arxiv

    if not arxiv_id:
        logger.error("必须提供 arxiv 编号或网址。请在 config.json 中设置 'arxiv' 或使用 --arxiv 参数。")
        parser.print_help()
        sys.exit(1)

    llm_kwargs = {
        "api_key_env": app_config.llm.api_key_env,
        "api_key": app_config.llm.api_key,
        "llm_model": app_config.model,
        "llm_url": app_config.llm.llm_url,
        "temperature": app_config.llm.temperature,
        "top_p": app_config.llm.top_p,
        "default_worker_num": app_config.default_worker_num,
        "proxies": app_config.proxies,
    }

    plugin_kwargs = {
        "advanced_arg": app_config.advanced_arg,
        "arxiv_cache_dir": app_config.arxiv_cache_dir,
    }

    from src.main_fns import Latex_to_CN_PDF

    Latex_to_CN_PDF(arxiv_id, llm_kwargs, plugin_kwargs)


if __name__ == "__main__":
    main()
