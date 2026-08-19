# 快照 interactive 开放 — 设计 Plan（2026-08-19）

- 阶段：仅设计；不改任何代码/测试/文档（Allowed write set 见文末）。
- 背景：design.md §6.25 裁决 15 记录「interactive：本期不扩开放问答；快照命令独立闭环，不接入 interactive 检索路由」。本 slice 收口该 backlog：已导入的季报（quarterly_report）/半年报（semiannual_report）快照文档接入 interactive 开放问答，走既有 LLM 工具调用检索链路（search/read_section/read_table 等）；年度 interactive 行为必须零变化。
- 口径：CIC-lite；plan artifact 最多 1 份；plan review ACCEPTED 后才进入实现。

## 1. 现状分析（基于代码事实）

### 1.1 interactive 入口与文档选择（fund_agent/cli/main.py）
- interactive parser（main.py:261-268）：现有参数 `--fund-code`（必填）/`--work-dir`/`--label`/`--year`（可空，默认最新）。
- `_run_interactive_command`（main.py:1479 起）：
  - 文档解析：`service.resolve_by_fund_code(fund_code, work_dir)`（main.py:1498），失败输出「未找到基金 X 的已导入年报」并返回 `CLASSIFIED_FAILURE_EXIT_CODE`。
  - 年份选择（main.py:1508-1528）：`--year` 校验不通过即报错退出；stdin 非 TTY 时自动默认最新年份（F3 规则，不调用 input()）；TTY 交互选择。
  - PinnedState 构造（main.py:1552-1558）：`available_document_ids` / `active_document_id` / `active_year`。
  - store 构建（main.py:1572-1584）：遍历 `resolution.documents` 用 `FilesystemReportRepository.load_store(document_id)` 逐个加载进 `_stores`，再包 `FundDocumentToolService(_stores)`；单文档加载异常被 `except Exception: pass` 静默跳过（既有行为）。
  - ChatService 构造（main.py:1586-1592）：`tool_service=_tool_svc`、`aggregate_handler=_build_aggregate_handler(work_dir)`。
  - `/document` 切换（main.py:1678-1701）：重建 PinnedState（只保留 fund_code/available_document_ids/active_document_id/active_year；`user_constraints` 也会被丢弃——既有行为），切换范围 = `available_document_ids`。（行号修正：1700-1724 为 chat_turn 区域，非 /document handler。）
- `_build_aggregate_handler`（main.py:333-372）：以 catalog 重解析 `annual_report_documents`（`_collect_matching_docs`，main.py:333-365 已按 `report_type == "annual_report"` 过滤，与 §6.25 裁决 17 口径一致）。

### 1.2 resolve_by_fund_code（fund_agent/service/extraction.py:4569-4612）
- 当前实现**不按 report_type 过滤**：把 catalog 中该 fund_code 下所有 report（含 snapshot）按 `year` last-wins 收进 `seen_years`。
- 污染事实：同一基金同一年既有年报又有季报时，后导入者会覆盖 `seen_years[year]`，annual interactive 可能拿到快照 document_id（main.py 只调用了 resolve_by_fund_code，见 extraction.py:4569 唯一调用点 main.py:1498）。
- 返回 `FundCodeResolution`（models.py:308-321）：`documents: tuple[AnnualReportDocument, ...]`（models.py:288-305，仅 year+document_id）+ `available_years`。季度多期同一年会在 year key 上冲突，无法直接复用该 DTO 表达快照。

