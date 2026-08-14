# 阶段判定「建仓期」真源修正 slice（2026-08-13 规划）

## 依据（用户确认的问题与方向）

- 用户对 005680（财通资管价值成长混合，2025 年报）的判定结果不认同：报告输出「🟡 建仓期」，判定依据为「基金经理任职于2025年，管理本基金不足2年」。
- 事实链（已在本仓库代码与年报 Docling JSON 中验证）：
  - 005680 基金合同 **2019-03-25 生效**（2021 年报文本「本基金合同于2019年3月25日生效」；2022-2025 年报 §2 基金简介表 `基金合同生效日 | 2019 年 03 月 25 日`）。
  - 005680 现任基金经理李响 **2025-07-15** 任职（任职日期表）。
  - 当前代码 `fund_agent/service/chapter_generator.py:596-606` 的建仓期判定只读 `fund_manager.tenure_start` 的年份与 `report_year`，**从不读基金成立日期**；`report_year(2025) - start_year(2025) = 0 < 2` → 误判建仓期。
  - 建仓期在语义上属于**基金产品生命周期**（合同生效后建仓），不属于基金经理任期；经理变更风险已有独立信号：`signal_scoring.py:381-391` `score_manager_change`（指标 5，0/20，「已变更/无数据」），Ch7 信号评分保留该口径。
- 用户已同意修正方向（三条）：
  1. 新增「基金合同生效日」结构化字段，作为建仓期判定真源；成立不足 2 年才判建仓期。
  2. 经理变更不再占用 5 阶段枚举（保留在 Ch5 关键变化 / Ch7 信号评分或标注）。
  3. 成立日期缺失时 fail-closed：不做建仓期判定（回稳定期并说明），不用经理任期代理。

## 目标

1. 新增「基金合同生效日」的确定性抽取（Service 层，带 Citation），作为建仓期判定唯一真源。
2. 建仓期判定切换为产品生命周期口径：`report_year - 合同生效年份 < 2` 才判建仓期（被动基金仍跳过）。
3. 移除经理维度对 5 阶段枚举的全部占用：`tenure_start` 为空判「转型期」的分支删除；建仓期不再引用 `tenure_start`。
4. 成立日期缺失时 fail-closed：不判建仓期，判定依据明确说明，不使用经理任期代理。
5. 验收含 Host / Agent loop 或 CLI 端到端 smoke（AGENTS.md 硬约束）：005680 真实数据经 CLI `generate` 模板模式，Ch5 输出稳定期且不含建仓期。

## 非目标

- 不改 5 阶段枚举与优先级顺序（转型期 > 建仓期 > 膨胀期 > 萎缩期 > 稳定期）。
- 不改 Ch7 信号评分 `score_manager_change`（经理变更风险继续按任职年份单独计分）。
- 不改 040046 转型期判定（资产配置结构转型检测，`chapter_generator.py:565-589` 保留）。
- 不新增 CLI 子命令 / 参数；不新增依赖；不新增 DTO（合同生效日是一个标量字符串，显式参数即可，避免过度设计）。
- 不更新 AGENTS.md（本 slice 无执行规则变更）。
- **`_generate_chapters_with_llm`（`extraction.py:3604`）为 dead code（全仓库无调用点，已 grep 核实），本 slice 不改**；若将来复活，需同步 `contract_effective_date` 透传（LLM 失败回退 `_generate_template_chapter` 的调用点 `extraction.py:3680-3687` 一并同步）。

## 现状（grep / 读码验证，2026-08-13）

- `generate_data_table`（`chapter_generator.py:231`）签名：`(chapter_id, fund_code, fund_name, report_year, performance, holdings, allocation, fees, fund_manager=None, scale_info=None, evidence=None, stress_test=None, signal_judgment=None, fund_type="")`。
- Ch5 数据表「阶段判定规则」块在 `if chapter_id == 5:`（`chapter_generator.py:491`）内，顺序：
  1. 规模膨胀/萎缩期（531-562，权益投资金额代理指标）；
  2. **经理信息缺失 → 转型期（562-564，「基金经理信息缺失，可能涉及变更」）【本 slice 删除】**；
  3. 资产配置结构转型 → 转型期（565-589）【保留】；
  4. **建仓期（596-606，经理任期年份）【本 slice 改真源】**。
