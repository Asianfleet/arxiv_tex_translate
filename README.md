# ArXiv LaTeX 论文自动翻译工具

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

一个基于大语言模型（LLM）的自动化工具，用于将 ArXiv 英文 LaTeX 论文翻译为中文并重新编译生成 PDF。该项目源自 [GPT-Academic](https://github.com/binary-husky/gpt_academic) 的 LaTeX 翻译插件，提取为独立版本以便使用。

## 核心特性

- **智能 LaTeX 分解**：使用二进制掩码和链表结构精准识别保留区域（公式、图表、命令）和翻译区域（正文、摘要、标题）
- **多线程 GPT 翻译**：支持并发请求，大幅提升翻译效率
- **自动 PDF 编译**：集成 LaTeX 编译流程，自动处理交叉引用和参考文献
- **错误自动修复**：编译失败时自动识别错误行并回滚修复
- **ArXiv 集成**：支持直接输入 ArXiv ID 自动下载源码
- **缓存机制**：支持本地缓存，避免重复下载和翻译

## 工作原理

### 精细分解流程

```
原始 LaTeX → 掩码标记 → 链表转换 → 后处理 → GPT 翻译 → 重组 → PDF 编译
```

1. **掩码初始化**：默认所有内容为 `TRANSFORM`（需翻译）
2. **多层防护标记**：逐步标记保留区域
   - 文档头部（导言区）
   - 数学公式环境（`equation`, `align`, `$$` 等）
   - 图表环境（`figure`, `table` 等）
   - LaTeX 命令（`\section`, `\cite`, `\ref` 等）
3. **反向开放**：精准开放需要翻译的区域（`\caption{}` 内部、`abstract` 环境等）
4. **链表转换**：合并同类节点，生成处理片段
5. **GPT 翻译**：多线程并发翻译文本片段
6. **重组修复**：合并翻译结果，修复常见 LaTeX 错误
7. **PDF 编译**：自动编译并生成最终 PDF

## 安装

### 环境要求

- Python 3.8+
- LaTeX 发行版（TeX Live 或 MiKTeX，需包含 `pdflatex`/`xelatex` 和 `bibtex`）

### 安装步骤

1. **克隆仓库**

```bash
git clone https://github.com/Asianfleet/arxiv_tex_translate.git
cd arxiv_tex_translate
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置 API 密钥**

复制 `config.json.example` 为 `config.json` 并填写配置：

```json
{
    "arxiv": "",
    "model": "qwen-plus",
    "api_key": "your-api-key-here",
    "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "arxiv_cache_dir": "arxiv_cache",
    "default_worker_num": 8,
    "proxies": null,
    "temperature": 1.0,
    "top_p": 1.0
}
```

**支持的模型**：
- OpenAI GPT 系列（`gpt-3.5-turbo`, `gpt-4` 等）
- 通义千问（`qwen-plus`, `qwen-max` 等）
- 其他兼容 OpenAI API 格式的模型

**环境变量方式**（优先级高于配置文件）：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

## 使用说明

### 基本用法

**翻译 ArXiv 论文：**

```bash
# 使用 ArXiv ID
python main.py --arxiv 1812.10695

# 使用 ArXiv 链接
python main.py --arxiv https://arxiv.org/abs/1812.10695
```

**使用自定义配置文件：**

```bash
python main.py --config my_config.json
```

**命令行参数覆盖配置：**

```bash
python main.py --arxiv 1812.10695 --model gpt-4 --advanced_arg "使用学术风格翻译"
```

### 高级用法

**本地 LaTeX 项目翻译：**

```bash
python main.py --arxiv /path/to/your/latex/project
```

**添加额外翻译要求：**

```bash
python main.py --arxiv 1812.10695 --advanced_arg "保持专业术语准确，使用正式学术语言"
```

**禁用缓存（强制重新下载和翻译）：**

```bash
python main.py --arxiv 1812.10695 --advanced_arg "--no-cache"
```

### 配置文件选项

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `arxiv` | ArXiv ID 或链接 | `""` |
| `model` | LLM 模型名称 | `"qwen-plus"` |
| `api_key` | API 密钥 | `""` |
| `llm_url` | API 端点 URL | `"https://dashscope.aliyuncs.com/compatible-mode/v1"` |
| `advanced_arg` | 额外翻译提示词 | `""` |
| `arxiv_cache_dir` | 缓存目录 | `"arxiv_cache"` |
| `default_worker_num` | 并发线程数 | `8` |
| `proxies` | 代理设置 | `null` |
| `temperature` | 模型温度参数 | `1.0` |
| `top_p` | 模型 top_p 参数 | `1.0` |

## 项目结构

```
.
├── main.py                     # 主入口、命令行接口
├── config.json                 # 配置文件
├── config.example.json         # 配置文件示例
├── requirements.txt            # 依赖列表
├── README.md                   # 项目说明文档
├── src/                        # 源代码目录
│   ├── utils.py                # 配置管理和通用工具
│   ├── llm_utils.py            # LLM API 调用和多线程请求处理
│   ├── latex_fns/              # LaTeX 处理模块
│   │   ├── latex_actions.py    # LaTeX分解转换核心逻辑
│   │   ├── latex_toolbox.py    # LaTeX处理工具库
│   │   └── latex_pickle_io.py  # 安全对象序列化
│   └── main_fns/               # 主要功能模块
│       ├── arxiv_utils.py      # ArXiv 下载功能
│       ├── file_manager.py     # 文件管理工具
│       ├── prompts.py          # 翻译提示词模板
│       └── workflow.py         # 翻译工作流控制
└── arxiv_cache/                # 缓存目录
    └── {arxiv_id}/
        ├── extract/            # 解压后的 LaTeX 源码
        ├── workfolder/         # 工作目录（翻译和编译在此进行）
        │   ├── merge.tex       # 合并后的原始文档
        │   ├── merge_translate_zh.tex  # 翻译后的文档
        │   ├── merge_translate_zh.pdf  # 翻译后的 PDF
        │   ├── merge_bilingual.pdf     # 双语对照 PDF
        │   └── debug_log.html  # 调试可视化文件
        └── translation/        # 最终输出目录
            ├── translate_zh.pdf   # 最终翻译 PDF
            └── comparison.pdf     # 双语对比 PDF
```

## 输出文件说明

翻译完成后，在 `arxiv_cache/{arxiv_id}/workfolder/` 目录下会生成以下文件：

| 文件 | 说明 |
|------|------|
| `merge.tex` | 合并后的原始 LaTeX 文档 |
| `merge_translate_zh.tex` | 翻译后的中文 LaTeX 文档 |
| `merge_translate_zh.pdf` | 翻译后的中文 PDF |
| `merge_bilingual.pdf` | 双语对照 PDF（并排显示，原文在左，译文在右） |
| `merge_diff.pdf` | 双语对比 PDF（并排显示差异） |
| `debug_log.html` | 调试文件，可视化标记保留区域（红色）和翻译区域（黑色） |
| `temp.pkl` | 缓存的翻译节点数据（用于调试和重新编译） |
| `merge_result.pkl` | 缓存的翻译结果对象 |

## 技术细节

### 保留区域（不翻译）

以下 LaTeX 元素会被自动识别并保留：

- 文档导言区（`\documentclass` 之前）
- 数学公式环境：`equation`, `align`, `multline`, `$$`, `\[...\]` 等
- 图表环境：`figure`, `table`, `wrapfigure`, `wraptable` 等
- 代码块：`lstlisting`, `algorithm` 等
- LaTeX 命令：`\section`, `\cite`, `\ref`, `\label`, `\bibliography` 等
- 参考文献环境：`thebibliography`
- 复杂嵌套结构（通过大括号层级识别）

### 翻译区域

以下内容会被提取并送给 GPT 翻译：

- 摘要（`abstract` 环境或 `\abstract{}` 命令内部）
- 图表标题（`\caption{}` 内部）
- 正文段落
- 其他纯文本内容

### 后处理修复

翻译完成后，系统会自动修复以下常见问题：

1. 未转义的百分号（`%` → `\%`）
2. 命令后多余空格（`\section {` → `\section{`）
3. 中文化标点符号（中文冒号、逗号转换）
4. 括号不匹配
5. GPT 错误标记（`Traceback` 自动回滚）

### 编译错误自动修复

如果 PDF 编译失败：

1. 从编译日志中提取错误行号
2. 从缓存还原原始节点数据
3. 将错误行及其周围行还原为原文
4. 重新编译（最多重试 32 次）

## 注意事项

### LaTeX 编译要求

- 需要安装完整的 LaTeX 发行版（推荐 TeX Live 2022+）
- 确保 `pdflatex` 或 `xelatex` 以及 `bibtex` 命令在系统 PATH 中
- 如果论文包含中文，系统会自动检测并使用 `xelatex` 编译

### API 费用

- 翻译一篇典型论文（约 20 页）大约需要 50K-100K tokens
- 请确保您的 API 账户有足够的额度
- 使用本地缓存可以避免重复消费

### 翻译质量

- 该工具旨在辅助阅读，翻译结果**不建议直接用于学术发表**
- 专业术语和公式编号可能需要人工校对
- 复杂表格和特殊宏包可能需要手动调整

## 故障排除

### 下载失败

```
ERROR: 无法自动下载该论文的Latex源码
```

- 检查网络连接和代理设置（`proxies` 配置）
- 某些 ArXiv 论文可能没有提供 LaTeX 源码（只有 PDF）
- 尝试手动下载源码并指定本地路径

### 编译失败

```
ERROR: PDF生成失败
```

- 检查 LaTeX 安装是否完整
- 查看 `workfolder/*.log` 文件获取详细错误信息
- 尝试在本地手动编译 `merge_translate_zh.tex` 定位问题
- 某些复杂宏包可能需要额外安装

### API 错误

```
ERROR: API Error: ...
```

- 检查 API 密钥是否正确
- 检查 API 端点 URL 是否可达
- 检查模型名称是否正确
- 查看 API 提供商的额度限制

## 开发计划

- [ ] 支持更多 LLM 提供商（Claude、Gemini 等）
- [ ] 支持双向翻译（中文→英文）
- [ ] 支持更多语言（日文、韩文等）
- [ ] 图形用户界面（GUI）版本
- [ ] 在线版本（Web 服务）

## 致谢

本项目源自 [GPT-Academic](https://github.com/binary-husky/gpt_academic) 项目的 LaTeX 翻译插件，感谢原作者的贡献。

## 许可证

本项目采用 GNU General Public License v3.0 许可证。

## 免责声明

- 本工具生成的翻译内容版权归原作者所有
- 翻译内容的准确性和可靠性无保障，请仔细鉴别并以原文为准
- 请勿删除或修改生成的版权声明

---

**提示**：如果您是论文原作者，欢迎使用本工具辅助中文读者阅读您的作品。如需移除版权声明，请联系作者（见项目 README 中的联系方式）。
