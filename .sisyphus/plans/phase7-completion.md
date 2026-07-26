# Phase 7 补完计划：集成 & 验证

## TL;DR

> **Quick Summary**：Phase 7 大部分代码已完成（~80%），本计划聚焦 10 项集成缺口和 5 项零代码缺失能力的补完，不重做已完成的工作。
>
> **Deliverables**：
> - ToolResult 信封接入主循环（`_tool_result_from_output` 包装旧结果）
> - ToolExecutionContext 注入每次工具调用 trace
> - ContextBudgetState 集成到 `LlmToolLoopRunner.run()`（预算检查 + 工具结果裁剪）
> - `force_answer` 降级：max_steps 达到时强制 LLM 文本回答（不报错）
> - `tool_calls_remaining` 信号注入 LLM prompt
> - `_SYSTEM_PROMPT` 从 `deepseek_llm.py` 默认迁移到 SceneConfig
> - 补齐缺失测试（`test_session_models.py` + `test_rich_render.py`）
> - 端点验证：`interactive --fund-code 011649` 全链路通过

> **Estimated Effort**：Short（7 tasks，3 波并行）
> **Parallel Execution**：YES — 3 波
> **Critical Path**：C1 → C4 → C5 → C7
> **Test Strategy**：TDD（RED → GREEN → REFACTOR）

---

## Context

### Phase 7 原始范围（17 Slice）

`.sisyphus/plans/phase7-interactive.md` 定义了 7X、7A-7P 共 17 个 Slice。代码审计确认：

- **已完成且有代码**：7A、7B、7C、7D、7F、7G、7I、7J、7K、7L、7M、7N、7O（13/17）
- **代码存在但未集成**：7X（ToolResult 封装 + ToolExecutionContext）、7E（部分：_SYSTEM_PROMPT 未完全迁移）
- **部分集成漏缺**：7H（Host 无 `run_chat_turn`）、7M（ContextBudget 未接入 runner）

### 审计发现的集成缺口

| # | 缺口 | 代码状态 | 严重度 |
|---|------|---------|--------|
| 1 | `tool_result.ToolResult` 未替换 `llm_tool_loop.ToolResult` | 两套同名不兼容 dataclass | 🔴 P0 |
| 2 | `ToolExecutionContext` 未在 `llm_tool_loop.py` 中使用 | 定义存在，零 import | 🔴 P0 |
| 3 | `ContextBudgetState` + `ToolResultBudgetCapper` 未接入 runner | 代码存在，零调用 | 🔴 P0 |
| 4 | `force_answer` 降级缺失 | 零代码 | 🔴 P0 |
| 5 | `_SYSTEM_PROMPT` 硬编码未完全迁移 | deepseek_llm.py:30-42 仍是默认值 | 🟡 P1 |
| 6 | `tool_calls_remaining` 信号缺失 | 零代码 | 🟡 P1 |
| 7 | `test_session_models.py` 缺失 | 零代码 | 🟡 P1 |
| 8 | `test_rich_render.py` 缺失 | 零代码 | 🟢 P2 |
| 9 | `prompt_toolkit` 依赖未添加 | pyproject.toml 无此项 | 🟢 P2 |
| 10 | Host 层无 `run_chat_turn` | ChatService 绕过 Host 直接调用 runner | 🟢 P2（接受现状） |

### Metis 复核关键发现

- **Two-ToolResult 问题不是简单替换**：新旧 ToolResult 服务不同层次。正确方案是新 ToolResult **包裹**旧结果（`ToolResult.success(value=old_tool_result)`），而非替换。
- **`generate_text()` 绕过基础设施**：Episode Summary 调用不经过 ContextBudget、ToolResult 信封或 ToolExecutionContext，需显式追踪。
- **Routing context 直返路径无投资建议检测**：`chat_service.py:169-189` 返回前未调 `contains_investment_advice()`，需补上。
- **compaction 线程可能覆盖主线程最新 turn**：后台 `threading.Thread` 的 load-save 与主线程存在写冲突风险。

