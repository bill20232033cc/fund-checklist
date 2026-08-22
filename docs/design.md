# fund-checklist 设计真源

更新时间：2026-08-22（投资者偏好分析 §6.26 新增 §6.26.10 智慧笔记数据导出导入（Slice P4 note-import），邮件「我的思考记录」2026-08-11 收件，65 条记录 = 分析记录 20 / 多维度分析 20 / 孵化报告 5 / 结构分析 20；原 §6.26.8 行为证据对照顺延为 Slice P5；2026-08-21 已完成存储格式 / 图片 / 题库口径 / C1-C5 去留 / 五维权重裁决，见 §6.26.6 / §6.26.9）
文档状态：设计真源，覆盖基金分析助手完整链路；不得作为实现完成证据。
适用范围：基金分析助手（年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道）+ 投资者偏好分析（Flomo 导入 → 问卷基线 → 季度偏好快照）。
关联文档：AGENTS.md（执行规则）、docs/implementation-control.md（当前执行面板）

## 0. 证据口径

### 0.1 当前代码事实

- 本仓库已实现 `fund_agent/` 完整分层（fund / service / host / agent / cli），`tests/` 覆盖 document_tools / service / agent / cli，`docs/design.md` 与 `docs/implementation-control.md` 为真源文档。
- CLI 已实现 17 个子命令：`read` / `multi-year` / `import` / `holdings` / `download` / `allocation` / `fees` / `audit` / `deep-audit` / `generate` / `ask` / `interactive` / `repair` / `regenerate` / `fix` / `snapshot-quarterly` / `snapshot-semiannual`（后两者为季报/半年报单期快照，2026-08-14，见 §6.25）。
- 已实现能力：本地 PDF 导入、Docling 转换、7 个 reading tools、Service 层 profile routing + disclosure target contract、结构化字段抽取（费率/业绩/持仓/资产配置）、多年度聚合、确定性信号评分（基金类型感知：主动基金 6 指标；被动基金 3 指标 100 分制）、8 章分析报告生成、三层审计管道。
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
 -> 确定性信号评分 (基金类型感知：主动基金 6 指标 135→100 归一化；被动基金 3 指标 100 分制)
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
- 事实：本仓库已实现 DoclingDocumentStore section/table/search 能力、FundDocumentToolService、persistent repository、LLM adapter、信号评分和报告生成；已实现 EID downloader（`fund_agent/fund/document_tools/eid_downloader.py`），通过 CLI `download` 子命令提供单只基金单年度 PDF 下载；尚未实现多 provider matrix 和仓储协议拆分。
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
- `annual performance table extraction` 属于 extraction contract（10F）。
- `annual excess return disclosed-field extraction` 属于 extraction contract（10G）。
- `multi-year annual performance source contract` 属于 reading contract（10H）。
- `multi-year annual performance aggregation service` 属于 calculation contract（10I）。
- `multi-year performance Agent tool-loop` 属于 agent contract（10K）。
- `disclosure locator contract registry` 属于 reading contract（11B）。
- `batch PDF import` 属于 service contract（10M）。

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
- Post-MVP Slice 8B 已实现为 DeepSeek real LLM adapter behind existing contract：真实 provider 只能实现 `LlmClientProtocol`，所有输出仍经 8A runner/enforcement；Mimo 已通过 OpenAI-compatible adapter 准入；2026-08-10 起经 `FUND_CHECKLIST_LLM_PROVIDER`（`deepseek` 默认 / `mimo`）+ 每 provider 独立 env 自由切换，请求组装（next_step / next_step_stream / generate_text）统一走 `_provider_runtime`，scene/contract 模型名按翻译表映射（`deepseek-v4-pro→mimo-v2.5-pro`、`deepseek-v4-flash→mimo-v2.5`，未知透传），MODEL env 非空优先。
- Post-MVP Slice 8C 已实现 opt-in live DeepSeek smoke：默认 pytest no-network，只在 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 且存在 `DEEPSEEK_API_KEY` 时验证一次真实 provider 输出。
- 后续 Slice 10K 已实现多年度聚合受控工具（aggregate_multi_year_annual_performance）；Slice 13B 已实现 LLM 章节生成 tool-loop（逐章独立 prompt + hallucination 检测 + 模板回退）；Slice 14C 已实现三层审计管道（程序审计 + LLM 审计 + LLM 复核）。
- `AgentRunResult` 至少包含 `answer`、`citations`、`tool_trace`、`failure`。
- `ToolTraceEntry` 至少包含 `tool_name`、`arguments`、`result_kind`、`failure_code`。
- `search_document` 无命中时不猜测章节，返回 `AgentRunResult.failure`。
- 已实现（2026-08-02，Phase 7.4，见 `.sisyphus/plans/interactive-e2e-fix-20260802.md`）：
  - 工具失败（ToolFailure）回喂 LLM 作为下一轮输入，允许修正 section_ref / 工具名 / document_id；重复失败调用按 key 去重短路；终态失败（step 耗尽、终答守卫、provider 异常）仍 fail-closed。
  - 失败轮在 session 中成对持久化（含 tool_trace 与 tool_calls）；被投资建议拦截的回答保留原文与触发词（磁盘往返可保留）。
  - tool_trace 边界：工具失败路径 trace 非空；provider 首轮失败（next_step 内）trace 为空。
  - `document_id` 缺失时由 runner 用 expected 补全；未知工具名先有界归一化（去空白、去尾部括号参数），仍未知才拒绝且 trace 保留原始名。
  - prompt 硬规则：无事实检索目标问题直接 final answer；空搜索最多换 1 次查询词后声明未找到；section_ref/table_ref 一律从工具结果复制。
  - 投资建议检测（决策 A）：弱词豁免窗口 ±100 字符，事实性上下文词 15 个；指令动词（建议/应当/可考虑/适合/值得持有/应买入/应卖出/应增持/应减持）拦截；无上下文词 fail-closed 兜底；指令动词不含裸「应」（避免误命中 应付/应计）；main.py 用户输入预检合一为单一真源。
  - provider malformed 有界重试 1 次（stream + 非 stream；重试后仍 fail-closed，不回喂）。
  - interactive 终答投资建议守卫有界改写重试 1 次（重答仍走同一守卫；ask/generate 不重试）。
  - force-answer 分支同走终答守卫（2026-08-11 Fix A；2026-08-13 细化）：`max_steps` 耗尽降级（`_force_answer_from_evidence`）在 interactive 下经 `_apply_interactive_final_guards` 过投资建议拦截与 ≤200 字约束，不再绕过守卫；2026-08-13（用户裁决方案 2）降级产物跳过「原文粘贴 → 有界重答」子规则（产物即证据原文拼接，必然触发且重答轮 provider 不收敛时必失败为 unavailable），超长直接截断为 ≤200 字摘要，投资建议拦截语义不变。

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
- `report_type` 支持 `annual_report`（年报主链）；`semiannual_report` / `quarterly_report` 自 2026-08-14 起支持（季报/半年报单期快照，见 §6.25；quarterly 的 document_id 带 `-Q[1-4]` 期次段）。

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

排序：

- 召回不变：候选集来自 section text、table caption 与 bounded table rows 的子串命中（空白归一化）；0 命中返回空 tuple。
- 排序（2026-08-12 裁决）：命中候选按确定性 BM25F 多字段重排序（字段权重与参数见 §6.20），同分依次回退子串命中计数、source_order；纯函数、不联网、不接 LLM。
- public contract 不变：`SearchResult` 字段、match_kind、locator/citation、failure code 均不变；不新增公共字段。

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

interactive 表号一致性校验（2026-08-11 Fix C，仅 interactive）：`read_table` 的 `table_ref` 必须属于本轮已列出/已命中的表集合——本轮 `list_tables` 成功结果的 table_ref ∪ search 命中结果的 `SearchResult.table_ref`；未列出/未命中的表号返回 `NOT_FOUND`（「table_ref 未在当前已列出章节的表格中，请先 list_tables 并复制返回的表号」），作为工具失败回喂 LLM 并计入失败调用短路（LLM 改表号重试或先 list_tables）；`ask` 场景不拦截（白名单边界）。

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
- 工具失败回喂不新增 failure code；`llm_malformed_response` 仍仅用于 provider response 结构不可解析。
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


### 6.6 报告质量门禁

报告生成必须处理数据不完整场景。核心原则：降级而非失败，输出结构化声明而非空内容。

#### 6.6.1 数据充足场景

多年度 PDF 导入（≥3 年）且核心数据源（performance、holdings、fees）完整时：
- 各章节按 ChapterContract 全要求生成。
- 审计管道按标准阈值打分（≥80 通过）。

#### 6.6.2 数据不足场景

单年导入或核心数据源缺失时，按章节分别处理：

| 章节 | 数据不足条件 | 降级策略 |
|------|------------|---------|
| Ch2 R=A+B-C | 仅导入 <3 年 | 保留多年要求，输出结构化缺失声明：「仅导入 N 年，以下为已导入年份的 R-A-B-C 拆解」+ 已有数据表格 |
| Ch3 基金经理画像 | fund_manager 部分字段缺失（如 tenure_start / years_of_service / investment_strategy 为空） | LLM 只分析已有数据（如持仓行为），逐项声明缺失字段及原因；禁止从持仓反推基金经理意图或投资策略 |
| Ch4 投资者获得感 | report_year < 2026（2026 新规前年报不披露投资者实际收益） | 明确标注「本章节适用于 2026 年及以后年度报告」，输出结构化 N/A 声明，不尝试生成分析 |
| Ch5 当前阶段与关键变化 | must_answer 结构化规则未定义或 LLM 分析不可用 | 先定义 must_answer 的结构化规则（阶段判定 5 选 1 含优先级、关键变化 3 维度含阈值、时间窗口为同比），LLM 在规则框架内分析；失败时重试 1 次，仍失败则模板降级（数据表格 + 阶段判定 + 缺失声明） |

#### 6.6.3 结构化缺失声明格式

缺失声明必须包含：
- 缺失的具体字段或维度
- 缺失原因（数据未导入 / 年报未披露 / 数据源不可用）
- 对分析结论的影响（哪些判断因此无法做出）

#### 6.6.4 多年数据强制要求

- 报告生成最少需要 3 年数据（performance/holdings/fees）。
- 可用年份 < 3 时，`generate` 命令拒绝执行并报错。
- `import` 命令 `--year-range` 默认最近 3 年。

#### 6.6.5 hallucination 检测规则

`contains_non_year_numbers`（`chapter_generator.py`）用于检测 LLM 输出中的编造数字：

- **数字归一化**：strip trailing zeros（`1.20` → `1.2`，`2.60` → `2.6`），避免格式微差导致误杀。
- **跨章节引用**：所有章节的 `allowed_numbers` 合并为全局集合；LLM 引用其他章节 data_table 中的数字视为合法。
- **保留拦截**：不在任何 data_table 中的数字仍被拦截（凭空编造）。
- **LLM 提示词**：允许引用数据表中的数字（如净值增长率、费率、持仓比例），但不得编造数据表中不存在的数字。

#### 6.6.6 审计管道约束

**程序审计**（`ProgrammaticAuditor`）：
- 投资建议关键词检测（如"买入"）跳过 `## 分析` 之前的内容（data_table 区域包含引用文本，不应触发）。

**LLM 审计**（`LlmAuditor`）：
- prompt 必须包含正例/反例，明确"投资建议"的定义：必须是"买入/卖出/持有"的直接操作建议。
- "建议关注"、"基金仍可跟踪"、"超额收益持续性有待观察"等分析性表述不视为投资建议。
- JSON 解析失败时重试 1 次。

#### 6.6.7 截断限制

审计管道中存在 4 处内容截断，可能导致信息丢失：

| 位置 | 截断长度 | 影响 |
|------|---------|------|
| Ch0/Ch7 审计上下文（章节摘要） | 300 字符 | LLM 审计器只看到每章前 300 字，可能遗漏违规项 |
| Ch0/Ch7 LLM 生成提示词（章节摘要） | 500 字符 | LLM 生成 Ch0/Ch7 时只看到每章前 500 字 |
| LLM 审计器数据表 | 1000 字符 | 审计器只看到数据表前 1000 字符 |
| Ch5/Ch6 LLM 审计器上下文 | 500 字符 | 审计器只看到数据表前 500 字符 |

修复方向：增大截断限制或改为分段传递。

#### 6.6.8 fallback 条件

- LLM 生成失败（返回 None）→ 模板降级，标记 `passed_with_degradation`。
- hallucination 检测命中 → 模板降级。
- 审计循环耗尽：得分 < 50 → 模板降级；≥ 50 → 返回 LLM 内容 + 标记 `passed_with_degradation`。
- 异常捕获：只捕获 `LlmClientFailure` 和 `TimeoutError`，其他异常向上抛出。
- 审计阈值 ≥80 通过；修复 hallucination/程序审计/LLM 审计后观察得分，再决定是否调整。

禁止用模糊表述（如数据不足详见年报）替代结构化声明。

### 6.7 审计管道数据适配

审计打分必须考虑输入数据完整性，不得对数据不足的章节按完整报告标准打分。

#### 6.7.1 LLM 审计权重动态调整

当 ChapterContract 的 data_sources 存在缺失时：
- LLM 审计权重从 70% 降至 50%，程序审计权重从 30% 升至 50%。
- 判定规则：data_sources 中任意一个数据源为空或仅含 1 个年份 → 触发权重调整。
- 程序审计仍按确定性规则检查（格式、字段、引用），不因数据不足而放松。

#### 6.7.2 通过阈值

- 数据充足场景：≥80 分通过，50-79 分 PATCH，<50 分 REGENERATE。
- 数据不足场景：≥70 分通过（因 LLM 审计权重降低后，数据不足章节更难达到 80）。
- 通过后标记章节状态为 `passed_with_degradation`，与正常 `passed` 区分。

#### 6.7.3 审计产物要求

审计产物必须记录：
- 该章节是否处于数据不足状态
- 触发了哪些降级规则
- 最终评分及权重调整情况

### 6.8 章节级并发（Phase 7.5）

报告生成（`ReportGenerationCoordinator.generate_report`）的章节执行并发语义（2026-08-05 裁决，Mimo review ACCEPTED）：

- 四阶段依赖顺序：A 前置串行（预生成 data_table + global_numbers，纯程序计算）→ B 中间并行（Ch1-6 各自完整「写→审计→重写」闭环，章间零依赖）→ C 决策串行（B 全部 join 后 all_passed 判定；不通过则 Ch0/Ch7 模板生成并提前返回）→ D 收尾并行（Ch0/Ch7 带 Ch1-6 内容摘要并行生成）。**B 与 D 之间必须完全 join**，保证 Ch0/Ch7 永远读到 Ch1-6 最终内容。
- 并发机制：`ThreadPoolExecutor(max_workers=effective_concurrency)`，阶段 B/D 复用同一 executor；worker 运行完整单章闭环（等价 Dayu 单章 worker 模式，但 fc 不引入 async 事件循环，DeepSeek 调用为同步 `generate_text`）。
- 每 worker 独立 `DeepSeekLlmClient`（`clone()`：同 transport/env/options/temperature，独立 `_cumulative_usage`）；章节闭环内 3 处 `self._llm_client` 引用（LlmAuditor / ChapterRepairer / `_generate_chapter_content`）显式下传局部 client。
- 并发上限 lane：`chapter_concurrency`，生效优先级 CLI `--concurrency` → `GenerateReportRequest.chapter_concurrency` → env `FUND_CHECKLIST_CHAPTER_CONCURRENCY` → 默认 4（范围 1..8；`1` = 串行等价）。Service 层唯一解析点；client 无 `clone()` 时回退串行 + warning（不破坏既有 fake 测试）。
- 线程安全边界：`_process_states` 按章分立 key + `threading.Lock` 防御；ArtifactStore 按章分文件、唯一 writer；共享输入（performance/holdings/allocation/fees/fund_manager/scale/evidence/signal/global_numbers/fund_type）全阶段只读；每章 data_table 在 worker 内独立重算，不缓存复用；warnings 由 worker 返回值带回、主线程按 chapter_id 排序；worker 禁止直接 print（未来进度输出必须经主线程）。
- 失败语义：单章失败仅影响该章（worker 顶层兜异常 → None + failed state + warning），`passed` / `passed_with_degradation` / `audit_exhausted` 逐章判定不变；cancel 用 `executor.shutdown(wait=True, cancel_futures=True)` 收敛，不产生半报告文件。
- 与 Dayu 的差异：不引入 dayu runtime/代码；不使用 async 事件循环；lane 命名独立（`chapter_concurrency`，`write_chapter` 仅为参考量级）；并发不改变每章 prompt 与 LLM 调用序列（仅执行顺序交错），输出按 chapter_id 0..7 稳定组装。

