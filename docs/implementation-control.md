# fund-checklist implementation-control

更新时间：2026-07-07
当前阶段：`POST_MVP_SLICE_10K_ACCEPTED`
当前角色：control / CIC-lite controller
当前目标：Slice 10K multi-year performance fake/injected Agent tool-loop 已实现并经 ds review `ACCEPTED`。不得扩成 gateflow / phaseflow / release-readiness，不新增 plan artifact，不进入 batch benchmark、开放语义理解、自动分词、embedding、LLM intent、template contract execution、chapter contract execution、calculation framework、`fund-checklist ask`、UI、自动报告或投资判断。

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
- Slice 9B 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `54a5d30 Implement table-backed document search`。
- Slice 9B 验证结果：`uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py` -> `17 passed`；`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `14 passed`；`git diff --check` 通过。
- Post-MVP Slice 9C 裁决为 table-backed first-hit consumption。
- Slice 9C 只在 `search_document` first hit 是 high-certainty table-backed result 时直接消费 `table_ref`；否则沿用既有 section-first table-aware 路径。
- high-certainty 只用确定性 exact containment 判断：`match_kind == table_row` 且 query 原文出现在 excerpt 中；或 `match_kind == table_caption` 且 query 原文出现在 caption/excerpt 中。
- high-certainty table-backed first hit 的工具顺序为 `search_document -> read_section -> read_table`；不调用 `list_tables` 进行表格发现。
- high-certainty table-backed first hit 的 answer 必须 table-first：section title / table caption 只作来源上下文，bounded table rows 是主体内容；不得做 section 摘要或解释性综合。
- citations 至少包含 table citation；可以保留 section citation。
- first hit 不是 table-backed result、table-backed hit 不满足 high-certainty、或 table-backed hit 缺少 `table_ref` 时，不得强行直读表；应保持既有稳定失败或回落语义。
- Slice 9C 不扫描 top-N、不做二次排序、不做歧义消解、不做 query intent 分类、不做 synonym routing、不接 LLM 判断表格相关性。
- Slice 9C 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `eb1d13c Consume table-backed first search hit`。
- Slice 9C 验证结果：`uv run pytest tests/fund/agent/test_minimal_tool_loop.py` -> `9 passed`；`uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py tests/fund/cli/test_cli.py` -> `26 passed`；`git diff --check` 通过。
- Post-MVP Slice 9D 裁决为 controlled query profile routing，位置在 Service 层。
- Slice 9D 不修改 `search_document` public contract；`search_document` 仍只接收单个 query。Service routing 负责把用户 query 转成最多 3 个受控 candidate queries，并按顺序调用既有 Host/Agent 路径。
- candidate 顺序必须包含原始 query，并且总数最多 3 个；命中后返回第一个成功的 Agent result。
- Slice 9D 只支持 hardcoded controlled profiles；不做自动分词、同义词扩散、开放语义理解、LLM intent 或 embedding。
- 首批 controlled profiles 仅三类：
  - `holdings_top10`: alias 为 `前十大持仓` / `重仓股` / `持仓明细`；candidate queries 为原始 query、`股票投资明细`、`前十名股票投资明细`。
  - `asset_allocation`: alias 为 `资产配置` / `资产组合`；candidate queries 为原始 query、`期末基金资产组合情况`、`基金资产组合情况`。
  - `expenses`: alias 为 `费用` / `管理费` / `托管费`；candidate queries 为原始 query、`基金费用`、`报告期内基金费用`。
- failure 语义保持稳定：所有 candidate 都无命中时仍为 `not_found`；routing 配置异常为 `schema_drift`；ToolService 内部异常仍为 `unavailable`。不新增 `synonym_not_found` 等错误码。
- citation 必须来自实际命中的 candidate 对应的 section/table tool result，不引用 alias 本身。
- trace 可记录实际使用的 query candidate；不新增 CLI 输出格式，测试可断言 Agent result / tool trace。
- 9D 真实 CLI smoke 只证明 controlled alias routing：`--query 前十大持仓` 能走到 `股票投资明细`；不证明泛化问答。
- Slice 9D 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `91a4da9 Add controlled query profile routing`。
- Slice 9D 验证结果：`uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py` -> `29 passed`；`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py` -> `26 passed`；`git diff --check` 通过。
- Slice 9D 真实 CLI smoke 结果：exit code `0`，`--query 前十大持仓` 输出股票投资明细相关 answer、section/table citations 和 trace；该 smoke 只证明 controlled alias routing，不证明泛化问答。
- Post-MVP Slice 9E 裁决为 Service routing attempts audit。
- Slice 9E 只为 9D 的 Service routing 增加最小审计记录；它不是新召回能力，不新增 profile，不做 rerank、语义理解、计算或报告。
- `ReadLocalReportResult` 可增加 `routing_trace` 字段，类型为 `tuple[QueryRouteAttempt, ...]` 或等价只读结构。
- 每个 `QueryRouteAttempt` 只记录原始事实：`query`、`profile_name`、`result_kind`、`failure_code`。`result_kind` 仅允许 `success` / `failure`；成功 attempt 的 `failure_code` 必须为 `None`。
- 不存 `selected_query`、`selected_index`、rationale、score、confidence、candidate_results 或 evidence links；`selected_query` / `selected_index` 只能从第一个 success attempt 推导。
- `routing_trace` 是 Service-level audit metadata，不暴露给 Agent，不并入 Agent `tool_trace`。
- CLI 默认输出格式不变；citations、answer、failure code、`search_document` contract、Agent policy、Store search 均不变。
- failure 语义保持稳定：所有 candidate 都无命中时仍为 `not_found`；routing 配置异常仍为 `schema_drift`；ToolService 内部异常仍为 `unavailable`。
- Slice 9E 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `336c94e Add service routing audit trace`。
- Slice 9E 验证结果：`uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py` -> `32 passed`；`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py` -> `26 passed`；`git diff --check` 通过。
- Post-MVP Slice 9F 裁决为 controlled profile real-smoke regression。
- Slice 9F 不新增能力，只把 9D/9E 的三类 controlled profiles 在仓库本地真实 PDF 上固化为回归验证。
- Slice 9F 真实样本范围仅限当前本地 PDF：`基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf`。样本缺失是 blocker，不得用 fake PDF 替代真实 smoke。
- Slice 9F smoke queries 固定为三条：`前十大持仓`、`资产配置`、`费用`；不同时覆盖所有 alias，不扩大 profile 矩阵。
- 每条 smoke 最小 expected evidence：
  - `前十大持仓` -> `股票投资明细` 或 `前十名股票投资明细`。
  - `资产配置` -> `期末基金资产组合情况` 或 `基金资产组合情况`。
  - `费用` -> `基金费用` 或 `报告期内基金费用`。
- 9F 只要求 exit code `0`、answer 包含 expected evidence 文本、Citations 存在、Trace 存在、CLI 默认输出不包含 `routing_trace`。
- 9F 可在 Service 测试层继续断言 `routing_trace`；CLI smoke 层不展示 routing metadata。
- 9F 不新增 profile、不新增 alias、不改 routing 规则、不改 `search_document` contract、不改 Agent/Store/ToolService、不改 CLI 输出格式、不做 benchmark 或 correctness evaluation。
- Slice 9F verdict 为 `BLOCKED_BY_DESIGN` / `NOT_ACCEPTED`，不是 flaky smoke，也不是已知最小实现 bug。
- Slice 9F 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；answer 包含 `股票投资明细`；Citations / Trace 存在；无 `routing_trace`。
  - `资产配置`: exit code `0`；answer 命中 `3.2.1 基金份额净值增长率...`，缺少 expected evidence `期末基金资产组合情况` / `基金资产组合情况`。
  - `费用`: exit code `0`；answer 命中 `3.1 主要会计数据和财务指标`，缺少 expected evidence `基金费用` / `报告期内基金费用`。
- Root cause：controlled alias original-query false positive；更一般地，keyword-level routing success 不能证明 disclosure target success。
- 禁止把 9F 失败解释为“canonical candidates 不够多”或“真实 PDF 特殊”；当前问题是 query 命中与披露目标命中不是同一个事实。
- `canonical-first` 不列为 10A 候选策略，也不作为 9F 修复方案；它仍是 keyword-level strategy，只改变候选顺序，不能建立 disclosure target success 契约。
- 暂不引入 profile-specific evidence validation；该路线会引入 expected title pattern、section/table validator、score/confidence 或新 failure taxonomy，复杂度高，容易造成 doc truth drift。
- Post-MVP 10A 裁决为 Controlled disclosure target contract，位置仍在 Service 层；Store / ToolService / Agent 不承担业务 profile 判断。
- 10A 目标不是新增 synonym，而是为受控 profile 定义 disclosure target id、allowed evidence kind、acceptable section/table title family、expected citation kind 和 fail-closed semantics。
- 10A 不做 LLM intent、embedding、top-N rerank、profile-specific complex validators、template contract execution、calculation framework、字段抽取、自动报告或投资判断。
- Slice 10A 已经 MiMo review `ACCEPTED`。
- Slice 10A 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；evidence 为 `股票投资明细`；Citations / Trace 存在。
  - `资产配置`: exit code `0`；evidence 为 `期末基金资产组合情况`；Citations / Trace 存在。
  - `费用`: exit code `2`；`failure_code=not_found`；target contract fail-closed，没有把无关章节误判为成功。
- `费用` 在当前 9D candidate 下 target-unmatched 是预期设计结果，不是 10A blocker。
- Post-MVP 10B 裁决为 fee_rates reading locator，只做阅读定位和 citation，不抽取费率数值，不计算显性成本小计，不计算扣费后收益率。
- 10B 将 `expenses` profile 改名 / 收窄为 `fee_rates`，`target_id` 为 `fee_rates`；旧 `expenses` 语义过宽，容易覆盖其他费用、交易费用、审计费用、所得税费用、佣金费率等对象。
- `fee_rates` 的目标 disclosure sections 固定为三类：`基金管理费`、`基金托管费`、`销售服务费`。
- `acceptable title family` 固定为：`基金管理费`、`基金托管费`、`销售服务费`。
- 当前真实样本已存在三类披露，因此 10B smoke 对该样本要求三项目标全命中；不引入 `partial_success` 或新 failure taxonomy。
- `fee_rates` aliases 可包含 `费用`、`费率`、`管理费`、`托管费`、`销售服务费`；alias 只用于进入 profile，不作为 evidence 成功条件。
- controlled candidate queries 固定为原始 query、`基金管理费`、`基金托管费`、`销售服务费`；不把单独 `费率` 作为 evidence candidate。
- Service 层可以对同一 profile 执行多个 target queries，并把多个安全 Agent result 聚合为一个 answer；每个 citation 必须来自实际命中的 section/table。
- 10B 不修改 `search_document` public contract，不把业务 profile 判断下沉到 Store / ToolService / Agent，不改变 CLI 输出格式。
- 10B 不做开放语义理解、自动分词、同义词扩散、embedding、LLM intent、top-N scan、rerank、歧义消解、字段抽取、自动报告或投资判断。
- Slice 10B 已经 MiMo review `ACCEPTED`。
- Slice 10B 真实 CLI smoke 结果：
  - `费用`: exit code `0`；answer 同时包含 `基金管理费`、`基金托管费`、`销售服务费`。
  - Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
- 10B remaining blocking risk: none。
- 10B 仍只完成 fee_rates 阅读定位；管理费率、托管费率、销售服务费率等字段值抽取后置，不属于 10B。
- Post-MVP 10C 裁决为 fee_rates value extraction contract。
- 10C 字段范围只包含三项：`management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate`。
- 10C 不抽取 `nav_growth_rate`、`benchmark_return_rate`、`turnover_rate`，不计算显性成本小计、总成本、扣费后收益率、年化收益率或 `R=A+B-C`。
- 10C 口径固定为当前报告期适用的年费率；不是当期发生金额，不是历史调整前费率，不做历史期间加权。
- 10C 必须处理份额类别口径：A 类销售服务费为不收取，C 类销售服务费为年费率；用户未指定 share class 时，返回 fund-level fee policy 中 A / C 两类口径，不猜默认份额。
- 10C 遇到历史调整文字时，只抽取当前适用费率，并保留原文 citation；不得把调整前费率当成当前费率。
- 10C 数值格式固定为受控 DTO 字段：`field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`；`decimal_percent_text` 保持 `"1.20%"` 形式，`period` 固定为 `"year"`，不先转成 `0.012`。
- 10C 失败语义不新增 failure code：字段未找到为 `not_found`；候选章节存在但无法唯一抽取为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10C 可新增受控 extraction DTO 和 Service 方法 / use case；不得修改 `search_document` public contract，不得改变 Agent / Store / ToolService 职责边界。
- 10C 暂不改变 CLI 默认输出格式；优先在 Service / tests 层验证结构化字段抽取，CLI 仍可保持 10B 的原文 answer / citation。
- 10C 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、template contract execution、chapter contract execution、自动报告或投资判断。
- Slice 10C 已经 MiMo review `ACCEPTED`。
- Slice 10C 真实 CLI smoke 结果：
  - work dir: `.fund_checklist_cli_smoke_10c`
  - `费用`: exit code `0`；output 包含 `基金管理费`、`基金托管费`、`销售服务费`。
  - Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
- 10C remaining blocking risk: none reported。
- 10C 没有进入净值增长率、基准收益率、换手率、成本计算、`R=A+B-C`、模板执行、自动报告或投资判断。
- Post-MVP 10D 裁决为 performance return fields extraction contract。
- 10D 目标是在 11A 已定位的 performance disclosure table 中抽取受控字段，不重新做开放检索。
- 首批字段只允许 `nav_growth_rate` 和 `benchmark_return_rate`。
- 首批 period 裁决为 `past_1_year`，对应真实样本表格行标题 `过去一年`；不得把它命名为 `report_year` 或年度 2024。
- 10D 不抽取近 3 年、近 5 年、成立以来、年度序列表或图表数据；后续 period 必须另开裁决。
- 10D 不抽取 `excess_return`、`annualized_return`、`max_drawdown`、`volatility`、`sharpe`、`tracking_error`、`turnover_rate`。
- 10D 不计算 `A=R-B`、`R=A+B-C`、显性成本小计、总成本、扣费后收益率、年化收益率或同类中位数。
- share class 口径：用户未指定 share class 时不得猜默认份额；可返回所有可唯一识别 share class 的 `past_1_year` DTO。若 share class 无法从表格上下文唯一识别，则 fail-closed 为 `not_found`。
- 若某个 share class 没有 `过去一年` 行，不得合成或外推该 share class 的 `past_1_year` 字段。
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`。
- `decimal_percent_text` 保持原文百分号格式，例如 `"17.32%"`；不先转为小数。
- 数据源只允许来自 11A acceptable title family：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`。
- 10D 必须 table-first：目标字段必须来自 table citation；section-only evidence 不足以抽字段。
- 列标题必须能唯一匹配 `份额净值增长率` / `基金份额净值增长率` 和 `业绩比较基准收益率`；行标题必须唯一匹配 `过去一年`。
- 失败语义沿用现有 failure code：目标表格未找到、目标列缺失、period 行缺失、share class 无法区分、数值无法唯一抽取均为 `not_found`；extractor 配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10D 可新增受控 extraction DTO 和 Service 方法 / use case；不得修改 `search_document` public contract，不得改变 Agent / Store / ToolService 职责边界。
- 10D 暂不改变 CLI 默认输出格式；字段 DTO 先在 Service / tests 层验证，CLI 仍保持阅读 answer / citation / trace。
- 10D 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、template contract execution、chapter contract execution、自动报告或投资判断。
- 当前样本年报未直接披露 `turnover_rate`；后续不做 `turnover_rate` locator，也不把股票买入 / 卖出金额、投资组合重大变动或股票投资明细包装成换手率 evidence。若未来需要换手率，必须另开 calculation / external-data gate，先裁决公式、数据源、期间、基金资产净值口径、失败语义和 citation。
- Slice 10D 已经 MiMo review `ACCEPTED`。
- Slice 10D Service extraction summary：
  - fake multi-table cited case returns A/C `nav_growth_rate` and `benchmark_return_rate`, `period=past_1_year`, `raw_text` present, citations are table locators.
  - uncited same-section table regression covered: only cited table is consumed.
  - current real PDF Service extraction fail-closes if 11A cites a table without `过去一年`; it does not scan sibling tables.
- 10D remaining blocking risk: none reported。剩余非阻塞风险是：real-PDF extraction success depends on the 11A locator citing the actual `过去一年` performance table.
- `past_1_year` 是 10D 底层抽取能力，对应年报表格原文 `过去一年`；它不作为后续主分析口径扩展。用户分析语义中，“2024 年度”比“过去一年”更自然；“过去 5 年”应理解为多个自然年度或明确年度序列，而不是 10D 的 `past_1_year` 行。
- Post-MVP 10E 裁决为 annual performance returns source decision。
- 10E 不是字段抽取实现 slice，而是 source decision slice。
- 10E 目标是裁决“年度业绩数据”应来自哪个公开披露位置，避免继续围绕 `past_1_year` 修 citation specificity。
- 10E 首批只回答 source decision，不新增 DTO、不抽值、不计算、不改 CLI。
- 10E 是 docs-only slice；预期写入只限 `docs/design.md` 和 `docs/implementation-control.md`，除非另行裁决，不修改 Python 代码、测试或 README。
- 候选来源限定为：
  - title-family matched performance comparison table：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`
  - 管理人报告 / 报告期内基金的业绩表现文字，例如“本报告期基金份额净值增长率为...同期业绩比较基准收益率为...”
  - `自基金合同生效以来基金每年净值增长率及其与同期业绩比较基准收益率的比较` 年度图 / 表
