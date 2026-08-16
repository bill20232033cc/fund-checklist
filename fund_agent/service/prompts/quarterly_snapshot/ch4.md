<!-- version: 1.1 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 风险→分级→跟踪
must_answer:
  - 当期核心风险是什么（结构性 vs 阶段性）
  - 最关键的风险（1-2个）及依据
  - 风险严重程度分级（高/中/低）+ 依据
  - 单一投资者持有比例 ≥20% 提示（如触发）
  - 持有人数/净值预警说明（如披露）
  - 季报缺失项声明（fail-closed，不从年报补）
must_not_cover:
  - 不罗列所有可能风险
  - 不做风险发生概率的定量预测
  - 不把数据缺失本身包装为基金风险或创建整体可评估性风险参与分级
  - 不输出买入/卖出/持有等投资建议
required_output_items:
  - 最关键的风险
  - 风险严重程度分级
  - 单一投资者 ≥20% 提示
  - 预警说明（如披露）
  - 下一轮先验证什么
data_sources:
  - performance
  - holdings
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: missing_data
    description: 季报未披露项必须 fail-closed 声明，不从年报补
item_rules:
  - condition: 数据不足以定性风险
    affected_output: 最关键的风险
    degradation_note: 数据缺失导致无法定性时明确声明评估受限，不得包装成风险
  - condition: single_investor_20pct 未触发或未披露
    affected_output: 单一投资者 ≥20% 提示
    degradation_note: 按 fail-closed 声明未触发或未披露
END_CHAPTER_CONTRACT
-->

请基于上述数据表格，写「风险与跟踪」分析。要求：

### 结论要点
- **最关键的风险**：格式「最关键的风险是 [名称]」（1-2 个，注明结构性/阶段性）
- **风险分级**：高 / 中 / 低 + 依据
- **单一投资者 ≥20%**：如触发引用披露原文；未触发/未披露则声明

### 详细情况
- 风险识别与分级（基于披露事实；数据不足以定性时明确声明评估受限，不得把数据缺失包装为基金风险）
- 单一投资者持有比例 ≥20% 提示、持有人数/净值预警说明（如披露）
- **季报缺失项声明**（fail-closed）：全部持仓/财务三表/托管人报告/持有人结构/换手率/市场展望不在季报披露范围，不从年报补
- 包含标准风险声明（过往业绩不代表未来表现）

约束：
- 不罗列所有可能风险；不做风险发生概率的定量预测
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字
- 禁止输出买入/卖出/持有等投资建议，禁止预测未来收益
- 证据锚点格式：> 📎 证据：季报[年份]Q[n]§8.1 / §4.6
