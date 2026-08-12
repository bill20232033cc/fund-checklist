# fund-checklist Agent 能力演进方案

> 状态：设计候选研究材料（2026-07-15 创建，2026-07-28 最后更新），非设计真源。`docs/design.md` 已明确本文仅作候选研究输入材料。§0.1 / §8.1 的现状与差距表为 2026-07-28 快照：对话历史注入、memory 注入、ContextBudget 接入 runner 均已在 Phase 7.3 / 2026-08-09 P1 / Phase 7.1 完成；Phase 9 联网搜索已裁决不采用；唯一仍开放的候选是 Phase 8 跨轮预算治理（见 §7.1）。最新研究见 `docs/research/dayu-agent-r-research-20260810.md`；fc 当前状态以 `docs/implementation-control.md` 为准。

> 设计时间：2026-07-15 | 最后更新：2026-07-28
> 文档定位：候选研究输入材料 + 已裁决能力记录
> 设计目标：基于 dayu-agent 能力模式，为 fund-checklist 提供渐进式 Agent 能力候选方向
> 关联文档：docs/design.md（设计真源）、docs/implementation-control.md（执行面板）、.sisyphus/plans/phase5-implementation.md（Phase 5 正式计划）
> 使用边界：Phase 5（`ask` + streaming）已裁决并进入实施；`interactive`、上下文治理、联网搜索、会话持久化仍为候选，必须先进入 `docs/implementation-control.md` 单独裁决

---

## 0. 设计背景

### 0.1 当前能力现状

| 能力维度 | fund-checklist | dayu-agent | 差距 |
|----------|----------------|------------|------|
| Agent 驱动方式 | `LlmToolLoopRunner` — LLM 自主决策工具调用（Phase 5 已完成） | LLM 自主决策 | ✅ 已对齐 |
| 多轮对话 | `interactive` CLI 已实现（Phase 7）；**对话历史已注入 LLM context（Phase 7.3，2026-07-29，方案 B prompt 层编织）** | interactive + WeChat，历史完整注入 | ✅ 已对齐 |
| 会话记忆 | Session 模型 + PinnedState + Turn + EpisodeSummary + SessionStore 已实现；**memory slot 已注入 LLM（2026-08-09 P1：EpisodeSummary ≤3 条 + confirmed_facts）** | 两层记忆（pinned + 统一池） | ✅ 已对齐 |
| 流式输出 | StreamEvent + SSE 解析（Phase 5 已完成） | SSE 流式 | ✅ 已对齐 |
| 联网搜索 | 仅限本地 PDF | Tavily/Serper/Playwright | ⛔ 不采用（产品边界与合规决策，2026-08-10 研究收口） |
| 上下文治理 | ContextBudgetState 软/硬限制已接入 runner（Phase 7.1，2026-07-27）；**跨轮预算治理仍开放** | 软上限压缩 + 硬上限重试 + 预测性截断 | 🟡 唯一开放候选（Phase 8） |
| Prompt 装配 | SceneConfig + Fragments + Context Slots（Phase 7 已完成）；条件块支持有限 | SceneDefinition + PromptAssemblyPlan + 条件块 + PromptContributions | 🟡 基础已通，条件块缺失 |
| 温度透传 | ✅ 已修复 — SceneConfig → DeepSeekLlmClient(temperature) | 模型级温度配置 | ✅ 已对齐 |

### 0.2 架构定位（2026-07-28 DS Review 确认）

> DS Review 结论：fund-checklist 当前架构是 **fail-closed tool-enforced retrieval pipeline**，不是多轮自主 agent。

**核心特征**：
- 每次 `runner.run()` 完全独立，LLM 只看到 system + user 两条消息
- `_final_result` 强制 JSON + citation 三重校验（evidence → citation → key_fact）
- 适用于 `ask` 命令（单次受控 Q&A），不适用于多轮对话

**两条完全分离的 LLM 路径**：

| 路径 | 入口 | LLM 调用 | 校验 | 使用场景 |
|------|------|---------|------|---------|
| tool loop | `chat_service.chat_turn()` | `runner.run() → next_step()` | `_final_result` 三重校验 | ask, interactive, repair, regenerate, fix |
| generate/audit | `audit_pipeline._generate_chapter_content()` | `llm_client.generate_text()` | 无校验，直接文本生成 | generate 8 章, audit 审计 |

