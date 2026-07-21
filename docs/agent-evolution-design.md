# fund-checklist Agent 能力演进方案

> 设计时间：2026-07-15
> 文档定位：候选研究输入材料，不是已承诺 roadmap
> 设计目标：基于 dayu-agent 能力模式，为 fund-checklist 提供渐进式 Agent 能力候选方向
> 关联文档：docs/design.md（设计真源）、docs/implementation-control.md（执行面板）
> 使用边界：本文件不是已裁决 roadmap；任何 `ask`、`interactive`、`streaming`、联网搜索或会话持久化能力，必须先进入 `docs/implementation-control.md` 单独裁决，并遵守 `AGENTS.md` 对 `dayu` 引用和新增 CLI 入口的硬约束

---

## 0. 设计背景

### 0.1 当前能力现状

| 能力维度 | fund-checklist | dayu-agent | 差距 |
|----------|----------------|------------|------|
| Agent 驱动方式 | 当前用户链路偏确定性；内部已有 `LlmToolLoopRunner`，但尚未成为用户问答入口 | LLM 自主决策 | 待定 |
| 多轮对话 | 不支持 | interactive + WeChat | 🔴 高 |
| 会话记忆 | 无 | 单总池 raw turn 回放 + episode summary（Durable Memory 尚未完整实现） | 🔴 高 |
| 流式输出 | 无 | SSE 流式 | 🟡 中 |
| 联网搜索 | 仅限本地 PDF | Tavily/Serper/Playwright | 🟡 中 |
| 上下文治理 | 无 | 软上限压缩 + 硬上限重试 | 🟡 中 |

### 0.2 设计约束

1. **架构不变**：保持 `UI -> Service -> Host -> Agent` 四层架构
2. **边界不破**：`fund_agent/fund` 仍是领域能力包，不是架构层
3. **渐进式**：每个 Phase 独立可验证，不依赖后续 Phase
4. **向后兼容**：不破坏现有确定性 Agent 路径和报告生成能力

---

### 0.3 Phase 5 前置条件（已满足）

> Phase 3.5 已于 2026-07-19 正式关闭，Phase 3.6 已于 2026-07-21 正式关闭。
> 以下三项前置条件均已满足，Phase 5 可从文档审批路径启动：

1. **8 章报告全部非空** ✅：Ch1-6 审计得分全部 ≥75（6/6），端到端验证通过（兴全 163415 5 年 + 安信 004393 3 年）。
2. **审计管道数据适配** ✅：data_sources 缺失时 LLM 审计权重 70%→50%（Phase 3.6 验收数据），数据不足场景通过阈值降至 ≥70。
3. **端到端验证通过** ✅：8/8 章 LLM 分析非空 + 审计产物落盘 + exit code 0（Phase 3.5 验收数据）。

### 0.4 Phase 5 裁决 gate（阻塞项）

> 以下裁决 gate 必须全部通过，Phase 5 实施才能启动：

1. **`ask` 子命令裁决**：`AGENTS.md` §68 要求新增 LLM 驱动 CLI 入口必须另开裁决。
   裁决标准：(a) LLM provider 稳定性足以支撑用户交互；(b) `LlmToolLoopRunner` 的 evidence/citation 校验在真实 LLM 路径无回退；(c) `ask` 不破坏 `read` 子命令的用户心智模型。
2. **Phase 5 整体裁决**：在 `implementation-control.md` 中记录 Phase 5 的 scope、allowed write set、verification commands、stop conditions。


## 1. Phase 5：LLM 自主工具调用 + 单次问答

### 1.1 目标

候选目标：**当且仅当 `ask` 子命令裁决（§0.4 Gate 1）+ Phase 5 整体裁决（§0.4 Gate 2）均通过后**，再将当前 `LlmToolLoopRunner` 从内部 contract 升级为用户可访问的问答入口，实现 LLM 自主决策工具调用。当前文档不代表已批准实施。

### 1.2 设计候选（非已生效裁决）

#### 1.2.1 新增 CLI 入口

```
fund-checklist ask "这份年报的主要风险是什么？" --document-id <id>
```

