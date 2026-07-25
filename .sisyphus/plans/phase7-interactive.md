# Phase 7：多轮对话 + 会话记忆 + 上下文治理 + Prompt 路由

## TL;DR

> **Quick Summary**：实现 `fund-checklist interactive --fund-code 011649` 多轮对话模式，三层记忆模型（Pinned State + Recent Turns + Episode Summary），对齐 Dayu Agent 的 Scene Manifest + Prompt Contributions + Context Budget 机制，融合 Phase 8 上下文治理。
>
> **Deliverables**：
> - Session 数据模型 + filesystem JSON 持久化
> - FundReadingService.resolve_by_fund_code() 基金代码解析
> - 统一 INVESTMENT_ADVICE_KEYWORDS 常量
> - DeepSeekLlmClient token usage 追踪
> - PromptComposer 升级：fragment 装配 + contribution 注入 + ask 路径迁移
> - Interactive Scene 配置（5 个 prompt fragment 模板 + scene definition）
> - Service 层 chat_turn use case
> - Host 多轮会话托管
> - CLI `interactive` 子命令（prompt_toolkit + rich）
> - 会话恢复（--label）+ Episode Summary（异步 LLM）+ 上下文预算治理
> - 扩展命令集（/stats /save /export /model /verbose）+ 多文档切换 + Rich Markdown 渲染
> - 011649 基金端到端验证 + 全量回归
>
> **Estimated Effort**：Large（16 Slice + 审计）
> **Parallel Execution**：YES — 5 波并行
> **Critical Path**：7E → 7F → 7J → 7L → 7M → 7P → F1-F4
> **Test Strategy**：TDD（RED → GREEN → REFACTOR）

---

## Context

### 原始需求

- `.sisyphus/goals/phase7-interactive-011649.md` 的 Phase 7 开发计划
- 用户裁决升级：三层记忆 + 全面对齐 Dayu prompt 路由 + prompt_toolkit 富 REPL + API usage token 计数
- Phase 8（上下文治理）合并到 Phase 7

### 用户裁决汇总（16 项）

| # | 维度 | 裁决 |
|---|------|------|
| 1 | 会话存储 | filesystem JSON，原子写入 |
| 2 | 记忆模型 | 三层：Pinned State + Recent Turns(3轮强制) + Episode Summary |
| 3 | Ep. Summary 触发 | ≥10 轮 OR ≥60% token |
| 4 | Ep. Summary 生成 | threading.Thread 后台 LLM 异步 |
| 5 | Token 计数 | API `usage` 字段精确计数 |
| 6 | REPL 库 | prompt_toolkit 富 REPL |
| 7 | 输出渲染 | rich（Markdown/表格/语法高亮），预留 textual |
| 8 | REPL 命令 | 扩展集：/help /clear /history /document /fund /label /save /export /stats /model /verbose exit/quit |
| 9 | CLI 入口 | `--fund-code 011649`（非 document_id） |
| 10 | 多年度默认 | 启动时列出可用年份，用户选择 |
| 11 | 会话恢复 | 支持 --label |
| 12 | 上下文治理 | 合并到 Phase 7 |
| 13 | 并发 | 不保证多进程安全 |
| 14 | 测试策略 | TDD |
| 15 | 投资建议检测 | 每轮都检测 |
| 16 | Prompt 路由 | 全面对齐 Dayu（Scene Manifest + Fragments + Contributions + Context Slots） |

### Dayu Agent 对标研究

**Prompt 路由全景**（详见 draft）：
```
Scene Manifest (JSON)  →  Fragments (有序 Markdown 片段)
                       →  Context Slots (声明可注入 slot)
                       →  Model/Temperature/max_iterations

Prompt Contributions   →  build_base_user() + build_fins_subject()
                       →  select_prompt_contributions(slots)

PromptComposer         →  assemble(fragments) + append(contributions)
                       →  最终 system_prompt
```

**上下文预算全景**：
```
ContextBudgetState     →  soft_limit(75%) / hard_limit(90%)
ToolResultBudgetCapper →  升序公平分配裁剪
Compaction             →  70% 触发，每次 1 轮 → LLM → Episode Summary
Memory                 →  Pinned State(不占预算) + Episodes(共享总池) + Forced Turns(强制保留)
```

### 代码现状

- `ask` 路径：硬编码 `_SYSTEM_PROMPT`（deepseek_llm.py:30-41），不经 PromptComposer
- 章节生成路径：PromptComposer + 9 个 .md 模板
- Session/Episode Summary：零代码
- PromptComposer：只支持单模板 `{{ var }}` + `<when_missing>`，不支持 fragment 数组 + contribution 注入
- StreamEvent：7 种事件类型已定义
- Phase 5 (ask + streaming)：已完成 ✅

### Metis 审计发现的代码缺口

| # | Gap | 影响 |
|---|-----|------|
| 1 | `ask` 路径不用 PromptComposer（硬编码 `_SYSTEM_PROMPT`） | 阻塞 prompt 路由对齐 |
| 2 | C3 投资建议检测有两套不同关键词（`extraction.py` vs `audit_pipeline.py`） | 统一前不可靠 |
| 3 | 当前 ask 路径无 token usage 追踪 | 阻塞上下文预算治理 |
| 4 | `_collect_matching_docs()` 在 CLI 层，Service 不可达 | 阻塞 `--fund-code` 入口 |

---

## Work Objectives

### Core Objective

实现 `fund-checklist interactive` 多轮对话模式，完整对齐 Dayu Agent 的 prompt 路由与上下文治理机制。

### Concrete Deliverables

- `fund_agent/host/session_store.py` — Session JSON 持久化
- `fund_agent/service/session_models.py` — Session/Turn/PinnedState 数据模型
- `fund_agent/service/prompt_composer.py` — 升级：fragment 装配 + contribution 注入
- `fund_agent/service/prompts/interactive/` — 5 个 prompt fragment 模板
- `fund_agent/service/scene_config.py` — Interactive Scene 配置
- `fund_agent/agent/context_budget.py` — 上下文预算治理
- `fund_agent/service/chat_service.py` — chat_turn use case
- `fund_agent/host/minimal_host.py` — 扩展：多轮会话托管
- `fund_agent/cli/main.py` — `interactive` 子命令
- 统一 `INVESTMENT_ADVICE_KEYWORDS` 常量
- DeepSeekLlmClient token usage 追踪
- FundReadingService.resolve_by_fund_code()

### Definition of Done

- [ ] `fund-checklist interactive --fund-code 011649` → REPL 正常进入，列出可用年份
- [ ] 3 轮连续对话：上下文正确传递（基金经理→任期→规模）
- [ ] 会话文件 `{work_dir}/sessions/{session_id}.json` 正确创建且可恢复
- [ ] Episode Summary：≥10 轮后触发异步压缩，summary 落盘
- [ ] 上下文预算：超出软限制时工具结果被裁剪
- [ ] 投资建议关键词每轮检测：含"建议买入"被拦截
- [ ] `fund-checklist ask` 路径行为不变（全量回归）
- [ ] 流式输出正常（rich Markdown 渲染）

### Must Have

- 三层记忆模型完整可用
- `--fund-code` 解析到多年度 document_id
- PromptComposer 支持 fragment + contribution
- 投资建议检测 fail-closed
- 会话原子写入
- TDD 测试覆盖

### Must NOT Have (Guardrails)

