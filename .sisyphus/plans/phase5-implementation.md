# Phase 5：LLM 自主工具调用 + 单次问答 + 流式输出

> **裁决时间**：2026-07-24
> **裁决结果**：Phase 5 启动；流式输出前置；ask 走 profile routing；编号 19A 起
> **本计划融合**：Prometheus 原始计划（Momus OKAY）+ 另一 Agent 计划（流式/路由设计）+ Metis 代码审计发现

## TL;DR

> **Quick Summary**：将 `LlmToolLoopRunner` 从测试层升级为 production 可用的 LLM 自主工具调用路径，新增 `fund-checklist ask` 子命令（默认流式输出），复用 Service 层 profile routing 提供 grounded context。
>
> **Deliverables**：
> - StreamEvent 模型 + production readiness 补齐（重试/截断/幻觉检测/tool schema 一致）
> - DeepSeekLlmClient `stream=True` 支持
> - MinimalHost `run_agent_stream()` 方法
> - Service 层 `ask_question`（含 profile routing）
> - CLI `ask` 子命令（流式默认）
> - 端到端 smoke + read 回归
>
> **Estimated Effort**：Medium-Large（因流式前置）
> **Parallel Execution**：NO — 顺序依赖
> **Critical Path**：19A → 19B → 19C → 19D → 19E → 19F

---

## Context

### 两份计划融合过程

| 来源 | 保留 | 拒绝 |
|------|------|------|
| **另一 Agent 计划** | 流式前置（8 事件 SSE）、profile routing、19A-F 编号 | Mimo smoke（用户已裁决后置） |
| **我的原始计划** | Production readiness 细节（重试/截断/投资建议/tool schema）、read 回归快照 | — |
| **Metis 代码审计** | 4 个代码缺口自动纳入 | — |

### 与 Dayu 路线对齐

Phase 5 对标 Dayu Stage 3（Agent/Engine 层）。Dayu 在 Engine 阶段内置了 streaming + context budget + cancellation。本计划将 streaming 前置到 Phase 5，与 Dayu 的设计一致。

### 前置条件

- Phase 3.5/3.6 已关闭 ✅
- Phase 5 Gate（持仓抽取 23/23）已通过 ✅
- DeepSeek adapter 已实现（Slice 8B）✅
- Live smoke 已 opt-in（Slice 8C）✅
- 13 项裁决已确认 ✅

---

## Work Objectives

### Core Objective

将 `LlmToolLoopRunner` 升级为 production-ready，新增流式 `ask` 子命令，复用 profile routing 提供受控上下文。

### Concrete Deliverables

- `fund_agent/agent/stream_events.py` — StreamEvent 数据模型（8 种事件类型）
- `fund_agent/agent/llm_tool_loop.py` — 补齐重试、截断、幻觉检测、tool schema 一致
- `fund_agent/agent/deepseek_llm.py` — `stream=True` + SSE 解析
- `fund_agent/host/minimal_host.py` — `run_agent_stream()` 方法
- `fund_agent/service/reading_service.py` — `ask_question`（含 profile routing）
- `fund_agent/cli/main.py` — `ask` 子命令（流式默认）

### Definition of Done

- [ ] `fund-checklist ask "基金经理是谁？" --document-id <id>` → exit 0，流式输出，answer 非空，citations 非空
- [ ] profile routing 在 ask 路径生效（`"费率"` → fee_rates profile → 回答含管理费/托管费）
- [ ] Streaming 完整（8 种事件类型全部可达）
- [ ] 全量回归通过（`read` 子命令行为不变）

### Must Have

- LLM 自主工具调用 + 流式 SSE 输出
- Service 层 profile routing 集成
- citation/evidence 四层校验在真实 LLM 路径不退化
- 投资建议检测 fail-closed
- 6 个 reading tools 的 tool schema 一致
- `next_step()` 3 次重试

### Must NOT Have (Guardrails)

