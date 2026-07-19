<!-- version: 3.0 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 数据→行为→差距
must_answer:
  - 投资者实际收益数据是否可用
  - 产品收益概况（净值增长率 vs 基准）
must_not_cover:
  - 不做市场走势预测
  - 不给投资建议
required_output_items:
  - 投资者实际收益数据可用性声明
  - 产品收益概况
data_sources:
  - performance
item_rules:
  - condition: investor_return_data 缺失（2026年之前年报）
    affected_output: 行为损益分析
    degradation_note: 本章节所需的投资者实际收益数据为2026年度报告新规要求披露的字段，当前报告年份不包含上述数据
END_CHAPTER_CONTRACT
-->

请基于上述数据，写一段「投资者获得感」分析。

<when_missing investor_return_data>
本章节所需的投资者实际收益数据（盈利投资者占比、加权平均投资者收益率）为 2026 年度报告新规要求披露的字段。当前报告年份不包含上述数据，仅展示基金产品收益。
</when_missing>

要求：
- 如果有投资者实际收益数据，分析行为损益 = 投资者实际收益 - 基金产品收益
- 分析份额变动趋势
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字

{{ must_answer_schema }}
