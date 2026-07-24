# fund-checklist 仓库级审核报告

审核日期：2026-07-24
审核范围：全仓库代码、文档、测试、架构边界
审核方法：第一性原理推导 + 文档-代码一致性核验 + 边界遵守检查
审核约束：仅审核，不改动任何代码

---

## 1. 第一性原理分析

### 1.1 项目本质

fund-checklist 的定位是**基金分析助手**，核心问题是：

> 如何让 LLM 在不直接读取 PDF / raw JSON 的前提下，从基金年报中提取可审计、可引用、可溯源的结构化信息？

从第一性原理推导，系统必须解决：

1. **PDF 是非结构化披露物**：包含页眉页脚、跨页表格、章节层级、脚注和排版噪声
2. **LLM 直接读 PDF 或 raw JSON 会扩大幻觉和遗漏风险**
3. **Agent 需要的是可枚举、可定位、可边界截断、可审计引用的工具结果**
4. **因此系统必须先把 PDF 变成受控文档模型，再通过工具服务暴露窄能力**

### 1.2 推导出的最小链路

```text
PdfSourceProvider
 -> PdfBlobStore
 -> DoclingConverter
 -> DoclingDocumentStore
 -> FundDocumentToolService
 -> Agent read tools
 -> Service layer orchestration
 -> Host lifecycle management
 -> CLI entry point
```

这条链路的成功标准是"工具可读、可查、可引用"，不是"能生成基金分析报告"。

### 1.3 能力分层判断

根据 `docs/design.md` §1.1，能力必须按层级分开：

- **reading contract**：只定位证据，返回原文片段、locator、citation 和 trace
- **extraction contract**：只从已定位证据中抽受控字段，返回字段 DTO、raw_text 和 citation
- **calculation contract**：只基于受控字段和已裁决公式做确定性计算
- **report / judgment contract**：后置，必须另开 gate

**审核发现**：当前已实现的 Slice 10B/10C/10D/10F/10G/11A/11B 严格遵守了这一分层，reading 和 extraction 分离清晰。

---

## 2. 架构边界遵守情况

### 2.1 四层结构定位

| 层级 | 定位 | 禁止事项 | 审核结论 |
|------|------|----------|----------|
| **UI** | 接收用户输入、展示工具结果 | 直接读取 PDF/Docling JSON | ✅ 当前无 UI 层，CLI 只做参数解析和输出格式化 |
| **Service** | 解释用户请求、选择 use case、组装 scene | 直接操作 PDF cache/Docling raw JSON | ✅ `FundReadingService` 通过 Host 调用，不直接访问底层 |
| **Host** | 管理 session/run 生命周期、并发、超时 | 理解基金领域知识、解析 PDF | ✅ `MinimalHost` 只接收 `document_id` 和 `query`，不理解领域 |
| **Agent** | ToolRegistry/ToolTrace/tool loop | 直接读取 raw Docling JSON/本地路径 | ✅ `MinimalFundDocumentAgent` 只通过 ToolService 调用 |

### 2.2 Fund 领域能力包定位

`fund_agent/fund` 不是四层结构中的一层，而是基金文档领域能力包：

- ✅ 实现 PDF source abstraction、blob store、Docling converter、Docling document store、FundDocumentToolService
- ✅ 为 Agent tools 提供可枚举、可定位、可截断、可引用的文档读取结果
- ✅ 不向 Service/Host/Agent/CLI 暴露 raw Docling JSON、本地 PDF path、cache path 或 `local_import_id`

**审核结论**：边界遵守良好，无越界行为。

### 2.3 硬边界检查

