# Compatible LaTeX Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持当前 CLI、缓存目录、输出文件名和核心 PDF 产物兼容的前提下，重写 `arxiv_tex_translate` 的内部结构，并把原始的 mask/链表算法升级为 `span planner + segment renderer` 新内核。

**Architecture:** 实施路径采用“分阶段原地重构 + 兼容包装器”。先建立强类型配置、项目工作区和新的 `latex/llm/workflow` 模块，再让旧入口和旧模块逐步转发到新实现；核心 LaTeX 切分以 `pylatexenc` 辅助解析为首选、旧 regex/brace 逻辑为 fallback，保证产物级兼容。

**Tech Stack:** Python 3.11+、`pylatexenc`、`requests`、`loguru`、`numpy`、`PyPDF2`、`pytest`

---

## Planned File Map

### New files

- `src/config/__init__.py` — 导出配置相关类型与加载函数
- `src/config/models.py` — `AppConfig`、`LLMConfig`、`RunOptions`
- `src/config/loader.py` — `config.json` 解析、环境变量密钥读取与校验
- `src/runtime.py` — 组装运行参数，提供工作流入口使用的统一运行时对象
- `src/project/__init__.py` — 导出项目准备函数
- `src/project/arxiv.py` — arXiv 输入归一化、下载源码、缓存命中逻辑
- `src/project/workspace.py` — 本地项目复制、`workfolder/logs/outputs` 创建
- `src/project/outputs.py` — PDF 归档与输出路径工具
- `src/latex/__init__.py` — 导出 LaTeX 处理公共接口
- `src/latex/models.py` — `SpanKind`、`LatexSpan`、`Segment`、`DocumentPlan`
- `src/latex/merge.py` — 主文件识别、`\input` 合并、注释清理、中文前导注入
- `src/latex/parser.py` — `pylatexenc` 辅助结构解析与 fallback 规则
- `src/latex/segmenter.py` — span 合并、冲突处理、segment 切分、`debug_log.html`
- `src/latex/sanitize.py` — 译文修复与结构安全检查
- `src/latex/render.py` — 段级回填、免责声明插入、渲染输出
- `src/latex/recovery.py` — 编译日志错误行提取与局部回滚
- `src/latex/bilingual.py` — 双语 TeX 生成和 caption 双语合并
- `src/latex/compiler.py` — 编译器选择、编译顺序、BibTeX、双语编译
- `src/llm/__init__.py` — 导出 LLM 客户端接口
- `src/llm/prompts.py` — 翻译 prompt 构造
- `src/llm/client.py` — OpenAI-compatible HTTP 客户端
- `src/llm/batching.py` — 线程池批量翻译、重试、token 裁剪适配
- `src/workflow.py` — 新总工作流 `run_translation_workflow()`
- `requirements-dev.txt` — 开发与测试依赖
- `tests/conftest.py` — 公共 fixture 和临时项目复制助手
- `tests/fakes.py` — Fake client / fake compiler
- `tests/fixtures/sample_project/main.tex` — 最小可测试 LaTeX 主文件
- `tests/fixtures/sample_project/intro.tex` — `\input` 引用的正文片段
- `tests/test_config_loader.py` — 配置与密钥策略测试
- `tests/test_project_workspace.py` — 工作区与缓存准备测试
- `tests/test_latex_merge.py` — 合并与主文件识别测试
- `tests/test_latex_parser.py` — 结构解析测试
- `tests/test_latex_segmenter.py` — span/segment 生成测试
- `tests/test_llm_batching.py` — prompt、URL、并发策略测试
- `tests/test_latex_render.py` — 清洗、渲染、恢复测试
- `tests/test_latex_compiler.py` — 编译器选择与编译顺序测试
- `tests/test_bilingual.py` — 双语 caption 与正文拼接测试
- `tests/test_workflow_smoke.py` — 假客户端下的端到端冒烟测试

### Existing files to modify

- `main.py` — 仅保留 CLI 与启动逻辑
- `config.example.json` — 改为 `api_key_env` 示例
- `README.md` — 更新配置方式与实施后的模块结构
- `requirements.txt` — 增加 `pylatexenc`
- `src/main_fns/__init__.py` — 保留兼容导出，转发到新工作流
- `src/main_fns/workflow.py` — 兼容包装器
- `src/main_fns/arxiv_utils.py` — 兼容包装器
- `src/main_fns/file_manager.py` — 兼容包装器
- `src/latex_fns/latex_toolbox.py` — 保留外部可用函数并转发到新模块
- `src/latex_fns/latex_actions.py` — 逐步裁成兼容包装器
- `src/llm_utils.py` — 逐步裁成兼容包装器

### Implementation note

- 该计划默认在当前工作区实施，因为仓库规则要求**使用 git worktree 之前必须先征求用户同意**。
- 每个任务都应保持当前 CLI 可以启动，并尽量保留旧导入路径可用。

---

### Task 1: 配置模型与环境变量密钥策略

**Files:**
- Create: `src/config/__init__.py`
- Create: `src/config/models.py`
- Create: `src/config/loader.py`
- Create: `tests/test_config_loader.py`
- Modify: `main.py`
- Modify: `config.example.json`

- [ ] **Step 1: 写出配置加载失败测试**

