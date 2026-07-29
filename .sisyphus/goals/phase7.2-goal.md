# Goal: Phase 7.2 交互体验增强 + 修复能力激活 + 场景扩展

**创建时间**：2026-07-27
**目标状态**：进行中
**关联文档**：
- `.sisyphus/plans/phase7.2-implementation.md`（实施计划）
- `docs/implementation-control.md`（真源执行面板）
- `AGENTS.md`（项目规则）

---

## 1. 目标定义

### 核心目标
完成 Phase 7.2 全部 10 个实现任务 + 2 个测试任务，推翻 Phase 7 routing context 预取，统一走 LLM 工具调用；激活已定义但未接线的 SceneConfig（regenerate/repair）；新建 fix 场景；增强交互体验。

### 具体交付物
- 删除 routing context 预取逻辑（~70 行）
- `repair --chapter` CLI 子命令（激活 REPAIR_SCENE_CONFIG）
- `regenerate --chapter` CLI 子命令（激活 REGENERATE_SCENE_CONFIG）
- `fix --chapter` CLI 子命令（新建 FIX_SCENE_CONFIG + scenes/fix.md）
- 扩展 `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 至少 5 个新 contract
- Rich Table 格式化输出（`--plain` 参数保留原始文本）
- `/history` 命令 + interactive 启动提示 + 追问建议
- 审计分数驱动的修复策略自动选择
- conversation_compaction prompt 接入

### Definition of Done (DoD)
- [ ] interactive/ask 所有查询走 LLM 工具调用路径（无 routing context 直返）
- [ ] `repair --chapter 0,1,2` 只修复指定章节，exit code 0
- [ ] `regenerate --chapter 3` 只重写指定章节，审计反馈注入 prompt
- [ ] `fix --chapter 3` 检测并补强占位符（Task 4b 负责 CLI）
- [ ] "基金经理是谁" 返回非空回答（LLM 自主搜索）
- [ ] interactive 表格数据以 Rich Table 显示
- [ ] `/history` 显示最近 10 轮对话摘要
- [ ] `compaction.md` prompt 接入 EpisodeSummary 触发逻辑
- [ ] Phase 7 全量回归 ≥153 passed（不回退）
- [ ] 新增测试 ≥20 passed

---

## 2. 范围定义

### 包含范围（In Scope）

**Wave 1（基础重构）**：
- Task 1: 删除 routing context 预取
- Task 2: 扩展路由 alias 覆盖
- Task 3: Rich 输出格式化

**Wave 2（CLI 子命令 + 场景）**：
- Task 4: 新建 FIX_SCENE_CONFIG + scenes/fix.md
- Task 4b: CLI fix 子命令（独立 `fix` 子命令，非 `repair --mode fix`）
- Task 5: CLI repair 子命令
- Task 6: CLI regenerate 子命令
- Task 7: 审计分数驱动策略自动选择
- Task 8: 多轮对话引导 + /history 命令
- Task 9: conversation_compaction 接入

**Wave 3（端到端验证）**：
- Task 10: 端到端 smoke 测试
- Task 11: 全量回归测试

**Final Verification Wave**：
- F1: 计划合规审计
- F2: 代码质量审查
- F3: 手动 QA 执行
- F4: 范围忠实度检查

### 排除范围（Out of Scope）

- **decision 场景**：Ch7 确定性信号评分已覆盖，LLM 版决策风险大于收益
- **新增 LLM provider**：当前仅支持 DeepSeek 与 Mimo
- **修改 generate 命令核心逻辑**：generate 保持现有行为
- **改变 SessionStore 持久化格式**：不破坏现有会话数据
- **wechat 场景**：不在 Dayu 借鉴范围内
- **投资建议相关内容**：fix 场景不补强投资建议

---

## 3. 禁止事项（Must NOT Have / Guardrails）

### 硬性禁止
1. **不新增 LLM provider**：仅使用 DeepSeek 与 Mimo
2. **不修改 generate 命令的核心逻辑**：generate 保持现有行为
3. **不改变 SessionStore 的持久化格式**：不破坏现有会话数据
4. **decision 场景不进入本次实施**：暂缓，需单独裁决
5. **fix 场景不产生投资建议**：仅处理结构化数据缺失

### 实施约束
6. **routing context 预取代码完全删除**：不留死代码
7. **repair/regenerate 不复用 generate 的全量重跑逻辑**：独立实现
8. **修复后保留 citation + evidence**：不丢失溯源能力
9. **fix 占位符格式对齐 Dayu 规范**：`【占位符】（缺口：... ｜ 需要：... ｜ 已检索：... ｜ 下一步：...）`
10. **`/history` 命令在 interactive REPL 中可用**：必须实现

### 代码规范
11. **禁止把显式参数塞进 `extra_payload`**：公共参数必须显式声明
12. **禁止魔法字符串/魔法数字**：source kind、failure code、tool name、locator kind 应集中定义
13. **禁止任何 Agent 用"逻辑上完成""应该通过""已按计划完成"替代测试输出**

---

## 4. 验证标准（Acceptance Criteria）

### 功能验证

**Task 1（删除 routing context 预取）**：
- [ ] `_DIRECT_KEYWORDS` 和 routing context 预取代码完全删除
- [ ] `grep -r "_DIRECT_KEYWORDS\|routing_context" fund_agent/` 无结果
- [ ] interactive/ask 所有查询走 LLM 工具调用路径

**Task 2（扩展路由 alias 覆盖）**：
- [ ] "基金经理是谁" 返回非空回答（LLM 自主搜索）
- [ ] `uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short` → PASS

**Task 3（Rich 输出格式化）**：
- [ ] interactive 表格数据以 Rich Table 显示
- [ ] `--plain` 参数保留原始文本

**Task 4（FIX_SCENE_CONFIG）**：
- [ ] `FIX_SCENE_CONFIG` 在 `scene_config.py` 中定义
- [ ] `prompts/scenes/fix.md` 存在，包含占位符检测和补强规则
- [ ] 修复后占位符格式符合规范

**Task 4b（CLI fix 子命令）**：
- [ ] `fix --chapter 3` 只修复 Ch3，exit code 0
- [ ] 输出包含修复统计（补强数量、保留数量）
- [ ] `uv run pytest tests/fund/cli/test_cli.py -k "fix" -v --tb=short` → PASS

**Task 5（CLI repair 子命令）**：
- [ ] `repair --chapter 0,1,2` 只修复指定章节，exit code 0
- [ ] `uv run pytest tests/fund/cli/test_cli.py -k "repair" -v --tb=short` → PASS

**Task 6（CLI regenerate 子命令）**：
- [ ] `regenerate --chapter 3` 只重写指定章节，审计反馈注入 prompt
- [ ] `uv run pytest tests/fund/cli/test_cli.py -k "regenerate" -v --tb=short` → PASS

**Task 7（审计分数驱动策略）**：
- [ ] 审计分数驱动的策略自动选择正确
- [ ] `uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short` → PASS

**Task 8（多轮对话引导）**：
- [ ] `/history` 显示最近 10 轮对话摘要
- [ ] interactive 启动时显示多轮对话提示
- [ ] 回答末尾添加追问建议

**Task 9（conversation_compaction）**：
- [ ] `compaction.md` prompt 接入 EpisodeSummary 触发逻辑
- [ ] `uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short` → PASS

**Task 10（端到端 smoke 测试）**：
- [ ] 端到端 smoke 测试通过

**Task 11（全量回归测试）**：
- [ ] Phase 7 全量回归 ≥153 passed（不回退）
- [ ] 新增测试 ≥20 passed

### 集成验证

**跨任务集成**：
- [ ] repair 后 regenerate 正常工作
- [ ] alias 扩展后 interactive 查询正常
- [ ] fix 后 audit 正常工作

**边界情况**：
- [ ] 空 chapter 参数 → 错误提示
- [ ] 无效 fund-code → 错误提示
- [ ] 缺失 work-dir → 错误提示

### 最终验证命令

```bash
# Phase 7 回归（确保不回退）
# Phase 7 回归（确保不回退）
uv run pytest tests/fund/cli/test_cli_interactive.py   tests/fund/service/test_chat_service.py   tests/fund/host/test_session_store.py   tests/fund/agent/test_context_budget.py   tests/fund/service/test_scene_config.py   tests/fund/service/test_prompt_contributions.py   tests/fund/service/test_prompt_composer_upgrade.py   tests/fund/agent/test_tool_result.py   tests/fund/agent/test_tool_context.py   -v --tb=short
# Phase 7.2 核心测试
uv run pytest tests/fund/cli/test_cli.py -k "repair or regenerate or fix" -v --tb=short
uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short
uv run pytest tests/fund/service/test_scene_config.py -k "fix" -v --tb=short
uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short
uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short

