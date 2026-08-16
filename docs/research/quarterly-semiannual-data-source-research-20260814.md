# 半年报/季报作为基金分析报告数据源研究（005680 实证）

更新时间：2026-08-14
状态：研究完成，待裁决（见 §5）
范围：只做下载实证 + 数据源集成路径研究 + 分析模板优化建议；未改动任何生产代码。

## 0. TL;DR

- 005680 2026 年一季报已下载；**2026 年半年报尚未披露**（截至 2026-08-14，EID 仅有 2020–2025 中期报告；法定披露截止 2026-08-31），因此补下 2026 二季报（最新一期）与 2025 中期报告（半年报格式证据）。
- 季报/半年报与年报是**互补而非替代**：5 年年报系列（10F/10G/multi-year）必须保持 annual-only；季报/半年报应以「最新披露快照」（latest disclosure snapshot）身份进入报告，不进年度序列。
- 现成风险：catalog 过滤（`_find_annual_report_documents` 等）不带 `report_type` 维度，若把 2026 季报/半年报导入同一 work_dir，会被误判为 2026 年报并污染 multi-year 聚合。**任何落地必须先修 catalog 过滤**。
- 模板优化方向：Ch5 新增「最新披露快照」数据块、Ch4 份额变动季度频、Ch3 言行一致性用季报/半年报刷新、附录 A 锚点格式扩展报告类型与数据日期。
- 证据：三份 PDF 下载路径见 §1；Docling 转换文本在 `/tmp/fc_q_research/`（005680_2026_Q1/Q2_quarterly_report.md、005680_2025_semiannual.md）。

## 1. 下载事实

EID（eid.csrc.gov.cn/fund）报告类型码（2026-08-14 实测）：

| reportType | reportCode | reportDesp | 说明 |
|---|---|---|---|
| FB010 | FB010010 | 年度报告 | 现有 `download` 仅支持此 spec |
| FB020 | FB020010 | 中期报告 | 半年报 |
| FB030 | FB030010 / FB030020 / FB030030 / FB030040 | 第1/2/3/4季度报告 | 季报 |

005680 下载结果：

| 文件 | uploadInfoId | 大小 | 说明 |
|---|---|---|---|
| `基金季报/005680_财通资管价值成长混合_2026_Q1_quarterly_report.pdf` | 1473543 | 704,397 B | 用户指定；FB030010，2026 年第 1 季度报告 |
| `基金季报/005680_财通资管价值成长混合_2026_Q2_quarterly_report.pdf` | 1534983 | 492,726 B | 2026 年最新一期披露；FB030020 |
| `基金半年报/005680_财通资管价值成长混合_2025_semiannual_report.pdf` | 1341853 | 1,414,571 B | 半年报格式证据；FB020010，2025 年中期报告 |

- 2026 半年报：EID `FB020` reportYear=2026 返回 0 条；全年度查询仅有 2020–2025。法定披露期至 2026-08-31，预计 8 月底前后可用，届时补下即可。
- 2026 Q1/Q2 季报 EID `reportYear` 均为 2026，无需额外年份参数。

## 2. 三种披露的数据能力对比（005680 实证）

依据：2025 年报 Docling JSON（`.fund_checklist_005680/docling_json/005680-2025-*`）、2025 中期报告与 2026 Q1/Q2 季报 Docling 文本（`/tmp/fc_q_research/`）。

| 数据项 | 年报 | 半年报 | 季报 |
|---|---|---|---|
| 完整财务报表 | ✅ §7 已审计 | ✅ §6 未经审计 | ❌ |
| 过去五年基金每年净值增长率（日历年度逐年） | ✅ §3.2.3 | ❌ | ❌ |
| 净值增长率表（3.2.1，含 ①－③ 超额列） | ✅（过去一个月…自成立） | ✅（过去一个月…自成立，无五年） | ✅（窗口随期变化） |
| 全部股票持仓明细 | ✅ §8 | ✅ §7.3 | ❌（仅前十） |
| 前十股票持仓 | ✅ | ✅ | ✅ §5.3.1 |
| 行业/资产配置 | ✅ | ✅ | ✅ §5.1/§5.2 |
| 换手率（累计买入/卖出） | ✅ §8.4 | ✅ §7.4 | ❌ |
| 持有人结构（户数/机构个人） | ✅ §9 | ✅ §8 | ❌ |
| 份额变动（期初/申购/赎回/期末） | ✅ §10 | ✅ §9 | ✅ §6 |
| 运作分析（当前市场+操作） | ✅ §4.4.1 | ✅ §4.4.1 | ✅ §4.4 |
| 市场展望 | ✅ §4.5 | ✅ §4.5 | ❌ |
| 单一投资者 ≥20% | ✅ §12.1 | ✅ §11.1 | ✅ §8.1 |
| 持有人数/净值预警说明 | ✅ §4.9 | ✅ §4.8 | ✅ §4.6 |
| 基金经理持有/固有资金 | ✅ §9/§11 | ✅ | ✅ §7 |