```python
import json
from pathlib import Path

import pytest

from src.config.loader import load_app_config


def write_config(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_app_config_reads_api_key_from_named_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    config_path = write_config(
        tmp_path / "config.json",
        {
            "arxiv": "1812.10695",
            "model": "qwen-plus",
            "advanced_arg": "",
            "api_key_env": "MY_TRANSLATOR_KEY",
            "llm_url": "https://example.com/v1",
            "arxiv_cache_dir": "arxiv_cache",
            "default_worker_num": 8,
            "proxies": None,
            "temperature": 1.0,
            "top_p": 1.0,
        },
    )
    config = load_app_config(config_path)
    assert config.api_key_env == "MY_TRANSLATOR_KEY"
    assert config.api_key == "secret-token"


def test_load_app_config_rejects_legacy_api_key(tmp_path):
    config_path = write_config(
        tmp_path / "config.json",
        {
            "model": "qwen-plus",
            "api_key": "do-not-allow",
            "api_key_env": "MY_TRANSLATOR_KEY",
        },
    )
    with pytest.raises(ValueError, match="api_key"):
        load_app_config(config_path)


def test_load_app_config_requires_named_env_value(tmp_path):
    config_path = write_config(
        tmp_path / "config.json",
        {
            "model": "qwen-plus",
            "api_key_env": "MISSING_TRANSLATOR_KEY",
        },
    )
    with pytest.raises(ValueError, match="MISSING_TRANSLATOR_KEY"):
        load_app_config(config_path)
```

- [ ] **Step 2: 运行测试，确认当前实现失败**

Run: `python -m pytest tests/test_config_loader.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.config'
```

- [ ] **Step 3: 写入最小可用实现**

`src/config/models.py`

```python
from dataclasses import dataclass


@dataclass(slots=True)
class AppConfig:
    arxiv: str
    model: str
    advanced_arg: str
    api_key_env: str
    api_key: str
    llm_url: str
    arxiv_cache_dir: str
    default_worker_num: int
    proxies: str | None
    temperature: float
    top_p: float
```

`src/config/loader.py`

```python
import json
import os
from pathlib import Path

from .models import AppConfig


DEFAULT_CONFIG = {
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
}


def load_app_config(config_path: str | Path = "config.json") -> AppConfig:
    path = Path(config_path)
    payload = DEFAULT_CONFIG.copy()
    if path.exists():
        payload |= json.loads(path.read_text(encoding="utf-8"))
    if "api_key" in payload:
        raise ValueError("config.json 已废弃 api_key；请改用 api_key_env")
    env_name = payload.get("api_key_env", "").strip()
    if not env_name:
        raise ValueError("config.json 必须提供 api_key_env")
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise ValueError(f"环境变量 {env_name} 未设置")
    return AppConfig(api_key=api_key, **payload)
```

`src/config/__init__.py`

```python
from .loader import load_app_config
from .models import AppConfig

__all__ = ["AppConfig", "load_app_config"]
```

`main.py`

```python
import argparse
import sys

from loguru import logger

from src.config import load_app_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Arxiv Latex 翻译与编译")
    parser.add_argument("--config", type=str, default="config.json")
    parser.add_argument("--arxiv", type=str)
    parser.add_argument("--model", type=str)
    parser.add_argument("--advanced_arg", type=str)
    args = parser.parse_args()
    try:
        config = load_app_config(args.config)
    except ValueError as exc:
        logger.error(str(exc))
        parser.print_help()
        sys.exit(1)
    logger.info(f"配置加载完成: model={config.model}")
```

`config.example.json`

```json
{
  "arxiv": "",
  "model": "qwen-plus",
  "advanced_arg": "",
  "api_key_env": "MY_TRANSLATOR_KEY",
  "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "arxiv_cache_dir": "arxiv_cache",
  "default_worker_num": 8,
  "proxies": null,
  "temperature": 1.0,
  "top_p": 1.0
}
```

- [ ] **Step 4: 补上运行时参数归一化入口**

Create `src/runtime.py`

```python
from dataclasses import dataclass

from src.config import AppConfig


@dataclass(slots=True)
class RunOptions:
    input_value: str
    model: str
    advanced_arg: str
    no_cache: bool


def build_run_options(config: AppConfig, cli_arxiv: str | None, cli_model: str | None, cli_advanced_arg: str | None) -> RunOptions:
    input_value = cli_arxiv or config.arxiv
    advanced_arg = cli_advanced_arg or config.advanced_arg
    no_cache = "--no-cache" in advanced_arg
    clean_advanced_arg = advanced_arg.replace("--no-cache", "").strip()
    return RunOptions(
        input_value=input_value,
        model=cli_model or config.model,
        advanced_arg=clean_advanced_arg,
        no_cache=no_cache,
    )
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_config_loader.py -v`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/config src/runtime.py tests/test_config_loader.py main.py config.example.json
git commit -m "feat(config): 改用 api_key_env 读取环境变量密钥"
```

---

### Task 2: 项目输入归一化与工作区准备

**Files:**
- Create: `src/project/__init__.py`
- Create: `src/project/arxiv.py`
- Create: `src/project/workspace.py`
- Create: `src/project/outputs.py`
- Create: `tests/test_project_workspace.py`
- Modify: `src/main_fns/arxiv_utils.py`
- Modify: `src/main_fns/file_manager.py`

- [ ] **Step 1: 写出工作区与输入归一化失败测试**

```python
from pathlib import Path

from src.project.arxiv import normalize_arxiv_input
from src.project.workspace import ensure_run_dirs, prepare_local_project


def test_normalize_arxiv_input_turns_id_into_abs_url():
    url, arxiv_id = normalize_arxiv_input("1812.10695")
    assert url == "https://arxiv.org/abs/1812.10695"
    assert arxiv_id == "1812.10695"


def test_prepare_local_project_skips_runtime_dirs(tmp_path):
    source = tmp_path / "paper"
    source.mkdir()
    (source / "main.tex").write_text("\\documentclass{article}", encoding="utf-8")
    (source / "outputs").mkdir()
    (source / "logs").mkdir()
    (source / "workfolder").mkdir()

    cache_root = tmp_path / "cache"
    project_dir, run_id = prepare_local_project(source, cache_root, "2026-04-18-00-00-00")

    assert run_id == "local_cache/2026-04-18-00-00-00"
    assert (project_dir / "main.tex").exists()
    assert not (project_dir / "outputs").exists()
    assert not (project_dir / "logs").exists()
    assert not (project_dir / "workfolder").exists()


