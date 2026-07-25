# Phase 7 文档更新研究

> 研究时间：2026-07-25
> 研究目的：梳理 docs/design.md、docs/implementation-control.md、AGENTS.md 需要更新的内容

---

## 一、Phase 7 裁决汇总（16 项）

| # | 维度 | 裁决 | 来源 |
|---|------|------|------|
| 1 | 会话存储 | filesystem JSON，原子写入 | phase7-interactive.md |
| 2 | 记忆模型 | 三层：Pinned State + Recent Turns(3轮强制) + Episode Summary | phase7-interactive.md |
| 3 | Ep. Summary 触发 | ≥10 轮 OR ≥60% token | phase7-interactive.md |
| 4 | Ep. Summary 生成 | threading.Thread 后台 LLM 异步 | phase7-interactive.md |
| 5 | Token 计数 | API `usage` 字段精确计数 | phase7-interactive.md |
| 6 | REPL 库 | prompt_toolkit 富 REPL | phase7-interactive.md |
| 7 | 输出渲染 | rich（Markdown/表格/语法高亮），预留 textual | phase7-interactive.md |
| 8 | REPL 命令 | 扩展集：/help /clear /history /document /fund /label /save /export /stats /model /verbose exit/quit | phase7-interactive.md |
| 9 | CLI 入口 | `--fund-code 011649`（非 document_id） | phase7-interactive.md |
| 10 | 多年度默认 | 启动时列出可用年份，用户选择 | phase7-interactive.md |
| 11 | 会话恢复 | 支持 --label | phase7-interactive.md |
| 12 | 上下文治理 | 合并到 Phase 7 | phase7-interactive.md |
| 13 | 并发 | 不保证多进程安全 | phase7-interactive.md |
| 14 | 测试策略 | TDD | phase7-interactive.md |
| 15 | 投资建议检测 | 每轮都检测 | phase7-interactive.md |
| 16 | Prompt 路由 | 全面对齐 Dayu（Scene Manifest + Fragments + Contributions + Context Slots） | phase7-interactive.md |

---

## 二、docs/design.md 更新内容

### 2.1 当前状态

- 文档最后更新：2026-07-12
- Phase 5 已裁决（2026-07-24），但 design.md 未更新裁决时间
- Phase 6 已完成（✅），但 design.md 未更新"已完成"状态
- Phase 7 未在 design.md 中出现

### 2.2 需要新增的内容

#### 2.2.1 Phase 7 章节（在 Phase 6 之后）

```markdown
### Phase 7：多轮对话 + 会话记忆 + 上下文治理 + Prompt 路由

> 裁决时间：2026-07-25
> 计划文件：`.sisyphus/plans/phase7-interactive.md`

**裁决汇总**：16 项裁决，详见计划文件。

**核心能力**：
- Session 数据模型 + filesystem JSON 持久化
- 三层记忆模型（Pinned State + Recent Turns + Episode Summary）
- Scene Manifest + Fragments + Context Slots（对齐 Dayu Prompt 路由）
- 上下文预算治理（Context Budget）
- CLI `interactive` 子命令（prompt_toolkit + rich）
- 会话恢复（--label）

**Slice 列表**：
- **7A**：Session 数据模型 + 持久化
- **7B**：上下文截断（Context Budget）
- **7C**：Scene Manifest 数据模型
- **7D**：PromptComposer 升级（Fragments + Context Slots）
- **7E**：Service 层 chat_turn use case
- **7F**：Host 多轮会话托管
- **7G**：CLI interactive 子命令（prompt_toolkit + rich）
- **7H**：会话恢复（--label）
- **7I**：Episode Summary（异步 LLM）
- **7J**：扩展命令集
- **7K**：多文档切换
- **7L-7P**：集成测试 + 端到端验证

**新增文件**：
- `fund_agent/host/session_store.py` — Session JSON 持久化
- `fund_agent/service/session_models.py` — Session/Turn/PinnedState 数据模型
- `fund_agent/service/scene_manifest.py` — Scene Manifest 数据模型
- `fund_agent/service/prompt_composer.py` — 升级：fragment 装配 + contribution 注入
- `fund_agent/service/prompts/interactive/` — prompt fragment 模板
- `fund_agent/agent/context_budget.py` — 上下文预算治理
- `tests/fund/cli/test_cli_interactive.py` — interactive 测试
```

#### 2.2.2 更新 Phase 5 裁决时间

```markdown
### Phase 5：LLM 自主工具调用 + 流式输出

> 裁决时间：2026-07-24 | 状态：✅ 已完成
> 计划文件：`.sisyphus/plans/phase5-implementation.md`
```

#### 2.2.3 更新 Phase 6 状态

