# 2026-08-09 interactive 问答与记忆能力改进（检索锚点 + aggregate 接线 + 跨轮去重 + 记忆注入）

> 状态：🟡 计划待 review（design only，不实现）。来源：R5 live e2e（2026-08-08，007466 四问）验收不通过 + 记忆注入未完成。所有证据均以当前代码与 docs 核实为准。

---

## 1. 背景与证据（代码实证）

### 1.1 R5 live e2e 验收不通过（docs/implementation-control.md:2783）

命令 = `printf '...4 问 + exit' | FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 uv run fund-checklist interactive --fund-code 007466 --work-dir .fund_e2e_007466 --no-stream --plain --enable-tool-trace --label r5-007466-live`；会话 = `.fund_e2e_007466/sessions/80936402c9a9484e8403a63c3cc1e110.json`。逐问 tool trace 复现：

- **Q1「基金经理持有本产品吗」→ 假阴性**：`search('基金经理持有本基金')` / `search('持有本基金')` 有命中但 agent 只读 `table-0097`（9.2 从业人员合计表）与 `section-0748`，未读真源 `table-0098`。
  - 当前 007466-2025 docling JSON 实证：`table-0098` 行头含「本基金基金经理持有本 开放式基金」（A 类 50~100 万份）、`table-0097` 行头为「基金管理人所有从业人员持有本基金」（9.2 合计口径）；两表 caption 均为空，标题只存在于表内行头。
- **Q3「基金前十大持仓是什么」→ 假阴性**：`search('股票投资明细')` 命中后 agent 只读 `table-0086`（分行业股票投资组合，B 采矿业/C 制造业），未读真源 `table-0087`。
  - 实证：`table-0087` 表头签名 = 序号/股票代码/股票名称/数量（股）/公允价值（元）/占基金资产净值比例（%），10 行；`table-0086` = 行业配置 decoy。
- **Q4「2021-2025 份额净值增长率」→ 原文粘贴 + aggregate 2 次失败**：`aggregate_multi_year_annual_performance` 两次调用均 `failure=unavailable`（第一次缺 share_class，第二次 `share_class='A'`），agent 转而 read_table 并原文粘贴整段表格（>200 字，无结构化总结）。
- **结论**：R5 记录「live 结果只作验收证据，不驱动 production adapter 变更」，本批另排修复 slice。

### 1.2 aggregate 生产接线缺失（根因）

- `fund_agent/agent/llm_tool_loop.py:446-459`：`LlmToolLoopRunner` 支持 `aggregate_handler` 参数；`llm_tool_loop.py:1140` handler 为 `None` 时直接 `ToolFailure(UNAVAILABLE)`。
- `fund_agent/service/chat_service.py:129-138`：`_default_runner_factory(llm_client, tool_service, max_steps)` 不透传 `aggregate_handler`。
- `fund_agent/cli/main.py:1138 / 1408 / 1573 / 1996`：interactive/fix/repair/regenerate 四处 `ChatService(...)` 构造均未传 `aggregate_handler`（fix/repair/regenerate 场景 allowed_tools 本就不含 aggregate，无影响；interactive 白名单含 aggregate → 必失败）。
- commit `04f9554`（2026-08-08）只修了 runner 侧 `document_id` 注入（不再豁免 aggregate）与 handler 调用处 `call.document_id` 透传，未接线 handler；因此 R5 实测 `document_id=''` 的 trace 参数与 `unavailable` 同时成立。
- Service 侧五年聚合已存在：`fund_agent/service/extraction.py:1308` `FundReadingService.aggregate_multi_year_annual_performance(request)`（10F/10G 复用，3-5 年 bounded，`share_class` 缺省 A 类优先）；CLI aggregate 分支（main.py:650-668）已有 catalog 解析 annual_report_documents 的现成逻辑。

### 1.3 重复调用治理现状

- `fund_agent/agent/llm_tool_loop.py:1579-1600` `_dedup_key`：比较完全相等参数（tool/document_id/query/section_ref/table_ref/max_* /locator/extra），语义相近不同词不命中。
- `seen_calls` 在 `run()`（llm_tool_loop.py:488）与 `run_stream()`（llm_tool_loop.py:626）每轮重建，跨轮无去重。
- 004393 实测 Q4 14 次调用且 search/list_tables/aggregate 重复调用（`.sisyphus/plans/interactive-quality-fix-20260805.md:16`）；R5 Q4 aggregate 失败 2 次仍执行 2 次（参数不同：share_class 缺失 vs 'A'）。

