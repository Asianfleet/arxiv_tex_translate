import os
import time
import random
import numpy as np
from loguru import logger
from concurrent.futures import ThreadPoolExecutor

from .llm.batching import can_multi_process as _can_multi_process
from .llm.model_info import get_max_token_for_model, model_info
from .llm.streaming import (
    get_reduce_token_percent,
    predict_no_ui_long_connection,
    trimmed_format_exc,
)
from .llm.batching import translate_segments

def input_clipping(inputs, history, max_token_limit, return_clip_flags=False):
    """
    截断输入文本和历史记录以满足token限制。

    当输入和历史记录的总token数超过限制时，会逐步截断历史记录中的内容。

    Args:
        inputs: 当前输入文本
        history: 历史对话记录列表
        max_token_limit: 最大token数限制
        return_clip_flags: 是否返回截断标志信息

    Returns:
        如果return_clip_flags为False，返回(inputs, history)
        如果return_clip_flags为True，返回(inputs, history, flags)
    """
    enc = model_info["gpt-3.5-turbo"]['tokenizer']
    def get_token_num(txt): return len(enc.encode(txt, disallowed_special=()))

    mode = 'input-and-history'
    input_token_num = get_token_num(inputs)
    original_input_len = len(inputs)
    if input_token_num < max_token_limit//2:
        mode = 'only-history'
        max_token_limit = max_token_limit - input_token_num

    everything = [inputs] if mode == 'input-and-history' else ['']
    everything.extend(history)
    full_token_num = n_token = get_token_num('\n'.join(everything))
    everything_token = [get_token_num(e) for e in everything]
    everything_token_num = sum(everything_token)
    delta = max(everything_token) // 16

    while n_token > max_token_limit:
        where = np.argmax(everything_token)
        encoded = enc.encode(everything[where], disallowed_special=())
        clipped_encoded = encoded[:len(encoded)-delta]
        everything[where] = enc.decode(clipped_encoded)[:-1]
        everything_token[where] = get_token_num(everything[where])
        n_token = get_token_num('\n'.join(everything))

    if mode == 'input-and-history':
        inputs = everything[0]
        full_token_num = everything_token_num
    else:
        full_token_num = everything_token_num + input_token_num

    history = everything[1:]

    flags = {
        "mode": mode,
        "original_input_token_num": input_token_num,
        "original_full_token_num": full_token_num,
        "original_input_len": original_input_len,
        "clipped_input_len": len(inputs),
    }

    if not return_clip_flags:
        return inputs, history
    else:
        return inputs, history, flags

def can_multi_process(llm) -> bool:
    """
    判断指定的LLM模型是否支持多线程并发请求。

    Args:
        llm: LLM模型名称

    Returns:
        是否支持多线程
    """
    return _can_multi_process(llm)