```markdown
### Phase 6：模板框架适配 + 基金类型感知

> 启动时间：2026-07-22 | 状态：✅ 已完成
> 详见 `docs/implementation-control.md` Phase 6 节
```

#### 2.2.4 更新 CLI 入口列表

```markdown
CLI 已实现 10 个子命令：`read` / `multi-year` / `import` / `holdings` / `allocation` / `fees` / `audit` / `deep-audit` / `generate` / `ask`。
Phase 7 将新增：`interactive`。
```

#### 2.2.5 更新技术债

```markdown
### 技术债

- **P1-3**：提取 compute_signal_judgment / compute_risk_checklist 共享评分 helper。
- **extraction.py 二次拆分**：当前 5931 行。signal_scoring.py（439 行）已完成一次拆分；残留 7 个评分/风险函数（约 450 行）待迁移。
  - 排期：Phase 7 完成后执行（理由：Phase 7 新增 Session/Scene/ContextBudget，会产生新的 import 依赖；并行做会产生 merge 冲突）。
```

---

## 三、docs/implementation-control.md 更新内容

### 3.1 当前状态

- 文档最后更新：2026-07-12
- Phase 5 已裁决（2026-07-24），但 implementation-control.md 未更新裁决时间
- Phase 6 已完成（✅），但 implementation-control.md 未更新"已完成"状态
- Phase 7 未在 implementation-control.md 中出现

### 3.2 需要新增的内容

#### 3.2.1 Phase 7 章节（在 Phase 6 之后）

```markdown
## Phase 7：多轮对话 + 会话记忆 + 上下文治理 + Prompt 路由

> 裁决时间：2026-07-25
> 前置条件：Phase 5 ✅（2026-07-24 完成）、Phase 6 ✅（2026-07-22 完成）
> 设计来源：`docs/agent-evolution-design.md` §2 + dayu-agent 场景研究
> 计划文件：`.sisyphus/plans/phase7-interactive.md`

### Phase 7 裁决 Gate

| Gate | 条件 | 状态 |
|------|------|------|
| Gate 1 | Phase 7 scope/write set/verification/stop conditions 写入本文件 | ✅ 本文档记录 |
| Gate 2 | 16 项裁决策通过 | ✅ 已裁决 |

### Phase 7 Slice 列表

| Slice | 内容 | 状态 |
|-------|------|------|
| **7A** | Session 数据模型 + 持久化（filesystem JSON） | 待启动 |
| **7B** | 上下文截断（Context Budget） | 依赖 7A |
| **7C** | Scene Manifest 数据模型 | 依赖 7A |
| **7D** | PromptComposer 升级（Fragments + Context Slots） | 依赖 7C |
| **7E** | Service 层 chat_turn use case | 依赖 7A, 7B |
| **7F** | Host 多轮会话托管 | 依赖 7E |
| **7G** | CLI interactive 子命令（prompt_toolkit + rich） | 依赖 7F |
| **7H** | 会话恢复（--label） | 依赖 7G |
| **7I** | Episode Summary（异步 LLM） | 依赖 7F |
| **7J** | 扩展命令集 | 依赖 7G |
| **7K** | 多文档切换 | 依赖 7G |
| **7L** | 集成测试 | 依赖 7A-7K |
| **7M** | 端到端验证（011649 基金） | 依赖 7L |
| **7N** | DS Review | 依赖 7M |
| **7O** | 全量回归 | 依赖 7N |
| **7P** | 最终审计（F1-F4） | 依赖 7O |

### Phase 7 总体验收标准

1. `interactive --fund-code 011649` 端到端通过
2. 多轮对话 3 轮以上上下文正确传递
3. 会话持久化（filesystem JSON）正确
4. 会话恢复（--label）正确
5. Episode Summary 异步触发并落盘
6. 上下文预算裁减生效
7. Scene Manifest + Fragments + Context Slots 正确装配
8. 投资建议检测每轮生效
9. ask 命令行为不变（回归）
10. 全量测试通过（≥200 tests）

### Allowed Write Set

| 文件 | 变更类型 | 所属 Slice |
|------|---------|-----------|
| `fund_agent/host/session_store.py` | **新增** — Session JSON 持久化 | 7A |
| `fund_agent/service/session_models.py` | **新增** — Session/Turn/PinnedState 数据模型 | 7A |
| `fund_agent/agent/context_budget.py` | **新增** — 上下文预算治理 | 7B |
| `fund_agent/service/scene_manifest.py` | **新增** — Scene Manifest 数据模型 | 7C |
| `fund_agent/service/prompt_composer.py` | 升级 — fragment 装配 + contribution 注入 | 7D |
| `fund_agent/service/prompts/interactive/` | **新增** — prompt fragment 模板 | 7C, 7D |
| `fund_agent/service/extraction.py` | 升级 — chat_turn use case | 7E |
| `fund_agent/host/minimal_host.py` | 升级 — 多轮会话托管 | 7F |
| `fund_agent/cli/main.py` | 升级 — interactive 子命令 | 7G |
| `tests/fund/cli/test_cli_interactive.py` | **新增** — interactive 测试 | 7G |
| `tests/fund/service/test_chat_service.py` | **新增** — chat_turn 测试 | 7E |
| `tests/fund/host/test_session_store.py` | **新增** — session 持久化测试 | 7A |
| `tests/fund/agent/test_context_budget.py` | **新增** — 上下文预算测试 | 7B |
| `tests/fund/service/test_scene_manifest.py` | **新增** — Scene Manifest 测试 | 7C |
| `tests/fund/service/test_prompt_composer_upgrade.py` | **新增** — PromptComposer 升级测试 | 7D |
| `docs/design.md` | 更新 — Phase 7 设计 | — |
| `docs/implementation-control.md` | 更新 — Phase 7 执行面板 | — |

### Stop Conditions

- `interactive` 破坏 `ask` 子命令现有行为 → 停止
- 会话持久化导致数据损坏 → 停止
- 上下文截断导致 LLM 回答质量下降 → 停止
- Scene Manifest 装配失败 → 停止

### 验证命令

```bash
# Phase 7 核心测试
uv run pytest tests/fund/cli/test_cli_interactive.py \
  tests/fund/service/test_chat_service.py \
  tests/fund/host/test_session_store.py \
  tests/fund/agent/test_context_budget.py \
  tests/fund/service/test_scene_manifest.py \
  tests/fund/service/test_prompt_composer_upgrade.py \
  -v --tb=short

