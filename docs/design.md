# fund-checklist 设计真源初稿

更新时间：2026-06-27  
文档状态：设计真源初稿，已可作为 MVP plan 输入；不得作为实现完成证据。  
适用范围：基金年报阅读工具层。除非另有独立 gate，本文件不覆盖字段抽取、自动报告、投资判断或发布就绪。

## 0. 证据口径

### 0.1 当前代码事实

- 本仓库当前不是 git repository；无法用 branch / commit / dirty status 证明变更归属。
- 本次 bootstrap 前，当前仓库只有 `AGENTS.md`、研究文档、基金年报 PDF 和两份历史分析报告；没有 `fund_agent/`、`tests/`、`docs/design.md`、`docs/implementation-control.md` 的既有实现或真源文档。
- 当前样本材料位于 `基金年报/`，包含多只基金多个年度的 PDF；这些 PDF 是本仓库可见材料，不等于已经存在受控 `PdfSourceProvider`、`PdfBlobStore` 或 `DoclingDocumentStore`。
- `docs/fund-analysis-template-draft.md` 存在，但按 `AGENTS.md` 规则，只在后续报告、字段抽取或投资判断路径中读取和使用；阅读工具 MVP 不以该模板为成功标准。

### 0.2 当前规则事实

- `AGENTS.md` 是本仓库 Agent 执行规则唯一权威入口。
- `docs/architecture.md` 是轻量架构坐标系；它固定不可摇摆的层次、主链路和稳定契约，但不代表当前代码已实现。
- 当前优先方向是基金年报阅读工具层，主链路为：

```text
PDF
 -> Docling JSON
 -> FundDocumentToolService
 -> Agent tools
    - list_reports
    - list_sections
    - read_section
    - search_document
    - list_tables
    - read_table
    - get_excerpt
```

- 阅读工具层的目标是稳定阅读、检索、返回可引用片段；不是字段抽取、自动报告、投资判断、报告渲染或数据仓库晋升。
- 目标架构固定为 `UI -> Service -> Host -> Agent`；基金文档读取、PDF source、Docling conversion、Docling document store、FundDocumentToolService 归 `fund_agent/fund`。
- Service / UI / Host / 展示层不得直接操作 PDF cache、Docling raw JSON、parser private payload 或本地路径。
- Dayu 是参考，不是生产 runtime 依赖；禁止直接引入 `dayu-agent`、`dayu.host`、`dayu.engine`。
- Docling production path for local-PDF MVP 已准入：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`；不做与 `pdfplumber` 的替代路线比较，不做字段抽取 correctness benchmark。
- 当前开发流程采用 CIC-lite：1 份 MVP plan、1 次 plan review；review `ACCEPTED` 后必须进入代码实现，每个 slice 只走 implement -> tests -> diff review。

### 0.3 dayu 本地代码事实

已查看本地仓库 `/Users/maomao/dayu-workspace/dayu-agent/`。以下是代码事实，不是本仓库已实现事实：

- dayu 的稳定分层写在 `dayu/README.md`：`UI -> Service -> Host -> Agent` 是层次，`startup preparation`、`contract preparation`、`scene preparation` 是装配过程，不是新层。
- `dayu/fins/README.md` 明确 Fins 有两条路径：
  - Agent augmentation path：Fins 给 Agent 注入财报读取工具、公司/source/processed/blob 窄仓储和工具服务。
  - Direct operation path：`UI -> FinsService -> Host -> FinsRuntime / pipeline`，覆盖下载、上传、预处理，不经过 Agent。
- `dayu/fins/tools/service.py` 中 `FinsToolService` 负责参数校验、`document_id -> source_kind -> source -> processor` 路由、能力降级和 Processor LRU 缓存；它不是 Host，也不是 UI。
- dayu 仓储协议拆成 `CompanyMetaRepositoryProtocol`、`SourceDocumentRepositoryProtocol`、`ProcessedDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol`、`FilingMaintenanceRepositoryProtocol` 等窄协议，定义在 `dayu/fins/storage/repository_protocols.py`。
- dayu CN/HK 下载链路已有 `PDF -> Docling JSON -> source meta 完成态` 的实际代码：`cn_download_filing_workflow.py` 下载或复用 PDF，转换或复用 Docling JSON，最后提交 source meta；`cn_download_source_upsert.py` 要求完成态 `primary_document` 指向 `_docling.json`。
- dayu 的 `DoclingProcessor` 位于 `dayu/engine/processors/docling_processor.py`，读取 `*_docling.json`，提供 `list_sections`、`read_section`、`search`、`list_tables`、`read_table` 等 processor 能力；`FinsDoclingProcessor` 在 Fins 层继承它并补充金融表格语义。
- dayu 的 CNINFO downloader 明确只做 discovery / PDF 下载，不写 workspace、不调用 Docling、不生成 document_id；document_id 和落盘由 pipeline 层处理。

### 0.4 事实与推断边界

- 事实：dayu 已经有可参考的 source / blob / processed repository、processor registry、tool service、CN/HK PDF + Docling pipeline。
- 事实：本仓库尚未实现这些模块。
- 推断：本仓库最短可行路径应先建立本地年报阅读工具的受控边界和最小端到端 slice，再逐步吸收 dayu 的仓储/处理器/Host 形态。
- 不得推断：本仓库可以直接复制 dayu runtime、可以复用 dayu 的全部 Host / Engine、或者当前样本 PDF 已经具备可生产读取能力。

## 1. 第一性原理判断

基金年报阅读工具要解决的问题不是“让 LLM 看见 PDF”，而是：

1. PDF 是非结构化披露物，包含页眉页脚、跨页表格、章节层级、脚注和排版噪声。
2. LLM 直接读 PDF 或 raw JSON 会扩大幻觉和遗漏风险。
3. Agent 需要的是可枚举、可定位、可边界截断、可审计引用的工具结果。
4. 因此系统必须先把 PDF 变成受控文档模型，再通过工具服务暴露窄能力。

由此推出本仓库 MVP 的最小链路：

```text
PdfSourceProvider
 -> PdfBlobStore
 -> DoclingConverter
 -> DoclingDocumentStore
 -> FundDocumentToolService
 -> Agent read tools