### 裁决

| # | 裁决 | 理由 |
|---|------|------|
| 1 | 新 ToolResult **包裹**旧结果，不替换 | 两层语义不同：一次工具执行（ok/error）vs 一次证据提取（citations/evidence_text） |
| 2 | `force_answer` 纳入本计划（P0） | 模型不稳定时必须有降级路径，不能报错 |
| 3 | `prompt_toolkit` **推迟**至 Phase 7 后 polish | 非阻塞，`input()` 功能完整 |
| 4 | `_detect_context_overflow` **推迟**至 Phase 8 | 需要完整 compaction 栈配合 |
| 5 | Host 架构**接受现状**：ChatService 是编排者，更新设计文档 | 重构风险高于收益 |
| 6 | Session race condition 用 **last-write-wins + merge** 修复 | compaction 不覆盖主线程新增的 turn |

---

## Work Objectives

### Core Objective

补完 Phase 7 的集成缺口，使所有已写代码在实际运行链路中生效，并补齐零代码缺失能力。

### Concrete Deliverables

- `llm_tool_loop.py`：ToolResult 信封包裹 + ToolExecutionContext 注入 + ContextBudget 预算检查 + `force_answer` 降级
- `deepseek_llm.py`：移除 `_SYSTEM_PROMPT` 默认值，`tool_calls_remaining` 注入 prompt
- `chat_service.py`：routing context 直返路径加投资建议检测；compaction 线程写安全
- `tests/fund/service/test_session_models.py`：新建，≥8 tests
- `tests/fund/cli/test_rich_render.py`：新建，≥4 tests
- `docs/design.md`：更新 Host 层职责描述

### Definition of Done

- [ ] `uv run fund-checklist interactive --fund-code 011649` → 3 轮以上正常对话
- [ ] LLM 达到 max_steps 时触发 `force_answer` 降级（非报错）
- [ ] 工具调用 trace 包含 `run_id` / `iteration_id` / `tool_call_id`
- [ ] ContextBudget 检查生效：工具结果超过硬阈值时被裁剪
- [ ] `fund-checklist ask` 使用的 system prompt 来自 PromptComposer（非硬编码 `_SYSTEM_PROMPT`）
- [ ] 全量回归：`uv run pytest tests/fund/` → 全部 PASS

### Must Have

- ToolResult 信封包裹旧结果，`project_for_llm()` 生效
- ToolExecutionContext 注入每次工具调用
- ContextBudget 预算检查接入 runner
- `force_answer` 降级
- `test_session_models.py`

### Must NOT Have (Guardrails)

- **不修改** `FundDocumentToolService` 或其工具签名
- **不修改** `ToolCall` 或 `FinalAnswer` 数据类
- **不移除** `_SYSTEM_PROMPT`（保留为向后兼容常量，加 deprecation 注释）
- **不实现** `TruncationManager`、`fetch_more`、`_detect_context_overflow`
- **不新增** TUI 特性（prompt_toolkit 推迟）
- **不重构** ChatService → Host 编排关系

---

## Verification Strategy

### Test Decision

- **Infrastructure exists**: YES（pytest）
- **Automated tests**: TDD
- **Framework**: pytest

### QA Policy

- CLI/TUI：`interactive_bash`（tmux）— 启动 interactive，输入问题，验证输出
- API/Backend：Bash（pytest + curl）
- Library/Module：Bash（pytest）— 单测验证

---

## Execution Strategy

```
Wave 1 (Start Immediately — 4 PARALLEL, core integration):
├── C1: ToolResult 信封 + ToolExecutionContext 接入主循环
├── C2: 补齐缺失测试（session_models + rich_render）
├── C3: SYSTEM_PROMPT 迁移 + tool_calls_remaining 信号
└── C4: ContextBudget 接入 + force_answer 降级

Wave 2 (After Wave 1 — 2 PARALLEL, fix & verify):
├── C5: chat_service 修复（routing context guard + compaction 线程安全）
└── C6: 设计文档更新 + 清理

Wave FINAL (After Wave 2 — 验证):
└── C7: 端到端验证 + 全量回归
```

