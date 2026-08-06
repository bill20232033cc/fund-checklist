# 2026-08-02 163415 报告缺陷诊断与修复规格（费率 + 持仓）

> 状态：🟡 待 Mimo review。来源：`generate 163415 2025`（.fund_e2e_163415）报告缺陷排查，全部根因经代码/数据实证。

---

## 1. 问题现象

1. 持仓：2023 与 2025 年前十大持仓抽取为空（2021/2022/2024 正常，含 10 行完整数据）。
2. 费率：成本数据(C) 表所有年份费率均等于该年 LLM 答案中最后一个百分比（2025 三项 0.60%，2022 两项 0.25%，2023/2024 两项 0.20%）；综合费率 1.80% 因此错误。

## 2. 根因一：持仓（数据存在，路由+解析失败）

### 实证链

1. 数据存在：2025 store `table-0076` 首行 = 序号/股票代码/股票名称/数量（股）/公允价值（元）/占基金资产净值比例（%），宁德时代 6.86%…；2023 store `table-0075` = 海尔智家 6.46%…。两份 top-10 表 caption 均为垃圾页眉 **「第 58 页 共 70 页」**。
2. `_NO_SEMANTIC_CAPTION_RE`（docling_store.py:728）只匹配「第\s*N\s*页」+ 可选单位噪声，**不匹配「共 N 页」**——「第 58 页 共 70 页」整体匹配失败 → `_is_semantic_caption` 返回 True → 垃圾 caption 被保留（WIP 的 caption 回填未生效）。
3. `search("股票投资明细")` 实测排序：rank1 section 文本、rank3 `table-0074`（caption 命中）、rank4 `table-0075`；top-10 表（0076）不在前 4。
4. Agent 路由引用了 `table-0074`（行业分类表，行如 `['4','贵金属投资','-','-']`）→ `_holdings_column_indexes` 表头匹配失败（extraction.py:1235 附近）。
5. header-fallback 只搜编号更小的表（`if cand_num >= current_num or current_num - cand_num > 5: continue`），top-10 表编号更大（0075/0076）→ 找不到表头 → 0 行。

### 修复（F2）

- `docling_store.py`：`_NO_SEMANTIC_CAPTION_RE` 的页码模式扩展为 `第\s*[...]+\s*页(?:\s*共\s*[...]+\s*页)?`，使「第 N 页 共 M 页」判定为非语义 → caption 回填 section 标题（含「股票投资明细」→ 可被 search 命中）。
- `extraction.py`：`_extract_holdings_from_agent_result` 的 header-fallback 放宽为同 section 内双向查找（[current-5, current+5]），且优先在**同 section** 内找含 股票名称+占基金资产净值比例 表头的表；仍找不到才放弃。
- 测试：现成 2023/2025 docling JSON 做 fixture，断言持仓抽取非空（≥10 行）；caption 噪声正则单测（含 共 N 页、纯单位噪声、正常 caption 三态）。

## 3. 根因二：费率（贪婪正则抓句末百分比）

### 实证链

1. 年报真值：2025 管理费 1.20%/托管费 0.20%/销售服务费C类 0.60%（A类不收取）；2022 1.50%/0.25%；2023 于 7-10 起由 1.50%/0.25% 调低至 1.20%/0.20%；2024 1.20%/0.20%。
2. `_extract_fee_rates_from_agent_result`（extraction.py:5772）内正则 `基金管理费.*(\d+\.\d+%)` / `基金托管费.*(\d+\.\d+%)`（extraction.py:5781-5782）的 `.*` **贪婪**，捕获答案最后一个百分比（注：extraction.py:389 的 `_FeeRateExtractionSpec` 用 `[^。\n]*?` 非贪婪，不是 bug 源）。
3. 模拟（答案按年报原文结构含 1.20%/0.20%/0.60%）三项全部提取为 0.60%——与报告 2025 取值完全一致；2022/2023/2024 同理取到句末值。
4. `signal_scoring.score_fee_rate` 对提取项求和（0.60+0.60+0.60=1.80%）→ 输入错导致综合费率与费率评分（5/25）、费率变动分析全部错误。正确口径：A类 1.40%（1.20+0.20）、C类 2.00%（再加 0.60）。

### 修复（F1）

