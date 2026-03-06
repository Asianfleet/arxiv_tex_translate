import os
import re
import shutil
import numpy as np
from loguru import logger

PRESERVE = 0
TRANSFORM = 1

pj = os.path.join


class LinkedListNode:
    """
    链表节点类，用于表示LaTeX文档的分段。

    每个节点包含一段文本内容、是否保留的标志，以及指向下一个节点的链接。

    Attributes:
        string: 节点存储的文本内容
        preserve: 是否为保留区域（不需要GPT处理）
        next: 指向下一个节点的引用
        range: 节点在原文中的行数范围
    """

    def __init__(self, string, preserve=True) -> None:
        """初始化链表节点。"""
        self.string = string
        self.preserve = preserve
        self.next = None
        self.range = None
        # self.begin_line = 0
        # self.begin_char = 0


def convert_to_linklist(text, mask):
    """
    根据掩码将文本转换为链表结构。

    根据PRESERVE/TRANSFORM掩码将文本分割为多个节点，相同类型的连续字符会被合并到同一个节点。

    Args:
        text: 原始文本字符串
        mask: 掩码数组，PRESERVE(0)表示保留，TRANSFORM(1)表示需要处理

    Returns:
        链表的头节点（root节点本身不包含有效内容）
    """
    root = LinkedListNode("", preserve=True)
    current_node = root
    for c, m, i in zip(text, mask, range(len(text))):
        if (m == PRESERVE and current_node.preserve) or (
            m == TRANSFORM and not current_node.preserve
        ):
            # add
            current_node.string += c
        else:
            current_node.next = LinkedListNode(c, preserve=(m == PRESERVE))
            current_node = current_node.next
    return root


def post_process(root):
    """
    后处理链表节点，修复括号错误和优化节点结构。

    执行以下操作：
    1. 修复括号不匹配的问题
    2. 屏蔽空行和太短的句子（标记为保留）
    3. 合并连续的保留节点
    4. 将前后断行符脱离转换区域
    5. 标注节点的行数范围

    Args:
        root: 链表的头节点

    Returns:
        处理后的链表头节点
    """
    # 修复括号
    node = root
    while True:
        string = node.string
        if node.preserve:
            node = node.next
            if node is None:
                break
            continue

        def break_check(string):
            """检查字符串中的括号是否平衡，返回第一个不匹配的位置。"""
            str_stack = [""]  # (lv, index)
            for i, c in enumerate(string):
                if c == "{":
                    str_stack.append("{")
                elif c == "}":
                    if len(str_stack) == 1:
                        logger.warning("fixing brace error")
                        return i
                    str_stack.pop(-1)
                else:
                    str_stack[-1] += c
            return -1

        bp = break_check(string)

        if bp == -1:
            pass
        elif bp == 0:
            node.string = string[:1]
            q = LinkedListNode(string[1:], False)
            q.next = node.next
            node.next = q
        else:
            node.string = string[:bp]
            q = LinkedListNode(string[bp:], False)
            q.next = node.next
            node.next = q

        node = node.next
        if node is None:
            break

    # 屏蔽空行和太短的句子
    node = root
    while True:
        if len(node.string.strip("\n").strip("")) == 0:
            node.preserve = True
        if len(node.string.strip("\n").strip("")) < 42:
            node.preserve = True
        node = node.next
        if node is None:
            break
    node = root
    while True:
        if node.next and node.preserve and node.next.preserve:
            node.string += node.next.string
            node.next = node.next.next
        node = node.next
        if node is None:
            break

    # 将前后断行符脱离
    node = root
    prev_node = None
    while True:
        if not node.preserve:
            lstriped_ = node.string.lstrip().lstrip("\n")
            if (
                (prev_node is not None)
                and (prev_node.preserve)
                and (len(lstriped_) != len(node.string))
            ):
                prev_node.string += node.string[: -len(lstriped_)]
                node.string = lstriped_
            rstriped_ = node.string.rstrip().rstrip("\n")
            if (
                (node.next is not None)
                and (node.next.preserve)
                and (len(rstriped_) != len(node.string))
            ):
                node.next.string = node.string[len(rstriped_) :] + node.next.string
                node.string = rstriped_
        # =-=-=
        prev_node = node
        node = node.next
        if node is None:
            break

    # 标注节点的行数范围
    node = root
    n_line = 0
    expansion = 2
    while True:
        n_l = node.string.count("\n")
        node.range = [n_line - expansion, n_line + n_l + expansion]  # 失败时，扭转的范围
        n_line = n_line + n_l
        node = node.next
        if node is None:
            break
    return root


