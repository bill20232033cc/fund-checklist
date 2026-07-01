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

未实现：真实 LLM、prompt 编排、自动报告、投资判断、字段抽取、长期会话、`fund-checklist ask`。
