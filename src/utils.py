import os
import time
import tarfile
import zipfile
import traceback
import requests
import tiktoken
import json
from loguru import logger

# --- Configuration ---
CONFIG = {}

def load_config(config_path="config.json"):
    """
    从 JSON 配置文件加载配置。

    加载顺序（优先级从低到高）：
    1. 默认配置
    2. JSON 配置文件中的配置
    3. 环境变量（覆盖配置文件）

    Args:
        config_path: JSON 配置文件路径，默认为 "config.json"

    Returns:
        dict: 加载后的配置字典
    """
    global CONFIG

    # 默认配置
    default_config = {
        "arxiv": "",
        "model": "qwen-plus",
        "advanced_arg": "",
        "api_key": "sk-85a045810ddb487fad347a9d276d2c83",
        "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "arxiv_cache_dir": "arxiv_cache",
        "default_worker_num": 8,
        "proxies": None,
        "temperature": 1.0,
        "top_p": 1.0
    }

    # 从配置文件加载
    file_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            logger.info(f"已从配置文件加载: {config_path}")
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}")
    else:
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")

    # 合并配置（默认 -> 文件）
    CONFIG = {**default_config, **file_config}

    # 环境变量覆盖（优先级最高）
    env_mappings = {
        "OPENAI_API_KEY": "api_key",
        "OPENAI_BASE_URL": "llm_url",
        "ARXIV_CACHE_DIR": "arxiv_cache_dir"
    }

    for env_var, config_key in env_mappings.items():
        env_value = os.environ.get(env_var)
        if env_value:
            CONFIG[config_key] = env_value
            logger.info(f"环境变量 {env_var} 已覆盖配置文件设置")

    # 为了向后兼容，设置旧键名
    # 使用项目根目录（src的上一级目录）作为arxiv_cache的基础路径
    project_root = os.path.dirname(os.path.dirname(__file__))
    CONFIG["ARXIV_CACHE_DIR"] = os.path.join(project_root, CONFIG.get("arxiv_cache_dir", "arxiv_cache"))
    CONFIG["API_KEY"] = CONFIG.get("api_key")
    CONFIG["LLM_URL"] = CONFIG.get("llm_url")
    CONFIG["DEFAULT_WORKER_NUM"] = CONFIG.get("default_worker_num", 8)

    return CONFIG

# 模块加载时自动加载配置
load_config()

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
    os.makedirs(dest_dir, exist_ok=True)
    if tarfile.is_tarfile(file_path):
        with tarfile.open(file_path, 'r') as tar:
            tar.extractall(path=dest_dir)
    elif zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
    else:
        raise ValueError(f"Unknown archive format: {file_path}")

def trimmed_format_exc():
    """
    获取格式化的异常跟踪信息。

    Returns:
        异常跟踪字符串
    """
    return traceback.format_exc()

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
    model = llm_kwargs.get("llm_model", "gpt-3.5-turbo")
    if "16k" in model:
        return 16384
    elif "32k" in model:
        return 32768
    elif "gpt-4" in model:
        return 8192
    else:
        return 4096

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

# --- LLM Stub ---
class MockTokenizer:
    """
    分词器模拟类，用于计算文本token数量。

    优先使用tiktoken的cl100k_base编码器，不可用时退化为字符计数。
    """
    def __init__(self):
        """初始化分词器，尝试加载tiktoken编码器。"""
        try:
            self.enc = tiktoken.get_encoding("cl100k_base")
        except:
            self.enc = None

    def encode(self, txt, disallowed_special=()):
        """
        将文本编码为token列表。

        Args:
            txt: 输入文本
            disallowed_special: 不允许的特殊token集合

        Returns:
            token列表
        """
        if self.enc:
            return self.enc.encode(txt, disallowed_special=disallowed_special)
        return list(txt) # Fallback character counting

    def decode(self, tokens):
        """
        将token列表解码为文本。

        Args:
            tokens: token列表

        Returns:
            解码后的文本字符串
        """
        if self.enc:
            return self.enc.decode(tokens)
        return "".join(tokens) # Fallback

model_info = {
    "gpt-3.5-turbo": {
        "tokenizer": MockTokenizer(),
        "can_multi_thread": True
    }
}

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
    api_key = llm_kwargs.get("api_key", CONFIG["API_KEY"])
    if not api_key:
        raise ValueError("API KEY is missing. Set OPENAI_API_KEY environment variable.")

    url = llm_kwargs.get("llm_url", CONFIG["LLM_URL"])
    if not url.endswith("/chat/completions") and "api.openai.com" not in url:
        url = url.rstrip("/") + "/chat/completions"
    elif "api.openai.com" in url and not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    model = llm_kwargs.get("llm_model", "gpt-3.5-turbo")

    messages = []
    if sys_prompt:
        messages.append({"role": "system", "content": sys_prompt})
    for i in range(0, len(history), 2):
        if i < len(history):
            messages.append({"role": "user", "content": history[i]})
        if i + 1 < len(history):
            messages.append({"role": "assistant", "content": history[i+1]})

    messages.append({"role": "user", "content": inputs})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": llm_kwargs.get("temperature", 1.0),
        "top_p": llm_kwargs.get("top_p", 1.0),
        "stream": True
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, stream=True, proxies=CONFIG.get('proxies'))
        response.raise_for_status()

        full_text = ""
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8')
            if line.startswith('data: ') and line != 'data: [DONE]':
                try:
                    data = json.loads(line[6:])
                    if len(data['choices']) > 0 and 'delta' in data['choices'][0] and 'content' in data['choices'][0]['delta']:
                        chunk = data['choices'][0]['delta']['content']
                        full_text += chunk
                        if observe_window and len(observe_window) > 0:
                            observe_window[0] = full_text
                except Exception as e:
                    pass
        return full_text
    except Exception as e:
        logger.error(f"API Error: {str(e)}")
        raise
