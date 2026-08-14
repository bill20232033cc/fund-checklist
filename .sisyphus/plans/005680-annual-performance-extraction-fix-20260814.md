# 005680-2022 年度业绩抽取缺口修复 slice（2026-08-14 规划）

## 依据（用户前提纠正与实证）

- 用户纠正：问题对象是 **005680（财通资管价值成长混合）2022 年报的「近一年净值增长率」未抽取**，不是此前假设的 004393 转型年。
- 前置说明：按 004393 转型年设计的「multi-year 缺失原因透传」slice（`.sisyphus/plans/multi-year-missing-reason-slice-20260814.md`）已实现并全绿（197 passed），保留为支撑改动——它把 005680-2022 的失败原因「annual performance 目标 title-family 未找到」暴露出来；本 slice 修复该真实抽取缺口。
- 本地复现：`uv run fund-checklist multi-year --fund-code 005680 --years 2021,2022,2023,2024,2025 --work-dir .fund_checklist_005680`
  → `missing_years: [2022]`，note = 「annual performance 目标 title-family 未找到」。

## 根因（代码 + 源文档实证，2026-08-14）

1. **Docling section 切分异常 → title-family 判定漏检**：005680-2022 的 3.2.1 标题
   「基金份额净值增长率及其与同期业绩比较基准收益率的比较」嵌在「3.2 基金净值表现」section
   （`section-0041`）正文内，agent answer 为 raw excerpt 格式（首行 = 「3.2 基金净值表现」）。
   `_target_title_lines`（`fund_agent/service/extraction.py:5230`）只提取首行 /「来源章节:」/
   「表格标题:」前缀行 /「相关表格:」后一行，漏掉正文里的 3.2.1 标题 →
   `_annual_performance_source_section_refs`（`extraction.py:5860-5866`）判
   「目标 title-family 未找到」→ 10F（`_extract_annual_performance_fields`）与 10G
   （`_extract_annual_excess_return_fields`）同时 fail-closed。
   - 对照实证：005680-2021/2023、007466-2022、004393-2025 的 3.2.1 均为独立 section 标题
     （answer 首行即标题），`_target_title_lines` 首行命中，不受影响。
   - 005680-2022 的 host 结果本身正常：citations = [(`section`, `section-0041`, None),
     (`table`, `section-0041`, `table-0010`)]；表格内容完整（`过去一年 | -22.35% | -15.20% | -7.15%`）。
2. **修复 1 后暴露的 share-scope 误绑**：`_annual_performance_share_scope_from_rows`
   （`extraction.py:5771-5780`）把「自基金合同生效起至今」一律映射 C。005680 为非转型基金，
   A/C 两类业绩表都用「自基金合同生效起至今」；A 表（`table-0010`，含「过去三年」行，-22.35%）
   会被误绑成 C，C 表（`table-0011`，无「过去三年」，-22.59%）未被 cite 不进入抽取。
   - 实证（`section-0041` 内两个完整表头表）：`table-0010` = A（过去三个月/六个月/一年/三年/自基金合同生效起至今），
     `table-0011` = C（三个月/六个月/一年/自基金合同生效起至今）。
   - 正确输出应为 A 类 -22.35% / -15.20% / -7.15%（citation `table-0010`）。
3. 全链路原型验证（本机 monkeypatch 两处修复后）：10F 返回 `annual_nav_growth_rate=-22.35%`、
   `annual_benchmark_return_rate=-15.20%`、10G 返回 `annual_excess_return=-7.15%`，share=A，table-0010；
   `aggregate_multi_year_annual_performance` 005680 覆盖 2021-2025 全绿。

## 目标

1. 10F/10G 的 title-family 判定支持 raw-excerpt answer 格式：title-family 命中 = 前缀行命中
   OR `_ANNUAL_PERFORMANCE_TITLE_FAMILY in result.answer`（正文兜底）。
2. 非转型 A/C 对的行级 share-scope 判别：含「过去三年/过去五年」行 → A（历史更长的份额类别，
   A 为原始/主份额）；「自基金转型起至今」→ A 保留；仅「自基金合同生效起至今」→ C 保留。
3. 005680 multi-year 2021-2025 全覆盖：2022 A 类 = -22.35% / -15.20% / -7.15%（citation `table-0010`）；
   2021/2023/2024/2025 不回退；004393-2022 转型年仍 fail-closed 带「转型当年无全年」解释。

