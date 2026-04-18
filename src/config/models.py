from dataclasses import dataclass, field


@dataclass(slots=True)
class RunOptions:
    arxiv: str | None = None
    model: str | None = None
    advanced_arg: str | None = None


@dataclass(slots=True)
class LLMConfig:
    api_key_env: str
    api_key: str
    llm_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    temperature: float = 1.0
    top_p: float = 1.0


@dataclass(slots=True)
class AppConfig:
    arxiv: str = ""
    model: str = "qwen-plus"
    advanced_arg: str = ""
    llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(api_key_env="", api_key="")
    )
    arxiv_cache_dir: str = "arxiv_cache"
    default_worker_num: int = 8
    proxies: str | None = None