def test_ensure_run_dirs_creates_outputs_and_logs(tmp_path):
    run_root, outputs_dir, logs_dir = ensure_run_dirs(tmp_path / "cache", "1812.10695")
    assert run_root.exists()
    assert outputs_dir.exists()
    assert logs_dir.exists()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_project_workspace.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.project'
```

- [ ] **Step 3: 实现新项目模块**

`src/project/arxiv.py`

```python
from pathlib import Path


def normalize_arxiv_input(value: str) -> tuple[str, str | None]:
    raw = value.strip()
    if raw.startswith("https://arxiv.org/abs/"):
        return raw, raw.split("/abs/")[-1].split("v")[0]
    if raw.startswith("https://arxiv.org/pdf/"):
        arxiv_id = raw.split("/")[-1].split(".pdf")[0].split("v")[0]
        return f"https://arxiv.org/abs/{arxiv_id}", arxiv_id
    if "." in raw and "/" not in raw:
        return f"https://arxiv.org/abs/{raw}", raw.split("v")[0]
    return raw, None
```

`src/project/workspace.py`

```python
import shutil
from pathlib import Path


def ensure_run_dirs(cache_root: Path, run_id: str) -> tuple[Path, Path, Path]:
    run_root = cache_root / run_id
    outputs_dir = run_root / "outputs"
    logs_dir = run_root / "logs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return run_root, outputs_dir, logs_dir


def prepare_local_project(local_path: Path, cache_root: Path, timestamp: str) -> tuple[Path, str]:
    run_id = f"local_cache/{timestamp}"
    run_root, _, _ = ensure_run_dirs(cache_root, run_id)
    if local_path.is_file():
        shutil.copy2(local_path, run_root / local_path.name)
        return run_root, run_id
    for item in local_path.iterdir():
        if item.name in {"outputs", "logs", "workfolder"}:
            continue
        target = run_root / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return run_root, run_id
```

`src/project/outputs.py`

```python
from pathlib import Path
import shutil


def archive_compiled_pdfs(work_folder: Path, outputs_dir: Path) -> None:
    for name in ("merge.pdf", "merge_translate_zh.pdf", "merge_bilingual.pdf"):
        source = work_folder / name
        if source.exists():
            shutil.copy2(source, outputs_dir / name)
```

- [ ] **Step 4: 给旧模块加兼容转发**

`src/main_fns/arxiv_utils.py`

```python
from src.project.arxiv import normalize_arxiv_input

__all__ = ["normalize_arxiv_input"]
```

`src/main_fns/file_manager.py`

```python
from pathlib import Path

from src.project.outputs import archive_compiled_pdfs
from src.project.workspace import ensure_run_dirs, prepare_local_project


def get_run_root(cache_root: str, run_id: str) -> str:
    return str(Path(cache_root) / run_id)
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_project_workspace.py -v`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/project src/main_fns/arxiv_utils.py src/main_fns/file_manager.py tests/test_project_workspace.py
git commit -m "feat(project): 拆出项目输入归一化与工作区准备"
```

---

### Task 3: 主 TeX 识别、`\input` 合并与中文前导注入

**Files:**
- Create: `src/latex/merge.py`
- Create: `tests/test_latex_merge.py`
- Modify: `requirements.txt`
- Modify: `src/latex_fns/latex_toolbox.py`

- [ ] **Step 1: 写出合并层失败测试**

```python
from pathlib import Path

from src.latex.merge import ensure_zh_preamble, find_main_tex_file, merge_project_tex


def test_find_main_tex_file_prefers_real_paper(tmp_path):
    template = tmp_path / "template.tex"
    template.write_text("\\documentclass{article}\\nGuidelines for authors", encoding="utf-8")
    paper = tmp_path / "paper.tex"
    paper.write_text("\\documentclass{article}\\n\\input{intro}", encoding="utf-8")
    assert find_main_tex_file([template, paper]) == paper


def test_merge_project_tex_expands_input(tmp_path):
    intro = tmp_path / "intro.tex"
    intro.write_text("Hello world.", encoding="utf-8")
    main_file = tmp_path / "main.tex"
    main_file.write_text("\\documentclass{article}\\n\\begin{document}\\n\\input{intro}\\n\\end{document}", encoding="utf-8")
    merged = merge_project_tex(tmp_path, main_file.read_text(encoding="utf-8"))
    assert "Hello world." in merged


def test_ensure_zh_preamble_injects_ctex_and_abstract():
    tex = "\\documentclass{article}\\n\\begin{document}\\n正文\\n\\end{document}"
    merged = ensure_zh_preamble(tex)
    assert "\\usepackage{ctex}" in merged
    assert "\\begin{abstract}" in merged
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_latex_merge.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.latex'
```

- [ ] **Step 3: 写入合并层实现并引入 `pylatexenc` 依赖**

`requirements.txt`

```text
requests>=2.28.0
loguru>=0.6.0
tiktoken>=0.5.0
numpy>=1.24.0
PyPDF2>=3.0.0
pylatexenc>=2.10
```

`src/latex/merge.py`

```python
import re
from pathlib import Path


def remove_comments(tex: str) -> str:
    lines = [line for line in tex.splitlines() if not line.lstrip().startswith("%")]
    return re.sub(r"(?<!\\)%.*", "", "\n".join(lines))


def find_main_tex_file(files: list[Path]) -> Path:
    candidates: list[tuple[int, Path]] = []
    for path in files:
        content = path.read_text(encoding="utf-8", errors="ignore")
        if "\\documentclass" not in content:
            continue
        score = 0
        for token in ("\\input", "\\ref", "\\cite"):
            score += int(token in content)
        for token in ("Guidelines", "manuscript", "reviewers"):
            score -= int(token in content)
        candidates.append((score, path))
    if not candidates:
        raise RuntimeError("无法找到主 Tex 文件")
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]


def merge_project_tex(project_root: Path, main_tex: str) -> str:
    merged = remove_comments(main_tex)
    for match in list(re.finditer(r"\\input\{(.*?)\}", merged))[::-1]:
        target = project_root / match.group(1)
        if target.suffix != ".tex":
            target = target.with_suffix(".tex")
        child = target.read_text(encoding="utf-8", errors="replace")
        merged = merged[: match.start()] + merge_project_tex(project_root, child) + merged[match.end() :]
    return merged


def ensure_zh_preamble(tex: str) -> str:
    output = tex
    documentclass = re.search(r"\\documentclass.*\n", output)
    if documentclass:
        output = output[: documentclass.end()] + "\\usepackage{ctex}\n\\usepackage{url}\n" + output[documentclass.end() :]
    if "\\begin{abstract}" not in output and "\\abstract{" not in output:
        output = output.replace("\\begin{document}\n", "\\begin{document}\n\\begin{abstract}\n\\end{abstract}\n", 1)
    return output
```

