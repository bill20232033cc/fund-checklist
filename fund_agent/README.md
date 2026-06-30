# fund_agent

`fund_agent` 当前实现基金年报阅读工具层 MVP 的最小分层：

```text
fund_agent/fund -> FundDocumentToolService
fund_agent/agent -> deterministic tool loop
fund_agent/host -> MinimalHost
```

- `fund_agent/fund` 负责本地 PDF 导入、Docling conversion/store 和七个 reading tools。
- `fund_agent/agent` 只通过 `FundDocumentToolService` 调用工具，Slice 4 固定执行 `search_document -> read_section`。
- `fund_agent/host` 只托管 Agent loop，不理解基金领域，不访问 Fund store 或 Docling raw payload。

当前不是自动报告、字段抽取、投资判断或发布就绪系统。
