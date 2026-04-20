# arxiv_tex_translate 彻底删除 legacy 逻辑设计

## 1. 背景

当前仓库已经完成核心重构：

- 正式实现集中在 `src/workflow.py`、`src/config/`、`src/latex/`、`src/llm/`、`src/project/`
- 旧路径 `src/main_fns/`、`src/utils.py`、`src/llm_utils.py`、`src/latex_fns/` 主要只剩兼容包装或历史实现

但仓库仍然同时维护两套认知模型：

- 一套是新的流水线架构
- 一套是旧的导入路径、旧的工具层、旧的测试与文档叙述

这会带来三个问题：

1. 维护者很难判断“哪个入口才是正式实现”
2. 删除旧逻辑时容易因为兼容层反向拖住新模块演进
3. 测试和 README 仍然把旧路径当成可用接口，阻碍彻底收敛

本次工作的目标不是继续做“兼容式并存”，而是**物理删除旧逻辑与旧接口，只保留新模块树作为唯一正式实现**。

---

## 2. 目标与非目标

### 2.1 目标

1. **只保留一套正式实现路径**
   - `main.py`
   - `src/workflow.py`
   - `src/config/`
   - `src/latex/`
   - `src/llm/`
   - `src/project/`

2. **彻底删除旧逻辑**
   - 删除 `src/main_fns/`
   - 删除 `src/utils.py`
   - 删除 `src/llm_utils.py`
   - 删除 `src/latex_fns/`

3. **收敛外部接口**
   - `main.py` 直接调用新工作流
   - 不再保留 Python 层旧 API 兼容入口

4. **保持用户可见行为不变**
   - CLI 用法不变
   - `api_key_env` 配置语义不变
   - ArXiv 缓存语义与本地项目缓存语义不变
   - 输出 PDF 与核心中间产物语义不变

5. **同步收敛测试与文档**
   - 测试只验证新正式接口
   - README 只描述新架构

### 2.2 非目标

- 不再尝试保留旧 Python 导入路径的兼容性
- 不新增 GUI、批处理、异步翻译、多语言扩展等范围
- 不在本次工作中改变 CLI 参数设计
- 不以“删除 legacy”为由修改翻译算法或输出格式

---

## 3. 已确认边界

本设计基于以下已确认决定：

- 允许**彻底删除旧导入路径**
- 允许**收敛外部接口**
- 允许删除只为旧接口存在的测试与文档描述
- 不允许改变 CLI 行为与核心产物语义

因此，本次工作的判断标准不是“旧入口还能不能用”，而是：

> **新入口是否已经完整承载全部正式功能。**

---

## 4. 目标架构

删除完成后，仓库的正式架构应收敛为：

```text
main.py
src/
  workflow.py
  config/
  latex/
  llm/
  project/
tests/
docs/
```

### 4.1 唯一正式入口

- CLI 唯一入口：`main.py`
- 工作流唯一入口：`src.workflow.run_translation_workflow`

### 4.2 唯一正式模块树

- `src/config/`
  - 配置模型与加载
- `src/project/`
  - arXiv 下载、解压、缓存目录、工作区准备、输出归档
- `src/latex/`
  - 合并、解析、切分、渲染、恢复、双语、编译
- `src/llm/`
  - Prompt、客户端、批处理、流式能力、模型能力表
- `src/workflow.py`
  - 总编排入口

### 4.3 明确不再存在的模块

- `src/main_fns/`
- `src/utils.py`
- `src/llm_utils.py`
- `src/latex_fns/`

这些路径在删除后不应再作为导入目标、文档入口或测试对象出现。

---

## 5. 删除策略

### 5.1 总原则

删除 legacy 的顺序必须是：

```text
先切入口 -> 再切测试/文档 -> 再物理删除旧模块 -> 最后跑全量验证
```

不能反过来先删文件再边跑边补，这样容易混入临时兼容壳，最后形成“名义删除、实际保留”的伪重构。

### 5.2 具体步骤

#### 第一步：切正式入口

- 修改 `main.py`
- 直接使用 `src.config.load_app_config`
- 直接调用 `src.workflow.run_translation_workflow`
- 去掉 `src.main_fns.workflow.Latex_to_CN_PDF` 路径

#### 第二步：切测试

- 删除或重写所有依赖旧导入路径的测试
- 测试只围绕新模块树与 CLI 行为

