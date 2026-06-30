# Fund 文档能力

当前已实现 Slice 1: Local PDF Ingestion，以及 Slice 2: Docling Conversion / Store。

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

未实现：FundDocumentToolService、Host/Agent tool loop。