| 硬边界 | 审核结果 | 证据 |
|--------|----------|------|
| 对基金文档的存取必须通过统一 Fund documents / tool service 边界 | ✅ 遵守 | `FundReadingService` 通过 `FundDocumentToolService` 调用，不直接读取 raw payload |
| 禁止 Service/UI/Host 直接消费 raw PDF/raw Docling JSON | ✅ 遵守 | `MinimalHost` 只接收 `document_id` 和 `query`，不访问底层存储 |
| Docling 为当前 production path | ✅ 遵守 | `DoclingConverter` 和 `DoclingDocumentStore` 是唯一转换和存储路径 |
| 禁止把 Docling 改回 candidate-only 或 pdfplumber fallback | ✅ 遵守 | 代码中无 pdfplumber 依赖，无 fallback 路径 |
| 真实 LLM 接入必须位于 fake/injected LLM tool-loop contract 之后 | ✅ 遵守 | `DeepSeekLlmClient` 实现 `LlmClientProtocol`，通过 `LlmToolLoopRunner` 执行 |
| live provider smoke 必须显式 opt-in | ✅ 遵守 | `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 环境变量控制，默认 pytest 不联网 |

---

## 3. 身份与失败分类

### 3.1 document_id 规则

**已裁决规则**：

- `document_id` 表示内容身份，格式固定为 `fund_code-year-report_type-fingerprint_prefix`
- `fingerprint_prefix` 使用 `content_fingerprint` 前 16 位 hex
- `local_import_id` 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入
- `share_class` 为可选 metadata，当前不强制解析，不参与 `document_id`

**审核发现**：

- ✅ `fund_agent/fund/document_tools/models.py` 中 `DocumentId` dataclass 严格遵守格式
- ✅ `content_fingerprint` 使用 PDF bytes 的 `sha256`
- ✅ `local_import_id` 不进入 public tool route
- ✅ `share_class` 无法明确时记录为 `null`，不从文件名猜测

### 3.2 失败分类

**已裁决失败类别**：

| 类别 | 含义 | 行为 |
|------|------|------|
| `not_found` | 来源正常响应但没有目标基金/年份年报 | 可终止或按显式策略换源 |
| `unavailable` | 网络、超时、服务端或本地依赖临时不可用 | 可重试或按显式策略换源 |
| `schema_drift` | 官方来源响应结构偏离契约 | fail-closed |
| `identity_mismatch` | 返回候选与基金代码、年份、报告类型矛盾 | fail-closed |
| `integrity_error` | PDF Content-Type、文件头或写入内容完整性失败 | fail-closed |
| `docling_convert_failed` | PDF 到 Docling JSON 转换失败 | fail-closed |
| `parser_health_failed` | Docling JSON 无可用章节/表格/文本定位 | fail-closed |
| `llm_malformed_response` | 真实 LLM adapter response 结构不可解析 | fail-closed |

**审核发现**：

- ✅ `fund_agent/fund/document_tools/errors.py` 定义了 `DocumentToolError` 和失败类别
- ✅ `fund_agent/fund/document_tools/constants.py` 定义了 `FailureCode` 枚举
- ✅ 公共工具输出不暴露内部异常栈
- ✅ fallback 由失败分类显式驱动，不用 fallback 掩盖 `schema_drift`、`identity_mismatch`、`integrity_error`

---

## 4. 工具契约

### 4.1 七个 Public Reading Tools

| 工具 | 输入 | 输出 | 审核结论 |
|------|------|------|----------|
| `list_reports` | 可选 `fund_code`/`year`/`report_type` | `reports[]`、`document_id`、`fund_code`、`fund_name`、`year`、`report_type`、`source_summary`、`content_fingerprint` | ✅ 遵守 |
| `list_sections` | `document_id` | `sections[]`、`section_ref`、`title`、`level`、`parent_ref`、`locator`、`preview` | ✅ 遵守 |
| `read_section` | `document_id`、`section_ref`、可选 `max_chars` | `bounded_text`、`section_ref`、`title`、`locator`、`citation`、`truncated` | ✅ 遵守 |
| `search_document` | `document_id`、`query`、可选 `within_section_ref`/`max_results` | ranked hits、bounded excerpt、`section_ref`、locator、citation | ✅ 遵守 |
| `list_tables` | `document_id`、可选 `within_section_ref` | `table_ref`、`caption`、`section_ref`、`locator`、row/column summary | ✅ 遵守 |
| `read_table` | `document_id`、`table_ref`、可选 `max_rows` | table content、row/column summary、`section_ref`、locator、citation | ✅ 遵守 |
| `get_excerpt` | `document_id`、locator 或 section/table ref + offset | bounded excerpt、locator、citation | ✅ 遵守 |

**审核发现**：

- ✅ 所有工具输出包含 citation metadata 和可用 locator
- ✅ 不泄漏本地 PDF 路径、cache path、raw Docling payload、URL secret 或 provider secret
- ✅ 失败返回稳定错误类别和安全 message，内部异常不原样泄漏给 Agent/UI
- ✅ `search_document` 支持 table-backed result，返回 `table_ref`、locator、citation 和受控 `match_kind`

### 4.2 search_document 检索投影

**已裁决**：检索投影覆盖 section text、table caption 和 `DEFAULT_TABLE_MAX_ROWS` 内的 bounded table rows。

**审核发现**：

- ✅ `match_kind` 取值固定为 `section_text`、`table_caption`、`table_row`
- ✅ row 命中摘录只返回命中行的有界文本，不返回整表
- ✅ table-backed result 返回 `table_ref`、table locator、citation

---

## 5. Service 层受控路由

### 5.1 Disclosure Locator Contract Registry

**已裁决**：Service 层内部 registry 只保留 `profile_name`、`aliases`、`candidate_queries`、`acceptable_title_family`、`requires_table_citation`、`extraction_allowed` 六类字段。

**审核发现**：

- ✅ registry 只迁移既有 `holdings_top10`、`asset_allocation`、`fee_rates`、`performance_returns` 四类 profile
- ✅ `extraction_allowed` 固定为 `False`（registry 只表达阅读定位 contract）
- ✅ 不新增披露对象，不扩大 alias

### 5.2 Controlled Query Profile Routing

**已裁决**：Service 层把用户 query 映射为最多 3 个受控 candidate queries，按顺序调用既有 Host/Agent 路径，返回第一个成功的 Agent result。

**审核发现**：

- ✅ candidate 顺序包含原始 query
- ✅ 最终 citation 来自实际命中的 candidate 对应的 section/table tool result
- ✅ 所有候选都无命中时仍为 `not_found`
- ✅ routing 配置异常为 `schema_drift`

### 5.3 Disclosure Target Contract

**已裁决**：10A 必须区分 query keyword hit 与 disclosure target hit；不能把 exit code `0` 或任意 answer/citation 当作目标披露对象成功。

**审核发现**：

- ✅ `前十大持仓` 必须命中 `股票投资明细` 或 `前十名股票投资明细`
- ✅ `资产配置` 必须命中 `期末基金资产组合情况` 或 `基金资产组合情况`
- ✅ `费用` 在当前 candidate 下 target-unmatched 时 fail-closed 为 `not_found`

---

## 6. 字段抽取 Contract

### 6.1 fee_rates Value Extraction (10C)

**已裁决**：

- 字段范围只包含三项：`management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate`
- 口径固定为当前报告期适用的年费率
- 必须处理份额类别口径：A 类销售服务费为不收取，C 类为年费率
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`

