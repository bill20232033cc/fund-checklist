# Dayu Agent vs Fund-Checklist 对比研究报告

更新时间：2026-07-11
研究范围：Agent 问答能力、分析报告生成能力、架构层面差距分析
数据来源：dayu-agent GitHub 公开代码（v0.1.4）、fund-checklist 本地代码库

---

## 一、项目定位对比

| 维度 | Dayu Agent | Fund-Checklist |
|------|-----------|----------------|
| **定位** | 买方财报分析 Agent 系统 | 基金年报阅读工具层 |
| **目标用户** | 买方分析师、个人投资者 | 基金研究者 |
| **覆盖市场** | 美股(SEC) / A股(巨潮) / 港股(披露易) | 仅本地基金年报 PDF |
| **核心理念** | "宿主强约束下的 LLM in the loop" | "PDF → 受控文档模型 → 工具服务 → Agent" |
| **产品形态** | CLI + Web(Streamlit) + WeChat | 纯 CLI |
| **代码规模** | ~50,000+ 行（推测） | ~10,000+ 行 |
| **开源状态** | Apache 2.0, 475 stars | 内部项目 |

**核心差距**：Dayu 是一个完整的"投研 Agent 产品"，fund-checklist 是一个"文档阅读工具 MVP"。两者不在同一成熟度层级。

---

## 二、Agent 问答能力差距

### 2.1 对话能力

| 能力 | Dayu | Fund-Checklist | 差距评估 |
|------|------|---------------|---------|
| **单次问答** | `prompt` 命令，Scene 驱动 | `read` 命令，确定性 loop | Dayu 支持自然语言自由提问；fc 只支持固定检索路径 |
| **多轮对话** | `interactive` 终端 + 微信 daemon | 无 | **关键差距**：fc 完全没有多轮对话能力 |
| **会话记忆** | 两层记忆模型（pinned state + episode summary + compaction） | 无 | **关键差距**：fc 无上下文记忆 |
| **Streaming** | SSE 流式输出，实时回显 | 无 | fc 只能等全部完成后输出 |
| **Reasoning 回显** | 支持 Gemini `<thought>` 等 vendor reasoning 协议 | 无 | fc 无思考过程可见性 |

### 2.2 Agent Loop 架构

| 能力 | Dayu | Fund-Checklist | 差距评估 |
|------|------|---------------|---------|
| **Agent 主循环** | `AsyncAgent` 状态机：PrepareIteration → CallRunner → HandleToolBatch / ContinueAnswer / Finalize | `MinimalFundDocumentAgent` 确定性序列 | Dayu 是通用 LLM-driven loop；fc 是硬编码检索序列 |
| **工具调用** | LLM 自主决定调用哪些工具、什么顺序 | 固定顺序：search → section → table | **关键差距**：fc 的 Agent 没有自主决策能力 |
| **失败恢复** | 连续失败时 fallback_mode 降级、压缩后重试、续写 | 基础 fail-closed | Dayu 有完整的失败分级处理 |
| **上下文治理** | `context_budget.py` 软/硬上限、预测性截断、宽字符感知 | 无 | fc 无上下文预算管理 |
| **取消机制** | CancellationToken + CancellationBridge，Runner 全链路协作式取消 | 无 | fc 无法中途取消 |
| **最大迭代降级** | 达到 max_iterations 后移除工具能力，强制直接回答 | 无 | fc 无迭代限制机制 |

### 2.3 LLM 集成

| 能力 | Dayu | Fund-Checklist | 差距评估 |
|------|------|---------------|---------|
| **支持模型** | Mimo / DeepSeek / Gemini / OpenAI / Anthropic / 通义千问 / Ollama / 自定义 | DeepSeek only | Dayu 支持 8+ provider；fc 只有 1 个 |
| **Prompt 系统** | Scene manifest + Prompt Contributions + 条件块 + temperature profiles | 硬编码 prompt 字符串 | Dayu 有声明式 prompt 编排；fc 无 prompt framework |
| **Prompt 模板** | `<when_tool>` / `<when_tag>` 条件块、动态 slot 注入 | 无模板系统 | Dayu 的 prompt 可按场景/公司/行业动态组装 |
| **模型切换** | CLI `--model-name` + workspace config | 环境变量 | Dayu 支持运行时切换；fc 需要改环境变量 |
| **Reasoning 协议** | 统一 reasoning 协议探测（Gemini thought / thinking_config） | 无 | fc 无法利用模型的思考能力 |

### 2.4 工具系统

