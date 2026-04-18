# arxiv_tex_translate 兼容式重写设计

## 1. 背景

当前仓库的核心目标是：**将 LaTeX 原文件尽可能精准地翻译为中文，并重新编译出可用 PDF，且尽量不破坏原始工程结构与排版行为。**

现有实现已经具备可用能力，但存在以下问题：

- 核心逻辑集中在少数超大文件中，职责边界不清；
- LaTeX 解析、切分、翻译、渲染、编译、错误修复耦合严重；
- 正则与掩码规则直接交织在流程代码中，顺序依赖强，难以维护；
- 全局状态较多，调试和测试成本高；
- 外部行为虽然可用，但内部结构已经明显阻碍后续演进。

本次重写的目标不是做一版“新产品”，而是做一版**外部行为兼容、内部结构可维护、算法显著升级**的新实现。

---

## 2. 目标与非目标

### 2.1 目标

1. **保持外部功能不变**
   - 保留当前 CLI 入口与主要参数；
   - 保留 `config.json` 作为主配置文件；
   - 保留 `arxiv_cache` 目录布局与主要输出文件名；
   - 保留 `merge.tex`、`merge_translate_zh.tex`、`merge_bilingual.tex/.pdf` 等核心产物。

2. **重构为清晰的流水线架构**
   - 借鉴 `LaTeXTrans` 的职责拆分方式；
   - 但不照搬其 TOML、GUI、多项目处理习惯；
   - 仍以当前项目的兼容输出为中心。

3. **升级当前 LaTeX 切分算法**
   - 保留“源码级精确保真”的核心思想；
   - 不再使用原始的“边匹配边写 mask”的方式；
   - 改为“结构发现 → span 规划 → segment 切分 → 原位渲染”的可解释模型。

4. **引入外部库简化解析**
   - 引入 `pylatexenc` 作为辅助解析层；
   - 但不依赖它完全替换当前兼容逻辑；
   - 解析失败时必须存在 fallback。

5. **采用更现代的 Python 写法**
   - 最低 Python 版本提升到 **3.11+**；
   - 广泛使用 `dataclass`、`Enum/StrEnum`、`pathlib.Path`、现代类型标注等语法特性。

### 2.2 非目标

- 不迁移到 `LaTeXTrans` 的 TOML 配置体系；
- 不引入 GUI、Streamlit、多项目批处理等新范围；
- 第一阶段不强行改为异步翻译；
- 不追求“译文文本逐字一致”，验收标准以**产物级一致**为主；
- 不在本次设计中扩展更多语言方向，仍以英文 TeX 精准翻译为中文为主。

---

## 3. 已确认约束

本设计基于以下已确认决策：

- 兼容策略：**严格兼容当前仓库的外部行为**；
- 算法路线：**保留当前掩码/链表思路的核心目标，但重写实现**；
- 验收标准：**产物级一致**；
- Python 版本：**3.11+**；
- 依赖策略：**允许新增少量运行时依赖**；
- 参考项目：主要借鉴 `LaTeXTrans` 的**模块组织与流水线边界**；
- 推进方式：**分阶段原地重构**；
- API Key 策略：
  - `config.json` 中**禁止**出现 `api_key`；
  - 改为配置 `api_key_env`，其值是“用户自定义的环境变量名称”；
  - 运行时读取该环境变量的实际值；
  - 如果检测到旧字段 `api_key`，则**直接报错并停止启动**。

---

## 4. 重写后的总体架构

目标架构借鉴 `LaTeXTrans` 的流水线边界，但保持当前项目的外部契约不变。

建议的主结构如下：

```text
main.py
src/
  runtime.py
  workflow.py
  config/
    models.py
    loader.py
  project/
    arxiv.py
    workspace.py
    outputs.py
  llm/
    client.py
    prompts.py
    batching.py
    retry.py
  latex/
    merge.py
    parser.py
    segmenter.py
    render.py
    sanitize.py
    bilingual.py
    compiler.py
    recovery.py
    models.py
```

### 4.1 各模块职责

