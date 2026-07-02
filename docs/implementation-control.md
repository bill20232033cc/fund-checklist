# fund-checklist implementation-control

更新时间：2026-07-03
当前阶段：`POST_MVP_SLICE_9A_ACCEPTED_9B_PLANNED`
当前角色：control / CIC-lite controller
当前目标：Slice 9A Service boundary 已经 MiMo review `ACCEPTED`，可收口；下一步只设计并执行 Slice 9B evidence retrieval substrate。不得扩成 gateflow / phaseflow / release-readiness，不新增 plan artifact，不进入 template contract execution、calculation framework、`fund-checklist ask`、UI、自动报告或投资判断。

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
- Slice 5-7 已提交并推送到 `origin/main`，提交为 `b618e20 feat: add table-aware reading, persistent catalog, and CLI entrypoint`。
- Post-MVP Slice 8A 已实现 fake/injected LLM tool-loop contract，最新提交为 `f53dac2 Add fake LLM tool loop contract`。
- Slice 8A 验证结果：`uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `20 passed`。
- Slice 8A 扩展回归结果：`uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/agent/test_llm_tool_loop.py tests/fund/cli/test_cli.py` -> `33 passed`。
- Slice 8A `git diff --cached --check` 通过；`.fund_checklist_cli_smoke/` 仍是未跟踪本地 smoke work-dir，未 stage、未提交。
- Post-MVP Slice 8B 已实现 DeepSeek-only OpenAI-compatible adapter：`DeepSeekLlmClient` 实现既有 `LlmClientProtocol`，使用 injected transport，默认测试 no-network/no-real-key。
- Slice 8B provider 输出仍进入 8A `LlmToolLoopRunner`，citation/evidence enforcement 未绕过。
- Slice 8B 已新增集中 failure code `llm_malformed_response`；key missing/auth/network/timeout/rate-limit 映射为 `unavailable`，malformed response 映射为 `llm_malformed_response`。
- Slice 8B 未改 CLI、repository/private loader、`pyproject.toml` 或 `uv.lock`。
- MiMo review 已按 Slice 8B 口径输出 `ACCEPTED`。
- Slice 8B 本地验证结果：`uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `36 passed`。
- Slice 8B `git diff --check` 通过。
- Slice 8B 已本地提交：`f55ed4c feat: add deepseek llm adapter`；当前 `main` 相对 `origin/main` ahead 1，尚未 push。
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
- Post-MVP Slice 8B 已实现为 DeepSeek real LLM adapter behind existing contract；真实 provider 只能实现 `LlmClientProtocol`，不得绕过 8A runner/enforcement。
- Slice 8B 只接 DeepSeek OpenAI-compatible API；Mimo / MiMo 与多 provider 后置。
- Slice 8B 不新增 SDK 依赖，使用 adapter + injected transport；若实现必须使用官方 SDK，需先停止并申请允许修改 `pyproject.toml` / `uv.lock`。
- Slice 8B 环境变量裁决为 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`；`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，测试不得依赖真实 model 值。
- Slice 8B 单元测试默认不联网；live provider smoke 必须显式 opt-in，并且不得作为默认 pytest gate。
- Slice 8B 不新增 `fund-checklist ask`、streaming、多 provider matrix、prompt framework、richer QA/eval、自动报告或投资判断。
- Post-MVP Slice 8C 裁决为 opt-in live DeepSeek smoke；默认 pytest 仍 no-network。
- Slice 8C 只由 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 触发；未设置时 live test 自动 skip。
- Slice 8C API key 来源为 `DEEPSEEK_API_KEY`；缺失时 skip，不失败。
- Slice 8C `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，可覆盖。
- Slice 8C `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，可覆盖。
- Slice 8C 不跑真实 PDF、不跑 CLI、不使用 repository-backed loader；只使用 fake/in-memory tool service 或现有测试 fixture。
- Slice 8C 最多 1 个 live run，timeout 300 秒，最多 1 次 retry，不做批量问题。
- Slice 8C opt-in 后 provider response 不可解析、8A enforcement fail、network/429/auth error 均为 test fail；未 opt-in 或缺 key 为 skip。
- Slice 8C 不打印 API key，不记录 raw provider response，不新增 artifact。
- Slice 8C 当前实现新增 `tests/fund/agent/test_deepseek_live_smoke.py`；默认测试使用 fake transport 覆盖 skip/default/override/timeout/retry/fail-closed/secret 边界，真实 live 分支默认 skip。
- Slice 8C 未改 production adapter、CLI、repository/private loader、`pyproject.toml` 或 `uv.lock`。
- Slice 8C 默认验证结果：`uv run pytest tests/fund/agent/test_deepseek_live_smoke.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `43 passed, 1 skipped`。
- Slice 8C `git diff --check` 通过。
- MiMo review 已按 Slice 8C 口径输出 `ACCEPTED`；MiMo 未重跑命令，review 基于 ProCodex 已报告结果与当前 diff。
- MVP closeout accepted 只表示本地阅读工具 MVP 已通过固定测试；不表示 release ready、CI ready、真实 LLM ready、CLI/UI ready、batch queue ready 或字段抽取 ready。
- Slice 9A 已实现 Service 层 use case boundary；现有 CLI 不再直接装配 PDF provider、repository、converter、tool service 或 Host。
- Slice 9A 最小验证结果：`uv run pytest tests/fund/service tests/fund/cli/test_cli.py tests/fund/agent/test_minimal_tool_loop.py` -> `21 passed`。
- Slice 9A 真实 CLI smoke 结果：exit code `0`，输出包含 `股票投资明细`、section/table citations 和 `search_document -> read_section -> list_tables -> read_table` trace。
- Slice 9A `git diff --check` 通过；MiMo review verdict 为 `ACCEPTED`。
- Post-MVP Slice 9A 裁决为 `FundReadingService` use case boundary。
- Slice 9A 只新增/修改 Service boundary 和 CLI wiring：Service 负责参数校验、local PDF import、repository-backed load、必要时 Docling conversion fallback、Host 调用和稳定失败传播；CLI 只保留 argparse 与 stdout/stderr 格式化。
- Slice 9A 首批 use case：`import_local_report`、`read_local_report`、`list_reports`。
- Slice 9A Service 输入 DTO 可接收本地 PDF path；Service 不得把 path、work dir、repository/private loader、Docling JSON path、cache path、raw Docling JSON 或 `local_import_id` 传给 Host/Agent 或 public output。
- Slice 9A Host 调用契约：只传 `document_id` 和 `query`。
- Slice 9A repository 口径沿用 Slice 6：catalog 有 completed report 时复用；catalog missing 时允许 import + convert；catalog record 指向的 Docling JSON 缺失或不可读时 fail-closed，不自动 repair / rebuild / reconvert。
- Slice 9A 不做 query normalization / synonym routing；`前十大持仓 -> 股票投资明细` 另开 gate。
- Slice 9A 不新增 `fund-checklist ask`、不把 DeepSeek 接入真实 PDF CLI、不改 8A/8B/8C contract、不做 UI、多轮会话、反馈式阅读、批量任务、指标计算、字段抽取、自动报告或投资判断。
- Post-MVP Slice 9B 裁决为 evidence retrieval substrate。
- Slice 9B 目标是让 ToolService / Store 检索基底覆盖 section text、table caption 和 bounded table rows，返回可追溯的 table-backed evidence candidates / search results；它不是自然语言语义路由，不解决 synonym intent，不执行 template chapter contract，也不做计算。
- Slice 9B 可以增强既有 `search_document` 的召回范围，但不得新增 raw Docling JSON 暴露，不得改变 public tool 的安全输出、locator/citation/redaction 约束。
- Slice 9B 不扩展 failure code；命中颗粒度只落在成功侧 metadata，不把表格检索失败细分成新错误码。
- `search_document` 无 evidence candidate 时仍返回空 tuple；Agent 将空 search result 转成 `not_found` 的既有行为不变。
- Slice 9B 验收应证明：当 query 只出现在表格 caption 或 bounded table rows 中、而不在 section 正文中时，`search_document` 仍可返回带 `table_ref`、locator、citation、bounded excerpt 和 `match_kind` / 等价 `matched_field` 的 table-backed result。
- table-backed result 的 `match_kind` / `matched_field` 取值必须是受控枚举，至少区分 `section_text`、`table_caption`、`table_row` 或等价组合；不得引入 confidence / semantic score。
- table row 命中 excerpt 必须 bounded，只返回命中行或有限上下文，不返回整表；排序必须 deterministic / reproducible。
- 失败分类沿用既有稳定 code：`schema_drift`、`not_found`、`unavailable`；不新增 `table_caption_not_found`、`table_row_not_found`、`ambiguous_table_match` 等细分错误码。
- Slice 9B 不修改 deterministic Agent retrieval policy，不要求 Agent 自动 `read_table`，不要求 CLI table-only query 成功；这些能力另开 Slice 9C。

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

执行 Slice 9B implementation + tests。Allowed write set：

- `fund_agent/fund/document_tools/docling_store.py`
- `fund_agent/fund/document_tools/service.py`
- `fund_agent/fund/document_tools/models.py`，仅当既有 `SearchResult` / `Locator` 无法表达 table-backed search result 时允许
- `tests/fund/document_tools/test_docling_store.py`
- `tests/fund/document_tools/test_service.py`
- `fund_agent/fund/README.md`
- `tests/README.md`
- 必要时同步 `docs/design.md` / `docs/implementation-control.md`

禁止事项：

- 禁止新增 query normalization / synonym routing。
- 禁止把 `前十大持仓` 映射为 `股票投资明细`；该能力另开 semantic routing gate。
- 禁止修改 deterministic Agent retrieval policy；table-backed result 的 Agent 消费另开 Slice 9C。
- 禁止要求 CLI table-only query 成功；CLI smoke 只作为旧路径不回退检查。
- 禁止新增 `fund-checklist ask` 或 CLI 参数。
- 禁止接真实 LLM、embedding、外部搜索服务。
- 禁止执行 template-informed intent routing、chapter contract execution、calculation framework、report audit、字段抽取、自动报告或投资判断。
- 禁止暴露 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。

最小验证命令：

```bash
uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
```

回归验证命令：

```bash
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

