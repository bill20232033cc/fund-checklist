# 2026-08-06 QDII 抽取适配 slice 序列（519696 实测缺口）

> 状态：🟡 S1 待 Mimo review；S2-S4 按序排队。来源：519696 交银环球精选混合(QDII) 端到端报告验收暴露的 4 类抽取 corner case，根因均经代码 + docling 实证。

---

## 0. 背景

519696（主动 QDII）报告已生成（2026-08-06，16 页 PDF），但存在 4 类数据缺口。按影响面排序为 4 个顺序 slice（每 slice 独立走 CIC-lite：计划 → Mimo review → 真源 → DS → controller review）。

## 1. S1：QDII 持仓抽取适配（11C）—— 优先级最高

### 现象

Ch3 持仓集中度表空、风格漂移/持仓集中度指标 0 分；`extract_multi_year_holdings` 2024/2025 均 not_found「未找到可读取的匹配章节」。

### 根因（实证，Mimo review 修正）

- 检索层：`search_document` 只匹配 `section.text`、**不匹配 `section.title`**（docling_store.py:510 `score = section.text.count(query)`）；QDII 持仓章节标题为「8.9 期末按公允价值占基金资产净值比例大小排序的前十名股票投资明细」，正文不含候选词 → equity query（`股票投资明细` / `前十名股票投资明细`，后者已在 candidate_queries，extraction.py:192）均 0 命中。
- 分支层：QDII fallback 分支条件（extraction.py:1408/1462）只覆盖 `index_etf` 或 `index_fund + "QDII" in fund_name`；519696 为**主动 QDII**（`infer_fund_type("交银环球精选混合(QDII)")` = active_fund）→ 不走 QDII 分支。
- 表头层：QDII 表头适配**已实现**（`_holdings_column_indexes` 处理 公司名称→stock_name、证券代码→stock_code、占基金资产净值比例→percentage，extraction.py:6318-6342），且已有 `_extract_qdii_holdings_from_tables` 直接扫描路径（1462 分支内调用）——无需新增适配。

### 修复

- 将 QDII fallback 分支条件扩展为覆盖主动 QDII：`"QDII" in fund_name` 且 fund_type 非 bond/index_feeder 时进入 QDII 分支（`_QDII_HOLDINGS_QUERY` + `_extract_qdii_holdings_from_tables` 直接扫描）。
- 验证 `_extract_qdii_holdings_from_tables` 对 519696-2025 table-61 抽取 10 行（腾讯控股/中国宏桥/中芯国际…）；如直接扫描有缺口再最小适配。
- **不改 search_document public contract**（不做 title 匹配扩展，避免公共契约变更）。
- 验收真值：519696 2024/2025 各 10 行（2025 表61：腾讯控股/中国宏桥/中芯国际 …），集中度/风格漂移指标恢复计算。

### allowed write set（S1）

- `fund_agent/service/extraction.py`（QDII fallback 分支条件扩展 + 直接扫描验证）
- 测试：`tests/fund/service/test_extraction.py`
- 真源：`docs/design.md`、`docs/implementation-control.md`、（AGENTS.md 如需）

### S1 验证与验收

```bash
uv run pytest tests/fund/service/test_extraction.py -k "holdings" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py tests/fund/cli/test_cli.py -q --tb=short
```

实数据：519696 2024/2025 top-10 各 10 行；既有 A 股基金（163415/007466/004393）持仓不回退。

## 2. S2：费率「管理人报酬」措辞 + 托管费路由稳定（10C）

### 根因（实证）

- QDII 年报把管理费表述为「支付基金管理人的**管理人报酬**按前一日基金资产净值 1.80%…」，无「基金管理费」字样 → 多年度/10C 主正则 `基金管理费.{0,80}?(\d+\.\d+%)` 失配；2022 管理费缺失。
- 2022/2023/2024 托管费（0.35%）正文存在但抽取结果只有 2022 有托管费、2023/2024 缺失 → 各年 托管费 查询路由/标题绑定不稳定，需逐年度定位。

