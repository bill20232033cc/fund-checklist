<!-- version: 1.0 -->
请基于上述数据，写一段「投资者获得感」分析。

<when_missing investor_return_data>
本章节所需的投资者实际收益数据（盈利投资者占比、加权平均投资者收益率）为 2026 年度报告新规要求披露的字段。当前报告年份不包含上述数据，仅展示基金产品收益。
</when_missing>

要求：
- 如果有投资者实际收益数据，分析行为损益 = 投资者实际收益 - 基金产品收益
- 分析份额变动趋势
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字

must_answer 字段：
- 投资者实际收益数据是否可用
<when_missing investor_return_data>
- 产品收益概况（净值增长率 vs 基准）
</when_missing>

{{ must_answer_schema }}