"""
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
Latex segmentation with a binary mask (PRESERVE=0, TRANSFORM=1)
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
"""


def set_forbidden_text(text, mask, pattern, flags=0):
    """
    在LaTeX文档中标记保留文本区域。

    将匹配正则表达式的文本区域标记为PRESERVE，使GPT不会处理这些区域。
    例如：使用 pattern = r"\\begin\{algorithm\}(.*?)\\end\{algorithm\}"
    可以将 "\begin{equation}" 和 "\end{equation}" 之间的内容标记为保留。

    Args:
        text: LaTeX文本内容
        mask: 掩码数组
        pattern: 正则表达式或表达式列表
        flags: 正则表达式标志

    Returns:
        tuple: (text, mask)
    """
    if isinstance(pattern, list):
        pattern = "|".join(pattern)
    pattern_compile = re.compile(pattern, flags)
    for res in pattern_compile.finditer(text):
        mask[res.span()[0] : res.span()[1]] = PRESERVE
    return text, mask


def reverse_forbidden_text(text, mask, pattern, flags=0, forbid_wrapper=True):
    """
    将保留区域中的部分内容转为可编辑区域（供GPT处理）。

    例如对于 \begin{abstract} 内容 \end{abstract}，可以将中间的内容部分
    标记为TRANSFORM让GPT处理，而保留begin和end标记。

    Args:
        text: LaTeX文本内容
        mask: 掩码数组
        pattern: 正则表达式，第一个捕获组将作为可编辑区域
        flags: 正则表达式标志
        forbid_wrapper: 是否保留外层包裹标记

    Returns:
        tuple: (text, mask)
    """
    if isinstance(pattern, list):
        pattern = "|".join(pattern)
    pattern_compile = re.compile(pattern, flags)
    for res in pattern_compile.finditer(text):
        if not forbid_wrapper:
            mask[res.span()[0] : res.span()[1]] = TRANSFORM
        else:
            mask[res.regs[0][0] : res.regs[1][0]] = PRESERVE  # '\\begin{abstract}'
            mask[res.regs[1][0] : res.regs[1][1]] = TRANSFORM  # abstract
            mask[res.regs[1][1] : res.regs[0][1]] = PRESERVE  # abstract
    return text, mask


def set_forbidden_text_careful_brace(text, mask, pattern, flags=0):
    """
    通过计算大括号层级来精确标记保留区域。

    适用于包含嵌套大括号的复杂结构，如：
    \caption{blablablablabla\texbf{blablabla}blablabla.}

    Args:
        text: LaTeX文本内容
        mask: 掩码数组
        pattern: 正则表达式，用于定位起始位置
        flags: 正则表达式标志

    Returns:
        tuple: (text, mask)
    """
    pattern_compile = re.compile(pattern, flags)
    for res in pattern_compile.finditer(text):
        brace_level = -1
        p = begin = end = res.regs[0][0]
        for _ in range(1024 * 16):
            if text[p] == "}" and brace_level == 0:
                break
            elif text[p] == "}":
                brace_level -= 1
            elif text[p] == "{":
                brace_level += 1
            p += 1
        end = p + 1
        mask[begin:end] = PRESERVE
    return text, mask


def reverse_forbidden_text_careful_brace(
    text, mask, pattern, flags=0, forbid_wrapper=True
):
    """
    通过计算大括号层级，将保留区域中的部分内容转为可编辑区域。

    适用于包含嵌套大括号的复杂结构，可以精确识别出可编辑的内部内容。
    例如：\caption{内容} 可以将"内容"部分标记为可编辑。

    Args:
        text: LaTeX文本内容
        mask: 掩码数组
        pattern: 正则表达式，第一个捕获组将作为可编辑区域的起始
        flags: 正则表达式标志
        forbid_wrapper: 是否保留外层包裹标记

    Returns:
        tuple: (text, mask)
    """
    pattern_compile = re.compile(pattern, flags)
    for res in pattern_compile.finditer(text):
        brace_level = 0
        p = begin = end = res.regs[1][0]
        for _ in range(1024 * 16):
            if text[p] == "}" and brace_level == 0:
                break
            elif text[p] == "}":
                brace_level -= 1
            elif text[p] == "{":
                brace_level += 1
            p += 1
        end = p
        mask[begin:end] = TRANSFORM
        if forbid_wrapper:
            mask[res.regs[0][0] : begin] = PRESERVE
            mask[end : res.regs[0][1]] = PRESERVE
    return text, mask


