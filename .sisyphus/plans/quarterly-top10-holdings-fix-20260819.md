# interactive 季报「前十大持仓」查询失败修复 — 设计方案（2026-08-19）

- 阶段：仅设计。本 slice 只产出本 plan artifact；不写代码、不改测试/文档、不 commit、不 push。
- 口径：CIC-lite；plan review ACCEPTED 后才进入 implement -> tests -> diff review。
- 复现目录：`.fund_checklist_005680_snapshot`（005680 Q2 2026 季报，doc_id `005680-2026-Q2-quarterly_report-c04170add3a3cf98`）。

## 1. 根因确认（已本地复核，与总控证据一致）

### 1.1 主根因：store 表格归属只按页码（docling_store.py）

`_section_ref_for_page`（`fund_agent/fund/document_tools/docling_store.py:837-848`）把表格归属到「页码不大于表格页码的最后一个 section header」（按 texts 下标顺序遍历，完全不看纵向位置）。同页多章节时该启发式失效；唯一调用点在 `_parse_tables`（docling_store.py:473）。

用真实 store 实测（`uv run python` 构建 `DoclingDocumentStore` 于 005680 Q2 docling.json）：

- `table-0010`（page 9，prov t=502.97，BOTTOMLEFT）：被归属 `section-0100`（5.5 前五名债券）；正确应为 `section-0097`（5.3.1 前十名股票投资明细）。page 9 纵向顺序（BOTTOMLEFT：t 越大越靠上）：texts/94 `5.2.2`(t=611.97) → texts/96 `5.3`(553.86) → texts/97 `5.3.1`(520.62) → table-0010(502.97) → texts/98 `5.4`(273.99) → texts/100 `5.5`(215.77)。
- `table-0009`（page 9 顶部 t=771.0，5.2.1 行业分类续表，行 M-S+合计）：被归属 `section-0100`；正确应为 `section-0069`（5.2.1，header 在 page 8）。
- 同源附带错误：`table-0007`（page 8 t=646.4，5.1 报告期末基金资产组合情况表）被归属 `section-0069`（5.2.1）；正确应为 `section-0067`（5.1）。

后果链：`list_tables(within_section_ref=section-0097)` 返回空（section-0097 名下 0 张表）→ `holdings_top10` 表锚点 `_resolve_holdings_top10_anchor_table_ref`（`fund_agent/service/extraction.py:5341`，经 `_anchor_section_refs` extraction.py:5261 定位后 list_tables 为空）解析失败 fail-open 不注入 → 会话 `sessions/b697a2f3e1a244a286abcd142dc04361.json` 只输出章节标题，拿不到持仓行。

### 1.2 次级根因：`holdings_top10` alias 未覆盖「前十大持哪些」

`_route_plan_for_query`（extraction.py:5174-5181）alias 匹配为子串包含；`holdings_top10` aliases=`("前十大持仓", "重仓股", "持仓明细")`（extraction.py:231）。query「前十大持哪些」不含任一 alias → `profile=None`，无候选词、无锚点注入。而 `search_document` 为整串子串匹配（`_section_search_candidates` / `_table_search_candidates` 用去空白后的 query 连续子串计数），「前十大重仓股股票投资」归一化后不是任何 section/table 文本的连续子串 → 0 命中 → 会话 `sessions/bd714968950345599a5d10504b0b6cc2.json` 终答「未找到相关数据」，全程未 read_table。

结论：两个根因均与总控证据一致；二者需同时修复才能闭环两个复现会话。

## 2. 修复点设计

### 2.1 store 表格归属：页码 + 纵向位置（主修复）

语义改为「归属到阅读顺序上最近的前序 section header」：

- 候选集：
  - `page < 表格页` 的所有 header（同页内按纵向位置取最靠下者，即阅读顺序最后者）；
  - 同页且 `header.reading_top < 表格.reading_top`（header 在表格上方）的 header。
- 选取：`(page, reading_top)` 最大者。`reading_top` 为归一化「页内向下坐标」（越大越靠下）：`coord_origin == "BOTTOMLEFT"` 时 `page_height - bbox.t`，`TOPLEFT` 时 `bbox.t`；取 `prov[0].bbox.coord_origin`。
- 兜底：表格无 prov / 无 bbox / 无法算 reading_top / 无候选时，回退现有 page-only 逻辑（docling_store.py:837-848 原语义，行为不变）。