**关键结论**：改 `_final_result` 只影响 tool loop 路径，不影响 generate/audit。

### 0.3 设计约束

1. **架构不变**：保持 `UI -> Service -> Host -> Agent` 四层架构
2. **边界不破**：`fund_agent/fund` 仍是领域能力包，不是架构层
3. **渐进式**：每个 Phase 独立可验证，不依赖后续 Phase
4. **向后兼容**：不破坏现有确定性 Agent 路径和报告生成能力

---

### 0.4 Phase 5 前置条件（已满足）

> Phase 3.5 已于 2026-07-19 正式关闭，Phase 3.6 已于 2026-07-21 正式关闭。
> 以下三项前置条件均已满足，Phase 5 可从文档审批路径启动：

1. **8 章报告全部非空** ✅：Ch1-6 审计得分全部 ≥75（6/6），端到端验证通过（兴全 163415 5 年 + 安信 004393 3 年）。
2. **审计管道数据适配** ✅：data_sources 缺失时 LLM 审计权重 70%→50%（Phase 3.6 验收数据），数据不足场景通过阈值降至 ≥70。
3. **端到端验证通过** ✅：8/8 章 LLM 分析非空 + 审计产物落盘 + exit code 0（Phase 3.5 验收数据）。

### 0.5 Phase 5 裁决 gate（阻塞项）

> ~~以下裁决 gate 必须全部通过，Phase 5 实施才能启动：~~
>
> **2026-07-24 更新：Phase 5 全部 Gate 已通过，已进入实施阶段。**

1. ~~**`ask` 子命令裁决**~~ → ✅ 已裁决通过（2026-07-22）
2. ~~**Phase 5 整体裁决**~~ → ✅ 已写入 `implementation-control.md`（2026-07-22），2026-07-24 更新为 19A-19F 计划


## 1. Phase 5：LLM 自主工具调用 + 单次问答 + 流式输出

> **状态：已裁决（2026-07-24），正式计划见 `.sisyphus/plans/phase5-implementation.md`**
> 流式输出已从原 Phase 7 前置并入 Phase 5（裁决理由：ask 命令响应延迟 >10s 时流式输出减少感知等待）。

### 1.1 目标

**已裁决**：将当前 `LlmToolLoopRunner` 从内部 contract 升级为用户可访问的问答入口，实现 LLM 自主决策工具调用 + 流式输出。

### 1.2 设计详情（已裁决）

> 正式计划编号：19A-19F，详见 `.sisyphus/plans/phase5-implementation.md`

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

> ~~Slice 编号为临时标识（`[Phase5-X]` 格式）~~ → 正式编号已确定为 19A-19F，详见 `.sisyphus/plans/phase5-implementation.md`。

| Slice | 内容 | 依赖 | 状态 |
|-------|------|------|------|
| **19A** | StreamEvent 数据模型 + LlmToolLoopRunner production readiness | — | 待启动 |
| **19B** | DeepSeekLlmClient `stream=True` + SSE 解析 | 19A | 待启动 |
| **19C** | MinimalHost `run_agent_stream()` | 19A, 19B | 待启动 |
| **19D** | Service 层 `ask_question`（含 profile routing） | 19A | 待启动 |
| **19E** | CLI `ask` 子命令（流式默认） | 19C, 19D | 待启动 |
| **19F** | 端到端 smoke + read 回归 + 全量回归 | 19E | 待启动 |

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

## 2. Phase 7：多轮对话 + 会话记忆（原 Phase 6，重编号）

> **2026-07-24 更新**：因 `implementation-control.md` 的 Phase 6（模板框架适配）已占用编号，本节重编号为 Phase 7。
> **2026-07-27 更新**：Phase 7（interactive CLI + Session 模型 + Scene Config）、Phase 7.1（ContextBudget + ToolResult 信封）、Phase 7.2（交互体验增强 + 修复能力激活）已全部完成。但 **对话历史注入 LLM context 的管道尚未实现**——这是当前最关键差距。详见 §2.5。

### 2.1 目标

