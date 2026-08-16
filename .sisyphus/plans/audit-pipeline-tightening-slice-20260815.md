# Slice A：审计管道设计收紧（critical 阻断 + 装配审计）（2026-08-15 设计）

## 任务界定（口径）

- 来源：F1-F4 收口报告「遗留建议」明确留出两项裁决：① critical violation 不阻断；② 无装配审计。controller 按价值排序给出候选 A/B/C，用户裁决「先做A」。
- 性质：**设计变更（需用户拍板口径后实施）**，不是代码 bug。本计划给出推荐口径，标记决策点 D1-D4。
- 流程：用户拍板 → MiMo plan review（PASS）→ DS（agents:0.1）实施 → MiMo diff review（ACCEPTED/NEEDS_FIX）。CIC-lite，不 commit 不 push。

## 实证（2026-08-15，代码核验）

### A1（critical violation 不阻断）

1. `audit_pipeline.py:2539-2542`：`_generate_and_audit_chapter` 通过判据 `if final_score >= score_pass: return content`（`score_pass` = 数据充足 80.0 / 数据不足或 LLM_ERROR 75.0），**不检查 critical**。
2. `audit_pipeline.py:1769-1812` `select_repair_strategy`：`score >= SCORE_PASS(80) → "skip"` 同样**不检查 critical**；仅 [50,80) 区间内有 critical 才走 regenerate。
3. `audit_pipeline.py:2537` `AuditDecision.recommendation`：`"pass" if final_score >= score_pass`，同缺口。
4. 历史 QNone 证据：LLM 审计命中 critical（Ch1 P1「报告期使用占位符'QNone'」），Ch1 加权 87.4 ≥ 80 → pass 放行。
5. 修复边界：`_LLM_REPAIR_SYSTEM_PROMPT`（audit_pipeline.py:1457-1488）PATCH「不修改数据表格」→ 程序化表头缺陷（如 QNone）修复环结构上无法触碰；regenerate 有界（MAX_REGENERATE_ATTEMPTS=3）→ 耗尽后模板降级 `passed_with_degradation`（2539 之后逻辑已存在），**critical 阻断不会死循环**。
6. 附注：`SCORE_PASS_DEGRADED=75.0` 注释写「数据不足时 ≥70分通过」与代码 75 不符，顺手修正注释。

### A2（无装配审计）

1. 快照装配 `extraction.py:2821-2834`：`chapters = tuple(ReportChapter(...) for cid in sorted(template.chapter_ids))`，title 取 `template.chapter_titles.get(cid, f"章节 {cid}")`——无「集合==chapter_ids / 顺序==模板 / 标题==manifest」任何校验。
2. 年报 LLM 路径 `extraction.py:2614-2654`：`chapter_specs` 0..7 **硬编码**标题与 data_sources，无模板校验。
3. 年报模板路径 `extraction.py:3690-3712`（`_generate_chapters`）：同款硬编码 chapter_specs。
4. 审计只见单章（ProgrammaticAuditor/LlmAuditor 在 worker 内），coordinator 只聚合 passed/failed 计数（extraction.py:2611-2612）——「2,3,4,5,1 错位」在审计视野外（该错位源头已由 F1-F4 修复为 `sorted(template.chapter_ids)`，本项为回归防线）。
5. 三模板 chapter_titles 与三处装配标题**逐字一致**（report_template.py:219-257 vs extraction.py 三处 specs），校验可安全接入不会误报。

## 设计

### A1：critical 阻断通过（推荐口径）

- 提取纯函数 `_passes_audit(final_score, score_pass, violations) -> bool`（audit_pipeline.py），语义：`final_score >= score_pass and 无 critical`。
- `_generate_and_audit_chapter`：
  - 通过分支改调 `_passes_audit`；critical 存在 → 不通过，**跳过 PATCH 直接走 REGENERATE**（与 `select_repair_strategy` 语义对齐：critical 只能 regenerate，不能 patch）。
  - `AuditDecision.recommendation` 同步：`has_critical → "regenerate"`（不再因高分标 pass）。
- `select_repair_strategy`：`score >= SCORE_PASS 且有 critical → "regenerate"`（reason 列出 codes），无 critical 仍 "skip"。
- 降级语义不变：数据不足只降分数门槛（75），**不豁免 critical**（P1 空表在 degraded 模式同样不该 pass；「数据完整性声明」标记场景 data_table 非空，P1 不误触）。
- LLM 审计 critical 与程序化 critical 同等阻断（不区分来源）；误报代价 = ≤3 次 regenerate 后模板降级，有界。

### A2：装配审计（推荐口径）