- `extraction.py`：管理费/托管费/销售服务费正则改**有界非贪婪**：`基金管理费.{0,80}?(\d+\.\d+%)`，或锚定句式「按前一日基金资产净值(\d+\.\d+%)的年费率计提」；销售服务费 A/C 分支同改有界。
- 测试：多百分比答案逐项取对（1.20/0.20/0.60 → 管理费 1.20%、托管费 0.20%、销售C 0.60%）；「A类不收取」保持；既有费率测试不回退。

## 4. 修复范围与验收

### allowed write set（F1+F2）

- `fund_agent/service/extraction.py`（费率正则 + holdings header-fallback）
- `fund_agent/fund/document_tools/docling_store.py`（caption 噪声正则；保留既有 WIP 改动，只增量修改）
- 测试：`tests/fund/service/test_extraction.py`、`tests/fund/document_tools/test_docling_store.py`
- 文档：`fund_agent/fund/README.md`、`fund_agent/agent/README.md`（如边界描述变化）

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py tests/fund/document_tools/test_docling_store.py -q --tb=short
```

### 验收口径

- 重跑 `uv run fund-checklist generate --fund-code 163415 --fund-name "兴全商业模式混合(LOF)" --year 2025 --work-dir .fund_e2e_163415 --llm --format markdown`：
  - 2023/2025 前十大持仓非空（股票名称/占比完整，与 docling 原文一致）。
  - 2025 费率 = 管理费 1.20%、托管费 0.20%、销售服务费C类 0.60%（A类不收取）；2022/2023/2024 与年报真值一致。
  - 综合费率按 A/C 分份额口径展示（A类 1.40%、C类 2.00%）——若报告模板仍用单值加总，则该口径调整另走设计裁决，本 slice 只保证输入正确。
- 既有测试不回退；`git diff --check` 干净。

## 5. 非目标

- 不重跑 Docling 转换；不改 `_holdings_column_indexes` 的列语义（股票名称→股票代码 禁止映射等）。
- 不改 signal_scoring 的综合费率口径（A/C 分份额为独立设计决策）。

---

## 6. F3 基金经理持有区间抽取缺失（2026-08-02 追加）

### 现象

2025 年报 9.4 节披露「本基金基金经理持有本开放式基金 A类份额数量区间 >100 万份、C类 0、合计 >100」，但报告 Ch4 显示「持有本基金：未披露」。

### 根因（实证）

store `table-0090`（section-0663，9.4 节）共 7 行：row 0 表头、row 1-3 高级管理人员段、row 4-6 基金经理段。基金经理段行结构：

```text
['项目', '份额级别', '持有基金份额总量的数量区间（万份）']
['本基金基金经理持有 本开放式基金', '兴全商业模式混合（LOF） A', '>100']
['', '兴全商业模式混合（LOF） C', '0']
['', '合计', '>100']
```

`_extract_manager_info` 的 holds_fund 抽取（extraction.py:2612-2624）：行条件（含「基金经理持有」+「开放式基金」）命中，但**取值条件只认单元格内含「~」或「万份」**；本表区间值为 `>100`，单位「（万份）」在表头 → `holds_fund` 保持空 → 回退「未披露」。

### 修复（F3）

- 区间取值支持 `>N` / `<N` / `>=N` / `<=N` / `N~M` / `N-M` / 纯数字 形态，单位从表头「（万份）」继承，输出如「A类>100万份」；单元格文本先做空白归一化（Docling 单元格内可能含空格）。
- 优先取「基金经理持有」类目下 A 类份额行（无 A 行则取非零行，再退合计行）；高级管理人员类目不混入。
- 输出格式建议：`A类>100万份（C类0）` 或与既有格式兼容的最小变更；`FundManagerInfo.holds_fund` 语义不变（字符串）。
- 测试：真实 2025 docling JSON fixture 断言 `holds_fund` 非空且含 `>100` 与 `万份`；旧形态（`10~50万份`）不回退；无 9.4 节文档保持「未披露」。

### allowed write set（F3）

- `fund_agent/service/extraction.py`（holds_fund 抽取逻辑）
- 测试：`tests/fund/service/test_extraction.py`
- 文档：`fund_agent/agent/README.md`（条件项）

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -q --tb=short
```

### 验收口径

- 单测：9.4 fixture 断言通过；既有测试不回退（含真实 PDF smoke 的 1 条预置失败，与 F3 无关）。
- 端到端（可选，controller 手动）：重跑 generate 后 Ch4「持有本基金」显示实际区间（如「A类>100万份」），不再「未披露」。
