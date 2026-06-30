# Host 层

当前实现 Slice 4 的 `MinimalHost`。

- Host 只接收 `document_id` 和 `query`，调用 `MinimalFundDocumentAgent.run()`。
- Host 返回原始 `AgentRunResult`。
- Host 不理解基金领域，不解析 PDF，不访问 `DoclingDocumentStore`，不读取 raw Docling JSON。
- Host 不实现真实 LLM、并发、取消、持久会话、事件恢复或 outbox。

后续若扩展 Host 生命周期能力，仍不得绕过 Fund documents / tool service 边界。
