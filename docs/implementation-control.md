# fund-checklist implementation-control

更新时间：2026-06-29
当前阶段：`SLICE_0_DEPENDENCY_PREFLIGHT`  
当前角色：control / CIC-lite controller  
当前目标：把 `pyproject.toml` / `uv.lock` / `.gitignore` 作为正式 dependency preflight 纳入控制面板，并初始化 git 首个提交。

## 当前事实

- 当前已有 `fund_agent/` 代码目录和 `tests/` 目录；Slice 1 本地 PDF ingestion 代码与测试已存在。
- 当前已有 `pyproject.toml`、`uv.lock` 和 `.gitignore`。
- `uv run python -c "import docling; ..."` 已通过，输出 `docling import ok`。
- `uv run pytest tests/fund/document_tools/test_local_pdf_source.py` 已通过，输出 `3 passed`。
- 当前有样本 PDF 和历史分析报告；`基金年报/` 作为本地材料目录不纳入 public git，后续按分析需求下载或本地提供。
- `AGENTS.md` 是执行规则入口；`docs/design.md` 是设计真源。
- 当前目录此前不是 git repository；本次允许执行 git 初始化和首个 commit。

## Accepted Decisions

- 产品方向：基金年报阅读工具层，不是字段抽取、自动报告、投资判断或发布就绪。
- MVP source：仅本地 PDF 导入。
- Docling admission：local-PDF MVP 中，PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止路线：Docling candidate-only、benchmark-before-admission、`pdfplumber` fallback、字段抽取 correctness benchmark。
- Runtime：MVP closeout 必须同时通过离线 `FundDocumentToolService` smoke 和最小 Host / Agent tool loop smoke。
- `document_id`：ASCII-only，格式 `fund_code-year-report_type-fingerprint_prefix`；`fingerprint_prefix` 为 `content_fingerprint` 前 16 位 hex。
- `local_import_id`：导入事件身份，仅用于审计 metadata，不作为 public tool 输入。
- `share_class`：MVP 可选 metadata，不强制解析，不参与 `document_id`；无法明确则为 `null`。
- `report_type`：MVP 首批仅 `annual_report`。
- Locator：必须返回 `document_id`、`locator_kind`、section/table ref；page/page_range/internal_ref 可得时透传；`bbox` 仅增强。
- GitHub 仓库：public。
- Dependency preflight：`pyproject.toml` / `uv.lock` 是正式 Slice 0 产物。
- `.gitignore` 必须排除 `.venv/`、`.pytest_cache/`、`.DS_Store`、`基金年报/` 本地材料目录、Docling/cache 临时目录和常见 secret 文件。
- `docling` 版本策略：`pyproject.toml` 使用 `docling>=2.90.0,<3.0.0`；`uv.lock` 锁定实际解析版本，常规开发不得无故升级锁。
- Slice 2 conversion smoke 允许首次联网下载 Docling runtime/model 资源；缓存产物不得纳入 git。若后续要求完全离线/CI 稳定运行，另开预缓存策略，只固定资源版本/校验和。
- Slice 2 timeout：单份真实 PDF smoke 默认 300 秒；cold start download 单独计量，不作为 production conversion SLA。
- Slice 2 batch：5 份年报 batch 默认总预算 1800 秒；batch 必须按 document 独立 timeout、独立失败分类、可断点续跑，单份失败不得静默吞并整批结果。

## CIC-lite Rules

- MVP plan artifact 最多 1 份。
- plan review artifact 最多 1 份。
- plan review `ACCEPTED` 后必须进入代码实现。
- 禁止新增 plan-fix / re-review / evidence gate，除非 review 明确指出违反已裁决硬口径。
- 每个实现 slice 只走：implement -> tests -> diff review。
- Controller 只核边界、diff、测试命令和测试输出。
- Implementation Agent 写代码和测试。
- Review Agent 只 review diff + tests，不产出新 plan，不开新路线。
- 禁止用文档更新代替可运行代码。
- 没有 diff，不算实现；没有测试命令和输出，不算完成；没有 review agent 独立检查，不算 accepted。

## Next Action

完成 Slice 0 收口：

- 更新 `.gitignore`。
- 将 `docling` 依赖范围收敛到 `docling>=2.90.0,<3.0.0`。
- 更新 `uv.lock`。
- 将 dependency preflight 写入 MVP plan 和本控制面板。
- 执行 git 初始化和首个 commit。

Slice 0 后续最小验证：

```bash
uv run python -c "import docling; print('docling import ok')"
uv run pytest tests/fund/document_tools/test_local_pdf_source.py
```

## Implementation Slices

0. Dependency / repository preflight：`pyproject.toml`、`uv.lock`、`.gitignore`、`docling import` 验证、git 初始化。
1. Local PDF ingestion：`PdfSourceProvider`、`PdfBlobStore`、identity、fingerprint、integrity。
2. Docling conversion/store：`DoclingConverter`、`DoclingDocumentStore`、parser_health、raw payload redaction。
3. FundDocumentToolService：7 个 reading tools、bounded output、citation、locator、safe redaction。
4. Minimal Agent loop：`search_document -> read_section` trace，最终回答只引用 tool result。

## MVP Acceptance Matrix

- local PDF import
- PDF integrity failure classification
- Docling conversion
- DoclingDocumentStore parser health
- seven FundDocumentToolService tools
- locator + citation + redaction
- `test_agent_tool_loop_searches_then_reads_section`
- `test_agent_tool_loop_does_not_receive_raw_docling_json`

## Stop Conditions

- 需要新增或改变 document_id / report_type / share_class 规则。
- 需要复制或改写 dayu 代码但没有 license/compliance gate。
- 需要引入外部网络来源策略。
- 计划把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback。
- 计划把阅读工具扩大为字段抽取、自动报告、投资判断、数据仓库晋升或发布就绪。
- 计划只用 fake fixture 证明 production conversion path。
- 文档声称当前未实现能力已完成。
- 计划把 `基金年报/`、`.venv/`、Docling/model cache 或 secret 文件纳入 git。
- Slice 2 conversion smoke 需要无版本约束地升级 Docling 或绕过 `uv.lock`。

## Validation Commands

文档控制面板检查：

```bash
rg -n "SLICE_0_DEPENDENCY_PREFLIGHT|docling>=2.90.0,<3.0.0|基金年报/|test_agent_tool_loop_searches_then_reads_section" AGENTS.md docs/design.md docs/implementation-control.md docs/reviews/fund-document-reading-tool-mvp-plan-20260627.md pyproject.toml .gitignore
wc -l AGENTS.md docs/implementation-control.md
```

后续代码实现最小验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```