### 1.3 快照匹配与 store（fund_agent/service/extraction.py / fund_agent/fund/document_tools/persistent_repository.py）
- `generate_snapshot_report` 匹配（extraction.py:2749-2757）：`fund_code + report_type + year (+ quarter)`，取 `matches[0]`；无匹配返回 `NOT_FOUND`「catalog 中未找到 … 文档」。semiannual 不匹配 period（H1 固定）。
- `generate_report`/multi-year 防污染口径（extraction.py:2487-2502）：只匹配 `report_type == "annual_report"`（§6.25 裁决 17）。
- catalog schema（persistent_repository.py:131-155 `list_reports()`）：每条含 `document_id/fund_code/fund_name/year/report_type/quarter/period/share_class`；`quarter`/`period` 在 `_identity_to_catalog`（persistent_repository.py:205-218）落库。
- `load_store`（persistent_repository.py:92-118）：按 document_id 从 catalog 恢复 store，report-type 无关（identity 从 catalog record 读取，不解析 document_id 字符串），快照 store 可直接复用。
- `_PARSED_DOCUMENT_ID_PATTERN`（local_pdf_source.py:31-35）与 `_QUARTERLY_DOCUMENT_ID_PATTERN`（local_pdf_source.py:36-37）：quarterly document_id 含 `-Q[1-4]-` 段；semiannual 不带期次段。导入期已校验，读取期不依赖该 pattern。

### 1.4 检索链路（fund_agent/agent/llm_tool_loop.py）
- runner 按 `document_id` 驱动：`run(document_id=active_document_id, ...)`（main.py 经 ChatService 传 session.pinned_state.active_document_id，chat_service.py:266）。
- `_invoke_tool_call`（llm_tool_loop.py:1270-1337）：document_id 为空用 `expected_document_id` 补全（:1307），不匹配拒绝（:1308-1311）；search/read_section/read_table/get_excerpt 全部走 `FundDocumentToolService` 按 document_id 取 store。
- `_dedup_key`（llm_tool_loop.py:1855-1900）：search/read_section/read_table 的 key 均含 document_id——快照 doc id 天然参与去重。
- interactive 既有机制：空搜索连续 2 次收敛（llm_tool_loop.py:626-666）、read_table 表号一致性校验（:1319-1326，仅 interactive）、终答守卫 + ≤200 字（:557-563）、force_answer 降级（:676+）、失败调用跨轮短路（:574-580）——均为 runner/scene 级，与文档类型无关。
- aggregate：`_call_allowed_tool` 中 `aggregate_handler is None` 时返回 unavailable fail-closed（llm_tool_loop.py:1346-1348）。

### 1.5 报告期口径（fund_agent/service/chat_service.py + fund_agent/service/session_models.py + fund_agent/host/session_store.py）
- `_build_contributions` runtime 段（chat_service.py:733-760）：注入「当前基金代码 / 查看年份 / 当前文档 document_id」；**无 report_type/期次**。fund_context 段（:767-777）同理。
- `user_constraints` 透传（chat_service.py:762-765）：`PinnedState.user_constraints` 直接作为 contribution 注入——可作为免 schema 变更的旁路，但语义上是用户约束（current_goal/confirmed_facts 等，session_models.py:256-296），不宜承载内部报告上下文。
- `PinnedState`（session_models.py:14-30）：fund_code / available_document_ids / active_document_id / active_year / user_constraints。`Session.with_pinned_state`（session_models.py:293-296）仅透传这四个字段。
- session 序列化（host/session_store.py:170-184 save / :224-231 load）：字段显式列出；load 用 `.get()` 缺省——新增 PinnedState 字段带默认值时，旧 session（schema v1）可无损加载，`_SESSION_SCHEMA_VERSION` 无需 bump。
- scene config（scene_config.py:104-118）：INTERACTIVE_SCENE_CONFIG 的 context_slots=("runtime","fund_context","memory","history","retrieval")，max_iterations=8，allowed_tools 含 aggregate。快照模式不改 scene config（保持 annual 行为零变化）。

## 2. 设计决策

### 决策 1：参数形态（interactive parser）
新增参数（全部可选，默认值保证既有调用零变化）：
- `--report-type`：choices `annual_report`（默认）/ `quarterly_report` / `semiannual_report`。
- `--quarter`：int 1-4，仅 `--report-type quarterly_report` 时合法；缺省 = 所选年份内 catalog 中最新季度。
- `--period`：choices `["H1"]`（默认 H1），仅 `--report-type semiannual_report` 时合法；与 snapshot-semiannual CLI（main.py:253-254）对称，当前只支持 H1（non-goal：不做 H2）。
- `--year`：语义统一为「报告年份」；annual 与 snapshot 共用；缺省 = 该 report-type 家族内最新年份（沿用 F3：stdin 非 TTY 自动默认，TTY 交互选择）。
- 校验：`--quarter`/`--period` 与 `--report-type` 不匹配时报错退出（`CLASSIFIED_FAILURE_EXIT_CODE`，风格对齐 main.py:1511-1515 的 year 校验）；非法组合直接拒绝，不做静默忽略。
- 理由：参数名与 snapshot-quarterly/semiannual CLI 对齐；默认最新与 annual interactive 既有默认行为一致；`--report-type` 默认 annual 保证老命令/老 session 恢复路径不变。