- 不新增 Agent 类——复用 `LlmToolLoopRunner`
- 不开放 extraction tools（`extract_fee_rates`、`extract_performance_returns`）
- 不支持跨文档问答（`--document-id` 强制绑定）
- 不引入 Mimo（用户已裁决后置）
- 不新增 `--provider` CLI 参数
- 不改变 `read` 子命令行为
- 不暴露 raw Docling JSON / 本地路径 / cache path

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision

- **Infrastructure exists**: YES（pytest）
- **Automated tests**: Tests-after（单元测试 + fake LLM + opt-in live smoke）
- **Framework**: pytest

---

## Execution Strategy

### Slice 顺序

```
19A: StreamEvent + production readiness
  ↓
19B: DeepSeekLlmClient stream=True
  ↓
19C: MinimalHost.run_agent_stream()
  ↓
19D: Service ask_question + profile routing
  ↓
19E: CLI ask 子命令 + 流式输出
  ↓
19F: 端到端 smoke + read 回归
```

### Dependency Matrix

| Slice | Depends On | Blocks |
|-------|-----------|--------|
| 19A | — | 19B, 19C, 19D |
| 19B | 19A | 19C |
| 19C | 19A, 19B | 19E |
| 19D | 19A | 19E |
| 19E | 19C, 19D | 19F |
| 19F | 19E | — |

---

## TODOs

- [ ] 19A. StreamEvent 数据模型 + Production Readiness

  **What to do**：
  - 新增 `fund_agent/agent/stream_events.py`，定义 StreamEvent 数据模型（对齐 dayu AppEvent）：
    ```python
    class StreamEventType(Enum):
        CONTENT_DELTA = "content_delta"
        REASONING_DELTA = "reasoning_delta"
        TOOL_EVENT = "tool_event"
        METADATA = "metadata"
        WARNING = "warning"
        ERROR = "error"
        DONE = "done"

    @dataclass
    class StreamEvent:
        type: StreamEventType
        payload: Any
        sequence: int
    ```
  - 补齐 production readiness（Metis 发现的 4 个代码缺口）：
    1. **Tool schema 一致性**：`DeepSeekLlmClient._tool_schemas()` 补上 `aggregate_multi_year_annual_performance` 的完整 schema（参数：`fund_code`、`requested_years`、`annual_report_documents`、`share_class`）。确保 `ALLOWED_LLM_TOOL_NAMES`（6 个）与 `_tool_schemas()` 暴露的工具完全一致。
    2. **next_step() 重试**：`DeepSeekLlmClient.next_step()` 添加 3 次指数退避重试（1s/2s/4s），匹配 `generate_text()` 行为。network error/429/timeout 重试；auth error(401/403) 不重试。
    3. **evidence_text 截断**：`LlmToolLoopRunner._tool_result_from_output()` 对 tool result 截断至 4096 字符。保留开头 3072 + 结尾 1024，中间标记 `[...已截断 N 字符...]`。截断后必须保留 citation locator。
    4. **投资建议检测**：`LlmToolLoopRunner._final_result()` 检测 final answer 中的投资建议关键词。命中列表 `["买入", "卖出", "建议加仓", "建议减仓", "推荐买入", "推荐卖出", "强烈建议"]` 中任一项 → fail-closed。`"建议关注"`、`"需持续跟踪"` 不触发（与 Phase 3.5 C3 一致）。
  - `LlmToolLoopRunner` 集成 StreamEvent 产出：tool call/result → TOOL_EVENT，final answer → CONTENT_DELTA + METADATA + DONE
  - 新增 `tests/fund/agent/test_llm_production_readiness.py` 使用 `FakeLlmClient` 覆盖：幻觉拦截、越权工具拒绝、无引用拦截、tool schema 一致、重试/不重试边界、截断保留 citation

  **Must NOT do**：
  - 不修改现有 `test_llm_tool_loop.py` 测试
  - 不在 StreamEvent 模型中引入 dayu 特有的 session/run 字段

  **Recommended Agent Profile**：
  - **Category**: `deep` — 涉及 Agent 层 enforcement 机制修改 + 新数据模型
  - **Skills**: `[]`

  **Parallelization**：顺序依赖（19A 是所有后续 slice 的前置）

  **References**：
  - `fund_agent/agent/llm_tool_loop.py` — `ALLOWED_LLM_TOOL_NAMES`、`_tool_result_from_output()`、`_final_result()`
  - `fund_agent/agent/deepseek_llm.py` — `_tool_schemas()`、`next_step()`（零重试）、`generate_text()`（3 次重试参照）
  - `fund_agent/service/audit_pipeline.py` — C3 投资建议检测规则（复用关键词列表思路）
  - `dayu/engine/async_agent.py` — StreamEvent 设计参照（8 种事件类型）

  **Acceptance Criteria**：
  - [ ] `StreamEventType` 包含全部 8 种类型
  - [ ] `test_tool_schema_consistency` 通过
  - [ ] `test_next_step_retry` 验证 3 次重试 + auth error 不重试
  - [ ] `test_evidence_truncation` 验证 4096 字符截断 + citation 保留
  - [ ] `test_investment_advice_blocked` 验证关键词拦截 + 分析性表述不误杀

  **QA Scenarios**：

  ```
  Scenario: all production readiness tests pass
    Tool: Bash (pytest)
    Preconditions: code changes applied
    Steps:
      1. uv run pytest tests/fund/agent/test_stream_events.py tests/fund/agent/test_llm_production_readiness.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short
      2. Assert exit code 0
      3. Assert test count >= 10
    Expected Result: all tests pass, no network calls
    Evidence: .sisyphus/evidence/task-19a-all-tests.txt
  ```

  **Commit**: YES — `feat(agent): add StreamEvent model and production readiness`
  - Files: `stream_events.py`, `llm_tool_loop.py`, `deepseek_llm.py`, `test_stream_events.py`, `test_llm_production_readiness.py`

