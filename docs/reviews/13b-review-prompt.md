# Slice 13B Review Prompt — LLM-Generated Chapter Text

## 你的角色

你是一个严格的 code reviewer。请审查以下 diff，找出 correctness、stability、maintainability 问题。

## 项目背景

基金年报阅读工具（fund-checklist）。核心链路：
```
PDF → Docling → 7 reading tools → 数据抽取 → 报告生成
```

本次变更（Slice 13B）为 `fund-checklist generate` 子命令接入 DeepSeek LLM，生成 8 章分析报告。

## 硬边界（违反即 P0）

1. **禁止投资建议**：不得输出"买入""卖出""推荐"。
2. **禁止数字 hallucination**：LLM 不得输出数据中不存在的数字。
3. **所有数据必须可溯源到年报**：数据表格由程序从数据 dict 生成，不经过 LLM。
4. **禁止直接消费 raw PDF / raw Docling JSON / 本地路径**。
5. **失败必须 fail-closed**：LLM 失败回退模板，不静默忽略。

## 13B 裁决

1. LLM 用途：复用 8A/8B 的 `DeepSeekLlmClient`
2. 章节粒度：逐章独立 prompt
3. 输出约束：程序生成数据表格 + LLM 只写定性分析（两阶段模式）
4. 失败回退：LLM 失败的章节回退 13A 模板
5. 章节范围：全部 8 章

## 核心变更

### 1. DeepSeekLlmClient 新增 generate_text()

`fund_agent/agent/deepseek_llm.py`:

```python
def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    """直接调用 LLM 生成文本，不走 tool-loop。"""
    # 构造 OpenAI-compatible payload（无 tools）
    # 调用 transport.send()
    # 解析 response.choices[0].message.content
```

### 2. 两阶段章节生成

`fund_agent/service/reading_service.py`:

**阶段 1 — 程序生成数据表格**（数字 100% 从数据 dict 提取）：
```python
def _generate_data_table(chapter_id, fund_code, fund_name, report_year, performance, holdings, allocation, fees) -> str:
    """程序化生成 Markdown 数据表格。"""
    # Ch0: 基本信息表
    # Ch1: 基金概况表
    # Ch2: 业绩数据表（净值增长率、基准收益率、超额收益）
    # Ch3: 持仓数据表（前十大持仓，按年份）
    # Ch4: 资产配置表
    # Ch5: 费率数据表
    # Ch6: 分红数据（暂不可用）
    # Ch7: 无数据表格
```

**阶段 2 — LLM 只写定性分析**（禁止输出数字）：
```python
_LLM_CHAPTER_SYSTEM_PROMPT = (
    "你是一位专业的基金分析师。请基于提供的数据表格，撰写定性分析评论。\n"
    "【输出格式 - 必须严格遵守】\n"
    "1. 你的输出是纯定性分析文本，禁止包含任何数字、百分比、金额\n"
    # ...
)

_LLM_ANALYSIS_PROMPTS: dict[int, str] = {
    0: "请基于上述数据，用 3-5 个 bullet point 概括基金的核心特征和业绩亮点。不要包含任何数字。",
    2: "请分析上述业绩数据的趋势：净值增长率的变化方向、超额收益的稳定性。用定性描述，不要重复数字。",
    # ... 每章独立 prompt
}
```

**Hallucination 检测**：
```python
def _contains_non_year_numbers(text: str) -> bool:
    """检查文本是否包含非年份的数字。"""
    numbers = re.findall(r'(?<!\d)\d+\.?\d*%?(?!\d)', text)
    for n in numbers:
        cleaned = n.rstrip('%')
        if not re.match(r'^(20[12]\d|[1-9]|10)$', cleaned):
            return True  # 检测到 hallucination
    return False
```

**组合输出**：
```python
class LlmChapterGenerator:
    def generate_chapter(self, chapter_id, fund_code, fund_name, report_year, performance, holdings, allocation, fees):
        # 阶段 1: 程序生成数据表格
        data_table = _generate_data_table(...)
        # 阶段 2: LLM 生成定性分析
        llm_analysis = self._llm_client.generate_text(system_prompt=..., user_prompt=...)
        # 检测 hallucination
        if _contains_non_year_numbers(llm_analysis):
            return None  # 回退模板
        return f"{data_table}\n\n## 分析\n\n{llm_analysis}"
```