- 不破坏 Phase 5 `ask` 子命令行为
- 不引入 SQLite 或新数据库依赖
- 不暴露 raw Docling JSON / 本地路径 / cache path
- 不实现多进程并发安全
- 跳过投资建议检测时 fail-closed
- 不实现 episode summary 的实时流式生成
- prompt_toolkit + rich 为新依赖，需确认 pyproject.toml 变更范围

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision

- **Infrastructure exists**: YES（pytest，70 个 CLI 测试）
- **Automated tests**: TDD（测试驱动开发）
- **Framework**: pytest
- **Each task follows**: RED（先写 failing test）→ GREEN（最小实现通过）→ REFACTOR

### QA Policy

Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **CLI/TUI**: interactive_bash（tmux）— Run command, send keystrokes, validate output
- **API/Backend**: Bash（curl 或 Python REPL）— Send requests, assert fields
- **Library/Module**: Bash（pytest）— Run specific test files, assert pass

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — 6 PARALLEL, foundation):
├── 7A: Session 数据模型 + JSON 持久化 [2 files]
├── 7B: FundReadingService.resolve_by_fund_code() [2 files]
├── 7C: 统一 INVESTMENT_ADVICE_KEYWORDS [2 files]
├── 7D: DeepSeekLlmClient token usage 追踪 [1 file]
├── 7E: PromptComposer 升级 (fragment assembly + contribution injection) [1 file]
└── 7F: Interactive + Ask 双 Scene Config + Fragment 模板 + Prompt Contributions [8 files]

Wave 2 (After Wave 1 — 3 PARALLEL, core implementation):
├── 7G: Service 层 chat_turn use case (depends: 7A, 7B, 7F) [2 files]
├── 7H: Host 多轮会话托管 (depends: 7A) [2 files]
└── 7I: CLI interactive 子命令 (depends: 7B, 7F) [2 files]

Wave 3 (After Wave 2 — sequential chain):
├── 7J: Integration: wire-up chat_turn → Host → CLI (depends: 7G, 7H, 7I) [3 files]
├── 7K: 会话恢复 + --label 支持 (depends: 7A, 7I) [parallel with 7J]
├── 7L: Episode Summary (异步 LLM) (depends: 7D, 7J) [2 files]

Wave 4 (After Wave 3 — 3 PARALLEL):
├── 7M: 上下文预算治理 (depends: 7D, 7L) [2 files]
├── 7N: 扩展命令 + 多文档 (depends: 7J) [2 files]
└── 7O: Rich Markdown 渲染 (depends: 7J) [2 files]

Wave 5 (After Wave 4 — 1 sequential):
└── 7P: 端到端验证 + 全量回归 [2 files]

Wave FINAL (After ALL tasks — 4 PARALLEL):
├── F1: Plan Compliance Audit (oracle)
├── F2: Code Quality Review (unspecified-high)
├── F3: Real Manual QA (unspecified-high)
└── F4: Scope Fidelity Check (deep)
```

### Dependency Matrix

- **7A-7F**: None → Wave 2
- **7G**: 7A, 7B, 7F → 7J
- **7H**: 7A → 7J
- **7I**: 7B, 7F → 7J, 7K
- **7J**: 7G, 7H, 7I → 7L, 7M, 7N, 7O
- **7K**: 7A, 7I → (parallel with 7J)
- **7L**: 7D, 7J → 7M
- **7M**: 7D, 7L → 7P
- **7N**: 7J → 7P
- **7O**: 7J → 7P
- **7P**: 7M, 7N, 7O → F1-F4

### Agent Dispatch Summary

- **Wave 1**: **6** — 7A→`quick`, 7B→`quick`, 7C→`quick`, 7D→`quick`, 7E→`deep`, 7F→`deep`
- **Wave 2**: **3** — 7G→`deep`, 7H→`deep`, 7I→`visual-engineering`
- **Wave 3**: **3** — 7J→`deep`, 7K→`quick`, 7L→`deep`
- **Wave 4**: **3** — 7M→`unspecified-high`, 7N→`quick`, 7O→`visual-engineering`
- **Wave 5**: **1** — 7P→`unspecified-high`
- **FINAL**: **4** — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 7A. Session 数据模型 + filesystem JSON 持久化

  **What to do**:
  - 创建 `fund_agent/service/session_models.py`：定义 Session/Turn/PinnedState/EpisodeSummary 数据类
  - 创建 `fund_agent/host/session_store.py`：SessionStore 类，支持 save/load/list/delete
  - Session 目录：`{work_dir}/sessions/{session_id}.json`
  - PinnedState 字段：fund_code / available_document_ids / active_document_id / active_year / user_constraints
  - Turn 字段：role(user|assistant) / content / citations / tool_trace / timestamp
  - EpisodeSummary 字段：episode_id / start_turn_id / end_turn_id / title / goal / confirmed_facts / open_questions
  - 原子写入：临时文件 + `os.replace()`
  - 测试：创建/保存/加载/原子性/损坏恢复

  **Must NOT do**:
  - 不引入 SQLite
  - 不实现多进程并发安全
  - 不包含 chat_turn 业务逻辑（留给 7F）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with 7B, 7C, 7D, 7E)
  -   **Blocks**: 7G, 7H, 7K

  **References**:
  - `fund_agent/fund/document_tools/persistent_repository.py` — FilesystemReportRepository 的 JSON catalog 模式（原子写入、work_dir 路径）
  - `fund_agent/service/models.py` — 现有 DTO 风格（dataclass、frozen、类型注解）
  - Dayu: `dayu/host/conversation_store.py` — ConversationTranscript/ConversationPinnedState/ConversationEpisodeSummary 结构参考

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/host/test_session_store.py` 新建
  - [ ] 测试文件：`tests/fund/service/test_session_models.py` 新建
  - [ ] `uv run pytest tests/fund/host/test_session_store.py tests/fund/service/test_session_models.py` → PASS（≥8 tests）

  **QA Scenarios**:

  ```
  Scenario: 会话创建与持久化
    Tool: Bash (Python REPL)
    Steps:
      1. from fund_agent.host.session_store import SessionStore
      2. store = SessionStore(Path("/tmp/test_sessions"))
      3. session = store.create(fund_code="011649", available_years=[2021,2022,2023,2024,2025])
      4. assert session.session_id is not None
      5. assert Path("/tmp/test_sessions/{session.session_id}.json").exists()
    Expected Result: 文件存在且 JSON 可解析
    Evidence: .sisyphus/evidence/task-7a-session-create.txt

  Scenario: 原子写入防止损坏
    Tool: Bash (Python REPL)
    Steps:
      1. 写入中途模拟 KeyboardInterrupt（在 os.replace 之前）
      2. 检查原始文件是否完整（如果存在）
      3. 检查临时文件是否已清理
    Expected Result: 原文件不变或不存在，无损坏 JSON
    Evidence: .sisyphus/evidence/task-7a-atomic-write.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): session data model + filesystem JSON persistence`
  - Files: `fund_agent/service/session_models.py`, `fund_agent/host/session_store.py`
  - Pre-commit: `uv run pytest tests/fund/host/test_session_store.py tests/fund/service/test_session_models.py`