**候选口径**：
- 新增 `ask` 子命令，与现有 `read` 并存
- `ask` 走 LLM 自主工具调用路径，`read` 保持确定性路径
- 必须指定 `--document-id`，不支持跨文档问答

#### 1.2.2 Agent 路径分层

```
用户输入
  ↓
Service.ask_question(request)
  ↓
┌─────────────────────────────────────┐
│  Host.run_agent(contract)           │
│    ↓                                │
│  LlmToolLoopRunner.run()            │
│    ↓                                │
│  LLM 自主决策工具调用                 │
│  (search/read_section/list_tables)  │
│    ↓                                │
│  FinalAnswer (含 citations)         │
└─────────────────────────────────────┘
  ↓
UI 渲染
```

**候选口径**：
- Phase 5 的核心工作是：将 `LlmToolLoopRunner` 从测试层 fake/injected contract（Slice 8A/8B）升级为 production 可用路径。当前 `LlmToolLoopRunner` 的 25 处实例化全在测试文件中，CLI `read` 命令走 `MinimalFundDocumentAgent`（确定性 Agent），不经过 `LlmToolLoopRunner`
- 升级需要：(a) 验证 `DeepSeekLlmClient` 在真实 PDF + 真实 LLM 场景下的 enforcement 不变；(b) 确认 `AgentRunResult` 的 citation/evidence 四层校验在 LLM-driven 路径上不回退；(c) 处理 LLM 自主工具调用中可能出现的幻觉、越权、无引用等失败场景
- Phase 5 不新建 Agent 类——复用 `LlmToolLoopRunner` 的架构，但补齐 production readiness
- LLM 工具允许列表：6 个 reading tools 开放给 LLM，2 个 extraction tools（`extract_fee_rates`、`extract_performance_returns`）不开放
- 最终回答必须通过现有 citation/evidence 四层校验

#### 1.2.3 Service 层新增 Use Case

```python
class FundReadingService:
    # 现有方法
    def read_local_report(self, request: ReadLocalReportRequest) -> ReadLocalReportResult: ...
    def extract_fee_rates(self, request: ExtractFeeRatesRequest) -> FeeRatesResult: ...

    # 新增方法
    def ask_question(self, request: AskQuestionRequest) -> AskQuestionResult: ...
```

**候选口径**：
- `AskQuestionRequest` 包含 `document_id: str`、`question: str`、`session_id: Optional[str]`
- `AskQuestionResult` 包含 `answer: str`、`citations: tuple[Citation, ...]`、`tool_trace: tuple[ToolTraceEntry, ...]`
- 复用现有 `Host.run_agent_and_wait()` 或新增 `Host.run_agent_stream()`

#### 1.2.4 LLM 工具允许列表

| 工具 | 当前状态 | Phase 5 |
|------|----------|---------|
| `search_document` | ✅ 已有 | ✅ 复用 |
| `read_section` | ✅ 已有 | ✅ 复用 |
| `list_tables` | ✅ 已有 | ✅ 复用 |
| `read_table` | ✅ 已有 | ✅ 复用 |
| `get_excerpt` | ✅ 已有 | ✅ 复用 |
| `aggregate_multi_year_annual_performance` | ✅ 已有（Slice 10K） | ✅ 复用 |
| `extract_fee_rates` | ❌ Service 层方法 | ❌ 不开放 |
| `extract_performance_returns` | ❌ Service 层方法 | ❌ 不开放 |

**候选口径**：
- 只开放查询类工具（reading tools）：LLM 可通过它们获取事实原文和 citation
- 不开放抽取类工具（extraction tools）：extraction contract 是 Service 层受控边界，LLM 不得绕过 Service 层直接消费字段抽取结果
- 理由：字段抽取涉及口径定义（如 10C 的年费率 vs 当期发生金额、10F 的 report_year vs source_period_label）、share class 辨析（A 类 vs C 类销售服务费）、失败分类（not_found vs identity_mismatch vs schema_drift）。这些决策必须由 Service 层显式编排，不能交给 LLM 自主判断

