# Remove Legacy Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 `src/main_fns/`、`src/utils.py`、`src/llm_utils.py`、`src/latex_fns/`，把仓库正式实现路径收敛到 `main.py + src/workflow.py + src/config + src/latex + src/llm + src/project`，同时保持 CLI 与输出语义不变。

**Architecture:** 先把 CLI、项目复制语义、测试与文档全部切到新模块树，再物理删除 legacy 文件。任何在删旧过程中发现仍被旧模块独占的能力，都必须先迁入 `src/project/`、`src/latex/` 或 `src/llm/`，绝不保留临时兼容壳。

**Tech Stack:** Python 3.12, pytest, argparse, pathlib, requests, pylatexenc

---

## File Map

- Modify: `main.py`
- Modify: `src/workflow.py`
- Modify: `src/project/workspace.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_config_loader.py`
- Modify: `tests/test_latex_merge.py`
- Modify: `tests/test_llm_batching.py`
- Modify: `tests/test_project_workspace.py`
- Modify: `tests/test_workflow_smoke.py`
- Delete: `src/main_fns/__init__.py`
- Delete: `src/main_fns/arxiv_utils.py`
- Delete: `src/main_fns/file_manager.py`
- Delete: `src/main_fns/prompts.py`
- Delete: `src/main_fns/workflow.py`
- Delete: `src/utils.py`
- Delete: `src/llm_utils.py`
- Delete: `src/latex_fns/latex_actions.py`
- Delete: `src/latex_fns/latex_pickle_io.py`
- Delete: `src/latex_fns/latex_toolbox.py`

### Task 1: 切换 CLI 到新工作流

**Files:**
- Modify: `main.py`
- Modify: `tests/test_config_loader.py`
- Test: `tests/test_config_loader.py`

- [ ] **Step 1: 写失败测试，约束 `main.py` 直接调用 `run_translation_workflow`**

```python
def test_main_calls_run_translation_workflow_directly(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv": "2401.00001",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])

    main_module = importlib.import_module("main")
    captured = {}

    def fake_run_translation_workflow(input_value, config, **kwargs):
        captured["input_value"] = input_value
        captured["config"] = config
        captured["kwargs"] = kwargs
        return {
            "project_folder": "unused",
            "outputs_dir": "unused",
            "success": True,
        }

    monkeypatch.setattr(main_module, "run_translation_workflow", fake_run_translation_workflow)

    main_module.main()

    assert captured["input_value"] == "2401.00001"
    assert captured["config"].arxiv == "2401.00001"
    assert captured["kwargs"] == {}
```

- [ ] **Step 2: 运行单测，确认当前实现失败**

Run: `python -m pytest tests/test_config_loader.py::test_main_calls_run_translation_workflow_directly -v`

Expected: FAIL，错误应显示 `main` 模块不存在 `run_translation_workflow`，或断言未命中，因为当前 CLI 仍走 `src.main_fns.Latex_to_CN_PDF`。

- [ ] **Step 3: 最小实现 `main.py`，直接导入并调用新工作流**

```python
import sys
from loguru import logger

from src.config import ConfigError, RunOptions, load_app_config
from src.workflow import run_translation_workflow


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Arxiv Latex 翻译与编译 (Standalone)")
    parser.add_argument("--config", type=str, default="config.json", help="配置文件路径 (JSON格式)")
    parser.add_argument("--arxiv", type=str, help="arxiv编号或网址，如 1812.10695（覆盖配置文件）")
    parser.add_argument("--model", type=str, help="LLM 模型（覆盖配置文件）")
    parser.add_argument("--advanced_arg", type=str, help="额外的翻译提示词（覆盖配置文件）")
    args = parser.parse_args()

    run_options = RunOptions(
        arxiv=args.arxiv,
        model=args.model,
        advanced_arg=args.advanced_arg,
    )

    try:
        app_config = load_app_config(args.config, overrides=run_options)
    except ConfigError as exc:
        logger.error(str(exc))
        sys.exit(1)

    if not app_config.arxiv:
        logger.error("必须提供 arxiv 编号或网址。请在 config.json 中设置 'arxiv' 或使用 --arxiv 参数。")
        parser.print_help()
        sys.exit(1)

    result = run_translation_workflow(app_config.arxiv, app_config)
    if not result.get("success", False):
        sys.exit(1)
```

