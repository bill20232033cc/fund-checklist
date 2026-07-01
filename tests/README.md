# Tests

当前 Slice 1/2/3/4 与 CLI Read Command Gate 测试覆盖本地 PDF 导入、Docling conversion、DoclingDocumentStore、FundDocumentToolService、最小 Host/Agent tool loop 和 `fund-checklist read`：

```bash
uv run pytest tests/fund/document_tools/test_service.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_docling_conversion.py tests/fund/document_tools/test_local_pdf_source.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py
uv run pytest tests/fund/cli/test_cli.py
```

测试范围：

- report identity 与 `document_id` 规则。
- 非 PDF magic bytes 的 `integrity_error` 分类。
- 改名后同一 PDF 仍使用内容指纹生成稳定 `document_id`。
- 重复导入同一 PDF 复用 `document_id`，但 `local_import_id` 不进入 public identity route。
- 真实本地样本 PDF 通过 `DoclingConverter` 写出受控 Docling JSON。
- Docling conversion 失败分类为 `docling_convert_failed`。
- Docling JSON 无可读文本/章节索引时分类为 `parser_health_failed`。
- DoclingDocumentStore 返回带 locator 的章节、bounded section content、表格投影和 ranked search excerpt。
- FundDocumentToolService 使用内存 `document_id -> DoclingDocumentStore` registry 暴露七个 reading tools。
- `list_reports` 返回 safe source summary，不暴露 `local_import_id`、本地路径或 Docling cache path。
- `read_section`、`search_document`、`read_table` 返回 citation 和 locator，且不暴露 raw Docling JSON。
- public tools 捕获 `DocumentToolError` 并返回 `ToolFailure`；unknown locator 返回 `not_found`。
- `get_excerpt` 只接受 prior tools 返回的受控 `Locator`，按 section/table/excerpt locator kind 路由。
- `MinimalFundDocumentAgent` 先执行 `search_document -> read_section`，再通过 `list_tables/read_table` 补充相关表格。
- `AgentRunResult.answer` 成功时只由 section/table tool result 生成。
- table-aware loop 覆盖人物表格信息、持仓表格信息和无相邻表格的 section-only answer。
- `ToolTraceEntry` 记录工具名、显式参数、success/failure 和可选失败码。
- `search_document` 无命中时返回 `AgentRunResult.failure`，不猜测章节。
- `MinimalHost` 只调用 Agent loop，不访问 Docling store、raw Docling JSON 或本地路径。
- `fund-checklist read` 使用 argparse 参数解析，只实现 read 子命令；console script entrypoint 指向 `fund_agent.cli.main:main`。
- CLI happy path 串起 import、converter/store、service、host/agent；CLI 单测用 fake converter 或预置 Docling JSON，避免重复真实 Docling conversion。
- CLI classified failure 输出稳定 failure code 且退出码为 2；unexpected exception 退出码为 1。
- CLI 输出不得包含 raw Docling JSON、本地 cache path 或 `local_import_id`。

MVP 完整验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Post-MVP Slice 6 persistent repository 测试范围：

- completed report 写入 filesystem JSON catalog 后可按 `document_id` 恢复 `DoclingDocumentStore`。
- 恢复后的 `FundDocumentToolService` 可 `search_document`、`read_section`、`list_tables`、`read_table`。
- 重复导入同一 PDF 复用 `document_id` 和 catalog record。
- catalog missing 返回 `not_found`。
- Docling JSON missing/unreadable 返回 `unavailable`。
- catalog identity mismatch 返回 `identity_mismatch`。
- blob fingerprint mismatch 返回 `integrity_error`。
- public output 不泄漏 raw Docling JSON、本地路径、Docling cache path 或 `local_import_id`。
- CLI happy path 写入 completed report catalog，后续同 `document_id` 可复用。

Slice 6 验证命令：

```bash
uv run pytest tests/fund/document_tools/test_persistent_repository.py
uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Slice 6 暂不测试 schema migration、concurrent writes、repair/rebuild、batch、downloader、delete/update lifecycle、SQLite performance、true LLM 或 release readiness。

Post-MVP Slice 7 CLI packaging 验证命令：

```bash
uv sync
uv run fund-checklist read --help
uv run python -m fund_agent.cli.main read --help
uv run pytest tests/fund/cli/test_cli.py
```

Slice 7 只验证 documented console script entrypoint 和 Python module fallback；不新增 CLI 子命令，不做 release packaging、installer、shell completion、downloader、batch 或 true LLM。

Post-MVP Slice 8A fake/injected LLM tool-loop 预期测试范围：

- fake LLM 正常调用 `search_document` / `read_section` 后回答，并携带 section citation。
- fake LLM 调用 `list_tables` / `read_table` 后回答表格问题，并携带 table citation。
- fake LLM 直接给出无 evidence final answer 时 fail-closed。
- fake LLM 请求未知工具或越权工具时 fail-closed。
- fake LLM 输出不泄漏 raw Docling JSON、本地路径、Docling cache path 或 `local_import_id`。
- deterministic `fund-checklist read` CLI 旧路径不回退。

Slice 8A 预期最小验证命令：

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Slice 8A 不测试真实 OpenAI / Claude / 外部模型 API、provider auth、streaming、rate limit、cost tracking、prompt framework、`fund-checklist ask`、字段抽取、自动报告、投资判断或 release readiness。
