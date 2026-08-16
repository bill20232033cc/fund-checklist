# Goal Command（可直接发送）

```
/goal 按 .sisyphus/goals/search-excerpt-boundary-goal-20260815.md 实施「search excerpt 截断边界（候选 C）」slice（来源：F1-F4 收口 review 非阻塞观察 3（docs/reviews/code-review-20260815-122324.md）：search excerpt 截断在数字中间（如 787,727,）时，快照份额回退正则 `\d[\d,，.]*` 会捕获不完整值；此为 `_search_texts` excerpt 截断的通用问题，非 F2 引入。实证：截断发生在 docling_store.py `_excerpt`（995-1006）/`_search_excerpt`（1034-1052）的 240 字符窗口任意字符处截断（DEFAULT_SEARCH_EXCERPT_CHARS=240，constants.py:86）；`_search_texts`（snapshot_extraction.py:745-751）是被动消费 excerpt，无截断标记无法自行补全，故根因修复在 excerpt 生成端。口径已定（D1-D4 推荐，用户 2026-08-15 授权继续开发）：D1 修复层 = docling_store excerpt 窗口边界对齐，`_search_texts`/snapshot_extraction.py 不改（自动受益）；D2 对齐语义 = 截断点两侧均为数字串字符（`0123456789,，.`）才算「数字串内部」→ end 只向后扩展至数字串结束、start 只向前回退至数字串起点（命中区间永不缩短）；D3 测试 = 新文件纯函数 + 集成（构造数值跨窗口边缘的真实场景，可证伪旧行为）+ 回归；D4 非目标 = 不改 `_bounded`（list_sections preview/read_section 截断行为不变）、不做跨页/跨节数字拼接（页断切数字恢复超出本 slice）、不改 SearchResult 结构 / search_document 签名 / failure taxonomy / CLI / prompts / registry、不改 AGENTS.md、不 commit / 不 push）。只走 CIC-lite implement -> tests -> diff review。实施内容：① fund_agent/fund/document_tools/docling_store.py——新增纯函数 `_align_start_no_number_cut(text, start)` / `_align_end_no_number_cut(text, end)`（数字串字符集 `0123456789,，.`；仅当截断点前一字符与当前字符均属该集合才判定「数字串内部」，避免吞孤立标点）；`_excerpt` 窗口 start/end 与 `_search_excerpt`（归一化路径）begin/end 均做对齐；`_excerpt`/`_search_excerpt` 的 no-hit fallback（`_bounded(text, max_chars)[0]`）改为 `text[:_align_end_no_number_cut(text, max_chars)]`（仅 excerpt fallback 对齐，不动 `_bounded` 本身）；② tests/fund/document_tools/test_search_excerpt_boundary.py（新文件）——纯函数：`_excerpt` 右边界切在 `787,727,758.47` 中间 → 返回 excerpt 末尾为完整数字（旧行为 `...787,727,` 可证伪）；左边界切在数字串中间 → 开头为完整数字；`_search_excerpt` 空白归一化路径同两态；no-hit fallback 右边界对齐；窗口恰在数字串结束处不扩展；query 命中区间保留；集成：构造长 section 文本使 240 字符窗口左/右边缘切入数字串 → `search_document` 返回 excerpt 不含半截数字 → 快照 `_extract_share_change` 文本回退路径捕获完整值；③ 回归：test_docling_store.py / test_bm25f_scorer.py / test_snapshot_extraction.py / test_snapshot_report_assembly.py 全量保持通过。allowed write set 严格按本 goal（4 文件：fund_agent/fund/document_tools/docling_store.py、tests/fund/document_tools/test_search_excerpt_boundary.py、docs/design.md、docs/implementation-control.md）。测试：uv run pytest tests/fund/document_tools/test_search_excerpt_boundary.py -q --tb=short；uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_bm25f_scorer.py -q --tb=short；uv run pytest tests/fund/service/test_snapshot_extraction.py tests/fund/service/test_snapshot_report_assembly.py -q --tb=short；AGENTS.md 最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short；全部通过 + git diff --check 干净。文档同步：docs/design.md §6.25 追加第 22 项裁决（search excerpt 窗口截断对齐数字串边界：截断点落在数字串内部时 end 后扩至数字串结束、start 前退至数字串起点，命中区间保留；`_bounded` 与跨页拼接不纳入）、docs/implementation-control.md 追加本 slice 记录。输出交接报告（changed files / diff 摘要 / 实际测试命令与输出 / 旧行为可证伪说明）。
```

## Goal

- goal_id: `search-excerpt-boundary-20260815`
- 目标：修复 search excerpt 窗口截断切断数字串的问题——`docling_store._excerpt`/`_search_excerpt` 的截断边界对齐到数字串边界（截断点落在数字串内部时 end 后扩至数字串结束、start 前退至数字串起点，命中区间永不缩短），使所有 search excerpt 消费者（含快照 `_search_texts` 回退正则）不再捕获半截数值。
- 前置条件：候选 B slice 已收口（diff review ACCEPTED，未 commit）；工作区基线 = 快照大任务 + A/B 未收口改动。
- 设计来源：本文件（内嵌实证 + 口径 D1-D4）；候选 C 定义见 `docs/reviews/code-review-20260815-122324.md` 非阻塞观察 3 与 `.sisyphus/plans/audit-pipeline-tightening-slice-20260815.md` 非目标节。
- 日期：2026-08-15