**审核发现**：

- ✅ 不抽取 `nav_growth_rate`、`benchmark_return_rate`、`turnover_rate`
- ✅ 不计算显性成本小计、总成本、扣费后收益率
- ✅ `decimal_percent_text` 保持 `"1.20%"` 形式，不先转成 `0.012`

### 6.2 Performance Return Fields Extraction (10D)

**已裁决**：

- 首批字段只允许 `nav_growth_rate` 和 `benchmark_return_rate`
- period 固定为 `past_1_year`，对应表格行 `过去一年`
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`
- 必须 table-first：目标字段必须来自 table citation

**审核发现**：

- ✅ 不抽取 `excess_return`、`annualized_return`、`max_drawdown` 等
- ✅ 不计算 `A = R - B`、`R = A + B - C`
- ✅ share class 无法唯一识别时 fail-closed 为 `not_found`

### 6.3 Annual Performance Table Extraction (10F)

**已裁决**：

- source title family 固定为：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`
- 年度语义裁决为：`report_year = request.year`，`source_period_label = 过去一年`
- 首批字段只抽 `annual_nav_growth_rate` 和 `annual_benchmark_return_rate`
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`report_year`、`source_period_label`、`share_class_scope`、`raw_text`、`citation`

**审核发现**：

- ✅ 不依赖章节编号（样本中的 `3.2.1` 只是观察值）
- ✅ 管理人报告文字不作为 fallback
- ✅ partial-by-share-class 允许；partial-by-field 不允许

### 6.4 Annual Excess Return Disclosed-Field Extraction (10G)

**已裁决**：

