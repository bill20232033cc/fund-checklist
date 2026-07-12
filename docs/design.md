# fund-checklist 设计真源

更新时间：2026-07-11
文档状态：设计真源，覆盖基金分析助手完整链路；不得作为实现完成证据。
适用范围：基金分析助手，覆盖年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道。
关联文档：AGENTS.md（执行规则）、docs/implementation-control.md（当前执行面板）

## 0. 证据口径

### 0.1 当前代码事实

- 本仓库已实现 `fund_agent/` 完整分层（fund / service / host / agent / cli），`tests/` 覆盖 document_tools / service / agent / cli，`docs/design.md` 与 `docs/implementation-control.md` 为真源文档。
- CLI 已实现 9 个子命令：`read` / `multi-year` / `import` / `holdings` / `allocation` / `fees` / `audit` / `deep-audit` / `generate`。
- 已实现能力：本地 PDF 导入、Docling 转换、7 个 reading tools、Service 层 profile routing + disclosure target contract、结构化字段抽取（费率/业绩/持仓/资产配置）、多年度聚合、确定性信号评分（6 指标）、8 章分析报告生成、三层审计管道。
- 当前样本材料位于 `基金年报/`，包含多只基金多个年度的 PDF；已通过受控 import 管理。
- `docs/fund-analysis-template-draft.md` 存在，按 `AGENTS.md` 规则，在报告生成、字段抽取或投资判断路径中使用。

### 0.2 当前规则事实

- `AGENTS.md` 是本仓库 Agent 执行规则唯一权威入口。
- `docs/architecture.md` 是轻量架构坐标系；它固定不可摇摆的层次、主链路和稳定契约，但不代表当前代码已实现。
- 当前产品方向是基金分析助手，覆盖年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道。主链路为：

```text
PDF
 -> Docling JSON
 -> FundDocumentToolService (7 个 reading tools)
 -> Service 层受控 profile routing + disclosure target contract
 -> 结构化字段抽取 (performance / fee_rates / holdings / allocation)
 -> 多年度聚合 (3-5 年 bounded coverage)
 -> 确定性信号评分 (6 指标，135→100 归一化)
 -> 8 章分析报告生成 (程序数据表格 + LLM 定性分析)
 -> 三层审计管道 (程序+LLM+复核，4 类 22 项)
```

- 结构化字段抽取、自动报告、信号评分已通过正式 Slice 准入（10C/10F/10G/11C/11D/13A/13B/14A/14C），纳入正式产品范围。
- 目标架构固定为 `UI -> Service -> Host -> Agent`；`fund_agent/fund` 是基金文档领域能力包，不是四层结构中的一层。基金文档读取、PDF source、Docling conversion、Docling document store、FundDocumentToolService 归 `fund_agent/fund`，由 Service / Agent 通过受控边界使用。
- Service / UI / Host / 展示层不得直接操作 PDF cache、Docling raw JSON、parser private payload 或本地路径。
- Dayu 是参考，不是生产 runtime 依赖；禁止直接引入 `dayu-agent`、`dayu.host`、`dayu.engine`。
- Docling 为当前 production path：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`；不做与 `pdfplumber` 的替代路线比较，不做字段抽取 correctness benchmark。
- 当前开发流程采用 CIC-lite：1 份 MVP plan、1 次 plan review；review `ACCEPTED` 后必须进入代码实现，每个 slice 只走 implement -> tests -> diff review。

### 0.3 dayu 本地代码事实

已查看本地仓库 `/Users/maomao/dayu-workspace/dayu-agent/`。以下是代码事实，不是本仓库已实现事实：

- dayu 的稳定分层写在 `dayu/README.md`：`UI -> Service -> Host -> Agent` 是层次，`startup preparation`、`contract preparation`、`scene preparation` 是装配过程，不是新层。
- `dayu/fins/README.md` 明确 Fins 有两条路径：
  - Agent augmentation path：Fins 给 Agent 注入财报读取工具、公司/source/processed/blob 窄仓储和工具服务。
  - Direct operation path：`UI -> FinsService -> Host -> FinsRuntime / pipeline`，覆盖下载、上传、预处理，不经过 Agent。
- Fins 不是 `UI -> Service -> Host -> Agent` 四层中的一层，而是证券财报领域能力包；`FinsService` 是 direct operation 的 Service 入口，`FinsToolService` 是 Fins 内部给 Agent tools 使用的财报读取工具边界。
- `dayu/fins/tools/service.py` 中 `FinsToolService` 负责参数校验、`document_id -> source_kind -> source -> processor` 路由、能力降级和 Processor LRU 缓存；它不是 Host，也不是 UI。
- dayu 仓储协议拆成 `CompanyMetaRepositoryProtocol`、`SourceDocumentRepositoryProtocol`、`ProcessedDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol`、`FilingMaintenanceRepositoryProtocol` 等窄协议，定义在 `dayu/fins/storage/repository_protocols.py`。
- dayu CN/HK 下载链路已有 `PDF -> Docling JSON -> source meta 完成态` 的实际代码：`cn_download_filing_workflow.py` 下载或复用 PDF，转换或复用 Docling JSON，最后提交 source meta；`cn_download_source_upsert.py` 要求完成态 `primary_document` 指向 `_docling.json`。
- dayu 的 `DoclingProcessor` 位于 `dayu/engine/processors/docling_processor.py`，读取 `*_docling.json`，提供 `list_sections`、`read_section`、`search`、`list_tables`、`read_table` 等 processor 能力；`FinsDoclingProcessor` 在 Fins 层继承它并补充金融表格语义。本仓库 `DoclingDocumentStore` 已实现等价的 section/table/search 能力。
- dayu 的 CNINFO downloader 明确只做 discovery / PDF 下载，不写 workspace、不调用 Docling、不生成 document_id；document_id 和落盘由 pipeline 层处理。

### 0.4 事实与推断边界

- 事实：dayu 已经有可参考的 source / blob / processed repository、processor registry、tool service、CN/HK PDF + Docling pipeline。
- 事实：本仓库已实现 DoclingDocumentStore section/table/search 能力、FundDocumentToolService、persistent repository、LLM adapter、信号评分和报告生成；尚未实现 downloader、多 provider matrix 和仓储协议拆分。
- 推断：本仓库最短可行路径应先建立本地年报阅读工具的受控边界和最小端到端 slice，再逐步吸收 dayu 的仓储/处理器/Host 形态。
- 不得推断：本仓库可以直接复制 dayu runtime、可以复用 dayu 的全部 Host / Engine、或者当前样本 PDF 已经具备可生产读取能力。

## 1. 第一性原理判断

基金年报阅读工具要解决的问题不是“让 LLM 看见 PDF”，而是：

1. PDF 是非结构化披露物，包含页眉页脚、跨页表格、章节层级、脚注和排版噪声。
2. LLM 直接读 PDF 或 raw JSON 会扩大幻觉和遗漏风险。
3. Agent 需要的是可枚举、可定位、可边界截断、可审计引用的工具结果。
4. 因此系统必须先把 PDF 变成受控文档模型，再通过工具服务暴露窄能力。

由此推出本仓库最小链路：

```text
PdfSourceProvider
 -> PdfBlobStore
 -> DoclingConverter
 -> DoclingDocumentStore
 -> FundDocumentToolService
 -> Agent read tools
```

这条链路的成功标准是“工具可读、可查、可引用”，不是“能生成基金分析报告”。

## 1.1 Contract 能力分层

Docling JSON 是把 PDF 长期化、结构化、可索引化的文档底座。它不是 Agent / Service 可以直接读取的公共事实源；上层只能通过 `DoclingDocumentStore` 和 `FundDocumentToolService` 取得受控 section、table、search result、locator 和 citation。

`FundDocumentToolService` 是读取 Docling 底座的工具地图。它负责把底层文档结构转换成可枚举、可定位、可截断、可引用的 reading tools；它不理解用户任务，也不执行投资分析。

Service / scene contract 负责把任务拆成受控工具调用流程。Service 可以从 use case 出发选择或编排 contract，但不得绕过工具地图读取 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。

后续 contract 必须按能力层级分开裁决和实现：

```text
reading contract
  只定位证据，返回原文片段、locator、citation 和 trace。

extraction contract
  只从已定位证据中抽受控字段，返回字段 DTO、raw_text 和 citation。

calculation contract
  只基于受控字段和已裁决公式做确定性计算。

report / judgment contract
  后置，必须另开 gate；不得塞进 reading / extraction / calculation slice。
