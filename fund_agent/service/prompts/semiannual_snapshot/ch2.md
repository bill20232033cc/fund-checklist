<!-- version: 1.1 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 仓位→行业→持仓→变动
must_answer:
  - 当期仓位（权益/债券等资产类别占净值比例）
  - 行业配置分布
  - 全部股票持仓（名称、公允价值、占净值比例）与重大变动
  - 份额变动（期初/申购/赎回/期末）
must_not_cover:
  - 不猜测基金经理的调仓动机
  - 不为缺失持仓编造数值
  - 不输出买入/卖出/持有等投资建议
required_output_items:
  - 资产配置/仓位
  - 行业配置
  - 全部持仓与重大变动
  - 份额变动
data_sources:
  - allocation
  - holdings
  - scale_info
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: missing_data
    description: 数据缺失时明确声明，不得跳过
item_rules:
  - condition: holdings_rows 缺失
    affected_output: 全部持仓与重大变动
    degradation_note: 持仓表缺失时只声明证据缺口
  - condition: allocation_rows 缺失
    affected_output: 资产配置/仓位
    degradation_note: 资产配置表缺失时只声明证据缺口
  - condition: share_change 缺失
    affected_output: 份额变动
    degradation_note: 份额变动缺失时只声明证据缺口
END_CHAPTER_CONTRACT
-->

请基于上述数据表格，写「持仓与资产配置」分析。要求：

### 结论要点
- **仓位**：权益 X% / 债券 X%（标注口径：占净值或占基金资产）
- **集中度**：前十大合计占净值 X%（按数据表加总，标注为推算值）
- **份额变动**：期初→期末

### 详细情况
- 资产配置/仓位表、行业配置表、全部持仓表（名称、公允价值、占净值比例）
- 持仓重大变动（较上期，如有；半年报 §7.4）
- 份额变动（期初/申购/赎回/期末）

约束：
- 不猜测基金经理的调仓动机
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字
- 禁止输出买入/卖出/持有等投资建议
- 证据锚点格式：> 📎 证据：半年报[年份]§7.1 / §7.2 / §7.3 / §7.4 / §9