- 10E 不扩大到基金净值表现图、第三方平台、净值数据库、季报 / 半年报、基金合同或招募说明书。
- source 可用性判定标准：能定位到稳定章节 / 表格 / 文本；能给出 citation；能表达自然年度或报告期年度；能区分 A/C 份额或明确 fund-level；不依赖图像解析 / OCR；不依赖模型猜字段。
- 10E source 类型固定为 `table`、`text`、`chart_or_image`、`unsupported`。
- 年度语义固定为自然年度 / 报告期年度，例如 `2024`；不再把 `过去一年` 作为主分析口径。
- 10E 本地样本核验范围固定为 `基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf` 及既有 `.fund_checklist_cli_smoke_*` Docling JSON；smoke artifact 不纳入提交。
- 10E 样本核验结论：
  - title-family matched performance comparison table 在 2024 年度报告第 6 / 7 页可定位到稳定表格；标题为 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`。样本中的章节编号为 `3.2.1`，但编号不得作为 contract；只可作为样本观察。
  - 该表格 source 类型为 `table`，是后续年度业绩 deterministic extraction 的 primary source。
  - 管理人报告 / 报告期内基金的业绩表现文字可定位到 stable text，source 类型为 `text`；但其位置和句式可能随年份变化，因此仅作为 secondary reference，不作为 10F 首批 extraction source。
  - `自基金合同生效以来基金每年净值增长率及其与同期业绩比较基准收益率的比较` 在当前样本中表现为图 / 图片，source 类型为 `chart_or_image`，不进入当前 deterministic extraction。
- 10E source decision：选择 title-family matched performance comparison table。年度业绩数据当前应来自 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` 标准披露表；不得依赖 `3.2.1` 章节编号。
- 10E 后续推荐：可开 10F annual performance table extraction from title-family matched table；管理人报告年度文字后置为 secondary reference，不作为 10F fallback；年度图 / 图片不得进入抽取，除非另开 chart/OCR gate。
- 10E 不做 `past_1_year` citation specificity，不做 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- Post-MVP 10F 裁决为 annual performance table extraction from title-family matched table。
- 10F 目标是从 title-family matched performance comparison table 中抽取年度收益字段。
- 10F 不依赖章节编号；样本中的 `3.2.1` 只是观察值，不能写入 public contract、locator contract 或测试断言。
- source title family 固定为：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`。`基金净值表现` 可作为上层 section context，但不能单独作为字段抽取表成功条件。
- table signature 必须包含：`source_period_label = 过去一年`、`份额净值增长率` / `基金份额净值增长率` 列、`业绩比较基准收益率` 列。
- 年度语义裁决为：`report_year = request.year`，`source_period_label = 过去一年`。用户 / DTO 层表达为 `2024` 等自然年度，citation / raw_text 必须保留原文 `过去一年`。
- 首批字段只抽 `annual_nav_growth_rate` 和 `annual_benchmark_return_rate`。
- 10F 不抽标准差、超额收益、年度序列、近 3 年 / 近 5 年、成立以来、图表数据或管理人报告文字。
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`report_year`、`source_period_label`、`share_class_scope`、`raw_text`、`citation`。
- share class 口径：用户未指定 share class 时，返回所有可唯一识别的 share class DTO。
- partial-by-share-class 允许；partial-by-field 不允许。某个 share class 同时具备两个字段则返回该 share class；某个 share class 缺任一字段则不返回该 share class；若全部 share class 都不完整则整体 `not_found`。
- 管理人报告文字不作为 10F fallback；不得用文字披露补齐缺失 share class、缺失行或缺失字段。
- 真实 PDF 验收必须证明至少 A 类可从 2024 年度报告标准披露表抽取：`annual_nav_growth_rate = 17.32%`，`annual_benchmark_return_rate = 14.45%`。C 类是否返回取决于标准披露表是否存在完整 `过去一年` 行，不得外推或 fallback。
- Slice 10F 已经 MiMo review `ACCEPTED`。
- Slice 10F 真实 PDF annual DTO：
  - `annual_nav_growth_rate`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`decimal_percent_text=17.32%`，table citation `table-0010`。
  - `annual_benchmark_return_rate`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`decimal_percent_text=14.45%`，table citation `table-0010`。
- 10F remaining blocking risk: none reported。
- 10F 没有依赖章节编号，没有使用管理人报告文字 fallback，没有进入 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- Post-MVP 10G 裁决为 annual excess return disclosed-field extraction。
- 10G 目标是从 title-family matched performance comparison table 中抽取年报显式披露的年度超额收益字段。
- 10G source title family 沿用 10F：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`；不得依赖样本章节编号 `3.2.1`。
- 10G table signature 必须包含：`source_period_label = 过去一年`、`份额净值增长率` / `基金份额净值增长率` 列、`业绩比较基准收益率` 列，以及显式披露列 `①－③`。
- 10G 字段固定为 `annual_excess_return`，语义为年报表格中直接披露的 `份额净值增长率 - 业绩比较基准收益率` 对应列值。
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`report_year`、`source_period_label`、`share_class_scope`、`source_column_label`、`raw_text`、`citation`。
- 固定 DTO 口径：`field_name=annual_excess_return`，`report_year=request.year`，`source_period_label=过去一年`，`source_column_label=①－③`。
- `decimal_percent_text` 保持原文百分号格式；不先转成小数，不重新计算，不做四舍五入。
- share class 口径沿用 10F：用户未指定 share class 时，返回所有可唯一识别且具备完整 `过去一年` / `①－③` 数据的 share class DTO。
- partial-by-share-class 允许；某 share class 缺 `过去一年` 行、缺 `①－③` 列值或无法唯一识别时，不返回该 share class；若全部 share class 都缺失则整体 `not_found`。
- 管理人报告文字、年度图 / 图片、第三方数据、10F 已抽取的 nav / benchmark 字段都不得作为 10G fallback。
- 失败语义沿用现有 failure code：目标 title-family table 未找到、table citation 缺失、`过去一年` 行缺失、`①－③` 列缺失、目标值无法唯一抽取、share class 无法识别或全部 share class 缺失，均为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10G 不新增 `calculation_error`、`formula_missing`、`partial_success` 或新的 failure taxonomy。
- 10G 不改 CLI 默认输出；字段 DTO 先在 Service / tests 层验证。
- 真实 PDF 验收应证明至少 A 类可从 2024 年度报告标准披露表抽取：`annual_excess_return = 2.87%`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`source_column_label=①－③`，citation 为 table locator。
- C 类是否返回取决于标准披露表是否存在完整 `过去一年` / `①－③` 行列，不得外推或 fallback。
- 10G 不做 `annual_nav_growth_rate - annual_benchmark_return_rate` 计算，不做 `A=R-B` 计算，不做 `R=A+B-C`、换手率、成本计算、扣费后收益率、年化收益率、同类中位数、模板执行、自动报告或投资判断。
- Slice 10G 已经 MiMo review `ACCEPTED`。
- Service 层已实现 annual excess return disclosed-field extraction。
- 10G 抽取 `annual_excess_return` 只消费标准披露表的 `①－③` 显式披露列；不通过 10F 的 `annual_nav_growth_rate` / `annual_benchmark_return_rate` 做差计算。
- 真实 PDF / Service 测试已覆盖 A 类 DTO：`annual_excess_return = 2.87%`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`source_column_label=①－③`，citation 为 table locator。
- 测试已覆盖缺 `①－③` 列时 fail-closed 为 `not_found`，且不得使用管理人报告文字、年度图 / 图片或未 citation 指向的 sibling table fallback。
- 10G remaining blocking risk: none reported。
- 10G 没有依赖章节编号，没有改变 CLI 默认输出，没有新增 failure taxonomy，没有进入 `A=R-B` 计算、`R=A+B-C`、换手率、成本计算、扣费后收益率、年化收益率、同类中位数、模板执行、自动报告或投资判断。
- Post-MVP 10H 裁决为 multi-year annual performance source contract with bounded year coverage。
- 10H 目标是裁决近 3 年 / 近 5 年收益表现的 deterministic source 和 aggregation contract；不直接进入报告生成或投资判断。
- 10H 仅做 docs update / source contract，不做代码实现，不新增 Service method，不改 CLI，不改测试。
- 10H source 选择 multiple annual reports。每个自然年度使用该年度基金年报中的标准披露表 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`，复用 10F / 10G 的单年度字段抽取结果。
- 每个年度复用 10F / 10G 字段：`annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return`。
- 10H 不做 single-report rolling period extraction。当前 2024 年度报告没有 `过去三年` / `过去五年` 行，因此不得从单份 2024 年报合成近 3 年 / 近 5 年 rolling period。
- 10H 不使用单份年报年度图 / 图片、OCR / chart parsing、外部净值数据库、第三方平台、管理人报告文字 fallback 或模型推断。
- 10H 年度窗口裁决为：`requested_window_years = 5`，`minimum_complete_years = 3`，`maximum_complete_years = 5`。
- 允许 bounded partial-by-year：请求近 5 年时可接受 3-5 个完整年度；缺 1-2 年仍可返回成功结果，但必须结构化暴露 coverage metadata。
- coverage metadata 固定包含：`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`。
- `coverage_status` 只允许 `complete` 或 `partial`。5 年完整为 `complete`；3-4 年完整为 `partial`。
- 少于 3 个完整年度时整体 fail-closed 为 `not_found`；不新增 `partial_success`、`missing_year` 或新的 failure taxonomy。
- 某年度完整的定义：该年度年报存在且可读取；标准披露表命中；同一 share class 下 `annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return` 三个字段都完整；三个字段都有对应 table locator citation。
- 多年度 share class 口径按 share class 独立计算 coverage：某 share class 至少 3 个完整年度才返回该 share class series；所有 share class 都不足 3 年则整体 `not_found`。
- 多年度 DTO 目标形态为 `MultiYearAnnualPerformanceSeries`，包含：`fund_code`、`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`、`share_class_scope`、`rows`、`citations`。
- 每个 row 包含：`year`、`annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return`、`citations`。
- 每个字段仍保留原单年度 DTO 的 `decimal_percent_text`、`source_period_label=过去一年`、`source_column_label`、`citation`；多年度聚合不产生新的 source，只组合多个年度 source。
- citation 口径：每个 year 的每个字段必须保留来自对应年度年报 table locator 的 citation；不得只给汇总 citation。
- 10I 才能实现 multi-year annual performance aggregation service；10I 才裁决显式 `document_id` list 输入和 Service 编排。10H 不做 repository 自动补齐或自然语言 `近 5 年` 解析。
- 10H 后续实现不得重新写第二套表格抽取规则；只能编排 10F / 10G 的单年度 extraction result。
- 10H 不做年化收益率、扣费后收益率、收益复权、净值计算、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- Slice 10H 已经 MiMo review `ACCEPTED`。
- 10H 已完成 docs-only source contract，不实现 aggregation service。
- 10H source contract 固定为 multiple annual reports；每个年度复用 10F / 10G 单年度 extraction result。
- 10H 已明确 bounded year coverage：5 年窗口内允许 3-5 个完整年度，缺失年份必须结构化暴露；少于 3 年整体 `not_found`。
- 10H 已明确不做 single-report rolling period extraction，不使用 `过去三年` / `过去五年` 行，不做 OCR / chart parsing、外部数据源、管理人报告文字 fallback、自然语言 `近 5 年` 解析或 repository 自动补齐。
- 10H remaining blocking risk: none reported。
- Post-MVP 10I 裁决为 multi-year annual performance aggregation service。
- 10I 放在 Service 层，定位为 use case orchestration；不放到 Agent、CLI、Store 或 ToolService。
- 10I 目标是显式接收多年度已导入年报，编排 10F / 10G 单年度 extraction result，返回 3-5 年 bounded coverage 的 `MultiYearAnnualPerformanceSeries`。
- 10I 首批输入固定为：`fund_code`、`requested_years: list[int]`、`annual_report_documents: list[{year, document_id}]`、`share_class: optional`。
- 10I 不做 `fund_code + years -> repository 自动查找`，不做自然语言 `近 5 年` 解析，不自动导入缺失 PDF，不改 CLI 默认输出。
- `requested_years` 约束：长度必须为 3-5；年份必须唯一；Service 可 normalize 为升序，并在 DTO 中输出 normalized `requested_years`。
- 每个 `document_id` 必须显式绑定 year；不得只从 `document_id` 字符串猜年份。
- 绑定 year 与单年度 extraction result 的 `report_year` 不一致时，整体 fail-closed 为 `identity_mismatch`。
- 10I 不重新解析表格，不新增第二套表格抽取规则；只能编排 10F / 10G 的单年度 extraction result。
- 某 year / share class 同时具备 `annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return` 三个字段及 table locator citation，才算 complete year。
- 任一字段缺失时，该 year 对该 share class 计入 `missing_years`；若导致该 share class 完整年度少于 3 年，则不返回该 share class。
- coverage 语义沿用 10H：`minimum_complete_years=3`，`maximum_complete_years=5`；5 年完整为 `coverage_status=complete`，3-4 年完整为 `coverage_status=partial`，少于 3 年整体 `not_found`。
- `coverage_status=partial` 是成功结果的 coverage metadata，不是 failure code；不新增 `partial_success`。
- share class 口径：按 share class 独立计算 coverage。用户指定 share class 时只评估该 share class；未指定时返回所有达到 3-5 年 coverage 的 share class series。所有 share class 都不足 3 年时整体 `not_found`。
- `missing_years` 首批只返回年份列表，不新增 `missing_reasons`。
- DTO 形态沿用 10H：`MultiYearAnnualPerformanceSeries` 包含 `fund_code`、`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`、`share_class_scope`、`rows`、`citations`。
- 每个 row 包含：`year`、`annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return`、`citations`。
- citation 口径：每个 year / field 保留原年度年报 table locator citation；禁止只给汇总 citation。
- 失败语义沿用现有 failure code：document/year 与 extraction `report_year` 冲突为 `identity_mismatch`；少于 3 个完整年度为 `not_found`；单年度文档不可读、目标表缺失或字段缺失只计入 `missing_years`，若导致不足 3 年则 `not_found`；extractor 配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10I 不新增 `missing_year`、`partial_success`、`coverage_error` 或新 failure taxonomy。
- 10I 不做 repository 自动补齐、自然语言解析、OCR / chart parsing、外部数据源、年化收益率、扣费后收益率、收益复权、净值计算、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- 10I 测试必须覆盖：5 年完整为 `complete`；4 年完整 / 缺 1 年为 `partial`；3 年完整 / 缺 2 年为 `partial`；少于 3 年为 `not_found`；C 类不足 3 年时不返回 C 类；每个字段保留对应年度 table citation；不重新解析表格、不走 OCR / chart / external source。
- Slice 10I 已经 MiMo review `ACCEPTED`。
- Service 层已实现 multi-year annual performance aggregation service。
- 10I 显式接收 `requested_years` 与 `annual_report_documents[{year, document_id}]`，编排 10F / 10G 单年度 extraction result；不做 repository 自动补齐、自然语言解析、自动导入 PDF、CLI 改造、OCR / chart parsing 或外部数据源。
- 10I 已实现 3-5 年 bounded coverage：5 年完整为 `coverage_status=complete`；3-4 年完整为 `coverage_status=partial`；少于 3 年整体 `not_found`。
- 10I 已实现 share class 独立 coverage；不足 3 年的 share class 不返回，所有 share class 都不足 3 年时整体 `not_found`。
- 10I 已覆盖 document/year 与 extraction `report_year` 冲突时 `identity_mismatch`。
- 10I remaining blocking risk: none reported。
- Post-MVP 10J 裁决为 multi-year performance service-to-agent exposure contract。
- 10J 是 docs-only contract slice：只更新 `docs/design.md` 和 `docs/implementation-control.md`，不实现 tool-loop，不修改 CLI / code / tests，不做 repo auto lookup，不做自然语言 `近 5 年` 解析，不做 missing-PDF auto import，不做 filename / document_id year guessing。
- 10J 目标是定义 Agent / Host 如何通过受控工具消费 10I 的 `MultiYearAnnualPerformanceSeries`。
- 10J 新增受控 Agent tool contract，工具名为 `aggregate_multi_year_annual_performance`。
- 该工具是 controlled tool，不是开放问答能力；Agent 不得直接调用 Service 内部方法或读取 raw Docling JSON / 本地 PDF path / cache path。
- 受控工具输入字段固定为：`fund_code`、`requested_years`、`annual_report_documents[{year, document_id}]`、`share_class optional`。
- Agent / Host 不得做自然语言 `近 5 年` 解析、repository 自动查找、缺失 PDF 自动导入、文件名猜年份或 document_id 字符串猜年份。
- 工具输出成功时返回 `series[]`，失败时返回 `failure`；不生成投资分析文本。
- 每个 series 必须保留 `coverage_status`、`covered_years`、`missing_years`、`rows` 和每年每字段 citation。
- Agent 允许做的事仅限：调用受控工具 `aggregate_multi_year_annual_performance`；把 DTO 字段转述为 plain answer；明确展示 `coverage_status`、`covered_years`、`missing_years`；引用每年每字段 table locator citation。
- Agent 禁止做的事：计算年化收益率、扣费后收益率、排名、打分、收益来源解释、`R=A+B-C`、投资结论或补齐缺失年份。
- CLI 边界：10J 不改 CLI 默认输出，不新增 `fund-checklist ask`、multi-year CLI 子命令或 CLI 参数。
- coverage 展示语义：`coverage_status=complete` 可表述为覆盖全部 requested years；`coverage_status=partial` 必须同时展示 `covered_years` 和 `missing_years`，不得写成”近 5 年完整表现”。
- 少于 3 年时工具沿用 10I 返回 `not_found`；Agent 不得生成部分答案。
- citation 要求：final answer citations 必须包含被引用 year / field 的 table locator citation；禁止只引用汇总 series citation。
- failure 语义沿用 10I，只允许四个 failure code：`identity_mismatch`、`not_found`、`schema_drift`、`unavailable`；Agent 只把 failure 转为 fail-closed plain answer，不新增 failure code。
- 后续实现测试建议放在 10K fake/injected Agent tool-loop：验证 Agent 调用 `aggregate_multi_year_annual_performance`，消费 `coverage_status=partial`，最终回答包含 covered/missing years 和 citations，且不泄漏 raw Docling JSON / local path / cache path，不输出年化收益、扣费后收益或投资判断。
- 10J 不做 LLM 自然语言 query routing、repository 自动补齐、CLI 新入口、多 PDF 导入流程、报告生成、template chapter execution、`R=A+B-C`、年化收益率、扣费后收益率或投资判断。
- Post-MVP 10K 裁决为 multi-year performance fake/injected Agent tool-loop。
- 10K 是 implementation slice，目标是在 fake/injected Agent tool-loop 中暴露受控工具 `aggregate_multi_year_annual_performance`，验证 Agent 能消费 10I `MultiYearAnnualPerformanceSeries`。
- 10K 不接真实 LLM，不改 CLI 默认输出，不新增 `fund-checklist ask`、multi-year CLI 子命令或 CLI 参数。
- 10K 工具名称固定为 `aggregate_multi_year_annual_performance`，不得新增别名。
- 工具输入沿用 10I / 10J：`fund_code`、`requested_years`、`annual_report_documents[{year, document_id}]`、`share_class optional`。
- Agent 不得自己执行自然语言 `近 5 年` 解析、repository 自动查找、自动导入 PDF、文件名猜年份或 document_id 字符串猜年份。
- 工具输出只返回 10I 结构化 result：成功为 `series[]`，失败为 `failure`；tool 层不生成分析文本。
- Agent 允许行为只限：调用受控工具；转述 DTO 字段；展示 `coverage_status`、`covered_years`、`missing_years`；附带 per-year / per-field table locator citation。
- `coverage_status=partial` 时，final answer 必须同时出现 `covered_years` 和 `missing_years`；不得写成“近 5 年完整表现”。
- final answer citations 必须来自具体 year / field 的 table locator；禁止只给 series-level citation、汇总 citation 或无字段来源 citation。
- tool failure 时 Agent 必须 fail-closed，返回 `AgentRunResult.failure`；不得生成部分答案。
- failure 语义沿用 10I / 10J：`identity_mismatch`、`not_found`、`schema_drift`、`unavailable`；10K 不新增 failure code。
- 10K 禁止计算年化收益率、扣费后收益率、排名、打分、收益来源解释、`R=A+B-C`、投资结论、报告生成或补齐缺失年份。
- 10K 测试只使用 fake/injected tool-loop，不接真实 provider，不联网，不读取真实 API key。
- 10K 必须测试：partial coverage final answer includes covered_years and missing_years；complete coverage final answer does not invent missing_years；tool failure `not_found` -> `AgentRunResult.failure`；`identity_mismatch` -> `AgentRunResult.failure`；final answer includes per-year / per-field citations；final answer does not include annualized_return / fee-adjusted return / investment judgment；no raw Docling JSON / local path / cache path leakage。
- Post-MVP 11A 裁决为 performance disclosure locator，插入 10D 之前；11A 只做业绩表现披露定位和 citation，不抽取结构化字段。
- 11A profile 名称为 `performance_returns`；名称只表示业绩表现披露定位，不代表字段抽取。
- acceptable title family 固定为：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`。
- 首批 aliases 固定为：`净值增长率`、`业绩比较基准收益率`、`基准收益率`、`收益表现`、`基金净值表现`；不纳入 `业绩`、`收益`、`表现` 等宽泛 alias。
- candidate queries 固定为原始 query、`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`、`业绩比较基准收益率`。
- success 语义：必须命中 acceptable title family，并返回 section citation；若目标披露存在相关表格，则必须包含 table citation。当前真实样本存在表格，因此 11A smoke 要求 table citation。
- 11A 不裁决 A/C 类字段值；若表格同时包含多个份额类别，只展示原始表格片段，不筛选、不判断、不抽值。
- failure 语义沿用现有 failure code：目标披露未命中为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`；不新增 `performance_not_found`、`period_not_found` 或 `partial_success`。
- 11A 不输出 `nav_growth_rate`、`benchmark_return_rate`、`period`、`decimal_percent_text` 等结构化字段，不计算 `A=R-B`。
- 11A 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、字段抽取、calculation framework、template contract execution、chapter contract execution、自动报告或投资判断。
- Slice 11A 已经 MiMo review `ACCEPTED`。
- Slice 11A 真实 CLI smoke 结果：
  - work dir: `.fund_checklist_cli_smoke_11a`
  - `净值增长率`: exit code `0`；answer 包含 `3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较`。
  - Citations / Trace 存在，且包含 table citation：CLI 输出包含 `locator_kind=table`。
  - CLI 默认输出不包含 `routing_trace`。
  - CLI 输出不包含 `nav_growth_rate`、`benchmark_return_rate` 或 `decimal_percent_text` DTO；没有字段值抽取或计算。
- 11A remaining blocking risk: none reported。
- Post-MVP 11B 裁决为 disclosure locator contract registry。
- 11B 目标是把现有 controlled disclosure profiles 收敛为 Service 层内部 locator contract registry，降低后续继续堆零散 hardcoded profile 的风险。
- 11B 不新增新的披露对象定位能力；只迁移 / 规范已有 `holdings_top10`、`asset_allocation`、`fee_rates`、`performance_returns` 等 reading locator profile。
- registry 最小字段固定为：`profile_name`、`aliases`、`candidate_queries`、`acceptable_title_family`、`requires_table_citation`、`extraction_allowed`。
- `profile_name` 是内部 profile 名称，不作为 public tool 输出或用户可见契约。
- `aliases` 只用于判断用户 query 是否进入该受控 profile；alias 本身不得作为 evidence 成功条件或 citation 来源。
- `candidate_queries` 是 Service 层按顺序调用既有 Host / Agent / `search_document` 的受控检索候选，不修改 `search_document` public contract。
- `acceptable_title_family` 是披露目标成功条件；只有命中可接受标题族才算 profile 成功，不能把 keyword 命中当成 disclosure target success。
- `requires_table_citation` 只表达该 profile 是否要求 table citation；若为 true 且目标样本存在表格，最终 evidence 必须包含 table citation。
- `extraction_allowed` 在 11B 固定为 `False`；registry 只表达阅读定位 contract，不开放字段抽取、计算或章节生成。
- 11B 仍放在 Service 层；Store / ToolService / Agent 不承担 routing registry、自由语义理解或 target success 判定。
- 11B 不改变 CLI 默认输出格式，不暴露 `routing_trace`，不新增 DTO，不新增 public failure code。
- failure 语义沿用现有 failure code：所有 candidate 未命中目标披露为 `not_found`；registry 配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 11B 不接 LLM、embedding、外部搜索服务，不做开放语义理解、自动分词、同义词扩散、top-N rerank、歧义消解、字段抽取、calculation framework、template contract execution、chapter contract execution、自动报告或投资判断。
- Slice 11B 已经 MiMo review `ACCEPTED`。
- Slice 11B 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；命中 `股票投资明细`；Citations / Trace / table citation 存在；CLI 默认输出不包含 `routing_trace`。
  - `资产配置`: exit code `0`；命中 `期末基金资产组合情况`；Citations / Trace / table citation 存在；CLI 默认输出不包含 `routing_trace`。
  - `费用`: exit code `0`；命中 `基金管理费`、`基金托管费`、`销售服务费`；Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
  - `净值增长率`: exit code `0`；命中 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`；Citations / Trace / table citation 存在；未输出结构化字段 DTO。