- `main.py`
  - 只负责 CLI 参数解析与启动；
  - 不再直接拼装复杂运行参数。

- `src/runtime.py`
  - 负责配置加载、参数归一化、运行选项组织；
  - 输出强类型运行对象。

- `src/workflow.py`
  - 总编排入口；
  - 固定串联：输入解析 → 项目准备 → 合并 TeX → 解析与切分 → 翻译 → 渲染 → 编译 → 归档。

- `src/project/`
  - 负责 arXiv 下载、本地项目准备、`workfolder/logs/outputs` 目录创建与产物归档；
  - 接管当前 `arxiv_utils.py`、`file_manager.py` 的职责。

- `src/latex/merge.py`
  - 负责主 TeX 识别、`\input{}` 展开、注释清理、中文编译宏包注入、abstract 补齐。

- `src/latex/parser.py`
  - 使用 `pylatexenc` 做辅助结构发现；
  - 识别命令、环境、caption、abstract、数学环境等源码位置。

- `src/latex/segmenter.py`
  - 将解析结果与兼容规则合并为 span 计划；
  - 基于 span 计划生成可翻译/不可翻译 segment；
  - 生成 `debug_log.html`。

- `src/llm/`
  - 封装 OpenAI-compatible API 请求、多线程并发、token 裁剪、重试与 prompt 构建。

- `src/latex/render.py`
  - 将译文按原顺序拼回；
  - 执行译文修复、局部回退、AI 提示插入。

- `src/latex/compiler.py`
  - 负责编译器选择、BibTeX、交叉引用、多轮编译、双语 PDF 编译。

- `src/latex/recovery.py`
  - 负责编译失败后的错误行定位与局部回滚重试。

- `src/latex/bilingual.py`
  - 独立负责 `merge_bilingual.tex` 的构造与 caption 双语合并。

---

## 5. 核心数据模型

本次重写的关键不是“多拆几个文件”，而是把当前隐含在流程中的状态显式化。

### 5.1 配置模型

- `AppConfig`
  - `arxiv`
  - `model`
  - `advanced_arg`
  - `llm_url`
  - `api_key_env`
  - `arxiv_cache_dir`
  - `default_worker_num`
  - `proxies`
  - `temperature`
  - `top_p`

- `LLMConfig`
  - 模型名、base url、真实 api key、采样参数、并发参数

- `RunOptions`
  - `input_value`
  - `mode`
  - `no_cache`
  - `more_requirement`

### 5.2 LaTeX 处理模型

- `LatexSpan`
  - `start`
  - `end`
  - `kind`
  - `translatable`
  - `reason`
  - `priority`

- `Segment`
  - `index`
  - `kind`
  - `source_text`
  - `translatable`
  - `line_start`
  - `line_end`
  - `reason`

- `DocumentPlan`
  - `main_tex_path`
  - `merged_tex`
  - `spans`
  - `segments`
  - `title`
  - `abstract`

这种设计用于替代当前 `LinkedListNode + numpy mask + 多处隐式状态` 的组合。

---

## 6. LaTeX 解析与切分算法设计

### 6.1 总体原则

保留旧实现的核心目标：**尽量只翻译正文自然语言，不破坏命令、数学、结构与工程布局。**

但具体实现升级为：

```text
源码 -> 结构发现(parser) -> span 规划(segmenter) -> segment 切分 -> LLM 翻译 -> 原位渲染
```

### 6.2 结构发现：`pylatexenc` + fallback

- 优先使用 `pylatexenc.LatexWalker` 辅助定位：
  - 命令；
  - 环境；
  - 平衡大括号；
  - `caption`、`abstract`、标题等局部结构。

- 解析失败或节点位置不可靠时：
  - fallback 到兼容 regex/brace-scanner 路径；
  - 不允许因为解析库不稳定而中断整个翻译流程。

### 6.3 span 规划替代原始 mask 写入

旧实现的问题在于：

- 匹配与决策耦合；
- 规则顺序强依赖；
- 很难说明“为什么这里被保护/开放”；
- 多层 reverse/open 操作容易互相覆盖。

新实现改为三步：