- [ ] 19B. DeepSeekLlmClient stream=True + SSE 解析

  **What to do**：
  - 修改 `DeepSeekLlmClient`：payload 中 `stream` 参数从硬编码 `False` 改为可配置（默认 `True`，可通过 `ExecutionOptions` 覆盖）
  - 实现 SSE 流解析：将 OpenAI-compatible `data: {"choices":[{"delta":{"content":"..."}}]}` 格式转为 `StreamEvent(CONTENT_DELTA)`
  - 处理 tool_call delta（流式工具调用增量）→ `StreamEvent(TOOL_EVENT)`
  - 处理 `finish_reason=stop` → `StreamEvent(DONE)`
  - 处理 reasoning content（如 DeepSeek 支持）→ `StreamEvent(REASONING_DELTA)`
  - 处理错误响应 → `StreamEvent(ERROR)`
  - 新增/扩展 `tests/fund/agent/test_real_llm_adapter.py` 验证 `stream=True` 路径

  **Must NOT do**：
  - 不新增 Mimo 相关代码（用户已裁决后置）
  - 不改变 `generate_text()` 的同步行为

  **Recommended Agent Profile**：
  - **Category**: `deep` — SSE 解析涉及网络层 + 事件转换
  - **Skills**: `[]`

  **Parallelization**：依赖 19A（StreamEvent 模型）

  **References**：
  - `fund_agent/agent/deepseek_llm.py` — `next_step()` 方法（payload 构造处、response 解析处）
  - `fund_agent/agent/llm_tool_loop.py` — `LlmClientProtocol`（确保 stream 路径仍满足协议）
  - `tests/fund/agent/test_real_llm_adapter.py` — 现有 adapter 测试模式

  **Acceptance Criteria**：
  - [ ] `stream=True` 时返回 `AsyncIterator[StreamEvent]`
  - [ ] CONTENT_DELTA 事件逐 token 产出
  - [ ] TOOL_EVENT 在工具调用时产出
  - [ ] DONE 事件在 `finish_reason=stop` 时产出
  - [ ] ERROR 事件在 HTTP error 时产出

  **QA Scenarios**：

  ```
  Scenario: streaming content deltas
    Tool: Bash (pytest with fake SSE transport)
    Preconditions: fake transport returns SSE chunks
    Steps:
      1. uv run pytest tests/fund/agent/test_real_llm_adapter.py -k "stream" -v --tb=short
      2. Assert exit code 0
      3. Assert events include CONTENT_DELTA, TOOL_EVENT, DONE
    Expected Result: streaming pipeline complete
    Evidence: .sisyphus/evidence/task-19b-stream.txt
  ```

  **Commit**: YES — `feat(agent): add stream=True support to DeepSeekLlmClient`
  - Files: `deepseek_llm.py`, `test_real_llm_adapter.py`

