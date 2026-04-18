from __future__ import annotations

import json
import os
import traceback

import requests
from loguru import logger

from .client import normalize_chat_completions_endpoint


def trimmed_format_exc():
    return traceback.format_exc()


def get_reduce_token_percent(err_msg):
    return 0.5, 500


def _resolve_api_key(llm_kwargs: dict) -> str:
    api_key = str(llm_kwargs.get("api_key", "") or "").strip()
    if api_key:
        return api_key

    env_name = str(llm_kwargs.get("api_key_env", "") or "").strip()
    if not env_name:
        return ""
    return os.environ.get(env_name, "").strip()


def predict_no_ui_long_connection(
    inputs: str,
    llm_kwargs: dict,
    history: list,
    sys_prompt: str,
    observe_window: list | None = None,
    console_silence: bool = False,
):
    """
    与 OpenAI 兼容接口建立长连接并增量读取响应。
    """
    del console_silence

    api_key = _resolve_api_key(llm_kwargs)
    if not api_key:
        raise ValueError("API KEY is missing. Set the configured API key environment variable.")

    url = normalize_chat_completions_endpoint(
        str(llm_kwargs.get("llm_url") or "https://api.openai.com/v1")
    )
    model = llm_kwargs.get("llm_model", "gpt-3.5-turbo")

    messages = []
    if sys_prompt:
        messages.append({"role": "system", "content": sys_prompt})
    for index in range(0, len(history), 2):
        messages.append({"role": "user", "content": history[index]})
        if index + 1 < len(history):
            messages.append({"role": "assistant", "content": history[index + 1]})
    messages.append({"role": "user", "content": inputs})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": llm_kwargs.get("temperature", 1.0),
        "top_p": llm_kwargs.get("top_p", 1.0),
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            proxies=llm_kwargs.get("proxies"),
            timeout=120,
        )
        response.raise_for_status()

        full_text = ""
        for line in response.iter_lines():
            if not line:
                continue
            decoded_line = line.decode("utf-8")
            if not decoded_line.startswith("data: ") or decoded_line == "data: [DONE]":
                continue
            try:
                data = json.loads(decoded_line[6:])
                choices = data.get("choices", [])
                if not choices:
                    continue
                chunk = choices[0].get("delta", {}).get("content", "")
                if not chunk:
                    continue
                full_text += chunk
                if observe_window:
                    observe_window[0] = full_text
            except Exception:
                continue
        return full_text
    except Exception as exc:
        logger.error(f"API Error: {exc}")
        raise
