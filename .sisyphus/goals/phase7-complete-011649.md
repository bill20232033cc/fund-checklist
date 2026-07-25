# Goal Command（可直接发送）

发送以下命令即可开启本次任务：

```
/goal .sisyphus/goals/phase7-complete-011649.md
```

---

## Goal

- goal_id: `phase7-complete-011649`
- 目标：完成 Phase 7 实施，并通过基金代码 `011649` 的端到端验收（含真实 LLM 接入）。
- 数据口径：报告生成、审计、ask、interactive 统一基于最近5年年报（2021-2025）。
- 日期：2026-07-25

---

## Objective（明确目标）

1. 完成 Phase 7 全部 17 个 Slice（`7X + 7A-7P`）实现与测试。
2. 基于基金代码 `011649` 完成 5 年年报（2021-2025）端到端验证。
3. 接入真实 LLM（opt-in）完成 `interactive` 与 `ask` 链路验证（均基于5年口径）。
4. 生成基金分析报告（覆盖最近5年年报数据），并进入三层审计（程序+LLM+复核）闭环。
5. 最终输出可复现的验证结果与 evidence。

---

## Scope（范围）

- 必须覆盖：
  - `interactive --fund-code 011649` 全流程（5年年报上下文）
  - 会话创建、上下文传递、会话恢复（`--label`）
  - 上下文治理（Context Budget / WorkingMemory overflow）
  - Episode Summary + PinnedState patch
  - ToolResult envelope + ToolExecutionContext
  - ChatTurnContract、SceneModelSpec、allowed_tools
  - 全量回归（不得回退 ask / read 等既有命令）
- 必须产出：
  - 基金分析报告（覆盖 011649 最近5年年报，2021-2025）
  - 三层审计结果（基于5年口径报告，程序+LLM+复核）
  - evidence 文件（命令、日志、关键输出）

---

## 数据口径说明

- **统一口径**：报告生成、三层审计、ask 问答、interactive 交互，均基于最近5年年报（2021-2025）数据。
- `generate` 命令覆盖5年，而非单一年度。
- `audit` / `deep-audit` 对5年报告执行审计。
- `ask` 在多文档模式下可引用5年内任意年度数据。
- `interactive` 默认加载5年年报上下文，支持 `/document 20XX` 在年度间切换。

---

## Prohibitions（禁止事项）

- 禁止输出"买入/卖出"等投资建议。
- 禁止预测未来收益或市场走势。
- 禁止在默认测试中联网或读取真实 API key（live 验收必须显式 opt-in）。
- 禁止用 fake fixture 替代 production path 来证明验收通过。
- 禁止仅以 Service/ToolService 层测试作为最终验收。
- 禁止扩大 Phase 7 范围（不引入未裁决能力）。

---

## Acceptance Criteria（验收标准）

### A. 功能验收（必须全过）
1. `fund-checklist interactive --fund-code 011649` 可启动，加载5年年报上下文。
2. 可跨年度完成至少 3 轮上下文问答（如：基金经理/任期/规模/跨年业绩对比）。
3. `/document 2023` 切换后，后续回答基于2023 年年报上下文，并引用 2023 document_id；`/document 2021` 可切回早年数据。
4. `/save` 可导出会话文件；`exit` 后 session 落盘；`--label` 可恢复。
5. 输入"建议买入该基金"被拦截（投资建议检测生效）。

### B. 真实 LLM 验收（opt-in）
6. 在显式 opt-in 条件下，`ask`（多文档模式）与 `interactive`（5年上下文）可完成真实 LLM 调用。
7. live smoke 不得在默认 `pytest` 中执行。

### C. 报告与审计（必须闭环，5年口径）
8. 生成 011649 基金分析报告，覆盖最近5年年报（2021-2025）。
9. 对5年报告执行三层审计，并保留审计结果。
10. 审计结果纳入 evidence，不做强制分数约束（除非你额外设定阈值）。

### D. 回归与稳定性
11. `uv run pytest tests/fund/ -v --tb=short` 全部通过。
12. Phase 5/6 关键能力无回退（ask/read/generate/audit）。

---

## Verification Commands（验证命令）

### 1) 离线核心测试（默认，不联网）
```bash
uv run pytest tests/fund/cli/test_cli_interactive.py \
  tests/fund/service/test_chat_service.py \
  tests/fund/host/test_session_store.py \
  tests/fund/agent/test_context_budget.py \
  tests/fund/service/test_scene_config.py \
  tests/fund/service/test_prompt_contributions.py \
  tests/fund/service/test_prompt_composer_upgrade.py \
  tests/fund/agent/test_tool_result.py \
  tests/fund/agent/test_tool_context.py \
  -v --tb=short
```

### 2) 全量回归
```bash
uv run pytest tests/fund/ -v --tb=short
```
### 3) 真实 LLM 端到端（opt-in，5年口径）
```bash
# ask 多文档模式（引用5年内年报）
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 \
uv run fund-checklist ask "该基金最近5年业绩如何变化？" \
  --document-id <011649-2025-annual_report-xxx> \
  --document-id <011649-2024-annual_report-xxx> \
  --document-id <011649-2023-annual_report-xxx> \
  --document-id <011649-2022-annual_report-xxx> \
  --document-id <011649-2021-annual_report-xxx>
```

```bash
# interactive 5年上下文
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 \
uv run fund-checklist interactive --fund-code 011649
```

### 4) 报告生成（5年口径）
```bash
uv run fund-checklist generate --fund-code 011649 --fund-name "易方达逆向投资混合" --format markdown --llm --work-dir .fund_e2e_011649
```

### 5) 三层审计（5年口径）
```bash
uv run fund-checklist audit --fund-code 011649 --work-dir .fund_e2e_011649
uv run fund-checklist deep-audit --fund-code 011649 --work-dir .fund_e2e_011649
```
> `--document-id` 实际值以导入后 `document_id` 为准；goal 验收以真实执行输出为准。

---

## Final Gate（最终放行条件）

满足以下全部，`goal` 才算 PASS：

1. 离线核心测试 PASS
2. 全量回归 PASS
3. `interactive --fund-code 011649` 端到端通过（5年上下文）
4. 真实 LLM（opt-in）端到端通过
5. 011649 基金分析报告生成成功（覆盖2021-2025）
6. 三层审计执行完成且 evidence 落盘
7. 投资建议拦截验证通过

---

## Evidence（证据落盘）

所有 evidence 统一落到：
```text
.sisyphus/evidence/phase7-goal-011649/
```

建议包含：
- `offline-tests.txt`
- `regression.txt`
- `live-ask.txt`
- `live-interactive.txt`
- `generate.txt`
- `audit.txt`
- `report-path.txt`
- `final-gate.txt`

---

## Status（状态流转）

- `pending` -> `in_progress` -> `blocked`（可选）-> `done`
- 状态更新必须与 evidence 文件同步。

---

## 一句话执行说明

直接发送：
```
/goal .sisyphus/goals/phase7-complete-011649.md
```
即按本文档目标、范围、禁止项和验证标准执行 Phase 7 完成任务。数据口径统一为最近5年年报（2021-2025）。