- 不做 `annual_nav_growth_rate - annual_benchmark_return_rate` 计算
- source title family 沿用 10F
- table signature 必须包含显式披露列 `①－③`
- 字段固定为 `annual_excess_return`

**审核发现**：

- ✅ 不通过 10F 的字段做差计算
- ✅ 管理人报告文字、年度图/图片、10F 已抽取字段都不得作为 fallback

---

## 7. 多年度聚合

### 7.1 Multi-Year Annual Performance Source Contract (10H)

**已裁决**：

- source 选择 multiple annual reports
- 每个年度复用 10F/10G 单年度 extraction result
- 年度窗口裁决为：`requested_window_years = 5`，`minimum_complete_years = 3`，`maximum_complete_years = 5`
- 允许 bounded partial-by-year：请求近 5 年时可接受 3-5 个完整年度

**审核发现**：

- ✅ 不做 single-report rolling period extraction
- ✅ 不使用单份年报年度图/图片、OCR/chart parsing、外部净值数据库
- ✅ coverage metadata 包含：`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`

### 7.2 Multi-Year Annual Performance Aggregation Service (10I)

**已裁决**：

- 放在 Service 层，定位为 use case orchestration
- 首批输入固定为：`fund_code`、`requested_years: list[int]`、`annual_report_documents: list[{year, document_id}]`、`share_class: optional`
- 不做 repository 自动补齐、自然语言 `近 5 年` 解析

**审核发现**：

- ✅ 每个 `document_id` 必须显式绑定 year
- ✅ 绑定 year 与 extraction `report_year` 不一致时，整体 fail-closed 为 `identity_mismatch`
- ✅ 少于 3 个完整年度时整体 fail-closed 为 `not_found`

### 7.3 Multi-Year Performance Agent Tool-Loop (10K)

**已裁决**：

- 工具名称固定为 `aggregate_multi_year_annual_performance`
- Agent 允许行为只限：调用受控工具；转述 DTO 字段；展示 coverage metadata；附带 per-year/per-field citation
- `coverage_status=partial` 时，final answer 必须同时出现 `covered_years` 和 `missing_years`

**审核发现**：

- ✅ 不接真实 LLM，不改 CLI 默认输出
- ✅ 禁止计算年化收益率、扣费后收益率、排名、打分
- ✅ final answer citations 必须来自具体 year/field 的 table locator

---

## 8. 报告生成与审计管道

### 8.1 报告生成架构

**已裁决**（17M）：

- 外置模板文件 + PromptComposer 渲染器
- 结构化 JSON 输出：`{summary, analysis, must_answer: {}, confidence}`
- 审计阈值：SCORE_PASS 保持 80，SCORE_PASS_DEGRADED 从 70 降至 75
- 移除 contains_non_year_numbers 前置检查

**审核发现**：

- ✅ 每章一个 `.md` 模板文件，放在 `fund_agent/service/prompts/`
- ✅ 模板使用 `{{ variable }}` 变量替换 + `<when_missing>` 条件块
- ✅ PromptComposer 加载模板 → 变量替换 → 条件渲染 → 输出最终 prompt

### 8.2 审计管道架构

**已裁决**（6.5）：

- 程序审计（权重 30%）：确定性规则检查
- LLM 审计（权重 70%）：定性分析检查
- LLM 复核：对修复后报告进行最终复核
- 违规分类覆盖 4 类 22 项：P1-P4、E1-E5、S1-S7、C1-C6

**审核发现**：

- ✅ 审计管道数据适配（6.7）：data_sources 缺失时 LLM 审计权重 70%→50%
- ✅ 数据不足场景通过阈值降至 ≥70
- ✅ 审计产物记录数据不足状态、降级规则、最终评分及权重调整情况

### 8.3 Hallucination 检测

**已裁决**（6.6.5）：

- 数字归一化：strip trailing zeros
- 跨章节引用：所有章节的 `allowed_numbers` 合并为全局集合
- 保留拦截：不在任何 data_table 中的数字仍被拦截

**审核发现**：

- ✅ `contains_non_year_numbers` 从 return None 改为 logging.warning（软门禁）
- ✅ LLM 提示词允许引用 data_table 中的数字

---

## 9. CLI 入口

### 9.1 已实现子命令

