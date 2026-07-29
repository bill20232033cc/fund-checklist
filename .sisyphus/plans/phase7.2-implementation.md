# Phase 7.2 实施计划：交互体验增强 + 修复能力激活 + 场景扩展

## TL;DR

> **Quick Summary**: 推翻 Phase 7 routing context 预取，统一走 LLM 工具调用消除"硬编码感"；激活已定义但未接线的 SceneConfig（regenerate/repair）；新建 fix 场景（结构化占位符）；扩展 alias 覆盖；Rich 输出格式化；多轮对话增强。
>
> **Deliverables**:
> - 删除 routing context 预取，chat_service + extraction 统一走 LLM 工具调用
> - CLI `repair --chapter` 和 `regenerate --chapter` 子命令（激活已定义的 SceneConfig）
> - 新建 `FIX_SCENE_CONFIG` + `scenes/fix.md`（结构化占位符补强）
> - 扩展 `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` alias 覆盖
> - Rich 格式化表格输出
> - interactive 模式 `/history` 命令 + 追问建议
> - 审计分数驱动的修复策略自动选择
>
> **Estimated Effort**: Medium（12-16 天）
> **Parallel Execution**: YES — 3 waves

---

## Context

### 原始讨论

用户实测反馈（0626-07-26）揭示了 4 个问题：
1. 路由 alias 覆盖不足导致查询空结果
2. Routing Context 直返导致"硬编码感"
3. 多轮对话能力未被用户感知
4. 输出格式不直观

与 Dayu 的深度对照研究（14 场景、WeChat 机制、write 管道）确认了 fc 当前最紧迫的差距不是"做更多"，而是**激活已有但未接线的组件**。

### 裁决记录

| 裁决 | 结论 | 理由 |
|------|------|------|
| Routing Context 润色（方向B） | **推翻 Phase 7 预取，全量走 LLM** | 代码简化（删 70 行），统一对话体验，对齐 Dayu。延迟增加由 streaming 缓解，精度由 citation 强制校验兜底 |
| fix 场景 | **纳入 Phase 7.2** | Dayu 定义清晰：结构化占位符补强。对 fc 多年度数据不完整场景有价值。需新建 SceneConfig + prompt |
| decision 场景 | **暂缓** | Ch7 确定性信号评分已覆盖"继续/关注/替换"判断。LLM 版决策风险（隐性投资建议）大于收益，且基金分析 vs 股票分析的决策框架差异大 |
| conversation_compaction | **纳入（轻量）** | Phase 7 EpisodeSummary 已有基础，compaction.md prompt 已写但未接线。1 天接线 |
| regenerate/repair SceneConfig 激活 | **P0** — 组件已有，仅需接线 | SceneConfig + prompt fragment 已定义，从未被代码引用 |

---

## Work Objectives

### Core Objective
推翻 Phase 7 routing context 预取（统一走 LLM 工具调用），激活已定义的 repair/regenerate SceneConfig，新建 fix 场景，增强交互体验。

### Concrete Deliverables
- 删除 chat_service + extraction 中的 routing context 预取逻辑（~70 行）
- `fund-checklist repair --chapter` CLI 子命令（激活 REPAIR_SCENE_CONFIG）
- `fund-checklist regenerate --chapter` CLI 子命令（激活 REGENERATE_SCENE_CONFIG）
- `FIX_SCENE_CONFIG` + `prompts/scenes/fix.md` — 结构化占位符补强
- 扩展 `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 至少 5 个新 contract
- Rich Table 格式化输出（`--plain` 参数保留原始文本）
- `/history` 命令 + interactive 启动提示 + 追问建议
- 审计分数驱动的修复策略自动选择
- conversation_compaction prompt 接入

### Definition of Done
- [ ] interactive/ask 所有查询走 LLM 工具调用路径（无 routing context 直返）
- [ ] `repair --chapter 0,1,2` 只修复指定章节，exit code 0
- [ ] `regenerate --chapter 3` 只重写指定章节，审计反馈注入 prompt
- [ ] `fix --chapter 3` 检测并补强占位符（Task 4b 负责 CLI）
- [ ] "基金经理是谁" 返回非空回答（LLM 自主搜索）
- [ ] interactive 表格数据以 Rich Table 显示
- [ ] `/history` 显示最近 10 轮对话摘要
- [ ] `compaction.md` prompt 接入 EpisodeSummary 触发逻辑

### Must Have
- routing context 预取代码完全删除（不留死代码）
- repair/regenerate 不复用 generate 的全量重跑逻辑
- 修复后保留 citation + evidence
- fix 占位符格式对齐 Dayu 规范（`【占位符】（缺口：... ｜ 需要：...）`）
- `/history` 命令在 interactive REPL 中可用

### Must NOT Have (Guardrails)
- 不新增 LLM provider
- 不修改 generate 命令的核心逻辑
- 不改变 SessionStore 的持久化格式
- decision 场景不进入本次实施
- fix 场景不产生投资建议

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES（pytest + fixtures）
- **Automated tests**: YES (TDD for new code, tests-after for wiring)
- **Framework**: pytest (uv run pytest)

### QA Policy
Every task MUST include agent-executed QA scenarios.
- **CLI**: Bash 执行命令，验证 exit code + stdout
- **Interactive**: interactive_bash (tmux) 模拟用户输入，捕获输出
- **API/Service**: Bash (curl / uv run python) 调用 CLI 验证

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (启动即可并行 — 基础设施重构):
├── Task 1: 删除 routing context 预取 [quick]
├── Task 2: 扩展路由 alias 覆盖 [quick]
└── Task 3: Rich 输出格式化 [quick]

Wave 2 (依赖 Wave 1 — CLI 子命令 + 场景):
├── Task 4: 新建 FIX_SCENE_CONFIG + scenes/fix.md [deep]
├── Task 4b: CLI fix 子命令 [deep]  (依赖: Task 4)
├── Task 5: CLI repair 子命令 [deep]  (依赖: Task 1)
├── Task 6: CLI regenerate 子命令 [deep]  (依赖: Task 1)
├── Task 7: 审计分数驱动策略自动选择 [deep]  (依赖: Task 1)
├── Task 8: 多轮对话引导 + /history [quick]  (依赖: Task 1)
└── Task 9: conversation_compaction 接入 [quick]  (依赖: Task 1)

Wave 3 (依赖 Wave 2 — 端到端验证):
├── Task 10: 端到端 smoke 测试 [unspecified-high]
└── Task 11: 全量回归 [unspecified-high]

Wave FINAL (4 个并行审查):
├── Task F1: 计划合规审计 [oracle]
├── Task F2: 代码质量审查 [unspecified-high]
├── Task F3: 手动 QA 执行 [unspecified-high]
└── Task F4: 范围忠实度检查 [deep]
```