def set_forbidden_text_begin_end(text, mask, pattern, flags=0, limit_n_lines=42):
    """
    查找所有行数小于限制的\begin{}...\end{}文本块并标记为保留区域。

    对于白名单中的环境（如document、abstract等）或行数超过限制的内容，
    会递归处理内部内容；其他环境整体标记为保留。

    Args:
        text: LaTeX文本内容
        mask: 掩码数组
        pattern: 匹配begin-end结构的正则表达式
        flags: 正则表达式标志
        limit_n_lines: 行数限制阈值，默认为42

    Returns:
        tuple: (text, mask)
    """
    pattern_compile = re.compile(pattern, flags)

    def search_with_line_limit(text, mask):
        """递归搜索并处理begin-end块。"""
        for res in pattern_compile.finditer(text):
            cmd = res.group(1)  # begin{what}
            this = res.group(2)  # content between begin and end
            this_mask = mask[res.regs[2][0] : res.regs[2][1]]
            white_list = [
                "document",
                "abstract",
                "lemma",
                "definition",
                "sproof",
                "em",
                "emph",
                "textit",
                "textbf",
                "itemize",
                "enumerate",
            ]
            if (cmd in white_list) or this.count(
                "\n"
            ) >= limit_n_lines:  # use a magical number 42
                this, this_mask = search_with_line_limit(this, this_mask)
                mask[res.regs[2][0] : res.regs[2][1]] = this_mask
            else:
                mask[res.regs[0][0] : res.regs[0][1]] = PRESERVE
        return text, mask

    return search_with_line_limit(text, mask)


"""
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
Latex Merge File
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
"""


def find_main_tex_file(file_manifest, mode):
    """
    在多Tex文档中寻找主文件。

    主文件必须包含\documentclass。如果找到多个候选文件，
    会通过评分机制排除模板文件（包含manuscript、Guidelines等关键词的）
    并优先选择包含\input、\ref、\cite等正文特征的文档。

    Args:
        file_manifest: tex文件路径列表
        mode: 处理模式

    Returns:
        主tex文件的完整路径

    Raises:
        RuntimeError: 如果找不到包含documentclass的文件
    """
    candidates = []
    for texf in file_manifest:
        if os.path.basename(texf).startswith("merge"):
            continue
        with open(texf, "r", encoding="utf8", errors="ignore") as f:
            file_content = f.read()
        if r"\documentclass" in file_content:
            candidates.append(texf)
        else:
            continue

    if len(candidates) == 0:
        raise RuntimeError("无法找到一个主Tex文件（包含documentclass关键字）")
    elif len(candidates) == 1:
        return candidates[0]
    else:  # if len(candidates) >= 2 通过一些Latex模板中常见（但通常不会出现在正文）的单词，对不同latex源文件扣分，取评分最高者返回
        candidates_score = []
        # 给出一些判定模板文档的词作为扣分项
        unexpected_words = [
            "\\LaTeX",
            "manuscript",
            "Guidelines",
            "font",
            "citations",
            "rejected",
            "blind review",
            "reviewers",
        ]
        expected_words = ["\\input", "\\ref", "\\cite"]
        for texf in candidates:
            candidates_score.append(0)
            with open(texf, "r", encoding="utf8", errors="ignore") as f:
                file_content = f.read()
                file_content = rm_comments(file_content)
            for uw in unexpected_words:
                if uw in file_content:
                    candidates_score[-1] -= 1
            for uw in expected_words:
                if uw in file_content:
                    candidates_score[-1] += 1
        select = np.argmax(candidates_score)  # 取评分最高者返回
        return candidates[select]


def rm_comments(main_file):
    """
    移除LaTeX文件中的注释。

    删除整行注释（以%开头的行）和行内注释（%后的内容）。
    保留转义的百分号（\%）。

    Args:
        main_file: LaTeX文件内容字符串

    Returns:
        移除注释后的内容
    """
    new_file_remove_comment_lines = []
    for l in main_file.splitlines():
        # 删除整行的空注释
        if l.lstrip().startswith("%"):
            pass
        else:
            new_file_remove_comment_lines.append(l)
    main_file = "\n".join(new_file_remove_comment_lines)
    # main_file = re.sub(r"\\include{(.*?)}", r"\\input{\1}", main_file)  # 将 \include 命令转换为 \input 命令
    main_file = re.sub(r"(?<!\\)%.*", "", main_file)  # 使用正则表达式查找半行注释, 并替换为空字符串
    return main_file


