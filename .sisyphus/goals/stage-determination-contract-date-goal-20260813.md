# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/stage-determination-contract-date-slice-20260813.md 实施「阶段判定「建仓期」真源修正」slice（plan 已于 2026-08-13 经 MiMo plan review，NEEDS_FIX 2 项最小修复已按 review 原文修正进 plan：Fix 1 决策 6 引用不存在的 _generate_llm_chapters 已改正为 _generate_chapters/_generate_template_chapter（模板路径）并注明 LLM 路径经 coordinator.generate_report() 透传；Fix 2 _generate_chapters_with_llm（extraction.py:3604）确认为 dead code 已列入非目标明确不改；docs/design.md §6.24 与 docs/implementation-control.md 已由 controller 先行同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review。实施内容：① 新增 fund_agent/service/extraction.py 的 _extract_contract_effective_date_with_citation（Service 层，返回 (归一化日期 "YYYY-MM-DD" 或 "", Citation|None)）：主路径 search_document("基金简介") 锚定标题含「基金简介」的节 → list_tables 中 section_ref 匹配的表 → read_table(max_rows=40) → 行文本含「基金合同生效日」→ 去空白正则 (\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日 → 归一化，Citation locator_kind=TABLE；回退 1 search_document("基金合同生效日") 逐命中节同样表行扫描；回退 2 read_section 节文本正则「基金合同生效日\s*(?:为|：|:)?\s*[（(]?\s*日期」或「基金合同于\s*日期[^。]{0,8}生效」（日期必须紧跟短语，规避 163415 §4.1.2「本期 2025年4月8日（基金合同生效日）至2025年12月31日」经理任职口径误取），Citation locator_kind=SECTION；全部失败返回 ("", None) fail-closed）。② 修改 fund_agent/service/chapter_generator.py：generate_data_table 签名追加 contract_effective_date: str = ""（追加在 fund_type 之后，显式公共参数，不塞 extra_payload）；Ch5 阶段判定块重写——删除「tenure_start 为空 → 转型期」分支（562-564）；建仓期分支改为 if not is_passive and contract_effective_date: year 解析后 report_year - contract_year < 2 and stage != "转型期" → stage="建仓期"、reason="基金合同 {year} 年生效，成立不足2年"，elif stage == "稳定期" → reason="基金合同 {year} 年生效，成立已满2年，未触发建仓期"；elif not is_passive and not contract_effective_date and stage == "稳定期" → reason="未提取到基金合同生效日，建仓期判定跳过（不采用基金经理任职年限代理）"；阶段判定表新增行「| 基金合同生效日 | {date 或 '未提取到'} |」；LlmChapterGenerator.generate_chapter 签名追加同参数并透传；generate_evidence_section 在 Ch5 追加「**基金合同生效信息来源**：format_citation(evidence.contract_citation)」。③ 修改 fund_agent/service/audit_pipeline.py：ReportGenerationCoordinator.generate_report / _run_chapter_worker / _generate_and_audit_chapter / _generate_and_audit_chapter_inner 签名追加 contract_effective_date: str = "" 并透传到 generate_data_table（含全局数字预生成循环 1924）。④ 修改 fund_agent/service/models.py：ChapterEvidence 新增 contract_citation: Citation | None = None（含 docstring）。⑤ 修改 fund_agent/service/prompts/system_base.md：Ch5 正例稳定期判定依据「基金经理任职超过2年」改为「基金合同 XXXX 年生效，成立已满 2 年」。⑥ 测试——新增 tests/fund/service/test_stage_determination.py（确定性单元 6 用例：旧基金+新经理非建仓期/新基金建仓期/缺失 fail-closed/经理 tenure 空不触发转型期/被动基金跳过/建仓期不覆盖转型期）；修改 tests/fund/test_e2e_regression.py 新增 test_extract_contract_effective_date_005680（.fund_checklist_005680 缺失则 skip，断言返回 "2019-03-25" 且 Citation 非空）；修改 tests/fund/cli/test_cli.py 新增 test_generate_cli_005680_stage_not_building_phase（复制 .fund_checklist_005680 的 completed_reports.json + docling_json/ 到 tmp_path workdir，源缺失 skip，_run(["generate","--fund-code","005680","--fund-name","财通资管价值成长混合","--year","2025","--format","markdown","--work-dir",str(work_dir)]) 模板模式无 --llm 无网络，断言 exit 0、reports/005680-2025-analysis.md 含「🟢 稳定期」与「基金合同 2019 年生效」不含「建仓期」）。⑦ 文档：tests/README.md 新增测试文件与验证命令 1 句。allowed write set 严格按 plan 清单（8 修改：fund_agent/service/extraction.py、chapter_generator.py、audit_pipeline.py、models.py、prompts/system_base.md、tests/fund/cli/test_cli.py、tests/fund/test_e2e_regression.py、tests/README.md；1 新增：tests/fund/service/test_stage_determination.py），禁止动 AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/ / fund_agent/host/ / fund_agent/agent/ / fund_agent/cli/ / fund_agent/fund/ / FailureCode / DocumentToolError / 公共工具契约 / 新 CLI 子命令与参数 / 新依赖 / _generate_chapters_with_llm（dead code 不改）/ commit / push。验收：uv run pytest tests/fund/service/test_stage_determination.py -v --tb=short、uv run pytest tests/fund/cli/test_cli.py -k "005680_stage" -v --tb=short、uv run pytest tests/fund/test_e2e_regression.py -v --tb=short、uv run pytest tests/fund/service/test_llm_chapter_generation.py tests/fund/service/test_report_concurrency.py -v --tb=short、最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 全部通过（含 005680 CLI smoke：Ch5 稳定期无建仓期；040046 转型期回归通过），输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/stage-determination-contract-date-goal-20260813.md
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

