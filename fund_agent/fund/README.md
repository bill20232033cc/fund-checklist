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
- parser contract 当前使用 Docling JSON 顶层 `texts[]` 和 `tables[]`：章节来自 `texts[].label == "section_header"`，正文来自 `texts[].text`，locator 来自 `self_ref` 与 `prov[].page_no/bbox`，表格来自 `tables[].data.table_cells[]`。
- parser health 要求存在可读文本、章节或全文替代索引，以及可检索文本；表格可为空。
- `FundDocumentToolService` 使用内存 registry `document_id -> DoclingDocumentStore`，提供七个 public reading tools：`list_reports`、`list_sections`、`read_section`、`search_document`、`list_tables`、`read_table`、`get_excerpt`。
- public tools 成功时返回受控 dataclass 或受控列表；业务失败返回 `ToolFailure`，不向 Agent 抛出 `DocumentToolError`。
- 未分类异常统一映射为 `unavailable`，公共输出不得暴露本地 PDF path、Docling cache path、raw Docling JSON、parser private payload 或异常栈。
- `list_reports` 返回 safe source summary，不暴露 `local_import_id`、本地路径或 cache path。
- `get_excerpt` 只接受 prior tools 返回的受控 `Locator`；section/table/excerpt locator 均按 kind 路由，unknown `section_ref`、`table_ref` 或 document mismatch 返回 `not_found`。
- `list_tables` 返回空列表表示当前文档或范围内无可用表格投影，不是失败。

未实现：Host/Agent tool loop。
