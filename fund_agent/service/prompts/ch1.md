<!-- version: 3.0 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 定义→策略→基准
must_answer:
  - 用最低认知负担定义这只基金到底是什么产品
  - 说明基金的投资目标和投资策略
  - 说明基金的业绩基准是什么
  - 说明基金的类型分类
  - 回答看这类基金时，通常最先要看什么
must_not_cover:
  - 不展开基金经理选股能力的分析（属于第3章）
  - 不展开收益率的详细计算（属于第2章）
  - 不分析市场竞争或同业比较
required_output_items:
  - 基金类型与分类标签
  - 投资目标（一句话）
  - 投资策略概述
  - 业绩基准及合理性
  - 看这类基金最先看什么
data_sources:
  - basic_info
  - fund_manager
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: comma_handling
    description: 提取数字前去除逗号
END_CHAPTER_CONTRACT
-->

请基于上述基本信息和基金经理投资策略，写一段「产品定义」分析。

要求：
- 用最低认知负担定义这只基金到底是什么产品
- 说明投资目标和投资策略
- 说明看这类基金时通常最先要看什么
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字

章节边界：只做产品定义，不分析基金经理选股能力（属于 Ch3）。

{{ must_answer_schema }}