- 新增纯函数 `verify_report_assembly(template, chapters) -> tuple[bool, list[str]]`（audit_pipeline.py）：
  - `{ch.chapter_id} == set(template.chapter_ids)`（缺章/多章 → fail）
  - 顺序 == `sorted(template.chapter_ids)`（展示顺序 → fail）
  - 每章 title == `template.chapter_titles[cid]`（标题与 manifest 一致 → fail）
  - 内容为空 → warning（沿用现状，不 fail）
- 装配点接入（三处，程序化校验，**模板模式同样生效**）：
  - `generate_snapshot_report`（extraction.py:2834 之后）：fail → 返回 `ToolFailure(code=schema_drift, message=校验明细)`，不再产出报告。
  - `generate_report` LLM 路径（extraction.py:2654 之后）：fail → 返回失败（复用既有失败返回路径，code=schema_drift）。
  - `_generate_chapters` 模板路径（extraction.py:3710 之后）：fail → 抛/返回失败（同 code）。
- 不新增 failure code：复用 `schema_drift`（结构/契约与模板不一致语义）。

### 口径裁决（2026-08-15 用户已拍板「确认」，全部按推荐口径）

- **D1**：critical 阻断是否含数据不足（degraded）模式？推荐：**含**（只降门槛，不豁免 critical）。
- **D2**：LLM 审计 critical 是否与程序化 critical 同等阻断？推荐：**同等**（误报代价有界）。
- **D3**：装配违反行为？推荐：**fail-closed**（ToolFailure/schema_drift）；仅内容为空 warning。
- **D4**：装配校验范围？推荐：**三处全接**（snapshot ×2 + annual LLM + annual 模板路径；annual 标题已与 ANNUAL_TEMPLATE 逐字一致，无误报风险）。

## 测试计划

- A1（test_audit_pipeline.py）：
  - `select_repair_strategy`：score=87.4 + critical → regenerate（可证伪旧逻辑）；score=80 无 critical → 仍 skip（既有测试保留）。
  - `_passes_audit` 纯函数：≥门槛无 critical → True；≥门槛有 critical → False；<门槛 → False。
  - 集成：fake LLM 持续返回「高分 + critical」→ 章节走 regenerate → 耗尽 → 模板降级 `passed_with_degradation`（断言最终状态非 "passed"）。
- A2（test_snapshot_report_assembly.py）：
  - `verify_report_assembly` 纯函数：正确装配 pass；乱序 fail；缺章 fail；多章 fail；标题不符 fail；空内容 warning。
  - 集成：注入缺失章节/乱序的 chapter_contents → `generate_snapshot_report` 返回 schema_drift 失败（可证伪：当前代码无校验会照常产出）。
- 回归：既有 30 快照测试 + audit_pipeline 全量（含 select_repair_strategy 既有 7 测试，需核对 critical 高分场景无既有断言依赖旧行为）。

## 验证命令

```bash
uv run pytest tests/fund/service/test_audit_pipeline.py -q --tb=short
uv run pytest tests/fund/service/test_snapshot_report_assembly.py -q --tb=short
uv run pytest tests/fund/service/test_snapshot_template.py tests/fund/service/test_snapshot_extraction.py -q --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

## 文档同步（用户要求：更新真源文档 + AGENTS.md）

1. `docs/design.md` §6.25 追加第 20 项裁决：审计通过判据 = 加权分数达门槛 **且** 无 critical（critical 一律 regenerate，不因高分放行）；报告级装配审计（章节集合/顺序/标题与模板 manifest 一致，违反 fail-closed schema_drift，内容为空仅 warning）。
2. `docs/implementation-control.md` 快照进度节（或新「审计收紧 slice」节）追加本 slice 记录。
3. `AGENTS.md` 审计规则节追加：禁止「高分放行 critical」；报告装配必须经模板 manifest 校验。

## 非目标（明确）

- 不改修复环上限（MAX_PATCH/REGENERATE=3）、不改 repairer prompt「禁止修改数据表格」语义。
- 不动 CLI / prompts / registry / public tool 契约 / failure taxonomy（A2 复用既有 `schema_drift`，不新增 code）。
- 模板模式（无 `--llm`）不接入逐章审计管道（候选 A 范围外；装配校验为程序化检查，模板模式同样生效）。
- 不做候选 B（`to_context_dict()` 完整性）/ 候选 C（`_search_texts` 截断边界）。
- 不 commit / 不 push。

## allowed write set（DS 执行边界，禁止越界）

- `fund_agent/service/audit_pipeline.py`
- `fund_agent/service/extraction.py`
- `tests/fund/service/test_audit_pipeline.py`
- `tests/fund/service/test_snapshot_report_assembly.py`
- `docs/design.md`
- `docs/implementation-control.md`
- `AGENTS.md`

（计划与 plan-review / diff-review artifact 由 controller / reviewer 产出，不在 DS write set。）
