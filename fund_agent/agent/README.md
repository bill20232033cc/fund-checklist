# Agent 层

当前实现 Slice 4 的 deterministic minimal Agent loop。

- `MinimalFundDocumentAgent` 只依赖 `FundDocumentToolService`。
- 固定调用顺序为 `search_document -> read_section`。
- `AgentRunResult.answer` 成功时只由 `read_section` 返回的 `title`、`text` 生成。
- `AgentRunResult.citations` 只使用 `read_section` 返回的 citation。
- `ToolTraceEntry` 记录 `tool_name`、显式 `arguments`、`result_kind` 和可选 `failure_code`。
- `search_document` 无命中时返回 `AgentRunResult.failure`，不猜测 section。
- `ToolFailure` 传播到 `AgentRunResult.failure`，不向 Host/UI 抛内部异常。
- Agent 不读取 raw PDF、raw Docling JSON、本地路径或 Docling cache path。

未实现：真实 LLM、prompt 编排、自动报告、投资判断、字段抽取、长期会话。