**Critical Path**: Task 1 → Task 5 → Task 10
**Parallel Speedup**: ~60% faster than sequential (Wave 1: 3 parallel, Wave 2: 6 parallel)

### Agent Dispatch Summary

- **Wave 1**: 3 — T1 → `quick`, T2 → `quick`, T3 → `visual-engineering`
- **Wave 2**: 6 — T4 → `deep`, T4b → `deep`, T5 → `deep`, T6 → `deep`, T7 → `deep`, T8 → `quick`, T9 → `quick`
- **Wave 3**: 2 — T10 → `unspecified-high`, T11 → `unspecified-high`
- **FINAL**: 4 — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [ ] 1. 删除 routing context 预取，统一走 LLM 工具调用

  **What to do**:
  - 删除 `chat_service.py:169-195` 中的 routing context 预取逻辑（确定性 agent 检索 + `_DIRECT_KEYWORDS` 判断 + 直返）
  - 删除 `extraction.py:816-900` 中 `ask_question()` 的独立预取逻辑（含 `_DIRECT_RETURN_KEYWORDS`）
  - 删除两处的 `_DIRECT_KEYWORDS` / `_DIRECT_RETURN_KEYWORDS` 局部变量
  - `chat_turn()` 直接走 LLM 工具调用路径：`agent_result = self._run_agent(scene_config=scene_config, ...)`
  - `ask_question()` 同理，删除独立预取，统一走 LLM
  - `_route_plan_for_query` 保留（`read` 确定性命令仍使用）
  - 测试：验证 interactive/ask 模式下所有查询走 LLM 路径

  **Must NOT do**:
  - 不删除 `_route_plan_for_query` 函数（`read` 确定性命令依赖）
  - 不修改 LLM 工具调用路径的 citation enforcement
  - 不改变 SceneConfig 的 allowed_tools

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯删除操作（~70 行），不新增逻辑
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: Tasks 5, 6, 7, 8, 9
  - **Blocked By**: None

  **References**:
  - `fund_agent/service/chat_service.py:169-195` — routing context 预取逻辑（确定性 agent + _DIRECT_KEYWORDS + 直返）
  - `fund_agent/service/extraction.py:816-900` — ask_question() 独立的预取逻辑（_DIRECT_RETURN_KEYWORDS）
  - `fund_agent/service/chat_service.py:130-165` — chat_turn() 中 LLM 工具调用路径（预取删除后应保留的唯一路径）

  **Acceptance Criteria**:
  - [ ] `grep -rn "_DIRECT_KEYWORDS\|_DIRECT_RETURN_KEYWORDS" fund_agent/service/` 无匹配
  - [ ] `grep -rn "routing_context" fund_agent/service/` 仅在 `_route_plan_for_query` 返回值和 `read` 确定性命令中出现
  - [ ] interactive 模式下"管理费率是多少"走 LLM 路径（tool trace 包含 search_document）
  - [ ] `uv run pytest tests/fund/service/test_chat_service.py tests/fund/cli/test_cli_interactive.py -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: No DIRECT_KEYWORDS remains in codebase
    Tool: Bash (grep)
    Steps:
      1. grep -rn "DIRECT_KEYWORDS\|DIRECT_RETURN_KEYWORDS" fund_agent/service/
    Expected Result: Zero matches (all deleted)
    Evidence: .sisyphus/evidence/task-1-no-direct-keywords.txt

  Scenario: Interactive query "管理费率是多少" goes through LLM path
    Tool: interactive_bash (tmux)
    Preconditions: interactive mode with document loaded
    Steps:
      1. send-keys "管理费率是多少" Enter
      2. Wait 10s for LLM response with tool calls
      3. capture-pane and check for natural language response (not raw data dump)
    Expected Result: Natural language answer with citation, no raw "查询管理费] 1.20%" format
    Evidence: .sisyphus/evidence/task-1-llm-path.txt
  ```

  **Commit**: YES
  - Message: `refactor(phase7.2): remove routing context pre-fetch, unify to LLM tool-calling path`
  - Files: `fund_agent/service/chat_service.py`, `fund_agent/service/extraction.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_chat_service.py tests/fund/cli/test_cli_interactive.py -v --tb=short`