### Dependency Matrix

- **C1**: - → C5（信封生效后 routing context 路径也受益）
- **C2**: - → (独立)
- **C3**: - → C7
- **C4**: C1 → C5, C7
- **C5**: C1, C4 → C7
- **C6**: - → (独立)
- **C7**: C3, C4, C5 → done

> **Critical Path**: C1 → C4 → C5 → C7

---

## TODOs

- [ ] C1. ToolResult 信封 + ToolExecutionContext 接入主循环

  **What to do**:
  - **Part 1: ToolResult 包裹**（修改 `llm_tool_loop.py` 的 `_tool_result_from_output`）
    - 将 `tool_result.ToolResult`（新信封）包裹 `llm_tool_loop.ToolResult`（旧结果）
    - 旧 `ToolResult` **保持不变**，作为新信封的 `value` 字段
    - `project_for_llm()` 提取旧结果的 `evidence_text` + `citations`
    - 工厂方法：`ToolResult.success(value=old_tool_result, truncation=truncation_meta)`
    - 错误路径：`ToolResult.error(code="not_found", message=err.message)`
  - **Part 2: ToolExecutionContext 注入**（修改 `_invoke_tool_call`）
    - 构造 `ToolExecutionContext(run_id, iteration_id, tool_call_id, index_in_iteration)`
    - 传递给 `ToolTraceEntry` 或日志
    - 在 `run()` 和 `run_stream()` 中维护 `iteration_counter`
  - **Part 3: 向后兼容**
    - `_safe_tool_result()`（`deepseek_llm.py:501`）适配新信封：提取内层 `evidence_text`
    - 所有现有 `ToolResult` 消费者继续工作

  **Must NOT do**:
  - 不修改 `ToolCall` / `FinalAnswer` 数据类
  - 不修改 `_call_allowed_tool()` 签名
  - 不修改 `FundDocumentToolService` 任何方法

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES（Wave 1，与 C2/C3 并行）
  - **Blocks**: C4, C5
  - **Blocked By**: None

  **References**:
  - `fund_agent/agent/llm_tool_loop.py:_tool_result_from_output()` — 旧结果构造点（L615-672）
  - `fund_agent/agent/llm_tool_loop.py:_invoke_tool_call()` — 工具调用入口（L474-506）
  - `fund_agent/agent/tool_result.py` — 新信封定义（L12-89）
  - `fund_agent/agent/tool_context.py` — 上下文定义（L11-27）
  - `fund_agent/agent/deepseek_llm.py:_safe_tool_result()` — LLM 投射适配点（L501-508）
  - Dayu: `dayu/engine/tool_result.py:project_for_llm()` — 包裹模式参考

  **Acceptance Criteria** (TDD):
  - [ ] 旧测试全 PASS：`uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_real_llm_adapter.py`
  - [ ] 新测试：ToolResult 包裹后 `project_for_llm()` 输出格式不变
  - [ ] 新测试：`_invoke_tool_call()` trace 含 `run_id/iteration_id/tool_call_id`

  **QA Scenarios**:

  ```
  Scenario: ToolResult 信封包裹旧结果
    Tool: Bash (pytest)
    Steps:
      1. old = ToolResult(tool_name=..., result=..., citations=..., evidence_text="经理张明")
      2. wrapped = ToolResult.success(value=old)
      3. llm_view = project_for_llm(wrapped)
      4. assert llm_view["content"] == "经理张明"
      5. assert "ok" not in llm_view  # 内部字段不暴露
    Expected Result: LLM 看到 evidence_text，看不到 ok/error_code
    Evidence: .sisyphus/evidence/task-c1-envelope.txt

  Scenario: ToolExecutionContext 注入 trace
    Tool: Bash (pytest)
    Steps:
      1. runner.run(document_id="X", query="test")
      2. trace_entries = result.tool_trace
      3. 检查首个 ToolTraceEntry 含 run_id（非空字符串）
    Expected Result: 每个 ToolTraceEntry 有上下文 ID
    Evidence: .sisyphus/evidence/task-c1-context.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): integrate ToolResult envelope + ToolExecutionContext into runner`
  - Files: `fund_agent/agent/llm_tool_loop.py`, `fund_agent/agent/deepseek_llm.py`
  - Pre-commit: `uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py`