验收点：query 只命中表格内容或表格标题时，`search_document` 返回 table-backed result，并带 `table_ref`、locator、citation、bounded excerpt 和 `match_kind` / `matched_field`；无 evidence candidate 时仍返回空 tuple，failure code 不扩展；旧 deterministic Agent 和 CLI 测试不回退。

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
8B. DeepSeek real LLM adapter behind existing contract：已实现 DeepSeek OpenAI-compatible adapter 进入 `LlmClientProtocol`，默认测试不联网，所有输出仍经 8A runner/enforcement。
8C. Opt-in live DeepSeek smoke：已实现只在显式环境变量启用时验证真实 DeepSeek 返回一次合法 `ToolCall` 或 `FinalAnswer`，最终仍经 8A runner；默认 gate no-network。
9A. Service boundary：新增 `FundReadingService` use case boundary，把 CLI 编排迁入 Service；CLI 行为、exit code、redaction、repository reuse 和 deterministic Agent loop 不回退，不做 query routing 或 LLM/UI 能力扩展。
9B. Evidence retrieval substrate：增强 ToolService / Store 检索基底，使 section text、table caption、bounded table rows 都能成为可引用 search result；不修改 Agent retrieval policy，不要求 CLI table-only query 成功，不做 synonym intent、template contract、calculation、LLM ask 或报告生成。

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