### 1.4 记忆注入未完成

- `chat_service._build_contributions`（chat_service.py:544-620）只注入 runtime/fund_context/user_constraints/history/retrieval，不注入 memory。
- `scene_config.py:97-107` `INTERACTIVE_SCENE_CONFIG.context_slots = ("runtime", "fund_context", "memory", "history", "retrieval")` 已声明 `memory` slot，但从未被填充。
- `prompt_contributions.py:62-90` `build_memory_contribution(episode_summaries_text, pinned_facts)` 已存在但未接线。
- `EpisodeSummary` 只写不读：写于 chat_service.py:323/427（compaction 线程 + 落盘 session_store.py:252），生产代码无任何读取注入点。
- `docs/phase7.3-option-b-optimization.md:376`：ContextBudget 与 history token 的交互留 TODO，Phase 8 处理（本批不碰）。

### 1.5 预算与收敛现状

- `scene_config.py:103`：`INTERACTIVE_SCENE_CONFIG.runtime.max_iterations = 12`（2026-08-05 从 20 降到 12）。
- 空结果收敛（search 连续 2 次 0 命中强制收敛 + 有 profile 候选词自动重试 1 轮）已实现（llm_tool_loop.py:520-585）；R5 Q1/Q3 的失败是「有命中但选错表」，非空结果问题 → 需要确定性表锚点而非更多收敛。

---

## 2. 目标 / 非目标

### 2.1 目标

1. **P0-1 检索命中质量**：对 R5 暴露的两类高误命中 query（9.4 基金经理持有、前十大持仓）注入 Service 层确定性 table_ref 锚点；其余 query 保持 LLM 自由选表（D1 受控扩展，范围限定 D2）。
2. **P0-2 aggregate 接线 + 重复调用治理**：interactive 打通 `aggregate_multi_year_annual_performance`（复用 Service 五年聚合，A 类优先，D3）；跨轮失败调用去重短路（D4-一）+ 去重键放宽（D4-二）；不做结果缓存复用（D4-三）；interactive `max_iterations` 12 → 8（D5）。
3. **P1 记忆注入**：EpisodeSummary / PinnedState 按方案 B 编织进 system prompt（D6），与 Phase 8 上下文治理分离、先注入后治理（D7）。

### 2.2 非目标（硬边界）

- 不改 `search_document` / `read_section` / `list_tables` / `read_table` / `get_excerpt` / `list_reports` / `list_sections` 公共契约与实现；锚点只由 Service 组合既有工具解析，不新增 public tool。
- 不实现完整结果缓存复用（D4-三）。
- 不加 list_tables / read_table 收敛扩展（D5）。
- 不做规模 / 份额 / 基准收益率 / 超额收益率 profile（D2，列入 backlog）。
- 不开放 ask 场景的 aggregate 工具（本期建议，见 §3.2 决策项）。
- 不做方案 A 协议层；不动 compaction 触发阈值 / 截断策略 / ContextBudget × history 治理（Phase 8，D7）。
- 不触碰 generate / repair / fix / regenerate 场景、报告管线、审计管线、评分管线。
- 不引入 dayu runtime / 代码复制；不新增 gateflow / plan-fix / re-review / evidence gate（CIC-lite）。
- 本任务只产出本 plan artifact：不实现、不 commit、不改任何代码与 docs。

---

## 3. 分 slice 规格

实施顺序：**P0-1 → P0-2 → P1**（三 slice 都触碰 `chat_service.py` 写面，串行实施避免冲突；每 slice 独立走 implement → tests → diff review）。

### 3.1 P0-1 检索命中质量（Service 表锚点）

**规格**：

