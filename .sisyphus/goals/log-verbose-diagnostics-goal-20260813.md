# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/log-verbose-diagnostics-slice-20260813.md 实施「日志 VERBOSE 级 + 有界脱敏诊断载荷」slice（plan 已于 2026-08-13 经 MiMo plan review ACCEPTED，仅 1 条 P2 措辞已修正；docs/design.md §6.21、AGENTS.md、docs/implementation-control.md 已由 controller 先行同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review：新增 fund_agent/agent/log_levels.py（VERBOSE=15 幂等注册 + verbose() + configure_logging()，env FUND_CHECKLIST_LOG_LEVEL，absent 零行为变更、未知值 fail-fast ValueError）与 fund_agent/agent/diagnostic_payload.py（build_diagnostic_payload 显式命名参数 message 必填 + code/document_id/tool_name/provider/query 可选、逐字段脱敏+500 字符截断、总量 2000 超限按 query→provider→tool_name→document_id→code 丢可选字段、message 永不丢；脱敏覆盖 sk-/pk- key、Bearer、URL query secret、local_import_id、/Users/、/tmp/、/private/、~、.fund_checklist_*）；接线 llm_tool_loop.run/run_stream 入口 verbose（trace 初始化之后、循环开始前）+ deepseek_llm._parse_response malformed 分支 verbose（只带 llm_malformed_response code + 安全消息，任何路径不得把 body/raw provider response 写入日志）；cli main() 入口调 configure_logging()；同步 fund_agent/agent/README.md 与 tests/README.md 一句话；新增 tests/fund/agent/test_log_levels.py、tests/fund/agent/test_diagnostic_payload.py，增补 test_llm_tool_loop.py 与 test_real_llm_adapter.py（malformed 脱敏断言）。allowed write set 严格按 plan 清单，禁止动 AGENTS.md / docs/design.md / docs/implementation-control.md / 公共契约（StreamEvent/ToolResult/FailureCode/public 方法签名）/ 现有 logger.warning 行为；禁止新增依赖与 CLI 子命令；不 commit、不 push。验收：uv run pytest tests/fund/agent/test_log_levels.py tests/fund/agent/test_diagnostic_payload.py -v --tb=short、uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_real_llm_adapter.py -v --tb=short、最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py 全部通过，输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/log-verbose-diagnostics-goal-20260813.md
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

- goal_id: `log-verbose-diagnostics-20260813`
- 目标：实施「日志 VERBOSE 级 + 有界脱敏诊断载荷」（dayu-agent-r 研究 §5 建议 2），按已 ACCEPTED 计划完成实现 + 测试。
- 前置条件：`.sisyphus/plans/log-verbose-diagnostics-slice-20260813.md` ACCEPTED（MiMo plan review，2026-08-13）；真源三件套已由 controller 先行同步（AGENTS.md / docs/design.md §6.21 / docs/implementation-control.md）。
- 设计来源：`.sisyphus/plans/log-verbose-diagnostics-slice-20260813.md`（唯一计划真源）+ `docs/research/dayu-agent-r-research-20260810.md` §5 建议 2。
- 日期：2026-08-13

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自 plan）

| 项 | 内容 |
|-------|------|
| 新增模块 | `fund_agent/agent/log_levels.py`（VERBOSE=15 / register / verbose() / configure_logging） |
| 新增模块 | `fund_agent/agent/diagnostic_payload.py`（redact_diagnostic_text / build_diagnostic_payload 有界脱敏载荷） |
| 接线 | `llm_tool_loop.run / run_stream` 入口 verbose；`deepseek_llm._parse_response` malformed verbose；`cli/main.py` `main()` 入口 `configure_logging()` |
| 文档 | `fund_agent/agent/README.md`、`tests/README.md`（各 1 句） |
| 测试 | 新增 `test_log_levels.py` / `test_diagnostic_payload.py`；增补 `test_llm_tool_loop.py` / `test_real_llm_adapter.py` |
| 禁止 | AGENTS.md / design.md / implementation-control.md / 公共契约 / 现有 warning 行为 / 新依赖 / 新 CLI 子命令 / commit / push |

## Definition of Done

- 按 CIC-lite：`implement -> tests -> diff review`，diff review 输出 `ACCEPTED`；无新增 plan-fix / re-review / evidence gate。
- 三条验证命令全部通过（见上方 Goal Command 验收段）。
- 交接报告：changed files、diff 摘要、实际测试命令与输出。
- 全部改动在 plan 的 allowed write set 内；无 commit / push。