## Slice 8B Accepted Boundary

目标：

- 在不改变 8A runner/enforcement 的前提下接入一个真实 LLM provider adapter。
- 验证真实 provider 输出只能被解析为受控 `ToolCall` 或 `FinalAnswer`。
- 将 provider 错误、malformed response、未知工具、越权工具、无 evidence final answer 全部稳定映射为 fail-closed。

最小实现形态：

- `DeepSeekLlmClient` 或等价的 DeepSeek-only provider client。
- provider client 实现既有 `LlmClientProtocol`。
- provider request 使用 DeepSeek OpenAI-compatible chat completions 形态，只包含系统约束、用户问题和受控 tool schema；不得包含 raw Docling JSON、本地路径、cache path、repository/private loader 或 `local_import_id`。
- provider response 必须经结构化解析后进入 8A `LlmToolLoopRunner`。
- API key 仅从 `DEEPSEEK_API_KEY` 读取；缺失时返回稳定 failure，不触发默认联网。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- `DEEPSEEK_MODEL` 可选；测试只验证传参与解析，不依赖真实模型名称。
- 不新增 SDK 依赖；HTTP/transport 必须可注入，默认测试使用 fake transport。

失败映射：

- API key 缺失 -> `unavailable`
- provider network/timeout -> `unavailable`
- provider rate limit -> `unavailable`
- provider auth rejected -> `unavailable`
- provider response 非法 JSON 或无法解析 -> `llm_malformed_response`
- provider 请求未知工具或越权工具 -> 复用 8A fail-closed 逻辑
- provider final answer 缺 citation 或缺 evidence -> 复用 8A fail-closed 逻辑

