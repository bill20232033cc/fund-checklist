# Fund Document Reading Tool MVP Plan

日期：2026-06-28
状态：MVP plan accepted；Dependency preflight added by controller裁决
流程：CIC-lite；不使用 gateflow / phaseflow

## 1. Scope

本计划只覆盖基金年报阅读工具层：

```text
local PDF -> Docling JSON -> DoclingDocumentStore -> FundDocumentToolService -> Agent tools
```

非目标：字段抽取、自动报告、投资判断、报告渲染、数据仓库晋升、发布就绪、外部网络来源 discovery、`pdfplumber` fallback、Docling correctness benchmark。

硬口径：

- MVP source 仅本地 PDF 导入。
- Docling production path for local-PDF MVP 已准入。
- PDF 通过 integrity check 后进入 `DoclingConverter`。
- Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止 candidate-only、benchmark-before-admission、`pdfplumber` fallback。
- `document_id = fund_code-year-report_type-fingerprint_prefix`。
- `fingerprint_prefix = content_fingerprint` 前 16 位 hex。
- `document_id` 是 public reading tools 的内容身份。
- `local_import_id` 只作审计 metadata，不作 public tool 输入。
- `share_class` 可选，不参与 `document_id`；无法明确时为 `null`。
- `report_type` MVP 首批仅 `annual_report`。
- fake fixture 只能测试边界和错误，不得证明 production conversion path。
- dependency preflight 是正式 Slice 0；`pyproject.toml` / `uv.lock` / `.gitignore` 是前置准入产物。
- plan review `ACCEPTED` 后进入代码 slice；当前 plan 是唯一 MVP plan artifact。

## 2. Exact Write Set

除对应 slice 的路径外，不得修改其它文件；不得修改 `docs/fund-analysis-template-draft.md`、`基金年报/*.md`、`基金年报/*.pdf`、任意 Dayu 仓库或 Dayu runtime 依赖。

### Slice 0: Dependency / Repository Preflight

```text
.gitignore
pyproject.toml
uv.lock
docs/implementation-control.md
docs/reviews/fund-document-reading-tool-mvp-plan-20260627.md
```

Slice 0 裁决：

- GitHub 仓库创建为 public。
- `基金年报/` 作为本地材料目录不纳入 public git；后续按分析需求下载或本地提供。
- `docling` 版本范围采用 `docling>=2.90.0,<3.0.0`；`uv.lock` 锁定实际解析版本，常规开发不得无故 `uv lock --upgrade`。
- 首次安装依赖允许联网下载 Python wheel。
- Slice 2 conversion smoke 允许 Docling 按锁定包版本下载 runtime/model 资源；缓存目录必须固定在可忽略的本地目录，不得纳入 git。
- 若后续要求完全离线/CI 稳定运行，另行建立预缓存策略；预缓存只固定资源版本/校验和，不把大模型或缓存产物提交到仓库。

### Slice 1: Local PDF Ingestion

```text
fund_agent/__init__.py
fund_agent/fund/__init__.py
fund_agent/fund/document_tools/__init__.py
fund_agent/fund/document_tools/constants.py
fund_agent/fund/document_tools/errors.py
fund_agent/fund/document_tools/models.py
fund_agent/fund/document_tools/local_pdf_source.py
fund_agent/fund/README.md
tests/fund/document_tools/test_local_pdf_source.py
tests/README.md
```

### Slice 2: Docling Conversion / Store

```text
fund_agent/fund/document_tools/constants.py
fund_agent/fund/document_tools/errors.py
fund_agent/fund/document_tools/models.py
fund_agent/fund/document_tools/docling_converter.py
fund_agent/fund/document_tools/docling_store.py
fund_agent/fund/README.md
tests/fund/document_tools/test_docling_conversion.py
tests/fund/document_tools/test_docling_store.py
tests/README.md
```

### Slice 3: FundDocumentToolService

```text
fund_agent/fund/document_tools/constants.py
fund_agent/fund/document_tools/errors.py
fund_agent/fund/document_tools/models.py
fund_agent/fund/document_tools/service.py
fund_agent/fund/README.md
tests/fund/document_tools/test_service.py
tests/README.md
```

### Slice 4: Minimal Agent Loop

```text
fund_agent/agent/__init__.py
fund_agent/agent/tool_loop.py
fund_agent/agent/README.md
fund_agent/host/__init__.py
fund_agent/host/minimal_host.py
fund_agent/host/README.md
fund_agent/README.md
docs/design.md
tests/fund/agent/test_minimal_tool_loop.py
tests/README.md
```

`docs/design.md` 只允许同步已实现的最小 Host/Agent 边界；不得写发布就绪、投资判断或自动报告能力。

## 3. Slice Order

