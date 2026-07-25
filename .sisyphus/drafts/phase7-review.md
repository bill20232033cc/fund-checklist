# Phase 7 设计文档全面审核

> 审核时间：2026-07-25
> 审核范围：AGENTS.md / docs/design.md / docs/implementation-control.md / docs/agent-evolution-design.md / docs/architecture.md / docs/dayu-scenes-research.md / .sisyphus/plans/phase7-interactive.md
> 状态：审核中

---

## 一、裁决门禁 ✅ (Governance Gate — PASS)

| 检查项 | 状态 | 证据 |
|--------|------|------|
| AGENTS.md 声明 Phase 7 已裁决 | ✅ | L31: "interactive 模式已裁决通过（Phase 7，2026-07-25）" |
| AGENTS.md 含 Phase 7 验证命令 | ✅ | L130-133: Phase 7 验证命令 |
| implementation-control.md Phase 7 节 | ✅ | L2066-2160: 完整 Slice 列表 + Gate 1/2 ✅ |
| Phase 7 计划在 `.sisyphus/plans/` | ✅ | `.sisyphus/plans/phase7-interactive.md` (1364 行) |

**结论**：Phase 7 已通过正式裁决门禁，可进入实施。

---

## 二、发现的问题

### 🟡 P1 — 文档过期/不一致（需修复）

#### 2.1 agent-evolution-design.md 状态标记过期

**位置**：`docs/agent-evolution-design.md:178`
**问题**：仍标记为 `🔵 候选，未裁决`
**实际**：Phase 7 已于 2026-07-25 正式裁决
**影响**：误导开发者以为 Phase 7 尚未批准
**建议**：更新 §2 的状态标记为 `✅ 已裁决（2026-07-25）`，与 implementation-control.md 对齐

#### 2.2 architecture.md 过时

**位置**：`docs/architecture.md`
**问题**：最后更新 2026-06-28，只描述 MVP 阅读工具层，不反映当前「基金分析助手」阶段
**影响**：新加入的开发者可能被误导
**建议**：要么更新到当前阶段，要么在文件头明确标注 "本文档已冻结，当前架构真源见 docs/design.md"

#### 2.3 Phase 7 Plan 中 Slice 数量自相矛盾

**位置**：`.sisyphus/plans/phase7-interactive.md`
**问题**：
- TL;DR 声称 `16 Slice + 审计`
- Final Checklist 声称 `所有 15 个 Slice 实现完成`
- 实际 Slice 数量：7A-7P = 16 个
**建议**：统一为 16

### 🟡 P2 — 依赖关系不一致（需修复）

#### 2.4 Phase 7 Plan vs implementation-control.md 依赖声明冲突

| Slice | Plan 中的依赖 | implementation-control 中 | 谁对？ |
|-------|-------------|--------------------------|--------|
| 7B | Wave 1 并行，无依赖 | `依赖 7A` | **Plan 对** — 7B 只读 catalog，不需要 7A |
| 7C | Wave 1 并行，无依赖 | `依赖 7A` | **Plan 对** — 关键词独立 |
| 7D | Wave 1 并行，无依赖 | `依赖 7A` | **Plan 对** — token 追踪独立 |
| 7E | Wave 1 并行，无依赖 | `依赖 7A` | **Plan 对** — PromptComposer 升级独立 |

**根因**：implementation-control.md 的 Slice 列表中，7B-7E 的依赖栏填了 `依赖 7A`（可能是复制粘贴错误），而 Plan 中正确标注为 Wave 1 并行。

**建议**：修正 implementation-control.md 中 7B-7E 的依赖为 `无` 或直接删除依赖列

#### 2.5 7B 依赖标注错误

**位置**：`.sisyphus/plans/phase7-interactive.md` 中 7B 的 Parallelization
**问题**：`Blocks: 7F, 7H`
**应该**：`Blocks: 7G, 7I`（resolve_by_fund_code 被 chat_turn 和 CLI 使用）
**证据**：
- 7G (chat_turn) depends on 7A, 7B, 7F
- 7I (CLI) depends on 7B, 7F
- 7F 在 Wave 1 并行运行，不能被 7B 阻塞
- 7H 只依赖 7A（会话存储），不依赖 7B

#### 2.6 7F 与 7E 的隐式依赖

**问题**：7F 需要 PromptComposer 的 `compose_from_scene()` 方法来做测试，但 Plan 将两者放在同一 Wave 1 中并行执行。
**实际风险**：低 — 7F 可以在测试中使用 mock/fake composer，先用数据结构验证，再在 7J (integration) 中串联。但 Plan 未明确说明这种解耦策略。
**建议**：在 7F 的 References 中注明可以先 mock PromptComposer 接口进行 TDD

