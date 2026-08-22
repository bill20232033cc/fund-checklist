# Repository Agent Rules

更新时间：2026-08-13

## 语言与沟通

- 默认用中文回答。
- 去情绪化：不写安抚、寒暄、道德说教；结论以代码和证据为准。
- 回答前先审查问题前提、口径和逻辑；前提错误或信息不足时直接指出，并列出最少必要补充项。
- 不迎合用户立场。用户给出的方向可以作为目标，但实现判断必须回到代码事实、架构边界和最短可行路径。

## 规则真源

- 本文件是本仓库所有 Agent 执行规则的唯一权威入口。
- `docs/design.md` 是设计真源；详细 UI / Service / Host / Agent 分层、域模型和工具契约放在该文档。
- `docs/implementation-control.md` 是当前执行面板；只记录当前状态、下一步、stop conditions 和验证命令。
- `docs/fund-analysis-template-draft.md` 仅在处理后续报告、字段抽取或投资判断路径时读取。

## 当前产品方向

当前产品方向是 **基金分析助手**（已脱离 MVP 阅读工具层阶段）。

项目定位：面向基金投资者的多年度分析工具，覆盖年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道的完整链路。

目标主链路：

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

已实现的 CLI 入口：`read` / `multi-year` / `import` / `holdings` / `download` / `allocation` / `fees` / `audit` / `deep-audit` / `generate` / `ask` / `interactive` / `repair` / `regenerate` / `fix` / `snapshot-quarterly` / `snapshot-semiannual`（季报/半年报单期快照，2026-08-14，设计见 design.md §6.25）。

`generate --format pdf` 的渲染走引擎 fallback 链：`xelatex` → Chrome headless（pandoc md→HTML + 内嵌打印 CSS → `--print-to-pdf`，A4 794×1123）→ 回退 Markdown + warning；pandoc/xelatex/Chrome 均 `shutil.which` 前置探测，打印 CSS 为原创资产（详见 design.md §6.9），不依赖 LaTeX 发行版。

验收约束（适用于所有阶段）：
- 不接受仅 Service / ToolService 层测试；任何阶段的验收必须包含 Host / Agent loop 或 CLI 端到端 smoke。

当前已知能力差距（基线：dayu-agent 对标研究 2026-07-11；2026-08-11 按 dayu-agent-r 研究收口更新，完整研究见 `docs/research/dayu-agent-r-research-20260810.md`）：
- **多轮对话**：✅ 已完成（`interactive` 子命令，会话持久化 + 上下文记忆，Phase 7）
- **上下文治理**：✅ 已完成（Context Budget 基础 + Episode Summary + 记忆注入 P1；ContextBudget 已接入 runner，Phase 7.1a 2026-07-27）
- **联网搜索 / 网页抓取**：未采用（产品边界与合规决策，研究 §5 决策项 6）
- **微信入口 / GUI / Web UI**：不在基金分析助手范围（研究 §3）
- **BM25F 检索排序增强**（研究 §5 建议 1）：✅ 已完成（2026-08-13，确定性排序升级、不改变召回；设计见 `docs/design.md` §6.20）
- **日志 VERBOSE 分级 + 有界脱敏诊断载荷**（研究 §5 建议 2）：✅ 已完成（2026-08-13，设计见 `docs/design.md` §6.21）
- **Tool Trace operator 对齐**（研究 §5 建议 3）：✅ 已完成（2026-08-13，只读分析器，设计见 `docs/design.md` §6.22）
- **process-backed 工具执行（可抢占超时）**（研究 §2.1.4，落地 `DoclingConverter.convert_pdf` 阻塞转换子进程化 + 硬 deadline 杀子进程）：已规划（2026-08-13，MiMo plan review，实施状态见 `docs/implementation-control.md`；设计见 `docs/design.md` §6.23）
- **后续 backlog 候选**：Host 级整 loop 进程隔离（Agent loop 整体子进程化，等真实异步需求，研究 §5 决策 5）、wait-resume 长事务工具治理（研究 §2.1.4 项 3，等批量下载/异步导入真实需求）