```

当前已实现 / 裁决的 slice 对应关系：

- `fee_rates reading locator` 属于 reading contract。
- `fee_rates value extraction contract` 属于 extraction contract。
- `performance disclosure locator` 属于 reading contract。
- `performance return fields extraction contract`、turnover calculation、`R=A+B-C`、报告章节生成均后置，不得混入 11A。

## 2. 当前设计目标

### 2.1 核心目标

- 支持把一份基金年报 PDF 登记为受控 report/document。
- 保留来源身份：基金代码、年份、报告类型、来源、远端 ID 或本地导入 ID、内容 fingerprint。
- 校验 PDF integrity：Content-Type 或本地等价 media type、PDF magic bytes、非空内容、原子写入。
- 转换为 Docling JSON，并在完成态 document store 中只暴露受控模型，不把 raw payload 交给上层。
- 提供 `FundDocumentToolService`，覆盖：
  - `list_reports`
  - `list_sections`
  - `read_section`
  - `search_document`
  - `list_tables`
  - `read_table`
  - `get_excerpt`
- 工具输出包含 citation metadata 和可用 locator；不得泄漏本地 PDF 路径、cache path、raw Docling payload、URL secret 或 provider secret。
- public tool 失败返回稳定错误类别和安全 message；内部异常不得原样泄漏给 Agent / UI。
- 同时通过离线 `FundDocumentToolService` smoke 和最小 Host / Agent tool loop smoke；只通过离线 ToolService 不构成验收通过。

### 2.2 非目标

- 不做超出已裁决 slice 范围的字段抽取。
- 不做未经裁决的自动报告生成。
- 不做投资判断。
- 不做报告渲染。
- 不做最终投资结论。
- 不做数据仓库晋升。
- 不做发布就绪判定。
- 不直接依赖 `dayu-agent` runtime。

## 3. 目标分层

### 3.1 UI

职责：

- 接收用户输入、展示工具结果或 Agent 回复。
- 只依赖 Service 公共接口。

禁止：

- 直接读取 PDF 文件、PDF cache、Docling JSON。
- 直接调用 parser / converter。
- 直接解释基金年报领域规则。

### 3.2 Service

职责：

- 解释用户请求语义。
- 选择 use case，例如“登记本地年报”“列出报告”“发起阅读会话”。
- 组装 scene / prompt / ExecutionContract，并调用 Host。
- 可以编排 Agent 阅读工具。
- Post-MVP Slice 9A 已裁决为补齐 `FundReadingService` use case boundary：把当前 CLI 中的 local PDF import、repository-backed load、必要时 Docling conversion fallback、Host 调用迁入 Service；CLI 只保留 argparse 和 stdout/stderr 格式化。
- Slice 9A 首批 use case 只覆盖 `import_local_report`、`read_local_report` 和 `list_reports`；输入 DTO 可以接收本地 PDF path，但 path 不得传给 Host/Agent 或进入 public output。

禁止：

- 直接操作 PDF cache、Docling raw JSON、parser raw payload。
- 管理 Host 生命周期细节。
- 实现 Agent tool loop。
- 在 Slice 9A 混入 query routing、`fund-checklist ask`、真实 PDF LLM e2e、UI、多轮会话、反馈式阅读、批量任务、指标计算、字段抽取、自动报告或投资判断。

### 3.3 Host

职责：

- 管理 session / run 生命周期。
- 管理并发、取消、超时、事件、恢复、reply outbox。
- 托管 Agent 或 direct operation。
- Slice 4 当前已实现 `MinimalHost`：只接收 `document_id` 与 `query`，调用 `MinimalFundDocumentAgent.run()` 并返回 `AgentRunResult`。

禁止：

- 理解基金领域知识。
- 解析 PDF / Docling。
- 读取 Fund 文档私有存储。
- 在 Host 层读取 raw PDF、raw Docling JSON、本地路径或 Docling cache path。

### 3.4 Agent

职责：

- Agent 层负责 ToolRegistry / ToolTrace / context budget / tool loop。
- MVP Slice 4 已实现 `MinimalFundDocumentAgent` 的最小 loop：`search_document -> read_section`。
- Post-MVP Slice 5 扩展为 table-aware retrieval / citation loop：先读取命中章节，再通过 `list_tables` / `read_table` 读取同 section、同页或相邻页候选表格，按 query 命中和 proximity 排序；成功时 `answer` 只由 section/table tool result 生成，`citations` 同时包含 section/table citation。
- Post-MVP Slice 8A 已实现 fake/injected LLM tool-loop contract：LLM adapter 只能通过受控 reading tools 取得事实，不得直接读取 repository/private loader、raw Docling JSON 或本地路径。
- Post-MVP Slice 8B 已实现为 DeepSeek real LLM adapter behind existing contract：真实 provider 只能实现 `LlmClientProtocol`，所有输出仍经 8A runner/enforcement；Mimo 已通过 OpenAI-compatible adapter 准入。
- Post-MVP Slice 8C 已实现 opt-in live DeepSeek smoke：默认 pytest no-network，只在 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 且存在 `DEEPSEEK_API_KEY` 时验证一次真实 provider 输出。
- `AgentRunResult` 至少包含 `answer`、`citations`、`tool_trace`、`failure`。
- `ToolTraceEntry` 至少包含 `tool_name`、`arguments`、`result_kind`、`failure_code`。
- `search_document` 无命中时不猜测章节，返回 `AgentRunResult.failure`。

禁止：

- 把 dayu 的 `dayu.host` / `dayu.engine` 作为生产 runtime 直接依赖。
- 绕过 Fund documents / tool service 边界向上层暴露 raw PDF / raw Docling。
- 在 Agent 层直接读取 store 私有字段、raw Docling payload、PDF cache 或本地路径。

### 3.5 Fund 领域能力包

`fund_agent/fund` 不是 `UI -> Service -> Host -> Agent` 四层结构中的一层，而是基金文档领域能力包。它与 Dayu 的 Fins 定位相同：向 Service / Agent 提供受控领域能力，不承担 use case 语义入口、Host run 管理或 Agent tool loop。

职责：

- 实现 PDF source abstraction、blob store、Docling converter、Docling document store、FundDocumentToolService。
- `FundDocumentToolService` 是 Fund 包内部的工具服务边界，负责受控 section / table / search / excerpt / citation 能力。
- 为 Agent tools 提供可枚举、可定位、可截断、可引用的文档读取结果。

与 Service 的关系：

- `FundReadingService` 是 use case / 业务语义入口，负责 query routing、target contract、fee_rates extraction contract 和 Host 调用。
- `FundReadingService` 可以调用 `FundDocumentToolService` 或基于其安全结果编排业务 use case。
- `FundDocumentToolService` 不等同于 `FundReadingService`；前者是领域工具边界，后者是业务用例边界。

禁止：

- 在 Fund 包中理解 UI intent、管理 Host 生命周期或实现 Agent loop。
- 向 Service / Host / Agent / CLI 暴露 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。

## 4. Fund 文档域模型

### 4.1 Report Identity

每份年报必须有稳定身份：

- `fund_code`
- `fund_name`
- `year`
- `report_type`
- `source_kind`
- `remote_id` 或 `local_import_id`
- `content_fingerprint`
- `document_id`
- `share_class`
- `ingest_status`

已裁决规则：

- `document_id` 表示内容身份，用于 public reading tools。
- `document_id` 固定为 ASCII-only，格式为 `fund_code-year-report_type-fingerprint_prefix`。
- `fingerprint_prefix` 使用 `content_fingerprint` 前 16 位 hex。
- `document_id` 不能只靠文件名；文件名可以重复、被人工改名，也可能缺少基金代码或年份。
- `local_import_id` 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入。
- 重复导入相同 PDF 时复用 `document_id`；导入事件可以追加记录。
- `share_class` 为可选 metadata；当前不强制解析，不参与 `document_id`。
- 无法明确 A/C 类时记录 `share_class = null`，不得从文件名或标题猜测。
- 若同一年同 `report_type` 下不同份额类别 PDF 内容不同，`content_fingerprint` 会区分 `document_id`。
- `report_type` 当前仅支持 `annual_report`。
- `semiannual_report` / `quarterly_report` 保留为未来扩展，不进入当前实现。

### 4.2 Source 与 Blob

`PdfSourceProvider` 只负责发现或导入 PDF，并返回 source identity 与 PDF bytes/stream；它不决定 parser。

`PdfBlobStore` 只负责受控落盘、读取和 fingerprint；它不向 UI / Service / Host 暴露本地路径。

### 4.3 Docling 转换与存储

`DoclingConverter` 只负责 `PDF -> Docling JSON`，失败必须分类为 `docling_convert_failed`。

`DoclingDocumentStore` 只保存和读取受控文档模型：

- report summary
- section summary
- section content
- table summary
- table content
- search index 或 searchable text projection
- locator / citation metadata

raw Docling JSON 只能作为 store 内部中间态，不是上层事实源。

### 4.4 Persistent Repository

Post-MVP Slice 6 引入 local persistent repository，用于把已完成的本地年报导入/转换结果登记为可恢复的 report catalog。首个实现只使用 filesystem JSON catalog，不引入 SQLite。

最小路径：

```text
PdfBlobStore
 -> DoclingConverter
 -> DoclingDocumentStore(parser_health passed)
 -> PersistentReportRepository catalog record
 -> repository-backed loader
 -> FundDocumentToolService