关键实证细节：

- 季报 3.2.1 窗口行**不稳定**：2026 Q1 A 类为 三个月/六个月/一年/三年/五年/自成立；2026 Q2 A 类为 三个月/六个月/一年/三年/五年/**过去七年**/自成立。C 类（2021-12-23 增设）两期均无 五年/七年 行。→ 抽取必须按「阶段」行标签精确匹配，禁止假设固定窗口集合；「表存在但无某窗口行」复用 F2 可解释后缀语义。
- 滚动窗口 ≠ 日历年度：Q1 A 类「过去五年」1.00%，Q2 A 类「过去五年」-6.69%，是滚动 5 年值，与年报 §3.2.3 逐年值不可混用。→ 5 年系列只能来自年报。
- 季报无 3.2.3、无完整财报、无全部持仓、无持有人结构、无换手率 → 报告不能只靠季报。

## 3. 进入管线的技术路径与边界

### 3.1 现状（代码事实）

- `ReportType` 仅 `annual_report`（`fund_agent/fund/document_tools/constants.py`）；design.md 明确 `semiannual_report` / `quarterly_report` 保留为未来扩展。
- `document_id = fund_code-year-report_type-fingerprint_prefix`（docs/design.md）。同 year 下 Q1/Q2 的 fingerprint 天然不同 → **document_id 格式无需改变即可保证唯一**；但「year=2026 + quarterly_report」无法区分季度，需要在 catalog/metadata 增加 `period` 维度。
- `download` CLI 仅支持年报 spec（`eid_downloader.py` `ANNUAL_REPORT_SPEC` = FB010/FB010010/年度报告；main.py `--fund-code --year --output-dir --force`）。
- `import` CLI 硬编码 `report_type=ReportType.ANNUAL_REPORT`（main.py:683）。
- multi-year 聚合身份校验硬编码 annual（`extraction.py _validate_multi_year_report_identity`）→ 年度系列已具备 annual-only 防线。
- **风险**：catalog 过滤 `_find_annual_report_documents`（main.py:278 循环）与 `_run_multi_year_command`（main.py:735 循环）只按 `fund_code` + `year` 匹配，不校验 `report_type`。一旦导入 2026 季报/半年报，会被当成 2026 年报进入 multi-year。必须先修。
- 10G title family「基金份额净值增长率及其与同期业绩比较基准收益率的比较」与表锚点头签名（阶段/份额净值增长率/业绩比较基准收益率）在季报/半年报 §3.2.1 **同样命中** → 受控表锚点机制可复用。

### 3.2 建议方案（方案 A，最小侵入）

1. **`ReportType` 扩展**：新增 `SEMIANNUAL_REPORT` / `QUARTERLY_REPORT`；`document_id` 格式保持不变。
2. **`period` 元数据**：catalog 与报告 metadata 增加 `period`（`h1` / `q1` / `q2` / `q3` / `q4`），来源为显式参数或 reportName 解析；不参与 document_id、不参与 fingerprint。
3. **`download` 扩展**：spec 表改为 `{annual: FB010/FB010010, semiannual: FB020/FB020010, quarterly: FB030/FB0300X}`；CLI 增加 `--report-type`（默认 `annual`，行为不变）+ `--quarter 1..4`（仅 quarterly）。
4. **`import` 扩展**：`PdfImportRequest` / CLI 增加 `report_type` + `period` 显式参数（不做文件名魔法推断，避免 share_class 从文件名猜测同类禁令）。
5. **catalog 过滤修复（前置项）**：所有按 `fund_code` + `year` 过滤的 catalog 查询增加 `report_type=annual_report` 维度；否则季报/半年报导入即污染。
6. **「最新披露快照」数据块**：新增服务层概念 — 按 fund_code 取最新 `period` 的季报/半年报（半年报优先于 Q2 季报，同一报告期只取一份），供 Ch0/Ch3/Ch4/Ch5/Ch6 使用；不进 multi-year 系列。
7. **抽取复用边界**：`performance_returns` / 10G 标题族对快照 doc 开放时，必须（a）标注报告期口径（三个月/六个月/一年为滚动窗口）；（b）行标签精确匹配（含「过去七年」这类新增行）；（c）C 类缺行走 F2 可解释 not_found。