### 1.3 实施路径

> Slice 编号为临时标识（`[Phase5-X]` 格式），正式编号待 Phase 5 进入 `implementation-control.md` 裁决时确定。编号不暗示与 Phase 4 Slice 18/19 的先后关系。

| Slice | 内容 | 依赖 |
|-------|------|------|
| **[Phase5-A]** | `LlmToolLoopRunner` production readiness 评估 | 8B (DeepSeek adapter) |
| **[Phase5-B]** | Service 层 `ask_question` use case | [Phase5-A] |
| **[Phase5-C]** | CLI `ask` 子命令 | [Phase5-B] |
| **[Phase5-D]** | Host 适配 LLM agent 模式 | [Phase5-B] |
| **[Phase5-E]** | 真实 LLM 端到端 smoke | [Phase5-C] + [Phase5-D] |

### 1.4 验收标准

```bash
# 单次问答
fund-checklist ask "基金经理是谁？" --document-id <id>
# 期望：exit code 0，answer 包含基金经理信息，citations 存在

# 工具调用追踪
fund-checklist ask "前十大持仓是什么？" --document-id <id> --enable-tool-trace
# 期望：tool_trace 显示 search_document -> read_section -> list_tables -> read_table
```

**[Phase5-A] production readiness 验收标准**：
- 在真实 DeepSeek 路径下，`AgentRunResult` 的 citation/evidence 四层校验全部通过（不回退到 fallback 60 分）
- LLM 幻觉场景（编造不存在的数据）被 `ProgrammaticAuditor` 正确拦截（P2 检查触发）
- LLM 越权场景（调用不允许的工具）被 `ToolLoopContract` 正确拒绝
- 无引用场景（LLM 回答不包含 citation）被 `evidence` 校验正确拦截

---

## 2. Phase 6：多轮对话 + 会话记忆

### 2.1 目标

候选目标：若 Phase 5 裁决通过，再考虑实现 `fund-checklist interactive` 多轮对话模式，支持会话恢复和上下文记忆。当前文档不代表已批准实施。

### 2.2 设计候选（非已生效裁决）

#### 2.2.1 会话模型

```python
@dataclass
class Session:
    session_id: str
    fund_code: Optional[str]  # 绑定的基金代码
    document_id: Optional[str]  # 绑定的文档
    created_at: datetime
    last_active_at: datetime
    turns: list[Turn]

@dataclass
class Turn:
    role: Literal["user", "assistant"]
    content: str
    citations: tuple[Citation, ...]
    tool_trace: tuple[ToolTraceEntry, ...]
    timestamp: datetime
```

**候选口径**：
- 会话持久化使用 filesystem JSON（与现有 catalog 一致）
- 会话目录：`{work_dir}/sessions/{session_id}.json`
- 不引入 SQLite，不新增外部依赖

##### 2.2.1.1 并发与数据安全声明

**候选口径**：
- **原子写入**：先写临时文件 → `os.replace()` 原子重命名（POSIX 保证），避免写了一半 JSON 崩溃导致整个 session 文件损坏
- **并发限制**：不保证多进程并发安全。interactive 模式同一 label 同时只允许一个实例运行
- **Citation 时效**：Pinned State 中记录 `active_document_id`。当用户在 interactive 中切换到新文档时，旧 citations 仍在 Turn 中保留但不作为新回答的引用源。LLM 需要基于新文档的 tool result 重新生成 citations

#### 2.2.2 受 Dayu 启发但大幅简化的记忆模型

> **Dayu 实际实现**：Pinned State + 单总池（raw turn 回放 + episode summary）+ Raw Transcript 三层结构。Dayu 的 Durable Memory / Retrieval layer 本身也尚未完整实现（dayu README §0 原文："Memory 当前只实现了单总池 raw turn 回放与 episode summary"）。
>
> **本文档简化**：移除 episode summary 和 compaction，仅保留 Pinned State + Recent Turns 两层。Phase 6 首批不实现 episode summary，但需在架构上预留注入点（Pinned State 旁边预留 `summary_block` 字段，触发条件为 recent_turns 超过 10 轮或 token 占比超过 60%）。