Phase 5 已完成（2026-07-24）：
- **LLM 自主工具调用**：`ask` 子命令走 LLM 自主决策工具调用路径（Slice 19A-19F）
- **Streaming**：StreamEvent 模型 + DeepSeek stream=True + CLI 流式输出（Slice 19A-19C, 19E）

Phase 6 已完成（2026-07-22）：
- **模板框架适配**：preferred_lens 接入 generate 流程
- **基金类型感知**：评分框架 fund_type 感知（主动 6 指标 135→100 / 被动 3 指标 100 分制 / 债券 5 指标）

Phase 7 已完成（2026-07-26）：
- **多轮对话**：`interactive` 子命令，支持会话持久化、上下文记忆、会话恢复（--label）
- **上下文治理**：Context Budget 基础 + Episode Summary 异步压缩
- **Prompt 路由**：Scene Config + Fragments + Context Slots，对齐 Dayu
- **7X**：ToolResult 统一信封 + ToolExecutionContext
- **LLM 工具调用链路**：routing context 直返 + prompt search→read→cite 策略 + tool call 去重 + extra 字段解析
- 真实 LLM 验证通过（deepseek-v4-flash，ask + interactive）

LLM provider 已支持 DeepSeek 与 Mimo（OpenAI-compatible adapter），经 `FUND_CHECKLIST_LLM_PROVIDER`（`deepseek` 默认 / `mimo`）自由切换，各自独立 env（`DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL` 与 `MIMO_API_KEY`/`MIMO_BASE_URL`/`MIMO_MODEL`）；暂不需要接入 Gemini/OpenAI/Anthropic 等其他 provider。

- 对基金文档的存取必须通过统一 Fund documents / tool service 边界。
Phase 7.1 已裁决（2026-07-26）。集成补完 + Dayu 场景借鉴：
- **集成补完**：ToolResult 信封接入 runner、ContextBudget 接入 runner、force_answer 降级、tool_calls_remaining 信号注入 ✅ Phase 7.1a 已完成（2026-07-27）
- **Dayu 场景借鉴**（除 wechat）：regenerate（整章重建）、repair（局部修复）、fix（占位符补强）、decision（研究决策综合）、conversation_compaction（会话摘要压缩） ✅ Phase 7.2 已完成（2026-07-27）
- 详见 `docs/implementation-control.md` Phase 7.1 节

Phase 7.2 已裁决（2026-07-27），✅ 已完成（2026-07-27）。交互体验增强 + 修复能力激活 + 场景扩展：
- 推翻 Phase 7 routing context 预取，统一走 LLM 工具调用 ✅
- 激活已定义但未接线的 SceneConfig（regenerate/repair） ✅
- 新建 fix 场景（结构化占位符补强） ✅
- 扩展 alias 覆盖；Rich 输出格式化；多轮对话增强 ✅
- 详见 `docs/implementation-control.md` Phase 7.2 节

Phase 7.2 fix 场景补接线（2026-08-05，Mimo review ACCEPTED）：`fix` CLI 已接入 `FIX_SCENE_CONFIG` → ChatService（`PinnedState.user_constraints` 透传 chapter_content/audit_feedback/chapter_contract，workdir tool_service，`--llm`）；修复此前 `_run_fix_command` 惰性导入已移除符号导致的运行断链。测试数据源（`test_docling_conversion.py` / `tests/README.md` smoke 命令）统一为 `基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf`（含 2021-2025 五年完整年报）。