### 6.9 报告输出渲染（PDF 引擎 fallback，2026-08-05 裁决）

`_export_pdf` 的渲染语义（Mimo review ACCEPTED）：

- 引擎 fallback 链（任一成功即返回 `(pdf_path, None)`）：① `xelatex` 可用 → pandoc `--pdf-engine=xelatex`（现行路径）；② `Chrome` 可用 → pandoc md→HTML（gfm→html5 standalone + 内嵌打印 CSS）→ Headless Chrome `--print-to-pdf`（A4 794×1123，`--no-pdf-header-footer`，timeout 120s）；③ 都不可用/都失败 → 回退 md + warning（返回签名 `(str, str|None)` 不变）。
- Chrome 探测顺序：`PUPPETEER_EXECUTABLE_PATH` → PATH `google-chrome` → macOS 默认 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`；pandoc 与 xelatex 均用 `shutil.which` 前置探测（避免无谓 subprocess 失败）。
- 打印 CSS 为原创资产（`fund_agent/service/assets/report_print.css`，不复制 dayu 文件）：`@page A4` + `@media print`、中英文换行、表格/代码块防溢出；HTML 中间产物放临时目录，成功转 PDF 后清理。
- 参考：dayu/render/render.py（md→HTML+打印 CSS→Chrome print-to-pdf）仅作架构参考，不引入其 runtime/代码。

### 6.10 interactive 问答质量语义（检索路由 + 收敛 + 终答，2026-08-05 裁决）

interactive 问答的检索与终答语义（Mimo review ACCEPTED，用户按推荐裁决）：

- 受控检索路由：新增 `manager_holdings` profile（target：9.4 期末基金管理人的从业人员持有本基金；candidate_queries 覆盖 持有本基金 / 基金经理持有 / 期末基金管理人的从业人员持有本基金 / 基金经理持有本基金），复用 `_extract_manager_holding` 的 9.4 定位语义；该 profile 的候选词为 4 个，Service 候选上限（原始 query + 受控候选）同步调整为 5；规模、份额、基准收益率、超额收益率、十大持仓 等 profile 排后续 slice。
- 受控表锚点（2026-08-09 裁决 + P0-1 实施；2026-08-11 Fix C 扩展 `performance_returns`）：Service 层对高误命中 query 类（`manager_holdings`、`holdings_top10`、`performance_returns`）组合 public tools 解析 `table_ref` 锚点注入 prompt（「候选表锚点: table-XXXX——请先 list_tables 确认表号在列，再 read_table 该表，勿自行猜测表号」，2026-08-11 与 runner 表号一致性校验对齐，锚点表号同样必须先经 list_tables 确认）；`manager_holdings` 按 9.4 行头优先、9.2 行头回退，`holdings_top10` 按表头签名（序号/股票名称/公允价值）且 row_count ≥10，`performance_returns` 按 3.2.1 表头签名（阶段/份额净值增长率/业绩比较基准收益率）且 A 类标题优先（含 A 排除 C，004393-2025 命中 table-0009）；解析失败 / document_id 为 None / 工具不可用 → fail-open 不注入（不走候选词路径的 fail-open 语义保持不变）；其余 profile 不注入锚点，保持 LLM 自由选表（Phase 7.2「全量走 LLM」的受控扩展）。（2026-08-14 第4个任务收口：`performance_returns` aliases 扩展「超额收益/超额收益率/超额/净值表现」，净值增长率/基准收益率/超额收益/净值表现词面全部进入受控路由并复用 3.2.1 表锚点；规模/份额因正文 note 数据落点且 search 首命中不可靠，排后续独立 slice，本设计不新增节锚点机制）
- 空结果收敛契约：search 连续 2 次 0 命中（interactive）→ runner 强制收敛返回「未找到相关数据」，不依赖模型自觉；有 profile 且候选词未用尽时自动用候选词重试（最多 1 轮）。候选词注入在 Service 层（chat_service 基于 `_route_plan_for_query`），收敛执行在 Agent 层（runner 不 import service）。
- 终答契约：保持「最终回答必须返回 JSON」；runner 解包（content 为 JSON 且含 answer 字段 → 提取 answer 展示，citations/key_facts 落盘）。原文粘贴检测：answer 与任一 evidence 连续重叠 ≥40 字符或 >200 字 → 有界重答 1 次，仍超标截断为 ≤200 字摘要（含省略说明；2026-08-09 F1 修复：终答 ≤200 字为 runner 硬约束，`_INTERACTIVE_FINAL_ANSWER_MAX_CHARS=200`，截断正文按 200-len(note) 计）。
- 预算：interactive `max_iterations` 20 → 12 → 8（2026-08-09 下调）；interactive 方案 E（跳过 evidence/citation 校验）保持不变（Phase 7.4 已裁决口径）。
- aggregate 开放（2026-08-09 裁决 + P0-2 实施）：`aggregate_multi_year_annual_performance` 在 interactive 开放——Service 层 handler 以 catalog 重解析 `annual_report_documents`（`_collect_matching_docs` last-wins，忽略 LLM 提供的 document_id 列表防幻觉），share_class A 类优先；ask 不开放（`ASK_SCENE_CONFIG.allowed_tools` 白名单边界）。
- 跨轮失败调用短路（2026-08-09 裁决 + P0-2 实施）：失败调用 key（与 `_dedup_key` 同结构，天然含 document_id 维度）持久化进 session（`failed_tool_call_keys`，上限 50 丢最旧，旧 session 缺字段默认空元组不回退）；相同失败调用跨轮直接短路（不调用工具、不消耗真实调用），LLM 可改参数或收尾。`_dedup_key` 工具级归一化：search 归一化 query（去空白 + CJK 标点）、read_section/read_table 按 ref（忽略 query 措辞）、get_excerpt 按 locator、aggregate 按 fund_code+years+share_class。
- 记忆注入（2026-08-09 裁决 + P1 实施）：`_build_contributions` 增加 `memory` slot，EpisodeSummary（最近 ≤3 条，总长 ≤500 token 超限丢最旧，单条超 100 token 截断加省略号）与 PinnedState `confirmed_facts` 经 `build_memory_contribution` 编织进 system prompt，标注「历史摘要，非当前证据」（引用仍须来自本轮工具返回，方案 E 不变）；空数据不产生 slot。

### 6.11 业绩抽取 A/C 分段表 + 关联 ETF 持仓源（2026-08-06 裁决）

业绩表与持仓源的语义（Mimo review ACCEPTED）：

- **业绩表 A/C 分段支持**：3.2.1 份额净值增长率表可能按 A/C 份额拆成多表/分段表（C 类段无表头、A/C 合并表出现多个「过去一年」行，实测 007466 2024/2025）。抽取规则：①「过去一年」行唯一性按 `share_scope` 过滤（每个份额类别各取自己的过去一年行），不再要求单表内全局唯一；② 无表头部分表用同 section 相邻 A 类表头对齐列定位，定位失败才 not_found；③ 验收真值（007466 A 类过去一年）：2024 净值增长率 21.06% / 基准 17.00% / 超额 4.06%；2025 4.18% / 0.47% / 3.71%。
- **报告数据表防错填**：性能字段缺失时单元格显式标「缺失」，禁止用相邻费率等其他列数据补空（实测 Ch2 曾把费率行 0.50/0.10/0.25/不收取 错填进 2024/2025 业绩列）。
- **关联 ETF 持仓集中度**：ETF 联接基金（如 007466 → 标的 ETF 512890 红利低波ETF华泰柏瑞）的持仓集中度改从关联标的 ETF 年报 top-10 提取（`.fund_checklist_512890`，2021-2025 可用）；generate 新增可选关联源参数（如 `--holdings-source-fund 512890 --holdings-source-workdir .fund_checklist_512890`），Service 层解析，报告标注「来源：标的 ETF 512890 年报」；未指定时保持本基金持仓现状，不破坏既有调用方。

### 6.12 QDII 持仓 fallback 语义（2026-08-06 裁决）

主动/指数 QDII 基金前十大持仓抽取（Mimo review ACCEPTED）：

- `search_document` 只匹配 `section.text`、不匹配 `section.title`（docling_store.py:510）；QDII 持仓章节标题「期末按公允价值…前十名股票投资明细」正文不含候选词 → equity query 0 命中。**不改 search_document public contract**。
- 持仓抽取的 QDII fallback 分支（extraction.py:1408/1462）扩展为 `"QDII" in fund_name` 且基金类型非 bond/index_feeder 即进入：先 `_QDII_HOLDINGS_QUERY`，再 `_extract_qdii_holdings_from_tables` 直接扫描（表头适配已实现：公司名称→stock_name、证券代码→stock_code、占基金资产净值比例→percentage，extraction.py:6318-6342）。
- 实测 519696 持仓表为跨页分裂表（2025 table-61 仅含第 1-5 名；2024 table-61 表头截断、数据行全在续表），直接扫描扩展为：表头被跨页截断时用续表首行碎片补齐（`_merge_qdii_header_fragments`），同章节跨页续表按列合并、跳过碎片行（首列非序号），直至 10 行；QDII 分支以直接扫描结果为准（query 路径可能只命中续表碎片行），query 路径仅作兜底。
- `_holdings_column_indexes` 对双公司名称列优先中文列（公司名称（中文）→stock_name）；A 股 股票名称 列映射不变。
- 验收样例（S1，2026-08-06）：519696（交银环球精选混合 QDII）2024/2025 top-10 各 10 行且 failure=None（2024 首行 腾讯控股/700 HK/3.33；2025 前三 腾讯控股/中国宏桥/中芯国际）。

### 6.13 QDII 费率「管理人报酬」措辞（2026-08-06 裁决）

费率抽取的措辞语义（Mimo review ACCEPTED）：

- QDII 年报把管理费表述为「支付基金管理人的**管理人报酬**按前一日基金资产净值 X%…」（无「基金管理费」字样）；`_extract_fee_rates_from_agent_result` 主/回退路径以 `_FEE_RATE_MANAGEMENT_WORDINGS`（extraction.py:142 附近）中的「管理人报酬」作标题块查找别名，输出字段仍为 `基金管理费`；`_FeeRateExtractionSpec` 正则（extraction.py:442）已覆盖 `(?:管理费|管理人报酬)`，但多年度路径不走该 spec，已同步。注意「管理人报酬」**不进入** `_FEE_RATE_TITLES`：该元组同时喂 10B 三标题契约（`_fee_rate_segments`/`_fee_rate_section_citations`），直接追加会破坏 A 股既有路径，且会把「基金管理费」块截断在注文「管理人报酬按…」处。
- 托管费 2023/2024 缺失（fee_queries 已含「基金托管费」）需逐年度 debug `search_document` → `_matched_disclosure_titles` 绑定（acceptable title family 映射）。
- 验收真值：519696 五年管理费/托管费 = 2021-2024 1.80%/0.35%、2025 1.20%/0.20%。

### 6.14 资产配置 asset_allocation 全表扫描 fallback（2026-08-06 裁决）

资产配置抽取的 fallback 语义（Mimo review ACCEPTED）：

- `search("期末基金资产组合情况")` 可能命中 caption 含查询词的**非资产配置表**（实测 519696-2023 命中 table-0059 估值表），而真正资产配置表（table-0060，表头 序号/项目/金额/占基金总资产的比例（%））caption 不含查询词 → citation 错绑后 asset_allocation 空。
- `_extract_allocation_from_agent_result`（extraction.py:6601）在 citation 表循环后增加 asset_allocation 全表扫描 fallback（与既有 industry_allocation fallback 对称）：遍历 `list_tables`，`_is_asset_allocation_table` 命中则 `_parse_asset_allocation_table`，break。
- 表结构判定/解析函数已就绪（`_is_asset_allocation_table`:6642、`_parse_asset_allocation_table`:6675），无需适配解析逻辑。

### 6.15 持有本基金 9.2/9.4 回退口径（2026-08-06 裁决）

`FundManagerInfo.holds_fund` 的抽取口径（Mimo review ACCEPTED）：

- 9.4 基金经理持有区间表存在（如 163415 A类>100万份）→ `holds_fund` = 区间文本（既有语义，命中即 break 不回退）。
- 9.4 区间表不存在（实测 519696-2025）→ 回退 9.2 从业人员整体持有（table-80「基金管理人所有从业人员持有本基金 7,312.84 份 / 0.01%」），口径标注**直接嵌入 holds_fund 字符串**（如「基金经理区间未披露；从业人员整体持有 7,312.84 份（0.01%）」），3 处渲染点（chapter_generator.py:418 / extraction.py:3720 / audit_pipeline.py:2621 的 `holds_fund or '未披露'`）零改动生效。
- `FundManagerInfo.holds_fund` docstring（models.py:624）同步更新回退语义。

### 6.16 A 股持仓表级鉴别 + 直接扫描 fallback（2026-08-07 裁决）

004393 持仓 0 行修复（R1，Mimo review ACCEPTED）：

- 根因（A/B 实证）：2022/2024 年报中行业配置表（table-0103/table-0079，表头 行业类别/公允价值/占净值比例）与真实持仓表同 section，且 caption 回填 section 标题后排序高于真实持仓表（caption 为「金额单位：人民币元」），Agent 首位 TABLE citation 命中行业配置表；`_extract_holdings_from_agent_result` 无表级鉴别，经相邻表头查找后消费 → 数据行全被列宽过滤 → 0 行 → break。
- 表级鉴别：`_extract_holdings_from_agent_result` 消费每个 citation 表前先过 `_is_holdings_table_candidate`（自身表头须含 stock_code 或 quantity + stock_name + percentage；或为债券持仓表；或为无表头续表），不满足则跳过该 citation 继续遍历，而非 break。
- 直接扫描 fallback：A 股基金（非 bond/index_feeder/QDII）agent 路径持仓为空时，`_extract_stock_holdings_from_tables` 按 list_tables 顺序扫描表头特征，命中后解析并复用 `_extract_holdings_continuations` 跨页续表合并，同步把 citation 校正到真实持仓表。
- 验收：004393 2021-2025 各年 top-10 非空（2022 首行 01088 中国神华 6.19；2024 首行 00939 建设银行 6.08）；163415/519696 持仓不回退；行业配置表不再被当作持仓表消费。

### 6.17 519696-2025 持仓第 6 名跨页断裂验证结论（2026-08-07 裁决）

R2（Mimo review ACCEPTED 计划）定位结论：

- 定位（Docling JSON + 分支跟踪）：2025 主表 table-0061（section-0599/page 49/9 列）表头完整 → `_extract_qdii_table_with_continuations` 不进 `_find_qdii_header_continuation`，走「主表 1-5 名 + `_extract_qdii_continuation_rows` 同 section 同列数续表合并」；续表 table-0062（page 50/9 列）命中，首行表头碎片（首列非序号）跳过、6-10 名数据行补齐。2024 为表头截断分支：table-0061 仅截断表头（1 行）、table-0062 承载碎片+全量数据行，合并后同样 10 行完整。
- 结论：计划所载「第 6 名仍断裂」在当前 fixture/代码上不可复现（`.fund_e2e_519696` 为 gitignored 本地再生成数据，观察可能来自 S1 开发中间态）；验收真值全部满足：2025 持仓 10 行、rank 1-10 连续、第 6 名 1209 HK/华润万象生活/2.82% 代码与占比非空；2024 不回退。
- 未采用计划修复方向 2 的字面规则（仅首列非序号且全行无代码/名称特征才算碎片）：实测续表表头碎片含名称残片（如「资源有 限公司」）而无代码/占比，按该规则会被消费为残缺持仓行，反而复现「第 6 名代码/占比丢失」；当前「首列非序号即跳过」是正确且必要的保护。修复方向 1（放宽候选范围）经定位确认为非 section/列数判定问题，未改动。
- 交付：真实 fixture 测试新增 rank 1-10 连续 + 第 6 名代码/占比非空断言；新增最小表结构模拟回归测试 `test_extract_qdii_holdings_cross_page_rank6_complete`（去掉续表合并立即失败）。生产代码零改动。

### 6.18 519696-2023 持仓表头截断修复（2026-08-07 实施）

R3（Mimo review ACCEPTED 计划）实施结论：

- 定位（Docling JSON 复核）：2023 持仓表头被 Docling 截断为「序 | 公司名称 | 公司名 | 证券代 | 所在证 | 所属 | 数量 | 公允价值 | 占基」（table-0064/page 48，仅表头 1 行），数据在续表 table-0065（page 49，首行碎片「号 | （英文） | 称（中文） | 码 | 券市场 | …」+ 11 行数据）。与 2024 不同，主表自身无数据行，且预检 `_QDII_COLUMN_KEYWORDS`（完整「证券代码」「公司名称」）直接把截断表头挡在 `_extract_qdii_holdings_from_tables` 扫描入口之外。
- 修复 1（截断前缀识别）：`_holdings_column_indexes` 对 `stock_code` 增加「证券代」前缀匹配、对 `percentage` 增加「占基」「占基金」前缀匹配；前缀匹配必须通过 `_column_has_digits` 校验（该列其余单元格含数字），表头仅一行或无数字列时 fail-closed，防行业配置表/估值表误绑。
- 修复 2（扫描入口预检放宽）：`_extract_qdii_holdings_from_tables` 改用 `_is_qdii_header_text`，接受「证券代码/证券代」与「公司名称/公司名」截断形态；真正的表级鉴别仍由 `_extract_qdii_table_with_continuations` 内 `_holdings_column_indexes` 完成（买入/卖出明细表可过预检但缺 percentage/数量列，被下游拒绝）。
- 修复 3（列位置推断兜底）：前缀识别仍失败时，`_infer_qdii_column_indexes_by_position` 按 QDII 固定列序推断——首列为序号、存在「数量」「公允价值」相邻列、占比为末列且含数字、代码列数据匹配 `\S+ [A-Z]{2}`（QDII 代码形如 700 HK / MSFT US）；任一条件不满足即返回 None。
- 链路：2023 主表（仅截断表头，前缀匹配因无数据行 fail-closed）→ `_find_qdii_header_continuation` 命中同 section 下一页 9 列表格 → `_merge_qdii_header_fragments` 拼接为完整表头 → 完整子串匹配命中 → 从续表数据行抽取 10 行。2024 主表（截断表头 + 数据行）直接由前缀识别命中。
- 验收：519696-2023 持仓 10 行（首行 3808 HK 中国重汽 4.17%，与 2025 正常表头年份行数对齐）；2021/2022/2024/2025 真实 fixture 均 10 行不回退；行业配置表/估值表/资产组合表（占基金总资产）/买卖明细表负例全部拒绝。

### 6.19 持仓 direct 扫描 citation 校正（2026-08-08 裁决）

- 持仓 direct 扫描路径（A 股 `_extract_stock_holdings_from_tables` 与 QDII `_extract_qdii_holdings_from_tables`）的 citation 必须指向实际消费的持仓主表；调用方命中 direct 时同步校正 `table_citation`，不得停留在国家（地区）/行业类别/续表碎片表。

### 6.20 search_document BM25F 检索排序增强（2026-08-12 裁决，2026-08-13 实施完成）

- 现状事实：`search_document` 候选来自 section text、table caption、bounded table rows 的子串命中（空白归一化），排序为 `(-子串命中计数, source_order)`（docling_store.py:271）。
- 决策：候选召回不变，排序升级为确定性 BM25F 多字段重排序。字段权重：section title 3.0 / section text 1.0 / table caption 2.0 / table row 1.0；`k1=1.2`；`b`：title/caption 0.35、text/rows 0.75。排序键：BM25F 分数 desc → 子串命中计数 desc → source_order asc。
- 分词：无新依赖；ASCII 单词（`[a-z0-9]+`，lowercase）+ CJK 二元组（单字符段回退一元组）；沿用空白归一化语义。
- 索引：每个 store 构建一次；document unit = section ∪ table caption ∪ bounded table row；df 按 unit 计数，avg field length 按字段统计。
- 约束：纯函数、不联网、不接 LLM、无随机；分数 round 6 位；不改 `SearchResult` 公共契约、不新增 failure code；0 命中仍返回空 tuple；excerpt/citation/locator 组装不变。
- 依据：`docs/research/dayu-agent-r-research-20260810.md` §2.1.1 / §5 建议 1；dayu 本地 `bm25f_scorer.py` 仅作算法参考，不复制代码（Apache-2.0 license gate）。
- 实现与测试：见 `.sisyphus/plans/bm25f-search-ranking-slice-20260812.md`；CIC-lite：DS 实施 + MiMo review。


### 6.21 日志 VERBOSE 级 + 有界脱敏诊断载荷（2026-08-13 裁决，规划完成）

- 现状事实：仓库无任何日志级别配置（`basicConfig / dictConfig / fileConfig / setLevel / addHandler` 均 0 命中）；现有日志仅 4 个模块的 `logger.warning`（`llm_tool_loop / chapter_generator / audit_pipeline / extraction`）；LLM provider 异常消息已保证不包含 raw body（`deepseek_llm._parse_response` 只抛固定 `_MALFORMED_MESSAGE`）。
- 决策：
  - 新增 `VERBOSE = 15` 日志级别（介于 DEBUG 10 / INFO 20），注册名 `"VERBOSE"`，幂等注册 + `verbose(logger, ...)` 帮助函数；概念级借鉴 dayu `runtime/log_levels.py`，不复制代码（Apache-2.0 license gate）。
  - 启用路径：env `FUND_CHECKLIST_LOG_LEVEL`（合法值 `DEBUG / VERBOSE / INFO / WARNING / ERROR`）；absent 或空值 → 零行为变更；未知值 → fail-fast `ValueError`（与 `FUND_CHECKLIST_LLM_PROVIDER` 一致）。CLI `main()` 入口调用 `configure_logging()`；不新增 CLI 子命令。
  - 有界脱敏诊断载荷：`build_diagnostic_payload(message, *, code / document_id / tool_name / provider / query)` 显式命名参数（未知 kwargs 抛 `TypeError`）；逐字段脱敏 + 截断（字段上限 500 字符 + `…(截断)` 后缀）；总量上限 2000 字符，超限按 `query → provider → tool_name → document_id → code` 顺序丢可选字段，`message` 永不丢。
  - 脱敏规则（正则集中定义）：`sk-`/`pk-` API key、`Bearer` token、URL query secret（`api_key/token/secret/signature/sig=`）、`local_import_id`、本地绝对路径（`/Users/`、`/tmp/`、`/private/`、`~`）、工作目录（`.fund_checklist_*`），替换为 `***`。
- 硬约束：任何诊断日志不得携带 raw provider response、API key、Bearer token、URL secret、本地绝对路径、工作目录、`local_import_id`；不改现有 `logger.warning` 语义；不改 `StreamEvent / ToolResult / FailureCode` 公共契约；不新增依赖。
- 接线点：`llm_tool_loop.run / run_stream` 入口 verbose；`deepseek_llm._parse_response` malformed 分支 verbose（只带 `llm_malformed_response` code + 安全消息，不带 body）。
- 依据：`docs/research/dayu-agent-r-research-20260810.md` §5 建议 2。
- 实现与测试：见 `.sisyphus/plans/log-verbose-diagnostics-slice-20260813.md`；CIC-lite：MiMo plan review ACCEPTED（2026-08-13，1 条 P2 措辞已按 review 修正），DS 实施待执行。

### 6.22 Tool Trace 只读分析器（operator 层）（2026-08-13 裁决，规划完成）

- 现状事实：`AgentRunResult.tool_trace: tuple[ToolTraceEntry]`（tool_name / arguments / result_kind / failure_code，`tool_loop.py:36`）；`AskQuestionResult.tool_trace` 同构（`service/models.py:1194`）；`ChatTurnResponse.tool_trace` 为字符串摘要（`chat_service.py:95`）；`MinimalHost._compute_tool_trace_summary` 已有 total/success/failure 只读统计（`minimal_host.py:423`）；CLI `--enable-tool-trace` 已有 ask 流式 TOOL_EVENT 实时显示与 interactive `[工具调用: ...]` 打印。缺口：无独立 operator 层——无结构化 report、无 typed policy、无 deterministic JSON renderer、无「分析器只读」显式契约。
- 决策：
  - 新增 `fund_agent/agent/tool_trace_analysis.py`（Agent 层，与 `ToolTraceEntry` 同层）：纯函数集，只读消费显式传入的派生 trace（`tuple[ToolTraceEntry]`）+ typed policy，输出 immutable structured report；不读 session / durable internals、不写任何状态、不落盘、不成为 truth 源（模块 docstring + 函数签名锁定）。
  - `ToolTraceAnalysisPolicy`：`large_argument_chars: int = 120`（arguments 确定性序列化长度阈值）。
  - `ToolTraceAnalysisReport`：summary（total/success/failure/unique_tools）+ by_tool（首次出现顺序、failure_codes 去重保序）+ findings + limitations（固定 4 条：trace 是派生视图不含 raw payload；arguments 仅含显式参数；provider 首轮失败 trace 为空显示 0 次；分析只读不成为 truth 源）。
  - findings 确定性规则：`failed_call`（每条失败 entry 一条，failure_code 用 `.value` 归一化，与 `main.py:430` 一致）；`repeated_failure`（同一 `(tool_name, failure_code)` ≥2 次补一条）；`large_arguments`（序列化长度 > 阈值一条，`==` 阈值不触发）。
  - JSON renderer：`tool_trace_analysis_to_json(report)` → `json.dumps(asdict, ensure_ascii=False, sort_keys=True, indent=2) + "\n"`；`analyze_tool_trace` / renderer 均对类型不符抛 `TypeError`（显式契约）。
- 硬约束：不改 `AgentRunResult / ToolTraceEntry / AskQuestionResult / StreamEvent / ToolResult / FailureCode` 公共契约；不支持 session `ToolCallSummary` / 字符串摘要输入（backlog）；不新增 CLI 子命令；不引入 dayu 代码（Apache-2.0 license gate，仅概念对齐）。
- 接线点：ask 流式路径成功分支（`cli/main.py` `result = service.ask_question(...)` 后、`return SUCCESS_EXIT_CODE` 前），`--enable-tool-trace` 开启且 trace 非空时追加 `[工具分析: 共 N 次 / 成功 S / 失败 F]` + findings 行；`--no-stream` JSON 输出不含分析字段；TOOL_EVENT 实时显示不变。
- 依据：`docs/research/dayu-agent-r-research-20260810.md` §2.2.7 / §5 建议 3；dayu `service/tool_trace_analysis.py` + `host/tool_trace_analysis.py` 仅作边界参考（Analyzer 只读消费派生 trace，不成为 durable truth）。
- 实现与测试：见 `.sisyphus/plans/tool-trace-operator-slice-20260813.md`；CIC-lite：MiMo plan review `NEEDS_FIX`（2026-08-13，3 项最小修复——failure_code 用 `.value`、by_tool 首现顺序显式断言、large_arguments `==` 阈值边界——已按 review 原文修正），DS 实施待执行。

### 6.26 投资者偏好分析（Flomo 导入 + 问卷基线 + 季度偏好快照）（2026-08-20 讨论稿）

- 定位：面向投资者本人的**自我认知工具**，与基金文档分析主链并列的第二个产品模块。输入 = 私人笔记（Flomo 导出）+ 自报问卷 + （远期）真实持仓；输出 = 偏好画像（C1-C5）+ 季度偏好快照（声明 vs 行为对照 + 四问反思）。确定性优先，MVP 不接 LLM。
- 产品形态（2026-08-20 用户裁决 C）：问卷基线（自我声明）+ 行为证据对照（Flomo + 真实持仓收益），季度输出对照与反思。
- 依据：AMAC 投资者风险承受能力调查问卷相关指引文章（2019-12-22，amac.org.cn/fwdt/wyb/jgdjhcpbeian/zcglcpba/xgzc/201912/t20191222_19879.html）；有知有行材料页 / 基金 CT（youzhiyouxing.cn/x/ct）/ 数据页（youzhiyouxing.cn/data）/ 《和你聊聊「知行温度计」幕后的事》（youzhiyouxing.cn/n/materials/172，2026-08-20 补充）；`docs/research/fund-assistant-expansion-and-behavior-20260815.md`（持仓估值、市场温度计、投资者行为矫正研究）。

#### 6.26.1 已裁决项（2026-08-20，用户 7 项决策）

1. **产品形态 C**：问卷基线 + 行为证据对照 + 季度输出。
2. **将增加基金持仓导入**：设计 xlsx 持仓表格读取与解析（契约草案见 6.26.5）。
3. **flomo import 子命令**：解析 HTML → 结构化 memo（时间/内容/图片引用）；存储格式 = SQLite（2026-08-21 裁决 B，见 6.26.4）；图片首版仅引用不解析（2026-08-21 确认，见 6.26.4）；zip 与解压目录走 gitignore（见 6.26.3）。
4. **画像模型**：第一轮 AMAC 100 分制五类（C1-C5）；第二轮丰富维度采用有知有行答题模式（情境/行为题），分值表自建并标注非官方。（2026-08-21 更新：第一轮基线版题库已裁决改为融入有知有行五大板块结构、自建 80 题，见 §6.26.6；C1-C5 已裁决保留为辅助输出，见 §6.26.6）
5. **季度更新**：复用 `snapshot-quarterly` 的季度节奏，产出"偏好快照报告"；反思四问模板。
6. **合规边界**：偏好画像 + 反思允许输出，须带免责声明；资产大类比例建议放行（方案 A，适用于所有 LLM 通道，免责声明文案已确认），AGENTS.md 已按此修改（2026-08-20 裁决，见 6.26.7）。
7. **MVP 范围**：Slice P1 Flomo 导入 + Slice P2 问卷基线 + Slice P3 季度偏好快照模板（确定性，不接 LLM）；行为证据对照为第二切片（Slice P4）；后续 slice 逐个设计。

#### 6.26.2 外部参考事实与边界

- **AMAC 指引（2019-12-22 文章）**：五维框架 = 基本信息（年龄/学历/职业）、财务状况（收入/可投资资产比例）、投资知识经验、投资目标（期限/目的）、风险偏好（态度/最大可承受损失）；100 分制；**分值表与评级映射由机构自定**，指引只给框架；输出 C1-C5（保守/稳健/平衡/成长/进取）。私募合格投资者门槛（金融资产 ≥300 万 或 三年年均收入 ≥50 万）与本工具无关，不采用。
- **适当性管理规则**：2017 年《证券期货投资者适当性管理办法》配套指引要求测评至少每两年更新；2026-06 中基协公募适当性新规：测评有效期 ≤12 个月、单日评估 ≤2 次、12 个月累计 ≤8 次、风险等级改变须重新评估。本工具为自我认知用途，仍按"季度可重测、结果带时间戳"设计，不与机构合规义务混同。
- **有知有行「合格基金持有人测评」**（2024-05 上线，一手来源：知行周报 materials/1682 + E144 播客文字稿，2026-08-21 补充）：
  - 定位：**不是风险等级测评（C1-C5），而是一场"合格持有人"考试**——评估基金投资的"最小知识集"，理念 = "做 80 分投资者就可以了，更多的努力 ≠ 更多的收益"，季凯帆（《解读基金》作者）参与考纲搭建。
  - 规模：80 道题、平均 40 分钟完成；初版出到 150 道，精简至 80；考试大纲迭代两次；公司内部两场模拟考。
  - 五大板块：基金常识 / 投前准备 / 系统投资 / 投资心态 / 实战经验（3 认知篇 = 基金常识 / 投前准备 / 系统投资，2 行动篇 = 投资心态 / 实战经验）。
  - 考纲哲学：不考价值投资定义/市场走势分析/财务报表，只考"好资产、好价格、长期持有"、A 股美股基本认知、如何规划好每一笔钱。
  - 产品设计：题目分三个部分、难度依次递进；限时考场（每周三 20:00-22:00）；完成发徽章「知识的缝隙」。
  - 公开样题（播客披露）："十年十倍需年化约 26%"；"10000 元买入下跌 30% 回本需涨 43%（直觉 30% 是错的）"；"资金进出决定投资者收益（基金收益 ≠ 基民收益）"；"别人推荐基金时如何判断可信"；"中概股高点 -50% 买入、再跌 80% 时亏损 -60%（非直觉相加的 -130%）"；"A 股长期年化约 9.61%（过去 19 年）"。
  - 输出形态：**总分 100 + 五维子分**（用户实测 90 分 = 基金常识 79 / 投前准备 85 / 系统投资·投资心态·实战经验 满分，E144 评论区实证）；复习包 = 投资第一课 / 投资ABC / 中国大类资产 2023 年报 / 海外投资白皮书 / 有理有据。
  - 打分：公开层面只有理念（80 分线是隐喻，非披露分数线），**具体分值表与合格线未公开**。
  - 结论：第二轮只能借鉴出题形态（板块划分、情境题/行为题、难度递进），题库与分值表必须自建并标注"非官方、自行设计"。
- **基金 CT（youzhiyouxing.cn/x/ct）**：投资者年化收益率 vs 基金收益差距、持仓言行一致（vs 业绩基准）、完整成本（含换手率交易成本）、基金经理员工跟投——作为第二切片"组合体检"的概念基准。
- **市场温度计**：一手来源《和你聊聊「知行温度计」幕后的事》（youzhiyouxing.cn/n/materials/172）：样本 = A 股所有上市公司；指标 = 综合 PE 与 PB；加权 = **等权**（非市值加权）；考察周期 = **覆盖两轮完整牛熊周期**；温带 = 官方三档 低估 0-30° / 中估 30-70° / 高估 70-100°；应用语义 = 大周期择时（低估买入、高估兑现），短期温度小幅变化无效，高估温带买入持有 5 年平均累计收益为负，历史统计不承诺未来；**精确算法未公开**（官方明示"出于保密的要求"）。
  - 数据页一手事实（youzhiyouxing.cn/data，2026-08-20）：当前 49° 中估；官方温带概率表 = 低估 40% 发生概率（买入持有 5 年盈利概率 >95%）、中估 38%（>90%）、高估 22%（>35%）；**不提供历史温度序列导出与 API**；官方对数据不完整的指数（中国互联网指数、中证2000）明确"暂不提供内在收益率"——与 fail-closed 口径一致。
  - 自制路径（`docs/research/fund-assistant-expansion-and-behavior-20260815.md` §1.3，修正对齐官方口径）：akshare 中证全指 000985 日频 PE/PB → 等权分位合成（`0.5·PE分位+0.5·PB分位`）×100，考察窗口以覆盖两轮完整牛熊为准（约 5-8 年，须含 2018 熊市与 2021 牛市）→ 档位对齐官方三档（如需可加 ≥90 极度高估为自制扩展）→ 连续函数映射股债现金比例；必须标注"有知有行风格自制，非官方公式"。

#### 6.26.3 数据源与隐私边界（Flomo）

- 事实：`docs/flomo@多多爸爸-20260819.zip`（用户私人笔记导出）已解压至 `docs/flomo-export-20260819/`，主体 `多多爸爸的笔记.html`（331 条 memo，2023-01-16 ~ 2026-04-14）+ `file/` 28 张图片。
- 硬约束：私人笔记**只本地处理，不进 git**。`.gitignore` 新增：
  ```
  # Flomo 私人笔记导出（本地只读，不进 git）
  docs/flomo@*.zip
  docs/flomo-export-*/
  ```
- 导入产物写入 `--work-dir`（默认 `.fund_checklist`）下 `preferences/` 子目录，同样受 `.fund_checklist*/` ignore 覆盖；**不允许**把 memo 内容写入任何被 git 跟踪的目录。

#### 6.26.4 Flomo 导入设计（Slice P1）

- 命令：`flomo-import --html <path> --work-dir <dir> [--images-dir <path>]`。
- 解析契约（HTML 结构已实证）：
  - 每个 `.memo` 容器 = 一条 memo；`.time` 元素格式 `YYYY-MM-DD HH:MM:SS`（精确到秒，实测如 `2026-04-14 19:22:20`）；`.content` 内 p/ul/ol/li 文本为正文，`<br>` 转换行；`<img src="file/...">` 为图片引用（src 是相对导出根目录的路径）。
  - 结构化输出字段：`id`（`flomo-<YYYY-MM-DD>-<序号>`）、`created_at`（ISO8601，+08:00）、`content`（纯文本，列表层级转缩进文本）、`images`（相对路径数组，保留原文件名）、`source`（导出文件相对路径 + HTML 内偏移，供溯源）。
- **存储格式（2026-08-21 已裁决：SQLite）**：
  - 理由（用户裁决 B：便于长期使用）：偏好域将跨季度积累问卷结果、快照、持仓，SQL 式关联查询（某季度快照 ↔ 该季度 memo ↔ 持仓变动）是长期主路径；SQLite 用 Python 标准库 `sqlite3`，**不新增第三方依赖**；单文件随 work-dir 隔离（`preferences.db` 在 `.fund_checklist*` 下，天然被 ignore）。
  - 落盘：`preferences/preferences.db`，表结构草案：
    - `memos(id, created_at, content, images_json, source)`——flomo 导入，`images_json` 存相对路径数组；
    - `questionnaire_results(id, answered_at, dimension_scores_json, total_score, risk_level, answers_json)`；
    - `preference_snapshots(id, quarter, created_at, questionnaire_result_id, behavior_summary_json, reflection_json, disclaimer)`；
    - `holdings(id, fund_code, fund_name, shares, cost_price, buy_date, note, updated_at)`。
- **图片处理（2026-08-21 已确认）**：首版仅引用路径，不解析内容，后续 opt-in OCR：
  - 事实：管线 Docling 默认 `do_ocr=False`（OCR 非主路径）；Flomo 图片多为笔记截图。
  - 口径：`images` 字段只保留相对路径，memo 文本已含主要信息；不新增 OCR 依赖与不确定性。
  - 后续：若图片含正文未记录的关键信息（如持仓/交易截图），第二切片做 opt-in 单图提取（本地文件 → 复用 Docling 单图转换或显式不支持，明确分类）。
- 幂等与校验：重复导入同一导出（按 `exported_at` + memo 数指纹）→ 报告 cached 不覆盖；HTML 结构不匹配 → `schema_drift` 分类失败，fail-closed。

**Slice P1 实现设计（2026-08-21 落盘）**：

- 解析器：Python 标准库 `html.parser.HTMLParser` 子类状态机（不新增第三方依赖）。状态 = 当前 `.memo` 容器 / `.time` / `.content` / `.files`；`<br>` → `\n`，`<li>` → 缩进项目符号，`<img src="file/...">` → 追加 images 数组（相对导出根路径）。正文纯文本化，列表层级转缩进。
- 库表（`preferences/preferences.db`，`sqlite3` 标准库）：
  - `memos(id TEXT PK, created_at TEXT, content TEXT, images_json TEXT DEFAULT '[]', source TEXT)`；
  - `imports(id INTEGER PK AUTOINCREMENT, source_path TEXT, fingerprint TEXT UNIQUE, memo_count INTEGER, imported_at TEXT)`——导入事件表，`fingerprint = sha256(exported_at + 全部 memo 的 created_at+content 前 64 字符)`，用于幂等。
- 导入流程：解析 HTML → 校验结构（无 `.memo` 或 `.time` → `schema_drift` fail-closed）→ 计算指纹 → 已存在则输出 cached（含首次导入时间与 memo 数，不覆盖）→ 否则事务写入 `memos` + `imports`，输出 imported（memo 数、图片引用数、db 路径）。
- 失败分类：HTML 文件不存在 → `not_found`；结构不匹配 → `schema_drift`；SQLite 打开/写入失败 → `unavailable`；均 fail-closed，不产生部分导入。
- 测试计划：① 单元——小型 HTML fixture（memo/time/content/br/ul/img）验证解析字段与图片数组；② 单元——结构不匹配 fixture → `schema_drift`；③ 单元——同 fixture 重复导入 → cached 不覆盖；④ 端到端——fixture HTML 经 `fund-checklist flomo-import` CLI → 验证 `memos` 行与 `imports` 幂等；⑤ 真实导出文件（331 条）作为手动 smoke 可选，默认测试不依赖私人数据。
- 边界：不解析图片内容；不把 memo 写入任何 git 跟踪目录（写 `--work-dir` 下 `preferences/`，受 `.fund_checklist*/` ignore 覆盖）；不接 LLM。

#### 6.26.5 持仓表格导入（xlsx，契约草案，待用户确认列）

- 命令（后续 slice）：`portfolio-import --xlsx <path> --work-dir <dir>`。
- 依赖：需新增 `openpyxl`（当前 pyproject 仅有 docling + rich，**无 xlsx 依赖**，待裁决）。
- 表格列契约草案（单 sheet，首行表头）：

  | 列 | 类型 | 必填 | 校验 |
  |---|---|---|---|
  | 基金代码 | str 6 位数字 | 是 | 正则 `^\d{6}$` |
  | 基金名称 | str | 否 | 与代码不一致仅 warning |
  | 份额 | float >0 | 是 | 缺失/非法 → `schema_drift` |
  | 成本价 | float ≥0 | 否 | 缺失记 null，估值用最新净值 |
  | 买入日期 | date YYYY-MM-DD | 否 | 非法 → `integrity_error` |
  | 账户/备注 | str | 否 | 透传 |

- 语义：持仓 = 用户自报组合，与基金文档 catalog 分离；后续估值用已导入快照/年报最新净值（或 akshare 日频，远期）。
- 输出：`preferences/preferences.db` 的 `holdings` 表（fund_code → shares/cost/buy_date），重复导入按（fund_code + 买入日期）upsert。

#### 6.26.6 问卷基线设计（Slice P2，有知有行板块结构 + 80 题，2026-08-21 裁决）

- **题库口径（2026-08-21 用户裁决：融入有知有行板块结构，题库 80 道）**：
  - 题库自建 80 题基线版，按有知有行「合格基金持有人测评」五大板块组织：基金常识 / 投前准备 / 系统投资 / 投资心态 / 实战经验（3 认知篇 + 2 行动篇）；难度三档递进；情境题与行为题（样题与考纲哲学见 §6.26.2）。
  - 题库 JSON：仓库资产 `fund_agent/preferences/questionnaire/baseline-v1.json`（git 跟踪，题目/选项/分值/板块/难度/解释），标注"非官方、自行设计，考纲参考有知有行合格基金持有人测评"；答题结果才写 work-dir（`preferences/questionnaire/results/`），题库本身不是 work-dir 产物。
- **评分（自建口径，标注非官方；有知有行未公开分值表）**：
  - 输出形态 = 总分 100 + 五维子分（对齐有知有行实测输出：90 分 = 基金常识 79 / 投前准备 85 / 其余三维满分）。
- 五维权重（2026-08-21 用户确认草案）：基金常识 25 / 投前准备 20 / 系统投资 20 / 投资心态 20 / 实战经验 15（合计 100）；权重记录在题目 JSON 中，可调；后续可寻找更多参考资料对齐有知有行。
  - 板块得分 = 该板块题得分率 × 板块权重；总分 = 五维得分之和。
- **C1-C5 档位（2026-08-21 用户裁决：选 A，保留为辅助输出）**：主输出 = 总分 100 + 五维子分；辅助输出 = C1-C5 风险等级（从投资心态/实战经验板块中风险承受相关题项映射，供季度快照"声明 vs 行为"对照基线）；原 AMAC 五维权重与 C 级档位（0-19/20-36/37-53/54-75/76-100）仅作历史参考，不再作为第一轮骨架；后续 slice 对齐有知有行（用户画像、成熟度等）。
- 命令：`preference-questionnaire --work-dir <dir>`（交互答题，TTY 提示 / 非 TTY 读 JSON 答案文件 `--answers`）。
- 产出：`preferences/questionnaire/results/YYYY-MM-DD.json`（五维子分/总分/逐题答案快照）+ `preferences.db` 的 `questionnaire_results` 表。
- 频次约束：季度节奏可重测；每次结果带时间戳，不覆盖历史；报告中标注"自我认知用途，非机构适当性测评"。
- 第二轮（待设计）：在有知有行结构上进一步丰富维度（候选：行为证据对照、个性化错题重测、难度自适应），逐个设计。

#### 6.26.7 季度偏好快照（Slice P3）与合规边界

- 命令：`preference-snapshot --work-dir <dir> --quarter 2026Q3`（MVP 仅确定性路径，不接 LLM）。
- 节奏：复用 `snapshot-quarterly` 的季度节奏（每季度一份，时间戳命名）。
- 报告内容：
  1. 问卷基线（当时总分 + 五维子分 + 辅助 C1-C5）；
  2. 本季度行为证据摘要（来自已导入 `preferences.db` 的 `memos` 表：季度内投资相关条目按关键词/日期过滤，引用原文 + 时间；不读原始 HTML）；
  3. 四问反思（模板，问答形式）：本季度实际做了什么 → 与声明一致吗 → 偏差在哪 → 下季度调整什么；
  4. （可选，后续 slice）组合体检对照：投资者年化收益 vs 基金收益、言行一致、完整成本（概念基准：有知有行基金 CT）。
- 产出：`preferences/quarters/2026Q3/preference-snapshot.json` + markdown。
- **合规硬边界**：
  - 所有偏好画像/反思/配置建议输出必须附固定免责声明："本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"
  - MVP 只输出"声明 vs 行为"对照与反思，**不输出任何调仓/配置建议**（避免触碰 AGENTS.md 硬规则）。
  - 若启用资产大类比例建议（远期），必须先完成 AGENTS.md 放宽（见下）。
- **AGENTS.md 修改（2026-08-20 已裁决，已生效）**：裁决 = 方案 A（资产大类比例）+ 生效范围 = 所有 LLM 通道（interactive / ask 等）+ 免责声明文案确认。AGENTS.md 禁止事项已改为：
  - "禁止对个股、单只基金输出买入/卖出/增持/减持等操作指令与择时建议。允许输出资产大类配置比例建议（债券基金 / 货币基金 / 股票指数基金 / 主动式权益基金 / FOF），适用于所有 LLM 通道（interactive / ask 等），前提：① 基于公开披露数据或用户自报持仓；② 输出必须附固定免责声明「本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益」。"
  - 保留不动："禁止预测未来收益或市场走势"；"禁止超出公开披露信息的因果推断"。
  - 实现联动（另开 slice）：`llm_tool_loop.contains_investment_advice` 拦截口径需同步评估——资产大类比例建议含"建议"指令动词时当前守卫是否误拦/放行，须有明确口径，不能靠 AGENTS.md 文字与守卫实现漂移；落地前守卫行为不变。

#### 6.26.8 第二切片与远期规划

- Slice P5（第二切片，原 P4）：行为证据对照——memo / 思考记录 投资关键词抽取（买卖/加仓/减仓/亏损/收益 等）+ 持仓变动 vs 问卷声明一致性打分（确定性规则，不接 LLM）。
- 远期（用户规划，逐个设计）：① 基金组合体检（投资者年化收益 vs 基金收益、言行一致、完整成本）；② 持仓估值（已导入净值 / akshare 日频）；③ 市场温度计（akshare 中证全指 000985 PE/PB 等权分位，自制非官方；温度不可得的备用计算方案见下）；④ 温度驱动持仓调整提示（仅提示过热风险与权益/债券/现金比例建议，不做具体操作）；⑤ 可视化工作台。
  - **温度不可得备用计算方案（2026-08-20 补充，依据 youzhiyouxing.cn/data 与 `docs/research/fund-assistant-expansion-and-behavior-20260815.md` §1.3）**：fallback 链按失败分类显式驱动，**禁止用过期缓存冒充实时值**——
    1. 主方案：akshare 中证全指 000985 日频 PE/PB → 等权分位合成（`0.5·PE分位+0.5·PB分位`）×100 → 官方三档温带；
    2. 备 1（双源校验）：中证指数官网估值页（csindex）同口径 PE/PB 计算；
    3. 备 2（替代数据源）：GitHub `hillerliao/index_valuation`（A 股指数估值实时+历史）或 defeatbeta-api 开源行情库；
    4. 备 3（降级口径）：000985 数据缺失时改用沪深300 PE/PB 计算，输出必须标注"样本口径与官方不一致"；
    5. 兜底（fail-closed）：全部数据源不可得时**不输出温度、不给出配置提示**，报告标注"温度数据不可得"；可附官方 app 当前展示值（如 49° 中估）作人工参考，必须标注"来源 = 官方 app 展示值，非自制计算"。
- 温度计/组合体检涉及外部数据（akshare）与新增依赖，**不在 MVP 范围**；进入实施前单独裁决数据源合规与依赖准入。

#### 6.26.9 裁决进度（2026-08-21 更新）

- ✅ 已裁决（2026-08-21）：① 存储格式 = SQLite（见 6.26.4）；② 图片 = 仅引用路径，后续 opt-in OCR；③ 问卷题库口径 = 融入有知有行五大板块结构 + 自建 80 题（见 6.26.6）+ C1-C5 保留为辅助输出（选 A，见 6.26.6）+ 五维权重确认草案 25/20/20/20/15（见 6.26.6）；④ xlsx 列契约 = 按 6.26.5 草案；⑤ 命令 = `preference-snapshot --quarter YYYYQn`，每季度一份；⑥ `openpyxl` = 持仓导入 slice 开始时引入，不进 MVP；⑦ 温度计/组合体检 = 列入 MVP 之后的下一阶段规划，逐个设计。

#### 6.26.10 智慧笔记数据导出导入（Slice P4：note-import，2026-08-22）

- 数据源事实：用户邮箱（xingchen0150@agent.qq.com）2026-08-11 收到邮件「我的思考记录」（发件人 星辰 632217862@qq.com，智慧笔记小程序数据导出）。导出文件已保存为 `docs/note-export-20260811/思考记录-20260811.html`（`.gitignore` 已含 `docs/note-export-*/`）。正文为 div 包裹的 Markdown 渲染 HTML：`# 智慧笔记 - 数据导出` + `导出时间：YYYY-MM-DD HH:MM` + `总记录数：N 条` + `## 类别` + `### 序号. 标题` + `> 分析时间：` + `> 状态：` + `**原始问题：**` / `**分析结果：**` 分节。实测 65 条 = 分析记录 20 / 多维度分析 20 / 孵化报告 5 / 结构分析 20。
- 隐私边界：与 Flomo 同口径（§6.26.3）——只本地处理、不进 git；导入写入 `--work-dir` 下 `preferences/preferences.db`（受 `.fund_checklist*/` ignore 覆盖），与 memos 同库。
- 命令：`note-import --html <path> --work-dir <dir>`（对齐 `flomo-import`，不接 LLM）。
- 解析契约：标准库实现（`</div>`→换行、去标签、HTML unescape 后按 Markdown 结构解析），产出 `ThoughtNote(id, category, title, created_at, status, content, source)`：
  - `id` = `note-<导出日期 YYYYMMDD>-<category-key>-<序号>`（category-key：analysis / roundtable / incubator / structure，未知类别 fail-closed）；
  - `created_at` = `> 分析时间：` 或 `> 生成时间：`（孵化报告用后者）→ ISO8601 +08:00；`status` = `> 状态：` 原文优先，无状态行时取 `> 类型：` 值（结构分析用），两者皆无 → `未知`；`content` = 该记录全文（保留 `**原始问题：**` / `**分析结果：**` 分节、多导师 `####` 子节、孵化/结构分析的 `## 一、` 子标题）；
  - `##` 行规则：`## 目录` 跳过；`## 已知类别` 切换类别并结束当前记录；其他 `##`（记录已打开）归入当前记录 content 不结束记录；无记录打开时的未知 `##` → `schema_drift`；
  - header 缺失「导出时间」/「总记录数」或声明条数与实解析数不一致 → `schema_drift` fail-closed（防静默丢记录）；无 `分析时间`/`生成时间` → `schema_drift`。
