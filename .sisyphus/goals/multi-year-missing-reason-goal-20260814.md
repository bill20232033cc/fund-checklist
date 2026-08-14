# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/multi-year-missing-reason-slice-20260814.md 实施「multi-year 缺失原因透传」slice（plan 已于 2026-08-14 规划；根因已实证：004393-2022 为转型当年（2022-08-08 合同生效），年报 3.2.1 表只披露「转型前 2022-01-01~08-07：-7.20%」与「转型后 2022-08-08~12-31：2.39%」两个子期间，无「过去一年」行；10F/10G 已 fail-closed 返回带「转型当年无全年份额净值增长率」可解释后缀的 NOT_FOUND message，但 aggregate_multi_year_annual_performance（extraction.py:1356，吞掉点 except/continue 在 extraction.py:1410/1421）对单年度 NOT_FOUND 一律 continue 吞掉 message，导致 multi-year CLI 输出与 interactive 证据文本只有裸 missing_years=[2022]，无原因；docs/design.md:1224 10I 原裁决「不新增 missing_reasons」一并修订）。只走 CIC-lite implement -> tests -> diff review。实施内容：① fund_agent/service/models.py 新增 frozen dataclass MultiYearMissingYearNote(year:int, reason:str)（中文 docstring），MultiYearAnnualPerformanceSeries 末尾追加 missing_year_notes: tuple[MultiYearMissingYearNote, ...] = ()。② fund_agent/service/extraction.py 的 aggregate_multi_year_annual_performance：新增局部 missing_notes: dict[int,str]；document 为 None（catalog 无该年）时记录 reason「catalog 中无该年度年报（未导入或未匹配）」；except DocumentToolError 中非 IDENTITY_MISMATCH/SCHEMA_DRIFT 分支改为 missing_notes[year]=exc.message 后 continue（不再静默丢弃，message 已含 10F/10G 可解释后缀，不截断）；_multi_year_series_for_share 追加 missing_notes 参数并构造 missing_year_notes（仅该 series missing_years 内的年份）。③ fund_agent/agent/llm_tool_loop.py 的 _aggregate_evidence_text：保留 missing_years=... 行，其后逐条追加 missing_year_note={year}: {reason}。④ 文档：docs/design.md 10I 节把「missing_years 首批只返回年份列表，不新增 missing_reasons」修订为「missing_years 保持年份列表，新增 missing_year_notes（year+reason）逐条解释缺失原因；数值语义与 failure taxonomy 不变」；docs/implementation-control.md 当前状态补一行；tests/README.md 验证命令一句；README.md multi-year 小节补一句（可选）。allowed write set 严格按 plan 清单（7 修改：fund_agent/service/models.py、extraction.py、llm_tool_loop.py、tests/fund/service/test_extraction.py、tests/fund/agent/test_llm_tool_loop.py、tests/fund/cli/test_cli.py、tests/fund/test_e2e_regression.py；4 文档：docs/design.md、docs/implementation-control.md、tests/README.md、README.md 可选），禁止动 AGENTS.md / fund_agent/host/ / fund_agent/fund/ / fund_agent/cli/main.py（asdict 自动透传新字段，实现时复查输出形状，若异常再显式组装）/ scene.md / FailureCode / DocumentToolError / 10F/10G 单年度抽取逻辑与 failure code / 把「自基金转型起至今/转型前期间」数值写入 annual series（F2 硬口径，不伪造年度数据）/ 新增 CLI 子命令与参数 / 新依赖 / commit / push。测试：tests/fund/service/test_extraction.py 新增 2 用例（monkeypatch 10F fake extractor 对 2022 返回 NOT_FOUND failure 含「转型当年无全年份额净值增长率」，断言 series.missing_years==(2022,) 且 missing_year_notes[0] 的 year/reason；catalog 外年份 note reason 含「catalog 中无该年度年报」）+ 既有 3 个 aggregate 用例补 assert series.missing_year_notes == ()；tests/fund/agent/test_llm_tool_loop.py 的 _fake_multi_year_result 增加 missing_notes 参数 + 新增断言 _aggregate_evidence_text 输出含 missing_year_note=2022；tests/fund/cli/test_cli.py 新增 test_multi_year_output_includes_missing_year_notes（stdout JSON series[0].missing_year_notes 含 {"year":2022,"reason":...}）；tests/fund/test_e2e_regression.py 新增 test_multi_year_004393_missing_year_note（.fund_e2e_004393 缺失则 skip，_run(["multi-year","--fund-code","004393","--years","2021,2022,2023,2024,2025","--work-dir",str(work_dir)]) 断言 exit 0 且 missing_year_notes 含 year=2022、reason 含「转型当年无全年份额净值增长率」）。验收命令：uv run pytest tests/fund/service/test_extraction.py -k "aggregate_multi_year or missing_year_note" -v --tb=short、uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "aggregate or missing_year" -v --tb=short、uv run pytest tests/fund/cli/test_cli.py -k "multi_year" -v --tb=short、uv run pytest tests/fund/test_e2e_regression.py -v --tb=short、最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 全部通过；真实数据复跑 uv run fund-checklist multi-year --fund-code 004393 --years 2021,2022,2023,2024,2025 --work-dir .fund_e2e_004393 输出 missing_year_notes 含「转型当年无全年份额净值增长率」；git diff --check 干净。输出交接报告（changed files / diff 摘要 / 实际测试命令与输出 / 004393 CLI 复跑输出片段）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/multi-year-missing-reason-goal-20260814.md
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

- goal_id: `multi-year-missing-reason-20260814`
- 目标：实施「multi-year 缺失原因透传」，按已规划计划完成实现 + 测试。
- 前置条件：`.sisyphus/plans/multi-year-missing-reason-slice-20260814.md` 已规划（2026-08-14，含根因实证与 line 级现状）。
- 设计来源：`.sisyphus/plans/multi-year-missing-reason-slice-20260814.md`（唯一计划真源）。
- 日期：2026-08-14

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自 plan）

| 项 | 内容 |
|-------|------|
| DTO | `fund_agent/service/models.py`：新增 `MultiYearMissingYearNote(year, reason)`；`MultiYearAnnualPerformanceSeries` 追加 `missing_year_notes`（默认 `()`） |
| 聚合 | `fund_agent/service/extraction.py`：`aggregate_multi_year_annual_performance` 收集 `missing_notes`（catalog 缺失 / 单年度抽取失败 message），不再静默 `continue`；`_multi_year_series_for_share` 透传构造 notes |
| 证据文本 | `fund_agent/agent/llm_tool_loop.py`：`_aggregate_evidence_text` 追加 `missing_year_note={year}: {reason}` |
| CLI | `fund_agent/cli/main.py` 代码零改动（`asdict` 自动带出新字段；实施时复查形状） |
| 测试 | `test_extraction.py`（+2 用例、既有 3 用例补断言）、`test_llm_tool_loop.py`（+1 用例）、`test_cli.py`（+1 用例）、`test_e2e_regression.py`（004393 真实数据 CLI smoke） |
| 文档 | `docs/design.md`（10I missing_reasons 裁决修订）、`docs/implementation-control.md`（1 行）、`tests/README.md`（1 句）、`README.md`（可选 1 句） |
| 禁止 | AGENTS.md / host/fund 层 / cli/main.py（除非复查异常）/ scene.md / 10F/10G 单年度逻辑与 failure code / 期间数值写入 annual series / 新 CLI 参数 / 新依赖 / commit / push |