- [ ] 2. 扩展路由 alias 覆盖

  **What to do**:
  - 在 `fund_agent/service/extraction.py` 的 `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 中添加 5 个新 `_DisclosureLocatorContract`：
    - `fund_manager`: aliases=("基金经理", "基金经理是谁", "谁是基金经理", "经理信息")
    - `fund_type`: aliases=("基金类型", "什么类型", "主动还是被动")
    - `investment_strategy`: aliases=("投资策略", "投资理念", "投资方法")
    - `risk_return`: aliases=("风险收益特征", "风险等级", "收益风险")
    - `conclusion`: aliases=("结论", "观点", "评价", "综合评价")
  - 为每个新 contract 配置 `candidate_queries` 和 `acceptable_title_family`
  - 在 `models.py` 中确认 `_DisclosureLocatorContract` 字段完整
  - 测试：验证每个新 alias 能命中 `_route_plan_for_query()`

  **Must NOT do**:
  - 不修改现有 4 个 contract 的 alias（holdings_top10, asset_allocation, fee_rates, performance_returns）
  - 不新增 LLM intent 路由（保持关键词匹配）
  - 不新增 Service 方法

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯数据条目添加，不改变路由逻辑，遵循已有 contract 模式
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Tasks 4, 5 (CLI repair/regenerate 依赖 routing 正确)
  - **Blocked By**: None

  **References**:
  - `fund_agent/service/extraction.py:174-213` — 现有 4 个 `_DisclosureLocatorContract` 示例
  - `fund_agent/service/extraction.py:4163-4200` — `_route_plan_for_query()` 遍历 registry 的逻辑
  - `fund_agent/service/models.py` — `_DisclosureLocatorContract` 字段定义（`profile_name`, `aliases`, `candidate_queries`, `acceptable_title_family`, `requires_table_citation`, `extraction_allowed`）

  **Acceptance Criteria**:
  - [ ] `len(DISCLOSURE_LOCATOR_CONTRACT_REGISTRY)` 从 4 增加到至少 9
  - [ ] `_route_plan_for_query("基金经理是谁")` 返回 `profile_name="fund_manager"` 的 route plan
  - [ ] `_route_plan_for_query("基金类型是什么")` 返回 `profile_name="fund_type"` 的 route plan
  - [ ] 现有 4 个 contract alias 无回退
  - [ ] `uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: "基金经理是谁" hits fund_manager route
    Tool: Bash (uv run python)
    Steps:
      1. python -c "from fund_agent.service.extraction import _route_plan_for_query; r = _route_plan_for_query('基金经理是谁'); print(r.profile_name)"
      2. Assert output contains "fund_manager"
    Expected Result: route profile_name == "fund_manager"
    Evidence: .sisyphus/evidence/task-2-manager-route.txt

  Scenario: "结论是什么" hits conclusion route
    Tool: Bash (uv run python)
    Steps:
      1. python -c "from fund_agent.service.extraction import _route_plan_for_query; r = _route_plan_for_query('结论是什么'); print(r.profile_name)"
    Expected Result: route profile_name == "conclusion"
    Evidence: .sisyphus/evidence/task-2-conclusion-route.txt

  Scenario: Existing alias "重仓股" still works
    Tool: Bash (uv run python)
    Steps:
      1. python -c "from fund_agent.service.extraction import _route_plan_for_query; r = _route_plan_for_query('重仓股'); print(r.profile_name)"
    Expected Result: route profile_name == "holdings_top10"
    Evidence: .sisyphus/evidence/task-2-existing-alias.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7.2): expand routing alias coverage (fund_manager, fund_type, strategy, risk, conclusion)`
  - Files: `fund_agent/service/extraction.py`, `tests/fund/service/test_extraction.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short`

- [ ] 3. Rich 输出格式化

  **What to do**:
  - 在 interactive 模式的回答输出中，检测 Markdown 表格并转换为 Rich Table
  - 为 CLI 新增 `--plain` 参数保留原始文本输出
  - 在 `_run_interactive_command` 中集成 Rich Console
  - 表格渲染：表头粗体、列对齐、边框样式
  - Markdown 粗体/斜体渲染

  **Must NOT do**:
  - 不改变 streaming 模式下的输出（streaming 以内容增量为主，不适合 Rich 表格）
  - 不改变 generate 命令的输出格式
  - 不引入新的外部依赖（Rich 已在 pyproject.toml 中）

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 终端 UI 格式化，Rich 表格渲染
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `fund_agent/cli/main.py:1067-1167` — `_run_interactive_command` 回答输出逻辑
  - `pyproject.toml` — Rich 已在依赖中
  - Rich 官方文档: `https://rich.readthedocs.io/en/stable/tables.html` — Table 构造方法

  **Acceptance Criteria**:
  - [ ] interactive 模式中表格数据以 Rich Table 显示（有边框、表头粗体、列对齐）
  - [ ] `--plain` 参数保留原始 Markdown 文本
  - [ ] Markdown 粗体/斜体正确渲染
  - [ ] 非表格内容无格式化变化
  - [ ] `uv run pytest tests/fund/cli/test_cli_interactive.py -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: Table data rendered as Rich Table in interactive
    Tool: interactive_bash (tmux)
    Preconditions: interactive mode started with a fund document loaded
    Steps:
      1. send-keys "前十大持仓是什么？" Enter
      2. Wait 5 seconds for response
      3. capture-pane and check for Rich table borders (│, ─, ┌, ┐ characters)
    Expected Result: Output contains Rich table formatting characters
    Failure Indicators: Plain text table without borders
    Evidence: .sisyphus/evidence/task-3-rich-table.txt

  Scenario: --plain flag preserves raw text
    Tool: Bash
    Steps:
      1. uv run fund-checklist interactive --fund-code 011649 --work-dir .fund_e2e_011649 --plain <<< "exit"
      2. Check that --plain flag is accepted
    Expected Result: --plain flag shows in --help output and is accepted
    Evidence: .sisyphus/evidence/task-3-plain-flag.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7.2): add Rich table formatting for interactive mode`
  - Files: `fund_agent/cli/main.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli_interactive.py -v --tb=short`