测试口径：

- 默认 pytest 只使用 fake transport / injected provider response，不访问网络。
- live smoke 只能作为显式 opt-in 命令，不进入默认 CI 或本地最小 gate。
- deterministic `MinimalFundDocumentAgent`、fake 8A loop 和 `fund-checklist read` 路径不得回退。

Slice 8B 不做：

- 新增 `fund-checklist ask` 或其它 CLI 用户入口。
- streaming。
- Mimo / MiMo 或多 provider matrix。
- 新增 SDK 依赖，除非 Controller 先裁决允许改 `pyproject.toml` / `uv.lock`。
- prompt framework 或复杂 planner。
- richer QA/eval matrix。
- 自动报告、字段抽取、投资判断。
- release readiness、batch、downloader。
- repository schema 或 private loader 改造。

## Slice 8C Accepted Boundary

目标：

- 验证真实 DeepSeek live provider 能返回一次合法 `ToolCall` 或 `FinalAnswer`。
- 验证 live provider 输出最终仍进入 8A `LlmToolLoopRunner`。
- 保持默认 pytest no-network，不把 live provider 变成默认 gate。

触发与环境：

- `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时启用 live smoke。
- 未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK` 时 skip。
- `DEEPSEEK_API_KEY` 缺失时 skip，不失败。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，允许覆盖。
- `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，允许覆盖。

验收范围：

- 使用 fake/in-memory tool service 或现有测试 fixture。
- 不跑真实 PDF。
- 不跑 CLI。
- 不触发 Docling conversion。
- 不使用 repository-backed loader。
- 要求 live DeepSeek 返回一次合法 `ToolCall` 或合法 `FinalAnswer`。
- 最终结果必须经 8A runner/enforcement。

成本与运行上限：

- 最多 1 个 live run。
- timeout 300 秒。
- 最多 1 次 retry。
- 不做批量问题。

失败语义：

- opt-in 后 provider 返回不可解析 -> test fail。
- opt-in 后 8A enforcement fail -> test fail。
- opt-in 后 network / 429 / auth error -> test fail。
- 未 opt-in 或缺 key -> skip，不算 fail。

secret / artifact：

- pytest output、trace、assert message 不得打印 API key。
- 不记录 provider raw response 到文件。
- 不新增 artifact。

Allowed write set：

- `tests/fund/agent/test_deepseek_live_smoke.py`
- `tests/README.md`
- `docs/implementation-control.md`
- `fund_agent/agent/README.md`

Slice 8C 不做：

- 修改 production adapter；若 live test 暴露解析 bug，必须先停止并报告。
- 新增 `fund-checklist ask`。
- 真实 PDF / Docling / repository e2e。
- Mimo / MiMo、多 provider、streaming。
- retry/backoff hardening，除本 slice 裁决的最多 1 次 retry。
- richer QA/eval、prompt injection hardening、自动报告、投资判断。

## Stop Conditions

- 需要新增或改变 document_id / report_type / share_class 规则。
- 需要复制或改写 dayu 代码但没有 license/compliance gate。
- 需要引入外部网络来源策略。
- 计划把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback。
- 计划把阅读工具扩大为字段抽取、自动报告、投资判断、数据仓库晋升或发布就绪。
- 计划只用 fake fixture 证明 production conversion path。
- 文档声称当前未实现能力已完成。
- Slice 8A 实现计划直接接真实 LLM provider、增加 CLI ask、或让 LLM adapter 读取 repository/private loader。
- Slice 8B 实现计划绕过 8A runner/enforcement、默认联网、记录 API key、增加 CLI ask、增加 Mimo / MiMo 或多 provider、或让 provider prompt 接收 raw Docling/private loader。
- Slice 8B 实现计划新增 SDK 依赖但未先获得 Controller 裁决。
- Slice 8C 实现计划让 live smoke 进入默认 pytest gate、缺 key 时失败、打印 API key、记录 raw provider response、跑真实 PDF/CLI/repository，或修改 production adapter 且未先停止报告。
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

Post-MVP Slice 8A 验证命令：

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Slice 8A 已覆盖测试范围：

- fake LLM 正常调用 `search_document` / `read_section` 后回答并携带 citation。
- fake LLM 调用 `read_table` 后回答表格问题并携带 table citation。
- fake LLM 直接无证据回答时 fail-closed。
- fake LLM 请求未知工具或越权工具时 fail-closed。
- 输出不泄漏 raw Docling JSON、本地路径、cache path 或 `local_import_id`。
- deterministic `fund-checklist read` 旧路径不回退。

Post-MVP Slice 8B 验证命令：

```bash
uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