- 存储：`preferences.db` 新增 `thought_records(id TEXT PK, category, title, created_at, status, content, source)` 与 `note_imports(id INTEGER PK AUTOINCREMENT, source_path, fingerprint TEXT UNIQUE, exported_at, record_count, imported_at)`；fingerprint = sha256(exported_at + 全部记录 title+created_at+content 前 64 字符)；同指纹重复导入 → cached 不覆盖，单事务写入。
- 失败分类：文件不存在 → `not_found`；解析失败（结构/条数/必填元数据不符）→ `schema_drift`；SQLite 打开/写入失败 → `unavailable`；均 fail-closed，不产生部分导入。
- 与第二切片关系：thought_records 为行为证据对照（Slice P5）新增证据源（投资关键词抽取范围扩到 memos + thought_records）。
- 测试计划：构造样例 `tests/fund/preferences/fixtures/note_sample.html`（非私人数据，4 类别各含代表性记录）覆盖解析字段/类别映射/序号/幂等/声明条数不符/缺失分析时间；CLI e2e 覆盖成功/not_found/schema_drift/cached；真实导出（65 条）作为 controller 手动 smoke。

#### 6.26.11 新增规划想法（2026-08-22，用户口述，待逐个设计）

- **想法 A：每 6 个月一次的问卷调查定时任务**——主动收集用户最新风险偏好变化情况。
  - 与现有节奏的关系：当前设计为「季度可重测、结果带时间戳」（§6.26.2，用户主动跑）；定时任务 = 主动提醒/调度，按 6 个月周期触发问卷。
  - 待裁决：① 定时形态（CLI 提醒子命令 / 系统调度 crontab / 应用内提醒）；② 与适当性新规「测评有效期 ≤12 个月」的衔接（6 个月周期兼容，需在快照/报告中标注最近测评时间与有效期）；③ 复用 `baseline-v1` 80 题还是新增「风险偏好变化」专用短卷（对比上一轮结果输出变化轨迹）。