- [ ] 19C. MinimalHost.run_agent_stream()

  **What to do**：
  - 在 `MinimalHost` 中新增 `run_agent_stream(contract) -> AsyncIterator[StreamEvent]` 方法
  - 内部调用 `LlmToolLoopRunner.run_stream()`（或等价流式方法），收集 StreamEvent 逐级转发
  - 保持 `run_agent_and_wait()` 向后兼容（内部可复用流式路径 + `list()` 收集）
  - 处理 MinimalHost 的异步化问题：当前 `MinimalHost` 使用 `threading.Thread + join(timeout)` 同步模式。19C 引入 `async/await` 或使用 `asyncio.run()` 包装
  - 新增 `tests/fund/host/test_host_stream.py` 验证流式事件转发

  **Must NOT do**：
  - 不在此 slice 实现 session/concurrency/cancel/resume（Phase 6/7 范围）
  - 不改变 `MinimalHost` 对 `MinimalFundDocumentAgent` 的支持（确定性路径）

  **Recommended Agent Profile**：
  - **Category**: `deep` — Host 层异步化 + 事件转发涉及架构边界
  - **Skills**: `[]`

  **Parallelization**：依赖 19A + 19B

  **References**：
  - `fund_agent/host/minimal_host.py` — 当前 `run()` 方法（threading 模式）
  - `fund_agent/agent/llm_tool_loop.py` — `LlmToolLoopRunner.run()` 签名
  - `fund_agent/agent/stream_events.py` — StreamEvent 模型（19A 产物）

  **Acceptance Criteria**：
  - [ ] `run_agent_stream()` 返回 `AsyncIterator[StreamEvent]`
  - [ ] CONTENT_DELTA 事件正确转发（不丢失、不重复）
  - [ ] TOOL_EVENT 事件正确转发
  - [ ] DONE 事件在 Agent 完成时产出
  - [ ] `run_agent_and_wait()` 仍可用（向后兼容）

  **QA Scenarios**：

  ```
  Scenario: host streams events from agent
    Tool: Bash (pytest)
    Preconditions: fake StreamEvent-producing agent
    Steps:
      1. uv run pytest tests/fund/host/test_host_stream.py -v --tb=short
      2. Assert exit code 0
      3. Assert events received include CONTENT_DELTA and DONE
    Expected Result: all events forwarded, backward compat preserved
    Evidence: .sisyphus/evidence/task-19c-host-stream.txt
  ```

  **Commit**: YES — `feat(host): add run_agent_stream to MinimalHost`
  - Files: `minimal_host.py`, `test_host_stream.py`

