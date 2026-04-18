from __future__ import annotations

import re

from .models import LatexSpan, SpanKind

try:
    from pylatexenc.latexwalker import LatexWalker
except Exception:
    LatexWalker = None


class LatexStructureParser:
    def collect_spans(self, tex: str) -> list[LatexSpan]:
        if LatexWalker is not None:
            try:
                return self._collect_with_latexwalker(tex)
            except Exception:
                return self._collect_with_fallback(tex)
        return self._collect_with_fallback(tex)

    def _collect_with_latexwalker(self, tex: str) -> list[LatexSpan]:
        walker = LatexWalker(tex)
        nodes, *_ = walker.get_latex_nodes(pos=0)
        spans: list[LatexSpan] = []
        self._collect_nodes(nodes, spans)
        if not spans:
            return self._collect_with_fallback(tex)
        return sorted(self._dedupe_spans(spans), key=lambda span: (span.start, span.priority))

    def _collect_with_fallback(self, tex: str) -> list[LatexSpan]:
        spans: list[LatexSpan] = []
        spans.extend(self._collect_abstract_environment(tex))
        spans.extend(self._collect_abstract_macro(tex))
        spans.extend(self._collect_captionof(tex))
        spans.extend(self._collect_caption(tex))
        spans.extend(self._collect_generic_commands(tex))
        return sorted(spans, key=lambda span: (span.start, span.priority))

    def _collect_nodes(self, nodes: list[object] | None, spans: list[LatexSpan]) -> None:
        if not nodes:
            return
        for index, node in enumerate(nodes):
            environment_name = getattr(node, "environmentname", None)
            if environment_name == "abstract":
                abstract_span = self._make_environment_span(node)
                if abstract_span is not None:
                    spans.append(abstract_span)
            macro_name = getattr(node, "macroname", None)
            if macro_name == "caption":
                group = self._get_macro_groups(node, nodes, index, 1)
                if group:
                    spans.append(self._make_group_content_span(group[0], SpanKind.CAPTION, "caption content"))
            elif macro_name == "captionof":
                groups = self._get_macro_groups(node, nodes, index, 2)
                if len(groups) == 2:
                    spans.append(self._make_group_content_span(groups[1], SpanKind.CAPTION, "captionof content"))
            elif macro_name == "abstract":
                group = self._get_macro_groups(node, nodes, index, 1)
                if group:
                    spans.append(self._make_group_content_span(group[0], SpanKind.ABSTRACT, "abstract macro content"))
            elif macro_name:
                groups = self._get_macro_groups(node, nodes, index, 1)
                if groups:
                    spans.append(
                        LatexSpan(
                            start=node.pos,
                            end=max(node.pos + node.len, groups[-1].pos + groups[-1].len),
                            kind=SpanKind.COMMAND,
                            translatable=False,
                            reason="generic command block",
                            priority=100,
                        )
                    )
            self._collect_nodes(getattr(node, "nodelist", None), spans)

    def _get_macro_groups(self, node: object, nodes: list[object], index: int, count: int) -> list[object]:
        groups = self._get_nodeargd_groups(node)
        if len(groups) < count:
            groups.extend(self._find_following_groups(nodes, index, count - len(groups)))
        return groups

    def _get_nodeargd_groups(self, node: object) -> list[object]:
        argnlist = getattr(getattr(node, "nodeargd", None), "argnlist", None) or []
        return [arg for arg in argnlist if self._is_group_node(arg)]

    def _find_following_groups(self, nodes: list[object], start_index: int, count: int) -> list[object]:
        groups: list[object] = []
        for node in nodes[start_index + 1 :]:
            if getattr(node, "chars", None) is not None and str(getattr(node, "chars", "")).isspace():
                continue
            if self._is_group_node(node):
                groups.append(node)
                if len(groups) == count:
                    return groups
                continue
            break
        return groups

    def _is_group_node(self, node: object) -> bool:
        return node is not None and hasattr(node, "nodelist") and hasattr(node, "delimiters")

    def _make_group_content_span(self, group: object, kind: SpanKind, reason: str) -> LatexSpan:
        return LatexSpan(
            start=group.pos + 1,
            end=group.pos + group.len - 1,
            kind=kind,
            translatable=True,
            reason=reason,
            priority=10,
        )

    def _make_environment_span(self, node: object) -> LatexSpan | None:
        children = getattr(node, "nodelist", None) or []
        if not children:
            return None
        start = children[0].pos
        last = children[-1]
        end = last.pos + last.len
        return LatexSpan(
            start=start,
            end=end,
            kind=SpanKind.ABSTRACT,
            translatable=True,
            reason="abstract environment content",
            priority=10,
        )

    def _dedupe_spans(self, spans: list[LatexSpan]) -> list[LatexSpan]:
        unique: list[LatexSpan] = []
        seen: set[tuple[int, int, SpanKind, bool, str, int]] = set()
        for span in spans:
            key = (span.start, span.end, span.kind, span.translatable, span.reason, span.priority)
            if key in seen:
                continue
            seen.add(key)
            unique.append(span)
        return unique

    def _collect_abstract_environment(self, tex: str) -> list[LatexSpan]:
        pattern = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
        return [
            LatexSpan(
                start=match.start(1),
                end=match.end(1),
                kind=SpanKind.ABSTRACT,
                translatable=True,
                reason="abstract environment content",
                priority=10,
            )
            for match in pattern.finditer(tex)
        ]

    def _collect_abstract_macro(self, tex: str) -> list[LatexSpan]:
        return [
            LatexSpan(
                start=content_start,
                end=content_end,
                kind=SpanKind.ABSTRACT,
                translatable=True,
                reason="abstract macro content",
                priority=10,
            )
            for _command_start, content_start, content_end, _command_end in self._find_command_braces(tex, "abstract", 1)
        ]

    def _collect_captionof(self, tex: str) -> list[LatexSpan]:
        return [
            LatexSpan(
                start=content_start,
                end=content_end,
                kind=SpanKind.CAPTION,
                translatable=True,
                reason="captionof content",
                priority=10,
            )
            for _command_start, content_start, content_end, _command_end in self._find_command_braces(
                tex, "captionof", 2
            )
        ]

    def _collect_caption(self, tex: str) -> list[LatexSpan]:
        return [
            LatexSpan(
                start=content_start,
                end=content_end,
                kind=SpanKind.CAPTION,
                translatable=True,
                reason="caption content",
                priority=10,
            )
            for _command_start, content_start, content_end, _command_end in self._find_command_braces(tex, "caption", 1)
        ]

    def _collect_generic_commands(self, tex: str) -> list[LatexSpan]:
        spans: list[LatexSpan] = []
        pattern = re.compile(r"\\([A-Za-z@]+)(?:\s*\[[^\]]*\])?\s*\{")
        for match in pattern.finditer(tex):
            name = match.group(1)
            if name in {"abstract", "caption", "captionof"}:
                continue
            brace_start = match.end() - 1
            brace_end = self._find_matching_brace(tex, brace_start)
            if brace_end == -1:
                continue
            spans.append(
                LatexSpan(
                    start=match.start(),
                    end=brace_end + 1,
                    kind=SpanKind.COMMAND,
                    translatable=False,
                    reason="generic command block",
                    priority=100,
                )
            )
        return spans

    def _find_command_braces(self, tex: str, name: str, brace_count: int) -> list[tuple[int, int, int, int]]:
        matches: list[tuple[int, int, int, int]] = []
        start = 0
        token = f"\\{name}"
        while True:
            command_start = tex.find(token, start)
            if command_start == -1:
                return matches
            cursor = command_start + len(token)
            groups: list[tuple[int, int]] = []
            while len(groups) < brace_count:
                while cursor < len(tex) and tex[cursor].isspace():
                    cursor += 1
                if cursor >= len(tex) or tex[cursor] != "{":
                    break
                brace_end = self._find_matching_brace(tex, cursor)
                if brace_end == -1:
                    break
                groups.append((cursor + 1, brace_end))
                cursor = brace_end + 1
            if len(groups) == brace_count:
                content_start, content_end = groups[-1]
                matches.append((command_start, content_start, content_end, cursor))
                start = cursor
            else:
                start = command_start + len(token)

    def _find_matching_brace(self, tex: str, brace_start: int) -> int:
        depth = 0
        for index in range(brace_start, len(tex)):
            char = tex[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return -1