1. `fund_agent/service/extraction.py`：
   - `_DisclosureLocatorContract`（models.py:28）增加可选字段 `anchor_title_family: tuple[str, ...] = ()`；仅对 `manager_holdings` 与 `holdings_top10` 两个 contract 配置（其余不配，保持 LLM 自由选表）。
     - `manager_holdings`：`("本基金基金经理持有本开放式基金", "基金管理人所有从业人员持有本基金")`（9.4 优先、9.2 回退，归一化空白后匹配）。
     - `holdings_top10`：表头签名匹配（含「序号」「股票名称」「公允价值」，row_count ≥ 10），不复用 `acceptable_title_family` 的正文标题语义。
   - 新增 `_resolve_anchor_table_ref(document_id, contract, tool_service) -> str | None`（Service 层私有，组合 public tools）：
     - manager_holdings：`search_document` 用「期末基金管理人的从业人员持有本基金的情况」定位 section → `list_tables(within_section_ref)` → 对候选表 `read_table`（有界行）扫描行头，命中 9.4 优先、9.2 回退；返回 `table_ref`。
     - holdings_top10：`search_document` 用「前十名股票投资明细」定位 section → `list_tables(within_section_ref)` → 表头签名匹配；返回 `table_ref`。
     - 解析失败 / 工具不可用 / 无候选表 → 返回 `None`，走既有候选词路径（**不 fail-closed**）。
   - 复用既有 `_extract_manager_holding` / `_extract_manager_holds_overall` 的 9.4/9.2 标题族常量与归一化规则，不重复实现抽取逻辑。
2. `fund_agent/service/chat_service.py` `_build_contributions`：retrieval contribution 追加锚点块（profile 命中且锚点解析成功时）：
   `- 候选表锚点: table-XXXX（<标题族>）——请优先 read_table 该表，并以该表返回内容作为引用依据（勿自行猜测表号）`。
   锚点仅注入 `manager_holdings` / `holdings_top10` 两类（D1/D2 硬口径）。
3. runner 不 import service；锚点为 prompt 数据，与既有候选词注入同机制（分层约束不变）。

**allowed write set**：

- `fund_agent/service/models.py`（`_DisclosureLocatorContract` 字段）
- `fund_agent/service/extraction.py`（registry 配置 + `_resolve_anchor_table_ref` + 标题族常量）
- `fund_agent/service/chat_service.py`（retrieval contribution 锚点注入）
- `tests/fund/service/test_extraction.py`（锚点解析单测：007466 fixture 命中 table-0098/0087，解析失败回退 None）
- `tests/fund/service/test_chat_service.py`（retrieval contribution 含锚点断言；非目标 profile 无锚点断言）

**验证命令**：

