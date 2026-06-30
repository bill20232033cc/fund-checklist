# fund-checklist

基金年报阅读工具层 MVP。

当前成功路径：

```text
local PDF
 -> Docling conversion/store
 -> FundDocumentToolService reading tools
 -> MinimalHost / deterministic Agent loop
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
- 最小 Host / Agent loop：固定执行 `search_document -> read_section`，最终回答只使用 `read_section` tool result。
- 最小 CLI 用户入口：`fund-checklist read`。

安装命令：

```bash
uv sync
```

CLI 使用：

```bash
uv run fund-checklist read --pdf path/to/report.pdf --fund-code 004393 --fund-name 安信企业价值优选混合型证券投资基金 --year 2024
```

测试命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

非目标：

- 不接真实 LLM。
- 不实现 UI。
- 不实现 downloader、batch queue 或 persistent repository。
- 不做字段抽取、自动报告或投资判断。
- 不声明 release ready。

本地样本 PDF、`.fund_checklist/` 工作目录、Docling/model cache、虚拟环境和测试 cache 不纳入 git。
