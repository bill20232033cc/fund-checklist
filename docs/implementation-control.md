# fund-checklist implementation-control

更新时间：2026-07-01
当前阶段：`POST_MVP_SLICE_8A_DESIGN_SYNC`
当前角色：control / CIC-lite controller  
当前目标：docs-only 同步 Slice 8A fake/injected LLM tool-loop contract。只裁决下一实现 slice 的边界、非目标和测试口径；不实现真实 LLM、不新增 CLI 参数、不进入 release readiness、downloader、字段抽取、自动报告或投资判断。

## 当前事实

- Slice 1-4 已完成并通过 CIC-lite diff review。
- 当前已实现本地 PDF 导入、Docling conversion/store、`FundDocumentToolService` 七个 reading tools 和最小 Host / Agent loop。
- Post-MVP Slice 5 当前实现 table-aware Agent loop：`search_document -> read_section -> list_tables -> read_table`，按 query、section proximity、page proximity 选择相关表格，最终回答只使用 section/table tool result。
- 真实样本 CLI smoke 已验证 `query="基金经理"` 时，Answer 包含基金经理表格中的“张明”，并输出 section citation 与 table citation。
- MiMo review 已按 Post-MVP Slice 5 口径输出 `ACCEPTED`；Slice 5 可视为本地 accepted。
- Post-MVP Slice 6 当前实现 filesystem JSON catalog persistent repository：只记录 completed report，并可按 `document_id` 恢复 `DoclingDocumentStore` 给 `FundDocumentToolService` 使用。
- `fund-checklist read` 已接入 repository-backed loader；catalog 中已有 completed report 时复用 store，不重复调用 Docling converter。
- Slice 6 review 已结束；P0 audit 确认 identity mismatch、private output redaction、incomplete/unhealthy fail-closed 和 stable failure mapping 达到 Slice 6 最小接受标准。
- Post-MVP Slice 7 当前实现 CLI packaging / command entry polish：`uv run fund-checklist read --help` 与 `uv run python -m fund_agent.cli.main read --help` 均可用。
- `uv sync` 已验证不再出现 project scripts entrypoint 被跳过的警告。
- Slice 5-7 已提交并推送到 `origin/main`，当前最新提交为 `b618e20 feat: add table-aware reading, persistent catalog, and CLI entrypoint`。
- MVP closeout 命令已通过：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

结果：`17 passed, 1 warning`。

- warning 是 Docling internal deprecation warning，不改变 MVP closeout 结论。
- 根 `README.md` 只写 public repo 用户成功路径、安装/测试命令、本地 PDF 不入库和当前不支持能力。
- 当前有样本 PDF 和历史分析报告；`基金年报/` 作为本地材料目录不纳入 public git，后续按分析需求下载或本地提供。
- `AGENTS.md` 是执行规则入口；`docs/design.md` 是设计真源。

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
- MVP Slice 4 closeout 时，最小 Agent loop 固定执行 `search_document -> read_section`；该事实是 MVP 历史验收口径，不是当前 Post-MVP Slice 5 的上限。
- Post-MVP Slice 5 允许 Agent 在 `read_section` 后读取同 section、同页或相邻页的候选表格；LLM/Agent 输入真源仍是受控 tool result + locator/citation，不是 raw Docling JSON。
- Post-MVP Slice 6 采用 filesystem JSON catalog 作为 local persistent repository 起点；不引入 SQLite，不新增 downloader，不改变七个 public reading tools API。
- Slice 6 repository-backed loader 的职责是从 completed catalog record 恢复 `DoclingDocumentStore` 或装配 `FundDocumentToolService`；不得向 Agent/Host/UI 暴露 raw Docling JSON、本地路径、cache path 或 `local_import_id`。
- Slice 6 只登记已完成 local PDF + Docling JSON + parser_health 通过的 report；catalog 有记录但 Docling JSON 缺失时 fail-closed，不自动 reconvert 或 repair。
- Post-MVP Slice 7 只修 CLI packaging / command entry；不新增 CLI 子命令，不改变 repository、Agent 或 Fund public tool 行为。
- Post-MVP Slice 8A 裁决为 fake/injected LLM tool-loop contract；不直接接 OpenAI、Claude 或其它真实外部模型 API。
- Slice 8A 的最小协议是 `LlmClientProtocol`、`FakeLlmClient`、`ToolCall -> ToolResult -> FinalAnswer`。
- Slice 8A 只开放 reading tool 子集：`search_document`、`read_section`、`list_tables`、`read_table`、`get_excerpt`；不得向 LLM adapter 暴露 repository/private loader、raw Docling JSON、PDF path、cache path 或 `local_import_id`。
- Slice 8A 最终回答必须只来自 tool result；`citations` 必须非空；每个关键事实至少有 section 或 table citation。
- Slice 8A 不新增用户 CLI 参数或 `fund-checklist ask`；CLI 暴露 LLM 模式需另行裁决。
- MVP closeout accepted 只表示本地阅读工具 MVP 已通过固定测试；不表示 release ready、CI ready、真实 LLM ready、CLI/UI ready、batch queue ready 或字段抽取 ready。

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

