# fund-checklist

基金分析助手。

当前成功路径：

```text
PDF
 -> Docling conversion
 -> FundDocumentToolService reading tools
 -> 结构化字段抽取
 -> 多年度聚合
 -> 信号评分
 -> 报告生成
 -> 审计管道
```

已实现能力：

- 本地基金年报 PDF 导入与 PDF integrity 校验。
- Docling conversion 和受控 DoclingDocumentStore。
- `FundDocumentToolService` 七个 reading tools：
  - `list_reports`
  - `list_sections`
  - `read_section`
  - `search_document`
  - `list_tables`
  - `read_table`
  - `get_excerpt`
- locator、citation、bounded output 和 safe redaction。
- Host / Agent loop：先执行 `search_document -> read_section`，再按 query 与章节/页码邻近性读取相关表格，最终回答只使用 section/table tool result。
- 本地 persistent repository：completed report 写入 filesystem JSON catalog，后续同 `document_id` 可恢复并复用。
- 受控 query profile routing：`holdings_top10`、`asset_allocation`、`fee_rates`、`performance_returns`。
- 多年度业绩聚合与持仓追踪。
- 结构化字段抽取（费率、业绩、持仓、资产配置）。
- 确定性信号评分（6 指标）。
- 8 章分析报告生成。
- 三层审计管道（程序 + LLM + 复核，4 类 22 项）。
- CLI 9 个子命令（read / multi-year / import / holdings / allocation / fees / audit / deep-audit / generate）。

安装命令：

```bash
uv sync
```

CLI 使用：

```bash
# 批量导入 PDF 到 catalog
uv run fund-checklist import \
  --pdf-dir ./基金年报/ \
  --fund-code 004393 \
  --fund-name '安信企业价值优选混合型证券投资基金' \
  --year-range 2022-2025

# 单份年报阅读问答
uv run fund-checklist read \
  --pdf path/to/report.pdf \
  --fund-code 004393 \
  --fund-name '安信企业价值优选混合型证券投资基金' \
  --year 2024 \
  --query '前十大持仓'

# 多年度业绩聚合
uv run fund-checklist multi-year \
  --fund-code 004393 \
  --years 2022,2023,2024,2025

# 多年度持仓追踪
uv run fund-checklist holdings \
  --fund-code 004393 \
  --years 2022,2023,2024,2025
```

样本 PDF：

本项目不包含真实基金年报 PDF。如需测试，请从基金公司官网或公开信息披露平台下载年报 PDF，放入 `基金年报/` 目录。文件名需包含基金名称和年份（如 `安信企业价值优选混合型证券投资基金2024年年度报告.pdf`），以便 `import` 命令自动匹配。

测试命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

非目标：

- 不实现 UI。
- 不实现 downloader 或 batch queue。
- 不做投资判断。
- 不声明 release ready。

本地样本 PDF、`.fund_checklist/` 工作目录、Docling/model cache、虚拟环境和测试 cache 不纳入 git。