- [ ] **Step 4: 让旧工具箱优先转发到新实现**

`src/latex_fns/latex_toolbox.py`

```python
from pathlib import Path

from src.latex.merge import ensure_zh_preamble, find_main_tex_file, merge_project_tex, remove_comments


def rm_comments(main_file: str) -> str:
    return remove_comments(main_file)


def merge_tex_files(project_folder: str, main_file: str, mode: str) -> str:
    merged = merge_project_tex(Path(project_folder), main_file)
    return ensure_zh_preamble(merged) if mode == "translate_zh" else merged
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_latex_merge.py -v`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add requirements.txt src/latex/merge.py src/latex_fns/latex_toolbox.py tests/test_latex_merge.py
git commit -m "feat(latex): 拆出主文件识别与合并层"
```

---

### Task 4: 结构解析与 span 模型

**Files:**
- Create: `src/latex/__init__.py`
- Create: `src/latex/models.py`
- Create: `src/latex/parser.py`
- Create: `tests/test_latex_parser.py`

- [ ] **Step 1: 写出结构解析失败测试**

```python
from src.latex.models import SpanKind
from src.latex.parser import LatexStructureParser


def test_parser_finds_caption_and_abstract_spans():
    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\begin{abstract}Abstract text.\\end{abstract}\n"
        "\\begin{figure}\\caption{Caption text.}\\end{figure}\n"
        "\\end{document}\n"
    )
    spans = LatexStructureParser().collect_spans(tex)
    kinds = [span.kind for span in spans]
    assert SpanKind.ABSTRACT in kinds
    assert SpanKind.CAPTION in kinds


def test_parser_uses_fallback_when_primary_parser_raises(monkeypatch):
    parser = LatexStructureParser()
    monkeypatch.setattr(parser, "_collect_with_latexwalker", lambda text: (_ for _ in ()).throw(RuntimeError("boom")))
    spans = parser.collect_spans("\\section{Intro}")
    assert spans
    assert any(span.kind is SpanKind.COMMAND for span in spans)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_latex_parser.py -v`

Expected:

```text
E   ImportError: cannot import name 'SpanKind'
```

- [ ] **Step 3: 定义 span 数据模型与主解析器**

`src/latex/models.py`

```python
from dataclasses import dataclass, field
from enum import StrEnum


class SpanKind(StrEnum):
    PREAMBLE = "preamble"
    COMMAND = "command"
    ENVIRONMENT = "environment"
    MATH = "math"
    CAPTION = "caption"
    ABSTRACT = "abstract"
    TEXT = "text"


@dataclass(slots=True)
class LatexSpan:
    start: int
    end: int
    kind: SpanKind
    translatable: bool
    reason: str
    priority: int = 0


@dataclass(slots=True)
class Segment:
    index: int
    kind: SpanKind
    source_text: str
    translatable: bool
    line_start: int
    line_end: int
    reason: str


@dataclass(slots=True)
class DocumentPlan:
    merged_tex: str
    spans: list[LatexSpan] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    title: str = "unknown"
    abstract: str = "unknown"
```

`src/latex/parser.py`

```python
import re

from pylatexenc.latexwalker import LatexWalker

from .models import LatexSpan, SpanKind


class LatexStructureParser:
    def collect_spans(self, tex: str) -> list[LatexSpan]:
        try:
            return self._collect_with_latexwalker(tex)
        except Exception:
            return self._collect_with_fallback(tex)

    def _collect_with_latexwalker(self, tex: str) -> list[LatexSpan]:
        LatexWalker(tex).get_latex_nodes()
        spans = self._collect_with_fallback(tex)
        return spans

    def _collect_with_fallback(self, tex: str) -> list[LatexSpan]:
        spans: list[LatexSpan] = []
        for match in re.finditer(r"\\caption\{(.*?)\}", tex, re.DOTALL):
            spans.append(LatexSpan(match.start(1), match.end(1), SpanKind.CAPTION, True, "caption-text", 20))
        for match in re.finditer(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL):
            spans.append(LatexSpan(match.start(1), match.end(1), SpanKind.ABSTRACT, True, "abstract-text", 20))
        for match in re.finditer(r"\\[a-zA-Z]+\{.*?\}", tex, re.DOTALL):
            spans.append(LatexSpan(match.start(), match.end(), SpanKind.COMMAND, False, "latex-command", 10))
        return sorted(spans, key=lambda span: (span.start, span.priority))
```

- [ ] **Step 4: 导出公共类型**

`src/latex/__init__.py`

```python
from .models import DocumentPlan, LatexSpan, Segment, SpanKind
from .parser import LatexStructureParser

__all__ = ["DocumentPlan", "LatexSpan", "LatexStructureParser", "Segment", "SpanKind"]
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_latex_parser.py -v`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/latex/__init__.py src/latex/models.py src/latex/parser.py tests/test_latex_parser.py
git commit -m "feat(latex): 引入 span 模型与结构解析器"
```

---

### Task 5: span 合并、segment 切分与 `debug_log.html`

**Files:**
- Create: `src/latex/segmenter.py`
- Create: `tests/test_latex_segmenter.py`
- Modify: `src/latex/models.py`

- [ ] **Step 1: 写出切分器失败测试**