- [ ] 4. 新建 FIX_SCENE_CONFIG + `scenes/fix.md`

  **What to do**:
  - 在 `scene_config.py` 中新增 `FIX_SCENE_CONFIG`
    - model: deepseek-v4-flash (t=0.2)
    - max_iterations: 12
    - fragments: base/agents.md + base/soul.md + base/fact_rules.md + scenes/fix.md
    - context_slots: `chapter_content`, `audit_feedback`, `chapter_contract`
    - allowed_tools: 5 reading tools
  - 新建 `prompts/scenes/fix.md`：
    - 定义 fix 场景的 LLM 行为契约
    - 占位符检测：识别 `[数据缺失]`、`N/A`、`<when_missing>` 触发的降级声明
    - 占位符补强：LLM 使用 reading tools 检索缺失数据
    - 能补则补，不能补则保留规范化占位符
    - 占位符格式对齐 Dayu：`【占位符】（缺口：{缺失信息} ｜ 需要：{来源类型} ｜ 已检索：{已检索范围} ｜ 下一步：{建议}）`
  - 在 `chapter_generator.py` 中新增 `_fix_chapter_placeholders()`，调用 ChatService 执行 fix

  **Must NOT do**:
  - 不修改 generate 命令的核心逻辑
  - fix 不补强投资建议相关内容
  - 不编造不存在的数据

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 新 SceneConfig + prompt fragment + 占位符检测逻辑 + CLI 接入
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 7, 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Task 1

  **References**:
  - `fund_agent/service/scene_config.py:121-168` — REGENERATE/REPAIR SceneConfig 模式（复用为模板）
  - `fund_agent/service/prompts/scenes/repair.md` — repair prompt 参考（fix 比 repair 更结构化）
  - `docs/dayu-scenes-research.md:101-124` — Dayu fix 场景定义（占位符格式、执行契约）
  - `fund_agent/service/chapter_generator.py` — `generate_data_table` 中 `<when_missing>` 触发点
  - `fund_agent/service/audit_pipeline.py:1497` — ChapterRepairer（参考修复入口模式）

  **Acceptance Criteria**:
  - [ ] `FIX_SCENE_CONFIG` 在 `scene_config.py` 中定义，fragments 正确组装
  - [ ] `prompts/scenes/fix.md` 存在，包含占位符检测和补强规则
  - [ ] 修复后占位符格式符合规范：`【占位符】（缺口：...）`
  - [ ] 能补的数据被补上（如从其他年份年报中获取缺失字段）
  - [ ] 不能补的数据保留规范化占位符（不编造）
  - [ ] `uv run pytest tests/fund/service/test_scene_config.py -k "fix" -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: fix detects and fills placeholder
    Tool: Bash
    Preconditions: Chapter with a [数据缺失] marker
    Steps:
      1. Create report with placeholder in chapter 3
      2. Run fix on that chapter
      3. Check placeholder is replaced with actual data or structured gap report
    Expected Result: Placeholder replaced — either with real data OR structured 【占位符】format
    Failure Indicators: Placeholder unchanged, no attempt to fill, hallucinated data
    Evidence: .sisyphus/evidence/task-4-fix-placeholder.txt

  Scenario: fix preserves structured gap for unfillable data
    Tool: Bash
    Steps:
      1. Create scenario where data genuinely unavailable
      2. Run fix
      3. Check output contains 【占位符】with gap/source/retrieved/next fields
    Expected Result: Structured placeholder format, no hallucination
    Evidence: .sisyphus/evidence/task-4-fix-gap.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7.2): add FIX_SCENE_CONFIG + scenes/fix.md for structured placeholder filling`
  - Files: `fund_agent/service/scene_config.py`, `fund_agent/service/prompts/scenes/fix.md`, `fund_agent/service/chapter_generator.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_scene_config.py -k "fix" -v --tb=short`

- [ ] 4b. CLI `fix` 子命令

  **What to do**:
  - 在 `fund_agent/cli/main.py` 中新增 `_run_fix_command` 函数和 `fix` 子命令
    - 参数：`--fund-code`、`--work-dir`、`--chapter`（必填，指定修复的章节号）
    - 调用 `chapter_generator._fix_chapter_placeholders()` 执行修复
    - 输出修复结果（补强的占位符数量、保留的占位符数量）
  - 在 `tests/fund/cli/test_cli.py` 中新增 `test_fix_chapter` 测试
    - 验证 `fix --chapter 3` 只修复 Ch3
    - 验证 exit code 0
    - 验证输出包含修复统计

  **Must NOT do**:
  - 不修改 `repair` 或 `regenerate` 子命令
  - 不修改 `_fix_chapter_placeholders()` 内部逻辑（Task 4 负责）
  - 不引入新的 LLM provider

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: CLI 子命令注册 + 参数解析 + 调用链路
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 7, 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Task 4

  **References**:
  - `fund_agent/cli/main.py:1-50` — 现有 CLI 子命令注册模式
  - `fund_agent/cli/main.py:200-250` — `_run_generate_command` 参考（参数解析 + 调用 service）
  - `fund_agent/service/chapter_generator.py` — `_fix_chapter_placeholders()` 函数（Task 4 实现）

  **Acceptance Criteria**:
  - [ ] `fix` 子命令在 `main.py` 中注册，参数正确
  - [ ] `fix --chapter 3` 只修复 Ch3，exit code 0
  - [ ] 输出包含修复统计（补强数量、保留数量）
  - [ ] `uv run pytest tests/fund/cli/test_cli.py -k "fix" -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: fix repairs only specified chapter
    Tool: Bash
    Steps:
      1. fund-checklist fix --fund-code 006597 --work-dir .fund_checklist_cli_smoke --chapter 3
      2. Check exit code is 0
      3. Check output mentions chapter 3 repair stats
    Expected Result: Only chapter 3 placeholders processed
    Failure Indicators: Exit code != 0, processes other chapters, no repair stats
    Evidence: .sisyphus/evidence/task-4b-fix-chapter.txt

  Scenario: fix rejects missing chapter argument
    Tool: Bash
    Steps:
      1. fund-checklist fix --fund-code 006597 --work-dir .fund_checklist_cli_smoke
      2. Check exit code is non-zero
      3. Check error message mentions missing --chapter
    Expected Result: CLI error with clear message
    Evidence: .sisyphus/evidence/task-4b-fix-missing-chapter.txt
  ```

  **Commit**: YES (groups with Task 4)
  - Message: `feat(phase7.2): add CLI fix subcommand for placeholder repair`
  - Files: `fund_agent/cli/main.py`, `tests/fund/cli/test_cli.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli.py -k "fix" -v --tb=short`

