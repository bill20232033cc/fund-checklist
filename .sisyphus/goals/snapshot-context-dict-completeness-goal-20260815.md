# Goal Command（可直接发送）

```
/goal 按 .sisyphus/goals/snapshot-context-dict-completeness-goal-20260815.md 实施「快照 to_context_dict 完整性（候选 B）」slice（来源：F1-F4 收口 review 非阻塞观察 #1 + 候选 B 裁决；候选 B = SnapshotReportData.to_context_dict() 缺失 7 字段序列化：fund_code/fund_name/report_year/template_id/quarter/period/citations。现状实证：extraction.py:2779 唯一消费点，身份字段由 service 层显式 kwargs 传入 generator（extraction.py:2805/2823/2831 + snapshot_generator.py:179-184），不依赖 dict，故当前非阻塞（review 实证 test_snapshot_report_semiannual_period_propagated 通过）；风险为未来消费者从 dict 读身份/citations 会缺字段）。只走 CIC-lite implement -> tests -> diff review。实施内容：① fund_agent/service/snapshot_extraction.py to_context_dict()（91-118 行）补齐 7 个缺失字段——身份字段原样序列化（fund_code/fund_name/report_year/template_id/quarter/period），citations 序列化为 [dict(c) for c in self.citations]（与既有 rows 序列化风格一致），既有 15 个 key 不变（纯增量、向后兼容）；② tests/fund/service/test_snapshot_extraction.py 新增单元测试——构造含非默认值（quarter=3/period="H2"/citations 非空）的 SnapshotReportData，断言 set(to_context_dict().keys()) == {f.name for f in dataclasses.fields(SnapshotReportData)}（可证伪：未来新增字段不同步序列化即红），并逐 key 断言值与 dataclass 一致；③ 回归：既有快照测试全量保持通过（证明补字段不改消费者行为）。allowed write set 严格按本 goal（4 文件：fund_agent/service/snapshot_extraction.py、tests/fund/service/test_snapshot_extraction.py、docs/design.md、docs/implementation-control.md），禁止改消费者传参契约（身份字段仍走显式 kwargs，不从 dict 读）、禁止把 citations 接入 generator 渲染、禁止改 failure taxonomy / public tool 契约 / CLI / prompts / registry、禁止做候选 C（_search_texts 截断边界）、不改 AGENTS.md（非验收规则变化）、不 commit / 不 push。测试：uv run pytest tests/fund/service/test_snapshot_extraction.py -q --tb=short；uv run pytest tests/fund/service/test_snapshot_report_assembly.py tests/fund/service/test_snapshot_template.py -q --tb=short；AGENTS.md 最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short；全部通过 + git diff --check 干净。文档同步：docs/design.md §6.25 追加裁决（to_context_dict 序列化契约 = dataclass 字段全集，新增字段必须同步序列化，dataclasses.fields 全集断言为回归防线）、docs/implementation-control.md 追加本 slice 记录。输出交接报告（changed files / diff 摘要 / 实际测试命令与输出 / 旧行为可证伪说明）。
```

## Goal

- goal_id: `snapshot-context-dict-completeness-20260815`
- 目标：补全 `SnapshotReportData.to_context_dict()` 序列化——dict 输出覆盖 dataclass 字段全集（含身份字段 `fund_code`/`fund_name`/`report_year`/`template_id`/`quarter`/`period` 与 `citations`），并以 `dataclasses.fields` 全集断言作为回归防线；纯增量、不改消费者行为。
- 前置条件：工作区既有未收口改动（F1-F4 snapshot fix + audit-pipeline-tightening A slice）先收口/确认基线后实施，避免与未提交改动交错。
- 设计来源：本文件（内嵌实证 + 口径 D1-D3）；候选 B 定义见 `.sisyphus/plans/audit-pipeline-tightening-slice-20260815.md` 非目标节与 `docs/reviews/code-review-20260815-122324.md` 非阻塞观察 #1。
- 日期：2026-08-15

## 实证（2026-08-15，代码核验）