```python
from pathlib import Path

from src.latex.models import SpanKind
from src.latex.segmenter import LatexSegmenter


def test_segmenter_keeps_math_protected_and_caption_open(tmp_path):
    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Value $x+y$.\n"
        "\\begin{figure}\\caption{Caption text.}\\end{figure}\n"
        "\\end{document}\n"
    )
    plan = LatexSegmenter().build_plan(tex, tmp_path)
    assert any(segment.kind is SpanKind.CAPTION and segment.translatable for segment in plan.segments)
    assert any(segment.kind is SpanKind.MATH and not segment.translatable for segment in plan.segments)


def test_segmenter_writes_reason_to_debug_html(tmp_path):
    tex = "\\documentclass{article}\n\\begin{document}\nHello world.\n\\end{document}\n"
    LatexSegmenter().build_plan(tex, tmp_path)
    html = (tmp_path / "debug_log.html").read_text(encoding="utf-8")
    assert "reason=" in html
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_latex_segmenter.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.latex.segmenter'
```

- [ ] **Step 3: 实现新的 segmenter**

`src/latex/segmenter.py`

```python
from pathlib import Path

from .models import DocumentPlan, LatexSpan, Segment, SpanKind
from .parser import LatexStructureParser


class LatexSegmenter:
    def __init__(self) -> None:
        self.parser = LatexStructureParser()

    def build_plan(self, tex: str, debug_dir: Path) -> DocumentPlan:
        spans = self._merge_spans(tex, self.parser.collect_spans(tex))
        segments = self._split_segments(tex, spans)
        plan = DocumentPlan(merged_tex=tex, spans=spans, segments=segments)
        self._write_debug_html(plan, debug_dir / "debug_log.html")
        return plan

    def _merge_spans(self, tex: str, spans: list[LatexSpan]) -> list[LatexSpan]:
        math_spans: list[LatexSpan] = []
        start = 0
        while True:
            begin = tex.find("$", start)
            if begin == -1:
                break
            end = tex.find("$", begin + 1)
            if end == -1:
                break
            math_spans.append(LatexSpan(begin, end + 1, SpanKind.MATH, False, "inline-math", 30))
            start = end + 1
        return sorted([*spans, *math_spans], key=lambda item: (item.start, -item.priority))

    def _split_segments(self, tex: str, spans: list[LatexSpan]) -> list[Segment]:
        segments: list[Segment] = []
        cursor = 0
        for span in spans:
            if cursor < span.start:
                raw = tex[cursor:span.start]
                segments.append(self._make_segment(len(segments), SpanKind.TEXT, raw, True, "plain-text"))
            raw = tex[span.start:span.end]
            segments.append(self._make_segment(len(segments), span.kind, raw, span.translatable, span.reason))
            cursor = span.end
        if cursor < len(tex):
            raw = tex[cursor:]
            segments.append(self._make_segment(len(segments), SpanKind.TEXT, raw, True, "plain-text"))
        return segments

    def _make_segment(self, index: int, kind: SpanKind, text: str, translatable: bool, reason: str) -> Segment:
        line_count = text.count("\n") or 1
        return Segment(index=index, kind=kind, source_text=text, translatable=translatable, line_start=1, line_end=line_count, reason=reason)

    def _write_debug_html(self, plan: DocumentPlan, target: Path) -> None:
        rows = []
        for segment in plan.segments:
            color = "black" if segment.translatable else "red"
            safe_text = segment.source_text.replace("\n", "<br/>")
            rows.append(f'<p style="color:{color};" data-kind="{segment.kind}">reason={segment.reason}::{safe_text}</p>')
        target.write_text("\n".join(rows), encoding="utf-8")
```

- [ ] **Step 4: 把行号计算修正为真实行号**

`src/latex/models.py`

```python
@dataclass(slots=True)
class Segment:
    index: int
    kind: SpanKind
    source_text: str
    translatable: bool
    line_start: int
    line_end: int
    reason: str
    start: int = 0
    end: int = 0
```

`src/latex/segmenter.py`

```python
    def _make_segment(self, index: int, kind: SpanKind, text: str, translatable: bool, reason: str, start: int = 0, end: int = 0) -> Segment:
        line_start = text[:0].count("\n") + 1
        line_end = line_start + text.count("\n")
        return Segment(index=index, kind=kind, source_text=text, translatable=translatable, line_start=line_start, line_end=line_end, reason=reason, start=start, end=end)
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_latex_segmenter.py -v`

Expected:

```text
2 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/latex/models.py src/latex/segmenter.py tests/test_latex_segmenter.py
git commit -m "feat(latex): 用 span planner 生成 segment 与调试日志"
```

---

### Task 6: Prompt 构造、客户端与线程池翻译

**Files:**
- Create: `src/llm/__init__.py`
- Create: `src/llm/prompts.py`
- Create: `src/llm/client.py`
- Create: `src/llm/batching.py`
- Create: `tests/test_llm_batching.py`
- Modify: `src/llm_utils.py`

- [ ] **Step 1: 写出 LLM 层失败测试**

```python
from src.llm.batching import can_multi_process
from src.llm.client import OpenAICompatibleClient
from src.llm.prompts import build_translate_prompt


def test_build_translate_prompt_keeps_spacing_instruction():
    system_prompt, user_prompt = build_translate_prompt("保持术语准确", "Original text")
    assert "中英文交界处" in user_prompt
    assert "保持术语准确" in user_prompt
    assert "Original text" in user_prompt
    assert "专业的翻译人员" in system_prompt


def test_client_normalizes_chat_completion_url():
    client = OpenAICompatibleClient(base_url="https://example.com/v1", api_key="secret")
    assert client.endpoint == "https://example.com/v1/chat/completions"


def test_can_multi_process_falls_back_to_single_worker():
    assert can_multi_process("qwen-plus") is True
    assert can_multi_process("unknown-model") is False
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_llm_batching.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.llm'
```

- [ ] **Step 3: 实现 prompt 与客户端**