改动点（全部在 `fund_agent/fund/document_tools/docling_store.py`）：

1. `DoclingDocumentStore.__init__`：从 `self._raw["pages"]`（`dict[str(page_no)] -> {"size": {"height": ...}}`）解析 `page_heights: dict[int, float]`，传入 `_parse_sections` / `_parse_tables`；pages 缺失/无 height 时该页回退 page-only。
2. `_parse_sections`：给内部模型 `_ParsedSection` 增加字段 `reading_top: float | None`（私有字段，不进入 `SectionSummary` / `Locator` 公共契约）。
3. `_parse_tables`：用表格自身 reading_top + sections.reading_top 调用新归属函数，替换 `_section_ref_for_page` 唯一调用点（docling_store.py:473）；建议新增 `_section_ref_for_position(sections, page_no, reading_top)`，原 `_section_ref_for_page` 保留为 fallback。
4. 不动：`Locator.bbox` 契约（`_first_bbox` docling_store.py:702-716 只保留 l/t/r/b 数值，coord_origin 不进 bbox）；不新增 failure code；不动 `_is_continuation_of` 合并算法本身。

跨页续表合并（`_is_continuation_of` docling_store.py:934-957）影响：合并前提是两表 section_ref 相同。归属修正后，同签名跨页续表（header 为上一页最后 header 的常见形态）会正确进入合并分支。005680 具体案例：table-0009 与 table-0008 列数签名不一致（table-0008 4 列 vs table-0009 33 列展平），即使 section 相同也不合并——归属正确、保持独立表，符合「续表可溯源到 5.2.1」即可，无回归。

### 2.2 `holdings_top10` alias 扩展（次级修复，含边界）

- 建议：aliases 扩展为 `("前十大持仓", "重仓股", "持仓明细", "前十大持")`。覆盖「前十大持哪些 / 前十大持有什么」等 surface 变体；「前十大持仓有哪些」已由既有 alias 覆盖，不重复。
- 边界（明确接受，写进测试）：
  - alias 匹配算法不变（子串包含）。「前十大持有人 / 前十大股东」类 query 也会命中 holdings_top10（registry 无持有人 profile，且本 slice 禁止新增 profile）。后果有界：候选词注入仅是 prompt 提示，LLM 终答仍以工具返回为准；该歧义列为已知限制，若出现真实误路由，另开专项（non-goal）。
  - 不新增 `candidate_queries` / `acceptable_title_family` / `anchor_title_family`；不触 `extraction_allowed`；alias 不增加候选数，`_MAX_QUERY_CANDIDATES` 校验（extraction.py:5190-5222）不受影响。
  - `_route_plan_for_query` 的「首个命中 contract 返回」语义不变。
- 备选（不推荐）：只做 store 修复不加 alias → 会话 bd71…（「前十大持哪些」）仍 profile=None、无候选注入、整串检索仍 0 命中，问题不闭环。

## 3. 影响面

- 同页多章节归属修正：对 005680 Q2 全 13 张表模拟，11 张归属变化，逐张核对均为修正（p2 基金产品概况/2.1、p3 3.1/3.2.1/C 类净值表、p8 table-0007→5.1、p9 table-0009→5.2.1 / table-0010→5.3.1 等）。table-0007 修正同时修复 `asset_allocation`（期末基金资产组合情况）对该文档的关联。
- 跨页续表：005680 table-0009 归属修正到 5.2.1（不合并，见 2.1）；同签名跨页续表受益于 section 一致后按既有逻辑合并。
- 3.2.1（performance_returns）：004393-2025 模拟 57 张表归属变化，但 Fix C 锚点表 table-0009 归属不变 → 锚点断言（test_chat_service.py:862/878/901）不受影响；同页其他表归属变化会改变 search/list_tables 候选集合，须回归。
- 5.5（前五名债券）：table-0009/0010 移出 5.5 后 5.5 名下只剩自身表；`_BOND_HOLDINGS_QUERY` 相关抽取直接 read_table，不受归属影响，且归属更准。
- 2.1（主要会计数据）：005680 p3 table-0001 由 running header（section-0026）修正为 section-0018（3.1 主要财务指标）。
- 年报 fixture 目录/TOC 区（007466 p5-7、004393 p5-6、519696 p5-7）存在大量归属修正，均属同源 heuristics 修正；这些 fixture 上的抽取/锚点测试是回归重点（见 §4）。
- 现有测试：007466 锚点 table-0087 / table-0098（test_chat_service.py:842/817）模拟归属不变；extraction 真实 fixture（163415 前十大、519696 QDII 跨页分裂表）、e2e regression、cli interactive 相关测试全部纳入回归。

