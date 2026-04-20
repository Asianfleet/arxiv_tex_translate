"""
ArXiv LaTeX 翻译与编译工具 - 命令行入口

该脚本提供ArXiv论文LaTeX源码的自动下载、中文翻译和PDF编译功能。
"""

import sys
from loguru import logger

from src.config import ConfigError, RunOptions, load_app_config
from src.workflow import run_translation_workflow


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

    if not app_config.arxiv:
        logger.error("必须提供 arxiv 编号或网址。请在 config.json 中设置 'arxiv' 或使用 --arxiv 参数。")
        parser.print_help()
        sys.exit(1)

    try:
        result = run_translation_workflow(app_config.arxiv, app_config)
    except Exception as exc:
        logger.exception(f"工作流执行失败: {exc}")
        sys.exit(1)

    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