- [ ] C2. 补齐缺失测试（session_models + rich_render）

  **What to do**:
  - **Part 1: `tests/fund/service/test_session_models.py`**（新建）
    - TestSession: 创建/关闭/不可变性/add_turn/add_episode_summary/apply_pinned_state_patch
    - TestPinnedState: 字段完整性/默认值
    - TestTurn: 时间戳自动生成/字段类型
    - TestEpisodeSummary: 创建/frozen 不可变性
    - 边界：空 turns / 空 episode_summaries / patch 三态语义
    - ≥10 tests
  - **Part 2: `tests/fund/cli/test_rich_render.py`**（新建）
    - TestRichMarkdownRenderer: 表格渲染/代码块渲染/语法高亮
    - TestRichMarkdownEdgeCases: 空文本/纯文本/超长文本
    - ≥4 tests

  **Must NOT do**:
  - 不创建新的测试 infrastructure/fixture 框架
  - 不测试 rich 库内部行为

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES（Wave 1，与 C1/C3/C4 并行）
  - **Blocked By**: None

  **References**:
  - `fund_agent/service/session_models.py` — 被测模型
  - `tests/fund/host/test_session_store.py` — 现有测试模式参考
  - `fund_agent/cli/main.py:render_markdown()` — rich 渲染函数

  **Acceptance Criteria** (TDD):
  - [ ] `uv run pytest tests/fund/service/test_session_models.py` → PASS（≥10 tests）
  - [ ] `uv run pytest tests/fund/cli/test_rich_render.py` → PASS（≥4 tests）

  **Commit**: YES
  - Message: `test(phase7): add session_models + rich_render tests`
  - Files: `tests/fund/service/test_session_models.py`, `tests/fund/cli/test_rich_render.py`

- [ ] C3. SYSTEM_PROMPT 迁移 + tool_calls_remaining 信号

  **What to do**:
  - **Part 1: SYSTEM_PROMPT 迁移**
    - `deepseek_llm.py`：`_SYSTEM_PROMPT` 保留为常量，加 `# Deprecated: use PromptComposer + SceneConfig` 注释
    - `_request_payload()`：默认 `system_prompt` 参数改为必填（不再 fallback 到 `_SYSTEM_PROMPT`）
    - 所有调用方（`next_step()`, `next_step_stream()`, `generate_text()`）显式传入 `self._system_prompt`
    - `ChatService` 确认 `chat_turn()` 传入了 `composed.system_message`
    - `ask` 路径：确认 `ask_question()` 通过 PromptComposer 组装 system prompt
  - **Part 2: tool_calls_remaining 信号**
    - 在 `_request_payload()` 的 system prompt 或 user message 中注入剩余工具调用次数
    - 格式：`[系统提示] 你还有 {remaining} 次工具调用机会。`
    - 每次 LLM 返回 ToolCall 后递减
    - 当 `remaining <= 1` 时加强措辞："这是最后一次工具调用机会，调用后必须基于已有信息直接回答"

  **Must NOT do**:
  - 不删除 `_SYSTEM_PROMPT` 常量
  - 不修改 ask 子命令的用户可见行为

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES（Wave 1，与 C1/C2/C4 并行）
  - **Blocked By**: None

  **References**:
  - `fund_agent/agent/deepseek_llm.py:_SYSTEM_PROMPT` — 旧默认值（L30-42）
  - `fund_agent/agent/deepseek_llm.py:_request_payload()` — prompt 构造点（L467-498）
  - `fund_agent/service/chat_service.py:chat_turn()` — ChatService 已传 system_prompt（L208-211）
  - `fund_agent/service/extraction.py:ask_question()` — ask 路径
  - Dayu: `dayu/engine/tool_result.py:project_for_llm()` — tool_calls_remaining 参考

  **Acceptance Criteria** (TDD):
  - [ ] `uv run pytest tests/fund/agent/test_real_llm_adapter.py` → PASS（行为不变）
  - [ ] `uv run pytest tests/fund/cli/test_cli.py -k ask` → PASS（ask 不变）
  - [ ] 新测试：`DeepSeekLlmClient(system_prompt=None)` 不再 fallback 到硬编码 prompt（抛异常或使用空 prompt）
  - [ ] 新测试：tool_calls_remaining 正确递减

  **Commit**: YES
  - Message: `feat(phase7): migrate _SYSTEM_PROMPT default to PromptComposer + add tool_calls_remaining signal`
  - Files: `fund_agent/agent/deepseek_llm.py`
  - Pre-commit: `uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/cli/test_cli.py`