### 决策 2：文档匹配与 store 加载（含防污染）
- **annual 模式**：`resolve_by_fund_code` 增加可选参数 `report_type: str = "annual_report"`，循环内加 `report.get("report_type") == report_type` 过滤（对齐 extraction.py:2487-2502 口径）。该函数唯一调用方是 interactive（main.py:1498），改动 blast radius 小；mixed catalog 场景下行为从「可能拿到快照 doc」修正为「只拿年报 doc」（修复 §1.2 污染事实）。
- **快照模式**：新增 Service 层解析（与 generate_snapshot_report 匹配同源，extraction.py:2749-2757）：
  - `resolve_snapshot_reports(fund_code, work_dir, report_type)` → 新 DTO `SnapshotResolution`（models.py 新增，含 `fund_code/fund_name/documents/available_years`；`SnapshotReportDocument(year, quarter, period, document_id)`）。匹配键 = `fund_code + report_type`（+ year 由调用方过滤），quarterly 的同一 year 多条 quarter 全部保留（不再 year last-wins）。
  - 期次选择：`--quarter` 缺省 = 所选 year 内最大 quarter；`--period` 缺省 H1。
- **防污染双向**：annual 模式匹配不到 snapshot（决策 2 过滤）；快照模式匹配不到 annual（report_type 键本身互斥）；与 generate/multi-year 的 report_type 过滤口径一致。
- **store 加载**：复用 `FilesystemReportRepository.load_store(document_id)`（persistent_repository.py:92），循环逻辑沿用 main.py:1544-1550；`available_document_ids` = 该 fund_code + report_type 家族全部 doc id（支持 `/document` 在期次间切换），`active_document_id` = 选中期次。
- 无匹配：输出「未找到基金 X 的已导入季报/半年报。请先导入…」（风格对齐 main.py:1501 现有文案），返回 `CLASSIFIED_FAILURE_EXIT_CODE`。

### 决策 3：检索链路与 aggregate 边界
- runner 零改动：active_document_id = 快照 doc id 后，expected document_id 补全、`_document_id_matches` 校验、`_dedup_key`（含 document_id 维度）、空搜索收敛、read_table 表号一致性校验全部原样生效（llm_tool_loop.py:1270-1337 / :1855-1900）。
- **aggregate 对快照不开放**：快照模式 ChatService 传 `aggregate_handler=None`（main.py:1553-1561 处分支），runner 对 aggregate 调用返回 unavailable fail-closed 并回喂 LLM（llm_tool_loop.py:1346-1348）。不修改 INTERACTIVE_SCENE_CONFIG.allowed_tools / ALLOWED_LLM_TOOL_NAMES（避免影响 annual 与 ask）。aggregate 的 handler 本身已是 annual-only（_collect_matching_docs），但仅靠它不足以阻止「快照会话里聚合年报」，必须 handler=None 显式关闭。
- 受控检索路由（candidate queries + 表锚点，chat_service.py:790-830）：不改。候选词为纯查询文本；锚点解析对 active document 执行且失败 fail-open 不注入（既有语义）；快照表格结构不同时最多浪费受控的候选词尝试，由空搜索收敛兜底。不新增快照 routing profile（non-goal：不改抽取 profile）。

