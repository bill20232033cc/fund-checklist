# multi-year 缺失原因透传 slice（2026-08-14 规划）

## 依据（用户问题与前提审查）

- 用户问题：「2022年净值增长率数据缺失，请排查原因，设计slice和goal命令修复」。
- 前提核查：仓库中「2022 净值增长率缺失」有明确实证对象——004393（安信企业价值优选混合A）。本地复现
  `uv run fund-checklist multi-year --fund-code 004393 --years 2021,2022,2023,2024,2025 --work-dir .fund_e2e_004393`
  输出 `missing_years: [2022]`，无任何原因说明。横向扫描（519696 五年 complete / 163415 缺 2025 / 040046 缺 2023 /
  007466 A/C 分段 / 159632、005680 本地 catalog 不足 3 年）确认「2022 缺失」是 004393 转型年个案。
- 若用户实际指其他基金/PDF/命令路径，需补充基金代码与复现命令；本 slice 以 004393 为验收对象。

## 根因（代码 + 源文档实证，2026-08-14）

1. **源文档事实（非解析 bug）**：004393 于 2022-08-08 转型（安信合作创新主题沪港深灵活配置混合 → 安信企业价值优选混合，
   基金合同生效日 2022-08-08）。2022 年报 3.2.1 业绩表只披露两个子期间，无「过去一年」行：
   - 转型前（2022-01-01 ~ 2022-08-07）：份额净值增长率 -7.20%、基准 -7.99%；
   - 转型后（2022-08-08 ~ 2022-12-31）：份额净值增长率 2.39%、基准 -3.68%。
   - 实证：`.fund_e2e_004393/docling_json/004393-2022-annual_report-045987cad6e956ad/*.docling.json`
     `texts[121]`「自转型日2022年8月8日起至2022年12月31日止…净值增长率为2.39%」、`texts[122]`「自2022年1月1日起至
     转型前一工作日2022年8月5日…净值增长率为-7.20%」。
2. **10F/10G 已正确 fail-closed**：直调 004393-2022 的 10F/10G 返回
   `NOT_FOUND`，message 已带可解释后缀（F2 修复，2026-08-09）：
   - 10F：「annual performance 过去一年完整字段缺失：业绩阶段表存在但无「过去一年」行（表内仅披露「自基金转型起至今」等期间，转型当年无全年份额净值增长率）」
   - 10G：「annual excess return 过去一年 ①－③ 字段缺失：…转型当年无全年份额净值增长率）」
3. **残留缺口（本 slice 修复对象）**：`aggregate_multi_year_annual_performance`
   （`fund_agent/service/extraction.py:1356`）对单年度 `DocumentToolError`（NOT_FOUND）在
   `except DocumentToolError as exc:`（`extraction.py:1410`，吞掉点 `continue` 在 `extraction.py:1421`）分支只对 `IDENTITY_MISMATCH` / `SCHEMA_DRIFT`
   return failure，其余一律 `continue`——10F/10G 的可解释 message 被**吞掉**，series 只记录 `missing_years: [2022]`
   裸年份：
   - `MultiYearAnnualPerformanceSeries`（`fund_agent/service/models.py:368-401`）无缺失原因字段；
   - `multi-year` CLI 输出 `asdict(s)`（`fund_agent/cli/main.py:759-763`）无解释；
   - interactive 工具证据文本 `_aggregate_evidence_text`（`fund_agent/agent/llm_tool_loop.py:2112`）
     只渲染 `missing_years=2022`（`llm_tool_loop.py:2123`），LLM 拿不到工具侧原因（scene.md 规则 10 已要求解释缺失原因，但原因不来自工具返回）。
4. **设计真源冲突**：`docs/design.md:1224` 10I 原裁决「`missing_years` 首批只返回年份列表，不新增 `missing_reasons`」。
   本 slice 是对该裁决的**修订**：F2（2026-08-09）已确立「可解释缺失、不伪造数据」口径，本次把缺失原因落到
   10I DTO 与全部消费层。