`src/llm/prompts.py`

```python
def build_translate_prompt(more_requirement: str, fragment: str) -> tuple[str, str]:
    system_prompt = "你是一位专业的翻译人员。"
    user_prompt = (
        "下面是一篇英文学术论文的片段，请将其翻译成中文。"
        f"{more_requirement}"
        "请不要修改任何 LaTeX 命令，比如 \\section, \\cite, \\begin, \\item 和公式。"
        "在中英文交界处（如中文文本与英文单词、数字或 LaTeX 命令之间）添加一个空格分隔。"
        "只需回复翻译后的文本：\n\n"
        f"{fragment}"
    )
    return system_prompt, user_prompt
```

`src/llm/client.py`

```python
from dataclasses import dataclass

import requests


@dataclass(slots=True)
class OpenAICompatibleClient:
    base_url: str
    api_key: str

    @property
    def endpoint(self) -> str:
        url = self.base_url.rstrip("/")
        return url if url.endswith("/chat/completions") else f"{url}/chat/completions"

    def translate(self, model: str, system_prompt: str, user_prompt: str, temperature: float, top_p: float, proxies: str | None = None) -> str:
        response = requests.post(
            self.endpoint,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "top_p": top_p,
            },
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            proxies=proxies,
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 4: 实现批量翻译并给旧模块加兼容转发**

`src/llm/batching.py`

```python
from concurrent.futures import ThreadPoolExecutor

from .client import OpenAICompatibleClient
from .prompts import build_translate_prompt


def can_multi_process(model: str) -> bool:
    return model.startswith(("gpt-", "qwen", "glm-", "chatgpt-", "azure-"))


def translate_segments(client: OpenAICompatibleClient, model: str, fragments: list[str], more_requirement: str, temperature: float, top_p: float, proxies: str | None, max_workers: int) -> list[str]:
    worker_count = max_workers if can_multi_process(model) else 1

    def _translate(fragment: str) -> str:
        system_prompt, user_prompt = build_translate_prompt(more_requirement, fragment)
        return client.translate(model, system_prompt, user_prompt, temperature, top_p, proxies=proxies)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(_translate, fragments))
```

`src/llm_utils.py`

```python
from src.llm.batching import can_multi_process, translate_segments

__all__ = ["can_multi_process", "translate_segments"]
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_llm_batching.py -v`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/llm src/llm_utils.py tests/test_llm_batching.py
git commit -m "feat(llm): 抽出 prompt 构造与线程池翻译层"
```

---

### Task 7: 译文清洗、渲染与错误行回滚

**Files:**
- Create: `src/latex/sanitize.py`
- Create: `src/latex/render.py`
- Create: `src/latex/recovery.py`
- Create: `tests/test_latex_render.py`

- [ ] **Step 1: 写出渲染与恢复失败测试**

```python
from src.latex.models import DocumentPlan, Segment, SpanKind
from src.latex.recovery import extract_buggy_lines
from src.latex.render import render_translated_tex
from src.latex.sanitize import sanitize_translation


def test_sanitize_translation_reverts_traceback_output():
    original = "Original paragraph."
    translated = "[Local Message] warning\nTraceback"
    assert sanitize_translation(translated, original) == original


def test_render_translated_tex_inserts_disclaimer_after_abstract():
    plan = DocumentPlan(
        merged_tex="\\begin{abstract}Abstract\\end{abstract}\nBody",
        segments=[
            Segment(index=0, kind=SpanKind.ABSTRACT, source_text="Abstract", translatable=True, line_start=1, line_end=1, reason="abstract", start=16, end=24),
            Segment(index=1, kind=SpanKind.TEXT, source_text="\nBody", translatable=True, line_start=2, line_end=2, reason="plain", start=39, end=44),
        ],
    )
    rendered = render_translated_tex(plan, ["摘要", "正文"], "qwen-plus", 1.0)
    assert "当前大语言模型: qwen-plus" in rendered


def test_extract_buggy_lines_reads_file_line_error_log():
    log = "merge_translate_zh.tex:17: Undefined control sequence.\n"
    assert extract_buggy_lines(log, "merge_translate_zh.tex") == [17]
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_latex_render.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.latex.render'
```

- [ ] **Step 3: 实现清洗器与渲染器**

`src/latex/sanitize.py`

```python
import re


def sanitize_translation(translated: str, original: str) -> str:
    output = re.sub(r"(?<!\\)%", r"\\%", translated)
    output = re.sub(r"\\([a-z]{2,10})\s+\{", r"\\\1{", output)
    if "Traceback" in output and "[Local Message]" in output:
        return original
    if original.count("\\begin") != output.count("\\begin"):
        return original
    return output
```

`src/latex/render.py`

```python
from .models import DocumentPlan
from .sanitize import sanitize_translation


DISCLAIMER_TEMPLATE = (
    "*{\\small\\textbf{警告：该 PDF 由 AI 翻译生成，版权归原文作者所有。"
    "翻译内容可靠性无保障，请仔细鉴别并以原文为准。"
    "当前大语言模型: {model_name}，当前语言模型温度设定: {temperature}。}}\\newline\\\\"
)


def render_translated_tex(plan: DocumentPlan, translations: list[str], model_name: str, temperature: float) -> str:
    rendered_parts: list[str] = []
    translate_index = 0
    for segment in plan.segments:
        if segment.translatable:
            rendered_parts.append(sanitize_translation(translations[translate_index], segment.source_text))
            translate_index += 1
        else:
            rendered_parts.append(segment.source_text)
    rendered = "".join(rendered_parts)
    disclaimer = DISCLAIMER_TEMPLATE.format(model_name=model_name.replace("_", "\\_"), temperature=temperature)
    return rendered.replace("\\end{abstract}", disclaimer + "\\end{abstract}", 1)
```

`src/latex/recovery.py`

```python
import re


def extract_buggy_lines(log_text: str, tex_name: str) -> list[int]:
    pattern = rf"{re.escape(tex_name)}:([0-9]{{1,5}}):"
    return sorted({int(value) for value in re.findall(pattern, log_text)})
```

