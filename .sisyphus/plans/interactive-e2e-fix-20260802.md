# 2026-08-02 interactive e2e 失败修复计划（细化稿）

> 来源：`.sisyphus/tasks/20260802-interactive-fix-brief.md`（08-01 23:51 e2e：`uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace`，9 问，4 成功 / 5 失败 / 2 误拦截）。
> 本任务只写计划：不实现代码、不改测试、不 commit、不 push、不写 review。

---

## 0. 总控口径（Controller 验收）

- 流程：CIC-lite，每个 slice 只走 `implement -> tests -> diff review`；review 输出只能是 `ACCEPTED` / `NEEDS_FIX`。
- 唯一计划产物：本文件。实现阶段不允许再新增 plan-fix / re-review / evidence gate。
- 工作区未提交 WIP（B1 投资建议强弱词豁免、B2 document_id runtime contribution 注入）是本计划基线，**已存在，不得重复规划或回退**；实现 slice 只在其之上增量修改。
- 默认 pytest 不得联网、不得读取真实 API key、不得记录 raw provider response；live e2e smoke 必须显式 opt-in，只作为整体验收（总控手动执行），不作为 slice 单元验证。
- 预检（DS 只核对现状，不执行修复）：`uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_chat_service.py -q --tb=short`。
- 每个 slice 的 diff 必须只包含其 allowed write set 内的文件；write set 之外出现任何改动即 review 拒绝。

### Slice 顺序与依赖

```text
S0（调试盲区，必须最先）→ S1（P0-a）→ S2（P1-b）→ S3（P1-a，依赖口径确认）→ S4（P2）→ S5（doc-sync）
```

- S0 先行：失败轮 trace / session 不可见时，其余 slice 的 e2e 验证无法取证。
- S1 与 S4 都改 `fund_agent/service/prompts/` 下两个 fragment 文件，必须串行（S4 在 S1 review 通过后执行），禁止并行提交同一文件。
- S3 依赖 B1 口径 owner 确认（见 §5）；未确认前 S3 挂起，不影响 S0/S1/S2/S4 推进。
- S5 最后执行，且只在全部实现 slice review 通过后启动。

### 整体验收（全部 slice 完成后，总控手动执行）