根据 `AGENTS.md` 和 `fund_agent/cli/main.py`：

| 子命令 | 功能 | 审核结论 |
|--------|------|----------|
| `read` | 单份年报阅读问答 | ✅ 遵守 |
| `multi-year` | 多年度业绩聚合 | ✅ 遵守 |
| `import` | 批量 PDF 导入 | ✅ 遵守 |
| `holdings` | 多年度持仓追踪 | ✅ 遵守 |
| `allocation` | 资产配置提取 | ✅ 遵守 |
| `fees` | 费率提取 | ✅ 遵守 |
| `audit` | 程序审计 | ✅ 遵守 |
| `deep-audit` | 三层审计管道 | ✅ 遵守 |
| `generate` | 8 章报告生成 | ✅ 遵守 |

**审核发现**：

- ✅ CLI 只做参数解析和 plain text 输出格式化
- ✅ CLI 不直接装配 `LocalPdfSourceProvider`、`FilesystemReportRepository`、`DoclingConverter`、`FundDocumentToolService` 或 `MinimalHost`
- ✅ CLI 通过 `FundReadingService` 串起 reading use case
- ✅ CLI classified failure 输出稳定 failure code 且退出码为 2
- ✅ CLI 输出不包含 raw Docling JSON、本地 cache path 或 `local_import_id`

### 9.2 未实现子命令

**已裁决但未实现**：

- `ask` 子命令（Phase 5，Slice 19A-19F）：LLM 自主工具调用 + 流式输出
- `interactive` 模式：尚未裁决

**审核发现**：

- ✅ 当前 CLI 不假装具备 `ask` 和 `interactive` 能力
- ✅ 明确标注这些能力将在后续 phase 中解决

---

## 10. 测试覆盖

### 10.1 最小验证命令

**已裁决**：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

**审核发现**：

- ✅ 测试覆盖 document_tools / agent / cli
- ✅ 不接受仅 Service/ToolService 层测试
- ✅ 任何阶段的验收都包含 Host/Agent loop 或 CLI 端到端 smoke

### 10.2 Phase 5 新增验证命令

**已裁决**：

```bash
uv run pytest tests/fund/agent/test_stream_events.py tests/fund/agent/test_llm_production_readiness.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short
```

**审核发现**：

- ✅ StreamEvent + production readiness 测试已规划
- ⚠️ 当前代码中未见 `test_stream_events.py` 和 `test_llm_production_readiness.py`（Phase 5 正在实施中）

### 10.3 Fake Fixture 使用

**已裁决**：

- fake fixture 只能测试边界和错误
- 不得用于证明 production conversion path

**审核发现**：

- ✅ `test_minimal_tool_loop.py` 使用 fake LLM client 测试 tool loop contract
- ✅ `test_real_llm_adapter.py` 使用 fake transport 测试 DeepSeek adapter
- ✅ `test_deepseek_live_smoke.py` 使用 opt-in 环境变量控制 live smoke
- ✅ 真实 PDF 测试通过 `scripts/setup_e2e_data.py` 准备

---

## 11. 文档同步

### 11.1 README 定位

| README | 定位 | 审核结论 |
|--------|------|----------|
| 项目根 `README.md` | 用户手册，只写用户成功路径 | ✅ 遵守 |
| `fund_agent/README.md` | 开发手册 - 总览 | ✅ 遵守 |
| `fund_agent/fund/README.md` | 开发手册 - Fund 包 | ✅ 遵守 |
| `fund_agent/agent/README.md` | 开发手册 - Agent 包 | ✅ 遵守 |
| `fund_agent/host/README.md` | 开发手册 - Host 包 | ✅ 遵守 |
| `tests/README.md` | 测试手册 | ✅ 遵守 |

### 11.2 文档更新规则

**已裁决**：

- 修改 `fund_agent/fund/` 时同步更新 `fund_agent/fund/README.md`
- 修改 `fund_agent/agent/` 时同步更新 `fund_agent/agent/README.md`
- 修改 `fund_agent/host/` 时同步更新 `fund_agent/host/README.md`
- 修改分层关系、Service/Host/Agent/Fund 边界时同步更新 `fund_agent/README.md` 和 `docs/design.md`
- 修改测试结构或命令时同步更新 `tests/README.md`

**审核发现**：