## 实证（2026-08-15，代码核验）

1. `docling_store.py:995-1006` `_excerpt`：窗口 `start = max(index - half_window, 0)`、`end = min(start + max_chars, len(text))`，在任意字符处截断，可切断数字串。
2. `docling_store.py:1034-1052` `_search_excerpt`：空白归一化路径同样在 `begin + max_chars` 处任意截断。
3. `constants.py:86`：`DEFAULT_SEARCH_EXCERPT_CHARS = 240`（窗口有界）。
4. `snapshot_extraction.py:745-751` `_search_texts`：被动消费 `SearchResult.excerpt`，无截断标记，无法自行补全 → 根因修复必须在 excerpt 生成端。
5. `snapshot_extraction.py:553-556` 快照份额回退正则 `\d[\d,，.]*(?:\.\d+)?`：excerpt 末尾半截数字（如 `787,727,`）会被捕获为完整值。
6. 边界澄清：F2 场景数值紧跟 query（`期初基金份额总额` 后 ≤8 字符），窗口中心化后通常不被切；真正被切的是「数值跨窗口左/右边缘」与「section 文本本身被页断切在数字中间」两类。本 slice 修复前者（通用不变量）；后者需跨节拼接，超出本 slice（列为非目标，如未来有真实数据可另立）。

## 口径（D1-D4，推荐，用户已授权继续开发）

- **D1 修复层**：`docling_store.py` excerpt 窗口边界对齐（根因，所有 search 消费者受益）；`_search_texts`/`snapshot_extraction.py` 不改。
- **D2 对齐语义**：数字串字符集 `0123456789,，.`；仅当截断点前一字符与当前字符均属该集合才判定「数字串内部」（避免吞孤立标点）；end 只向后扩展、start 只向前回退（命中区间永不缩短）。
- **D3 测试**：新测试文件纯函数（左右边界 + 归一化路径 + fallback + 不扩展边界 + 命中保留）+ 集成（构造数值跨窗口边缘场景，`search_document` excerpt 不含半截数字 + 快照回退捕获完整值，可证伪旧行为）。
- **D4 非目标**：不改 `_bounded`（list_sections preview / read_section 截断行为不变）；不做跨页/跨节数字拼接；不改 `SearchResult` 结构 / `search_document` 签名 / failure taxonomy / CLI / prompts / registry；不改 AGENTS.md。

## 实施内容

- `fund_agent/fund/document_tools/docling_store.py`：
  - 新增纯函数 `_align_start_no_number_cut(text, start) -> int`、`_align_end_no_number_cut(text, end) -> int`。
  - `_excerpt`：窗口 start/end 对齐；no-hit fallback 改为 `text[:_align_end_no_number_cut(text, max_chars)]`。
  - `_search_excerpt`：归一化路径 begin/end 对齐。
- `tests/fund/document_tools/test_search_excerpt_boundary.py`（新文件）：见口径 D3。
- `docs/design.md` §6.25 第 22 项、`docs/implementation-control.md` slice 记录。

## 非目标（明确）

- 不改 `_bounded` 本身（list_sections preview / read_section 行为不变）。
- 不做跨页/跨节数字拼接恢复（页断切数字）。
- 不改 `SearchResult` 结构 / `search_document` 签名 / failure taxonomy / public tool 契约 / CLI / prompts / registry。
- 不改 `snapshot_extraction.py`（`_search_texts` 无改动，端到端受益由集成测试证明）。
- 不改 `AGENTS.md`。
- 不 commit / 不 push。

## allowed write set（DS 执行边界，禁止越界）

- `fund_agent/fund/document_tools/docling_store.py`
- `tests/fund/document_tools/test_search_excerpt_boundary.py`
- `docs/design.md`
- `docs/implementation-control.md`

（goal/diff-review artifact 由 controller / reviewer 产出，不在 DS write set。）

## 验证命令

```bash
uv run pytest tests/fund/document_tools/test_search_excerpt_boundary.py -q --tb=short
uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_bm25f_scorer.py -q --tb=short
uv run pytest tests/fund/service/test_snapshot_extraction.py tests/fund/service/test_snapshot_report_assembly.py -q --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

## 文档同步（用户要求：更新真源文档）

1. `docs/design.md` §6.25 追加第 22 项裁决：search excerpt 窗口截断对齐数字串边界（截断点落在数字串内部时 end 后扩至数字串结束、start 前退至数字串起点，命中区间保留；`_bounded` 与跨页拼接不纳入）。
2. `docs/implementation-control.md` 追加本 slice 记录。