Phase 7.3 已完成（2026-07-29）。对话历史注入 LLM context（方案 B — Prompt 层编织）：
- **方案 B 优化设计**：`docs/phase7.3-option-b-optimization.md`（DS 二审有条件通过）
- **核心变更**：ToolCallSummary + history contribution 注入 system prompt + truncate_turns + temperature 透传修复（5 处）+ document_id 前缀匹配
- **总改动量**：~164 行（session_models ~30 + chat_service ~63 + scene_config ~1 + deepseek_llm ~1 + llm_tool_loop ~15 + extraction ~3 + main ~1 + 测试 ~50）
- **失败模式缓解**：9 项（FM1-FM9），详见优化设计文档
- **Bug 修复**：5 处 temperature 未透传（deepseek_llm.py / chat_service.py / extraction.py / main.py）+ document_id 前缀匹配（llm_tool_loop.py）
- **DS 二审裁决**：有条件通过（已处理全部 3 项）
- **记忆注入补接线（2026-08-09，P1）**：`_build_contributions` 增加 `memory` slot，EpisodeSummary（最近 ≤3 条，总长 ≤500 token 超限丢最旧，单条超 100 token 截断加省略号）与 PinnedState `confirmed_facts` 经 `build_memory_contribution` 编织进 system prompt，并标注「历史摘要，非当前证据」；空数据不产生 slot；方案 B 不变，协议层/ContextBudget/compaction 策略不动。
Phase 7.4 已实现（2026-08-02）：interactive e2e 失败修复 S0-S7 全部 ACCEPTED，opt-in live e2e 11/11 通过（0 失败 / 0 误拦截）：
- **失败自愈**：工具失败（ToolFailure）回喂 LLM 作为下一轮输入（可修正 section_ref/工具名/document_id），重复失败调用去重短路；provider 畸形响应仍 fail-closed，不回喂。
- **失败轮可观测性**：失败轮成对持久化进 session（含 tool_calls/tool_trace）；被投资建议拦截的回答保留原文与触发词；`--enable-tool-trace` 可显示失败路径工具调用（注意 e276ff3 曾误用不存在的 `entry.status` 字段，实现以 `result_kind`/`failure_code` 为准）。
- **tool call 容错**：`document_id` 缺失由 runner 用 expected 补全；工具名仅格式归一化（去空白/尾部括号参数）后白名单匹配，不做语义映射。
- **prompt 硬规则**：无事实目标问题直接 final answer；空搜索最多换 1 次词后声明未找到；section_ref/table_ref 一律复制不猜测。
- **投资建议判据（决策 A）**：弱词（买入/卖出/增持/减持）在 ±100 字符窗口内遇指令动词（建议/应当/可考虑/适合/值得持有/应买入/应卖出/应增持/应减持）拦截；否则窗口内含年报事实性上下文词（策略/报告期内/期末/持仓/重仓/股票投资明细/财务报表附注/买入返售/卖出回购/基金合同 等）放行；否则 fail-closed 兜底。强指令词与预期收益预测句式始终 fail-closed；main.py 用户输入预检已合一到 `llm_tool_loop.contains_investment_advice`（单一真源）。指令动词不使用单字「应」（会误命中 应付/应计）。注：2026-08-20 裁决「资产大类配置比例建议放行（见禁止事项）」后，守卫口径调整另开实现 slice；落地前本节仍为当前代码事实，守卫行为不变。
- **provider malformed 有界重试**：DeepSeek response 不可解析时最多重试 1 次（stream + 非 stream），重试后仍 fail-closed；不回喂。
- **interactive 终答守卫改写重试**：final answer 因投资建议关键词被拦时最多重答 1 次（重答仍过同一守卫）；ask/generate 不重试。
- 计划与 goal 产物：`.sisyphus/plans/interactive-e2e-fix-20260802.md`、`.sisyphus/goals/phase7.4-goal.md`、`.sisyphus/plans/phase7.4-s3-caliber-proposal.md`（均经 Mimo review ACCEPTED）。
- 禁止 Service / UI / Host / 展示层 / LLM prompt 直接消费 raw PDF、raw Docling JSON、PDF cache path、本地路径、URL secret 或 parser private payload。

