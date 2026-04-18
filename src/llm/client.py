from dataclasses import dataclass

import requests


def normalize_chat_completions_endpoint(endpoint: str) -> str:
    normalized_endpoint = endpoint.rstrip("/")
    if normalized_endpoint.endswith("/chat/completions"):
        return normalized_endpoint
    return f"{normalized_endpoint}/chat/completions"


def _extract_content(response_json: dict) -> str:
    return response_json["choices"][0]["message"]["content"]


@dataclass(slots=True)
class OpenAICompatibleClient:
    base_url: str
    api_key: str

    @property
    def endpoint(self) -> str:
        return normalize_chat_completions_endpoint(self.base_url)

    def translate(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        top_p: float,
        proxies: dict | None = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=120,
        )
        response.raise_for_status()
        return _extract_content(response.json()).strip()