- [ ] **Step 4: 收紧 `tests/test_config_loader.py`，删除 legacy 配置桥断言，替换为新 CLI 断言**

```python
from src.config.loader import ConfigError, load_app_config
from src.config.models import RunOptions


def test_main_calls_run_translation_workflow_directly(config_factory, monkeypatch):
    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv": "2401.00001",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])
    main_module = importlib.import_module("main")

    captured = {}

    def fake_run_translation_workflow(input_value, config, **kwargs):
        captured["input_value"] = input_value
        captured["config"] = config
        captured["kwargs"] = kwargs
        return {
            "project_folder": "unused",
            "outputs_dir": "unused",
            "success": True,
        }

    monkeypatch.setattr(main_module, "run_translation_workflow", fake_run_translation_workflow)

    main_module.main()

    assert captured["input_value"] == "2401.00001"
    assert captured["config"].arxiv == "2401.00001"
    assert captured["kwargs"] == {}
```

- [ ] **Step 5: 运行配置测试确认通过**

Run: `python -m pytest tests/test_config_loader.py -v`

Expected: PASS，且 `test_utils_load_config_exposes_legacy_api_key_accessor`、`test_old_module_reads_updated_config_after_import` 这类 legacy 断言已删除，不再出现在收集结果中。

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_config_loader.py
git commit -m "refactor(cli): 直接接入新工作流入口"
```

### Task 2: 把旧 `move_project` 语义迁入 `src/project/workspace.py`

**Files:**
- Modify: `src/project/workspace.py`
- Modify: `src/workflow.py`
- Modify: `tests/test_project_workspace.py`
- Test: `tests/test_project_workspace.py`

- [ ] **Step 1: 写失败测试，约束工作流复制时只忽略顶层 `outputs/logs/workfolder`，保留嵌套同名目录**

```python
def test_copy_project_to_workfolder_skips_only_top_level_runtime_dirs():
    from src.project.workspace import copy_project_to_workfolder

    case_dir = _make_case_dir("copy_project_to_workfolder")
    source = case_dir / "source"
    source.mkdir()
    (source / "main.tex").write_text("content", encoding="utf-8")
    for skipped_name in ("outputs", "logs", "workfolder"):
        skipped_dir = source / skipped_name
        skipped_dir.mkdir()
        (skipped_dir / "top.txt").write_text("skip", encoding="utf-8")
    for nested_name in ("outputs", "logs", "workfolder"):
        nested_dir = source / "chapter1" / nested_name
        nested_dir.mkdir(parents=True)
        (nested_dir / "keep.txt").write_text("keep", encoding="utf-8")

    destination = case_dir / "destination"
    copy_project_to_workfolder(source, destination)

    assert not (destination / "outputs" / "top.txt").exists()
    assert not (destination / "logs" / "top.txt").exists()
    assert not (destination / "workfolder" / "top.txt").exists()
    assert (destination / "chapter1" / "outputs" / "keep.txt").exists()
    assert (destination / "chapter1" / "logs" / "keep.txt").exists()
    assert (destination / "chapter1" / "workfolder" / "keep.txt").exists()
