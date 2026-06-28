# fund-checklist architecture

更新时间：2026-06-28  
文档状态：轻量架构坐标系；不是当前实现说明，不是完成证据。  
适用范围：基金年报阅读工具 MVP 及其直接后续迭代。

## 0. 用途

本文固定后续计划、实现和 review 时不应摇摆的架构判断。

- 若本文与当前代码不一致，不能据此声称代码已实现。
- 若实现计划违反本文边界，应停止并修正计划。
- 本文不得替代 `docs/implementation-control.md` 的当前执行面板。
- 本文不得替代测试、diff 或可执行证据。

## 1. 北极星

本项目的 MVP 是让 Agent 能稳定阅读基金年报。

成功标准：

```text
本地 PDF
 -> Docling JSON
 -> FundDocumentToolService
 -> Agent tools
 -> 可引用的章节 / 搜索 / 表格 / excerpt 结果
```

非目标：

- 字段抽取
- 自动报告生成
- 投资判断
- 报告渲染
- 数据仓库晋升
- 发布就绪判定

## 2. 层次

目标层次：

```text
UI -> Service -> Host -> Agent / Fund
```

职责：

- UI：用户交互、命令入口、展示；只依赖 Service 公共接口。
- Service：use case、用户请求语义、scene / prompt / contract 组装、Host 调用。
- Host：session / run 生命周期、并发、取消、超时、事件、恢复、reply outbox。
- Agent：tool loop、tool trace、上下文预算、工具调用。
- Fund：基金文档领域能力包，包含 PDF source、blob、Docling、document store、tool service。

禁止跨层：

- UI / Service / Host / prompt 不得直接读取 raw PDF。
- UI / Service / Host / prompt 不得直接读取 raw Docling JSON。
- UI / Service / Host / prompt 不得接收本地 cache path、PDF path、URL secret 或 parser private payload。

## 3. Fund 文档主链路

MVP 主链路固定为：

```text
PdfSourceProvider
 -> PdfBlobStore
 -> DoclingConverter
 -> DoclingDocumentStore
 -> FundDocumentToolService
 -> Agent read tools
```

边界：

- `PdfSourceProvider` 只负责本地 PDF 导入和 source identity。
- `PdfBlobStore` 只负责受控落盘、原子写入、读取和 fingerprint。
- `DoclingConverter` 只负责 `PDF -> Docling JSON`。
- `DoclingDocumentStore` 只暴露受控文档模型，不向上层暴露 raw payload。
- `FundDocumentToolService` 是 public reading tools 的唯一入口。

## 4. 稳定契约

身份：

- `document_id = fund_code-year-report_type-fingerprint_prefix`
- `fingerprint_prefix = content_fingerprint` 前 16 位 hex
- `document_id` 表示内容身份，用于 public reading tools
- `local_import_id` 表示导入事件身份，仅用于审计 metadata
- `share_class` 是可选 metadata，不参与 `document_id`
- `report_type` MVP 首批仅 `annual_report`

工具：

- `list_reports`
- `list_sections`
- `read_section`
- `search_document`
- `list_tables`
- `read_table`
- `get_excerpt`

输出必须包含：

- bounded content
- locator
- citation metadata
- safe redaction
- stable failure code

## 5. Docling 准入口径

Docling production path for local-PDF MVP 已准入。

固定规则：

- PDF 通过 integrity check 后进入 `DoclingConverter`。
- Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- parser_health 失败时返回 `parser_health_failed` 并 fail-closed。
- 不做与 `pdfplumber` 的替代路线比较。
- 不做字段抽取 correctness benchmark。
- 禁止把 Docling 改回 candidate-only 或 benchmark-before-admission。

## 6. MVP closeout

MVP closeout 必须同时证明：

- `FundDocumentToolService` 离线工具 smoke 通过。
- 最小 Host / Agent tool loop smoke 通过。

最小 Agent trace：

```text
search_document(document_id, query="基金经理")
 -> section_ref / locator
 -> read_section(document_id, section_ref)
 -> final answer uses only tool result
```

必须通过：

- `test_agent_tool_loop_searches_then_reads_section`
- `test_agent_tool_loop_does_not_receive_raw_docling_json`

## 7. 测试坐标

MVP 必须包含：

- local PDF import tests
- PDF integrity failure classification tests
- Docling conversion tests
- 至少一个仓库内真实本地样本 PDF 的 Docling conversion smoke
- DoclingDocumentStore parser_health tests
- ToolService contract tests
- Minimal Agent loop tests

fake fixture 只能测试边界和错误，不得证明 production conversion path。

## 8. Dayu 使用边界

Dayu 是参考，不是生产 runtime 依赖。

可借鉴：

- source / blob / processed repository 形态
- processor registry
- tool service
- parser signature
- rejected artifact / failure classification

禁止：

- 直接引入 `dayu-agent`
- 直接引入 `dayu.host`
- 直接引入 `dayu.engine`
- 未经 license/compliance gate 复制或改写 Dayu 代码