### 决策 4：报告期口径（prompt 注入）
- `PinnedState` 新增 3 字段（session_models.py:14-30）：`report_type: str = "annual_report"`、`quarter: int | None = None`、`period: str | None = None`。
- `Session.with_pinned_state`（session_models.py:293-296）与 `_session_to_json` / `_session_from_json`（host/session_store.py:170-184 / :224-231）同步透传/序列化；load 用 `.get()` 缺省，旧 session 兼容，`_SESSION_SCHEMA_VERSION` 不 bump。
- `_build_contributions` runtime 段（chat_service.py:733-760）快照模式追加（annual 模式不追加任何行，行为零变化）：
  - `- 报告类型: 季报（quarterly_report）` / `- 报告类型: 半年报（semiannual_report）`
  - `- 报告期: 2026 年二季度（Q2）` / `- 报告期: 2025 年 H1 半年报`
  - 硬规则行：`注意：当前文档为单期快照，非年度报告；数据仅覆盖当期，禁止与年度/多年数据混用，禁止做多年趋势判断。`
- 不新增 prompt fragment / context_slot / scene config 变更（annual 与 snapshot 共用 scene，避免 annual 行为漂移）。
- `/document` 命令（main.py:1678-1701）重建 PinnedState 时保留新字段（当期次家族内切换）。
- 快照模式 `/document` 在期次间切换时，`quarter`/`period` 应从目标 document 的 catalog record 重新解析（非透传旧值）。
- 投资建议守卫、终答 ≤200 字、有界重答、force_answer 降级截断：全部 runner/scene 级既有机制，不动。

### 决策 5：边界 / non-goals
- 不改快照报告生成（`generate_snapshot_report` / `extract_snapshot_data` / snapshot 模板 / prompts）。
- 不改 snapshot 抽取 profile（`quarterly_performance` / `semiannual_performance` 等 registry）。
- 不改 annual interactive 行为（annual 专属断言见测试计划；唯一例外是 mixed catalog 下 annual 解析修正为 annual-only，见决策 2/裁决点 2）。
- 不做 H2（半年报仅 H1，`--period` choices 硬约束）。
- 不接入 `ask` 子命令（本 slice 仅 interactive）。
- 不引入多年聚合 / 不把快照纳入 multi-year 与 generate annual 系列（catalog 过滤既有口径不变）。
- 不改 llm_tool_loop / scene_config / prompt 模板 / DocumentToolService 公共契约。

### 决策 6：write set 草案（实施阶段用，本阶段不实施）
- `fund_agent/cli/main.py`（interactive parser + `_run_interactive_command` 分支 + `/document` 字段保留 + 校验；`/document` handler（main.py:1678-1701）重建 PinnedState 时需保留 `report_type`/`quarter`/`period` 字段，快照模式期次从目标 document 的 catalog record 重新解析）
- `fund_agent/service/extraction.py`（`resolve_by_fund_code` 加 report_type 过滤 + 新增 `resolve_snapshot_reports`）
- `fund_agent/service/models.py`（新增 `SnapshotResolution` / `SnapshotReportDocument` DTO）
- `fund_agent/service/session_models.py`（PinnedState 3 字段）
- `fund_agent/host/session_store.py`（pinned_state 序列化；路径确认：session_store 位于 host 层，非 service 层）
- `fund_agent/service/chat_service.py`（runtime contribution 报告期注入）
- 测试：`tests/fund/cli/test_cli_interactive.py`（新增快照用例 + annual 回归守卫）、`tests/fund/service/`（解析/匹配单测，可与 test_snapshot_extraction.py 的 005680 fixture 同源）、必要时新增 `tests/fund/cli/test_cli_interactive_snapshot.py`
- 文档同步：`docs/design.md`（§6.25 裁决 15 状态更新为已收口）、`docs/implementation-control.md`（快照 interactive slice 记录）

### 决策 7：测试计划（默认 pytest 不联网；live 仅 opt-in）
- 回归（annual 零变化）：
  - 既有 `tests/fund/cli/test_cli_interactive.py` 全量通过（解析/REPL/ChatTurnContract/投资建议拦截/渲染）。
  - 新增守卫：mixed catalog（同基金同年年报+季报）下 annual 解析只含 annual doc id；annual prompt runtime 无「报告类型/报告期」行。
  - 最小验证命令 + Phase 7 验证命令全绿。