interactive 问答质量语义（2026-08-05，Mimo review ACCEPTED；2026-08-09 补充；2026-08-11 补充 Fix A/E/C）：受控检索路由新增 `manager_holdings` profile（9.4 持有本基金；规模/份额/基准/超额/十大持仓 profile 排后续）；search 连续 2 次 0 命中由 runner 强制收敛（有 profile 自动候选词重试最多 1 轮），候选词注入在 Service 层、收敛执行在 Agent 层（runner 不 import service）；终答保持 JSON 契约 + runner 解包，answer 与 evidence 连续重叠 ≥40 字符或 >200 字时有界重答 1 次（2026-08-09 F1：终答 ≤200 字为 runner 硬约束，>200 触发有界重答 1 次，仍超标截断为 ≤200 字摘要，含省略说明）；interactive `max_iterations` = 8（2026-08-09 由 12 下调）；方案 E（跳过 evidence/citation 校验）不变。2026-08-09 补接线（P0-1/P0-2，Mimo review ACCEPTED）：① 受控表锚点——Service 层对高误命中 query 类（`manager_holdings` 9.4 行头优先 9.2 回退、`holdings_top10` 表头签名 序号/股票名称/公允价值 且 ≥10 行）组合 public tools 解析 `table_ref` 锚点注入 prompt，解析失败 fail-open 不注入；② `aggregate_multi_year_annual_performance` 在 interactive 开放（handler 以 catalog 重解析 annual_report_documents，忽略 LLM document_id；share_class A 类优先；ask 不开放）；③ 跨轮失败调用短路——失败调用 key（与 `_dedup_key` 同结构、含 document_id 维度）持久化进 session（上限 50 丢最旧），相同失败调用直接短路不重跑；`_dedup_key` 工具级归一化（search 归一化 query、read_section/read_table 按 ref、aggregate 按 fund_code+years+share_class）。2026-08-09 遗留缺口修复（F1/F2/F3，均 Mimo review ACCEPTED）：F1 终答 ≤200 字硬约束（见上）；F2 004393-2022 为转型当年（2022-08-08 合同生效）无「过去一年」行——10F/10G 对「表存在但无过去一年行」的 not_found message 携带可解释后缀，interactive 必须对 missing_years 逐一说明原因、禁止静默跳过或把「自基金转型起至今/期间增长率」写入年度 series；F3 interactive 年份选择新增 `--year` 参数，无 `--year` 且 stdin 非 TTY 时直接默认最新年份（不调用 input() 消费 REPL 首行），TTY 保留交互提示。2026-08-11 修复（004393「近一年净值增长率」问答，根因 R1/R2 见 implementation-control.md，均 Mimo review ACCEPTED）：① Fix A——`force_answer`（max_steps 耗尽降级）分支在 interactive 下与正常 FinalAnswer 同走终答守卫（`_apply_interactive_final_guards`，含投资建议拦截 + ≤200 字约束），不再绕过守卫；2026-08-13 细化（用户裁决方案 2，MiMo plan review ACCEPTED）：降级产物为证据原文拼接，跳过「原文粘贴 → 有界重答」子规则（该子规则对降级产物必然触发，且重答轮 provider 不收敛时必失败为 `LLM 工具循环暂不可用`），超长直接截断为 ≤200 字摘要；投资建议拦截语义不变；② Fix E——`performance_returns` 受控候选词首位加入「净值增长率」（原已是 alias，仅调候选词顺序；aliases / acceptable_title_family / requires_table_citation / extraction_allowed 不变）；③ Fix C——`performance_returns` 加入受控表锚点范围（3.2.1 exact-title search → list_tables → 表头签名 阶段/份额净值增长率/业绩比较基准收益率 去空白归一化 → A 类标题优先含 A 排除 C，004393-2025 命中 table-0009，解析失败 fail-open 不注入）；runner 层新增 `read_table` 表号一致性校验（仅 interactive）：放行集合 = 本轮 `list_tables` 结果 ∪ search 命中 `SearchResult.table_ref`，未列出/未命中的表号返回 `NOT_FOUND`「table_ref 未在当前已列出章节的表格中，请先 list_tables 并复制返回的表号」并回喂 LLM、计入失败调用短路；`ask` 不拦截。