已裁决目标（2026-07-25）：实现 `fund-checklist interactive` 多轮对话模式，支持会话恢复和上下文记忆。

**当前状态**：interactive CLI 可用，Session 持久化可用，但 LLM 每轮只能看到 system prompt + 当前 user message，**无法看到历史对话**。多轮对话退化为一系列独立 Q&A。

### 2.2 设计裁决（已生效）

#### 2.2.1 会话模型

```python
@dataclass
class Session:
    session_id: str
    created_at: datetime
    last_active_at: datetime
    turns: list[Turn]
    pinned_state: PinnedState
    episode_summaries: list[EpisodeSummary]
    compacted_turn_count: int
    label: Optional[str]

@dataclass
class PinnedState:
    fund_code: Optional[str]
    available_document_ids: list[str]
    active_document_id: Optional[str]
    active_year: Optional[int]
    user_constraints: dict[str, Any]

@dataclass
class Turn:
    role: Literal["user", "assistant"]
    content: str
    citations: tuple[Citation, ...]
    tool_trace: tuple[ToolTraceEntry, ...]
    timestamp: datetime

@dataclass
class EpisodeSummary:
    title: str
    goal: str
    confirmed_facts: list[str]
    open_questions: list[str]
    next_step: str
```

**裁决口径**：
- 会话持久化使用 filesystem JSON（与现有 catalog 一致）
- 会话目录：`{work_dir}/sessions/{session_id}.json`
- 不引入 SQLite，不新增外部依赖

##### 2.2.1.1 并发与数据安全声明

**裁决口径**：
- **原子写入**：先写临时文件 → `os.replace()` 原子重命名（POSIX 保证），避免写了一半 JSON 崩溃导致整个 session 文件损坏
- **并发限制**：不保证多进程并发安全。interactive 模式同一 label 同时只允许一个实例运行
- **Citation 时效**：Pinned State 中记录 `active_document_id`。当用户在 interactive 中切换到新文档时，旧 citations 仍在 Turn 中保留但不作为新回答的引用源。LLM 需要基于新文档的 tool result 重新生成 citations

#### 2.2.2 三层记忆模型（已实现）

> **Dayu 实际实现**：Pinned State + 单总池（raw turn 回放 + episode summary）+ Raw Transcript 三层结构。Dayu 的 Durable Memory / Retrieval layer 本身也尚未完整实现（dayu README §0 原文："Memory 当前只实现了单总池 raw turn 回放与 episode summary"）。
>
> **fund-checklist 当前实现**：三层记忆模型已全部实现（Session + PinnedState + Turn + EpisodeSummary），但 **memory contribution 未注入 LLM context**。`_build_contributions()` 只构建 `runtime` 和 `fund_context`，不构建 `memory` slot。

当前实现的三层结构：

```
┌─────────────────────────────────────────┐
│ Pinned State (钉住状态)                  │
│ - fund_code, active_document_id, year   │
│ - available_document_ids                │
│ - user_constraints                      │
│ - 不计入 token budget                   │
├─────────────────────────────────────────┤
│ Recent Turns (最近 N 轮)                │
│ - user/assistant 交替                    │
│ - 含 citations 和 tool_trace             │
├─────────────────────────────────────────┤
│ Episode Summaries (压缩摘要)             │
│ - episode_id, title, goal               │
│ - confirmed_facts, open_questions       │
│ - 由 LLM 驱动的异步压缩生成              │
└─────────────────────────────────────────┘
```

**已裁决口径**：
- 会话持久化使用 filesystem JSON（`{work_dir}/sessions/{session_id}.json`）
- 原子写入：临时文件 → `os.replace()`
- Pinned State 不参与 token 池竞争
- Episode Summary 由 `compaction.md` 模板驱动的 LLM 异步生成

**关键缺失**：这三层数据**从未被编译成 LLM messages**。Session turns 存储在 JSON 中，但 `_request_payload()` 只构造 system + 当前 user 两条消息。

#### 2.2.3 CLI 入口

```
fund-checklist interactive [--document-id <id>]
```

**裁决口径**：
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

**裁决口径**：
- 会话标签映射到 `{work_dir}/sessions/{label}.json`
- 恢复时加载历史 turns，重建 Pinned State
- 不实现 pending turn lease（简化版）