## 4. 测试计划

### 新增用例

1. `tests/fund/document_tools/test_docling_store.py`（合成 docling JSON，沿用现有 `_write_docling_json` 风格）：
   - 同页多章节：表格位于 5.3.1 之后、5.4 之前 → 归属 5.3.1；
   - 页顶续表归属上一页最后 header（BOTTOMLEFT）；
   - `coord_origin=TOPLEFT` 归一化等价；
   - 缺 bbox / 缺 page / pages 缺 height → 回退 page-only；
   - 同 section 同签名跨页续表仍合并（`_is_continuation_of` 不回归）。
2. 真实 fixture 集成（005680 Q2 docling.json，沿用 `.fund_e2e_*` fixture 断言风格）：`table-0010 → section-0097`、`table-0009 → section-0069`、`table-0007 → section-0067`；`list_tables(within_section_ref=section-0097)` 含 table-0010；`search('前十名股票投资明细')` 命中后可 `read_table(table-0010)` 得到 10 行持仓。
3. `tests/fund/service/test_extraction.py`：
   - `_route_plan_for_query('前十大持哪些')` → `holdings_top10`，候选 = (`前十大持哪些`, `股票投资明细`, `前十名股票投资明细`)；
   - registry 断言更新（extraction.py:988 aliases 元组）；
   - 「前十大持有人」命中 holdings_top10 的边界断言（记录已知歧义）。
4. `tests/fund/service/test_chat_service.py`：005680 fixture 上 query「前十大持哪些」→ retrieval contribution 含 `候选表锚点: table-0010（序号、股票名称、公允价值）`。

### 回归范围（必须全绿）

- 最小验证命令（AGENTS.md 固定）：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`
- Phase 7 验证命令（interactive/chat/anchor）：`uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short`
- 抽取回归：`uv run pytest tests/fund/service/test_extraction.py -k "holdings or qdii or real_fixture or performance or route" -v --tb=short`
- e2e：`uv run pytest tests/fund/test_e2e_regression.py tests/fund/test_e2e_holdings_regression.py -q --tb=short`
- 复现验证（手工，interactive）：对 005680 Q2 复跑「前十大持哪些」「前十大持仓是什么」，确认终答返回持仓行（非 live LLM 时可先核 routing contribution 含候选词 + 锚点 table-0010，再核工具序列 search→list_tables(section-0097)→read_table(table-0010)）。

## 5. Non-goals

- 不改 LLM prompt / runner 收敛逻辑（空搜索换词、read_table 表号一致性校验、终答守卫、≤200 字约束等一律不动）。
- 不新增 profile（禁止新增 持有人 profile）；不改 alias 匹配算法。
- 不改 `candidate_queries` / `acceptable_title_family` / `anchor_title_family` / `extraction_allowed` / registry 结构。
- 不改 `Locator.bbox` / 公共工具契约；不新增 failure code。
- 不做 Docling/PDF 重新转换；不改 `_is_continuation_of` / `_merge_locator` 合并算法本身。
- 不处理「前十大持有人」专项路由（已知限制，另开专项）。
- 本 slice 不 commit、不 push、不跑 live LLM smoke（默认 no-network）。

## 6. Allowed write set（实现阶段参考；本次设计阶段不执行）

- `fund_agent/fund/document_tools/docling_store.py`
- `fund_agent/service/extraction.py`（仅 holdings_top10 aliases 元组一行）
- `tests/fund/document_tools/test_docling_store.py`
- `tests/fund/service/test_extraction.py`
- `tests/fund/service/test_chat_service.py`
- 如需真实 fixture：新增对 `.fund_checklist_005680_snapshot/docling_json/005680-2026-Q2-quarterly_report-c04170add3a3cf98/*.docling.json` 的只读引用（跟随 `.fund_e2e_*` fixture 惯例，仅 docling.json）。