- 11B remaining blocking risk: none reported。

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

10K 已完成并经 ds review `ACCEPTED`。下一步尚未裁决。若继续收益链路，可考虑 10L multi-year performance CLI integration 或其它后续 slice。不得改 CLI 默认输出，不接真实 LLM，不做自然语言 `近 5 年` 解析、repository 自动补齐、报告生成、年化收益率、扣费后收益率、`R=A+B-C` 或投资判断。

禁止事项：

- 禁止把 10D 扩成计算、报告或投资判断。
- 禁止依赖章节编号 `3.2.1`；只能依赖 title family + table signature + citation。
- 禁止把年度业绩表格抽取扩成计算或自动报告。
- 禁止把 10G 的 `annual_excess_return` 表述为系统计算值；它只能来自年报显式披露列 `①－③`。
- 禁止用管理人报告文字作为 10F fallback。
- 禁止回到年度图 / 图片做 OCR / chart parsing，除非另开 chart/OCR gate。
- 禁止扩大候选来源到第三方平台、净值数据库、季报 / 半年报、基金合同或招募说明书。
- 禁止把 `chart_or_image` source 强行 OCR 或图表解析。
- 禁止做 `past_1_year` citation specificity。
- 禁止新增披露对象定位能力。
- 禁止把 `past_1_year` 命名为 `report_year` 或年度 2024。
- 禁止抽取近 3 年、近 5 年、成立以来、年度序列表或图表数据。
- 除 10G 已裁决的 `annual_excess_return` disclosed-field DTO 外，禁止输出其它 `excess_return`、`annualized_return`、`max_drawdown`、`volatility`、`sharpe`、`tracking_error`、`turnover_rate`。
- 禁止抽取换手率；禁止新增 `turnover_rate` locator；禁止把股票买入 / 卖出金额包装成换手率 evidence。
- 禁止从单份年报合成近 3 年 / 近 5 年 rolling period；当前 2024 年报不存在 `过去三年` / `过去五年` 行。
- 禁止把 bounded partial-by-year 命名为 `partial_success`；3-4 年完整覆盖只能作为成功结果里的 `coverage_status=partial`。
- 禁止在少于 3 个完整年度时返回多年度序列。
- 禁止计算显性成本小计、总成本、扣费后收益率或年化收益率。
- 禁止实现 `R=A+B-C`、Alpha/Beta/Cost 综合评估、同类中位数或判断生成。
- 禁止新增 alias 覆盖矩阵；11B 只允许把既有 aliases 迁入 registry，不扩大 alias 范围。
- 禁止改 `search_document` public contract。
- 禁止把 routing 放入 Store / ToolService / Agent 层。
- 禁止开放式 query normalization、自动分词、同义词扩散、query intent 分类、embedding 或 LLM intent。
- 禁止扫描 top-N search results、rerank、歧义消解或 LLM 判断哪个表更相关。
- 禁止引入 score、confidence、rationale、`partial_success` 或新 failure taxonomy。
- 禁止改变 CLI 默认输出格式。
- 禁止把 10D 解释为泛化字段抽取能力或 benchmark；10D 只抽取已裁决的两个 `past_1_year` performance return 字段。
- 禁止新增 `fund-checklist ask` 或 CLI 参数。
- 禁止接真实 LLM、embedding、外部搜索服务。
- 禁止执行 template-informed intent routing、chapter contract execution、calculation framework、report audit、自动报告或投资判断。
- 禁止暴露 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。