- [ ] C4. ContextBudget 接入 + force_answer 降级

  **What to do**:
  - **Part 1: ContextBudget 接入 runner**
    - `LlmToolLoopRunner.__init__` 新增 `context_budget: ContextBudgetState | None` 参数
    - `run()` 中：每轮 LLM 调用后 `budget_state.record_usage(chat_response.usage)`
    - 工具结果序列化后、注入下一轮前：若 `budget_state.is_over_hard_limit` → 调用 `ToolResultBudgetCapper.cap_results_for_budget()`（简化版）
    - 预算检查不阻塞工具执行——只在发送给 LLM 时裁剪
  - **Part 2: force_answer 降级**
    - `run()` 和 `run_stream()` 中：当 `iteration >= max_steps` 时
    - 不返回 `_STEP_LIMIT_MESSAGE` 错误
    - 改为：构造降级 prompt（"你已达到最大工具调用次数，请基于已有工具结果直接回答"）
    - 再调一次 `_llm_client.next_step()`，`disable_tools=True`
    - 如果降级也失败 → 返回错误
  - **Part 3: BudgetCapper 适配**
    - 复用 `context_budget.py` 的 `ToolResultBudgetCapper.allocate()` 升序公平分配
    - 简化：不使用 `MIN_RESULT_TOKENS` 全局保底（Phase 8 再加）
    - 截断标记 `[TOOL_RESULT_TRUNCATED: ...]`

  **Must NOT do**:
  - 不实现 `_compact_messages()`（推迟到 Phase 8）
  - 不实现 `_detect_context_overflow()`（推迟到 Phase 8）
  - 不修改 `ChatService.chat_turn()` 的 max_steps 设置

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES（Wave 1，依赖 C1 但可 mock 先行）
  - **Blocks**: C5, C7
  - **Blocked By**: C1（ToolResult 包裹后才能正确估算 token）

  **References**:
  - `fund_agent/agent/context_budget.py:ContextBudgetState` — 预算状态（L20-101）
  - `fund_agent/agent/context_budget.py:ToolResultBudgetCapper` — 裁剪器（L104-166）
  - `fund_agent/agent/llm_tool_loop.py:run()` — 主循环（L301-346）
  - `fund_agent/agent/llm_tool_loop.py:run_stream()` — 流式循环（L348-472）
  - Dayu: `dayu/engine/async_agent.py:_run_loop` — force_answer 参考（L1087+）
  - Dayu: `dayu/engine/async_agent.py` — 预测性预算检查（L1027-1048）

  **Acceptance Criteria** (TDD):
  - [ ] `uv run pytest tests/fund/agent/test_context_budget.py` → PASS（已有 25 tests）
  - [ ] 新集成测试：runner 达到 max_steps 时触发 `force_answer`，不返回 error
  - [ ] 新集成测试：工具结果总 token 超过 hard_limit 时被裁剪
  - [ ] 新集成测试：`record_usage()` 正确累计 prompt/completion tokens

  **QA Scenarios**:

  ```
  Scenario: force_answer 降级（max_steps 达到）
    Tool: Bash (pytest)
    Steps:
      1. 设置 runner max_steps=3
      2. LLM 持续返回 ToolCall（不返回 FinalAnswer）
      3. 第 3 次后触发降级
      4. assert result.failure is None（降级成功返回 answer）
      5. assert "达到最大工具调用次数" in result.answer 或类似降级标记
    Expected Result: 返回回答而非错误，含降级提示
    Evidence: .sisyphus/evidence/task-c4-force-answer.txt

  Scenario: ContextBudget 裁剪工具结果
    Tool: Bash (pytest)
    Steps:
      1. budget_state = ContextBudgetState(max_context_tokens=8000, used_tokens=7000)
      2. 工具结果总 estimated_tokens=3000 > remaining=2000
      3. capped = capper.allocate(results, key=estimate_tokens)
      4. assert sum(r["budget"] for r in capped) <= 2000
    Expected Result: 工具结果被按比例裁剪
    Evidence: .sisyphus/evidence/task-c4-budget-cap.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): integrate ContextBudget + force_answer degradation into runner`
  - Files: `fund_agent/agent/llm_tool_loop.py`
  - Pre-commit: `uv run pytest tests/fund/agent/test_context_budget.py tests/fund/agent/test_llm_tool_loop.py`