- 阶段标签与优先级行：`chapter_generator.py:610-619`（不变）。
- 调用点（全部需透传新参数，默认 `""` 向后兼容）：
  - `chapter_generator.py:981`（`LlmChapterGenerator.generate_chapter` 内）；
  - `extraction.py:3772`（`_generate_template_chapter` Ch1-6）；
  - `audit_pipeline.py:1924`（全局允许数字预生成循环）、`audit_pipeline.py:2203`（`_generate_and_audit_chapter_inner` 单章数据表）。
- 抽取参考：`_extract_fund_manager_with_citation`（`extraction.py:2826-2989`）为 Service 层现有模式（latest doc → store → `FundDocumentToolService`）。
- 真实数据验证（`search_document` + `read_table`，2025 年报）：
  - 005680：query「基金简介」首命中 `section-0026`（§ 2 基金简介），`table-0002` 行 `基金合同生效日 | 2019 年 03 月 25 日`。
  - 004393：`section-0026` + `table-0002` 行 `基金合同生效日 | 2022年8月8日`（转型后合同）。
  - 163415：`section-0021` + `table-0002` 行 `基金合同生效日 | 2012年12月18日`。
  - 陷阱：163415 §4.1.2 表含「本期 2025年4月8日（基金合同生效日）至2025年12月31日」（基金经理首任任职口径），**禁止从该上下文取日期**；抽取必须锚定 §2 基金简介表行且日期出现在「基金合同生效日」之后。
- 基线（本 slice 修复前，模板模式）：005680 Ch5 输出「| 判定结果 | 🟡 建仓期 |」「| 判定依据 | 基金经理任职于2025年，管理本基金不足2年 |」（已实测）。

## 决策

1. **抽取方法**：`FundReadingService._extract_contract_effective_date_with_citation(fund_code, annual_docs, work_dir) -> tuple[str, Citation | None]`（`extraction.py` 新增）。返回归一化日期 `YYYY-MM-DD`；未找到返回 `("", None)`（fail-closed）。
2. **抽取链路（按序）**：
   - 主路径：`search_document(doc_id, "基金简介")` → 取首个非 `ToolFailure` 且标题含「基金简介」的命中 → `list_tables` 中 `section_ref` 匹配该节的表 → `read_table(max_rows=40)` → 行内文本含「基金合同生效日」→ 对行文本（去空白）正则 `(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日` → 归一化。Citation `locator_kind=TABLE` + `table_ref`/`section_ref`。
   - 回退 1：`search_document(doc_id, "基金合同生效日")` → 逐命中节执行同样的表行扫描。
   - 回退 2：`read_section` 取 §2 基金简介节文本 → 正则 `基金合同生效日\s*(?:为|：|:)?\s*[（(]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日` 或 `基金合同于\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。]{0,8}生效`（日期必须紧跟在「基金合同生效日/合同于」之后，避免 4.1.2 任职口径误取）。Citation `locator_kind=SECTION`。
   - 都不命中 → `("", None)`。
3. **数据表参数**：`generate_data_table(..., contract_effective_date: str = "")`（显式公共参数，追加在 `fund_type` 之后，全部调用点以关键字传入；不塞 `extra_payload`）。
4. **Ch5 阶段判定重写**（替换 562-564 与 596-606）：
   - 删除经理信息缺失 → 转型期分支。
   - 建仓期分支改为（在资产配置结构转型检测之后）：
     ```
     if not is_passive and contract_effective_date:
         year_match = _re.search(r'(\d{4})', contract_effective_date)
         if year_match:
             contract_year = int(year_match.group(1))
             if report_year - contract_year < 2 and stage != "转型期":
                 stage = "建仓期"
                 stage_reason = f"基金合同 {contract_year} 年生效，成立不足2年"
             elif stage == "稳定期":
                 stage_reason = f"基金合同 {contract_year} 年生效，成立已满2年，未触发建仓期"
     elif not is_passive and not contract_effective_date and stage == "稳定期":
         stage_reason = "未提取到基金合同生效日，建仓期判定跳过（不采用基金经理任职年限代理）"
     ```
   - 建仓期不覆盖转型期（对齐文档优先级「转型期 > 建仓期」）；膨胀/萎缩期已有更早检测，建仓期优先级高于膨胀/萎缩（当前代码即此顺序，不变）。
   - 阶段判定表新增一行 `| 基金合同生效日 | {contract_effective_date 或 '未提取到'} |`（仅在 Ch5 阶段判定规则表内）。
