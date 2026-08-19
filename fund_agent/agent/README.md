# Agent 层

当前实现 deterministic table-backed first-hit / table-aware Agent loop。

- `MinimalFundDocumentAgent` 只依赖 `FundDocumentToolService`。
- 基础调用顺序为 `search_document -> read_section`。
- 当 `search_document` first hit 是 high-certainty table-backed result 且带 `table_ref` 时，调用顺序为 `search_document -> read_section -> read_table`，不经 `list_tables` 做表格发现。
- high-certainty 只按 exact containment 判断：`table_row` 命中要求 query 原文出现在 excerpt；`table_caption` 命中要求 query 原文出现在 title/excerpt。
- 其它 first hit 继续沿用 section-first table-aware 路径：`search_document -> read_section -> list_tables -> read_table`；没有相关表格时保持 section-only answer。
- 表格候选按 query 命中、同 section、同页或相邻页 proximity 排序。
- high-certainty table-backed answer 以 `read_table` 返回的 bounded table rows 为主体；section title / table caption 只作为来源上下文，不做 section 摘要或解释性综合。
- `AgentRunResult.answer` 成功时只由 section/table tool result 生成。
- `AgentRunResult.citations` 使用 `read_section` 和可用 `read_table` 返回的 citation。
- `ToolTraceEntry` 记录 `tool_name`、显式 `arguments`、`result_kind` 和可选 `failure_code`。
- `search_document` 无命中时返回 `AgentRunResult.failure`，不猜测 section。
- `ToolFailure` 传播到 `AgentRunResult.failure`，不向 Host/UI 抛内部异常。
- Agent 不读取 raw PDF、raw Docling JSON、本地路径或 Docling cache path。
- persistent repository 已由 Fund document tools / CLI loader 路径承载；Agent 只消费 `FundDocumentToolService` public tools，不直接读取 catalog 或 private loader。

Post-MVP Slice 10K 已实现 multi-year performance fake/injected Agent tool-loop：

- `aggregate_multi_year_annual_performance` 是新增受控 Agent 工具，暴露 10I `AggregateMultiYearAnnualPerformanceResult`。
- 工具输入沿用 10I/10J：`fund_code`、`requested_years`、`annual_report_documents[{year, document_id}]`、`share_class` optional，通过 `ToolCall.extra` 传入。
- 工具输出只返回 10I 结构化 result：成功为 `series[]`，失败为 `failure`；tool 层不生成分析文本。
- `LlmToolLoopRunner.__init__` 新增可选 `aggregate_handler` 参数，类型为 `Callable[..., AggregateMultiYearAnnualPerformanceResult]`。
- runner 不直接调用 `FundReadingService.aggregate_multi_year_annual_performance()`，而是通过 `aggregate_handler` 回调注入，保持 Service 层与 Agent 层解耦。
- `ToolResult.evidence_text` 包含 coverage_status、covered_years、missing_years 和逐行字段值（annual_nav_growth_rate / annual_benchmark_return_rate / annual_excess_return）。
- `ToolResult.citations` 包含所有 series rows 的字段级 table locator citations。
- failure 语义沿用 10I/10J：`identity_mismatch`、`not_found`、`schema_drift`、`unavailable`。
- `ToolCall.extra` 字段可携带任意 tool-specific 参数，trace 只记录 `str | int` 类型值。
- 10K 不接真实 LLM，不改 CLI 默认输出，不做自然语言解析、repository 自动补齐、报告生成或投资判断。

Post-MVP Slice 8A 已实现 fake/injected LLM tool-loop contract：