## 非目标

- 不把 C 表（`table-0011`，未被 cite）纳入抽取：10F cited-table-only 契约不变（005680 各年 C 类
  覆盖不一致是既有行为，另排）。
- 不改 `_performance_table_share_scopes` 的 label-count 顺序绑定主路径（`extraction.py:6158`）。
- 不改 004393-2022 转型年口径（「自基金转型起至今 → A」判别保留）。
- 不改已实现的多年度 missing_year_notes / 10I DTO / llm_tool_loop 证据文本。
- 不新增 CLI 子命令/参数/依赖；不 commit / push。

## 决策

1. **`_annual_performance_source_section_refs`（`extraction.py:5860`）**：
   ```python
   title_lines = _target_title_lines(result.answer)
   title_family_hit = any(_ANNUAL_PERFORMANCE_TITLE_FAMILY in line for line in title_lines) or (
       _ANNUAL_PERFORMANCE_TITLE_FAMILY in result.answer
   )
   if not title_family_hit:
       raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 目标 title-family 未找到")
   ```
   answer 为有界公开输出；下游仍要求 SECTION citation + TABLE citation + 列签名 + 「过去一年」行，误放行风险有界。
2. **`_annual_performance_share_scope_from_rows`（`extraction.py:5771`）**：在「自基金合同生效起至今 → C」
   之前增加「过去三年/过去五年 → A」判别（行标签去空白归一化后匹配）：
   ```python
   if any("自基金转型起至今" in cell for cell in normalized_rows):
       return _SHARE_SCOPE_A
   if any(("过去三年" in cell or "过去五年" in cell) for cell in normalized_rows):
       return _SHARE_SCOPE_A
   if any("自基金合同生效起至今" in cell for cell in normalized_rows):
       return _SHARE_SCOPE_C
   return None
   ```
   语义：非转型 A/C 对中，A 是历史更长的份额类别（多年度行存在）；C 仅合同生效起至今。
3. 不改 `_target_title_lines` 本身（被 fee_rates / holdings 等 profile 共用，避免全局松绑）。

## 实施清单（allowed write set）

修改：
- `fund_agent/service/extraction.py`（仅 `_annual_performance_source_section_refs` + `_annual_performance_share_scope_from_rows` 两处）
- `tests/fund/service/test_extraction.py`（新增 title-family raw-excerpt 判定用例 + share-scope 判别用例（非转型 A/C + 转型回归）+ 可选 10F 全链路 fake 用例）
- `tests/fund/test_e2e_regression.py`（新增 `test_multi_year_005680_2022_covered` 真实数据：`.fund_checklist_005680` 缺失 skip，断言 2022 covered、A 类 -22.35% / -15.20%、2021/2023-2025 不回退）
- `docs/design.md`（10F title-family 判定补 raw-excerpt 兜底一句）
- `docs/implementation-control.md`（当前状态一行）
- `tests/README.md`（验证命令一句）

禁止修改：AGENTS.md / fund_agent/host/ / fund_agent/fund/ / fund_agent/cli/main.py / models.py / llm_tool_loop.py /
scene.md / FailureCode / DocumentToolError / 10F/10G DTO 契约 / 多年度 DTO / `_target_title_lines` /
`_performance_table_share_scopes` 主路径 / 004393-2022 转型年口径 / commit / push。

## 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "annual_performance or share_scope or missing_year_note" -v --tb=short
uv run pytest tests/fund/test_e2e_regression.py -v --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short
uv run fund-checklist multi-year --fund-code 005680 --years 2021,2022,2023,2024,2025 --work-dir .fund_checklist_005680
# 004393 转型年回归（仍应为可解释缺失）
uv run fund-checklist multi-year --fund-code 004393 --years 2021,2022,2023,2024,2025 --work-dir .fund_e2e_004393
git diff --check
```

## 验收口径

- 005680 multi-year 输出 2022 covered（A 类 -22.35% / -15.20% / -7.15%，citation `table-0010`），
  2021/2023/2024/2025 不回退；004393-2022 仍为「转型当年无全年份额净值增长率」可解释缺失；
  既有测试全绿；`git diff --check` 干净；未 commit / push。

## 交接报告形状（实现方回传）

changed files / diff 摘要 / 实际测试命令与输出 / 005680 与 004393 multi-year 复跑输出片段。