- [ ] 19D. Service 层 ask_question + Profile Routing

  **What to do**：
  - 新增 DTO：
    ```python
    @dataclass(frozen=True)
    class AskQuestionRequest:
        document_id: str       # 必须
        question: str          # 必须
        session_id: Optional[str] = None  # Phase 5 接受但忽略，预留 Phase 6

    @dataclass(frozen=True)
    class AskQuestionResult:
        answer: str
        citations: tuple[Citation, ...]
        tool_trace: tuple[ToolTraceEntry, ...]
        routing_trace: tuple[QueryRouteAttempt, ...]  # 复用 9E
        failure: Optional[ToolFailure] = None
    ```
  - 在 `FundReadingService` 中新增 `ask_question(request) -> AskQuestionResult`：
    1. **Profile routing**（核心新增）：调用 `_route_query(document_id, question)`，复用现有 controlled profile routing（holdings_top10 / asset_allocation / fee_rates / performance_returns）。routing 结果为 LLM 提供 grounded context
    2. **构造 ExecutionContract**：将 routing 结果（原文片段 + citations）+ 用户原始问题 作为 LLM 的 context。system prompt 使用硬编码模板（不引入 prompt framework）
    3. **调用 Host**：`Host.run_agent_stream(contract)`，LLM 在 routing 结果基础上生成自然语言回答，可自主决定是否需要额外 reading tools
    4. **结果组装**：收集 StreamEvent → 组装 `AskQuestionResult(answer, citations, tool_trace, routing_trace)`
  - System prompt 模板（硬编码，不引入 prompt framework）：
    ```
    你是基金年报分析助手。以下是用户问题相关的年报内容（已通过受控检索获得）。
    你的回答必须基于提供的内容和工具返回的结果，不得编造信息。
    每个事实都必须有引用来源。不要提供投资建议（买入/卖出/持有）。
    ```
  - 新增 `tests/fund/service/test_ask_question.py` 验证 routing 集成 + LLM 生成

  **Must NOT do**：
  - 不暴露 raw Docling JSON、本地路径、cache path
  - 不跳过 profile routing（即使 routing 返回 not_found，LLM 也需基于此事实回答）
  - 不在 routing 失败时让 LLM 自行搜索（与 "受控" 设计原则冲突）

  **Recommended Agent Profile**：
  - **Category**: `deep` — Service 层 orchestration 涉及 routing + Host + Agent 多组件
  - **Skills**: `[]`

  **Parallelization**：依赖 19A（可并行于 19B/19C）

  **References**：
  - `fund_agent/service/extraction.py` — `FundReadingService`、`_route_query()`、`_default_host_factory()`
  - `fund_agent/service/models.py` — 现有 `ReadLocalReportRequest` / `ReadLocalReportResult` 模式
  - `fund_agent/host/minimal_host.py` — `run_agent_stream()` 方法（19C 产物）
  - `fund_agent/agent/llm_tool_loop.py` — `LlmToolLoopRunner.run()` 签名

  **Acceptance Criteria**：
  - [ ] `AskQuestionRequest` 和 `AskQuestionResult` 定义在 `models.py`（`frozen=True`）
  - [ ] `ask_question` 方法可被调用
  - [ ] routing 命中 fee_rates profile → answer 含管理费/托管费
  - [ ] routing 返回 not_found → answer 说明未找到 + `AskQuestionResult.failure` 非 None
  - [ ] fake LLM 路径：answer 非空 + citations 非空 + routing_trace 非空

  **QA Scenarios**：

  ```
  Scenario: ask with profile routing success
    Tool: Bash (pytest)
    Preconditions: fake catalog + fake routing + fake LLM
    Steps:
      1. uv run pytest tests/fund/service/test_ask_question.py -k "routing_success" -v
      2. Assert answer contains routing result context
      3. Assert routing_trace shows fee_rates profile
    Expected Result: routing + LLM integration works
    Evidence: .sisyphus/evidence/task-19d-routing.txt

  Scenario: ask with routing not_found
    Tool: Bash (pytest)
    Preconditions: routing returns not_found for query
    Steps:
      1. uv run pytest tests/fund/service/test_ask_question.py -k "routing_not_found" -v
      2. Assert AskQuestionResult.failure is not None
    Expected Result: graceful failure with routing info
    Evidence: .sisyphus/evidence/task-19d-not-found.txt
  ```

  **Commit**: YES — `feat(service): add ask_question use case with profile routing`
  - Files: `extraction.py`, `models.py`, `test_ask_question.py`