```bash
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_chat_service.py -k "route or anchor or manager_holdings or holdings" -q --tb=short
# 回归
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

**stop conditions**：

- 锚点解析单测以 007466-2025 真实 fixture 断言：manager_holdings → 行头含「本基金基金经理持有本开放式基金」的表；holdings_top10 → 表头签名含 序号/股票名称/公允价值 且 ≥10 行。
- 锚点注入只出现在两类 profile 的 retrieval contribution；其余 profile / 无 profile query 不出现锚点。
- 解析失败路径返回 None 且不抛异常（fail-open 到候选词路径）。
- 不改任何 public tool 契约；diff 只落在 write set。

---

### 3.2 P0-2 aggregate 接线 + 重复调用治理

**规格（aggregate 接线）**：

1. `fund_agent/service/chat_service.py`：
   - `ChatService.__init__` 增加 `aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None`；`_default_runner_factory` 增加同参数并透传给 `LlmToolLoopRunner`。
   - runner 构造处（chat_service.py 第 4 步）保持 `runner.run(..., candidate_queries=...)` 不变；`aggregate_handler` 由 factory 注入。
2. `fund_agent/cli/main.py`：
   - 新增 `_build_aggregate_handler(work_dir)` helper：复用 main.py:650-668 的 catalog 解析逻辑（`fund_code` + `requested_years` → `annual_report_documents`，last-wins），构造 `AggregateMultiYearAnnualPerformanceRequest(fund_code, requested_years, annual_report_documents, work_dir, share_class)`，调用 `FundReadingService().aggregate_multi_year_annual_performance` 返回结果。
   - 仅 interactive 分支（main.py:1138）传 `aggregate_handler=_build_aggregate_handler(work_dir)`。
   - **handler 以 catalog 重解析 annual_report_documents，忽略 LLM 提供的 document_id 列表**（防幻觉 document_id 注入）。
3. `fund_agent/service/prompts/interactive/scene.md`：追加 aggregate 使用说明——「`aggregate_multi_year_annual_performance` 需带 `fund_code` 与 `requested_years`（如 2021-2025），一次调用即可获取多年结构化 series；成功后直接用自己的话总结（≤200 字），禁止粘贴原文表格」。
4. **决策项（ask 是否开放）**：本期 **不开放**。理由：`ASK_SCENE_CONFIG.allowed_tools` 白名单不含 aggregate（工具白名单即接口边界）；ask 为单文档单轮、无 fund 级多年 catalog 上下文，开放需另定义多年度解析语义，超出 R5 修复范围。列入 backlog，需单独裁决。

**规格（重复调用治理）**：

1. `fund_agent/agent/llm_tool_loop.py`：
   - `_dedup_key` 放宽（D4-二），工具级归一化：
     - `search_document` → `(tool, document_id, _normalize_query_text(query))`（去空白 + CJK 标点）；
     - `read_section` → `(tool, document_id, section_ref, max_chars)`；
     - `read_table` → `(tool, document_id, table_ref, max_rows)`；
     - `get_excerpt` → `(tool, document_id, locator_key)`（沿用 locator 归一化）；
     - `aggregate_multi_year_annual_performance` → `(tool, fund_code, tuple(sorted(requested_years)), share_class or "")`；
     - 新增 `_normalize_query_text` 纯函数（单一真源，可单测）。
   - `run()` / `run_stream()` 增加参数 `failed_call_keys: frozenset[tuple] | None = None`：LLM 请求的工具 key ∈ failed_call_keys 时**直接短路**（不调用工具、不消耗真实调用），追加失败标记 ToolResult（failure 提示「该调用此前已失败（failure_code），不再重跑」），LLM 可改参数或收尾。
   - `AgentRunResult`（tool_loop.py:59）新增 `failed_call_keys: tuple[tuple, ...] = ()`：runner 在轮末按同归一化规则收集本轮失败调用的 key。
2. `fund_agent/service/session_models.py`：`Session` 新增 `failed_tool_call_keys: tuple[tuple, ...] = ()`（不可变，新增 `with_failed_tool_call_keys` 方法）；`Turn` 不动。
3. `fund_agent/host/session_store.py`：序列化/反序列化 `failed_tool_call_keys`（旧 session 缺字段默认空元组，不回退——沿用 R4 key_facts 兼容模式）。
4. `fund_agent/service/chat_service.py`：每轮结束后 `session.failed_tool_call_keys + agent_result.failed_call_keys` 合并（去重 + 上限 50 条，超限丢最旧）；下一轮构造 runner 时传入。
5. **预算**：`fund_agent/service/scene_config.py:103` `INTERACTIVE_SCENE_CONFIG.runtime.max_iterations` 12 → 8（D5）。依据：锚点收敛 Q1/Q3、aggregate 单次成功 Q4、跨轮失败短路消除重跑；R5 Q4 实际 8 次调用已 <12，8 是可行下界。**设计确认：8 合适**，但以 live e2e Q4 工具调用 ≤8 为验收锚；若复跑超限，回查根因（不静默放宽）。

**allowed write set**：

- `fund_agent/agent/tool_loop.py`（`AgentRunResult.failed_call_keys` 槽位）
- `fund_agent/agent/llm_tool_loop.py`（`_dedup_key` 放宽 + `_normalize_query_text` + `failed_call_keys` 短路 + `AgentRunResult.failed_call_keys` 收集）
- `fund_agent/service/chat_service.py`（`aggregate_handler` 参数 + failed keys 读写）
- `fund_agent/service/session_models.py`（`Session.failed_tool_call_keys`）
- `fund_agent/host/session_store.py`（序列化兼容）
- `fund_agent/service/scene_config.py`（max_iterations 12 → 8）
- `fund_agent/service/prompts/interactive/scene.md`（aggregate 使用说明）
- `fund_agent/cli/main.py`（`_build_aggregate_handler` + interactive 构造传参）
- `tests/fund/agent/test_llm_tool_loop.py`（去重放宽 + 跨轮短路 + failed keys 收集）
- `tests/fund/service/test_chat_service.py`（aggregate handler 透传 + failed keys 落 session）
- `tests/fund/host/test_session_store.py`（序列化兼容）
- `tests/fund/cli/test_cli_interactive.py`（interactive 构造注入 aggregate handler 的接线测试）

**验证命令**：

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/cli/test_cli_interactive.py -q --tb=short
# Phase 7 回归
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short
# 最小验证
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

**stop conditions**：

- 单测证明：相同失败调用跨轮短路（第二次不实际调用工具）；语义相近 search query 去重；read_section/read_table 忽略 query 措辞按 ref 去重；旧 session 无 `failed_tool_call_keys` 字段恢复不回退。
- 单测证明：ChatService 构造注入 handler 后 aggregate 调用返回结构化结果；不注入时保持既有 `unavailable` 行为（fix/repair/regenerate 不受影响）。
- `max_iterations` 8 生效；scene_config 单测断言 interactive 为 8。
- 不新增任何 public tool；`search_document` / Service reading tools 契约零改动。
- 默认 pytest 不联网（aggregate 接线用 fake handler / 既有 fixture，不触发真实 LLM）。

**opt-in live（需用户显式授权后执行）**：

```bash
printf '基金经理持有本产品吗\n基金经理是谁\n基金前十大持仓是什么\n2021-2025 份额净值增长率\nexit\n' | \
  FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 uv run fund-checklist interactive \
  --fund-code 007466 --work-dir .fund_e2e_007466 --no-stream --plain --enable-tool-trace \
  --label r5-recheck-20260809
