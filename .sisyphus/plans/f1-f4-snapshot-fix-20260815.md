# F1-F4 快照修复 slice（2026-08-15 设计）

## 任务界定（口径）

- 来源：MiMo deepreview `docs/reviews/code-review-20260815-094136.md` 的 4 项 findings（F1 严重 / F2 高 / F3 中 / F4 低）。
- 用户裁决：F1-F4 全部修复；DS 使用现有 pane（agents:0.1）；先 plan review 通过后实施。
- 前置：findings 已经 controller 逐条 grep 核验，全部真实存在。

## 实证（2026-08-15，代码核验）

1. **F1（严重）**：`snapshot_extraction.py:206` `risk_notes=single_investor` 误赋值；无 `_RISK_NOTES_QUERY` 常量（仅 `_SINGLE_INVESTOR_QUERY`，line 40）；无独立风险提示抽取。影响季报 Ch4 / 半年报 Ch5 风险提示节。
2. **F2（高）**：`snapshot_extraction.py:549-553` 份额变动文本回退 4 个正则使用字面 `d`/`s`（如 `期初s*基金份额总额[^d]{0,8}(d[d,，.]*(?:.d+)?)`），`re.search` 恒 None；现有测试 `test_extract_share_change_semiannual_labels` 仅覆盖表格路径（search 命中 table_ref）。
3. **F3（中）**：`snapshot_generator.py:17` `_period_label(template_id, report_year, quarter=None)` 无 `period` 参数，line 29 半年报恒返回「上半年」；`_snapshot_common_header`（line 39 接收 `period`，line 47 未透传）；`generate_snapshot_template_chapter`（约 line 296-325）未取 `period`；CLI `--period` choices=["H1"]（main.py:239）。
4. **F4（低）**：`audit_pipeline.py:2471` 审计上下文 `for cid in range(1, 7)` 硬编码；line 2192 已用 `self._template.front_chapter_ids`。三模板 front ids：annual (1..6)、quarterly (1..4)、semiannual (1..5)，均 ⊂ range(1,7)，当前行为等价。

## 设计

### F1（严重，snapshot_extraction.py）

- 新增常量 `_RISK_NOTES_QUERY = "风险提示"`（与 `_SINGLE_INVESTOR_QUERY` 并列）。
- `extract_snapshot_data` 新增 `risk_notes_text = _extract_text_field(tool_service, document_id, _RISK_NOTES_QUERY, "风险提示")`。
- 构造 `SnapshotReportData` 时改为 `risk_notes=risk_notes_text`；`single_investor_20pct=single_investor` 保持不变。
- 测试：`test_snapshot_report_assembly.py` 新增 duck-typed `_FakeStore`（实现 `search` / `list_tables` / `read_table`，供 `FundDocumentToolService({document_id: store})` 包装），「风险提示」与「单一投资者」search 返回不同 excerpt；断言 `risk_notes != single_investor_20pct` 且各自命中对应文本；缺失时断言降级文案「（风险提示未披露）」。

### F2（高，snapshot_extraction.py:549-553）

- 4 个正则修正：`s*` → `\s*`、`[^d]` → `[^\d]`、`(d[d,，.]*` → `(\d[\d,，.]*`、`(?:.d+)?` → `(?:\.\d+)?`；其余结构不变。
- 测试：纯文本回退路径——fake tool service search 命中**无 table_ref** 的 excerpt（表格路径不触发），断言期初/申购/赎回/期末 4 字段提取正确；既有 table 路径测试保留。
- 效果：residual risk 1（文本回退无测试）消除。

### F3（中，snapshot_generator.py）

- `_period_label(template_id, report_year, quarter=None, period=None)`：semiannual 分支按 `{"H1": "上半年", "H2": "下半年"}.get(period, "上半年")` 映射；quarterly 分支不变。
- `_snapshot_common_header`：line 47 调用改为透传 `period`。
- `generate_snapshot_template_chapter`：从 kwargs 读取 `period`，两处 `_period_label` 调用透传。
- 测试：`_period_label(SEMIANNUAL, 2025, period="H1") == "2025 年上半年"`、`period="H2" == "2025 年下半年"`、`period=None` 默认「上半年」；既有 `test_period_label_no_qnone_when_quarter_missing` 保持通过（签名向后兼容）。

### F4（低，audit_pipeline.py:2471）

- `for cid in range(1, 7)` → `for cid in self._template.front_chapter_ids`。
- 行为等价（三模板 front ids ⊂ range(1,7)）；不加重型集成测试，由既有 `test_audit_pipeline.py` 全量回归 + diff review 核验。若 review 要求测试，再抽纯函数 `_build_audit_summary_context` 单测（本计划不预置，控制范围）。

## 测试计划

- 更新/新增：
  - `tests/fund/service/test_snapshot_report_assembly.py`：F1 fake-store 集成测试、F2 文本回退测试、F3 period 映射测试。
- 验证命令：
  - `uv run pytest tests/fund/service/test_snapshot_template.py tests/fund/service/test_snapshot_extraction.py tests/fund/service/test_snapshot_report_assembly.py -q --tb=short`
  - `uv run pytest tests/fund/service/test_audit_pipeline.py -q --tb=short`（F4 回归）
  - AGENTS.md 最小验证：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short`
  - `git diff --check`

## 非目标（明确）

- 不修 residual risk 3/4（模板模式端到端 Markdown 未测、LLM 模式审计管道快照集成未测）——超出 F1-F4 范围，另立 slice。
- 不改 CLI `--period` choices（仍仅 H1；H2 只做标签映射预留，不加 CLI 入口）。
- 不改 public tool / profile registry / 10F/10G/11A 契约 / failure taxonomy。
- 不 commit / 不 push。

## allowed write set

- `fund_agent/service/snapshot_extraction.py`
- `fund_agent/service/snapshot_generator.py`
- `fund_agent/service/audit_pipeline.py`
- `tests/fund/service/test_snapshot_report_assembly.py`

（计划与 plan-review artifact 由 controller / reviewer 产出，不在 DS write set。）