### 3.3 红线

- 季报/半年报不得进入 5 年年报系列（滚动窗口 ≠ 日历年度；且季报无 §3.2.3）。
- 季报无完整财报/全部持仓/持有人结构 → 模板不得把这些章节降级为仅季报来源。
- 未经 catalog 过滤修复前，禁止把季报/半年报导入既有 work_dir。
- 失败分类沿用现有 `not_found` / `schema_drift` / `identity_mismatch` 等；不新增模糊异常。

## 4. 分析模板优化建议

现状：`docs/fund-analysis-template-draft.md` 为 8 章 typed contract（ch0–ch7 + 附录 A/B）；证据锚点全部为「年报§N」，免责声明已提及半年报/季度报告但契约未定义其进入方式。

### 4.1 数据源分层（模板契约新增口径）

- 年报 = 年度主链：5 年业绩系列、已审计财报、全部持仓、换手率、持有人结构、利润分配。
- 半年报 = 半年刷新：未审计 6 个月财报、全部持仓、持有人结构、市场展望。
- 季报 = 最新快照：期末规模、前十持仓、份额变动、运作分析、单一投资者 ≥20%、预警说明。

### 4.2 分章优化

- **Ch5 当前阶段与关键变化**：新增「最新披露快照」数据块（报告期、期末规模、前十持仓较上期变化、本期申购/赎回净额、最新窗口超额收益、运作分析要点、单一投资者 ≥20% 提示）；「关键变化清单」的时间基准改为最近一期披露而非上年年报。
- **Ch4 投资者获得感**：份额变动趋势改为季度频（每期期初/申购/赎回/期末），追涨/抄底判断用季度资金流；行为损益仍以年度数据为主。
- **Ch3 言行一致性**：新增季报/半年报交叉验证 — 季报 §4.4（说）vs §5.3.1 前十持仓（做）；半年报 §4.4.1（说）vs §7.3 全部持仓（做）。比年报更接近决策时点。
- **Ch2 R=A+B-C**：5 年系列不变；新增「最近一期超额」行（季报/半年报 3.2.1 ①－③，必须标注报告期口径，如「2026 二季度 · 过去一年」）。
- **Ch6 核心风险与否决项**：单一投资者 ≥20% 与预警说明改用最近一期季报/半年报（更及时）。
- **附录 A 数据来源锚点**：锚点格式扩展为 `年报[年份]§N` / `半年报[年份]§N` / `季报[年份]Q[n]§N`；新增「报告期/数据日期」列；模板 manifest 的 must_answer/must_not_cover 增加报告期口径约束（不得把季报三个月窗口外推为年度趋势；业绩对比须同报告期口径）。

### 4.3 模板契约变更影响

- `TEMPLATE_CONTRACT_MANIFEST_JSON` 的 schema_version / public_chapter_ids 不变，但需扩展数据源枚举与证据锚点格式 → 属于模板契约版本升级，需单独裁决后再改模板文件。

## 5. 裁决项与下一步

待裁决：

1. 是否批准方案 A（ReportType + period + download/import 扩展 + catalog 过滤修复），还是先只做最小防御 slice（仅修 catalog report_type 过滤）。
2. 模板是否新增「最新披露快照」块并升级证据锚点格式（影响 manifest schema_version）。
3. 2026 半年报披露后（约 2026-08-31 前）补下并复验 §3.2.1 行集与 §7 全部持仓。

最小可执行验证（落地首个 slice 时）：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

研究产出：PDF 3 份（`基金季报/`、`基金半年报/`，已 gitignore）；Docling 文本证据在 `/tmp/fc_q_research/`。