- [ ] C5. ChatService 修复（routing context guard + 线程安全）

  **What to do**:
  - **Part 1: routing context 直返路径加投资建议检测**
    - `chat_service.py:169-189`：在 `return ChatTurnResponse(answer=routing_context)` 之前
    - 加 `contains_investment_advice(routing_context)` 检查
    - 如果触发 → 走正常 LLM 路径（fall through 到 runner）
  - **Part 2: compaction 线程写安全**
    - `_run_compaction()` 中：`load()` → 修改 → `save()` 之间，主线程可能已写入新 turn
    - 修复：compaction 只更新 `episode_summaries` 和 `pinned_state`，不覆盖 `turns`
    - 或者：`save()` 前重新 `load()`，merge 主线程新增的 turns
    - 选择简单方案：compaction 线程追加 episode 到最新 session，不修改 turns

  **Must NOT do**:
  - 不重构 ChatService 的整体架构
  - 不改变 routing context 的触发逻辑

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES（Wave 2，与 C6 并行）
  - **Blocks**: C7
  - **Blocked By**: C1（信封生效后 routing context 受益）, C4（force_answer 生效后交互路径更稳定）

  **References**:
  - `fund_agent/service/chat_service.py:chat_turn()` — routing context 路径（L169-189）
  - `fund_agent/service/chat_service.py:_run_compaction()` — 后台压缩（L288-377）
  - `fund_agent/service/chat_service.py:_maybe_trigger_compaction()` — 触发条件（L258-286）
  - `fund_agent/service/investment_guard.py:contains_investment_advice()` — 守卫函数

  **Acceptance Criteria** (TDD):
  - [ ] routing context 返回含"建议买入"的内容时 → 走 LLM 路径而非直返
  - [ ] compaction 线程不覆盖主线程新增的 turn
  - [ ] `uv run pytest tests/fund/service/test_chat_service.py` → PASS

  **Commit**: YES
  - Message: `fix(phase7): add investment guard to routing context + thread-safe compaction`
  - Files: `fund_agent/service/chat_service.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_chat_service.py`