# 全量
uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ -v --tb=short
```

---

## 5. 执行策略

### 并行执行

**Wave 1（3 个并行）**：
- Task 1（quick）: 删除 routing context 预取
- Task 2（quick）: 扩展路由 alias 覆盖
- Task 3（quick）: Rich 输出格式化

**Wave 2（7 个并行）**：
- Task 4（deep）: FIX_SCENE_CONFIG + scenes/fix.md
- Task 4b（deep）: CLI fix 子命令（依赖 Task 4）
- Task 5（deep）: CLI repair 子命令
- Task 6（deep）: CLI regenerate 子命令
- Task 7（deep）: 审计分数驱动策略
- Task 8（quick）: 多轮对话引导 + /history
- Task 9（quick）: conversation_compaction

**Wave 3（2 个并行）**：
- Task 10（unspecified-high）: 端到端 smoke 测试
- Task 11（unspecified-high）: 全量回归测试

**Final Verification（4 个并行）**：
- F1（oracle）: 计划合规审计
- F2（unspecified-high）: 代码质量审查
- F3（unspecified-high）: 手动 QA 执行
- F4（deep）: 范围忠实度检查

### 关键路径
Task 1 → Task 5 → Task 10

### 预计工期
Medium（12-16 天）

---

## 6. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| Wave 2 并行 agent 同文件冲突 | 中 | merge 返工 | 明确 merge 策略，谁先合谁负责解决冲突 |
| fix 功能因 CLI 入口悬空无法端到端验证 | 高 | DoD 失败 | Task 4b 明确实现独立 `fix` 子命令 |
| Phase 7.1 与 Phase 7.2 范围重叠 | 中 | 浪费工时 | Phase 7.2 覆盖 Phase 7.1b 的 regenerate/repair/fix/conversation_compaction |
| Task 7 在没有 repair CLI 可用时无法端到端测试 | 中 | 测试 gap | Task 7 依赖 Task 5 完成 |

---

## 7. 进度追踪

### 任务状态

**Wave 1**：
- [ ] Task 1: 删除 routing context 预取
- [ ] Task 2: 扩展路由 alias 覆盖
- [ ] Task 3: Rich 输出格式化

**Wave 2**：
- [ ] Task 4: FIX_SCENE_CONFIG + scenes/fix.md
- [ ] Task 4b: CLI fix 子命令
- [ ] Task 5: CLI repair 子命令
- [ ] Task 6: CLI regenerate 子命令
- [ ] Task 7: 审计分数驱动策略
- [ ] Task 8: 多轮对话引导 + /history
- [ ] Task 9: conversation_compaction

**Wave 3**：
- [ ] Task 10: 端到端 smoke 测试
- [ ] Task 11: 全量回归测试

**Final Verification**：
- [ ] F1: 计划合规审计
- [ ] F2: 代码质量审查
- [ ] F3: 手动 QA 执行
- [ ] F4: 范围忠实度检查

### Commit Strategy

- **1**: `refactor(phase7.2): remove routing context pre-fetch` — chat_service.py, extraction.py
- **2**: `feat(phase7.2): expand routing alias coverage` — extraction.py, test_extraction.py
- **3**: `feat(phase7.2): add Rich table formatting` — main.py
- **4**: `feat(phase7.2): add FIX_SCENE_CONFIG + scenes/fix.md` — scene_config.py, prompts/scenes/fix.md, chapter_generator.py
- **4b**: `feat(phase7.2): add CLI fix subcommand` — main.py, test_cli.py
- **5**: `feat(phase7.2): add CLI repair subcommand` — main.py, test_cli.py
- **6+7**: `feat(phase7.2): add CLI regenerate + auto-select repair strategy` — main.py, audit_pipeline.py, test_cli.py, test_audit_pipeline.py
- **8**: `feat(phase7.2): add /history command + follow-up suggestions` — main.py
- **9**: `feat(phase7.2): wire compaction.md prompt into ChatService` — chat_service.py
- **10**: `test(phase7.2): add end-to-end smoke tests` — test_cli.py, test_cli_interactive.py

---

## 8. 与 Phase 7.1 的关系

Phase 7.2 覆盖了 Phase 7.1b 中的以下项：
- regenerate（整章重建）→ Task 6
- repair（局部修复）→ Task 5
- fix（占位符补强）→ Task 4 + Task 4b
- conversation_compaction（会话摘要压缩）→ Task 9

Phase 7.1a 的 4 项集成补完（ToolResult 信封、ContextBudget、force_answer、tool_calls_remaining）仍待独立实施。

---

## 9. 使用方法

### 启动 Goal
```
/goal phase7.2
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