- `LlmClientProtocol` 是注入式 client 最小协议；当前不连接 OpenAI、Claude 或其它外部模型 API。
- `FakeLlmClient` 按测试脚本返回 `ToolCall` 或 `FinalAnswer`，用于验证 LLM 风格工具闭环。
- `LlmToolLoopRunner` 执行 `ToolCall -> ToolResult -> FinalAnswer`，返回既有 `AgentRunResult`。
- `run()` 和 `run_stream()` 对重复 (tool_name, arguments) 调用做去重，直接返回缓存 `ToolResult` 而非重新执行，防止 LLM search 后重复 search。
- 工具调用失败不再终止整轮：`ToolFailure` 转为带 `failure` 标记的 `ToolResult`（无 evidence/citation）追加到 `tool_results`，下一轮 `next_step` 可见，LLM 可修正 section_ref / 工具名 / document_id 后重试；重复的失败调用与成功调用一样按 key 去重短路。
- `run_stream` 对工具失败发 `TOOL_EVENT(phase=result)`（含 failure_code/message）并继续循环；只有终态失败（step 耗尽、终答守卫、provider 异常）才发 `ERROR`。
- interactive 终答投资建议守卫失败（`LLM 最终回答包含投资建议关键词`）时，`run` / `run_stream` 最多重试 1 次：query 追加纠正指令（要求只陈述年报客观事实、中性表述）重新调用 `next_step`，新 FinalAnswer 仍走同一 `_final_result` 守卫；重试通过则正常返回，重试后仍失败或未产出 FinalAnswer 则维持原失败（fail-closed）。ask / generate 等其它 scene 不重试，保持原语义；其它失败类型（证据缺失 / citation 缺失 / step 耗尽 / 不可用）不回退。
- interactive 终答质量守卫（原文粘贴：answer 与任一 evidence 连续重叠 ≥40 字符；或 answer >200 字）：正常 FinalAnswer 先过守卫，有界重答 1 次（query 追加概括指令），重答仍超标则截断为 ≤200 字摘要（含省略说明），重答未产出 FinalAnswer 或异常则 fail-closed；max_steps 耗尽的 force-answer 降级产物（2026-08-13 方案 2）跳过原文粘贴/超长有界重答，超长直接截断为 ≤200 字摘要（含省略说明）；投资建议拦截对两者一致保留（命中均有界重答 1 次，仍失败 fail-closed）。守卫对无证据的 step 耗尽失败原样放行。ask / generate 等其它 scene 的 force-answer 保持既有降级语义（证据原文拼接，不触发重答）。
- 失败反馈序列化：`DeepSeekLlmClient._safe_tool_result` 与 `wrap_results_for_llm` 对失败条目走 `Envelope.error` + `project_for_llm` 的 `ok=False` 投影（`{"error": code, "message": message}`）；provider 侧 `LlmClientFailure`（`llm_malformed_response` / `unavailable`）不回喂，维持 fail-closed。
- tool call 容错：`_parse_tool_call` 不再强制 document_id（缺失/空字符串解析为空串，仅结构不可解析或类型错误才映射 `llm_malformed_response`）；runner `_invoke_tool_call` 对非 aggregate 工具用 `expected_document_id` 补全空 document_id 后再做前缀校验，`aggregate_multi_year_annual_performance` 维持既有豁免。
- 工具名归一化：`_coerce_tool_name` 只做格式归一化（去首尾空白、去尾部括号参数）后精确匹配白名单；不做语义级映射（如 "search" -> search_document），未知工具名仍拒绝且 trace 保留 LLM 原始工具名。
- read_table section 一致性校验（Fix C，Mimo 根因 review）：interactive 场景下，runner 收集本轮 `list_tables` 成功结果与 `search_document` 命中结果（`SearchResult.table_ref`，table-backed first hit 合法来源）的 `table_ref` 集合；LLM 调 `read_table(table_ref=T)` 时 T 必须属于该集合（含未先 list_tables / search 直接读从未出现表号的情况），否则返回 `ToolFailure(not_found, "table_ref 未在当前已列出章节的表格中，请先 list_tables 并复制返回的表号")` 走既有失败回喂路径并计入 failed_call_keys，不终止循环。ask / generate 场景不拦截（控制 blast radius）；public reading tool 签名与实现不变。
- 允许工具固定为 `search_document`、`read_section`、`list_tables`、`read_table`、`get_excerpt`。
- `ToolResult` 只由 `FundDocumentToolService` public tool result 构造，不读取 repository/private loader。

