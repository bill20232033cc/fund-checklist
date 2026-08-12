# Dayu-agent-r 新能力研究总结

更新时间：2026-08-10
研究范围：新版 Dayu（`noho/dayu-agent-r`）`dayu/README.md` 呈现的新能力，及对 fund-checklist 的可学习价值。
数据源：
- 主源：`https://github.com/noho/dayu-agent-r/blob/main/dayu/README.md`（278 行，仓库最后推送 2026-08-09）
- 交叉验证：GitHub code tree（7,842 个文件）+ 关键源码文件（见 §4 验证状态表）
- 基线：本地 `/Users/maomao/dayu-workspace/dayu-agent`（最后提交 2026-05-04，`2115c86`）
- fund-checklist 对照基线：`docs/research/dayu-agent-vs-fund-checklist-analysis.md`（2026-07-11）

## 1. 版本关系与整体判断

- dayu-agent-r 是 dayu-agent 的重构新版：仓库 2026-08-09 仍有推送，本地 dayu-agent 停更于 2026-05-04，两者相差约 3 个月。
- 包结构重构：新增 `dayu/contracts`、`dayu/runtime`、`dayu/documents`、`dayu/service`、`dayu/tools` 五个层中立/装配包；顶层不再有 `gui` / `web` / `wechat` 目录（CLI 保留）。
- 依赖方向收紧为 `UI -> Service -> Host -> Engine` 单向；`contracts` / `runtime` / `documents` 为层中立基础包，不属于任何业务层。
- 核心范式不变：宿主强约束下的 LLM in the loop；可靠性来自宿主边界（admission、ToolRuntime、EventLog 事实真源），不依赖模型自律。
- 本文档所有「可学习价值」是研究观点；所有代码/README 存在性均为已验证事实（验证方式见 §4）。

## 2. 新能力清单（按 fund-checklist 可学习价值分级）

### 2.1 高价值：直接对应 fund-checklist 现状短板

1. **BM25F 多字段检索排序**（代码已验证，`dayu/fins/tools/bm25f_scorer.py`）
   - 事实：为 `search_document` 提供低侵入的多字段词法排序；字段权重 title 3.0 / item 2.0 / topic 2.0 / path 2.0 / preview 1.0 / content 1.0；只增强排序、不负责召回。
   - 已集成：`dayu/fins/tools/read_runtime.py` `build_section_bm25f_index`；`search_engine.py` 排序链 = 策略优先级 → 意图一致性 → 噪音惩罚 → BM25F → 邻近度。
   - 借鉴点：fund-checklist `search_document` 当前是字面子串 + 命中次数排序（`fund_agent/fund/document_tools/docling_store.py`）。BM25F 是确定性、可解释的排序增强，不改变召回，契合 fail-closed 口径；可作为根因 R2/Fix D（search token-AND）的低风险替代或前置步骤。

2. **查询意图分类 + 自适应检索计划 + 查询扩展**（代码已验证，`search_engine.py`）
   - 事实：`_classify_query_intent`（token 意图分类）→ `_build_adaptive_search_plan` → `_filter_matches_by_intent`（期望 bucket 过滤）→ `_build_search_query_expansions`（短语变体 + 同义词）；另有 `fiscal_period_recency_rank` 财政期时效排序。
   - 借鉴点：fund-checklist 已有 Service 层受控 profile routing + `candidate_queries` 注入（9C/10B/11A），与「意图 → 期望 bucket」模式同构；可对照补强 performance 类 profile 的检索侧短板（根因 R3）。是否需要 LLM 侧意图分类由 D1/D2 决策，非默认建议。
   - 落地风险：中。fund-checklist 已用确定性 profile 实现同等目的，优先做排序增强而不是引入 LLM 意图分类。

3. **wait-resume 长事务工具治理**（代码已验证）
   - 事实：长事务工具返回 `ToolAwaitingOutcome` → Engine 以 `run_suspended` 收口（`engine/contracts/engine_events.py` `RUN_SUSPENDED = "run_suspended"`）→ Host 把 Run 推进为 `WAITING` 并创建 wait record → 外部完成后 `resolve_wait(...)` → 为同一 Run 创建新的 resume Attempt；resume 不恢复旧 Agent / Runner / 工具调用栈。配套 production wait poller（construction-time 注册）与 wait callback endpoint（`service/wait_callback_endpoint.py`，framework-neutral mapper）。
   - 借鉴点：fund-checklist 的 `download` / `import` 是同步 CLI 命令；若未来出现批量下载、异步导入或长事务工具，可用 wait-resume 而不是在 CLI 内阻塞等待。
   - 落地风险：高（涉及 Host 状态机）；建议仅在真实异步需求出现时引入。

