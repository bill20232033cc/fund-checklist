# Slice 14A Review Prompt — Template-Aligned Report Generation

## 你的角色

你是一个严格的 code reviewer。请审查以下变更，找出 correctness、stability、maintainability 问题。

**重要规则**：对每个 P0/P1 findings，必须先 `grep -n` 确认代码存在再评论。不要捏造不存在的代码。

## 项目背景

基金年报阅读工具（fund-checklist）。核心链路：
```
PDF → Docling → 7 reading tools → 数据抽取 → 报告生成
```

本次变更（Slice 14A）：
1. 新增基金经理数据抽取（`FundManagerInfo` + `_extract_fund_manager`）
2. 新增规模明细数据抽取（`ScaleInfo` + `_extract_scale_info`）
3. 按 `docs/fund-analysis-template-draft.md` 重做 8 章 prompt + 数据表格
4. 用现有数据组装 Ch2 R=A+B-C

## 硬边界（违反即 P0）

1. **禁止投资建议**：不得输出"买入""卖出""推荐"。
2. **禁止数字 hallucination**：LLM 不得输出数据中不存在的数字。
3. **所有数据必须可溯源到年报**：数据表格由程序从数据 dict 生成。
4. **禁止直接消费 raw PDF / raw Docling JSON / 本地路径**。
5. **换手率保持禁止**：AGENTS.md 明确禁止换手率抽取。

## 核心变更

### 1. 新增 DTO

`fund_agent/service/reading_service.py`:

```python
@dataclass(frozen=True)
class FundManagerInfo:
    """基金经理信息。"""
    name: str
    tenure_start: str
    years_of_service: str
    investment_strategy: str
    holds_fund: str

@dataclass(frozen=True)
class ScaleInfo:
    """基金规模信息。"""
    total_shares_a: str
    total_shares_c: str
    individual_investor_ratio: str
    management_holds: str
```

### 2. 新增抽取方法

```python
def _extract_fund_manager(self, fund_code, annual_docs, work_dir) -> FundManagerInfo | None:
    """从最新年报§4提取基金经理信息。"""
    # 搜索"基金经理" → 找 table-0014 → 提取姓名/任职日期/从业年限
    # 搜索"投资策略和运作分析" → 提取§4.4.1文本
    # 搜索 tables → 找"基金经理持有" → 提取持有区间

def _extract_scale_info(self, fund_code, annual_docs, work_dir) -> ScaleInfo | None:
    """从年报§10提取规模信息（多年回退）。"""
    # 搜索"开放式基金份额变动" → 找 table-0093 → 提取 A/C 类份额
    # 2025 无数据时回退到 2024
```

### 3. 模板对齐的 8 章

`_generate_data_table()` 重写，每章对应模板要求：

| 章节 | 标题 | 数据来源 |
|------|------|---------|
| Ch0 | 投资要点概览 | 业绩+费率+经理 |
| Ch1 | 这只基金到底是什么产品 | 基本信息+经理策略 |
| Ch2 | R=A+B-C 收益归因 | 业绩+费率（R-B-C） |
| Ch3 | 基金经理画像与言行一致性 | 经理信息+持仓 |
| Ch4 | 投资者获得感 | 跳过（占位） |
| Ch5 | 当前阶段与关键变化 | 规模+资产配置 |
| Ch6 | 核心风险与否决项 | 持仓集中度+业绩波动 |
| Ch7 | 是否值得持有——最终判断 | 业绩汇总 |

`_LLM_ANALYSIS_PROMPTS` 重写，每章有模板要求的 must_answer 指令。

### 4. 动态年份

`GenerateReportRequest.years` 默认为空元组。`generate_report()` 不指定 years 时自动从 catalog 查找该基金所有可用年份。

### 5. 业绩抽取修复

`_extract_report_performance` 改为逐年直接抽取，跳过失败年份，绕过 `aggregate_multi_year_annual_performance` 的 3 年最低要求。

## 测试

`tests/fund/service/test_llm_chapter_generation.py` — 10 个测试：

```python
test_generate_data_table_ch2_performance()    # Ch2 包含业绩+费率
test_generate_data_table_ch3_holdings()        # Ch3 包含持仓
test_generate_data_table_ch5_scale()           # Ch5 包含资产配置
test_contains_non_year_numbers_detects()       # hallucination 检测
test_contains_non_year_numbers_allows_years()  # 年份不触发
test_contains_non_year_numbers_allows_text()   # 纯文本不触发
test_llm_chapter_generator_success()           # LLM 正常
test_llm_chapter_generator_hallucination_rejected()  # 数字被拒绝
test_llm_chapter_generator_failure_returns_none()    # 失败返回 None
test_generate_report_with_llm_uses_data_tables()     # 端到端
test_generate_report_llm_fallback_to_template()      # 回退模板
```

## 已知问题（不在 review 范围）

1. Ch4 投资者获得感：跳过（数据抽取难度大）
2. Ch6 核心风险：模板模式下只有静态风险声明
3. 规模数据 2025 年 Docling 未提取，回退到 2024
4. 管理人持有比例：Docling 未提取为表格

## 请输出

### P0（必须修复）
问题 + 文件:行号 + 修复建议（必须先 grep 确认代码存在）

### P1（建议修复）
问题 + 文件:行号 + 修复建议

### P2（可选优化）
问题 + 建议

### 总结
一段话概括代码质量和主要风险。