| 能力 | Dayu | Fund-Checklist | 差距评估 |
|------|------|---------------|---------|
| **文档读取工具** | 7 个（list_sections, read_section, search_document, list_tables, read_table, get_excerpt, read_document） | 7 个（同等能力） | **对等**：fc 的 reading tools 与 Dayu 基本对齐 |
| **联网搜索** | Tavily / Serper / DuckDuckGo | 无 | **关键差距**：fc 无法获取实时信息 |
| **网页抓取** | requests + Playwright 浏览器回退 | 无 | fc 无法访问外部网页 |
| **文件写入** | write_file 工具 | 无 | fc 无法输出文件 |
| **财报下载** | SEC/巨潮/披露易自动下载 | 无 | fc 只能处理本地 PDF |
| **工具注册** | `ToolRegistry` + `@tool()` 装饰器 + ToolsetRegistrar 三层求交 | 硬编码工具列表 | Dayu 工具可插拔；fc 工具固定 |
| **工具超时** | 全局 + 单工具超时控制 | Docling 转换超时 | Dayu 有更细粒度的超时治理 |
| **工具 Trace** | `--enable-tool-trace` 完整调用链追踪 | AgentRunResult.tool_trace | 基本对等 |

### 2.5 差距总结：Agent 问答

**fc 已对齐的能力**：
- 7 个文档读取工具（list_reports, list_sections, read_section, search_document, list_tables, read_table, get_excerpt）
- 工具 trace
- Locator + Citation 输出

**fc 缺失的关键能力**（按优先级排序）：

1. **多轮对话**：无 interactive mode，无会话记忆，无上下文延续
2. **LLM 自主工具调用**：Agent loop 是硬编码序列，不是 LLM-driven
3. **多模型支持**：只有 DeepSeek，无 Mimo/Gemini/OpenAI
4. **联网搜索**：无法获取实时市场信息
5. **Prompt Framework**：无 Scene manifest、无条件块、无动态 prompt 组装
6. **Streaming**：无法实时回显
7. **上下文治理**：无 budget、无 truncation、无 compaction

---

## 三、分析报告生成差距

### 3.1 报告生成流程

| 能力 | Dayu | Fund-Checklist | 差距评估 |
|------|------|---------------|---------|
| **触发方式** | `dayu-cli write --ticker AAPL` | `fund-checklist generate` | 基本对等 |
| **模板系统** | `定性分析模板.md`，分文章骨架/章节骨架/条件项三层 | `fund-analysis-template-draft.md`，8 章固定结构 | Dayu 模板更灵活（条件项、preferred_lens、ITEM_RULE） |
| **写作流程** | infer → 第1-9章 → 第10章 → 第0章 → 来源清单 | 程序数据表格 + LLM 定性分析 | Dayu 是纯 LLM 逐章写作；fc 是程序+LLM 混合 |
| **公司推断** | `infer` 阶段判断公司业务类型、关键约束（facets） | 无 | fc 无公司级特征识别 |
| **章节独立** | 每章独立 LLM 调用，支持单章重写 | 整体生成 | Dayu 支持增量修复；fc 只能整体重生成 |
| **断点恢复** | `--resume` / `--no-resume` | 无 | Dayu 中断后可续写 |
| **审计质量** | 三层审计（程序+LLM+LLM复核），4类22项违规，30%/70%加权 | 审计管道已实现（同等架构） | **基本对等**：fc 的审计管道已对齐 Dayu |
| **修复机制** | PATCH/REGENERATE/NONE 三策略，各最多3次 | PATCH/REGENERATE 策略 | **基本对等** |
| **信号评分** | 无独立信号评分 | 6 项指标，135 分归一化到 100 | **fc 领先**：fc 有独立的确定性信号评分 |
| **渲染输出** | HTML / PDF / Word (Pandoc + Chrome) | JSON / Markdown / PDF | Dayu 输出格式更丰富 |

### 3.2 报告内容质量

| 维度 | Dayu | Fund-Checklist | 差距评估 |
|------|------|---------------|---------|
| **报告结构** | 10 章 + 来源清单（投资要点概览、做的是什么生意、经营表现、竞争格局、管理层、财务分析、估值、风险、是否值得深研） | 8 章（投资要点、产品定义、业绩分析、基金经理、投资者获得感、规模与配置、风险提示、证据小节） | Dayu 面向股票，fc 面向基金；结构不同但各有侧重 |
| **数据来源** | 财报工具 + 联网搜索 + 网页抓取 | 仅年报文档工具 | **关键差距**：fc 数据来源单一 |
| **多年度追踪** | 按 ticker 自动聚合多年财报 | 多年度业绩/持仓/配置/费率聚合 | **基本对等**：fc 的多年度聚合已实现 |
| **证据溯源** | Tool Trace + 来源清单 | Locator + Citation + 证据小节 | **基本对等** |
| **Hallucination 检测** | 审计阶段检测 | `_contains_non_year_numbers()` 检测 | fc 有程序级 hallucination 拦截 |
| **行业差异化** | 条件项 + preferred_lens + ITEM_RULE | 无 | **关键差距**：fc 的报告千篇一律，无行业/公司特化 |

