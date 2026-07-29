# Goal: Phase 7.1a 集成补完（4 项 P0）

**创建时间**：2026-07-27
**目标状态**：进行中
**关联文档**：
- `docs/implementation-control.md`（真源执行面板）
- `AGENTS.md`（项目规则）

---

## 1. 目标定义

### 核心目标
完成 Phase 7.1a 的 4 项 P0 集成补完任务，提升 LLM 工具调用链路的健壮性和可观测性。

### 具体交付物
1. **ToolResult 信封接入 runner**：包裹旧结果，统一工具输出格式
2. **ContextBudget 接入 runner**：预算检查 + 工具结果裁剪，防止 token 超限
3. **force_answer 降级**：max_steps 耗尽时 tool_results 直返，不报错
4. **tool_calls_remaining 信号注入**：每个 tool result 包含剩余调用次数

### Definition of Done (DoD)
- [ ] ToolResult 信封包裹所有旧工具结果
- [ ] ContextBudget 接入 runner，工具结果超过硬阈值时被裁剪
- [ ] force_answer 降级验证：max_steps 耗尽时不报错，返回已收集的 tool_results
- [ ] tool_calls_remaining 生效：每个 tool result 包含剩余调用次数
- [ ] 全量回归通过（≥250 tests）

---

## 2. 范围定义

### 包含范围（In Scope）

**Task 1: ToolResult 信封接入 runner**
- 在 `llm_tool_loop.py` 中接入 `ToolResult` 信封
- 包裹旧工具结果，统一输出格式
- 验证：所有工具输出都使用 `ToolResult` 格式

**Task 2: ContextBudget 接入 runner**
- 在 `llm_tool_loop.py` 中接入 `ContextBudget`
- 预算检查 + 工具结果裁剪
- 验证：工具结果超过硬阈值时被裁剪

**Task 3: force_answer 降级**
- 在 `llm_tool_loop.py` 中实现 `force_answer` 降级逻辑
- max_steps 耗尽时 tool_results 直返，不报错
- 验证：max_steps 耗尽时不报错，返回已收集的 tool_results

**Task 4: tool_calls_remaining 信号注入**
- 在 `llm_tool_loop.py` 中注入 `tool_calls_remaining` 信号
- 每个 tool result 包含剩余调用次数
- 验证：每个 tool result 包含剩余调用次数

### 排除范围（Out of Scope）

- **Dayu 场景借鉴**：Phase 7.1b 的 5 项任务（regenerate/repair/fix/decision/conversation_compaction）已在 Phase 7.2 完成
- **新增 LLM provider**：当前仅支持 DeepSeek 与 Mimo
- **修改 generate 命令核心逻辑**：generate 保持现有行为
- **改变 SessionStore 持久化格式**：不破坏现有会话数据

---

## 3. 禁止事项（Must NOT Have / Guardrails）

### 硬性禁止
1. **不新增 LLM provider**：仅使用 DeepSeek 与 Mimo
2. **不修改 generate 命令的核心逻辑**：generate 保持现有行为
3. **不改变 SessionStore 的持久化格式**：不破坏现有会话数据
4. **不引入新的外部依赖**：使用现有依赖

### 实施约束
5. **ToolResult 信封必须包裹所有旧工具结果**：不留遗漏
6. **ContextBudget 裁剪必须保留有效数据**：不丢失关键信息
7. **force_answer 降级必须返回已收集的 tool_results**：不丢弃已有数据
8. **tool_calls_remaining 信号必须准确**：不误导 LLM

### 代码规范
9. **禁止把显式参数塞进 `extra_payload`**：公共参数必须显式声明
10. **禁止魔法字符串/魔法数字**：source kind、failure code、tool name、locator kind 应集中定义
11. **禁止任何 Agent 用"逻辑上完成""应该通过""已按计划完成"替代测试输出**

---

## 4. 验证标准（Acceptance Criteria）

### 功能验证

**Task 1: ToolResult 信封接入 runner**
- [ ] `ToolResult` 信封包裹所有旧工具结果
- [ ] 工具输出格式统一为 `ToolResult`
- [ ] `uv run pytest tests/fund/agent/test_tool_result.py -v --tb=short` → PASS

**Task 2: ContextBudget 接入 runner**
- [ ] `ContextBudget` 接入 runner
- [ ] 工具结果超过硬阈值时被裁剪
- [ ] `uv run pytest tests/fund/agent/test_context_budget.py -v --tb=short` → PASS