0. Slice 0: dependency/repository preflight，完成 `pyproject.toml`、`uv.lock`、`.gitignore`、`docling import` 验证和 git 初始化。
1. Slice 1: local PDF ingestion，完成 identity、fingerprint、integrity、受控 blob 引用。
2. Slice 2: Docling conversion/store，完成真实 conversion、parser_health、受控文档模型。
3. Slice 3: 七个 `FundDocumentToolService` reading tools，完成 bounded output、locator、citation、redaction。
4. Slice 4: minimal Host/Agent tool loop，完成 `search_document -> read_section` smoke。

每个 slice 只走：

```text
implement -> tests -> diff review
```

Slice 2 conversion smoke 建议口径：

- 超时：`single_pdf_smoke_timeout_seconds = 300`；超过则分类为 `unavailable` 或 `docling_convert_failed`，以实际异常区分。
- cold start download 单独计量，不作为 production conversion SLA。
- batch conversion 使用 per-document timeout 和 resumable queue，不用单个长同步任务吞并所有年份。
- 5 份年报 batch 默认 `max_runtime_seconds = 1800`；单份失败或超时必须返回 per-document classified failure，不得静默失败或让整批结果不可用。
- 输出目录：测试使用 `tmp_path` 下的受控 output/cache，不写入 `基金年报/` 或源码目录。
- 缓存目录：测试通过环境变量把 Docling/HuggingFace/模型缓存固定到 `tmp_path` 或 `.docling_cache/`；`.gitignore` 排除该目录。
- 失败分类：缺少依赖或模型资源临时不可用为 `unavailable`；转换 API 抛出的 PDF 转换失败为 `docling_convert_failed`；转换成功但受控 parser contract 不满足为 `schema_drift` 或 `parser_health_failed`。

## 4. Schema

集中定义常量，禁止魔法字符串：

```text
ReportType: annual_report
SourceKind: local_pdf
FailureCode: not_found | unavailable | schema_drift | identity_mismatch | integrity_error | docling_convert_failed | parser_health_failed
LocatorKind: section | table | excerpt
ToolName: list_reports | list_sections | read_section | search_document | list_tables | read_table | get_excerpt
```

核心 dataclass 写入 `fund_agent/fund/document_tools/models.py`；class 和 public function 必须有中文 docstring。

```text
ReportIdentity:
  fund_code: str
  fund_name: str
  year: int
  report_type: Literal["annual_report"]
  source_kind: Literal["local_pdf"]
  local_import_id: str
  content_fingerprint: str
  document_id: str
  share_class: str | None

PdfImportRequest:
  path: Path
  fund_code: str
  fund_name: str
  year: int
  report_type: Literal["annual_report"]
  share_class: str | None = None
  content_type: str = "application/pdf"

PdfImportResult:
  identity: ReportIdentity
  stored_blob_ref: str

Locator:
  document_id: str
  locator_kind: Literal["section", "table", "excerpt"]
  section_ref: str | None
  table_ref: str | None
  page_no: int | None
  page_range: tuple[int, int] | None
  internal_ref: str | None
  internal_ref_available: bool
  bbox: dict[str, float] | None

Citation:
  document_id: str
  fund_code: str
  fund_name: str
  year: int
  report_type: str
  locator: Locator

SectionSummary:
  section_ref: str
  title: str
  level: int
  parent_ref: str | None
  locator: Locator
  preview: str

TableSummary:
  table_ref: str
  caption: str | None
  section_ref: str | None
  locator: Locator
  row_count: int | None
  column_count: int | None

ToolFailure:
  code: FailureCode
  message: str
```

Identity rule：

```text
content_fingerprint = stable hash of PDF bytes
fingerprint_prefix = first 16 hex chars of content_fingerprint
document_id = f"{fund_code}-{year}-{report_type}-{fingerprint_prefix}"
```

## 5. Failure Classification

公共失败必须返回稳定 `FailureCode`，不得泄漏内部异常、本地路径、cache path、raw Docling JSON、parser private payload、URL secret 或 provider secret。

| Code | Trigger | Behavior |
| --- | --- | --- |
| `not_found` | `document_id`、`section_ref`、`table_ref` 或 locator 不存在 | fail-closed |
| `unavailable` | 本地依赖或 Docling runtime 临时不可用 | 显式返回，可重试 |
| `schema_drift` | Docling JSON 偏离当前 parser contract | fail-closed |
| `identity_mismatch` | 同 fingerprint 已存身份与导入请求冲突 | fail-closed |
| `integrity_error` | Content-Type、PDF magic bytes、非空内容或原子写入失败 | fail-closed |
| `docling_convert_failed` | PDF 到 Docling JSON 转换失败 | fail-closed |
| `parser_health_failed` | 无可读文本且无章节/可替代章节索引 | fail-closed |

fallback 只能由失败分类显式驱动；禁止用 fallback 掩盖 `schema_drift`、`identity_mismatch`、`integrity_error`。

