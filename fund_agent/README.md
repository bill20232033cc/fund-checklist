# fund_agent

`fund_agent` 当前实现基金年报阅读工具层 MVP 的最小分层：

```text
fund_agent/service -> FundReadingService
fund_agent/host -> MinimalHost
fund_agent/agent -> deterministic tool loop
fund_agent/fund -> FundDocumentToolService
fund_agent/cli -> fund-checklist read
```

- `fund_agent/fund` 是基金文档领域能力包，不是 `UI -> Service -> Host -> Agent` 四层结构中的一层；它负责本地 PDF 导入、Docling conversion/store、local persistent repository、repository-backed loader 和七个 reading tools。
- `fund_agent/service` 负责 `import_local_report`、`read_local_report`、`list_reports`、`extract_fee_rates` use case，编排本地 PDF 导入、completed catalog 复用、必要时 Docling conversion fallback、hardcoded controlled query profile routing、Service-level routing attempts audit、controlled disclosure target contract、`fee_rates` 多目标阅读定位、`performance_returns` 业绩表现披露定位、三项当前适用年费率受控抽取和 Host 调用。
- `fund_agent/agent` 只通过 `FundDocumentToolService` 调用工具，当前执行 section-first、table-aware retrieval loop。
- `fund_agent/host` 只托管 Agent loop，不理解基金领域，不访问 Fund store 或 Docling raw payload。
- `fund_agent/cli` 只提供 `fund-checklist read`，通过 console script 或 `python -m fund_agent.cli.main` 解析参数并格式化 plain text 答案、citation 和 trace。

`FundReadingService` 是 use case / 业务语义入口；`FundDocumentToolService` 是 Fund 包内部的文档工具边界。二者不可混同：Service 可以使用 Fund 领域能力，但 Fund 不管理 Host run、不解释 UI intent、不实现 Agent loop。

当前不是自动报告、投资判断或发布就绪系统；`performance_returns` 只定位披露和 citation，不抽取净值增长率或基准收益率；`extract_fee_rates` 只覆盖已裁决的三项费率字段，不扩展为通用字段抽取框架。