简化为：

```
┌─────────────────────────────────────┐
│ Pinned State (钉住状态)              │
│ - 当前 document_id                   │
│ - 基金代码、基金名称                  │
│ - 用户明确约束                        │
│ - 不计入 token budget                │
├─────────────────────────────────────┤
│ Recent Turns (最近 N 轮)             │
│ - 强制保留最近 3 轮                   │
│ - 超出部分按 budget 从新到老回放       │
└─────────────────────────────────────┘
```

**候选口径**：
- Pinned State 包含：`document_id`、`fund_code`、`fund_name`、用户约束
- Recent Turns 强制保留最近 3 轮，超出部分按 token budget 截断
- 不实现 episode summary（Phase 7 可选）

#### 2.2.3 CLI 入口

```
fund-checklist interactive [--document-id <id>]
```

**候选口径**：
- 进入交互式 REPL 模式
- 支持 `--document-id` 预绑定文档
- 支持 `exit` / `quit` 退出
- 支持 `--label` 会话标签（可恢复）

#### 2.2.4 会话恢复

```
fund-checklist interactive --label my-session
# 如果 my-session 存在，恢复上次会话
# 如果不存在，创建新会话
```

**候选口径**：
- 会话标签映射到 `{work_dir}/sessions/{label}.json`
- 恢复时加载历史 turns，重建 Pinned State
- 不实现 pending turn lease（简化版）

### 2.3 实施路径

> Slice 编号为临时标识（`[Phase6-X]` 格式），正式编号待裁决时确定。

| Slice | 内容 | 依赖 |
|-------|------|------|
| **[Phase6-A]** | Session 数据模型 + 持久化 | [Phase5-B] |
| **[Phase6-B]** | Service 层 `chat_turn` use case | [Phase6-A] |
| **[Phase6-C]** | Host 多轮会话托管 | [Phase6-B] |
| **[Phase6-D]** | CLI `interactive` 子命令 | [Phase6-C] |
| **[Phase6-E]** | 会话恢复 + label 支持 | [Phase6-D] |

### 2.4 验收标准

```bash
# 多轮对话
fund-checklist interactive --document-id <id>
> 基金经理是谁？
< 基金经理是张明...
> 他的任期有多长？
< 张明的任期为...

# 会话恢复
fund-checklist interactive --label my-session
# 恢复上次会话，显示历史对话
```

---

## 3. Phase 7：流式输出 + 上下文治理

### 3.1 目标

候选目标：若多轮对话路径成立，再考虑实现 SSE 流式输出和上下文预算治理。当前文档不代表已批准实施。

### 3.2 设计候选（非已生效裁决）

#### 3.2.1 流式事件模型

对齐 dayu-agent 的 `AppEvent` 模式，扩展为 8 种事件类型：

```python
class StreamEventType(Enum):
    CONTENT_DELTA = "content_delta"      # 内容增量
    REASONING_DELTA = "reasoning_delta"  # LLM 推理/思维链增量（可选，部分模型支持）
    TOOL_EVENT = "tool_event"            # 工具调用事件（含子类型：tool_call / tool_result）
    METADATA = "metadata"                # 元数据（含 citation 子类型）
    WARNING = "warning"                  # 非致命告警
    ERROR = "error"                      # 错误
    DONE = "done"                        # 完成

@dataclass
class StreamEvent:
    type: StreamEventType
    payload: Any
    sequence: int
```

**候选口径**：
- 直接对齐 dayu-agent 的 `AppEvent` 模式，保持 8 种事件类型
- `TOOL_EVENT` 合并了原来的 `TOOL_CALL` 和 `TOOL_RESULT`，通过 payload 中的子类型区分
- `METADATA` 的 citation 子类型替代了原来的独立 `CITATION` 事件
- `REASONING_DELTA` 可选实现——取决于 LLM provider 是否支持 reasoning 内容回显（DeepSeek 支持，Mimo 待确认）
- 事件通过 `AsyncIterator[StreamEvent]` 返回