Phase 7.5 已裁决（2026-08-05）：generate 报告生成章节级并发（设计经 Mimo review ACCEPTED，实现完成，待 controller review）：
- **并发语义**：A 前置串行 → B Ch1-6 并行（写→审计→重写闭环在 worker 内）→ C 决策串行 → D Ch0/Ch7 并行收尾；B/D 之间强制 join；输出按 chapter_id 0..7 稳定组装，warnings 按章排序。
- **并发上限 lane**：`chapter_concurrency`（CLI `--concurrency` → request 字段 → env `FUND_CHECKLIST_CHAPTER_CONCURRENCY` → 默认 4，范围 1..8；1 = 串行等价）；Service 层唯一解析点；client 无 `clone()` 时回退串行 + warning。
- **每 worker 独立 LLM client**：`DeepSeekLlmClient.clone()`（独立 `_cumulative_usage`）；章节闭环内 3 处 `self._llm_client` 引用（LlmAuditor / ChapterRepairer / `_generate_chapter_content`）显式下传局部 client。
- **线程安全硬约束**：worker 禁止直接 print（进度输出必须经主线程）；`_process_states` 按章 key + Lock；ArtifactStore 按章分文件唯一 writer；共享输入全阶段只读。
- **边界**：不引入 dayu runtime/代码/async 事件循环（DeepSeek 调用为同步 `generate_text`）；复制 Dayu 代码需先过 license gate；不改 `search_document` / Service reading tools 公共契约；不触碰 Phase 7.4 与 F1.1 未提交区域。
- 设计产物：`.sisyphus/plans/phase7.5-chapter-concurrency-design.md`（Mimo review ACCEPTED）；命名 Phase 7.5，备选 Slice 14D。
- LLM provider 自由切换（2026-08-10，DS 实施 + controller 复跑 + Mimo review ACCEPTED）：新增 `FUND_CHECKLIST_LLM_PROVIDER`（`deepseek` 默认 / `mimo`，未知值 fail-fast 抛 ValueError 提示合法取值）+ 每 provider 独立 env（mimo 默认 base `https://api.xiaomimimo.com/v1`、模型 `mimo-v2.5-pro`），请求组装（next_step / next_step_stream / generate_text）统一走 `_provider_runtime`；scene/contract 模型名翻译表（`deepseek-v4-pro→mimo-v2.5-pro`、`deepseek-v4-flash→mimo-v2.5`，未知透传），解析顺序 provider 对应 MODEL env 非空优先；`ChatService` 注入层与 interactive current_model 展示 provider 化；错误文案泛化（去 DeepSeek 前缀）；类名/文件名保留。验证：provider 测试 20 passed、adapter+chat+interactive 196 passed、最小验证 175 passed；未 commit。slice 产物：`.sisyphus/plans/provider-switch-slice-20260810.md`。
- Dayu 只能作为架构参考和能力来源；禁止直接引入 `dayu-agent`、`dayu.host`、`dayu.engine` 作为生产 runtime。
- 复制或改写 Dayu 代码必须先经过 license/compliance gate。
- Docling 为当前 production path：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback 路线。
- 禁止做与 `pdfplumber` 的替代路线比较。
- 结构化字段抽取、自动报告、信号评分已通过正式 Slice 准入（10C/10F/10G/11C/11D/13A/13B/14A/14C），不再受 MVP 禁止条款约束。
- 真实 LLM 接入必须位于已实现的 fake/injected LLM tool-loop contract 之后；不得让 LLM provider、prompt 或 adapter 直接读取 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、`local_import_id` 或 secret。
- 当前 LLM provider 支持 DeepSeek 与 Mimo（OpenAI-compatible adapter），经 `FUND_CHECKLIST_LLM_PROVIDER`（`deepseek` 默认 / `mimo`）自由切换，各自独立 env（`DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL` 与 `MIMO_API_KEY`/`MIMO_BASE_URL`/`MIMO_MODEL`）；暂不需要接入 Gemini/OpenAI/Anthropic 等其他 provider。
- live provider smoke 必须显式 opt-in；默认 pytest 不得联网、不得读取真实 API key、不得记录 raw provider response 或新增 artifact。
- `ask` 子命令已裁决通过（Phase 5，2026-07-24），streaming 已并入 Phase 5。
- `interactive` 模式已裁决通过（Phase 7，2026-07-25）。