- goal_id: `stage-determination-contract-date-20260813`
- 目标：实施「阶段判定「建仓期」真源修正」，按已 review 计划完成实现 + 测试。
- 前置条件：`.sisyphus/plans/stage-determination-contract-date-slice-20260813.md` 已 review（MiMo plan review，2026-08-13，NEEDS_FIX 2 项已按 review 原文修正进 plan）；真源文档已由 controller 先行同步（docs/design.md §6.24 / docs/implementation-control.md）。
- 设计来源：`.sisyphus/plans/stage-determination-contract-date-slice-20260813.md`（唯一计划真源）。
- 日期：2026-08-13

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自 plan）

| 项 | 内容 |
|-------|------|
| 新增抽取 | `fund_agent/service/extraction.py`：`_extract_contract_effective_date_with_citation`（§2 基金简介表行锚定 + 两级回退，带 Citation，fail-closed） |
| 修改判定 | `fund_agent/service/chapter_generator.py`：`generate_data_table` / `LlmChapterGenerator.generate_chapter` 追加 `contract_effective_date` 参数；Ch5 建仓期真源切换 + 删除经理维度分支 + fail-closed 说明 + 合同生效日行 + Ch5 证据来源 |
| 透传 | `fund_agent/service/audit_pipeline.py`：`ReportGenerationCoordinator.generate_report` / `_run_chapter_worker` / `_generate_and_audit_chapter` / `_generate_and_audit_chapter_inner` |
| 模型 | `fund_agent/service/models.py`：`ChapterEvidence.contract_citation` |
| Prompt | `fund_agent/service/prompts/system_base.md`：Ch5 正例稳定期依据改为合同生效口径 |
| 测试 | 新增 `tests/fund/service/test_stage_determination.py`（6 用例）；修改 `tests/fund/test_e2e_regression.py`（抽取真实数据 1 用例）、`tests/fund/cli/test_cli.py`（005680 CLI smoke 1 用例） |
| 文档 | `tests/README.md`（1 句） |
| 禁止 | AGENTS.md / design.md / implementation-control.md / .sisyphus/ / host/agent/cli/fund 层 / `_generate_chapters_with_llm`（dead code）/ 公共契约 / 新 CLI 子命令与参数 / 新依赖 / commit / push |
