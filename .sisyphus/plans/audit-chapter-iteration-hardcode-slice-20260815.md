# Slice G：audit_pipeline 章节迭代硬编码收口 + 真源文档/AGENTS.md 同步（2026-08-15 设计）

## 任务界定（口径）

- 来源：F1-F4 快照修复 MiMo 最终 diff review ACCEPTED（`docs/reviews/code-review-20260815-122324.md`）后，用户裁决：`audit_pipeline.py:2681` 同款 `for cid in range(1, 7)` 硬编码**另立 slice**（F4 计划声称 2471 是唯一位置不准确）。
- 用户本次指令：启动该 slice；同步更新真源文档（design.md / implementation-control.md）与 AGENTS.md。
- 流程：计划 → MiMo plan review（PASS）→ DS（agents:0.1）实施 → MiMo diff review（ACCEPTED/NEEDS_FIX）。CIC-lite，不 commit 不 push。

## 实证（2026-08-15，代码核验）

1. `audit_pipeline.py:2681`：`ReportGenerationCoordinator._generate_chapter_content`（line 2641 def）内 LLM 分析摘要注入循环 `for cid in range(1, 7):`（Ch0/Ch7 读取前序章节摘要，`use_chapter_summaries=True` 时）。
2. 同文件其余章节迭代已模板驱动：2135 / 2138 / 2148（允许数字收集）、2195（生产调用方构造 chapter_summaries）、2471（审计上下文，F4 已修）。
3. 全量 `rg -n "for cid in range\(|range\(1, [0-9]\)|range\(0, [0-9]\)" fund_agent/service/` 确认仅 2681 一处剩余硬编码。
4. 模板 front ids：annual (1..6)、quarterly (1..4)、semiannual (1..5)，均 ⊂ range(1,7) → 修复后行为等价（只影响摘要注入循环的上界来源）。
5. `SnapshotReportTemplate.load_analysis_prompt(0)` 存在（prompts/ch0.md），`_generate_chapter_content` 对 Ch0 可走通。

## 设计

### 代码（audit_pipeline.py）

- 2681：`for cid in range(1, 7):` → `for cid in self._template.front_chapter_ids:`。
- 不抽新函数、不改签名、不动 annual 默认路径。

### 测试（tests/fund/service/test_snapshot_report_assembly.py 追加）

- 构造 fake LLM client（捕获 `generate_text` 的 user_prompt）＋ `ReportGenerationCoordinator(..., template=QUARTERLY_SNAPSHOT_TEMPLATE)`。
- 调用 `_generate_chapter_content(chapter_id=0, data_table="", performance={}, holdings={}, allocation={}, fees={}, use_chapter_summaries=True, chapter_summaries={1..6: "摘要{cid}"}, llm_client=fake)`。
- 断言 user_prompt 含 `### Ch4 摘要`、不含 `### Ch5 摘要` / `### Ch6 摘要`（quarterly front=(1..4)）；SEMIANNUAL（front=(1..5)）断言含 `### Ch5 摘要`、不含 `### Ch6 摘要`。
- 区分度：旧代码 `range(1,7)` 会把 Ch5/Ch6 摘要注入 quarterly/semiannual prompt → 断言失败，测试可证伪旧逻辑。
- 注意：`_generate_chapter_content` 内部还会对 llm_analysis 跑 `contains_non_year_numbers` 警告（非阻断），fake 返回不含数字的文本即可。

### 文档（用户要求同步）

1. `docs/design.md` §6.25 追加第 19 项：**章节迭代与摘要注入按模板驱动**——LLM 分析摘要注入（Ch0/Ch7 读前序摘要）与审计上下文均按 `template.front_chapter_ids` 驱动，禁止硬编码 `range(1,7)`；三模板 front ids：annual (1..6)、quarterly (1..4)、semiannual (1..5)。
2. `docs/implementation-control.md`「快照 slice 进度」节追加记录：
   - F1-F4 快照修复 slice（2026-08-15 收口）：MiMo deepreview 4 findings（F1 严重 risk_notes 误赋值 / F2 高 份额变动文本回退正则 / F3 中 period 标签 / F4 低 审计上下文硬编码）→ 用户裁决全修 → plan review PASS → DS 实施（snapshot_extraction / snapshot_generator / audit_pipeline / 测试）→ MiMo diff review ACCEPTED；测试 30+50+224 passed。
   - Slice G（本次）：audit_pipeline.py:2681 同款硬编码收口 + 文档/AGENTS.md 同步；验证命令与 review verdict 记录。
3. `AGENTS.md`「禁止事项」追加：禁止在报告/快照管线硬编码章节编号（如 `range(1,7)` / `range(1,8)`）；章节迭代、摘要注入与审计上下文必须按模板 `front_chapter_ids` / `chapter_ids` 驱动。

## 测试计划

- `uv run pytest tests/fund/service/test_snapshot_report_assembly.py -q --tb=short`（新测试）
- `uv run pytest tests/fund/service/test_audit_pipeline.py -q --tb=short`（回归）
- `uv run pytest tests/fund/service/test_snapshot_template.py tests/fund/service/test_snapshot_extraction.py -q --tb=short`
- AGENTS.md 最小验证：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short`
- `git diff --check`

## 非目标（明确）

- 不改其他章节迭代点（已全量 rg 确认仅 2681 一处）。
- 不动 CLI / prompts / registry / public tool 契约 / failure taxonomy。
- 不引入新函数或重构 `_generate_chapter_content` 签名。
- 不 commit / 不 push。

## allowed write set（DS 执行边界，禁止越界）

- `fund_agent/service/audit_pipeline.py`
- `tests/fund/service/test_snapshot_report_assembly.py`
- `docs/design.md`
- `docs/implementation-control.md`
- `AGENTS.md`

（计划与 plan-review / diff-review artifact 由 controller / reviewer 产出，不在 DS write set。）