## 身份与失败分类

- `document_id` 表示内容身份，用于 public reading tools，格式固定为 `fund_code-year-report_type-fingerprint_prefix`。
- `fingerprint_prefix` 使用 `content_fingerprint` 前 16 位 hex。
- `local_import_id` 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入；重复导入相同 PDF 时复用 `document_id`。
- `share_class` 为可选 metadata；当前不强制解析，不参与 `document_id`；无法明确 A/C 类时记录为 `null`，不得从文件名或标题猜测。
- `report_type` 支持 `annual_report`（年报主链）；`semiannual_report` / `quarterly_report` 自 2026-08-14 起支持（季报/半年报单期快照，见 design.md §6.25；quarterly 的 document_id 带 `-Q[1-4]` 期次段）。快照文档不得进入 multi-year / generate annual 系列（catalog 过滤按 `report_type=annual_report` 防污染）。
- PDF integrity 至少校验 Content-Type、PDF magic bytes、非空内容和原子写入。
- 失败必须分类，禁止吞并为模糊异常：
  - `not_found`
  - `unavailable`
  - `schema_drift`
  - `identity_mismatch`
  - `integrity_error`
  - `docling_convert_failed`
  - `parser_health_failed`
  - `llm_malformed_response`（仅用于真实 LLM adapter response 结构不可解析）
- fallback 必须由失败分类显式驱动；禁止用 fallback 掩盖 `schema_drift`、`identity_mismatch`、`integrity_error`。
- LLM provider 的 key 缺失、auth、network、timeout、rate limit 默认映射为 `unavailable`；provider response 非法或不可解析映射为 `llm_malformed_response`。

## 当前阶段

MVP 阅读工具层已于 Slice 4 验收通过并 close。项目现已进入 **基金分析助手** 阶段，已实现能力包括：

- 本地 PDF 导入、Docling 转换、parser health 校验
- 7 个文档阅读工具 + locator/citation/redaction
- Service 层受控 profile routing + disclosure target contract
- 结构化字段抽取：费率 (10C)、年度业绩 (10F/10G)、持仓 (11C)、资产配置 (11D)
- 多年度聚合 (3-5 年 bounded coverage, 10I/10L)
- 批量 PDF 导入 (10M)
- 确定性信号评分 (基金类型感知：主动基金 6 指标 135→100 归一化；被动基金 3 指标 100 分制)
- 8 章分析报告生成 (13A 模板填充 + 13B LLM 定性分析)
- 三层审计管道 (14C: 程序+LLM+复核, 4 类 22 项)
- Host 生命周期 (12A: timeout/event tracing)
- 披露完整性审计 (12B/12C)
- CLI 子命令：`read` / `multi-year` / `import` / `holdings` / `allocation` / `fees` / `audit` / `deep-audit` / `generate` / `snapshot-quarterly` / `snapshot-semiannual`（+ `ask` / `interactive` / `repair` / `regenerate` / `fix`，见文首 CLI 入口）

**Phase 3.5/3.6 已关闭（2026-07-21）**：报告质量稳定化 + 审计管道数据适配全部完成。三基金（512890/006597/012346）Ch1-6 审计得分全部 ≥75，端到端验证通过。**Phase 5 Gate 已解除**（持仓抽取 23/23 全部通过）。**Phase 5 已裁决并进入实施阶段（2026-07-24）**，Slice 19A-19F，详见 `docs/implementation-control.md` Phase 5 节和 `.sisyphus/plans/phase5-implementation.md`。

