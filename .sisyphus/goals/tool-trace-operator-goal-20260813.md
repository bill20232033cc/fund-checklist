# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/tool-trace-operator-slice-20260813.md 实施「Tool Trace 只读分析器（operator 层）」slice（plan 已于 2026-08-13 经 MiMo plan review，NEEDS_FIX 3 项最小修复已按 review 原文修正进 plan；docs/design.md §6.22、AGENTS.md、docs/implementation-control.md 已由 controller 先行同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review：新增 fund_agent/agent/tool_trace_analysis.py（纯函数只读分析器——模块 docstring 声明「不读 session/durable internals、不写任何状态、不落盘、不成为 truth 源」；analyze_tool_trace(trace: tuple[ToolTraceEntry], policy: ToolTraceAnalysisPolicy) -> ToolTraceAnalysisReport，类型不符抛 TypeError；policy 含 large_argument_chars=120；report 含 summary total/success/failure/unique_tools + by_tool 首现顺序/failure_codes 去重保序 + findings（failed_call 每条失败 entry、repeated_failure 同 tool+failure_code ≥2 次、large_arguments 序列化长度 > 阈值，== 阈值不触发；failure_code 一律用 .value 归一化，与 main.py:430 一致）+ limitations 固定 4 条；tool_trace_analysis_to_json 用 json.dumps(asdict, ensure_ascii=False, sort_keys=True, indent=2) + 尾换行，report 类型不符抛 TypeError；同输入两次结果一致）；接线 fund_agent/cli/main.py 仅 ask 流式成功分支（result = service.ask_question(...) 后、return SUCCESS_EXIT_CODE 前）：show_tool_trace 为真且 result.tool_trace 非空时打印 [工具分析: 共 N 次 / 成功 S / 失败 F] + 每条 finding 一行 [工具分析] {detail}，现有 TOOL_EVENT 实时显示不变、--no-stream JSON 不含分析字段、失败分支不输出；同步 fund_agent/agent/README.md 与 tests/README.md 一句话；新增 tests/fund/agent/test_tool_trace_analysis.py（summary/by_tool 首现顺序显式断言 toolA→toolB→toolA 得 (toolA,toolB)/failed_call/repeated_failure/large_arguments 含 == 与 +1 边界/空 trace limitations 恰 4 条/TypeError 契约/确定性/JSON deterministic 中文不转义尾换行/只读签名无 IO 参数），增补 tests/fund/cli/test_cli.py 1 用例（test_ask_stream_enable_tool_trace_outputs_analysis：monkeypatch FundReadingService.ask_question 返回带失败 ToolTraceEntry 的 AskQuestionResult，断言 stdout 含 [工具分析: 与 [工具分析] 行，不加 flag 时无 [工具分析:）。allowed write set 严格按 plan 清单，禁止动 AGENTS.md / docs/design.md / docs/implementation-control.md / 公共契约（AgentRunResult/ToolTraceEntry/AskQuestionResult/StreamEvent/ToolResult/FailureCode/public 方法签名）/ --no-stream JSON 输出 / TOOL_EVENT 实时显示；禁止接 interactive/read/generate 路径；禁止新增 CLI 子命令与依赖；不 commit、不 push。验收：uv run pytest tests/fund/agent/test_tool_trace_analysis.py -v --tb=short、uv run pytest tests/fund/cli/test_cli.py -k "ask" -v --tb=short、最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py 全部通过，输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/tool-trace-operator-goal-20260813.md
```

---

## /goal 命令特性（设计依据）

基于 Codex goal 存储（`~/.codex/goals_1.sqlite`，表 `thread_goals`）与现有 `.sisyphus/goals/` 产物格式：

| 特性 | 设计影响 |
|------|---------|
| 单线程单 active goal（`thread_id` 主键，存在未完成 goal 时新建失败） | objective 必须是**一条自包含、可独立完成的表述**；不能拆成多条 /goal |
| `objective` 是唯一执行依据文本，agent 收到后自主持续推进（可跨压缩） | 表述内必须自带：真源计划路径、slice 边界、allowed write set、验证命令、验收口径、禁止事项；不依赖追加说明 |
| 状态流 `active -> blocked/paused -> complete`（另有 usage/budget 限制态） | 本 slice 无阻塞依赖；实施完成后由 diff review 判定 |
| `token_budget` 可选，仅在显式要求时设置 | 本命令不设 budget |
| 完成判定由 objective 的验收标准驱动 | DoD 写死可执行验证命令与禁止事项，不用模糊措辞 |

## Goal

- goal_id: `tool-trace-operator-20260813`
- 目标：实施「Tool Trace 只读分析器（operator 层）」（dayu-agent-r 研究 §5 建议 3），按已 review 计划完成实现 + 测试。
- 前置条件：`.sisyphus/plans/tool-trace-operator-slice-20260813.md` 已 review（MiMo plan review，2026-08-13，NEEDS_FIX 3 项已按 review 原文修正进 plan）；真源三件套已由 controller 先行同步（AGENTS.md / docs/design.md §6.22 / docs/implementation-control.md）。
- 设计来源：`.sisyphus/plans/tool-trace-operator-slice-20260813.md`（唯一计划真源）+ `docs/research/dayu-agent-r-research-20260810.md` §2.2.7 / §5 建议 3。
- 日期：2026-08-13

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自 plan）

| 项 | 内容 |
|-------|------|
| 新增模块 | `fund_agent/agent/tool_trace_analysis.py`（只读分析器：Policy / RunSummary / ToolStat / Finding / Report / analyze_tool_trace / to_json） |
| 接线 | `fund_agent/cli/main.py` 仅 ask 流式成功分支（`[工具分析: ...]` 追加行） |
| 文档 | `fund_agent/agent/README.md`、`tests/README.md`（各 1 句） |
| 测试 | 新增 `test_tool_trace_analysis.py`；增补 `test_cli.py` 1 用例（ask 流式 + --enable-tool-trace） |
| 禁止 | AGENTS.md / design.md / implementation-control.md / 公共契约 / --no-stream JSON / TOOL_EVENT 实时显示 / interactive/read/generate 路径 / 新 CLI 子命令 / 新依赖 / commit / push |

## Definition of Done

- 按 CIC-lite：`implement -> tests -> diff review`，diff review 输出 `ACCEPTED`；无新增 plan-fix / re-review / evidence gate。
- 三条验证命令全部通过（见上方 Goal Command 验收段）。
- 交接报告：changed files、diff 摘要、实际测试命令与输出。
- 全部改动在 plan 的 allowed write set 内；无 commit / push。
