<!-- version: 1.1 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 仓位→行业→持仓→变动
must_answer:
  - 当期仓位（权益/债券等资产类别占净值比例）
  - 行业配置分布
  - 前十大股票持仓（名称、公允价值、占净值比例）
  - 份额变动（期初/申购/赎回/期末）
  - 季报缺失项声明：全部持仓/财务三表/托管人报告不在季报披露范围
must_not_cover:
  - 不从年报补充季报缺失项（全部持仓/财务三表/托管人报告）
  - 不猜测基金经理的调仓动机
  - 不输出买入/卖出/持有等投资建议
required_output_items:
  - 资产配置/仓位
  - 行业配置
  - 前十大持仓
  - 份额变动
  - 季报缺失项声明
data_sources:
  - allocation
  - holdings
  - scale_info
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: missing_data
    description: 季报未披露项必须 fail-closed 声明，不从年报补
item_rules:
  - condition: holdings_rows 缺失
    affected_output: 前十大持仓
    degradation_note: 前十持仓表缺失时只声明证据缺口
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
- 资产配置/仓位表、行业配置表、前十大持仓表（名称、公允价值、占净值比例）
- 份额变动（期初/申购/赎回/期末）
- **季报缺失项声明**（fail-closed）：全部持仓明细（仅披露前十大）、财务三表、托管人报告不在季报披露范围，不从年报补充

约束：
- 不猜测基金经理的调仓动机
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字
- 禁止输出买入/卖出/持有等投资建议
- 证据锚点格式：> 📎 证据：季报[年份]Q[n]§5.1 / §5.2 / §5.3.1 / §6