4. **process-backed 工具执行（可抢占取消/超时）**（代码已验证，`dayu/runtime/interruptible_process.py`）
   - 事实：Doc / Fins read 与 Web blocking 工具生产路径使用子进程执行，使 Host 取消或超时时不等待同进程 blocking I/O 自然结束；模块只负责子进程启动、结果回收、terminate/kill 与 bounded close。
   - 借鉴点：fund-checklist 的 Docling 转换 / read 是同步阻塞；Host 生命周期 12A 已有 timeout 但没有进程隔离。可借鉴「取消/超时 = 杀子进程」模式。
   - 落地风险：中。

5. **durable EventLog + admission + outbox + startup recovery（事实真源治理）**（代码已验证，`dayu/host/durable/`）
   - 事实：Host durable EventLog 与同事务状态索引是治理事实真源；projection、memory、tool trace、outbox、audit 都是派生视图。同 Session 的 active Run 由 admission 约束；queued Run 是 durable state。进程退出时不在退出瞬间伪造 terminal facts，启动时 startup recovery 基于 durable truth 做 positive orphan proof 分类后才 closeout 或创建 recovery Attempt。
   - 借鉴点：fund-checklist 的 session store 是轻量持久化；若 interactive 会话需要可审计、可恢复、防重复提交（幂等），可借鉴 EventLog + idempotency + recovery proof 语义。
   - 落地风险：高（架构级重构）；不建议近期做，仅记录为方向。

6. **终答守卫覆盖降级路径**（本次修复已落地）
   - 事实（dayu-agent-r README）：assistant final answer 和普通工具证据不会自动成为 evidence-backed fact。
   - 对应落地：interactive 下 max_steps 耗尽的 `_force_answer_from_evidence` 降级产物与正常 FinalAnswer 同走 `_apply_interactive_final_guards`（≤200 字硬约束 + 原文粘贴 ≥40 字符检测 + 有界重答 1 次 + 截断摘要），Mimo review ACCEPTED（2026-08-10）。

### 2.2 中价值：模式可借鉴

7. **Tool Trace operator 固定路径**（README 声明 + 代码存在 `service/tool_trace_analysis.py`）
   - 事实：`CLI -> Service path discovery/publication -> Host Analyzer -> Tool Trace projection/resolver`；Analyzer 只读消费派生 trace，不成为 durable truth。
   - 借鉴点：fund-checklist 已有 `--enable-tool-trace`（AgentRunResult.tool_trace），可对照补 operator 层与「分析器只读」边界。

8. **日志分级 VERBOSE=15 + 有界脱敏诊断载荷**（代码已验证，`dayu/runtime/log_levels.py`）
   - 事实：`VERBOSE_LOG_LEVEL = 15`；Runner/provider 诊断事件上的 `raw_payload` 是有界、脱敏、摘要化诊断载荷，不保证保留 provider 原始 payload；Engine/Runner 日志不输出完整 prompt、provider headers、API key、完整工具结果。
   - 借鉴点：与 fund-checklist「不得记录 raw provider response、不得打印 API key」一致；可补 VERBOSE 级执行路径骨架日志。

9. **context compaction governance**（README 声明 + 代码存在 `host/compaction*.py` / `context_governance.py` / `context_policy.py`）
   - 事实：proactive/reactive compaction；每个操作的成功/失败终态由共享 terminal owner 在 transaction 内 first-committer-wins；Engine 的成功 final contract 携带终止该回答的 Runner response identity，compactor 直接保留该 identity，不从配置/相邻事件反推 provider 响应。
   - 借鉴点：fund-checklist 已有 ContextBudget + EpisodeSummary 异步压缩（Phase 7.1），但「compact 生命周期属于 Host、迟到结果不能写 artifact」的治理语义可补强。

10. **Conversation Memory 作为 projection read model**（README 声明 + 代码存在 `host/durable/memory.py`）
    - 事实：Host Session-level read model，只消费 committed facts 与 accepted compact 结果；保持可重建、带 provenance、带 digest。
    - 借鉴点：fund-checklist 的 memory slot 编织（2026-08-09 P1）可对照「memory 是派生视图、不是真源」的边界。

11. **层中立契约包 `dayu.contracts`**（代码已验证，`dayu/contracts/`）
    - 事实：承载 JsonValue、CancellationToken、ToolSchema/ToolBundle、process envelope、ToolResultEnvelope、ToolAwaitingOutcome、AgentFallbackMode 等层中立契约，不承载 Host/Engine 状态机与财报业务事实。
    - 借鉴点：fund-checklist 已有 ToolResult 信封 + failure code 集中定义；可对照把公共契约从业务包中拆出。

12. **结构化输出 request**（代码已验证，`engine/contracts/structured_output.py`）
    - 事实：`JsonObjectStructuredOutputRequest` / `JsonSchemaStructuredOutputRequest`，JSON object 或 JSON schema 两种形态。
    - 借鉴点：可用于 fund-checklist 受控 JSON 契约（终答 JSON + runner 解包）的 provider 侧强制。

