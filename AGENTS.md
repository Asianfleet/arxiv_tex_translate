# Repository Guidelines

## Project Structure & Module Organization
`main.py` is the CLI entrypoint for local runs. The only formal implementation path lives under `src/`: `workflow.py` orchestrates the end-to-end flow, `config/` handles config loading, `latex/` contains merge/segment/render/compile logic, `llm/` wraps batch translation clients, and `project/` manages workspace and ArXiv cache flow. Tests live in `tests/`. Reference material belongs in `docs/`, helper scripts in `scripts/`, and generated paper artifacts in `arxiv_cache/`.

## Build, Test, and Development Commands
Install runtime dependencies with `pip install -r requirements.txt` and developer dependencies with `pip install -r requirements-dev.txt`.

Run the tool locally with `python main.py --config config.json --arxiv 1812.10695`.

Run the full test suite with `pytest`. For focused checks, use commands such as `pytest tests/test_workflow_smoke.py` or `pytest tests/test_latex_render.py`.

## Coding Style & Naming Conventions
Use 4-space indentation and keep modules and functions in `snake_case`. Follow the existing Python layout: small focused modules, explicit imports, and short docstrings on public entry points. Add new code only under the formal implementation path (`src/workflow.py`, `src/config`, `src/latex`, `src/llm`, `src/project`). No formatter or linter is pinned in the repo today, so keep style consistent with surrounding files and avoid unrelated refactors.

## Testing Guidelines
Tests use `pytest` and follow the `test_*.py` naming pattern. Place new tests in `tests/` near the area they cover, and prefer targeted unit tests plus one workflow-level regression when behavior crosses modules. When changing translation, rendering, or compile flow, add or update a test before opening a PR.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit style with scoped prefixes, for example `feat(latex_actions): ...`, `refactor(main): ...`, and `docs(README): ...`. Keep subjects short and specific. PRs should describe the user-visible change, list affected commands or config fields, note any cache or PDF output impact, and include sample logs or screenshots only when CLI output or generated artifacts changed materially.

## Security & Configuration Tips
Do not commit real API keys. Keep secrets in environment variables and reference them through `config.json` fields such as `api_key_env`. Treat `arxiv_cache/` as generated output; review it carefully before committing anything from that tree.

## Project Memory
- 唯一正式实现路径是 `main.py`、`src/workflow.py`、`src/config/`、`src/latex/`、`src/llm/`、`src/project/`；不再保留 `src/main_fns/`、`src/latex_fns/`、`src/llm_utils.py`、`src/utils.py` 作为兼容入口。
- `arXiv` 下载、解压、缓存目录与工作区准备统一收口到 `src/project/`；模型能力表、token 上限和流式请求统一收口到 `src/llm/`。
- 配置层禁止恢复 `api_key` 明文字段；继续使用 `api_key_env`，并允许用户自定义环境变量名。
- 修改核心入口时，优先覆盖 `main.py` 与 `src/workflow.py` 的工作流回归，避免模块树收敛后出现无感回退。