```

repository-backed loader 是内部装配层，不是新的 public reading tool。它负责：

- 按 `document_id` 读取 completed catalog record。
- 校验 catalog schema、identity、Docling JSON 引用和 parser_health。
- 构造 `DoclingDocumentStore(identity, json_path)`。
- 将 store 注册给 `FundDocumentToolService`，或返回可注册的 store。

它不得：

- 改变七个 public reading tools API。
- 接受 `local_import_id` 作为 public route。
- 向 Agent / Host / UI 暴露 raw Docling JSON、本地 PDF path、Docling cache path、absolute path 或 `local_import_id`。
- 自动 repair、rebuild 或 reconvert 缺失的 Docling JSON。

Slice 6 最小 catalog record 字段：

- `schema_version`
- `document_id`
- `fund_code`
- `fund_name`
- `year`
- `report_type`
- `share_class`
- `source_kind`
- `content_fingerprint`
- `stored_blob_ref`
- `docling_json_ref`
- parser health summary
- `created_at`
- `updated_at`

`local_import_id` 仍只属于导入审计 metadata，不进入 public tool route；Slice 6 不要求把导入事件历史纳入 catalog public contract。

Failure mapping:

- catalog missing -> `not_found`
- catalog schema incompatible -> `schema_drift`
- catalog identity 与 `document_id` 不一致 -> `identity_mismatch`
- completed record 指向的 Docling JSON 缺失或不可读 -> `unavailable`
- Docling JSON 顶层结构 drift -> `schema_drift`
- parser_health 不通过 -> `parser_health_failed`
- blob fingerprint mismatch -> `integrity_error`

Slice 6 非目标：

- SQLite 或外部数据库。
- catalog schema migration。
- concurrent write locking。
- repair / rebuild / reconvert。
- downloader。
- batch queue。
- delete/update lifecycle。
- true LLM integration。
- release readiness。

### 4.5 Tool Service

`FundDocumentToolService` 是工具边界的唯一入口。它负责：

- 参数校验和标准化。
- document/report 路由。
- processor / store 访问。
- bounded output。
- safe redaction。
- failure classification。
- citation metadata 组装。

它不负责：

- Host session / run。
- UI rendering。
- 自动报告。
- 投资判断。

## 5. 工具契约

### 5.1 list_reports

输入：

- 可选 `fund_code`
- 可选 `year`
- 可选 `report_type`

输出：

- `reports[]`
- `document_id`
- `fund_code`
- `fund_name`
- `year`
- `report_type`
- `source_summary`
- `content_fingerprint`

### 5.2 list_sections

输入：

- `document_id`

输出：

- `sections[]`
- `section_ref`
- `title`
- `level`
- `parent_ref`
- `locator`
- `preview`

### 5.3 read_section

输入：

- `document_id`
- `section_ref`
- 可选 `max_chars`

输出：

- `bounded_text`
- `section_ref`
- `title`
- `locator`
- `citation`
- `truncated`

### 5.4 search_document

输入：

- `document_id`
- `query`
- 可选 `within_section_ref`
- 可选 `max_results`

输出：

- ranked hits
- bounded excerpt
- `section_ref`
- locator
- citation

### 5.5 list_tables

输入：

- `document_id`
- 可选 `within_section_ref`

输出：

- `table_ref`
- `caption`
- `section_ref`
- `locator`
- row / column summary

### 5.6 read_table

输入：

- `document_id`
- `table_ref`
- 可选 `max_rows`

输出：

- table content
- row / column summary
- `section_ref`
- locator
- citation

### 5.7 get_excerpt

输入：

- `document_id`
- locator 或 section/table ref + offset

输出：

- bounded excerpt
- locator
- citation

## 6. 失败分类

公共失败类别沿用 `AGENTS.md`：

| 类别 | 含义 | 行为 |
| --- | --- | --- |
| `not_found` | 来源正常响应但没有目标基金/年份年报 | 可终止或按显式策略换源 |
| `unavailable` | 网络、超时、服务端或本地依赖临时不可用 | 可重试或按显式策略换源 |
| `schema_drift` | 官方来源响应结构偏离契约 | fail-closed |
| `identity_mismatch` | 返回候选与基金代码、年份、报告类型矛盾 | fail-closed |
| `integrity_error` | PDF Content-Type、文件头或写入内容完整性失败 | fail-closed |
| `docling_convert_failed` | PDF 到 Docling JSON 转换失败 | fail-closed |
| `parser_health_failed` | Docling JSON 无可用章节/表格/文本定位 | fail-closed |
| `llm_malformed_response` | 真实 LLM adapter response 结构不可解析 | fail-closed |

新增实现约束：

- fallback 必须由失败分类显式驱动。
- 不得用 fallback 掩盖 `schema_drift`、`identity_mismatch`、`integrity_error`。
- parser health 至少验证：存在可读文本、章节或可替代章节索引、表格索引可安全为空但不能破坏章节读取。

## 6.5 审计管道架构概述

审计管道采用三层递进架构：

1. **程序审计（权重 30%）**：确定性规则检查，覆盖结构化字段完整性、数据一致性、格式合规。
2. **LLM 审计（权重 70%）**：定性分析检查，覆盖论述逻辑、证据引用、结论合理性。
3. **LLM 复核**：对修复后报告进行最终复核。

违规分类覆盖 4 类 22 项：

- **P1–P4**：程序性违规（Programmatic）—— 数据缺失、字段格式错误、计算错误、引用断裂
- **E1–E5**：证据性违规（Evidential）—— 无 citation、citation 不匹配、证据不充分、数据源错误、引用过期
- **S1–S7**：结构性违规（Structural）—— 章节缺失、章节顺序错误、标题不匹配、表格缺失、表格格式错误、段落重复、内容越界
- **C1–C6**：内容性违规（Content）—— 事实错误、论述矛盾、逻辑跳跃、过度推断、遗漏关键信息、表述模糊

评分与修复阈值：

- **≥80 分**：通过，报告可交付
- **50–79 分**：PATCH，程序性修复后重新审计
- **<50 分**：REGENERATE，重新生成报告

修复策略（每种最多 3 次）：

- **PATCH**：针对性修复单项违规，不重新生成整章
- **REGENERATE**：重新生成整章报告
- **NONE**：标记为已知限制，不修复

## 7. dayu 可迁移部分

### 7.1 可迁移为设计参考

- 窄仓储协议拆分：source、processed、blob、company/meta、maintenance。
- `ToolService -> ProcessorRegistry -> Processor` 的读取路径。
- `PDF -> Docling JSON -> primary_document` 的完成态约束。
- source meta 中显式记录 fingerprint、version、ingest status、primary document。
- downloader 不写 workspace、不调用 parser、不生成最终持久化事实。
- processor 返回 section/table/search/read 的受控结构。

### 7.2 不可直接迁移

- 不直接依赖 dayu `Host` / `Engine` / `FinsRuntime`。
- 不直接复制 dayu 代码，除非经过 license/compliance gate。
- 不把 dayu 股票财报的 `ticker` / `filing` / `form_type` 原样套到基金年报。
- 不把 dayu 的 SEC / CN / HK 市场规则当成基金年报规则。

### 7.3 需要重新设计的部分

- 基金年报 source identity：基金代码、基金名称、年份、报告类型、基金份额类别的处理。
- 基金 PDF 中章节层级、目录页、表格页码、跨页表格的 locator 表达。
- report_type 枚举。

## 8. 已裁决设计口径

### 8.1 数据源范围

当前只支持本地 `基金年报/` PDF 导入。官方来源 discovery 不进入当前范围。

### 8.2 Runtime 范围

当前覆盖以下验证路径：

- 离线工具验证（FundDocumentToolService）
- Agent loop 验证
- Service 层受控 profile routing
- 多年度聚合（3-5 年 bounded coverage）
- 确定性信号评分（6 指标，135→100 归一化）
- 8 章分析报告生成
- 三层审计管道（程序+LLM+复核，4 类 22 项）

不允许只以 `FundDocumentToolService` 离线测试通过收口。验收必须同时通过：

1. `FundDocumentToolService` 离线工具 smoke。
2. 最小 Host / Agent tool loop smoke。

最小 Host / Agent loop 的验收问题固定为：

```text
用户问题: "在这份年报里搜索基金经理，并读取相关章节"
```

期望 trace：

```text
1. Agent 调用 search_document(document_id, query="基金经理")
2. Agent 拿到 section_ref / locator
3. Agent 调用 read_section(document_id, section_ref)
4. 最终回答只引用 tool result，不泄漏本地路径或 raw Docling JSON
```

MVP Slice 4 实现为 deterministic minimal loop；Post-MVP Slice 5 在该 loop 上增加 table-aware retrieval。当前已支持 DeepSeek + Mimo 真实 LLM adapter；字段抽取和自动报告已通过正式 Slice 准入。`ToolFailure` 传播到 `AgentRunResult.failure`，不向 Host/UI 抛内部异常。

Post-MVP Slice 5 的 table-aware loop 仍属于阅读工具层泛化，不是完整 LLM Agent 真源系统：

- LLM/Agent 输入真源是受控 tool result + locator/citation。
- raw Docling JSON、本地 PDF path、Docling cache path、`local_import_id` 仍不得进入 Agent / Host / UI 输出。
- table-aware retrieval 可泛化到章节 + 表格里的公开披露信息问答，例如基金经理、持仓、资产配置、费用等；不得扩展成字段抽取 correctness benchmark、自动报告或投资判断。
- 当没有相邻或相关表格时，Agent 保持 section-only answer，不硬拼不相关表格。

Post-MVP Slice 8A 已实现 fake/injected contract，不接真实 provider：

- 最小协议为 `LlmClientProtocol`、`FakeLlmClient`、`ToolCall -> ToolResult -> FinalAnswer`。
- 允许工具仅限 `search_document`、`read_section`、`list_tables`、`read_table`、`get_excerpt`。
- LLM adapter 不得接触 repository/private loader、raw PDF、raw Docling JSON、本地路径、Docling cache path、URL secret、parser private payload 或 `local_import_id`。
- 最终 answer 必须只来自 tool result；`citations` 必须非空；每个关键事实至少有 section 或 table citation。
- 无 citation 回答、未知工具、越权工具或无证据最终回答必须 fail-closed。
- Slice 8A 不新增用户 CLI 参数，不新增 `fund-checklist ask`；CLI 暴露 LLM 模式需另开裁决。
- Slice 8A 不做 OpenAI / Claude / 外部模型 API、provider auth、streaming、rate limit、cost tracking、prompt framework、字段抽取、自动报告或投资判断。

Post-MVP Slice 8B 的 DeepSeek adapter 已按 8A contract 后置实现：

- 目标是实现 DeepSeek OpenAI-compatible provider adapter，例如 `DeepSeekLlmClient`，并让它实现既有 `LlmClientProtocol`。
- provider response 只能被解析为受控 `ToolCall` 或 `FinalAnswer`；解析后必须进入 8A `LlmToolLoopRunner`。
- provider prompt/request 只能包含系统约束、用户问题和受控 tool schema，不得包含 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、URL secret、parser private payload 或 `local_import_id`。
- `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 只能从环境变量读取；`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- API key 不得写入配置文件、测试 fixture、trace、日志或 public output。
- 不新增 SDK 依赖；使用 adapter + injected transport。若实现必须使用官方 SDK，需另行裁决 `pyproject.toml` / `uv.lock`。
- 默认 pytest 不访问网络，不读取真实 API key；live provider smoke 必须显式 opt-in。
- provider error 必须稳定 fail-closed：key 缺失、auth、network、timeout、rate limit 映射为 `unavailable`；malformed response 映射为 `llm_malformed_response` 或等价稳定 failure code。
- 真实 provider 的未知工具、越权工具、无 citation final answer 或无 evidence final answer 仍复用 8A enforcement。
- Slice 8B 不新增 `fund-checklist ask`、streaming、多 provider matrix、prompt framework、richer QA/eval、字段抽取、自动报告或投资判断。

Post-MVP Slice 8C 的 live smoke 已实现为只验证真实 DeepSeek provider 的最小可用性：

- 默认 pytest 不联网；live smoke 必须由 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 显式启用。
- `DEEPSEEK_API_KEY` 缺失时 skip，不失败。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，可覆盖。
- `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，可覆盖。
- live smoke 使用 fake/in-memory tool service 或现有测试 fixture，不跑真实 PDF、不跑 CLI、不触发 Docling conversion、不使用 repository-backed loader。
- live smoke 最多 1 个 live run，timeout 300 秒，最多 1 次 retry，不做批量问题。
- opt-in 后 provider 返回不可解析、8A enforcement fail、network/429/auth error 均为 test fail。
- pytest output、trace、assert message 不得打印 API key；不得记录 provider raw response 到文件，不新增 artifact。
- Slice 8C 不修改 production adapter；若 live test 暴露解析 bug，必须先停止并报告。
- Slice 8C 不做 `fund-checklist ask`、真实 PDF/Docling/repository e2e、多 provider、streaming、retry/backoff hardening、richer QA/eval、prompt injection hardening、自动报告或投资判断。

Post-MVP Slice 9A 裁决为 Service 层 use case boundary，不做能力泛化：

- 新增 `fund_agent/service/`，实现 `FundReadingService` 和受控 request/result DTO。
- Service 已负责参数校验、local PDF import、repository-backed load、必要时 Docling conversion fallback、Host 调用和稳定失败传播。
- CLI 只做参数解析和 plain text 输出格式化，不再直接装配 `LocalPdfSourceProvider`、`FilesystemReportRepository`、`DoclingConverter`、`FundDocumentToolService` 或 `MinimalHost`。
- Service 调用 Host 时只传 `document_id` 和 `query`；Host 不接收 PDF path、work dir、repository、converter、Docling JSON path 或任何 private loader。
- catalog 有 completed report 时复用；catalog missing 时允许 import + convert；catalog record 指向的 Docling JSON 缺失或不可读时按既有 Slice 6 口径 fail-closed，不自动 repair / rebuild / reconvert。
- Service 不吞并下层失败；`DocumentToolError` / `ToolFailure` 保持稳定 failure code，CLI classified failure 仍返回 exit code `2`。
- 本 slice 不做 query normalization / synonym routing；`前十大持仓 -> 股票投资明细` 另开 gate。
- 本 slice 不新增 `fund-checklist ask`、不把 DeepSeek 接入真实 PDF CLI、不改 8A/8B/8C contract、不做 UI。