#### 2.2.5 对话历史注入管道（⚠️ 关键缺失）

> **2026-07-27 诊断确认**：这是当前 interactive 模式无法真正"对话"的根本原因。

**现状**：`deepseek_llm.py` 的 `_request_payload()` 构造的消息列表只有 2 条：

```python
messages = [
    {"role": "system", "content": system_prompt},      # fragments + contributions 拼成
    {"role": "user", "content": json.dumps({            # 仅当前轮
        "document_id": "...",
        "query": "基金经理是谁",
        "prior_tool_results": []
    })}
]
```

`session.turns` 中的历史轮次**从未被注入**。LLM 每轮都是"失忆"的——它看不到之前的问答，无法做代词消解、无法维持对话流。

**dayu 的对标方案**：`DefaultConversationMemoryManager.build_messages()` 按四段固定顺序编译消息列表：

```
1. System Prompt                          → system role
2. [Conversation Memory] 块               → system role
   ├── Pinned State（反幻觉锚点）
   └── Episode Summaries（从新到老按预算填充）
3. Working Memory（最近 N 轮 user/assistant） → user/assistant roles
4. 当前 user 消息                          → user role
```

**修复方案**：

```python
# chat_service.py: chat_turn() 中收集历史轮次
history_messages = []
for turn in session.turns[-12:]:  # 最近 12 条（6 轮）
    history_messages.append({
        "role": turn.role,
        "content": turn.content,
    })

# deepseek_llm.py: _request_payload() 接受 history_messages
def _request_payload(*, ..., history_messages=None):
    messages = [{"role": "system", "content": system_prompt}]
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": json.dumps({...})})
    return {"messages": messages, ...}
```

**涉及文件**：
- `fund_agent/service/chat_service.py` — 从 `session.turns` 收集历史
- `fund_agent/agent/deepseek_llm.py` — `_request_payload` 接受 `history_messages`
- `fund_agent/agent/llm_tool_loop.py` — `LlmToolLoopRunner.run()` 传递 history

#### 2.2.6 跨轮工具结果不可见（⚠️ 关键缺失）

即使注入了 `session.turns` 历史轮次，LLM 仍然**看不到上轮的工具调用结果**。`ToolResult` 仅存在于 `runner.run()` 的局部循环中，run 结束后即销毁。

**影响**：
- 用户追问"那托管费呢"时，LLM 看不到上轮 `read_table` 的结果，必须重新 `search → read_section → read_table`
- 重新读取可能得到不同的截断结果，导致引用不一致
- 浪费工具调用预算（interactive 的 `max_steps=20`）

**dayu 的方案**：工具结果折叠为摘要文本，存入 `assistant` 消息的文本中（不是独立的 `tool` role 消息）。`_build_full_working_turn_view()` 将 `tool_uses` 追加到 `assistant_text`。

**修复方案（分两步）**：

第一步（简单）：注入 history 时，assistant 消息保留原始 answer 文本（含事实信息），不注入 tool results。LLM 可从回答文本中引用之前提到的数据。

第二步（完整）：在 `Turn` 中存储 `tool_results_summary`，注入 history 时作为 assistant 消息的附加块：

```python
# session_models.py: Turn 增加字段
@dataclass
class Turn:
    role: str
    content: str
    tool_results_summary: str = ""  # 新增：工具结果摘要
    ...

# chat_service.py: 构建 history 时附加工具摘要
for turn in session.turns[-12:]:
    content = turn.content
    if turn.role == "assistant" and turn.tool_results_summary:
        content += f"\n\n[工具结果]\n{turn.tool_results_summary}"
    history_messages.append({"role": turn.role, "content": content})
```

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

## 3. Phase 8：上下文治理（流式已并入 Phase 5）

> **2026-07-24 更新**：流式输出（§3.2.1 StreamEvent 模型、§3.2.2 DeepSeek stream、§3.2.3 CLI 流式输出）已裁决并入 Phase 5（Slice 19A-19E）。
> 本节剩余内容为上下文预算治理，重编号为 Phase 8。

### 3.1 目标

候选目标：在 Phase 5（ask + streaming）和 Phase 7（多轮对话）基础上，实现上下文预算治理，支持长对话不超限。当前文档不代表已批准实施。

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