def find_tex_file_ignore_case(fp):
    """
    不区分大小写地查找tex文件。

    依次尝试：
    1. 原路径
    2. 添加.tex后缀
    3. 不区分大小写匹配

    Args:
        fp: 文件路径

    Returns:
        找到的文件路径，或None
    """
    dir_name = os.path.dirname(fp)
    base_name = os.path.basename(fp)
    # 如果输入的文件路径是正确的
    if os.path.isfile(pj(dir_name, base_name)):
        return pj(dir_name, base_name)
    # 如果不正确，试着加上.tex后缀试试
    if not base_name.endswith(".tex"):
        base_name += ".tex"
    if os.path.isfile(pj(dir_name, base_name)):
        return pj(dir_name, base_name)
    # 如果还找不到，解除大小写限制，再试一次
    import glob

    for f in glob.glob(dir_name + "/*.tex"):
        base_name_s = os.path.basename(fp)
        base_name_f = os.path.basename(f)
        if base_name_s.lower() == base_name_f.lower():
            return f
        # 试着加上.tex后缀试试
        if not base_name_s.endswith(".tex"):
            base_name_s += ".tex"
        if base_name_s.lower() == base_name_f.lower():
            return f
    return None


def merge_tex_files_(project_foler, main_file, mode):
    """
    递归合并LaTeX项目的所有文件（内部辅助函数）。

    处理\input命令，将引用的外部文件内容嵌入到主文件中。

    Args:
        project_foler: 项目文件夹路径
        main_file: 主文件内容
        mode: 处理模式

    Returns:
        合并后的文件内容
    """
    main_file = rm_comments(main_file)
    for s in reversed([q for q in re.finditer(r"\\input\{(.*?)\}", main_file, re.M)]):
        f = s.group(1)
        fp = os.path.join(project_foler, f)
        fp_ = find_tex_file_ignore_case(fp)
        if fp_:
            try:
                with open(fp_, "r", encoding="utf-8", errors="replace") as fx:
                    c = fx.read()
            except:
                c = f"\n\nWarning from GPT-Academic: LaTex source file is missing!\n\n"
        else:
            raise RuntimeError(f"找不到{fp}，Tex源文件缺失！")
        c = merge_tex_files_(project_foler, c, mode)
        main_file = main_file[: s.span()[0]] + c + main_file[s.span()[1] :]
    return main_file


def find_title_and_abs(main_file):
    """
    从LaTeX文件中提取标题和摘要。

    支持两种摘要格式：
    1. \abstract{内容}
    2. \begin{abstract}内容\end{abstract}

    Args:
        main_file: LaTeX文件内容

    Returns:
        tuple: (标题, 摘要)，如果未找到则为None
    """
    def extract_abstract_1(text):
        """提取\abstract{}格式的摘要。"""
        pattern = r"\\abstract\{(.*?)\}"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        else:
            return None

    def extract_abstract_2(text):
        """提取\begin{abstract}格式的摘要。"""
        pattern = r"\\begin\{abstract\}(.*?)\\end\{abstract\}"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        else:
            return None

    def extract_title(string):
        """提取\title{}格式的标题。"""
        pattern = r"\\title\{(.*?)\}"
        match = re.search(pattern, string, re.DOTALL)

        if match:
            return match.group(1)
        else:
            return None

    abstract = extract_abstract_1(main_file)
    if abstract is None:
        abstract = extract_abstract_2(main_file)
    title = extract_title(main_file)
    return title, abstract


def merge_tex_files(project_foler, main_file, mode):
    """
    递归合并LaTeX项目的所有文件。

    主要功能：
    1. 处理\input命令，合并所有引用的文件
    2. 移除LaTeX注释
    3. 翻译模式下自动添加ctex宏包支持中文
    4. 配置中文字体设置

    Args:
        project_foler: 项目文件夹路径
        main_file: 主文件内容
        mode: 处理模式，'translate_zh'会添加中文支持

    Returns:
        合并后的完整文件内容
    """
    main_file = merge_tex_files_(project_foler, main_file, mode)
    main_file = rm_comments(main_file)

    if mode == "translate_zh":
        # find paper documentclass
        pattern = re.compile(r"\\documentclass.*\n")
        match = pattern.search(main_file)
        assert match is not None, "Cannot find documentclass statement!"
        position = match.end()
        add_ctex = "\\usepackage{ctex}\n"
        add_url = "\\usepackage{url}\n" if "{url}" not in main_file else ""
        main_file = main_file[:position] + add_ctex + add_url + main_file[position:]
        # fontset=windows

        main_file = re.sub(
            r"\\documentclass\[(.*?)\]{(.*?)}",
            r"\\documentclass[\1,fontset=windows,UTF8]{\2}",
            main_file,
        )
        main_file = re.sub(
            r"\\documentclass{(.*?)}",
            r"\\documentclass[fontset=windows,UTF8]{\1}",
            main_file,
        )
        # find paper abstract
        pattern_opt1 = re.compile(r"\\begin\{abstract\}.*\n")
        pattern_opt2 = re.compile(r"\\abstract\{(.*?)\}", flags=re.DOTALL)
        match_opt1 = pattern_opt1.search(main_file)
        match_opt2 = pattern_opt2.search(main_file)
        if (match_opt1 is None) and (match_opt2 is None):
            # "Cannot find paper abstract section!"
            main_file = insert_abstract(main_file)
        match_opt1 = pattern_opt1.search(main_file)
        match_opt2 = pattern_opt2.search(main_file)
        assert (match_opt1 is not None) or (
            match_opt2 is not None
        ), "Cannot find paper abstract section!"
    return main_file