- **想法 B：结合有知有行知识体系构建知识库，支持投资者学习与成长**。
  - 合规边界（先决问题）：有知有行材料（materials / 播客 / 课程 / 付费内容）为第三方版权内容，**禁止未经许可复制付费/独家内容**；可行路径 = 自建摘要/结构化笔记 + 原文链接引用，题库沿用 §6.26.6「自建 + 标注非官方」口径。
  - 待裁决：① 知识库形态（本地 SQLite 笔记 / 文档目录 + 检索，是否复用 `thought_records` / `memos` 统一存储）；② 内容来源准入（公开材料清单 + 版权审查）；③ 学习路径（按五维板块组织 + 答题后推荐阅读）。
  - 定位：MVP 之后的下一阶段，与温度计/组合体检（§6.26.8）同属远期候选，进入实施前单独设计。

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
- 确定性信号评分（基金类型感知：主动基金 6 指标 135→100 归一化；被动基金 3 指标 100 分制）
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
- 2026-08-03 补充（fee_rates 聚合语义）：fee_rates contract 允许路由聚合全部三个 candidate query 的 success 结果（`aggregate_all_matches=True`），因为各 query 的确定性 answer 存在正文互补（销售服务费费率正文只出现在「销售服务费」query 的 answer）；聚合时按标题块去重（剥离「相关表格:」金额表块），citations 按 locator 去重合并；section citation 覆盖按 `section_ref` 去重统计，TABLE locator 携带的 `section_ref` 计入（table-0052 → section-0398 已验证）。该语义只作用于 fee_rates，holdings / performance 等契约保持标题去重聚合。
- 2026-08-04 补充（百分比归一化 + 当期适用费率实现细则）：Docling 分块可能把 `1.50%` 切成 `1.  50%`（数字与小数点/百分号间出现空白），抽取前必须做百分比邻域归一化（`1.  50%` → `1.50%`），否则正则失配会误捕获相邻费率（163415-2022 管理费误取 0.25%）或返回 not_found（163415-2021 管理费）。费率沿革披露（「自 YYYY 年 M 月 D 日起…」）只取「自…起」之后的当期适用费率；无沿革文本时取该费率标题块内最后一个百分比（年报注文以当期费率结尾）。10C 路径 `_extract_fee_rate_fields` 已实现沿革选择（多匹配且含「自 YYYY」时取最后一个），多年度报告路径 `_extract_fee_rates_from_agent_result` 同步该语义。163415 五年度验收样例：管理费/托管费 2021 1.50%/0.25%、2022 1.50%/0.25%、2023 1.20%/0.20%、2024 1.20%/0.20%、2025 1.20%/0.20%；销售服务费 C 类仅 2025 披露 0.60%（其余年份无费率正文）。

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
- title-family 判定支持 raw-excerpt 兜底：Docling section 切分把 3.2.1 标题嵌在「3.2 基金净值表现」正文内（answer 首行非标题）时，以 answer 正文包含 title-family 判定命中；answer 为有界公开输出，下游仍要求 SECTION/TABLE citation、列签名与「过去一年」行。
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
- `missing_years` 保持年份列表；新增 `missing_year_notes`（year + reason）逐条解释缺失原因（单年度抽取失败复用 10F/10G 的 NOT_FOUND message、catalog 无该年度年报时说明「未导入或未匹配」、无显式原因时补默认说明）；数值语义与 failure taxonomy 不变。
- DTO 形态沿用 10H：`MultiYearAnnualPerformanceSeries` 包含 `fund_code`、`requested_years`、`covered_years`、`missing_years`、`coverage_status`、`coverage_count`、`minimum_required_count`、`share_class_scope`、`rows`、`citations`、`missing_year_notes`。
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
- candidate queries 固定为原始 query、`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`、`业绩比较基准收益率`。2026-08-11 Fix E 更新：首位加入 `净值增长率`（原已是 alias，仅调候选词顺序；004393「近一年净值增长率」问答空搜索自动重试时首命中 section-0097 含 12.77% / 基准 15.34%）。
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
report_type 支持 annual_report；semiannual_report / quarterly_report（快照，quarterly document_id 带 -Q[1-4] 期次段，见 §6.25）
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