5. **证据可溯源**（AGENTS.md「所有工具输出必须可溯源到年报 locator」）：`ChapterEvidence` 新增 `contract_citation: Citation | None = None`；`generate_evidence_section`（`chapter_generator.py:846`）在 Ch5 的「证据与出处」追加 `**基金合同生效信息来源**：...`。
6. **透传**：`contract_effective_date: str = ""` 追加到：
   - `LlmChapterGenerator.generate_chapter`（`chapter_generator.py:960`）；
   - `FundReadingService._generate_chapters` / `_generate_template_chapter`（`extraction.py`，模板路径）；
   - `FundReadingService.generate_report`（`extraction.py:2388`，抽取后传入两条生成路径）；
   - `ReportGenerationCoordinator.generate_report` / `_run_chapter_worker` / `_generate_and_audit_chapter` / `_generate_and_audit_chapter_inner`（`audit_pipeline.py:1884/2043/2111/2166`，LLM 路径入口）。
   - 注：仓库中**不存在** `_generate_llm_chapters` 方法；LLM 路径经 `coordinator.generate_report()`（`extraction.py:2516`）透传，不经过 `_generate_chapters_with_llm`。
7. **Prompt 口径同步**：`fund_agent/service/prompts/system_base.md` Ch5 正例「基金经理任职超过2年」改为「基金合同 XXXX 年生效，成立已满 2 年」（与数据表判定依据口径一致）；`ch5.md` / `audit_pipeline.py` 的「5选1 优先级」表述不变。

## 模块改动规格

### 模块 1：`fund_agent/service/extraction.py`（修改）

- 新增 `_extract_contract_effective_date_with_citation(self, fund_code, annual_docs, work_dir) -> tuple[str, Citation | None]`（按决策 2，中文 docstring）。
- `generate_report` 在 `_extract_fund_manager_with_citation` 之后调用它，得到 `(contract_effective_date, contract_citation)`：
  - `evidence = ChapterEvidence(..., contract_citation=contract_citation)`；
  - LLM 路径：`ReportGenerationCoordinator.generate_report(..., contract_effective_date=contract_effective_date)`；
  - 模板路径：`self._generate_chapters(..., contract_effective_date=contract_effective_date)`。
- `_generate_chapters` / `_generate_template_chapter` 签名加 `contract_effective_date: str = ""` 并透传到 `generate_data_table` / `LlmChapterGenerator.generate_chapter`（`_generate_chapters_with_llm` 为 dead code，不改，见非目标）。

### 模块 2：`fund_agent/service/chapter_generator.py`（修改）

- `generate_data_table` 签名追加 `contract_effective_date: str = ""`。
- Ch5 阶段判定块按决策 4 重写；判定表新增基金合同生效日行。
- `LlmChapterGenerator.generate_chapter` 签名追加 `contract_effective_date: str = ""` 并透传。
- `generate_evidence_section` 在 `chapter_id in (0, 5, 7)` 的规模来源后追加合同生效日来源（`evidence.contract_citation` 非空时）。

### 模块 3：`fund_agent/service/audit_pipeline.py`（修改）

- `ReportGenerationCoordinator.generate_report` / `_run_chapter_worker` / `_generate_and_audit_chapter` / `_generate_and_audit_chapter_inner` 签名追加 `contract_effective_date: str = ""` 并透传到 `generate_data_table`；全局数字预生成循环同样传入。

### 模块 4：`fund_agent/service/models.py`（修改）

- `ChapterEvidence` 新增 `contract_citation: Citation | None = None`（含 docstring）。

### 模块 5：`fund_agent/service/prompts/system_base.md`（修改）

- Ch5 正例的稳定期判定依据改为基金合同生效年份口径（决策 7）。

## 测试

### 新增 `tests/fund/service/test_stage_determination.py`（确定性单元，构造 Ch5 数据表）

1. `test_old_fund_new_manager_not_building_phase`：`contract_effective_date="2019-03-25"`、`fund_manager.tenure_start="2025-07-15"`、`report_year=2025` → 输出含「🟢 稳定期」与「基金合同 2019 年生效，成立已满2年」，不含「建仓期」。
2. `test_new_fund_is_building_phase`：`contract_effective_date="2025-01-01"`、`report_year=2025` → 含「🟡 建仓期」与「成立不足2年」。
3. `test_missing_contract_date_fail_closed`：`contract_effective_date=""`、经理任期 2025 → 不含「建仓期」，含「建仓期判定跳过」。
4. `test_manager_tenure_missing_does_not_trigger_transformation`：`fund_manager.tenure_start=""`、无资产配置转型数据 → 不含「转型期」。
5. `test_passive_fund_skips_building_phase`：`fund_type="index_etf"`、合同 2025 → 不含「建仓期」。
6. `test_building_phase_does_not_override_transformation`：构造权益→基金资产结构转型数据 + 合同 2025 → 含「转型期」且不含「建仓期」。