完成本次 docs-only Slice 8A design sync 后，下一步才可派发 Slice 8A implementation。Implementation Agent 只允许实现 fake/injected LLM tool-loop contract 与对应测试；不得接真实 LLM provider、不得新增 CLI 子命令、不得改 repository private loader contract、不得把字段抽取、自动报告或投资判断混入本 slice。

## Implementation Slices

0. Dependency / repository preflight：`pyproject.toml`、`uv.lock`、`.gitignore`、`docling import` 验证、git 初始化。
1. Local PDF ingestion：`PdfSourceProvider`、`PdfBlobStore`、identity、fingerprint、integrity。
2. Docling conversion/store：`DoclingConverter`、`DoclingDocumentStore`、parser_health、raw payload redaction。
3. FundDocumentToolService：7 个 reading tools、bounded output、citation、locator、safe redaction。
4. Minimal Agent loop：`search_document -> read_section` trace，最终回答只引用 tool result。
5. Table-aware Agent retrieval：在 section-first 检索后读取相关表格，回答表格型人物/资产信息，并同时返回 section/table citation。
6. Persistent repository：filesystem JSON catalog + repository-backed loader，支持 completed report 跨进程恢复为 reading tools 可用文档。
7. CLI packaging / command entry polish：打包配置安装 `fund-checklist` console script，README 主命令 `uv run fund-checklist read ...` 可用，并保留 `python -m fund_agent.cli.main` fallback。
8A. Fake/injected LLM tool-loop contract：用 fake client 验证 LLM 工具调用闭环、citation enforcement 和 fail-closed 行为；不接真实 provider，不新增用户 CLI 面。

## MVP Acceptance Matrix

- local PDF import
- PDF integrity failure classification
- Docling conversion
- DoclingDocumentStore parser health
- seven FundDocumentToolService tools
- locator + citation + redaction
- `test_agent_tool_loop_searches_then_reads_section`
- `test_agent_tool_loop_does_not_receive_raw_docling_json`
- `test_agent_table_aware_loop_answers_manager_table_information`
- `test_agent_table_aware_loop_answers_holding_table_information`
- `test_agent_table_aware_loop_keeps_section_only_answer_when_no_nearby_table`

## Slice 6 Design Boundary

最小持久化对象：

- `schema_version`
- `document_id`
- `ReportIdentity` safe fields
- `stored_blob_ref`
- `docling_json_ref`
- parser health summary
- `created_at` / `updated_at`

禁止进入 public tool 输入或输出：

- `local_import_id`
- absolute local path
- raw Docling JSON
- Docling/model cache path
- URL secret

Failure mapping:

- catalog missing -> `not_found`
- catalog schema incompatible -> `schema_drift`
- catalog identity 与 `document_id` 不一致 -> `identity_mismatch`
- completed record 指向的 Docling JSON 缺失或不可读 -> `unavailable`
- Docling JSON 顶层结构 drift -> `schema_drift`
- parser_health 不通过 -> `parser_health_failed`
- blob fingerprint mismatch -> `integrity_error`

Slice 6 不做：

- SQLite
- catalog schema migration
- concurrent write locking
- repair / rebuild / reconvert
- downloader
- batch queue
- delete/update lifecycle
- true LLM
- release readiness