- [ ] 5. CLI `repair` 子命令

  **What to do**:
  - 在 `fund_agent/cli/main.py` 中新增 `_run_repair_command` 函数和 `repair` 子命令
  - 参数：`--fund-code`（必填）、`--year`（必填）、`--chapter`（必填，逗号分隔）、`--work-dir`、`--llm`
  - 接入 `REPAIR_SCENE_CONFIG` → `ChatTurnContract(scene="repair")` → `ChatService.chat_turn()`
  - 调用 `ChapterRepairer.generate_repair_plan()` + `apply_patch()`
  - 只修复指定章节，不改动其他章节
  - 输出：修复前后审计分数对比

  **Must NOT do**:
  - 不注册新的 LLM provider
  - 不修改 `ChapterRepairer` 的核心逻辑
  - 不重新生成整份报告

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: CLI 新子命令、Service 层接入、SceneConfig 激活、审计管线串联
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES (different function in same file as T6)
  - **Parallel Group**: Wave 2 (with Tasks 4, 6, 7, 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Task 1

  **References**:
  - `fund_agent/cli/main.py:870-920` — generate 子命令的 CLI 参数模式
  - `fund_agent/service/scene_config.py:145-168` — `REPAIR_SCENE_CONFIG`（已定义，未接线）
  - `fund_agent/service/prompts/scenes/repair.md` — repair prompt（已写，未用）
  - `fund_agent/service/audit_pipeline.py:1497-1630` — `ChapterRepairer.generate_repair_plan()` + `apply_patch()`
  - `fund_agent/service/chat_service.py:89-130` — ChatService 使用 SceneConfig 的参考模式

  **Acceptance Criteria**:
  - [ ] `fund-checklist repair --help` 显示参数说明
  - [ ] `fund-checklist repair --fund-code 004393 --year 2024 --chapter 3` exit code 0
  - [ ] 修复后只有 Ch3 被修改，其他章节不变
  - [ ] `uv run pytest tests/fund/cli/test_cli.py -k "repair" -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: repair single chapter
    Tool: Bash
    Preconditions: Report exists for fund 004393 year 2024
    Steps:
      1. uv run fund-checklist repair --fund-code 004393 --year 2024 --chapter 3 --llm 2>&1
      2. Check exit code 0, report shows before/after scores
    Expected Result: exit code 0, only Ch3 modified
    Evidence: .sisyphus/evidence/task-5-repair-ch3.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7.2): add CLI repair subcommand, activate REPAIR_SCENE_CONFIG`
  - Files: `fund_agent/cli/main.py`, `tests/fund/cli/test_cli.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli.py -k "repair" -v --tb=short`

- [ ] 6. CLI `regenerate` 子命令

  **What to do**:
  - 在 `fund_agent/cli/main.py` 中新增 `_run_regenerate_command` 函数和 `regenerate` 子命令
  - 参数：`--fund-code`（必填）、`--year`（必填）、`--chapter`（必填，逗号分隔）、`--work-dir`、`--llm`
  - 调用 `ReportGenerationCoordinator._regenerate_chapter()`，但**注入审计反馈**作为 prompt context
  - 接入 `REGENERATE_SCENE_CONFIG` → `ChatTurnContract(scene="regenerate")` → `ChatService.chat_turn()`
  - 只重写指定章节，保留其他章节不变
  - 输出：重写前后审计分数对比

  **Must NOT do**:
  - 不在 `_regenerate_chapter()` 中只做相同的 prompt 重调（当前行为）— 必须注入审计违规作为 context slot
  - 不重写非指定章节
  - 不改变 `ReportGenerationCoordinator` 的章节生成顺序

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 与 Task 4 同级复杂度，但涉及 `_regenerate_chapter()` 的行为变更（审计反馈注入）
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 4 — different CLI subcommand, same file but different functions)
  - **Parallel Group**: Wave 2 (with Tasks 4, 6, 7)
  - **Blocks**: Task 8

  **References**:
  - `fund_agent/service/scene_config.py:121-143` — `REGENERATE_SCENE_CONFIG`（已定义，未接线）
  - `fund_agent/service/prompts/scenes/regenerate.md` — regenerate prompt fragment（已写，未用）
  - `fund_agent/service/audit_pipeline.py:2316-2344` — `_regenerate_chapter()` 当前实现（仅重新调用 `_generate_chapter_content`，无审计反馈注入）
  - `fund_agent/service/audit_pipeline.py:559-580` — `AuditDecision` 含违规列表（注入为 context slot 的数据源）
  - Task 4 references — CLI 子命令的参考模式

  **Acceptance Criteria**:
  - [ ] `fund-checklist regenerate --help` 显示参数说明
  - [ ] `fund-checklist regenerate --fund-code 004393 --year 2024 --chapter 3` exit code 0
  - [ ] 只重写 Ch3，其他章节内容不变
  - [ ] 重写 prompt 包含审计违规（通过 audit_feedback context slot 注入）
  - [ ] `uv run pytest tests/fund/cli/test_cli.py -k "regenerate" -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: regenerate single chapter with audit feedback
    Tool: Bash
    Preconditions: A report with known audit violations in chapter 3
    Steps:
      1. uv run fund-checklist regenerate --fund-code 004393 --year 2024 --chapter 3 --llm 2>&1
      2. Check exit code is 0
      3. Check output mentions audit violations being addressed
      4. Verify Ch0/1/2/4/5/6/7 unchanged
    Expected Result: exit code 0, Ch3 regenerated with audit context, other chapters intact
    Failure Indicators: exit code non-zero, no audit context mentioned, other chapters modified
    Evidence: .sisyphus/evidence/task-5-regenerate-ch3.txt

  Scenario: regenerate reports before/after audit score
    Tool: Bash
    Steps:
      1. Run regenerate and capture output
      2. Check output contains "修复前分数" and "修复后分数" (or equivalent)
      3. Verify after-score >= before-score
    Expected Result: Score comparison visible in output
    Evidence: .sisyphus/evidence/task-5-score-delta.txt
  ```

  **Commit**: YES (groups with Task 7)
  - Message: `feat(phase7.2): add CLI regenerate subcommand with audit feedback injection`
  - Files: `fund_agent/cli/main.py`, `fund_agent/service/audit_pipeline.py`, `tests/fund/cli/test_cli.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli.py -k "regenerate" -v --tb=short`

