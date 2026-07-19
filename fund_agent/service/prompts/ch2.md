<!-- version: 3.0 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 拆解→判断→成本
must_answer:
  - 近1年、3年、5年的基金净值增长率（R）
  - 同期业绩基准收益率（B）
  - 计算超额收益（A = R - B）
  - 判断超额收益是结构性的还是阶段性的
  - 拆解成本C：管理费+托管费+销售服务费
  - 判断超额收益是否为正且稳定、是否覆盖成本
must_not_cover:
  - 不展开基金经理选股能力的详细归因（属于第3章）
  - 不展开市场走势分析
  - 不做未来收益预测
required_output_items:
  - 近1/3/5年净值增长率
  - 近1/3/5年业绩基准收益率
  - 超额收益（A = R - B）及稳定性
  - 超额收益性质判断（结构性 vs 阶段性）
  - 成本拆解（管理费、托管费）
  - R=A+B-C 综合评估
data_sources:
  - performance
  - fees
metrics:
  - name: 近1年净值增长率
    formula: 当年净值增长率
    unit: "%"
    threshold: 无
    source: performance
    note: R值
  - name: 近3年净值增长率
    formula: 最近3年净值增长率
    unit: "%"
    threshold: 无
    source: performance
    note: R值，数据不足时声明
  - name: 近5年净值增长率
    formula: 最近5年净值增长率
    unit: "%"
    threshold: 无
    source: performance
    note: R值，数据不足时声明
  - name: 超额收益
    formula: R - B
    unit: "%"
    threshold: 正且稳定
    source: performance
    note: A = R - B
  - name: 总成本率
    formula: 管理费+托管费+销售服务费
    unit: "%"
    threshold: 无
    source: fees
    note: C值
  - name: 净超额收益
    formula: A - C
    unit: "%"
    threshold: 正
    source: performance+fees
    note: 超额收益是否覆盖成本
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: comma_handling
    description: 提取数字前去除逗号
item_rules:
  - condition: 数据年份不足3年
    affected_output: 近3年/5年净值增长率
    degradation_note: 数据年份不足，声明局限性
  - condition: 销售服务费缺失
    affected_output: 成本拆解
    degradation_note: 销售服务费数据缺失，仅展示管理费+托管费
END_CHAPTER_CONTRACT
-->

请基于上述业绩数据和成本数据，写一段「R=A+B-C 收益归因」分析。

要求：
- 分析超额收益(A=R-B)的趋势：是结构性的还是阶段性的
- 判断超额收益是否为正且稳定
- 用定性描述（如"上升""下降""稳定""由正转负"），不要重复数字
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字

<when_missing multi_year_note>
注意：当前数据年份不足，分析时需声明数据局限性，不做长期趋势判断。
</when_missing>

章节边界：只分析 R=A+B-C，不分析持仓（属于 Ch3/Ch6）。

{{ must_answer_schema }}