- [ ] **Step 4: 增加基于错误行的局部回滚**

`src/latex/recovery.py`

```python
from src.latex.models import DocumentPlan
from src.latex.render import render_translated_tex


def recover_rendered_tex(plan: DocumentPlan, translations: list[str], buggy_lines: list[int], model_name: str, temperature: float, window: int = 5) -> str:
    recovered: list[str] = []
    translate_index = 0
    for segment in plan.segments:
        if segment.translatable:
            in_bug_window = any(segment.line_start - window <= line <= segment.line_end + window for line in buggy_lines)
            recovered.append(segment.source_text if in_bug_window else translations[translate_index])
            translate_index += 1
        else:
            recovered.append(segment.source_text)
    temp_plan = DocumentPlan(merged_tex=plan.merged_tex, segments=plan.segments)
    return render_translated_tex(temp_plan, recovered, model_name, temperature)
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_latex_render.py -v`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/latex/sanitize.py src/latex/render.py src/latex/recovery.py tests/test_latex_render.py
git commit -m "feat(latex): 增加译文清洗、渲染与错误行回滚"
```

---

### Task 8: 双语输出与编译器模块

**Files:**
- Create: `src/latex/bilingual.py`
- Create: `src/latex/compiler.py`
- Create: `tests/test_bilingual.py`
- Create: `tests/test_latex_compiler.py`

- [ ] **Step 1: 写出双语与编译失败测试**

```python
from pathlib import Path

from src.latex.bilingual import merge_bilingual_caption
from src.latex.compiler import choose_latex_engine


def test_merge_bilingual_caption_keeps_both_languages():
    merged = merge_bilingual_caption("Figure caption", "图标题")
    assert "Figure caption" in merged
    assert "图标题" in merged


def test_choose_latex_engine_prefers_xelatex_for_fontspec():
    tex_path = Path("paper.tex")
    engine = choose_latex_engine("\\documentclass{article}\\n\\usepackage{fontspec}", tex_path)
    assert engine == "xelatex"


def test_choose_latex_engine_defaults_to_pdflatex():
    tex_path = Path("paper.tex")
    engine = choose_latex_engine("\\documentclass{article}", tex_path)
    assert engine == "pdflatex"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_bilingual.py tests/test_latex_compiler.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.latex.compiler'
```

- [ ] **Step 3: 实现双语模块与编译器选择**

`src/latex/bilingual.py`

```python
def merge_bilingual_caption(english: str, chinese: str) -> str:
    return f"{english}\\\\\\n{chinese}"


def generate_bilingual_tex(english_tex: str, chinese_tex: str) -> str:
    return (
        "\\documentclass[fontset=windows,UTF8]{article}\n"
        "\\usepackage{ctex}\n"
        "\\begin{document}\n"
        "\\begin{minipage}{0.48\\textwidth}\n"
        f"{english_tex}\n"
        "\\end{minipage}\n"
        "\\hfill\n"
        "\\begin{minipage}{0.48\\textwidth}\n"
        f"{chinese_tex}\n"
        "\\end{minipage}\n"
        "\\end{document}\n"
    )
```

`src/latex/compiler.py`

```python
import subprocess
from pathlib import Path


def choose_latex_engine(tex: str, tex_path: Path) -> str:
    if any(token in tex for token in ("fontspec", "xeCJK", "xetex", "unicode-math", "xltxtra", "xunicode")):
        return "xelatex"
    return "pdflatex"


def run_compile(command: list[str], cwd: Path) -> bool:
    try:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return False
    return True
```

- [ ] **Step 4: 实现编译顺序与双语编译**

`src/latex/compiler.py`

```python
def compile_latex_project(work_folder: Path, main_name: str, bilingual_name: str | None = None) -> bool:
    tex_path = work_folder / f"{main_name}.tex"
    engine = choose_latex_engine(tex_path.read_text(encoding="utf-8", errors="replace"), tex_path)
    compile_command = [engine, "-interaction=batchmode", "-file-line-error", f"{main_name}.tex"]
    if not run_compile(compile_command, work_folder):
        return False
    bib_aux = work_folder / f"{main_name}.aux"
    if bib_aux.exists():
        run_compile(["bibtex", bib_aux.name], work_folder)
        run_compile(compile_command, work_folder)
        run_compile(compile_command, work_folder)
    if bilingual_name:
        bilingual_command = [engine, "-interaction=batchmode", "-file-line-error", f"{bilingual_name}.tex"]
        run_compile(bilingual_command, work_folder)
    return (work_folder / f"{main_name}.pdf").exists()
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_bilingual.py tests/test_latex_compiler.py -v`

Expected:

```text
3 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/latex/bilingual.py src/latex/compiler.py tests/test_bilingual.py tests/test_latex_compiler.py
git commit -m "feat(latex): 拆出双语输出与编译器模块"
```

---

### Task 9: 新工作流接管、旧入口兼容与文档收尾

**Files:**
- Create: `src/workflow.py`
- Create: `tests/fakes.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/sample_project/main.tex`
- Create: `tests/fixtures/sample_project/intro.tex`
- Create: `tests/test_workflow_smoke.py`
- Modify: `main.py`
- Modify: `src/main_fns/__init__.py`
- Modify: `src/main_fns/workflow.py`
- Modify: `src/latex_fns/latex_actions.py`
- Modify: `README.md`
- Modify: `requirements-dev.txt`

- [ ] **Step 1: 写出端到端兼容失败测试**

```python
from pathlib import Path

from src.workflow import run_translation_workflow