insert_missing_abs_str = r"""
\begin{abstract}
The GPT-Academic program cannot find abstract section in this paper.
\end{abstract}
"""


def insert_abstract(tex_content):
    """
    在LaTeX文档中插入缺失的摘要环境。

    尝试在\maketitle或\begin{document}之后插入默认的摘要。

    Args:
        tex_content: LaTeX文档内容

    Returns:
        插入摘要后的文档内容
    """
    if "\\maketitle" in tex_content:
        # find the position of "\maketitle"
        find_index = tex_content.index("\\maketitle")
        # find the nearest ending line
        end_line_index = tex_content.find("\n", find_index)
        # insert "abs_str" on the next line
        modified_tex = (
            tex_content[: end_line_index + 1]
            + "\n\n"
            + insert_missing_abs_str
            + "\n\n"
            + tex_content[end_line_index + 1 :]
        )
        return modified_tex
    elif r"\begin{document}" in tex_content:
        # find the position of "\maketitle"
        find_index = tex_content.index(r"\begin{document}")
        # find the nearest ending line
        end_line_index = tex_content.find("\n", find_index)
        # insert "abs_str" on the next line
        modified_tex = (
            tex_content[: end_line_index + 1]
            + "\n\n"
            + insert_missing_abs_str
            + "\n\n"
            + tex_content[end_line_index + 1 :]
        )
        return modified_tex
    else:
        return tex_content


"""
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
Post process
=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
"""


def mod_inbraket(match):
    """
    修复GPT错误地将LaTeX命令中的标点符号中文化的问题。

    例如：将中文逗号"，"替换为英文逗号","，
    将中文冒号"："替换为英文冒号":"。

    Args:
        match: 正则表达式匹配对象

    Returns:
        修复后的LaTeX命令字符串
    """
    # get the matched string
    cmd = match.group(1)
    str_to_modify = match.group(2)
    # modify the matched string
    str_to_modify = str_to_modify.replace("：", ":")  # 前面是中文冒号，后面是英文冒号
    str_to_modify = str_to_modify.replace("，", ",")  # 前面是中文逗号，后面是英文逗号
    # str_to_modify = 'BOOM'
    return "\\" + cmd + "{" + str_to_modify + "}"


def fix_content(final_tex, node_string):
    """
    修复GPT产生的常见LaTeX错误以提高编译成功率。

    修复的问题包括：
    1. 未转义的百分号
    2. 命令后多余的空格
    3. 中文化的标点符号
    4. 括号不匹配
    5. 错误标记（Traceback）
    6. 下划线未转义

    Args:
        final_tex: GPT返回的LaTeX文本
        node_string: 原始文本（用于错误恢复）

    Returns:
        修复后的LaTeX文本
    """
    final_tex = re.sub(r"(?<!\\)%", "\\%", final_tex)
    final_tex = re.sub(r"\\([a-z]{2,10})\ \{", r"\\\1{", string=final_tex)
    final_tex = re.sub(r"\\\ ([a-z]{2,10})\{", r"\\\1{", string=final_tex)
    final_tex = re.sub(r"\\([a-z]{2,10})\{([^\}]*?)\}", mod_inbraket, string=final_tex)

    if "Traceback" in final_tex and "[Local Message]" in final_tex:
        final_tex = node_string  # 出问题了，还原原文
    if node_string.count("\\begin") != final_tex.count("\\begin"):
        final_tex = node_string  # 出问题了，还原原文
    if node_string.count("\_") > 0 and node_string.count("\_") > final_tex.count("\_"):
        # walk and replace any _ without \
        final_tex = re.sub(r"(?<!\\)_", "\\_", final_tex)

    def compute_brace_level(string):
        """计算字符串中大括号的层级。"""
        brace_level = 0
        for c in string:
            if c == "{":
                brace_level += 1
            elif c == "}":
                brace_level -= 1
        return brace_level

    def join_most(tex_t, tex_o):
        """
        当翻译出现问题时，智能合并翻译文本和原文。

        通过匹配大括号位置，尽可能保留正确的翻译部分，用原文修复错误部分。
        """
        p_t = 0
        p_o = 0

        def find_next(string, chars, begin):
            """在字符串中查找下一个指定字符。"""
            p = begin
            while p < len(string):
                if string[p] in chars:
                    return p, string[p]
                p += 1
            return None, None

        while True:
            res1, char = find_next(tex_o, ["{", "}"], p_o)
            if res1 is None:
                break
            res2, char = find_next(tex_t, [char], p_t)
            if res2 is None:
                break
            p_o = res1 + 1
            p_t = res2 + 1
        return tex_t[:p_t] + tex_o[p_o:]

    if compute_brace_level(final_tex) != compute_brace_level(node_string):
        # 出问题了，还原部分原文，保证括号正确
        final_tex = join_most(final_tex, node_string)
    return final_tex


