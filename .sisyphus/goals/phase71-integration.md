# Goal Command（可直接发送）

发送以下命令即可开启本次任务：

```
/goal .sisyphus/goals/phase71-integration.md
```

---

## Goal

- goal_id: `phase71-integration`
- 目标：完成 Phase 7.1 集成补完 + Dayu 场景借鉴，使 Phase 7 已写代码在运行链路中生效，并引入 regenerate/repair/fix/decision/compaction 5 个新场景。
- 前置条件：Phase 7 ✅（2026-07-26 完成，201 tests pass，真实 LLM 验证通过）
- 设计来源：`docs/implementation-control.md` Phase 7.1 节 + `docs/dayu-scenes-research.md`
- 日期：2026-07-26

---

## Objective（明确目标）

1. 补完 Phase 7 集成缺口：ToolResult 信封接入 runner、ContextBudget 接入 runner、force_answer 降级、tool_calls_remaining 信号注入。
2. 借鉴 Dayu 场景（除 wechat）：regenerate（整章重建）、repair（局部修复）、fix（占位符补强）、decision（研究决策综合）、conversation_compaction（会话摘要压缩）。
3. 全量回归通过，Phase 5/6/7 关键能力无回退。
4. 最终输出可复现的验证结果与 evidence。

---

## Scope（范围）

### 7.1a 集成补完（4 项 P0）

- **ToolResult 信封接入 runner**：`_tool_result_from_output()` 包裹旧结果，新 ToolResult 包裹旧结果（不替换），`project_for_llm()` 注入 `tool_calls_remaining`。
- **ContextBudget 接入 runner**：`run()` 和 `run_stream()` 中 `record_usage()` + 工具结果裁剪检查。
- **force_answer 降级**：max_steps 耗尽时用已收集的 tool_results 直返（拼成回答），不报错。
- **tool_calls_remaining 信号**：每个 tool result 注入 `tool_calls_remaining: N`，LLM 每步可见剩余预算。

### 7.1b Dayu 场景借鉴（5 项）

- **regenerate**：基于审计反馈整章重建。执行契约：保留骨架，修复结构问题，不补占位符，不局部 patch。
- **repair**：审计小问题最小必要局部修复。执行契约：只改有问题的句子，不整章重写，不顺手优化。
- **fix**：占位符补强。执行契约：能补证则补证，不能补证则保留规范化占位符。
- **decision**：研究决策综合。执行契约：继续研究/暂缓/放弃判断，输出最小判断链 + 最大反证 + 最小验证计划。
- **conversation_compaction**：长对话上下文压缩。触发条件：≥10 轮 OR ≥60% token。

### 不在范围内

- `_SYSTEM_PROMPT` 迁移到 PromptComposer（裁决：保持现状）
- routing context 直返路径投资建议检测（裁决：不补）
- `wechat` 场景（裁决：不做）
- `prompt_toolkit` 依赖（裁决：推迟）
- `_detect_context_overflow`（裁决：推迟至 Phase 8）

---

## Prohibitions（禁止事项）

- 禁止输出"买入/卖出"等投资建议。
- 禁止预测未来收益或市场走势。
- 禁止在默认测试中联网或读取真实 API key（live 验收必须显式 opt-in）。
- 禁止用 fake fixture 替代 production path 来证明验收通过。
- 禁止修改 FundDocumentToolService、ToolCall、FinalAnswer 的已有接口。
- 禁止扩大 Phase 7.1 范围（不引入未裁决能力）。
- 禁止引入 dayu-agent、dayu.host、dayu.engine 作为生产 runtime。

---

## Acceptance Criteria（验收标准）

### A. 集成补完验收（必须全过）

1. **ToolResult 信封**：`_tool_result_from_output()` 返回新信封包裹旧结果，`project_for_llm()` 输出包含 `tool_calls_remaining` 字段。
2. **ContextBudget 接入**：`run()` 中 `record_usage()` 生效，工具结果超过硬阈值时被裁剪。
3. **force_answer 降级**：max_steps 耗尽时不报错，返回已收集的 tool_results 拼成的回答。
4. **tool_calls_remaining**：每个 tool result 的 `project_for_llm()` 输出包含 `tool_calls_remaining: N`（N 递减）。

### B. Dayu 场景验收（P1/P2）

5. **regenerate**：审计失败章节可单独重建，不重写其他章节。
6. **repair**：审计小问题可局部修复，不整章重写。
7. **fix**：数据缺失时保留结构化占位符，不跳过。
8. **decision**：基于前文章节输出继续研究/暂缓/放弃判断。
9. **conversation_compaction**：≥10 轮触发压缩，压缩后上下文不超限。

### C. 回归与稳定性

10. `uv run pytest tests/fund/ -v --tb=short` 全部通过（≥250 tests）。
11. Phase 5/6/7 关键能力无回退（由全量回归 ≥250 tests 保证，含 ask/read/generate/audit/interactive 相关测试）。

---

## Verification Commands（验证命令）

### 1) 集成补完核心测试
```bash
uv run pytest tests/fund/agent/test_tool_result.py \
  tests/fund/agent/test_llm_tool_loop.py \
  tests/fund/agent/test_context_budget.py \
  tests/fund/agent/test_llm_production_readiness.py \
  tests/fund/service/test_session_models.py \
  -v --tb=short
```

### 2) 全量回归
```bash
uv run pytest tests/fund/ -v --tb=short
```

### 3) force_answer 降级验证
```bash
# 构造 max_steps=1 的 runner，验证不报错而是返回 tool_results
uv run pytest tests/fund/agent/test_llm_tool_loop.py -k force_answer -v --tb=short
```

### 4) tool_calls_remaining 验证
```bash
# 验证 project_for_llm() 输出包含 tool_calls_remaining
uv run pytest tests/fund/agent/test_tool_result.py -k remaining -v --tb=short
```

### 5) 真实 LLM 验证（opt-in）
```bash
# interactive 路由上下文直返（已有验证）
printf '\n这只基金2025年管理费率是多少\nexit\n' | \
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 \
uv run fund-checklist interactive --fund-code 011649 --work-dir .fund_e2e_011649 --no-stream
```

---

## Final Gate（最终放行条件）

满足以下全部，`goal` 才算 PASS：

1. 集成补完 4 项 P0 全部实现且测试通过（含 force_answer 降级 + tool_calls_remaining 注入）
2. 全量回归 PASS（≥250 tests，Phase 5/6/7 无回退）
3. Dayu 场景至少 regenerate + repair 实现且测试通过（fix/decision/compaction 可推迟）

---

## Evidence（证据落盘）

所有 evidence 统一落到：
```text
.sisyphus/evidence/phase71-integration/
```

建议包含：
- `integration-tests.txt`（集成补完核心测试）
- `regression.txt`（全量回归）
- `force-answer.txt`（force_answer 降级验证）
- `tool-calls-remaining.txt`（tool_calls_remaining 验证）
- `live-llm.txt`（真实 LLM 验证，opt-in）
- `final-gate.txt`

---

## Status（状态流转）

- `pending` -> `in_progress` -> `blocked`（可选）-> `done`
- 状态更新必须与 evidence 文件同步。

---

## 一句话执行说明

直接发送：
```
/goal .sisyphus/goals/phase71-integration.md
```
即按本文档目标、范围、禁止项和验证标准执行 Phase 7.1 集成补完任务。优先完成 4 项 P0 集成补完，Dayu 场景按 P1/P2 优先级实施。