1. **收集 span**
   - 结构层保护区；
   - 命令层保护区；
   - 开放层翻译区；
   - 兼容特例规则。

2. **统一合并与裁剪**
   - 排序；
   - 解决重叠；
   - 保护优先；
   - 显式开放优先于普通保护。

3. **一次性生成 segment**
   - 根据 span 将源码切成顺序 segment；
   - 每段记录类型、行号、原因。

### 6.4 保护规则分层

建议将当前混杂规则拆成四层：

1. **结构层**
   - preamble；
   - 数学环境；
   - figure/table/algorithm/listing；
   - bibliography；
   - appendix 等结构性区域。

2. **命令层**
   - `\cite`、`\ref`、`\label`、`\bibliography`、`\includegraphics`、`\usepackage` 等。

3. **可翻译开口层**
   - `caption` 内文本；
   - `abstract` 内文本；
   - 必要时标题文本。

4. **兼容特例层**
   - 当前项目已有的 42 行阈值；
   - `hl/hide`；
   - 某些复杂 brace 规则；
   - 当前经验性修复策略。

### 6.5 超长片段切分改进

旧实现按字符长度直接切分，容易出现：

- 切断命令上下文；
- 切断句子；
- 切断中英文混排边界。

新实现按以下优先级切分：

1. 空行段落；
2. 句子边界；
3. token 预算；
4. 最后才做字符级兜底硬切。

---

## 7. 翻译层设计

### 7.1 基本策略

- 第一阶段保留当前**线程池并发**；
- 不强行切换到 async；
- 仍使用 OpenAI-compatible Chat Completions 接口。

### 7.2 Prompt 构造

将当前 `switch_prompt()` 升级为 `PromptBuilder`：

- `build_translate_prompt()`
- `build_proofread_prompt()`

要求：

- 继续支持 `advanced_arg`；
- 继续支持“中英文交界处加空格”等现有约束；
- `--no-cache` 不再通过字符串搜索传播，而在运行时提早结构化解析。

### 7.3 API Key 读取规则

新的密钥规则如下：

1. `config.json` 必须包含 `api_key_env`；
2. `api_key_env` 的值是一个环境变量名，例如：

```json
{
  "api_key_env": "MY_LLM_API_KEY"
}
```

3. 程序启动时读取 `os.environ[api_key_env]`；
4. 如果 `config.json` 中出现 `api_key` 字段：
   - 直接报错并停止；
   - 不做兼容兜底。

---

## 8. 渲染、修复与回滚

### 8.1 渲染策略

不再依赖链表回写，而是按 `Segment` 顺序渲染完整文档：

- 不可翻译段：直接保留原文；
- 可翻译段：先做译文清洗，再决定是否落盘。

### 8.2 译文清洗

保留并模块化当前 `fix_content()` 的能力：

- `%` 转义；
- LaTeX 命令空格修复；
- 括号平衡检查；
- `Traceback/[Local Message]` 检测；
- `\begin` 数量检查；
- 下划线修复。

### 8.3 局部回退

若某段译文存在结构风险：

- 只回退该段原文；
- 不影响其他 segment；
- 回退原因应记录到调试信息中。

### 8.4 编译失败恢复

保留当前策略，但明确模块边界：

- 从 log 中提取错误行；
- 映射回 segment；
- 回滚错误段附近内容；
- 最多重试 32 次。

---

## 9. 编译与双语输出设计

### 9.1 编译

保留当前行为：

- 默认 `pdflatex`；
- 必要时切换 `xelatex`；
- 处理 BibTeX；
- 多轮交叉引用编译；
- 归档核心 PDF 到 `outputs/`。

改进点：

- 尽量使用参数列表代替 `shell=True`；
- 编译步骤拆解为可测试函数；
- 日志与错误信息更明确。

### 9.2 双语输出

保留：

- `merge_bilingual.tex`
- `merge_bilingual.pdf`

但将当前 `BilingualTexMerger` 从超大文件中解耦为独立模块，专门负责：

- 中英正文对照；
- caption 双语合并；
- preamble 兼容处理。

---

