"""
提示词管理模块 - 处理不同处理模式的GPT提示词切换。
"""


def switch_prompt(pfg, mode, more_requirement):
    """
    根据处理模式切换GPT提示词。

    Args:
        pfg: LatexPaperFileGroup实例，包含文件内容
        mode: 处理模式，'proofread_en'英文校对或'translate_zh'翻译中文
        more_requirement: 额外的提示词要求

    Returns:
        tuple: (输入文本数组, 系统提示词数组)
    """
    n_split = len(pfg.sp_file_contents)
    if mode == 'proofread_en':
        inputs_array = [r"Below is a section from an academic paper, proofread this section." +
                        r"Do not modify any latex command such as \section, \cite, \begin, \item and equations. " + more_requirement +
                        r"Answer me only with the revised text:" +
                        f"\n\n{frag}" for frag in pfg.sp_file_contents]
        sys_prompt_array = ["You are a professional academic paper writer." for _ in range(n_split)]
    elif mode == 'translate_zh':
        inputs_array = [
            r"下面是一篇英文学术论文的片段，请将其翻译成中文。" + more_requirement +
            r"请不要修改任何 LaTeX 命令，比如 \section, \cite, \begin, \item 和公式。" +
            r"请用一个空格分隔中文、英文和 LaTeX 命令。" +
            r"翻译时，请推断论文所属的领域，并参照该领域的译法翻译术语。如果不确定，请保持原文。" +
            r"只需回复翻译后的文本：" +
            f"\n\n{frag}" for frag in pfg.sp_file_contents]
        sys_prompt_array = ["你是一位专业的翻译人员。" for _ in range(n_split)]
    else:
        assert False, "未知指令"
    return inputs_array, sys_prompt_array
