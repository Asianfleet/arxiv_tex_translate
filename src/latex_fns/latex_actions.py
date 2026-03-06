import os
import re
import shutil
import numpy as np
from loguru import logger
from .latex_toolbox import PRESERVE, TRANSFORM
from .latex_toolbox import set_forbidden_text, set_forbidden_text_begin_end, set_forbidden_text_careful_brace
from .latex_toolbox import reverse_forbidden_text_careful_brace, reverse_forbidden_text, convert_to_linklist, post_process
from .latex_toolbox import fix_content, find_main_tex_file, merge_tex_files, compile_latex_with_timeout
from .latex_toolbox import find_title_and_abs
from .latex_pickle_io import objdump, objload


pj = os.path.join


def split_subprocess(txt, project_folder, return_dict):
    """
    将LaTeX文件分解为链表，每个节点使用保留标志来指示是否应由GPT处理。

    Args:
        txt: LaTeX文件内容字符串
        project_folder: 项目文件夹路径
        return_dict: 用于返回结果的多进程字典

    Returns:
        包含处理结果的字典，包含nodes和segment_parts_for_gpt
    """
    text = txt
    mask = np.zeros(len(txt), dtype=np.uint8) + TRANSFORM
    def apply_forbidden(pattern, flags=0):
        """统一执行保留标记，减少重复代码。"""
        nonlocal text, mask
        text, mask = set_forbidden_text(text, mask, pattern, flags)

    # 吸收title与作者以上的部分
    for pattern in [r"^(.*?)\\maketitle", r"^(.*?)\\begin{document}"]:
        apply_forbidden(pattern, re.DOTALL)
    # 吸收iffalse注释
    apply_forbidden(r"\\iffalse(.*?)\\fi", re.DOTALL)
    # 吸收在42行以内的begin-end组合
    text, mask = set_forbidden_text_begin_end(text, mask, r"\\begin\{([a-z\*]*)\}(.*?)\\end\{\1\}", re.DOTALL, limit_n_lines=42)
    # 吸收匿名公式
    apply_forbidden([r"\$\$([^$]+)\$\$", r"\\\[.*?\\\]"], re.DOTALL)
    # 吸收其他杂项
    forbidden_patterns = [
        ([r"\\section\{(.*?)\}", r"\\section\*\{(.*?)\}", r"\\subsection\{(.*?)\}", r"\\subsubsection\{(.*?)\}"], 0),
        ([r"\\bibliography\{(.*?)\}", r"\\bibliographystyle\{(.*?)\}"], 0),
        (r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", re.DOTALL),
        (r"\\begin\{lstlisting\}(.*?)\\end\{lstlisting\}", re.DOTALL),
        (r"\\begin\{wraptable\}(.*?)\\end\{wraptable\}", re.DOTALL),
        (r"\\begin\{algorithm\}(.*?)\\end\{algorithm\}", re.DOTALL),
        ([r"\\begin\{wrapfigure\}(.*?)\\end\{wrapfigure\}", r"\\begin\{wrapfigure\*\}(.*?)\\end\{wrapfigure\*\}"], re.DOTALL),
        ([r"\\begin\{figure\}(.*?)\\end\{figure\}", r"\\begin\{figure\*\}(.*?)\\end\{figure\*\}"], re.DOTALL),
        ([r"\\begin\{multline\}(.*?)\\end\{multline\}", r"\\begin\{multline\*\}(.*?)\\end\{multline\*\}"], re.DOTALL),
        ([r"\\begin\{table\}(.*?)\\end\{table\}", r"\\begin\{table\*\}(.*?)\\end\{table\*\}"], re.DOTALL),
        ([r"\\begin\{minipage\}(.*?)\\end\{minipage\}", r"\\begin\{minipage\*\}(.*?)\\end\{minipage\*\}"], re.DOTALL),
        ([r"\\begin\{align\*\}(.*?)\\end\{align\*\}", r"\\begin\{align\}(.*?)\\end\{align\}"], re.DOTALL),
        ([r"\\begin\{equation\}(.*?)\\end\{equation\}", r"\\begin\{equation\*\}(.*?)\\end\{equation\*\}"], re.DOTALL),
        ([r"\\includepdf\[(.*?)\]\{(.*?)\}", r"\\clearpage", r"\\newpage", r"\\appendix", r"\\tableofcontents", r"\\include\{(.*?)\}"], 0),
        ([r"\\vspace\{(.*?)\}", r"\\hspace\{(.*?)\}", r"\\label\{(.*?)\}", r"\\begin\{(.*?)\}", r"\\end\{(.*?)\}", r"\\item "], 0),
    ]
    for pattern, flags in forbidden_patterns:
        apply_forbidden(pattern, flags)
    text, mask = set_forbidden_text_careful_brace(text, mask, r"\\hl\{(.*?)\}", re.DOTALL)
    # reverse 操作必须放在最后
    text, mask = reverse_forbidden_text_careful_brace(text, mask, r"\\caption\{(.*?)\}", re.DOTALL, forbid_wrapper=True)
    text, mask = reverse_forbidden_text_careful_brace(text, mask, r"\\abstract\{(.*?)\}", re.DOTALL, forbid_wrapper=True)
    text, mask = reverse_forbidden_text(text, mask, r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL, forbid_wrapper=True)
    root = convert_to_linklist(text, mask)

    # 最后一步处理，增强稳健性
    root = post_process(root)

    # 输出html调试文件，用红色标注处保留区（PRESERVE），用黑色标注转换区（TRANSFORM）
    with open(pj(project_folder, 'debug_log.html'), 'w', encoding='utf8') as f:
        segment_parts_for_gpt = []
        nodes = []
        node = root
        while True:
            nodes.append(node)
            show_html = node.string.replace('\n','<br/>')
            if not node.preserve:
                segment_parts_for_gpt.append(node.string)
                f.write(f'<p style="color:black;">#{node.range}{show_html}#</p>')
            else:
                f.write(f'<p style="color:red;">{show_html}</p>')
            node = node.next
            if node is None: break

    for n in nodes: n.next = None   # break
    return_dict['nodes'] = nodes
    return_dict['segment_parts_for_gpt'] = segment_parts_for_gpt
    return return_dict


class BilingualTexMerger:
    """中英对照 LaTeX 合并器。"""

    @staticmethod
    def _find_first_match_position(text, patterns, start=0):
        """返回多个正则中最早匹配的位置。"""
        positions = []
        for pattern, flags in patterns:
            match = re.search(pattern, text[start:], flags)
            if match:
                positions.append(start + match.start())
        return min(positions) if positions else None

    @staticmethod
    def _normalize_bilingual_root(root):
        """
        对中英对照切分结果做轻量归一化。

        与 `post_process` 不同，这里不会根据段落长度强行转为保留区，
        以避免中英文长度差异导致分段数量不一致。
        """
        node = root
        while True:
            if len(node.string.strip()) == 0:
                node.preserve = True
            node = node.next
            if node is None:
                break

        node = root
        while True:
            if node.next and node.preserve and node.next.preserve:
                node.string += node.next.string
                node.next = node.next.next
                continue
            node = node.next
            if node is None:
                break

        node = root
        prev_node = None
        while True:
            if not node.preserve:
                lstriped_ = node.string.lstrip().lstrip("\n")
                if (
                    (prev_node is not None)
                    and prev_node.preserve
                    and (len(lstriped_) != len(node.string))
                ):
                    prev_node.string += node.string[: -len(lstriped_)]
                    node.string = lstriped_
                rstriped_ = node.string.rstrip().rstrip("\n")
                if (
                    (node.next is not None)
                    and node.next.preserve
                    and (len(rstriped_) != len(node.string))
                ):
                    node.next.string = node.string[len(rstriped_) :] + node.next.string
                    node.string = rstriped_
            prev_node = node
            node = node.next
            if node is None:
                break

        return root

    @classmethod
    def split_bilingual_body_subprocess(cls, txt, return_dict):
        """
        仅切分正文段落，用于生成中英对照版本。

        规则：
        1. 仅处理首个 `\\section` 之后到附录/参考文献/致谢之前的正文
        2. 图表、公式、标题、caption、摘要等保持为保留区
        3. 只把普通正文段落作为可转换区域
        """
        text = txt
        mask = np.zeros(len(txt), dtype=np.uint8) + PRESERVE

        body_start = cls._find_first_match_position(
            text,
            [
                (r"\\section\*\{", 0),
                (r"\\section\{", 0),
            ],
        )
        if body_start is None:
            raise ValueError("无法在 LaTeX 文档中找到正文起始 section。")

        body_end = cls._find_first_match_position(
            text,
            [
                (r"\\appendix\b", 0),
                (r"\\bibliography\{", 0),
                (r"\\begin\{thebibliography\}", 0),
                (r"\\section\*\{Acknowledg?ements\}", re.IGNORECASE),
                (r"\\section\*\{Author Contributions\}", re.IGNORECASE),
                (r"\\section\*\{References\}", re.IGNORECASE),
            ],
            start=body_start,
        )
        if body_end is None:
            body_end = len(text)

        mask[body_start:body_end] = TRANSFORM

        def apply_forbidden(pattern, flags=0):
            nonlocal text, mask
            text, mask = set_forbidden_text(text, mask, pattern, flags)

        text, mask = set_forbidden_text_begin_end(
            text,
            mask,
            r"\\begin\{([a-zA-Z\*]+)\}(.*?)\\end\{\1\}",
            re.DOTALL,
            limit_n_lines=42,
        )

        forbidden_patterns = [
            (r"^\{\s*$.*?^\}\s*$", re.DOTALL | re.MULTILINE),
            ([r"\\section\{(.*?)\}", r"\\section\*\{(.*?)\}", r"\\subsection\{(.*?)\}", r"\\subsection\*\{(.*?)\}", r"\\subsubsection\{(.*?)\}", r"\\subsubsection\*\{(.*?)\}"], 0),
            (r"\\begin\{[a-zA-Z\*]*abstract[a-zA-Z\*]*\}(.*?)\\end\{[a-zA-Z\*]*abstract[a-zA-Z\*]*\}", re.DOTALL),
            (r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", re.DOTALL),
            (r"\\begin\{lstlisting\}(.*?)\\end\{lstlisting\}", re.DOTALL),
            (r"\\begin\{algorithm\}(.*?)\\end\{algorithm\}", re.DOTALL),
            (r"\\begin\{algorithm\*\}(.*?)\\end\{algorithm\*\}", re.DOTALL),
            (r"\\begin\{wraptable\}(.*?)\\end\{wraptable\}", re.DOTALL),
            (r"\\begin\{wrapfigure\}(.*?)\\end\{wrapfigure\}", re.DOTALL),
            (r"\\begin\{wrapfigure\*\}(.*?)\\end\{wrapfigure\*\}", re.DOTALL),
            (r"\\begin\{figure\}(.*?)\\end\{figure\}", re.DOTALL),
            (r"\\begin\{figure\*\}(.*?)\\end\{figure\*\}", re.DOTALL),
            (r"\\begin\{table\}(.*?)\\end\{table\}", re.DOTALL),
            (r"\\begin\{table\*\}(.*?)\\end\{table\*\}", re.DOTALL),
            (r"\\begin\{tabular\}(.*?)\\end\{tabular\}", re.DOTALL),
            (r"\\begin\{tabularx\}(.*?)\\end\{tabularx\}", re.DOTALL),
            (r"\\begin\{longtable\}(.*?)\\end\{longtable\}", re.DOTALL),
            (r"\\begin\{minipage\}(.*?)\\end\{minipage\}", re.DOTALL),
            (r"\\begin\{multline\}(.*?)\\end\{multline\}", re.DOTALL),
            (r"\\begin\{multline\*\}(.*?)\\end\{multline\*\}", re.DOTALL),
            (r"\\begin\{align\}(.*?)\\end\{align\}", re.DOTALL),
            (r"\\begin\{align\*\}(.*?)\\end\{align\*\}", re.DOTALL),
            (r"\\begin\{equation\}(.*?)\\end\{equation\}", re.DOTALL),
            (r"\\begin\{equation\*\}(.*?)\\end\{equation\*\}", re.DOTALL),
            ([r"\$\$([^$]+)\$\$", r"\\\[.*?\\\]"], re.DOTALL),
            ([r"\\bibliography\{(.*?)\}", r"\\bibliographystyle\{(.*?)\}", r"\\appendix", r"\\tableofcontents", r"\\clearpage", r"\\newpage"], 0),
            ([r"\\vspace\{(.*?)\}", r"\\hspace\{(.*?)\}", r"\\label\{(.*?)\}", r"\\begin\{(.*?)\}", r"\\end\{(.*?)\}", r"\\item "], 0),
        ]
        for pattern, flags in forbidden_patterns:
            apply_forbidden(pattern, flags)

        text, mask = set_forbidden_text_careful_brace(
            text, mask, r"\\caption\{(.*?)\}", re.DOTALL
        )
        text, mask = set_forbidden_text_careful_brace(
            text, mask, r"\\captionof\{(.*?)\}\{", re.DOTALL
        )

        root = convert_to_linklist(text, mask)
        root = cls._normalize_bilingual_root(root)

        nodes = []
        segment_parts_for_bilingual = []
        node = root
        while True:
            nodes.append(node)
            if not node.preserve:
                segment_parts_for_bilingual.append(node.string)
            node = node.next
            if node is None:
                break

        for n in nodes:
            n.next = None

        return_dict["nodes"] = nodes
        return_dict["segment_parts_for_bilingual"] = segment_parts_for_bilingual
        return return_dict

    @classmethod
    def split_bilingual_body(cls, txt):
        """同步切分正文段落，返回节点和正文片段。"""
        return_dict = {}
        cls.split_bilingual_body_subprocess(txt, return_dict)
        return return_dict["nodes"], return_dict["segment_parts_for_bilingual"]

    @staticmethod
    def _deduplicate_preamble_usepackages(tex_content):
        """
        对导言区中完全相同的 `\\usepackage` 行做去重。

        只处理 `\\begin{document}` 之前的内容，且仅移除字面完全相同的包声明，
        避免误伤带不同选项或确有顺序依赖的语句。
        """
        begin_doc_match = re.search(r"\\begin\{document\}", tex_content)
        if not begin_doc_match:
            return tex_content

        preamble = tex_content[: begin_doc_match.start()]
        body = tex_content[begin_doc_match.start() :]
        deduped_lines = []
        seen_usepackages = set()

        for line in preamble.splitlines(keepends=True):
            normalized = line.strip()
            if normalized.startswith(r"\usepackage"):
                if normalized in seen_usepackages:
                    continue
                seen_usepackages.add(normalized)
            deduped_lines.append(line)

        return "".join(deduped_lines) + body

    @classmethod
    def ensure_bilingual_preamble(cls, tex_content, color_name="bilingualzhcolor"):
        """为中英对照文档注入颜色定义。"""
        tex_content = cls._deduplicate_preamble_usepackages(tex_content)

        if f"\\definecolor{{{color_name}}}" in tex_content:
            return tex_content

        if "{xcolor}" not in tex_content:
            pattern = re.compile(r"\\documentclass.*\n")
            match = pattern.search(tex_content)
            if not match:
                raise ValueError("无法在 LaTeX 文档中找到 documentclass。")
            position = match.end()
            tex_content = (
                tex_content[:position]
                + "\\usepackage{xcolor}\n"
                + tex_content[position:]
            )

        color_def = f"\\definecolor{{{color_name}}}{{RGB}}{{128,128,128}}\n"
        begin_doc_match = re.search(r"\\begin\{document\}", tex_content)
        if begin_doc_match:
            position = begin_doc_match.start()
            return tex_content[:position] + color_def + tex_content[position:]
        return tex_content + "\n" + color_def

    @staticmethod
    def _split_tex_paragraphs(text):
        """按 LaTeX 空行拆分段落。"""
        return [p.strip() for p in re.split(r"\n\s*\n+", text.strip()) if p.strip()]

    @staticmethod
    def _can_paragraph_split_segment(text):
        """
        判断一个正文块是否适合继续按段落细分。

        只在“纯文本段落”场景下细分；若块中包含环境边界、列表项、
        单独的大括号或显示公式边界，则整体保留，避免破坏 LaTeX 结构。
        """
        if not text.strip():
            return False

        structural_patterns = [
            r"^\s*\\begin\{",
            r"^\s*\\end\{",
            r"^\s*\\item\b",
            r"^\s*[\{\}]\s*$",
            r"^\s*\$\$\s*$",
            r"^\s*\\\[\s*$",
            r"^\s*\\\]\s*$",
        ]
        return not any(
            re.search(pattern, text, flags=re.MULTILINE)
            for pattern in structural_patterns
        )

    @classmethod
    def _render_bilingual_segment(cls, en_text, zh_text, zh_color):
        """
        将一个正文块渲染为中英对照。

        如果中英块都能按空行拆成相同数量的段落，则逐段交错输出；
        否则退化为整块英文后跟整块中文，避免误配段落。
        """
        en_paragraphs = cls._split_tex_paragraphs(en_text)
        zh_paragraphs = cls._split_tex_paragraphs(zh_text)

        if (
            len(en_paragraphs) > 1
            and zh_paragraphs
            and cls._can_paragraph_split_segment(en_text)
            and cls._can_paragraph_split_segment(zh_text)
        ):
            zh_groups = []
            zh_count = len(zh_paragraphs)
            en_count = len(en_paragraphs)
            for i in range(en_count):
                start = round(i * zh_count / en_count)
                end = round((i + 1) * zh_count / en_count)
                if end <= start:
                    end = min(start + 1, zh_count)
                zh_groups.append("\n\n".join(zh_paragraphs[start:end]).strip())

            rendered = []
            for en_para, zh_para in zip(en_paragraphs, zh_groups):
                rendered.append(en_para)
                if zh_para:
                    rendered.append("")
                    rendered.append(f"\\begingroup\\color{{{zh_color}}}")
                    rendered.append(zh_para)
                    rendered.append("\\par\\endgroup")
                rendered.append("")
            return "\n\n".join(rendered).strip() + "\n\n"

        rendered = [en_text.rstrip()]
        if zh_text.strip():
            rendered.extend(
                [
                    "",
                    f"\\begingroup\\color{{{zh_color}}}",
                    zh_text.strip(),
                    "\\par\\endgroup",
                    "",
                ]
            )
        return "\n\n".join(rendered).strip() + "\n\n"

    @classmethod
    def merge_bilingual_body_tex(
        cls,
        english_tex_path,
        chinese_tex_path,
        output_tex_path=None,
        zh_color="bilingualzhcolor",
    ):
        """
        将英文 `merge.tex` 与中文 `merge_translate_zh.tex` 合并为中英对照文档。

        合并规则：
        1. 以中文文档为骨架输出，因此标题、摘要、图片、表格等保持与中文翻译稿一致
        2. 仅对正文段落做“英文后跟中文”的对照排版
        3. 中文正文统一使用灰色显示
        """
        with open(english_tex_path, "r", encoding="utf-8", errors="replace") as f:
            english_tex = f.read()
        with open(chinese_tex_path, "r", encoding="utf-8", errors="replace") as f:
            chinese_tex = f.read()

        _, english_segments = cls.split_bilingual_body(english_tex)
        chinese_nodes, chinese_segments = cls.split_bilingual_body(chinese_tex)

        if len(english_segments) != len(chinese_segments):
            raise ValueError(
                "中英文正文段落切分数量不一致，无法安全合并。"
                f" 英文段落数={len(english_segments)}，中文段落数={len(chinese_segments)}"
            )

        result_parts = []
        segment_index = 0
        for node in chinese_nodes:
            if node.preserve:
                result_parts.append(node.string)
                continue

            en_text = english_segments[segment_index].rstrip()
            zh_text = chinese_segments[segment_index].strip()
            result_parts.append(cls._render_bilingual_segment(en_text, zh_text, zh_color))
            segment_index += 1

        merged_tex = "".join(result_parts)
        merged_tex = cls.ensure_bilingual_preamble(merged_tex, color_name=zh_color)

        if output_tex_path is None:
            output_tex_path = pj(
                os.path.dirname(os.path.abspath(english_tex_path)),
                "merge_bilingual_zh.tex",
            )

        with open(output_tex_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(merged_tex)
        logger.info(f"已生成中英对照文档: {output_tex_path}")
        return output_tex_path


class LatexPaperSplit():
    """
    将LaTeX文件分解为链表，每个节点使用保留标志来指示是否应由GPT处理。

    该类用于精细切分LaTeX文件，识别出需要保留的部分（如公式、图表）和
    需要转换的部分（如正文文本）。
    """
    def __init__(self) -> None:
        """初始化LatexPaperSplit实例，设置警告信息和默认标题摘要。"""
        self.nodes = None
        self.msg = "*{\\scriptsize\\textbf{警告：该PDF由GPT-Academic开源项目调用大语言模型+Latex翻译插件一键生成，" + \
            "版权归原文作者所有。翻译内容可靠性无保障，请仔细鉴别并以原文为准。" + \
            "项目Github地址 \\url{https://github.com/binary-husky/gpt_academic/}。"
        # 请您不要删除或修改这行警告，除非您是论文的原作者（如果您是论文原作者，欢迎加README中的QQ联系开发者）
        self.msg_declare = "为了防止大语言模型的意外谬误产生扩散影响，禁止移除或修改此警告。}}\\\\"
        self.title = "unknown"
        self.abstract = "unknown"

    def read_title_and_abstract(self, txt):
        """
        从LaTeX文本中提取标题和摘要。

        Args:
            txt: LaTeX文件内容字符串
        """
        def normalize_text(content):
            return content.replace('\n', ' ').replace('\\\\', ' ').replace('  ', '').replace('  ', '')

        try:
            title, abstract = find_title_and_abs(txt)
            if title is not None:
                self.title = normalize_text(title)
            if abstract is not None:
                self.abstract = normalize_text(abstract)
        except:
            pass

    def merge_result(self, arr, mode, msg, buggy_lines=[], buggy_line_surgery_n_lines=10):
        """
        在GPT处理完成后合并结果。

        Args:
            arr: GPT处理后的文本片段数组
            mode: 处理模式（如'translate_zh'翻译中文，'proofread'校对）
            msg: 要插入的消息字符串
            buggy_lines: 有错误的行号列表，这些行将被还原为原文
            buggy_line_surgery_n_lines: 错误行周围需要处理的行数

        Returns:
            合并后的完整LaTeX字符串
        """
        result_string = ""
        node_cnt = 0
        line_cnt = 0

        for node in self.nodes:
            if node.preserve:
                line_cnt += node.string.count('\n')
                result_string += node.string
            else:
                translated_txt = fix_content(arr[node_cnt], node.string)
                begin_line = line_cnt
                end_line = line_cnt + translated_txt.count('\n')

                # reverse translation if any error
                if any([begin_line-buggy_line_surgery_n_lines <= b_line <= end_line+buggy_line_surgery_n_lines for b_line in buggy_lines]):
                    translated_txt = node.string

                result_string += translated_txt
                node_cnt += 1
                line_cnt += translated_txt.count('\n')

        if mode == 'translate_zh':
            pattern = re.compile(r'\\begin\{abstract\}.*\n')
            match = pattern.search(result_string)
            if not match:
                # match \abstract{xxxx}
                pattern_compile = re.compile(r"\\abstract\{(.*?)\}", flags=re.DOTALL)
                match = pattern_compile.search(result_string)
                position = match.regs[1][0]
            else:
                # match \begin{abstract}xxxx\end{abstract}
                position = match.end()
            result_string = result_string[:position] + self.msg + msg + self.msg_declare + result_string[position:]
        return result_string


    def split(self, txt, project_folder):
        """
        将LaTeX文件分解为链表，使用多进程避免超时错误。

        Args:
            txt: LaTeX文件内容字符串
            project_folder: 项目文件夹路径

        Returns:
            需要GPT处理的文本片段列表
        """
        import multiprocessing
        manager = multiprocessing.Manager()
        return_dict = manager.dict()
        p = multiprocessing.Process(
            target=split_subprocess,
            args=(txt, project_folder, return_dict))
        p.start()
        p.join()
        p.close()
        self.nodes = return_dict['nodes']
        self.sp = return_dict['segment_parts_for_gpt']
        return self.sp


class LatexPaperFileGroup():
    """
    使用分词器根据最大token限制拆分文本。

    该类用于管理LaTeX文件组，将大文件拆分为符合token限制的小片段。
    """
    def __init__(self):
        """初始化LatexPaperFileGroup实例，设置文件列表和token计数器。"""
        self.file_paths = []
        self.file_contents = []
        self.sp_file_contents = []
        self.sp_file_index = []
        self.sp_file_tag = []
        # count_token
        from ..utils import model_info
        enc = model_info["gpt-3.5-turbo"]['tokenizer']
        def get_token_num(txt): return len(enc.encode(txt, disallowed_special=()))
        self.get_token_num = get_token_num

    def run_file_split(self, max_token_limit=1900):
        """
        使用分词器根据最大token限制拆分文本。

        Args:
            max_token_limit: 每个片段的最大token数，默认为1900
        """
        for index, file_content in enumerate(self.file_contents):
            if self.get_token_num(file_content) < max_token_limit:
                self.sp_file_contents.append(file_content)
                self.sp_file_index.append(index)
                self.sp_file_tag.append(self.file_paths[index])
            else:
                def breakdown_text_to_satisfy_token_limit(txt, max_token):
                    return [txt[i:i+max_token] for i in range(0, len(txt), max_token)]
                
                segments = breakdown_text_to_satisfy_token_limit(file_content, max_token_limit)
                for j, segment in enumerate(segments):
                    self.sp_file_contents.append(segment)
                    self.sp_file_index.append(index)
                    self.sp_file_tag.append(self.file_paths[index] + f".part-{j}.tex")

    def merge_result(self):
        """将拆分后的文件结果合并回原始文件结构。"""
        self.file_result = ["" for _ in range(len(self.file_paths))]
        for r, k in zip(self.sp_file_result, self.sp_file_index):
            self.file_result[k] += r

    def write_result(self):
        """
        将处理结果写入.polish.tex文件。

        Returns:
            写入的文件路径列表
        """
        manifest = []
        for path, res in zip(self.file_paths, self.file_result):
            with open(path + '.polish.tex', 'w', encoding='utf8') as f:
                manifest.append(path + '.polish.tex')
                f.write(res)
        return manifest


def LatexDetailedDecompositionAndTransform(file_manifest, project_folder, llm_kwargs, plugin_kwargs, mode='proofread', switch_prompt=None):
    """
    对LaTeX文件进行精细分解和转换处理。

    该函数执行以下步骤：
    1. 寻找主tex文件
    2. 融合多文件tex工程为一个巨型tex
    3. 精细切分latex文件，识别保留区域和转换区域
    4. 多线程GPT处理文本片段
    5. 重组处理后的文本并输出

    Args:
        file_manifest: tex文件列表
        project_folder: 项目文件夹路径
        llm_kwargs: LLM模型参数字典
        plugin_kwargs: 插件参数字典
        mode: 处理模式，'proofread'校对或'translate_zh'翻译中文
        switch_prompt: prompt切换函数
        opts: 处理选项列表

    Returns:
        生成的合并tex文件路径
    """
    import time
    from ..llm_utils import request_gpt_model_multi_threads_with_very_awesome_ui_and_high_efficiency

    #  <-------- 寻找主tex文件 ---------->
    maintex = find_main_tex_file(file_manifest)
    logger.info(f"定位主Latex文件: 分析结果：该项目的Latex主文件是{maintex}")
    time.sleep(3)

    #  <-------- 读取Latex文件, 将多文件tex工程融合为一个巨型tex ---------->
    main_tex_basename = os.path.basename(maintex)
    assert main_tex_basename.endswith('.tex')
    main_tex_basename_bare = main_tex_basename[:-4]
    may_exist_bbl = pj(project_folder, f'{main_tex_basename_bare}.bbl')
    if os.path.exists(may_exist_bbl):
        shutil.copyfile(may_exist_bbl, pj(project_folder, f'merge.bbl'))
        shutil.copyfile(may_exist_bbl, pj(project_folder, f'merge_{mode}.bbl'))
        shutil.copyfile(may_exist_bbl, pj(project_folder, f'merge_diff.bbl'))

    with open(maintex, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        merged_content = merge_tex_files(project_folder, content, mode)

    with open(project_folder + '/merge.tex', 'w', encoding='utf-8', errors='replace') as f:
        f.write(merged_content)

    #  <-------- 精细切分latex文件 ---------->
    logger.info("Latex文件融合完成: 正在精细切分latex文件，这需要一段时间计算...")
    lps = LatexPaperSplit()
    lps.read_title_and_abstract(merged_content)
    res = lps.split(merged_content, project_folder) # 消耗时间的函数
    #  <-------- 拆分过长的latex片段 ---------->
    pfg = LatexPaperFileGroup()
    for index, r in enumerate(res):
        pfg.file_paths.append('segment-' + str(index))
        pfg.file_contents.append(r)

    pfg.run_file_split(max_token_limit=1024)
    n_split = len(pfg.sp_file_contents)

    #  <-------- 根据需要切换prompt ---------->
    inputs_array, sys_prompt_array = switch_prompt(pfg, mode)
    inputs_show_user_array = [f"{mode} {f}" for f in pfg.sp_file_tag]

    if os.path.exists(pj(project_folder,'temp.pkl')):

        #  <-------- 【仅调试】如果存在调试缓存文件，则跳过GPT请求环节 ---------->
        pfg = objload(file=pj(project_folder,'temp.pkl'))

    else:
        #  <-------- gpt 多线程请求 ---------->
        history_array = [[""] for _ in range(n_split)]
        # LATEX_EXPERIMENTAL, = get_conf('LATEX_EXPERIMENTAL')
        # if LATEX_EXPERIMENTAL:
        #     paper_meta = f"The paper you processing is `{lps.title}`, a part of the abstraction is `{lps.abstract}`"
        #     paper_meta_max_len = 888
        #     history_array = [[ paper_meta[:paper_meta_max_len] + '...',  "Understand, what should I do?"] for _ in range(n_split)]

        gpt_response_collection = request_gpt_model_multi_threads_with_very_awesome_ui_and_high_efficiency(
            inputs_array=inputs_array,
            inputs_show_user_array=inputs_show_user_array,
            llm_kwargs=llm_kwargs,
            history_array=history_array,
            sys_prompt_array=sys_prompt_array,
        )

        #  <-------- 文本碎片重组为完整的tex片段 ---------->
        pfg.sp_file_result = []
        for i_say, gpt_say, orig_content in zip(gpt_response_collection[0::2], gpt_response_collection[1::2], pfg.sp_file_contents):
            pfg.sp_file_result.append(gpt_say)
        pfg.merge_result()

        # <-------- 临时存储用于调试 ---------->
        pfg.get_token_num = None
        objdump(pfg, file=pj(project_folder,'temp.pkl'))

    #  <-------- 写出文件 ---------->
    model_name = llm_kwargs['llm_model'].replace('_', '\\_')  # 替换LLM模型名称中的下划线为转义字符
    msg = f"当前大语言模型: {model_name}，当前语言模型温度设定: {llm_kwargs['temperature']}。"
    final_tex = lps.merge_result(pfg.file_result, mode, msg)
    objdump((lps, pfg.file_result, mode, msg), file=pj(project_folder,'merge_result.pkl'))

    with open(project_folder + f'/merge_{mode}.tex', 'w', encoding='utf-8', errors='replace') as f:
        if mode != 'translate_zh' or "binary" in final_tex: f.write(final_tex)


    #  <-------- 整理结果, 退出 ---------->
    logger.info("完成了吗？: GPT结果已输出, 即将编译PDF")

    #  <-------- 生成中英对照tex文件 ---------->
    if mode == 'translate_zh':
        try:
            BilingualTexMerger.merge_bilingual_body_tex(
                english_tex_path=project_folder + '/merge.tex',
                chinese_tex_path=project_folder + '/merge_translate_zh.tex',
            )
            logger.info("已生成中英对照tex文件: merge_bilingual_zh.tex")
        except Exception as e:
            logger.warning(f"生成中英对照文件时出错: {e}")

    #  <-------- 返回 ---------->
    return [project_folder + f'/merge_{mode}.tex', project_folder + f'/merge_bilingual_zh.tex']


def remove_buggy_lines(file_path, log_path, tex_name, tex_name_pure, n_fix, work_folder_modified, fixed_line=[]):
    """
    从LaTeX编译日志中识别错误行，并修复这些行。

    Args:
        file_path: tex文件路径
        log_path: 编译日志文件路径
        tex_name: tex文件名
        tex_name_pure: 纯净的tex文件名（不含扩展名）
        n_fix: 当前修复尝试次数
        work_folder_modified: 工作文件夹路径
        fixed_line: 已修复的行号列表

    Returns:
        tuple: (是否成功, 修复后的文件名, 错误行列表)
    """
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            log = f.read()
        buggy_lines = re.findall(tex_name+':([0-9]{1,5}):', log)
        buggy_lines = [int(l) for l in buggy_lines]
        buggy_lines = sorted(buggy_lines)
        buggy_line = buggy_lines[0]-1
        logger.warning("reversing tex line that has errors", buggy_line)

        # 重组，逆转出错的段落
        if buggy_line not in fixed_line:
            fixed_line.append(buggy_line)

        lps, file_result, mode, msg = objload(file=pj(work_folder_modified,'merge_result.pkl'))
        final_tex = lps.merge_result(file_result, mode, msg, buggy_lines=fixed_line, buggy_line_surgery_n_lines=5*n_fix)

        with open(pj(work_folder_modified, f"{tex_name_pure}_fix_{n_fix}.tex"), 'w', encoding='utf-8', errors='replace') as f:
            f.write(final_tex)

        return True, f"{tex_name_pure}_fix_{n_fix}", buggy_lines
    except:
        logger.error("Fatal error occurred, but we cannot identify error, please download zip, read latex log, and compile manually.")
        return False, -1, [-1]


def CompileLatex(main_file_original, main_file_modified, work_folder_original, work_folder_modified, work_folder, mode='default', bilingual_file=None):
    """
    编译LaTeX文件生成PDF。

    该函数执行完整的LaTeX编译流程：
    1. 自动检测需要使用pdflatex还是xelatex编译器
    2. 多次编译以确保交叉引用正确
    3. 处理bibtex引用
    4. 生成对比PDF（使用latexdiff）
    5. 如果编译失败，自动识别错误行并修复后重试
    6. （可选）编译中英对照PDF

    Args:
        main_file_original: 原始主tex文件名（不含扩展名）
        main_file_modified: 修改后主tex文件名（不含扩展名）
        work_folder_original: 原始文件工作目录
        work_folder_modified: 修改后文件工作目录
        work_folder: 主工作目录
        mode: 编译模式，'default'默认或'translate_zh'翻译中文
        bilingual_file: 中英对照tex文件名（不含扩展名），仅在mode='translate_zh'时生效

    Returns:
        bool: 编译是否成功
    """
    n_fix = 1
    fixed_line = []
    max_try = 32
    logger.info(f"正在编译PDF文档: 编译已经开始。当前工作路径为{work_folder}")
    logger.info("正在编译PDF文档: ...")
    logger.info('编译已经开始...')   # 刷新Gradio前端界面
    # 检查是否需要使用xelatex
    def check_if_need_xelatex(tex_path):
        """检查tex文件是否需要使用xelatex编译。"""
        try:
            with open(tex_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(5000)
                # 检查是否有使用xelatex的宏包
                need_xelatex = any(
                    pkg in content
                    for pkg in ['fontspec', 'xeCJK', 'xetex', 'unicode-math', 'xltxtra', 'xunicode']
                )
                if need_xelatex:
                    logger.info(f"检测到宏包需要xelatex编译, 切换至xelatex编译")
                else:
                    logger.info(f"未检测到宏包需要xelatex编译, 使用pdflatex编译")
                return need_xelatex
        except Exception:
            return False

    # 根据编译器类型返回编译命令
    def get_compile_command(compiler, filename):
        """根据编译器类型生成编译命令。"""
        compile_command = f'{compiler} -interaction=batchmode -file-line-error {filename}.tex'
        logger.info('Latex 编译指令: ' + compile_command)
        return compile_command

    # 确定使用的编译器
    compiler = 'pdflatex'
    if check_if_need_xelatex(pj(work_folder_modified, f'{main_file_modified}.tex')):
        logger.info("检测到宏包需要xelatex编译，切换至xelatex编译")
        # Check if xelatex is installed
        try:
            import subprocess
            subprocess.run(['xelatex', '--version'], capture_output=True, check=True)
            compiler = 'xelatex'
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("检测到需要使用xelatex编译，但系统中未安装xelatex。请先安装texlive或其他提供xelatex的LaTeX发行版。")

    while True:
        may_exist_bbl = pj(work_folder_modified, f'merge.bbl')
        target_bbl = pj(work_folder_modified, f'{main_file_modified}.bbl')
        if os.path.exists(may_exist_bbl) and not os.path.exists(target_bbl):
            shutil.copyfile(may_exist_bbl, target_bbl)

        # https://stackoverflow.com/questions/738755/dont-make-me-manually-abort-a-latex-compile-when-theres-an-error
        logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 编译原始PDF ...')   # 刷新Gradio前端界面
        ok = compile_latex_with_timeout(get_compile_command(compiler, main_file_original), work_folder_original)

        logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 编译转化后的PDF ...')   # 刷新Gradio前端界面
        ok = compile_latex_with_timeout(get_compile_command(compiler, main_file_modified), work_folder_modified)

        if ok and os.path.exists(pj(work_folder_modified, f'{main_file_modified}.pdf')):
            # 只有第二步成功，才能继续下面的步骤
            logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 编译BibTex ...')    # 刷新Gradio前端界面
            if not os.path.exists(pj(work_folder_original, f'{main_file_original}.bbl')):
                ok = compile_latex_with_timeout(f'bibtex  {main_file_original}.aux', work_folder_original)
            if not os.path.exists(pj(work_folder_modified, f'{main_file_modified}.bbl')):
                ok = compile_latex_with_timeout(f'bibtex  {main_file_modified}.aux', work_folder_modified)

            logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 编译文献交叉引用 ...')  # 刷新Gradio前端界面
            ok = compile_latex_with_timeout(get_compile_command(compiler, main_file_original), work_folder_original)
            ok = compile_latex_with_timeout(get_compile_command(compiler, main_file_modified), work_folder_modified)
            ok = compile_latex_with_timeout(get_compile_command(compiler, main_file_original), work_folder_original)
            ok = compile_latex_with_timeout(get_compile_command(compiler, main_file_modified), work_folder_modified)

            # 编译中英对照PDF（在主文件交叉引用完成后）
            bilingual_ok = True
            if bilingual_file and os.path.exists(pj(work_folder_modified, f'{bilingual_file}.tex')):
                logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 编译中英对照PDF ...')
                may_exist_bbl_bilingual = pj(work_folder_modified, f'{bilingual_file}.bbl')
                if not os.path.exists(may_exist_bbl_bilingual) and os.path.exists(pj(work_folder_modified, 'merge.bbl')):
                    shutil.copyfile(pj(work_folder_modified, 'merge.bbl'), may_exist_bbl_bilingual)
                bilingual_ok = compile_latex_with_timeout(get_compile_command(compiler, bilingual_file), work_folder_modified)
                if bilingual_ok and not os.path.exists(may_exist_bbl_bilingual):
                    bilingual_ok = compile_latex_with_timeout(f'bibtex  {bilingual_file}.aux', work_folder_modified)
                if bilingual_ok:
                    bilingual_ok = compile_latex_with_timeout(get_compile_command(compiler, bilingual_file), work_folder_modified)
                    bilingual_ok = compile_latex_with_timeout(get_compile_command(compiler, bilingual_file), work_folder_modified)

            if mode!='translate_zh':
                logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 使用latexdiff生成论文转化前后对比 ...') # 刷新Gradio前端界面
                logger.info(    f'latexdiff --encoding=utf8 --append-safecmd=subfile {work_folder_original}/{main_file_original}.tex  {work_folder_modified}/{main_file_modified}.tex --flatten > {work_folder}/merge_diff.tex')
                ok = compile_latex_with_timeout(f'latexdiff --encoding=utf8 --append-safecmd=subfile {work_folder_original}/{main_file_original}.tex  {work_folder_modified}/{main_file_modified}.tex --flatten > {work_folder}/merge_diff.tex', os.getcwd())

                logger.info(f'尝试第 {n_fix}/{max_try} 次编译, 正在编译对比PDF ...')   # 刷新Gradio前端界面
                ok = compile_latex_with_timeout(get_compile_command(compiler, 'merge_diff'), work_folder)
                ok = compile_latex_with_timeout(f'bibtex    merge_diff.aux', work_folder)
                ok = compile_latex_with_timeout(get_compile_command(compiler, 'merge_diff'), work_folder)
                ok = compile_latex_with_timeout(get_compile_command(compiler, 'merge_diff'), work_folder)

        # <---------- 检查结果 ----------->
        results_ = ""
        original_pdf_success = os.path.exists(pj(work_folder_original, f'{main_file_original}.pdf'))
        modified_pdf_success = os.path.exists(pj(work_folder_modified, f'{main_file_modified}.pdf'))
        diff_pdf_success     = os.path.exists(pj(work_folder, f'merge_diff.pdf'))
        bilingual_pdf_success = os.path.exists(pj(work_folder_modified, f'{bilingual_file}.pdf')) if bilingual_file else False
        results_ += f"原始PDF编译是否成功: {original_pdf_success};"
        results_ += f"转化PDF编译是否成功: {modified_pdf_success};"
        results_ += f"对比PDF编译是否成功: {diff_pdf_success};"
        if bilingual_file:
            results_ += f"中英对照PDF编译是否成功: {bilingual_pdf_success};"
        logger.info(f'第{n_fix}编译结束:<br/>{results_}...') # 刷新Gradio前端界面

        if diff_pdf_success:
            result_pdf = pj(work_folder_modified, f'merge_diff.pdf')    # get pdf path
            pass  # promote file to web UI
        if modified_pdf_success:
            logger.info(f'转化PDF编译已经成功, 正在尝试生成对比PDF, 请稍候 ...')    # 刷新Gradio前端界面
            result_pdf = pj(work_folder_modified, f'{main_file_modified}.pdf') # get pdf path
            origin_pdf = pj(work_folder_original, f'{main_file_original}.pdf') # get pdf path
            if os.path.exists(pj(work_folder, '..', 'translation')):
                shutil.copyfile(result_pdf, pj(work_folder, '..', 'translation', 'translate_zh.pdf'))
                # 同时复制中英对照PDF（如果存在）
                if bilingual_pdf_success:
                    shutil.copyfile(pj(work_folder_modified, f'{bilingual_file}.pdf'),
                                    pj(work_folder, '..', 'translation', f'{bilingual_file}.pdf'))
            pass  # promote file to web UI
            return True # 成功啦
        else:
            if n_fix>=max_try: break
            n_fix += 1
            can_retry, main_file_modified, buggy_lines = remove_buggy_lines(
                file_path=pj(work_folder_modified, f'{main_file_modified}.tex'),
                log_path=pj(work_folder_modified, f'{main_file_modified}.log'),
                tex_name=f'{main_file_modified}.tex',
                tex_name_pure=f'{main_file_modified}',
                n_fix=n_fix,
                work_folder_modified=work_folder_modified,
                fixed_line=fixed_line
            )
            logger.info(f'由于最为关键的转化PDF编译失败, 将根据报错信息修正tex源文件并重试, 当前报错的latex代码处于第{buggy_lines}行 ...')   # 刷新Gradio前端界面
            if not can_retry: break

    return False # 失败啦