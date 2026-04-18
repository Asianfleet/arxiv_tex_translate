SYSTEM_PROMPT = "你是一位专业的翻译人员。"


def build_translate_prompt(more_requirement: str, fragment: str) -> tuple[str, str]:
    extra_requirement = more_requirement or ""
    user_prompt = (
        "下面是一篇英文学术论文的片段，请将其翻译成中文。"
        f"{extra_requirement}"
        "请不要修改任何 LaTeX 命令，比如 \\section, \\cite, \\begin, \\item 和公式。"
        "在中英文交界处（如中文文本与英文单词、数字或 LaTeX 命令之间）添加一个空格分隔，"
        "但绝对不要在中文字符之间添加空格，保持中文文本的连续性。"
        "请注意，翻译时不要添加任何多余的换行符，严格按照原文。"
        "翻译时，请推断论文所属的领域，并参照该领域的译法翻译术语。如果不确定，请保持原文。"
        "只需回复翻译后的文本："
        f"\n\n{fragment}"
    )
    return SYSTEM_PROMPT, user_prompt