### 3.3 差距总结：报告生成

**fc 已对齐的能力**：
- 三层审计管道（程序+LLM+复核）
- 修复策略（PATCH/REGENERATE）
- 多年度数据聚合
- 证据溯源（Locator + Citation）
- 信号评分（fc 独有优势）

**fc 缺失的关键能力**（按优先级排序）：

1. **多数据源**：只读年报，无法联网搜索、无法读取季报/半年报/公告
2. **行业/公司特化**：模板无条件项，所有基金用同一套分析框架
3. **单章重写**：不支持增量修复，只能整体重生成
4. **公司推断**：无基金类型/风格自动识别
5. **断点恢复**：中断后需从头开始
6. **报告渲染**：无 HTML/Word 输出

---

## 四、架构层面差距

### 4.1 分层架构

| 层级 | Dayu | Fund-Checklist | 评估 |
|------|------|---------------|------|
| **UI** | CLI + Web(Streamlit) + WeChat | CLI only | Dayu 有 3 个入口；fc 只有 1 个 |
| **Service** | PromptService / ChatService / WriteService / FinsService / HostAdminService | FundReadingService（extraction.py 4345行） | Dayu Service 按职责拆分；fc Service 是单体 |
| **Host** | 完整 9 项能力（Session/Run/并发/事件/timeout/cancel/resume/multi-turn/reply outbox） | MinimalHost（最小生命周期） | Dayu Host 是生产级；fc Host 是 MVP 级 |
| **Agent** | AsyncAgent 通用消息执行器 | MinimalFundDocumentAgent 确定性 loop | Dayu Agent 是 LLM-driven；fc Agent 是 deterministic |

### 4.2 关键架构差异

| 架构特性 | Dayu | Fund-Checklist |
|----------|------|---------------|
| **Scene 机制** | 声明式执行策略（manifest JSON），每个 scene 声明 prompt 装配、context slots、模型、temperature、迭代上限、工具集合 | 无 Scene 概念 |
| **Contract 机制** | Service → Execution Contract → Host → Agent Input，三类稳定数据对象 | Service 直接调用 Agent |
| **Prompt Contributions** | 动态 prompt 片段注入（fins_default_subject, base_user） | 无动态 prompt |
| **工具三层求交** | scene manifest ∩ selected_toolsets ∩ execution_permissions | 硬编码工具列表 |
| **会话持久化** | SQLite Session/Run Registry + ConversationMemoryManager | 无持久化 |
| **并发治理** | ConcurrencyGovernor | 无并发控制 |
| **取消桥** | CancellationBridge（进程内 + Host 侧） | 无取消能力 |
| **Reply Outbox** | 可靠投递 + claim/ack/nack 语义 | 无 |
| **Reasoning Protocol** | 统一 vendor reasoning 探测与分离 | 无 |

### 4.3 领域包对比

| 领域能力 | Dayu Fins | Fund-Checklist Fund | 差距 |
|----------|-----------|-------------------|------|
| **下载器** | SEC / 巨潮 / 披露易 | 无 | fc 只能处理本地 PDF |
| **处理器体系** | 优先级降序 fallback（BS processor → edgartools → Docling → Markdown → HTML） | 单一 Docling 路径 | Dayu 有 processor registry + fallback |
| **仓储协议** | 5 个窄协议（Company/Source/Processed/Blob/Maintenance） | FilesystemReportRepository 单体 | Dayu 仓储更细粒度 |
| **Ticker 归一化** | 多格式支持（0700.HK / HK.00700 / 600519.SH / AAPL.US） | 基金代码 + 年份 | Dayu 支持跨市场 ticker |
| **SEC 表单** | 10-K / 10-Q / 20-F / 8-K / 6-K / DEF14A 专项处理 | 不适用 | 领域不同 |
| **多年度聚合** | 按 ticker 自动聚合多年财报 | 按 fund_code + year 聚合 | 基本对等 |

---

## 五、差距根因分析

### 5.1 产品定位差异

fund-checklist 的 AGENTS.md 明确定位为"基金年报阅读工具层"，不是投研 Agent 系统。这是一个**刻意的范围控制**，不是能力缺失。

关键约束（来自 AGENTS.md）：
- "阅读工具层的目标是稳定阅读、检索、返回可引用片段"
- "不是字段抽取、自动报告、投资判断、报告渲染或发布就绪判定"
- "禁止把阅读工具 MVP 扩大成字段抽取、自动报告、投资判断、数据仓库晋升或发布就绪判定"

