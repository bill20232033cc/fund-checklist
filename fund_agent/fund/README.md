# Fund 文档能力

当前已实现 Slice 1: Local PDF Ingestion、Slice 2: Docling Conversion / Store，以及 Slice 3: FundDocumentToolService。

- `LocalPdfSourceProvider` 只支持本地 PDF 导入。
- `PdfBlobStore` 负责受控落盘和读取，不向 public identity 暴露本地路径。
- `document_id` 按 `fund_code-year-report_type-fingerprint_prefix` 生成。
- `content_fingerprint` 使用 PDF bytes 的 `sha256`。
- `local_import_id` 仅表示导入事件，不参与 public tool route。
- `share_class` 为可选 metadata，不参与 `document_id`。
- Content-Type、空内容、PDF magic bytes、原子写入失败均分类为稳定 failure code。
- `DoclingConverter` 使用 `docling.document_converter.DocumentConverter.convert()` 把受控 PDF bytes 转成 Docling JSON，并把输出写到调用方指定的 tmp/cache 根目录。
- `DoclingDocumentStore` 只从 Docling JSON 暴露受控 section、table、search、locator、citation 模型，不暴露 raw JSON、本地 PDF path 或 cache path。
- `search_document` 的检索投影覆盖 section text、table caption 和 `DEFAULT_TABLE_MAX_ROWS` 内的 bounded table rows；table-backed result 返回 `table_ref`、table locator、citation 和受控 `match_kind`。
- `match_kind` 取值固定为 `section_text`、`table_caption`、`table_row`；row 命中摘录只返回命中行的有界文本，不返回整表。
- parser contract 当前使用 Docling JSON 顶层 `texts[]` 和 `tables[]`：章节来自 `texts[].label == "section_header"`，正文来自 `texts[].text`，locator 来自 `self_ref` 与 `prov[].page_no/bbox`，表格来自 `tables[].data.table_cells[]`。
- parser health 要求存在可读文本、章节或全文替代索引，以及可检索文本；表格可为空。
- `FundDocumentToolService` 使用内存 registry `document_id -> DoclingDocumentStore`，提供七个 public reading tools：`list_reports`、`list_sections`、`read_section`、`search_document`、`list_tables`、`read_table`、`get_excerpt`。
- public tools 成功时返回受控 dataclass 或受控列表；业务失败返回 `ToolFailure`，不向 Agent 抛出 `DocumentToolError`。
- 未分类异常统一映射为 `unavailable`，公共输出不得暴露本地 PDF path、Docling cache path、raw Docling JSON、parser private payload 或异常栈。
- `list_reports` 返回 safe source summary，不暴露 `local_import_id`、本地路径或 cache path。
- `get_excerpt` 只接受 prior tools 返回的受控 `Locator`；section/table/excerpt locator 均按 kind 路由，unknown `section_ref`、`table_ref` 或 document mismatch 返回 `not_found`。
- `list_tables` 返回空列表表示当前文档或范围内无可用表格投影，不是失败。

Host/Agent tool loop 已实现；Fund 层仍只提供受控文档工具，不理解 Agent 策略。

## Post-MVP Slice 6 Persistent repository

当前已实现 local persistent repository：

- 使用 filesystem JSON catalog 登记 completed report。
- 只登记已通过 PDF integrity、Docling conversion 和 parser_health 的本地年报。
- 通过 repository-backed loader 按 `document_id` 恢复 `DoclingDocumentStore`，再交给 `FundDocumentToolService`。
- 保持七个 public reading tools API 不变。
- CLI `fund-checklist read` 优先按 catalog 复用 completed report；只有 catalog missing 时才执行首次 Docling conversion。

catalog 最小记录 safe identity、`stored_blob_ref`、`docling_json_ref`、parser health summary 和创建/更新时间；不得把 raw Docling JSON、本地绝对路径、Docling cache path 或 `local_import_id` 暴露给 Agent/Host/UI。

Slice 6 failure mapping：

- catalog missing -> `not_found`
- catalog schema incompatible -> `schema_drift`
- identity mismatch -> `identity_mismatch`
- Docling JSON missing/unreadable -> `unavailable`
- Docling JSON schema drift -> `schema_drift`
- parser health failed -> `parser_health_failed`
- blob fingerprint mismatch -> `integrity_error`

Slice 6 不做 SQLite、schema migration、concurrent write locking、repair/rebuild/reconvert、downloader、batch queue、delete/update lifecycle、true LLM 或 release readiness。