- 新增快照用例（FakeLlmClient / 注入 AgentRunResult，no-network）：
  - parser：`--report-type quarterly_report --quarter 5` 拒绝；`--quarter` 配 annual 拒绝；`--period` 配 quarterly 拒绝；缺省期次 = 最新季度。
  - 解析：quarterly 按 fund_code+report_type+year+quarter 命中；semiannual H1；无匹配 → not_found 文案与退出码。
  - 检索：fake LLM 依次 ToolCall(search/read_section) → FinalAnswer，断言工具实际作用在快照 store（document_id 为 `-Q[1-4]-` 段）；read_table 未列出表号仍被拒；快照模式 aggregate 调用 → unavailable（handler=None）。
  - prompt：快照 runtime contribution 含「报告期: …年…季度（Q…）」与「单期快照，非年度报告」；annual 不含。
  - CLI e2e：`run_cli` interactive（快照 catalog fixture + mock 注入）端到端 smoke（对齐 test_cli_interactive.py 既有模式；仓库验收约束：不接受仅 Service/ToolService 层测试）。
- 验证命令：最小验证命令（document_tools + test_minimal_tool_loop + test_cli）+ Phase 7 验证命令 + 新增测试文件；`tests/fund/cli/test_interactive_live_smoke.py` 保持默认 skip。

### 决策 8：风险与失败模式
- catalog 无匹配（fund 无任何快照 / 所选 year 无该期次）：not_found + 明确文案；期次缺省「最新」逻辑必须 fallback 到「该 year 内最大 quarter」，避免无期次时静默选错。
- 旧 session 恢复：schema v1 缺新字段 → `.get()` 默认 annual，行为不变；快照新 session 用新 label 或新 pinned state 覆盖（main.py 恢复路径总是 `with_pinned_state(ps)` 覆写，无跨模式污染）。
- document_id 期次段解析：读取路径不解析 document_id（load_store 从 catalog record 恢复 identity），无新增解析风险；catalog record 异常由既有 `identity_mismatch`/`schema_drift` 分类（persistent_repository.py:240-256），interactive 单文档加载异常沿用 `except Exception: pass` 静默跳过（既有行为，不扩）。
- LLM 把快照当年度数据：runtime 报告期注入 + 硬规则行兜底；仍属 prompt 级防线，行为以工具返回为准（与既有「历史摘要非当前证据」同哲学）。
- aggregate 误调用：handler=None → unavailable fail-closed，回喂后由失败调用跨轮短路收敛（llm_tool_loop.py:574-580）。
- mixed catalog 下 annual 解析修正（决策 2）：仅在污染场景改变行为，属修复；需 plan review 确认接受（裁决点 2）。

## 3. 待总控 / plan review 裁决的决策点

1. **匹配实现位置**：Service 层（extraction.py 扩展 + models.py 新 DTO，与 resolve_by_fund_code / generate_snapshot_report 匹配同源）vs main.py 本地匹配（blast radius 更小但逻辑分散）。推荐 Service 层。
2. **resolve_by_fund_code 加 report_type 过滤**：修复「annual interactive 可能拿到快照 doc」的既有污染（extraction.py:4569-4612 现无过滤，唯一调用方 main.py:1498）。仅在 mixed catalog 场景改变行为；是否接受该修正并入本 slice（推荐接受，与裁决 17 口径一致）。
3. **PinnedState 加字段 vs user_constraints 透传**：推荐 PinnedState 加 3 字段（语义正确、序列化向后兼容、/document 可保留）；user_constraints 承载内部报告上下文会污染用户约束语义（session_models.py:256-296 复用该字段做 goal/facts 存储）。
4. **aggregate 边界实现**：推荐快照模式 `aggregate_handler=None`（复用既有 fail-closed，llm_tool_loop.py:1346-1348）；不推荐改 INTERACTIVE_SCENE_CONFIG.allowed_tools（会波及 annual/ask 行为）。
5. **期次缺省语义**：无 `--quarter` 时 = 所选 year 内最新季度（推荐，与 annual 默认最新一致）；备选 = catalog 全部季度中最新（跨 year）。

## 4. 本阶段 Allowed write set

- 只允许写本文件 `.sisyphus/plans/snapshot-interactive-20260819.md`。
- 禁止改任何代码/测试/其它文档。
