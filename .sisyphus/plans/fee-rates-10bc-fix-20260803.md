# 2026-08-03 fee_rates 10B/10C 链路修复规格

> 状态：🟡 待 Mimo review。来源：`test_real_pdf_controlled_profiles_apply_disclosure_target_contract` 预置失败（004393-2024 真实 PDF），三层根因全部经代码+数据实证。

---

## 1. 问题现象

`service.extract_fee_rates`（10C DTO 路径）对 004393-2024 返回：

```text
ToolFailure(code=NOT_FOUND, message='fee_rates citation 不完整')
```

测试断言目标（既有，不修改）：管理费 1.20%、托管费 0.20%、销售服务费 A=不收取、C=0.40%，每条带 section citation；routing_trace 为「费用→failure + 基金管理费/基金托管费/销售服务费→success」。

## 2. 根因（三层，全部实证）

### 根因一：路由聚合按披露标题去重，丢弃了含销售服务费正文的结果

实证链：

1. `_run_with_query_candidates`（extraction.py:3907-3960）对 `_requires_all_target_titles` 契约按「披露标题集合」去重 `matched_results`：`if any(title not in matched_titles for title in disclosure_titles)` 才 append。
2. 004393-2024 三个候选 query（基金管理费/基金托管费/销售服务费）各自的 answer 都覆盖全部三个标题（确定性 Agent 的费用回答包含三大节标题），因此只有第一个结果（基金管理费 query）被保留，后两个被去重丢弃。
3. 但「基金管理费」「基金托管费」query 的 answer（len=765）**不含销售服务费费率正文**，只有「相关表格: 7.4.10.2.3 销售服务费」引用 + 托管费金额表残留；销售服务费正文（「本基金A类基金份额不收取销售服务费，C类基 金份额的销售服务费按前一日C类基金资产净值的0.40%年费率计提」）只在「销售服务费」query 的 answer（len=1344）里。
4. 聚合 citations 因此缺 section-0398 的 SECTION locator（只有 table-0052 的 TABLE locator）→ `_fee_rate_section_citations`（要求 ≥3 个 `LocatorKind.SECTION`）抛 NOT_FOUND。

### 根因二：`_fee_rate_segments` 裸 find 标题，被「相关表格:」引用干扰

实证链：

- answer 中「相关表格:\n7.4.10.2.3 销售服务费」行含裸标题文本；`answer.find("销售服务费")` 命中该引用而非正文标题，销售服务费 segment 被切成托管费金额表内容（len=110，无费率正文）。
- 修复根因一（拼接三个 answer）后仍存在：任何拼接顺序下都有一个「相关表格:」引用出现在正文标题之前。

### 根因三：简单拼接聚合导致正文重复 → 字段无法唯一抽取

实证链（模拟聚合 + 剥离表格块 + citation 合并后实测）：

- 三个 query answer 都含管理费/托管费正文（销售服务费 query 的 answer 含全部三节）→ 拼接后正文重复。
- 管理费 segment matches=2（1 个正文 1.20% + 1 个变更历史句「由 1.50%调整为 1.20%」；变更句被 `_change_re` 排除后剩 1 个，恰好唯一）。
- 托管费 segment matches=4（2 个正文 0.20% + 2 个变更句；排除后剩 2 个）→ `fee_rates 字段无法唯一抽取`。
- 销售服务费 A/C 各 matches=1，可唯一抽取。

## 3. 修复设计

### F-R1：路由层支持「聚合全部 success 结果」语义

- `fund_agent/service/models.py` `_DisclosureLocatorContract` 新增字段 `aggregate_all_matches: bool = False`。
- `fund_agent/service/extraction.py` fee_rates 契约（DISCLOSURE_LOCATOR_CONTRACT_REGISTRY 内）设 `aggregate_all_matches=True`。
- `_run_with_query_candidates` 的 `_requires_all_target_titles` 分支：`aggregate_all_matches=True` 时所有 success 结果都 append 到 `matched_results`（不做标题去重）；其余契约（holdings/performance）保持现状，避免同一表格被两个 candidate query 重复聚合。

### F-R2：fee_rates 专用聚合（标题块去重）

新增 `_aggregate_fee_rate_results(results)`：

- answer：对每个结果先剥离「相关表格:」块（金额表，从「相关表格:」到下一个 `\n\n`），按标题（基金管理费/基金托管费/销售服务费）定位**首个完整块**，按固定顺序拼接，标题块去重（消除正文重复）。
- citations：按 `(locator_kind, section_ref, table_ref)` 去重合并（三个 query 的 citations 都保留，覆盖三节）。
- tool_trace：合并。

在 fee_rates 聚合点用 `_aggregate_fee_rate_results` 替换 `_aggregate_agent_results`（或作为其前置处理）。

### F-R3：`_fee_rate_section_citations` section 覆盖按 section_ref 统计

- 不再只统计 `LocatorKind.SECTION`：TABLE locator 携带的 `section_ref` 也计入覆盖（table-0052 的 `section_ref=section-0398` 已验证可定位到销售服务费节）。
- 按 `section_ref` 去重后要求覆盖 ≥3 个不同 section；返回 dict 仍按固定标题顺序 zip。

### 测试

- 既有 real-pdf 测试断言不变（1.20/0.20/不收取/0.40 + routing_trace 四步 + citations 非空）。
- 新增单元测试：
  - `_aggregate_fee_rate_results`：构造 3 个标题重叠的 answer，断言标题块去重、正文不重复、citations 按 locator 去重合并。
  - `_fee_rate_section_citations`：TABLE locator 的 section_ref 计入覆盖；不足 3 节仍抛 NOT_FOUND。
  - 聚合后四字段唯一抽取（管理费/托管费各 1 个正文匹配）。

## 4. 修复范围与验收

### allowed write set

- `fund_agent/service/models.py`（契约字段，默认 False 不破坏既有契约）
- `fund_agent/service/extraction.py`（路由聚合 + `_aggregate_fee_rate_results` + `_fee_rate_segments`/`_fee_rate_section_citations`）
- `tests/fund/service/test_extraction.py`
- 真源文档：`docs/design.md`、`docs/implementation-control.md`（AGENTS.md 仅当分层/规则表述变化时）

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py::test_real_pdf_controlled_profiles_apply_disclosure_target_contract -x -q --tb=short
uv run pytest tests/fund/service/test_extraction.py -k "fee_rate" -q --tb=short
```

### 验收口径

- 上述命令全绿；`git diff --check` 干净。
- `extract_fee_rates` 对 004393-2024 返回 4 条字段（1.20% / 0.20% / 不收取 / 0.40%），每条带 section citation（section-0379 / section-0390 / section-0398）。
- routing_trace 保持「费用 failure + 三 query success」四步。

### non-goals

- 不改 `_extract_fee_rates_from_store`（多年度报告路径，F1 已修，不受此失败影响）。
- 不改 holdings/performance 路由语义（`aggregate_all_matches` 默认 False）。
- 不引入新 provider / LLM；不 commit / push。