## 6. Tool Contract

`FundDocumentToolService` 是 public reading tools 唯一入口。

```text
list_reports(fund_code=None, year=None, report_type=None)
list_sections(document_id)
read_section(document_id, section_ref, max_chars=None)
search_document(document_id, query, within_section_ref=None, max_results=None)
list_tables(document_id, within_section_ref=None)
read_table(document_id, table_ref, max_rows=None)
get_excerpt(document_id, locator)
```

工具输出必须包含 bounded content、locator、citation metadata、safe redaction、stable failure code。禁止输出本地 PDF path、cache path、raw Docling JSON、parser private payload、URL secret、provider secret。

Minimal Agent trace：

```text
search_document(document_id, query="基金经理")
 -> section_ref / locator
 -> read_section(document_id, section_ref)
 -> final answer uses only tool result
```

## 7. Test Matrix

```text
tests/fund/document_tools/test_local_pdf_source.py
- test_import_local_pdf_preserves_report_identity
- test_import_local_pdf_rejects_non_pdf_magic_bytes
- test_import_local_pdf_uses_content_fingerprint_not_filename
```

必须覆盖：`document_id` 规则、改名后 identity 稳定、非 PDF magic bytes 返回 `integrity_error`、重复导入复用 `document_id`、`local_import_id` 不作 public tool 输入。

```text
tests/fund/document_tools/test_docling_conversion.py
- test_convert_local_pdf_writes_docling_json
- test_convert_failure_returns_docling_convert_failed
- test_parser_health_fails_when_no_text_and_no_sections
```

真实本地样本 PDF smoke 必须走真实 `DoclingConverter`：

```text
基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf
fund_code=004393
fund_name=安信企业价值优选混合型证券投资基金
year=2024
report_type=annual_report
share_class=null
```

```text
tests/fund/document_tools/test_docling_store.py
- test_store_lists_sections_with_locator
- test_store_reads_section_with_bounded_text
- test_store_lists_and_reads_tables
- test_store_search_returns_ranked_excerpt
```

必须覆盖：parser_health 后才进入 store；section 返回 `section_ref`、locator、preview；table 可为空但不得破坏 section/search；search 返回 ranked excerpt、section_ref、locator、citation。

```text
tests/fund/document_tools/test_service.py
- test_list_reports_returns_safe_source_summary
- test_read_section_redacts_local_paths
- test_search_document_returns_citation_and_locator
- test_read_table_returns_table_ref_and_section_ref
- test_get_excerpt_rejects_unknown_locator
```

必须覆盖：七个 tools 的 public contract、本地路径与 raw Docling JSON redaction、unknown locator 返回 `not_found`、bounded output 与 truncated 标记。

```text
tests/fund/agent/test_minimal_tool_loop.py
- test_agent_tool_loop_searches_then_reads_section
- test_agent_tool_loop_does_not_receive_raw_docling_json
```

MVP closeout 不接受 only ToolService tests；必须同时通过 ToolService smoke 和 minimal Host/Agent tool loop smoke。

## 8. Docs Sync

按实际修改同步：

- 修改 `fund_agent/fund/` 同步 `fund_agent/fund/README.md`。
- 修改 `fund_agent/agent/` 同步 `fund_agent/agent/README.md`。
- 修改 `fund_agent/host/` 同步 `fund_agent/host/README.md`。
- 修改分层或 Service/Host/Agent/Fund 边界同步 `fund_agent/README.md` 与 `docs/design.md`。
- 修改测试结构或命令同步 `tests/README.md`。

禁止用 docs sync 替代可运行代码和测试。

## 9. Validation

Slice 级 closeout 必须报告实际命令和输出。Slice 1 在 Agent tests 尚不存在前可先跑：

```bash
uv run pytest tests/fund/document_tools/test_local_pdf_source.py
```

MVP closeout 固定最小验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

## 10. Review Instruction

Plan review 只审本文件是否满足 `AGENTS.md`、`docs/implementation-control.md`、`docs/architecture.md`、`docs/design.md` 已裁决口径。

输出格式：

```text
Verdict: ACCEPTED
```

或：

```text
Verdict: NEEDS_FIX
Findings:
- ...
```

`NEEDS_FIX` 只能列同一 plan artifact 的最小修复项并停止。不得创建新的 plan、plan-fix、re-review、evidence、control-sync、release-readiness artifact。

## 11. Stop Conditions

立即停止并报告：

- 需要新增或改变 `document_id` / `report_type` / `share_class` 规则。
- 需要复制或改写 Dayu 代码但没有 license/compliance gate。
- 需要引入外部网络来源策略。
- 计划把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback。
- 计划把阅读工具扩大为字段抽取、自动报告、投资判断、数据仓库晋升或发布就绪。
- 计划只用 fake fixture 证明 production conversion path。