### 🟡 P3 — 设计细节歧义（建议澄清）

#### 2.7 Episode Summary 最近轮次保留数量不一致

- Plan 7L Must NOT do：`不压缩最近 4 轮（compaction_tail_preserve_turns=4）`
- 记忆模型定义：`强制保留最近 3 轮`
- **歧义**：到底保留 3 轮还是 4 轮？
- **影响**：实现时会产生不同的压缩行为

#### 2.8 Episode Summary 触发阈值定义不清

- 用户裁决 3：`≥10 轮 OR ≥60% token`
- Plan 7L：`total_turns >= 10 OR total_tokens >= max_context * 0.6`
- **歧义**：60% 的什么？
  - 如果是 max_context（如 DeepSeek 128K 的 60%），那是 ~77K tokens，可能永远不会触发
  - 如果是当前已用 token 占比，逻辑循环（只有用完才知道用了多少）
- **建议**：明确 `max_context = model_context_window`，60% = 模型上下文窗口的 60%

#### 2.9 PromptComposer 迁移 ask 路径的回滚策略缺失

- 7E 要将 `deepseek_llm.py:30-41` 的硬编码 `_SYSTEM_PROMPT` 替换为 PromptComposer
- **缺失**：如果迁移后 ask 行为退化（如 citation 质量下降），如何快速回滚？
- **建议**：7E 保留硬编码 `_SYSTEM_PROMPT` 作为 fallback 常量，PromptComposer 失败时回退

#### 2.10 Episode Summary 后台线程失败处理未定义

- 7L：`threading.Thread` 后台异步调用 LLM 生成摘要
- **缺失**：后台 LLM 调用失败时（网络错误/malformed response/timeout）的行为
- **建议**：明确定义：失败时静默丢弃（不阻塞主对话）+ 记录 warning 日志 + 下次触发时重试

### 🔵 低优先级

#### 2.11 7F compation 模板未列入交付物

- 7L 要求 `conversation_compaction` prompt 模板
- 7F 的 fragment 模板交付物列表中没有这个模板
- **建议**：在 7F 中新增 `fund_agent/service/prompts/interactive/compaction.md`

#### 2.12 PinnedState vs Session 模型的字段不一致

- agent-evolution-design.md 的 PinnedState 包含：`document_id`, `fund_code`, `fund_name`, 用户约束
- Plan 7A 的 PinnedState 包含：`fund_code`, `available_document_ids`, `active_document_id`, `active_year`, `user_constraints`
- **差异**：Plan 版本更丰富（多了 `available_document_ids` 和 `active_year`），更适配 `--fund-code` 多年度场景
- **建议**：agent-evolution-design.md 中的旧 PinnedState 应更新为 Plan 版本

---

## 三、代码现状确认（bg_b4e4652f 探索结果）

### 3.0 Phase 7 实现代码：0 行

| 计划文件 | 状态 |
|----------|------|
| `fund_agent/service/chat_service.py` | ❌ 不存在 |
| `fund_agent/host/session_store.py` | ❌ 不存在 |
| `fund_agent/agent/context_budget.py` | ❌ 不存在 |
| `fund_agent/service/scene_config.py` | ❌ 不存在 |
| `fund_agent/service/prompt_contributions.py` | ❌ 不存在 |
| `fund_agent/service/session_models.py` | ❌ 不存在 |
| `fund_agent/service/investment_guard.py` | ❌ 不存在 |
| `tests/fund/cli/test_cli_interactive.py` | ❌ 不存在 |
| `tests/fund/service/test_chat_service.py` | ❌ 不存在 |
| `tests/fund/host/test_session_store.py` | ❌ 不存在 |
| `tests/fund/agent/test_context_budget.py` | ❌ 不存在 |
| `tests/fund/service/test_scene_config.py` | ❌ 不存在 |
| `tests/fund/service/test_prompt_contributions.py` | ❌ 不存在 |
| `tests/fund/service/test_prompt_composer_upgrade.py` | ❌ 不存在 |

### 3.0.1 关键代码预检

| 检查项 | 结果 |
|--------|------|
| `pyproject.toml` 含 `prompt_toolkit` | ❌ **需要新增** |
| `pyproject.toml` 含 `rich` 直接依赖 | ❌ 仅作为传递依赖存在，**需声明** |
| `deepseek_llm.py` 硬编码 `_SYSTEM_PROMPT` | ✅ 确认为 7E 迁移目标（L30-41） |
| `extraction.py` 含投资建议关键词 | ✅ L132-136，与 audit_pipeline.py 各有一套 |
| `models.py` 预留 `session_id` 字段 | ✅ 在 `AskQuestionRequest` 中，但从未使用 |
| CLI 注册 `interactive` 子命令 | ❌ 不存在 |
| `service/prompts/` 目录 | 仅有 8 个章节模板，无 `base/`/`ask/`/`interactive/` 子目录 |

