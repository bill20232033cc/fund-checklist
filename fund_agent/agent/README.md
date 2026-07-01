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

未实现：真实 LLM、prompt 编排、自动报告、投资判断、字段抽取、长期会话、persistent repository。
