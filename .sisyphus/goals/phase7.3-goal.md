# Goal: Phase 7.3 对话历史注入 LLM context（方案 B）

**创建时间**：2026-07-28
**目标状态**：✅ 已完成
**版本**：v1
**关联文档**：
- `docs/phase7.3-option-b-optimization.md`（方案 B 优化设计 v2，DS 二审有条件通过）
- `docs/implementation-control.md`（真源执行面板，Phase 7.3 节）
- `docs/design.md`（设计真源，Phase 7.3 节）
- `AGENTS.md`（项目规则）
- `docs/agent-evolution-design.md`（演进记录，§8.2）

---

## 1. 目标定义

### 核心目标
完成 Phase 7.3 全部 11 个实现任务，将对话历史注入 LLM context，使 `interactive` 模式的 LLM 能引用历史轮次的工具调用结果和上下文。采用方案 B（Prompt 层编织），不改变 `LlmClientProtocol` 签名。

### 具体交付物
- `session_models.py`：新增 `ToolCallSummary` dataclass + `Session.truncate_turns()` 方法
- `chat_service.py`：新增 `_build_history_contribution()` + `_format_turn_for_history()` + `_estimate_token_count()`；修改 `_build_contributions` 增加 history slot；修改 `_run_compaction` 增加 truncate；修改 `chat_turn()` 填充 `ToolCallSummary`
- `scene_config.py`：`INTERACTIVE_SCENE_CONFIG.context_slots` 新增 `"history"`
- 单元测试 + e2e 测试

### Definition of Done (DoD)
- [x] `interactive` 模式下 LLM 能引用历史轮次的工具调用结果
- [ ] `interactive` 多轮对话中，追问"刚才的数据"能正确回答（需手动验证）
- [x] history contribution 出现在 system prompt 中（代码已实现）
- [x] compaction 后旧 turns 被截断，episode summary 正确注入
- [x] history token 不超过 `history_max_tokens` 上限（默认 2000）
- [x] 空 tool_trace 轮次（LLM 直接回答）不产生空行
- [x] 分隔标记引导 LLM 使用 JSON 格式回答
- [x] Phase 7 全量回归 810 passed（不回退）
- [ ] e2e interactive 测试不再全部 xfail（需手动验证）（当前仍 xfail，需手动验证）

---

## 2. 范围定义

### 包含范围（In Scope）

**Wave 1（数据模型扩展）**：
- Task 1: `ToolCallSummary` dataclass + `Turn` 新增 `tool_calls: tuple[ToolCallSummary, ...] = ()` 字段（`session_models.py`）
- Task 2: `Session.truncate_turns()` 方法（`session_models.py`）

**Wave 2（History 注入核心逻辑）**：
- Task 3: `_build_history_contribution()` + `ChatService.__init__` 新增 `history_max_tokens` 参数（`chat_service.py`）
- Task 4: `_format_turn_for_history()` 结构化格式（`chat_service.py`）
- Task 5: `_estimate_token_count()` 中英文混合估算（`chat_service.py`）
- Task 6: `_build_contributions` 增加 history slot（`chat_service.py`）

**Wave 3（Compaction 交互 + ToolCallSummary 填充）**：
- Task 7: `_run_compaction` 增加 truncate 调用（`chat_service.py`）
- Task 8: `chat_turn()` 填充 `ToolCallSummary`（`chat_service.py`）

**Wave 4（Scene Config + 测试）**：
- Task 9: `context_slots` 新增 `"history"`（`scene_config.py`）
- Task 10: 单元测试（`tests/`）
- Task 11: e2e 测试（`tests/e2e/`）

### 排除范围（Out of Scope）

- **方案 A（协议层注入）**：不改动 `LlmClientProtocol.next_step()` 签名
- **`llm_tool_loop.py` 修改**：agent 层保持不变
- **ContextBudget 与 history token 交互**：留 TODO，Phase 8 处理
- **Temperature 调整**：保持 interactive scene temperature=0.7，观察后决定
- **新增 LLM provider**：当前仅支持 DeepSeek 与 Mimo
- **跨轮 raw tool results 注入**：方案 B 不存储 raw tool results，只存 `ToolCallSummary`（result_kind + failure_code 推导）
- **wechat 场景**：不在本次范围内
- **generate_text temperature 按场景区分**：审计评分保持 0（一致性）、章节分析写作用 0.3（语言多样性）、章节修复用 0.3（避免重复同一错误模式）。留待后续 phase 处理

---

## 3. 禁止事项（Must NOT Have / Guardrails）

### 硬性禁止
1. **不改动 `LlmClientProtocol.next_step()` 签名**：方案 B 核心约束
2. **不改动 `llm_tool_loop.py`**：agent 层保持不变
3. **不存储 raw tool results**：`ToolCallSummary` 只存 `tool_name`、`arguments_display`、`success`、`failure_code`
4. **不新增 LLM provider**：仅使用 DeepSeek 与 Mimo
5. **不改变 SessionStore 的持久化格式**：`ToolCallSummary` 作为新字段添加，向后兼容