Post-MVP Slice 9B 裁决为 evidence retrieval substrate，不做语义路由：

- 目标是让 ToolService / Store 受控检索基底覆盖 section text、table caption 和 bounded table rows。
- `search_document` 可以返回 table-backed evidence candidates / search results，但必须保留 locator、citation、bounded output 和 redaction 约束。
- Slice 9B 不扩展 failure code；命中颗粒度只落在成功侧 metadata，不把表格检索失败细分成新错误码。
- `search_document` 无 evidence candidate 时仍返回空 tuple；Agent 将空 search result 转成 `not_found` 的既有行为不变。
- 当 query 只出现在表格 caption 或 bounded table rows 中、而不在 section 正文中时，`search_document` 仍应能返回带 `table_ref`、locator、citation、bounded excerpt 和 `match_kind` / 等价 `matched_field` 的 table-backed result。
- table-backed result 的 `match_kind` / `matched_field` 取值必须是受控枚举，至少区分 `section_text`、`table_caption`、`table_row` 或等价组合；不得引入 confidence / semantic score。
- table row 命中 excerpt 必须 bounded，只返回命中行或有限上下文，不返回整表；排序必须 deterministic / reproducible。
- 失败分类沿用既有稳定 code：`schema_drift`、`not_found`、`unavailable`；不新增 `table_caption_not_found`、`table_row_not_found`、`ambiguous_table_match` 等细分错误码。
- 9B 不修改 deterministic Agent retrieval policy，不要求 Agent 自动 `read_table`，不要求 CLI table-only query 成功；table-backed result 的 Agent 消费另开 Slice 9C。
- 9B 不做 query normalization / synonym routing，不把 `前十大持仓` 映射为 `股票投资明细`。
- 9B 不接 LLM、embedding 或外部搜索服务；不执行 template-informed intent routing、chapter contract execution、calculation framework、report audit、字段抽取、自动报告或投资判断。

Post-MVP Slice 9C 裁决为 table-backed first-hit consumption，不做表格选择策略泛化：

- 9C 只在 `search_document` first hit 是 high-certainty table-backed result 时直接消费 `table_ref`。
- high-certainty 只用确定性 exact containment 判断：`match_kind == table_row` 且 query 原文出现在 excerpt 中；或 `match_kind == table_caption` 且 query 原文出现在 caption/excerpt 中。
- high-certainty table-backed first hit 的工具顺序为 `search_document -> read_section -> read_table`；不调用 `list_tables` 进行表格发现。
- first hit 不是 table-backed result、table-backed hit 不满足 high-certainty、或 table-backed hit 缺少 `table_ref` 时，沿用既有 section-first table-aware 路径或稳定失败语义。
- answer 必须 table-first：section title / table caption 只作来源上下文，bounded table rows 是主体内容；不得做 section 摘要或解释性综合。
- citations 至少包含 table citation；可以保留 section citation。
- 9C 不扫描 top-N、不做二次排序、不做歧义消解、不做 query intent 分类、不做 synonym routing、不接 LLM 判断表格相关性。
- 9C 不新增 `fund-checklist ask`、CLI 参数、embedding、外部搜索、template contract execution、calculation framework、字段抽取、自动报告或投资判断。

Post-MVP Slice 9D 裁决为 Service 层 controlled query profile routing，不做开放语义理解：

- routing 位置在 Service 层；Store / ToolService / Agent 不承担业务别名理解。
- 不修改 `search_document` public contract；`search_document` 仍只接收单个 query。
- Service routing 把用户 query 映射为最多 3 个受控 candidate queries，按顺序调用既有 Host/Agent 路径，返回第一个成功的 Agent result。
- candidate 顺序必须包含原始 query；最终 citation 必须来自实际命中的 candidate 对应的 section/table tool result，不引用 alias 本身。
- trace 可记录实际使用的 query candidate；不新增 CLI 输出格式。
- failure 语义保持稳定：所有 candidate 都无命中时仍为 `not_found`；routing 配置异常为 `schema_drift`；ToolService 内部异常仍为 `unavailable`；不新增 `synonym_not_found` 等错误码。
- 首批 controlled profiles 仅三类：
  - `holdings_top10`: alias 为 `前十大持仓` / `重仓股` / `持仓明细`；candidate queries 为原始 query、`股票投资明细`、`前十名股票投资明细`。
  - `asset_allocation`: alias 为 `资产配置` / `资产组合`；candidate queries 为原始 query、`期末基金资产组合情况`、`基金资产组合情况`。
  - `expenses`: alias 为 `费用` / `管理费` / `托管费`；candidate queries 为原始 query、`基金费用`、`报告期内基金费用`。
- 9D 不做自动分词、同义词扩散、开放语义理解、query intent 分类、embedding、LLM intent、top-N rerank、template contract execution、calculation framework、字段抽取、自动报告或投资判断。
- 9D 真实 CLI smoke 只证明 controlled alias routing：`--query 前十大持仓` 能走到 `股票投资明细`；不证明泛化问答。

Post-MVP Slice 9E 裁决为 Service routing attempts audit，不做新召回能力：

- 9E 只为 9D 的 Service routing 增加最小审计记录，回答“Service 到底尝试了哪些 query，哪个 attempt 成功或最终失败”。
- `ReadLocalReportResult` 可增加 `routing_trace` 字段，类型为 `tuple[QueryRouteAttempt, ...]` 或等价只读结构。
- 每个 `QueryRouteAttempt` 只记录原始事实：`query`、`profile_name`、`result_kind`、`failure_code`。`result_kind` 仅允许 `success` / `failure`；成功 attempt 的 `failure_code` 必须为 `None`。
- 不存 `selected_query`、`selected_index`、rationale、score、confidence、candidate_results 或 evidence links；`selected_query` / `selected_index` 只能从第一个 success attempt 推导，避免派生值与 attempts 不一致。
- `routing_trace` 是 Service-level audit metadata，不暴露给 Agent，不并入 Agent `tool_trace`。
- CLI 默认输出格式不变；citations、answer、failure code、`search_document` contract、Agent policy、Store search 均不变。
- 9E 不新增或修改 controlled profiles，不做自动分词、同义词扩散、开放语义理解、query intent 分类、embedding、LLM intent、top-N rerank、template contract execution、calculation framework、字段抽取、自动报告或投资判断。

Post-MVP Slice 9F 裁决为 controlled profile real-smoke regression，不新增能力：

- 9F 只把 9D/9E 的三类 controlled profiles 在仓库本地真实 PDF 上固化为回归验证。
- 真实样本范围仅限当前本地 PDF：`基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf`；样本缺失是 blocker，不得用 fake PDF 替代真实 smoke。
- smoke queries 固定为 `前十大持仓`、`资产配置`、`费用` 三条；不同时覆盖所有 alias，不扩大 profile 矩阵。
- 每条 smoke 最小 expected evidence：`前十大持仓` -> `股票投资明细` 或 `前十名股票投资明细`；`资产配置` -> `期末基金资产组合情况` 或 `基金资产组合情况`；`费用` -> `基金费用` 或 `报告期内基金费用`。
- CLI smoke 只要求 exit code `0`、answer 包含 expected evidence 文本、Citations 存在、Trace 存在、CLI 默认输出不包含 `routing_trace`。
- 9F 不新增 profile、不新增 alias、不改 routing 规则、不改 `search_document` contract、不改 Agent/Store/ToolService、不改 CLI 输出格式、不做 benchmark 或 correctness evaluation。
- 9F 不做开放语义理解、embedding、LLM intent、top-N rerank、template contract execution、calculation framework、字段抽取、自动报告或投资判断。

Slice 9F 真实 smoke 结论为 `BLOCKED_BY_DESIGN` / `NOT_ACCEPTED`：

- `前十大持仓`: exit code `0`；answer 包含 `股票投资明细`；Citations / Trace 存在；无 `routing_trace`。
- `资产配置`: exit code `0`；answer 命中 `3.2.1 基金份额净值增长率...`，缺少 expected evidence `期末基金资产组合情况` / `基金资产组合情况`。
- `费用`: exit code `0`；answer 命中 `3.1 主要会计数据和财务指标`，缺少 expected evidence `基金费用` / `报告期内基金费用`。
- Root cause 是 controlled alias original-query false positive；更一般地，keyword-level routing success 不能证明 disclosure target success。
- `canonical-first` 不列为 10A 候选策略，也不作为 9F 修复方案；它仍是 keyword-level strategy，只改变候选顺序，不能建立 disclosure target success 契约。
- 暂不引入 profile-specific evidence validation；该路线会引入 expected title pattern、section/table validator、score/confidence 或新 failure taxonomy，复杂度高，容易造成 doc truth drift。

Post-MVP 10A 裁决为 Controlled disclosure target contract：

- 10A 仍放在 Service 层；Store / ToolService / Agent 不承担业务 profile 判断。
- 10A 目标不是新增 synonym，而是为受控 profile 定义 disclosure target id、allowed evidence kind、acceptable section/table title family、expected citation kind 和 fail-closed semantics。
- 10A 必须区分 query keyword hit 与 disclosure target hit；不能把 exit code `0` 或任意 answer/citation 当作目标披露对象成功。
- 10A 不使用 `canonical-first`，不做开放语义理解、embedding、LLM intent、top-N rerank、profile-specific complex validators、template contract execution、calculation framework、字段抽取、自动报告或投资判断。

Slice 10A 已经 MiMo review `ACCEPTED`：

- `前十大持仓`: exit code `0`；evidence 为 `股票投资明细`；Citations / Trace 存在。
- `资产配置`: exit code `0`；evidence 为 `期末基金资产组合情况`；Citations / Trace 存在。
- `费用`: exit code `2`；`failure_code=not_found`；target contract fail-closed，没有把无关章节误判为成功。
- 费用在当前 9D candidate 下 target-unmatched 是预期设计结果，不是 10A blocker。

Post-MVP 10B 裁决为 fee_rates reading locator：