## 10. 配置与依赖策略

### 10.1 配置文件

继续保留 `config.json`，但去除敏感信息。

建议的示例结构：

```json
{
  "arxiv": "",
  "model": "qwen-plus",
  "advanced_arg": "",
  "api_key_env": "MY_LLM_API_KEY",
  "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "arxiv_cache_dir": "arxiv_cache",
  "default_worker_num": 8,
  "proxies": null,
  "temperature": 1.0,
  "top_p": 1.0
}
```

### 10.2 依赖

建议新增：

- `pylatexenc`：辅助 LaTeX 结构解析；
- `pytest`：测试框架（开发依赖）。

第一阶段不引入：

- `pydantic`
- `aiohttp`
- GUI 相关新依赖

除非实施阶段证明确有必要。

---

## 11. 分阶段重构计划

### 阶段 1：配置与运行时

- 引入强类型配置模型；
- 迁移 `load_config/get_conf`；
- 完成 `api_key_env` 新规则。

### 阶段 2：项目准备与工作区管理

- 拆出 arXiv 下载、本地项目准备、输出归档；
- 保持缓存目录兼容。

### 阶段 3：TeX 合并与主文件识别

- 迁移 `find_main_tex_file`、`\input` 合并、注释清理、abstract 注入等。

### 阶段 4：解析与切分算法重写

- 建立 `LatexSpan/Segment/DocumentPlan`；
- 引入 `pylatexenc` 辅助解析；
- 以新算法替换当前直接写 mask 的流程。

### 阶段 5：翻译与渲染

- 迁移 prompt、并发请求、译文拼回、免责声明注入。

### 阶段 6：编译与恢复

- 拆出编译器逻辑；
- 保留错误行回滚重试；
- 保留双语 PDF 输出。

### 阶段 7：清理与收尾

- 删除遗留耦合代码；
- 更新 README；
- 补齐测试。

---

## 12. 测试与验收

### 12.1 单元测试

覆盖以下核心能力：

- 主文件识别；
- 注释去除；
- `\input` 合并；
- span 冲突合并；
- caption/abstract 开口；
- segment 切分；
- `fix_content` 修复；
- 编译日志错误行提取。

### 12.2 集成测试

使用小型本地 TeX fixture：

- 不访问真实 LLM；
- 使用 fake translator；
- 验证输出文件名、目录结构、TeX 是否可生成。

### 12.3 验收标准

对同类输入，重写后应满足：

- CLI 参数仍可使用；
- `config.json` 仍是主配置文件；
- 核心输出文件名保持兼容；
- `arxiv_cache` 布局保持兼容；
- 常见样例仍能生成中文 PDF 与双语 PDF；
- 算法可解释、模块职责清晰、代码体量明显下降。

---

## 13. 风险与缓解

### 风险 1：`pylatexenc` 无法覆盖全部 TeX 方言

缓解：

- 仅作为辅助解析器；
- 保留 regex/brace fallback。

### 风险 2：算法改进导致行为漂移

缓解：

- 以产物级兼容为验收目标；
- 逐阶段替换；
- 建立 fixture 测试。

### 风险 3：编译恢复逻辑在新结构中失效

缓解：

- 提前把“错误行 ↔ segment”映射设计为显式能力；
- 保留当前回滚思路，不一次性重写成全新策略。

### 风险 4：范围膨胀

缓解：

- 明确不引入 GUI、TOML、批量任务、async 重构；
- 实施阶段只围绕兼容重构推进。

---

## 14. 最终建议

本项目的最佳重写路径不是“推倒重来”，也不是“只搬文件”，而是：

> **在保持当前外部行为不变的前提下，借鉴 LaTeXTrans 的流水线边界，引入 `pylatexenc` 辅助解析，把当前原始的 mask/链表算法升级为 span planner + segment renderer 的兼容式新内核。**

这样能同时满足：

- 对现有用户几乎无感迁移；
- 内部结构明显清晰；
- 算法比当前实现更稳、更可解释；
- 后续继续扩展测试、验证和规则时不会再回到“大文件堆逻辑”的状态。
