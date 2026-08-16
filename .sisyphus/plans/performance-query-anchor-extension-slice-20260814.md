# performance 类查询受控表锚点注入收口 slice（第4个任务，2026-08-14 设计）

## 任务界定（口径）

- 第4个任务 = `docs/research/dayu-agent-r-research-20260810.md` §5 落地建议 4「performance 类查询表锚点注入（Fix C，D1/D2 决策）」。
- 建议 1-3（BM25F 排序增强 / VERBOSE 日志分级 / Tool Trace operator 对齐）已完成并收口（commit `2c00677`）。
- Fix C（2026-08-11）已为 `performance_returns` 单 profile 实现 3.2.1 表锚点（exact-title search → list_tables → 表头签名「阶段/份额净值增长率/业绩比较基准收益率」→ A 类标题优先，004393-2025 命中 table-0009）。
- 本 slice 收口 performance 类查询族的受控路由与锚点覆盖，使 净值增长率 / 基准收益率 / 超额收益 / 净值表现 四类词面全部进入受控路径。

## 实证（2026-08-14，代码 + 真实 fixture）

1. 路由缺口（`_route_plan_for_query` 实测，未做任何代码修改）：
   - 「近一年净值增长率」「业绩比较基准收益率是多少」→ `performance_returns` ✅（基准收益率已在 alias 内）。
   - 「超额收益率是多少」「超额收益」→ `None` ❌（不受控，LLM 自由选表，与 R5 Q1/Q3 高误命中同模式）。
   - 「净值表现如何」→ `None` ❌（alias 仅有「基金净值表现」，缺「净值表现」词面）。
2. 数据落点（005680-2025 真实 Docling JSON 核验）：
   - 超额收益列（①－③ / R-B）与净值增长率、业绩比较基准收益率同表（3.2.1 业绩表）→ performance_returns 既有表锚点可直接覆盖，**无需新解析器**。
   - 规模/份额数据在 8.2 正文 note（无 caption 表），且 search 首命中不可靠（「期末基金资产净值」首命中 section-0031/table-0009 非规模节；报告规模节为 section-0630）→ 表锚点不适用，需独立「节锚点」机制，**排后续独立 slice，本 slice 不做**。

## 决策（D1/D2 更新）

- D1（保持确定性）：不做 LLM 侧意图分类（研究文档「非默认建议」），沿用 Service 层确定性 profile routing + 受控锚点注入。
- D2（范围，证据驱动）：performance 类查询族 = 净值增长率、业绩比较基准收益率、超额收益、净值表现。净值增长率/基准收益率已受控；本 slice 补齐 超额收益（超额收益率/超额）与 净值表现 词面。规模/份额仍属 backlog（正文 note 数据，节锚点机制另立 slice）；基准收益率不新增独立 profile（alias 已覆盖查询层）。

## 设计

1. registry 扩展（`fund_agent/service/extraction.py` `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY`）：
   - `performance_returns` aliases 增加 `"超额收益"`、`"超额收益率"`、`"超额"`、`"净值表现"`。
   - 匹配机制为子串包含（`any(alias in query ...)`）；「超额」具特异性，不与 fee_rates / manager_holdings / holdings_top10 现有 alias 冲突；registry alias 全局唯一校验（`_validated_locator_contracts`）通过。
   - candidate_queries / acceptable_title_family / anchor_title_family / requires_table_citation 全部不变，复用既有 3.2.1 表锚点与候选词路径。
2. 锚点注入（`fund_agent/service/chat_service.py`）：`_ANCHOR_PROFILE_NAMES` 不变（`performance_returns` 已在列）；超额/净值表现 query 路由到 `performance_returns` 后自动获得既有「候选表锚点」注入，零新增解析器。
3. 边界：不改 `_resolve_anchor_table_ref`；不改 runner 表号一致性校验；不改 10F/10G/11A 契约；不新增 failure taxonomy / profile / CLI 参数 / 依赖。

## 测试计划

1. `tests/fund/service/test_extraction.py`：
   - 正例：`_route_plan_for_query("超额收益是多少")`、`("超额收益率")`、`("超额表现")`、`("净值表现如何")` → profile_name == `performance_returns`（注：「超额表现」经「超额」子串 alias 命中，非「超额收益/超额收益率」；子串匹配语义下预期成立）。
   - 负例：`("基金规模")`、`("持仓明细")`、`("管理费")`、`("前十大持仓")` 不误命中 `performance_returns`。
   - registry 校验：aliases 扩展后 `_validated_locator_contracts()` 不抛 `schema_drift`。
2. `tests/fund/service/test_chat_service.py`：
   - retrieval contribution 用例：超额收益 query → 含「已识别披露主题: performance_returns」+ 既有「候选表锚点」注入（复用既有 fake tool service 锚点 fixture）。
3. `tests/fund/test_e2e_regression.py`：
   - 真实 fixture smoke（`.fund_e2e_004393` / `.fund_checklist_005680` 缺失则 skip，沿用既有模式）：超额收益 query 经既有锚点解析路径成功。
4. 验证命令：
   - `uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_chat_service.py -k "route or anchor or performance or query" -q --tb=short`
   - AGENTS.md 最小验证集：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short`
   - `git diff --check`

## 非目标（明确）

- 不做 LLM 侧意图分类。
- 不做规模/份额受控 profile（正文 note 数据、节锚点机制另立 slice；本 slice 不新增节锚点机制）。
- 不新增 failure taxonomy / public tool / 10F/10G/11A 契约变更 / CLI 参数 / 依赖。
- 不 commit / 不 push（实施阶段约束）。

## allowed write set

修改：
- `fund_agent/service/extraction.py`（仅 registry aliases 扩展）
- `tests/fund/service/test_extraction.py`
- `tests/fund/service/test_chat_service.py`
- `tests/fund/test_e2e_regression.py`
- `docs/design.md`（受控表锚点段落补 performance 类词面范围）
- `docs/implementation-control.md`（本 slice 记录）
- `tests/README.md`（如验证命令变化，可选）

禁止修改：AGENTS.md / `fund_agent/agent/` / `fund_agent/fund/` / `fund_agent/host/` / `fund_agent/cli/` / `fund_agent/service/models.py` / scene.md / FailureCode / DocumentToolError / 新依赖 / commit / push。
