# Goal Command（可直接发送）

发送以下命令即可开启本次任务：

```
/goal .sisyphus/goals/phase7-complete-011649.md
```

---

## Goal

- goal_id: `phase7-complete-011649`
- 目标：完成 Phase 7 实施，并通过基金代码 `011649` 的端到端验收（含真实 LLM 接入）。
- 日期：2026-07-25

---

## Objective（明确目标）

1. 完成 Phase 7 全部 17 个 Slice（`7X + 7A-7P`）实现与测试。
2. 基于基金代码 `011649` 完成 5 年年报（2021-2025）端到端验证。
3. 接入真实 LLM（opt-in）完成 `interactive` 与 `ask` 链路验证。
4. 生成基金分析报告，并进入三层审计（程序+LLM+复核）闭环。
5. 最终输出可复现的验证结果与 evidence。

---

## Scope（范围）

- 必须覆盖：
  - `interactive --fund-code 011649` 全流程
  - 会话创建、上下文传递、会话恢复（`--label`）
  - 上下文治理（Context Budget / WorkingMemory overflow）
  - Episode Summary + PinnedState patch
  - ToolResult envelope + ToolExecutionContext
  - ChatTurnContract、SceneModelSpec、allowed_tools
  - 全量回归（不得回退 ask / read 等既有命令）
- 必须产出：
  - 基金分析报告（至少覆盖 011649 最新年报）
  - 三层审计结果（程序+LLM+复核）
  - evidence 文件（命令、日志、关键输出）

---

## Prohibitions（禁止事项）

- 禁止输出“买入/卖出”等投资建议。
- 禁止预测未来收益或市场走势。
- 禁止在默认测试中联网或读取真实 API key（live 验收必须显式 opt-in）。
- 禁止用 fake fixture 替代 production path 来证明验收通过。
- 禁止仅以 Service/ToolService 层测试作为最终验收。
- 禁止扩大 Phase 7 范围（不引入未裁决能力）。

---

## Acceptance Criteria（验收标准）

### A. 功能验收（必须全过）
1. `fund-checklist interactive --fund-code 011649` 可启动。
2. 选择 2025 后可完成至少 3 轮上下文问答（基金经理/任期/规模）。
3. `/document 2023` 切换后，后续回答基于2023 年年报上下文，并引用 2023 document_id。
4. `/save` 可导出会话文件；`exit` 后 session 落盘；`--label` 可恢复。
5. 输入“建议买入该基金”被拦截（投资建议检测生效）。

### B. 真实 LLM 验收（opt-in）
6. 在显式 opt-in 条件下，`ask` 与 `interactive` 可完成真实 LLM 调用。
7. live smoke 不得在默认 `pytest` 中执行。

### C. 报告与审计（必须闭环）
8. 生成 011649 基金分析报告（至少最新年度）。
9. 对报告执行三层审计，并保留审计结果。
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
### 3) 真实 LLM 端到端（opt-in）
```bash
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 \
uv run fund-checklist ask "基金经理是谁？" \
  --document-id <011649 最新年报 document_id>
```

```bash
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 \
uv run fund-checklist interactive --fund-code 011649
```

### 4) 报告生成
```bash
uv run fund-checklist generate --fund-code 011649 --fund-name "易方达逆向投资混合" --year 2025 --format markdown --llm --work-dir .fund_e2e_011649
```

### 5) 三层审计
```bash
uv run fund-checklist audit --fund-code 011649 --year 2025 --work-dir .fund_e2e_011649
uv run fund-checklist deep-audit --fund-code 011649 --year 2025 --work-dir .fund_e2e_011649
```
> `...` 请按你当前 CLI 参数补全实际命令参数；goal 验收以真实执行输出为准。

---

## Final Gate（最终放行条件）

满足以下全部，`goal` 才算 PASS：

1. 离线核心测试 PASS
2. 全量回归 PASS
3. `interactive --fund-code 011649` 端到端通过
4. 真实 LLM（opt-in）端到端通过
5. 011649 基金分析报告生成成功
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
即按本文档目标、范围、禁止项和验证标准执行 Phase 7 完成任务。
