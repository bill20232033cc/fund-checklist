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
- `fund_agent/service` 负责 `import_local_report`、`read_local_report`、`list_reports`、`extract_fee_rates`、`extract_performance_returns`、`extract_annual_performance` use case，编排本地 PDF 导入、completed catalog 复用、必要时 Docling conversion fallback、Service-level routing attempts audit、disclosure locator contract registry、`fee_rates` 多目标阅读定位、`performance_returns` 业绩表现披露定位、三项当前适用年费率受控抽取、`past_1_year` 净值增长率/业绩比较基准收益率受控抽取、自然年度业绩表格受控抽取和 Host 调用。
- `fund_agent/agent` 只通过 `FundDocumentToolService` 调用工具，当前执行 section-first、table-aware retrieval loop。
- `fund_agent/host` 只托管 Agent loop，不理解基金领域，不访问 Fund store 或 Docling raw payload。
- `fund_agent/cli` 只提供 `fund-checklist read`，通过 console script 或 `python -m fund_agent.cli.main` 解析参数并格式化 plain text 答案、citation 和 trace。
- `fund_agent/preferences` 是投资者偏好域（与 `fund` 平级）：`flomo_parser.py` 用标准库 `html.parser` 把 Flomo HTML 导出解析为结构化 memo，`store.py` 以 SQLite 幂等持久化到 `--work-dir` 下 `preferences/preferences.db`，经 CLI `flomo-import` 子命令使用；`questionnaire.py` + `questionnaire/baseline-v1.json` 提供自建 80 题题库的加载校验与确定性评分（总分 100 + 五维子分 + 辅助 C1-C5，不接 LLM），经 CLI `preference-questionnaire` 子命令使用；`snapshot.py` 生成季度偏好快照（问卷基线 + 行为证据摘要 + 四问反思模板 + 免责声明，不接 LLM），经 CLI `preference-snapshot` 子命令使用；`note_parser.py` 用标准库解析智慧笔记导出 HTML（div 换行/去标签/unescape 后按 Markdown 结构解析，未知类别与声明条数不符 fail-closed），经 CLI `note-import` 子命令幂等写入 `thought_records` + `note_imports`（不接 LLM）。

`FundReadingService` 是 use case / 业务语义入口；`FundDocumentToolService` 是 Fund 包内部的文档工具边界。二者不可混同：Service 可以使用 Fund 领域能力，但 Fund 不管理 Host run、不解释 UI intent、不实现 Agent loop。

当前不是自动报告、投资判断或发布就绪系统；`performance_returns` 默认 reading locator 只定位披露和 citation；`extract_performance_returns` 只在 Service 层基于已定位表格抽取 `past_1_year` 的 `nav_growth_rate` / `benchmark_return_rate` DTO；`extract_annual_performance` 只从固定标题族标准披露表抽取 `report_year` 对应的 `annual_nav_growth_rate` / `annual_benchmark_return_rate` DTO，并保留原文 `过去一年` citation；这些路径都不计算差额或年化收益；`extract_fee_rates` 只覆盖已裁决的三项费率字段，不扩展为通用字段抽取框架。