### 新增抽取真实数据测试（`tests/fund/test_e2e_regression.py`）

7. `test_extract_contract_effective_date_005680`：`.fund_checklist_005680` 存在时（否则 skip），`_extract_contract_effective_date_with_citation` 返回 `"2019-03-25"` 且 Citation 非空。

### 新增 CLI 端到端 smoke（`tests/fund/cli/test_cli.py`，满足「Host / Agent loop 或 CLI e2e」硬约束）

8. `test_generate_cli_005680_stage_not_building_phase`：复制 `.fund_checklist_005680` 的 `completed_reports.json` + `docling_json/` 到 `tmp_path` workdir（源缺失则 skip）→ `_run(["generate", "--fund-code", "005680", "--fund-name", "财通资管价值成长混合", "--year", "2025", "--format", "markdown", "--work-dir", str(work_dir)])`（模板模式，无 `--llm`、无网络）→ exit 0；`reports/005680-2025-analysis.md` 存在；内容含「🟢 稳定期」与「基金合同 2019 年生效」，不含「建仓期」。

### 既有回归

- `tests/fund/test_e2e_regression.py` 现有 040046 转型期测试（`test_e2e_040046_stage_is_transformation`）必须保持通过（资产配置结构转型检测未改动）。

## 验证命令

```bash
uv run pytest tests/fund/service/test_stage_determination.py -v --tb=short
uv run pytest tests/fund/cli/test_cli.py -k "005680_stage" -v --tb=short
uv run pytest tests/fund/test_e2e_regression.py -v --tb=short
uv run pytest tests/fund/service/test_llm_chapter_generation.py tests/fund/service/test_report_concurrency.py -v --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short
```

## 真源文档同步（review 通过后由 controller 执行）

- **MiMo plan review（2026-08-13，AgentMiMo）**：`Verdict: NEEDS_FIX` 2 项，均已按 review 原文修正进本 plan：
  1. Fix 1 — 决策 6 原引用不存在的 `_generate_llm_chapters`，已改为 `_generate_chapters` / `_generate_template_chapter`（模板路径）+ 注明 LLM 路径经 `coordinator.generate_report()` 透传；
  2. Fix 2 — `_generate_chapters_with_llm`（`extraction.py:3604`）为 dead code，已列入非目标明确不改。
  - Fix 3（tests/README.md 未列入 write set）经 reviewer 自查撤回，确认 write set 完整。
  - 其余验证项全部 ✓（前提正确性、163415 反例、scope、4 调用点透传、audit_pipeline 四层、fail-closed、被动基金跳过、优先级保留、CLI e2e smoke、write set）。

- `docs/design.md`：新增 §6.24「阶段判定「建仓期」真源修正（2026-08-13 裁决）」：现状事实、决策（合同生效日真源 / 经理变更退出阶段枚举 / fail-closed）、依据行号与真实数据证据。
- `docs/implementation-control.md`：文首更新 + 文末 slice 节追加本 slice 记录（MiMo plan review 结论、DS 实施、controller 复跑、MiMo diff review 结论占位）。
- `tests/README.md`：新增测试文件与验证命令 1 句。
- `fund_agent/README.md`：本 slice 不改分层边界，无需更新（如 reviewer 认为必要可加 1 句）。
- `AGENTS.md`：不更新。

## allowed write set（DS 实施阶段）

- 修改：`fund_agent/service/extraction.py`、`fund_agent/service/chapter_generator.py`、`fund_agent/service/audit_pipeline.py`、`fund_agent/service/models.py`、`fund_agent/service/prompts/system_base.md`、`tests/fund/cli/test_cli.py`、`tests/fund/test_e2e_regression.py`、`tests/README.md`。
- 新增：`tests/fund/service/test_stage_determination.py`。
- 禁止：`AGENTS.md` / `docs/design.md` / `docs/implementation-control.md` / `.sisyphus/`（真源同步由 controller 在 review 通过后执行）/ `fund_agent/host/` / `fund_agent/agent/` / `fund_agent/cli/` / `fund_agent/fund/` / `FailureCode` / `DocumentToolError` / 公共工具契约 / 新 CLI 子命令与参数 / 新依赖 / commit / push。

## stop conditions

- 验证命令全部通过（含 005680 CLI smoke：Ch5 稳定期、无建仓期；040046 转型期回归通过）。
- 输出交接报告：changed files / diff 摘要 / 实际测试命令与输出。
- 不 commit、不 push、不进入后续 gate。