1. repo 最小验证命令：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`。
2. interactive 相关验证：`uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_stream_events.py -v --tb=short`。
3. opt-in live e2e：`uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace` 重跑原 9 问。
4. 验收目标：9 问中 0 条 `LLM 处理失败`（工具失败可自愈或正确降级为"未找到"声明）；2 条误拦截（前十大重仓股 / 基金风格一致）不再被投资建议检测拦截；失败轮在 session 中可见（含 tool_trace 与被拦截原文）。S3 口径未确认时，该 slice 的豁免验收项挂起，其余验收项不挂起。

---

## 1. 失败证据 → 根因映射（代码事实）

| # | 现象 | 用户可见错误 | 代码证据 | 根因 | 对应 slice |
|---|------|-------------|---------|------|-----------|
| 1 | 基金规模是多大 / 港股持仓情况是什么 | `LLM 处理失败：章节不存在` | `docling_store._find_section` 抛 `NOT_FOUND`（`fund_agent/fund/document_tools/docling_store.py:295`）；`search_document` 入口不传 `within_section_ref`（`llm_tool_loop.py:684`），section_ref 只能来自 LLM 对 read_section / list_tables 的猜测 | 首个 ToolFailure 即整轮失败（`llm_tool_loop.py:424-425` run、`:534-535` run_stream），失败不回喂 LLM 修正 | S1（P0-a） |
| 2 | 对比2021-2024年的策略，有哪些变化吗 | `DeepSeek LLM provider response 不符合受控结构` | `_parse_tool_call` 要求 arguments 必含非空 document_id（`deepseek_llm.py:656`，缺失/空抛 `LLM_MALFORMED_RESPONSE`，消息常量 `:29`） | 多年度比较最可能触发 `AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE`，LLM 输出参数不全即整轮 malformed；该工具本就豁免 document_id 校验（`llm_tool_loop.py:640-641`），parser 却仍强制 | S2（P1-b） |
| 3 | 这是基金值得继续关注吗 | `LLM 工具调用超过限制` | interactive `max_iterations=20`（`scene_config.py:101`）；耗尽后 `_force_answer_from_evidence` 无证据 → `_STEP_LIMIT`（`llm_tool_loop.py:1042`） | 无可检索事实目标的问题，LLM 反复空搜索耗尽预算 | S4（P2） |
| 4 | 基金管理费、托管费、销售服务费分别是多少 | `LLM 工具调用不被允许` | 工具名严格白名单（`llm_tool_loop.py:638`）+ document_id 前缀一致校验（`:641-644`），LLM 一次偏差即整轮失败 | 工具名归一化缺失、document_id 未用 expected 补全 | S2（P1-b） |
| 5 | 前十大重仓股有哪些 / 基金风格一致 | 回答被投资建议检测拦截（误拦截） | `contains_investment_advice` 弱词豁免窗口只认 策略/宣称/原文/摘录/运作分析（`llm_tool_loop.py:83-133`）；本次运行发生时 WIP B1（17:18 修改）已在场仍被拦（23:51 运行） | 持仓/风格事实描述（本期买入/卖出/增持/减持/重仓）不在豁免内 → 结构性误判；被拦截原文未持久化，触发词无法确证 | S3（P1-a）+ S0 持久化 |

### 调试盲区（S0 必须先解决）

| 盲区 | 证据 | 修复边界 |
|------|------|---------|
| 失败轮不写入 session | `chat_service.py:205` failure 分支提前 return，未走 session save（`:242`） | S0：失败轮也落 session（user + assistant 成对），assistant content 为失败消息 |
| 失败 tool_trace 被 revert 切断 | HEAD 为 `c4e5e71`（Revert e276ff3）；e276ff3 的失败分支用了 `entry.status`，但 `ToolTraceEntry` 只有 `tool_name / arguments / result_kind / failure_code`（`tool_loop.py:36-56`），该字段不存在 → revert 属正确纠错 | S0：恢复 trace 传递，改用 `result_kind / failure_code`，补两条测试（工具失败路径 trace 非空；provider 首轮失败 trace 为空） |
| 被拦截回答原文不可见 | `.fund_e2e_004393/sessions/5773559e...json` 中"前十大重仓股有哪些？"的 assistant turn 只有替换文本"抱歉，不支持涉及投资建议的问题。" | S0：session 持久化原始回答 + 触发词（新增 Turn 可选字段，旧 session JSON 缺字段必须可加载） |

---

## 2. 现状基线（不得重复规划）

- B1：`llm_tool_loop.py` 新增 `contains_investment_advice`（强弱词 + 引用上下文豁免），runner 终答校验与 `chat_service.py:211` 第二道守卫已共用（`chat_service.py:25` 改引 `llm_tool_loop`）。
- B2：`chat_service._build_contributions(session, document_id=...)` 把当前 `document_id` 注入 runtime contribution，缓解 LLM 截断 document_id。
- 已实现测试基线：B1/B2 相关单测 92 passed + 生产就绪/最小循环/CLI 124 passed（DS 已验证，本计划不重跑）。
- 已知不一致（本计划修复）：`main.py:1104/1243` 用户输入预检仍用旧 naive `investment_guard.contains_investment_advice`（`fund_agent/service/investment_guard.py:40`），与 B1 单一真源不一致 → S3。
- 工作区还有与本任务无关的 `docling_store.py` WIP（搜索空白归一化、表标题 fallback）：**所有 slice 禁止触碰该文件**，不属于 B1/B2，也不属于本计划。

---

## 3. Slice 定义

### S0 — 失败轮可观测性与持久化（调试盲区 / P0-b）

**目标**
- 失败轮在 session 中成对落盘：user turn + assistant turn（content = 失败消息），保留 `tool_calls` 与 `tool_trace`。
- `ChatTurnResponse` 失败路径返回非空 `tool_trace`（与成功路径同构，字符串元组），CLI `--enable-tool-trace` 可显示。
- 被投资建议拦截的回答：session 与 response 保留原始回答 + 触发词（检测到的最短命中词元）。
- 修复 e276ff3 的字段错误：`entry.status` → `entry.result_kind` / `entry.failure_code`，不恢复原样。

**Allowed write set**
- `fund_agent/service/chat_service.py`（failure 分支改为记录后返回；拦截路径持久化原文与触发词）
- `fund_agent/service/session_models.py`（`Turn` 新增可选字段，如 `original_content: str | None = None`、`blocked_terms: tuple[str, ...] = ()`；序列化对缺失键容错，旧 session 可加载）
- `fund_agent/agent/llm_tool_loop.py`（仅新增"命中词元"辅助函数，复用 B1 既有关键词集合；不改变 `contains_investment_advice` 判定）
- `fund_agent/cli/main.py`（interactive REPL 展示被拦截原文/触发词与失败 trace）
- `fund_agent/agent/README.md`（agent 层变更同步，repo 规则）
- 测试：`tests/fund/service/test_chat_service.py`、`tests/fund/host/test_session_store.py`、`tests/fund/cli/test_cli_interactive.py`

**禁止事项**
- 不改 `contains_investment_advice` 判定逻辑（属 S3 口径范围）。
- 不新增 failure code；不把拦截从 fail-closed 改成 fail-open。
- 不删除/覆盖既有 session 文件或重写 session 格式（只能向后兼容扩展）。

**验证命令**
```bash
uv run pytest tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/cli/test_cli_interactive.py -q --tb=short
```

**Stop conditions**
- 至少两条新测试：工具失败路径（ToolFailure → `AgentRunResult.failure`）返回的 `ChatTurnResponse.tool_trace` 非空；provider 首轮失败（`llm_tool_loop.py:406-408` `next_step` 抛 `LlmClientFailure`）trace 为空。
- 至少一条新测试：被拦截回答后 session 中保存原文与触发词，且旧格式 session JSON 可加载。
- 失败轮 session 含成对 turn，`--enable-tool-trace` 显示失败路径工具调用。

**非目标**
- 不实现 ToolFailure 回喂（S1）；不改 prompt（S4）；不扩展豁免口径（S3）。

---

### S1 — ToolFailure 回喂（P0-a）

**目标**
- 工具调用失败不再终止整轮：失败作为带 failure 标记的 ToolResult 追加到 `tool_results`，下一轮 `next_step` 可见（LLM 可修正 section_ref / 工具名 / document_id 后重试）。
- `run` 与 `run_stream` 同步生效；`run_stream` 对工具失败发 `TOOL_EVENT(result)` 并继续，只有终态失败（step 耗尽、终答守卫、provider 异常）才发 `ERROR`。
- 相同失败调用去重：`seen_calls` 对失败结果同样生效，LLM 重复同一失败调用时短路返回既有失败结果，不重复执行工具。
- FakeLlmClient 契约覆盖：`FakeStepFactory` 能读取含失败项的 `tool_results` 并给出修正步骤。
- 失败反馈可被 DeepSeek payload 序列化：`_safe_tool_result` 对失败项输出 `{"error": code, "message": message}`（复用 `Envelope.error` / `project_for_llm` 的 `ok=False` 投影，`tool_result.py` 已支持，不改该文件）。
- prompt 增加失败重试引导：工具返回失败时，基于 message 修正参数（section_ref / table_ref 必须从 search / list 结果复制，不得再猜），最多重试 1 次，仍失败则声明"未找到相关数据"。

**Allowed write set**
- `fund_agent/agent/llm_tool_loop.py`（runner `ToolResult` 增加可选 failure 标记；`run`/`run_stream` 失败不终止；`seen_calls` 收录失败；`_invoke_tool_call` 不变）
- `fund_agent/agent/deepseek_llm.py`（`_safe_tool_result` 投影失败信封）
- `fund_agent/service/prompts/ask/tools_scene.md`、`fund_agent/service/prompts/interactive/scene.md`（失败重试引导）
- `fund_agent/agent/README.md`
- 测试：`tests/fund/agent/test_llm_tool_loop.py`、`tests/fund/agent/test_stream_events.py`、`tests/fund/agent/test_tool_result.py`

**禁止事项**
- provider 侧 `LlmClientFailure`（`llm_malformed_response` / `unavailable`）不回喂，维持 fail-closed：畸形响应不得进入无限重试。
- 不改终答证据校验：最终回答仍必须由成功工具结果的 evidence 支持；失败项不贡献 evidence_text / citations。
- 不新增工具、不新增 failure code、不改 `max_iterations` 语义。
- 不触碰 `docling_store.py`。

**验证命令**
```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_stream_events.py tests/fund/agent/test_tool_result.py -q --tb=short
```

**Stop conditions**
- 至少一条测试：首调 read_section 用错 section_ref 返回失败 → 第二轮 LLM 收到含失败 code/message 的 tool_results 并改用 search 成功后正常收尾（对应"章节不存在"用例）。
- 至少一条测试：同一失败调用重复出现时短路返回既有失败结果（不二次执行工具）。
- `run_stream` 工具失败路径不发 `ERROR`、继续循环；终态失败仍发 `ERROR`。
- FakeLlmClient 契约文档与既有 fake 步骤无破坏（既有 92/124 测试不回退）。

**非目标**
- 不做无事实目标问题的预算保护（S4）；不做 document_id 解析放宽（S2）。

---

### S2 — tool call 容错（P1-b）

**目标**
- `_parse_tool_call` 不再强制 document_id：缺失/空字符串允许解析通过（不再整轮 `LLM_MALFORMED_RESPONSE`）。
- runner 在 `_invoke_tool_call` 对非 aggregate 工具用 `expected_document_id` 补全空 document_id 后再做前缀校验；`AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE` 维持现有豁免。
- 工具名归一化：去空白、去尾部括号参数等有界归一化后再做白名单精确匹配；仍未知则维持拒绝并写 trace（trace 保留 LLM 原始工具名）。

**Allowed write set**
- `fund_agent/agent/deepseek_llm.py`（`_parse_tool_call` document_id 改为 optional）
- `fund_agent/agent/llm_tool_loop.py`（`_invoke_tool_call` expected 补全；`_coerce_tool_name` 有界归一化）
- `fund_agent/agent/README.md`
- 测试：`tests/fund/agent/test_llm_tool_loop.py`、`tests/fund/agent/test_real_llm_adapter.py`

**禁止事项**
- 不做语义级别名映射（如 "search" → SEARCH_DOCUMENT）；只做格式归一化，未知工具名仍拒绝，防止静默扩大工具面。
- 不新增工具、不新增 failure code；`llm_malformed_response` 分类仍保留（用于 JSON 结构不可解析等真实畸形响应）。
- 不改非 interactive / ask 链路的工具调用行为（generate / audit / 评分路径不受影响）。

**验证命令**
```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_real_llm_adapter.py -q --tb=short
```

**Stop conditions**
- 至少两条测试：document_id 缺失/空字符串时工具调用成功（runner 用 expected 补全）；document_id 明显错误（前缀不匹配）仍拒绝。
- 至少一条测试：带格式噪声的工具名（空白/括号参数）归一化后放行；未知工具名仍拒绝且 trace 保留原始名。
- 既有 `llm_malformed_response` 测试不回退。

**非目标**
- 不做失败回喂（S1）；不改投资建议判据（S3）。

---

### S3 — 投资建议单一真源 + 持仓/风格事实豁免（P1-a，依赖 B1 口径 owner 确认）

**目标**
- interactive/ask 全链投资建议判据单一真源：`main.py:1104/1243` 用户输入预检改引 B1 实现（`llm_tool_loop.contains_investment_advice`），与 runner 终答守卫、`chat_service.py:211` 第二道守卫同一实现。
- 按确认后的口径扩展弱词豁免：持仓/风格事实描述（本期买入/卖出/增持/减持/重仓 等）不被误拦截。

**前置依赖（口径确认）**
- B1 口径 owner 需确认：弱词豁免的引用上下文关键词集合是否扩展（如 持仓/重仓/报告期内/期末/股票投资明细/基金风格），以及"事实性描述 vs 操作建议"的判定边界。未确认前本 slice 不启动实现，只允许先写口径提案。

**Allowed write set**
- `fund_agent/agent/llm_tool_loop.py`（仅按确认口径调整豁免规则，保持单一真源）
- `fund_agent/cli/main.py`（预检 import 合一；删除 1104 的旧 naive import）
- `fund_agent/agent/README.md`
- 测试：`tests/fund/agent/test_llm_tool_loop.py`、`tests/fund/service/test_chat_service.py`、`tests/fund/cli/test_cli.py`

**禁止事项**
- 不改 `fund_agent/service/investment_guard.py`（仍是 extraction routing guard / audit C3 的 legacy 真源，属于 generate/audit 链路，不在本任务范围；两实现并存属于已记录的边界，不扩大处理）。
- 不改 audit_pipeline.py / extraction.py 的 guard 行为。
- 不把拦截改 fail-open；强指令词与预测句式维持 fail-closed。

**验证命令**
```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_chat_service.py tests/fund/cli/test_cli.py -q --tb=short
```

**Stop conditions**
- 至少一条测试：持仓/风格事实描述（按确认口径的正例）不再被拦截。
- 至少一条测试：main.py 用户输入预检与 runner 守卫对同一文本判定一致（单一真源）。
- 强指令词（建议买入/强烈推荐/目标价/预测句式）拦截测试不回退。

**非目标**
- 不合一 extraction/audit 的 investment_guard 用法；不调整 audit C3 关键词语义。

---

### S4 — prompt 引导（P2）

**目标**
- 无可检索事实目标的问题（观点/闲聊/主观判断）尽早 final answer，不发起空搜索（`interactive/scene.md` 已有 rule 7，需强化为硬规则）。
- 空搜索结果的处理策略：换一次查询词；仍无命中则直接声明"未找到相关数据"，禁止反复空搜索耗尽预算。
- 不猜 section_ref / table_ref：一律从 search / list 结果复制（与 S1 失败重试引导合并成一致口径）。

**Allowed write set**
- `fund_agent/service/prompts/ask/tools_scene.md`、`fund_agent/service/prompts/interactive/scene.md`
- `fund_agent/agent/README.md`（如 prompt 文件归属 agent 层描述变化）
- 测试：`tests/fund/service/test_scene_config.py`、`tests/fund/service/test_prompt_composer_upgrade.py`、`tests/fund/agent/test_llm_tool_loop.py`

**禁止事项**
- 不改 `scene_config.py` 的 `max_iterations=20` 语义与数值（预算保护靠 prompt，不靠砍预算）。
- 不改 runner / client 代码；不新增 prompt fragment 文件。

**验证命令**
```bash
uv run pytest tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_llm_tool_loop.py -q --tb=short
```

**Stop conditions**
- 至少一条 fake 测试：无工具目标问题在 0 工具调用后直接 final answer。
- 至少一条 fake 测试：空搜索结果后 LLM 最多再发起一次替代查询，之后声明未找到，不触发 step limit。
- prompt 文件 diff 与 S1 的失败重试引导不冲突（同一文件同一节）。

**非目标**
- 不改 runner 的 step-limit / force-answer 逻辑；不引入新 LLM provider。

---

### S5 — 真源文档与 AGENTS.md 同步（doc-sync，最后执行）

**目标**
- 按 §4 清单完成真源文档 / AGENTS.md / README 同步，作为全部实现 slice review 通过后的收口。

**Allowed write set**
- §4 清单列出的文档文件（仅文档，无代码）。

**禁止事项**
- 不携带任何代码/测试改动；不借 doc-sync 扩大描述范围（不写未实现的路线）。

**验证命令**
```bash
git diff --check
```

**Stop conditions**
- §4 清单逐项核销；`docs/design.md`、`docs/implementation-control.md`、`AGENTS.md` 与最终代码行为一致。

---

## 4. 真源文档与 AGENTS.md 同步清单（S5 执行）

| 文档 | 章节 | 要同步的内容 |
|------|------|-------------|
| `docs/design.md` | Agent / LLM tool loop（含 `AgentRunResult` 段，约 :216） | ToolFailure 回喂语义：工具失败作为下一轮输入、重复调用去重、终态失败仍 fail-closed；失败轮持久化与 tool_trace 边界（provider 首轮失败 trace 为空） |
| `docs/design.md` | 失败分类（§6，约 :504-521） | 明确工具失败回喂不新增 failure code；`llm_malformed_response` 仅用于 provider 结构不可解析 |
| `docs/design.md` | 投资建议检测（若口径确认落地） | 单一真源位置（`llm_tool_loop.contains_investment_advice`）、弱词豁免上下文集合与事实性描述边界 |
| `docs/implementation-control.md` | 当前状态 / 下一步 / stop conditions | interactive e2e 修复完成记录、各 slice 验收结果、opt-in live e2e 命令与结果 |
| `AGENTS.md` | 当前产品方向 Phase 7 / interactive 能力描述；禁止事项（投资建议相关） | interactive 失败自愈能力、失败轮可观测性；投资建议判据口径变更（若 S3 确认） |
| `fund_agent/agent/README.md` | 工具调用循环 | 失败回喂、失败 trace、document_id 补全与工具名归一化（随 S0-S3 同步） |
| `tests/README.md` | 验证命令 | interactive 相关验证命令（若 S5 确认命令集合有增删） |
| 根 `README.md` | — | 不更新（用户成功路径不展开内部机制） |

## 5. 依赖 B1 口径 owner 确认的 slice

- **S3（P1-a）**：依赖 owner 确认弱词豁免上下文关键词与"事实性描述 vs 操作建议"边界。未确认前只允许口径提案，不进入实现。
- S0 的"触发词"持久化只复用 B1 既有关键词集合，不依赖口径确认，不受阻塞。
- 其余 slice（S0/S1/S2/S4/S5）不依赖口径确认。