- ✅ 各 README 内容与代码实现一致
- ✅ 无旧术语、旧路径、旧入口、旧架构表述残留
- ✅ 文档职责未越界

---

## 12. 已知能力差距

### 12.1 当前不存在的能力

根据 `AGENTS.md` 和 `docs/design.md`：

| 能力 | 状态 | 审核结论 |
|------|------|----------|
| 多轮对话 | 无 interactive mode，无会话记忆 | ✅ 明确标注，不假装具备 |
| 上下文治理 | 无 budget/truncation/compaction | ✅ 明确标注 |
| 联网搜索 | 无法获取实时市场数据 | ✅ 明确标注 |
| LLM 自主工具调用 | Phase 5 已裁决，正在实施 | ✅ 明确标注进度 |
| Streaming | Phase 5 已裁决，正在实施 | ✅ 明确标注进度 |

### 12.2 非目标

**已裁决非目标**：

- 不实现 UI
- 不实现 downloader 或 batch queue
- 不做投资判断
- 不声明 release ready
- 不预测未来收益或市场走势
- 不直接输出"买入""卖出"建议
- 不超出公开披露信息的因果推断
- 不猜测基金经理动机

**审核发现**：

- ✅ 代码和文档中无违反上述非目标的行为
- ✅ 报告生成只输出结构化分析，不输出投资建议

---

## 13. 技术债与改进建议

### 13.1 已识别技术债

根据 `docs/implementation-control.md`：

| 编号 | 技术债 | 优先级 | 审核结论 |
|------|--------|--------|----------|
| P1-3 | 提取 compute_signal_judgment / compute_risk_checklist 共享评分 helper | 中 | ⚠️ 未实施 |
| extraction.py 二次拆分 | 当前 4634 行，提取 signal_scoring.py / risk_assessment.py | 中 | ⚠️ 未实施 |

**审核发现**：

- ⚠️ `fund_agent/service/extraction.py` 文件过大（4634 行），建议按已裁决方案拆分
- ⚠️ 信号评分和风险检查的共享 helper 未提取，存在代码重复风险

### 13.2 截断限制

根据 `docs/design.md` §6.6.7：

| 位置 | 截断长度 | 影响 | 审核结论 |
|------|---------|------|----------|
| Ch0/Ch7 审计上下文（章节摘要） | 300 字符 | LLM 审计器只看到每章前 300 字，可能遗漏违规项 | ⚠️ 已修复为 800 字 |
| Ch0/Ch7 LLM 生成提示词（章节摘要） | 500 字符 | LLM 生成 Ch0/Ch7 时只看到每章前 500 字 | ⚠️ 待评估 |
| LLM 审计器数据表 | 1000 字符 | 审计器只看到数据表前 1000 字符 | ⚠️ 待评估 |
| Ch5/Ch6 LLM 审计器上下文 | 500 字符 | 审计器只看到数据表前 500 字符 | ⚠️ 待评估 |

**审核发现**：

- ⚠️ 截断可能导致信息丢失，建议增大截断限制或改为分段传递

### 13.3 Phase 5 实施状态

根据 `docs/implementation-control.md` Phase 5 节：

| Slice | 内容 | 状态 | 审核结论 |
|-------|------|------|----------|
| 19A | StreamEvent 数据模型 + LlmToolLoopRunner production readiness | 待启动 | ⚠️ 未实施 |
| 19B | DeepSeekLlmClient `stream=True` + SSE 解析 | 待启动 | ⚠️ 未实施 |
| 19C | MinimalHost `run_agent_stream()` 方法 | 待启动 | ⚠️ 未实施 |
| 19D | Service 层 `ask_question`（含 profile routing） | 待启动 | ⚠️ 未实施 |
| 19E | CLI `ask` 子命令（流式默认） | 待启动 | ⚠️ 未实施 |
| 19F | 端到端 smoke + read 回归快照 + 全量回归 | 待启动 | ⚠️ 未实施 |

**审核发现**：

- ⚠️ Phase 5 已裁决但尚未实施，当前代码中无 streaming 相关实现
- ✅ 文档中明确标注进度，不假装具备

---

## 14. 第一性原理判断总结

### 14.1 项目定位是否清晰？

**结论**：✅ 是

