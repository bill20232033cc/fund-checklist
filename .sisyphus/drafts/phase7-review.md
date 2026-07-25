# Phase 7 计划审核草案

> 审核时间：2026-07-25
> 计划文件：`.sisyphus/goals/phase7-interactive-011649.md`
> 状态：审核中

---

## 调研发现

| 维度 | 状态 |
|------|------|
| Phase 5 实施进度 | ✅ 19A-19E 代码已完成，仅 19F e2e smoke 待完成 |
| 现有 session/memory 基础设施 | ✅ 全部需从头构建：无 Session/Turn 模型、无存储、无 context budget |
| 011649 基金数据可用性 | ✅ 5年PDF齐全，.fund_e2e_011649/ 已有完整pipeline产物 |

---

## 初步发现

### 1. 治理门禁问题（CRITICAL）

**AGENTS.md 明确约束**：
- "多轮对话：无 interactive mode，无会话记忆" — 列为已知能力差距
- "ask 子命令已裁决通过（Phase 5，2026-07-24），streaming 已并入 Phase 5。interactive 模式尚未裁决"
- "新增 LLM 驱动的 CLI 用户入口必须另开裁决"

**agent-evolution-design.md**：
- Phase 7 标记为 "🔵 候选，未裁决"
- "当前文档不代表已批准实施"

**Phase 7 计划当前状态**：
- 位于 `.sisyphus/goals/` 而非 `.sisyphus/plans/`
- 标题带有 "待裁决确认" 标记
- 列举了 6 项必须裁决项

**结论**：Phase 7 处于 goal/proposal 阶段，尚未通过正式裁决门禁。这本身不是问题（计划文件承认了这一点），但需要确认裁决流程。

### 2. Phase 5 依赖链问题

Phase 7 计划显示：
- 7C（Host 多轮会话托管）依赖 7B
- 7B（Service 层 chat_turn）依赖 7A

但 agent-evolution-design.md 显示 Phase 7 依赖 Phase 5 的完成：
- [Phase6-A] Session 数据模型 → 依赖 [Phase5-B]
- 需要 `LlmToolLoopRunner` production readiness
- 需要 `ask_question` use case 已实现
- 需要 Host 层已支持 Agent 自主调用

**待确认**：Phase 5 Slice 19A-19F 当前实施状态。

### 3. 计划优点

1. **范围清晰**：5 个 slice（7A-7E），依赖关系明确
2. **裁决项结构化**：6 项裁决，每项给出 A/B/C 选项和推荐方案
3. **验证标准具体**：4 个功能验证项 + 端到端 CLI 命令
4. **风险缓解**：4 项风险及缓解措施
5. **Dayu 对标**：5 个能力维度的差距分析

### 4. 待确认问题

---

## 011649 数据现状（bg_d4316bc2 已返回）

- 5 年 PDF 齐全（2021-2025）
- `.fund_e2e_011649/` 工作目录已存在，含 Docling JSON、completed_reports.json、audit artifacts
- 无 `.fund_checklist_e2e_011649/`（计划中使用的目录名尚未创建）
- 无 Python 测试 fixture 引用 011649
- Phase 6 也有 011649 e2e 目标文件：`.sisyphus/goals/phase6-e2e-011649.md`

---

## 技术问题清单

### Q1: 会话 ID 生成策略
计划未指定 session_id 生成方式。UUID4？时间戳？label 映射？

### Q2: Turn 模型的 JSON 序列化
Turn 包含 `citations: tuple[Citation, ...]` 和 `tool_trace: tuple[ToolTraceEntry, ...]`，这些是复杂 dataclass。JSON 序列化方案是什么？
- 方案 A：自定义 encoder/decoder
- 方案 B：dataclasses.asdict() + 手动重建
- 方案 C：Pydantic 模型

### Q3: 投资建议检测集成点
计划要求"禁止跳过投资建议关键词检测"，但未指定在管道的哪个环节执行：
- Service 层 chat_turn 调用前？
- Host 层每次 turn 完成后？
- LLM 回答生成后？用户输入时？

### Q4: Pinned State 的文档切换
计划说 Pinned State 包含 document_id。交互式模式下用户能否切换文档？
- 如果支持切换：Pinned State 更新，旧 citations 如何处理？
- agent-evolution-design.md 提到："旧 citations 仍在 Turn 中保留但不作为新回答的引用源"

### Q5: 上下文预算的具体实现
计划说"按 token budget 截断"，但：
- Token 估算方式：tiktoken？字符估算（中文字数×2）？API usage 字段？
- budget 值：固定 128K？从模型配置读取？
- 3 轮强制保留 + budget 截断的精确算法？

### Q6: Label 冲突处理
`--label my-session` 如果标签已被另一个实例使用，行为是什么？
- 方案 A：报错拒绝
- 方案 B：覆盖旧会话
- 方案 C：追加到旧会话

### Q7: REPL 实现选型
计划未指定交互式 REPL 的实现方式：
- Python `input()` + readline？
- `prompt_toolkit`（支持语法高亮、自动补全）？
- 自定义 readline 集成？

### Q8: 测试策略
计划只给出了 CLI E2E 验证，缺少：
- 单元测试策略（TDD？tests-after？）
- Session/Turn 模型的单元测试
- Service chat_turn 的单元测试（fake/injected LLM）
- Host 会话托管的单元测试

### Q9: 与现有 ask 命令的关系
Phase 5 的 `ask` 命令是单次问答。Phase 7 的 `interactive` 是多轮对话。
两者的关系是什么？
- `interactive` 是否复用 `ask` 的底层 `LlmToolLoopRunner`？
- `interactive` 的每一轮是否等价于一次 `ask` 调用？
- 如果不复用，是否会有两套 LLM 调用路径？

### Q10: Phase 5 vs Phase 7 的上下文治理边界
agent-evolution-design.md 将"上下文治理"放在 Phase 8（独立 phase），但 Phase 7 计划明确说 "Phase 7 实现基础版（token budget 截断）"。这造成了职责重叠：
- Phase 7 的"基础版 token budget 截断"是否只是 Phase 7 的临时方案？
- Phase 8 完整上下文治理是否会替换 Phase 7 的基础版？
- 如果 Phase 8 未裁决前 Phase 7 就要做基础版，如何确保不造成技术债？

### Q11: 记忆模型的 Season 边界
Dayu 和 agent-evolution-design.md 都提到"单总池 raw turn 回放"概念，但 Phase 7 简化为"Pinned State + Recent Turns"两层。这里有个隐含问题：
- 交互式会话可能跨越多天（session resume）。一天的对话结束后，下次恢复时 Recent Turns 如何处理？
- 简化为 3 轮强制保留，意味着跨 session 只能记住 3 轮。这是用户可接受的吗？
- 是否需要区分"同一 session 内"和"跨 session 恢复"两种 recent turns 范围？