### 已接受的 Slice（按时间顺序）

- **Slice 10F**：annual performance table extraction from title-family matched table。✅ 已完成。
- **Slice 10G**：annual excess return disclosed-field extraction。✅ 已完成。
- **Slice 10H**：multi-year annual performance source contract with bounded year coverage。✅ 已完成。
- **Slice 10I**：multi-year annual performance aggregation service。✅ 已完成。
- **Slice 10J**：multi-year performance service-to-agent exposure contract（docs-only）。✅ 已完成。
- **Slice 10K**：multi-year performance fake/injected Agent tool-loop。✅ 已完成。
- **Slice 11A**：performance disclosure locator，插入 10D 之前。✅ 已完成。
- **Slice 11B**：disclosure locator contract registry。✅ 已完成。
- **Slice 10L**：multi-year performance CLI integration。✅ 已完成。
- **Slice 10M**：batch PDF import。✅ 已完成。
- **Slice 11C**：holdings multi-year tracking。✅ 已完成。
- **Slice 11D**：asset allocation + fee rates multi-year tracking。✅ 已完成。
- **Slice 12A**：Host lifecycle basics。✅ 已完成。
- **Slice 12B**：Disclosure completeness audit。✅ 已完成。
- **Slice 12C**：Deep disclosure audit。✅ 已完成。
- **Slice 13A**：Fund report generation。✅ 已完成。
- **Slice 13B**：LLM-generated chapter text。✅ 已完成。
- **Slice 14A**：Template-aligned report generation。✅ 已完成。
- **Slice 14C**：Chapter audit pipeline。✅ 已完成。

### Phase 1：稳定化

- **Slice 15A**：提交遗留 + 清理 smoke work-dirs + full regression。目标：main 干净可复现。✅ 已完成。
- **Slice 15B**：拆分 reading_service.py（5533 行 → models + chapter_generator + extraction）。✅ 已完成。

### Phase 2：Ch7 结构化信号 + 模板区块补齐

- **Slice 16A**：Ch7 确定性信号判断 + Ch6 风险清单表。✅ 已完成。含加权 Jaccard 风格漂移检测。
- **Slice 16B**：Ch6 压力测试表。✅ 裁决已确认。按基金类型选阈值（index_fund/bond_fund/active_fund），从年报取规模+净值增长率+基准收益率，计算三档场景损失金额 + 超额收益 stress_level。
- **Slice 16C**：Ch0 升级/降级阈值事件 + 一句话产品定义。从 Ch7 信号反推 Ch0 封面。

### Phase 3：报告质量 + 可用性

- **Slice 17A**：报告 Markdown 持久化 + metadata sidecar（fund_code, year, audit_score, generation_time）。✅ 已完成。
- **Slice 17B**：citation 验证工具（给定 citation locator → 定位年报原文 → 返回上下文片段）。✅ 已完成。
- **Slice 17C**：CLI 端到端 smoke（真实 PDF → 完整报告 → 审计产物落盘 → exit code 验证）。✅ 已完成（发现 3/8 章失败，触发 Phase 3.5）。

### Phase 3.5：报告质量稳定化（阻塞 Phase 4）

> 17C 验证发现 Ch2/Ch3/Ch5 生成失败、Ch4 为硬编码占位符。根因：单年数据无降级策略、LLM 分析约束不足、审计阈值与数据现实脱节。

- **Slice 17D**：Ch2 单年降级 + Ch3 fund_manager 抽取修复 + LLM 分析约束。Ch2 单年导入时输出结构化缺失声明；Ch3 修复 table locator 跨 section 匹配 bug（按 section title 关键词匹配 + ±10 fallback）；Ch3 LLM 禁止从持仓反推基金经理意图。
- **Slice 17E**：Ch4 报告年份适配 + Ch5 must_answer 结构化规则。Ch4 report_year < 2026 时输出 N/A 声明；Ch5 定义阶段判定（5选1含优先级，时间窗口同比）、关键变化阈值（持仓换手>40%/规模同比>30%/费率>0.1%）。
- **Slice 17F**：审计管道数据适配。data_sources 缺失时 LLM 审计权重 70%→50%，数据不足场景通过阈值降至 ≥70。
- **Slice 17G**：端到端验证——单年 PDF 导入 → 8 章报告全部非空 → exit code 0。