## 4. Phase 9：联网搜索 + 实时数据（可选，原 Phase 8，重编号）

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
Phase 5 (LLM 自主工具调用 + 流式输出) — ✅ 已完成
  ↓
Phase 6 (模板框架适配 + 基金类型感知) — ✅ 已完成
  ↓
Phase 7 (多轮对话 + 会话记忆) — ✅ 已完成
  ↓
Phase 7.3 (对话历史注入 LLM context) — ✅ 已完成（2026-07-29）
  ↓
Phase 8 (跨轮上下文治理 + Episode Summary 压缩) — 🔵 唯一仍开放候选（Episode Summary 已接入，跨轮预算治理留 TODO）
  ↓
Phase 9 (联网搜索，可选) — ⛔ 关闭（产品边界与合规决策，不采用）
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

本文件记录 fund-checklist 从"确定性分析助手"向"可交互投资分析 Agent"的演进过程：

| Phase | 能力 | 状态 | 关键缺口 |
|-------|------|------|---------|
| **Phase 5** | LLM 自主工具调用 + 流式输出 | ✅ 已完成 | — |
| **Phase 6** | 模板框架适配 + 基金类型感知 | ✅ 已完成 | — |
| **Phase 7** | 多轮对话 + 会话记忆 | ✅ 基础完成 | 对话历史未注入 LLM context（§2.2.5） |
| **Phase 7.1** | ContextBudget + ToolResult 信封 | ✅ 已完成 | — |
| **Phase 7.2** | 交互体验增强 + 修复能力激活 | ✅ 已完成（含 e2e 测试） | — |
| **Phase 7.3** | 对话历史注入 LLM context | ✅ 已完成（2026-07-29） | `build_messages()` 管道 + 跨轮证据；DS Review 二审修正：方案 B 40-60 行（首选），方案 A 100-130 行 |
| **Phase 8** | 跨轮上下文治理 + 压缩 | 🔵 候选 | Episode Summary 接入 LLM context |
| **Phase 9** | 联网搜索 | 🔵 候选 | — |

### 8.1 dayu 对标关键差距（2026-07-27 更新）

> 状态更新（2026-08-11）：本表为 2026-07-27 快照。P0 两项（对话历史 / 跨轮工具结果不可见）已由 Phase 7.3 方案 B 解决；P1 两项（Memory Contribution / Pinned State 不注入）已由 2026-08-09 P1 记忆注入解决；P2/P3 项仍未实施，均未列入当前排期。

从 dayu-agent 架构分析提炼的差距，按优先级排列：

| 优先级 | 差距 | dayu 方案 | fc 现状 | 修复路径 |
|--------|------|----------|---------|---------|
| **P0** | 对话历史不注入 LLM | `build_messages()` 四段编译 | `_request_payload` 仅 system + user | §2.2.5 修复方案（DS：同一根因的两个表现） |
| **P0** | 跨轮工具结果不可见 | 工具结果折叠为 assistant 消息文本 | ToolResult 在 run() 结束后销毁 | §2.2.6 修复方案（DS：根因同上） |
| **P1** | Memory Contribution 未接入 | `select_prompt_contributions()` 按 slot 筛选 | `_build_contributions` 不构建 memory slot | 接入 `prompt_contributions.py` |
| **P1** | Pinned State 不注入 LLM | 独立 system 块，不参与 token 池 | Session.pinned_state 存在但不注入 | §2.2.5 memory 块 |
| **P2** | Prompt 条件块 | `<when_tool>` / `<when_tag>` 按工具快照过滤 | 仅 `<when_missing>` 条件块 | 扩展 `prompt_renderer.py` |
| **P2** | Host/Executor 层 | Run 注册表 + 取消桥 + 并发许可 | CLI 直调 ChatService | 重构 host 层 |
| **P3** | PendingTurn 恢复 | resume_lease + CAS 状态机 | 无断连恢复 | 新增 pending_turn_store |

### 8.2 Phase 7.3 修复方案对比（2026-07-28 DS Review 二审）

P0 的两个问题是同一个根因的两个表现：`_request_payload → LlmClientProtocol` 管道上没有历史通道。修了管道，两个问题一起解决。