def compile_latex_with_timeout(command, cwd, timeout=60):
    """
    执行LaTeX编译命令，带有超时保护。

    Args:
        command: 要执行的shell命令
        cwd: 工作目录
        timeout: 超时时间（秒），默认60秒

    Returns:
        bool: 是否成功完成（未超时）
    """
    import subprocess

    process = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        logger.error("Process timed out (compile_latex_with_timeout)!")
        return False
    return True


def run_in_subprocess_wrapper_func(func, args, kwargs, return_dict, exception_dict):
    """
    子进程中运行的包装函数，捕获函数返回值或异常。

    Args:
        func: 要执行的函数
        args: 函数的位置参数
        kwargs: 函数的关键字参数
        return_dict: 用于存储返回值的共享字典
        exception_dict: 用于存储异常的共享字典
    """
    import sys

    try:
        result = func(*args, **kwargs)
        return_dict["result"] = result
    except Exception as e:
        exc_info = sys.exc_info()
        exception_dict["exception"] = exc_info


def run_in_subprocess(func):
    """
    装饰器，将函数放到子进程中运行。

    用于隔离可能内存泄漏的操作（如PyPDF2处理），或防止函数崩溃影响主进程。

    Args:
        func: 要装饰的函数

    Returns:
        包装后的函数
    """
    import multiprocessing

    def wrapper(*args, **kwargs):
        """在子进程中执行被装饰的函数。"""
        return_dict = multiprocessing.Manager().dict()
        exception_dict = multiprocessing.Manager().dict()
        process = multiprocessing.Process(
            target=run_in_subprocess_wrapper_func,
            args=(func, args, kwargs, return_dict, exception_dict),
        )
        process.start()
        process.join()
        process.close()
        if "exception" in exception_dict:
            # ooops, the subprocess ran into an exception
            exc_info = exception_dict["exception"]
            raise exc_info[1].with_traceback(exc_info[2])
        if "result" in return_dict.keys():
            # If the subprocess ran successfully, return the result
            return return_dict["result"]

    return wrapper


def _merge_pdfs(pdf1_path, pdf2_path, output_path):
    """
    合并两个PDF文件，先尝试新方法，失败后使用旧方法。

    Args:
        pdf1_path: 第一个PDF文件路径
        pdf2_path: 第二个PDF文件路径
        output_path: 输出PDF文件路径
    """
    try:
        logger.info("Merging PDFs using _merge_pdfs_ng")
        _merge_pdfs_ng(pdf1_path, pdf2_path, output_path)
    except:
        logger.info("Merging PDFs using _merge_pdfs_legacy")
        _merge_pdfs_legacy(pdf1_path, pdf2_path, output_path)


