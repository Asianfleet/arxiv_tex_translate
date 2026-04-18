from __future__ import annotations

import tiktoken


class MockTokenizer:
    """
    兼容旧逻辑的轻量分词器包装。
    """

    def __init__(self):
        try:
            self.enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.enc = None

    def encode(self, txt, disallowed_special=()):
        if self.enc:
            return self.enc.encode(txt, disallowed_special=disallowed_special)
        return list(txt)

    def decode(self, tokens):
        if self.enc:
            return self.enc.decode(tokens)
        return "".join(tokens)


model_info = {
    "gpt-3.5-turbo": {
        "tokenizer": MockTokenizer(),
        "can_multi_thread": True,
    }
}


def get_max_token_for_model(model_name: str) -> int:
    normalized_name = str(model_name or "gpt-3.5-turbo")
    if "16k" in normalized_name:
        return 16384
    if "32k" in normalized_name:
        return 32768
    if "gpt-4" in normalized_name:
        return 8192
    return 4096