- [ ] 7B. FundReadingService.resolve_by_fund_code() — 基金代码 → 文档解析

  **What to do**:
  - 将 CLI 层 `_collect_matching_docs()` 逻辑下沉到 Service 层
  - 新增 `FundReadingService.resolve_by_fund_code(fund_code, work_dir)` 方法
  - 返回 `FundCodeResolution`：fund_code / fund_name / documents[{year, document_id}] / available_years
  - 复用 `FilesystemReportRepository.list_reports()` 过滤 catalog
  - 测试：正常解析 / 无匹配基金 / 空 catalog / 部分年份缺失

  **Must NOT do**:
  - 不做自动导入缺失 PDF
  - 不做文件名猜年份
  - 不从 document_id 字符串解析年份

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with 7A, 7C, 7D, 7E)
  - **Blocks**: 7F, 7H

  **References**:
  - `fund_agent/cli/main.py:_collect_matching_docs()` — 现有 CLI 层 fund_code 解析逻辑
  - `fund_agent/fund/document_tools/persistent_repository.py:list_reports()` — catalog 查询接口
  - `fund_agent/service/extraction.py` — FundReadingService 现有方法模式

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/service/test_fund_code_resolution.py` 新建
  - [ ] `uv run pytest tests/fund/service/test_fund_code_resolution.py` → PASS（≥5 tests）

  **QA Scenarios**:

  ```
  Scenario: 正常解析基金代码
    Tool: Bash (Python REPL)
    Steps:
      1. 准备 fake catalog：011649 含 2021-2025 共 5 个 document_id
      2. result = service.resolve_by_fund_code("011649", work_dir)
      3. assert len(result.documents) == 5
      4. assert result.available_years == [2021,2022,2023,2024,2025]
    Expected Result: 5 个文档，年份升序排列
    Evidence: .sisyphus/evidence/task-7b-resolution.txt

  Scenario: 无匹配基金代码
    Tool: Bash (Python REPL)
    Steps:
      1. result = service.resolve_by_fund_code("999999", work_dir)
      2. assert result is None or result.documents == []
    Expected Result: 空结果，不抛异常
    Evidence: .sisyphus/evidence/task-7b-no-match.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): fund code → documents resolution in Service layer`
  - Files: `fund_agent/service/extraction.py`, `fund_agent/service/models.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_fund_code_resolution.py`

- [ ] 7C. 统一投资建议关键词为单一真源

  **What to do**:
  - 提取 `extraction.py` 和 `audit_pipeline.py` 中两套 C3 关键词列表
  - 创建 `fund_agent/service/investment_guard.py` → 单一 `INVESTMENT_ADVICE_KEYWORDS` 常量
  - 包含：买入/卖出/持有/增持/减持/目标价/建议配置/强烈推荐/值得买入 等
  - 提供 `contains_investment_advice(text) → bool` 公共函数
  - 替换 extraction.py 和 audit_pipeline.py 中的散落关键词
  - 测试：覆盖所有关键词 / 正常内容不过滤 / 边界情况

  **Must NOT do**:
  - 不改变 C3 审计规则的行为
  - 不添加新的关键词（只统一现有）
  - 不修改审计评分逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with 7A, 7B, 7D, 7E)
  - **Blocks**: None（独立任务）

  **References**:
  - `fund_agent/service/extraction.py:132-136` — 现有 pre-LLM 投资建议检测关键词
  - `fund_agent/service/audit_pipeline.py:C3` — 现有审计管道 C3 关键词列表
  - `fund_agent/fund/document_tools/constants.py` — 集中定义 failure code 的模式

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/service/test_investment_guard.py` 新建
  - [ ] `uv run pytest tests/fund/service/test_investment_guard.py` → PASS（≥10 tests）
  - [ ] 回退测试：`uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py` → PASS（现有行为不变）

  **QA Scenarios**:

  ```
  Scenario: 检测投资建议关键词
    Tool: Bash (pytest)
    Steps:
      1. assert contains_investment_advice("建议买入该基金") == True
      2. assert contains_investment_advice("建议卖出") == True
      3. assert contains_investment_advice("目标价 3.5 元") == True
    Expected Result: 所有已知关键词触发 True
    Evidence: .sisyphus/evidence/task-7c-detect.txt

  Scenario: 正常内容不过滤
    Tool: Bash (pytest)
    Steps:
      1. assert contains_investment_advice("该基金经理管理规模 50 亿") == False
      2. assert contains_investment_advice("建议关注费率变化") == False
    Expected Result: 分析性内容不触发
    Evidence: .sisyphus/evidence/task-7c-false-positive.txt
  ```

  **Commit**: YES
  - Message: `refactor(phase7): extract unified INVESTMENT_ADVICE_KEYWORDS constant`
  - Files: `fund_agent/service/investment_guard.py`, `fund_agent/service/extraction.py`, `fund_agent/service/audit_pipeline.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_investment_guard.py tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py`

- [ ] 7D. DeepSeekLlmClient token usage 追踪

  **What to do**:
  - 在 `DeepSeekLlmClient.next_step()` 响应处理中提取 `response["usage"]` → `prompt_tokens` / `completion_tokens`
  - `ChatResponse` 新增 `usage: Optional[TokenUsage]` 字段（prompt_tokens / completion_tokens / total_tokens）
  - `ChatResponse` 新增 `cumulative_usage: TokenUsage`（会话累计）
  - 不暴露 API key 或 raw response
  - 测试：fake transport 注入 usage → ChatResponse 正确携带

  **Must NOT do**:
  - 不做 tiktoken 客户端估算
  - 不做计费逻辑
  - 不拦截或修改 LLM 响应内容

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with 7A, 7B, 7C, 7E)
  - **Blocks**: 7K, 7L

  **References**:
  - `fund_agent/agent/deepseek_llm.py:next_step()` — 现有 response 解析逻辑
  - `fund_agent/agent/deepseek_llm.py:parse_response()` — ChatResponse 构造
  - `fund_agent/agent/llm_tool_loop.py` — LlmClientProtocol 接口
  - DeepSeek API: `usage.prompt_tokens` / `usage.completion_tokens` 字段

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/agent/test_token_usage.py` 新建
  - [ ] `uv run pytest tests/fund/agent/test_token_usage.py` → PASS（≥4 tests）
  - [ ] 回退：`uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py` → PASS

  **QA Scenarios**:

  ```
  Scenario: API 返回 usage 正确提取
    Tool: Bash (pytest)
    Steps:
      1. fake transport 返回含 usage.prompt_tokens=150, usage.completion_tokens=50 的响应
      2. response = client.next_step(...)
      3. assert response.usage.prompt_tokens == 150
    Expected Result: ChatResponse.usage 正确
    Evidence: .sisyphus/evidence/task-7d-usage.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): add token usage tracking to DeepSeekLlmClient`
  - Files: `fund_agent/agent/deepseek_llm.py`, `fund_agent/agent/llm_tool_loop.py`
  - Pre-commit: `uv run pytest tests/fund/agent/test_token_usage.py tests/fund/agent/test_real_llm_adapter.py`

- [ ] 7E. PromptComposer 升级 (fragment assembly + contribution injection) + ask 路径迁移

  **What to do**:
  - **Part 1: PromptComposer 升级**
    - `PromptComposer.compose_from_scene(scene_config, contributions) → ComposedPrompt`
    - 支持 fragment 数组：按 order 排序，加载每个 path 的 .md 模板，拼装为 system_prompt
    - 支持 contribution 尾部注入：按 context_slots 顺序追加
    - 向后兼容现有 `compose(template_name, context)` 单模板接口
  - **Part 2: ask 路径迁移到 PromptComposer**
    - 替换 `deepseek_llm.py` 中硬编码 `_SYSTEM_PROMPT`（第30-41行）为 PromptComposer
    - `DeepSeekLlmClient` 新增可选 `system_prompt: str` 参数（Service 层预渲染后传入）
    - 不改变 ask 的 JSON user message 格式和 tool schemas
    - 不改变 Profile Routing + augmented_query 机制
  - 测试：fragment 装配正确性 / contribution 注入 / 向后兼容 / ask 路径行为不变

  **Must NOT do**:
  - 不改变现有 `compose()` 单模板调用方
  - 不改变 ask 的 user message 和 tool schemas
  - 不将 scene config 与 LLM 运行时耦合

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with 7A-7D, 7F)
  - **Blocks**: 7G, 7I

  **References**:
  - `fund_agent/service/prompt_composer.py:compose()` — 现有单模板渲染
  - `fund_agent/agent/deepseek_llm.py:30-41` — 现有硬编码 _SYSTEM_PROMPT
  - Dayu: `dayu/prompting/prompt_composer.py:compose()` — fragment 装配

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/service/test_prompt_composer_upgrade.py` 新建
  - [ ] `uv run pytest tests/fund/service/test_prompt_composer_upgrade.py` → PASS（≥6 tests）
  - [ ] 回退：`uv run pytest tests/fund/cli/test_cli.py -k ask` → PASS（ask 不变）
  - [ ] 回退：`uv run pytest tests/fund/service/test_prompt_composer.py` → PASS
  - [ ] ask 路径验证：`uv run pytest tests/fund/agent/test_real_llm_adapter.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: fragment 装配 + ask 不变
    Tool: Bash (pytest)
    Steps:
      1. 用 2 fragments 组装 system_prompt
      2. assert system_prompt 包含 fragment 内容且按 order 排序
      3. 用该 system_prompt 创建 DeepSeekLlmClient → next_step
      4. assert ask 行为的 answer/citations 格式不变
    Expected Result: 新旧路径输出格式一致
    Evidence: .sisyphus/evidence/task-7e-compose-ask.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): PromptComposer fragment assembly + ask path migration`
  - Files: `fund_agent/service/prompt_composer.py`, `fund_agent/agent/deepseek_llm.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_prompt_composer.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/cli/test_cli.py -k ask`

