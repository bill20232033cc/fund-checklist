# 2026-08-08 slice 设计：QDII direct 分支校正 table_citation（R6）

> 状态：🟡 计划待 Mimo review。来源：R1-R4 收口（`04f9554`）后发现 QDII direct 分支与 A 股 direct 分支存在 citation 不对称——A 股分支在 R1 已做「返回 (holdings, citation) + 调用方同步校正」，QDII 分支漏校。CIC-lite：计划 → Mimo review → 真源 → DS → controller review。

---

## 0. 背景与问题

`extract_annual_holdings`（`_extract_holdings_from_store`，extraction.py:1420+）对 QDII 基金以**直接扫描（list_tables + QDII 表头特征）为权威路径**，但最终 `AnnualHoldingsResult.citation` 却取自 LLM 路由结果（`routed.agent_result.citations`）的首个 TABLE citation，二者不一致时报告「持仓数据来源」会引用错表。

R1 已修复 A 股侧：`_extract_stock_holdings_from_tables` 返回 `(holdings, citation)`，调用方 `holdings, table_citation = direct` 同步校正（extraction.py:1543-1549）。QDII 侧未做对称处理。

## 1. 根因（代码 + 数据同源）

### 代码侧

- `_extract_qdii_holdings_from_tables`（extraction.py:6186-6230）：返回类型 `tuple[HoldingExtraction, ...] | None`，命中时只 `return tuple(holdings[:_HOLDINGS_TOP_N])`，**不返回 citation**。
- 调用方 QDII 分支（extraction.py:1519-1530）：`if direct: holdings = list(direct)`，**不更新 `table_citation`**。
- `table_citation` 在调用方最初由 `routed.agent_result.citations` 首个 TABLE citation 填充（extraction.py:1462-1467），QDII 查询「所有权益投资明细」的首表常为该节内**国家（地区）表 / 行业类别表 / 续表碎片**，而非持仓明细表。

### 数据侧（.fund_e2e_519696 五年 docling JSON vs 报告 519696-2025-analysis.md）

| 年份 | 报告当前「持仓数据来源」citation | 该 table_ref 实际内容 | QDII 持仓主表（首个通过 `_is_qdii_header_text`） | 结论 |
| --- | --- | --- | --- | --- |
| 2021 | table-0067, p.50 | 持仓表（序号/公司名称/证券代码/占基金…） | table-0067 | ✅ |
| 2022 | table-0068, p.55 | 行业类别表 | table-0069 | ❌ |
| 2023 | table-0062, p.48 | 国家（地区）表 | table-0064 | ❌ |
| 2024 | table-0059, p.48 | 国家（地区）表 | table-0061 | ❌ |
| 2025 | table-0062, p.50 | 续表碎片行表（International Resources…） | table-0061 | ❌ |

持仓行内容本身正确（2023 top-1 中国重汽 3808 HK 4.17 等），问题仅在 citation 指向错表。

## 2. 修复方案（镜像 A 股分支）

1. `_extract_qdii_holdings_from_tables` 返回类型改为 `tuple[tuple[HoldingExtraction, ...], Citation] | None`：
   - 命中时返回 `(tuple(holdings[:_HOLDINGS_TOP_N]), full_table.citation)`。
   - `full_table.citation` 是命中的 QDII 主表（表头通过 `_is_qdii_header_text` 的那张表）的 citation，与 A 股分支同约定：跨页续表合并/表头截断补齐时，citation 仍以主表为准（持仓列表起点与表头所在表）。
2. 调用方 QDII 分支（extraction.py:1525-1527）改为：
   ```python
   if direct:
       holdings, table_citation = direct
   ```
   `elif not holdings:` 的 query 兜底分支保持不变。
3. **不动** `_extract_qdii_table_with_continuations` / `_find_qdii_header_continuation` / `_merge_qdii_header_fragments` / `_holding_from_qdii_row` 的抽取逻辑：本 slice 只校正 citation，不改持仓行内容。
4. **不动** `_audit_holdings`（披露完整性审计走 routed citation，与本问题无关）。

## 3. 测试计划（tests/fund/service/test_extraction.py）

1. 更新 3 个现有 QDII direct 调用测试（返回契约变化）：`test_extract_qdii_holdings_from_tables_real_fixture_top10`（:5205）、`test_extract_qdii_holdings_from_tables_2023_truncated_header`（:5235）、`test_extract_qdii_holdings_cross_page_rank6_complete`（:5259）——改为解包 `(holdings, citation)`，新增断言 `citation.locator.table_ref` 与主表一致（2023 fixture → table-0064；fake 表 → table-main）。
2. 扩展 `test_extract_multi_year_holdings_qdii_519696_top10`（:5360）：新增 citation 断言 2024 → table-0061、2025 → table-0061。
3. 新增真值回归：2022 → table-0069、2023 → table-0064（用 `_QDII_2022/2023_DOCLING_JSON` fixture，报告修复后预期值）。
4. 新增 `_extract_holdings_from_store` 级测试：构造 fake tool_service / host，首个 TABLE citation 指向国家（地区）表，QDII 直扫命中真实持仓表后，断言 `AnnualHoldingsResult.citation.locator.table_ref` 为持仓表（覆盖调用方同步逻辑）。

## 4. allowed write set

- `fund_agent/service/extraction.py`（返回值契约 + 调用方同步）
- `tests/fund/service/test_extraction.py`
- 真源：`docs/design.md`（持仓 citation 规则一行：direct 扫描路径的 citation 必须指向实际消费的主表）、`docs/implementation-control.md`（R6 登记）

## 5. 验证命令

```bash
# 核心：QDII / holdings 抽取
uv run pytest tests/fund/service/test_extraction.py -k "qdii or QDII or holdings" -q --tb=short
# AGENTS.md 最小验证集
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
# 确定性 CLI 验收（不联网、不走 LLM）
uv run fund-checklist holdings --fund-code 519696 --years 2021,2022,2023,2024,2025 --work-dir .fund_e2e_519696
```

## 6. 验收真值

- 519696 五年 citation 与 QDII 持仓主表一致：2021→table-0067、2022→table-0069、2023→table-0064、2024→table-0061、2025→table-0061。
- 持仓行内容不回退：各年 top-10 名称/代码/占比与修复前一致（含 2023 表头截断、2025 跨页第 6 名）。
- A 股 004393 路径不回退（`test_extract_multi_year_holdings_004393_top10_regression` 通过）。
- `git diff --check` 干净；不 commit / 不 push（除非另行授权）。

## 7. 边界 / 禁止事项

- 不新增依赖、不联网、不引入 dayu 代码。
- 不改 `search_document` / reading tools 公共契约。
- 不把本 slice 与 R5 的 Q1/Q3（007466 interactive 命中错表）混排；R5 Q1/Q3 是 interactive 路由问题，另排。