### 修复

- `_extract_fee_rates_from_agent_result`（extraction.py:6775 附近，标题块循环）与 `_FEE_RATE_TITLES`（extraction.py:142）：增加「管理人报酬」到标题块边界检测/查找（主路径 `answer.find("基金管理费")` 与回退路径 `answer.find("管理费")` 对「支付基金管理人的管理人报酬…」均返回 -1）；输出字段仍为 `基金管理费`。注意 `_FeeRateExtractionSpec`（extraction.py:442）正则已覆盖 `(?:管理费|管理人报酬)`，但多年度路径不走该 spec，修复以 `_extract_fee_rates_from_agent_result` 为主。
- 排查并修复 2023/2024 托管费查询路由/绑定失败点（fee_queries 已含「基金托管费」extraction.py:1807；逐年度 debug `search_document` → `_matched_disclosure_titles` 绑定）。
- 验收真值：519696 五年管理费/托管费 = 2021 1.80%/0.35%、2022 1.80%/0.35%、2023 1.80%/0.35%、2024 1.80%/0.35%、2025 1.20%/0.20%；既有 163415/007466/004393 费率不回退。

## 3. S3：资产配置 2023 空结果（11D）

### 根因（实证）

- `_extract_allocation_from_agent_result`（extraction.py:6601）对 519696-2023 返回空（`failure=None` 但 `asset_allocation` 0 行，静默空）；2021/2022/2024/2025 正常（3/6/2/5 行）。
- 根因（Mimo review 修正）：**搜索路由错绑 + 缺 asset_allocation fallback**——`search("期末基金资产组合情况")` 命中 table-0059（估值表，caption 恰好含「8.1 期末基金资产组合情况」），真正资产配置表是 table-0060（caption=「金额单位：人民币元」，表头 序号/项目/金额/占基金总资产的比例（%）完全匹配 `_is_asset_allocation_table` 三条件）；`_extract_allocation_from_agent_result` 的 citation 表循环只解析被 cite 的表，全表扫描 fallback 仅覆盖 industry_allocation（6629-6637），**asset_allocation 无全表扫描兜底** → 绑定错表后直接空。

### 修复

- `_extract_allocation_from_agent_result`：在 industry_allocation fallback 之前（或并行）增加 asset_allocation 全表扫描 fallback——遍历 `tool_service.list_tables`，`_is_asset_allocation_table` 命中则 `_parse_asset_allocation_table`，break。表结构无需适配（table-0060 已匹配三条件）。
- 验收：519696 2023 资产配置非空（权益投资等行）；2021/2022/2024/2025 不回退；空结果语义保持（真缺失仍显式处理）。

## 4. S4：持有本基金 9.2/9.4 口径（fund_manager）

### 根因（实证）

- 519696-2025 **无 9.4 基金经理持有区间表**（`_extract_manager_holding` 找不到 → 报告「未披露」基本正确）。
- 但年报有 **9.2 从业人员持有本基金**：table-80「基金管理人所有从业人员持有本基金 7,312.84 份 / 0.01%」，当前完全未利用。

### 修复

- 持有本基金抽取：9.4 区间表不存在时回退 9.2 从业人员整体数据，报告标注口径（「基金经理区间未披露；从业人员整体持有 7,312.84 份（0.01%）」）。
- `FundManagerInfo.holds_fund` docstring（models.py:624）同步更新为回退语义（如「基金经理持有本基金区间（如"10~50万份"）；无 9.4 区间表时回退从业人员整体持有（份额数）」）。
- 验收：519696 报告 Ch3 显示 9.2 数据 + 口径说明；163415（有 9.4 区间表）不回退。

---

## 5. 执行顺序与依赖

S1（持仓）→ S2（费率）→ S3（资产配置）→ S4（持有本基金）。四者互不依赖，按序逐个推进；每个 slice 完成 controller review 后再开下一个。真源文档在每个 slice 的 Mimo review 通过后更新。
