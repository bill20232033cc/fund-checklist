# fund_agent

`fund_agent` 当前实现基金年报阅读工具层 MVP 的最小分层：

```text
fund_agent/fund -> FundDocumentToolService
fund_agent/agent -> deterministic tool loop
fund_agent/host -> MinimalHost
fund_agent/cli -> fund-checklist read
```

- `fund_agent/fund` 负责本地 PDF 导入、Docling conversion/store、local persistent repository、repository-backed loader 和七个 reading tools。
- `fund_agent/agent` 只通过 `FundDocumentToolService` 调用工具，当前执行 section-first、table-aware retrieval loop。
- `fund_agent/host` 只托管 Agent loop，不理解基金领域，不访问 Fund store 或 Docling raw payload。
- `fund_agent/cli` 只提供 `fund-checklist read`，通过 console script 或 `python -m fund_agent.cli.main` 编排本地 PDF 到最小 Host/Agent loop，并输出 plain text 答案、citation 和 trace。

当前不是自动报告、字段抽取、投资判断或发布就绪系统。
