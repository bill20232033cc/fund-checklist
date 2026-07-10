请严格审查以下 Python 代码变更（Slice 14A: Template-aligned report generation）。

**重要规则**：对每个 P0/P1 findings，必须先 `grep -n` 确认代码存在再评论。不要捏造不存在的代码。

## 项目背景
基金年报阅读工具。本次变更新增基金经理+规模明细数据抽取，按模板重做 8 章。

## 硬边界（违反即 P0）
1. 禁止投资建议
2. 禁止数字 hallucination（LLM 不输出数字，数字由程序填充）
3. 数据必须可溯源到年报
4. 禁止直接消费 raw PDF/Docling JSON
5. 换手率保持禁止

## 核心变更

### 新增 DTO 和抽取方法
```python
class FundManagerInfo:  # 姓名/任职日期/从业年限/投资策略/持有基金
class ScaleInfo:  # A/C类份额/个人投资者比例/管理人持有

def _extract_fund_manager(self, fund_code, annual_docs, work_dir) -> FundManagerInfo | None:
    # 搜索"基金经理" → table-0014 → 姓名/任职/从业年限
    # 搜索"投资策略和运作分析" → §4.4.1文本
    # 搜索tables → "基金经理持有" → 持有区间

def _extract_scale_info(self, fund_code, annual_docs, work_dir) -> ScaleInfo | None:
    # 搜索"开放式基金份额变动" → table-0093 → A/C类份额
    # 2025无数据时回退到2024
```

### 模板对齐的 8 章
`_generate_data_table()` 和 `_LLM_ANALYSIS_PROMPTS` 重写：
- Ch0: 投资要点概览（关键指标表）
- Ch1: 产品定义（基本信息+经理策略）
- Ch2: R=A+B-C（业绩+费率）
- Ch3: 基金经理画像（经理信息+持仓）
- Ch4: 投资者获得感（跳过，占位）
- Ch5: 当前阶段（规模+资产配置）
- Ch6: 核心风险（持仓集中度+业绩波动）
- Ch7: 最终判断（业绩汇总）

### 动态年份
`GenerateReportRequest.years` 默认空元组，自动从 catalog 获取可用年份。

### 业绩抽取修复
`_extract_report_performance` 改为逐年直接抽取，跳过失败年份。

## 测试
10 passed:
- test_generate_data_table_ch2/ch3/ch5（数据表格）
- test_contains_non_year_numbers（hallucination 检测）
- test_llm_chapter_generator_*（LLM 成功/失败/拒绝）
- test_generate_report_with_llm/fallback（端到端）

## 已知问题（不在 review 范围）
- Ch4 投资者获得感：跳过
- Ch6 核心风险：模板模式下只有静态声明
- 规模数据2025年Docling未提取，回退2024
- 管理人持有比例：Docling未提取为表格

## 请输出
### P0（必须修复）
问题 + 文件:行号 + 修复建议

### P1（建议修复）
问题 + 文件:行号 + 修复建议

### P2（可选优化）
问题 + 建议

### 总结
一段话概括代码质量和主要风险。