```

这条链路的成功标准是“工具可读、可查、可引用”，不是“能生成基金分析报告”。

## 2. 当前设计目标

### 2.1 MVP 目标

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
- 同时通过离线 `FundDocumentToolService` smoke 和最小 Host / Agent tool loop smoke；只通过离线 ToolService 不构成 MVP closeout。

### 2.2 非目标

- 不做字段抽取。
- 不做自动报告生成。
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

禁止：

- 直接操作 PDF cache、Docling raw JSON、parser raw payload。
- 管理 Host 生命周期细节。
- 实现 Agent tool loop。

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

### 3.4 Agent / Fund

职责：

- `fund_agent/fund` 承载基金文档领域能力包。
- 实现 PDF source abstraction、blob store、Docling converter、Docling document store、FundDocumentToolService。
- Agent 层负责 ToolRegistry / ToolTrace / context budget / tool loop。
- MVP Slice 4 已实现 `MinimalFundDocumentAgent` 的最小 loop：`search_document -> read_section`。
- Post-MVP Slice 5 扩展为 table-aware retrieval / citation loop：先读取命中章节，再通过 `list_tables` / `read_table` 读取同 section、同页或相邻页候选表格，按 query 命中和 proximity 排序；成功时 `answer` 只由 section/table tool result 生成，`citations` 同时包含 section/table citation。
- Post-MVP Slice 8A 已实现 fake/injected LLM tool-loop contract：LLM adapter 只能通过受控 reading tools 取得事实，不得直接读取 repository/private loader、raw Docling JSON 或本地路径。
- Post-MVP Slice 8B 已实现为 DeepSeek real LLM adapter behind existing contract：真实 provider 只能实现 `LlmClientProtocol`，所有输出仍经 8A runner/enforcement；Mimo / MiMo 与多 provider 后置。
- Post-MVP Slice 8C 设计为 opt-in live DeepSeek smoke：默认 pytest no-network，只在 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 且存在 `DEEPSEEK_API_KEY` 时验证一次真实 provider 输出。
- `AgentRunResult` 至少包含 `answer`、`citations`、`tool_trace`、`failure`。
- `ToolTraceEntry` 至少包含 `tool_name`、`arguments`、`result_kind`、`failure_code`。
- `search_document` 无命中时不猜测章节，返回 `AgentRunResult.failure`。

禁止：

- 把 dayu 的 `dayu.host` / `dayu.engine` 作为生产 runtime 直接依赖。
- 绕过 Fund documents / tool service 边界向上层暴露 raw PDF / raw Docling。
- 在 Agent 层直接读取 store 私有字段、raw Docling payload、PDF cache 或本地路径。

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
- `share_class` 为可选 metadata；MVP 不强制解析，不参与 `document_id`。
- 无法明确 A/C 类时记录 `share_class = null`，不得从文件名或标题猜测。
- 若同一年同 `report_type` 下不同份额类别 PDF 内容不同，`content_fingerprint` 会区分 `document_id`。
- `report_type` MVP 首批仅支持 `annual_report`。
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

新增实现约束：

- fallback 必须由失败分类显式驱动。
- 不得用 fallback 掩盖 `schema_drift`、`identity_mismatch`、`integrity_error`。
- parser health 至少验证：存在可读文本、章节或可替代章节索引、表格索引可安全为空但不能破坏章节读取。

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

### 8.1 MVP source 范围

MVP 只支持本地 `基金年报/` PDF 导入。官方来源 discovery 不进入当前 MVP。

### 8.2 MVP runtime 范围

MVP 同时覆盖两条验证路径：

- `FundDocumentToolService` 离线工具验证。
- 最小 Host / Agent tool loop 内化验证。

其中离线工具验证用于证明 Fund 文档边界和工具契约；最小 Host / Agent tool loop 用于证明阅读工具能被 Agent 路径稳定调用。二者都不允许扩展为自动报告或投资判断。

MVP 不允许只以 `FundDocumentToolService` 离线测试通过收口。MVP closeout 必须同时通过：

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

MVP Slice 4 实现为 deterministic minimal loop；Post-MVP Slice 5 在该 loop 上增加 table-aware retrieval。当前仍不接真实 LLM，不调用外部模型，不做字段抽取、自动报告或投资判断。`ToolFailure` 传播到 `AgentRunResult.failure`，不向 Host/UI 抛内部异常。

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
- Slice 8B 不新增 `fund-checklist ask`、streaming、Mimo / MiMo、多 provider matrix、prompt framework、richer QA/eval、字段抽取、自动报告或投资判断。

Post-MVP Slice 8C 的 live smoke 只验证真实 DeepSeek provider 的最小可用性：

- 默认 pytest 不联网；live smoke 必须由 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 显式启用。
- `DEEPSEEK_API_KEY` 缺失时 skip，不失败。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，可覆盖。
- `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，可覆盖。
- live smoke 使用 fake/in-memory tool service 或现有测试 fixture，不跑真实 PDF、不跑 CLI、不触发 Docling conversion、不使用 repository-backed loader。
- live smoke 最多 1 个 live run，timeout 300 秒，最多 1 次 retry，不做批量问题。
- opt-in 后 provider 返回不可解析、8A enforcement fail、network/429/auth error 均为 test fail。
- pytest output、trace、assert message 不得打印 API key；不得记录 provider raw response 到文件，不新增 artifact。
- Slice 8C 不修改 production adapter；若 live test 暴露解析 bug，必须先停止并报告。
- Slice 8C 不做 `fund-checklist ask`、真实 PDF/Docling/repository e2e、Mimo / MiMo、多 provider、streaming、retry/backoff hardening、richer QA/eval、prompt injection hardening、自动报告或投资判断。