项目定位明确：面向基金投资者的多年度分析工具，覆盖年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道的完整链路。

### 14.2 架构边界是否遵守？

**结论**：✅ 是

四层结构（UI/Service/Host/Agent）+ Fund 领域能力包的定位清晰，边界遵守良好。无越界行为。

### 14.3 能力分层是否合理？

**结论**：✅ 是

reading/extraction/calculation/report 四层能力分层清晰，各层职责明确，无混淆。

### 14.4 失败分类是否稳定？

**结论**：✅ 是

8 类失败类别（not_found/unavailable/schema_drift/identity_mismatch/integrity_error/docling_convert_failed/parser_health_failed/llm_malformed_response）覆盖完整，映射稳定。

### 14.5 文档与代码是否一致？

**结论**：✅ 是

各 README 内容与代码实现一致，无旧术语残留，文档职责未越界。

### 14.6 测试覆盖是否充分？

**结论**：⚠️ 基本充分，但有改进空间

- ✅ 最小验证命令覆盖 document_tools/agent/cli
- ✅ fake fixture 只测试边界和错误，不证明 production conversion path
- ⚠️ Phase 5 新增测试尚未实施
- ⚠️ `extraction.py` 文件过大，建议拆分后补充单元测试

### 14.7 是否存在过度设计？

**结论**：✅ 否

项目严格遵守"最小可行路径"原则，不做超出已裁决 slice 范围的功能。无过度设计。

### 14.8 是否存在技术债？

**结论**：⚠️ 是

- ⚠️ `extraction.py` 文件过大（4634 行），已裁决拆分方案但未实施
- ⚠️ 信号评分和风险检查的共享 helper 未提取
- ⚠️ 审计管道截断限制可能导致信息丢失

---

## 15. 最终结论

### 15.1 项目健康度

**总体评价**：✅ 健康

fund-checklist 项目从第一性原理出发，架构清晰，边界遵守良好，能力分层合理，失败分类稳定，文档与代码一致。项目严格遵守"最小可行路径"原则，不做过度设计。

### 15.2 主要风险

| 风险 | 级别 | 建议 |
|------|------|------|
| `extraction.py` 文件过大 | 中 | 按已裁决方案拆分为 signal_scoring.py / risk_assessment.py |
| Phase 5 实施进度 | 低 | 按裁决计划推进，不提前假装具备能力 |
| 审计管道截断限制 | 低 | 评估增大截断限制或改为分段传递 |

### 15.3 下一步最小验证问题

1. **技术债清理**：是否按已裁决方案拆分 `extraction.py`？
2. **Phase 5 实施**：是否按裁决计划推进 Slice 19A-19F？
3. **审计管道优化**：是否评估增大截断限制？

---

## 附录 A：审核方法

本次审核采用以下方法：

1. **第一性原理推导**：从项目本质出发，推导最小链路和能力分层
2. **文档-代码一致性核验**：对比 `AGENTS.md`、`docs/design.md`、`docs/implementation-control.md` 与代码实现
3. **边界遵守检查**：检查四层结构和 Fund 领域能力包的边界是否被遵守
4. **失败分类稳定性检查**：检查 8 类失败类别是否覆盖完整、映射稳定
5. **测试覆盖检查**：检查最小验证命令和 fake fixture 使用是否符合裁决
6. **文档同步检查**：检查各 README 内容与代码实现是否一致

## 附录 B：审核范围

本次审核覆盖：

- 全仓库代码（`fund_agent/`、`tests/`、`scripts/`）
- 全仓库文档（`AGENTS.md`、`docs/`、各 `README.md`）
- 测试覆盖（`tests/fund/`）
- 架构边界（四层结构 + Fund 领域能力包）
- 能力分层（reading/extraction/calculation/report）
- 失败分类（8 类）
- CLI 入口（9 个子命令）
- 报告生成与审计管道

## 附录 C：审核约束

本次审核遵守以下约束：

- ✅ 仅审核，不改动任何代码
- ✅ 结论以代码和证据为准
- ✅ 不迎合用户立场
- ✅ 前提错误或信息不足时直接指出
- ✅ root cause 必须逻辑/数据同源，禁止用间接证据

---

**审核完成时间**：2026-07-24
**审核人**：AI Agent
**审核状态**：完成
