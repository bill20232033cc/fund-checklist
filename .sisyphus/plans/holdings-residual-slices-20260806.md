# 2026-08-06 遗留 slice 设计（持仓抽取残差 + 交互小修）

> 状态：🟡 计划待 Mimo review。来源：QDII slice 序列（519696）收口后记录在 `docs/implementation-control.md`「QDII 序列收尾状态」的遗留项，加上 interactive 质量修复 slice 的已知偏差。所有 slice 独立走 CIC-lite：计划 → Mimo review → 真源 → DS → controller review。

---

## 0. 背景与遗留清单

QDII 序列 S1-S4 已收口并 commit（`d92a9e1`），以下遗留项未处理：

| 编号 | 遗留项 | 类别 | 来源记录 |
| --- | --- | --- | --- |
| R1 | 004393 持仓 0 行（首个 table citation 命中行业配置表 table-0079） | 代码修复 | implementation-control.md QDII 收尾状态 |
| R2 | 519696-2025 持仓第 6 名跨页断裂（代码/占比丢失） | 代码修复 | 同上 |
| R3 | 519696-2023 持仓表头截断（「证券代」「占基」仍为空） | 代码修复 | 同上 |
| R4 | interactive key_facts 未落盘（`AgentRunResult`/`Turn` 无槽位） | 可选小修 | interactive 质量修复 slice 已知偏差 |
| R5 | 007466 interactive opt-in live e2e 未跑 | 验证任务（非设计） | interactive 质量修复 slice 遗留 |

R1-R3 是持仓抽取不完备的主体；R4/R5 非持仓。R5 无设计需求，仅需显式授权后按既有 live e2e 流程运行，本设计只登记执行条件。

---

## 1. R1：004393 持仓 0 行（search/citation 路由回归）

### 现象

`extract_multi_year_holdings` / 报告 Ch3 对 004393 返回 0 行；已 A/B 实证为非 QDII 序列引入，来源是前序未提交区 search/citation 变化导致首个 table citation 命中行业配置表 `table-0079`。

### 已知根因（部分定位）

- `_extract_holdings_from_agent_result`（extraction.py:6326）只消费 `result.citations` 中首个能解析出列索引的表，命中非持仓表（行业配置表）后无表级鉴别。
- 行业配置表表头（行业类别/占净值比例）不满足 `_holdings_column_indexes` 的 `stock_name`+`percentage` 要求，会走相邻表头查找；但相邻 5 表范围内未必有 A 股持仓表头，或解析出列后数据行全为空。
- 具体为何 004393 的 citation 首位变成 `table-0079`（行业配置表）尚未完全定位——需先复现确认再定修复。

### 定位步骤（实现前必须完成）

1. 复现：`-k holdings` 中 004393 用例，打印 004393 各年 `AgentRunResult.citations` 的 table_ref 序列与首表表头。
2. 对比 `d92a9e1` 与上一可工作提交（`c4e5e71`）之间 `search_document` / citation 行为差异，确认 004393 路由偏移的触发点。
3. 用 Docling JSON 核对 `table-0079` 实际表头与 section，确认是否为行业配置表。

### 修复方向（按优先级）

1. 表级鉴别：在 `_extract_holdings_from_agent_result` 首表解析前增加 `_is_holdings_table` 校验（要求 `stock_code` 或 `quantity` 特征列之一 + `stock_name` + `percentage`，行业配置表无股票特征列），不满足则跳过该 citation 继续遍历，而非 break。
2. 若跳过机制仍不能命中（citation 列表里根本没有持仓表），对 A 股基金补一个与 QDII 对称的直接扫描 fallback（`list_tables` + 表头特征扫描），复用 `_extract_holdings_continuations` 的跨页合并。
3. 修复后 004393 各年 top-10 与历史真值比对（参照 `.sisyphus/plans/fee-holdings-fix-20260802.md` 留下的 A 股回归真值）。

### 验收真值

- 004393 持仓非空（2021-2025 各年 top-10 行数与历史真值一致）；行业配置表不再被当作持仓表消费。
- 既有 A 股基金（163415/007466）与 QDII（519696）持仓不回退。

### allowed write set（R1）

- `fund_agent/service/extraction.py`（表级鉴别 + 必要 fallback）
- 测试：`tests/fund/service/test_extraction.py`
- 真源：`docs/design.md`、`docs/implementation-control.md`