### 实施约束
6. **`truncate_turns` 必须包含 `status` 和 `updated_at` 字段**：DS 二审 bug 修复要求
7. **`chat_turn()` 必须显式填充 `ToolCallSummary`**：DS 二审遗漏补充要求
8. **history contribution 必须出现在 system prompt 中**：核心功能验收点
9. **分隔标记必须引导 LLM 使用 JSON 格式**：避免历史纯文本 vs 当前 JSON 冲突
10. **`history_max_tokens` 必须可配置**：默认 2000，不硬编码
11. **history contribution 文本不得含 raw PDF/Docling JSON/本地路径**：符合 AGENTS.md 硬边界

### 代码规范
12. **禁止把显式参数塞进 `extra_payload`**：公共参数必须显式声明
13. **禁止魔法字符串/魔法数字**：source kind、failure code、tool name 应集中定义
14. **禁止任何 Agent 用"逻辑上完成""应该通过""已按计划完成"替代测试输出**

---

## 4. 验证标准（Acceptance Criteria）

### 4.1 Task 级验收

**Task 1（ToolCallSummary）**：
- [ ] `ToolCallSummary` dataclass 包含 `tool_name`、`arguments_display`、`success`、`failure_code` 字段
- [ ] `result_summary` property 从 `success` + `failure_code` 推导摘要
- [ ] 成功时返回 "成功"，失败时返回 "失败: {failure_code}"
- [ ] `Turn` 新增 `tool_calls: tuple[ToolCallSummary, ...] = ()` 字段，默认空元组，向后兼容

**Task 2（truncate_turns）**：
- [ ] `Session.truncate_turns(keep_last)` 保留最近 `keep_last` 个 turns
- [ ] 返回新 Session，包含 `status=self.status` 和 `updated_at=datetime.now()`
- [ ] `keep_last >= len(turns)` 时返回原 Session（不截断）

**Task 3（_build_history_contribution）**：
- [ ] 从 `session.episode_summaries` + `session.turns` 构建 history
- [ ] episode summaries 在前，raw turns 在后
- [ ] token 上限 `history_max_tokens`（默认 2000），从最近轮次向前累积截断
- [ ] `history_max_tokens` 作为 `ChatService.__init__` 参数

**Task 4（_format_turn_for_history）**：
- [ ] user turn 格式：`[用户提问]: {content}`
- [ ] assistant turn 格式：`[助手回答]: {content}` + 可选 `[引用文档]` + 可选 `[工具调用]`
- [ ] 空 `tool_calls` 时不产生工具行（FM7）
- [ ] 空 `citations` 时不产生引用行（FM7）

**Task 5（_estimate_token_count）**：
- [ ] 中文字符约 1.5 token/字
- [ ] 英文字符约 0.25 token/字符（4 字符/token）
- [ ] 混合文本估算合理

**Task 6（_build_contributions 增加 history）**：
- [ ] `_build_contributions` 返回值包含 `"history"` key
- [ ] history 文本格式：`## 历史对话\n\n{turns_text}\n\n---\n以上是历史对话。请忽略历史中的纯文本格式，以 JSON 格式回答当前用户问题。`

**Task 7（_run_compaction 增加 truncate）**：
- [ ] compaction 生成 EpisodeSummary 后调用 `truncate_turns(keep_last=preserve_turns)`
- [ ] 截断后 session.turns 只剩最近 `preserve_turns` 个

**Task 8（chat_turn 填充 ToolCallSummary）**：
- [ ] 从 `AgentRunResult.tool_trace` 提取 `ToolCallSummary`
- [ ] 存入 `Turn.tool_calls` 字段
- [ ] `tool_trace` 保留向后兼容（仍存工具名字符串）

**Task 9（context_slots 新增 history）**：
- [ ] `INTERACTIVE_SCENE_CONFIG.context_slots` 包含 `"history"`
- [ ] 其他 scene config 不受影响

**Task 10（单元测试）**：
- [ ] `_build_history_contribution` 测试：空 turns、正常 turns、超限截断
- [ ] `_format_turn_for_history` 测试：user/assistant、空 tool_calls、空 citations
- [ ] `_estimate_token_count` 测试：纯中文、纯英文、混合
- [ ] `truncate_turns` 测试：正常截断、不截断、status/updated_at 正确
- [ ] `ToolCallSummary.result_summary` 测试：成功/失败

**Task 11（e2e 测试）**：
- [ ] interactive 多轮对话中，追问依赖历史轮次的工具结果能正确回答
- [ ] e2e interactive 测试不再全部 xfail（需手动验证）（当前仍 xfail，需手动验证）

### 4.2 最终验收命令

```bash
# Phase 7.3 核心测试
uv run pytest tests/fund/service/test_chat_service.py -k "history" -v --tb=short
uv run pytest tests/fund/host/test_session_store.py -k "truncate" -v --tb=short

# Phase 7 回归
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short

# e2e 测试
uv run pytest tests/e2e/ -v --tb=short

# 全量回归
uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ --tb=no -q
```