## 目标

1. 单年度抽取失败原因透传到 10I 聚合结果：`MultiYearAnnualPerformanceSeries` 新增
   `missing_year_notes`（year + reason），原因复用 10F/10G 的 NOT_FOUND message（已含可解释后缀）；
   catalog 无该年度年报时给出「未导入或未匹配」说明。
2. `multi-year` CLI 与 interactive 证据文本均带出原因，用户/LLM 不再面对裸 `missing_years`。
3. 验收含 CLI 端到端 smoke（AGENTS.md 硬约束）：004393 真实数据经 `multi-year` CLI，输出含
   「转型当年无全年份额净值增长率」解释。

## 非目标

- 不把「自基金转型起至今 / 转型前期间」数值写入 `annual_nav_growth_rate` 或 annual series（F2 硬口径，不伪造年度数据）。
- 不新增「转型子期间披露值」DTO 或抽取（若用户需要 2022 有数可看，需另行裁决新 disclosed-field 契约，本 slice 不做）。
- 不改 10F/10G 单年度抽取逻辑、failure code、DTO 数值语义、`source_period_label`。
- 不改 scene.md / interactive 终答守卫 / 投资建议拦截 / `_aggregate_citations`。
- 不新增 CLI 子命令/参数/依赖；不改 `docs/design.md` 10I 以外的契约行（仅修订 `missing_year_notes` 相关两处）。
- 不更新 AGENTS.md（无执行规则变更）；不 commit / push。

## 决策

1. **DTO（`fund_agent/service/models.py`）**：新增 frozen dataclass
   `MultiYearMissingYearNote(year: int, reason: str)`；`MultiYearAnnualPerformanceSeries` 末尾追加
   `missing_year_notes: tuple[MultiYearMissingYearNote, ...] = ()`（带默认值，向后兼容现有 keyword/positional 构造）。
2. **聚合（`fund_agent/service/extraction.py:1356`）**：
   - 新增局部 `missing_notes: dict[int, str]`；
   - `document is None`（catalog 无该年，`extraction.py:1384`）→ `missing_notes[year] = "catalog 中无该年度年报（未导入或未匹配）"`；
   - `except DocumentToolError as exc:` 中非 `IDENTITY_MISMATCH` / `SCHEMA_DRIFT` 分支改为
     `missing_notes[year] = exc.message` 后 `continue`（不再静默丢弃）；
   - `_multi_year_series_for_share`（`extraction.py:4654`）追加参数 `missing_notes`，构造
     `missing_year_notes = tuple(MultiYearMissingYearNote(year=y, reason=missing_notes[y]) for y in missing_years if y in missing_notes)`。
   - reason 不截断：10F/10G message 为有界短文案（约 70 字符）。
3. **CLI（`fund_agent/cli/main.py:759-763`）**：代码零改动——`asdict(s)` 自动带出嵌套 dataclass
   `missing_year_notes`；实现时复查输出形状，若异常再显式组装。
4. **interactive 证据文本（`fund_agent/agent/llm_tool_loop.py:2123`）**：保留 `missing_years=...` 行，
   在其后逐条追加 `missing_year_note={year}: {reason}`；scene.md 规则 10 已要求「原因以工具返回的 message/note 为准」，无需改 scene.md。
5. **文档同步**：`docs/design.md` 10I 节把「不新增 missing_reasons」修订为「`missing_years` 保持年份列表，
   新增 `missing_year_notes`（year + reason）逐条解释缺失原因；数值语义与 failure taxonomy 不变」；
   `docs/implementation-control.md` 当前状态补一行；`tests/README.md` 验证命令一句；`README.md` multi-year 小节补一句说明（可选）。

## 实施清单（allowed write set）

