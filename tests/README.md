# Tests

当前 Slice 1 测试只覆盖本地 PDF 导入边界：

```bash
uv run pytest tests/fund/document_tools/test_local_pdf_source.py
```

测试范围：

- report identity 与 `document_id` 规则。
- 非 PDF magic bytes 的 `integrity_error` 分类。
- 改名后同一 PDF 仍使用内容指纹生成稳定 `document_id`。
- 重复导入同一 PDF 复用 `document_id`，但 `local_import_id` 不进入 public identity route。

MVP 完整验证命令将在后续 Slice 补齐 Docling、ToolService 和 Agent loop 后使用：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