# Phase 5 ask 回归
uv run pytest tests/fund/agent/test_stream_events.py \
  tests/fund/agent/test_llm_production_readiness.py \
  tests/fund/agent/test_llm_tool_loop.py \
  tests/fund/cli/test_cli.py -k ask \
  -v --tb=short

# 全量回归
uv run pytest tests/fund/ -v --tb=short
```
```

---

## 四、AGENTS.md 更新内容

### 4.1 当前状态

- 文档最后更新：2026-07-12
- Phase 5 已裁决（2026-07-24），但 AGENTS.md 未更新裁决时间
- Phase 6 已完成（✅），但 AGENTS.md 未更新"已完成"状态
- Phase 7 未在 AGENTS.md 中出现

### 4.2 需要更新的内容

#### 4.2.1 更新"当前产品方向"章节

```markdown
## 当前产品方向

当前产品方向是 **基金分析助手**（已脱离 MVP 阅读工具层阶段）。

项目定位：面向基金投资者的多年度分析工具，覆盖年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道的完整链路。

目标主链路：

```text
PDF
 -> Docling JSON
 -> FundDocumentToolService (7 个 reading tools)
 -> Service 层受控 profile routing + disclosure target contract
 -> 结构化字段抽取 (performance / fee_rates / holdings / allocation)
 -> 多年度聚合 (3-5 年 bounded coverage)
 -> 确定性信号评分 (基金类型感知：主动基金 6 指标 135→100 归一化；被动基金 3 指标 100 分制)
 -> 8 章分析报告生成 (程序数据表格 + LLM 定性分析)
 -> 三层审计管道 (程序+LLM+复核，4 类 22 项)
```

已实现的 CLI 入口：`read` / `multi-year` / `import` / `holdings` / `allocation` / `fees` / `audit` / `deep-audit` / `generate` / `ask`。
Phase 7 将新增：`interactive`。

验收约束（适用于所有阶段）：
- 不接受仅 Service / ToolService 层测试；任何阶段的验收必须包含 Host / Agent loop 或 CLI 端到端 smoke。

当前已知能力差距（来自 dayu-agent 对标研究，2026-07-11），以下能力当前不存在，Agent 不得假装具备：
- **多轮对话**：无 interactive mode，无会话记忆（Phase 7 将解决）
- **上下文治理**：无 budget/truncation/compaction（Phase 7 将解决）
- **联网搜索**：无法获取实时市场数据

Phase 5 已完成（2026-07-24）：
- **LLM 自主工具调用**：`ask` 子命令走 LLM 自主决策工具调用路径（Slice 19A-19F）
- **Streaming**：StreamEvent 模型 + DeepSeek stream=True + CLI 流式输出（Slice 19A-19C, 19E）

Phase 6 已完成（2026-07-22）：
- **模板框架适配**：preferred_lens 接入 generate 流程
- **基金类型感知**：评分框架 fund_type 感知（主动 6 指标 135→100 / 被动 3 指标 100 分制 / 债券 5 指标）

Phase 7 已裁决（2026-07-25）并正在实施：
- **多轮对话**：`interactive` 子命令，支持会话持久化和上下文记忆
- **上下文治理**：Context Budget，支持长对话不超限
- **Prompt 路由**：Scene Manifest + Fragments + Context Slots，对齐 Dayu

LLM provider 已支持 DeepSeek 与 Mimo（OpenAI-compatible adapter）；暂不需要接入 Gemini/OpenAI/Anthropic 等其他 provider。

这些差距将在后续 phase 中按优先级解决，不影响当前已实现功能的使用。
```

