# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/goals/preference-p3-quarterly-snapshot-goal-20260821.md 实施「Slice P3：preference-snapshot（季度偏好快照 + 四问反思模板）」slice（设计真源：docs/design.md §6.26.7，2026-08-21 已定稿：报告内容 = 问卷基线（总分 + 五维子分 + 辅助 C1-C5）+ 本季度行为证据摘要（来自 preferences.db memos 表）+ 四问反思模板 + 固定免责声明；MVP 只输出声明 vs 行为对照与反思，不输出任何调仓/配置建议）。前置：Slice P1（flomo-import）与 Slice P2（preference-questionnaire）已实现。AGENTS.md / docs/design.md 已由 controller 同步，禁止修改。只走 CIC-lite implement -> tests -> diff review。实施内容：① 新增 fund_agent/preferences/snapshot.py——INVESTMENT_KEYWORDS 常量（基金/买入/卖出/定投/赎回/申购/加仓/减仓/止盈/止损/亏损/收益/回撤/估值/仓位/净值/分红 等，至少 16 词）+ QUARTER_REGEX（YYYYQ[1-4]）+ build_behavior_summary(memos: list[dict], quarter: str) 按季度日期范围过滤 + 关键词命中过滤，输出 [{created_at, content, hit_keywords}] 摘要（引用原文 + 时间，不读原始 HTML）+ generate_snapshot(store, quarter, *, bank) -> PreferenceSnapshot（四问反思模板字段：actual_actions="" / consistent_with_statement="" / deviation="" / next_adjustments=""，答案留空由用户填写）+ 固定免责声明文案（与 design §6.26.7 逐字一致：「本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。」）+ 写入 preferences/quarters/<quarter>/preference-snapshot.json 与同名 .md（json 含 quarter/created_at/questionnaire 基线（总分+五维子分+辅助 C1-C5，取该季度最近一次问卷结果，无则 null）/behavior_summary/reflection 四问/disclaimer）；② 修改 fund_agent/preferences/store.py——新增 preference_snapshots 表（id TEXT PK, quarter TEXT, created_at TEXT, questionnaire_result_id TEXT NULL, behavior_summary_json TEXT, reflection_json TEXT, disclaimer TEXT）+ save_snapshot(store, snapshot) + query_memos_by_date_range(store, start, end)（按 created_at 过滤）+ latest_questionnaire_result(store, quarter_end)（≤ quarter_end 最近一次）；③ 修改 fund_agent/cli/main.py——注册 preference-snapshot 子命令（--work-dir 默认 .fund_checklist、--quarter 必填 YYYYQn、--bank 可选）+ _run_preference_snapshot_command（quarter 非法 → schema_drift 退出码 2；无问卷结果时行为证据摘要仍生成、问卷基线记 null；成功输出快照 json/md 路径；不接 LLM）；④ 新增 tests/fund/preferences/test_snapshot.py（关键词过滤：命中/未命中；季度日期范围：跨季度 memo 不混入；四问模板字段齐全；免责声明逐字；无问卷结果 → null 基线；快照落盘 json+md）；⑤ 新增 tests/fund/cli/test_cli_preference_snapshot.py（run_cli 端到端：fixture db（预置 memos + 问卷结果）→ 退出码 0 + 快照文件存在 + json 结构；--quarter 非法 → 退出码 2）。allowed write set：fund_agent/preferences/snapshot.py 新增、fund_agent/preferences/store.py、fund_agent/cli/main.py、tests/fund/preferences/ 新增、tests/fund/cli/test_cli_preference_snapshot.py 新增、fund_agent/README.md 与 tests/README.md 各补 1 句。禁止修改 AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/（本 goal 文件除外）/ fund_agent/fund|service|host|agent / 存量 quarterly-top10-holdings-fix 涉及文件 / Slice P1/P2 已实现文件（flomo_parser.py、questionnaire.py、questionnaire_data/、flomo-import 与 preference-questionnaire CLI）；禁止新增第三方依赖；禁止输出调仓/配置建议；禁止接 LLM；不 commit、不 push。验收：uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_preference_snapshot.py -v --tb=short 全通过，且最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 回归通过；输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/preference-p3-quarterly-snapshot-goal-20260821.md
```

## Goal

- goal_id: `preference-p3-quarterly-snapshot-20260821`
- 目标：实施投资者偏好分析 MVP Slice P3——`preference-snapshot`（季度偏好快照：问卷基线 + 行为证据摘要 + 四问反思模板 + 免责声明），确定性、不接 LLM、不输出调仓建议。
- 前置条件：`docs/design.md` §6.26.7 已定稿；Slice P1（flomo-import）与 Slice P2（preference-questionnaire）已实现。
- 设计来源：`docs/design.md` §6.26.7（季度偏好快照与合规边界）。
- 日期：2026-08-21

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope

| 项 | 内容 |
|-------|------|
| 新增模块 | `fund_agent/preferences/snapshot.py`（INVESTMENT_KEYWORDS / build_behavior_summary / generate_snapshot） |
| 修改模块 | `fund_agent/preferences/store.py`（preference_snapshots 表 + save_snapshot / query_memos_by_date_range / latest_questionnaire_result）、`fund_agent/cli/main.py`（preference-snapshot 子命令） |
| 新增测试 | `tests/fund/preferences/test_snapshot.py`、`tests/fund/cli/test_cli_preference_snapshot.py` |
| 文档 | `fund_agent/README.md`、`tests/README.md`（各 1 句） |
| 禁止 | AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/（本 goal 文件除外）/ fund_agent/fund|service|host|agent / 存量 quarterly-top10-holdings-fix 涉及文件 / Slice P1/P2 已实现文件 / 新第三方依赖 / 输出调仓/配置建议 / LLM / commit / push |

## 验收（DoD）

- `uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_preference_snapshot.py -v --tb=short` 全通过。
- 最小验证集 `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short` 回归通过。
- 交接报告：changed files / diff 摘要 / 实际测试命令与输出。