#### 被低估的 4 个复杂度（DS 二审确认）

| 复杂度 | 影响 | DS 判断 |
|--------|------|---------|
| Protocol 级联效应 | `LlmClientProtocol` 被 5 处引用（DeepSeekLlmClient、FakeLlmClient、runner.run/run_stream），签名变更需同步所有实现者 | 真实存在，但原 DS 估计已注明"含协议变更"，Controller 重新包装为"遗漏"不够公允 |
| 代词消解 / citation 跨轮 | scene.md 有 6 条对话规则，但 LLM 从未看到历史，规则形同虚设 | 成立 |
| citation 校验场景感知 | `_final_result()` 含 5 层严格校验，对非数据性问题（"继续说"）会误杀 | 成立，**但方案 B 天然规避此问题** |
| 测试复杂度 | 3 个 e2e test class 全部 xfail，原因正是"LLM 返回'最终回答缺少受控 citation'" | 成立 |

**Controller 遗漏**：方案 B（prompt 层编织）不改动 `runner.run()`，citation 校验逻辑完全不受影响。历史轮次混入 system prompt，LLM 仍只看当前轮的 tool results，`_final_result()` 仍校验当前轮的 evidence → citation。方案 B 反而比方案 A 更安全。

**方案 A：协议层注入（文档原方案）**

改动 `LlmClientProtocol.next_step()` 签名，新增 `history_messages` 参数。

| 文件 | 变更 | 风险 |
|------|------|------|
| `chat_service.py` | 从 session.turns 收集历史轮次 | 低风险 |
| `deepseek_llm.py` | `_request_payload` 接受 history_messages | 低风险 |
| `llm_tool_loop.py` | `LlmClientProtocol.next_step()` 签名变更 | **breaking change** — 破坏所有实现者（FakeLlmClient、测试注入点） |

- 改动量：100-130 行（DS 逐文件计数：Protocol 签名 5 行 + DeepSeek 适配 35 行 + FakeLlmClient 3 行 + runner 透传 20 行 + chat_service 25 行 + 测试 mock 30 行）
- 优点：架构干净，历史轮次作为一等公民
- 缺点：breaking change，需同步更新所有测试 mock；需要在 runner 层面决定何时 strict/relaxed citation 校验

**方案 B：Prompt 层编织（DS 提出的替代方案）**

在 `chat_service` 层将历史轮次直接编织进 system prompt（作为 composed prompt 的附加块），完全不改变 agent 层协议。

| 文件 | 变更 | 风险 |
|------|------|------|
| `chat_service.py` | `_build_contributions` 增加 history slot | 低风险 |
| `prompt_composer.py` | 支持 history contribution 注入 | 低风险 |
| `llm_tool_loop.py` | 无变更 | 零风险 |

- 改动量：40-60 行
- 优点：零 breaking change，变更安全；**天然规避 citation 校验问题**（不改动 runner.run()，_final_result() 校验逻辑完全不受影响，历史轮次混入 system prompt 但 LLM 仍只看当前轮的 tool results）
- 缺点：历史轮次混入 system prompt，架构不如方案 A 干净；token 开销略高（system prompt 更长）

**裁决建议**：**方案 B 为首选**（成功概率中高，零 breaking change，天然规避 citation 校验问题）。方案 A 作为后续架构纯度重构目标（100-130 行，2-3 周）。

**方案 B 优化设计 v2**（DS 二审有条件通过，详见 `docs/phase7.3-option-b-optimization.md`）：

针对 6 个失败模式（FM1-FM6）+ 3 个遗漏（FM7-FM9）的缓解方案，核心改动：
- `session_models.py`：新增 `ToolCallSummary` + `Session.truncate_turns()`（~30 行）
- `chat_service.py`：history 注入 + token 估算 + compaction 截断 + ToolCallSummary 填充（~60 行）
- `scene_config.py`：context_slots 新增 "history"（1 行）
- 测试：~30 行
- **合计 ~121 行**

DS 二审裁决：有条件通过。实施前处理 3 项：① truncate_turns 补充 status/updated_at 字段；② chat_turn() 显式填充 ToolCallSummary；③ ContextBudget 与 history token 交互留 TODO（Phase 8 处理）。