10G closeout 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
```

回归验证命令：

```bash
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
```

10G 保留 11A/11B 已完成真实 CLI smoke 行为；如实现触及 CLI 或 routing，需重跑：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '净值增长率' --work-dir .fund_checklist_cli_smoke_11a
```

11B 既有真实 CLI smoke 回归命令：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '前十大持仓' --work-dir .fund_checklist_cli_smoke_11b_holdings
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '资产配置' --work-dir .fund_checklist_cli_smoke_11b_asset
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '费用' --work-dir .fund_checklist_cli_smoke_11b_fees
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '净值增长率' --work-dir .fund_checklist_cli_smoke_11b_performance
```

验收点：10G Service / tests 层可从真实 2024 年度报告标准披露表抽取 A 类 `annual_excess_return = 2.87%`，并返回 `report_year=2024`、`source_period_label=过去一年`、`share_class_scope=A`、`source_column_label=①－③` 和 table locator citation。10G 不通过 `annual_nav_growth_rate - annual_benchmark_return_rate` 计算，不扫描管理人报告文字或年度图 / 图片 fallback，不改变 CLI 默认输出；既有 CLI 对 `净值增长率` 仍只展示阅读 answer / citation / trace，不暴露结构化 DTO。MiMo verdict: `ACCEPTED`；remaining blocking risk: none reported。

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
9C. Table-backed first-hit consumption：Agent 只在 first hit 为 high-certainty table-backed result 时直接 `read_table`；不扫描 top-N、不做 rerank、synonym routing、LLM 判断或 section 摘要。
9D. Controlled query profile routing：Service 层对三类 hardcoded profile 生成最多 3 个 candidate queries 并顺序调用既有 Host/Agent；不改 `search_document` contract，不做开放语义理解、embedding、LLM intent 或计算。
9E. Service routing attempts audit：为 9D routing 增加最小 attempts 记录；只记录 query/profile/result/failure_code，不存 selected_query、score、confidence 或解释字段，不改 CLI/Agent/ToolService contract。
9F. Controlled profile real-smoke regression：blocked by design；真实 smoke 证明 keyword-level routing success 不能证明 disclosure target success。
10A. Controlled disclosure target contract：Service 层定义受控披露目标契约，区分 query 命中和披露目标命中；已 accepted；`费用` 在旧 target 下 fail-closed 为 `not_found`。
10B. fee_rates reading locator：已 accepted；把 `expenses` 收窄为 `fee_rates`，定位 `基金管理费`、`基金托管费`、`销售服务费` 三个目标 disclosure sections；只做阅读定位和 citation，不抽取数值、不计算成本或收益率。
10C. fee_rates value extraction contract：已 accepted；抽取 `management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate` 三个当前适用年费率字段；不抽取收益/换手率，不做成本或收益计算。
10D. performance return fields extraction contract：已 accepted；基于 11A 已定位的 performance disclosure table 抽取 `past_1_year` 的 `nav_growth_rate` / `benchmark_return_rate` 受控 DTO；不计算、不改 CLI 默认输出；不做 `turnover_rate` locator。
10E. annual performance returns source decision：source-decided；年度业绩 deterministic source 选择 title-family matched performance comparison table，即 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` 标准披露表；管理人报告文字仅为 secondary reference；年度图 / 图片不进入当前 deterministic extraction。
10F. annual performance table extraction from title-family matched table：已 accepted；抽取 `report_year=request.year`、`source_period_label=过去一年` 的 `annual_nav_growth_rate` / `annual_benchmark_return_rate`；不依赖章节编号，不使用管理人报告文字 fallback，不计算。
10G. annual excess return disclosed-field extraction：已 accepted；从 title-family matched performance comparison table 的显式披露列 `①－③` 抽取 `annual_excess_return`；不通过 10F 字段计算，不改 CLI 默认输出，不进入 `R=A+B-C`。
10H. multi-year annual performance source contract with bounded year coverage：已 accepted；source 选择 multiple annual reports，后续聚合 10F / 10G 单年度 DTO；允许 3-5 年 bounded coverage，缺失年份必须结构化暴露，少于 3 年 fail-closed；10H 不实现 aggregation service。
10I. multi-year annual performance aggregation service：已 accepted；Service 层显式接收 requested_years + year/document_id 映射，编排 10F / 10G 单年度 extraction result，返回 3-5 年 bounded coverage series；不改 CLI，不做 repository 自动补齐或自然语言解析。
10J. multi-year performance service-to-agent exposure contract：docs-only completed；定义 Agent / Host 通过受控 tool `aggregate_multi_year_annual_performance` 消费 10I series DTO 的边界；受控工具输入固定为 `fund_code` / `requested_years` / `annual_report_documents[{year, document_id}]` / `share_class optional`，输出成功时 `series[]` 含 `coverage_status` / `covered_years` / `missing_years` / `rows` / per-year per-field citations，失败时 `failure`；failure code 只允许 `identity_mismatch` / `not_found` / `schema_drift` / `unavailable`；Agent 只允许调用受控工具并转述 DTO 字段，禁止年化收益 / 扣费后收益 / 排名 / 打分 / R=A+B-C / 投资结论 / 补齐缺失年份；不实现 tool-loop，不改 CLI / code / tests，不做 repo auto lookup / 自然语言解析 / missing-PDF auto import / filename year guessing。
10K. multi-year performance fake/injected Agent tool-loop：已 accepted；在 fake/injected Agent tool-loop 中暴露 `aggregate_multi_year_annual_performance`，通过 `aggregate_handler` 注入回调调用 10I Service；`ToolCall.extra` 携带 tool-specific 参数；failure 时 `AgentRunResult.failure`；163 passed, 0 failures；不改 CLI，不接真实 LLM，不做自然语言解析或报告生成。
11A. performance disclosure locator：已 accepted；定位 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` / `基金净值表现` 披露，返回 section/table citation 和原始表格片段；不抽值、不计算。
11B. disclosure locator contract registry：已 accepted；把既有 controlled disclosure profiles 收敛为 Service 内部 locator contract registry；不新增披露对象，不抽值、不计算、不改 public tool / CLI contract。

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