- [ ] 19E. CLI ask 子命令 + 流式输出

  **What to do**：
  - 新增 `fund_agent/cli/main.py` 中的 `ask` 子命令注册
  - CLI 接口：
    ```
    fund-checklist ask "这只基金的费率高吗？" --document-id <id>
    fund-checklist ask "基金经理是谁？" --document-id <id> --no-stream
    fund-checklist ask "前十大持仓是什么？" --document-id <id> --enable-tool-trace
    ```
  - 参数：
    - `question`：位置参数（必选）
    - `--document-id`：必选
    - `--work-dir`：可选，默认 `.fund_checklist`
    - `--no-stream`：回退同步输出
    - `--enable-tool-trace`：流式模式下同步输出 tool call/result
  - 流式输出格式：逐字打印 CONTENT_DELTA payload，`--enable-tool-trace` 时同步输出 TOOL_EVENT
  - 同步回退（`--no-stream`）：等待完成后输出完整 answer（兼容模式）
  - 输出格式：JSON（含 answer、citations、routing_trace）

  **Must NOT do**：
  - 不改变 `read` 子命令行为
  - 不暴露 raw Docling JSON / 本地路径
  - 流式输出不做 ANSI 颜色或进度条（保持纯文本，为 Phase 8 Web 接入做准备）

  **Recommended Agent Profile**：
  - **Category**: `quick` — CLI wiring，不涉及核心逻辑
  - **Skills**: `[]`

  **Parallelization**：依赖 19C + 19D

  **References**：
  - `fund_agent/cli/main.py` — `_run_read_command()` 实现模式
  - `fund_agent/service/extraction.py` — `FundReadingService.ask_question()`（19D 产物）
  - `fund_agent/host/minimal_host.py` — `run_agent_stream()`（19C 产物）

  **Acceptance Criteria**：
  - [ ] `uv run fund-checklist ask --help` 显示参数
  - [ ] 缺 `--document-id` → argparse 报错
  - [ ] 默认流式输出（逐字显示）
  - [ ] `--no-stream` 回退同步（等待完成后输出）
  - [ ] `--enable-tool-trace` 显示 tool call/result
  - [ ] 失败 exit 2 + stderr 含 failure 信息

  **QA Scenarios**：

  ```
  Scenario: ask --help
    Tool: Bash (CLI)
    Steps:
      1. uv run python -m fund_agent.cli.main ask --help
      2. Assert exit 0, stdout contains "--document-id", "--no-stream", "--enable-tool-trace"
    Expected Result: help text complete
    Evidence: .sisyphus/evidence/task-19e-help.txt

  Scenario: ask with --no-stream (sync fallback)
    Tool: Bash (CLI)
    Preconditions: fake service returning result
    Steps:
      1. uv run pytest tests/fund/cli/test_cli.py -k "ask_no_stream" -v
      2. Assert exit 0, stdout JSON has answer + citations
    Expected Result: synchronous output works
    Evidence: .sisyphus/evidence/task-19e-no-stream.txt
  ```

  **Commit**: YES — `feat(cli): add ask subcommand with streaming output`
  - Files: `cli/main.py`, `test_cli.py`

