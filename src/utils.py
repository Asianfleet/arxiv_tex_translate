import os
import time
from loguru import logger

from src.config import AppConfig, RunOptions, load_app_config
from src.llm.model_info import model_info, get_max_token_for_model
from src.llm.streaming import (
    predict_no_ui_long_connection as _predict_no_ui_long_connection,
    trimmed_format_exc as _trimmed_format_exc,
)
from src.project.arxiv import extract_archive as _extract_archive

# --- Configuration ---
CONFIG = {}


def _default_legacy_config():
    project_root = os.path.dirname(os.path.dirname(__file__))
    cache_dir = os.path.join(project_root, "arxiv_cache")
    return {
        "arxiv": "",
        "model": "qwen-plus",
        "advanced_arg": "",
        "api_key_env": "",
        "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "arxiv_cache_dir": "arxiv_cache",
        "default_worker_num": 8,
        "proxies": None,
        "temperature": 1.0,
        "top_p": 1.0,
        "ARXIV_CACHE_DIR": cache_dir,
        "API_KEY": "",
        "LLM_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DEFAULT_WORKER_NUM": 8,
    }


def _to_legacy_config(app_config: AppConfig):
    project_root = os.path.dirname(os.path.dirname(__file__))
    return {
        "arxiv": app_config.arxiv,
        "model": app_config.model,
        "advanced_arg": app_config.advanced_arg,
        "api_key_env": app_config.llm.api_key_env,
        "llm_url": app_config.llm.llm_url,
        "arxiv_cache_dir": app_config.arxiv_cache_dir,
        "default_worker_num": app_config.default_worker_num,
        "proxies": app_config.proxies,
        "temperature": app_config.llm.temperature,
        "top_p": app_config.llm.top_p,
        "ARXIV_CACHE_DIR": os.path.join(project_root, app_config.arxiv_cache_dir),
        "API_KEY": app_config.llm.api_key,
        "LLM_URL": app_config.llm.llm_url,
        "DEFAULT_WORKER_NUM": app_config.default_worker_num,
    }


def load_config(
    config_path="config.json",
    overrides: RunOptions | None = None,
    app_config: AppConfig | None = None,
):
    """
    从配置文件与环境变量加载配置，并同步旧版 CONFIG 兼容键。
    """
    resolved_config = app_config or load_app_config(config_path, overrides=overrides)
    CONFIG.clear()
    CONFIG.update(_to_legacy_config(resolved_config))
    logger.info(f"已加载配置: {config_path}")
    return CONFIG


CONFIG.update(_default_legacy_config())

def get_conf(*args):
    """
    从配置中获取指定键的值。

    Args:
        *args: 一个或多个配置键名

    Returns:
        单个值（如果只传入一个键）或值的元组（如果传入多个键）
    """
    if len(args) == 1:
        return CONFIG.get(args[0], None)
    return tuple(CONFIG.get(arg, None) for arg in args)

def get_log_folder(plugin_name='default'):
    """
    获取日志文件夹路径，如果不存在则创建。

    Args:
        plugin_name: 插件名称，默认为'default'

    Returns:
        日志文件夹路径
    """
    folder = os.path.join(os.path.dirname(__file__), "logs", plugin_name)
    os.makedirs(folder, exist_ok=True)
    return folder

def gen_time_str():
    """
    生成当前时间的字符串格式（用于文件命名）。

    Returns:
        格式为"YYYY-MM-DD-HH-MM-SS"的时间字符串
    """
    return time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())

def extract_archive(file_path, dest_dir):
    """
    解压tar或zip压缩文件到目标目录。

    Args:
        file_path: 压缩文件路径
        dest_dir: 目标解压目录

    Raises:
        ValueError: 如果文件格式不支持
    """
    _extract_archive(file_path=file_path, dest_dir=dest_dir)

def trimmed_format_exc():
    """
    获取格式化的异常跟踪信息。

    Returns:
        异常跟踪字符串
    """
    return _trimmed_format_exc()

def map_file_to_sha256(file_path):
    """
    计算文件的SHA256哈希值。

    Args:
        file_path: 文件路径

    Returns:
        SHA256哈希值的十六进制字符串
    """
    import hashlib
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_max_token(llm_kwargs):
    """
    根据模型名称获取最大token数限制。

    Args:
        llm_kwargs: 包含llm_model的参数字典

    Returns:
        模型的最大token数
    """
    return get_max_token_for_model(llm_kwargs.get("llm_model", "gpt-3.5-turbo"))

def get_reduce_token_percent(err_msg):
    """
    根据错误消息决定token缩减比例和数量。

    Args:
        err_msg: 错误消息字符串

    Returns:
        tuple: (缩减比例, 缩减的token数)
    """
    return 0.5, 500

class Singleton(object):
    """
    单例模式装饰器类，确保一个类只有一个实例。
    """
    def __init__(self, cls):
        """初始化单例装饰器。"""
        self._cls = cls
        self._instance = {}
    def __call__(self):
        """获取或创建类实例。"""
        if self._cls not in self._instance:
            self._instance[self._cls] = self._cls()
        return self._instance[self._cls]

def predict_no_ui_long_connection(inputs: str, llm_kwargs: dict, history: list, sys_prompt: str, observe_window: list=[], console_silence: bool=False):
    """
    与LLM API建立长连接，流式获取响应。

    Args:
        inputs: 用户输入文本
        llm_kwargs: LLM参数字典，包含api_key、llm_url、llm_model等
        history: 历史对话记录列表
        sys_prompt: 系统提示词
        observe_window: 观察窗口列表，用于实时显示响应内容
        console_silence: 是否静默控制台输出

    Returns:
        LLM的完整响应文本

    Raises:
        ValueError: 如果API KEY缺失
        Exception: 如果API请求失败
    """
    effective_kwargs = dict(llm_kwargs)
    if "api_key" not in effective_kwargs and CONFIG.get("API_KEY"):
        effective_kwargs["api_key"] = CONFIG["API_KEY"]
    if "api_key_env" not in effective_kwargs and CONFIG.get("api_key_env"):
        effective_kwargs["api_key_env"] = CONFIG["api_key_env"]
    if "llm_url" not in effective_kwargs and CONFIG.get("LLM_URL"):
        effective_kwargs["llm_url"] = CONFIG["LLM_URL"]
    if "proxies" not in effective_kwargs and CONFIG.get("proxies") is not None:
        effective_kwargs["proxies"] = CONFIG["proxies"]

    return _predict_no_ui_long_connection(
        inputs=inputs,
        llm_kwargs=effective_kwargs,
        history=history,
        sys_prompt=sys_prompt,
        observe_window=observe_window,
        console_silence=console_silence,
    )