```

- [ ] **Step 2: 运行目标单测，确认当前实现失败**

Run: `python -m pytest tests/test_project_workspace.py::test_copy_project_to_workfolder_skips_only_top_level_runtime_dirs -v`

Expected: FAIL，错误应显示 `copy_project_to_workfolder` 不存在。

- [ ] **Step 3: 在 `src/project/workspace.py` 增加正式复制 helper，并让 `src/workflow.py` 复用它**

```python
def copy_project_to_workfolder(source_project, workfolder):
    source_root = os.fspath(source_project)
    target_root = os.fspath(workfolder)
    top_level_ignored_names = {"__MACOSX", "workfolder", "outputs", "logs"}

    def _ignore_top_level_only(current_dir, names):
        if os.path.normpath(current_dir) != os.path.normpath(source_root):
            return []
        return [name for name in names if name in top_level_ignored_names]

    shutil.copytree(source_root, target_root, ignore=_ignore_top_level_only)
```

```python
from src.project import copy_project_to_workfolder


def _copy_project(source_project: Path, workfolder: Path) -> None:
    copy_project_to_workfolder(source_project, workfolder)
```

- [ ] **Step 4: 用新 helper 改写项目工作区测试，删除对 `src.main_fns.file_manager.move_project` 的依赖**

```python
def test_copy_project_to_workfolder_skips_only_top_level_runtime_dirs():
    from src.project.workspace import copy_project_to_workfolder

    case_dir = _make_case_dir("copy_project_to_workfolder")
    source = case_dir / "source"
    source.mkdir()
    (source / "main.tex").write_text("content", encoding="utf-8")
    for skipped_name in ("outputs", "logs", "workfolder"):
        skipped_dir = source / skipped_name
        skipped_dir.mkdir()
        (skipped_dir / "top.txt").write_text("skip", encoding="utf-8")
    for nested_name in ("outputs", "logs", "workfolder"):
        nested_dir = source / "chapter1" / nested_name
        nested_dir.mkdir(parents=True)
        (nested_dir / "keep.txt").write_text("keep", encoding="utf-8")

    destination = case_dir / "destination"
    copy_project_to_workfolder(source, destination)

    assert not (destination / "outputs" / "top.txt").exists()
    assert not (destination / "logs" / "top.txt").exists()
    assert not (destination / "workfolder" / "top.txt").exists()
    assert (destination / "chapter1" / "outputs" / "keep.txt").exists()
    assert (destination / "chapter1" / "logs" / "keep.txt").exists()
    assert (destination / "chapter1" / "workfolder" / "keep.txt").exists()
```

- [ ] **Step 5: 运行项目工作区测试确认通过**

Run: `python -m pytest tests/test_project_workspace.py -v`

Expected: PASS，且不再收集 `test_move_project_*` 这类 legacy 桥接测试。

- [ ] **Step 6: Commit**

```bash
git add src/project/workspace.py src/workflow.py tests/test_project_workspace.py
git commit -m "refactor(project): 收口项目复制语义到新工作区模块"
```

### Task 3: 清理 legacy 测试并收敛到新模块树

**Files:**
- Modify: `tests/test_latex_merge.py`
- Modify: `tests/test_llm_batching.py`
- Modify: `tests/test_workflow_smoke.py`
- Test: `tests/test_latex_merge.py`
- Test: `tests/test_llm_batching.py`
- Test: `tests/test_workflow_smoke.py`

- [ ] **Step 1: 写失败测试，要求工作流 smoke test 直接对 `main.run_translation_workflow` 新入口建桩，而不是旧包装器**

```python
def test_main_cli_uses_new_workflow_entry(monkeypatch, config_factory):
    import main as main_module

    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv": "demo-input",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    monkeypatch.setattr(main_module.sys, "argv", ["main.py", "--config", str(config_path)])

    captured = {}

    def fake_run_translation_workflow(input_value, config, **kwargs):
        captured["input_value"] = input_value
        captured["config"] = config
        return {
            "project_folder": "unused",
            "outputs_dir": "unused",
            "success": True,
        }

    monkeypatch.setattr(main_module, "run_translation_workflow", fake_run_translation_workflow)

    main_module.main()

    assert captured["input_value"] == "demo-input"
    assert captured["config"].arxiv == "demo-input"