Slice 8B 已覆盖测试范围：

- provider adapter 使用 injected fake transport，将合法 tool-call response 解析为 `ToolCall` 并进入 8A runner。
- provider adapter 使用 injected fake transport，将合法 final-answer response 解析为 `FinalAnswer`，并保留 8A citation/evidence enforcement。
- DeepSeek adapter 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 组装 OpenAI-compatible request，默认 base URL 为 `https://api.deepseek.com`。
- API key 缺失、network/timeout、auth/rate-limit 类错误稳定映射为 `unavailable`。
- malformed provider response 稳定映射为 `llm_malformed_response` 或等价稳定 failure code。
- provider 请求未知工具、越权工具、无 citation answer 或无 evidence answer 时 fail-closed。
- 默认测试不访问网络，不读取真实 API key，不泄漏 secret。
- 默认测试不依赖真实 DeepSeek model 值。
- deterministic read CLI、minimal deterministic Agent 和 fake 8A loop 旧测试不回退。

Post-MVP Slice 8C 默认验证命令：

```bash
uv run pytest tests/fund/agent/test_deepseek_live_smoke.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时，live smoke test 必须 skip，默认命令不得联网。

Post-MVP Slice 8C live smoke 命令：

```bash
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 DEEPSEEK_API_KEY=... uv run pytest tests/fund/agent/test_deepseek_live_smoke.py
```

Slice 8C 测试覆盖：

- 未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK` -> skip。
- 设置 opt-in 但缺 `DEEPSEEK_API_KEY` -> skip。
- opt-in live run 使用 `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- opt-in live run 使用 `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`。
- live DeepSeek 返回合法 `ToolCall` 或 `FinalAnswer` 后进入 8A runner。
- live provider 不可解析、8A enforcement fail、network/429/auth error -> fail。
- pytest output、trace、assert message 不泄漏 API key。
- 不写 raw provider response artifact。
- 默认测试不联网；真实 live 分支只有 opt-in 且 key 存在时运行。

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
Slice 8A targeted: 20 passed
Slice 8A broader regression: 33 passed
Slice 8A commit: f53dac2 Add fake LLM tool loop contract
Slice 8B targeted: 36 passed
Slice 8B review: MiMo ACCEPTED
Slice 8B git diff --check: passed
Slice 8C default targeted: 43 passed, 1 skipped
Slice 8C review: MiMo ACCEPTED
Slice 8C git diff --check: passed
```
