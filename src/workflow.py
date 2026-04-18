from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.latex.bilingual import generate_bilingual_tex
from src.latex.compiler import compile_latex_project
from src.latex.merge import ensure_zh_preamble, find_main_tex_file, merge_project_tex
from src.latex.render import render_translated_tex
from src.latex.segmenter import LatexSegmenter
from src.llm import OpenAICompatibleClient, translate_segments
from src.project import download_arxiv_source, resolve_extracted_project_root


@dataclass(slots=True)
class _ResolvedSource:
    project_path: Path
    arxiv_id: str | None = None
    cached_pdf: Path | None = None


def run_translation_workflow(
    input_value: str,
    config,
    translator_outputs: dict[str, str] | None = None,
    skip_compile: bool = False,
    client=None,
) -> dict:
    advanced_arg, allow_cache = _parse_advanced_arg(_get_config_value(config, "advanced_arg", ""))
    source = _resolve_source_project(
        input_value,
        allow_cache=allow_cache,
        cache_dir=_get_config_value(config, "arxiv_cache_dir", "arxiv_cache"),
        proxies=_normalize_proxies(_get_config_value(config, "proxies", None)),
    )
    run_root = _resolve_run_root(config, source)
    workfolder, outputs_dir, translation_dir = _prepare_run_dirs(run_root, source)
    if source.cached_pdf is not None:
        translate_target = translation_dir / "translate_zh.pdf"
        if source.cached_pdf.exists() and source.cached_pdf.resolve() != translate_target.resolve():
            shutil.copy2(source.cached_pdf, translate_target)
        return {
            "project_folder": str(workfolder),
            "outputs_dir": str(outputs_dir),
            "success": True,
        }

    _copy_project(source.project_path, workfolder)

    tex_files = list(workfolder.rglob("*.tex"))
    if not tex_files:
        raise RuntimeError(f"找不到任何 .tex 文件: {workfolder}")

    main_tex = find_main_tex_file(tex_files)
    merged_tex = ensure_zh_preamble(merge_project_tex(workfolder, main_tex))
    merge_path = workfolder / "merge.tex"
    merge_path.write_text(merged_tex, encoding="utf-8")

    plan = LatexSegmenter().build_plan(merged_tex, workfolder)
    fragments = [segment.source_text for segment in plan.segments if segment.translatable]
    translations = _resolve_translations(
        fragments=fragments,
        translator_outputs=translator_outputs,
        config=config,
        advanced_arg=advanced_arg,
        client=client,
    )

    model_name = _get_model_name(config)
    temperature = float(_get_llm_value(config, "temperature", 1.0))
    translated_tex = render_translated_tex(
        plan,
        translations,
        model_name=model_name,
        temperature=temperature,
    )
    translated_path = workfolder / "merge_translate_zh.tex"
    translated_path.write_text(translated_tex, encoding="utf-8")

    bilingual_tex = generate_bilingual_tex(merged_tex, translated_tex)
    bilingual_path = workfolder / "merge_bilingual.tex"
    bilingual_path.write_text(bilingual_tex, encoding="utf-8")

    success = True
    if not skip_compile:
        success = compile_latex_project(workfolder, "merge_translate_zh", bilingual_name="merge_bilingual")
        _copy_generated_pdfs(workfolder, outputs_dir)
        _sync_legacy_translation_outputs(workfolder, translation_dir)

    return {
        "project_folder": str(workfolder),
        "outputs_dir": str(outputs_dir),
        "success": bool(success),
    }


def _parse_advanced_arg(advanced_arg: str) -> tuple[str, bool]:
    cleaned = (advanced_arg or "").strip()
    if "--no-cache" not in cleaned:
        return cleaned, True
    return cleaned.replace("--no-cache", "").strip(), False


def _resolve_source_project(
    input_value: str,
    allow_cache: bool,
    cache_dir: str,
    proxies,
) -> _ResolvedSource:
    candidate = Path(input_value).expanduser()
    if candidate.exists():
        return _ResolvedSource(_normalize_local_project(candidate))

    resolved, arxiv_id = download_arxiv_source(
        input_value,
        cache_dir=cache_dir,
        allow_cache=allow_cache,
        proxies=proxies,
    )
    if not resolved:
        raise RuntimeError(f"无法处理输入: {input_value}")

    resolved_path = Path(resolved)
    if resolved_path.suffix.lower() == ".pdf":
        return _ResolvedSource(resolved_path.parent, arxiv_id=arxiv_id, cached_pdf=resolved_path)
    return _ResolvedSource(
        resolve_extracted_project_root(resolved_path),
        arxiv_id=arxiv_id,
    )