### 3.0.2 隐含风险

- **`rich` 已作为 docling 传递依赖安装** — 但直接声明为依赖时可能出现版本冲突
- **`prompt_toolkit` 完全是新依赖** — 可能导致 `uv.lock` 大范围变更
- **当前 268 个测试通过** — Phase 7 需保持全量回归

---

## 四、设计质量评估

### 4.1 优点 ✅

| 维度 | 评价 |
|------|------|
| 范围清晰 | 16 Slice 各司其职，依赖关系明确 |
| 三层记忆模型 | Pinned State + Recent Turns + Episode Summary，对齐 Dayu 但有简化 |
| TDD 策略 | 每个 Slice 先写测试后退回实现，QA scenario 具体可执行 |
| Prompt 路由对齐 | Fragment + Contribution + Context Slot，完整借鉴 Dayu 设计 |
| 向后兼容 | ask 命令行为不变，新增 interactive 不破坏既有路径 |
| 投资建议防护 | 统一关键词常量 + 每轮检测，fail-closed |

### 4.2 架构一致性 ✅

- 保持 `UI → Service → Host → Agent` 四层不变
- `fund_agent/fund` 仍是领域能力包，不承担 Agent 逻辑
- 会话持久化用 filesystem JSON（与现有 catalog 一致）
- 不引入 SQLite、不多进程并发、不暴露 raw Docling JSON

### 4.3 Dayu 对齐程度

| Dayu 概念 | Plan 对齐 | 简化 |
|-----------|----------|------|
| Scene Manifest | 7F SceneConfig | ✅ 无 model/temperature 配置 |
| Fragments | 7F .md 模板文件 | ✅ |
| Context Slots | 7F context_slots | ✅ |
| Prompt Contributions | 7F prompt_contributions.py | ✅ |
| Context Budget | 7M context_budget.py | ✅ 无 Compaction 多轮机制 |
| Episode Memory | 7L Episode Summary | ✅ 单线程异步，无 Durable Memory |
| Pending Turn / Resume Lease | 7K --label | ✅ 大幅简化 |

---

## 五、实施风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| prompt_toolkit + rich 新依赖引入兼容问题 | 🟡 中 | pyproject.toml 明确版本范围，测试覆盖 |
| ask 迁移到 PromptComposer 导致行为退化 | 🟡 中 | 保留硬编码 fallback，ask 回归测试 |
| Episode Summary 异步线程崩溃 | 🟢 低 | 静默失败 + 日志，不阻塞主对话 |
| 多文档切换时 citation 混淆 | 🟢 低 | PinnedState 记录 active_document_id，citation 绑定 |
| 16 Slice 工作量大，上下文丢失 | 🟡 中 | 每个 Slice 独立提交 + 独立测试验证 |

---

## 六、修复建议优先级

### 必须修复（阻塞实施）

无 — Phase 7 已通过裁决门禁，可进入实施。

### 建议在实施前修复（减少返工）

1. **更新 agent-evolution-design.md** — 标记 Phase 7 为已裁决
2. **修正 implementation-control.md 依赖列表** — 7B-7E 应为"无依赖"
3. **修正 Plan 中 7B 的 Blocks 字段** — 从 "7F, 7H" 修正为 "7G, 7I"
4. **统一 Slice 数量** — 16（非 15）
5. **明确 Episode Summary 阈值** — `max_context * 0.6` 中 max_context 的定义
6. **统一保留轮次** — 3 轮 vs 4 轮，二选一

### 建议在实施中处理

7. **7F 与 7E 的解耦说明** — 先 mock 后集成
8. **Episode Summary 失败处理** — 静默失败 + 日志
9. **ask 回滚策略** — 保留硬编码 fallback
10. **compation 模板** — 加入 7F 交付物

---

## 七、总结

Phase 7 的设计文档整体质量高，裁决门禁完整，Slice 分解合理，Dayu 对齐充分。主要问题是 **agent-evolution-design.md 过期** 和 **implementation-control.md 依赖列表的几个复制粘贴错误**，属于文档维护问题而非设计问题。建议在启动实施前完成 6 项建议修复（约 30 分钟工作量）。

**审核结论**：✅ 可以实施，建议先完成文档修正。
