# Agent 层

当前实现 deterministic table-aware Agent loop。

- `MinimalFundDocumentAgent` 只依赖 `FundDocumentToolService`。
- 基础调用顺序为 `search_document -> read_section -> list_tables -> read_table`；没有相关表格时保持 section-only answer。
- 表格候选按 query 命中、同 section、同页或相邻页 proximity 排序。
- `AgentRunResult.answer` 成功时只由 section/table tool result 生成。
- `AgentRunResult.citations` 使用 `read_section` 和可用 `read_table` 返回的 citation。
- `ToolTraceEntry` 记录 `tool_name`、显式 `arguments`、`result_kind` 和可选 `failure_code`。
- `search_document` 无命中时返回 `AgentRunResult.failure`，不猜测 section。
- `ToolFailure` 传播到 `AgentRunResult.failure`，不向 Host/UI 抛内部异常。
- Agent 不读取 raw PDF、raw Docling JSON、本地路径或 Docling cache path。
- persistent repository 已由 Fund document tools / CLI loader 路径承载；Agent 只消费 `FundDocumentToolService` public tools，不直接读取 catalog 或 private loader。

Post-MVP Slice 8A 已实现 fake/injected LLM tool-loop contract：

- `LlmClientProtocol` 是注入式 client 最小协议；当前不连接 OpenAI、Claude 或其它外部模型 API。
- `FakeLlmClient` 按测试脚本返回 `ToolCall` 或 `FinalAnswer`，用于验证 LLM 风格工具闭环。
- `LlmToolLoopRunner` 执行 `ToolCall -> ToolResult -> FinalAnswer`，返回既有 `AgentRunResult`。
- 允许工具固定为 `search_document`、`read_section`、`list_tables`、`read_table`、`get_excerpt`。
- `ToolResult` 只由 `FundDocumentToolService` public tool result 构造，不读取 repository/private loader。
- `FinalAnswer` 必须有非空 citation，citation 必须来自先前 section/table tool result。
- `FinalAnswer.key_facts` 中每个关键事实必须同时出现在最终回答和先前受控 tool evidence 中。
- 未知工具、越权工具、缺参数、无 evidence final answer、无 citation final answer、无工具证据支撑的关键事实均 fail-closed 为 `AgentRunResult.failure`。
- LLM runner 最终输出会净化 citation 中的 parser 内部引用字段，不暴露 raw Docling JSON、本地路径、cache path 或 `local_import_id`。

Post-MVP Slice 8B 当前实现：

- `DeepSeekLlmClient` 是 DeepSeek-only OpenAI-compatible provider adapter，实现既有 `LlmClientProtocol`。
- adapter 使用 `DeepSeekTransportProtocol` 注入 transport；默认 transport 基于标准库 `urllib`，测试使用 fake transport，不新增 SDK 依赖。
- request 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 组装 `/chat/completions`；`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- provider response 只能解析为受控 `ToolCall` 或 `FinalAnswer`，并继续交给 8A `LlmToolLoopRunner` 执行 enforcement。
- provider prompt/request 不得包含 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、URL secret、parser private payload 或 `local_import_id`。
- 默认测试不得联网、读取真实 key 或依赖真实 model 值。
- provider key 缺失、auth、network、timeout、rate limit 映射为 `unavailable`；malformed JSON/schema parse failed 映射为 `llm_malformed_response`。
- Slice 8B 不新增 `fund-checklist ask`，不做 streaming、Mimo / MiMo、多 provider matrix、prompt framework、richer QA/eval、自动报告、字段抽取或投资判断。

Post-MVP Slice 8C 当前实现：

- 新增 `tests/fund/agent/test_deepseek_live_smoke.py`，作为 opt-in live DeepSeek smoke。
- live smoke 验证真实 provider 能返回一次合法 `ToolCall` 或 `FinalAnswer`，并最终进入 8A `LlmToolLoopRunner`。
- 默认 pytest no-network；只有 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时启用 live smoke。
- `DEEPSEEK_API_KEY` 缺失时 skip，不失败。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，`DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`。
- live smoke 使用 fake/in-memory tool service 或现有测试 fixture，不跑真实 PDF、CLI、Docling conversion 或 repository-backed loader。
- live smoke 最多 1 个 run、timeout 300 秒、最多 1 次 retry。
- 默认测试用 fake transport 验证 skip 语义、默认 base/model、timeout、最多 1 次 retry、malformed response fail-closed 和 secret 不泄漏。
- pytest output、trace、assert message 不得打印 API key；不得记录 raw provider response 或新增 artifact。
- Slice 8C 不修改 production adapter；若 live test 暴露解析 bug，必须先停止并报告。

未实现：Mimo / MiMo、多 provider、prompt 编排、自动报告、投资判断、字段抽取、长期会话、`fund-checklist ask`。