- **Slice 17H**：hallucination 数字归一化 + 提示词改造。contains_non_year_numbers 从 return None 改为 logging.warning（软门禁）；LLM 提示词允许引用 data_table 中的数字。✅ 已完成。
- **Slice 17I**：程序审计引用排除 + LLM 审计约束 + 截断修复。C3 投资建议检测只扫描 `## 分析` 之后内容（跳过 data_table）；LLM 审计器 prompt 增加正例/反例；章节摘要截断从 300→800 字。✅ 已完成。
- **Slice 17J**：fallback 得分分流 + 模板统一化 + CLI 警告。审计循环耗尽时 ≥50 返回 LLM 内容 + degraded，<50 返回模板；模板与 LLM 路径统一章节结构；CLI 生成时输出降级警告。✅ 已完成。
- **Slice 17K**：多年数据强制（≥3年）。`import` 默认最近 3 年，`generate` 年份 < 3 时拒绝。✅ 已完成。
- **Slice 17L**：Ch5 预计算 + hallucination 软门禁 + 阶段判定逻辑。data_table 添加份额万份、费率变动、关键变化指标；allowed_numbers 机制预收集所有章节数字。✅ 已完成。
- **Slice 17M**：报告生成架构重构（基于 dayu prompting/ 模块启示）。解决 LLM 输出不稳定导致审计分数波动的核心问题。

  **裁决记录**（2026-07-18）：

  | 编号 | 裁决 | 选项 | 理由 |
  |------|------|------|------|
  | 1 | 输出格式 | 结构化 JSON（must_answer + analysis 并存） | 结构化保证字段完整，analysis 保留 LLM 分析能力 |
  | 2 | prompt 模板管理 | 外置 .md 模板文件 + 变量替换 + 条件块 + PromptComposer | 接近 dayu 的 prompting/ 模块设计 |
  | 3 | 审计阈值 | data_sufficient=True 时降至 75 分 | 适配当前 LLM 能力 |
  | 4 | prompt 隔离程度 | 每章独立 system prompt（per-chapter 模板） | 消除章节间约束干扰 |
  | 5 | hallucination 策略 | 移除 contains_non_year_numbers 前置检查，完全依赖审计 P2 | 减少误杀，统一由审计评分处理 |
  | 6 | JSON schema | must_answer 字段清单 + analysis 正文 + summary + confidence | 6B |
  | 7 | 变量注入粒度 | 拆分为 data_table + stage_judgment + must_answer_fields 等关键变量 | 模板可精细控制 |
  | 8 | 模板版本管理 | 文件头加 `<!-- version: x.x -->` 注释行 | 简化实现，仅用于日志追踪 |
  | 9 | 审计 prompt | 本 slice 不外置，后续独立 slice 处理 | 范围可控 |
  | 10 | 回滚策略 | 直接替换，不保留旧路径 | 代码干净，git revert 即回滚 |

  **实施内容**：

  - 17M-1：外置模板文件 + PromptComposer 渲染器
    - 每章一个 `.md` 模板文件，放在 `fund_agent/service/prompts/`
    - 模板使用 `{{ variable }}` 变量替换 + `<when_missing>` 条件块
    - PromptComposer：加载模板 → 变量替换 → 条件渲染 → 输出最终 prompt
    - 模板文件头含 `<!-- version: x.x -->` 注释

  - 17M-2：结构化 JSON 输出改造
    - LLM 输出 JSON：`{summary, analysis, must_answer: {}, confidence}`
    - must_answer 字段由模板中的章节合同定义
    - 解析 JSON 后拼接为 Markdown 报告

  - 17M-3：审计阈值 + hallucination 策略调整
    - SCORE_PASS 保持 80，SCORE_PASS_DEGRADED 从 70 降至 75
    - 移除 contains_non_year_numbers 前置检查
    - C3 纵深防御保留（关键词紧邻策略/原文时降级 MAJOR）

  - 17M-4：端到端验证
    - 3 年数据测试，目标 passed 率 ≥ 6/8
    - 验证输出稳定性（连续 2 次运行结果一致）

  **Phase 3.5 初始 Fix（已完成但效果有限，保留在代码中）**：
  - Fix 1：Ch3 data_table 预计算持仓合计 ✅
  - Fix 2：Ch5 data_table 统一口径 + 口径说明 ✅
  - Fix 3：C3 纵深防御（上下文窗口 50 字符） ✅
  - Fix 4+5+6：系统提示词章节分工 + 禁止自行计算 + 操作建议禁令 ✅

### Phase 4：分析能力扩展（低优先级）

- ~~**Slice 18A**：风格漂移检测~~ → 已在 16A 加权 Jaccard 实现，删除。
- ~~**Slice 18D**：费率影响估算~~ → 已在 16A 费率评分覆盖，合并删除。
- **Slice 18B**：换手率追踪（年报 §8 换手率 → 多年度趋势）。低优先级。
- **Slice 18C**：份额变动 + 盈利投资者占比（年报 §10 + 2026 新规字段）。低优先级。

### Phase 5：LLM 自主工具调用 + 流式输出

> 裁决时间：2026-07-24 | 状态：✅ 已完成
> 计划文件：`.sisyphus/plans/phase5-implementation.md`
> 流式输出已从原 Phase 7 前置并入 Phase 5。

- **Slice 19A**：StreamEvent 数据模型 + LlmToolLoopRunner production readiness（重试/截断/幻觉检测/tool schema 一致）。✅ 已完成。
- **Slice 19B**：DeepSeekLlmClient `stream=True` + SSE 解析。✅ 已完成。
- **Slice 19C**：MinimalHost `run_agent_stream()` 方法。✅ 已完成。
- **Slice 19D**：Service 层 `ask_question`（含 profile routing）。✅ 已完成。
- **Slice 19E**：CLI `ask` 子命令（流式默认）。✅ 已完成。
- **Slice 19F**：端到端 smoke + read 回归快照 + 全量回归。✅ 已完成。

新增文件：`fund_agent/agent/stream_events.py`、`tests/fund/agent/test_stream_events.py`、`tests/fund/agent/test_llm_production_readiness.py`、`tests/fund/service/test_ask_question.py`

### Phase 6：模板框架适配 + 基金类型感知

> 启动时间：2026-07-22 | 状态：✅ 已完成
> 详见 `docs/implementation-control.md` Phase 6 节

- **Slice 6A**：净值增长率列匹配修复。✅ 已完成。
- **Slice 6B**：基金经理/规模数据接入报告。✅ 已完成。
- **Slice 6C**：`preferred_lens` 接入 generate 流程。✅ 已完成。
- **Slice 6D**：评分框架 fund_type 感知（主动 6 指标 135→100 / 被动 3 指标 100 分制 / 债券 5 指标）。✅ 已完成。
- **Slice 6E**：端到端验证 + DS Review。✅ 已完成。



### Phase 7：多轮对话 + 会话记忆 + 上下文治理 + Prompt 路由

> 裁决时间：2026-07-25 | 完成时间：2026-07-26 | 状态：✅ 已完成
> 计划文件：`.sisyphus/plans/phase7-interactive.md`
> 补完计划：`.sisyphus/plans/phase7-completion.md`（Phase 7.1 承接）

**裁决汇总**：17 项裁决，详见计划文件。

**核心能力**：
- Session 数据模型 + filesystem JSON 持久化
- 三层记忆模型（Pinned State + Recent Turns + Episode Summary）
- Scene Config + Fragments + Context Slots（对齐 Dayu Prompt 路由）
- 上下文预算治理（Context Budget）
- CLI `interactive` 子命令（prompt_toolkit + rich）
- 会话恢复（--label）

**Slice 列表**（对齐计划文件 Wave 结构）：
- **7A**：Session 数据模型 + JSON 持久化
- **7X**：ToolResult 统一信封 + ToolExecutionContext（7F/7J/7L/7M 增强点：7F 注入 ToolExecutionContext 到 prompt contribution；7J wire-up 中 agent loop 所有工具返回走 envelope；7L Episode Summary 输出走 ToolResult envelope；7M Context Budget 裁决依赖 ToolExecutionContext.working_memory_overflow）
- **7B**：FundReadingService.resolve_by_fund_code()
- **7C**：统一 INVESTMENT_ADVICE_KEYWORDS
- **7D**：DeepSeekLlmClient token usage 追踪
- **7E**：PromptComposer 升级（fragment assembly + contribution injection）
- **7F**：Scene Config + Fragment 模板 + Prompt Contributions
- **7G**：Service 层 chat_turn use case（新建 `chat_service.py`）
- **7H**：Host 多轮会话托管
- **7I**：CLI interactive 子命令（prompt_toolkit + rich）
- **7J**：Integration wire-up（chat_turn → Host → CLI）
- **7K**：会话恢复 + --label 支持
- **7L**：Episode Summary（异步 LLM）
- **7M**：上下文预算治理（Context Budget）
- **7N**：扩展命令 + 多文档切换
- **7O**：Rich Markdown 渲染
- **7P**：端到端验证 + 全量回归

**新增文件**：
- `fund_agent/host/session_store.py` — Session JSON 持久化
- `fund_agent/service/session_models.py` — Session/Turn/PinnedState 数据模型
- `fund_agent/service/scene_config.py` — Scene Config 数据模型
- `fund_agent/service/prompt_contributions.py` — Prompt Contributions 构建与选择
- `fund_agent/service/prompt_composer.py` — 升级：fragment 装配 + contribution 注入
- `fund_agent/service/chat_service.py` — chat_turn use case
- `fund_agent/service/prompts/interactive/` — prompt fragment 模板
- `fund_agent/agent/context_budget.py` — 上下文预算治理
- `tests/fund/cli/test_cli_interactive.py` — interactive 测试
- `tests/fund/service/test_chat_service.py` — chat_turn 测试
- `tests/fund/service/test_scene_config.py` — Scene Config 测试
- `tests/fund/service/test_prompt_contributions.py` — Prompt Contributions 测试
### Phase 7.3：对话历史注入 LLM context（方案 B）

> 裁决时间：2026-07-28 | 完成时间：2026-07-29 | 状态：✅ 已完成
> 优化设计：`docs/phase7.3-option-b-optimization.md`
> 演进记录：`docs/agent-evolution-design.md` §8.2

**问题**：`interactive` 模式的对话历史未注入 LLM context。每次 `runner.run()` 完全独立，LLM 只看到 system + user 两条消息，无法引用历史轮次的工具结果或上下文。

**方案**：方案 B — Prompt 层编织。在 `chat_service` 层将历史轮次直接编织进 system prompt，不改变 `LlmClientProtocol` 签名。

**架构变更**：

| 模块 | 变更 | 说明 |
|------|------|------|
| `session_models.py` | 新增 `ToolCallSummary` dataclass | 存储工具调用摘要（tool_name、arguments_display、success、failure_code） |
| `session_models.py` | `Session.truncate_turns(keep_last)` | compaction 后截断旧 turns |
| `chat_service.py` | `_build_history_contribution()` | 从 session 构建 history contribution，带 token 上限（默认 2000） |
| `chat_service.py` | `_format_turn_for_history()` | 结构化格式：`[用户提问]`/`[助手回答]`/`[工具调用]`/`[引用文档]` |
| `chat_service.py` | `_estimate_token_count()` | 中英文混合 token 估算 |
| `chat_service.py` | `chat_turn()` 填充 `ToolCallSummary` | 从 `AgentRunResult.tool_trace` 提取 |
| `chat_service.py` | `_run_compaction()` 增加 truncate | compaction 后调用 `truncate_turns()` |
| `scene_config.py` | `context_slots` 新增 `"history"` | interactive scene 配置 |
| `deepseek_llm.py` | Bug A: `next_step_stream()` 补 `temperature=self._temperature` | stream 路径 temperature 透传 |
| `chat_service.py` | Bug B (contract 分支) + Bug C (compaction 路径) temperature 修复 | 统一从 scene config 读取 temperature |
| `llm_tool_loop.py` | 新增 `_normalize_document_id()` 前缀匹配 | document_id 变体容错 |
| `extraction.py` | Bug D: `_default_runner_factory` 新增 `temperature` 参数 | ask 场景 temperature 透传 |
| `main.py` | Bug E: regenerate helper `DeepSeekLlmClient` 补 temperature | regenerate 路径 temperature 透传 |

**Bug 修复：Temperature 透传（5 处）**：

| Bug | 位置 | 问题 |
|-----|------|------|
| A | `deepseek_llm.py` `next_step_stream()` | 调用 `_request_payload()` 遗漏 `temperature=self._temperature` |
| B | `chat_service.py` contract 分支 | temperature 硬编码 0.7，不读 scene config |
| C | `chat_service.py` compaction 路径 | `DeepSeekLlmClient()` 无 temperature 参数 |
| D | `extraction.py` `_default_runner_factory` | 创建 `DeepSeekLlmClient()` 未传 temperature |
| E | `main.py` regenerate helper | `DeepSeekLlmClient()` 默认 temperature=0 |

**Bug 修复：document_id 前缀匹配**：

`llm_tool_loop.py` 中 `_invoke_tool_call()` 对 `call.document_id != expected_document_id` 做严格相等校验。LLM 可能传递 variant ID（如自行拼接后缀），导致合法工具调用被误拒。新增 `_normalize_document_id()`：精确匹配直接通过；`fund_code-year-report_type` 前缀一致则接受并使用 `expected_document_id`；前缀不匹配则拒绝。

**关键设计决策**：
- `ToolCallSummary.result_summary` 从 `result_kind + failure_code` 推导（B1 方案），不存储 raw tool result
- History 格式：episode summaries（全局上下文）+ 最近 N 轮 raw turns（细节）
- 分隔标记引导 LLM 使用 JSON 格式回答
- `history_max_tokens` 可配置（默认 2000）

**总改动量**：~164 行（session_models ~30 + chat_service ~63 + scene_config ~1 + deepseek_llm ~1 + llm_tool_loop ~15 + extraction ~3 + main ~1 + 测试 ~50）

**记忆注入补接线（2026-08-09，P1 完成）**：Phase 7.3 的 memory slot 补接线——`_build_contributions` 增加 `contributions["memory"]`（`build_memory_contribution`，`prompt_contributions.py`），EpisodeSummary（最近 ≤3 条，总长 ≤500 token 超限丢最旧，单条超 100 token 截断加省略号）与 PinnedState `confirmed_facts`（`user_constraints["confirmed_facts"]`，str/list/tuple 兼容）编织进 system prompt，标注「历史摘要，非当前证据」；空数据不产生 slot；`context_slots` 中 `memory` 已在 `history` 之前（scene_config 零改动）。详见 §6.10。

**失败模式缓解**（9 项，详见优化设计文档）：
- FM1: Context window 溢出 → token 上限 + 截断
- FM2: 历史/当前混淆 → 结构化格式 + 分隔标记
- FM3: 跨轮 tool results 不可见 → B1 方案（result_kind/failure_code 推导）
- FM4: Scene config slot 缺失 → 新增 history slot
- FM5: Compaction 交互 → truncate_turns
- FM6: Temperature → 修复 5 处未透传 bug（A~E），不改变 temperature 取值逻辑
- FM7: 空 tool_trace → 跳过空 tool_calls 行
- FM8: Token 估算 → 中英文混合估算函数
- FM9: JSON 指令冲突 → 分隔标记加格式指引

**后续优化**：

- **generate_text temperature 按场景区分**：`generate_text()` 当前默认 `temperature=0`，建议按场景区分 — 审计评分保持 0（一致性）、章节分析写作用 0.3（语言多样性）、章节修复用 0.3（避免重复同一错误模式）。留待后续 phase 处理。

### 技术债