def _resolve_run_root(config, source: _ResolvedSource) -> Path:
    cache_dir = Path(_get_config_value(config, "arxiv_cache_dir", "arxiv_cache"))
    if source.arxiv_id:
        return cache_dir / source.arxiv_id
    return _create_local_run_root(cache_dir)


def _normalize_local_project(candidate: Path) -> Path:
    if candidate.is_file():
        return candidate.parent
    return candidate


def _create_local_run_root(cache_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_root = cache_dir / "local_cache" / timestamp
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def _prepare_run_dirs(run_root: Path, source: _ResolvedSource) -> tuple[Path, Path, Path]:
    workfolder = run_root / "workfolder"
    outputs_dir = run_root / "outputs"
    translation_dir = run_root / "translation"
    if workfolder.exists():
        if source.cached_pdf is None:
            shutil.rmtree(workfolder)
    elif source.cached_pdf is not None:
        workfolder.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    translation_dir.mkdir(parents=True, exist_ok=True)
    return workfolder, outputs_dir, translation_dir


def _copy_project(source_project: Path, workfolder: Path) -> None:
    ignored_names = {"__MACOSX", "workfolder", "outputs", "logs"}

    def _ignore(current_dir: str, names: list[str]) -> list[str]:
        return [name for name in names if name in ignored_names]

    shutil.copytree(source_project, workfolder, ignore=_ignore)


def _resolve_translations(
    *,
    fragments: list[str],
    translator_outputs: dict[str, str] | None,
    config,
    advanced_arg: str,
    client,
) -> list[str]:
    if translator_outputs is not None:
        return [_lookup_translation(translator_outputs, fragment) for fragment in fragments]

    effective_client = client or OpenAICompatibleClient(
        base_url=_get_llm_value(config, "llm_url", ""),
        api_key=_resolve_api_key(config),
    )
    return translate_segments(
        client=effective_client,
        model=_get_model_name(config),
        fragments=fragments,
        more_requirement=advanced_arg,
        temperature=float(_get_llm_value(config, "temperature", 1.0)),
        top_p=float(_get_llm_value(config, "top_p", 1.0)),
        proxies=_normalize_proxies(_get_config_value(config, "proxies", None)),
        max_workers=int(_get_config_value(config, "default_worker_num", 8)),
    )


def _lookup_translation(translator_outputs: dict[str, str], fragment: str) -> str:
    if fragment in translator_outputs:
        return translator_outputs[fragment]
    stripped = fragment.strip()
    if not stripped:
        return fragment
    if stripped in translator_outputs:
        return translator_outputs[stripped]
    replaced = fragment
    changed = False
    for source_text, translated_text in sorted(translator_outputs.items(), key=lambda item: len(item[0]), reverse=True):
        key = source_text.strip()
        if source_text and source_text in replaced:
            replaced = replaced.replace(source_text, translated_text)
            changed = True
        elif key and key in replaced:
            replaced = replaced.replace(key, translated_text)
            changed = True
    if changed:
        return replaced
    return fragment


def _copy_generated_pdfs(workfolder: Path, outputs_dir: Path) -> None:
    for pdf_name in ("merge_translate_zh.pdf", "merge_bilingual.pdf"):
        pdf_path = workfolder / pdf_name
        if pdf_path.exists():
            shutil.copy2(pdf_path, outputs_dir / pdf_name)


def _sync_legacy_translation_outputs(workfolder: Path, translation_dir: Path) -> None:
    translate_pdf = workfolder / "merge_translate_zh.pdf"
    if translate_pdf.exists():
        shutil.copy2(translate_pdf, translation_dir / "translate_zh.pdf")

    bilingual_pdf = workfolder / "merge_bilingual.pdf"
    if bilingual_pdf.exists():
        shutil.copy2(bilingual_pdf, translation_dir / "merge_bilingual.pdf")


def _get_model_name(config) -> str:
    return str(_get_config_value(config, "model", _get_config_value(config, "llm_model", "")))


def _get_config_value(config, field_name: str, default):
    return getattr(config, field_name, default)


def _get_llm_value(config, field_name: str, default):
    llm_config = getattr(config, "llm", None)
    if llm_config is not None and hasattr(llm_config, field_name):
        return getattr(llm_config, field_name)
    return getattr(config, field_name, default)


def _resolve_api_key(config) -> str:
    api_key = str(_get_llm_value(config, "api_key", "") or "").strip()
    if api_key:
        return api_key

    api_key_env = str(_get_llm_value(config, "api_key_env", "") or "").strip()
    if api_key_env:
        return os.environ.get(api_key_env, "").strip()
    return ""


def _normalize_proxies(proxies):
    if proxies in (None, "", {}):
        return None
    if isinstance(proxies, dict):
        return proxies
    if isinstance(proxies, str):
        return {"http": proxies, "https": proxies}
    return proxies