详细 phase 与裁决记录见 `docs/implementation-control.md`。

最小验证命令见测试规则节。

## CIC-lite 开发流程

当前项目使用 CIC-lite，不使用重型 gateflow。

- MVP plan artifact 最多 1 份。
- plan review artifact 最多 1 份。
- plan review `ACCEPTED` 后必须进入代码实现。
- 禁止新增 plan-fix / re-review / evidence gate，除非 review 明确指出违反已裁决硬口径。
- 每个实现 slice 只走：implement -> tests -> diff review。
- Controller 只维护边界、non-goals、write set、测试命令，并核验 diff 与测试输出。
- Implementation Agent 只写代码和测试，不扩大目标。
- Review Agent 只 review diff + tests，不产出新 plan，不开新路线。
- 禁止 Evidence Agent 单独写 evidence report。
- 禁止用文档更新代替可运行代码。
- 没有 diff，不算实现；没有测试命令和输出，不算完成；没有 review agent 独立检查，不算 accepted。
- Controller 不为每个 slice 同步长 control checkpoint。

## 多 Agent 协作模式

多 Agent 的目的不是增加流程产物，而是防止单 Agent 走捷径、漏测或谎报完成。

推荐三角色：

```text
Controller Agent
Implementation Agent
Review Agent
```

可以用 3 个 tmux pane，也可以用 3 个 Codex thread；tmux 只是角色隔离方式，不是必须条件。

职责固定：

- Controller Agent：派发当前唯一 slice，约束 allowed write set、stop conditions、测试命令；只采信 diff、测试输出和 review verdict。
- Implementation Agent：只写当前 slice 的代码和测试；不得写 plan、review、evidence、control-sync artifact；不得扩大 scope。
- Review Agent：只 review 当前 diff + tests；不得写代码；不得产出新 plan；不得开启新路线；输出只能是 `ACCEPTED` 或 `NEEDS_FIX`。

每个 slice 的唯一流程：

```text
implement -> tests -> diff review
```

交接材料必须包含：

- Controller -> Implementation：slice 目标、allowed write set、禁止事项、必须运行的测试命令。
- Implementation -> Controller：changed files、diff 摘要、实际测试命令、测试输出；失败时报告最小失败原因，不得声称完成。
- Controller -> Review：当前 diff、测试输出、相关真源文件路径。
- Review -> Controller：`ACCEPTED` 或 `NEEDS_FIX`；`NEEDS_FIX` 只能列最小修复项。

禁止事项：

- 禁止 Review Agent 要求新增 plan-fix / re-review / evidence gate。
- 禁止 Controller 因 review comments 新建长期流程链。
- 禁止 Implementation Agent 用 mock / fake fixture 证明 production conversion path。
- 若调用 code-is-cheap 相关 skill，必须显式声明本项目使用 CIC-lite；不得启用完整 gateflow / phaseflow / release-readiness。

## Review 规则

- LLM reviewer（DeepSeek 等）处理大 diff 时可能捏造不存在的代码并给出"修复建议"。
- 对 review findings 中的 P0/P1 项，必须先 `grep -n` 确认代码存在再行动。
- review prompt 应要求 reviewer 先列出代码行号和实际内容，再给出判断。
- 不要盲目信任 review 结论——reviewer 也会 hallucinate。

## 测试规则

- 每次代码修改必须同步新增或更新测试。
- fake fixture 只能测试边界和错误；不得用于证明 production conversion path。
- 最小验证命令固定为：
```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```
- Phase 5 验证命令：
```bash
uv run pytest tests/fund/agent/test_stream_events.py tests/fund/agent/test_llm_production_readiness.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short
```
- Phase 7 验证命令：
```bash
uv run pytest tests/fund/cli/test_cli_interactive.py   tests/fund/service/test_chat_service.py   tests/fund/host/test_session_store.py   tests/fund/agent/test_context_budget.py   tests/fund/service/test_scene_config.py   tests/fund/service/test_prompt_contributions.py   tests/fund/service/test_prompt_composer_upgrade.py   tests/fund/agent/test_tool_result.py   tests/fund/agent/test_tool_context.py   -v --tb=short
```

