# Tests

当前 Slice 1/2 测试覆盖本地 PDF 导入、Docling conversion 和 DoclingDocumentStore：

```bash
uv run pytest tests/fund/document_tools/test_docling_conversion.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_local_pdf_source.py
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

MVP 完整验证命令将在后续 Slice 补齐 Docling、ToolService 和 Agent loop 后使用：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```