### 3. 业绩抽取修复

`_extract_report_performance` 改为逐年直接抽取，绕过 `aggregate_multi_year_annual_performance` 的 3 年最低要求：

```python
def _extract_report_performance(self, fund_code, annual_docs, work_dir):
    """逐年抽取，跳过失败年份。"""
    for doc in annual_docs:
        store = repository.load_store(doc.document_id)
        result = self._extract_annual_performance_from_store(...)
        if result.failure or not result.fields:
            continue  # 跳过失败年份
        # 提取 nav_growth_rate, benchmark_return_rate, excess_return
```

### 4. CLI 新增 --llm 标志

```python
generate_parser.add_argument("--llm", action="store_true", help="使用 LLM 生成分析文本")
# --years 留空则自动从 catalog 获取可用年份
generate_parser.add_argument("--years", default="", help="逗号分隔年份；留空自动用 catalog 可用年份")
```

### 5. 动态年份（不写死）

`GenerateReportRequest.years` 默认为空元组。`generate_report()` 不指定 years 时自动从 catalog 查找该基金所有可用年份：

```python
# 之前（写死）
years = tuple(request.years) if request.years else tuple(range(request.report_year - 4, request.report_year + 1))

# 之后（动态）
for report in catalog_reports:
    if report.get("fund_code") == request.fund_code:
        docs_by_year[year] = str(report["document_id"])
# 用户指定 years 时过滤；否则使用 catalog 全部可用年份
```

`_parse_years` 空字符串返回空元组，CLI `--years ""` 表示自动。

## 测试变更

`tests/fund/service/test_llm_chapter_generation.py` — 11 个新测试：

```python
test_generate_data_table_performance()      # 业绩表格包含真实数字
test_generate_data_table_holdings()          # 持仓表格包含真实股票代码
test_generate_data_table_fees()              # 费率表格包含真实费率
test_contains_non_year_numbers_detects()     # 非年份数字被检测
test_contains_non_year_numbers_allows_years() # 年份不触发检测
test_contains_non_year_numbers_allows_text()  # 纯文本不触发检测
test_llm_chapter_generator_success()          # LLM 正常返回：表格+分析
test_llm_chapter_generator_hallucination_rejected()  # LLM 输出数字被拒绝
test_llm_chapter_generator_failure_returns_none()    # LLM 失败返回 None
test_generate_report_with_llm_uses_data_tables()     # 端到端：数据表格有真实数字
test_generate_report_llm_fallback_to_template()      # 端到端：LLM 全部失败回退模板
```

## 真实 LLM Smoke 结果

```
Ch0: 投资要点概览 — LLM 生成，表格+定性分析
Ch1: 基金概况 — LLM 生成
Ch2: 业绩分析 — 数据表格包含 2023(-1.11%)、2024(17.32%)、2025(12.77%)
Ch3: 持仓分析 — 数据表格包含真实持仓
Ch4: 资产配置 — 数据表格包含真实配置
Ch5: 费率分析 — 数据表格包含管理费(1.20%)、托管费(0.20%)
Ch6: 分红分析 — 暂不可用
Ch7: 风险提示 — LLM 生成
Warnings: 0
```

## 已知问题（不在本次 review 范围）

1. **2022 年业绩数据缺失**：基金 2022 年重组，业绩表无"过去一年"行，属于数据问题非代码 bug。
2. **catalog 有重复/坏条目**：2024 年有两个 catalog 条目，其中一个 (`85c08ef235b06f5d`) 是坏数据。`_extract_report_performance` 的容错逻辑已处理此情况。
3. **章节结构与模板不匹配**：当前 8 章（投资要点/概况/业绩/持仓/配置/费率/分红/风险）与 `docs/fund-analysis-template-draft.md`（投资要点/产品定义/R=A+B-C/经理画像/投资者获得感/阶段变化/风险否决/最终判断）完全不同。后续 13C 将按模板重做。

## 请输出

### P0（必须修复）
问题 + 文件:行号 + 修复建议

### P1（建议修复）
问题 + 文件:行号 + 修复建议

### P2（可选优化）
问题 + 建议

### 总结
一段话概括代码质量和主要风险。