- [ ] 19F. 端到端 Smoke + Read 回归

  **What to do**：
  - 真实 LLM + 真实 PDF 端到端 smoke（opt-in：`FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1`）：
    1. `"基金经理是谁？"` → 期望 answer 含基金经理姓名 + citations
    2. `"前十大持仓是什么？"` → 期望 answer 含股票列表 + table citation，tool_trace 含 search_document → read_section → list_tables → read_table
    3. `"这只基金的费率高吗？"` → 期望 routing 走 fee_rates profile，answer 含管理费/托管费/销售服务费
  - Read 回归快照：
    - **在 Phase 5 开始前**保存 `read` 子命令 baseline 快照（3 条 query）
    - **Phase 5 全部完成后**对比快照，任何差异需记录理由
  - 全量回归：`uv run pytest tests/fund/...` 全部通过

  **Must NOT do**：
  - 不在默认 pytest 中运行 live smoke（必须 opt-in）
  - 不打印 API key
  - 不做泛化问答测试

  **Recommended Agent Profile**：
  - **Category**: `quick` — smoke 测试编写
  - **Skills**: `[]`

  **Parallelization**：依赖 19E

  **References**：
  - `tests/fund/cli/test_cli.py` — 现有 test 结构
  - `tests/fund/agent/test_deepseek_live_smoke.py` — opt-in live smoke 模式
  - `基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf` — 真实 PDF 样本

  **Acceptance Criteria**：
  - [ ] 3 条 smoke query 全部 exit 0（opt-in 时）
  - [ ] 每条 answer 非空 + citations 非空
  - [ ] read 回归快照 3 条全部匹配
  - [ ] 全量回归通过

  **QA Scenarios**：

  ```
  Scenario: real LLM e2e smoke
    Tool: Bash (CLI)
    Preconditions: DEEPSEEK_API_KEY set, FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1, PDF imported
    Steps:
      1. Import PDF → get document_id
      2. ask "基金经理是谁？" → exit 0, answer non-empty, citations non-empty
      3. ask "前十大持仓是什么？" → exit 0, tool_trace shows search→read_section→read_table
      4. ask "这只基金的费率高吗？" → exit 0, routing is fee_rates, answer mentions 管理费/托管费
    Expected Result: 3/3 passed
    Evidence: .sisyphus/evidence/task-19f-smoke-{1,2,3}.txt

  Scenario: read regression
    Tool: Bash (CLI)
    Preconditions: baseline snapshot saved before Phase 5
    Steps:
      1. read --query "前十大持仓" → compare with baseline
      2. read --query "资产配置" → compare with baseline
      3. read --query "费用" → compare with baseline
    Expected Result: all 3 match baseline
    Evidence: .sisyphus/evidence/task-19f-regression.txt
  ```

  **Commit**: YES — `test: add e2e smoke and read regression for ask command`
  - Files: `test_cli.py`
  - Pre-commit: save baseline; `uv run pytest tests/fund/document_tools tests/fund/agent tests/fund/service tests/fund/cli tests/fund/host`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
- [ ] F2. **Code Quality Review** — `unspecified-high`
- [ ] F3. **Real Manual QA** — `unspecified-high`
- [ ] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **19A-1~5**: `feat(agent): add StreamEvent model and production readiness` — stream_events.py, llm_tool_loop.py, deepseek_llm.py
- **19B**: `feat(agent): add stream=True support to DeepSeekLlmClient` — deepseek_llm.py
- **19C**: `feat(host): add run_agent_stream to MinimalHost` — minimal_host.py
- **19D**: `feat(service): add ask_question use case with profile routing` — reading_service.py, models.py
- **19E**: `feat(cli): add ask subcommand with streaming output` — cli/main.py
- **19F**: `test: add e2e smoke and read regression` — test_cli.py

---

## Success Criteria

### Verification Commands

```bash
# 19A: StreamEvent + production readiness
uv run pytest tests/fund/agent/test_stream_events.py tests/fund/agent/test_llm_production_readiness.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short

# 19B: DeepSeek stream
uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short

# 19C: Host stream
uv run pytest tests/fund/host/ tests/fund/agent/test_minimal_tool_loop.py -v --tb=short

# 19D: Service ask_question
uv run pytest tests/fund/service/test_ask_question.py tests/fund/service/test_reading_service.py -v --tb=short

# 19E: CLI ask
uv run pytest tests/fund/cli/test_cli.py -v --tb=short

# 19F: 端到端（需真实 LLM）
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 uv run python -m fund_agent.cli.main ask "基金经理是谁？" --document-id <id>

# 全量回归
uv run pytest tests/fund/document_tools tests/fund/agent tests/fund/service tests/fund/cli tests/fund/host -v --tb=short
```

### Final Checklist

- [ ] 6 个工具 schema 一致
- [ ] `next_step()` 有 3 次重试
- [ ] evidence_text 截断至 4096 字符
- [ ] 投资建议关键词拦截生效
- [ ] Streaming 8 种事件类型全部可达
- [ ] `ask` 默认流式输出，`--no-stream` 回退同步
- [ ] profile routing 在 ask 路径生效
- [ ] `read` CLI 行为不变（快照对比通过）
- [ ] 全量回归通过
