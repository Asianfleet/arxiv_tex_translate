import time


def test_build_translate_prompt_preserves_legacy_translation_rules():
    from src.llm.prompts import build_translate_prompt

    system_prompt, user_prompt = build_translate_prompt("保留缩写原文。", "Original fragment.")

    assert system_prompt == "你是一位专业的翻译人员。"
    assert "中英文交界处" in user_prompt
    assert "不要在中文字符之间添加空格" in user_prompt
    assert "不要添加任何多余的换行符" in user_prompt
    assert "保留缩写原文。" in user_prompt
    assert "Original fragment." in user_prompt


def test_openai_compatible_client_normalizes_endpoint():
    from src.llm.client import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url="https://example.com/v1",
        api_key="secret",
    )
    already_normalized = OpenAICompatibleClient(
        base_url="https://example.com/v1/chat/completions",
        api_key="secret",
    )

    assert client.endpoint == "https://example.com/v1/chat/completions"
    assert already_normalized.endpoint == "https://example.com/v1/chat/completions"


def test_openai_compatible_client_translate_posts_openai_payload(monkeypatch):
    from src.llm import client as client_module

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": " 译文结果 \n"}}]}

    def fake_post(url, *, headers, json, proxies, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["proxies"] = proxies
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(client_module.requests, "post", fake_post)

    openai_client = client_module.OpenAICompatibleClient(
        base_url="https://example.com/v1",
        api_key="secret",
    )

    result = openai_client.translate(
        model="gpt-4o-mini",
        system_prompt="系统提示",
        user_prompt="待翻译片段",
        temperature=0.2,
        top_p=0.8,
        proxies={"https": "http://proxy.local:8080"},
    )

    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret",
    }
    assert captured["json"] == {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "待翻译片段"},
        ],
        "temperature": 0.2,
        "top_p": 0.8,
        "stream": False,
    }
    assert captured["proxies"] == {"https": "http://proxy.local:8080"}
    assert captured["timeout"] == 120
    assert result == "译文结果"


def test_can_multi_process_supports_known_prefixes():
    from src.llm.batching import can_multi_process

    assert can_multi_process("qwen-plus") is True
    assert can_multi_process(" QWEN-plus ") is True
    assert can_multi_process("gpt-4o-mini") is True
    assert can_multi_process("glm-4-flash") is True
    assert can_multi_process("azure-gpt-4o") is True
    assert can_multi_process("unknown-model") is False


def test_can_multi_process_prefers_explicit_model_metadata(monkeypatch):
    from src.llm import batching

    monkeypatch.setitem(batching.model_info, "custom-parallel", {"can_multi_thread": True})
    monkeypatch.setitem(batching.model_info, "qwen-serial", {"can_multi_thread": False})

    assert batching.can_multi_process("custom-parallel") is True
    assert batching.can_multi_process("qwen-serial") is False
    assert batching.can_multi_process(" QWEN-plus ") is True


def test_translate_segments_preserves_result_order():
    from src.llm.batching import translate_segments

    class FakeClient:
        def translate(self, model, system_prompt, user_prompt, temperature, top_p, proxies=None):
            assert model == "qwen-plus"
            assert temperature == 0.3
            assert top_p == 0.9
            assert proxies == {"https": "http://proxy.local:8080"}
            assert system_prompt == "你是一位专业的翻译人员。"
            if "fragment-1" in user_prompt:
                time.sleep(0.03)
                return "译文-1"
            if "fragment-2" in user_prompt:
                time.sleep(0.01)
                return "译文-2"
            return "译文-3"

    results = translate_segments(
        client=FakeClient(),
        model="qwen-plus",
        fragments=["fragment-1", "fragment-2", "fragment-3"],
        more_requirement="保留术语。",
        temperature=0.3,
        top_p=0.9,
        proxies={"https": "http://proxy.local:8080"},
        max_workers=3,
    )

    assert results == ["译文-1", "译文-2", "译文-3"]


def test_translate_segments_falls_back_to_single_worker_for_unknown_model(monkeypatch):
    from src.llm import batching

    captured = {}

    class ImmediateFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class DummyExecutor:
        def __init__(self, *, max_workers):
            captured["max_workers"] = max_workers

        def submit(self, fn, *args, **kwargs):
            return ImmediateFuture(fn(*args, **kwargs))

        def shutdown(self, wait=True):
            captured["shutdown"] = wait

    class FakeClient:
        def translate(self, model, system_prompt, user_prompt, temperature, top_p, proxies=None):
            captured.setdefault("translated_prompts", []).append(user_prompt)
            captured["translate_args"] = {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "top_p": top_p,
                "proxies": proxies,
            }
            return "单线程译文"

    monkeypatch.setattr(batching, "ThreadPoolExecutor", DummyExecutor)

    results = batching.translate_segments(
        client=FakeClient(),
        model="unknown-model",
        fragments=["fragment-1", "fragment-2"],
        more_requirement="",
        temperature=0.4,
        top_p=0.7,
        proxies=None,
        max_workers=4,
    )

    assert captured["max_workers"] == 1
    assert captured["shutdown"] is True
    assert captured["translate_args"]["model"] == "unknown-model"
    assert captured["translate_args"]["temperature"] == 0.4
    assert captured["translate_args"]["top_p"] == 0.7
    assert len(captured["translated_prompts"]) == 2
    assert results == ["单线程译文", "单线程译文"]


def test_llm_package_exposes_core_exports():
    import src.llm as llm

    assert callable(llm.OpenAICompatibleClient)
    assert callable(llm.build_translate_prompt)
    assert callable(llm.can_multi_process)
    assert callable(llm.translate_segments)
    assert "TranslatePrompt" not in getattr(llm, "__all__", [])
    assert not hasattr(llm, "TranslatePrompt")
