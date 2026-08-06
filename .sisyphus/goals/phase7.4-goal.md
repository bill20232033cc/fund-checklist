# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/interactive-e2e-fix-20260802.md 执行 Phase 7.4 interactive e2e 失败修复（计划已于 2026-08-02 经 Mimo review ACCEPTED）。以工作区未提交 WIP（B1 投资建议强弱词豁免、B2 document_id 注入）为基线增量实现：S0 失败轮 session 持久化与 tool_trace 恢复（纠正 e276ff3 的 entry.status 字段错误，改用 result_kind/failure_code；保留被投资建议拦截的回答原文与触发词）；S1 ToolFailure 回喂 LLM 修正 section_ref/工具名/document_id（终态失败仍 fail-closed）；S2 document_id 缺失用 expected 补全、未知工具名先有界归一化再拒绝（llm_malformed_response 仅保留给 provider 结构不可解析）；S3 投资建议判据统一单一真源（main.py 用户输入预检改引 llm_tool_loop.contains_investment_advice）+ 持仓/风格事实描述不拦截，依赖 B1 口径 owner 确认，未确认前 S3 挂起且不阻塞其余 slice；S4 prompt 引导无事实目标问题尽早 final answer、空搜索结果不猜 section_ref；S5 真源文档同步。每个 slice 走 CIC-lite implement -> tests -> diff review，review 输出只能是 ACCEPTED 或 NEEDS_FIX；不 commit、不 push、不触碰 docling_store.py 与本计划 write set 之外的文件。验收：最小验证命令 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py 及 interactive 相关测试通过；opt-in 重跑 uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace 原 9 问达到 0 条 LLM 处理失败、2 条误拦截解除、失败轮在 session 可见；完成后同步 docs/design.md、docs/implementation-control.md、AGENTS.md 并输出最小可复现验证证据。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/phase7.4-goal.md
```

---

## /goal 命令特性（设计依据）

基于 Codex goal 存储（`~/.codex/goals_1.sqlite`，表 `thread_goals`）与现有 `.sisyphus/goals/` 产物格式：

| 特性 | 设计影响 |
|------|---------|
| 单线程单 active goal（`thread_id` 主键，存在未完成 goal 时新建失败） | objective 必须是**一条自包含、可独立完成的表述**；不能拆成多条 /goal |
| `objective` 是唯一执行依据文本，agent 收到后自主持续推进（可跨压缩） | 表述内必须自带：真源计划路径、slice 顺序、验收口径、禁止事项；不依赖追加说明 |
| 状态流 `active -> blocked/paused -> complete`（另有 usage/budget 限制态） | 文中标注唯一阻塞依赖（S3 口径确认），阻塞时 `/goal block`，其余 slice 不挂起 |
| `token_budget` 可选，仅在显式要求时设置 | 本命令不设 budget |
| 完成判定由 objective 的验收标准驱动 | DoD 写死可执行验证命令与 e2e 指标，不用模糊措辞 |

## Goal

- goal_id: `phase7.4-interactive-e2e-fix`
- 目标：完成 Phase 7.4 interactive e2e 失败修复（08-01 e2e 9 问中的 5 失败 + 2 误拦截），按已 ACCEPTED 计划执行 S0-S5。
- 前置条件：`.sisyphus/plans/interactive-e2e-fix-20260802.md` ACCEPTED（Mimo review，2026-08-02）；工作区 WIP B1/B2 为基线；S3 依赖 B1 口径 owner 确认。
- 设计来源：`.sisyphus/plans/interactive-e2e-fix-20260802.md`（唯一计划真源）+ `docs/implementation-control.md` Phase 7.4 节。
- 日期：2026-08-02

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自计划 S0-S5）

| slice | 内容 | 依赖 |
|-------|------|------|
| S0 | 失败轮 session 成对持久化 + tool_trace 恢复（纠正 `entry.status` 字段错误）+ 被拦截原文与触发词落盘 | 最先执行 |
| S1 | ToolFailure 回喂：失败作为下一轮 tool result，允许修正 section_ref/工具名/document_id；provider 畸形响应不回喂（S1 与 S4 都改 prompts，必须串行） | S0 之后 |
| S2 | `document_id` 缺失用 expected 补全；工具名有界归一化 | S1 之后 |
| S3 | 投资建议判据：main.py 预检改引单一真源 + 持仓/风格事实描述豁免 | 依赖 B1 口径 owner 确认，未确认前挂起 |
| S4 | prompt 引导：无事实目标尽早 final answer、空搜索不猜 section_ref | S1 review 通过后（与 S1 串行改 prompts） |
| S5 | 真源文档同步（design.md / implementation-control.md / AGENTS.md） | 全部实现 slice review 通过后 |

## Definition of Done

- 每个 slice：`implement -> tests -> diff review`，review 输出 `ACCEPTED`；无新增 plan-fix / re-review / evidence gate。
- 最小验证命令通过：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`。
- interactive 相关验证通过：`uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_stream_events.py -v --tb=short`。
- opt-in live e2e（总控手动执行）：原 9 问 0 条 `LLM 处理失败`、2 条误拦截（前十大重仓股 / 基金风格一致）解除、失败轮在 session 可见（含 tool_trace 与被拦截原文）。
- 真源文档与 AGENTS.md 同步完成，与代码行为一致。
- S3 口径未确认时：S3 挂起并记录阻塞原因，其余验收项不受影响。

## 禁止事项

- 不 commit、不 push。
- 不触碰 `fund_agent/fund/document_tools/docling_store.py`（与本计划无关的 WIP）。
- 不改 write set 之外的文件；不删除/覆盖既有 session 文件（只能向后兼容扩展）。
- 不新增 failure code；不把投资建议拦截从 fail-closed 改为 fail-open。
- 不重复规划或回退 WIP B1/B2；不扩大范围到 generate/audit/评分等非 interactive 链路。

## Status 流转

```text
active -> blocked（可选，S3 口径阻塞）-> complete
```

- 查看进度：`/goal status`
- 标记阻塞（含阻塞原因）：`/goal block`（或 `paused`）
- 完成（全部 DoD 达成后）：`/goal complete`