投资建议检测区分强弱（B1 决策 A）：强指令词（建议买入/强烈推荐/目标价等，`预期收益` 精确匹配预测句式、排除年报术语 `预期收益率` / `预期收益及预期风险`）始终 fail-closed；弱指令词（买入/卖出/增持/减持）按判定顺序处理——出现处 ±100 字符窗口内含指令动词（建议/应当/可考虑/适合/值得持有/应买入/应卖出/应增持/应减持，复合指令形式，不用裸 应 以避免误命中 应付/应计 等事实表述）→ 拦截，否则窗口内含事实性上下文词（策略/宣称/原文/摘录/运作分析/报告期内/期末/持仓/重仓/股票投资明细/投资范围/财务报表附注/买入返售/卖出回购/基金合同）→ 放行，否则拦截（fail-closed 兜底）。该检测统一由 `llm_tool_loop.contains_investment_advice()` 提供，runner `_final_result`、`ChatService` 第二道守卫与 CLI 用户输入预检共用（单一真源）。

- `matched_investment_advice_terms()` 复用同一关键词集合与引用上下文判据，返回按首次命中顺序排列的命中词元（无命中时为空元组），用于被拦截回答的触发词持久化与展示；其判定与 `contains_investment_advice()` 严格一致。

- `FinalAnswer` 必须有非空 citation，citation 必须来自先前 section/table tool result。
- `FinalAnswer.key_facts` 中每个关键事实必须同时出现在最终回答和先前受控 tool evidence 中。
- 未知工具、越权工具、缺参数、无 evidence final answer、无 citation final answer、无工具证据支撑的关键事实均 fail-closed 为 `AgentRunResult.failure`。
- LLM runner 最终输出会净化 citation 中的 parser 内部引用字段，不暴露 raw Docling JSON、本地路径、cache path 或 `local_import_id`。

Post-MVP Slice 8B 当前实现：

- `DeepSeekLlmClient` 是 OpenAI-compatible provider adapter，实现既有 `LlmClientProtocol`。
- adapter 使用 `DeepSeekTransportProtocol` 注入 transport；默认 transport 基于标准库 `urllib`，测试使用 fake transport，不新增 SDK 依赖。
- request 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 组装 `/chat/completions`；`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- provider response 只能解析为受控 `ToolCall` 或 `FinalAnswer`，并继续交给 8A `LlmToolLoopRunner` 执行 enforcement。
- provider prompt/request 不得包含 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、URL secret、parser private payload 或 `local_import_id`。
- 默认测试不得联网、读取真实 key 或依赖真实 model 值。
- provider key 缺失、auth、network、timeout、rate limit 映射为 `unavailable`；malformed JSON/schema parse failed 映射为 `llm_malformed_response`。
- `next_step` 对 `llm_malformed_response`（stream 与非 stream 两条路径）最多重试 1 次：重新发起一次新请求，重试后仍 malformed 才抛 `LlmClientFailure(LLM_MALFORMED_RESPONSE)`（fail-closed 不变，畸形响应不进入无限重试）；`unavailable` 维持既有 3 次指数退避重试（1s/2s/4s），401/403 不重试。
- system prompt 明确要求 search→read_section→cite 链路：search 获取 section_ref，再用 read_section 读取完整章节内容，禁止猜测 section_ref 或 table_ref。
- `_parse_tool_call` 将未知 arguments（如 fund_code、requested_years、annual_report_documents）自动收集到 `ToolCall.extra`，传递给 aggregate 等工具。
- Slice 8B 不新增 `fund-checklist ask`，不做 streaming、Mimo / MiMo、多 provider matrix、prompt framework、richer QA/eval、自动报告、字段抽取或投资判断。

LLM Provider 自由切换（DeepSeek ↔ Mimo，Slice provider-switch-20260810）：

- 新增 env `FUND_CHECKLIST_LLM_PROVIDER`，取值 `deepseek`（默认）/ `mimo`；未知值 fail-fast 抛 `ValueError` 并提示合法取值，不静默回退。
- Provider 配置表集中在 `deepseek_llm.py`：deepseek 用 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`）/ `DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）；mimo 用 `MIMO_API_KEY` / `MIMO_BASE_URL`（默认 `https://api.xiaomimimo.com/v1`）/ `MIMO_MODEL`（默认 `mimo-v2.5-pro`）。
- 配置解析发生在请求组装时（`next_step` / `next_step_stream` / `generate_text`），与既有 env 读取点一致；`DeepSeekLlmClient.env` 注入参数保持向后兼容。
- scene/contract 模型名翻译表：`deepseek-v4-pro -> mimo-v2.5-pro`、`deepseek-v4-flash -> mimo-v2.5`；未知模型名原样透传。解析顺序：provider 对应 MODEL env 非空优先，否则 scene/contract 模型名经翻译后写入 provider 对应 MODEL env。
- `ChatService` 注入层按 provider 组装 client env；`interactive` 的 current_model 展示由 `resolve_provider_model` 提供（读对应 MODEL env + provider 默认）。
- 错误文案已泛化：`_UNAVAILABLE_MESSAGE` / `_MALFORMED_MESSAGE` 不再带 DeepSeek 前缀。
- 保留类名/文件名 `DeepSeekLlmClient` / `deepseek_llm.py`，不 rename；不新建第二套 adapter。