def request_llm_multi_threads(
        inputs_array, inputs_show_user_array, llm_kwargs,
        history_array, sys_prompt_array,
        max_workers=-1,
        handle_token_exceed=True,
        retry_times_at_unknown_error=2,
        ):
    """
    多线程并发请求GPT模型，高效处理大量文本片段。

    该函数使用线程池并发执行多个GPT请求，支持自动重试、token溢出处理、
    超时检测等功能。

    Args:
        inputs_array: 输入文本数组
        inputs_show_user_array: 显示给用户的输入标签数组
        llm_kwargs: LLM参数字典
        history_array: 每个请求的历史记录数组
        sys_prompt_array: 每个请求的系统提示词数组
        max_workers: 最大工作线程数，-1表示使用配置默认值
        handle_token_exceed: 是否处理token溢出问题
        retry_times_at_unknown_error: 未知错误时的重试次数

    Returns:
        GPT响应集合列表，格式为[输入1, 响应1, 输入2, 响应2, ...]
    """

    if max_workers == -1:
        try:
            max_workers = int(llm_kwargs.get("default_worker_num", 8))
        except Exception:
            max_workers = 8
        if max_workers <= 0:
            max_workers = 3
    if not can_multi_process(llm_kwargs['llm_model']):
        max_workers = 1

    executor = ThreadPoolExecutor(max_workers=max_workers)
    n_frag = len(inputs_array)

    logger.info(f"多线程请求已启动，共 {n_frag} 个片段")

    mutable = [["", time.time(), "等待中"] for _ in range(n_frag)]
    watch_dog_patience = 5

    def _req_gpt(index, inputs, history, sys_prompt):
        """单个GPT请求的内部函数，支持重试和错误处理。"""
        gpt_say = ""
        retry_op = retry_times_at_unknown_error
        exceeded_cnt = 0
        mutable[index][2] = "执行中"
        detect_timeout = lambda: len(mutable[index]) >= 2 and (time.time()-mutable[index][1]) > watch_dog_patience
        while True:
            if detect_timeout(): raise RuntimeError("检测到程序终止。")
            try:
                gpt_say = predict_no_ui_long_connection(
                    inputs=inputs, llm_kwargs=llm_kwargs, history=history,
                    sys_prompt=sys_prompt, observe_window=mutable[index], console_silence=True
                )
                mutable[index][2] = "已成功"
                return gpt_say
            except ConnectionAbortedError as token_exceeded_error:
                if handle_token_exceed:
                    exceeded_cnt += 1
                    p_ratio, n_exceed = get_reduce_token_percent(str(token_exceeded_error))
                    MAX_TOKEN = get_max_token_for_model(llm_kwargs.get("llm_model"))
                    EXCEED_ALLO = 512 + 512 * exceeded_cnt
                    inputs, history = input_clipping(inputs, history, max_token_limit=MAX_TOKEN-EXCEED_ALLO)
                    gpt_say += f'[Local Message] 警告，文本过长将进行截断，Token溢出数：{n_exceed}。\n\n'
                    mutable[index][2] = f"截断重试"
                    continue
                else:
                    tb_str = '```\n' + trimmed_format_exc() + '```'
                    gpt_say += f"[Local Message] 警告，线程{index}在执行过程中遭遇问题, Traceback：\n\n{tb_str}\n\n"
                    mutable[index][2] = "输入过长已放弃"
                    return gpt_say
            except Exception as e:
                if detect_timeout(): raise RuntimeError("检测到程序终止。")
                tb_str = '```\n' + trimmed_format_exc() + '```'
                logger.error(f"线程{index}报错: {e}")
                gpt_say += f"[Local Message] 警告，线程{index}在执行过程中遭遇问题, Traceback：\n\n{tb_str}\n\n"
                if retry_op > 0:
                    retry_op -= 1
                    wait = random.randint(5, 20)
                    for i in range(wait):
                        mutable[index][2] = f"等待重试 {wait-i}"
                        time.sleep(1)
                    if detect_timeout(): raise RuntimeError("检测到程序终止。")
                    mutable[index][2] = f"重试中 {retry_times_at_unknown_error-retry_op}/{retry_times_at_unknown_error}"
                    continue
                else:
                    mutable[index][2] = "已失败"
                    time.sleep(5)
                    return gpt_say

    futures = [executor.submit(_req_gpt, index, inputs, history, sys_prompt) for index, inputs, history, sys_prompt in zip(
        range(len(inputs_array)), inputs_array, history_array, sys_prompt_array)]

    while True:
        time.sleep(2.0)
        worker_done = [h.done() for h in futures]
        for thread_index, _ in enumerate(worker_done):
            mutable[thread_index][1] = time.time()

        finished_cnt = sum(worker_done)
        logger.info(f"多线程进度: {finished_cnt} / {n_frag}")

        if all(worker_done):
            executor.shutdown()
            break

    gpt_response_collection = []
    for inputs_show_user, f in zip(inputs_show_user_array, futures):
        gpt_res = f.result()
        gpt_response_collection.extend([inputs_show_user, gpt_res])

    return gpt_response_collection