- 10B 只做阅读定位和 citation，不抽取费率数值，不计算显性成本小计，不计算扣费后收益率。
- `expenses` profile 在 10B 改名 / 收窄为 `fee_rates`，`target_id` 为 `fee_rates`；旧 `expenses` 语义过宽，容易覆盖其他费用、交易费用、审计费用、所得税费用、佣金费率等对象。
- `fee_rates` 的目标 disclosure sections 固定为三类：`基金管理费`、`基金托管费`、`销售服务费`。
- `acceptable title family` 固定为：`基金管理费`、`基金托管费`、`销售服务费`。
- 当前真实样本已存在三类披露，因此 10B smoke 对该样本要求三项目标全命中；不引入 `partial_success` 或新 failure taxonomy。
- `fee_rates` aliases 可包含 `费用`、`费率`、`管理费`、`托管费`、`销售服务费`；alias 只用于进入 profile，不作为 evidence 成功条件。
- controlled candidate queries 固定为原始 query、`基金管理费`、`基金托管费`、`销售服务费`；不把单独 `费率` 作为 evidence candidate。
- Service 层可以对同一 profile 执行多个 target queries，并把多个安全 Agent result 聚合为一个 answer；每个 citation 必须来自实际命中的 section/table。
- 10B 不修改 `search_document` public contract，不把业务 profile 判断下沉到 Store / ToolService / Agent，不改变 CLI 输出格式。
- 10B 不做开放语义理解、自动分词、同义词扩散、embedding、LLM intent、top-N scan、rerank、歧义消解、字段抽取、自动报告或投资判断。

Slice 10B 已经 MiMo review `ACCEPTED`：

- `费用`: exit code `0`；answer 同时包含 `基金管理费`、`基金托管费`、`销售服务费`。
- Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
- 10B remaining blocking risk: none。
- 10B 仍只完成 fee_rates 阅读定位；管理费率、托管费率、销售服务费率等字段值抽取后置，不属于 10B。

Post-MVP 10C 裁决为 fee_rates value extraction contract：

- 10C 是字段抽取 contract，不再属于纯阅读定位；仍必须通过 Service 边界消费 10B 已定位的安全章节 / citation，不得读取 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。
- 10C 字段范围只包含三项：`management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate`。
- 10C 不抽取 `nav_growth_rate`、`benchmark_return_rate`、`turnover_rate`，不计算显性成本小计、总成本、扣费后收益率、年化收益率或 `R=A+B-C`。
- 10C 口径固定为当前报告期适用的年费率；不是当期发生金额，不是历史调整前费率，不做历史期间加权。
- 10C 必须处理份额类别口径：A 类销售服务费为不收取，C 类销售服务费为年费率；用户未指定 share class 时，返回 fund-level fee policy 中 A / C 两类口径，不猜默认份额。
- 10C 遇到历史调整文字时，只抽取当前适用费率，并保留原文 citation；不得把调整前费率当成当前费率。
- 10C 数值格式固定为受控 DTO 字段：`field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`；`decimal_percent_text` 保持 `"1.20%"` 形式，`period` 固定为 `"year"`，不先转成 `0.012`。
- 10C 失败语义不新增 failure code：字段未找到为 `not_found`；候选章节存在但无法唯一抽取为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10C 可新增受控 extraction DTO 和 Service 方法 / use case；不得修改 `search_document` public contract，不得改变 Agent / Store / ToolService 职责边界。
- 10C 暂不改变 CLI 默认输出格式；优先在 Service / tests 层验证结构化字段抽取，CLI 仍可保持 10B 的原文 answer / citation。
- 10C 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、template contract execution、chapter contract execution、自动报告或投资判断。

Slice 10C 已经 MiMo review `ACCEPTED`：

- Service 层已实现 fee_rates 三字段抽取 contract。
- 抽取字段仍只限 `management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate`。
- 真实 CLI smoke 使用 `.fund_checklist_cli_smoke_10c`，`费用` exit code `0`；output 包含 `基金管理费`、`基金托管费`、`销售服务费`；Citations / Trace 存在；CLI 默认输出不暴露 `routing_trace`。
- 10C remaining blocking risk: none reported。
- 10C 没有进入净值增长率、基准收益率、换手率、成本计算、`R=A+B-C`、模板执行、自动报告或投资判断。

Post-MVP 10D 裁决为 performance return fields extraction contract：

- 10D 目标是在 11A 已定位的 performance disclosure table 中抽取受控字段，不重新做开放检索。
- 首批字段只允许 `nav_growth_rate` 和 `benchmark_return_rate`。
- 首批 period 裁决为 `past_1_year`，对应真实样本表格行标题 `过去一年`；不得把它命名为 `report_year` 或年度 2024。
- 10D 不抽取近 3 年、近 5 年、成立以来、年度序列表或图表数据；后续 period 必须另开裁决。
- 10D 不抽取 `excess_return`、`annualized_return`、`max_drawdown`、`volatility`、`sharpe`、`tracking_error`、`turnover_rate`。
- 10D 不计算 `A = R - B`、`R = A + B - C`、显性成本小计、总成本、扣费后收益率、年化收益率或同类中位数。
- share class 口径：用户未指定 share class 时不得猜默认份额；可返回所有可唯一识别 share class 的 `past_1_year` DTO。若 share class 无法从表格上下文唯一识别，则 fail-closed 为 `not_found`。
- 若某个 share class 没有 `过去一年` 行，不得合成或外推该 share class 的 `past_1_year` 字段。
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`。
- `decimal_percent_text` 保持原文百分号格式，例如 `"17.32%"`；不先转为小数。
- 数据源只允许来自 11A acceptable title family：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`。
- 10D 必须 table-first：目标字段必须来自 table citation；section-only evidence 不足以抽字段。
- 列标题必须能唯一匹配 `份额净值增长率` / `基金份额净值增长率` 和 `业绩比较基准收益率`；行标题必须唯一匹配 `过去一年`。
- 失败语义沿用现有 failure code：目标表格未找到、目标列缺失、period 行缺失、share class 无法区分、数值无法唯一抽取均为 `not_found`；extractor 配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10D 可新增受控 extraction DTO 和 Service 方法 / use case；不得修改 `search_document` public contract，不得改变 Agent / Store / ToolService 职责边界。
- 10D 暂不改变 CLI 默认输出格式；字段 DTO 先在 Service / tests 层验证，CLI 仍保持阅读 answer / citation / trace。
- 10D 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、template contract execution、chapter contract execution、自动报告或投资判断。
- 当前样本年报未直接披露 `turnover_rate`；后续不做 `turnover_rate` locator，也不把股票买入 / 卖出金额、投资组合重大变动或股票投资明细包装成换手率 evidence。若未来需要换手率，必须另开 calculation / external-data gate，先裁决公式、数据源、期间、基金资产净值口径、失败语义和 citation。

Slice 10D 已经 MiMo review `ACCEPTED`：

- Service 层已实现 performance return fields extraction contract。
- fake multi-table cited case 可返回 A / C 两类 `nav_growth_rate` 和 `benchmark_return_rate`，`period=past_1_year`，`raw_text` 存在，citation 均为 table locator。
- 已覆盖同 section 未被引用表格的回归：10D 只消费 11A result 中实际 cited table，不扫描 sibling tables。
- 当前真实 PDF Service extraction 在 11A 引用的 table 不含 `过去一年` 时 fail-closed；不会绕过 citation 去扫描 sibling tables。
- 10D remaining blocking risk: none reported。剩余非阻塞风险是：真实 PDF 字段抽取成功依赖 11A locator 引用到实际包含 `过去一年` 的 performance table。
- `past_1_year` 是 10D 底层抽取能力，对应年报表格原文 `过去一年`；它不作为后续主分析口径扩展。用户分析语义中，“2024 年度”比“过去一年”更自然；“过去 5 年”应理解为多个自然年度或明确年度序列，而不是 10D 的 `past_1_year` 行。
- 10D 没有进入 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。

Post-MVP 10E 裁决为 annual performance returns source decision：

- 10E 不是字段抽取实现 slice，而是 source decision slice。
- 10E 目标是裁决“年度业绩数据”应来自哪个公开披露位置，避免继续围绕 `past_1_year` 修 citation specificity。
- 10E 首批只回答 source decision，不新增 DTO、不抽值、不计算、不改 CLI。
- 10E 是 docs-only slice；预期写入只限 `docs/design.md` 和 `docs/implementation-control.md`，除非另行裁决，不修改 Python 代码、测试或 README。
- 候选来源限定为：
  - title-family matched performance comparison table：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`
  - 管理人报告 / 报告期内基金的业绩表现文字，例如“本报告期基金份额净值增长率为...同期业绩比较基准收益率为...”
  - `自基金合同生效以来基金每年净值增长率及其与同期业绩比较基准收益率的比较` 年度图 / 表
- 10E 不扩大到基金净值表现图、第三方平台、净值数据库、季报 / 半年报、基金合同或招募说明书。
- source 可用性判定标准：能定位到稳定章节 / 表格 / 文本；能给出 citation；能表达自然年度或报告期年度；能区分 A/C 份额或明确 fund-level；不依赖图像解析 / OCR；不依赖模型猜字段。
- 10E source 类型固定为 `table`、`text`、`chart_or_image`、`unsupported`。
- 年度语义固定为自然年度 / 报告期年度，例如 `2024`；不再把 `过去一年` 作为主分析口径。
- 本地样本核验范围固定为 `基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf` 及既有 `.fund_checklist_cli_smoke_*` Docling JSON；smoke artifact 不纳入提交。
- 样本核验结论：
  - title-family matched performance comparison table 在 2024 年度报告第 6 / 7 页可定位到稳定表格；标题为 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`。样本中的章节编号为 `3.2.1`，但编号不得作为 contract；只可作为样本观察。
  - 该表格 source 类型裁决为 `table`，是后续年度业绩 deterministic extraction 的 primary source。
  - 管理人报告 / 报告期内基金的业绩表现文字可定位到 stable text，source 类型为 `text`；但其位置和句式可能随年份变化，因此仅作为 secondary reference，不作为 10F 首批 extraction source。
  - `自基金合同生效以来基金每年净值增长率及其与同期业绩比较基准收益率的比较` 在当前样本中表现为图 / 图片，source 类型为 `chart_or_image`，不进入当前 deterministic extraction。