### 5.2 真正的能力差距（不受定位约束的部分）

即使在"阅读工具层"定位内，fc 仍有以下可改进的差距：

| 差距 | 优先级 | 原因 |
|------|--------|------|
| **LLM 自主工具调用** | P0 | 当前 Agent loop 是硬编码序列，不是真正的 Agent |
| **多轮对话** | P0 | 阅读工具也需要连续追问能力 |
| **多模型支持** | P1 | 只有 DeepSeek，无法利用 Mimo 等更优模型 |
| **上下文治理** | P1 | 长文档问答会超出 context window |
| **Streaming** | P2 | 用户体验问题 |
| **联网搜索** | P2 | 基金分析需要补充市场数据时有用 |
| **Prompt Framework** | P2 | 提升 LLM 回答质量 |

### 5.3 不应追赶的能力（超出定位）

| 能力 | 不追赶原因 |
|------|-----------|
| 自动报告写作 | AGENTS.md 明确禁止在 MVP 内 |
| 多市场下载 | 基金年报不需要 SEC/巨潮/披露易 |
| WeChat/WeChat daemon | 超出阅读工具层范围 |
| 报告渲染（HTML/Word） | 超出阅读工具层范围 |
| 公司推断（infer） | 基金不需要业务类型推断 |

---

## 六、优先级修复建议

### 6.1 Phase 1：Agent 核心能力补齐

**目标**：让 fc 从"确定性检索工具"升级为"真正的 Agent"

1. **LLM-driven Agent Loop**（P0）
   - 参考 Dayu `AsyncAgent` 状态机
   - 实现 LLM 自主决定工具调用顺序
   - 保留 citation/evidence enforcement
   - 实现最大迭代降级

2. **多轮对话**（P0）
   - 参考 Dayu `ChatService` + `ConversationMemoryManager`
   - 实现 interactive CLI mode
   - 最小会话记忆（最近 N 轮 + budget 截断）

3. **多模型支持**（P1）
   - 参考 Dayu `llm_models.json` 配置
   - 接入 Mimo（性价比最优）
   - 实现 `--model-name` CLI 参数

### 6.2 Phase 2：Agent 治理能力

4. **上下文预算治理**（P1）
   - 参考 Dayu `context_budget.py`
   - 实现软/硬上限、预测性截断
   - 长文档问答时自动压缩

5. **Prompt Framework**（P2）
   - 参考 Dayu Scene manifest
   - 实现声明式 prompt 装配
   - 支持按基金类型动态调整 prompt

6. **Streaming**（P2）
   - 参考 Dayu `SSEStreamParser`
   - 实现流式输出

### 6.3 Phase 3：阅读工具增强

7. **联网搜索**（P2）
   - 参考 Dayu `web_tools.py`
   - 接入 Tavily 或 DuckDuckGo
   - 补充市场实时数据

8. **单章重写**（P2）
   - 参考 Dayu `--chapter` 参数
   - 支持增量修复报告

---

## 七、关键结论

1. **fc 的 reading tools 已经与 Dayu 对齐**：7 个文档读取工具 + Locator/Citation + 失败分类体系，这是 fc 的核心竞争力。

2. **fc 的 Agent 能力远落后于 Dayu**：fc 的 Agent 是确定性检索序列，不是 LLM-driven Agent。这是最大的架构差距。

3. **fc 的报告生成已有独特优势**：信号评分（6 项指标）和审计管道（4 类 22 项）是 fc 独有的，Dayu 没有等价物。

4. **差距根因是定位差异**：fc 故意限制在"阅读工具层"，Dayu 是完整的"投研 Agent 系统"。不应盲目追赶 Dayu 的全部能力。

5. **最值得追赶的能力**：LLM-driven Agent loop + 多轮对话 + 多模型支持。这三项能让 fc 从"工具"升级为"Agent"，同时不超出阅读工具层的定位。

---

## 附录：Dayu 关键代码参考

| 能力模块 | 参考文件 |
|----------|---------|
| Agent 主循环 | `dayu/engine/async_agent.py` |
| OpenAI Runner | `dayu/engine/async_openai_runner.py` |
| 工具注册 | `dayu/engine/tool_registry.py` |
| 上下文预算 | `dayu/engine/context_budget.py` |
| Scene manifest | `workspace/config/prompts/manifests/*.json` |
| Prompt 组装 | `dayu/prompting/prompt_composer.py` |
| 会话记忆 | `dayu/host/conversation_memory.py` |
| 财报工具服务 | `dayu/fins/tools/service.py` |
| 文档处理器 | `dayu/engine/processors/docling_processor.py` |
| 写作模板 | `workspace/assets/定性分析模板.md` |
| 审计管道 | `dayu/services/write_service.py` |
