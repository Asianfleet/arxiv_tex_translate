"""
ArXiv LaTeX 翻译与编译工具 - 命令行入口

该脚本提供ArXiv论文LaTeX源码的自动下载、中文翻译和PDF编译功能。
"""

import sys
from loguru import logger

from src.utils import get_conf, load_config, CONFIG
from src.main_fns import Latex_to_CN_PDF


def main():
    """命令行入口点，支持 JSON 配置文件。"""
    import argparse

    parser = argparse.ArgumentParser(description="Arxiv Latex 翻译与编译 (Standalone)")
    parser.add_argument("--config", type=str, default="config.json", help="配置文件路径 (JSON格式)")
    parser.add_argument("--arxiv", type=str, help="arxiv编号或网址，如 1812.10695（覆盖配置文件）")
    parser.add_argument("--model", type=str, help="LLM 模型（覆盖配置文件）")
    parser.add_argument("--advanced_arg", type=str, help="额外的翻译提示词（覆盖配置文件）")
    args = parser.parse_args()

    # 加载配置文件
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

    Latex_to_CN_PDF(arxiv_id, llm_kwargs, plugin_kwargs)


if __name__ == "__main__":
    main()
