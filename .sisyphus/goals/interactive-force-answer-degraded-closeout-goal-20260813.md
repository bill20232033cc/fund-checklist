# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/interactive-force-answer-degraded-closeout-20260813.md 实施「interactive force_answer 降级收尾」slice（plan 已于 2026-08-13 经 MiMo plan review ACCEPTED，2 条 minor 不阻塞已记录；AGENTS.md、docs/design.md §3.4、docs/implementation-control.md 已由 controller 先行同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review：修改 fund_agent/agent/llm_tool_loop.py 的 _apply_interactive_final_guards 新增 degraded: bool = False 关键字参数（docstring 说明 degraded 语义：投资建议拦截分支不变、final.failure 非空原样返回、跳过原文粘贴/超长有界重答、answer >200 字直接 _truncate_final_answer_summary 截断为 ≤200 字摘要、≤200 字原样返回；实现用标准 if/else 块）；run()（约 :676）与 run_stream()（约 :987）的 force_answer 调用点传 degraded=True 并更新注释为「降级产物跳过原文粘贴/超长重答，超长直接截断收尾（2026-08-13 方案 2）」；正常 FinalAnswer 路径零变化（degraded=False 默认，原文粘贴/超长仍重答 1 次）。同步 fund_agent/agent/README.md 第 41-42 行终答守卫表述（正常 FinalAnswer 仍重答；force-answer 降级产物跳过原文粘贴/超长重答、超长直接截断 ≤200 字；投资建议拦截两者一致保留）与 tests/README.md 一句话。测试 tests/fund/agent/test_llm_tool_loop.py：更新 3 个既有 run_stream 用例（test_run_stream_interactive_force_answer_guard_retry_passes 改为降级产物不重答直接返回截断摘要 next_step_calls==2；guard_truncates_summary 改为直接截断 next_step_calls==2；guard_fails_closed 改为降级产物直接收尾不再 ERROR/UNAVAILABLE、无 ERROR 有 DONE，fake client 第 3 个 response 未消费可保留或移除）；新增 6 个用例（run() 降级超长截断无重答、降级原文粘贴直接返回不重答、降级无证据仍 fail-closed、降级命中投资建议仍拦截 fail-closed、正常 FinalAnswer 原文粘贴仍重答 1 次回归保护、正常 FinalAnswer 超长仍重答后截断回归保护）。allowed write set 严格按 plan 清单（fund_agent/agent/llm_tool_loop.py、fund_agent/agent/README.md、tests/fund/agent/test_llm_tool_loop.py、tests/README.md），禁止动 AGENTS.md / docs/design.md / docs/implementation-control.md / 投资建议拦截语义 / 正常 FinalAnswer 重答逻辑 / 公共契约 / 其他 scene；禁止新增依赖与 CLI 子命令；不 commit、不 push。验收：uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "force_answer or max_steps or interactive_paste or interactive_long or interactive_advice" -v --tb=short、uv run pytest tests/fund/agent/test_llm_tool_loop.py -v --tb=short、最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py 全部通过（test_llm_tool_loop 不应再有任何失败），输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/interactive-force-answer-degraded-closeout-goal-20260813.md
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

- goal_id: `interactive-force-answer-degraded-closeout-20260813`
- 目标：实施「interactive force_answer 降级收尾」（Fix A 细化，方案 2），按已 ACCEPTED 计划完成实现 + 测试。
- 前置条件：`.sisyphus/plans/interactive-force-answer-degraded-closeout-20260813.md` ACCEPTED（MiMo plan review，2026-08-13）；真源三件套已由 controller 先行同步（AGENTS.md / docs/design.md §3.4 / docs/implementation-control.md）。
- 设计来源：`.sisyphus/plans/interactive-force-answer-degraded-closeout-20260813.md`（唯一计划真源）。
- 日期：2026-08-13

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自 plan）

| 项 | 内容 |
|-------|------|
| 代码 | `fund_agent/agent/llm_tool_loop.py`：guard 加 `degraded: bool = False` + 2 个 force_answer 调用点传 `degraded=True` |
| 文档 | `fund_agent/agent/README.md`（第 41-42 行守卫表述）、`tests/README.md`（1 句） |
| 测试 | `test_llm_tool_loop.py`：更新 3 个既有 run_stream force_answer 用例 + 新增 6 个用例 |
| 禁止 | AGENTS.md / design.md / implementation-control.md / 投资建议拦截语义 / 正常 FinalAnswer 重答 / 公共契约 / 其他 scene / 新依赖 / 新 CLI 子命令 / commit / push |

## Definition of Done

- 按 CIC-lite：`implement -> tests -> diff review`，diff review 输出 `ACCEPTED`；无新增 plan-fix / re-review / evidence gate。
- 三条验证命令全部通过（见上方 Goal Command 验收段）；`test_llm_tool_loop.py` 无失败（既有回归已修复）。
- 交接报告：changed files、diff 摘要、实际测试命令与输出。
- 全部改动在 plan 的 allowed write set 内；无 commit / push。