## 代码与文档同步

- Python 代码使用类型注解和 dataclass / Protocol 等现代特性。
- 函数、类、模块必须有中文 docstring，说明参数、返回值、异常。

- Phase 7.3 验证命令：
```bash
# Phase 7.3 核心测试
uv run pytest tests/fund/host/test_session_models.py tests/fund/service/test_chat_service.py tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_scene_config.py -v --tb=short
```
- Phase 7.2 验证命令：
```bash
# Phase 7.2 核心测试
uv run pytest tests/fund/cli/test_cli.py -k "repair or regenerate or fix" -v --tb=short
uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short
uv run pytest tests/fund/service/test_scene_config.py -k "fix" -v --tb=short
uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short
uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short
```
- 复杂逻辑使用简短中文注释说明意图。
- 修改 `fund_agent/fund/` 时同步更新 `fund_agent/fund/README.md`。
- 修改 `fund_agent/agent/` 时同步更新 `fund_agent/agent/README.md`。
- 修改 `fund_agent/host/` 时同步更新 `fund_agent/host/README.md`。
- 修改分层关系、Service/Host/Agent/Fund 边界时同步更新 `fund_agent/README.md` 和 `docs/design.md`。
- 修改测试结构或命令时同步更新 `tests/README.md`。
- 项目根 `README.md` 只写用户成功路径，不展开内部机制。

## 禁止事项

- 禁止对个股、单只基金输出买入/卖出/增持/减持等操作指令与择时建议。允许输出资产大类配置比例建议（债券基金 / 货币基金 / 股票指数基金 / 主动式权益基金 / FOF），适用于所有 LLM 通道（interactive / ask 等），前提：① 基于公开披露数据或用户自报持仓；② 输出必须附固定免责声明「本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益」。
- 禁止预测未来收益或市场走势。
- 禁止超出公开披露信息的因果推断。
- 禁止基金经理动机猜测。
- 禁止删除或覆盖未明确属于当前任务的修改。
- 禁止在报告/快照管线硬编码章节编号（如 `range(1,7)` / `range(1,8)`）；章节迭代、摘要注入与审计上下文必须按模板 `front_chapter_ids` / `chapter_ids` 驱动。
- 禁止高分放行 critical：审计通过判据 = 加权分数达门槛（80/75）且无 CRITICAL 违规；critical 一律走 REGENERATE（不 PATCH、不因高分标 pass），数据不足只降分数门槛不豁免 critical。
- 报告装配必须经模板 manifest 校验（`verify_report_assembly`）：章节集合/顺序/标题与模板 `chapter_ids` / `chapter_titles` 一致，违反 fail-closed 返回 `schema_drift`（模板模式同样生效）；内容为空仅 warning。

## 代码规范

- 禁止把显式参数塞进 `extra_payload`；公共参数必须显式声明。
- 禁止魔法字符串/魔法数字；source kind、failure code、tool name、locator kind 应集中定义。
- 禁止任何 Agent 用“逻辑上完成”“应该通过”“已按计划完成”替代测试输出。

## 必须事项

- root cause 必须逻辑/数据同源，禁止用间接证据代替。
- 所有工具输出必须可溯源到年报 locator。
- 所有外部来源、PDF、Docling、parser 失败必须 fail-closed 或显式分类。
- 输出下一步时必须给出最小可执行验证问题或命令。

## 多 Agent 协作铁律

1. **代码实现默认派给 DS（tmux agents:0.1），Controller 做 review**
2. **发送指令给 DS 必须带 Enter（tmux send-keys 最后有 Enter）**
3. **发送新任务前必须 `/clear` 清理 DS 上下文（等 2 秒确认）**
4. **不要让用户提醒以上三条**