- 10E source decision：选择 title-family matched performance comparison table。年度业绩数据当前应来自 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` 标准披露表；不得依赖 `3.2.1` 章节编号。
- 后续推荐：
  - 后续可开 10F annual performance table extraction from title-family matched table。
  - 管理人报告年度文字后置为 secondary reference，不作为 10F fallback。
  - 年度图 / 图片不得进入抽取；除非另开 chart/OCR gate，否则不做 annual performance chart extraction。
- 10E 不做 `past_1_year` citation specificity，不做 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。

Post-MVP 10F 裁决为 annual performance table extraction from title-family matched table：

- 10F 目标是从 title-family matched performance comparison table 中抽取年度收益字段。
- 10F 不依赖章节编号；样本中的 `3.2.1` 只是观察值，不能写入 public contract、locator contract 或测试断言。
- source title family 固定为：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`。`基金净值表现` 可作为上层 section context，但不能单独作为字段抽取表成功条件。
- table signature 必须包含：`source_period_label = 过去一年`、`份额净值增长率` / `基金份额净值增长率` 列、`业绩比较基准收益率` 列。
- 年度语义裁决为：`report_year = request.year`，`source_period_label = 过去一年`。用户 / DTO 层表达为 `2024` 等自然年度，citation / raw_text 必须保留原文 `过去一年`。
- 首批字段只抽 `annual_nav_growth_rate` 和 `annual_benchmark_return_rate`。
- 10F 不抽标准差、超额收益、年度序列、近 3 年 / 近 5 年、成立以来、图表数据或管理人报告文字。
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`report_year`、`source_period_label`、`share_class_scope`、`raw_text`、`citation`。
- share class 口径：用户未指定 share class 时，返回所有可唯一识别的 share class DTO。
- partial-by-share-class 允许；partial-by-field 不允许。某个 share class 同时具备两个字段则返回该 share class；某个 share class 缺任一字段则不返回该 share class；若全部 share class 都不完整则整体 `not_found`。
- 管理人报告文字不作为 10F fallback；不得用文字披露补齐缺失 share class、缺失行或缺失字段。
- 失败语义沿用现有 failure code：目标 title-family table 未找到、table citation 缺失、`过去一年` 行缺失、目标列缺失、share class 无法识别、某 share class 字段不完整且无其它完整 share class，均为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10F 不改 CLI 默认输出；字段 DTO 先在 Service / tests 层验证。
- 真实 PDF 验收必须证明至少 A 类可从 2024 年度报告标准披露表抽取：`annual_nav_growth_rate = 17.32%`，`annual_benchmark_return_rate = 14.45%`。C 类是否返回取决于标准披露表是否存在完整 `过去一年` 行，不得外推或 fallback。
- 10F 不做 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。

Slice 10F 已经 MiMo review `ACCEPTED`：

- Service 层已实现 annual performance table extraction from title-family matched table。
- 真实 PDF annual DTO：
  - `annual_nav_growth_rate`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`decimal_percent_text=17.32%`，table citation `table-0010`。
  - `annual_benchmark_return_rate`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`decimal_percent_text=14.45%`，table citation `table-0010`。
- 10F remaining blocking risk: none reported。
- 10F 没有依赖章节编号，没有使用管理人报告文字 fallback，没有进入 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。

Post-MVP 10G 裁决为 annual excess return disclosed-field extraction：

- 10G 目标是从 title-family matched performance comparison table 中抽取年报显式披露的年度超额收益字段。
- 10G 不做 `annual_nav_growth_rate - annual_benchmark_return_rate` 计算；不得把结果表述为系统计算值。
- 10G source title family 沿用 10F：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`。不得依赖样本章节编号 `3.2.1`。
- 10G table signature 必须包含：`source_period_label = 过去一年`、`份额净值增长率` / `基金份额净值增长率` 列、`业绩比较基准收益率` 列，以及显式披露列 `①－③`。
- 10G 字段固定为 `annual_excess_return`，语义为年报表格中直接披露的 `份额净值增长率 - 业绩比较基准收益率` 对应列值。
- DTO 字段固定为：`field_name`、`decimal_percent_text`、`report_year`、`source_period_label`、`share_class_scope`、`source_column_label`、`raw_text`、`citation`。
- 固定 DTO 口径：`field_name=annual_excess_return`，`report_year=request.year`，`source_period_label=过去一年`，`source_column_label=①－③`。
- `decimal_percent_text` 保持原文百分号格式；不先转成小数，不重新计算，不做四舍五入。
- share class 口径沿用 10F：用户未指定 share class 时，返回所有可唯一识别且具备完整 `过去一年` / `①－③` 数据的 share class DTO。
- partial-by-share-class 允许；某 share class 缺 `过去一年` 行、缺 `①－③` 列值或无法唯一识别时，不返回该 share class；若全部 share class 都缺失则整体 `not_found`。
- 管理人报告文字、年度图 / 图片、第三方数据、10F 已抽取的 nav / benchmark 字段都不得作为 10G fallback。
- 失败语义沿用现有 failure code：目标 title-family table 未找到、table citation 缺失、`过去一年` 行缺失、`①－③` 列缺失、目标值无法唯一抽取、share class 无法识别或全部 share class 缺失，均为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10G 不新增 `calculation_error`、`formula_missing`、`partial_success` 或新的 failure taxonomy。
- 10G 不改 CLI 默认输出；字段 DTO 先在 Service / tests 层验证。
- 真实 PDF 验收应证明至少 A 类可从 2024 年度报告标准披露表抽取：`annual_excess_return = 2.87%`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`source_column_label=①－③`，citation 为 table locator。
- C 类是否返回取决于标准披露表是否存在完整 `过去一年` / `①－③` 行列，不得外推或 fallback。
- 10G 不做 `A=R-B` 计算、不做 `R=A+B-C`、换手率、成本计算、扣费后收益率、年化收益率、同类中位数、模板执行、自动报告或投资判断。

Slice 10G 已经 MiMo review `ACCEPTED`：

- Service 层已实现 annual excess return disclosed-field extraction。
- 10G 抽取 `annual_excess_return` 只消费标准披露表的 `①－③` 显式披露列；不通过 10F 的 `annual_nav_growth_rate` / `annual_benchmark_return_rate` 做差计算。
- 真实 PDF / Service 测试已覆盖 A 类 DTO：`annual_excess_return = 2.87%`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`source_column_label=①－③`，citation 为 table locator。
- 测试已覆盖缺 `①－③` 列时 fail-closed 为 `not_found`，且不得使用管理人报告文字、年度图 / 图片或未 citation 指向的 sibling table fallback。
- 10G remaining blocking risk: none reported。
- 10G 没有依赖章节编号，没有改变 CLI 默认输出，没有新增 failure taxonomy，没有进入 `A=R-B` 计算、`R=A+B-C`、换手率、成本计算、扣费后收益率、年化收益率、同类中位数、模板执行、自动报告或投资判断。

Post-MVP 10H 裁决为 multi-year annual performance source contract with bounded year coverage：

- 10H 目标是裁决近 3 年 / 近 5 年收益表现的 deterministic source 和 aggregation contract；不直接进入报告生成或投资判断。
- 10H 仅做 docs update / source contract，不做代码实现，不新增 Service method，不改 CLI，不改测试。
- 10H source 选择 multiple annual reports。每个自然年度使用该年度基金年报中的标准披露表 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`，复用 10F / 10G 的单年度字段抽取结果。
- 每个年度复用 10F / 10G 字段：`annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return`。
- 10H 不做 single-report rolling period extraction。当前 2024 年度报告没有 `过去三年` / `过去五年` 行，因此不得从单份 2024 年报合成近 3 年 / 近 5 年 rolling period。
- 10H 不使用单份年报年度图 / 图片、OCR / chart parsing、外部净值数据库、第三方平台、管理人报告文字 fallback 或模型推断。
- 10H 年度窗口裁决为：`requested_window_years = 5`，`minimum_complete_years = 3`，`maximum_complete_years = 5`。
- 允许 bounded partial-by-year：请求近 5 年时可接受 3-5 个完整年度；缺 1-2 年仍可返回成功结果，但必须结构化暴露 coverage metadata。
- coverage metadata 固定包含：`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`。
- `coverage_status` 只允许 `complete` 或 `partial`。5 年完整为 `complete`；3-4 年完整为 `partial`。
- 少于 3 个完整年度时整体 fail-closed 为 `not_found`；不新增 `partial_success`、`missing_year` 或新的 failure taxonomy。
- 某年度完整的定义：该年度年报存在且可读取；标准披露表命中；同一 share class 下 `annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return` 三个字段都完整；三个字段都有对应 table locator citation。
- 多年度 share class 口径按 share class 独立计算 coverage：某 share class 至少 3 个完整年度才返回该 share class series；所有 share class 都不足 3 年则整体 `not_found`。
- 多年度 DTO 目标形态为 `MultiYearAnnualPerformanceSeries`，包含：`fund_code`、`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`、`share_class_scope`、`rows`、`citations`。
- 每个 row 包含：`year`、`annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return`、`citations`。
- 每个字段仍保留原单年度 DTO 的 `decimal_percent_text`、`source_period_label=过去一年`、`source_column_label`、`citation`；多年度聚合不产生新的 source，只组合多个年度 source。
- citation 口径：每个 year 的每个字段必须保留来自对应年度年报 table locator 的 citation；不得只给汇总 citation。
- 10I 才能实现 multi-year annual performance aggregation service；10I 才裁决显式 `document_id` list 输入和 Service 编排。10H 不做 repository 自动补齐或自然语言 `近 5 年` 解析。
- 10H 后续实现不得重新写第二套表格抽取规则；只能编排 10F / 10G 的单年度 extraction result。
- 10H 不做年化收益率、扣费后收益率、收益复权、净值计算、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。

Slice 10H 已经 MiMo review `ACCEPTED`：

- 10H 已完成 docs-only source contract，不实现 aggregation service。
- 10H source contract 固定为 multiple annual reports；每个年度复用 10F / 10G 单年度 extraction result。
- 10H 已明确 bounded year coverage：5 年窗口内允许 3-5 个完整年度，缺失年份必须结构化暴露；少于 3 年整体 `not_found`。
- 10H 已明确不做 single-report rolling period extraction，不使用 `过去三年` / `过去五年` 行，不做 OCR / chart parsing、外部数据源、管理人报告文字 fallback、自然语言 `近 5 年` 解析或 repository 自动补齐。
- 10H remaining blocking risk: none reported。

Post-MVP 10I 裁决为 multi-year annual performance aggregation service：