## Slice 8A Design Boundary

目标：

- 在 Agent 层增加可测试的 injected LLM adapter 形态。
- 证明 LLM 风格的 `ToolCall -> ToolResult -> FinalAnswer` 闭环只能通过受控 reading tools 取事实。
- 将无 citation、未知工具、越权工具和无证据回答全部 fail-closed。

最小协议：

- `LlmClientProtocol`
- `FakeLlmClient`
- `ToolCall`
- `ToolResult`
- `FinalAnswer`

允许工具：

- `search_document`
- `read_section`
- `list_tables`
- `read_table`
- `get_excerpt`

禁止暴露：

- repository/private loader 细节
- raw PDF
- raw Docling JSON
- absolute local path
- Docling/model cache path
- `local_import_id`
- URL secret 或 parser private payload

回答验收：

- answer 必须来自 tool result。
- citations 必须非空。
- 每个关键事实至少有 section 或 table citation。
- citation 必须指向受控 locator。

Slice 8A 不做：

- OpenAI / Claude / 外部模型 API。
- provider auth、streaming、cost tracking、rate limit。
- prompt framework 或复杂 planner。
- 新增 `fund-checklist ask` 或其它用户 CLI 参数。
- repository schema migration 或 hardening。
- downloader、batch、release readiness。
- 字段抽取、自动报告、投资判断。

## Stop Conditions

- 需要新增或改变 document_id / report_type / share_class 规则。
- 需要复制或改写 dayu 代码但没有 license/compliance gate。
- 需要引入外部网络来源策略。
- 计划把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback。
- 计划把阅读工具扩大为字段抽取、自动报告、投资判断、数据仓库晋升或发布就绪。
- 计划只用 fake fixture 证明 production conversion path。
- 文档声称当前未实现能力已完成。
- Slice 8A 实现计划直接接真实 LLM provider、增加 CLI ask、或让 LLM adapter 读取 repository/private loader。
- 计划把 `基金年报/`、`.venv/`、Docling/model cache 或 secret 文件纳入 git。
- Slice 2 conversion smoke 需要无版本约束地升级 Docling 或绕过 `uv.lock`。

## Validation Commands

文档控制面板检查：

```bash
rg -n "SLICE_0_DEPENDENCY_PREFLIGHT|docling>=2.90.0,<3.0.0|基金年报/|test_agent_tool_loop_searches_then_reads_section" AGENTS.md docs/design.md docs/implementation-control.md docs/reviews/fund-document-reading-tool-mvp-plan-20260627.md pyproject.toml .gitignore
wc -l AGENTS.md docs/implementation-control.md
```

MVP closeout 固定验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

Post-MVP Slice 5 验证命令：

```bash
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '基金经理' --work-dir .fund_checklist_cli_smoke
```

Post-MVP Slice 6 预期验证命令：

```bash
uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Post-MVP Slice 7 验证命令：

```bash
uv sync
uv run fund-checklist read --help
uv run python -m fund_agent.cli.main read --help
uv run pytest tests/fund/cli/test_cli.py
```

Post-MVP Slice 8A 预期最小验证命令：

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Slice 8A 预期测试缺口：

- fake LLM 正常调用 `search_document` / `read_section` 后回答并携带 citation。
- fake LLM 调用 `read_table` 后回答表格问题并携带 table citation。
- fake LLM 直接无证据回答时 fail-closed。
- fake LLM 请求未知工具或越权工具时 fail-closed。
- 输出不泄漏 raw Docling JSON、本地路径、cache path 或 `local_import_id`。
- deterministic `fund-checklist read` 旧路径不回退。

最近已知结果：

```text
MVP closeout: 17 passed, 1 warning
Post-MVP Slice 5 full local regression: 26 passed, 1 warning
Real CLI smoke: query="基金经理" answer includes "张明" with section/table citations
Post-MVP Slice 6 repository unit: 8 passed
Post-MVP Slice 6/5/CLI targeted regression: 20 passed
Post-MVP Slice 7 CLI test: 7 passed
uv sync: passed, no skipped-entrypoint warning
uv run fund-checklist read --help: passed
uv run python -m fund_agent.cli.main read --help: passed
Full local regression before commit: 35 passed, 1 warning
```