### 8.3 Locator 最低标准

MVP 采用宽松 locator 硬标准：

- 必须返回 `document_id`。
- 必须返回 `locator_kind`。
- section 结果必须返回 `section_ref`，并在 parser 可得时返回 `page_range`。
- table 结果必须返回 `table_ref`，并在 parser 可得时返回 `page_no`。
- Docling `internal_ref` 可得时必须透传；缺失时不得自动失败，但要在 locator 中标记 `internal_ref_available=false`。

`bbox` 是增强字段，不是 MVP fail-closed 条件：

- raw Docling provenance 中存在 `prov[].bbox` 时，可以返回 `bbox`。
- 缺失 `bbox` 不得导致 `parser_health_failed`。
- 只有后续进入 PDF 高亮、截图裁剪或视觉核验 gate 时，才重新评估是否把 `bbox` 升级为硬准入。

### 8.4 Docling production path admission

Docling production path for local-PDF MVP is accepted after PDF integrity + Docling conversion + parser_health checks; field extraction correctness benchmark is out of scope.

具体范围：

- 仅限本地 PDF 导入。
- PDF 通过 integrity check 后进入 `DoclingConverter`。
- Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- parser_health 失败才返回 `parser_health_failed` 并 fail-closed。
- 不做与 `pdfplumber` 的替代路线比较。
- 不做字段抽取 correctness benchmark。

MVP 不问“Docling 是否完美”，只问“Docling 转换出的文档是否能支撑阅读工具”。

### 8.5 Document identity and report type

已裁决：

```text
document_id = fund_code-year-report_type-fingerprint_prefix
fingerprint_prefix = content_fingerprint 前 16 位 hex
document_id 表示内容身份，用于 public reading tools
local_import_id 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入
share_class 为可选 metadata；MVP 不强制解析，不参与 document_id；无法明确则为 null
report_type MVP 首批仅 annual_report
```

约束：

- public reading tools 只接受 `document_id`，不接受 `local_import_id` 作为文档路由输入。
- 同一份 PDF 重复导入时，`document_id` 保持稳定，`local_import_id` 可记录多次导入事件。
- A/C 类或其它份额类别不作为 MVP 准入条件；不能明确解析时 fail-open 为 `share_class = null`，但不得影响 locator、citation、redaction 和 reading tools。

### 8.6 MVP acceptance matrix

MVP acceptance requires:

- local PDF import
- PDF integrity failure classification
- Docling conversion
- DoclingDocumentStore parser health
- seven FundDocumentToolService tools
- locator + citation + redaction
- minimal Host/Agent tool loop smoke

### 8.7 MVP test matrix

后续 MVP plan 至少列出以下测试名：

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

MVP plan 已关闭。当前已完成到 Post-MVP Slice 8B；Slice 8C 的已裁决方向是 opt-in live DeepSeek smoke。

## 10. 下一步最小可验证问题

下一步只应验证一个问题：

```text
下一步只应验证一个问题：真实 DeepSeek provider 在显式 opt-in live smoke 中能否返回一次合法 `ToolCall` 或 `FinalAnswer`，并最终经 8A runner/enforcement。CLI ask、Mimo / MiMo、多 provider、richer QA/eval 仍不得混入 Slice 8C。
```