### 2.3 低价值 / 不适用

13. **runtime.lane 跨进程容量治理**（代码已验证 `runtime/lane.py`）：claim/heartbeat/timeout/acquire cancellation；fund-checklist 单机单进程场景收益低。
14. **web tools**（代码已验证 `dayu/tools/web/`：playwright backend、egress policy、challenge detection、recovery、resource budget）：fund-checklist 联网是已知能力差距（AGENTS.md「无法获取实时市场数据」），但引入联网涉及产品边界与合规决策，不做默认建议。
15. **section_semantic SEC Item 映射**（代码已验证 `fins/tools/section_semantic.py`）：10-K/10-Q/20-F 专用；模式可参考，资产不适用基金年报。
16. **美股 / A 股 / 港股市场能力**：超出 fund-checklist 基金年报定位。

## 3. 对 2026-07-11 对标结论的更新

- 已拉齐（Phase 5 / 7 / 7.1 / 7.2 后）：多轮对话 `interactive`、上下文记忆（memory slot）、LLM 自主工具调用 `ask`、streaming、多 provider（deepseek / mimo 自由切换）。
- 本次修复补上：interactive 终答质量守卫覆盖 force-answer 降级路径（Mimo ACCEPTED）。
- 仍缺：联网搜索、网页抓取、微信入口、GUI / Web UI。

## 4. 验证状态表

| 声明（README 位置） | 验证方式 | 结果 |
|------|------|------|
| 依赖方向 `UI -> Service -> Host -> Engine`（L6-9） | 目录结构 | 代码已验证：包分层存在且 Engine 不导入 Host |
| 层中立包 `contracts` / `runtime` / `documents`（L62-69） | 目录结构 | 代码已验证 |
| `run_agent_messages` / `run_agent_and_wait` 稳定入口（§Engine public contract） | `dayu/engine/__init__.py` | 代码已验证（函数式入口，不导出实现类） |
| `RUN_SUSPENDED = "run_suspended"`（wait-resume，L115-118） | `engine/contracts/engine_events.py` | 代码已验证 |
| `open_host` / `open_host_admin` 双 handle（§Host public contract） | `dayu/host/__init__.py` | 代码已验证（来自 `host/open_host.py`） |
| 日志 `VERBOSE=15`（§日志与可观测性） | `runtime/log_levels.py` | 代码已验证（`VERBOSE_LOG_LEVEL = 15`） |
| BM25F 检索排序（§工具与 Fins） | `fins/tools/bm25f_scorer.py` + `read_runtime.py` | 代码已验证（已集成进 search_document） |
| 查询意图/自适应计划/查询扩展 | `fins/tools/search_engine.py` | 代码已验证（函数存在） |
| process-backed 工具执行 | `runtime/interruptible_process.py` | 代码已验证 |
| wait callback endpoint（framework-neutral） | `service/wait_callback_endpoint.py` | 代码已验证（未验证真实 HTTP 路由，README 明示不包含） |
| Host durable EventLog / admission / outbox / recovery | `host/durable/`、`host/admission.py`、`host/dispatch.py` | 代码已验证（存在性；未做运行级验证） |
| 版本关系：dayu-agent-r 较新 | GitHub API（pushed_at 2026-08-09 vs 本地 2026-05-04） | 已验证 |
| 许可证 | GitHub API | Apache-2.0（代码复制需过 license/compliance gate） |

说明：本文档对关键项做了代码存在性验证，未做运行级验证；README 自身约束「代码真源高于设计文档」。

## 5. 落地建议

建议（低风险、直接受益，可进入后续 slice 评估）：
1. BM25F 排序增强：作为 `search_document` 的确定性排序升级（根因 R2 / Fix D 的低风险替代），保留现有召回与可解释排序说明。
2. 日志 VERBOSE 级 + 有界脱敏诊断载荷：与「不记录 raw provider response」约束对齐。
3. Tool Trace operator 对齐：只读分析器边界。

需决策（涉及边界或架构）：
4. performance 类查询表锚点注入（Fix C，D1/D2 决策）。
5. wait-resume / process-backed 执行是否引入（架构级，建议等真实异步需求）。
6. 联网 / web tools 是否立项（产品边界与合规决策）。

明确不做：SEC 市场能力、微信入口、lane。

## 6. 风险与合规

- dayu-agent-r 为 Apache-2.0：复制或改写 Dayu 代码前必须过 license/compliance gate（fund-checklist AGENTS.md 硬约束）；本文档只做概念级借鉴，未复制代码。
- dayu 只能作为架构参考与能力来源，禁止直接引入 `dayu-agent` / `dayu.host` / `dayu.engine` 作为生产 runtime。
- 研究快照：`noho/dayu-agent-r` @ `main`，2026-08-09 推送。