- **P1-3**：提取 compute_signal_judgment / compute_risk_checklist 共享评分 helper。
- **extraction.py 二次拆分**：当前 5931 行。signal_scoring.py（439 行）已完成一次拆分；残留 7 个评分/风险函数（约 450 行）待迁移。
  - 排期：Phase 7.1 后执行（理由：Phase 7.1 可能新增 import 依赖）。
  - 执行顺序：(1) 移 infer_fund_type + _next_tier_up/down + _compute_threshold_events 到 signal_scoring.py（消除循环依赖）(2) 移 compute_signal_judgment + 3 个 _compute_*_signal 到 signal_scoring.py (3) 新建 risk_assessment.py，移 STRESS_THRESHOLDS + compute_risk_checklist + compute_stress_test + _compute_ch6_stress_test (4) 更新 5 个文件的 import（extraction.py、audit_pipeline.py、__init__.py、chapter_generator.py、3 个测试文件）
  - 预期收益：extraction.py 减少约 450 行（5931→5480），评分逻辑完全独立可测试。
**Slice 16C**：Ch0 升级/降级阈值事件 + 一句话产品定义。从 Ch7 信号反推 Ch0 封面。✅ 已完成。含 tier-delta 阈值事件算法 + 确定性产品定义。
**Slice 17A**：报告 Markdown 持久化 + metadata sidecar。文件名 `{fund_code}-{year}-analysis.meta.json`，与 .md 同目录。字段：fund_code、fund_name、report_year、generation_time（ISO 8601）、audit_score（无审计 null）、signal、normalized_score。_export_markdown 增加 signal_judgment 参数。
**Slice 17A**：报告 Markdown 持久化 + metadata sidecar。文件名 `{fund_code}-{year}-analysis.meta.json`，与 .md 同目录。字段：fund_code、fund_name、report_year、generation_time（ISO 8601）、audit_score（无审计 null）、signal、normalized_score。_export_markdown 增加 signal_judgment 参数。✅ 已完成。
**Slice 17B**：citation 验证工具。输入必须为结构化 `Citation / Locator`；输出为 `ExcerptContent | ToolFailure`；验证口径仅限 locator 可回溯且可读取原文片段，不做内容语义真伪校验；实现层复用 `FundDocumentToolService.get_excerpt`，不新增 raw payload 暴露。

### 投资者偏好分析（2026-08-20 讨论稿，详见 §6.26）

- **Slice P1**：flomo import（HTML → SQLite，时间/内容/图片引用；gitignore）。存储格式 = SQLite、图片仅引用路径（2026-08-21 已裁决，见 §6.26.4）。
- **Slice P2**：问卷基线（自建 20 题 + AMAC 100 分制 C1-C5，确定性 CLI）。
- **Slice P3**：季度偏好快照（四问反思模板 + 免责声明，确定性，不接 LLM）。
- **Slice P4（第二切片）**：行为证据对照（memo 关键词 + 持仓变动 vs 声明一致性）。
- 后续切片：xlsx 持仓导入与估值、基金组合体检、市场温度计、温度驱动配置提示、可视化工作台（逐个设计）。

### 外部候选研究参考（非执行真源）

- `docs/dayu-agent-comparison-report.md`、`docs/agent-evolution-design.md` 与 `docs/dayu-agent-codiwiki-and-development-stage-analysis-20260614.md` 仅作为候选研究输入材料，不作为设计真源或已批准 roadmap。
- Phase 5（`ask` + streaming）已从候选状态裁决为正式实施计划，详见 implementation-control.md Phase 5 节。
- 若后续需要推进 `interactive`、联网搜索、会话持久化等能力，必须回到本文件与 `docs/implementation-control.md` 单独裁决。

- **Slice 17N** ✅：Ch5/Ch6 报告质量提升（模板优化 + 数字引用规范 + must_answer 补齐）。

  **裁决记录**（2026-07-18）：

  | 编号 | 裁决 | 选项 | 理由 |
  |------|------|------|------|
  | 1 | 数字引用规范 | 方案 A：模板约束 LLM 引用原始数字，不缩写 | 消除 P2 误杀根因，零误匹配风险 |
  | 2 | 目标阈值 | Ch1-6 审计得分 ≥75（passed，非 degradation） | 适配当前 LLM 能力，先消除降级 |
  | 3 | 修复范围 | 5 项全做 | 问题相互关联，部分修复效果有限 |

  **问题清单**：

  | # | 问题 | 根因 | 修复 |
  |---|------|------|------|
  | 1 | P2 hallucination 误杀 | LLM 缩写数字（10095099672.67→100.95亿），allowed_numbers 不匹配 | 模板增加"引用原始数字，不得缩写"规则 |
  | 2 | Ch5 数据验证不足 | LLM 未逐条核对数据表就输出结论 | 模板增加"先逐条核对数据，再输出结论"指令 |
  | 3 | Ch6 must_answer 缺"信息缺口" | ChapterContract 未定义该字段 | 补充 must_answer 条目 |
  | 4 | Ch6 投资建议违规 | 模板未明确禁止/允许边界 | 模板增加禁止/允许清单 |
  | 5 | Ch5 口径混淆 | LLM 混淆"权益投资规模"和"份额×净值同比" | 模板增加口径强调段 |

  **实施内容**：

  - 17N-1：所有章节模板增加数字引用规范（引用数据表原始数字，不缩写、不四舍五入）
  - 17N-2：Ch5 模板重写（数据验证规则 + 口径强调 + 阶段判定逐步核对）
  - 17N-3：Ch6 ChapterContract 补充 must_answer "哪个信息缺口最可能改变最终判断"
  - 17N-4：Ch6 模板增加投资建议边界清单
  - 17N-5：端到端验证（3年数据，Ch1-6 ≥75 passed 率 ≥4/6）


- **Slice 18A**（Phase 3.6）：合同架构重构 — 将 ChapterContract 从 Python 硬编码迁移到模板 HTML 注释。

  **裁决记录**（2026-07-19）：

  | 编号 | 裁决 | 选项 | 理由 |
  |------|------|------|------|
  | 1 | 迁移范围 | 全部 8 章 | 一次性完成，避免新旧两套并存 |
  | 2 | ITEM_RULE | 纳入，仅支持 `<when_missing>` 条件块 | 复用已有机制，不引入 facet 过滤 |
  | 3 | preferred_lens | 暂不引入 | 基金是单一领域，narrative_mode 已覆盖。后续研究基金类型划分后再决定 |
  | 4 | precomputed_metrics | 放在 contract 中 | 驱动预计算的核心输入，和 must_answer 并列 |
  | 5 | 审计校验 | must_answer 程序化校验 | 消除 S2 违规 |
  | 6 | Phase 3.5 关闭 | 现在正式关闭 | 验收标准已达成（4/6 ≥75） |

  **设计目标**：
  - 合同定义从 Python 代码迁移到模板 HTML 注释（`<!-- CHAPTER_CONTRACT ... END_CHAPTER_CONTRACT -->`）
  - PromptComposer 解析 HTML 注释，提取结构化合同
  - 审计管道根据合同做程序化校验（must_answer 完整性、数字引用规范）
  - 预计算指标由 contract 中的 `precomputed_metrics` 驱动

  **新增 contract 字段**：

  ```python
  metrics: tuple[Metric, ...]                         # 指标定义（合并预计算 + 口径）
  cross_chapter_refs: tuple[CrossChapterRef, ...]      # 跨章节依赖（引用 signal_scoring.py 程序化结果）
  data_verification: tuple[DataVerificationRule, ...]  # 数据验证规则（复数）
  item_rules: tuple[ItemRule, ...]                     # 条件写作规则（结构化元数据，供审计检查 must_answer 缺失是否因数据缺失导致合理降级）
  ```

  **模板格式**（以 Ch5 为例）：

  ```markdown
  <!--
  CHAPTER_CONTRACT
  narrative_mode: 变化→阶段→判断
  must_answer:
    - 当前阶段是什么（5选1）
    - 过去一年最关键的1-3个变化
    - 这些变化是否影响原始投资假设
    - 接下来最该跟踪的1-3个变量
  must_not_cover:
    - 不做市场整体走势预测
    - 不给最终持有/替换结论
  required_output_items:
    - 基金当前所处阶段（含判定依据）
    - 过去一年最关键的变化（含触发阈值）
  metrics:
    - name: 份额×净值同比
      formula: (当年份额×当年净值 - 上年份额×上年净值) / (上年份额×上年净值)
      unit: "%"
      threshold: ">30%触发膨胀期, <-30%触发萎缩期"
      source: scale_info + allocation
      note: 不可用权益投资规模替代
    - name: 前十大持仓换手率
      formula: 两年间前十大持仓中替换的股票数量 / 10
      unit: "%"
      threshold: ">40%触发关键变化"
      source: holdings（多年）
      note: 需多年 holdings 比对
    - name: 权益投资规模变动
      formula: 年报资产配置权益投资金额同比
      unit: "%"
      threshold: 无（仅参考）
      source: allocation
      note: 仅用于阶段判定参考，不用于阈值判定
  cross_chapter_refs:
    - target_chapter: 7
      ref_type: signal_score
      note: 对比Ch7信号评分方向是否逆转
  data_verification:
    number_citation_rule: 引用原始数字，不缩写
    comma_handling: 提取数字前去除逗号
  END_CHAPTER_CONTRACT
  -->

  ### 阶段判定
  ...
  ```

  **Phase 5 前置条件**：
  - ✅ 8 章报告全部非空（17G 已验证）
  - ✅ 审计管道数据适配（17F 权重调整 + 阈值适配）
  - ✅ 端到端验证通过（Phase 3.5 最终验收）
  - 🔲 Phase 3.6 验收通过（Ch1-6 ≥75 passed 率 ≥5/6）
  - Phase 5 范围定义（待裁决）

  **后续研究**：基金类型划分 + preferred_lens 设计（下一阶段）。

### 6.23 process-backed 工具执行（可抢占超时）（2026-08-13 裁决，规划完成）

- 现状事实：`MinimalHost.run()`（`fund_agent/host/minimal_host.py:141`）在 daemon 线程跑 Agent loop，`thread.join(timeout)` 超时后返回 `timed_out=True` 但**线程不杀**（12A 缺口）；`DoclingConverter.convert_pdf()` 同步阻塞执行 `converter.convert(stream)`，超时仅靠 Docling 内部 `document_timeout`（`_build_docling_converter` → `PdfPipelineOptions(document_timeout=...)`），模型下载 / OCR / C++ 路径卡死时内部超时不可靠、且无进程可杀。
- 决策：
  - 新增进程隔离原语 `fund_agent/fund/document_tools/interruptible_process.py`：子进程启动 / 结果回收（Pipe envelope）/ terminate→grace→kill / bounded close；`multiprocessing.get_context("spawn")` + 模块级子进程入口，目标必须是 spawn 可按引用序列化的顶层可调用；`SubprocessTimeoutError` / `SubprocessExecutionError` 两类异常；`InterruptibleProcess`（`run()` 与 `start()` 互斥，重复调用抛 `RuntimeError`）+ `run_in_subprocess` 薄封装。概念对齐 dayu `runtime/interruptible_process.py`，自实现不复制（Apache-2.0 license gate）。
  - 接线点：`DoclingConverter.convert_pdf` 的阻塞转换移入可抢占子进程；`timeout_seconds` 语义升级为「既是 Docling 内部 document_timeout，也是硬子进程 deadline」；公共签名与返回不变。子进程入口 `_run_conversion_in_child(pdf_bytes, do_ocr, timeout_seconds, output_json_path)` 复用既有 `_build_docling_converter` / `_build_document_stream` / `_save_docling_json` / `_is_unavailable_exception`，失败分类从父进程移入子进程（`unavailable` / `docling_convert_failed` 集合不变）。
  - 父进程映射与清理：`SubprocessTimeoutError` → 清理 `json_path` → `DocumentToolError(UNAVAILABLE, "Docling 转换超时")`；`SubprocessExecutionError` → 清理 → `DocumentToolError(UNAVAILABLE, "Docling 转换子进程异常")`；`docling_convert_failed` / `unavailable` envelope 原样映射。统一保证：convert_pdf 失败 ⇒ `json_path` 不残留。
  - Host 12A 的 thread timeout 语义与 `timed_out` 契约不变；不做 Host 级整 loop 进程隔离（Agent 持 LLM client / tool service / 会话状态，spawn 序列化脆弱；研究 §5 决策 5 定位为等真实异步需求，backlog 候选）。
- 硬约束：不引入 `fund_agent/runtime/` 新分层（原语放 fund/document_tools，架构坐标系不变）；不新增依赖（stdlib `multiprocessing`）；不改 `FailureCode / DocumentToolError / DoclingConversionResult / ReportIdentity / MinimalHost` 公共契约；不新增 CLI 子命令与参数；子进程只运行转换，不碰 Agent / LLM / session；测试 fake 只测边界与错误，生产转换路径真实执行（真实样本 PDF）。
- 依据：`docs/research/dayu-agent-r-research-20260810.md` §2.1.4 / §5 决策 5。
- 实现与测试：见 `.sisyphus/plans/process-backed-tool-execution-slice-20260813.md`；CIC-lite：MiMo plan review `NEEDS_FIX`（2026-08-13，1 项最小修复——test 2 改为纯手动 API 避免 start 后 run 孤儿子进程，`run()` 与 `start()` 互斥——已按 review 原文修正），DS 实施待执行。

### 6.24 阶段判定「建仓期」真源修正（2026-08-13 裁决，规划完成）

- 现状事实：`generate_data_table` 的建仓期判定（`fund_agent/service/chapter_generator.py:596-606`）只读 `fund_manager.tenure_start` 年份与 `report_year`，从不读基金成立日期。005680（财通资管价值成长混合，2025 年报）合同 2019-03-25 生效（2021 年报文本「本基金合同于2019年3月25日生效」；2022-2025 年报 §2 基金简介表 `基金合同生效日 | 2019 年 03 月 25 日`），经理李响 2025-07-15 任职，`2025-2025=0<2` → 误判「🟡 建仓期」（修复前模板模式实测）。另外 `chapter_generator.py:562-564` 在 `tenure_start` 为空时直接判「转型期」——经理维度占用 5 阶段枚举。
- 语义裁定：建仓期属于**基金产品生命周期**（合同生效后建仓），不属于基金经理任期；经理变更风险已有独立信号 `signal_scoring.py:381-391` `score_manager_change`（指标 5，0/20），保留在 Ch7 信号评分，不占用阶段枚举。
- 决策：
  - 新增「基金合同生效日」确定性抽取 `FundReadingService._extract_contract_effective_date_with_citation`（`extraction.py`，Service 层，带 Citation）：query「基金简介」锚定 §2 基金简介节 → 表行「基金合同生效日 | YYYY 年 M 月 D 日」正则归一化 `YYYY-MM-DD`；回退「基金合同生效日」query 逐命中节表行扫描；再回退 §2 节文本正则（`基金合同生效日[为：:]?\s*[（(]?日期` / `基金合同于日期…生效`，日期必须紧跟短语，避免 §4.1.2 经理首任任职口径误取——163415 实测陷阱「本期 2025年4月8日（基金合同生效日）至2025年12月31日」）；全部失败返回 `("", None)`（fail-closed）。已实测 005680/004393/163415 均命中 §2 table-0002。
  - 建仓期判定真源切换：`report_year - 合同生效年份 < 2` 才判建仓期（被动基金仍跳过，`not is_passive` 守卫不变）；判定表新增 `| 基金合同生效日 | ... |` 行；建仓期不覆盖转型期（`stage != "转型期"` 守卫，对齐优先级「转型期 > 建仓期」）。
  - 删除经理维度占用：`tenure_start` 为空判「转型期」分支删除；建仓期不再引用 `tenure_start`。
  - fail-closed：成立日期缺失时不做建仓期判定，判定依据明确说明「建仓期判定跳过（不采用基金经理任职年限代理）」；不引入经理任期代理。
  - 透传：`generate_data_table(..., contract_effective_date: str = "")` 显式公共参数，经 `LlmChapterGenerator.generate_chapter`（`chapter_generator.py:960`）、`FundReadingService._generate_chapters` / `_generate_template_chapter`、`ReportGenerationCoordinator.generate_report` / `_run_chapter_worker` / `_generate_and_audit_chapter` / `_generate_and_audit_chapter_inner`（`audit_pipeline.py:1884/2043/2111/2166`）全链路透传；`ChapterEvidence` 新增 `contract_citation`，Ch5「证据与出处」渲染合同生效日来源（可溯源）。
  - Prompt 口径同步：`fund_agent/service/prompts/system_base.md` Ch5 正例「基金经理任职超过2年」改为「基金合同 XXXX 年生效，成立已满 2 年」；Ch5「5选1 优先级」表述不变。
  - `_generate_chapters_with_llm`（`extraction.py:3604`）为 dead code（无调用点），不改；若复活需同步透传。