修改：
- `fund_agent/service/models.py`（新增 `MultiYearMissingYearNote` + series 字段）
- `fund_agent/service/extraction.py`（aggregate 收集 missing_notes + `_multi_year_series_for_share` 透传）
- `fund_agent/agent/llm_tool_loop.py`（`_aggregate_evidence_text` 渲染 `missing_year_note`）
- `tests/fund/service/test_extraction.py`（新增 2 用例 + 既有 3 个 aggregate 用例补 `missing_year_notes == ()` 断言）
- `tests/fund/agent/test_llm_tool_loop.py`（`_fake_multi_year_result` 支持 notes + 新增 evidence 渲染断言）
- `tests/fund/cli/test_cli.py`（新增 `missing_year_notes` JSON 输出用例）
- `tests/fund/test_e2e_regression.py`（新增 004393 真实数据 CLI smoke：`.fund_e2e_004393` 缺失则 skip）
- `docs/design.md` / `docs/implementation-control.md` / `tests/README.md`（README.md 可选）

禁止修改：AGENTS.md / fund_agent/host/ / fund_agent/fund/ / fund_agent/cli/main.py（除非 asdict 复查异常）/
scene.md / FailureCode / DocumentToolError / 10F/10G 单年度逻辑 / 新依赖 / commit / push。

## 测试

1. `tests/fund/service/test_extraction.py`：
   - `test_aggregate_multi_year_annual_performance_carries_missing_year_note`：5 年 documents，monkeypatch
     10F fake extractor 对 2022 返回 `failure=NOT_FOUND`（message 含「转型当年无全年份额净值增长率」），断言
     `series.missing_years == (2022,)` 且 `missing_year_notes[0]` year=2022、reason 含「转型当年无全年份额净值增长率」；
     其余年份 rows/citations 不回退。
   - `test_aggregate_multi_year_annual_performance_carries_not_in_catalog_note`：requested_years 含 catalog 外年份，
     断言对应 note reason 含「catalog 中无该年度年报」。
   - 既有 `returns_complete_five_year_series` / `returns_partial_for_four_complete_years` /
     `returns_partial_for_three_complete_years` 补 `assert series.missing_year_notes == ()`。
2. `tests/fund/agent/test_llm_tool_loop.py`：`_fake_multi_year_result` 增加 `missing_notes` 参数；
   新增用例断言 `_aggregate_evidence_text` 输出含 `missing_year_note=2022: ...`。
3. `tests/fund/cli/test_cli.py`：新增 `test_multi_year_output_includes_missing_year_notes`
   （fake series 带 1 条 note，断言 stdout JSON `series[0].missing_year_notes` 含 `{"year": 2022, "reason": "..."}`）。
4. `tests/fund/test_e2e_regression.py`：新增 `test_multi_year_004393_missing_year_note`
   （`.fund_e2e_004393` 缺失 skip；`_run(["multi-year", "--fund-code", "004393", "--years",
   "2021,2022,2023,2024,2025", "--work-dir", str(work_dir)])` 断言 exit 0、`series[0].missing_year_notes`
   含 year=2022 且 reason 含「转型当年无全年份额净值增长率」）。

## 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "aggregate_multi_year or missing_year_note" -v --tb=short
uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "aggregate or missing_year" -v --tb=short
uv run pytest tests/fund/cli/test_cli.py -k "multi_year" -v --tb=short
uv run pytest tests/fund/test_e2e_regression.py -v --tb=short
# AGENTS.md 最小验证集
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short
# 真实数据 CLI 复跑（人工核验输出）
uv run fund-checklist multi-year --fund-code 004393 --years 2021,2022,2023,2024,2025 --work-dir .fund_e2e_004393
git diff --check
```

## 验收口径

- `missing_year_notes` 对每个缺失年份给出原因；004393-2022 原因含「转型当年无全年份额净值增长率」。
- 现有 10I coverage 语义（complete/partial、3-5 年 bounded、share class 独立）零变化。
- 既有测试全绿（不回退）；`git diff --check` 干净；未 commit / push。

## 交接报告形状（实现方回传）

changed files / diff 摘要 / 实际测试命令与输出 / 004393 CLI 复跑输出片段（含 missing_year_notes）。