def _merge_pdfs_ng(pdf1_path, pdf2_path, output_path):
    """
    合并两个PDF文件（新版本），支持链接跳转。

    将两个PDF并排显示在一张页面上（横向拼接），并保留内部和外部链接。

    Args:
        pdf1_path: 第一个PDF文件路径
        pdf2_path: 第二个PDF文件路径
        output_path: 输出PDF文件路径
    """
    import PyPDF2  # PyPDF2这个库有严重的内存泄露问题，把它放到子进程中运行，从而方便内存的释放
    from PyPDF2.generic import NameObject, TextStringObject, ArrayObject, FloatObject, NumberObject

    Percent = 1
    # raise RuntimeError('PyPDF2 has a serious memory leak problem, please use other tools to merge PDF files.')
    # Open the first PDF file
    with open(pdf1_path, "rb") as pdf1_file:
        pdf1_reader = PyPDF2.PdfFileReader(pdf1_file)
        # Open the second PDF file
        with open(pdf2_path, "rb") as pdf2_file:
            pdf2_reader = PyPDF2.PdfFileReader(pdf2_file)
            # Create a new PDF file to store the merged pages
            output_writer = PyPDF2.PdfFileWriter()
            # Determine the number of pages in each PDF file
            num_pages = max(pdf1_reader.numPages, pdf2_reader.numPages)
            # Merge the pages from the two PDF files
            for page_num in range(num_pages):
                # Add the page from the first PDF file
                if page_num < pdf1_reader.numPages:
                    page1 = pdf1_reader.getPage(page_num)
                else:
                    page1 = PyPDF2.PageObject.createBlankPage(pdf1_reader)
                # Add the page from the second PDF file
                if page_num < pdf2_reader.numPages:
                    page2 = pdf2_reader.getPage(page_num)
                else:
                    page2 = PyPDF2.PageObject.createBlankPage(pdf1_reader)
                # Create a new empty page with double width
                new_page = PyPDF2.PageObject.createBlankPage(
                    width=int(
                        int(page1.mediaBox.getWidth())
                        + int(page2.mediaBox.getWidth()) * Percent
                    ),
                    height=max(page1.mediaBox.getHeight(), page2.mediaBox.getHeight()),
                )
                new_page.mergeTranslatedPage(page1, 0, 0)
                new_page.mergeTranslatedPage(
                    page2,
                    int(
                        int(page1.mediaBox.getWidth())
                        - int(page2.mediaBox.getWidth()) * (1 - Percent)
                    ),
                    0,
                )
                if "/Annots" in new_page:
                    annotations = new_page["/Annots"]
                    for i, annot in enumerate(annotations):
                        annot_obj = annot.get_object()

                        # 检查注释类型是否是链接（/Link）
                        if annot_obj.get("/Subtype") == "/Link":
                            # 检查是否为内部链接跳转（/GoTo）或外部URI链接（/URI）
                            action = annot_obj.get("/A")
                            if action:

                                if "/S" in action and action["/S"] == "/GoTo":
                                    # 内部链接：跳转到文档中的某个页面
                                    dest = action.get("/D")  # 目标页或目标位置
                                    # if dest and annot.idnum in page2_annot_id:
                                    # if dest in pdf2_reader.named_destinations:
                                    if dest and page2.annotations:
                                        if annot in page2.annotations:
                                            # 获取原始文件中跳转信息，包括跳转页面
                                            destination = pdf2_reader.named_destinations[
                                                dest
                                            ]
                                            page_number = (
                                                pdf2_reader.get_destination_page_number(
                                                    destination
                                                )
                                            )
                                            # 更新跳转信息，跳转到对应的页面和，指定坐标 (100, 150)，缩放比例为 100%
                                            # “/D”:[10,'/XYZ',100,100,0]
                                            if destination.dest_array[1] == "/XYZ":
                                                annot_obj["/A"].update(
                                                    {
                                                        NameObject("/D"): ArrayObject(
                                                            [
                                                                NumberObject(page_number),
                                                                destination.dest_array[1],
                                                                FloatObject(
                                                                    destination.dest_array[
                                                                        2
                                                                    ]
                                                                    + int(
                                                                        page1.mediaBox.getWidth()
                                                                    )
                                                                ),
                                                                destination.dest_array[3],
                                                                destination.dest_array[4],
                                                            ]
                                                        )  # 确保键和值是 PdfObject
                                                    }
                                                )
                                            else:
                                                annot_obj["/A"].update(
                                                    {
                                                        NameObject("/D"): ArrayObject(
                                                            [
                                                                NumberObject(page_number),
                                                                destination.dest_array[1],
                                                            ]
                                                        )  # 确保键和值是 PdfObject
                                                    }
                                                )

                                            rect = annot_obj.get("/Rect")
                                            # 更新点击坐标
                                            rect = ArrayObject(
                                                [
                                                    FloatObject(
                                                        rect[0]
                                                        + int(page1.mediaBox.getWidth())
                                                    ),
                                                    rect[1],
                                                    FloatObject(
                                                        rect[2]
                                                        + int(page1.mediaBox.getWidth())
                                                    ),
                                                    rect[3],
                                                ]
                                            )
                                            annot_obj.update(
                                                {
                                                    NameObject(
                                                        "/Rect"
                                                    ): rect  # 确保键和值是 PdfObject
                                                }
                                            )
                                    # if dest and annot.idnum in page1_annot_id:
                                    # if dest in pdf1_reader.named_destinations:
                                    if dest and page1.annotations:
                                        if annot in page1.annotations:
                                            # 获取原始文件中跳转信息，包括跳转页面
                                            destination = pdf1_reader.named_destinations[
                                                dest
                                            ]
                                            page_number = (
                                                pdf1_reader.get_destination_page_number(
                                                    destination
                                                )
                                            )
                                            # 更新跳转信息，跳转到对应的页面和，指定坐标 (100, 150)，缩放比例为 100%
                                            # “/D”:[10,'/XYZ',100,100,0]
                                            if destination.dest_array[1] == "/XYZ":
                                                annot_obj["/A"].update(
                                                    {
                                                        NameObject("/D"): ArrayObject(
                                                            [
                                                                NumberObject(page_number),
                                                                destination.dest_array[1],
                                                                FloatObject(
                                                                    destination.dest_array[
                                                                        2
                                                                    ]
                                                                ),
                                                                destination.dest_array[3],
                                                                destination.dest_array[4],
                                                            ]
                                                        )  # 确保键和值是 PdfObject
                                                    }
                                                )
                                            else:
                                                annot_obj["/A"].update(
                                                    {
                                                        NameObject("/D"): ArrayObject(
                                                            [
                                                                NumberObject(page_number),
                                                                destination.dest_array[1],
                                                            ]
                                                        )  # 确保键和值是 PdfObject
                                                    }
                                                )

                                            rect = annot_obj.get("/Rect")
                                            rect = ArrayObject(
                                                [
                                                    FloatObject(rect[0]),
                                                    rect[1],
                                                    FloatObject(rect[2]),
                                                    rect[3],
                                                ]
                                            )
                                            annot_obj.update(
                                                {
                                                    NameObject(
                                                        "/Rect"
                                                    ): rect  # 确保键和值是 PdfObject
                                                }
                                            )

                                elif "/S" in action and action["/S"] == "/URI":
                                    # 外部链接：跳转到某个URI
                                    uri = action.get("/URI")
                output_writer.addPage(new_page)
            # Save the merged PDF file
            with open(output_path, "wb") as output_file:
                output_writer.write(output_file)