- 硬约束：不改 5 阶段枚举与优先级；不改 `score_manager_change` 信号口径；不改 040046 资产配置结构转型检测；不新增 CLI 子命令/参数/依赖；不更新 AGENTS.md（无执行规则变更）。
- 依据：005680 2025 年报 Docling JSON 实测 + `docs/design.md` Ch5 must_answer「5选1 优先级」。
- 实现与测试：见 `.sisyphus/plans/stage-determination-contract-date-slice-20260813.md`；CIC-lite：MiMo plan review `NEEDS_FIX`（2026-08-13，2 项最小修复——决策 6 引用不存在的 `_generate_llm_chapters` 已改正、`_generate_chapters_with_llm` dead code 已列入非目标——已按 review 原文修正）；DS 实施完成（2026-08-13，9 文件，测试 6/1/15/26/196 全通过，005680 实跑稳定期），MiMo diff review `ACCEPTED`。

### 6.25 季报/半年报快照（snapshot）设计（2026-08-14 裁决，19 项定案）

- 定位：季报/半年报以**单期快照**（latest disclosure snapshot）身份进入分析管线——单份 PDF → 当期分析，**非多年**；与 5 年年报系列（10F/10G/multi-year）互补不替代。年报主链保持 annual-only；快照不进 multi-year 聚合。
- 依据：`docs/research/quarterly-semiannual-data-source-research-20260814.md`（005680 实证：EID 下载码、§3.2.1 行集、数据能力对比、catalog 过滤风险）。
- 裁决项（全部定案，直接写入本设计）：
  1. **document_id 期次编码**：快照 document_id 为 `fund_code-year-Q[1-4]-quarterly_report-fingerprint_prefix` 与 `fund_code-year-semiannual_report-fingerprint_prefix`（半年报不带期次段）；即 quarterly 在 year 与 report_type 之间插入 `-Q[1-4]` 段。`_PARSED_DOCUMENT_ID_PATTERN`（`local_pdf_source.py:31`）加可选 `-Q[1-4]` 段，`_assert_supported_identity` 同步放行 quarterly/semiannual；annual 格式不变。fingerprint 天然区分 Q1/Q2。
  2. **单期快照**：快照分析只消费当期单一 PDF；不要求同基金多年份快照数据。
  3. **LLM + 审计**：快照复用三层审计（程序+LLM+复核）的既有机制（`audit_pipeline.py` ProgrammaticAuditor/LlmAuditor/ChapterRepairer），但按**新 manifest 章节**驱动；必须解耦 `ReportGenerationCoordinator`（`audit_pipeline.py:1815`）对 8 章 specs（`CHAPTER_CONTRACTS` ch0-7 + `generate_data_table` 8 章分支）与 `prompts/ch0.md..ch7.md` 的绑定，改为按 template_id 取章节契约与 prompt。
  4. **评分**：采用简化评分（裁决项 b）——当期超额收益（净值增长率-基准收益率 ①-③ 列）+ 仓位 + 集中度三维确定性规则，**不依赖多年数据**；独立于 `signal_scoring.py` 年报 6 指标评分。
  5. **章节**：季报 5 章（概览 / 当期业绩与超额 / 持仓与资产配置 / 管理人动作 / 风险与跟踪）；半年报 6 章（多「财务质量+持有人」）。独立于年报 ch0-ch7。
  6. **模板**：独立文件 `docs/fund-quarterly-snapshot-template.md`、`docs/fund-semiannual-snapshot-template.md`，各自内嵌 manifest（含章节契约）；prompt 模板按 template_id 建命名空间（新增 `prompts/quarterly_snapshot/`、`prompts/semiannual_snapshot/`），现有 `ch0.md..ch7.md` 为年报专用，**不动**。
  7. **字段边界**：只覆盖真实存在字段——净值增长率各阶段行 + ①-③ 超额列、主要财务指标（半年报）、期末规模/份额、仓位（权益/债券占比）、前十大持仓（季报）/全部持仓+重大变动（半年报）、行业配置、基金经理、份额变动、固有资金（固有资金投资本基金）；半年报增加财务三表关键科目（标注「未经审计」）。**季报缺失项（全部持仓/财务三表/托管人报告）必须 fail-closed 声明，不从年报补**。
  8. **份额**：快照默认 A 类优先；沿用 share_class 显式限定；无法明确记 null，**不从文件名猜测**（与年报 share_class 规则一致）。
  9. **抽取**：新建受控 profile `quarterly_performance` / `semiannual_performance`（`DISCLOSURE_LOCATOR_CONTRACT_REGISTRY`），独立 title-family + table anchor（3.2.1 表头签名「阶段/份额净值增长率/业绩比较基准收益率」复用，行标签精确匹配、禁止假设固定窗口集合，C 类缺行走 F2 可解释 not_found 语义）；**不污染 10G annual 契约**；registry 的 `extraction_allowed=False` 口径对快照独立评估。
  10. **命令**：`snapshot-quarterly` / `snapshot-semiannual` 两个子命令；参数对齐 generate（`--fund-code` / `--fund-name` / `--work-dir` / `--llm` / `--format`）；期次参数 `--year 2026 --quarter 2`（季报）/ `--year 2025 --period H1`（半年报）。
  11. **输入**：从 catalog 读取已导入 document（generate 风格：fund_code + year 匹配、last-wins 去重），保持统一 Fund documents / tool service 边界；快照命令不直接消费 raw PDF 路径。
  12. **import 扩展**：加 `--report-type` + `--quarter` 显式参数（contract-first）；文件名推断仅便利；`_extract_year_from_filename`（`cli/main.py:543`）避免吞 Q1/Q2（年度正则只取 4 位年份，不受影响，但文件名匹配需按 report_type 过滤目录）。
  13. **catalog schema**：`ReportSummary` / `persistent_repository` 增加 `quarter` / `period` 字段，**向后兼容**（旧记录 → None；`list_reports` 缺省字段不报错）。
  14. **download 扩展（本期含）**：EID 实证——半年报 reportType=FB020 / reportCode=FB020010（reportDesp=中期报告）；季报 reportType=FB030 / reportCode=FB030010/020/030/040（Q1-Q4）；reportYear 与 `--year` 对齐；复用 `_candidate_matches` / `_strict_match`。
  15. **interactive**：本期不扩开放问答；快照命令独立闭环，不接入 interactive 检索路由。（2026-08-19 已收口：快照文档接入 interactive 开放问答，见第 24 项。）
  16. **输出**：json / markdown / pdf 三格式；markdown 落盘 `reports/{fund_code}-{year}Q{quarter}-quarterly-snapshot.md` / `reports/{fund_code}-{year}H1-semiannual-snapshot.md`；pdf 走既有渲染 fallback 链。
  17. **回归约束**：read / multi-year / generate 的 annual 行为保持回归不变；`_multi_year_documents_by_year`（annual_report_documents SCHEMA_DRIFT 边界）与 `_validate_multi_year_report_identity`（annual-only）不动；快照文档导入同一 work_dir 时 multi-year 过滤按 `report_type=annual_report` 维度防污染（catalog 查询修复）。
  18. **流程**：CIC-lite 8 slices（设计 → control 面板 → A 域模型 → B download → C 模板/prompts/coordinator 解耦 → D 受控 profile+抽取 → E CLI+输出 → F 回归+文档同步）；每 slice implement → tests → diff review；验收 = 最小验证集 + 005680 本地真实 PDF（`基金季报/*Q1*`、`基金季报/*Q2*`、`基金半年报/005680_*_2025_semiannual_report.pdf`）CLI 端到端（json/markdown/pdf 三格式）。
  19. **章节迭代与摘要注入按模板驱动**：LLM 分析摘要注入（Ch0/Ch7 读前序摘要）与审计上下文均按 `template.front_chapter_ids` 驱动（`audit_pipeline.py` `_generate_chapter_content` / `_run_chapter_worker`），禁止硬编码 `range(1,7)`；三模板 front ids：annual (1..6)、quarterly (1..4)、semiannual (1..5)。
  20. **审计通过判据 + 报告级装配审计（2026-08-15 裁决）**：审计通过判据 = 加权分数达门槛（数据充足 80 / 数据不足或 LLM_ERROR 75）**且**无 CRITICAL 违规（`audit_pipeline.py` `_passes_audit`）；critical 不因高分放行，一律走 REGENERATE（不 PATCH；LLM 审计 critical 与程序化 critical 同等阻断，误报代价 ≤3 次 regenerate 后模板降级，有界；数据不足只降分数门槛、不豁免 critical，「数据完整性声明」场景 data_table 非空不误触）。报告级装配审计（`verify_report_assembly`）：章节集合 == 模板 `chapter_ids`（缺章/多章 fail）、展示顺序 == sorted（乱序 fail）、每章标题 == `chapter_titles[cid]`（与 manifest 不一致 fail），违反 fail-closed 返回 `schema_drift`（不新增 failure code；模板模式同样生效）；内容为空仅 warning 不 fail。三处装配点全接：`generate_snapshot_report`（快照）、`generate_report` LLM 路径（年报）、`_generate_chapters` 模板路径（年报）。
  21. **`to_context_dict()` 序列化契约（2026-08-15 裁决，候选 B）**：`SnapshotReportData.to_context_dict()` 序列化范围 = dataclass 字段全集（22 key，含身份字段 `fund_code`/`fund_name`/`report_year`/`template_id`/`quarter`/`period` 与 `citations`）；身份字段原样序列化，`citations` 以 `[dict(c) for c in self.citations]` 序列化（与既有 rows 风格一致）；既有 15 个 key 纯增量不变、向后兼容。**新增字段必须同步序列化**，回归防线为 `dataclasses.fields` 全集断言（`tests/fund/service/test_snapshot_extraction.py`，新增字段不同步序列化即红）。消费者传参契约不变：身份字段仍由 service 层显式 kwargs 传入 generator（`extraction.py` `generate_snapshot_report`），不从 dict 读取；`citations` 不接入 generator 渲染 / prompt 注入。
  22. **search excerpt 窗口截断对齐数字串边界（2026-08-15 裁决，候选 C）**：`docling_store.py` `_excerpt` / `_search_excerpt` 的 240 字符窗口（`DEFAULT_SEARCH_EXCERPT_CHARS`）截断点落在数字串内部（数字串字符集 `0123456789,，.`；仅当截断点前一字符与当前字符均属该集合才判定，避免吞孤立标点）时，end 只向后扩展至数字串结束、start 只向前回退至数字串起点（命中区间永不缩短）；两函数 no-hit fallback 改为 `text[:_align_end_no_number_cut(text, max_chars)]`（仅 excerpt fallback 对齐）。`_bounded`（list_sections preview / read_section 截断行为）与跨页/跨节数字拼接不纳入。快照 `_search_texts` 被动消费方不改，自动受益。
  23. **download 批量下载 + --import 流水线（2026-08-17 裁决，plan 见 `.sisyphus/plans/download-batch-slice-20260817.md`）**：`download` 新增批量参数——`--year-range`（复用 `_parse_year_range`，`2021-2024` 或 `2021,2023`，parser 上 `default=None`）与 `--year` 组成互斥组、两者皆缺省 → `schema_drift`（退出码 2）；`--quarters`（仅 `quarterly_report`，`1-4` 或 `1,2,3` 逗号列表，与现有单值 `--quarter` 互斥，保留复数命名避免破坏单值契约）在 annual/semiannual 下给出 → `schema_drift`。批量触发 = `--year-range` 存在或 `--quarters` 存在；批量 quarterly 缺省期次 = 1,2,3,4（cached 幂等保证安全）。批量模式 stdout 输出 JSON 数组（每条目 `fund_code`/`year`/`quarter`/`report_type`/`status`/`file_path`/`source_url`，失败条目为 `failure{code,message}`），stderr 逐条进度与失败汇总；退出码与 `_run_import_command` 一致（全部成功含全部 cached → 0、全部条目失败 → 2、部分失败 → 0）。单模式（无 `--year-range`/`--quarters`）保持既有单对象 JSON 输出，字段不变、不新增 `report_type`/`quarter`。可选 `--import` 流水线（`--work-dir` 默认 `.fund_checklist`）：仅对 `status ∈ {downloaded, cached}` 且 `file_path is not None` 的条目调 `service.import_local_report`（`ImportLocalReportRequest`），复用 import 分类语义（`integrity_error` → skipped、其它分类 → failed、未捕获异常 → failed），导入失败不中断后续条目；汇总输出 imported/skipped/failed 到 stderr。不改 `download_report` 签名与单次语义、不改 EID spec/reportCode 映射；不新增限速参数（批量保持 `sleep_seconds=0.2`）。
  24. **快照 interactive 开放（2026-08-19 裁决，plan 见 `.sisyphus/plans/snapshot-interactive-20260819.md`）**：interactive 新增 `--report-type`（默认 `annual_report`）/`--quarter`（choices 1-4，缺省 = 所选年份内最新季度）/`--period`（仅 H1）参数，已导入快照文档（`quarterly_report`/`semiannual_report`）接入既有 LLM 工具调用检索链路（search/read_section/read_table 等，runner/scene 零改动）。annual 行为零变化（唯一例外：`resolve_by_fund_code` 加 `report_type="annual_report"` 默认过滤，修复 mixed catalog 下 annual 可能拿到快照 doc 的污染，与裁决 17 口径一致）。快照模式 `aggregate_handler=None`（aggregate 调用 fail-closed unavailable，不改 `INTERACTIVE_SCENE_CONFIG.allowed_tools`）；`PinnedState` 新增 `report_type`/`quarter`/`period` 三字段（session 序列化向后兼容，`_SESSION_SCHEMA_VERSION` 不 bump）；runtime contribution 快照模式追加「报告类型/报告期/单期快照硬规则行」（annual 不追加任何行）；`/document` 期次切换保留三字段，`quarter`/`period` 从目标 document 的 catalog record 重新解析（非透传旧值）。不接入 `ask`；不做 H2；不改快照报告生成/抽取 profile/多年聚合。

- 章节与字段边界（季报 5 章 / 半年报 6 章）：
  - 季报：① 概览（基金简介、期末规模/份额、当期净值表现、综合结论）；② 当期业绩与超额（3.2.1 各阶段行 + ①-③、窗口口径标注）；③ 持仓与资产配置（仓位、行业配置、前十大持仓、份额变动）；④ 管理人动作（运作分析 §4.4、基金经理、固有资金）；⑤ 风险与跟踪（单一投资者 ≥20%、持有人数/净值预警、fail-closed 缺失声明）。
  - 半年报：① 概览；② 当期业绩与超额；③ 持仓与资产配置（全部持仓 + 重大变动、行业配置、仓位）；④ 财务质量（主要财务指标 + 财务三表关键科目，标注「未经审计」）；⑤ 管理人动作（运作分析、基金经理、份额变动、固有资金）；⑥ 风险与持有人（持有人结构、单一投资者 ≥20%、预警说明、fail-closed 缺失声明）。

- 实现与测试：按 `docs/implementation-control.md`「季报/半年报快照」节逐 slice 记录；plan artifacts 见 `.sisyphus/plans/snapshot-*.md`。
