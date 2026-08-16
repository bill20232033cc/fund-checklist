<!-- version: 1.1 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 指标→三表→质量
must_answer:
  - 主要财务指标（本期/上期对比，如适用）
  - 财务三表关键科目（资产负债表/利润表/所有者权益变动表关键项）
  - 标注「未经审计」口径
  - 判断财务质量与可持续性（仅基于披露口径）
must_not_cover:
  - 不把未经审计数据当作已审计数据
  - 不臆造上期（previous）数值
  - 不做未来收益预测
  - 不输出买入/卖出/持有等投资建议
required_output_items:
  - 主要财务指标
  - 财务三表关键科目（含「未经审计」标注）
  - 财务质量判断
data_sources:
  - financial
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: 口径区分
    description: 半年报财务数据未经审计，不得与年报已审计数据混用
item_rules:
  - condition: financial_rows 缺失
    affected_output: 主要财务指标
    degradation_note: 3.1 财务指标表缺失时只声明证据缺口
  - condition: 无上期可比
    affected_output: 本期/上期对比
    degradation_note: 单期快照无上期可比时如实声明，不得臆造上期值
END_CHAPTER_CONTRACT
-->

请基于上述数据表格，写「财务质量」分析。要求：

### 结论要点
- **主要财务指标**（未经审计）：本期 A 类值
- **财务质量判断**：仅基于披露口径，不做过度推断

### 详细情况
- 主要财务指标（本期/上期对比，如适用；单期快照无上期可比时如实声明）
- 财务三表关键科目（资产负债表/利润表/净资产变动表关键项，如抽取到）
- **「未经审计」口径标注**：半年报财务数据未经审计，禁止与年报已审计数据混用

约束：
- 不把未经审计数据当作已审计数据；不臆造上期数值
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字
- 禁止输出买入/卖出/持有等投资建议，禁止预测未来收益
- 证据锚点格式：> 📎 证据：半年报[年份]§3.1 / §6