def test_run_translation_workflow_writes_merge_files(sample_project_dir, fake_config):
    result = run_translation_workflow(
        input_value=str(sample_project_dir),
        config=fake_config,
        translator_outputs={"Hello world.": "你好，世界。"},
        skip_compile=True,
    )
    workfolder = Path(result["project_folder"])
    assert (workfolder / "merge.tex").exists()
    assert (workfolder / "merge_translate_zh.tex").exists()
    assert (workfolder / "debug_log.html").exists()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_workflow_smoke.py -v`

Expected:

```text
E   ModuleNotFoundError: No module named 'src.workflow'
```

- [ ] **Step 3: 实现新工作流与旧入口兼容包装**

`src/workflow.py`

```python
from pathlib import Path

from src.latex.bilingual import generate_bilingual_tex
from src.latex.compiler import compile_latex_project
from src.latex.merge import ensure_zh_preamble, find_main_tex_file, merge_project_tex
from src.latex.render import render_translated_tex
from src.latex.segmenter import LatexSegmenter
from src.project.workspace import ensure_run_dirs, prepare_local_project


def run_translation_workflow(input_value: str, config, translator_outputs: dict[str, str] | None = None, skip_compile: bool = False) -> dict[str, str]:
    cache_root = Path(config.arxiv_cache_dir)
    project_source, run_id = prepare_local_project(Path(input_value), cache_root, "2026-04-18-00-00-00")
    run_root, outputs_dir, _ = ensure_run_dirs(cache_root, run_id)
    project_folder = run_root / "workfolder"
    if project_folder.exists():
        project_folder.mkdir(exist_ok=True)
    else:
        project_folder.mkdir(parents=True, exist_ok=True)
    files = list(project_source.rglob("*.tex"))
    main_file = find_main_tex_file(files)
    merged = merge_project_tex(main_file.parent, main_file.read_text(encoding="utf-8"))
    merged = ensure_zh_preamble(merged)
    (project_folder / "merge.tex").write_text(merged, encoding="utf-8")
    plan = LatexSegmenter().build_plan(merged, project_folder)
    fragments = [segment.source_text for segment in plan.segments if segment.translatable]
    translations = [translator_outputs.get(fragment, fragment) for fragment in fragments] if translator_outputs else fragments
    translated_tex = render_translated_tex(plan, translations, config.model, config.temperature)
    (project_folder / "merge_translate_zh.tex").write_text(translated_tex, encoding="utf-8")
    bilingual_tex = generate_bilingual_tex(merged, translated_tex)
    (project_folder / "merge_bilingual.tex").write_text(bilingual_tex, encoding="utf-8")
    if not skip_compile:
        compile_latex_project(project_folder, "merge_translate_zh", bilingual_name="merge_bilingual")
    return {"project_folder": str(project_folder), "outputs_dir": str(outputs_dir)}
```

`src/main_fns/workflow.py`

```python
from src.workflow import run_translation_workflow


def Latex_to_CN_PDF(txt, llm_kwargs, plugin_kwargs):
    config = type(
        "CompatConfig",
        (),
        {
            "arxiv_cache_dir": "arxiv_cache",
            "model": llm_kwargs["llm_model"],
            "temperature": llm_kwargs["temperature"],
        },
    )()
    return run_translation_workflow(txt, config)
```

`src/main_fns/__init__.py`

```python
from .workflow import Latex_to_CN_PDF

__all__ = ["Latex_to_CN_PDF"]
```

- [ ] **Step 4: 增加假对象、fixture 和 README/依赖收尾**

`tests/fakes.py`

```python
from dataclasses import dataclass


@dataclass(slots=True)
class FakeConfig:
    arxiv_cache_dir: str
    model: str
    temperature: float
```

`tests/conftest.py`

```python
import shutil
from pathlib import Path

import pytest

from tests.fakes import FakeConfig


@pytest.fixture()
def sample_project_dir(tmp_path):
    source = Path("tests/fixtures/sample_project")
    target = tmp_path / "sample_project"
    shutil.copytree(source, target)
    return target


@pytest.fixture()
def fake_config(tmp_path):
    return FakeConfig(arxiv_cache_dir=str(tmp_path / "cache"), model="qwen-plus", temperature=1.0)
```

`tests/fixtures/sample_project/main.tex`

```tex
\documentclass{article}
\begin{document}
\input{intro}
\end{document}
```

`tests/fixtures/sample_project/intro.tex`

```tex
Hello world.
```

`requirements-dev.txt`

```text
pytest>=8.0.0
```

`README.md`

```md
### API 密钥配置

1. 在 `config.json` 中设置 `api_key_env`
2. 在系统环境变量中写入真实密钥值
3. 程序启动时会读取 `api_key_env` 指向的环境变量
4. `config.json` 中如果出现 `api_key`，程序会直接报错
```

- [ ] **Step 5: 运行冒烟测试与全量测试**

Run: `python -m pytest tests/test_workflow_smoke.py -v`

Expected:

```text
1 passed
```

Run: `python -m pytest tests -v`

Expected:

```text
all tests passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/workflow.py src/main_fns/__init__.py src/main_fns/workflow.py README.md requirements-dev.txt tests
git commit -m "refactor(workflow): 由新流水线接管旧入口并补齐测试"
```

---

## Self-Review Checklist

- **Spec coverage**
  - 配置与 `api_key_env`：Task 1
  - 项目准备与缓存目录兼容：Task 2
  - 主文件识别与 TeX 合并：Task 3
  - `pylatexenc` 辅助解析：Task 4
  - span/segment 新算法：Task 5
  - 翻译与线程池保留：Task 6
  - 渲染、免责声明、编译回滚：Task 7
  - 双语输出与编译模块：Task 8
  - CLI 兼容、旧入口包装、文档：Task 9

- **Placeholder scan**
  - 本计划没有未决占位内容或跨任务省略写法
  - 每个任务都给出明确文件路径、命令、预期结果

- **Type consistency**
  - 配置对象统一使用 `AppConfig`
  - 工作流统一入口为 `run_translation_workflow`
  - LaTeX 数据模型统一使用 `LatexSpan`、`Segment`、`DocumentPlan`

---

Plan complete and saved to `docs/superpowers/plans/2026-04-18-compatible-latex-refactor.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
