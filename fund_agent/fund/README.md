# Fund 文档能力

当前已实现 Slice 1: Local PDF Ingestion。

- `LocalPdfSourceProvider` 只支持本地 PDF 导入。
- `PdfBlobStore` 负责受控落盘和读取，不向 public identity 暴露本地路径。
- `document_id` 按 `fund_code-year-report_type-fingerprint_prefix` 生成。
- `content_fingerprint` 使用 PDF bytes 的 `sha256`。
- `local_import_id` 仅表示导入事件，不参与 public tool route。
- `share_class` 为可选 metadata，不参与 `document_id`。
- Content-Type、空内容、PDF magic bytes、原子写入失败均分类为稳定 failure code。

未实现：Docling conversion、DoclingDocumentStore、FundDocumentToolService、Host/Agent tool loop。