#### 第三步：切文档

- README 删除“兼容包装器”“旧入口保留”“旧模块仍可用”等表述
- AGENTS.md 明确新模块树是唯一正式实现

#### 第四步：物理删除旧模块

- 删除 `src/main_fns/`
- 删除 `src/utils.py`
- 删除 `src/llm_utils.py`
- 删除 `src/latex_fns/`

#### 第五步：回归验证

- 跑全量测试
- 做一次 legacy 引用扫描
- 确认没有残留导入

---

## 6. 文件级影响范围

### 6.1 直接修改

- `main.py`
- `README.md`
- `AGENTS.md`
- `tests/` 下的相关测试文件

### 6.2 直接删除

- `src/main_fns/`
- `src/utils.py`
- `src/llm_utils.py`
- `src/latex_fns/`

### 6.3 保留并可能补强

- `src/workflow.py`
- `src/config/*`
- `src/project/*`
- `src/latex/*`
- `src/llm/*`

如果旧模块中仍存在任何未迁移能力，这些能力必须先补入上述新模块，再执行删除。

---

## 7. 测试策略

### 7.1 保留的测试方向

1. **CLI 行为**
   - `main.py` 能正常加载配置并调用新工作流

2. **配置**
   - `api_key_env` 必填
   - 自定义环境变量名可用
   - 禁止 `api_key` 明文字段

3. **工作流**
   - 本地项目输入
   - arXiv 输入
   - 缓存命中
   - 翻译文件与 PDF 输出同步

4. **LaTeX 核心能力**
   - 合并
   - 解析/切分
   - 渲染/修复
   - 编译/恢复
   - 双语输出

5. **LLM 核心能力**
   - OpenAI-compatible 请求
   - 并发判断
   - 顺序稳定性

6. **project 核心能力**
   - arXiv ID/URL 归一化
   - 解压目录下降
   - 运行目录校验

### 7.2 删除的测试方向

- 验证旧模块导入路径仍可用
- 验证旧包装器会转发到新实现
- 验证旧全局配置桥仍可读写
- 验证 legacy 兼容导出列表

### 7.3 回归重点

本次删除最容易回退的功能有两条：

1. **本地项目路径**
2. **arXiv 缓存命中**

因此这两条分支必须在最终回归中单独确认。

---

## 8. 风险与缓解

### 风险 1：`main.py` 切入口后遗漏旧参数拼装细节

缓解：

- 保留 CLI 参数表面行为不变
- 用 CLI 测试与 workflow smoke test 覆盖

### 风险 2：删除 `src/utils.py` / `src/llm_utils.py` 后仍有测试依赖旧全局状态

缓解：

- 删除这些测试而不是继续维护旧桥
- 将确有必要的状态转为新模块内的显式依赖

### 风险 3：删除 `src/latex_fns/` 后仍有未迁移能力

缓解：

- 删除前先做引用扫描
- 一旦发现独占能力，先迁入 `src/latex/`，不保留“临时壳”

### 风险 4：README 与代码状态再次分离

缓解：

- 删除后同步更新 README 和 AGENTS.md
- 把“新模块树是唯一正式实现”写成明确表述

---

## 9. 验收标准

删除完成后必须同时满足：

1. `git grep` 不再出现以下引用：
   - `src.main_fns`
   - `src.latex_fns`
   - `src.llm_utils`
   - `src.utils`

2. 仓库内只剩一套正式实现路径：
   - `main.py`
   - `src/workflow.py`
   - `src/config/`
   - `src/latex/`
   - `src/llm/`
   - `src/project/`

3. CLI 行为不变

4. `api_key_env` 配置语义不变

5. ArXiv/本地缓存语义不变

6. 全量测试通过

7. README 不再描述旧模块为可用接口

8. 删除是物理删除，不是换名保留或再加一层兼容壳

---

## 10. 最终建议

本次“删旧”不应被当成简单的删除文件动作，而应视为一次**正式实现路径收敛**：

> 只有当 `main.py`、测试、文档、模块树都同时收敛到新架构，legacy 删除才算真正完成。

因此，实施时应采用“先切正式入口与测试，再做物理删除”的策略。这样能保证：

- 删除动作可验证
- 新架构成为唯一认知入口
- 后续维护不再受旧兼容层拖累
