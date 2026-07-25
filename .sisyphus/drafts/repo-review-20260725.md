# 全仓深度审查报告

## 审查结论

**发现 2 个严重 + 5 个高 + 7 个中 + 1 个低 = 15 个问题**

最需优先处理的三个问题：
1. **#1 严重**：`annual_report_documents` 工具 schema 类型错误 — LLM 聚合工具当前必然失败
2. **#2 严重**：`parse_blob_ref` 路径遍历 — 安全漏洞
3. **#3 高**：`ask_question` 短路逻辑无 citation — 用户收到无引用的答案

---

## Findings

### 1-未修复-[严重]-`annual_report_documents` 工具 schema 类型错误
- **入口/函数**: `DeepSeekLlmClient._tool_schemas()` 中 `AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE` schema
- **文件**: `fund_agent/agent/deepseek_llm.py:518-527`
- **直接证据**: `items: {"type": "string"}` 但 `AnnualReportDocument`（`service/models.py:264-279`）有 `year: int` 和 `document_id: str` 字段
- **影响**: LLM 按 schema 发送字符串数组 → handler 抛出 `SCHEMA_DRIFT`，聚合工具在真实 LLM 路径下必然失败
- **建议改法**: 修改 schema 为 `{"type": "array", "items": {"type": "object", "properties": {"year": {"type": "integer"}, "document_id": {"type": "string"}}, "required": ["year", "document_id"]}}`
- **修复风险**: 低

### 2-未修复-[严重]-`parse_blob_ref` 路径遍历风险
- **入口/函数**: `PdfBlobStore.read_pdf()` 和 `FilesystemReportRepository._assert_blob_fingerprint()`
- **文件**: `fund_agent/fund/document_tools/local_pdf_source.py:247-263`
- **直接证据**: `return ref[len(_BLOB_REF_PREFIX):]` 无格式校验，直接用于路径构造
- **影响**: 通过构造恶意 `stored_blob_ref` 可实现任意目录文件读取
- **建议改法**: 在 `parse_blob_ref` 中增加 `_DOCUMENT_ID_FUND_CODE_PATTERN` + 年份 + hex 校验
- **修复风险**: 低

### 3-未修复-[高]-`ask_question` 路由短路逻辑无 citation
- **入口/函数**: `FundReadingService.ask_question()`
- **文件**: `fund_agent/service/extraction.py:851-879`
- **直接证据**: `extraction.py:865-868` — citation 提取循环为空 `pass`
- **影响**: 用户收到原始工具输出拼接文本，无 citation 引用可追溯
- **建议改法**: 从 host.run() 结果收集 citations，或移除短路逻辑强制走 LLM
- **修复风险**: 中

### 4-未修复-[高]-`service.py` 访问私有属性
- **入口/函数**: `FundDocumentToolService._identity_from_store()`
- **文件**: `fund_agent/fund/document_tools/service.py:332-338`
- **直接证据**: `getattr(store, "_identity", None)` 访问单下划线 private 属性
- **影响**: DoclingDocumentStore 重构属性名时 `_identity_from_store` 静默返回 `None`
- **建议改法**: 在 `DoclingDocumentStore` 添加 `@property identity`
- **修复风险**: 低

### 5-未修复-[高]-原子写入缺少 fsync
- **文件**: `local_pdf_source.py:384-393`；`persistent_repository.py:182-191`
- **直接证据**: `os.replace(temporary, path)` 前无 `os.fsync()`
- **影响**: 系统崩溃后 catalog/identity_index 可能内容不完整
- **修复风险**: 低

### 6-未修复-[高]-daemon thread 超时后资源泄漏
- **文件**: `fund_agent/host/minimal_host.py:168-169`
- **直接证据**: daemon thread 无 cancel 机制，持有 `self._agent` 引用到进程退出
- **影响**: 长时间运行进程中多次超时的线程累计内存泄漏
- **修复风险**: 中

### 7-未修复-[中]-双重模板实现
- **文件**: `extraction.py:3401` 和 `audit_pipeline.py:2351`
- **直接证据**: 两处独立实现 Ch0-Ch7 模板生成
- **修复风险**: 低

### 8-未修复-[中]-静默吞噬异常（4处）
- **文件**: `extraction.py:1359-1362`、`extraction.py:1628-1631`、`extraction.py:1752-1755`、`extraction.py:2448`
- **直接证据**: `except Exception: pass` 或 `except Exception: _extraction_error = True`，无 logging
- **修复风险**: 低

### 9-未修复-[中]-run/run_stream 代码重复 80%
- **文件**: `fund_agent/agent/llm_tool_loop.py:259-416`
- **修复风险**: 中

### 10-未修复-[中]-SSE 流式传输无限等待风险
- **文件**: `fund_agent/agent/deepseek_llm.py:176-178`
- **直接证据**: `urllib.request.urlopen` 有连接超时但无读取超时
- **修复风险**: 中

### 11-未修复-[中]-E2E 测试静默跳过
- **文件**: `tests/fund/test_e2e_regression.py:56-181`
- **直接证据**: `pytest.skip()` 静默跳过，无 CI 强制断言
- **修复风险**: 低

### 12-未修复-[低]-空 citations 绕过校验
- **文件**: `fund_agent/agent/llm_tool_loop.py:527-549`
- **直接证据**: `if final_answer.citations:` 为 False 时跳过全部校验

---

## 汇总

| 类别 | 严重 | 高 | 中 | 低 |
|------|------|-----|-----|-----|
| 架构边界 | — | 2 | 2 | — |
| 安全 | 1 | 1 | — | 1 |
| 错误处理 | — | — | 1 | — |
| 数据一致性 | 1 | — | — | — |
| 并发/资源 | — | 1 | 1 | — |
| 测试质量 | — | — | 1 | — |
| 代码重复 | — | — | 2 | — |
| **合计** | **2** | **5** | **7** | **1** |

---

## Residual Risk

- `test_extraction.py` 共享可变类变量导致测试间耦合（61 处 `.clear()` 调用）
- 5 处 `# type: ignore` 表明 Agent/Host 层类型契约存在偏差
- `docling_store.py` 依赖 Docling JSON 内部结构，Docling 升级可能静默破坏解析器
- 全仓无并发/线程安全回归测试
- 全仓无 benchmark/性能回归测试

---

*审查日期：2026-07-25 | 审查方式：4 subagent 并行 | 输出路径：.sisyphus/drafts/repo-review-20260725.md*