def _merge_pdfs_legacy(pdf1_path, pdf2_path, output_path):
    """
    合并两个PDF文件（旧版本），不支持链接跳转。

    将两个PDF并排显示在一张页面上（横向拼接）。

    Args:
        pdf1_path: 第一个PDF文件路径
        pdf2_path: 第二个PDF文件路径
        output_path: 输出PDF文件路径
    """
    import PyPDF2  # PyPDF2这个库有严重的内存泄露问题，把它放到子进程中运行，从而方便内存的释放

    Percent = 0.95
    # raise RuntimeError('PyPDF2 has a serious memory leak problem, please use other tools to merge PDF files.')
    # Open the first PDF file
    with open(pdf1_path, "rb") as pdf1_file:
        pdf1_reader = PyPDF2.PdfFileReader(pdf1_file)
        # Open the second PDF file
        with open(pdf2_path, "rb") as pdf2_file:
            pdf2_reader = PyPDF2.PdfFileReader(pdf2_file)
            # Create a new PDF file to store the merged pages
            output_writer = PyPDF2.PdfFileWriter()
            # Determine the number of pages in each PDF file
            num_pages = max(pdf1_reader.numPages, pdf2_reader.numPages)
            # Merge the pages from the two PDF files
            for page_num in range(num_pages):
                # Add the page from the first PDF file
                if page_num < pdf1_reader.numPages:
                    page1 = pdf1_reader.getPage(page_num)
                else:
                    page1 = PyPDF2.PageObject.createBlankPage(pdf1_reader)
                # Add the page from the second PDF file
                if page_num < pdf2_reader.numPages:
                    page2 = pdf2_reader.getPage(page_num)
                else:
                    page2 = PyPDF2.PageObject.createBlankPage(pdf1_reader)
                # Create a new empty page with double width
                new_page = PyPDF2.PageObject.createBlankPage(
                    width=int(
                        int(page1.mediaBox.getWidth())
                        + int(page2.mediaBox.getWidth()) * Percent
                    ),
                    height=max(page1.mediaBox.getHeight(), page2.mediaBox.getHeight()),
                )
                new_page.mergeTranslatedPage(page1, 0, 0)
                new_page.mergeTranslatedPage(
                    page2,
                    int(
                        int(page1.mediaBox.getWidth())
                        - int(page2.mediaBox.getWidth()) * (1 - Percent)
                    ),
                    0,
                )
                output_writer.addPage(new_page)
            # Save the merged PDF file
            with open(output_path, "wb") as output_file:
                output_writer.write(output_file)


merge_pdfs = run_in_subprocess(_merge_pdfs)  # PyPDF2这个库有严重的内存泄露问题，把它放到子进程中运行，从而方便内存的释放