```

断言（007466，真源 = 2025 docling JSON，与 R5 记录同源）：

- Q1 命中 9.4 表（行头含「本基金基金经理持有本开放式基金」），回答含 A 类 50~100 万份区间口径，不报「未找到相关数据」。
- Q2 回归通过（柳军/柳叶青）。
- Q3 命中表头签名含 序号/股票名称/公允价值 的持仓明细表（≥10 行），回答含 top-1（601009 等）股票名称与占比。
- Q4：`aggregate_multi_year_annual_performance` 成功 ≥1 次（≤2 次调用），回答为结构化总结 ≤200 字，无原文整段表格粘贴；该问工具调用 ≤8。
- 004393 复跑（`.fund_e2e_004393`，同四问）口径一致：Q1 命中 9.4/9.2、Q3 命中股票投资明细、Q4 aggregate 成功且 ≤200 字。
- live 结果只作验收证据，不驱动 production adapter 变更（沿用 R5 口径）。

---

### 3.3 P1 记忆注入（EpisodeSummary / PinnedState → system prompt）

**规格**：

1. `fund_agent/service/chat_service.py` `_build_contributions` 增加 memory slot：
   - `contributions["memory"] = build_memory_contribution(episode_summaries_text=_format_episode_summaries(session), pinned_facts=_pinned_facts(session))`（`prompt_contributions.build_memory_contribution` 已存在，直接接线）。
   - `pinned_facts` 来源 = `session.pinned_state.user_constraints["confirmed_facts"]`（compaction `pinned_state_patch` 写入；空则跳过）。
   - `_format_episode_summaries`：最近 ≤3 条 EpisodeSummary，每条 ≤ title / goal / confirmed_facts（≤5 条）/ open_questions（≤3 条），总长 ≤500 token（复用 `_estimate_token_count`，超限丢最旧）；全空返回 `""`。
   - slot 顺序由 `context_slots` 声明（"memory" 已在 history 之前，scene_config 零改动）。
2. 注入内容显式标注「历史摘要，非当前证据」，引用仍须来自本轮工具返回（interactive 方案 E 保持不变）。
3. 方案 B（编织进 system prompt）确认；不做协议层方案 A；不动 ContextBudget / history token 交互（Phase 8，D7）；不动 compaction 触发/截断策略。
4. `prompt_contributions.py` 如需 bounded 格式支持可微调 `build_memory_contribution`（保持默认参数兼容，旧调用不受影响）。

**allowed write set**：

- `fund_agent/service/chat_service.py`（memory 注入 + `_format_episode_summaries`）
- `fund_agent/service/prompt_contributions.py`（如需格式微调）
- `tests/fund/service/test_chat_service.py`（注入断言：episode/pinned facts 出现在 contributions；超限裁剪；空 memory 不产生 slot）
- `tests/fund/service/test_prompt_contributions.py`（bounded 格式兼容）

**验证命令**：

```bash
uv run pytest tests/fund/service/test_chat_service.py tests/fund/service/test_prompt_contributions.py -q --tb=short
# Phase 7.3 回归
uv run pytest tests/fund/host/test_session_models.py tests/fund/service/test_chat_service.py tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_scene_config.py -v --tb=short
git diff --check
```

**stop conditions**：

- compaction 后下一轮 `_build_contributions` 能从 `session.episode_summaries` 读出并注入（compaction 写 → 读闭环测试，用 `inject_compaction_result` 不联网）。
- 旧 session（无 episode_summaries / 无 confirmed_facts）不产生 memory slot，不回退。
- 注入有 token 上界（≤500），超限裁剪断言。
- 不改协议层、不改 ContextBudget、不改 compaction 策略。

---

## 4. 真源更新建议（实施/收口阶段同步，非本任务执行）

- **docs/implementation-control.md**：
  - R5 状态节（:2783）末尾追加一行：修复排期落地 = 本 plan（P0-1/P0-2/P1）。
  - 「interactive 质量修复 slice（计划 ACCEPTED，实施中）」（:2685）收口为已完成（2026-08-05 语义已落地）。
  - 新增「## 交互问答与记忆能力改进（2026-08-09 裁决）」：记录 D1-D9 硬口径、三 slice 状态行（计划 ACCEPTED / 待实施）、单测命令、opt-in live 命令与断言。
- **docs/design.md**：
  - §6.10 更新：受控表锚点语义（manager_holdings / holdings_top10 例外清单）、interactive aggregate 开放（A 类优先）、max_iterations 8、跨轮失败调用短路、记忆注入方案 B 完成。
  - 新增 §6.20「interactive 检索锚点 + aggregate 接线 + 跨轮失败去重 + 记忆注入（2026-08-09 裁决）」。
  - Phase 7.3 节（:1594-1659）标注 EpisodeSummary 注入接线完成；「已接受的 Slice」列表追加 P0-1/P0-2/P1。
- **AGENTS.md**（规则真源，只同步行为变化）：
  - 「interactive 问答质量语义（2026-08-05...）」段追加：受控表锚点、aggregate interactive 开放（A 类优先）、max_iterations 8、跨轮失败调用短路。
  - Phase 7.3 段追加「EpisodeSummary / PinnedState 已注入 system prompt（方案 B，2026-08-09）」。
- **tests/README.md**：若验证命令/测试文件结构变化则同步。
- **不做**：不新增 plan-fix / re-review / evidence gate；真源同步走实施阶段 slice 收口，不在此 design 任务中改文档。

---

## 5. 风险与回退

1. **锚点解析跨文档漂移**（表号/标题族因重新导入变化）：锚点解析失败返回 None 走候选词路径（fail-open）；live 断言按标题族/表头签名而非固定表号；表号仅作为审计信息记录。
2. **锚点注入过度硬化**（LLM 只读锚点表）：prompt 措辞为「优先读取」，锚点解析不到时不注入任何表号；D2 限定两类 profile，其余 query 保持自由选表。
3. **aggregate LLM 参数残缺**（缺 requested_years）：runner 参数校验已 fail-closed（`_TOOL_ARGUMENT_MESSAGE`）；prompt 说明 + live 断言兜底；不新增语义猜测。
4. **跨轮失败去重误伤**（相同 key 的临时性失败被永久短路）：key 含 document_id/工具级参数维度，会话生命周期内有效；上限 50 条防膨胀；若实测误伤，缩小去重范围至「接线/参数类失败」（backlog，不本期）。
5. **max_iterations 8 过紧**（force_answer 提前）：live 断言 Q4 工具调用 ≤8 为验收锚；超限回查根因，不静默放宽；必要时在实施阶段单独裁决回调 10/12。
6. **记忆注入污染**（episode summary 带观点/过时事实）：注入块标注「历史摘要，非当前证据」；引用必须来自本轮工具返回；interactive 方案 E 保持。
7. **e2e fixture 漂移**（007466/004393 work-dir 被重新导入导致表 ref 变化）：实施前核验 `.fund_e2e_007466` / `.fund_e2e_004393` docling JSON 与 R5 记录同源（表头签名一致）；不一致则以标题族断言为准。

---

## 6. 收口（CIC-lite，D9）

- 本 plan 经 review（Mimo 或等价独立 review）ACCEPTED 后，按 P0-1 → P0-2 → P1 逐 slice 实施：implement → tests → diff review。
- 每 slice 收口时同步真源（§4 建议），裁决记录落 `docs/implementation-control.md` + 本 plan artifact。
- 本 design 任务约束：只产出本文件；不 commit；不触碰未授权区域；默认 pytest 不得联网；live 复跑需用户显式授权。
