<!-- version: 3.0 -->
<!--
CHAPTER_CONTRACT
narrative_mode: 判断→依据→验证
must_answer:
  - 给出综合评估结论
  - 为什么现在更适合这个结论
  - 当前最容易看错的地方是什么
  - 下一轮先核实什么（1-2个最小验证问题）
  - 什么变化会升级、降级或终止当前判断
must_not_cover:
  - 不输出具体的买入金额、卖出时机或仓位比例
  - 不把本章写成前6章的摘要复述
  - 不把为什么写成多条理由堆砌
required_output_items:
  - 综合评估结论
  - 支撑结论的核心依据（1-2条）
  - 当前最容易看错的地方
  - 下一轮最小验证计划
  - 升级/降级阈值
data_sources:
  - performance
  - holdings
  - fees
  - fund_manager
metrics:
  - name: 综合评分
    formula: signal_scoring 程序化计算
    unit: "分"
    threshold: ">=80 通过, 50-79 需修复, <50 需重写"
    source: signal_scoring
    note: 由 signal_scoring.py 程序化生成，LLM 不得自行计算
  - name: 6指标评分详情
    formula: 6个子指标各自评分
    unit: "分"
    threshold: 无
    source: signal_scoring
    note: LLM 只解读，不计算
data_verification:
  - rule_type: number_citation
    description: 引用原始数字，不缩写
  - rule_type: comma_handling
    description: 提取数字前去除逗号
END_CHAPTER_CONTRACT
-->

请基于上述信号判断结果和前6章分析，写一段「综合评估与跟踪建议」的定性分析。

要求：
- 系统已给出信号判断和评分详情表，你只需写定性分析评论
- 解释为什么当前信号是合理的，结合评分详情中的最高分和最低分指标
- 指出当前最容易看错的地方
- 给出下一轮最小验证计划（1-2个）
- 禁止输出投资建议（如"买入""卖出""推荐"）
- 禁止预测未来收益或市场走势
- 可以引用数据表中的数字，但不得编造数据表中不存在的数字

{{ must_answer_schema }}