#### 4.2.2 更新"硬边界"章节

```markdown
## 硬边界

- 对基金文档的存取必须通过统一 Fund documents / tool service 边界。
- 禁止 Service / UI / Host / 展示层 / LLM prompt 直接消费 raw PDF、raw Docling JSON、PDF cache path、本地路径、URL secret 或 parser private payload。
- Dayu 只能作为架构参考和能力来源；禁止直接引入 `dayu-agent`、`dayu.host`、`dayu.engine` 作为生产 runtime。
- 复制或改写 Dayu 代码必须先经过 license/compliance gate。
- Docling 为当前 production path：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback 路线。
- 禁止做与 `pdfplumber` 的替代路线比较。
- 结构化字段抽取、自动报告、信号评分已通过正式 Slice 准入（10C/10F/10G/11C/11D/13A/13B/14A/14C），不再受 MVP 禁止条款约束。
- 真实 LLM 接入必须位于已实现的 fake/injected LLM tool-loop contract 之后；不得让 LLM provider、prompt 或 adapter 直接读取 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、`local_import_id` 或 secret。
- 当前 LLM provider 支持 DeepSeek 与 Mimo（OpenAI-compatible adapter）；暂不需要接入 Gemini/OpenAI/Anthropic 等其他 provider。
- live provider smoke 必须显式 opt-in；默认 pytest 不得联网、不得读取真实 API key、不得记录 raw provider response 或新增 artifact。
- `ask` 子命令已裁决通过（Phase 5，2026-07-24），streaming 已并入 Phase 5。
- `interactive` 模式已裁决通过（Phase 7，2026-07-25）。
```

#### 4.2.3 更新"测试规则"章节

```markdown
## 测试规则

- 每次代码修改必须同步新增或更新测试。
- fake fixture 只能测试边界和错误；不得用于证明 production conversion path。
- 最小验证命令固定为：
```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```
- Phase 5 验证命令：
```bash
uv run pytest tests/fund/agent/test_stream_events.py tests/fund/agent/test_llm_production_readiness.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short
```
- Phase 7 验证命令：
```bash
uv run pytest tests/fund/cli/test_cli_interactive.py \
  tests/fund/service/test_chat_service.py \
  tests/fund/host/test_session_store.py \
  tests/fund/agent/test_context_budget.py \
  tests/fund/service/test_scene_manifest.py \
  tests/fund/service/test_prompt_composer_upgrade.py \
  -v --tb=short
```
```

---

## 五、更新优先级

| 文档 | 优先级 | 理由 |
|------|--------|------|
| `docs/implementation-control.md` | P0 | 执行面板，必须先更新才能开始 Phase 7 |
| `docs/design.md` | P0 | 设计真源，必须同步更新 |
| `AGENTS.md` | P1 | 执行规则，更新裁决状态和验证命令 |

---

## 六、更新检查清单

### docs/design.md

- [ ] Phase 5 裁决时间更新为 2026-07-24
- [ ] Phase 6 状态更新为 ✅ 已完成
- [ ] 新增 Phase 7 章节（裁决时间、Slice 列表、新增文件）
- [ ] 更新 CLI 入口列表（增加 `ask`、`interactive`）
- [ ] 更新技术债排期（Phase 7 完成后执行）

### docs/implementation-control.md

- [ ] Phase 5 裁决时间更新为 2026-07-24
- [ ] Phase 6 状态更新为 ✅ 已完成
- [ ] 新增 Phase 7 章节（裁决 Gate、Slice 列表、验收标准、Allowed Write Set、Stop Conditions、验证命令）
- [ ] 更新已知能力差距（Phase 5、6 已完成，Phase 7 正在实施）

### AGENTS.md

- [ ] 更新"当前产品方向"章节（CLI 入口、能力差距、Phase 5/6/7 状态）
- [ ] 更新"硬边界"章节（interactive 模式已裁决）
- [ ] 更新"测试规则"章节（Phase 7 验证命令）