### R1 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "holdings" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py tests/fund/cli/test_cli.py -q --tb=short
```

---

## 2. R2：519696-2025 持仓第 6 名跨页断裂（代码/占比丢失）

### 现象

519696-2025 持仓第 6 名跨页断裂，代码/占比丢失；当前实现按最小适配跳过碎片行，报告 Ch3 出现残缺行。

### 已知根因（部分定位）

- `_extract_qdii_table_with_continuations`（extraction.py:6127）已实现「主表 + 同 section 续表」合并，`_extract_qdii_continuation_rows`（6244）会跳过碎片行。
- 第 6 名仍断裂，说明续表未被 `_find_qdii_header_continuation` / `_extract_qdii_continuation_rows` 命中。候选原因：续表与主表不同 section、列数不一致、或续表首行被误判为表头碎片/数据行。

### 定位步骤（实现前必须完成）

1. 用 Docling JSON 列出 519696-2025 持仓表所在 section 的全部 table：主表（table-61）与续表各自的 table_ref、section_ref、page_no、column_count。
2. 打印 `_extract_qdii_table_with_continuations` 对主表实际走到的分支（是否进入 continuation；`_find_qdii_header_continuation` 哪个条件失配）。

### 修复方向

1. 若为 section/列数判定问题：放宽 `_find_qdii_header_continuation` 的候选范围（同 section 同列数 → 相邻 section 或允许列数差 1 的碎片对齐），或复用 `_extract_holdings_continuations` 的 A 股跨页判定逻辑。
2. 若为碎片行误跳过：`_extract_qdii_continuation_rows` 对「首列序号 + 后列含代码/名称」的行不得跳过；仅在首列非序号且全行无代码/名称特征时才算碎片。
3. 补一条「第 6 名跨页」回归测试（固定 fixture 或最小表结构模拟），确保碎片行补齐后 rank 连续。

### 验收真值

- 519696-2025 持仓 10 行完整，rank 1-10 连续；第 6 名代码/占比非空。
- 519696-2024 不回退；A 股基金跨页合并（若存在）不回退。

### allowed write set（R2）

- `fund_agent/service/extraction.py`（continuation 判定）
- 测试：`tests/fund/service/test_extraction.py`
- 真源：`docs/design.md`、`docs/implementation-control.md`

### R2 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "holdings or qdii" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py tests/fund/cli/test_cli.py -q --tb=short
```

---

## 3. R3：519696-2023 持仓表头截断（「证券代」「占基」）

### 现象

519696-2023 持仓表头在 Docling 输出中被截断为「证券代」「占基（金资产净值比例）」，`_holdings_column_indexes` 对完整关键词失配 → `stock_code`/`percentage` 缺失 → 返回 None → 持仓为空。

### 已知根因（已定位）

- `_holdings_column_indexes`（extraction.py:6564）只做完整子串匹配：「证券代码」「占基金资产净值比例」「占比」；截断表头「证券代」「占基」全部失配。
- 与 2024 年「占基 金资 / 产净值比例（%）」不同，2023 的截断没有续表碎片可补（`_merge_qdii_header_fragments` 无从生效），需按截断前缀识别或列位置推断。

### 修复方向

1. 截断前缀识别：`_holdings_column_indexes` 对 `percentage` 增加「占基」「占基金」等前缀匹配，对 `stock_code` 增加「证券代」前缀匹配；匹配时校验该列其余单元格含数字（防误绑）。
2. 列位置推断兜底：QDII 表头固定为（序号/证券代码/证券名称/数量/公允价值/占基金资产净值比例）结构时，若前缀匹配仍失败，按已知列序推断 `stock_code`/`percentage` 索引。
3. 补 519696-2023 表头截断回归测试。

### 验收真值

- 519696-2023 持仓非空（与 2025 表头正常年份的行数/前几名真值对齐）；2021/2022/2024/2025 不回退。
- 行业配置表、估值表等非持仓表不得因前缀放宽被误判（需负例测试）。

### allowed write set（R3）

- `fund_agent/service/extraction.py`（`_holdings_column_indexes` + 必要兜底）
- 测试：`tests/fund/service/test_extraction.py`
- 真源：`docs/design.md`、`docs/implementation-control.md`

### R3 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "holdings or qdii or header" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py tests/fund/cli/test_cli.py -q --tb=short
```

---

## 4. R4：interactive key_facts 落盘（可选小修）

### 现象与已知偏差

interactive 质量修复 slice 已记录：`key_facts` 仅解析保留在 `FinalAnswer` 内，未随 `AgentRunResult`/`Turn` 持久化到 session（citations 已落盘）。展示链路不受影响。

### 修复方向

1. `session_models.py`：`AgentRunResult`/`Turn` 增加 `key_facts` 槽位（list[str] 或 dict），`tool_loop.py` 终答解析时写入。
2. 兼容：旧 session 反序列化缺失该字段时默认空列表，不破坏既有会话恢复。
3. 补序列化/恢复测试。

### 验收真值

- interactive 一轮问答后 session 中可读回 `key_facts`；旧 session（无该字段）恢复不回退。

### allowed write set（R4）

- `fund_agent/agent/llm_tool_loop.py`、`fund_agent/service/session_models.py`
- 测试：`tests/fund/agent/test_llm_tool_loop.py`、`tests/fund/host/test_session_store.py`
- 真源：`docs/implementation-control.md`

### R4 验证命令

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/host/test_session_store.py -q --tb=short
```

---

## 5. R5：007466 interactive opt-in live e2e（验证任务，非设计）

- 无设计需求：按 interactive 质量修复 slice 的 live e2e 流程执行（004393 复跑口径，Q1 命中 9.4、Q3/Q4 ≤200 字无原文粘贴、Q4 调用 <12）。
- 前置条件：用户显式授权 live 运行（默认 pytest 不得联网、不得读真实 API key）。
- 失败处理：live 结果只作为验收证据，不驱动 production adapter 变更。

---

## 6. 执行顺序与依赖

- R1 → R2 → R3 互不依赖，但同改 `extraction.py` 持仓路径，建议按 R1（路由回归）→ R2（跨页）→ R3（表头）顺序逐个推进，每个 slice 完成 controller review 后开下一个，避免同一函数多次并发改动。
- R4 独立于 R1-R3，可并行或最后做。
- R5 需用户授权，与 R1-R4 无依赖。
- 真源文档在每个 slice 的 Mimo review 通过后更新；全部收口后同步 `docs/implementation-control.md` 遗留状态。
