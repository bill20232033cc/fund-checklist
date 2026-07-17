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
| 会话记忆 | 无 | 两层记忆模型 | 🔴 高 |
| 流式输出 | 无 | SSE 流式 | 🟡 中 |
| 联网搜索 | 仅限本地 PDF | Tavily/Serper/Playwright | 🟡 中 |
| 上下文治理 | 无 | 软上限压缩 + 硬上限重试 | 🟡 中 |

### 0.2 设计约束

1. **架构不变**：保持 `UI -> Service -> Host -> Agent` 四层架构
2. **边界不破**：`fund_agent/fund` 仍是领域能力包，不是架构层
3. **渐进式**：每个 Phase 独立可验证，不依赖后续 Phase
4. **向后兼容**：不破坏现有确定性 Agent 路径和报告生成能力

---

### 0.3 Phase 5 前置条件（阻塞项）

> 以下条件未满足前，Phase 5 不得启动。

1. **8 章报告全部非空**：单年 PDF 导入后，`fund-checklist generate` 输出的 8 章报告不得有空章节。含降级声明的章节视为非空。
2. **审计管道数据适配**：审计打分已实现数据完整性感知（data_sources 缺失时 LLM 审计权重降低）。
3. **端到端验证通过**：单年 PDF → import → generate → 8 章非空 → exit code 0。

当前阻塞状态：Phase 3.5（报告质量稳定化）正在实施，上述 3 项均未满足。


## 1. Phase 5：LLM 自主工具调用 + 单次问答

### 1.1 目标

候选目标：若后续裁决通过，再将当前 `LlmToolLoopRunner` 从内部 contract 升级为用户可访问的问答入口，实现 LLM 自主决策工具调用。当前文档不代表已批准实施。

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
│  Host.run_agent_stream(contract)    │
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
- 复用现有 `LlmToolLoopRunner`，不新建 Agent 类
- LLM 工具允许列表扩展为 7 个（新增 `aggregate_multi_year_annual_performance`）
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

#### 1.2.4 LLM 工具允许列表扩展

| 工具 | 当前 | Phase 5 |
|------|------|---------|
| `search_document` | ✅ | ✅ |
| `read_section` | ✅ | ✅ |
| `list_tables` | ✅ | ✅ |
| `read_table` | ✅ | ✅ |
| `get_excerpt` | ✅ | ✅ |
| `aggregate_multi_year_annual_performance` | ❌ | ✅ |
| `extract_fee_rates` | ❌ | ❌ (Service 层方法) |
| `extract_performance_returns` | ❌ | ❌ (Service 层方法) |

**候选口径**：
- 只开放查询类工具，不开放抽取类工具
- 抽取类能力通过 Service 层方法暴露，不直接给 LLM

### 1.3 实施路径

| Slice | 内容 | 依赖 |
|-------|------|------|
| **20A** | Service 层 `ask_question` use case | 8B (DeepSeek adapter) |
| **20B** | CLI `ask` 子命令 | 20A |
| **20C** | Host `run_agent_stream` 方法 | 20A |
| **20D** | 真实 LLM 端到端 smoke | 20B + 20C |

### 1.4 验收标准

```bash
# 单次问答
fund-checklist ask "基金经理是谁？" --document-id <id>
# 期望：exit code 0，answer 包含基金经理信息，citations 存在

# 工具调用追踪
fund-checklist ask "前十大持仓是什么？" --document-id <id> --enable-tool-trace
# 期望：tool_trace 显示 search_document -> read_section -> list_tables -> read_table
```

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

#### 2.2.2 两层记忆模型（简化版）

参考 dayu-agent 的两层记忆模型，简化为：

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

| Slice | 内容 | 依赖 |
|-------|------|------|
| **21A** | Session 数据模型 + 持久化 | 20A |
| **21B** | Service 层 `chat_turn` use case | 21A |
| **21C** | Host 多轮会话托管 | 21B |
| **21D** | CLI `interactive` 子命令 | 21C |
| **21E** | 会话恢复 + label 支持 | 21D |

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

```python
class StreamEventType(Enum):
    CONTENT_DELTA = "content_delta"      # 内容增量
    TOOL_CALL = "tool_call"              # 工具调用开始
    TOOL_RESULT = "tool_result"          # 工具调用结果
    CITATION = "citation"                # 引用信息
    ERROR = "error"                      # 错误
    DONE = "done"                        # 完成

@dataclass
class StreamEvent:
    type: StreamEventType
    payload: Any
    sequence: int
```

**候选口径**：
- 复用 dayu-agent 的 `AppEvent` 模式，简化为 6 种事件类型
- 不实现 `REASONING_DELTA`（推理过程回显）
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
    max_context_tokens: int = 128000
    reserved_for_output: int = 4096
    truncation_threshold: float = 0.9  # 软上限
    hard_limit: float = 0.95           # 硬上限
```

**候选口径**：
- 软上限（90%）：主动压缩历史 turns
- 硬上限（95%）：压缩重试，失败则截断最旧 turns
- 工具结果预测性截断：按 token 估算截断过长结果
- 不实现 episode summary（可选后续）

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

| Slice | 内容 | 依赖 |
|-------|------|------|
| **22A** | StreamEvent 数据模型 | 20A |
| **22B** | Host `run_agent_stream` 方法 | 22A |
| **22C** | CLI `--stream` 流式输出 | 22B |
| **22D** | ContextBudget 上下文预算治理 | 21C |
| **22E** | 工具结果截断策略 | 22D |

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
- 搜索 provider 支持：Tavily / Serper / DuckDuckGo（按优先级回退）
- 网页抓取：requests 优先，Playwright 浏览器回退

#### 4.2.2 Provider 配置

```json
// workspace/config/web_tools.json
{
  "search_providers": {
    "tavily": {"api_key": "${TAVILY_API_KEY}"},
    "serper": {"api_key": "${SERPER_API_KEY}"},
    "duckduckgo": {}
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

| Slice | 内容 | 依赖 |
|-------|------|------|
| **23A** | search_web 工具实现 | 20A |
| **23B** | fetch_web_page 工具实现 | 23A |
| **23C** | 工具权限控制 | 23B |
| **23D** | CLI `--enable-web-search` 参数 | 23C |
| **23E** | 联网搜索端到端 smoke | 23D |

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
│   ├── llm_tool_loop.py          # LLM tool-loop (扩展)
│   ├── deepseek_llm.py           # DeepSeek adapter (保留)
│   ├── context_budget.py         # [新增] 上下文预算治理
│   └── stream_events.py          # [新增] 流式事件模型
├── service/
│   ├── extraction.py             # 现有 Service
│   └── chat_service.py           # [新增] 多轮对话 Service
├── host/
│   ├── minimal_host.py           # 现有 Host (扩展)
│   └── session_store.py          # [新增] 会话持久化
├── cli/
│   ├── main.py                   # CLI 入口 (扩展)
│   └── commands/
│       ├── ask.py                # [新增] ask 子命令
│       └── interactive.py        # [新增] interactive 子命令
└── fund/
    └── document_tools/
        └── web_tools.py          # [新增] 联网搜索工具
```

---

## 6. 风险与缓解

### 6.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 幻觉 | 回答不准确 | 保留确定性路径，LLM 路径强制 citation 校验 |
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
- Slice 20A：Service 层 `ask_question` use case
- Slice 20B：CLI `ask` 子命令
- 不实现 Host 流式，不实现多轮对话

**Phase 6 候选最小版本**：
- Slice 21A：Session 数据模型
- Slice 21B：Service 层 `chat_turn` use case
- Slice 21D：CLI `interactive` 子命令
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