```

- [ ] **Step 2: 运行相关测试，确认现有 legacy 断言需要被移除**

Run: `python -m pytest tests/test_latex_merge.py tests/test_llm_batching.py tests/test_workflow_smoke.py -v`

Expected: FAIL 或收集到大量 legacy 断言，包括：
- `src.latex_fns.latex_toolbox`
- `src.llm_utils`
- `src.main_fns.workflow`

- [ ] **Step 3: 改写 `tests/test_latex_merge.py`，只验证新 `src.latex.merge` API**

```python
def test_find_main_tex_file_ignores_merge_and_scores_body_features():
    from src.latex.merge import find_main_tex_file

    with _case_dir("find_main") as case_dir:
        merge_file = _write(
            case_dir / "merge_main.tex",
            r"\documentclass{article}" "\n" r"\begin{document}merged\end{document}",
        )
        template_file = _write(
            case_dir / "template.tex",
            (
                r"\documentclass{article}"
                "\n"
                r"\begin{document}"
                "\n"
                r"\LaTeX manuscript Guidelines for reviewers and blind review citations"
                "\n"
                r"\end{document}"
            ),
        )
        main_file = _write(
            case_dir / "main.tex",
            (
                r"\documentclass{article}"
                "\n"
                r"\input{sections/intro}"
                "\n"
                r"See \ref{sec:intro} and \cite{demo}."
            ),
        )

        selected = find_main_tex_file([merge_file, template_file, main_file])

        assert selected == main_file
```

- [ ] **Step 4: 改写 `tests/test_llm_batching.py` 与 `tests/test_workflow_smoke.py`，删除 legacy 导入与包装器断言**

```python
def test_can_multi_process_consults_model_info_table(monkeypatch):
    from src.llm import batching
    from src.llm.model_info import model_info

    monkeypatch.setitem(model_info, "custom-parallel", {"can_multi_thread": True})
    monkeypatch.setitem(model_info, "qwen-serial", {"can_multi_thread": False})

    assert batching.can_multi_process("custom-parallel") is True
    assert batching.can_multi_process("qwen-serial") is False
```

```python
def test_llm_package_exposes_supported_exports_only():
    import src.llm as llm

    assert callable(llm.OpenAICompatibleClient)
    assert callable(llm.build_translate_prompt)
    assert callable(llm.can_multi_process)
    assert callable(llm.translate_segments)
    assert "TranslatePrompt" not in getattr(llm, "__all__", [])
    assert not hasattr(llm, "TranslatePrompt")
```

```python
def test_main_cli_uses_new_workflow_entry(monkeypatch, config_factory):
    import main as main_module

    config_path = config_factory(
        {
            "api_key_env": "MY_TRANSLATOR_KEY",
            "arxiv": "demo-input",
        },
    )
    monkeypatch.setenv("MY_TRANSLATOR_KEY", "secret-token")
    monkeypatch.setattr(main_module.sys, "argv", ["main.py", "--config", str(config_path)])

    captured = {}

    def fake_run_translation_workflow(input_value, config, **kwargs):
        captured["input_value"] = input_value
        captured["config"] = config
        return {
            "project_folder": "unused",
            "outputs_dir": "unused",
            "success": True,
        }

    monkeypatch.setattr(main_module, "run_translation_workflow", fake_run_translation_workflow)

    main_module.main()

    assert captured["input_value"] == "demo-input"
    assert captured["config"].arxiv == "demo-input"