- [ ] C6. 设计文档更新 + 清理

  **What to do**:
  - **Part 1: 更新过期文档**
    - `docs/implementation-control.md` Phase 7 节：更新所有 Slice 状态为已完成/已集成
    - `docs/design.md`：Phase 7 状态从 `🔵 待启动` → `🟡 实施中`，更新 Host 层职责描述
    - `docs/agent-evolution-design.md`：Phase 7 状态从 `🔵 候选` → `✅ 已裁决`
  - **Part 2: TODO/FIXME 清理**
    - 搜索 `fund_agent/` 中的 `TODO phase7` / `FIXME phase7` 标记
    - 已完成的标记更新为 `DONE`
  - **Part 3: 验证命令确认**
    - 确认 Phase 7 验证命令可运行
    - 确认 `pyproject.toml` 中的 `rich` 依赖正确

  **Must NOT do**:
  - 不新增文档（只更新现有文档）
  - 不改写大片内容（只修正过期状态和错误描述）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES（Wave 2，与 C5 并行）
  - **Blocked By**: None

  **Commit**: YES
  - Message: `docs(phase7): update implementation status + clean up stale references`
  - Files: `docs/implementation-control.md`, `docs/design.md`, `docs/agent-evolution-design.md`

- [ ] C7. 端到端验证 + 全量回归

  **What to do**:
  - **Part 1: interactive 端到端 smoke**
    - `uv run fund-checklist interactive --fund-code 011649 --work-dir .fund_checklist`
    - 验证：基金代码解析 → 年份选择 → 3 轮对话 → 上下文传递 → 正常退出
    - 验证：`/stats` 显示正确轮数和模型
    - 验证：`/label` + 退出 + `--label` 恢复
  - **Part 2: ask 回归**
    - `uv run fund-checklist ask "基金经理是谁？" --document-id <id>`
    - 验证：exit code 0，answer 含 citation
    - 验证：system prompt 来自 PromptComposer（非硬编码 `_SYSTEM_PROMPT`）
  - **Part 3: 全量回归**
    - `uv run pytest tests/fund/` → 全部 PASS
    - 特别关注：Phase 5 回归（ask + streaming）+ Phase 7 新增测试
  - **Part 4: force_answer 真实路径验证**
    - 构造场景：连续 8 次 tool call 不返回 FinalAnswer
    - 验证：第 8 次后触发降级，返回回答而非错误

  **Must NOT do**:
  - 不跑需要真实 LLM API key 的 live smoke（除非显式 opt-in）
  - 不做性能 benchmark

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: NO（最终验证，在所有任务之后）
  - **Blocked By**: C3, C4, C5

  **Acceptance Criteria**:
  - [ ] `uv run pytest tests/fund/` → 全部 PASS（≥250 tests）
  - [ ] interactive 3 轮对话成功
  - [ ] ask 命令 system prompt 来自 PromptComposer
  - [ ] force_answer 降级验证通过

  **QA Scenarios**:

  ```
  Scenario: interactive 端到端 3 轮对话
    Tool: interactive_bash (tmux)
    Steps:
      1. uv run fund-checklist interactive --fund-code 011649
      2. 选择年份 → 进入 REPL
      3. "基金经理是谁？" → 含名字和 citation
      4. "任期多久？" → 含年份范围
      5. "规模多大？" → 含数字
      6. /stats → 显示轮数 3
      7. exit
    Expected Result: 3 轮正常，上下文连贯，统计正确
    Evidence: .sisyphus/evidence/task-c7-e2e.txt

  Scenario: ask 命令 system prompt 验证
    Tool: Bash (pytest)
    Steps:
      1. 注入 spy transport，记录发送给 LLM 的 system prompt
      2. uv run fund-checklist ask "测试" --document-id X
      3. assert system_prompt 不等于 hardcoded _SYSTEM_PROMPT
      4. assert system_prompt 包含 Fragment 内容（"你只能通过提供的基金年报"）
    Expected Result: system prompt 来自 PromptComposer
    Evidence: .sisyphus/evidence/task-c7-ask-prompt.txt
  ```

  **Commit**: YES
  - Message: `verify(phase7): end-to-end smoke + full regression pass`
  - 无代码变更（仅验证），不 commit

---

## Final Verification Wave

> 3 个 review agent 并行运行。ALL must PASS。