- [ ] 7F. Interactive + Ask 双 Scene Config + Fragment 模板 + Prompt Contributions

  **What to do**:
  - **Part 1: Scene 配置**
    - `fund_agent/service/scene_config.py`：SceneConfig 数据类 + `ASK_SCENE_CONFIG` + `INTERACTIVE_SCENE_CONFIG`
    - `ASK_SCENE_CONFIG`：4 fragments（base_agents, base_soul, base_fact_rules, ask_tools_scene）
    - `INTERACTIVE_SCENE_CONFIG`：5 fragments（+ interactive_scene, + conversation context_slot）
  - **Part 2: Fragment 模板**
    - `fund_agent/service/prompts/base/agents.md` — 身份定义（共用）
    - `fund_agent/service/prompts/base/soul.md` — 分析哲学（共用）
    - `fund_agent/service/prompts/base/fact_rules.md` — 事实规则（共用）
    - `fund_agent/service/prompts/ask/tools_scene.md` — ask 工具约束 + 场景指令
    - `fund_agent/service/prompts/interactive/scene.md` — interactive 场景指令（含对话规则）
  - **Part 3: Prompt Contributions**
    - `fund_agent/service/prompt_contributions.py`
    - `build_runtime_contribution()` / `build_fund_context_contribution()` / `build_memory_contribution()`
    - `select_contributions(raw, context_slots) → dict`

  **Must NOT do**:
  - episode summary 内容先为空占位

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with 7A-7E)
  - **Blocks**: 7G, 7I

  **References**:
  - Dayu: `dayu/config/prompts/manifests/interactive.json` — fragment 列表
  - Dayu: `workspace/prompts/base/agents.md` / `soul.md` / `fact_rules.md` — 内容参考
  - Dayu: `dayu/services/prompt_contributions.py` — build + select 模式
  - `fund_agent/service/prompts/system_base.md` — 现有模板风格

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/service/test_scene_config.py` 新建
  - [ ] 测试文件：`tests/fund/service/test_prompt_contributions.py` 新建
  - [ ] `uv run pytest tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py` → PASS（≥10 tests）

  **QA Scenarios**:
  ```
  Scenario: ASK_SCENE_CONFIG 渲染 ask prompt
    Tool: Bash (pytest)
    Steps:
      1. composer.compose_from_scene(ASK_SCENE_CONFIG, contributions)
      2. assert system_prompt 包含 "fund-checklist" 和 "annual report"
      3. assert system_prompt 不包含 "会话"（interactive 特有）
    Expected Result: ask 用简洁 prompt，interactive 用完整 prompt
    Evidence: .sisyphus/evidence/task-7f-scene-config.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): dual scene config + fragment templates + prompt contributions`
  - Files: `fund_agent/service/scene_config.py`, `fund_agent/service/prompt_contributions.py`, `fund_agent/service/prompts/base/*.md`, `fund_agent/service/prompts/ask/*.md`, `fund_agent/service/prompts/interactive/scene.md`
  - Pre-commit: `uv run pytest tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py`

- [ ] 7G. Service 层 chat_turn use case

  **What to do**:
  - 创建 `fund_agent/service/chat_service.py`：`ChatService` 类
  - 实现 `chat_turn(request: ChatTurnRequest) → ChatTurnResult` 方法
  - ChatTurnRequest：session_id / user_text / document_id（可选，无则用 PinnedState 的 active_document_id）
  - ChatTurnResult：answer / citations / tool_trace / stream_events / token_usage
  - 核心逻辑：
    1. 加载 Session → 读取 PinnedState + Recent Turns + Episode Summary
    2. 调用 PromptComposer 组装 system_prompt（fragments + context_slots + memory）
    3. 调用 Host.run_agent_stream()（复用 7G 的 Host 能力）
    4. 收集 StreamEvent → 构建 ChatTurnResult
    5. 投资建议检测：每轮输出经 `contains_investment_advice()` 检查
    6. 更新 Session：追加 Turn、更新 PinnedState、更新 token 累计
  - 测试：单轮对话 / 多轮上下文传递 / 投资建议拦截 / token 累计

  **Must NOT do**:
  - 不实现 Episode Summary 触发（留给 7K）
  - 不实现上下文预算裁剪（留给 7L）
  - 不直接操作 SessionStore（通过 7G Host）

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with 7G, 7H)
  - **Blocks**: 7I
  - **Blocked By**: 7A, 7B, 7E

  **References**:
  - `fund_agent/service/extraction.py:ask_question()` — 现有 ask 路径参考（profile routing、augmented query、runner factory）
  - `fund_agent/service/models.py:AskQuestionRequest` — 现有 DTO 模式
  - `fund_agent/service/session_models.py` — 7A 定义的 Session/Turn/PinnedState
  - Dayu: `dayu/services/chat_service.py` — ChatService 的 submit + wait 模式

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/service/test_chat_service.py` 新建
  - [ ] `uv run pytest tests/fund/service/test_chat_service.py` → PASS（≥8 tests）

  **QA Scenarios**:

  ```
  Scenario: 单轮对话
    Tool: Bash (pytest)
    Steps:
      1. session = create_session(fund_code="011649", active_document_id="011649-2025-...")
      2. result = chat_service.chat_turn(ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁？"))
      3. assert result.answer 包含 "经理"
      4. assert len(result.citations) > 0
    Expected Result: 回答非空，含 citation
    Evidence: .sisyphus/evidence/task-7f-single-turn.txt

  Scenario: 多轮上下文传递
    Tool: Bash (pytest)
    Steps:
      1. turn1: "基金经理是谁？" → answer1
      2. turn2: "他的任期有多长？" → answer2 (应理解"他"指 turn1 的经理)
      3. assert answer2 包含任期信息
    Expected Result: turn2 基于 turn1 上下文回答
    Evidence: .sisyphus/evidence/task-7f-multi-turn.txt

  Scenario: 投资建议拦截
    Tool: Bash (pytest)
    Steps:
      1. 模拟 LLM 返回含 "建议买入该基金" 的内容
      2. chat_turn() 应抛出或返回错误
    Expected Result: 投资建议被拦截
    Evidence: .sisyphus/evidence/task-7f-guard.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): Service layer chat_turn use case`
  - Files: `fund_agent/service/chat_service.py`, `fund_agent/service/models.py`
  - Pre-commit: `uv run pytest tests/fund/service/test_chat_service.py`

- [ ] 7H. Host 多轮会话托管

  **What to do**:
  - 扩展 `fund_agent/host/minimal_host.py`：`MinimalHost` 新增 session 管理能力
  - 新增方法：
    - `create_session(fund_code, ...) → Session`
    - `get_session(session_id) → Session`
    - `list_sessions() → list[Session]`
    - `close_session(session_id)`
  - Session 生命周期：ACTIVE → CLOSED
  - 复用 7A 的 `SessionStore` 做持久化
  - 新增 `run_chat_turn(session, user_text, ...)` 方法：
    - 从 session 读取记忆层
    - 组装 messages（system_prompt + memory + current turn）
    - 调用 LlmToolLoopRunner.run_stream()
    - 更新 session 状态
  - 测试：会话创建/关闭 / 记忆层传递 / token 累计更新

  **Must NOT do**:
  - 不实现 Episode Summary 压缩（留给 7K）
  - 不实现并发治理
  - 不实现 pending turn / reply outbox

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with 7F, 7H)
  - **Blocks**: 7I
  - **Blocked By**: 7A

  **References**:
  - `fund_agent/host/minimal_host.py:run_agent_stream()` — 现有 Host 流式执行模式
  - `fund_agent/host/session_store.py` — 7A 定义的 SessionStore
  - `fund_agent/service/session_models.py` — 7A 定义的 Session/Turn/PinnedState
  - Dayu: `dayu/host/conversation_memory.py:DefaultConversationMemoryManager.build_messages()` — 记忆 → messages 转换

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/host/test_minimal_host_session.py` 新建
  - [ ] `uv run pytest tests/fund/host/test_minimal_host_session.py` → PASS（≥6 tests）
  - [ ] 回退：`uv run pytest tests/fund/agent/test_stream_events.py` → PASS

  **QA Scenarios**:

  ```
  Scenario: 会话生命周期
    Tool: Bash (pytest)
    Steps:
      1. session = host.create_session(fund_code="011649")
      2. assert session.status == "ACTIVE"
      3. host.close_session(session.session_id)
      4. assert host.get_session(session.session_id).status == "CLOSED"
    Expected Result: 状态转换正确
    Evidence: .sisyphus/evidence/task-7g-lifecycle.txt

  Scenario: 记忆层传递
    Tool: Bash (pytest)
    Steps:
      1. 创建 session，PinnedState 含 fund_code
      2. run_chat_turn → 检查 LLM 收到的 system_prompt 包含 fund_code
    Expected Result: PinnedState 注入到 prompt
    Evidence: .sisyphus/evidence/task-7g-memory.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): Host multi-turn session lifecycle management`
  - Files: `fund_agent/host/minimal_host.py`
  - Pre-commit: `uv run pytest tests/fund/host/test_minimal_host_session.py tests/fund/agent/test_stream_events.py`

- [ ] 7I. CLI interactive 子命令（prompt_toolkit + 基础 REPL）

  **What to do**:
  - 在 `fund_agent/cli/main.py` 注册 `interactive` 子命令
  - 参数：`--fund-code`（必填）、`--work-dir`、`--label`、`--no-stream`、`--enable-tool-trace`
  - REPL 启动流程：
    1. 调用 `FundReadingService.resolve_by_fund_code(fund_code)` 获取可用年份
    2. **富 REPL** 展示可用年份列表，提示用户选择默认年份
    3. 创建/加载 Session
    4. 进入 prompt_toolkit REPL 循环
  - REPL 输入处理：
    - 以 `/` 开头 → 命令解析（本 Slice 只实现 /help, /clear, exit/quit）
    - 其他 → 调用 `ChatService.chat_turn()`
  - 输出渲染（基础版）：
    - 流式输出经 `StreamEvent` 回调 → 逐字打印
    - 无 rich Markdown 渲染（留给 7N）
  - 测试：CLI 启动 / 基本对话 / 退出 / 帮助命令

  **Must NOT do**:
  - 不实现 /history /document /fund /label /save /export /stats /model /verbose（留给 7M）
  - 不实现 rich Markdown 渲染（留给 7N）
  - 不破坏现有 ask 子命令

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with 7F, 7G)
  - **Blocks**: 7I, 7J
  - **Blocked By**: 7B, 7E

  **References**:
  - `fund_agent/cli/main.py:_run_ask_command()` — CLI 子命令 + 流式回调模式
  - `fund_agent/cli/main.py:register_parser()` — 子命令注册方式
  - `fund_agent/service/scene_config.py` — 7E 的 INTERACTIVE_SCENE_CONFIG
  - Dayu: prompt_toolkit 的 `PromptSession` + `HTML`/`ANSI` 格式化

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/cli/test_cli_interactive.py` 新建
  - [ ] `uv run pytest tests/fund/cli/test_cli_interactive.py` → PASS（≥6 tests）
  - [ ] 回退：`uv run pytest tests/fund/cli/test_cli.py -k ask` → PASS

  **QA Scenarios**:

  ```
  Scenario: interactive 启动并选择年份
    Tool: interactive_bash (tmux)
    Preconditions: catalog 含 011649 的 2021-2025 年文档
    Steps:
      1. send-keys: "uv run fund-checklist interactive --fund-code 011649 --work-dir /tmp/test_interactive"
      2. 等待输出 "可用年份"
      3. assert 输出包含 "2021, 2022, 2023, 2024, 2025"
      4. send-keys: "2025" Enter
      5. 等待 REPL 提示符 ">"
    Expected Result: 进入 REPL，显示 "011649"
    Evidence: .sisyphus/evidence/task-7h-startup.txt

  Scenario: 基本对话
    Tool: interactive_bash (tmux)
    Steps:
      1. send-keys: "基金经理是谁？" Enter
      2. 等待流式输出
      3. assert 输出包含 citation
    Expected Result: 正常回答
    Evidence: .sisyphus/evidence/task-7h-chat.txt

  Scenario: /help 和退出
    Tool: interactive_bash (tmux)
    Steps:
      1. send-keys: "/help" Enter
      2. assert 输出包含可用命令列表
      3. send-keys: "exit" Enter
      4. 等待 exit code 0
    Expected Result: 正常退出
    Evidence: .sisyphus/evidence/task-7h-exit.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): CLI interactive subcommand with prompt_toolkit REPL`
  - Files: `fund_agent/cli/main.py`, `pyproject.toml`（如新增依赖）
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/cli/test_cli.py`

- [ ] 7J. Integration: wire-up chat_turn → Host → CLI → PromptComposer 全链路

  **What to do**:
  - 将 7G/7H/7I 的实现串联为完整 interactive 对话通路
  - 修改 `_run_interactive_command()`：集成 ChatService + MinimalHost + SessionStore
  - 修改 `ChatService.chat_turn()`：调用 PromptComposer.compose_from_scene() + Host.run_chat_turn()
  - ask 路径已通过 7E 迁移到 PromptComposer（不在此 Slice 范围）
  - 流式输出与 StreamEvent 回调链路完整
  - 测试：全链路 smoke / 流式输出完整性 / 错误传播

  **Must NOT do**:
  - 不改动 ask 路径（7E 已完成迁移）
  - 不实现 Episode Summary 逻辑（留给 7L）

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (before 7L)
  - **Blocks**: 7L, 7M, 7N, 7O
  - **Blocked By**: 7G, 7H, 7I

  **References**:
  - `fund_agent/cli/main.py:_run_ask_command()` — 全链路 wiring 参考
  - `fund_agent/service/extraction.py:ask_question()` — Service → Host → runner 模式
  - 所有 Wave 1-2 产物

  **Acceptance Criteria** (TDD):
  - [ ] 扩展测试：`tests/fund/cli/test_cli_interactive.py` 增加全链路测试
  - [ ] `uv run pytest tests/fund/cli/test_cli_interactive.py -k integration` → PASS（≥3 tests）
  - [ ] 回退：`uv run pytest tests/fund/cli/test_cli.py` → PASS

  **QA Scenarios**:

  ```
  Scenario: 全链路 smoke（3 轮对话）
    Tool: interactive_bash (tmux)
    Steps:
      1. 启动 interactive --fund-code 011649
      2. turn1: "基金经理是谁？" → 含名字
      3. turn2: "任期多久？" → 含年份
      4. turn3: "规模多大？" → 含数字
    Expected Result: 3 轮均正常，上下文正确
    Evidence: .sisyphus/evidence/task-7i-smoke.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): integrate chat_turn → Host → CLI full interactive pipeline`
  - Files: `fund_agent/cli/main.py`, `fund_agent/service/chat_service.py`, `fund_agent/host/minimal_host.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/cli/test_cli.py`

- [ ] 7K. 会话恢复 + --label 支持

  **What to do**:
  - `--label my-session` 参数：启动时查找 `{work_dir}/sessions/my-session.json`
  - 若存在 → 加载历史 Session，显示历史 turns 摘要，恢复 PinnedState
  - 若不存在 → 创建新 session，label 映射到 session_id
  - 新增 `/label <name>` REPL 命令：为当前会话设置标签
  - session label 与 session_id 的双向映射：`{work_dir}/sessions/labels.json`
  - 测试：创建→退出→恢复 / label 冲突 / 不存在的 label

  **Must NOT do**:
  - 不实现 pending turn lease 或 resume lease
  - 不保证多进程恢复安全

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with 7I)
  - **Blocks**: None
  - **Blocked By**: 7A, 7H

  **References**:
  - `fund_agent/host/session_store.py` — 7A SessionStore
  - `fund_agent/cli/main.py:_run_ask_command()` — CLI 参数解析模式
  - Dayu: pending turn + resume lease 概念（简化版参照）

  **Acceptance Criteria** (TDD):
  - [ ] 扩展测试：`tests/fund/cli/test_cli_interactive.py` 增加恢复测试
  - [ ] `uv run pytest tests/fund/cli/test_cli_interactive.py -k resume` → PASS（≥4 tests）

  **QA Scenarios**:

  ```
  Scenario: 会话恢复
    Tool: interactive_bash (tmux)
    Steps:
      1. 启动: uv run fund-checklist interactive --fund-code 011649 --label test-resume
      2. turn: "基金经理是谁？" → answer
      3. exit
      4. 重新启动: --label test-resume
      5. assert 显示 "[恢复会话 test-resume]"
      6. turn: "他的任期？" → 应基于之前上下文回答
    Expected Result: 历史上下文恢复
    Evidence: .sisyphus/evidence/task-7j-resume.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): session resume with --label support`
  - Files: `fund_agent/cli/main.py`, `fund_agent/host/session_store.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli_interactive.py`

- [ ] 7L. Episode Summary（异步 LLM 压缩）

  **What to do**:
  - 实现触发条件：`total_turns >= 10 OR total_tokens >= max_context * 0.6`
  - 实现异步生成：`threading.Thread` 后台调用 LLM
  - LLM 调用：复用 `DeepSeekLlmClient.generate_text()`，传入结构化 prompt
    - 输入：PinnedState + 待压缩 Turn 列表（最老的 N 轮）
    - 输出 JSON：`{title, goal, confirmed_facts, open_questions, next_step}`
  - 压缩后：更新 Session.episode_summaries，推进 compacted_turn_count
  - 压缩使用独立的 `"conversation_compaction"` prompt 模板
  - 不阻塞主对话：后台线程完成前，继续使用旧 memory
  - 测试：触发条件 / 压缩结果落盘 / 不阻塞主线程

  **Must NOT do**:
  - 不压缩最近 4 轮（compaction_tail_preserve_turns=4）
  - 不同步压缩（不阻塞用户输入）
  - 单次压缩不超过 1 轮（避免 LLM 调用风暴）

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (after 7I)
  - **Blocks**: 7L
  - **Blocked By**: 7D, 7I

  **References**:
  - `fund_agent/host/minimal_host.py` — `threading.Thread` + `queue.Queue` 的流式执行模式
  - `fund_agent/agent/deepseek_llm.py:generate_text()` — 非流式 LLM 调用
  - Dayu: `dayu/host/conversation_memory.py:DefaultEpisodicMemoryCompressor.compress()` — 压缩 prompt 结构
  - Dayu: `dayu/host/conversation_memory.py:schedule_compaction()` — 后台调度模式
  - Dayu: `dayu/config/prompts/manifests/conversation_compaction.json` — compaction scene 配置

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/host/test_episode_summary.py` 新建
  - [ ] `uv run pytest tests/fund/host/test_episode_summary.py` → PASS（≥6 tests）

  **QA Scenarios**:

  ```
  Scenario: 触发条件 → 异步压缩
    Tool: Bash (pytest)
    Steps:
      1. 创建 session，手动填充 10 轮对话
      2. 调用 chat_turn（第 11 轮）
      3. assert episode_summary 压缩已触发（后台线程启动）
      4. 等待线程完成
      5. assert session.episodes 非空
      6. assert session.compacted_turn_count > 0
    Expected Result: 后台压缩完成，episode summary 落盘
    Evidence: .sisyphus/evidence/task-7k-compaction.txt

  Scenario: 压缩不阻塞主对话
    Tool: Bash (pytest)
    Steps:
      1. 填充 10 轮对话
      2. 立即发送第 11 轮问题（不等压缩完成）
      3. assert 第 11 轮回答正常返回
    Expected Result: 压缩不影响用户交互
    Evidence: .sisyphus/evidence/task-7k-nonblocking.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): Episode Summary async LLM compaction`
  - Files: `fund_agent/host/minimal_host.py`, `fund_agent/service/chat_service.py`, `fund_agent/service/prompts/interactive/compaction.md`
  - Pre-commit: `uv run pytest tests/fund/host/test_episode_summary.py`

- [ ] 7M. 上下文预算治理（软/硬上限 + 工具结果裁剪）

  **What to do**:
  - 创建 `fund_agent/agent/context_budget.py`
  - `ContextBudgetState`：max_context_tokens / soft_limit_ratio(0.75) / hard_limit_ratio(0.9) / current_prompt_tokens
  - 软上限：超过 75% 时，对 Episode Summary + Older Turns 按 budget 截断
  - 硬上限：超过 90% 时，触发 `_compact_messages()` 应急压缩（保留 system + 最近 6 条消息）
  - `ToolResultBudgetCapper`：升序公平分配，MIN_RESULT_TOKENS=2000，截断后追加 `[CONTEXT_BUDGET_TRUNCATED]` 标记
  - 与 7D token 追踪集成：每次 LLM 调用后 `budget_state.record_usage(usage)`
  - 与 7K Episode Summary 集成：软上限触发时优先触发压缩
  - 测试：软上限裁减 / 硬上限应急 / 工具结果裁剪 / context_overflow 恢复

  **Must NOT do**:
  - 不使用 tiktoken 客户端估算
  - 不做 `_compact_messages` 的 OpenAI 专有格式依赖

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with 7M, 7N)
  - **Blocks**: 7O
  - **Blocked By**: 7D, 7K

  **References**:
  - `fund_agent/agent/deepseek_llm.py:ChatResponse` — 7D 新增的 cumulative_usage
  - Dayu: `dayu/engine/context_budget.py:ContextBudgetState` — 软/硬上限 + 状态管理
  - Dayu: `dayu/engine/context_budget.py:ToolResultBudgetCapper.cap_results_for_budget()` — 升序公平分配
  - Dayu: `dayu/host/conversation_memory.py:DefaultWorkingMemoryPolicy` — 单总池预算解析

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/agent/test_context_budget.py` 新建
  - [ ] `uv run pytest tests/fund/agent/test_context_budget.py` → PASS（≥8 tests）

  **QA Scenarios**:

  ```
  Scenario: 工具结果裁剪
    Tool: Bash (pytest)
    Steps:
      1. budget = ContextBudgetState(max_context_tokens=8000, current_prompt_tokens=6000)
      2. 准备 3 个工具结果（各 2000 tokens 估算）
      3. capped = ToolResultBudgetCapper.cap_results_for_budget(results, budget)
      4. assert 部分结果被截断，标记 [CONTEXT_BUDGET_TRUNCATED]
    Expected Result: 小结果优先完整，大结果按比例截断
    Evidence: .sisyphus/evidence/task-7l-capping.txt

  Scenario: 硬上限应急压缩
    Tool: Bash (pytest)
    Steps:
      1. 填充 messages 到超过 hard_limit
      2. 触发 _compact_messages()
      3. assert 压缩后 messages 数减少
      4. assert system message 和最新 user message 保留
    Expected Result: 中间轮次被压缩为 summary
    Evidence: .sisyphus/evidence/task-7l-emergency.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): context budget governance with soft/hard limits`
  - Files: `fund_agent/agent/context_budget.py`
  - Pre-commit: `uv run pytest tests/fund/agent/test_context_budget.py`

- [ ] 7N. 扩展命令 + 多文档切换

  **What to do**:
  - 在 REPL 中实现扩展命令集：
    - `/history` — 显示最近 N 轮对话（默认 10 轮）
    - `/document <year>` — 切换 active_document_id 到指定年份
    - `/fund <code>` — 切换到新基金（需重新选择年份）
    - `/stats` — 显示当前 session 统计（turns / tokens / episodes）
    - `/save [path]` — 导出会话为 Markdown（对话记录）
    - `/export [path]` — 导出会话为 JSON（完整 session 数据）
    - `/model <name>` — 切换 LLM 模型（可选）
    - `/verbose` — 切换详细模式（显示 tool trace）
    - `/label <name>` — 更新会话标签
  - 多文档切换：`/document 2024` → 更改 PinnedState.active_document_id + active_year
  - 测试：每个命令的基本功能

  **Must NOT do**:
  - 不实现 `/model` 的实际模型切换逻辑（只预留接口）
  - 切换文档后不做历史 turns 清理（保留完整记录）

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with 7L, 7N)
  - **Blocks**: 7O
  - **Blocked By**: 7I

  **References**:
  - `fund_agent/cli/main.py:_run_interactive_command()` — 7H/7I 的 REPL 命令解析逻辑
  - `fund_agent/host/session_store.py` — session 数据导出

  **Acceptance Criteria** (TDD):
  - [ ] 扩展测试：`tests/fund/cli/test_cli_interactive.py` 增加命令测试
  - [ ] `uv run pytest tests/fund/cli/test_cli_interactive.py -k commands` → PASS（≥8 tests）

  **QA Scenarios**:

  ```
  Scenario: /history 显示历史
    Tool: interactive_bash (tmux)
    Steps:
      1. 启动 interactive 并完成 3 轮对话
      2. send-keys: "/history" Enter
      3. assert 输出包含前 3 轮 user/assistant 内容
    Evidence: .sisyphus/evidence/task-7m-history.txt

  Scenario: /document 切换年份
    Tool: interactive_bash (tmux)
    Steps:
      1. 启动后默认 2025
      2. send-keys: "/document 2023" Enter
      3. assert 输出 "已切换到 2023 年年报"
      4. 提问 → 应使用 2023 年文档
    Evidence: .sisyphus/evidence/task-7m-document.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): extended REPL commands + multi-document support`
  - Files: `fund_agent/cli/main.py`
  - Pre-commit: `uv run pytest tests/fund/cli/test_cli_interactive.py`

- [ ] 7O. Rich Markdown 渲染

  **What to do**:
  - 在 REPL 输出路径中集成 `rich` 库
  - LLM 回答经 `rich.markdown.Markdown` 渲染后再输出
  - 支持：标题、列表、加粗/斜体、代码块（语法高亮）、表格
  - 工具调用追踪用 `rich.panel.Panel` 展示
  - 错误/警告用 `rich.console.Console(stderr=True)` 红色输出
  - `/verbose` 模式切换：显示/隐藏原始 JSON
  - 测试：Markdown 渲染正确性 / 表格对齐 / 代码块高亮

  **Must NOT do**:
  - 不改变非 interactive 模式（ask/read/generate）的输出格式
  - 不在 ANSI 不可用终端崩溃

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with 7L, 7M)
  - **Blocks**: 7O
  - **Blocked By**: 7I

  **References**:
  - `fund_agent/cli/main.py:_run_interactive_command()` — 7I 的 REPL 输出路径
  - rich 官方文档：`from rich.markdown import Markdown; console.print(Markdown(text))`
  - rich 官方文档：`from rich.panel import Panel; console.print(Panel(content, title="Tool"))`

  **Acceptance Criteria** (TDD):
  - [ ] 测试文件：`tests/fund/cli/test_rich_render.py` 新建
  - [ ] `uv run pytest tests/fund/cli/test_rich_render.py` → PASS（≥5 tests）

  **QA Scenarios**:

  ```
  Scenario: Markdown 表格渲染
    Tool: Bash (Python REPL)
    Steps:
      1. 输入含 Markdown 表格的 LLM 回答
      2. render = Markdown(answer)
      3. console = Console(file=StringIO())
      4. console.print(render)
      5. assert 输出含 ANSI 表格线
    Expected Result: 表格正确渲染
    Evidence: .sisyphus/evidence/task-7n-table.txt

  Scenario: 代码块语法高亮
    Tool: Bash (Python REPL)
    Steps:
      1. 输入含 ```python ... ``` 代码块的回答
      2. 渲染后 assert 输出含 ANSI 颜色码
    Expected Result: 代码正确高亮
    Evidence: .sisyphus/evidence/task-7n-syntax.txt
  ```

  **Commit**: YES
  - Message: `feat(phase7): Rich Markdown rendering for interactive REPL`
  - Files: `fund_agent/cli/main.py`, `pyproject.toml`
  - Pre-commit: `uv run pytest tests/fund/cli/test_rich_render.py`

- [ ] 7P. 端到端验证 + 全量回归（基金 011649）

  **What to do**:
  - 准备测试数据：确保 011649 的 2021-2025 年年报已导入 catalog
  - 执行完整 interactive 流程验证：
    1. 启动 → 选择年份
    2. 3 轮上下文对话（基金经理、任期、规模）
    3. /document 切换 → 切换后新文档上下文
    4. /history → 验证历史显示
    5. /save → 导出会话 Markdown
    6. exit → 验证 session 落盘
    7. --label 恢复 → 验证恢复
    8. 投资建议检测：输入 "建议买入" → 被拦截
    9. 10+ 轮长对话 → 验证 Episode Summary 触发
  - 全量回归测试：
    - `fund-checklist ask` 所有现有行为不变
    - `fund-checklist read` 不变
    - `fund-checklist multi-year / import / holdings / allocation / fees / audit / deep-audit / generate / download` 全部可用
  - 收集 evidence 到 `.sisyphus/evidence/phase7-e2e/`

  **Must NOT do**:
  - 不做 LLM 输出质量评估（只验证功能通路）
  - 不做性能基准测试

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`git-master`]
  - **Skills Evaluated but Omitted**: none

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (after Wave 4)
  - **Blocks**: F1-F4
  - **Blocked By**: 7L, 7M, 7N

  **References**:
  - 原 Phase 7 计划 `.sisyphus/goals/phase7-interactive-011649.md` 验证标准
  - `tests/fund/cli/test_cli.py` — 现有 CLI 测试模式

  **Acceptance Criteria**:
  - [ ] E2E 脚本：`.sisyphus/evidence/phase7-e2e/run.sh`（所有步骤 exit code 0）
  - [ ] 全量回归：`uv run pytest tests/fund/` → 全部 PASS
  - [ ] 新增测试全部 PASS：`uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_minimal_host_session.py tests/fund/host/test_episode_summary.py tests/fund/agent/test_context_budget.py tests/fund/agent/test_token_usage.py`

  **QA Scenarios**:

  ```
  Scenario: 011649 完整流程
    Tool: interactive_bash (tmux)
    Steps:
      1. import 5 年年报（如未导入）
      2. uv run fund-checklist interactive --fund-code 011649
      3. 选择 2025
      4. > 基金经理是谁？ → 验证回答含名字
      5. > 任期有多长？ → 验证含年份
      6. > 规模多大？ → 验证含数字
      7. > /document 2023 → 验证切换
      8. > 持仓前十 → 验证含 2023 持仓
      9. > /history → 含前 4 轮
      10. > /save /tmp/test-session.md → 验证文件
      11. > exit → exit 0
    Expected Result: 所有步骤成功
    Evidence: .sisyphus/evidence/phase7-e2e/full-flow.txt

  Scenario: 投资建议拦截验证
    Tool: interactive_bash (tmux)
    Steps:
      1. 启动 interactive
      2. > 建议买入该基金
      3. assert 输出含 "投资建议" 或 "不支持" 或 "无法回答"
    Expected Result: 拦截成功
    Evidence: .sisyphus/evidence/phase7-e2e/guard.txt
  ```

  **Commit**: YES
  - Message: `test(phase7): end-to-end verification for fund 011649 + full regression`
  - Files: `tests/fund/cli/test_cli_interactive.py`, `.sisyphus/evidence/phase7-e2e/`
  - Pre-commit: `uv run pytest tests/fund/`

---

## Final Verification Wave

> 4 个 review agent 并行运行。ALL must APPROVE。提交综合结果给用户获取明确 "okay"。
> **禁止自动通过**。用户拒绝或反馈 → 修复 → 重新运行 → 再次提交 → 等待 okay。

- [ ] F1. **Plan Compliance Audit** — `oracle`
  通读计划。对每个 "Must Have"：验证实现存在（读文件、curl 端点、运行命令）。对每个 "Must NOT Have"：搜索代码库中的禁止模式——如发现则以 `file:line` 拒绝。检查 `.sisyphus/evidence/` 中的证据文件。对照交付物检查。
  输出：`Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  运行 `uv run ruff check .` + `uv run pytest tests/fund/`。审查所有变更文件：`as any`/`@ts-ignore`、空 catch、console.log、注释掉的代码、未使用的导入。检查 AI slop：过多注释、过度抽象、通用命名（data/result/item/temp）。
  输出：`Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  从干净状态启动。执行 7O 中的所有 QA 场景——遵循精确步骤，捕获证据。测试跨任务集成（功能协同工作而非隔离）。测试边界情况：空状态、无效输入、快速操作。保存到 `.sisyphus/evidence/final-qa/`。
  输出：`Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  对每个任务：读取 "What to do"，读取实际 diff（git log/diff）。验证 1:1 —— 规范中的所有内容均已构建（无遗漏），规范之外的内容未构建（无 scope creep）。检查 "Must NOT do" 合规性。检测跨任务污染：Task N 触碰 Task M 的文件。标记未记录的变更。
  输出：`Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **7A-7E** (Wave 1): 5 个独立提交，可同时 push
- **7F-7H** (Wave 2): 3 个独立提交
- **7I-7K** (Wave 3): 顺序提交（7I → 7J/7K 并行）
- **7L-7N** (Wave 4): 3 个独立提交
- **7O** (Wave 5): 1 个提交
- 每个提交含 pre-commit 测试命令

---

## Success Criteria

### Verification Commands

```bash
# Phase 7 核心测试
uv run pytest tests/fund/cli/test_cli_interactive.py \
  tests/fund/service/test_chat_service.py \
  tests/fund/host/test_minimal_host_session.py \
  tests/fund/host/test_episode_summary.py \
  tests/fund/agent/test_context_budget.py \
  tests/fund/agent/test_token_usage.py \
  tests/fund/service/test_prompt_composer_upgrade.py \
  tests/fund/service/test_scene_config.py \
  tests/fund/service/test_prompt_contributions.py \
  tests/fund/service/test_fund_code_resolution.py \
  tests/fund/service/test_investment_guard.py \
  tests/fund/service/test_session_models.py \
  tests/fund/host/test_session_store.py \
  tests/fund/cli/test_rich_render.py \
  -v --tb=short

# 全量回归（不破坏现有功能）
uv run pytest tests/fund/ -v --tb=short

# Phase 5 ask 回归
uv run pytest tests/fund/agent/test_stream_events.py \
  tests/fund/agent/test_llm_production_readiness.py \
  tests/fund/agent/test_llm_tool_loop.py \
  tests/fund/cli/test_cli.py -k ask \
  -v --tb=short
```

### Final Checklist

- [ ] 所有 15 个 Slice 实现完成
- [ ] 所有 "Must Have" 实现并验证
- [ ] 所有 "Must NOT Have" 未违反
- [ ] 全量回归通过（≥200 tests）
- [ ] ask 命令行为不变
- [ ] interactive --fund-code 011649 端到端通过
- [ ] 投资建议检测每轮生效
- [ ] Episode Summary 异步触发并落盘
- [ ] 上下文预算裁减生效
- [ ] 会话恢复 --label 可用
- [ ] F1-F4 全部 APPROVE