#### 3.2.2 Host 流式支持

```python
class Host:
    # 现有方法
    def run_agent_and_wait(self, contract: ExecutionContract) -> AppResult: ...

    # 新增方法
    def run_agent_stream(self, contract: ExecutionContract) -> AsyncIterator[StreamEvent]: ...
```

**候选口径**：
- 新增 `run_agent_stream` 方法，返回异步迭代器
- 内部调用 `AsyncAgent.run_messages()`，转发 `StreamEvent`
- 保持 `run_agent_and_wait` 向后兼容

#### 3.2.3 CLI 流式输出

```
fund-checklist ask "主要风险是什么？" --document-id <id> --stream
```

**候选口径**：
- 默认同步输出（向后兼容）
- `--stream` 启用流式输出
- 流式输出格式：逐字打印，工具调用显示 `[调用 search_document...]`

#### 3.2.4 上下文预算治理

```python
@dataclass
class ContextBudget:
    max_context_tokens: int = 128000  # 默认值；优先从模型配置读取
    reserved_for_output: int = 4096
    truncation_threshold: float = 0.9  # 软上限
    hard_limit: float = 0.95           # 硬上限

    @classmethod
    def from_model_config(cls, model_name: str) -> "ContextBudget":
        """从模型元数据读取上下文窗口大小。

        不同模型上下文窗口不同（DeepSeek 128K，Mimo 可能不同），
        优先使用 LLM adapter 提供的模型元数据，而非硬编码默认值。
        """
        ...
```

**候选口径**：
- `max_context_tokens` 优先从 LLM adapter 的模型元数据读取，硬编码 128000 仅作 fallback
- 软上限（90%）：主动压缩历史 turns
- 硬上限（95%）：压缩重试，失败则截断最旧 turns
- 工具结果预测性截断：按 token 估算截断过长结果
- 不实现 episode summary（可选后续）

#### 3.2.4.1 Token 用量追踪

**候选口径**：
- `HostRunResult` 增加 `total_tokens` 汇总（`prompt_tokens` + `completion_tokens`）
- `ToolTraceEntry` 增加 `token_usage`（单次工具调用的 token 消耗）
- 不实现计费系统，但记录基础用量供开发调试和用户感知
- CLI `ask` 命令在 verbose 模式下展示每次问答的 token 用量
- token 估算优先使用 LLM provider 返回的 `usage` 字段（DeepSeek API 有 `usage.prompt_tokens`），而非手工估算公式

#### 3.2.5 工具结果截断策略

```python
def estimate_tokens(text: str) -> int:
    """保守 token 估算：中文 1 字 ≈ 2 token，英文 1 词 ≈ 1.5 token"""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    english_words = len(text.split()) - chinese_chars
    return chinese_chars * 2 + int(english_words * 1.5)

def truncate_tool_result(result: str, max_tokens: int) -> str:
    """截断工具结果到指定 token 数"""
    if estimate_tokens(result) <= max_tokens:
        return result
    # 按比例截断，保留开头和结尾
    ...
```

**候选口径**：
- 工具结果单次最大 8000 token（约 4000 中文字）
- 超出部分按比例截断，保留开头和结尾
- 截断后添加 `[...已截断...]` 标记

### 3.3 实施路径

> Slice 编号为临时标识（`[Phase7-X]` 格式），正式编号待裁决时确定。
>
> **前置条件**：当前 `MinimalHost.run()` 为同步方法（`threading.Thread` + `join(timeout)`），`DeepSeekLlmClient` 的 payload 中 `stream: False` 硬编码。Phase 7 需先完成 MinimalHost 的异步化升级，再实现流式事件转发。如果 Phase 5 的 `ask` 命令响应延迟过长（多轮工具调用 >10s），应考虑将流式输出提前到 Phase 5 实现，但这会增加 Phase 5 的复杂度——此为 Phase 5 裁决时需明确的范围决策。