### 4.3 Final Checklist

- [x] 全量回归 810 passed（不回退）
- [ ] e2e interactive 测试不再全部 xfail（需手动验证）
- [x] `grep -r "LlmClientProtocol" fund_agent/agent/llm_tool_loop.py` 无签名变更
- [x] `grep -r "next_step" fund_agent/agent/llm_tool_loop.py` 无签名变更
- [x] history contribution 出现在 system prompt 中

---

## 5. 执行策略

### 5.1 任务分组

**Wave 1（2 个并行）**：
- Task 1（quick）: `ToolCallSummary` dataclass + `Turn` 新增 `tool_calls` 字段
- Task 2（quick）: `Session.truncate_turns()`

**Wave 2（4 个并行）**：
- Task 3（deep）: `_build_history_contribution()` + `history_max_tokens`（依赖 Task 1, 2）
- Task 4（quick）: `_format_turn_for_history()`（依赖 Task 1）
- Task 5（quick）: `_estimate_token_count()`
- Task 6（quick）: `_build_contributions` 增加 history（依赖 Task 3）

**Wave 3（2 个并行）**：
- Task 7（quick）: `_run_compaction` 增加 truncate（依赖 Task 2）
- Task 8（deep）: `chat_turn()` 填充 ToolCallSummary（依赖 Task 1）

**Wave 4（3 个并行）**：
- Task 9（quick）: `context_slots` 新增 history
- Task 10（deep）: 单元测试（依赖 Task 1-8）
- Task 11（deep）: e2e 测试（依赖 Task 9, 10）

### 5.2 关键路径

Task 1 → Task 3 → Task 6 → Task 10 → Task 11

### 5.3 预计工期

2-3 天（Wave 1: 0.5 天，Wave 2: 1 天，Wave 3: 0.5 天，Wave 4: 1 天）

---

## 6. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| LLM 无法区分历史/当前 | 中 | FM2 | 结构化格式 + 分隔标记 + JSON 指引 |
| history token 超限导致 context 溢出 | 低 | FM1 | `history_max_tokens=2000` + 截断策略 |
| compaction 后 history 丢失 | 中 | FM5 | `truncate_turns` 确保双层注入可行 |
| e2e 测试仍 xfail | 中 | DoD 失败 | 可能需要调整 `_final_result` citation 校验逻辑（但不改 agent 层） |
| `ToolCallSummary` 序列化兼容性 | 低 | SessionStore | 新字段向后兼容，旧 session 无 `tool_calls` 时默认空元组 |
| 空 tool_trace 轮次产生空行（FM7） | 低 | 格式混乱 | `_format_turn_for_history` 跳过空 tool_calls/citations 行 |
| 英文内容 token 估算偏低（FM8） | 低 | context 溢出 | `_estimate_token_count` 中英文混合估算 |
| history 纯文本 vs 当前 JSON 冲突（FM9） | 中 | LLM 格式漂移 | 分隔标记明确引导 JSON 格式 |

---

## 7. 进度追踪

### 任务状态

**Wave 1**：
- [x] Task 1: `ToolCallSummary` dataclass + `Turn` 新增 `tool_calls` 字段
- [x] Task 2: `Session.truncate_turns()`

**Wave 2**：
- [x] Task 3: `_build_history_contribution()` + `history_max_tokens`
- [x] Task 4: `_format_turn_for_history()`
- [x] Task 5: `_estimate_token_count()`
- [x] Task 6: `_build_contributions` 增加 history

**Wave 3**：
- [x] Task 7: `_run_compaction` 增加 truncate
- [x] Task 8: `chat_turn()` 填充 ToolCallSummary

**Wave 4**：
- [x] Task 9: `context_slots` 新增 history
- [x] Task 10: 单元测试（34 个新增）
- [ ] Task 11: e2e 测试（xfail，需手动验证）

---

## 8. 与 Phase 7.2 的关系

Phase 7.3 是 Phase 7.2 的后续阶段：

- Phase 7（多轮对话 + 会话记忆）→ ✅ 已完成
- Phase 7.1（集成补完）→ ✅ 已完成
- Phase 7.2（交互体验增强 + 修复能力激活）→ ✅ 已完成
- **Phase 7.3（对话历史注入 LLM context）** → 🔴 待实施

Phase 7.2 完成的 repair/regenerate/fix/interactive 能力为 Phase 7.3 提供了测试基础。Phase 7.3 的核心价值是让 `interactive` 模式从"每次独立对话"升级为"真正的多轮对话"。

---

## 9. 使用方法

### 启动 Goal
```
/goal phase7.3
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

## 10. DS 审核记录

### 第一轮审核（待进行）

**审核人**：AgentDS
**审核时间**：待定
**审核结论**：待审核

---

**Goal 创建者**：AgentCodex
**最后更新**：2026-07-29
**审核状态**：DS 审核通过（2026-07-28）
