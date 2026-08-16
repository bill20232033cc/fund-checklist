<!-- version: 1.1 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 动作→经理→利益
must_answer:
  - 报告期内的运作分析（管理人报告 §4.4 当期市场+操作）
  - 基金经理基本信息与当期动作
  - 固有资金投资本基金情况（如有披露）
  - 不猜测基金经理动机
must_not_cover:
  - 不猜测基金经理的动机或意图
  - 不把运作分析原文当作观点
  - 不输出买入/卖出/持有等投资建议
required_output_items:
  - 管理人运作分析要点
  - 基金经理信息
  - 固有资金投资情况（如披露）
data_sources:
  - fund_manager
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
item_rules:
  - condition: operation_analysis 缺失
    affected_output: 管理人运作分析要点
    degradation_note: 季报未披露运作分析时只声明证据缺口
  - condition: fund_manager 缺失
    affected_output: 基金经理信息
    degradation_note: 经理信息缺失时只声明证据缺口，不得编造
  - condition: own_funds 未披露
    affected_output: 固有资金投资情况
    degradation_note: 未披露固有资金投资时按 fail-closed 声明未披露
END_CHAPTER_CONTRACT
-->

请基于上述数据表格，写「管理人动作」分析。要求：

### 结论要点
- **运作分析要点**（据 §4.4）：复述当期市场判断与操作，引用时注明据报告
- **基金经理**：姓名、任职时间
- **固有资金**：投资情况（如披露；未披露时声明）

### 详细情况
- 运作分析复述（标注来源，不做观点化、不推断动机）
- 基金经理信息（姓名、任职时间等；报告期内变动如实呈现）
- 固有资金投资本基金情况（如披露）

约束：
- 不猜测基金经理的动机或意图，不做性格或人品的主观评价
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字
- 禁止输出买入/卖出/持有等投资建议
- 证据锚点格式：> 📎 证据：季报[年份]Q[n]§4.4 / §4.1 / §7