**Task 3: force_answer 降级**
- [ ] max_steps 耗尽时不报错，返回已收集的 tool_results
- [ ] `uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "force_answer" -v --tb=short` → PASS

**Task 4: tool_calls_remaining 信号注入**
- [ ] 每个 tool result 包含剩余调用次数
- [ ] `uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "tool_calls_remaining" -v --tb=short` → PASS

### 集成验证

**全量回归**：
- [ ] Phase 7 全量回归 ≥250 tests（不回退）
- [ ] 新增测试 ≥10 passed

### 最终验证命令

```bash
# Phase 7.1a 核心测试
uv run pytest tests/fund/agent/test_tool_result.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_context_budget.py -v --tb=short

# Phase 7 全量回归
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short
```

---

## 5. 执行策略

### 串行执行

**Task 1: ToolResult 信封接入 runner**
- 修改 `fund_agent/agent/llm_tool_loop.py`
- 验证：`uv run pytest tests/fund/agent/test_tool_result.py -v --tb=short`

**Task 2: ContextBudget 接入 runner**
- 修改 `fund_agent/agent/llm_tool_loop.py`
- 验证：`uv run pytest tests/fund/agent/test_context_budget.py -v --tb=short`

**Task 3: force_answer 降级**
- 修改 `fund_agent/agent/llm_tool_loop.py`
- 验证：`uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "force_answer" -v --tb=short`

**Task 4: tool_calls_remaining 信号注入**
- 修改 `fund_agent/agent/llm_tool_loop.py`
- 验证：`uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "tool_calls_remaining" -v --tb=short`

### 关键路径
Task 1 → Task 2 → Task 3 → Task 4

### 预计工期
Short（3-5 天）

---

## 6. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| ToolResult 信封包裹遗漏 | 中 | 工具输出格式不统一 | 全量测试验证 |
| ContextBudget 裁剪丢失有效数据 | 中 | 关键信息丢失 | 保留有效数据，只裁剪冗余 |
| force_answer 降级丢弃已有数据 | 低 | 已收集的 tool_results 丢失 | 返回已收集的 tool_results |
| tool_calls_remaining 信号不准确 | 低 | 误导 LLM | 准确计算剩余调用次数 |

---

## 7. 进度追踪

### 任务状态

**Task 1: ToolResult 信封接入 runner**
- [ ] 修改 `fund_agent/agent/llm_tool_loop.py`
- [ ] 验证：`uv run pytest tests/fund/agent/test_tool_result.py -v --tb=short`

**Task 2: ContextBudget 接入 runner**
- [ ] 修改 `fund_agent/agent/llm_tool_loop.py`
- [ ] 验证：`uv run pytest tests/fund/agent/test_context_budget.py -v --tb=short`

**Task 3: force_answer 降级**
- [ ] 修改 `fund_agent/agent/llm_tool_loop.py`
- [ ] 验证：`uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "force_answer" -v --tb=short`

**Task 4: tool_calls_remaining 信号注入**
- [ ] 修改 `fund_agent/agent/llm_tool_loop.py`
- [ ] 验证：`uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "tool_calls_remaining" -v --tb=short`

### Commit Strategy

- **1**: `feat(phase7.1a): wire ToolResult envelope into runner` — llm_tool_loop.py
- **2**: `feat(phase7.1a): wire ContextBudget into runner` — llm_tool_loop.py
- **3**: `feat(phase7.1a): implement force_answer degradation` — llm_tool_loop.py
- **4**: `feat(phase7.1a): inject tool_calls_remaining signal` — llm_tool_loop.py

---

## 8. 与 Phase 7.2 的关系

Phase 7.2 已完成 Dayu 场景借鉴的 4 项任务（regenerate/repair/fix/conversation_compaction）。Phase 7.1a 专注于 LLM 工具调用链路的集成补完，提升健壮性和可观测性。

---

## 9. 使用方法

### 启动 Goal
```
/goal phase7.1a
```

### 查看进度
```
/goal status
```

### 完成任务
```
/goal complete <task-id>
```

### 完成 Goal
当所有任务完成且验证通过后：
```
/goal done
```

---

**Goal 创建者**：AgentCodex
**最后更新**：2026-07-27
**审核状态**：待 DS 审核
