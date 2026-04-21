from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from .prompts import build_translate_prompt
from .model_info import model_info


MULTI_PROCESS_PREFIXES = (
    "gpt",
    "chatgpt-",
    "api2d-",
    "azure",
    "spark",
    "zhipuai",
    "glm",
    "qwen",
)


class TranslatorClient(Protocol):
    def translate(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        top_p: float,
        proxies: dict | None = None,
    ) -> str:
        ...


@dataclass(slots=True, frozen=True)
class TranslationTask:
    fragment: str
    more_requirement: str = ""


def can_multi_process(model: str) -> bool:
    normalized_model = (model or "").strip().lower()
    if normalized_model in model_info and "can_multi_thread" in model_info[normalized_model]:
        return model_info[normalized_model]["can_multi_thread"]
    return any(normalized_model.startswith(prefix) for prefix in MULTI_PROCESS_PREFIXES)


def _resolve_max_workers(model: str, requested_workers: int, task_count: int) -> int:
    if task_count <= 1:
        return 1
    if not can_multi_process(model):
        return 1
    if requested_workers <= 0:
        return min(8, task_count)
    return min(requested_workers, task_count)


def _translate_task(
    client: TranslatorClient,
    model: str,
    task: TranslationTask,
    temperature: float,
    top_p: float,
    proxies: dict | None,
) -> str:
    if not task.fragment.strip():
        return task.fragment
    system_prompt, user_prompt = build_translate_prompt(task.more_requirement, task.fragment)
    return client.translate(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        top_p=top_p,
        proxies=proxies,
    )


def translate_segments(
    client: TranslatorClient,
    model: str,
    fragments: list[str],
    more_requirement: str = "",
    temperature: float = 1.0,
    top_p: float = 1.0,
    proxies: dict | None = None,
    max_workers: int = 8,
) -> list[str]:
    if not fragments:
        return []

    worker_count = _resolve_max_workers(model, max_workers, len(fragments))
    tasks = [TranslationTask(fragment=fragment, more_requirement=more_requirement) for fragment in fragments]
    executor = ThreadPoolExecutor(max_workers=worker_count)

    try:
        futures = [
            executor.submit(_translate_task, client, model, task, temperature, top_p, proxies)
            for task in tasks
        ]
        return [future.result() for future in futures]
    finally:
        executor.shutdown(wait=True)