日志与诊断载荷（Slice log-verbose-diagnostics-20260813）：

- `log_levels.py` 提供 VERBOSE=15 诊断日志级（`verbose()`）与 `FUND_CHECKLIST_LOG_LEVEL` 环境变量配置（合法取值 DEBUG/VERBOSE/INFO/WARNING/ERROR，默认 absent 时零行为变更）。
- `diagnostic_payload.py` 的 `build_diagnostic_payload` 构造有界脱敏诊断载荷：显式命名参数、字段级截断 500、总量上限 2000、集中正则脱敏（API key / Bearer / URL secret / local_import_id / 本地绝对路径 / 工作目录）；任何路径不记录 raw provider response。

Tool Trace 只读分析器（operator 层，Slice tool-trace-operator-20260813）：

- `tool_trace_analysis.py` 提供纯函数只读分析器 `analyze_tool_trace`（只接受派生 `tuple[ToolTraceEntry]` + typed policy，不读 session / durable internals、不写状态、不落盘、不成为 truth 源）与确定性 JSON renderer `tool_trace_analysis_to_json`（sort_keys / ensure_ascii=False / 尾换行）。

Post-MVP Slice 8C 当前实现：

- 新增 `tests/fund/agent/test_deepseek_live_smoke.py`，作为 opt-in live provider smoke。
- live smoke 验证真实 provider 能返回一次合法 `ToolCall` 或 `FinalAnswer`，并最终进入 8A `LlmToolLoopRunner`。
- 默认 pytest no-network；只有 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时启用 live smoke。
- skip 判定与 env 组装按 `FUND_CHECKLIST_LLM_PROVIDER`（`deepseek` 默认 / `mimo`）解析：缺当前 provider 的 API key（`DEEPSEEK_API_KEY` / `MIMO_API_KEY`）时 skip，不失败；未知 provider 值 fail-fast 抛 `ValueError`。
- base URL / model 及其默认值来自 provider 配置表：deepseek 用 `DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`）/ `DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）；mimo 用 `MIMO_BASE_URL`（默认 `https://api.xiaomimimo.com/v1`）/ `MIMO_MODEL`（默认 `mimo-v2.5-pro`）。
- live smoke 使用 fake/in-memory tool service 或现有测试 fixture，不跑真实 PDF、CLI、Docling conversion 或 repository-backed loader。
- live smoke 最多 1 个 run、timeout 300 秒、最多 1 次 retry。
- 默认测试用 fake transport 验证 skip 语义、默认 base/model、timeout、最多 1 次 retry、malformed response fail-closed 和 secret 不泄漏。
- pytest output、trace、assert message 不得打印 API key；不得记录 raw provider response 或新增 artifact。
- Slice 8C 不修改 production adapter；若 live test 暴露解析 bug，必须先停止并报告。

未实现：prompt 编排、自动报告、投资判断、字段抽取、长期会话、`fund-checklist ask`。