- 10I 放在 Service 层，定位为 use case orchestration；不放到 Agent、CLI、Store 或 ToolService。
- 10I 目标是显式接收多年度已导入年报，编排 10F / 10G 单年度 extraction result，返回 3-5 年 bounded coverage 的 `MultiYearAnnualPerformanceSeries`。
- 10I 首批输入固定为：`fund_code`、`requested_years: list[int]`、`annual_report_documents: list[{year, document_id}]`、`share_class: optional`。
- 10I 不做 `fund_code + years -> repository 自动查找`，不做自然语言 `近 5 年` 解析，不自动导入缺失 PDF，不改 CLI 默认输出。
- `requested_years` 约束：长度必须为 3-5；年份必须唯一；Service 可 normalize 为升序，并在 DTO 中输出 normalized `requested_years`。
- 每个 `document_id` 必须显式绑定 year；不得只从 `document_id` 字符串猜年份。
- 绑定 year 与单年度 extraction result 的 `report_year` 不一致时，整体 fail-closed 为 `identity_mismatch`。
- 10I 不重新解析表格，不新增第二套表格抽取规则；只能编排 10F / 10G 的单年度 extraction result。
- 某 year / share class 同时具备 `annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return` 三个字段及 table locator citation，才算 complete year。
- 任一字段缺失时，该 year 对该 share class 计入 `missing_years`；若导致该 share class 完整年度少于 3 年，则不返回该 share class。
- coverage 语义沿用 10H：`minimum_complete_years=3`，`maximum_complete_years=5`；5 年完整为 `coverage_status=complete`，3-4 年完整为 `coverage_status=partial`，少于 3 年整体 `not_found`。
- `coverage_status=partial` 是成功结果的 coverage metadata，不是 failure code；不新增 `partial_success`。
- share class 口径：按 share class 独立计算 coverage。用户指定 share class 时只评估该 share class；未指定时返回所有达到 3-5 年 coverage 的 share class series。所有 share class 都不足 3 年时整体 `not_found`。
- `missing_years` 首批只返回年份列表，不新增 `missing_reasons`。
- DTO 形态沿用 10H：`MultiYearAnnualPerformanceSeries` 包含 `fund_code`、`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`、`share_class_scope`、`rows`、`citations`。
- 每个 row 包含：`year`、`annual_nav_growth_rate`、`annual_benchmark_return_rate`、`annual_excess_return`、`citations`。
- citation 口径：每个 year / field 保留原年度年报 table locator citation；禁止只给汇总 citation。
- 失败语义沿用现有 failure code：document/year 与 extraction `report_year` 冲突为 `identity_mismatch`；少于 3 个完整年度为 `not_found`；单年度文档不可读、目标表缺失或字段缺失只计入 `missing_years`，若导致不足 3 年则 `not_found`；extractor 配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 10I 不新增 `missing_year`、`partial_success`、`coverage_error` 或新 failure taxonomy。
- 10I 不做 repository 自动补齐、自然语言解析、OCR / chart parsing、外部数据源、年化收益率、扣费后收益率、收益复权、净值计算、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- 10I 测试必须覆盖：5 年完整为 `complete`；4 年完整 / 缺 1 年为 `partial`；3 年完整 / 缺 2 年为 `partial`；少于 3 年为 `not_found`；C 类不足 3 年时不返回 C 类；每个字段保留对应年度 table citation；不重新解析表格、不走 OCR / chart / external source。

Slice 10I 已经 MiMo review `ACCEPTED`：

- Service 层已实现 multi-year annual performance aggregation service。
- 10I 显式接收 `requested_years` 与 `annual_report_documents[{year, document_id}]`，编排 10F / 10G 单年度 extraction result；不做 repository 自动补齐、自然语言解析、自动导入 PDF、CLI 改造、OCR / chart parsing 或外部数据源。
- 10I 已实现 3-5 年 bounded coverage：5 年完整为 `coverage_status=complete`；3-4 年完整为 `coverage_status=partial`；少于 3 年整体 `not_found`。
- 10I 已实现 share class 独立 coverage；不足 3 年的 share class 不返回，所有 share class 都不足 3 年时整体 `not_found`。
- 10I 已覆盖 document/year 与 extraction `report_year` 冲突时 `identity_mismatch`。
- 10I remaining blocking risk: none reported。

Post-MVP 10J 裁决为 multi-year performance service-to-agent exposure contract：

- 10J 目标是定义 Agent / Host 如何通过受控工具消费 10I 的 `MultiYearAnnualPerformanceSeries`；10J 是 docs-only contract slice，只更新 `docs/design.md` 和 `docs/implementation-control.md`，不实现 tool-loop，不修改 CLI / code / tests，不做 repo auto lookup，不做自然语言 `近 5 年` 解析，不做 missing-PDF auto import，不做 filename / document_id year guessing。
- 10J 可新增受控 Agent tool contract，工具名建议为 `aggregate_multi_year_annual_performance`。
- 该工具仍是 controlled tool，不是开放问答能力；Agent 不得直接调用 Service 内部方法或读取 raw Docling JSON / 本地 PDF path / cache path。
- 工具输入沿用 10I：`fund_code`、`requested_years`、`annual_report_documents[{year, document_id}]`、`share_class optional`。
- Agent / Host 不得在 10J 中做自然语言 `近 5 年` 解析、repository 自动查找、缺失 PDF 自动导入、文件名猜年份或 document_id 字符串猜年份。
- 工具输出成功时返回 `series[]`，失败时返回 `failure`；不生成投资分析文本。
- 每个 series 必须保留 `coverage_status`、`covered_years`、`missing_years`、`rows` 和每年每字段 citation。
- Agent 允许做的事仅限：调用受控工具；把 DTO 字段转述为 plain answer；明确展示 `coverage_status`、`covered_years`、`missing_years`；引用每年每字段 table locator citation。
- Agent 不得计算年化收益率、扣费后收益率、排名、打分、收益来源解释、`R=A+B-C`、投资结论或补齐缺失年份。
- CLI 边界：10J 不改 CLI 默认输出，不新增 `fund-checklist ask`、multi-year CLI 子命令或 CLI 参数。
- coverage 展示语义：`coverage_status=complete` 可表述为覆盖全部 requested years；`coverage_status=partial` 必须同时展示 `covered_years` 和 `missing_years`，不得写成“近 5 年完整表现”。
- 少于 3 年时工具沿用 10I 返回 `not_found`；Agent 不得生成部分答案。
- citation 要求：final answer citations 必须包含被引用 year / field 的 table locator citation；禁止只引用汇总 series citation。
- failure 语义沿用 10I，只允许四个 failure code：`identity_mismatch`、`not_found`、`schema_drift`、`unavailable`；Agent 只把 failure 转为 fail-closed plain answer，不新增 failure code。
- 后续实现测试建议放在 10K fake/injected Agent tool-loop：验证 Agent 调用 `aggregate_multi_year_annual_performance`，消费 `coverage_status=partial`，最终回答包含 covered/missing years 和 citations，且不泄漏 raw Docling JSON / local path / cache path，不输出年化收益、扣费后收益或投资判断。
- 10J 不做 LLM 自然语言 query routing、repository 自动补齐、CLI 新入口、多 PDF 导入流程、报告生成、template chapter execution、`R=A+B-C`、年化收益率、扣费后收益率或投资判断。

Post-MVP 10K 裁决为 multi-year performance fake/injected Agent tool-loop：

- 10K 是 implementation slice，目标是在 fake/injected Agent tool-loop 中暴露受控工具 `aggregate_multi_year_annual_performance`，验证 Agent 能消费 10I `MultiYearAnnualPerformanceSeries`。
- 10K 不接真实 LLM，不改 CLI 默认输出，不新增 `fund-checklist ask`、multi-year CLI 子命令或 CLI 参数。
- 10K 工具名称固定为 `aggregate_multi_year_annual_performance`，不得新增别名。
- 工具输入沿用 10I / 10J：`fund_code`、`requested_years`、`annual_report_documents[{year, document_id}]`、`share_class optional`。
- Agent 不得自己执行自然语言 `近 5 年` 解析、repository 自动查找、自动导入 PDF、文件名猜年份或 document_id 字符串猜年份。
- 工具输出只返回 10I 结构化 result：成功为 `series[]`，失败为 `failure`；tool 层不生成分析文本。
- Agent 允许行为只限：调用受控工具；转述 DTO 字段；展示 `coverage_status`、`covered_years`、`missing_years`；附带 per-year / per-field table locator citation。
- `coverage_status=partial` 时，final answer 必须同时出现 `covered_years` 和 `missing_years`；不得写成“近 5 年完整表现”。
- final answer citations 必须来自具体 year / field 的 table locator；禁止只给 series-level citation、汇总 citation 或无字段来源 citation。
- tool failure 时 Agent 必须 fail-closed，返回 `AgentRunResult.failure`；不得生成部分答案。
- failure 语义沿用 10I / 10J：`identity_mismatch`、`not_found`、`schema_drift`、`unavailable`；10K 不新增 failure code。
- 10K 禁止计算年化收益率、扣费后收益率、排名、打分、收益来源解释、`R=A+B-C`、投资结论、报告生成或补齐缺失年份。
- 10K 测试只使用 fake/injected tool-loop，不接真实 provider，不联网，不读取真实 API key。
- 10K 必须测试：partial coverage final answer includes covered_years and missing_years；complete coverage final answer does not invent missing_years；tool failure `not_found` -> `AgentRunResult.failure`；`identity_mismatch` -> `AgentRunResult.failure`；final answer includes per-year / per-field citations；final answer does not include annualized_return / fee-adjusted return / investment judgment；no raw Docling JSON / local path / cache path leakage。

Post-MVP 11A 裁决为 performance disclosure locator，插入 10D 之前：