| Slice | 内容 | 依赖 |
|-------|------|------|
| **[Phase7-A]** | MinimalHost 异步化 + DeepSeekLlmClient 支持 `stream=True` | [Phase5-B] |
| **[Phase7-B]** | StreamEvent 数据模型 | [Phase7-A] |
| **[Phase7-C]** | Host `run_agent_stream` 方法 | [Phase7-B] |
| **[Phase7-D]** | CLI `--stream` 流式输出 | [Phase7-C] |
| **[Phase7-E]** | ContextBudget 上下文预算治理 | [Phase6-C] |
| **[Phase7-F]** | 工具结果截断策略 | [Phase7-E] |

### 3.4 验收标准

```bash
# 流式输出
fund-checklist ask "主要风险是什么？" --document-id <id> --stream
# 期望：逐字输出，工具调用有提示

# 长对话上下文治理
fund-checklist interactive --document-id <id>
> 问题1
< 回答1
> 问题2
< 回答2
... (持续 20+ 轮)
> 最后一个问题
< 正常回答，不因上下文超限而失败
```

---

## 4. Phase 8：联网搜索 + 实时数据（可选）

### 4.1 目标

候选目标：仅在产品方向明确需要实时外部数据时再考虑，不作为当前优先方向。当前文档不代表已批准实施。

### 4.2 设计候选（非已生效裁决）

#### 4.2.1 搜索工具

```python
@tool
def search_web(query: str, max_results: int = 5) -> SearchResult:
    """联网搜索"""
    ...

@tool
def fetch_web_page(url: str) -> WebPageContent:
    """抓取网页内容"""
    ...
```

**候选口径**：
- 新增 `search_web` 和 `fetch_web_page` 两个工具
- 搜索 provider 支持：Tavily / Serper（按优先级回退）。DuckDuckGo 不适用于中文基金信息检索（索引极差），已从 provider 列表移除
- 网页抓取：requests 优先，Playwright 浏览器回退
- 联网搜索场景限定为：(a) 补充全球宏观指标（英文源）；(b) 获取基金公告原文（如巨潮资讯网）；(c) 不依赖联网搜索获取基金净值/排名等实时金融数据

#### 4.2.2 Provider 配置

```json
// workspace/config/web_tools.json
{
  "search_providers": {
    "tavily": {"api_key": "${TAVILY_API_KEY}"},
    "serper": {"api_key": "${SERPER_API_KEY}"}
  },
  "fetch": {
    "timeout_seconds": 30,
    "use_playwright_fallback": true
  }
}
```

**候选口径**：
- 配置文件存放搜索 provider API key
- 支持环境变量覆盖
- 不实现 storage state 管理（简化版）

#### 4.2.3 工具权限控制

```python
@dataclass
class ToolPermissions:
    allow_web_search: bool = False
    allow_web_fetch: bool = False
    allowed_domains: list[str] = []  # 空 = 全部允许
    blocked_domains: list[str] = []  # 黑名单
```

**候选口径**：
- 默认禁止联网搜索（安全考虑）
- 通过 `--enable-web-search` CLI 参数显式启用
- 支持域名白名单/黑名单

#### 4.2.4 联网搜索与本地问答的融合

```
用户问题："这只基金最近的市场表现如何？"
  ↓
Agent 判断需要联网搜索
  ↓
调用 search_web("基金名称 最新净值 表现")
  ↓
获取搜索结果，结合本地年报数据
  ↓
生成综合回答
```

**候选口径**：
- LLM 自主决定是否需要联网搜索
- 联网搜索结果与本地数据分开引用
- 联网搜索结果标记为 `[网络来源]`，本地数据标记为 `[年报]`

### 4.3 实施路径

> Slice 编号为临时标识（`[Phase8-X]` 格式），正式编号待裁决时确定。

| Slice | 内容 | 依赖 |
|-------|------|------|
| **[Phase8-A]** | search_web 工具实现 | [Phase5-B] |
| **[Phase8-B]** | fetch_web_page 工具实现 | [Phase8-A] |
| **[Phase8-C]** | 工具权限控制 | [Phase8-B] |
| **[Phase8-D]** | CLI `--enable-web-search` 参数 | [Phase8-C] |
| **[Phase8-E]** | 联网搜索端到端 smoke | [Phase8-D] |