---

## 10. DS 审核记录

### 第一轮审核（2026-07-27）

**审核人**：AgentDS
**审核时间**：2026-07-27
**审核结论**：ACCEPTED（修正后）

**审查维度**：
1. 目标定义：通过 — 完整覆盖 Phase 7.2 的所有 deliverables
2. 范围定义：通过 — In Scope / Out of Scope 清晰
3. 禁止事项：通过 — 与 AGENTS.md 的硬边界一致
4. 验证标准：通过 — 可执行、可量化、可验证
5. 执行策略：通过 — 并行分组合理，关键路径正确（T1→T5→T10）
6. 与 Phase 7.1 关系：通过 — 正确说明覆盖 Phase 7.1b 的 4/5 项（除 decision），Phase 7.1a 的 4 项标注为仍待独立实施

**改进建议**：
1. Section 4 最终验证命令：将 Phase 7 回归命令替换为 AGENTS.md 的完整 9 文件命令 ✅ 已修复
2. Section 5 Wave 2：标注 Task 4b 对 Task 4 的串行依赖 ✅ 已修复

**修复状态**：
- 建议 1：✅ 已修复（验证命令已更新为 AGENTS.md 的完整 9 文件命令）
- 建议 2：✅ 已修复（Wave 2 已标注 Task 4b 依赖 Task 4）

**最终结论**：ACCEPTED（所有建议已修复）

---

**文档维护者**：AgentCodex
**最后更新**：2026-07-27
**审核状态**：✅ DS 审核通过