- 11A 目标是定位业绩表现披露位置，不抽取结构化字段；10D performance return fields extraction 后置。
- 11A 只回答净值增长率 / 业绩比较基准收益率相关披露在哪里，输出章节标题、表格片段、citation 和 trace。
- 11A 不输出 `nav_growth_rate`、`benchmark_return_rate`、`period`、`decimal_percent_text` 等结构化字段，不计算 `A = R - B`。
- 11A 仍放在 Service 层，作为 controlled disclosure profile；Store / ToolService / Agent 不承担自由语义理解。
- profile 名称裁决为 `performance_returns`；名称只表示业绩表现披露定位，不代表字段抽取。
- acceptable title family 固定为：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`。
- 首批 aliases 固定为：`净值增长率`、`业绩比较基准收益率`、`基准收益率`、`收益表现`、`基金净值表现`；不纳入 `业绩`、`收益`、`表现` 等宽泛 alias。
- candidate queries 固定为原始 query、`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`、`业绩比较基准收益率`。
- success 语义：必须命中 acceptable title family，并返回 section citation；若目标披露存在相关表格，则必须包含 table citation。真实样本存在表格，因此 11A smoke 要求 table citation。
- 11A 不裁决 A/C 类字段值；若表格同时包含多个份额类别，只展示原始表格片段，不筛选、不判断、不抽值。
- failure 语义沿用现有 failure code：目标披露未命中为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`；不新增 `performance_not_found`、`period_not_found` 或 `partial_success`。
- 真实 CLI smoke 使用 `--query '净值增长率'` 和 work dir `.fund_checklist_cli_smoke_11a`；验收必须 exit code `0`，answer 包含 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`，Citations / Trace 存在，包含 table citation，CLI 默认输出不包含 `routing_trace`。
- 11A 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、字段抽取、calculation framework、template contract execution、chapter contract execution、自动报告或投资判断。

Slice 11A 已经 MiMo review `ACCEPTED`：

- 真实 CLI smoke 使用 `.fund_checklist_cli_smoke_11a`，`--query '净值增长率'` exit code `0`。
- answer 包含 `3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较`。
- Citations / Trace 存在，且包含 table citation：CLI 输出包含 `locator_kind=table`。
- CLI 默认输出不暴露 `routing_trace`。
- CLI 输出不包含 `nav_growth_rate`、`benchmark_return_rate` 或 `decimal_percent_text` DTO；没有字段值抽取或计算。
- 11A remaining blocking risk: none reported。

Post-MVP 11B 裁决为 disclosure locator contract registry：

- 11B 目标是把现有 controlled disclosure profiles 收敛为 Service 层内部 locator contract registry，降低后续继续堆零散 hardcoded profile 的风险。
- 11B 不新增新的披露对象定位能力；只迁移 / 规范已有 `holdings_top10`、`asset_allocation`、`fee_rates`、`performance_returns` 等 reading locator profile。
- registry 最小字段固定为：`profile_name`、`aliases`、`candidate_queries`、`acceptable_title_family`、`requires_table_citation`、`extraction_allowed`。
- `profile_name` 是内部 profile 名称，不作为 public tool 输出或用户可见契约。
- `aliases` 只用于判断用户 query 是否进入该受控 profile；alias 本身不得作为 evidence 成功条件或 citation 来源。
- `candidate_queries` 是 Service 层按顺序调用既有 Host / Agent / `search_document` 的受控检索候选，不修改 `search_document` public contract。
- `acceptable_title_family` 是披露目标成功条件；只有命中可接受标题族才算 profile 成功，不能把 keyword 命中当成 disclosure target success。
- `requires_table_citation` 只表达该 profile 是否要求 table citation；若为 true 且目标样本存在表格，最终 evidence 必须包含 table citation。
- `extraction_allowed` 在 11B 固定为 `False`；registry 只表达阅读定位 contract，不开放字段抽取、计算或章节生成。
- 11B 仍放在 Service 层；Store / ToolService / Agent 不承担 routing registry、自由语义理解或 target success 判定。
- 11B 不改变 CLI 默认输出格式，不暴露 `routing_trace`，不新增 DTO，不新增 public failure code。
- failure 语义沿用现有 failure code：所有 candidate 未命中目标披露为 `not_found`；registry 配置异常为 `schema_drift`；内部异常为 `unavailable`。
- 11B 不接 LLM、embedding、外部搜索服务，不做开放语义理解、自动分词、同义词扩散、top-N rerank、歧义消解、字段抽取、calculation framework、template contract execution、chapter contract execution、自动报告或投资判断。
- 11B 验收必须证明已有 locator 能力不回退：`前十大持仓`、`资产配置`、`费用`、`净值增长率` 四类查询仍按既有 accepted contract 返回目标 disclosure evidence / citation；`费用` 仍命中 `基金管理费`、`基金托管费`、`销售服务费`；`净值增长率` 仍包含 table citation 且不输出结构化字段 DTO。

Slice 11B 已经 MiMo review `ACCEPTED`：

- Service 层已将既有 controlled disclosure profiles 收敛为 disclosure locator contract registry。
- registry 保持四类既有 profile：`holdings_top10`、`asset_allocation`、`fee_rates`、`performance_returns`；未新增披露对象，未扩大 alias。
- 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；命中 `股票投资明细`；Citations / Trace / table citation 存在；CLI 默认输出不包含 `routing_trace`。
  - `资产配置`: exit code `0`；命中 `期末基金资产组合情况`；Citations / Trace / table citation 存在；CLI 默认输出不包含 `routing_trace`。
  - `费用`: exit code `0`；命中 `基金管理费`、`基金托管费`、`销售服务费`；Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
  - `净值增长率`: exit code `0`；命中 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`；Citations / Trace / table citation 存在；未输出结构化字段 DTO。
- 11B remaining blocking risk: none reported。

### 8.3 Locator 最低标准

当前采用宽松 locator 硬标准：

- 必须返回 `document_id`。
- 必须返回 `locator_kind`。
- section 结果必须返回 `section_ref`，并在 parser 可得时返回 `page_range`。
- table 结果必须返回 `table_ref`，并在 parser 可得时返回 `page_no`。
- Docling `internal_ref` 可得时必须透传；缺失时不得自动失败，但要在 locator 中标记 `internal_ref_available=false`。

`bbox` 是增强字段，不是 fail-closed 条件：

- raw Docling provenance 中存在 `prov[].bbox` 时，可以返回 `bbox`。
- 缺失 `bbox` 不得导致 `parser_health_failed`。
- 只有后续进入 PDF 高亮、截图裁剪或视觉核验 gate 时，才重新评估是否把 `bbox` 升级为硬准入。

### 8.4 Docling production path admission

Docling 在通过 PDF integrity + Docling conversion + parser_health 校验后即视为 production path；字段抽取 correctness benchmark 不在当前范围内。

具体范围：

- 仅限本地 PDF 导入。
- PDF 通过 integrity check 后进入 `DoclingConverter`。
- Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- parser_health 失败才返回 `parser_health_failed` 并 fail-closed。
- 不做与 `pdfplumber` 的替代路线比较。
- 不做字段抽取 correctness benchmark。

当前不问“Docling 是否完美”，只问“Docling 转换出的文档是否能支撑阅读工具”。

### 8.5 Document identity and report type

已裁决：

```text
document_id = fund_code-year-report_type-fingerprint_prefix
fingerprint_prefix = content_fingerprint 前 16 位 hex
document_id 表示内容身份，用于 public reading tools
local_import_id 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入
share_class 为可选 metadata；当前不强制解析，不参与 document_id；无法明确则为 null
report_type 当前仅 annual_report
```

约束：

- public reading tools 只接受 `document_id`，不接受 `local_import_id` 作为文档路由输入。
- 同一份 PDF 重复导入时，`document_id` 保持稳定，`local_import_id` 可记录多次导入事件。
- A/C 类或其它份额类别不作为准入条件；不能明确解析时 fail-open 为 `share_class = null`，但不得影响 locator、citation、redaction 和 reading tools。

### 8.6 Acceptance matrix

Acceptance requires:

- local PDF import
- PDF integrity failure classification
- Docling conversion
- DoclingDocumentStore parser health
- seven FundDocumentToolService tools
- locator + citation + redaction
- minimal Host/Agent tool loop smoke

### 8.7 Test matrix

后续 plan 至少列出以下测试名：

```text
tests/fund/document_tools/test_local_pdf_source.py
- test_import_local_pdf_preserves_report_identity
- test_import_local_pdf_rejects_non_pdf_magic_bytes
- test_import_local_pdf_uses_content_fingerprint_not_filename

tests/fund/document_tools/test_docling_conversion.py
- test_convert_local_pdf_writes_docling_json
- test_convert_failure_returns_docling_convert_failed
- test_parser_health_fails_when_no_text_and_no_sections

tests/fund/document_tools/test_docling_store.py
- test_store_lists_sections_with_locator
- test_store_reads_section_with_bounded_text
- test_store_lists_and_reads_tables
- test_store_search_returns_ranked_excerpt

tests/fund/document_tools/test_service.py
- test_list_reports_returns_safe_source_summary
- test_read_section_redacts_local_paths
- test_search_document_returns_citation_and_locator
- test_read_table_returns_table_ref_and_section_ref
- test_get_excerpt_rejects_unknown_locator

tests/fund/agent/test_minimal_tool_loop.py
- test_agent_tool_loop_searches_then_reads_section
- test_agent_table_aware_loop_answers_manager_table_information
- test_agent_table_aware_loop_answers_holding_table_information
- test_agent_table_aware_loop_keeps_section_only_answer_when_no_nearby_table
- test_agent_tool_loop_does_not_receive_raw_docling_json
```

最小验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

测试约束：

- MVP 必须包含至少一个仓库内真实本地样本 PDF 的 Docling conversion smoke。
- fake fixture 只能测试边界和错误，不得用于证明 production conversion path。
- MVP closeout 不接受 only ToolService tests；必须通过 `test_agent_tool_loop_searches_then_reads_section`。

### 8.8 CIC-lite execution model

当前项目不使用重型 gateflow。CIC-lite 规则如下：

- MVP plan artifact 最多 1 份。
- plan review artifact 最多 1 份。
- plan review `ACCEPTED` 后必须进入代码实现。
- 禁止新增 plan-fix / re-review / evidence gate，除非 review 明确指出违反已裁决硬口径。
- 每个实现 slice 只走：implement -> tests -> diff review。
- Controller 只核边界、diff、测试命令和测试输出。
- Implementation Agent 写代码和测试。
- Review Agent 只 review diff + tests，不产出新 plan，不开新路线。
- 禁止 Evidence Agent 单独写 evidence report。
- 禁止用文档更新代替可运行代码。
- 没有 diff，不算实现；没有测试命令和输出，不算完成；没有 review agent 独立检查，不算 accepted。

## 9. 已关闭裁决项

详细裁决记录见 docs/implementation-control.md。

## 10. 开发路线

### Phase 1：稳定化

- **Slice 15A**：提交遗留 + 清理 smoke work-dirs + full regression。目标：main 干净可复现。
- **Slice 15B**：拆分 reading_service.py（5533 行 → models + chapter_generator + extraction）。✅ 已完成。

### Phase 2：Ch7 结构化信号 + 模板区块补齐

- **Slice 16A**：Ch7 确定性信号判断 + Ch6 风险清单表。✅ 已完成。含加权 Jaccard 风格漂移检测。
- **Slice 16B**：Ch6 压力测试表。按基金类型选阈值，从年报取规模/净值数据填充。
- **Slice 16C**：Ch0 升级/降级阈值事件 + 一句话产品定义。从 Ch7 信号反推 Ch0 封面。

### Phase 3：报告质量 + 可用性

- **Slice 17A**：报告 Markdown 持久化 + metadata sidecar（fund_code, year, audit_score, generation_time）。
- **Slice 17B**：citation 验证工具（给定 citation locator → 定位年报原文 → 返回上下文片段）。
- **Slice 17C**： CLI 端到端 smoke（真实 PDF → 完整报告 → 审计产物落盘 → exit code 验证）。

### Phase 4：分析能力扩展（低优先级）

- ~~**Slice 18A**：风格漂移检测~~ → 已在 16A 加权 Jaccard 实现，删除。
- ~~**Slice 18D**：费率影响估算~~ → 已在 16A 费率评分覆盖，合并删除。
- **Slice 18B**：换手率追踪（年报 §8 换手率 → 多年度趋势）。低优先级。
- **Slice 18C**：份额变动 + 盈利投资者占比（年报 §10 + 2026 新规字段）。低优先级。

### 技术债

- **P1-3**：提取 compute_signal_judgment / compute_risk_checklist 共享评分 helper。
- **extraction.py 二次拆分**：当前 4634 行，提取 signal_scoring.py / risk_assessment.py。