```

- [ ] **Step 5: 运行三组测试确认通过**

Run: `python -m pytest tests/test_latex_merge.py tests/test_llm_batching.py tests/test_workflow_smoke.py -v`

Expected: PASS，且不再收集任何来自 `src.latex_fns`、`src.llm_utils`、`src.main_fns.workflow` 的兼容测试。

- [ ] **Step 6: Commit**

```bash
git add tests/test_latex_merge.py tests/test_llm_batching.py tests/test_workflow_smoke.py
git commit -m "test(core): 移除 legacy 路径断言"
```

### Task 4: 删除 legacy 模块并收敛文档

**Files:**
- Delete: `src/main_fns/__init__.py`
- Delete: `src/main_fns/arxiv_utils.py`
- Delete: `src/main_fns/file_manager.py`
- Delete: `src/main_fns/prompts.py`
- Delete: `src/main_fns/workflow.py`
- Delete: `src/utils.py`
- Delete: `src/llm_utils.py`
- Delete: `src/latex_fns/latex_actions.py`
- Delete: `src/latex_fns/latex_pickle_io.py`
- Delete: `src/latex_fns/latex_toolbox.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `README.md`

- [ ] **Step 1: 写失败检查，要求仓库内不再存在 legacy 引用**

Run: `git grep -n "src\\.main_fns\\|src\\.latex_fns\\|src\\.llm_utils\\|src\\.utils" -- main.py src tests README.md AGENTS.md`

Expected: 当前仍能查到 legacy 路径引用。

- [ ] **Step 2: 删除 legacy 模块文件**

```text
src/main_fns/__init__.py
src/main_fns/arxiv_utils.py
src/main_fns/file_manager.py
src/main_fns/prompts.py
src/main_fns/workflow.py
src/utils.py
src/llm_utils.py
src/latex_fns/latex_actions.py
src/latex_fns/latex_pickle_io.py
src/latex_fns/latex_toolbox.py
```

- [ ] **Step 3: 更新 README，只描述新模块树**

```markdown
## 项目结构

```
.
├── main.py
├── src/
│   ├── workflow.py
│   ├── config/
│   ├── latex/
│   ├── llm/
│   └── project/
└── tests/
```

当前仓库只保留一套正式实现路径：`main.py`、`src/workflow.py`、`src/config/`、`src/latex/`、`src/llm/`、`src/project/`。
```

- [ ] **Step 4: 更新 AGENTS.md，把“新模块树是唯一正式实现”写成项目记忆**

```markdown
## Project Memory
- 新核心实现只放在 `src/workflow.py`、`src/latex/`、`src/llm/`、`src/project/`。
- 不再保留 `src/main_fns/`、`src/utils.py`、`src/llm_utils.py`、`src/latex_fns/` 作为兼容入口。
- 修改 CLI、测试或文档时，不允许重新引入 legacy 导入路径。
```

- [ ] **Step 5: 再跑 legacy 引用扫描，确认全部清零**

Run: `git grep -n "src\\.main_fns\\|src\\.latex_fns\\|src\\.llm_utils\\|src\\.utils" -- main.py src tests README.md AGENTS.md`

Expected: 无输出，退出码为 1。

- [ ] **Step 6: Commit**

```bash
git add README.md AGENTS.md src tests
git commit -m "refactor(core): 删除 legacy 模块树"
```

### Task 5: 做全量回归与完成检查

**Files:**
- Modify: `docs/superpowers/specs/2026-04-21-remove-legacy-logic-design.md`
- Test: `tests/`

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests -v`

Expected: 全量 PASS。

- [ ] **Step 2: 单独验证两条高风险分支**

Run: `python -m pytest tests/test_project_workspace.py tests/test_workflow_smoke.py -v`

Expected: PASS，并覆盖：
- 本地项目路径
- arXiv 缓存命中

- [ ] **Step 3: 运行最终删除检查**

Run: `git grep -n "src\\.main_fns\\|src\\.latex_fns\\|src\\.llm_utils\\|src\\.utils" -- main.py src tests README.md AGENTS.md`

Expected: 无输出，退出码 1。

- [ ] **Step 4: 记录 spec 已完成实施**

```markdown
实施完成后，将 spec 中与“兼容包装器仍保留”相冲突的表述删净，并保持：
- 目标架构与最终代码一致
- 验收标准与最终验证命令一致
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-04-21-remove-legacy-logic-design.md
git commit -m "docs(spec): 同步 legacy 删除落地结果"
```