- [ ] F1. **集成完整性检查** — `oracle`
  读取所有 C1-C6 变更 diff。对每个集成点：
  - ToolResult 信封：确认 `_tool_result_from_output()` 返回的是新信封包裹旧结果
  - ToolExecutionContext：确认 `_invoke_tool_call()` 构造并传入 context
  - ContextBudget：确认 `run()` 中 `record_usage()` + 裁剪检查
  - force_answer：确认 max_steps 达到时走降级路径
  - SYSTEM_PROMPT：确认 `_request_payload` 不再 fallback 到 `_SYSTEM_PROMPT`
  Output: `C1 [PASS/FAIL] | C3 [PASS/FAIL] | C4 [PASS/FAIL] | VERDICT`

- [ ] F2. **代码质量检查** — `unspecified-high`
  - `uv run pytest tests/fund/` → 全 PASS
  - `ruff check fund_agent/` → 0 errors
  - 搜索 `as any` / `@ts-ignore` / 空 `except:` / `console.log` — 0 新增
  - 确认无未使用的 import
  Output: `Tests [N pass/N fail] | Lint [PASS/FAIL] | VERDICT`

- [ ] F3. **范围保真检查** — `deep`
  - 对每个任务的 `Must NOT do` 逐条检查
  - 确认 `FundDocumentToolService` 未被修改
  - 确认 `ToolCall` / `FinalAnswer` 未被修改
  - 确认 `TruncationManager` / `fetch_more` 未实现
  Output: `Guardrails [N/N compliant] | Scope Creep [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **C1**: `feat(phase7): integrate ToolResult envelope + ToolExecutionContext into runner` — `llm_tool_loop.py`, `deepseek_llm.py`
- **C2**: `test(phase7): add session_models + rich_render tests` — 2 测试文件
- **C3**: `feat(phase7): migrate _SYSTEM_PROMPT default to PromptComposer + add tool_calls_remaining signal` — `deepseek_llm.py`
- **C4**: `feat(phase7): integrate ContextBudget + force_answer degradation into runner` — `llm_tool_loop.py`
- **C5**: `fix(phase7): add investment guard to routing context + thread-safe compaction` — `chat_service.py`
- **C6**: `docs(phase7): update implementation status + clean up stale references` — 3 文档文件

---

## Success Criteria

### Verification Commands
```bash
# Phase 7 核心测试
uv run pytest \
  tests/fund/agent/test_tool_result.py \
  tests/fund/agent/test_tool_context.py \
  tests/fund/agent/test_context_budget.py \
  tests/fund/agent/test_token_usage.py \
  tests/fund/agent/test_llm_tool_loop.py \
  tests/fund/agent/test_real_llm_adapter.py \
  tests/fund/service/test_session_models.py \
  tests/fund/service/test_chat_service.py \
  tests/fund/service/test_scene_config.py \
  tests/fund/service/test_prompt_contributions.py \
  tests/fund/service/test_prompt_composer_upgrade.py \
  tests/fund/service/test_investment_guard.py \
  tests/fund/host/test_session_store.py \
  tests/fund/host/test_minimal_host_session.py \
  tests/fund/cli/test_cli_interactive.py \
  tests/fund/cli/test_rich_render.py \
  tests/fund/cli/test_cli.py \
  -v --tb=short

# 全量回归
uv run pytest tests/fund/ -v --tb=short
```

### Final Checklist
- [ ] ToolResult 信封接入主循环，`project_for_llm()` 生效
- [ ] ToolExecutionContext 注入每次工具调用 trace
- [ ] ContextBudget 预算检查接入 runner
- [ ] `force_answer` 降级验证通过
- [ ] `_SYSTEM_PROMPT` 不再作为默认 fallback
- [ ] `tool_calls_remaining` 信号注入 LLM prompt
- [ ] routing context 直返路径含投资建议检测
- [ ] compaction 线程安全
- [ ] `test_session_models.py` 新建且通过
- [ ] `test_rich_render.py` 新建且通过
- [ ] 全量回归 PASS