- [ ] 7. 审计分数驱动的策略自动选择

  **What to do**:
  - 在 `fund_agent/cli/main.py` 中新增 `_run_auto_fix_command` 或扩展现有逻辑
  - 基于审计分数和违规严重度自动选择修复策略：
    - 分数 ≥ 80 → skip
    - 分数 50-79 + 无 CRITICAL → 走 repair 路径
    - 分数 50-79 + 有 CRITICAL → 走 regenerate 路径
    - 分数 < 50 → 走 regenerate 路径
  - 复用 `audit_pipeline.py` 中已有的 `AuditDecision.recommendation` 和 `ChapterProcessState`
  - 输出：每章策略选择 + 执行结果

  **Must NOT do**:
  - 不新增独立的 CLI 子命令（可以是一个 flag，如 `--auto`）
  - 不绕过现有的 PATCH/REGENERATE 重试上限（各 3 次）
  - 不改变审计阈值（SCORE_PASS=80, SCORE_PATCH=50）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 涉及审计管线串联、策略决策树、与 Task 4/5 的编排
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES (logic mostly independent of Task 4/5 implementation)
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 7)
  - **Blocks**: Task 8

  **References**:
  - `fund_agent/service/audit_pipeline.py:1751-1752` — `SCORE_PASS = 80.0`, `SCORE_PATCH = 50.0`
  - `fund_agent/service/audit_pipeline.py:559-580` — `AuditDecision.recommendation`（pass/patch/regenerate）
  - `fund_agent/service/audit_pipeline.py:629-680` — `ChapterProcessState.can_patch()` / `can_regenerate()`
  - `fund_agent/service/audit_pipeline.py:1763-1764` — `MAX_PATCH_ATTEMPTS = 3`, `MAX_REGENERATE_ATTEMPTS = 3`
  - `.sisyphus/plans/phase7.2-candidates.md:456-468` — 完整 4 层决策树流程图

  **Acceptance Criteria**:
  - [ ] 自动选择逻辑正确：score ≥ 80 → skip, 50-79 无 CRITICAL → repair, 其他 → regenerate
  - [ ] 每章输出策略选择原因
  - [ ] 修复后增量审计（只重审修复过的章节）
  - [ ] PATCH/REGENERATE 各最多 3 次，超过后降级
  - [ ] `uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: Auto-select repair for medium-scored chapter with no CRITICAL violations
    Tool: Bash
    Steps:
      1. Create test scenario: chapter score=65, violations=[MAJOR, MINOR] (no CRITICAL)
      2. Run auto-fix logic
      3. Assert strategy == "repair"
    Expected Result: strategy == "repair"
    Evidence: .sisyphus/evidence/task-6-auto-repair.txt

  Scenario: Auto-select regenerate for medium-scored chapter WITH CRITICAL
    Tool: Bash
    Steps:
      1. Create test scenario: chapter score=65, violations=[CRITICAL, MAJOR]
      2. Run auto-fix logic
      3. Assert strategy == "regenerate"
    Expected Result: strategy == "regenerate"
    Evidence: .sisyphus/evidence/task-6-auto-regenerate.txt

  Scenario: Skip for high-scored chapter
    Tool: Bash
    Steps:
      1. Create test scenario: chapter score=85, violations=[]
      2. Run auto-fix logic
      3. Assert strategy == "pass" (skip)
    Expected Result: strategy == "pass"
    Evidence: .sisyphus/evidence/task-6-auto-skip.txt
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `feat(phase7.2): add audit-score-driven repair strategy auto-selection`
  - Files: `fund_agent/cli/main.py`, `fund_agent/service/audit_pipeline.py`, `tests/fund/service/test_audit_pipeline.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short`

- [ ] 8. 多轮对话引导 + `/history` 命令

  **What to do**:
  - 在 interactive 启动时显示多轮对话提示
  - 在回答末尾添加追问建议（基于当前查询的上下文）
  - 新增 `/history` 命令：显示最近 10 轮对话摘要（角色 + 内容前 80 字符 + 时间）
  - 新增 `/help` 命令增强（显示 `/history`、`/document`、`/clear` 等可用命令）

  **Must NOT do**:
  - 不改变 SessionStore 的持久化格式
  - 不新增 Episode Summary 触发逻辑（Phase 7 已有）
  - 不在 `/history` 中显示 tool trace（只显示对话内容）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: CLI UX 增强，读取 session turns 并格式化输出
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `fund_agent/cli/main.py:1067-1167` — `_run_interactive_command` REPL 循环
  - `fund_agent/cli/main.py:1270-1272` — `known_commands` set（当前 11 个斜杠命令）
  - `fund_agent/host/session_store.py` — `SessionStore.load()` 返回 Session（含 turns 列表）
  - `fund_agent/service/session_models.py:75-100` — `Session` 模型（`turns: list[Turn]`, `pinned_state`）
  - `fund_agent/service/session_models.py:48-62` — `Turn` 模型（`role`, `content`, `timestamp`）

  **Acceptance Criteria**:
  - [ ] interactive 启动时显示 "提示：支持多轮对话，可以追问上一个问题的细节。输入 /help 查看命令。"
  - [ ] `/history` 显示最近 10 轮对话摘要
  - [ ] `/help` 列出 `/history`、`/document`、`/clear`、`exit`
  - [ ] 追问建议在分析性回答末尾出现
  - [ ] `uv run pytest tests/fund/cli/test_cli_interactive.py -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: /history shows recent conversation turns
    Tool: interactive_bash (tmux)
    Preconditions: interactive session with at least 2 turns of conversation
    Steps:
      1. send-keys "/history" Enter
      2. Wait 2 seconds
      3. capture-pane and check for "user:" and "assistant:" labels
    Expected Result: Output shows last N turns with role labels and timestamps
    Failure Indicators: "Unknown command" error, empty output, or only 1 turn
    Evidence: .sisyphus/evidence/task-7-history.txt

  Scenario: Follow-up suggestions after analytical response
    Tool: interactive_bash (tmux)
    Steps:
      1. send-keys "这只基金为什么表现好？" Enter
      2. Wait 10 seconds for LLM response
      3. capture-pane and check for suggestion text like "您可以继续问："
    Expected Result: Response ends with follow-up question suggestions
    Evidence: .sisyphus/evidence/task-7-suggestions.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7.2): add /history command, follow-up suggestions, interactive startup tips`
  - Files: `fund_agent/cli/main.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli_interactive.py -v --tb=short`

- [ ] 9. conversation_compaction prompt 接入

  **What to do**:
  - 将 `prompts/interactive/compaction.md` 接入 `ChatService._maybe_trigger_compaction()`
  - 当前 compaction 使用硬编码的压缩 prompt，改为从 `PromptComposer` 加载 `compaction.md`
  - 触发条件不变（≥10 轮 OR ≥60% token）
  - 执行方式不变（daemon thread 异步 LLM 调用）
  - EpisodeSummary 数据模型不变
  - 测试：验证长对话触发 compaction，且压缩摘要可读

  **Must NOT do**:
  - 不改变 EpisodeSummary 数据模型
  - 不修改 compaction 触发条件
  - 不新增 SceneConfig（compaction 不是独立 scene，是 ChatService 内部机制）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 1 行 prompt 引用替换 + 验证，逻辑和模型均不变
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 7, 8)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `fund_agent/service/prompts/interactive/compaction.md` — compaction prompt（已写，未接线）
  - `fund_agent/service/chat_service.py:240-280` — `_maybe_trigger_compaction()` 当前实现
  - `fund_agent/service/prompt_composer.py:60-120` — `PromptComposer.load_fragment()` 加载模式

  **Acceptance Criteria**:
  - [ ] `_maybe_trigger_compaction()` 使用 `PromptComposer` 加载 `compaction.md` 而非硬编码 prompt
  - [ ] compaction 触发后 EpisodeSummary 格式与当前一致
  - [ ] `uv run pytest tests/fund/service/test_chat_service.py -v --tb=short` → PASS

  **QA Scenarios**:
  ```
  Scenario: Compaction triggered after 10 turns
    Tool: Bash (pytest)
    Steps:
      1. uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short
      2. Verify compaction is triggered and summary is readable
    Expected Result: Test passes, compaction generates EpisodeSummary
    Evidence: .sisyphus/evidence/task-9-compaction.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7.2): wire compaction.md prompt into ChatService compaction trigger`
  - Files: `fund_agent/service/chat_service.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short`

- [ ] 10. 端到端 smoke 测试

  **What to do**:
  - 创建端到端 smoke 测试，验证 Phase 7.2 所有 P0 功能可串联工作
  - Smoke 1: interactive 启动 → 查询"基金经理是谁" → 验证非空回答 + Rich 表格
  - Smoke 2: generate 报告 → repair 指定章节 → 验证分数变化
  - Smoke 3: generate 报告 → regenerate 指定章节 → 验证单章重写
  - Smoke 4: `/history` 命令可用 + 追问建议出现
  - Smoke 5: 全量回归（Phase 7 所有测试）

  **Must NOT do**:
  - 不修改生产代码（仅测试）
  - 不新增慢路径测试（每个 smoke 最多 30s 或 skip）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 多场景串联验证，需要编排多个 CLI 调用
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 9)
  - **Parallel Group**: Wave 3
  - **Blocks**: Final Verification (F1-F4)
  - **Blocked By**: Tasks 4, 5, 6, 7

  **References**:
  - Task 4-7 acceptance criteria — smoke 测试验证的逻辑基准
  - `tests/fund/cli/test_cli.py` — 现有 CLI 测试模式

  **Acceptance Criteria**:
  - [ ] Smoke 1: "基金经理是谁" 返回非空结果
  - [ ] Smoke 2: repair 后分数不降低
  - [ ] Smoke 3: regenerate 后只有指定章节变化
  - [ ] Smoke 4: `/history` 显示对话摘要
  - [ ] Smoke 5: 全量回归 PASS（Phase 7 测试不回退）

  **QA Scenarios**:
  ```
  Scenario: Full end-to-end flow
    Tool: Bash
    Steps:
      1. uv run pytest tests/fund/cli/test_cli.py -k "repair or regenerate" -v --tb=short
      2. uv run pytest tests/fund/cli/test_cli_interactive.py -v --tb=short
      3. uv run pytest tests/fund/service/test_audit_pipeline.py -v --tb=short
    Expected Result: All tests pass, 0 failures
    Evidence: .sisyphus/evidence/task-8-e2e.txt
  ```

  **Commit**: YES
  - Message: `test(phase7.2): add end-to-end smoke tests for repair, regenerate, alias, formatting`
  - Files: `tests/fund/cli/test_cli.py`, `tests/fund/cli/test_cli_interactive.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli.py tests/fund/cli/test_cli_interactive.py -v --tb=short`

- [ ] 11. 全量回归测试

  **What to do**:
  - 运行 Phase 7 全量测试套件，确保所有变更无回退
  - 新增代码覆盖所有新增函数/分支
  - 检查 ci

  **Must NOT do**:
  - 不修改非测试文件
  - 不新增 Phase 7 范围外的测试

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 批量测试执行 + 回归分析
  - **Skills**: []
  - **Skills Evaluated but Omitted**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 8)
  - **Parallel Group**: Wave 3
  - **Blocks**: Final Verification (F1-F4)
  - **Blocked By**: Tasks 4, 5, 6, 7

  **References**:
  - Phase 7 验证命令 (AGENTS.md): `uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short`

  **Acceptance Criteria**:
  - [ ] Phase 7 全量回归 ≥153 passed（不回退）
  - [ ] 新增测试 ≥20 passed
  - [ ] 无 skipped（除 network-dependent tests）

  **QA Scenarios**:
  ```
  Scenario: Full regression passes
    Tool: Bash
    Steps:
      1. uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py -v --tb=short
      2. Check pass count >= pre-change baseline
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-9-regression.txt
  ```

  **Commit**: NO (验证任务，无代码变更)

---

## Final Verification Wave

- [ ] F1. **计划合规审计** — `oracle`
  逐条核对：Must Have 5 项是否全部实现，Must NOT Have 5 项是否全部遵守。搜索代码库中的禁止模式。检查 evidence 文件完整。
  Output: `Must Have [5/5] | Must NOT Have [5/5] | Tasks [9/9] | VERDICT: APPROVE/REJECT`

- [ ] F2. **代码质量审查** — `unspecified-high`
  Run `uv run pytest` (Phase 7 + new tests)。检查所有变更文件：`as any`/`@ts-ignore`，空 catch，console.log，注释掉的代码，未使用的 import，AI slop（过度注释、过度抽象、泛型命名 data/result/item/temp）。
  Output: `Tests [N pass/N fail] | Lint [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **手动 QA 执行** — `unspecified-high`
  从干净状态启动。执行 Task 1-7 的 ALL QA Scenarios。测试跨任务集成（repair 后 regenerate，alias 扩展后 interactive 查询等）。测试边界：空 chapter 参数、无效 fund-code、缺失 work-dir。保存 evidence 到 `.sisyphus/evidence/final-qa/`。
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **范围忠实度检查** — `deep`
  逐任务核对：对比 "What to do" 与实际 diff。验证 1:1——计划中的每项都实现了，没有超出计划的变更。检查 "Must NOT do" 合规。检测跨任务污染（Task N 修改了 Task M 的文件）。标记未经规划的变更。
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `refactor(phase7.2): remove routing context pre-fetch, unify to LLM tool-calling path` — chat_service.py, extraction.py
- **2**: `feat(phase7.2): expand routing alias coverage` — extraction.py, test_extraction.py
- **3**: `feat(phase7.2): add Rich table formatting for interactive mode` — main.py
- **4**: `feat(phase7.2): add FIX_SCENE_CONFIG + scenes/fix.md` — scene_config.py, prompts/scenes/fix.md, chapter_generator.py
- **5**: `feat(phase7.2): add CLI repair subcommand, activate REPAIR_SCENE_CONFIG` — main.py, test_cli.py
- **4b**: `feat(phase7.2): add CLI fix subcommand for placeholder repair` — main.py, test_cli.py
- **6+7**: `feat(phase7.2): add CLI regenerate + auto-select repair strategy` — main.py, audit_pipeline.py, test_cli.py, test_audit_pipeline.py
- **8**: `feat(phase7.2): add /history command, follow-up suggestions, interactive startup tips` — main.py
- **9**: `feat(phase7.2): wire compaction.md prompt into ChatService` — chat_service.py
- **10**: `test(phase7.2): add end-to-end smoke tests` — test_cli.py, test_cli_interactive.py

---

## Success Criteria

### Verification Commands
```bash
# Phase 7 回归（确保不回退）
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py -v --tb=short

# Phase 7.2 新增测试
uv run pytest tests/fund/cli/test_cli.py -k "repair or regenerate" -v --tb=short
uv run pytest tests/fund/cli/test_cli.py -k "fix" -v --tb=short
uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short
uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short
uv run pytest tests/fund/service/test_scene_config.py -k "fix" -v --tb=short
uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short

# 全量
uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ -v --tb=short
```

### Final Checklist
- [ ] `_DIRECT_KEYWORDS` 和 routing context 预取代码完全删除
- [ ] interactive/ask 所有查询走 LLM 工具调用路径
- [ ] "基金经理是谁" 返回非空回答
- [ ] `repair --chapter 3` 只修 Ch3
- [ ] `regenerate --chapter 3` 只重写 Ch3，审计反馈注入
- [ ] `fix` 占位符格式对齐 Dayu 规范
- [ ] Rich Table 在 interactive 中正确渲染
- [ ] `fix --chapter 3` 只修复 Ch3，exit code 0
- [ ] `/history` 命令可用
- [ ] compaction.md 接入 EpisodeSummary 触发
- [ ] 审计分数驱动的策略自动选择正确
- [ ] Phase 7 全量回归无回退
- [ ] 所有 Guardrails 合规