### 4.4 验收标准

```bash
# 联网搜索
fund-checklist ask "这只基金最近的市场表现如何？" --document-id <id> --enable-web-search
# 期望：answer 包含网络搜索结果和本地年报数据，citations 分别标记来源

# 权限控制
fund-checklist ask "..." --document-id <id>
# 期望：不调用 search_web，只使用本地数据
```

---

## 5. 整体架构演进

### 5.1 架构对比

```
当前架构：
┌─────┐    ┌─────────┐    ┌──────┐    ┌──────────────────┐
│ CLI │───→│ Service │───→│ Host │───→│ DeterministicAgent│
└─────┘    └─────────┘    └──────┘    └──────────────────┘

Phase 5 后：
┌─────┐    ┌─────────┐    ┌──────┐    ┌─────────────────┐
│ CLI │───→│ Service │───→│ Host │───→│ LlmToolLoopRunner│
│ ask │    │         │    │      │    │ (LLM 自主决策)    │
└─────┘    └─────────┘    └──────┘    └─────────────────┘

Phase 6 后：
┌─────────────┐    ┌─────────┐    ┌──────┐    ┌─────────────────┐
│ CLI         │───→│ Service │───→│ Host │───→│ LlmToolLoopRunner│
│ interactive │    │ chat()  │    │ 多轮 │    │ (LLM 自主决策)    │
└─────────────┘    └─────────┘    └──────┘    └─────────────────┘

Phase 7 后：
┌─────────────┐    ┌─────────┐    ┌──────┐    ┌─────────────────┐
│ CLI         │───→│ Service │───→│ Host │───→│ LlmToolLoopRunner│
│ --stream    │    │ chat()  │    │ 流式 │    │ (LLM 自主决策)    │
└─────────────┘    └─────────┘    │ 预算 │    └─────────────────┘
                                  └──────┘

Phase 8 后：
┌─────────────┐    ┌─────────┐    ┌──────┐    ┌─────────────────┐
│ CLI         │───→│ Service │───→│ Host │───→│ LlmToolLoopRunner│
│ --web       │    │ chat()  │    │ 流式 │    │ (LLM 自主决策)    │
└─────────────┘    └─────────┘    │ 预算 │    │ + 联网搜索        │
                                  └──────┘    └─────────────────┘
```

### 5.2 关键设计原则

1. **确定性路径保留**：`read` 子命令保持确定性 4 步序列，用于精确查询
2. **LLM 路径新增**：`ask` / `interactive` 走 LLM 自主决策，用于自由问答
3. **边界不破**：`fund_agent/fund` 仍是领域能力包，不承担 Agent 逻辑
4. **渐进式交付**：每个 Phase 独立可验收，不依赖后续 Phase

### 5.3 文件结构演进

```
fund_agent/
├── agent/
│   ├── tool_loop.py              # 确定性 Agent (保留)
│   ├── llm_tool_loop.py          # LLM tool-loop (扩展: production readiness)
│   ├── deepseek_llm.py           # DeepSeek adapter (扩展: stream=True)
│   ├── context_budget.py         # [新增] 上下文预算治理
│   └── stream_events.py          # [新增] 流式事件模型
├── service/
│   ├── extraction.py             # 现有 Service (保留)
│   └── chat_service.py           # [新增] 多轮对话 Service
├── host/
│   ├── minimal_host.py           # 现有 Host (扩展: 异步化 + session 托管)
│   └── session_store.py          # [新增] 会话持久化
├── cli/
│   ├── main.py                   # CLI 入口 (扩展: ask/interactive)
│   └── commands/
│       ├── ask.py                # [新增] ask 子命令
│       └── interactive.py        # [新增] interactive 子命令
└── fund/
    └── document_tools/
        └── web_tools.py          # [新增] 联网搜索工具
```

**演化映射表**：

