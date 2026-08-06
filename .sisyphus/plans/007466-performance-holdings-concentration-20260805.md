# 2026-08-05 007466 业绩抽取修复 + 关联 ETF 持仓集中度 slice

> 状态：🟡 待 Mimo review（排在前一 interactive 质量修复 slice 完成后实施）。来源：007466-2025 PDF 报告人工验收发现 2024/2025 业绩数据缺失且 Ch2 表格错填费率行；持仓集中度需改用标的 ETF 512890 数据。

---

## 1. 现象（实证）

`.fund_e2e_007466/reports/007466-2025-analysis.md`（及 PDF）：

- Ch0 概览：最新净值增长率 / 基准收益率 / 超额收益 均为 N/A；超额收益趋势只列到 2023。
- Ch2 表格 2024/2025 行：`| 2024 | 0.50% | 0.10% | 0.25% | 不收取 |` — 这列其实是**费率数据**（管理费 0.50% / 托管费 0.10% / 销售C 0.25% / A 不收取），被错填进业绩列（2021-2023 业绩正常）。
- 持仓集中度：007466 为 ETF 联接（≥90% 持有目标 ETF），自身前十大持仓无集中度意义。

## 2. 根因（代码实证）

### 2.1 业绩抽取失败（2024/2025）

`FundReadingService._extract_report_performance_with_citations` 只返回 2021-2023：

- 2024：`_extract_annual_performance_fields` → NOT_FOUND「annual performance 过去一年完整字段缺失」（extraction.py:4974）。
- 2025：`_performance_past_year_row` → NOT_FOUND「performance_returns 过去一年行无法唯一识别」（extraction.py:5343）。

数据实际存在（docling 表）：

| 年份 | 表 | 结构 | 过去一年（A类） |
|---|---|---|---|
| 2024 | table-15 | A 类全表（有表头） | 21.06% / 17.00% / 4.06% |
| 2024 | table-17 | C 类部分段（无表头，从过去六个月起） | （C 类） |
| 2025 | table-13 | A 类全表（有表头） | 4.18% / 0.47% / 3.71% |
| 2025 | table-14 | A 类尾部 + C 类全段（21 行合并表） | 多段过去一年 |

根因：10F/10D 抽取按「单表内唯一 过去一年 行 + 表头列定位 + share_scope」假设；007466 的 3.2.1 表按 A/C 份额拆成多表/分段表，C 类段缺表头、A/C 合并表出现多个 过去一年 行 → 2024 列/行定位失败、2025 唯一性 raise。

### 2.2 报告层错填

性能 dict 缺 2024/2025 → 报告数据表对应单元格为空 → LLM 组装 Ch2 时把相邻费率行（0.50/0.10/0.25/不收取）错位填入业绩列。抽取修复为主，数据表防错填为辅。

### 2.3 关联 ETF 数据可用性（Task B）

`.fund_checklist_512890`（华泰柏瑞中证红利低波动 ETF，512890）2021-2025 齐全；`_extract_holdings_from_store` 实测 2024/2025 各 10 行正常。

## 3. 修复规格

### Task A：业绩抽取 A/C 分段表支持（extraction.py）

- `_performance_past_year_row` 的「单表内 >1 个过去一年行即 raise」改为**按 share_scope 过滤**：每个份额类别取该 scope 的过去一年行；A/C 合并表（table-14 类）按行内份额标签切段。
- `_extract_annual_performance_fields` 支持无表头部分表：表头列定位失败时用同 section 相邻 A 类表头对齐（或按行标签+列位置回退），不再整体 not_found。
- 验收真值（A 类过去一年）：2024 净值增长率 21.06% / 基准 17.00% / 超额 4.06%；2025 净值增长率 4.18% / 基准 0.47% / 超额 3.71%。
- 报告数据表防错填：性能字段缺失时单元格显式标「缺失」（不写相邻费率值）；Ch2 prompt/data_table 组装禁止用其他列数据补空。

### Task B：关联 ETF 持仓集中度（512890）

- 007466 generate 时显式关联标的 ETF：CLI/request 新增可选参数（如 `--holdings-source-fund 512890 --holdings-source-workdir .fund_checklist_512890`），Service 层从关联源提取 top-10 持仓并计算前五/前十集中度。
- 报告注明数据来源：持仓集中度指标标注「来源：标的 ETF 512890 年报」；007466 自身持仓仅作展示（如披露），不参与集中度评分。
- 缺省行为：未指定关联源时保持现状（本基金持仓），不破坏既有调用方。

## 4. allowed write set

- `fund_agent/service/extraction.py`（业绩 A/C 分段表 + 关联持仓源解析）
- `fund_agent/service/models.py`（可选：request 关联源字段）
- `fund_agent/cli/main.py`（generate 关联源参数）
- 报告数据表/chapter prompt 组装（如涉及）：`fund_agent/service/chapter_generator.py` 或 data_table 组装点（DS 定位最小改动）
- 测试：`tests/fund/service/test_extraction.py`、`tests/fund/service/test_audit_pipeline.py`、`tests/fund/cli/test_cli.py`
- 真源文档：`docs/design.md`、`docs/implementation-control.md`、（`AGENTS.md` 如需）

禁止：改 search_document 公共契约；改 10F/10G 既有成功路径语义（2021-2023 不回退）；改 512890 数据；触碰前序 slice 未提交区域。

## 5. 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "performance or holdings or concentration" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py tests/fund/cli/test_cli.py -q --tb=short
```

实数据 smoke：

```bash
# 007466 五年业绩（A 类过去一年）：2024 21.06/17.00/4.06；2025 4.18/0.47/3.71
# 512890 关联持仓集中度：2025 前五/前十合计
```

## 6. 验收口径

- 007466 五年业绩 dict 含 2024/2025（真值如 §3）；Ch2 表格 2024/2025 行 = 业绩值，费率行独立不串位；Ch0 最新业绩非 N/A。
- 关联 ETF 持仓集中度：512890 2025 top-10 → 前五/前十合计正确，报告标注来源基金。
- 既有测试不回退（含 163415 五年业绩/费率实数据）；`git diff --check` 干净；不 commit / push。

## 7. stop conditions

- 触碰 §4 禁止事项 → 停止。
- 任一验证命令新增失败 → 停止。
- 2021-2023 既有业绩抽取回退 → 停止。