1. `snapshot_extraction.py:64-89`：`SnapshotReportData` 共 22 个字段（frozen dataclass）。
2. `snapshot_extraction.py:91-118`：`to_context_dict()` 仅序列化 15 个 key，缺失 7 个——`fund_code`(68)、`fund_name`(69)、`report_year`(70)、`template_id`(71)、`quarter`(72)、`period`(73)、`citations`(89)。
3. `extraction.py:2779`：唯一消费点 `snapshot_context = data.to_context_dict()`；身份字段由 service 层显式 kwargs 传入 generator（`extraction.py:2805/2823/2831`），generator 侧 `snapshot_generator.py:179-184` 也从 kwargs 读——**当前无消费者依赖 dict 中的身份字段**。
4. `citations`（89 行）声明但 `extract_snapshot_data`（128-206 行）从未填充，恒为 `()`；同时未序列化。
5. review 实证：`docs/reviews/code-review-20260815-122324.md:73`（非阻塞观察 #1）确认 `test_snapshot_report_semiannual_period_propagated` 端到端通过，period 走 kwargs 不透 dict——非阻塞但存在未来缺字段风险。

## 口径（D1-D3，本设计默认推荐，供用户拍板）

- **D1**：补齐范围？推荐：**补全集 7 字段**（含恒空的 `citations`——完整性契约 = 字段全集；dict 必须忠实序列化 dataclass，不因当前无填充/无消费者省略）。
- **D2**：是否改消费者？推荐：**不改**。身份字段继续走显式 kwargs 契约（`generate_snapshot_report` 传参不动），不从 dict 读取——避免行为变更与双通道漂移；本 slice 只补序列化 + 测试防线。
- **D3**：回归防线形式？推荐：**测试断言**（`dataclasses.fields` 全集 == dict keys，未来新增字段不同步序列化即红）；不加运行时校验（固定结构 dataclass 无需运行时自检，防过度设计）。

## 实施内容

- `fund_agent/service/snapshot_extraction.py` `to_context_dict()`（91-118 行）：
  - 新增 `fund_code` / `fund_name` / `report_year` / `template_id` / `quarter` / `period`：原样序列化。
  - 新增 `citations`：`[dict(c) for c in self.citations]`（与既有 `holdings_rows` 等序列化风格一致）。
  - 既有 15 个 key 不变；纯增量、向后兼容。
- `tests/fund/service/test_snapshot_extraction.py` 新增单元测试：
  - 构造含非默认值（`quarter=3` / `period="H2"` / 非空 `citations`）的 `SnapshotReportData`。
  - 断言 `set(to_context_dict().keys()) == {f.name for f in dataclasses.fields(SnapshotReportData)}`（可证伪）。
  - 逐 key 断言值与 dataclass 一致（含身份字段类型、citations 已 dict 化）。

## 非目标（明确）

- 不改消费者传参契约：`generate_snapshot_report` 的身份字段仍走显式 kwargs，不从 `to_context_dict()` 读取。
- 不把 `citations` 接入 generator 渲染 / prompt 注入（当前无此需求）。
- 不改 failure taxonomy / public tool 契约 / CLI / prompts / registry。
- 不做候选 C（`_search_texts` 截断边界）。
- 不改 `AGENTS.md`（非验收规则变化）。
- 不 commit / 不 push。

## allowed write set（DS 执行边界，禁止越界）

- `fund_agent/service/snapshot_extraction.py`
- `tests/fund/service/test_snapshot_extraction.py`
- `docs/design.md`
- `docs/implementation-control.md`

（goal/plan/diff-review artifact 由 controller / reviewer 产出，不在 DS write set。）

## 验证命令

```bash
uv run pytest tests/fund/service/test_snapshot_extraction.py -q --tb=short
uv run pytest tests/fund/service/test_snapshot_report_assembly.py tests/fund/service/test_snapshot_template.py -q --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

## 文档同步（用户要求：更新真源文档）

1. `docs/design.md` §6.25 追加裁决：`to_context_dict()` 序列化契约 = dataclass 字段全集（含身份字段与 `citations`）；新增字段必须同步序列化；`dataclasses.fields` 全集断言为回归防线。
2. `docs/implementation-control.md` 追加本 slice 记录。
