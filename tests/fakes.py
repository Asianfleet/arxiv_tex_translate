from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FakeLLMConfig:
    api_key_env: str = "TEST_API_KEY"
    api_key: str = "test-api-key"
    llm_url: str = "https://example.com/v1"
    temperature: float = 0.2
    top_p: float = 0.9


@dataclass(slots=True)
class FakeConfig:
    arxiv_cache_dir: str
    model: str = "qwen-plus"
    advanced_arg: str = ""
    default_worker_num: int = 2
    proxies: dict | None = None
    llm: FakeLLMConfig = field(default_factory=FakeLLMConfig)