| 目标文件 | 类型 | 来源 |
|----------|------|------|
| `agent/llm_tool_loop.py` | 扩展 | 现有 Slice 8A — 新增 production readiness 校验 |
| `agent/deepseek_llm.py` | 扩展 | 现有 Slice 8B — 新增 `stream=True` 支持 |
| `agent/context_budget.py` | 新增 | 无现有文件 |
| `agent/stream_events.py` | 新增 | 无现有文件 |
| `service/chat_service.py` | 新增 | 与现有 `extraction.py` 并列，不替代 |
| `host/minimal_host.py` | 扩展 | 现有 Slice 12A — 新增 `run_agent_stream()` 和 session 托管 |
| `host/session_store.py` | 新增 | 无现有文件 |
| `cli/main.py` | 扩展 | 现有 — 新增 `ask` 和 `interactive` 子命令 |

---

## 6. 风险与缓解

### 6.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 幻觉 | 回答不准确 | 保留确定性路径，LLM 路径强制 citation 校验 |
| LLM 幻觉放大投资建议风险 | LLM 自主路径更易产生隐性投资建议 | 保留 4 层 citation/evidence 校验；`AgentRunResult` 增加投资建议关键词检测（复用审计管道 C3 规则） |
| LLM 调用成本 | 每次 `ask` 产生 API 费用，多轮对话放大 | Token 用量追踪（见 §3.2.4.1）；默认限制单次最大工具调用步数（≤8）；交互式模式提示用户当前轮 token 消耗 |
| 响应延迟 | 多步工具调用（search→read→answer）延迟 3-10s | 流式输出减少感知等待（Phase 7 前置）；首轮 show-thinking 状态提示 |
| 上下文超限 | 长对话失败 | 实现上下文预算治理，软上限压缩 |
| 联网搜索不可靠 | 结果不稳定 | 默认禁止，显式启用，域名白名单 |
| 会话持久化失败 | 数据丢失 | 文件系统 JSON，原子写入 |

### 6.2 架构风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 破坏现有确定性路径 | 回归 | 保留 `read` 子命令，`ask` 独立路径 |
| Service 层膨胀 | 维护困难 | 拆分 `chat_service.py`，单一职责 |
| Host 层复杂化 | 调试困难 | 渐进式扩展，每步验证 |

---

## 7. 候选优先级（仅对照观察）

### 7.1 候选探索顺序（仅示意）

```
Phase 5 (LLM 自主工具调用)
  ↓
Phase 6 (多轮对话 + 会话记忆)
  ↓
Phase 7 (流式输出 + 上下文治理)
  ↓
Phase 8 (联网搜索，可选)
```

### 7.2 候选最小版本（仅示意，未纳入正式排期）

以下 Slice 划分仅为示意性分解，不代表已进入排期、已批准开发或已分配资源。仅用于说明“若后续裁决通过，可能按怎样粒度拆分验证”。

**Phase 5 候选最小版本**：
- [Phase5-A]：`LlmToolLoopRunner` production readiness 评估
- [Phase5-B]：Service 层 `ask_question` use case
- [Phase5-C]：CLI `ask` 子命令
- 不实现 Host 流式，不实现多轮对话

**Phase 6 候选最小版本**：
- [Phase6-A]：Session 数据模型
- [Phase6-B]：Service 层 `chat_turn` use case
- [Phase6-D]：CLI `interactive` 子命令
- 不实现会话恢复，不实现 label 支持

---

## 8. 总结

本文件用于对照观察 fund-checklist 从"确定性分析助手"向"可交互投资分析 Agent"的候选演进方向，不代表已批准实施：

| Phase | 候选能力 | 观察到的差异 |
|-------|----------|----------------|
| **Phase 5** | LLM 自主工具调用 | 用户可自由提问，不再受限于固定查询 |
| **Phase 6** | 多轮对话 + 会话记忆 | 支持追问、上下文保持，提升交互体验 |
| **Phase 7** | 流式输出 + 上下文治理 | 实时反馈、长对话支持，接近生产级体验 |
| **Phase 8** | 联网搜索 | 获取实时数据，扩展分析维度 |

如果后续进入正式裁决，可按“不破坏现有架构、按候选方向逐步验证”的方式推进；但各方向是否、何时推进，不以本文件为准。
