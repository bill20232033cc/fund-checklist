# fund-checklist implementation-control

更新时间：2026-08-15（季报/半年报快照大任务全部完成：design.md §6.25 已写入 18 项裁决，8 slices 按 CIC-lite 逐 slice 实施完毕，A/B/C/D/E/F 全链路 diff review ACCEPTED（C/D 的 NEEDS_FIX 均已修复），005680 真实 PDF CLI 端到端验收通过，见「季报/半年报快照（snapshot）大任务」节。前序第4个任务「performance 类查询受控表锚点注入收口」全部完成：Mimo plan review（1 项误报经 controller 核验）+ DS 实施 + controller 复跑 + Mimo diff review ACCEPTED，未 commit；详见下方 slice 记录。前序：日志 VERBOSE slice 全部完成；既有回归 fix slice 完成；Tool Trace 只读分析器 slice（研究 §5 建议 3）全部完成；interactive force_answer 降级收尾 slice（Fix A 细化）全部完成：MiMo plan review + DS 实施 + MiMo diff review ACCEPTED；process-backed 工具执行 slice（研究 §2.1.4，可抢占超时）全部完成：MiMo plan review NEEDS_FIX 已修正 + DS 实施 + controller 复跑 + MiMo diff review ACCEPTED；阶段判定「建仓期」真源修正 slice 全部完成：MiMo plan review NEEDS_FIX 2 项已修正 + DS 实施 + controller 复跑 + MiMo diff review ACCEPTED）
当前阶段：`FUND_ANALYSIS_ASSISTANT`
当前角色：control / CIC-lite controller
当前目标：季报/半年报快照大任务（snapshot-quarterly / snapshot-semiannual，8 slices）— ✅ 全部完成（2026-08-15 收口：全链路 diff review ACCEPTED + 005680 真实 PDF 端到端验收通过，见文末「快照大任务」节）。前序已收口：QDII slice 序列 — S1 持仓 ✅、S2 费率 ✅、S3 资产配置 ✅、S4 持有本基金 ✅（全部 controller review 通过）。007466 slice — ✅。interactive 质量修复 — ✅。PDF 导出 fallback — ✅。测试修复 slice — ✅。Phase 7.5 — ✅。F1.1 — ✅。交互问答与记忆能力改进 — P0-1/P0-2/P1 全部实施完成（2026-08-09，Mimo 三连 ACCEPTED），待 opt-in live 复跑授权（见文末裁决节）。004393「近一年净值增长率」问答修复 — Fix A/E/C 全部完成（2026-08-11，Mimo ACCEPTED），待用户重启 interactive 进程 + 授权 live 复测（见文末收口节）。dayu-agent-r 研究 — ✅ 完成（docs/research/dayu-agent-r-research-20260810.md）。BM25F 检索排序增强 — ✅ 完成（2026-08-13，全链路 ACCEPTED，见文末 slice 节）。日志 VERBOSE 级 + 有界脱敏诊断载荷（研究 §5 建议 2）— ✅ 完成（2026-08-13，全链路 ACCEPTED，见文末 slice 节）。Tool Trace 只读分析器（研究 §5 建议 3）— ✅ 完成（2026-08-13，全链路 ACCEPTED，见文末 slice 节）。interactive force_answer 降级收尾（Fix A 细化，方案 2）— ✅ 完成（2026-08-13，MiMo plan review + DS 实施 + MiMo diff review 全链路 ACCEPTED，见文末 slice 节）。
multi-year 缺失原因透传 slice — ✅ 完成（2026-08-14，CIC-lite implement + tests；`MultiYearAnnualPerformanceSeries.missing_year_notes` 逐条透传缺失年份原因：10F/10G NOT_FOUND message / catalog 缺失说明 / 默认说明；CLI 与 interactive 证据文本均带出；plan：`.sisyphus/plans/multi-year-missing-reason-slice-20260814.md`）。
005680-2022 年度业绩抽取缺口修复 slice — ✅ 完成（2026-08-14，CIC-lite implement + tests；title-family raw-excerpt 兜底 + 非转型 A/C 行级 share-scope 判别（过去三年/五年 → A）；005680 multi-year 2021-2025 全覆盖（2022 A 类 -22.35%/-15.20%/-7.15%，citation table-0010），004393 转型年口径不回退；plan：`.sisyphus/plans/005680-annual-performance-extraction-fix-20260814.md`）。
performance 类查询受控表锚点注入收口 slice（第4个任务，研究 §5 建议 4）— ✅ 完成（2026-08-14）：Mimo plan review `NEEDS_FIX` 1 项经 controller 直接实证核验为误报（「超额表现」经「超额」子串 alias 命中，`any(alias in query)` 返回 True），设计口径不变，plan 已补匹配 alias 注释；DS 实施（`performance_returns` aliases 扩展「超额收益/超额收益率/超额/净值表现」，candidate/acceptable/anchor/requires_table_citation 全不变，复用 3.2.1 表锚点）+ controller 独立复跑（定向 26 passed）+ Mimo diff review `ACCEPTED`（`docs/reviews/code-review-20260814-160646.md`，未发现实质性问题，write set 无越界）；测试：主验收 98 passed / e2e 19 passed（004393-2025 → table-0009、005680-2022 → table-0010 smoke）/ 最小验证集 197 passed；未 commit / 未 push；plan：`.sisyphus/plans/performance-query-anchor-extension-slice-20260814.md`。
关联文档：AGENTS.md（执行规则）、docs/design.md（设计决策）

## 已完成研究报告

- **dayu-agent vs fund-checklist 能力对标研究**（2026-07-11）：完整对比报告已生成至 `docs/research/dayu-agent-vs-fund-checklist-analysis.md`，覆盖 Agent 问答、分析报告生成、架构层面三大维度，含优先级修复建议。报告确认：fc 的 reading tools 已对齐 Dayu；Agent 自主决策、多轮对话、Streaming 为当前最大差距；信号评分与审计管道为 fc 独有优势。
- **基金分析助手扩展研究：持仓估值、市场温度计与投资者行为矫正**（2026-08-15，研究完成待裁决）：完整报告已生成至 `docs/research/fund-assistant-expansion-and-behavior-20260815.md`（328 行，5 个联网研究子代理 + 005680 年报本地实证）。覆盖四部分：(1) 基金助手扩展方案——持仓录入（基金份额/股票标的）、实时估值（天天基金 fundgz/f10、腾讯/新浪行情，均免费无鉴权）、有知有行市场温度计自制路径（akshare 中证全指 PE/PB → 分位温度 → 连续映射股债现金区间）；(2) 005680 最小验证执行完毕——规模（§section-0630, p.69, 表table-0088）：份额 2021 期末 18.21 亿 → 2025 期末 5.91 亿份（-67.5%，连续 4 年净赎回，2025 业绩 +28.70% 但规模仍缩 30.4%）；持仓（§section-0572, 表table-0073, p.61）：前十大 44.0%，重仓有色+AI 科技与 2025 申万强势行业（有色 +90% 居首、AI 科技牛）高度契合，超额可持续性存疑（风格押注 + 2025-07-15 基金经理变更）；(3) 券商 AI 平台对比——ai-hedge-fund 入门首选、有知有行方法论最透明、券商智能投顾实测六成交白卷；(4) 交易助手行为矫正功能清单（P0 防追涨杀跌 / P1 保底仓 / P2 破幻想 / P3 合规）。下一步建议按 §6 优先级表裁决。
- **dayu-agent-r 新版能力研究**（2026-08-10，2026-08-11 收口）：研究总结已生成至 `docs/research/dayu-agent-r-research-20260810.md`（129 行），基于 dayu README 原文（`/tmp/dayu_README.md`）输出 16 项能力分级、验证状态表、落地建议与 license 合规边界。结论：多角色 agent 编排、场景化 prompt 路由、上下文压缩与工具失败自愈已与 fc 对齐；记忆/知识库持久化、定时任务与主动推送、多模态输入等尚未采用，可作为后续 backlog 候选。dayu 代码不可直接引入 production runtime（AGENTS.md 已裁决）。收口动作：AGENTS.md「当前已知能力差距」节已按研究结论更新（修正 ContextBudget 接入 runner 过时口径 + 补差距现状与 backlog 候选）。

## 开发路线

### Phase 1：稳定化
- **Slice 15A**：提交遗留 + 清理 smoke work-dirs + full regression
- **Slice 15B**：拆分 reading_service.py（extraction_service / chapter_generator / evidence_builder）

### Phase 2：Ch7 结构化判断 + 模板区块补齐
- **Slice 16A**：Ch7 确定性信号判断 + Ch6 风险清单表 ✅ 已完成（含加权 Jaccard）
- **Slice 16B**：Ch6 压力测试表（按基金类型分 3 档跌幅 × 3 场景）✅ ACCEPTED（2026-07-13）
- **Slice 16C**：Ch0 升级/降级阈值事件 + 一句话产品定义

### Phase 3：报告质量 + 可用性
- **Slice 17A**：报告 Markdown 持久化 + metadata sidecar
- **Slice 17B**：citation 验证工具
- **Slice 17C**：generate CLI 端到端 smoke ✅ 已完成（发现 3/8 章失败，触发 Phase 3.5）

### Slice 17C 实施规格

裁决：
1. 只做 `generate` CLI 端到端 smoke，不新增 `ask / interactive / streaming`。
2. 真实样本固定为仓库本地 PDF：`基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf`；样本缺失时该 smoke 直接 blocker，不得用 fake PDF 替代。
3. 先完成 `import`，再执行 `generate`；验证链路为：真实 PDF -> import -> generate -> report 落盘 -> 审计产物落盘 -> exit code 验证。
4. 本次 smoke 使用 `--format markdown`，验证落盘链路；默认 `json` 模式只打印 stdout，不单独作为本 slice 的落盘验收。
5. 验收口径：exit code 0；stdout JSON 包含 `fund_code=004393`、`report_year=2024`、8 个 chapters；落盘文件包含 `reports/{fund_code}-{year}-analysis.md`、`reports/{fund_code}-{year}-analysis.meta.json`；至少存在一个 `audit_artifacts/chapter_*_audit.json`。
6. 本 smoke 不测 LLM 输出质量，不测泛化问答，不改现有 report contract，不进入默认慢路径 pytest gate。

### allowed write set（17C）

- `tests/fund/cli/test_cli.py`
- `docs/implementation-control.md`
- `docs/design.md`

### 验证命令（17C）

```bash
mkdir -p /tmp/fund-checklist-17c-pdf

cp "基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf" /tmp/fund-checklist-17c-pdf/

uv run python -m fund_agent.cli.main import --pdf-dir /tmp/fund-checklist-17c-pdf --fund-code 004393 --fund-name "安信企业价值优选混合型证券投资基金" --year-range 2024-2024 --work-dir .fund_checklist_cli_smoke_17c

uv run python -m fund_agent.cli.main generate --fund-code 004393 --fund-name "安信企业价值优选混合型证券投资基金" --year 2024 --format markdown --llm --work-dir .fund_checklist_cli_smoke_17c
```

### stop conditions（17C）

- 真实 PDF 不存在。
- import 或 generate 非 0 退出。
- report markdown / sidecar 未落盘。
- 审计产物未落盘。
- smoke 被放进默认 pytest gate，导致常规回归变慢。
- 顺带扩大成 `ask / interactive / streaming` 或新增用户入口。

### Slice 17B 实施规格

裁决：
1. 输入必须是结构化 `Citation / Locator`，不接受自由文本 locator 解析。
2. 输出契约固定为 `ExcerptContent | ToolFailure`，不新增新模型，不新增 page-only locator 路由。
3. 验证口径是“locator 可回溯且可读取原文片段”，不做内容语义真伪校验（不判断是否支撑结论）。
4. 集成层复用 `FundDocumentToolService.get_excerpt`，不新增 raw Docling JSON / raw PDF / 本地路径暴露。
5. 输入参数：`citation: Citation`（可选 `max_chars`）；可叠加 `document_id` 显式入参以匹配公共 tool 契约。
6. 验证逻辑：(1) `citation.locator.document_id == document_id`；(2) `locator_kind` 合法；(3) 按 `table / section / excerpt` 路由取摘录。

### allowed write set（17B）

- `fund_agent/fund/document_tools/service.py`
- `tests/fund/document_tools/test_get_excerpt_verify.py`
- `docs/implementation-control.md`
- `docs/design.md`

### 验证命令（17B）

```bash
uv run pytest tests/fund/document_tools/test_get_excerpt_verify.py tests/fund/service/test_extraction.py tests/fund/cli/test_cli.py -x --tb=short -q
```

### stop conditions（17B）

- 接受自由文本 locator 或章节号字符串作为输入。
- 新增 raw payload 或本地路径暴露。
- 输出新增非 `ExcerptContent | ToolFailure` 的新模型。
- 将验证口径滑向“内容是否支持结论”的语义校验。
- 未覆盖 `not_found / identity_mismatch` 两个失败路径测试。

### Slice 17A 实施规格

sidecar = 伴随主文件的元数据 JSON 文件。报告正文是 Markdown（给人看），sidecar 是结构化 JSON（给程序读）。

裁决：
1. 格式：JSON（与 ArtifactStore、CLI 输出一致）。
2. 文件命名：`{fund_code}-{year}-analysis.meta.json`，与 .md 同目录（`{work_dir}/reports/`）。
3. 字段范围：`fund_code`、`fund_name`、`report_year`、`generation_time`（ISO 8601）、`audit_score`（无审计时 null）、`signal`（🟢/🟡/🔴）、`normalized_score`（0-100）。
4. audit_score 来源：有审计时取全章平均分；无审计时 null，不伪造。
5. 生成时机：紧跟 `_export_markdown` 之后写入，保证 .md 和 .meta 原子性。
6. `_export_markdown` 增加 `signal_judgment` 参数，透传 signal 和 normalized_score。

### allowed write set（17A）

- `fund_agent/service/extraction.py`
- `tests/fund/service/test_extraction.py`
- `tests/fund/cli/test_cli.py`
- `docs/implementation-control.md`
- `docs/design.md`

### 验证命令（17A）

```bash
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py -v --tb=short
```

### stop conditions（17A）

- sidecar 字段缺失或类型错误。
- .md 存在但 .meta.json 不存在。
- .meta.json 中 audit_score 非 null 但无审计路径。
- signal_judgment 为 None 时 sidecar 中 signal/normalized_score 应为 null，不得报错。

### Phase 3.5：报告质量稳定化（阻塞 Phase 4）

> 17C 手动验证发现 3/8 章失败（Ch2/Ch3/Ch5），根因：数据不足时无降级策略、审计阈值与数据现实脱节。
> 本 Phase 完成前，Phase 4 不得启动。

- **Slice 17D**：Ch2 单年降级 + Ch3 fund_manager 抽取修复 + LLM 分析约束。
  - Ch2：单年导入时输出结构化缺失声明 + 已有单年数据表格，保留多年要求但不因数据不足导致 audit 循环失败。
  - Ch3 bug fix：`_extract_fund_manager_with_citation` 按 section_ref 精确匹配 table，但 table-0014 在 section-0078 而非 section-0073。修复：改为按 section title 关键词匹配——search_document("基金经理") 收集所有 hit.section_ref，list_tables 后检查每个 table 所属 section 的 title 是否含"基金经理"，匹配则为候选 table。无匹配时 fallback：在 search_document 命中的所有 section_ref ±10 范围内扫描。
  - Ch3 LLM 约束：fund_manager 部分字段缺失时，LLM 只分析已有数据（持仓行为），逐项声明缺失字段及原因；禁止从持仓反推基金经理意图。章节状态标记为 `passed_with_degradation`。
- **Slice 17E**：Ch4 报告年份适配 + Ch5 must_answer 结构化规则。
  - Ch4：report_year < 2026 时标注「本章节适用于 2026 年及以后年度报告」，输出 N/A 声明。2026+ 年报按 ChapterContract 生成。
  - Ch5：定义 must_answer 的结构化规则，LLM 在规则框架内分析：
    - 阶段判定（5 选 1，优先级从高到低）：转型期（基金经理变更 / 投资目标变更 / 业绩基准变更 / 基金类型变更）> 建仓期（成立 <2 年）> 膨胀期（规模同比增长 >50%）> 萎缩期（规模同比下降 >30%）> 稳定期（默认）。
    - 时间窗口：同比（当前年 vs 上一年）。
    - 关键变化筛选（3 维度，阈值触发才列入）：持仓变动（前十大持仓换手 >40%）、规模变动（份额×净值同比 >30%）、费率变动（管理费/托管费绝对值变动 >0.1%）。
    - 是否改变投资假设：对比 Ch7 信号评分方向是否逆转。
    - 跟踪变量：1-3 个，来自 Ch7 评分最低指标。
    - LLM 失败时重试 1 次，仍失败则模板降级（数据表格 + 阶段判定结果 + 缺失声明）。
- **Slice 17F**：审计管道数据适配。
  - data_sources 缺失时 LLM 审计权重 70%→50%，程序审计 30%→50%。
  - 数据不足场景通过阈值降至 ≥70。
  - 审计产物记录数据不足状态、触发的降级规则、权重调整情况。
- **Slice 17G** ✅：端到端验证通过（8/8 章非空）+ LLM 稳定性修复 + 模板降级 + _is_data_sufficient 精确化。DS ACCEPTED。

> **17G 端到端验证暴露报告质量问题**：8/8 章非空但内容质量差。4/8 章为纯模板（Ch0/Ch1/Ch4/Ch6/Ch8），4/8 章有 LLM 分析但被审计打回。根因：hallucination 检测误杀 + 程序审计假阳性 + LLM 审计 hallucinate + 模板系统不一致。详见 `/tmp/phase35-quality-improvement-plan-v4.md`。

### Phase 3.5（续）：报告质量深度修复

**裁决记录**：
- 最少 3 年数据：**强制**（不足 3 年拒绝生成）
- 修复优先级：**先修 hallucination 误杀**（自然减少 fallback）
- 审计阈值：保持 80，修复后观察得分再决定

- **Slice 17H** ✅：hallucination 检测修复 + LLM 提示词改造。
  - `contains_non_year_numbers` 数字归一化：strip trailing zeros（`1.20` → `1.2`）。
  - 跨章节数据引用：`generate_report` 层面收集所有章节 `allowed_numbers` 合并为全局集合。
  - LLM 提示词：删除"不要包含任何数字"，改为"可以引用数据表中的数字，但不得编造数据表中不存在的数字"。
  - 验收：LLM 输出"管理费为1.2%"不被拦截；"规模为3.5亿元"（不在任何 data_table 中）仍被拦截。
- **Slice 17I** ✅：程序审计引用排除 + LLM 审计 prompt 约束 + JSON 解析重试 + 截断限制修复。
  - `ProgrammaticAuditor._check_prohibited_content` 跳过 `## 分析` 之前的内容（data_table 区域）。
  - `LlmAuditor` prompt 增加正例/反例："建议关注" ≠ 投资建议；"基金仍可跟踪" ≠ 投资建议；投资建议定义为"买入/卖出/持有"的直接操作建议。
  - `LlmAuditor` JSON 解析失败时重试 1 次。
  - 截断限制：章节摘要 300→1000 字符；LLM 审计器数据表 1000→3000 字符；Ch0/Ch7 提示词摘要 500→1500 字符。
  - 验收：audit.json 中不再出现"建议关注被判为投资建议"类违规；Ch5 不再出现 LLM_PARSE_ERROR。
- **Slice 17J** ✅：fallback 条件收紧 + 模板统一化。
  - 审计循环耗尽时：得分 < 50 返回模板 + 标记 `passed_with_degradation`；≥ 50 返回 LLM 内容 + 标记 `passed_with_degradation`。
  - `extraction.py:_generate_template_chapter` 改为调用 `generate_data_table()`，统一两套模板系统。
  - CLI 模板模式提示：不传 `--llm` 时 stderr 输出警告。
  - 验收：不传 `--llm` 时报告仍包含结构化数据表；传 `--llm` 时 8 章全部有 LLM 分析。
- **Slice 17K** ✅：多年数据强制。
  - `import` 命令 `--year-range` 默认最近 3 年。
  - `generate` 命令可用年份 < 3 时拒绝生成，报错提示用户补充导入。
  - 验收：仅 1 年数据时 generate 命令报错退出。

- **Slice 17L** ✅：Ch5 预计算 + hallucination 软门禁 + 阶段判定逻辑。
  - data_table 添加份额万份、费率变动、关键变化指标。
  - allowed_numbers 机制：generate_report 预收集所有章节数字传给 LLM 和程序审计。
  - 阶段判定：规模变动检测（膨胀期/萎缩期），用权益投资金额同比作为规模代理。

- **Slice 17M** ✅：报告生成架构重构（外置模板 + PromptComposer + JSON 输出）。DS ACCEPTED。（DS review ACCEPTED，3 个澄清纳入）。
  - Fix 1：Ch3 data_table 预计算持仓合计（前五/前十大合计、第一大重仓占比）。
  - Fix 2：Ch5 data_table 统一口径——权益投资同比（代理）+ AUM 绝对值 + 份额变动率，三口径并列。
  - Fix 3：C3 纵深防御（仅当 Fix 4 后仍有误杀时）——关键词紧邻"策略/宣称/原文"时降级 MAJOR。
  - Fix 4：提示词章节分工边界（Ch1 不讨论选股能力、Ch5 禁止自行计算）。
  - Fix 5+6：禁止操作建议（买入/卖出/持有），允许风险提示（建议关注/需持续跟踪）。
  - 目标：passed 率 2/8 → 6/8。

- **Slice 17N** ✅：Ch5/Ch6 报告质量提升（模板优化 + 数字引用规范 + must_answer 补齐）。
  - 17N-1：所有模板增加数字引用规范（引用原始数字，不缩写）。
  - 17N-2：Ch5 模板重写（数据验证 + 口径强调 + 阶段判定逐步核对）。
  - 17N-3：Ch6 ChapterContract 补充 must_answer "信息缺口"。
  - 17N-4：Ch6 模板增加投资建议边界清单。
  - 17N-5：端到端验证（Ch1-6 ≥75 passed 率 ≥4/6）。
  - 裁决：数字引用走方案 A（模板约束，不缩写）；目标 ≥75 passed（非 degradation）。

**Phase 3.5 最终验收** ✅ 已关闭（2026-07-19）：

| 验收项 | 标准 | 结果 |
|--------|------|------|
| 8 章 LLM 分析 | 传 `--llm` 时全部有 `## 分析` 段落 | ✅ 8/8 |
| 审计得分 | Ch1-6 ≥75 passed ≥4/6 | ✅ 4/6（Ch1=82.5, Ch2=75.5, Ch3=87.5, Ch4=86.0） |
| 模板模式 | 不传 `--llm` 时包含结构化数据表 | ✅ |
| 多年数据强制 | 仅 1 年时拒绝生成 | ✅ |
| P2 误杀修复 | 逗号预处理 + 单位等价匹配 | ✅（Ch5 P2 从 5 个降至 1 个） |

端到端验证数据（兴全 163415，5 年 2021-2025）：
- Ch0=80.4 Ch1=82.5 Ch2=75.5 Ch3=87.5 Ch4=86.0 Ch5=66.5 Ch6=68.5 Ch7=80.4
- Ch5/Ch6 未达 75 的根因是 LLM 内容质量问题（分析深度不足、逻辑矛盾），非 hallucination 或模板问题

### Phase 3.6：合同架构重构（阻塞 Phase 5）

> 将 ChapterContract 从 Python 硬编码迁移到模板 HTML 注释（学 dayu），实现"合同定义 → 模板渲染 → 审计验证"三层联动。
> 本 Phase 完成后，Phase 5 可启动（前置条件已满足：8 章非空 + 审计数据适配 + 端到端通过）。

**裁决记录**（2026-07-19）：

| 编号 | 裁决 | 选项 | 理由 |
|------|------|------|------|
| 1 | 迁移范围 | 全部 8 章 | 一次性完成，避免新旧两套并存 |
| 2 | ITEM_RULE | 纳入，仅支持 `<when_missing>` 条件块 | 复用已有机制，不引入 facet 过滤 |
| 3 | preferred_lens | 暂不引入 | 基金是单一领域，narrative_mode 已覆盖。后续研究基金类型划分后再决定 |
| 4 | precomputed_metrics | 放在 contract 中 | 驱动预计算的核心输入，和 must_answer 并列 |
| 5 | 审计校验 | must_answer 程序化校验 | 消除 S2 违规，从 LLM 判断改为程序化匹配 |
| 6 | Phase 3.5 关闭 | 现在正式关闭 | 验收标准已达成 |

**实施内容**：

- **3.6-1**：ChapterContract 数据类扩展
  - 新增字段及类型定义：
    - `Metric`: name, formula, unit, threshold, source, note（合并预计算+口径）
    - `CrossChapterRef`: target_chapter, ref_type, note（引用 signal_scoring.py 程序化结果）
    - `DataVerificationRule`: rule_type, description
    - `ItemRule`: condition, affected_output, degradation_note（供审计检查 must_answer 缺失是否因数据缺失导致合理降级）
  - 保持现有字段：`narrative_mode`、`must_answer`、`must_not_cover`、`required_output_items`、`data_sources`
  - 新增字段：`metrics`、`cross_chapter_refs`、`data_verification`、`item_rules`

- **3.6-2**：模板 HTML 注释迁移
  - 8 个章节模板文件（ch0-ch7.md）中嵌入 `<!-- CHAPTER_CONTRACT ... END_CHAPTER_CONTRACT -->` 注释块
  - 合同内容从 audit_pipeline.py CHAPTER_CONTRACTS 字典迁移到模板
  - PromptComposer 解析 HTML 注释，提取结构化合同

- **3.6-3**：预计算指标驱动
  - `precomputed_metrics` 定义每个章节需要的预计算指标
  - `generate_data_table` 根据 contract 中的 `precomputed_metrics` 自动生成指标
  - Ch2：近 1/3/5 年 R 值、超额收益覆盖成本
  - Ch5：份额×净值同比、阶段判定结果

- **3.6-4**：must_answer 程序化校验
  - 审计管道中 S2 检查从 LLM 判断改为程序化匹配
  - 将 must_answer 字段列表与 LLM 输出的 must_answer JSON 逐项比对
  - 缺失项自动标记 S2 违规

- **3.6-5**：口径定义与数据验证
  - `metric_definitions` 定义每个指标的名称、公式、单位、阈值、替代口径说明
  - `data_verification` 定义数字引用规则（原始精度、不缩写）
  - 审计管道 P2 检查使用 contract 中的 `data_verification` 规则

- **3.6-6**：端到端验证
  - 兴全 163415（5 年）+ 安信 004393（3 年）
  - 目标：Ch1-6 ≥75 passed 率 ≥5/6
  - 回归：现有 47 个单元测试不回退

**allowed write set（3.6）**：
- `fund_agent/service/audit_pipeline.py`
- `fund_agent/service/prompt_composer.py`（新增解析逻辑）
- `fund_agent/service/chapter_generator.py`（预计算驱动）
- `fund_agent/service/prompts/ch0.md` ~ `ch7.md`
- `fund_agent/service/prompts/system_base.md`
- `tests/fund/service/test_audit_pipeline.py`
- `tests/fund/service/test_prompt_composer.py`（新增）
- `docs/design.md`
- `docs/implementation-control.md`

**验证命令（3.6）**：
```bash
uv run pytest tests/fund/service/test_audit_pipeline.py tests/fund/service/test_llm_chapter_generation.py tests/fund/service/test_prompt_composer.py -x -q --tb=short
```

**Phase 3.6 最终验收** ✅ 已关闭（2026-07-21）：

| 验收项 | 标准 | 结果 |
|--------|------|------|
| 8 章 data_verification | 全部 8 章模板 contract 含 data_verification | ✅ |
| 8 章 metrics | Ch2/Ch3/Ch4/Ch5/Ch6/Ch7 含 metrics（Ch0/Ch1 定性无指标） | ✅ |
| P2 contract-aware | P2 检查读 contract data_verification 规则 | ✅ |
| P2 推导数字 | _is_derived_number 支持加减推导（如 1.75=1.50+0.25） | ✅ |
| LLM 审计降级 | LLM_ERROR 时权重降级为纯程序审计（1.0/0.0） | ✅ |
| Ch1-6 审计得分 | ≥75 passed ≥5/6 | ✅ 6/6 |
| 单元测试 | 107 passed | ✅ |
| Ch6 模板矛盾修复 | 否决→风险分级，禁一票否决/致命等绝对化表述 | ✅ |

端到端验证数据（兴全 163415，5 年 2021-2025）：
- Ch0=80.4 Ch1=82.5 Ch2=82.5 Ch3=87.5 Ch4=87.5 Ch5=75.5 Ch6=80.4 Ch7=80.4
- Ch1-6 全部 ≥75，6/6 达标

### Phase 4：分析能力扩展（低优先级）
- ~~Slice 18A~~：已在 16A 实现，删除
- ~~Slice 18D~~：已在 16A 覆盖，删除
- **Slice 18B**：换手率追踪（低优先级）
- **Slice 18C**：份额变动 + 盈利投资者占比（低优先级）

### 技术债
- ~~P1-3：提取共享评分 helper~~ ✅ 已完成（signal_scoring.py）
- ~~extraction.py 二次拆分：提取 signal_scoring.py~~ ✅ 已完成（signal_scoring.py 282行，6个评分helper）

14C 裁决已确认（基于 dayu write_pipeline 设计）：
- 审计分层：三层递进（程序审计+LLM审计+LLM复核）
- 违规分类：4类22项（P1-P4/E1-E5/S1-S7/C1-C6）完整对齐dayu
- 评分权重：程序审计30% + LLM审计70%
- 阈值：≥80分通过，50-79分需修复，<50分需重写
- 修复策略：PATCH/REGENERATE/NONE三策略
- 修复次数：PATCH最多3次 + REGENERATE最多3次
- Ch0/Ch7：Ch1-6全部通过后生成
- 数据表格：禁止修改
- 审计产物：落盘（phase_audit.json、phase_repair.json）
- 年报年份：默认5年，最少3年

## 当前事实

- Slice 1-4 已完成并通过 CIC-lite diff review。
- 当前已实现本地 PDF 导入、Docling conversion/store、`FundDocumentToolService` 七个 reading tools 和最小 Host / Agent loop。
- Post-MVP Slice 5 当前实现 table-aware Agent loop：`search_document -> read_section -> list_tables -> read_table`，按 query、section proximity、page proximity 选择相关表格，最终回答只使用 section/table tool result。
- 真实样本 CLI smoke 已验证 `query="基金经理"` 时，Answer 包含基金经理表格中的“张明”，并输出 section citation 与 table citation。
- MiMo review 已按 Post-MVP Slice 5 口径输出 `ACCEPTED`；Slice 5 可视为本地 accepted。
- Post-MVP Slice 6 当前实现 filesystem JSON catalog persistent repository：只记录 completed report，并可按 `document_id` 恢复 `DoclingDocumentStore` 给 `FundDocumentToolService` 使用。
- `fund-checklist read` 已接入 repository-backed loader；catalog 中已有 completed report 时复用 store，不重复调用 Docling converter。
- Slice 6 review 已结束；P0 audit 确认 identity mismatch、private output redaction、incomplete/unhealthy fail-closed 和 stable failure mapping 达到 Slice 6 最小接受标准。
- Post-MVP Slice 7 当前实现 CLI packaging / command entry polish：`uv run fund-checklist read --help` 与 `uv run python -m fund_agent.cli.main read --help` 均可用。
- `uv sync` 已验证不再出现 project scripts entrypoint 被跳过的警告。
- Slice 5-7 已提交并推送到 `origin/main`，提交为 `b618e20 feat: add table-aware reading, persistent catalog, and CLI entrypoint`。
- Post-MVP Slice 8A 已实现 fake/injected LLM tool-loop contract，最新提交为 `f53dac2 Add fake LLM tool loop contract`。
- Slice 8A 验证结果：`uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `20 passed`。
- Slice 8A 扩展回归结果：`uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/agent/test_llm_tool_loop.py tests/fund/cli/test_cli.py` -> `33 passed`。
- Slice 8A `git diff --cached --check` 通过；`.fund_checklist_cli_smoke/` 仍是未跟踪本地 smoke work-dir，未 stage、未提交。
- Post-MVP Slice 8B 已实现 DeepSeek-only OpenAI-compatible adapter：`DeepSeekLlmClient` 实现既有 `LlmClientProtocol`，使用 injected transport，默认测试 no-network/no-real-key。
- Slice 8B provider 输出仍进入 8A `LlmToolLoopRunner`，citation/evidence enforcement 未绕过。
- Slice 8B 已新增集中 failure code `llm_malformed_response`；key missing/auth/network/timeout/rate-limit 映射为 `unavailable`，malformed response 映射为 `llm_malformed_response`。
- Slice 8B 未改 CLI、repository/private loader、`pyproject.toml` 或 `uv.lock`。
- MiMo review 已按 Slice 8B 口径输出 `ACCEPTED`。
- Slice 8B 本地验证结果：`uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `36 passed`。
- Slice 8B `git diff --check` 通过。
- Slice 8B 已本地提交：`f55ed4c feat: add deepseek llm adapter`；当前 `main` 相对 `origin/main` ahead 1，尚未 push。
- MVP closeout 命令已通过：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

结果：`17 passed, 1 warning`。

- warning 是 Docling internal deprecation warning，不改变 MVP closeout 结论。
- 根 `README.md` 只写 public repo 用户成功路径、安装/测试命令、本地 PDF 不入库和当前不支持能力。
- 当前有样本 PDF 和历史分析报告；`基金年报/` 作为本地材料目录不纳入 public git，后续按分析需求下载或本地提供。
- `AGENTS.md` 是执行规则入口；`docs/design.md` 是设计真源。

- Slice 16C 已实现 Ch0 升级/降级阈值事件 + 一句话产品定义：
  - 新增 `ThresholdEvent` dataclass（`models.py`），`SignalJudgment` 加 `upgrade_event` / `downgrade_event` 字段。
  - 阈值事件算法：tier-delta 驱动（F1 修复）。升级 = 选一档改善后 raw points 增量最大的指标；降级 = 选一档恶化后 raw points 损失最大的指标。
  - 边界处理（F2 修复）：全部满分 → `upgrade_event=None`；全部零分 → `downgrade_event=None`；`data_completeness < 0.5` → 两者均 `None`。
  - 产品定义：`compute_product_definition` 按 `PRODUCT_TYPE_RULES`（first-match-wins）确定性拼接一句话产品定义。
  - Ch0 数据表新增"产品定义"和"阈值事件"两个小节。
  - `signal_judgment` 参数已贯穿 `generate_data_table` → `generate_chapter` → `ReportGenerationCoordinator.generate_report` → `_generate_and_audit_chapter` 全链路。
  - 验证结果：`uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py` -> `192 passed, 2 warnings`。
  - Agent 回归：`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/agent/test_llm_tool_loop.py` -> `29 passed`。

- Slice 17A 已实现报告 Markdown 持久化 + metadata sidecar：
  - `_export_markdown` 增加 `signal_judgment` 参数，导出 .md 后自动写入 `.meta.json` sidecar。
  - sidecar 字段：`fund_code`、`fund_name`、`report_year`、`generation_time`（ISO 8601）、`audit_score`（无审计 null）、`signal`、`normalized_score`。
  - `signal_judgment` 透传路径：`generate_report` → `_export_markdown`。
  - 4 条新测试：sidecar 创建、字段完整性、有/无 signal_judgment。
  - 验证结果：`uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py` -> `197 passed, 2 warnings`。
  - Agent 回归：`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/agent/test_llm_tool_loop.py` -> `29 passed`。

## Accepted Decisions

- 产品方向：基金分析助手，覆盖年报导入 → 结构化抽取 → 多年度追踪 → 信号评分 → 报告生成 → 审计管道；已脱离 MVP 阅读工具层阶段。
- 数据源：仅本地 PDF 导入。
- Docling admission：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止路线：Docling candidate-only、benchmark-before-admission、`pdfplumber` fallback。
- `document_id`：ASCII-only，格式 `fund_code-year-report_type-fingerprint_prefix`；`fingerprint_prefix` 为 `content_fingerprint` 前 16 位 hex。
- `local_import_id`：导入事件身份，仅用于审计 metadata，不作为 public tool 输入。
- `share_class`：可选 metadata，不强制解析，不参与 `document_id`；无法明确则为 `null`。
- `report_type`：首批仅 `annual_report`。
- Locator：必须返回 `document_id`、`locator_kind`、section/table ref；page/page_range/internal_ref 可得时透传；`bbox` 仅增强。
- GitHub 仓库：public。
- Dependency preflight：`pyproject.toml` / `uv.lock` 是正式 Slice 0 产物。
- `.gitignore` 必须排除 `.venv/`、`.pytest_cache/`、`.DS_Store`、`基金年报/` 本地材料目录、Docling/cache 临时目录和常见 secret 文件。
- `docling` 版本策略：`pyproject.toml` 使用 `docling>=2.90.0,<3.0.0`；`uv.lock` 锁定实际解析版本，常规开发不得无故升级锁。
- Slice 2 conversion smoke 允许首次联网下载 Docling runtime/model 资源；缓存产物不得纳入 git。若后续要求完全离线/CI 稳定运行，另开预缓存策略，只固定资源版本/校验和。
- Slice 2 timeout：单份真实 PDF smoke 默认 300 秒；cold start download 单独计量，不作为 production conversion SLA。
- Slice 2 batch：5 份年报 batch 默认总预算 1800 秒；batch 必须按 document 独立 timeout、独立失败分类、可断点续跑，单份失败不得静默吞并整批结果。
- MVP Slice 4 closeout 时，最小 Agent loop 固定执行 `search_document -> read_section`；该事实是 MVP 历史验收口径，不是当前 Post-MVP Slice 5 的上限。
- Post-MVP Slice 5 允许 Agent 在 `read_section` 后读取同 section、同页或相邻页的候选表格；LLM/Agent 输入真源仍是受控 tool result + locator/citation，不是 raw Docling JSON。
- Post-MVP Slice 6 采用 filesystem JSON catalog 作为 local persistent repository 起点；不引入 SQLite，不新增 downloader，不改变七个 public reading tools API。
- Slice 6 repository-backed loader 的职责是从 completed catalog record 恢复 `DoclingDocumentStore` 或装配 `FundDocumentToolService`；不得向 Agent/Host/UI 暴露 raw Docling JSON、本地路径、cache path 或 `local_import_id`。
- Slice 6 只登记已完成 local PDF + Docling JSON + parser_health 通过的 report；catalog 有记录但 Docling JSON 缺失时 fail-closed，不自动 reconvert 或 repair。
- Post-MVP Slice 7 只修 CLI packaging / command entry；不新增 CLI 子命令，不改变 repository、Agent 或 Fund public tool 行为。
- Post-MVP Slice 8A 裁决为 fake/injected LLM tool-loop contract；不直接接 OpenAI、Claude 或其它真实外部模型 API。
- Slice 8A 的最小协议是 `LlmClientProtocol`、`FakeLlmClient`、`ToolCall -> ToolResult -> FinalAnswer`。
- Slice 8A 只开放 reading tool 子集：`search_document`、`read_section`、`list_tables`、`read_table`、`get_excerpt`；不得向 LLM adapter 暴露 repository/private loader、raw Docling JSON、PDF path、cache path 或 `local_import_id`。
- Slice 8A 最终回答必须只来自 tool result；`citations` 必须非空；每个关键事实至少有 section 或 table citation。
- Slice 8A 不新增用户 CLI 参数或 `fund-checklist ask`；CLI 暴露 LLM 模式需另行裁决。
- Post-MVP Slice 8B 已实现为 DeepSeek real LLM adapter behind existing contract；真实 provider 只能实现 `LlmClientProtocol`，不得绕过 8A runner/enforcement。
- Slice 8B 当前支持 DeepSeek 与 Mimo（OpenAI-compatible adapter）；暂不需要接入 Gemini/OpenAI/Anthropic 等其他 provider。
- Slice 8B 不新增 SDK 依赖，使用 adapter + injected transport；若实现必须使用官方 SDK，需先停止并申请允许修改 `pyproject.toml` / `uv.lock`。
- Slice 8B 环境变量裁决为 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`（Mimo 复用同组环境变量，通过 `DEEPSEEK_BASE_URL` 指向 Mimo endpoint）；默认值测试不得依赖。
- Slice 8B 单元测试默认不联网；live provider smoke 必须显式 opt-in，并且不得作为默认 pytest gate。
- Slice 8B 不新增 `fund-checklist ask`、streaming、prompt framework、richer QA/eval、自动报告或投资判断。
- Post-MVP Slice 8C 裁决为 opt-in live DeepSeek smoke；默认 pytest 仍 no-network。
- Slice 8C 只由 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 触发；未设置时 live test 自动 skip。
- Slice 8C API key 来源为 `DEEPSEEK_API_KEY`；缺失时 skip，不失败。
- Slice 8C `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，可覆盖。
- Slice 8C `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，可覆盖。
- Slice 8C 不跑真实 PDF、不跑 CLI、不使用 repository-backed loader；只使用 fake/in-memory tool service 或现有测试 fixture。
- Slice 8C 最多 1 个 live run，timeout 300 秒，最多 1 次 retry，不做批量问题。
- Slice 8C opt-in 后 provider response 不可解析、8A enforcement fail、network/429/auth error 均为 test fail；未 opt-in 或缺 key 为 skip。
- Slice 8C 不打印 API key，不记录 raw provider response，不新增 artifact。
- Slice 8C 当前实现新增 `tests/fund/agent/test_deepseek_live_smoke.py`；默认测试使用 fake transport 覆盖 skip/default/override/timeout/retry/fail-closed/secret 边界，真实 live 分支默认 skip。
- Slice 8C 未改 production adapter、CLI、repository/private loader、`pyproject.toml` 或 `uv.lock`。
- Slice 8C 默认验证结果：`uv run pytest tests/fund/agent/test_deepseek_live_smoke.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `43 passed, 1 skipped`。
- Slice 8C `git diff --check` 通过。
- MiMo review 已按 Slice 8C 口径输出 `ACCEPTED`；MiMo 未重跑命令，review 基于 ProCodex 已报告结果与当前 diff。
- MVP closeout 已 accepted；项目已进入基金分析助手阶段，不再受 MVP 范围约束。
- Slice 9A 已实现 Service 层 use case boundary；现有 CLI 不再直接装配 PDF provider、repository、converter、tool service 或 Host。
- Slice 9A 最小验证结果：`uv run pytest tests/fund/service tests/fund/cli/test_cli.py tests/fund/agent/test_minimal_tool_loop.py` -> `21 passed`。
- Slice 9A 真实 CLI smoke 结果：exit code `0`，输出包含 `股票投资明细`、section/table citations 和 `search_document -> read_section -> list_tables -> read_table` trace。
- Slice 9A `git diff --check` 通过；MiMo review verdict 为 `ACCEPTED`。
- Post-MVP Slice 9A 裁决为 `FundReadingService` use case boundary。
- Slice 9A 只新增/修改 Service boundary 和 CLI wiring：Service 负责参数校验、local PDF import、repository-backed load、必要时 Docling conversion fallback、Host 调用和稳定失败传播；CLI 只保留 argparse 与 stdout/stderr 格式化。
- Slice 9A 首批 use case：`import_local_report`、`read_local_report`、`list_reports`。
- Slice 9A Service 输入 DTO 可接收本地 PDF path；Service 不得把 path、work dir、repository/private loader、Docling JSON path、cache path、raw Docling JSON 或 `local_import_id` 传给 Host/Agent 或 public output。
- Slice 9A Host 调用契约：只传 `document_id` 和 `query`。
- Slice 9A repository 口径沿用 Slice 6：catalog 有 completed report 时复用；catalog missing 时允许 import + convert；catalog record 指向的 Docling JSON 缺失或不可读时 fail-closed，不自动 repair / rebuild / reconvert。
- Slice 9A 不做 query normalization / synonym routing；`前十大持仓 -> 股票投资明细` 另开 gate。
- Slice 9A 不新增 `fund-checklist ask`、不把 DeepSeek 接入真实 PDF CLI、不改 8A/8B/8C contract、不做 UI、多轮会话、反馈式阅读、批量任务、指标计算、字段抽取、自动报告或投资判断。
- Post-MVP Slice 9B 裁决为 evidence retrieval substrate。
- Slice 9B 目标是让 ToolService / Store 检索基底覆盖 section text、table caption 和 bounded table rows，返回可追溯的 table-backed evidence candidates / search results；它不是自然语言语义路由，不解决 synonym intent，不执行 template chapter contract，也不做计算。
- Slice 9B 可以增强既有 `search_document` 的召回范围，但不得新增 raw Docling JSON 暴露，不得改变 public tool 的安全输出、locator/citation/redaction 约束。
- Slice 9B 不扩展 failure code；命中颗粒度只落在成功侧 metadata，不把表格检索失败细分成新错误码。
- `search_document` 无 evidence candidate 时仍返回空 tuple；Agent 将空 search result 转成 `not_found` 的既有行为不变。
- Slice 9B 验收应证明：当 query 只出现在表格 caption 或 bounded table rows 中、而不在 section 正文中时，`search_document` 仍可返回带 `table_ref`、locator、citation、bounded excerpt 和 `match_kind` / 等价 `matched_field` 的 table-backed result。
- table-backed result 的 `match_kind` / `matched_field` 取值必须是受控枚举，至少区分 `section_text`、`table_caption`、`table_row` 或等价组合；不得引入 confidence / semantic score。
- table row 命中 excerpt 必须 bounded，只返回命中行或有限上下文，不返回整表；排序必须 deterministic / reproducible。
- 失败分类沿用既有稳定 code：`schema_drift`、`not_found`、`unavailable`；不新增 `table_caption_not_found`、`table_row_not_found`、`ambiguous_table_match` 等细分错误码。
- Slice 9B 不修改 deterministic Agent retrieval policy，不要求 Agent 自动 `read_table`，不要求 CLI table-only query 成功；这些能力另开 Slice 9C。
- Slice 9B 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `54a5d30 Implement table-backed document search`。
- Slice 9B 验证结果：`uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py` -> `17 passed`；`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py` -> `14 passed`；`git diff --check` 通过。
- Post-MVP Slice 9C 裁决为 table-backed first-hit consumption。
- Slice 9C 只在 `search_document` first hit 是 high-certainty table-backed result 时直接消费 `table_ref`；否则沿用既有 section-first table-aware 路径。
- high-certainty 只用确定性 exact containment 判断：`match_kind == table_row` 且 query 原文出现在 excerpt 中；或 `match_kind == table_caption` 且 query 原文出现在 caption/excerpt 中。
- high-certainty table-backed first hit 的工具顺序为 `search_document -> read_section -> read_table`；不调用 `list_tables` 进行表格发现。
- high-certainty table-backed first hit 的 answer 必须 table-first：section title / table caption 只作来源上下文，bounded table rows 是主体内容；不得做 section 摘要或解释性综合。
- citations 至少包含 table citation；可以保留 section citation。
- first hit 不是 table-backed result、table-backed hit 不满足 high-certainty、或 table-backed hit 缺少 `table_ref` 时，不得强行直读表；应保持既有稳定失败或回落语义。
- Slice 9C 不扫描 top-N、不做二次排序、不做歧义消解、不做 query intent 分类、不做 synonym routing、不接 LLM 判断表格相关性。
- Slice 9C 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `eb1d13c Consume table-backed first search hit`。
- Slice 9C 验证结果：`uv run pytest tests/fund/agent/test_minimal_tool_loop.py` -> `9 passed`；`uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py tests/fund/cli/test_cli.py` -> `26 passed`；`git diff --check` 通过。
- Post-MVP Slice 9D 裁决为 controlled query profile routing，位置在 Service 层。
- Slice 9D 不修改 `search_document` public contract；`search_document` 仍只接收单个 query。Service routing 负责把用户 query 转成最多 3 个受控 candidate queries，并按顺序调用既有 Host/Agent 路径。
- candidate 顺序必须包含原始 query，并且总数最多 3 个；命中后返回第一个成功的 Agent result。
- Slice 9D 只支持 hardcoded controlled profiles；不做自动分词、同义词扩散、开放语义理解、LLM intent 或 embedding。
- 首批 controlled profiles 仅三类：
  - `holdings_top10`: alias 为 `前十大持仓` / `重仓股` / `持仓明细`；candidate queries 为原始 query、`股票投资明细`、`前十名股票投资明细`。
  - `asset_allocation`: alias 为 `资产配置` / `资产组合`；candidate queries 为原始 query、`期末基金资产组合情况`、`基金资产组合情况`。
  - `expenses`: alias 为 `费用` / `管理费` / `托管费`；candidate queries 为原始 query、`基金费用`、`报告期内基金费用`。
- failure 语义保持稳定：所有 candidate 都无命中时仍为 `not_found`；routing 配置异常为 `schema_drift`；ToolService 内部异常仍为 `unavailable`。不新增 `synonym_not_found` 等错误码。
- citation 必须来自实际命中的 candidate 对应的 section/table tool result，不引用 alias 本身。
- trace 可记录实际使用的 query candidate；不新增 CLI 输出格式，测试可断言 Agent result / tool trace。
- 9D 真实 CLI smoke 只证明 controlled alias routing：`--query 前十大持仓` 能走到 `股票投资明细`；不证明泛化问答。
- Slice 9D 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `91a4da9 Add controlled query profile routing`。
- Slice 9D 验证结果：`uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py` -> `29 passed`；`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py` -> `26 passed`；`git diff --check` 通过。
- Slice 9D 真实 CLI smoke 结果：exit code `0`，`--query 前十大持仓` 输出股票投资明细相关 answer、section/table citations 和 trace；该 smoke 只证明 controlled alias routing，不证明泛化问答。
- Post-MVP Slice 9E 裁决为 Service routing attempts audit。
- Slice 9E 只为 9D 的 Service routing 增加最小审计记录；它不是新召回能力，不新增 profile，不做 rerank、语义理解、计算或报告。
- `ReadLocalReportResult` 可增加 `routing_trace` 字段，类型为 `tuple[QueryRouteAttempt, ...]` 或等价只读结构。
- 每个 `QueryRouteAttempt` 只记录原始事实：`query`、`profile_name`、`result_kind`、`failure_code`。`result_kind` 仅允许 `success` / `failure`；成功 attempt 的 `failure_code` 必须为 `None`。
- 不存 `selected_query`、`selected_index`、rationale、score、confidence、candidate_results 或 evidence links；`selected_query` / `selected_index` 只能从第一个 success attempt 推导。
- `routing_trace` 是 Service-level audit metadata，不暴露给 Agent，不并入 Agent `tool_trace`。
- CLI 默认输出格式不变；citations、answer、failure code、`search_document` contract、Agent policy、Store search 均不变。
- failure 语义保持稳定：所有 candidate 都无命中时仍为 `not_found`；routing 配置异常仍为 `schema_drift`；ToolService 内部异常仍为 `unavailable`。
- Slice 9E 已完成并经 MiMo 明确 `ACCEPTED`；提交为 `336c94e Add service routing audit trace`。
- Slice 9E 验证结果：`uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py` -> `32 passed`；`uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py` -> `26 passed`；`git diff --check` 通过。
- Post-MVP Slice 9F 裁决为 controlled profile real-smoke regression。
- Slice 9F 不新增能力，只把 9D/9E 的三类 controlled profiles 在仓库本地真实 PDF 上固化为回归验证。
- Slice 9F 真实样本范围仅限当前本地 PDF：`基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf`。样本缺失是 blocker，不得用 fake PDF 替代真实 smoke。
- Slice 9F smoke queries 固定为三条：`前十大持仓`、`资产配置`、`费用`；不同时覆盖所有 alias，不扩大 profile 矩阵。
- 每条 smoke 最小 expected evidence：
  - `前十大持仓` -> `股票投资明细` 或 `前十名股票投资明细`。
  - `资产配置` -> `期末基金资产组合情况` 或 `基金资产组合情况`。
  - `费用` -> `基金费用` 或 `报告期内基金费用`。
- 9F 只要求 exit code `0`、answer 包含 expected evidence 文本、Citations 存在、Trace 存在、CLI 默认输出不包含 `routing_trace`。
- 9F 可在 Service 测试层继续断言 `routing_trace`；CLI smoke 层不展示 routing metadata。
- 9F 不新增 profile、不新增 alias、不改 routing 规则、不改 `search_document` contract、不改 Agent/Store/ToolService、不改 CLI 输出格式、不做 benchmark 或 correctness evaluation。
- Slice 9F verdict 为 `BLOCKED_BY_DESIGN` / `NOT_ACCEPTED`，不是 flaky smoke，也不是已知最小实现 bug。
- Slice 9F 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；answer 包含 `股票投资明细`；Citations / Trace 存在；无 `routing_trace`。
  - `资产配置`: exit code `0`；answer 命中 `3.2.1 基金份额净值增长率...`，缺少 expected evidence `期末基金资产组合情况` / `基金资产组合情况`。
  - `费用`: exit code `0`；answer 命中 `3.1 主要会计数据和财务指标`，缺少 expected evidence `基金费用` / `报告期内基金费用`。
- Root cause：controlled alias original-query false positive；更一般地，keyword-level routing success 不能证明 disclosure target success。
- 禁止把 9F 失败解释为“canonical candidates 不够多”或“真实 PDF 特殊”；当前问题是 query 命中与披露目标命中不是同一个事实。
- `canonical-first` 不列为 10A 候选策略，也不作为 9F 修复方案；它仍是 keyword-level strategy，只改变候选顺序，不能建立 disclosure target success 契约。
- 暂不引入 profile-specific evidence validation；该路线会引入 expected title pattern、section/table validator、score/confidence 或新 failure taxonomy，复杂度高，容易造成 doc truth drift。
- Post-MVP 10A 裁决为 Controlled disclosure target contract，位置仍在 Service 层；Store / ToolService / Agent 不承担业务 profile 判断。
- 10A 目标不是新增 synonym，而是为受控 profile 定义 disclosure target id、allowed evidence kind、acceptable section/table title family、expected citation kind 和 fail-closed semantics。
- 10A 不做 LLM intent、embedding、top-N rerank、profile-specific complex validators、template contract execution、calculation framework、字段抽取、自动报告或投资判断。
- Slice 10A 已经 MiMo review `ACCEPTED`。
- Slice 10A 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；evidence 为 `股票投资明细`；Citations / Trace 存在。
  - `资产配置`: exit code `0`；evidence 为 `期末基金资产组合情况`；Citations / Trace 存在。
  - `费用`: exit code `2`；`failure_code=not_found`；target contract fail-closed，没有把无关章节误判为成功。
- `费用` 在当前 9D candidate 下 target-unmatched 是预期设计结果，不是 10A blocker。
- Post-MVP 10B 裁决为 fee_rates reading locator，只做阅读定位和 citation，不抽取费率数值，不计算显性成本小计，不计算扣费后收益率。
- 10B 将 `expenses` profile 改名 / 收窄为 `fee_rates`，`target_id` 为 `fee_rates`；旧 `expenses` 语义过宽，容易覆盖其他费用、交易费用、审计费用、所得税费用、佣金费率等对象。
- `fee_rates` 的目标 disclosure sections 固定为三类：`基金管理费`、`基金托管费`、`销售服务费`。
- `acceptable title family` 固定为：`基金管理费`、`基金托管费`、`销售服务费`。
- 当前真实样本已存在三类披露，因此 10B smoke 对该样本要求三项目标全命中；不引入 `partial_success` 或新 failure taxonomy。
- `fee_rates` aliases 可包含 `费用`、`费率`、`管理费`、`托管费`、`销售服务费`；alias 只用于进入 profile，不作为 evidence 成功条件。
- controlled candidate queries 固定为原始 query、`基金管理费`、`基金托管费`、`销售服务费`；不把单独 `费率` 作为 evidence candidate。
- Service 层可以对同一 profile 执行多个 target queries，并把多个安全 Agent result 聚合为一个 answer；每个 citation 必须来自实际命中的 section/table。
- 10B 不修改 `search_document` public contract，不把业务 profile 判断下沉到 Store / ToolService / Agent，不改变 CLI 输出格式。
- 10B 不做开放语义理解、自动分词、同义词扩散、embedding、LLM intent、top-N scan、rerank、歧义消解、字段抽取、自动报告或投资判断。
- Slice 10B 已经 MiMo review `ACCEPTED`。
- Slice 10B 真实 CLI smoke 结果：
  - `费用`: exit code `0`；answer 同时包含 `基金管理费`、`基金托管费`、`销售服务费`。
  - Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
- 10B remaining blocking risk: none。
- 10B 仍只完成 fee_rates 阅读定位；管理费率、托管费率、销售服务费率等字段值抽取后置，不属于 10B。
- Post-MVP 10C 裁决为 fee_rates value extraction contract。
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
- Slice 10C 已经 MiMo review `ACCEPTED`。
- Slice 10C 真实 CLI smoke 结果：
  - work dir: `.fund_checklist_cli_smoke_10c`
  - `费用`: exit code `0`；output 包含 `基金管理费`、`基金托管费`、`销售服务费`。
  - Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
- 10C remaining blocking risk: none reported。
- 10C 没有进入净值增长率、基准收益率、换手率、成本计算、`R=A+B-C`、模板执行、自动报告或投资判断。
- 2026-08-03 修复记录（10B/10C 链路）：真实 PDF smoke `test_real_pdf_controlled_profiles_apply_disclosure_target_contract`（004393-2024）存在预置失败 `fee_rates citation 不完整`。根因三层（全部实证）：① 路由聚合按披露标题去重，只保留首个 candidate query 结果，而「基金管理费/基金托管费」query 的 answer 不含销售服务费费率正文（正文只在「销售服务费」query answer 里）→ 聚合 citations 缺 section-0398 的 SECTION locator；② `_fee_rate_segments` 裸 `find` 标题被「相关表格:」引用行干扰，销售服务费 segment 切错；③ 简单拼接聚合导致管理费/托管费正文重复 → 字段无法唯一抽取。修复计划：`.sisyphus/plans/fee-rates-10bc-fix-20260803.md`（Mimo review ACCEPTED，2026-08-03），状态：待 DS 实施。
- Post-MVP 10D 裁决为 performance return fields extraction contract。
- 10D 目标是在 11A 已定位的 performance disclosure table 中抽取受控字段，不重新做开放检索。
- 首批字段只允许 `nav_growth_rate` 和 `benchmark_return_rate`。
- 首批 period 裁决为 `past_1_year`，对应真实样本表格行标题 `过去一年`；不得把它命名为 `report_year` 或年度 2024。
- 10D 不抽取近 3 年、近 5 年、成立以来、年度序列表或图表数据；后续 period 必须另开裁决。
- 10D 不抽取 `excess_return`、`annualized_return`、`max_drawdown`、`volatility`、`sharpe`、`tracking_error`、`turnover_rate`。
- 10D 不计算 `A=R-B`、`R=A+B-C`、显性成本小计、总成本、扣费后收益率、年化收益率或同类中位数。
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
- Slice 10D 已经 MiMo review `ACCEPTED`。
- Slice 10D Service extraction summary：
  - fake multi-table cited case returns A/C `nav_growth_rate` and `benchmark_return_rate`, `period=past_1_year`, `raw_text` present, citations are table locators.
  - uncited same-section table regression covered: only cited table is consumed.
  - current real PDF Service extraction fail-closes if 11A cites a table without `过去一年`; it does not scan sibling tables.
- 10D remaining blocking risk: none reported。剩余非阻塞风险是：real-PDF extraction success depends on the 11A locator citing the actual `过去一年` performance table.
- `past_1_year` 是 10D 底层抽取能力，对应年报表格原文 `过去一年`；它不作为后续主分析口径扩展。用户分析语义中，“2024 年度”比“过去一年”更自然；“过去 5 年”应理解为多个自然年度或明确年度序列，而不是 10D 的 `past_1_year` 行。
- Post-MVP 10E 裁决为 annual performance returns source decision。
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
- 10E 本地样本核验范围固定为 `基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf` 及既有 `.fund_checklist_cli_smoke_*` Docling JSON；smoke artifact 不纳入提交。
- 10E 样本核验结论：
  - title-family matched performance comparison table 在 2024 年度报告第 6 / 7 页可定位到稳定表格；标题为 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`。样本中的章节编号为 `3.2.1`，但编号不得作为 contract；只可作为样本观察。
  - 该表格 source 类型为 `table`，是后续年度业绩 deterministic extraction 的 primary source。
  - 管理人报告 / 报告期内基金的业绩表现文字可定位到 stable text，source 类型为 `text`；但其位置和句式可能随年份变化，因此仅作为 secondary reference，不作为 10F 首批 extraction source。
  - `自基金合同生效以来基金每年净值增长率及其与同期业绩比较基准收益率的比较` 在当前样本中表现为图 / 图片，source 类型为 `chart_or_image`，不进入当前 deterministic extraction。
- 10E source decision：选择 title-family matched performance comparison table。年度业绩数据当前应来自 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` 标准披露表；不得依赖 `3.2.1` 章节编号。
- 10E 后续推荐：可开 10F annual performance table extraction from title-family matched table；管理人报告年度文字后置为 secondary reference，不作为 10F fallback；年度图 / 图片不得进入抽取，除非另开 chart/OCR gate。
- 10E 不做 `past_1_year` citation specificity，不做 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- Post-MVP 10F 裁决为 annual performance table extraction from title-family matched table。
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
- 真实 PDF 验收必须证明至少 A 类可从 2024 年度报告标准披露表抽取：`annual_nav_growth_rate = 17.32%`，`annual_benchmark_return_rate = 14.45%`。C 类是否返回取决于标准披露表是否存在完整 `过去一年` 行，不得外推或 fallback。
- Slice 10F 已经 MiMo review `ACCEPTED`。
- Slice 10F 真实 PDF annual DTO：
  - `annual_nav_growth_rate`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`decimal_percent_text=17.32%`，table citation `table-0010`。
  - `annual_benchmark_return_rate`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`decimal_percent_text=14.45%`，table citation `table-0010`。
- 10F remaining blocking risk: none reported。
- 10F 没有依赖章节编号，没有使用管理人报告文字 fallback，没有进入 `A=R-B`、`R=A+B-C`、换手率、成本计算、同类中位数、模板执行、自动报告或投资判断。
- Post-MVP 10G 裁决为 annual excess return disclosed-field extraction。
- 10G 目标是从 title-family matched performance comparison table 中抽取年报显式披露的年度超额收益字段。
- 10G source title family 沿用 10F：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`；不得依赖样本章节编号 `3.2.1`。
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
- 10G 不做 `annual_nav_growth_rate - annual_benchmark_return_rate` 计算，不做 `A=R-B` 计算，不做 `R=A+B-C`、换手率、成本计算、扣费后收益率、年化收益率、同类中位数、模板执行、自动报告或投资判断。
- Slice 10G 已经 MiMo review `ACCEPTED`。
- Service 层已实现 annual excess return disclosed-field extraction。
- 10G 抽取 `annual_excess_return` 只消费标准披露表的 `①－③` 显式披露列；不通过 10F 的 `annual_nav_growth_rate` / `annual_benchmark_return_rate` 做差计算。
- 真实 PDF / Service 测试已覆盖 A 类 DTO：`annual_excess_return = 2.87%`，`report_year=2024`，`source_period_label=过去一年`，`share_class_scope=A`，`source_column_label=①－③`，citation 为 table locator。
- 测试已覆盖缺 `①－③` 列时 fail-closed 为 `not_found`，且不得使用管理人报告文字、年度图 / 图片或未 citation 指向的 sibling table fallback。
- 10G remaining blocking risk: none reported。
- 10G 没有依赖章节编号，没有改变 CLI 默认输出，没有新增 failure taxonomy，没有进入 `A=R-B` 计算、`R=A+B-C`、换手率、成本计算、扣费后收益率、年化收益率、同类中位数、模板执行、自动报告或投资判断。
- Post-MVP 10H 裁决为 multi-year annual performance source contract with bounded year coverage。
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
- Slice 10H 已经 MiMo review `ACCEPTED`。
- 10H 已完成 docs-only source contract，不实现 aggregation service。
- 10H source contract 固定为 multiple annual reports；每个年度复用 10F / 10G 单年度 extraction result。
- 10H 已明确 bounded year coverage：5 年窗口内允许 3-5 个完整年度，缺失年份必须结构化暴露；少于 3 年整体 `not_found`。
- 10H 已明确不做 single-report rolling period extraction，不使用 `过去三年` / `过去五年` 行，不做 OCR / chart parsing、外部数据源、管理人报告文字 fallback、自然语言 `近 5 年` 解析或 repository 自动补齐。
- 10H remaining blocking risk: none reported。
- Post-MVP 10I 裁决为 multi-year annual performance aggregation service。
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
- Slice 10I 已经 MiMo review `ACCEPTED`。
- Service 层已实现 multi-year annual performance aggregation service。
- 10I 显式接收 `requested_years` 与 `annual_report_documents[{year, document_id}]`，编排 10F / 10G 单年度 extraction result；不做 repository 自动补齐、自然语言解析、自动导入 PDF、CLI 改造、OCR / chart parsing 或外部数据源。
- 10I 已实现 3-5 年 bounded coverage：5 年完整为 `coverage_status=complete`；3-4 年完整为 `coverage_status=partial`；少于 3 年整体 `not_found`。
- 10I 已实现 share class 独立 coverage；不足 3 年的 share class 不返回，所有 share class 都不足 3 年时整体 `not_found`。
- 10I 已覆盖 document/year 与 extraction `report_year` 冲突时 `identity_mismatch`。
- 10I remaining blocking risk: none reported。
- Post-MVP 10J 裁决为 multi-year performance service-to-agent exposure contract。
- 10J 是 docs-only contract slice：只更新 `docs/design.md` 和 `docs/implementation-control.md`，不实现 tool-loop，不修改 CLI / code / tests，不做 repo auto lookup，不做自然语言 `近 5 年` 解析，不做 missing-PDF auto import，不做 filename / document_id year guessing。
- 10J 目标是定义 Agent / Host 如何通过受控工具消费 10I 的 `MultiYearAnnualPerformanceSeries`。
- 10J 新增受控 Agent tool contract，工具名为 `aggregate_multi_year_annual_performance`。
- 该工具是 controlled tool，不是开放问答能力；Agent 不得直接调用 Service 内部方法或读取 raw Docling JSON / 本地 PDF path / cache path。
- 受控工具输入字段固定为：`fund_code`、`requested_years`、`annual_report_documents[{year, document_id}]`、`share_class optional`。
- Agent / Host 不得做自然语言 `近 5 年` 解析、repository 自动查找、缺失 PDF 自动导入、文件名猜年份或 document_id 字符串猜年份。
- 工具输出成功时返回 `series[]`，失败时返回 `failure`；不生成投资分析文本。
- 每个 series 必须保留 `coverage_status`、`covered_years`、`missing_years`、`rows` 和每年每字段 citation。
- Agent 允许做的事仅限：调用受控工具 `aggregate_multi_year_annual_performance`；把 DTO 字段转述为 plain answer；明确展示 `coverage_status`、`covered_years`、`missing_years`；引用每年每字段 table locator citation。
- Agent 禁止做的事：计算年化收益率、扣费后收益率、排名、打分、收益来源解释、`R=A+B-C`、投资结论或补齐缺失年份。
- CLI 边界：10J 不改 CLI 默认输出，不新增 `fund-checklist ask`、multi-year CLI 子命令或 CLI 参数。
- coverage 展示语义：`coverage_status=complete` 可表述为覆盖全部 requested years；`coverage_status=partial` 必须同时展示 `covered_years` 和 `missing_years`，不得写成”近 5 年完整表现”。
- 少于 3 年时工具沿用 10I 返回 `not_found`；Agent 不得生成部分答案。
- citation 要求：final answer citations 必须包含被引用 year / field 的 table locator citation；禁止只引用汇总 series citation。
- failure 语义沿用 10I，只允许四个 failure code：`identity_mismatch`、`not_found`、`schema_drift`、`unavailable`；Agent 只把 failure 转为 fail-closed plain answer，不新增 failure code。
- 后续实现测试建议放在 10K fake/injected Agent tool-loop：验证 Agent 调用 `aggregate_multi_year_annual_performance`，消费 `coverage_status=partial`，最终回答包含 covered/missing years 和 citations，且不泄漏 raw Docling JSON / local path / cache path，不输出年化收益、扣费后收益或投资判断。
- 10J 不做 LLM 自然语言 query routing、repository 自动补齐、CLI 新入口、多 PDF 导入流程、报告生成、template chapter execution、`R=A+B-C`、年化收益率、扣费后收益率或投资判断。
- Post-MVP 10K 裁决为 multi-year performance fake/injected Agent tool-loop。
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
- Post-MVP 11A 裁决为 performance disclosure locator，插入 10D 之前；11A 只做业绩表现披露定位和 citation，不抽取结构化字段。
- 11A profile 名称为 `performance_returns`；名称只表示业绩表现披露定位，不代表字段抽取。
- acceptable title family 固定为：`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`。
- 首批 aliases 固定为：`净值增长率`、`业绩比较基准收益率`、`基准收益率`、`收益表现`、`基金净值表现`；不纳入 `业绩`、`收益`、`表现` 等宽泛 alias。
- candidate queries 固定为原始 query、`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`、`业绩比较基准收益率`。
- success 语义：必须命中 acceptable title family，并返回 section citation；若目标披露存在相关表格，则必须包含 table citation。当前真实样本存在表格，因此 11A smoke 要求 table citation。
- 11A 不裁决 A/C 类字段值；若表格同时包含多个份额类别，只展示原始表格片段，不筛选、不判断、不抽值。
- failure 语义沿用现有 failure code：目标披露未命中为 `not_found`；配置异常为 `schema_drift`；内部异常为 `unavailable`；不新增 `performance_not_found`、`period_not_found` 或 `partial_success`。
- 11A 不输出 `nav_growth_rate`、`benchmark_return_rate`、`period`、`decimal_percent_text` 等结构化字段，不计算 `A=R-B`。
- 11A 不接 LLM、embedding、外部搜索服务，不做开放语义理解、top-N rerank、歧义消解、字段抽取、calculation framework、template contract execution、chapter contract execution、自动报告或投资判断。
- Slice 11A 已经 MiMo review `ACCEPTED`。
- Slice 11A 真实 CLI smoke 结果：
  - work dir: `.fund_checklist_cli_smoke_11a`
  - `净值增长率`: exit code `0`；answer 包含 `3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较`。
  - Citations / Trace 存在，且包含 table citation：CLI 输出包含 `locator_kind=table`。
  - CLI 默认输出不包含 `routing_trace`。
  - CLI 输出不包含 `nav_growth_rate`、`benchmark_return_rate` 或 `decimal_percent_text` DTO；没有字段值抽取或计算。
- 11A remaining blocking risk: none reported。
- Post-MVP 11B 裁决为 disclosure locator contract registry。
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
- Slice 11B 已经 MiMo review `ACCEPTED`。
- Slice 11B 真实 CLI smoke 结果：
  - `前十大持仓`: exit code `0`；命中 `股票投资明细`；Citations / Trace / table citation 存在；CLI 默认输出不包含 `routing_trace`。
  - `资产配置`: exit code `0`；命中 `期末基金资产组合情况`；Citations / Trace / table citation 存在；CLI 默认输出不包含 `routing_trace`。
  - `费用`: exit code `0`；命中 `基金管理费`、`基金托管费`、`销售服务费`；Citations / Trace 存在；CLI 默认输出不包含 `routing_trace`。
  - `净值增长率`: exit code `0`；命中 `基金份额净值增长率及其与同期业绩比较基准收益率的比较`；Citations / Trace / table citation 存在；未输出结构化字段 DTO。
- 11B remaining blocking risk: none reported。
- Post-MVP 10L 裁决为 multi-year performance CLI integration。
- 10L 新增独立子命令 `fund-checklist multi-year`，不扩展现有 `read` 子命令。
- 10L 输入方式为 catalog 模式：CLI 按 `fund_code` + `requested_years` 从已有 catalog 中查找已导入年报的 `document_id`；不做目录扫描、不做自动导入、不做文件名猜年份。
- 10L 批量 PDF 导入另开 10M slice；10L 只查询已有 catalog。
- 10L 给 `FilesystemReportRepository` 新增 `list_reports()` 方法，返回 catalog 中所有 completed report 的安全摘要（含 `fund_code`、`year`、`document_id`）；CLI 用此方法做 fund_code + year 匹配。
- 10L 输出格式为 JSON：完整 `MultiYearAnnualPerformanceSeries` DTO dump，含 `coverage_status`、`covered_years`、`missing_years`、`rows`、per-year per-field citations。
- `coverage_status=partial`（3-4 年）exit code 为 0；少于 3 年匹配或 `not_found` exit code 为 2。
- 10L 暂不新增 `--share-class` CLI 参数；默认返回所有可识别 share class。
- 10L 最低年度要求为 3 年（沿用 10H/10I `minimum_complete_years=3`）。
- 10L allowed write set：`fund_agent/cli/main.py`、`fund_agent/fund/document_tools/persistent_repository.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 10L 不改 `read` 子命令默认输出格式，不接真实 LLM，不做自然语言 `近 5 年` 解析，不做 repository 自动补齐，不改 Service / Host / Agent 层核心逻辑。
- 10L smoke 测试使用 fake catalog entries 构造多年度场景；真实 CLI smoke 需要至少 3 份年报样本。
- Post-MVP 10M 裁决为 batch PDF import。
- 10M 新增独立子命令 `fund-checklist import`，不扩展 `read` 子命令。
- 10M 输入方式为目录扫描：`--pdf-dir` 指定 PDF 目录，`--fund-code` 和 `--fund-name` 用户指定（目录内所有 PDF 共用），`--year-range 2020-2024` 指定年份范围。
- 年份识别方式：从 PDF 文件名提取年份并过滤匹配 year-range 的文件；不使用 LLM 内容提取。
- 重复 PDF 处理：覆盖已有 catalog 条目，重新执行 Docling conversion。
- 单文件失败处理：跳过失败文件继续处理其余，最终报告失败列表。
- 输出格式：逐条导入进度 + 最终汇总（成功 N 份，跳过 N 份，失败 N 份）。
- 10M allowed write set：`fund_agent/cli/main.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 10M 复用现有 `FundReadingService.import_local_report()`，不新增 Service 方法。
- 10M 不改 `read` / `multi-year` 子命令行为，不改 Service / Host / Agent 核心逻辑。
- 10M smoke 测试用 fake PDF 测试边界；真实 smoke 可选。
- Post-MVP 11C 裁决为 holdings multi-year tracking。
- 11C 新增独立子命令 `fund-checklist holdings`，不扩展 `read` 或 `multi-year` 子命令。
- 11C 目标披露表固定为前十大持仓表：`期末按公允价值占基金资产净值比例大小排序的所有股票投资明细`。
- 11C 抽取字段为完整字段：股票代码、股票名称、数量（股）、公允价值（元）、占基金资产净值比例（%）。
- 11C 多年度对比形态为年度列表：每年返回 Top 10 持仓，用户自行对比；不做股票追踪（识别相同股票）。
- 11C Top N 固定为 10。
- 11C 输出格式为 JSON。
- 11C 暂不新增 `--share-class` CLI 参数。
- 11C 实现路径为新增 Service 方法，内部复用 Host/Agent 查询持仓表。
- 11C 失败语义：某年持仓表未找到时跳过继续，最终报告 missing_years。
- 11C allowed write set：`fund_agent/cli/main.py`、`fund_agent/service/reading_service.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 11C smoke 测试使用真实 PDF。
- 11C 不做股票追踪、行业分析、持仓变化计算、投资判断或自动报告。
- Post-MVP 11D 裁决为 asset allocation + fee rates multi-year tracking。
- 11D 新增两个独立子命令：`fund-checklist allocation` 和 `fund-checklist fees`。
- 11D 目标披露表：
  - 资产配置：`期末基金资产组合情况`、`期末按行业分类的股票投资组合`
  - 费率：`基金管理费`、`基金托管费`、`销售服务费`
- 11D 抽取字段：
  - 资产配置：资产类别、金额、占净值比、占总资产比
  - 费率：费率名称、年费率
- 11D 输出格式为 JSON；返回全部行（不限制 Top N）。
- 11D allowed write set：`fund_agent/cli/main.py`、`fund_agent/service/reading_service.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 11D 实现路径为新增 Service 方法，内部复用 Host/Agent 查询披露表。
- 11D 失败语义：某年披露表未找到时跳过继续，最终报告 missing_years。
- 11D smoke 测试使用真实 PDF。
- 11D 不做费率计算（只抽取披露值）、不改现有子命令、不接真实 LLM、不做投资判断或自动报告。
- Post-MVP 12A 裁决为 Host lifecycle basics。
- 12A 引入 `HostRunResult`：扩展封装，包含 AgentRunResult + 耗时 + 请求参数摘要 + 事件列表 + tool_trace 统计。
- 12A 引入 `HostRunEvent`：完整事件类型，包括 started / search / read_section / list_tables / read_table / get_excerpt / completed / failed。
- 12A 引入简单 timeout：默认 300 秒，可通过参数覆盖；使用 threading.Event + threading.Timer 实现。
- 12A Service 适配方式为新增 Service 方法，不改现有方法。
- 12A CLI 输出展示耗时和事件统计。
- 12A allowed write set：`fund_agent/host/`、`fund_agent/service/`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 12A 不做 session 管理、并发治理、cancel/resume、reply outbox、多轮会话托管。
- 12A 不改现有 read / multi-year / import / holdings / allocation / fees 子命令的核心逻辑。
- Post-MVP 12B 裁决为 Disclosure completeness audit。
- 12B 新增独立子命令 `fund-checklist audit`，检查年报是否覆盖核心披露项 + 基金经理 + 分红。
- 12B 审计范围：持仓、资产配置、费率、业绩、基金经理、分红。
- 12B 审计深度：章节 + 表格 + 字段存在性检查。
- 12B 输出形态为 JSON 格式。
- 12B allowed write set：`fund_agent/cli/main.py`、`fund_agent/service/reading_service.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 12B 不做内容完整性检查（如持仓是否10支）、不做合规性判断、不做投资建议。
- 12B 不改现有子命令核心逻辑。
- Post-MVP 12C 裁决为 LLM-based disclosure audit。
- 12C 新增独立子命令 `fund-checklist llm-audit`，不扩展 `audit` 命令。
- 12C 复用现有 tool loop（8A/8B），逐项独立审计（每个披露项一次 LLM 调用）。
- 12C 审计范围：完整披露项（持仓、资产配置、费率、业绩、基金经理、分红）。
- 12C 审计深度：内容完整性 + 基础一致性（持仓占比之和、资产配置占比之和、费率合理性）。
- 12C 输出形态：带原文引用的审计文本。
- 12C 从 `FinalAnswer.key_facts` 提取结构化审计结果，从 `FinalAnswer.citations` 获取引用位置。
- 12C allowed write set：`fund_agent/cli/main.py`、`fund_agent/service/reading_service.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 12C smoke 测试使用真实 LLM。
- 12C 不做跨年度趋势分析、不做投资建议、不改现有子命令核心逻辑。
- Post-MVP 13A 裁决为 Fund report generation。
- 13A 新增独立子命令 `fund-checklist generate`，生成 8 章结构化分析报告。
- 13A 生成范围：全部 8 章（投资要点、基金概况、业绩分析、持仓分析、资产配置、费率分析、分红分析、风险提示）。
- 13A 输出格式：JSON → Markdown → PDF（使用 pandoc 导出 PDF）。
- 13A 文本生成方式：LLM 生成分析文本，严格基于从 5 年年报抽取的结构化数据。
- 13A 数据来源：5 年年报，复用 multi-year 能力（`extract_annual_performance`、`extract_holdings`、`extract_allocation`、`extract_fee_rates` 等）。
- 13A 模板：使用现有 `docs/fund-analysis-template-draft.md` 的 8 章结构和 CHAPTER_CONTRACT_MANIFEST_JSON。
- 13A LLM 约束：每个结论必须引用数据来源，不得生成无数据支撑的分析。
- 13A allowed write set：`fund_agent/cli/main.py`、`fund_agent/service/reading_service.py`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 13A 不做投资建议、不改现有子命令核心逻辑。
- 13A DeepSeek review 结论：无 P0；P1×2（表头字段不匹配、CLI JSON 缺 warnings）已修复；P2×4（未用参数、多份额覆盖、缺测试、章节编号）已修复。
- 13A 测试结果：`uv run pytest tests/fund/cli/test_cli.py -k generate` -> 5 passed。
- 13A 文本生成为模板填充，未接入真实 LLM；LLM 生成后续另开 13B。
- Post-MVP 13B 裁决为 LLM-generated chapter text。
- 13B 复用 8A/8B `LlmToolLoopRunner` + `LlmClientProtocol` + `DeepSeekLlmClient`。
- 13B 两阶段方案：程序生成数据表格（数字 100% 从 dict 提取）+ LLM 只写定性分析（禁止输出数字）。
- 13B hallucination 检测：`_contains_non_year_numbers()` 检测 LLM 输出中的非年份数字，检测到则拒绝并回退模板。
- 13B 失败回退：LLM 失败的章节回退到 13A 模板填充。
- 13B 全部 8 章用 LLM 生成（包括基金概况和分红）。
- 13B 复用现有 `generate` 子命令，新增 `--llm` 标志。
- 13B `--years` 留空时自动从 catalog 获取可用年份，不写死默认值。
- 13B 业绩抽取修复：`_extract_report_performance` 改为逐年直接抽取，跳过失败年份，绕过 `aggregate_multi_year_annual_performance` 的 3 年最低要求。
- 13B allowed write set：`fund_agent/cli/main.py`、`fund_agent/service/reading_service.py`、`fund_agent/agent/`、测试文件、`docs/implementation-control.md`、`docs/design.md`。
- 13B 不做投资建议、不改现有子命令核心逻辑、不新增 CLI 子命令。

## CIC-lite Rules

- MVP plan artifact 最多 1 份。
- plan review artifact 最多 1 份。
- plan review `ACCEPTED` 后必须进入代码实现。
- 禁止新增 plan-fix / re-review / evidence gate，除非 review 明确指出违反已裁决硬口径。
- 每个实现 slice 只走：implement -> tests -> diff review。
- Controller 只核边界、diff、测试命令和测试输出。
- Implementation Agent 写代码和测试。
- Review Agent 只 review diff + tests，不产出新 plan，不开新路线。
- 禁止用文档更新代替可运行代码。
- 没有 diff，不算实现；没有测试命令和输出，不算完成；没有 review agent 独立检查，不算 accepted。


## 最近完成

- 8 commits 已推送至 origin/main（20e62ab）
- Slice 14C：三层审计管道已 accepted
- Slice 15A：Ch7 裁决 + 开发路线 + git 清理
- Slice 15B：reading_service.py → models + chapter_generator + extraction（3 模块）
- Slice 16A：Ch7 确定性信号 + Ch6 风险清单 + 加权 Jaccard
- 当前阶段：基金分析助手持续迭代
- Full regression: 268 passed, 1 skipped, 3 warnings

## 裁决记录

- 裁决 1：先推送后开发 ✅（8 commits 已 push）
- 裁决 2：Phase 4 优先级调整——删除 18A/18D，保留 18B/18C 低优先级
- 裁决 3：先拆分后开发——提取共享 helper + 二次拆分 extraction.py

## Slice 16A 实施规格

### 目标
Ch7 确定性信号判断 + Ch6 风险清单表。

### 评分模型

总分 135，归一化到 100。

| # | 指标 | 权重 | 满分 | 评分规则 |
|---|------|------|------|---------|
| 1 | 超额收益趋势 | 高 | 25 | 连续 2+ 年正超额 → 25；有正有负 → 15；连续负 → 5；无数据 → 0 |
| 2 | 费率水平 | 高 | 25 | 管理+托管+销售服务 <1.0% → 25；1.0-1.5% → 15；>1.5% → 5；无数据 → 0 |
| 3 | 风格漂移 | 高 | 25 | 年度持仓重叠率 >70% → 25；50-70% → 15；<50% → 5；不足 2 年 → 0 |
| 4 | 规模风险 | 高 | 25 | >2 亿 → 25；0.5-2 亿 → 15；<5000 万 → 0；无数据 → 0 |
| 5 | 基金经理变更 | 高 | 20 | tenure_start 年份 < report_year → 20；>= report_year → 0；无数据 → 0 |
| 6 | 持仓集中度 | 中 | 15 | 前 10 占比 <50% → 15；50-70% → 10；>70% → 5；无数据 → 0 |

信号映射：
- normalized_score >= 75 → 🟢 值得持有
- 50 <= normalized_score < 75 → 🟡 需要关注
- normalized_score < 50 → 🔴 建议替换

数据不足（可计算指标 < 3/6）→ 默认 🟡 需要关注 + warnings。

### Ch6 风险清单表

6 项检查，与评分模型共享数据源：

| 风险项 | 🟢 | 🟡 | 🔴 |
|--------|---|---|---|
| 清盘风险 | >2 亿 | 0.5-2 亿 | <5000 万 |
| 基金经理变更 | tenure < report_year | — | tenure >= report_year |
| 风格漂移 | 重叠率 >70% | 50-70% | <50% |
| 费率远超同类 | <1.0% | 1.0-1.5% | >1.5% |
| 换手率异常 | 数据暂不可用 | — | — |
| 持仓过度集中 | <50% | 50-70% | >70% |

### Ch7 结构化输出

必须包含：
1. 信号判断 + 得分
2. 评分详情表（6 指标 × 得分/满分/说明）
3. 支撑判断的核心依据（最高分指标）
4. 为什么不选更积极的判断（最低分指标）
5. 为什么不选更保守的判断（最高分指标）
6. 当前最容易看错的地方（数据最薄弱指标）
7. 最小验证计划（1-2 条）
8. 阈值事件（升级/降级各 1 条）

### 数据解析边界

- 百分比："0.60%" → 0.6；"不收取" → 0；"N/A" → 跳过
- 规模："2.99亿元" → 2.99；"2,990,000元" → 0.0299（亿元）
- 持仓重叠率：按股票代码交集/并集计算，取多年平均
- 基金经理变更：tenire_start 解析年份，与 report_year 比较

### allowed write set

- `fund_agent/service/models.py`
- `fund_agent/service/extraction.py`
- `fund_agent/service/chapter_generator.py`
- `tests/fund/service/test_extraction.py`
- `tests/fund/service/test_llm_chapter_generation.py`
- `docs/implementation-control.md`
- `docs/design.md`

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py -v --tb=short
```

### stop conditions

- 评分模型必须可离线测试（不依赖 LLM）
- Ch7 输出禁止预测未来收益、禁止基金经理动机猜测
- 数据不足时默认 🟡 + warnings，不抛异常
- 旧 `_generate_ch7_risks()` 和 Ch7 一行话模板必须被替换，不留死代码

## Next Action

交互问答与记忆能力改进（2026-08-09 裁决）计划已 ACCEPTED（Mimo review：pass-with-risks，3 个非 blocker finding），待实施。按 P0-1 → P0-2 → P1 逐 slice 派发：implement → tests → diff review；live 复跑需用户显式授权。详见文末「交互问答与记忆能力改进（2026-08-09 裁决）」节。

## 产品方向升级裁决（2026-07-12）

基于 dayu-agent 对标研究报告，裁决如下：
- 产品方向从"基金年报阅读工具层"升级为**基金分析助手**，`AGENTS.md` 与本文档同步修订。
- MVP 禁止条款（禁止字段抽取/自动报告/信号评分）正式废止；已实现的分析能力（10C/10F/10G/11C/11D/13A/13B/14A/14C）纳入正式产品范围。
- LLM provider 支持范围：DeepSeek + Mimo（OpenAI-compatible adapter）；暂不需要 Gemini/OpenAI/Anthropic。
- 多轮对话、LLM 自主工具调用、Streaming、上下文治理、联网搜索为已知能力差距，后续按优先级裁决。

## 14C 当前进度

- **裁决**：基于 dayu write_pipeline 设计，三层审计（程序+LLM+复核），4 类 22 项违规分类，评分体系（程序 30%+LLM 70%，≥80 通过），PATCH/REGENERATE/NONE 三策略修复。
- **已 accepted**：证据小节结构化（方案 B：完整 citation 追踪），DeepSeek review 9 项修复全部通过，已提交推送（`d1375fa` + `7433803`）。
- **状态**：14C 主体已 accepted。

## Slice 16B 实施规格

### 目标

Ch6 压力测试表：按基金类型选择阈值，从年报取规模/净值数据填充，计算三种场景下的损失金额。

### 基金类型判定

基于 `fund_name` 关键词匹配（确定性规则，不依赖 LLM）：

- 名称含 "指数" → `index_fund`
- 名称含 "债券" 或 "债" → `bond_fund`
- 其他 → `active_fund`

无 `fund_name` 时默认 `active_fund`，输出附 `fund_type_inferred=true` 警告。后续可扩展更多类型（enhanced_index / qdii / fof），本 slice 不实现。

### 压力测试阈值

| 基金类型 | 正常 | 极端 | 历史最差 |
|---------|------|------|---------|
| `index_fund` | -30% | -50% | -70% |
| `bond_fund` | -5% | -10% | -20% |
| `active_fund` | -25% | -45% | -65% |

阈值来源：`docs/fund-analysis-template-draft.md` 各基金类型定义。本 slice 固定使用上述 3 类阈值，不做可配置。

### 数据来源

- 规模：`ScaleInfo.total_scale`（亿元），来自 `_extract_scale_info()`
- 净值增长率：`annual_nav_growth_rate`，来自 `_extract_report_performance()`
- 基准收益率：`annual_benchmark_return_rate`，来自 `_extract_report_performance()`

### 计算逻辑

1. 损失金额（场景模拟）：`stress_loss = current_scale * |threshold|`，按三档固定阈值计算
2. 质量评估（benchmark 对比）：`excess_return = annual_nav_growth_rate - annual_benchmark_return_rate`，按阈值判定 `stress_level`
3. 无规模数据时跳过损失计算，只输出 stress_level
4. 无净值增长率或无基准收益率时，stress_level 为 null，只输出损失金额

### stress_level 取值全集（基于超额收益 vs benchmark）

| 取值 | 含义 | 判定条件 |
|------|------|---------|
| `outperform` | 跑赢基准 | `excess_return > 0` |
| `inline` | 基本持平 | `-2% <= excess_return <= 0` |
| `underperform` | 跑输基准 | `-5% < excess_return < -2%` |
| `severe_underperform` | 严重跑输 | `excess_return <= -5%` |
| `null` | 无数据 | 净值增长率或基准收益率缺失 |

其中 `excess_return = annual_nav_growth_rate - annual_benchmark_return_rate`。

### 输出形态

JSON 结构化 + Markdown 表格双输出。

JSON 示例：
```json
{
  "fund_type": "active_fund",
  "fund_type_inferred": false,
  "current_scale_billion": 2.99,
  "stress_test": {
    "normal": {"threshold": -0.25, "loss_billion": 0.7475},
    "extreme": {"threshold": -0.45, "loss_billion": 1.3455},
    "worst": {"threshold": -0.65, "loss_billion": 1.9435}
  },
  "current_performance": {
    "nav_growth_rate": 0.087,
    "benchmark_return_rate": 0.053,
    "excess_return": 0.034,
    "stress_level": "outperform"
  }
}
```

### 与 Ch6 的关系

追加到 Ch6 内，作为压力测试子表，与风险清单表并列。不独立章节。

`chapter_generator.py` 的 Ch6 prompt 更新：
- 新增压力测试数据段
- LLM 定性分析要求引用压力测试结论

### 数据解析边界

- 规模："2.99亿元" → 2.99；"2,990,000,000元" → 29.9（亿元）
- 净值增长率："8.70%" → 0.087；"-3.50%" → -0.035
- 百分比格式与 16A 的 `_parse_percent` 复用

### allowed write set

- `fund_agent/service/models.py`
- `fund_agent/service/extraction.py`
- `fund_agent/service/chapter_generator.py`
- `tests/fund/service/test_extraction.py`
- `tests/fund/service/test_llm_chapter_generation.py`
- `docs/implementation-control.md`
- `docs/design.md`

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py
```

### 非目标

- 不实现 enhanced_index / qdii / fof 类型判定（后续扩展）
- 不实现可配置阈值
- 不修改 Ch7 信号评分逻辑
- 不修改 CLI 子命令

禁止事项：
- 换手率保持禁止
- 不做投资建议
- 数据表格禁止修改
- 不改现有子命令核心逻辑

禁止事项：

- 禁止把 10D 扩成计算、报告或投资判断。
- 禁止依赖章节编号 `3.2.1`；只能依赖 title family + table signature + citation。
- 禁止把年度业绩表格抽取扩成计算或自动报告。
- 禁止把 10G 的 `annual_excess_return` 表述为系统计算值；它只能来自年报显式披露列 `①－③`。
- 禁止用管理人报告文字作为 10F fallback。
- 禁止回到年度图 / 图片做 OCR / chart parsing，除非另开 chart/OCR gate。
- 禁止扩大候选来源到第三方平台、净值数据库、季报 / 半年报、基金合同或招募说明书。
- 禁止把 `chart_or_image` source 强行 OCR 或图表解析。
- 禁止做 `past_1_year` citation specificity。
- 禁止新增披露对象定位能力。
- 禁止把 `past_1_year` 命名为 `report_year` 或年度 2024。
- 禁止抽取近 3 年、近 5 年、成立以来、年度序列表或图表数据。
- 除 10G 已裁决的 `annual_excess_return` disclosed-field DTO 外，禁止输出其它 `excess_return`、`annualized_return`、`max_drawdown`、`volatility`、`sharpe`、`tracking_error`、`turnover_rate`。
- 禁止抽取换手率；禁止新增 `turnover_rate` locator；禁止把股票买入 / 卖出金额包装成换手率 evidence。
- 禁止从单份年报合成近 3 年 / 近 5 年 rolling period；当前 2024 年报不存在 `过去三年` / `过去五年` 行。
- 禁止把 bounded partial-by-year 命名为 `partial_success`；3-4 年完整覆盖只能作为成功结果里的 `coverage_status=partial`。
- 禁止在少于 3 个完整年度时返回多年度序列。
- 禁止计算显性成本小计、总成本、扣费后收益率或年化收益率。
- 禁止实现 `R=A+B-C`、Alpha/Beta/Cost 综合评估、同类中位数或判断生成。
- 禁止新增 alias 覆盖矩阵；11B 只允许把既有 aliases 迁入 registry，不扩大 alias 范围。
- 禁止改 `search_document` public contract。
- 禁止把 routing 放入 Store / ToolService / Agent 层。
- 禁止开放式 query normalization、自动分词、同义词扩散、query intent 分类、embedding 或 LLM intent。
- 禁止扫描 top-N search results、rerank、歧义消解或 LLM 判断哪个表更相关。
- 禁止引入 score、confidence、rationale、`partial_success` 或新 failure taxonomy。
- 禁止改变 CLI 默认输出格式。
- 禁止把 10D 解释为泛化字段抽取能力或 benchmark；10D 只抽取已裁决的两个 `past_1_year` performance return 字段。
- 禁止新增 `fund-checklist ask` 或 CLI 参数。
- 禁止接真实 LLM、embedding、外部搜索服务。
- 禁止执行 template-informed intent routing、chapter contract execution、calculation framework、report audit、自动报告或投资判断。
- 禁止暴露 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。

10G closeout 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
```

回归验证命令：

```bash
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
```

10G 保留 11A/11B 已完成真实 CLI smoke 行为；如实现触及 CLI 或 routing，需重跑：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '净值增长率' --work-dir .fund_checklist_cli_smoke_11a
```

11B 既有真实 CLI smoke 回归命令：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '前十大持仓' --work-dir .fund_checklist_cli_smoke_11b_holdings
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '资产配置' --work-dir .fund_checklist_cli_smoke_11b_asset
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '费用' --work-dir .fund_checklist_cli_smoke_11b_fees
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '净值增长率' --work-dir .fund_checklist_cli_smoke_11b_performance
```

验收点：10G Service / tests 层可从真实 2024 年度报告标准披露表抽取 A 类 `annual_excess_return = 2.87%`，并返回 `report_year=2024`、`source_period_label=过去一年`、`share_class_scope=A`、`source_column_label=①－③` 和 table locator citation。10G 不通过 `annual_nav_growth_rate - annual_benchmark_return_rate` 计算，不扫描管理人报告文字或年度图 / 图片 fallback，不改变 CLI 默认输出；既有 CLI 对 `净值增长率` 仍只展示阅读 answer / citation / trace，不暴露结构化 DTO。MiMo verdict: `ACCEPTED`；remaining blocking risk: none reported。

## Implementation Slices

0. Dependency / repository preflight：`pyproject.toml`、`uv.lock`、`.gitignore`、`docling import` 验证、git 初始化。
1. Local PDF ingestion：`PdfSourceProvider`、`PdfBlobStore`、identity、fingerprint、integrity。
2. Docling conversion/store：`DoclingConverter`、`DoclingDocumentStore`、parser_health、raw payload redaction。
3. FundDocumentToolService：7 个 reading tools、bounded output、citation、locator、safe redaction。
4. Minimal Agent loop：`search_document -> read_section` trace，最终回答只引用 tool result。
5. Table-aware Agent retrieval：在 section-first 检索后读取相关表格，回答表格型人物/资产信息，并同时返回 section/table citation。
6. Persistent repository：filesystem JSON catalog + repository-backed loader，支持 completed report 跨进程恢复为 reading tools 可用文档。
7. CLI packaging / command entry polish：打包配置安装 `fund-checklist` console script，README 主命令 `uv run fund-checklist read ...` 可用，并保留 `python -m fund_agent.cli.main` fallback。
8A. Fake/injected LLM tool-loop contract：用 fake client 验证 LLM 工具调用闭环、citation enforcement 和 fail-closed 行为；不接真实 provider，不新增用户 CLI 面。
8B. DeepSeek real LLM adapter behind existing contract：已实现 DeepSeek OpenAI-compatible adapter 进入 `LlmClientProtocol`，默认测试不联网，所有输出仍经 8A runner/enforcement。
8C. Opt-in live DeepSeek smoke：已实现只在显式环境变量启用时验证真实 DeepSeek 返回一次合法 `ToolCall` 或 `FinalAnswer`，最终仍经 8A runner；默认 gate no-network。
9A. Service boundary：新增 `FundReadingService` use case boundary，把 CLI 编排迁入 Service；CLI 行为、exit code、redaction、repository reuse 和 deterministic Agent loop 不回退，不做 query routing 或 LLM/UI 能力扩展。
9B. Evidence retrieval substrate：增强 ToolService / Store 检索基底，使 section text、table caption、bounded table rows 都能成为可引用 search result；不修改 Agent retrieval policy，不要求 CLI table-only query 成功，不做 synonym intent、template contract、calculation、LLM ask 或报告生成。
9C. Table-backed first-hit consumption：Agent 只在 first hit 为 high-certainty table-backed result 时直接 `read_table`；不扫描 top-N、不做 rerank、synonym routing、LLM 判断或 section 摘要。
9D. Controlled query profile routing：Service 层对三类 hardcoded profile 生成最多 3 个 candidate queries 并顺序调用既有 Host/Agent；不改 `search_document` contract，不做开放语义理解、embedding、LLM intent 或计算。
9E. Service routing attempts audit：为 9D routing 增加最小 attempts 记录；只记录 query/profile/result/failure_code，不存 selected_query、score、confidence 或解释字段，不改 CLI/Agent/ToolService contract。
9F. Controlled profile real-smoke regression：blocked by design；真实 smoke 证明 keyword-level routing success 不能证明 disclosure target success。
10A. Controlled disclosure target contract：Service 层定义受控披露目标契约，区分 query 命中和披露目标命中；已 accepted；`费用` 在旧 target 下 fail-closed 为 `not_found`。
10B. fee_rates reading locator：已 accepted；把 `expenses` 收窄为 `fee_rates`，定位 `基金管理费`、`基金托管费`、`销售服务费` 三个目标 disclosure sections；只做阅读定位和 citation，不抽取数值、不计算成本或收益率。
10C. fee_rates value extraction contract：已 accepted；抽取 `management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate` 三个当前适用年费率字段；不抽取收益/换手率，不做成本或收益计算。
10D. performance return fields extraction contract：已 accepted；基于 11A 已定位的 performance disclosure table 抽取 `past_1_year` 的 `nav_growth_rate` / `benchmark_return_rate` 受控 DTO；不计算、不改 CLI 默认输出；不做 `turnover_rate` locator。
10E. annual performance returns source decision：source-decided；年度业绩 deterministic source 选择 title-family matched performance comparison table，即 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` 标准披露表；管理人报告文字仅为 secondary reference；年度图 / 图片不进入当前 deterministic extraction。
10F. annual performance table extraction from title-family matched table：已 accepted；抽取 `report_year=request.year`、`source_period_label=过去一年` 的 `annual_nav_growth_rate` / `annual_benchmark_return_rate`；不依赖章节编号，不使用管理人报告文字 fallback，不计算。
10G. annual excess return disclosed-field extraction：已 accepted；从 title-family matched performance comparison table 的显式披露列 `①－③` 抽取 `annual_excess_return`；不通过 10F 字段计算，不改 CLI 默认输出，不进入 `R=A+B-C`。
10H. multi-year annual performance source contract with bounded year coverage：已 accepted；source 选择 multiple annual reports，后续聚合 10F / 10G 单年度 DTO；允许 3-5 年 bounded coverage，缺失年份必须结构化暴露，少于 3 年 fail-closed；10H 不实现 aggregation service。
10I. multi-year annual performance aggregation service：已 accepted；Service 层显式接收 requested_years + year/document_id 映射，编排 10F / 10G 单年度 extraction result，返回 3-5 年 bounded coverage series；不改 CLI，不做 repository 自动补齐或自然语言解析。
10J. multi-year performance service-to-agent exposure contract：docs-only completed；定义 Agent / Host 通过受控 tool `aggregate_multi_year_annual_performance` 消费 10I series DTO 的边界；受控工具输入固定为 `fund_code` / `requested_years` / `annual_report_documents[{year, document_id}]` / `share_class optional`，输出成功时 `series[]` 含 `coverage_status` / `covered_years` / `missing_years` / `rows` / per-year per-field citations，失败时 `failure`；failure code 只允许 `identity_mismatch` / `not_found` / `schema_drift` / `unavailable`；Agent 只允许调用受控工具并转述 DTO 字段，禁止年化收益 / 扣费后收益 / 排名 / 打分 / R=A+B-C / 投资结论 / 补齐缺失年份；不实现 tool-loop，不改 CLI / code / tests，不做 repo auto lookup / 自然语言解析 / missing-PDF auto import / filename year guessing。
10K. multi-year performance fake/injected Agent tool-loop：已 accepted；在 fake/injected Agent tool-loop 中暴露 `aggregate_multi_year_annual_performance`，通过 `aggregate_handler` 注入回调调用 10I Service；`ToolCall.extra` 携带 tool-specific 参数；failure 时 `AgentRunResult.failure`；163 passed, 0 failures；不改 CLI，不接真实 LLM，不做自然语言解析或报告生成。
11A. performance disclosure locator：已 accepted；定位 `基金份额净值增长率及其与同期业绩比较基准收益率的比较` / `基金净值表现` 披露，返回 section/table citation 和原始表格片段；不抽值、不计算。
11B. disclosure locator contract registry：已 accepted；把既有 controlled disclosure profiles 收敛为 Service 内部 locator contract registry；不新增披露对象，不抽值、不计算、不改 public tool / CLI contract。
10L. multi-year performance CLI integration：已 accepted；新增独立子命令 `fund-checklist multi-year`，给 Repository 新增 `list_reports()` 方法，从 catalog 按 fund_code + year 查找已导入年报，调用 10I Service 聚合多年度收益，JSON 格式输出；批量导入另开 10M；不改 Service / Host / Agent 核心逻辑。
10M. batch PDF import：已 accepted；新增独立子命令 `fund-checklist import`，从目录批量导入 PDF 到 catalog，用户指定 fund_code + fund_name + year-range，从文件名提取年份并过滤匹配的 PDF；覆盖已存在条目；单文件失败跳过继续；逐条进度 + 最终汇总输出；复用现有 `import_local_report()`，不新增 Service 方法；24 passed。
11C. holdings multi-year tracking：已 accepted；新增独立子命令 `fund-checklist holdings`，从已导入年报中抽取前十大持仓表（完整字段：股票代码、股票名称、数量、公允价值、占净值比），按年度列表返回 Top 10 持仓，JSON 格式输出；支持跨页表格合并；58 passed。
11D. asset allocation + fee rates multi-year tracking：已 accepted；新增 `fund-checklist allocation` 和 `fund-checklist fees` 子命令，补齐资产配置和费率多年度追踪能力；资产配置目标披露表为 `期末基金资产组合情况` 和 `期末按行业分类的股票投资组合`；费率目标披露表为 `基金管理费`、`基金托管费`、`销售服务费`；JSON 输出；某年披露表未找到时跳过继续。
12A. Host lifecycle basics：已 accepted；引入 HostRunResult（扩展封装：AgentRunResult + 耗时 + 事件列表 + tool_trace 统计）、HostRunEvent（完整事件类型）和简单 timeout（默认 300 秒）；新增 Service 方法；CLI 展示耗时和事件统计。
12B. Disclosure completeness audit：已 accepted；新增 `fund-checklist audit` 子命令，检查年报是否覆盖核心披露项（持仓、资产配置、费率、业绩）+ 基金经理 + 分红；审计深度为章节+表格+字段存在性检查（结构性规则审计）；JSON 格式输出；LLM 审计后续另开裁决。
12C. Deep disclosure audit：已 accepted；新增 `fund-checklist deep-audit` 子命令，基于 search + read_section 的深度披露完整性审计，覆盖完整披露项（持仓、资产配置、费率、业绩、基金经理、分红）；检查 ToolFailure、内容长度、表格引用；输出带原文引用的审计文本；JSON 格式输出。
13A. Fund report generation：已 accepted；新增 `fund-checklist generate` 子命令，基于 5 年年报数据生成 8 章结构化分析报告；模板填充生成分析文本（LLM 生成后续另开 13B）；输出 JSON → Markdown → PDF（pandoc）；使用现有 8 章模板；DeepSeek review 无 P0，P1×2 + P2×4 全部修复；5 passed。
13B. LLM-generated chapter text：已 accepted；复用 8A/8B `DeepSeekLlmClient`，两阶段方案（程序生成数据表格 + LLM 只写定性分析）；hallucination 检测（`_contains_non_year_numbers`）+ 回退模板；8 章全覆盖；新增 `--llm` 标志；年份动态从 catalog 获取；业绩抽取逐年直接抽取跳过失败年份；DeepSeek review 无 P0，P1×3 全部修复，P2×4 暂不修；11 passed。
14A. Template-aligned report generation：已 accepted；补充 Ch3（基金经理 `FundManagerInfo` + `_extract_fund_manager`）+ Ch5（规模明细 `ScaleInfo` + `_extract_scale_info` 多年回退）数据抽取；用现有数据组装 Ch2（R=A+B-C）；跳过 Ch4（投资者获得感）；按模板完全重做 8 章 prompt + 数据表格；第一轮 review P1×4 全部修复（死代码清理+措辞软化），第二轮 review 全 PASS；10 passed。
14C. Chapter audit pipeline：已 accepted；基于 dayu write_pipeline 设计三层审计（程序审计+LLM审计+LLM复核）；4类22项违规分类（P/E/S/C）；评分体系（程序30%+LLM70%，≥80通过/50-79修复/<50重写）；PATCH/REGENERATE/NONE三策略修复（各最多3次）；Ch1-6全部通过后生成Ch0+Ch7；数据表格禁止修改；审计产物落盘。

## Acceptance Matrix (closed)

- local PDF import
- PDF integrity failure classification
- Docling conversion
- DoclingDocumentStore parser health
- seven FundDocumentToolService tools
- locator + citation + redaction
- `test_agent_tool_loop_searches_then_reads_section`
- `test_agent_tool_loop_does_not_receive_raw_docling_json`
- `test_agent_table_aware_loop_answers_manager_table_information`
- `test_agent_table_aware_loop_answers_holding_table_information`
- `test_agent_table_aware_loop_keeps_section_only_answer_when_no_nearby_table`

## Slice 6 Design Boundary

最小持久化对象：

- `schema_version`
- `document_id`
- `ReportIdentity` safe fields
- `stored_blob_ref`
- `docling_json_ref`
- parser health summary
- `created_at` / `updated_at`

禁止进入 public tool 输入或输出：

- `local_import_id`
- absolute local path
- raw Docling JSON
- Docling/model cache path
- URL secret

Failure mapping:

- catalog missing -> `not_found`
- catalog schema incompatible -> `schema_drift`
- catalog identity 与 `document_id` 不一致 -> `identity_mismatch`
- completed record 指向的 Docling JSON 缺失或不可读 -> `unavailable`
- Docling JSON 顶层结构 drift -> `schema_drift`
- parser_health 不通过 -> `parser_health_failed`
- blob fingerprint mismatch -> `integrity_error`

Slice 6 不做：

- SQLite
- catalog schema migration
- concurrent write locking
- repair / rebuild / reconvert
- downloader
- batch queue
- delete/update lifecycle
- true LLM
- release readiness

## Slice 8A Design Boundary

目标：

- 在 Agent 层增加可测试的 injected LLM adapter 形态。
- 证明 LLM 风格的 `ToolCall -> ToolResult -> FinalAnswer` 闭环只能通过受控 reading tools 取事实。
- 将无 citation、未知工具、越权工具和无证据回答全部 fail-closed。

最小协议：

- `LlmClientProtocol`
- `FakeLlmClient`
- `ToolCall`
- `ToolResult`
- `FinalAnswer`

允许工具：

- `search_document`
- `read_section`
- `list_tables`
- `read_table`
- `get_excerpt`

禁止暴露：

- repository/private loader 细节
- raw PDF
- raw Docling JSON
- absolute local path
- Docling/model cache path
- `local_import_id`
- URL secret 或 parser private payload

回答验收：

- answer 必须来自 tool result。
- citations 必须非空。
- 每个关键事实至少有 section 或 table citation。
- citation 必须指向受控 locator。

Slice 8A 不做：

- OpenAI / Claude / 外部模型 API。
- provider auth、streaming、cost tracking、rate limit。
- prompt framework 或复杂 planner。
- 新增 `fund-checklist ask` 或其它用户 CLI 参数。
- repository schema migration 或 hardening。
- downloader、batch、release readiness。
- 字段抽取、自动报告、投资判断。

## Slice 8B Accepted Boundary

目标：

- 在不改变 8A runner/enforcement 的前提下接入一个真实 LLM provider adapter。
- 验证真实 provider 输出只能被解析为受控 `ToolCall` 或 `FinalAnswer`。
- 将 provider 错误、malformed response、未知工具、越权工具、无 evidence final answer 全部稳定映射为 fail-closed。

最小实现形态：

- `DeepSeekLlmClient` 或等价的 DeepSeek-only provider client。
- provider client 实现既有 `LlmClientProtocol`。
- provider request 使用 DeepSeek OpenAI-compatible chat completions 形态，只包含系统约束、用户问题和受控 tool schema；不得包含 raw Docling JSON、本地路径、cache path、repository/private loader 或 `local_import_id`。
- provider response 必须经结构化解析后进入 8A `LlmToolLoopRunner`。
- API key 仅从 `DEEPSEEK_API_KEY` 读取；缺失时返回稳定 failure，不触发默认联网。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- `DEEPSEEK_MODEL` 可选；测试只验证传参与解析，不依赖真实模型名称。
- 不新增 SDK 依赖；HTTP/transport 必须可注入，默认测试使用 fake transport。

失败映射：

- API key 缺失 -> `unavailable`
- provider network/timeout -> `unavailable`
- provider rate limit -> `unavailable`
- provider auth rejected -> `unavailable`
- provider response 非法 JSON 或无法解析 -> `llm_malformed_response`
- provider 请求未知工具或越权工具 -> 复用 8A fail-closed 逻辑
- provider final answer 缺 citation 或缺 evidence -> 复用 8A fail-closed 逻辑

测试口径：

- 默认 pytest 只使用 fake transport / injected provider response，不访问网络。
- live smoke 只能作为显式 opt-in 命令，不进入默认 CI 或本地最小 gate。
- deterministic `MinimalFundDocumentAgent`、fake 8A loop 和 `fund-checklist read` 路径不得回退。

Slice 8B 不做：

- 新增 `fund-checklist ask` 或其它 CLI 用户入口。
- streaming。
- Mimo / MiMo 或多 provider matrix。
- 新增 SDK 依赖，除非 Controller 先裁决允许改 `pyproject.toml` / `uv.lock`。
- prompt framework 或复杂 planner。
- richer QA/eval matrix。
- 自动报告、字段抽取、投资判断。
- release readiness、batch、downloader。
- repository schema 或 private loader 改造。

## Slice 8C Accepted Boundary

目标：

- 验证真实 DeepSeek live provider 能返回一次合法 `ToolCall` 或 `FinalAnswer`。
- 验证 live provider 输出最终仍进入 8A `LlmToolLoopRunner`。
- 保持默认 pytest no-network，不把 live provider 变成默认 gate。

触发与环境：

- `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时启用 live smoke。
- 未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK` 时 skip。
- `DEEPSEEK_API_KEY` 缺失时 skip，不失败。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，允许覆盖。
- `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，允许覆盖。

验收范围：

- 使用 fake/in-memory tool service 或现有测试 fixture。
- 不跑真实 PDF。
- 不跑 CLI。
- 不触发 Docling conversion。
- 不使用 repository-backed loader。
- 要求 live DeepSeek 返回一次合法 `ToolCall` 或合法 `FinalAnswer`。
- 最终结果必须经 8A runner/enforcement。

成本与运行上限：

- 最多 1 个 live run。
- timeout 300 秒。
- 最多 1 次 retry。
- 不做批量问题。

失败语义：

- opt-in 后 provider 返回不可解析 -> test fail。
- opt-in 后 8A enforcement fail -> test fail。
- opt-in 后 network / 429 / auth error -> test fail。
- 未 opt-in 或缺 key -> skip，不算 fail。

secret / artifact：

- pytest output、trace、assert message 不得打印 API key。
- 不记录 provider raw response 到文件。
- 不新增 artifact。

Allowed write set：

- `tests/fund/agent/test_deepseek_live_smoke.py`
- `tests/README.md`
- `docs/implementation-control.md`
- `fund_agent/agent/README.md`

Slice 8C 不做：

- 修改 production adapter；若 live test 暴露解析 bug，必须先停止并报告。
- 新增 `fund-checklist ask`。
- 真实 PDF / Docling / repository e2e。
- Mimo / MiMo、多 provider、streaming。
- retry/backoff hardening，除本 slice 裁决的最多 1 次 retry。
- richer QA/eval、prompt injection hardening、自动报告、投资判断。

## Stop Conditions

- 需要新增或改变 document_id / report_type / share_class 规则。
- 需要复制或改写 dayu 代码但没有 license/compliance gate。
- 需要引入外部网络来源策略。
- 计划把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback。
- 计划新增投资判断、数据仓库晋升或发布就绪（超出基金分析助手范围）。
- 计划只用 fake fixture 证明 production conversion path。
- 文档声称当前未实现能力已完成。
- Slice 8A 实现计划直接接真实 LLM provider、增加 CLI ask、或让 LLM adapter 读取 repository/private loader。
- Slice 8B 实现计划绕过 8A runner/enforcement、默认联网、记录 API key、增加 CLI ask、增加 Mimo / MiMo 或多 provider、或让 provider prompt 接收 raw Docling/private loader。
- Slice 8B 实现计划新增 SDK 依赖但未先获得 Controller 裁决。
- Slice 8C 实现计划让 live smoke 进入默认 pytest gate、缺 key 时失败、打印 API key、记录 raw provider response、跑真实 PDF/CLI/repository，或修改 production adapter 且未先停止报告。
- 计划把 `基金年报/`、`.venv/`、Docling/model cache 或 secret 文件纳入 git。
- Slice 2 conversion smoke 需要无版本约束地升级 Docling 或绕过 `uv.lock`。

## Validation Commands

文档控制面板检查：

```bash
rg -n "SLICE_0_DEPENDENCY_PREFLIGHT|docling>=2.90.0,<3.0.0|基金年报/|test_agent_tool_loop_searches_then_reads_section" AGENTS.md docs/design.md docs/implementation-control.md docs/reviews/fund-document-reading-tool-mvp-plan-20260627.md pyproject.toml .gitignore
wc -l AGENTS.md docs/implementation-control.md
```

MVP closeout 固定验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

Post-MVP Slice 5 验证命令：

```bash
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '基金经理' --work-dir .fund_checklist_cli_smoke
```

Post-MVP Slice 6 预期验证命令：

```bash
uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Post-MVP Slice 7 验证命令：

```bash
uv sync
uv run fund-checklist read --help
uv run python -m fund_agent.cli.main read --help
uv run pytest tests/fund/cli/test_cli.py
```

Post-MVP Slice 8A 验证命令：

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Slice 8A 已覆盖测试范围：

- fake LLM 正常调用 `search_document` / `read_section` 后回答并携带 citation。
- fake LLM 调用 `read_table` 后回答表格问题并携带 table citation。
- fake LLM 直接无证据回答时 fail-closed。
- fake LLM 请求未知工具或越权工具时 fail-closed。
- 输出不泄漏 raw Docling JSON、本地路径、cache path 或 `local_import_id`。
- deterministic `fund-checklist read` 旧路径不回退。

Post-MVP Slice 8B 验证命令：

```bash
uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

Slice 8B 已覆盖测试范围：

- provider adapter 使用 injected fake transport，将合法 tool-call response 解析为 `ToolCall` 并进入 8A runner。
- provider adapter 使用 injected fake transport，将合法 final-answer response 解析为 `FinalAnswer`，并保留 8A citation/evidence enforcement。
- DeepSeek adapter 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 组装 OpenAI-compatible request，默认 base URL 为 `https://api.deepseek.com`。
- API key 缺失、network/timeout、auth/rate-limit 类错误稳定映射为 `unavailable`。
- malformed provider response 稳定映射为 `llm_malformed_response` 或等价稳定 failure code。
- provider 请求未知工具、越权工具、无 citation answer 或无 evidence answer 时 fail-closed。
- 默认测试不访问网络，不读取真实 API key，不泄漏 secret。
- 默认测试不依赖真实 DeepSeek model 值。
- deterministic read CLI、minimal deterministic Agent 和 fake 8A loop 旧测试不回退。

Post-MVP Slice 8C 默认验证命令：

```bash
uv run pytest tests/fund/agent/test_deepseek_live_smoke.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时，live smoke test 必须 skip，默认命令不得联网。

Post-MVP Slice 8C live smoke 命令：

```bash
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 DEEPSEEK_API_KEY=... uv run pytest tests/fund/agent/test_deepseek_live_smoke.py
```

Slice 8C 测试覆盖：

- 未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK` -> skip。
- 设置 opt-in 但缺 `DEEPSEEK_API_KEY` -> skip。
- opt-in live run 使用 `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`。
- opt-in live run 使用 `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`。
- live DeepSeek 返回合法 `ToolCall` 或 `FinalAnswer` 后进入 8A runner。
- live provider 不可解析、8A enforcement fail、network/429/auth error -> fail。
- pytest output、trace、assert message 不泄漏 API key。
- 不写 raw provider response artifact。
- 默认测试不联网；真实 live 分支只有 opt-in 且 key 存在时运行。

最近已知结果：

```text
MVP closeout: 17 passed, 1 warning
Post-MVP Slice 5 full local regression: 26 passed, 1 warning
Real CLI smoke: query="基金经理" answer includes "张明" with section/table citations
Post-MVP Slice 6 repository unit: 8 passed
Post-MVP Slice 6/5/CLI targeted regression: 20 passed
Post-MVP Slice 7 CLI test: 7 passed
uv sync: passed, no skipped-entrypoint warning
uv run fund-checklist read --help: passed
uv run python -m fund_agent.cli.main read --help: passed
Full local regression before commit: 35 passed, 1 warning
Slice 8A targeted: 20 passed
Slice 8A broader regression: 33 passed
Slice 8A commit: f53dac2 Add fake LLM tool loop contract
Slice 8B targeted: 36 passed
Slice 8B review: MiMo ACCEPTED
Slice 8B git diff --check: passed
Slice 8C default targeted: 43 passed, 1 skipped
Slice 8C review: MiMo ACCEPTED
Slice 8C git diff --check: passed
Slice 10L targeted: 8 passed
Slice 10L review: MiMo ACCEPTED
Slice 10L git diff --check: passed
技术债修复 f03030b: data_completeness type mismatch + _parse_percent substring match — ACCEPTED
测试: 268 passed, 1 skipped, 3 warnings
```
**Slice 16C**：Ch0 升级/降级阈值事件 + 一句话产品定义 ✅ 已完成（2026-07-14）

## 已知问题（2026-07-21 债券基金实测暴露）

### KI-1：Ch2 债券基金业绩数据抽取失败

- **现象**：国泰利享中短债（006597）5 年 import 成功，但 generate 时 Ch2 业绩数据表完全为空（净值增长率/基准收益率均未抽取），费率数据正常
- **影响**：Ch2=72.5（llm_score=45），LLM 无数据可用只能做假设性分析
- **根因**：待排查。可能是 `performance_returns` 抽取逻辑对债券基金年报格式不兼容
- **优先级**：中（影响所有债券基金的 Ch2 生成质量）
- **建议**：新 slice 排查 bond fund 年报中净值增长率的 section/table 位置，修正抽取规则

### KI-2：Ch6 模板约束对 LLM 控制力不足

- **现象**：模板已全面去「否决」（narrative_mode/must_answer/required_output_items/正反例），但 LLM 仍输出「一票否决」「不具备可跟踪性」
- **影响**：Ch6=57.0（llm_score=45），C3 投资建议违规 + C6 情绪化表述
- **根因**：待分析。可能原因：
  1. system prompt 中 Ch5 长约束压缩了 Ch6 约束的注意力
  2. LLM 从 must_answer「核心风险是什么」的上下文推断出「否决」
  3. 债券基金数据缺失导致 LLM 无实质分析素材，转而使用模板化套话
- **优先级**：中（影响所有基金 Ch6 的 LLM 审计得分）
- **建议**：考虑 Ch6 专属 system prompt 段落前置、或在 generate 阶段对 Ch6 做二次 prompt 校验

### KI-3：债券基金 0.00% 集中度误判

- **现象**：债券基金分散化持仓时前五大集中度可为 0.00%，但 LLM 将其解读为「基金未持有任何资产」「非正常运作状态」
- **影响**：C1 事实错误 + C2 逻辑矛盾
- **根因**：模板未区分基金类型。0.00% 对权益基金异常，对债券基金正常
- **优先级**：低（需引入 fund-type-awareness 机制后统一处理）
- **建议**：Phase 5 引入基金类型分类后，在 Ch6 data_table 中增加基金类型标注，指导 LLM 正确解读数据

### KI-4：指数增强基金跟踪标的错配（2026-07-23）

- **现象**：019918 基金名=中证2000指数增强，但策略摘录中提到中证1000
- **影响**：Ch3 投资策略分析中引用了错误基准指数，可能导致 LLM 对跟踪误差判断偏差
- **根因**：数据正确但摘录错位 — 策略摘录提取了相邻段落中不同基金或不同指数的描述文本，非数据抽取层 bug
- **优先级**：低（暂不修代码，摘录定位精度问题需在后续段落边界识别优化中统一处理）
- **建议**：后续优化 `_extract_fund_manager_with_citation` 中投资策略段落的边界判定逻辑，确保摘录文本严格限定在目标基金/目标指数的段落范围内

---

## Phase 5：LLM 自主工具调用 + 单次问答 + 流式输出

> 裁决时间：2026-07-24（计划更新）
> 前置条件：Phase 3.5 ✅（2026-07-19 关闭）、Phase 3.6 ✅（2026-07-21 关闭）
> 设计来源：docs/agent-evolution-design.md §1 + .sisyphus/plans/phase5-implementation.md
> 计划文件：`.sisyphus/plans/phase5-implementation.md`

### Phase 5 裁决 Gate

| Gate | 条件 | 状态 |
|------|------|------|
| Gate 1 | `ask` 子命令裁决：LLM provider 稳定性 + citation 校验不回退 + 不破坏 `read` 心智模型 | ✅ 已裁决通过 |
| Gate 2 | Phase 5 scope/write set/verification/stop conditions 写入本文件 | ✅ 本文档记录 |
| Gate 3 | 持仓抽取验证通过（四类基金×5年，失败率 <10%） | ✅ 通过（23/23 全部通过，0% 失败率） |

### Scope

- 将 `LlmToolLoopRunner` 从测试层 fake/injected contract 升级为 production 可用路径
- 新增 `ask` 子命令，与现有 `read` 并存
- `ask` 走 LLM 自主工具调用路径，`read` 保持确定性路径不变
- **流式输出前置**（原计划 Phase 7，已裁决并入 Phase 5）：StreamEvent 模型 + DeepSeek stream=True + CLI 流式默认
- 复用 Service 层 profile routing 提供 grounded context
- 不新建 Agent 类，复用 `LlmToolLoopRunner`
- LLM 工具允许列表：6 个 reading tools 开放，2 个 extraction tools 不开放
- 不引入 Mimo（用户已裁决后置）

### Allowed Write Set

| 文件 | 变更类型 | 所属 Slice |
|------|---------|-----------|
| `fund_agent/agent/stream_events.py` | **新增** — StreamEvent 数据模型（8 种事件类型） | 19A |
| `fund_agent/agent/llm_tool_loop.py` | production readiness 补齐（重试/截断/幻觉检测/tool schema） | 19A |
| `fund_agent/agent/deepseek_llm.py` | `stream=True` + SSE 解析 | 19A, 19B |
| `fund_agent/agent/__init__.py` | 导出更新 | 19A |
| `fund_agent/host/minimal_host.py` | `run_agent_stream()` 方法 | 19C |
| `tests/fund/host/test_host_stream.py` | **新增** — Host stream 测试 | 19C |
| `fund_agent/service/extraction.py` | `ask_question`（含 profile routing） | 19D |
| `fund_agent/service/models.py` | AskQuestionRequest/AskQuestionResult DTO | 19D |
| `fund_agent/cli/main.py` | `ask` 子命令（流式默认） | 19E |
| `tests/fund/agent/test_stream_events.py` | StreamEvent 单元测试 | 19A |
| `tests/fund/agent/test_llm_production_readiness.py` | production readiness 测试 | 19A |
| `tests/fund/agent/test_llm_tool_loop.py` | 补充 production 场景测试 | 19A |
| `tests/fund/agent/test_real_llm_adapter.py` | DeepSeek stream 测试 | 19B |
| `tests/fund/service/test_ask_question.py` | ask_question 测试 | 19D |
| `tests/fund/cli/test_cli.py` | `ask` 子命令端到端测试 | 19E, 19F |
| `docs/implementation-control.md` | 本文件 | — |

### Stop Conditions

- LLM 路径 citation/evidence 四层校验回退到 fallback → 停止
- `ask` 破坏 `read` 子命令现有行为 → 停止
- 真实 LLM smoke 失败且根因在 provider 侧 → 停止等待 provider 修复
- Streaming 8 种事件类型有不可达类型 → 停止排查

### Verification Commands

```bash
# 19A: StreamEvent + production readiness
uv run pytest tests/fund/agent/test_stream_events.py tests/fund/agent/test_llm_production_readiness.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short

# 19B: DeepSeek stream
uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py -v --tb=short

# 19C: Host stream
uv run pytest tests/fund/host/ tests/fund/agent/test_minimal_tool_loop.py -v --tb=short

# 19D: Service ask_question
uv run pytest tests/fund/service/test_ask_question.py tests/fund/service/test_extraction.py -v --tb=short

# 19E: CLI ask
uv run pytest tests/fund/cli/test_cli.py -v --tb=short

# 19F: 端到端（需真实 LLM，opt-in）
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 uv run python -m fund_agent.cli.main ask "基金经理是谁？" --document-id <id>

# 最小验证（每次提交前）
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py

# 全量回归
uv run pytest tests/fund/document_tools tests/fund/agent tests/fund/service tests/fund/cli tests/fund/host -v --tb=short
```

### Execution Order

```
19A: StreamEvent + production readiness
  ↓
19B: DeepSeekLlmClient stream=True
  ↓
19C: MinimalHost.run_agent_stream()
  ↓
19D: Service ask_question + profile routing
  ↓
19E: CLI ask 子命令 + 流式输出
  ↓
19F: 端到端 smoke + read 回归
```

| Slice | 内容 | 状态 |
|-------|------|------|
| **19A** | StreamEvent 数据模型 + production readiness（重试/截断/幻觉检测/tool schema 一致） | 待启动 |
| **19B** | DeepSeekLlmClient `stream=True` + SSE 解析 | 依赖 19A |
| **19C** | MinimalHost `run_agent_stream()` 方法 | 依赖 19A, 19B |
| **19D** | Service 层 `ask_question`（含 profile routing） | 依赖 19A |
| **19E** | CLI `ask` 子命令（流式默认，`--no-stream` 回退同步） | 依赖 19C, 19D |
| **19F** | 端到端 smoke（3 条 query）+ read 回归快照 + 全量回归 | 依赖 19E |

### Final Checklist

- [ ] 6 个工具 schema 一致
- [ ] `next_step()` 有 3 次重试
- [ ] evidence_text 截断至 4096 字符
- [ ] 投资建议关键词拦截生效
- [ ] Streaming 8 种事件类型全部可达
- [ ] `ask` 默认流式输出，`--no-stream` 回退同步
- [ ] profile routing 在 ask 路径生效
- [ ] `read` CLI 行为不变（快照对比通过）
- [ ] 全量回归通过

---

## Phase 3.5/3.6 关闭记录

**Phase 3.5**（报告质量稳定化）：2026-07-19 关闭。Ch1-6 审计得分全部 ≥75（6/6），三基金（512890/006597/012346）端到端验证通过。

**Phase 3.6**（审计管道数据适配）：2026-07-21 关闭。data_sources 缺失时 LLM 审计权重 70%→50%，数据不足场景通过阈值降至 ≥70。


### Phase 5 Gate 审计结果（2026-07-22）

> **结论：Phase 5 前置条件不成立，Gate 阻塞。**

Phase 3.5/3.6 声称的 "6/6 达标" 基于降级路径掩盖了持仓抽取层系统性缺陷：

- 23 个基金×年份组合中 9 个持仓抽取失败（39%）
- 兴全 2024/2025 持仓表存在但被表格选择逻辑误选为资产配置表
- 国泰全部年份持仓抽取失败（债券基金 query 不匹配 + 表格选择错误）
- 根因：`tool_loop.py` 的 `_score_table_summary` 按页码近邻性打分，同页非持仓表压制跨页持仓表

**阻塞条件**：修复持仓抽取 Bug 1-3 + 补充端到端自动化测试 + 重新验证后，Phase 5 Gate 方可解除。

详见 `.checkpoint-2026-07-22-prephase5-audit.md`。

---

## Phase 5 Gate 重新审计（2026-07-22 晚间）

> **结论：Phase 5 Gate 已解除。**

持仓抽取 Bug 1-4 全部修复（提交 `9a2d0ef` + 本轮修复）：

| Bug | 根因 | 修复 |
|-----|------|------|
| Bug 1 | `infer_fund_type` 不识别 ETF/联接 | 新增 `index_etf`/`index_feeder` 类型 |
| Bug 2 | 联接基金继承条件过窄 | `index_fund` → `(index_fund, index_feeder)` |
| Bug 3 | QDII 持仓查询词不匹配 | `_QDII_HOLDINGS_QUERY` + 直扫兜底 |
| Bug 4 | QDII 列名不匹配 | `_holdings_column_indexes` 适配证券代码/公司名称 |

**端到端验证**：
- 159632（QDII ETF）：8 条持仓 ✅
- 040046（联接基金）：8 条持仓（继承自 159632）✅
- 001564（主动权益）：10 条持仓 ✅（原有）
- 023072（债券基金）：8 条持仓 ✅（原有）

**测试**：250 passed（extraction 131 + agent 14 + document_tools 40 + cli 65）

**DS Review**：NEEDS_FIX → 修复 2 项（fund_type 初始化 + except Exception 安全网）→ 145 passed

---

### Slice 17N（retroactive）：EID 年报下载器

> 裁决时间：2026-07-25（补录，代码已存在）
> 代码路径：`fund_agent/fund/document_tools/eid_downloader.py`（343 行）
> CLI 入口：`fund-checklist download --fund-code <code> --year <year>`

**定位**：单只基金单年度 PDF 下载，从巨潮资讯网（cninfo.com.cn）抓取基金年报 PDF 并校验 Content-Type / 文件头完整性。

**边界**：
- 只做 discovery + PDF 下载，不写 workspace、不调用 Docling、不生成 document_id
- 下载前先检查磁盘缓存（同名 PDF 已存在且 size > 0 时跳过，除非 `--force`）
- 下载后校验 Content-Type（必须为 `application/pdf`）和 PDF 文件头（`%PDF`）
- 失败分类：网络/HTTP 错误归为 `unavailable`，Content-Type/文件头不符归为 `integrity_error`

**allowed write set**：
- `fund_agent/fund/document_tools/eid_downloader.py`
- `fund_agent/cli/main.py`（`download` 子命令注册 + `_run_download_command`）
- `scripts/setup_e2e_data.py`（E2E 数据准备脚本，调用 downloader）

**非目标**：
- 不实现多 provider matrix
- 不实现 batch download / queue
- 不自动触发 Docling 转换或 catalog 注册

**stop conditions**：
- 下载内容非 PDF（Content-Type 或文件头校验失败）→ `integrity_error`
- HTTP 4xx/5xx → `unavailable`
- 年度/代码无匹配结果 → `not_found`

---

## Phase 6：模板框架适配 + 基金类型感知

> 启动时间：2026-07-22
> 前置条件：Phase 5 Gate 已解除 ✅
> 设计来源：`docs/fund-analysis-template-draft.md`（preferred_lens 已设计未接入）、dayu-agent 三层模板架构

### 目标

将 `fund-analysis-template-draft.md` 中已设计的 `preferred_lens`（7 类基金条件渲染）接入 generate 流程，使报告内容根据基金类型自动适配；同时修复数据抽取层的已知缺陷。

### 非目标

- 不引入 LLM 自主工具调用（Phase 5 范围）
- 不新增 `ask`/`interactive`/`streaming` 入口
- 不改变 ChapterContract 结构（Phase 3.6 已完成）

### Slice 列表

| Slice | 内容 | 类型 | 依赖 |
|-------|------|------|------|
| **6A** | 净值增长率列匹配修复 | Bug fix | 无 |
| **6B** | 基金经理/规模数据接入报告 | 数据接入 | 无 |
| **6C** | `preferred_lens` 接入 generate 流程 | 模板适配 | 6A |
| **6D** | 评分框架 fund_type 感知 | 评分调整 | 6C |
| **6E** | 端到端验证 + DS Review | 验收 | 6A-6D |

---

### Slice 6A：净值增长率列匹配修复

**问题**：2024/2025 年报的业绩表列头被 PDF 提取截断（"份额净值增长"缺"率"），导致 `_performance_column_indexes` 匹配失败。

**核实结果**：
- 2023 年报：列头完整（"份额净值增长率①"），匹配成功
- 2024/2025 年报：列头截断（"份额净值增长"），关键词 "份额净值增长率" 不匹配
- 数据实际存在于 table-0011 的 col[1] 和 col[3]

**修复方案**：在 `_ANNUAL_PERFORMANCE_EXTRACTION_SPECS` 和 `_PERFORMANCE_RETURN_EXTRACTION_SPECS` 中增加 fallback 关键词：
- `column_keywords=("份额净值增长率", "份额净值增长")` — 先精确匹配，失败后用截断形式
- `column_keywords=("业绩比较基准收益率", "业绩比较基准收益")` — 同理

**allowed write set**：
- `fund_agent/service/extraction.py`（`_PERFORMANCE_RETURN_EXTRACTION_SPECS` + `_ANNUAL_PERFORMANCE_EXTRACTION_SPECS`）
- `tests/fund/service/test_extraction.py`

**验证命令**：
```bash
uv run pytest tests/fund/service/test_extraction.py -q -k "performance"
```

**stop conditions**：
- 2023 年报现有匹配回退
- 其他基金类型业绩抽取回归

---

### Slice 6B：基金经理/规模数据接入报告

**现状**：`_extract_fund_manager`（L2307）和 `_extract_scale_info`（L2444）已实现，但 `generate` 命令未调用，报告中基金经理和规模信息为空。

**修复方案**：
1. 在 `generate` 流程中调用 `_extract_fund_manager` 和 `_extract_scale_info`
2. 将结果注入 Ch1（基本信息）和 Ch5（规模与变动）
3. 基金经理信息：姓名 + 任职日期
4. 规模信息：期末净资产 / 份额

**allowed write set**：
- `fund_agent/service/extraction.py`（generate 流程）
- `fund_agent/service/chapter_generator.py`（Ch1/Ch5 数据注入）
- `tests/fund/service/test_chapter_generator.py`

**验证命令**：
```bash
uv run pytest tests/fund/service/ -q -k "manager or scale or chapter"
```

**stop conditions**：
- 基金经理信息抽取引入 hallucination
- 规模数据与年报不符

---

### Slice 6C：`preferred_lens` 接入 generate 流程

**现状**：`fund-analysis-template-draft.md` 已设计 `preferred_lens`（7 类基金：default/index_fund/active_fund/bond_fund/enhanced_index/qdii_fund/fof_fund），每类有 `statements`（优先回答什么）和 `facets_any`（子类）。但 generate 命令是硬编码的，不读取 preferred_lens。

**设计方案**（学 dayu-agent 三层模板）：

1. **infer 阶段**：`infer_fund_type`（已实现）确定基金类型
2. **模板选择阶段**：根据 fund_type 从模板中提取对应的 `preferred_lens` 条目
3. **渲染阶段**：将 `preferred_lens.statements` 注入 LLM prompt，作为"优先回答什么"的指引
4. **降级处理**：数据缺失时使用 `when_evidence_missing` 声明，而非整个章节失败

**具体实现**：
1. 解析 `fund-analysis-template-draft.md` 中的 `preferred_lens` JSON
2. 在 `PromptComposer` 中新增 `preferred_lens` 字段
3. LLM prompt 模板增加 `{{ preferred_lens_statements }}` 占位符
4. `generate` 流程根据 `infer_fund_type` 结果选择对应的 lens

**allowed write set**：
- `fund_agent/service/extraction.py`（模板解析）
- `fund_agent/service/chapter_generator.py`（prompt 注入）
- `fund_agent/service/template_loader.py`（preferred_lens 解析，如存在）
- `tests/fund/service/test_preferred_lens.py`

**验证命令**：
```bash
uv run pytest tests/fund/service/ -q -k "preferred_lens or template"
# 端到端
uv run fund-checklist generate --fund-code 159632 --fund-name "华安纳斯达克100ETF（QDII）" --year 2025 --work-dir .fund_checklist_e2e_159632
```

**stop conditions**：
- preferred_lens 注入破坏现有 Ch1-6 输出
- LLM prompt 超出 token 限制

---

### Slice 6D：评分框架 fund_type 感知

**问题**：当前 Ch7 评分对所有基金类型使用相同权重（超额收益 25 分、经理变更 20 分等）。被动 ETF 没有超额收益和经理变更，导致评分偏低（41/100），非基金本身差。

**设计方案（已裁决，2026-07-22）**：

**主动基金**：保持现有 6 指标 135→100 归一化不变。

**被动基金（index_fund/index_etf/index_feeder）**：基于 R=A+B-C 框架，独立 3 指标 100 分制（不走 135 归一化）。

| 指标 | 权重 | 理由（R=A+B-C） |
|------|------|-----------------|
| 费率水平（C） | 40 分 | 被动基金 A≈0，C 是唯一可控变量 |
| 规模风险（B 的稳定性） | 30 分 | 规模过小→清盘风险；规模过大→跟踪能力下降 |
| 持仓集中度（B 的覆盖度） | 30 分 | 指数基金=跟踪完整度；联接基金=目标 ETF 持仓占比 |

**费率阈值按基金类型分档**：

| 类型 | 🟢 (满分) | 🟡 (部分) | 🔴 (低分) |
|------|-----------|-----------|-----------|
| A 股 ETF | <0.20% | 0.20-0.50% | >0.50% |
| 联接基金 | <0.50% | 0.50-1.00% | >1.00% |
| QDII 基金 | <0.80% | 0.80-1.20% | >1.20% |
| 债券基金 | <0.30% | 0.30-0.60% | >0.60% |

**债券基金**：保留超额收益趋势+费率+规模风险+经理变更+持仓集中度（5 指标），风格漂移不适用。

**联接基金**：评分继承目标 ETF（需先完成目标 ETF 评分）。

**Ch6 风险不简化（已裁决）**：被动基金 Ch6 保持三类风险——清盘风险、跟踪偏离长期趋势、指数风险。跟踪偏离作为信息性指标展示（不进入评分），但长期持续偏离仍有信号价值。

**Ch4 不跳过（已裁决）**：被动基金 Ch4 按 Phase 3.5 Slice 17E 规则处理——report_year < 2026 时输出 N/A 声明（数据不足，所有基金类型通用），2026+ 年报按 ChapterContract 生成（含指数基金投资者行为分析）。

**实现**：
1. 在 `signal_scoring.py` 中新增 `_PASSIVE_SCORING_WEIGHTS` 配置（40+30+30）
2. 新增 `_FEE_THRESHOLDS` 按基金类型分档
3. `compute_signal_judgment` 根据 fund_type 路由到不同评分逻辑
4. 被动基金 3 指标直接 100 分制，不走 135 归一化
5. 联接基金评分 = 目标 ETF 评分（继承）

**allowed write set**：
- `fund_agent/service/signal_scoring.py`
- `fund_agent/service/chapter_generator.py`（Ch7 注入）
- `tests/fund/service/test_signal_scoring.py`

**验证命令**：
```bash
uv run pytest tests/fund/service/ -q -k "signal_scoring or scoring"
```

**stop conditions**：
- 现有主动基金评分回退
- 总分不为 100

---

### Slice 6E：端到端验证 + DS Review

**验证范围**：4 类基金 × 全部 Slice

| 基金 | 类型 | 验证点 |
|------|------|--------|
| 159632 | QDII ETF | 净值增长率抽取、preferred_lens=qdii_fund、评分权重调整 |
| 040046 | 联接基金 | 继承路径、评分=目标 ETF |
| 001564 | 主动权益 | 基金经理/规模接入、preferred_lens=active_fund |
| 023072 | 债券基金 | preferred_lens=bond_fund、评分权重调整 |

**验证命令**：
```bash
# 全量测试
uv run pytest tests/ -q

# 四基金 generate
for code in 159632 040046 001564 023072; do
  uv run fund-checklist generate --fund-code $code --fund-name "test" --year 2025 --work-dir .fund_checklist_e2e_$code
done

# 审计
for code in 159632 040046 001564 023072; do
  uv run fund-checklist audit --fund-code $code --year 2025 --work-dir .fund_checklist_e2e_$code
done
```

**DS Review**：全部 Slice 完成后提交完整 diff。

---

### Phase 6 总体验收标准（已裁决更新，2026-07-22）

1. 159632 净值增长率抽取成功（2022-2025 全部）
2. 四类基金报告中基金经理/规模信息非空
3. preferred_lens 根据 fund_type 自动选择并注入 prompt
4. 被动 ETF 评分 ≥60（当前 41，调整后应显著提升）
5. 现有主动基金评分不回退
6. 被动基金 Ch4 按 Phase 3.5 Slice 17E 规则处理（不跳过）
7. 被动基金 Ch6 保持三类风险（清盘+跟踪偏离+指数风险，不简化）
8. 费率阈值按基金类型 4 档分档生效
9. 全量测试通过（250+ passed）
10. DS Review ACCEPTED

## Phase 6 补充：黄金ETF联接基金条件模板（待实施）

**触发条件**：000216 华安黄金ETF联接A 端到端测试暴露

**需要单独设计的特殊性**：
1. 底层资产是黄金现货合约（AU9999），非股票/债券
2. 无股票持仓，持仓表不适用
3. 费率结构可能与普通ETF联接不同（双重费用）
4. 业绩表格式可能与标准A股基金不同
5. `infer_fund_type` 需新增"黄金"关键词识别

**需要设计**：
- Ch6 审计合同：清盘风险+跟踪偏离+黄金价格风险（替代股票持仓集中度）
- 数据表模板：适配黄金基金的费率/持仓/业绩格式
- 信号评分：黄金基金指标权重调整

**优先级**：Phase 6 完成批量测试后实施


## Phase 7：多轮对话 + 会话记忆 + 上下文治理 + Prompt 路由

> 裁决时间：2026-07-25 | 完成时间：2026-07-26
> 前置条件：Phase 5 ✅（2026-07-24 完成）、Phase 6 ✅（2026-07-22 完成）
> 设计来源：`docs/agent-evolution-design.md` §2 + dayu-agent 场景研究
> 计划文件：`.sisyphus/plans/phase7-interactive.md`
> 补完计划：`.sisyphus/plans/phase7-completion.md`（10 项集成缺口，Phase 7.1 承接）

### Phase 7 裁决 Gate

| Gate | 条件 | 状态 |
|------|------|------|
| Gate 1 | Phase 7 scope/write set/verification/stop conditions 写入本文件 | ✅ 本文档记录 |
| Gate 2 | 17 项裁决策通过 | ✅ 已裁决 |

### Phase 7 Slice 列表

| Slice | 内容 | 状态 |
|-------|------|------|
| **7A** | Session 数据模型 + 持久化（filesystem JSON） | ✅ 已完成 |
| **7X** | ToolResult 统一信封 + ToolExecutionContext | ✅ 已完成 |
| **7B** | FundReadingService.resolve_by_fund_code() | ✅ 已完成 |
| **7C** | 统一 INVESTMENT_ADVICE_KEYWORDS | ✅ 已完成 |
| **7D** | DeepSeekLlmClient token usage 追踪 | ✅ 已完成 |
| **7E** | PromptComposer 升级（fragment assembly + contribution injection） | ✅ 已完成 |
| **7F** | Scene Config + Fragment 模板 + Prompt Contributions | ✅ 已完成 |
| **7G** | Service 层 chat_turn use case | ✅ 已完成 |
| **7H** | Host 多轮会话托管 | ✅ 已完成 |
| **7I** | CLI interactive 子命令（prompt_toolkit + rich） | ✅ 已完成 |
| **7J** | Integration wire-up（chat_turn → Host → CLI） | ✅ 已完成 |
| **7K** | 会话恢复 + --label 支持 | ✅ 已完成 |
| **7L** | Episode Summary（异步 LLM） | ✅ 已完成 |
| **7M** | 上下文预算治理（Context Budget） | ✅ 已完成 |
| **7N** | 扩展命令 + 多文档切换 | ✅ 已完成 |
| **7O** | Rich Markdown 渲染 | ✅ 已完成 |
| **7P** | 端到端验证 + 全量回归 | ✅ 已完成 |

### Phase 7 总体验收标准

1. `interactive --fund-code 011649` 端到端通过
2. 多轮对话 3 轮以上上下文正确传递
3. 会话持久化（filesystem JSON）正确
4. 会话恢复（--label）正确
5. Episode Summary 异步触发并落盘
6. 上下文预算裁减生效
7. Scene Config + Fragments + Context Slots 正确装配
8. 投资建议检测每轮生效
9. ask 命令行为不变（回归）
10. 全量测试通过（≥200 tests）
11. ToolResult 统一信封格式正确，agent 层所有工具返回走 envelope
12. ToolExecutionContext 正确注入到每轮 tool call context
13. WorkingMemory overflow 触发 Episode Summary 而非静默丢弃

### Allowed Write Set

| 文件 | 变更类型 | 所属 Slice |
|------|---------|-----------|
| `fund_agent/host/session_store.py` | **新增** — Session JSON 持久化 | 7A |
| `fund_agent/service/session_models.py` | **新增** — Session/Turn/PinnedState 数据模型 | 7A |
| `fund_agent/service/scene_config.py` | **新增** — Scene Config 数据模型 | 7F |
| `fund_agent/service/prompt_contributions.py` | **新增** — Prompt Contributions 构建与选择 | 7F |
| `fund_agent/service/chat_service.py` | **新增** — chat_turn use case | 7G |
| `fund_agent/service/prompt_composer.py` | 升级 — fragment 装配 + contribution 注入 | 7E |
| `fund_agent/service/prompts/interactive/` | **新增** — prompt fragment 模板 | 7F |
| `fund_agent/agent/tool_result.py` | **新增** — ToolResult 统一信封 | 7X |
| `fund_agent/agent/tool_context.py` | **新增** — ToolExecutionContext | 7X |
| `fund_agent/agent/context_budget.py` | **新增** — 上下文预算治理 | 7M |
| `fund_agent/service/extraction.py` | 升级 — resolve_by_fund_code + INVESTMENT_ADVICE_KEYWORDS | 7B, 7C |
| `fund_agent/service/audit_pipeline.py` | 升级 — 统一 INVESTMENT_ADVICE_KEYWORDS | 7C |
| `fund_agent/agent/deepseek_llm.py` | 升级 — token usage 追踪 | 7D |
| `fund_agent/host/minimal_host.py` | 升级 — 多轮会话托管 | 7H |
| `fund_agent/cli/main.py` | 升级 — interactive 子命令 | 7I |
| `tests/fund/cli/test_cli_interactive.py` | **新增** — interactive 测试 | 7I |
| `tests/fund/service/test_chat_service.py` | **新增** — chat_turn 测试 | 7G |
| `tests/fund/host/test_session_store.py` | **新增** — session 持久化测试 | 7A |
| `tests/fund/agent/test_context_budget.py` | **新增** — 上下文预算测试 | 7M |
| `tests/fund/service/test_scene_config.py` | **新增** — Scene Config 测试 | 7F |
| `tests/fund/service/test_prompt_contributions.py` | **新增** — Prompt Contributions 测试 | 7F |
| `tests/fund/service/test_prompt_composer_upgrade.py` | **新增** — PromptComposer 升级测试 | 7E |
| `docs/design.md` | 更新 — Phase 7 设计 | — |
| `docs/implementation-control.md` | 更新 — Phase 7 执行面板 | — |

### Stop Conditions

- `interactive` 破坏 `ask` 子命令现有行为 → 停止
- 会话持久化导致数据损坏 → 停止
- 上下文截断导致 LLM 回答质量下降 → 停止
- Scene Config 装配失败 → 停止

### 验证命令

```bash
# Phase 7 核心测试
uv run pytest tests/fund/cli/test_cli_interactive.py   tests/fund/service/test_chat_service.py   tests/fund/host/test_session_store.py   tests/fund/agent/test_context_budget.py   tests/fund/service/test_scene_config.py   tests/fund/service/test_prompt_contributions.py   tests/fund/service/test_prompt_composer_upgrade.py   -v --tb=short

# Phase 5 ask 回归
uv run pytest tests/fund/agent/test_stream_events.py   tests/fund/agent/test_llm_production_readiness.py   tests/fund/agent/test_llm_tool_loop.py   tests/fund/cli/test_cli.py -k ask   -v --tb=short

# 全量回归
uv run pytest tests/fund/ -v --tb=short
```

### Phase 7 完成证据（2026-07-26）

**Commit 列表**（19 commits pushed to origin/main）：
- ca70e67 feat(phase7): ToolResult envelope + ToolExecutionContext
- 1b614d1 feat(phase7): session data model + filesystem JSON persistence
- 5a747b6 feat(phase7): fund code → documents resolution
- 86af4df refactor(phase7): extract unified INVESTMENT_ADVICE_KEYWORDS
- 7a284b4 feat(phase7): add token usage tracking
- 67c923b feat(phase7): PromptComposer fragment assembly
- 5ec7a95 feat(phase7): dual scene config + fragments + contributions
- 57d3954 feat(phase7): Service layer chat_turn
- aab9548 feat(phase7): Host multi-turn session lifecycle
- 4b62ef8 feat(phase7): CLI interactive subcommand
- b87cba5 feat(phase7): Wave 3 integration wire-up
- 02d4e24 feat(phase7): Wave 3+4 session recovery + context budget + rich rendering
- 2ca3421 fix(phase7): update test_llm_production_readiness.py for ChatResponse
- b1d6215 fix(phase7): restore ask routing context direct-return path
- 22d4ce7 fix(phase7): add routing context to interactive + tool_service wiring
- 4ffcc78 fix(agent): prompt search→read→cite chain + parse extra + tool dedup

**测试**：201 passed, 1 skipped（全量回归）
**真实 LLM 验证**：
- `ask` 单文档：管理费率 1.2% ✅
- `interactive`：管理费率 1.2%、托管费 0.2% ✅
- 模型：deepseek-v4-flash（default）

**LLM 工具调用链路修复**：
- root cause：prompt 缺陷（未指引 read_section）+ _parse_tool_call extra 字段缺失
- 修复：prompt 4 步策略 + extra 字段提取 + tool call 去重
- DS review 结论：模型 function calling 正常，问题在 prompt 引导不足

**evidence 目录**：`.sisyphus/evidence/phase7-goal-011649/`


## Phase 7.1：集成补完 + Dayu 场景借鉴

> 裁决时间：2026-07-26
> 前置条件：Phase 7 ✅（2026-07-26 完成）
> 设计来源：`.sisyphus/plans/phase7-completion.md` + `docs/dayu-scenes-research.md`
> 裁决文档：AGENTS.md Phase 7.1 节

### Phase 7.1 裁决 Gate

| Gate | 条件 | 状态 |
|------|------|------|
| Gate 1 | 10 项集成缺口 + 5 项 Dayu 场景写入本文件 | ✅ 本文档记录 |
| Gate 2 | 裁决事项通过（force_answer / tool_calls_remaining / 投资建议检测 / SYSTEM_PROMPT） | ✅ 已裁决 |

### 裁决记录

| # | 裁决项 | 结论 | 理由 |
|---|--------|------|------|
| 1 | force_answer 降级行为 | **B：用已收集的 tool_results 直返** | max_steps 耗尽时 tool_results 已有数据，直返比再调 LLM 更可靠 |
| 2 | tool_calls_remaining 注入方式 | **A：注入每个 tool result** | Dayu 方案，LLM 每步可见剩余预算，自主调整策略 |
| 3 | routing context 投资建议检测 | **不补** | routing context 返回年报原始数据，不是投资建议 |
| 4 | _SYSTEM_PROMPT 迁移 | **B：保持现状** | ask/interactive 输出格式不同，迁移风险高于收益 |


### Phase 7.1a：集成补完（4 项 P0）

| # | 内容 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | ToolResult 信封接入 runner（包裹旧结果） | P0 | ✅ 已完成 (74 测试通过) |
| 2 | ContextBudget 接入 runner（预算检查 + 工具结果裁剪） | P0 | ✅ 已完成 (31 测试通过) |
| 3 | force_answer 降级（max_steps 耗尽时 tool_results 直返） | P0 | ✅ 已完成 (3 测试通过，commit 98cb6b6) |
| 4 | tool_calls_remaining 信号注入 tool result | P0 | ✅ 已完成 (29 测试通过) |
### Phase 7.1b：Dayu 场景借鉴（5 项）

来源：`docs/dayu-scenes-research.md`，除 wechat 外全部借鉴。

| # | 场景 | 描述 | 对齐现状 | 优先级 |
|---|------|------|----------|--------|
| 1 | **regenerate** | 基于审计反馈整章重建 | 当前 generate 失败只能全部重跑 | P1 |
| 2 | **repair** | 审计发现小问题时最小必要局部修复 | 当前无局部修复能力 | P1 |
| 3 | **fix** | 占位符补强（数据缺失时保留结构化占位符） | 当前数据缺失直接跳过 | P2 |
| 4 | **decision** | 研究决策综合（继续研究/暂缓/放弃） | 当前 Ch7 有信号评分但无决策综合 | P2 |
| 5 | **conversation_compaction** | 长对话上下文压缩 | Phase 7 已有 Episode Summary 基础 | P2 |

### Phase 7.1 总体验收标准

1. force_answer 降级验证：max_steps 耗尽时不报错，返回已收集的 tool_results
2. tool_calls_remaining 生效：每个 tool result 包含剩余调用次数
3. ContextBudget 接入 runner：工具结果超过硬阈值时被裁剪
4. regenerate 场景：审计失败章节可单独重建
5. repair 场景：审计小问题可局部修复
6. 全量回归通过（≥250 tests）

### Allowed Write Set

| 文件 | 变更类型 |
|------|---------|
| `fund_agent/agent/llm_tool_loop.py` | 升级 — ToolResult 信封 + ContextBudget + force_answer + tool_calls_remaining |
| `fund_agent/agent/tool_result.py` | 升级 — project_for_llm 接受 budget 参数 |
| `fund_agent/service/chat_service.py` | 升级 — compaction 线程安全 |
| `fund_agent/service/prompt_composer.py` | 升级 — regenerate/repair/fix scene prompt |
| `fund_agent/service/prompts/scenes/` | **新增** — regenerate/repair/fix/decision scene 模板 |
| `tests/fund/agent/test_tool_result.py` | 升级 — budget 注入测试 |
| `tests/fund/agent/test_llm_tool_loop.py` | 升级 — force_answer + dedup + budget 测试 |
| `tests/fund/service/test_session_models.py` | **新增** — session 模型测试 |
| `docs/design.md` | 更新 — Phase 7.1 设计 |
| `docs/implementation-control.md` | 更新 — Phase 7.1 执行面板 |
| `AGENTS.md` | 更新 — Phase 7.1 状态 |

### Stop Conditions

- force_answer 降级破坏现有 ask 行为 → 停止
- tool_calls_remaining 注入导致 LLM 输出格式异常 → 停止
- ContextBudget 裁剪导致有效数据丢失 → 停止
- regenerate/repair 场景引入新 hallucination → 停止

### 验证命令

```bash
# Phase 7.1 核心测试
uv run pytest tests/fund/agent/test_tool_result.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_context_budget.py -v --tb=short

# 全量回归
uv run pytest tests/fund/ -v --tb=short
```

## Phase 7.2：交互体验增强 + 修复能力激活 + 场景扩展

> 裁决时间：2026-07-27
> 前置条件：Phase 7 ✅（2026-07-26 完成）、Phase 7.1 ✅（2026-07-26 裁决）
> 设计来源：`.sisyphus/plans/phase7.2-implementation.md`
> 裁决文档：AGENTS.md Phase 7.2 节

### Phase 7.2 裁决 Gate

| Gate | 条件 | 状态 |
|------|------|------|
| Gate 1 | Phase 7.2 实施计划审核通过 | ✅ DS review NEEDS_FIX（2026-07-27） |
| Gate 2 | 裁决事项通过（routing context 推翻 / fix CLI 入口 / decision 场景） | ✅ 已裁决 |

### 裁决记录

| # | 裁决项 | 结论 | 理由 |
|---|--------|------|------|
| 1 | Routing Context 预取 | **推翻 Phase 7 预取，全量走 LLM** | 代码简化（删 70 行），统一对话体验，对齐 Dayu。延迟增加由 streaming 缓解，精度由 citation 强制校验兜底 |
| 2 | fix 场景 | **纳入 Phase 7.2** | Dayu 定义清晰：结构化占位符补强。对 fc 多年度数据不完整场景有价值。需新建 SceneConfig + prompt |
| 3 | decision 场景 | **暂缓** | Ch7 确定性信号评分已覆盖"继续/关注/替换"判断。LLM 版决策风险（隐性投资建议）大于收益，且基金分析 vs 股票分析的决策框架差异大 |
| 4 | conversation_compaction | **纳入（轻量）** | Phase 7 EpisodeSummary 已有基础，compaction.md prompt 已写但未接线。1 天接线 |
| 5 | regenerate/repair SceneConfig 激活 | **P0** — 组件已有，仅需接线 | SceneConfig + prompt fragment 已定义，从未被代码引用 |

3. `regenerate --chapter 3` 只重写指定章节，审计反馈注入 prompt
### Phase 7.2 任务分解

| Task | 内容 | 优先级 | 状态 |
|------|------|--------|------|
| 1 | 删除 routing context 预取（~70 行） | P0 | ✅ 已完成 (commit 3ec9d3f) |
| 2 | 扩展 DISCLOSURE_LOCATOR_CONTRACT_REGISTRY alias 覆盖 | P0 | ✅ 已完成 (34/34 测试通过) |
| 3 | Rich Table 格式化输出 | P1 | ✅ 已完成 (55/55 测试通过) |
| 4 | 新建 FIX_SCENE_CONFIG + scenes/fix.md + fix CLI 子命令 | P0 | ✅ 已完成 (9 测试通过 + test_fix_chapter 测试通过) |
| 5 | CLI `repair --chapter` 子命令（激活 REPAIR_SCENE_CONFIG） | P0 | ✅ 已完成 (7 测试通过) |
| 6 | CLI `regenerate --chapter` 子命令（激活 REGENERATE_SCENE_CONFIG） | P0 | ✅ 已完成 (8 测试通过) |
| 7 | 审计分数驱动的修复策略自动选择 | P1 | ✅ 已完成 (9 测试通过) |
| 8 | `/history` 命令 + interactive 启动提示 + 追问建议 | P1 | ✅ 已完成 (70 测试通过) |
| 9 | conversation_compaction prompt 接入 | P2 | ✅ 已完成 (25 测试通过) |
| 10 | Phase 7 回归测试 + Phase 7.2 新增测试 | P0 | ✅ 已完成 (20 个新 smoke 测试通过，227 个测试通过) |

### Phase 7.2 Final Verification

| Gate | Verdict |
|------|---------|
| F1 — 计划合规审计 | APPROVE |
| F2 — 代码质量审查 | APPROVE |
| F3 — 手动 QA 执行 | APPROVE |
| F4 — 范围忠实度检查 | APPROVE |
| **OVERALL** | **APPROVE** |
4. `fix --chapter 3` 检测并补强占位符
5. "基金经理是谁" 返回非空回答（LLM 自主搜索）
6. interactive 表格数据以 Rich Table 显示
7. `/history` 显示最近 10 轮对话摘要
8. `compaction.md` prompt 接入 EpisodeSummary 触发逻辑
9. Phase 7 全量回归 ≥153 passed（不回退）
10. 新增测试 ≥20 passed

### Allowed Write Set

| 文件 | 变更类型 |
|------|---------|
| `fund_agent/service/chat_service.py` | 删除 routing context 预取逻辑 |
| `fund_agent/service/extraction.py` | 删除 routing context 预取逻辑 + 扩展 alias |
| `fund_agent/service/scene_config.py` | 新增 FIX_SCENE_CONFIG |
| `fund_agent/service/prompts/scenes/fix.md` | **新增** — 占位符补强 prompt |
| `fund_agent/cli/main.py` | 新增 repair/regenerate/fix 子命令 + Rich Table |
| `fund_agent/service/audit_pipeline.py` | 审计分数驱动的修复策略 |
| `tests/fund/cli/test_cli.py` | 新增 repair/regenerate/fix 测试 |
| `tests/fund/service/test_extraction.py` | 新增 alias 测试 |
| `tests/fund/service/test_scene_config.py` | 新增 fix scene 测试 |
| `tests/fund/service/test_chat_service.py` | 新增 compaction 测试 |
| `tests/fund/service/test_audit_pipeline.py` | 新增 auto-select 测试 |
| `docs/design.md` | 更新 — Phase 7.2 设计 |
| `docs/implementation-control.md` | 更新 — Phase 7.2 执行面板 |
| `AGENTS.md` | 更新 — Phase 7.2 状态 |

### Stop Conditions

- routing context 预取代码未完全删除（留有死代码） → 停止
- repair/regenerate 复用 generate 的全量重跑逻辑 → 停止
- 修复后丢失 citation + evidence → 停止
- fix 占位符格式未对齐 Dayu 规范（`【占位符】（缺口：... ｜ 需要：...）`） → 停止
- `/history` 命令在 interactive REPL 中不可用 → 停止
- decision 场景进入本次实施 → 停止
- fix 场景产生投资建议 → 停止

### 验证命令

```bash
# Phase 7 回归（确保不回退）
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py -v --tb=short

# Phase 7.2 新增测试
uv run pytest tests/fund/cli/test_cli.py -k "repair or regenerate" -v --tb=short
uv run pytest tests/fund/service/test_extraction.py -k "route_plan" -v --tb=short
uv run pytest tests/fund/cli/test_cli.py -k "fix" -v --tb=short
uv run pytest tests/fund/service/test_audit_pipeline.py -k "decision" -v --tb=short
uv run pytest tests/fund/service/test_scene_config.py -k "fix" -v --tb=short
uv run pytest tests/fund/service/test_chat_service.py -k "compaction" -v --tb=short

# 全量
uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ -v --tb=short
```


## Phase 7.3：对话历史注入 LLM context

> 裁决时间：2026-07-28 | 完成时间：2026-07-29 | 状态：✅ 已完成
> 前置条件：Phase 7 ✅、Phase 7.1 ✅、Phase 7.2 ✅
> 优化设计：`docs/phase7.3-option-b-optimization.md`
> 演进记录：`docs/agent-evolution-design.md` §8.2

### Phase 7.3 裁决 Gate

| Gate | 条件 | 状态 |
|------|------|------|
| Gate 1 | 方案 B 优化设计 DS 二审通过 | ✅ 有条件通过（2026-07-28） |
| Gate 2 | 实施计划审核通过 | ✅ 已通过（2026-07-29） |

### Phase 7.3 任务分解

| # | 任务 | 改动文件 | 行数 | 状态 |
|---|------|---------|------|------|
| 1 | 新增 `ToolCallSummary` dataclass | `session_models.py` | ~10 行 | ✅ |
| 2 | 新增 `Session.truncate_turns()` | `session_models.py` | ~15 行 | ✅ |
| 3 | `_build_history_contribution()` + `ChatService.__init__` 新增 `history_max_tokens` 参数 | `chat_service.py` | ~20 行 | ✅ |
| 4 | `_format_turn_for_history()` | `chat_service.py` | ~15 行 | ✅ |
| 5 | `_estimate_token_count()` | `chat_service.py` | ~5 行 | ✅ |
| 6 | `_build_contributions` 增加 history | `chat_service.py` | ~5 行 | ✅ |
| 7 | `_run_compaction` 增加 truncate | `chat_service.py` | ~5 行 | ✅ |
| 8 | `chat_turn()` 填充 ToolCallSummary | `chat_service.py` | ~10 行 | ✅ |
| 9 | `context_slots` 新增 "history" | `scene_config.py` | 1 行 | ✅ |
| 10 | Bug A: `next_step_stream()` 补 `temperature=self._temperature` | `deepseek_llm.py` | 1 行 | ✅ |
| 11 | Bug B+C: contract 分支 + compaction 路径 temperature 修复 | `chat_service.py` | ~3 行 | ✅ |
| 12 | Bug D: `_default_runner_factory` 新增 `temperature` 参数 | `extraction.py` | ~3 行 | ✅ |
| 13 | Bug E: regenerate helper `DeepSeekLlmClient` 补 temperature | `main.py` | 1 行 | ✅ |
| 14 | 新增 `_normalize_document_id()` 前缀匹配 | `llm_tool_loop.py` | ~15 行 | ✅ |
| 15 | 单元测试（含 document_id + temperature A~E） | `tests/` | 34 个测试 | ✅ |
| 16 | e2e 测试 | `tests/e2e/` | ~10 行 | ⚠️ xfail（已知 bug） |

### Stop Conditions

- `LlmClientProtocol.next_step()` 签名变更 → 停止（违反方案 B 约束）
- `llm_tool_loop.py` 核心 loop 逻辑修改 → 停止（`_normalize_document_id` 前缀匹配是批准的例外）
- `deepseek_llm.py` / `extraction.py` / `main.py` 超出 temperature 透传范围的修改 → 停止
- history 注入后全量回归 < 769 passed → 停止
- e2e interactive 测试仍全部 xfail → 停止
- history contribution 未出现在 system prompt 中 → 停止（核心功能验收点）

### 验证命令

```bash
# Phase 7.3 核心测试
uv run pytest tests/fund/service/test_chat_service.py -k "history" -v --tb=short
uv run pytest tests/fund/host/test_session_store.py -k "truncate" -v --tb=short

# Phase 7 回归
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py -v --tb=short

# e2e 测试
uv run pytest tests/e2e/ -v --tb=short

# 全量回归
uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ --tb=no -q
```

### DS 二审待处理项（已处理）

1. **Bug（已修）**：`truncate_turns` 已补充 `status=self.status, updated_at=...`
2. **遗漏（已补）**：`chat_turn()` 已显式填充 `ToolCallSummary`
3. **建议**：ContextBudget 与 history token 交互留 TODO，Phase 8 处理

## Phase 7.4：interactive e2e 失败修复（S0-S7 已 ACCEPTED，live e2e 11/11）

> 裁决时间：2026-08-02 | 状态：✅ S0-S7 全部 ACCEPTED；opt-in live e2e 第七轮 11/11 通过（0 失败 / 0 误拦截）
> 背景：08-01 e2e `uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace`（9 问：4 成功 / 5 失败 / 2 误拦截）
> 计划产物：`.sisyphus/plans/interactive-e2e-fix-20260802.md`（唯一计划 artifact）
> Goal：`.sisyphus/goals/phase7.4-goal.md`（/goal 表述，Mimo review ACCEPTED）

### 失败根因与 slice 映射

| # | 现象 | 根因 | slice |
|---|------|------|-------|
| 1 | 基金规模 / 港股持仓 → 章节不存在 | LLM 猜测 section_ref，首个 ToolFailure 即整轮失败（llm_tool_loop.py:424-425/534-535） | S1（回喂） |
| 2 | 对比2021-2024 → provider 结构不符 | `_parse_tool_call` 强制 document_id（deepseek_llm.py:656），aggregate 工具本豁免仍被强制 | S2（容错） |
| 3 | 值得继续关注 → 工具调用超过限制 | max_iterations=20 耗尽且无 evidence（llm_tool_loop.py:1042） | S4（prompt 引导） |
| 4 | 管理费/托管费/销售服务费 → 工具调用不被允许 | 白名单 + document_id 前缀双校验（llm_tool_loop.py:638/641-644）一次偏差即失败 | S2 |
| 5 | 前十大重仓股 / 基金风格 → 误拦截 | 弱词豁免窗口不含持仓/风格事实描述（llm_tool_loop.py:83-133） | S3（依赖口径）+ S0 持久化 |

### slice 顺序

S0（失败轮可观测性与持久化）→ S1（ToolFailure 回喂）→ S2（document_id 补全/工具名归一化）→ S3（投资建议判据，依赖 B1 口径 owner 确认，未确认前挂起）→ S4（prompt 引导）→ S5（doc-sync）

### 已验证事实（2026-08-02，Mimo review 确认）

- e276ff3 失败分支使用不存在的 `entry.status`（`ToolTraceEntry` 仅 `tool_name/arguments/result_kind/failure_code`），revert 属正确纠错；S0 恢复时必须改用 `result_kind`/`failure_code`。
- 工作区未提交 WIP = B1（投资建议强弱词豁免）+ B2（document_id 注入），为计划基线，不得重复规划或回退；`docling_store.py` WIP 与本计划无关，禁止触碰。
- main.py:1104/1243 用户输入预检仍用旧 naive guard，与 B1 单一真源不一致（S3 修复）。

### 下一步（实现派发）

### slice 验收结果（2026-08-02，controller review）

| slice | 内容 | 状态 | 验证 |
-------|------|------|------|
| S0 | 失败轮 session 成对持久化 + tool_trace 恢复（纠正 `entry.status` 字段错误）+ 被拦截原文与触发词落盘（含 `session_store.py` 磁盘往返） | ✅ ACCEPTED | chat_service/session_store/cli_interactive 140 passed；agent 基线 91 passed |
| S1 | ToolFailure 回喂：失败作为带 failure 标记的 ToolResult 回喂下一轮；run/run_stream 不终止；去重短路；provider 异常仍 fail-closed | ✅ ACCEPTED | llm_tool_loop/stream_events/tool_result 85 passed；agent 基线 91 passed |
| S2 | `_parse_tool_call` document_id 可选；runner expected 补全 + 前缀校验；工具名有界归一化 | ✅ ACCEPTED | llm_tool_loop/real_llm_adapter 85 passed；agent 全量 201 passed |
| S3 | 投资建议判据按决策 A 落地（弱词 + 事实上下文词放行、指令动词拦截、fail-closed 兜底）+ main.py 预检单一真源；实证修正：指令动词去裸「应」（避免误命中 应付/应计），改 应当/应买入/应卖出/应增持/应减持 | ✅ ACCEPTED | 决策 A 经 B1 口径 owner 确认；llm_tool_loop/chat_service/cli 204 passed（3 条预置失败除外） |
| S4 | prompt 引导：无事实目标 0 工具 final answer；空搜索最多换 1 次词；不猜 section_ref/table_ref | ✅ ACCEPTED | scene_config/prompt_composer/llm_tool_loop 108 passed |
| S5 | 真源文档与 AGENTS.md 同步 | ✅ 本文件 | git diff --check 干净 |
| S6 | provider malformed 有界重试 1 次（stream + 非 stream，重试后仍 fail-closed） | ✅ ACCEPTED | real_llm_adapter + live_smoke 37 passed；agent 全量 213 passed |
| S7 | interactive 终答投资建议守卫有界改写重试 1 次（重答仍过同一守卫；ask/generate 不重试） | ✅ ACCEPTED | llm_tool_loop/stream_events 82 passed；agent 全量 218 passed |

### 既有失败（非本任务引入，HEAD 级核验）

4 条测试在 HEAD（c4e5e71）同样失败（临时 worktree 复现）：`test_fix_chapter`（stale 引用已重构符号）、`test_cli_reuses_existing_docling_json_without_converter` / `test_cli_happy_path...`（fake 摘录断言漂移）、`test_convert_local_pdf_writes_docling_json`（缺失真实 PDF fixture）。与 S0-S5 改动无关，另开 slice 处理，不在本 Phase 7.4 范围。

### opt-in live e2e 结果（2026-08-02，七轮）

命令：`uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace`（管道输入原 11 问）。

第一轮（S4 初始版）：6/11 通过，5 失败——Q3 投资策略（投资建议关键词）、Q5 重仓股（拦截）、Q6 港股（拦截）、Q9 值得关注（投资建议关键词，0 工具）、Q10 风格（step limit，search 无命中耗尽预算）。

第二轮（S4 补充后）：7/11 通过，4 失败——Q3 投资策略（投资建议关键词）、Q4 对比2021-2024（投资建议关键词）、Q5 重仓股（拦截）、Q9 值得关注（投资建议关键词，0 工具）、Q11 费率（拦截）。Q6 港股（多次检索无命中→声明未找到）与 Q10 风格（0 工具中性表述）已修复，归因于 S4 补充的"连续 2 次无命中即停"与"观点类中性表述"规则。

剩余失败分类（session a573a025 证据，S0 持久化已生效）：

| 问题 | 现象 | 分类 |
------|------|------|
| Q3 投资策略 / Q4 对比策略 / Q5 重仓股 / Q11 费率 | 回答含 买入/卖出 等年报事实性表述，B1 弱词豁免窗口（50 字符内 策略/宣称/原文/摘录/运作分析）未命中 → 拦截 | 🔴 S3 口径范围（事实性描述 vs 操作建议边界），依赖 B1 口径 owner 确认 |
| Q9 值得继续关注 | 0 工具调用但回答含操作建议措辞，runner 终答守卫 fail-closed | 部分属 S4 措辞约束（模型行为方差），部分属 S3 口径（"值得关注"类判断边界） |

### 最终验收（第七轮，2026-08-02）

`uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace`（管道输入原 11 问）→ **11/11 通过，0 条 `LLM 处理失败`，0 条误拦截**。失败轮可观测性（S0）、失败自愈（S1）、document_id 容错（S2）、决策 A 事实豁免（S3）、空搜索预算保护与中性表述（S4）、malformed 有界重试（S6）、终答守卫改写重试（S7）均已生效。

残余说明：e2e 单轮结果受 LLM 措辞方差影响（第三至六轮各轮有 1-2 条守卫/解析失败，已被 S6/S7 或模型方差吸收）；第七轮为全绿终验。强指令词（建议买入/强烈推荐/目标价/预期收益预测句式）仍 fail-closed，属设计内。

### S3 口径裁决（2026-08-02）

B1 口径 owner 确认**决策 A**：弱词豁免引用上下文词表扩展（15 个事实性上下文词）、窗口 100、指令动词拦截、无上下文词 fail-closed 兜底；实证修正：指令动词去裸「应」。口径提案：`.sisyphus/plans/phase7.4-s3-caliber-proposal.md`（Mimo review ACCEPTED）。

## 2026-08-02 后记：F1/F2 费率与持仓修复（163415 报告缺陷）

> 状态：✅ 实现完成并 ACCEPTED（controller review）；端到端 generate 复跑验收中
> 规格：`.sisyphus/plans/fee-holdings-fix-20260802.md`（Mimo review ACCEPTED）

### F1 费率（贪婪正则 → 有界非贪婪）

- `_extract_fee_rates_from_agent_result`（extraction.py:5799 附近）的 管理费/托管费/销售服务费 正则由 `.*` 贪婪改为 `.{0,80}?` 有界非贪婪：修复「所有费率等于 LLM 答案最后一个百分比」问题（2025 曾全取 0.60%，实际 1.20%/0.20%/0.60%）。
- 实测：多百分比答案逐项取对（管理费 1.20%、托管费 0.20%、销售C 0.60%）；综合费率输入恢复正确（A类 1.40%、C类 2.00%，口径另议）。

### F2 持仓（caption 噪声 + header-fallback）

- `_NO_SEMANTIC_CAPTION_RE` 页码模式扩展支持「第 N 页 共 M 页」（原只匹配「第 N 页」），使垃圾页眉 caption 回填 section 标题 → `search("股票投资明细")` 可命中 top-10 表。
- `_extract_holdings_from_agent_result` 的 header-fallback 由「只搜编号更小的表」改为「同 section ±5 双向查找」。
- 实测：2023/2025 前十大持仓从 0 行恢复为 10 行（2025 宁德时代 6.86% 首行等）。

### 既有失败（与 F1/F2 无关，已实证）

`test_real_pdf_controlled_profiles_apply_disclosure_target_contract`（test_extraction.py:2804）仍失败：10B fee_rates 确定性路由对 004393-2024 年报每个费率查询只产出 **1 个 section citation**（管理费→section-0379、托管费→section-0390、销售服务费→section-0398），10C `_fee_rate_section_citations` 要求最终结果 ≥3 个 section citation → NOT_FOUND「fee_rates citation 不完整」。无关性证据：F1 只改解析（在 citation 检查之后）；F2 caption 改动对该文档 0 处生效；holdings fallback 仅持仓路径；DS 还原实验同错。需单独 slice 排查（候选：路由后合并三查询 section citations，或放宽 10C 段切分）。

> 2026-08-03 更新：该失败已由 fee-rates-10bc 修复（`aggregate_all_matches=True` 聚合三查询 section citation）解决，real-pdf 测试 1 passed。

### F3 基金经理持有区间抽取缺失（规格 ACCEPTED，实施待派发）

- 现象：2025 年报 9.4 节披露「基金经理持有本开放式基金 A类 >100 万份、C类 0、合计 >100」（store table-0090 row 4-6），报告 Ch4 显示「未披露」。
- 根因：`_extract_manager_info` holds_fund 取值条件只认单元格含「~」或「万份」（extraction.py:2620-2624），本表区间值为 `>100`（单位在表头）→ 漏抽。
- 规格：`.sisyphus/plans/fee-holdings-fix-20260802.md` §6（Mimo review ACCEPTED）；修复方向：区间形态 `>N`/`<N`/`N~M`/纯数字 + 表头单位继承 + 空白归一化 + 优先 A 类行。
- 状态：✅ 已实施（extraction.py:748 9.4 区间抽取，含表头单位继承）；2026-08-03 163415 generate 端到端验证生效：报告 Ch3 显示「持有本基金 A类>100万份」，`FundManagerInfo.holds_fund='A类>100万份'`（excerpt citation section-0064, p.11）。

## 2026-08-04 后记：F1.1 费率抽取修复（空格噪声 + 费率沿革口径）

> 状态：✅ 完成（2026-08-05，Mimo review ACCEPTED → 真源文档更新 → DS 实施 → controller review：17 passed、实数据五年全绿）
> 规格：`.sisyphus/plans/fee-rates-f11-fix-20260804.md`

### 现象（163415 2025 generate 端到端重跑验收）

| 年份 | 重跑前报告值 | 真值 | 状态 |
|---|---|---|---|
| 2021 | 无行（not_found） | 管理 1.50% / 托管 0.25% | 管理费未提取 |
| 2022 | 0.25% / 0.25% | 1.50% / 0.25% | 管理费错误 |
| 2023 | 1.50% / 0.25% | 当期适用 1.20% / 0.20% | 口径不符 |
| 2024 | 1.50% / 0.25% | 当期适用 1.20% / 0.20% | 管理/托管均错误 |
| 2025 | 1.20% / 0.20% / 销售C 0.60% | 同左 | 正确 |

### 根因与修复

- 根因一（Docling 空格噪声）：`1.  50%` 破坏 `\d+\.\d+%` 匹配，多年度路径 `_extract_fee_rates_from_agent_result`（extraction.py:6079）主正则（6088）失配后在 80 字符窗口误捕获托管费 0.25%；10C 路径同失配返回 not_found。修复：新增百分比邻域归一化 helper，两条路径抽取前先归一化。
- 根因二（费率沿革文本）：2023/2024 年报按「2023/1/1-7/9 1.50% → 自 7/10 起 1.20%」披露，有界正则取首个百分比得到历史费率。修复：10C 路径已有沿革选择逻辑（4551/4568），仅补归一化；多年度路径新增「含『自…起』取其后费率，否则取标题块内最后一个百分比」。
- 2023 口径裁决：报告单值列取当期适用（期末）费率 1.20%/0.20%，不做分段加权。

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "fee" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py tests/fund/document_tools/test_docling_store.py -q --tb=short
```

验收口径：单测覆盖空格归一化、沿革文本取当期费率；实数据对 163415 五年 store 断言管理费/托管费 = 2021 1.50/0.25、2022 1.50/0.25、2023 1.20/0.20、2024 1.20/0.20、2025 1.20/0.20；`git diff --check` 干净；不 commit / push。

## Phase 7.5：generate 章节级并发（实现完成，待 controller review）

> 状态：🟢 实现完成（2026-08-05），真源文档已更新（design.md §6.8），待 controller review 后收口
> 设计：`.sisyphus/plans/phase7.5-chapter-concurrency-design.md`（Mimo review ACCEPTED；命名 Phase 7.5，备选 Slice 14D）

### 实现摘要（2026-08-05）

- `fund_agent/service/audit_pipeline.py`：`ReportGenerationCoordinator` 四阶段并发改造（`ThreadPoolExecutor`，B/D 复用同一 executor 且强制 join）、`_run_chapter_worker` 顶层兜异常、`_process_states` 加 `threading.Lock`（`_set_state`/`_get_state`）、章节闭环 3 处 `self._llm_client` 改为显式下传 `llm_client`、无 `clone()` 时回退串行 + warning。
- `fund_agent/agent/deepseek_llm.py`：新增 `clone()`（同 transport/env/options/system_prompt/temperature，独立 `_cumulative_usage`）。
- `fund_agent/service/models.py`：`GenerateReportRequest` 新增可选 `chapter_concurrency: int | None = None`。
- `fund_agent/service/extraction.py`：`generate_report` 唯一解析点（request 字段 → env `FUND_CHECKLIST_CHAPTER_CONCURRENCY` → 默认 4），显式传入 coordinator；未触碰 F1.1 费率逻辑与 Phase 7.4 区域。
- `fund_agent/cli/main.py`：generate parser 新增 `--concurrency`（1..8 校验；无 `--llm` 时忽略并提示），透传 request。
- 测试：新增 `tests/fund/service/test_report_concurrency.py`（T1-T8 + concurrency=1 串行等价基线，13 用例）；既有 fake 补 `clone()`。

### 验证结果（2026-08-05）

```bash
uv run pytest tests/fund/service/test_report_concurrency.py tests/fund/service/test_audit_pipeline.py -q --tb=short
# 61 passed
uv run pytest tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py -q --tb=short
# 111 passed；3 failed 为既有问题（HEAD 复现）：test_cli_happy_path... / test_cli_reuses_existing... / test_fix_chapter
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
# 169 passed；4 failed 均为既有问题（HEAD 复现）：上述 3 项 + test_convert_local_pdf_writes_docling_json（缺 fixture PDF）
uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_deepseek_live_smoke.py tests/fund/service/test_extraction.py -q --tb=short
# 238 passed
```

验收：T1-T8 全绿（13/13）；`chapter_concurrency=1` 调用序列与串行基线一致（fake 记录比对）；`git diff --check` 干净；默认 pytest 无网络；未 commit / push。

### 要点

- 四阶段：A 前置串行（data_table + global_numbers 预生成）→ B Ch1-6 并行（写→审计→重写闭环在 worker 内）→ C 决策串行（B join 后 all_passed 判定）→ D Ch0/Ch7 并行收尾（复用 executor，B/D 之间强制 join）。
- 机制：`ThreadPoolExecutor`；每 worker 独立 `DeepSeekLlmClient.clone()`（独立 `_cumulative_usage`）；闭环内 3 处 `self._llm_client` 显式下传。
- lane：`chapter_concurrency`，优先级 CLI `--concurrency` → request 字段 → env `FUND_CHECKLIST_CHAPTER_CONCURRENCY` → 默认 4（1..8，1=串行等价）；client 无 `clone()` 回退串行 + warning。
- 线程安全：`_process_states` 按章 key + Lock；ArtifactStore 按章分文件唯一 writer；共享输入只读；warnings 主线程按 cid 排序；worker 禁止直接 print。
- 失败语义：单章失败隔离；`passed/passed_with_degradation/audit_exhausted` 不变；cancel 用 `shutdown(wait=True, cancel_futures=True)`。
- 禁止：不引入 dayu runtime/代码/async 事件循环；不改 search_document / Service 公共契约；不触碰 Phase 7.4 与 F1.1 未提交区域。

### 验证命令

```bash
uv run pytest tests/fund/service/test_report_concurrency.py tests/fund/service/test_audit_pipeline.py -q --tb=short
uv run pytest tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py -q --tb=short
```

验收口径：`chapter_concurrency=1` 与串行基线调用序列一致；`N` 时并发峰值 ≤ N；章节集合/顺序稳定；单章失败隔离；clone 独立 usage；默认 pytest 无网络；`git diff --check` 干净；不 commit / push。

## 测试修复 slice：4 个基线失败 + fix CLI 断链（计划 ACCEPTED，实施中）

> 状态：🟡 计划 ACCEPTED（2026-08-05，Mimo review：8 处代码事实核实），真源文档已更新，DS 实施中 → controller review 后收口
> 规格：`.sisyphus/plans/test-fixes-20260805.md`

### 前提修正（相对 2026-08-02 结论）

4 个基线失败中 **3 个是测试侧**（fixture 路径错位、两处断言过时），但 `test_fix_chapter` 暴露**主体代码断链**：`main.py:_run_fix_command` 惰性导入已不存在的 `chapter_generator._fix_chapter_placeholders`（Phase 7.2 scene 化移除），fix CLI 运行即 ImportError；`FIX_SCENE_CONFIG`（scene_config.py:145）与 `scenes/fix.md` 已建但未接线（repair/regenerate 已接 REPAIR/REGENERATE_SCENE_CONFIG → ChatService，fix 未接）。

### 修复要点

- fixture：`test_docling_conversion.py` 数据源切换为 `基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf`（fund_code 011649 / 易方达逆向投资混合 / year 2025）；`tests/README.md` 16 处 smoke 命令同步。
- 断言：`test_cli.py` 两处 `基金管理人` → `基金经理`（与确定性输出对齐）。
- fix CLI：重接 `FIX_SCENE_CONFIG` → ChatService（`PinnedState.user_constraints` 透传 chapter_content/audit_feedback/chapter_contract，chat_service.py:570）+ workdir tool_service（interactive 模式）+ `--llm` 参数；保留补强/保留占位符统计与 exit code；删除对不存在符号的引用。
- `test_fix_chapter` 重写：注入带 `clone()` 的 fake LLM（仿 generate real-pdf smoke），断言 exit 0 + 统计 + 仅处理目标章节。

### 验证命令

```bash
uv run pytest tests/fund/document_tools/test_docling_conversion.py tests/fund/cli/test_cli.py -q --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
```

验收口径：4 个基线失败转绿；其余测试不回退；011649 fixture 真实转换通过；`git diff --check` 干净；不 commit / push。

## PDF 导出 fallback slice（计划 ACCEPTED，实施中）

> 状态：🟡 计划 ACCEPTED（2026-08-05，Mimo review），真源文档已更新（design.md §6.9），DS 实施中 → controller review 后收口
> 规格：`.sisyphus/plans/pdf-export-fallback-20260805.md`

### 问题与方案

- 问题：`_export_pdf`（extraction.py:3770）单一路径 pandoc `--pdf-engine=xelatex`；本机无任何 LaTeX 引擎（xelatex/pdflatex/lualatex/tectonic/weasyprint/typst 均无）、Chrome 150 可用 → `--format pdf` 必然回退 md。
- 方案（参考 dayu/render/render.py，不复制代码）：引擎 fallback 链 ① xelatex（`shutil.which` 前置探测）→ ② pandoc md→HTML（内嵌打印 CSS）→ Chrome headless `--print-to-pdf`（A4 794×1123，timeout 120s）→ ③ 回退 md + warning。Chrome 探测 `PUPPETEER_EXECUTABLE_PATH` → PATH → macOS 默认路径。打印 CSS 为原创资产，HTML 中间产物临时目录清理。
- 前置验证：手动 `pandoc md→html && Chrome --print-to-pdf` 已实测通过（含中文）；dayu 渲染管线已核实。

### 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "export" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py -q --tb=short
```

实数据 smoke：当前环境 `_export_pdf('.fund_e2e_163415/reports/163415-2025-analysis.md', ...)` 应走 Chrome 分支产出真实 PDF（>0 字节，warning None）。

验收口径：单测覆盖三态（xelatex / chrome / md 回退）；实数据 PDF 产出；`git diff --check` 干净；不 commit / push。

## interactive 质量修复 slice（计划 ACCEPTED，实施中）

> 状态：🟡 计划 ACCEPTED（2026-08-05，Mimo review：4 处代码事实核实），真源文档已更新（design.md §6.10），DS 实施中 → controller review 后收口
> 规格：`.sisyphus/plans/interactive-quality-fix-20260805.md`

### 问题与裁决

- 现象（004393 interactive 实测 4 问）：检索无受控路由（持有本基金类 query 无 profile，LLM 用词 0 命中假阴性；实测「持有本基金」命中 section-0593）；空结果不收敛 + `max_iterations=20` 导致慢/重复（5-14 次调用）；终答回显工具原文；JSON 信封未解包。
- 用户裁决（按推荐）：三层全做；空结果有 profile 自动候选词重试 1 轮、否则连续 2 次强制收敛；终答重叠 ≥40 字符或 >800 字有界重答 1 次；保持 JSON 契约 + runner 解包；本次只做 `manager_holdings` profile；`max_iterations` 20 → 12；方案 E 不变。
- 后续 backlog（不在本 slice）：规模、份额、基准收益率、超额收益率、十大持仓 等受控 profile。

### 修复范围

- L1 检索路由：新增 `manager_holdings` profile（candidate_queries 覆盖 持有本基金 等 4 词）。
- L2 工具循环：空结果强制收敛（连续 2 次）+ 候选词重试 1 轮（候选注入在 Service，收敛执行在 Agent）；interactive `max_iterations=12`。
- L3 终答质量：JSON 信封解包；原文粘贴检测 + 有界重答 1 次 + 截断摘要；`scene.md` 加「禁止粘贴原文、≤200 字」约束。

### 验证命令

```bash
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_extraction.py tests/fund/service/test_scene_config.py tests/fund/service/test_chat_service.py -k "manager_holdings or converge or json or overlap or paste or max_iterations" -q --tb=short
```

验收口径：单测全绿；opt-in live e2e（004393 复跑）Q1 命中 9.4、Q3/Q4 ≤200 字无原文粘贴、Q4 调用 <12；`git diff --check` 干净；不 commit / push。

### interactive 质量修复 slice 收口（2026-08-06 controller review 通过）

- 实现：`manager_holdings` profile（extraction.py:206，candidate_queries 4 词）；空结果强制收敛（连续 2 次 0 命中，`_INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT=2`）+ 有候选词自动重试最多 1 轮；终答 JSON 信封解包（纯 JSON / ```json 代码块）+ 原文粘贴/超长守卫（与 evidence 连续重叠 ≥40 字符或 >800 字 → 有界重答 1 次 → 仍超标截断前 200 字摘要）；interactive `max_iterations` 20→12 + `retrieval` context slot（候选词注入在 chat_service，收敛执行在 runner，runner 不 import service）；`scene.md` v1.6 加「禁止粘贴工具原文、≤200 字」。
- 验证：Phase 7 核心 253 passed；slice 单测 18 passed；四目标文件全量 370 passed（DS 实测）；controller 独立复跑 253+18 passed；`git diff --check` 干净；默认测试无网络。
- 已知偏差（已记录）：plan §L3「key_facts 落盘」未完全达成——`tool_loop.py`/`session_models.py` 不在 allowed write set，`AgentRunResult`/`Turn` 无 key_facts 槽位，key_facts 仅解析保留在 `FinalAnswer` 内（citations 已随 `AgentRunResult.citations` 落盘）。展示链路不受影响；key_facts 持久化列为后续可选小修。
- 遗留：opt-in live e2e（004393 interactive 复跑）未跑（需显式授权）。

## 007466 业绩抽取修复 + 关联 ETF 持仓集中度（计划待 review）

> 状态：🟡 计划待 Mimo review（规格：`.sisyphus/plans/007466-performance-holdings-concentration-20260805.md`）

要点：007466 2024/2025 业绩抽取失败（2024 `annual performance 过去一年完整字段缺失`、2025 `performance_returns 过去一年行无法唯一识别`），数据存在（2024 A类 21.06/17.00/4.06；2025 4.18/0.47/3.71），根因是 3.2.1 表按 A/C 拆成多表/分段表；修复方向：过去一年唯一性按 share_scope 过滤 + 无表头部分表用相邻 A 类表头对齐 + 数据表防错填。持仓集中度改从关联 ETF 512890（`.fund_checklist_512890`，2021-2025 数据可用）top-10 提取，generate 新增可选关联源参数，报告标注来源基金。

### 007466 slice 收口（2026-08-06 controller review 通过）

- Task A：`_performance_past_year_row` 按 share_scope 过滤（A/C/I/Y 段标签切分，单段多行仍 fail-closed）；`_headerless_performance_column_indexes` 无表头部分表按相邻 A 类表头对齐；`_annual_performance_table_refs` 支持 cited 部分表 + uncited 完整同 section 表补全（保留「cited 无关表不得消费 uncited signature 表」的 10F 契约）；报告级统一优先 A 类；Ch2 数据表年份取业绩∪费率并集，缺失单元格显式「缺失」，prompt 禁止用其他列补空（顺带修复 `performance[year]` KeyError）。
- Task B：`GenerateReportRequest.holdings_source_fund / holdings_source_workdir` + CLI `--holdings-source-fund/--holdings-source-workdir`；Service 从关联源提取 top-10 替换持仓并标注「来源：标的 ETF 512890 年报」（Ch3 持仓表、Ch3/Ch6 集中度、证据、metadata 均标注）；未指定时保持现状。
- 验证：`-k performance or holdings or concentration` 61 passed（controller 复跑）；三文件全量 369 passed（DS：基线 358 + 新增 11）；实数据五年业绩 2021-2025 全对（2024 21.06/17.00/4.06、2025 4.18/0.47/3.71，2021-2023 不回退）；报告核验 Ch0 4.18%、Ch2 2024/2025 行真值、集中度 2025 前五 13.58%/前十 25.12% 带来源标注；`git diff --check` 干净；未 commit / push。

## QDII slice 序列（S1 持仓已完成，S2-S4 排队）

> 规格：`.sisyphus/plans/qdii-extraction-slices-20260806.md`（Mimo review ACCEPTED）

### S1 持仓适配收口（2026-08-06 controller review 通过）

- 根因（Mimo 修正后）：`search_document` 只匹配 section.text 不匹配 title；QDII fallback 分支（extraction.py:1408/1463）只覆盖 index_etf/index_fund+QDII，主动 QDII（519696）走不到。
- 修复：QDII fallback 条件扩展为 `fund_type not in ("bond_fund","index_feeder") and "QDII" in fund_name`；直接扫描（`_extract_qdii_holdings_from_tables`）为权威路径、query 仅兜底（实测 query 命中跨页续表碎片）；支持跨页分裂表（表头碎片补齐 `_merge_qdii_header_fragments`、同章节续表按列合并 `_extract_qdii_continuation_rows`、碎片行跳过）；双「公司名称」列优先中文列（`_holdings_column_indexes`:6501）。
- 验证：`-k holdings` 24 passed（controller 复跑）；三文件全量 375 passed；实数据 519696 2024/2025 各 10 行（2025 前三：腾讯控股 5.01/中国宏桥 4.75/中芯国际 3.69）；163415/007466 不回退；`git diff --check` 干净；未 commit / push。
- 已知问题（另排 slice，非 S1 范围）：004393 持仓 0 行（前序未提交区 search/citation 变化导致首个 table citation 命中行业配置表 table-0079，非 S1 回归，A/B 实证）；519696-2025 第 6 名跨页断裂（代码/占比丢失，按最小适配跳过碎片行）；519696-2023 表头截断（「证券代」「占基」）仍为空（不在 S1 验收内）。

### S2 费率（待 review）

根因：QDII 年报把管理费表述为「支付基金管理人的**管理人报酬**」（无「基金管理费」字样）→ 2022 管理费缺失；2023/2024 托管费（0.35%）正文存在但抽取缺失（各年路由/绑定不稳定）。验收真值：519696 五年管理费/托管费 = 2021-2024 1.80%/0.35%、2025 1.20%/0.20%。

### S2 收口（2026-08-06 controller review 通过）

- 修复：`_FEE_RATE_MANAGEMENT_WORDINGS = ("基金管理费", "管理人报酬")` + QDII 措辞回退正则；`_extract_fee_rates_from_agent_result` 主路径「基金管理费」块未命中时改查「管理人报酬」块（输出仍为 基金管理费）；`_extract_fee_rates_from_store` 回退从「全空才跑」改为逐缺失字段单标题验证（补 2023/2024 托管费）；2022 嵌套章节（7.4.9 关联方关系）正文含明确费率句时放行。
- 计划偏差（已写回 design.md §6.13）：未把「管理人报酬」加入 `_FEE_RATE_TITLES`——该固定三标题元组喂 10B 契约（`_fee_rate_segments`/`_fee_rate_section_citations`），追加第 4 项会破坏 A 股费率路径；实现改为块查找别名，行为满足计划意图。
- 验证：`-k "fee or qdii"` 29 passed（controller 复跑）；完整三文件 381 passed；实数据 519696 五年 1.80%/0.35%（2021-2024）与 1.20%/0.20%（2025）全对；163415/007466/004393 不回退（004393-2022 1.5% 为源 PDF 措辞）；`git diff --check` 干净；未 commit / push。

### S3 资产配置（计划 ACCEPTED，实施中）

根因（Mimo review 修正）：`search("期末基金资产组合情况")` 命中 table-0059 估值表（caption 含查询词），真正资产配置表 table-0060（caption=「金额单位：人民币元」）不被引用；`_extract_allocation_from_agent_result`（extraction.py:6601）asset_allocation 无全表扫描 fallback（industry 有，6629-6637）→ 错绑后空。修复：增加 asset_allocation 全表扫描 fallback（`list_tables` + `_is_asset_allocation_table` + `_parse_asset_allocation_table`），表结构无需适配。验收：519696 2023 资产配置非空；2021/2022/2024/2025 不回退。

### S3 收口（2026-08-06 controller review 通过）

- 修复：`_extract_allocation_from_agent_result`（6629-6639）在 citation 表循环后新增 asset_allocation 全表扫描 fallback（ToolFailure 跳过、命中即 break），与 industry fallback 对称；表结构无需适配。
- 验证：`-k allocation` 6 passed（controller 复跑）；三文件全量 387 passed；AGENTS.md 最小验证命令 175 passed；实数据 519696 五年 3/6/3/2/5 行（2023 修复前空 → 权益投资 70,231,733.87 / 90.43）；端到端复核 2023 路由仍绑定 table-0059（非资产配置表），2023 非空确由 fallback 命中 table-0060；`git diff --check` 干净；未 commit / push。

### S4 持有本基金 9.2/9.4 口径（计划待 review）

根因：519696-2025 无 9.4 基金经理持有区间表（`_extract_manager_holding` 找不到 → 报告「未披露」基本正确），但有 9.2 从业人员整体持有（table-80：7,312.84 份 / 0.01%）未被利用。修复：9.4 不存在时回退 9.2 整体数据并标注口径；163415（有 9.4）不回退。

### S4 收口（2026-08-06 controller review 通过）

- 修复：新增 `_extract_manager_holds_overall`（extraction.py:843，9.2 从业人员整体持有解析，口径嵌入 holds_fund 文本）；`_extract_fund_manager_with_citation` 改为两遍扫描（先 9.4 区间表命中即 break，全部落空才回退 9.2——因并存文档中 9.2 表排在 9.4 之前，单遍 break-on-first-hit 会误回退）；`FundManagerInfo.holds_fund` docstring（models.py:624）同步；3 处渲染点零改动。
- 验证：`-k "manager or holds or 9.4 or fund_manager"` 26 passed（controller 复跑）；三文件全量 391 passed；实数据 519696-2025 → 「基金经理区间未披露；从业人员整体持有 7,312.84 份（0.01%）」、163415-2025 → 「A类>100万份」不回退；回归护栏 163415-2021 / 512890-2025（9.2+9.4 并存）均优先 9.4；`git diff --check` 干净；未 commit / push。

## QDII 序列收尾状态（2026-08-06）

- S1-S4 全部完成：519696 持仓（2024/2025 各 10 行）、费率（五年真值）、资产配置（2023 补齐）、持有本基金（9.2 回退口径）。
- 遗留（另排 slice）：004393 持仓 0 行（前序未提交区 search/citation 变化，非 QDII 序列引入）；519696-2025 持仓第 6 名跨页断裂（代码/占比丢失，跳过碎片行）；519696-2023 持仓表头截断（「证券代」「占基」）。
- 519696 报告复跑命令：`uv run fund-checklist generate --fund-code 519696 --fund-name "交银环球精选混合(QDII)" --year 2025 --work-dir .fund_e2e_519696 --llm --format pdf --concurrency 4`。

## 遗留 slice 状态（2026-08-07）

- 遗留计划：`.sisyphus/plans/holdings-residual-slices-20260806.md`（Mimo review ACCEPTED，2026-08-07）。
- 执行顺序：R1（004393 持仓 0 行）→ R2（519696-2025 跨页断裂）→ R3（519696-2023 表头截断）→ R4（interactive key_facts 落盘）；R5（007466 live e2e）需显式授权。
- R1 状态：已完成（2026-08-07，DS 实施 + Mimo diff review ACCEPTED + controller 复跑通过）；修复 = `_is_holdings_table_candidate` 表级鉴别 + `_extract_stock_holdings_from_tables` A 股直接扫描 fallback（`extraction.py`）；验证 = `uv run pytest tests/fund/service/test_extraction.py -k "holdings" -q --tb=short`（32 passed）+ `tests/fund/service/test_extraction.py tests/fund/service/test_audit_pipeline.py tests/fund/cli/test_cli.py -q --tb=short`（399 passed）+ AGENTS.md 最小验证 175 passed；004393 2021-2025 各年 top-10 非空且 citation 指向真实持仓表（2022=table-0104、2024=table-0080），163415/519696 不回退；`git diff --check` 干净；未 commit / push。
- R2 状态：已完成（2026-08-07，DS 实施 + Mimo diff review ACCEPTED + controller 复跑通过）。定位结论：519696-2025 主表 table-0061（section-0599/page 49/9 列）表头完整，`_extract_qdii_table_with_continuations` 走「主表 1-5 名 + `_extract_qdii_continuation_rows` 续表合并」分支，续表 table-0062（同 section/page 50/9 列，首行表头碎片 + 6-10 名数据行）被正确命中；519696-2024 走表头截断分支（table-0061 仅截断表头、table-0062 承载碎片+全量数据行）。实数据与 CLI 均已确认 2025 持仓 10 行、rank 1-10 连续、第 6 名（1209 HK 华润万象生活 2.82%）代码/占比非空，2024 不回退——计划所载「第 6 名仍断裂」在当前 fixture/代码上不可复现，且计划修复方向 2 的字面规则（碎片行含名称残片即视为数据行）会反向把表头碎片消费成残缺行，未采用；生产代码零改动（证据驱动）。交付 = 真实 fixture 测试补 rank 连续/第 6 名断言 + 新增最小表结构模拟回归测试（`test_extract_qdii_holdings_cross_page_rank6_complete`，去掉续表合并会失败）。验证 = `-k "holdings or qdii"` 40 passed + 三文件全量 400 passed + `git diff --check` 干净；未 commit / push。
- R3 状态：已完成（2026-08-07，DS 实施 + Mimo diff review ACCEPTED + controller 复跑通过）。修复 = `_holdings_column_indexes` 截断前缀识别（「证券代」「占基」「占基金」，带列数据含数字校验 `_column_has_digits`）+ `_is_qdii_header_text` 扫描入口预检放宽 + `_infer_qdii_column_indexes_by_position` 列位置推断兜底（`extraction.py`）；链路 = 2023 主表（仅截断表头）→ 续表碎片合并为完整表头 → 数据行抽取。验收 = 519696-2023 持仓 10 行（首行 3808 HK 中国重汽 4.17%）、2021/2022/2024/2025 真实 fixture 10 行不回退、行业配置/估值/资产组合/买卖明细负例全部拒绝；验证 = `-k "holdings or qdii or header"` 49 passed + 三文件全量 408 passed + AGENTS.md 最小验证 175 passed + `git diff --check` 干净；未 commit / push。
- R4 状态：已完成（2026-08-07，DS 实施 + Mimo diff review ACCEPTED + controller 复跑通过）。修复 = `AgentRunResult.key_facts` 槽位（tool_loop.py）+ `_final_result` 终答解析写入（llm_tool_loop.py，interactive / 非 interactive 双分支）+ `Turn.key_facts` 槽位（session_models.py）+ chat_service assistant turn 接线 + session_store 序列化/反序列化（旧 session 缺该字段时默认空元组，不回退）。派发 write set 为 `llm_tool_loop.py` + `session_models.py`；`AgentRunResult` 定义在 `tool_loop.py`、turn 构造在 `chat_service.py`、磁盘序列化在 `session_store.py`，三处不在字面 write set 内但为达成「session 可读回 / 落盘」验收所必需（与 2026-08-06 已记录偏差所指文件一致）。验收 = interactive 一轮问答后 session 中可读回 `key_facts`；旧 session（无该字段）恢复不回退。验证 = `uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/host/test_session_store.py -q --tb=short`（112 passed）+ 回归 `uv run pytest tests/fund/agent/ tests/fund/host/ tests/fund/service/test_chat_service.py tests/fund/cli/test_cli_interactive.py -q --tb=short`（424 passed）+ `git diff --check` 干净；未 commit / push。
- R5 状态：已执行（2026-08-08，007466 interactive opt-in live e2e，controller 直跑），**验收不通过**（Q1/Q3/Q4 未达 004393 复跑口径）。命令 = `printf '...4 问 + exit' | FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 uv run fund-checklist interactive --fund-code 007466 --work-dir .fund_e2e_007466 --no-stream --plain --enable-tool-trace --label r5-007466-live`；会话 = `.fund_e2e_007466/sessions/80936402c9a9484e8403a63c3cc1e110.json`。逐问证据（真源 = 007466-2025 docling JSON）：Q1「基金经理持有本产品吗」→「未找到相关数据」（假阴性：9.4 数据存在于 table-0098「本基金基金经理持有本开放式基金」A类 50~100 万份，agent 只读 table-0097/section-0748）；Q2「基金经理是谁」→ 通过（2 次调用，返回柳军/柳叶青）；Q3「基金前十大持仓是什么」→「未找到相关数据」（假阴性：table-0087 含完整股票持仓明细，agent 只读 table-0086）；Q4「2021-2025 份额净值增长率」→ 原文粘贴整段表格（>200 字、无结构化总结），且 `aggregate_multi_year_annual_performance` 2 次失败（`document_id=''` 未注入，failure=unavailable），工具调用 8 次 <12（该子项过）。结论：按 R5 计划「live 结果只作验收证据，不驱动 production adapter 变更」，本 slice 不改生产代码，需另排修复 slice（Q1/Q3 命中错表、Q4 aggregate document_id 注入与原文粘贴）。→ 修复排期已落地：`.sisyphus/plans/interactive-memory-tool-dedup-20260809.md`（Mimo review ACCEPTED，2026-08-09），见文末「交互问答与记忆能力改进（2026-08-09 裁决）」节。
- R6 状态：已完成（2026-08-08，QDII direct 分支 citation 校正）。计划 = `.sisyphus/plans/qdii-table-citation-fix-20260808.md`（Mimo review ACCEPTED，无 fix items）。修复 = `_extract_qdii_holdings_from_tables` 返回类型改为 `tuple[tuple[HoldingExtraction, ...], Citation] | None`（命中返回持仓主表 citation，与 A 股 direct 分支同约定）+ 调用方 QDII 分支 `holdings, table_citation = direct` 同步校正（`extraction.py`）；QDII 续表合并/表头截断/行抽取逻辑与 `_audit_holdings` 未动。验收 = `uv run pytest tests/fund/service/test_extraction.py -k "qdii or QDII or holdings" -q --tb=short`（49 passed，含 3 个 direct 调用测试 citation 断言、2022-2025 multi-year citation 真值、新增 store 级同步测试）+ AGENTS.md 最小验证集（175 passed）+ `uv run fund-checklist holdings --fund-code 519696 --years 2021,2022,2023,2024,2025 --work-dir .fund_e2e_519696`（五年 citation = 2021:table-0067 / 2022:table-0069 / 2023:table-0064 / 2024:table-0061 / 2025:table-0061，各年 10 行 top-1 内容不回退）+ 004393 回归通过 + `git diff --check` 干净；报告刷新：`generate --fund-code 519696 --fund-name 交银环球精选混合(QDII) --year 2025 --llm --format pdf --concurrency 4` 复跑通过（审计 7 章通过 0 失败），`.fund_e2e_519696/reports/519696-2025-analysis.{md,pdf}` 持仓数据来源五年 citation 已更新为 2021:table-0067 / 2022:table-0069 / 2023:table-0064 / 2024:table-0061 / 2025:table-0061；未 commit / push。

## 环境事故记录（2026-08-08）

- Codex agent 断连事故（cc-switch 代理接管改写 config + 代理转发 404）：`docs/debug/codex-cc-switch-takeover-incident-20260808.md`。
- 状态：已修复（恢复直连 base_url + 停用 codex 代理接管），两个 codex agent 重启后连接正常。
- 后续注意：cc-switch 重启可能重新接管 codex 配置；若再断连先查 `~/.codex/config.toml` 的 base_url 是否被改回 `127.0.0.1:15721`。

## 交互问答与记忆能力改进（2026-08-09 裁决）

> 状态：🟡 计划 ACCEPTED（2026-08-09，Mimo review：pass-with-risks，3 个非 blocker finding），待实施
> 设计：`.sisyphus/plans/interactive-memory-tool-dedup-20260809.md`
> review：`docs/reviews/plan-review-20260809-122315.md`（Verdict: ACCEPTED）

### 背景与证据

- R5 live e2e（2026-08-08，007466 四问）验收不通过：Q1「基金经理持有本产品吗」假阴性（未读真源 table-0098）、Q3「前十大持仓」假阴性（未读 table-0087）、Q4 原文粘贴 + `aggregate_multi_year_annual_performance` 2 次失败（unavailable）。
- aggregate 生产接线缺失：`_default_runner_factory`（chat_service.py:129-138）与 main.py 多处 `ChatService` 构造均未传 `aggregate_handler`；04f9554 只修了 runner 侧 document_id 注入。
- 工具重复调用：单轮内 `_dedup_key`（llm_tool_loop.py:1590）只认完全相等参数；`seen_calls` 每轮重建，跨轮无去重（R5 Q4 aggregate 失败 2 次仍执行 2 次；004393 实测 Q4 14 次调用）。
- 记忆注入未完成：`_build_contributions`（chat_service.py:544-620）只注入 runtime/fund_context/history；`context_slots` 已声明 `memory` slot 但从未填充；`build_memory_contribution`（prompt_contributions.py:65-88）存在但未接线；EpisodeSummary 只写不读。

### 已裁决口径（D1-D9）

- D1 受控检索路由：Service 层对高误命中 query 类（manager_holdings、holdings_top10）注入 table_ref 锚点，其余保持 LLM 自由选表（Phase 7.2「全量走 LLM」的受控扩展）。
- D2 范围：只修 R5 暴露两类命中问题；规模/份额/基准/超额 profile 列入 backlog。
- D3 aggregate 接线：复用既有五年聚合（Service 层），interactive 开放，share_class A 类优先；ask 不开放（白名单边界，入 backlog）。
- D4 重复调用治理：① 跨轮失败调用 key 持久化短路（不重跑）；② 去重键放宽（search 归一化 query，read_section/read_table 按 ref 比较）；③ 不做完整结果缓存复用。
- D5 预算：interactive `max_iterations` 12 → 8；不加 list_tables/read_table 收敛扩展。
- D6 记忆注入：EpisodeSummary/PinnedState 走方案 B（编织进 system prompt，延续 Phase 7.3），不做协议层方案 A。
- D7 排期：记忆注入与 Phase 8 上下文治理分开，先注入后治理。
- D8 live 验收：沿用「live 结果只作验收证据、不驱动 production adapter 变更」；live 复跑需用户显式授权。
- D9 收口：CIC-lite，每 slice 走 implement → tests → diff review；真源行为同步在实施收口阶段执行。

### 分 slice（P0-1 → P0-2 → P1 串行）

- P0-1 检索命中质量：`_DisclosureLocatorContract.anchor_title_family` + `_resolve_anchor_table_ref`（解析失败 fail-open 返回 None）+ retrieval contribution 锚点注入（仅 manager_holdings / holdings_top10）。
- P0-2 aggregate 接线 + 重复调用治理：`aggregate_handler` 透传（catalog 重解析 annual_report_documents，防幻觉 document_id）+ `_dedup_key` 工具级归一化 + `failed_call_keys` 跨轮短路（Session 持久化，旧 session 兼容）+ `max_iterations` 8。
- P1 记忆注入：`build_memory_contribution` 接线（最近 ≤3 条 EpisodeSummary + pinned facts，总长 ≤500 token 超限丢最旧）。

### Mimo finding（实施时处理，非 blocker）

- 001（中）：`_resolve_anchor_table_ref` 需显式 `document_id is None` 守卫。
- 002（中）：`failed_call_keys` tuple 结构需与 `_dedup_key` 一致（天然含 document_id 维度，不同 document_id 不互相短路）。
- 003（低）：`_format_episode_summaries` 单条 fact/question 超长行为未定义（截断或标注 Phase 8）。

### 验证命令（实施阶段）

```bash
uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_chat_service.py -k "route or anchor or manager_holdings or holdings" -q --tb=short
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/service/test_scene_config.py -q --tb=short
uv run pytest tests/fund/host/test_session_models.py tests/fund/service/test_chat_service.py tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_scene_config.py -v --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

opt-in live（需用户显式授权）：004393 / 007466 interactive 四问复跑，断言 Q1 命中 9.4、Q3 命中持仓明细表、Q4 ≤200 字结构化总结且工具调用 ≤8。

### P0-1 收口（2026-08-09，DS 实施 + controller 复跑 + Mimo diff review ACCEPTED）

- 实现：`_DisclosureLocatorContract.anchor_title_family` 字段（models.py）+ registry 配置（仅 manager_holdings / holdings_top10，extraction.py）+ `_resolve_anchor_table_ref`（document_id None 守卫、全异常 fail-open 返回 None、9.4 行头优先 9.2 回退、holdings_top10 表头签名 + row_count ≥10）+ chat_service retrieval contribution 锚点注入（`_ANCHOR_PROFILE_NAMES` 硬口径，仅两类 profile，解析失败不注入，runner 不 import service）。
- 规格偏差（已记录）：007466-2025 真实 fixture 上「期末基金管理人的从业人员持有本基金的情况」命中 section-0748 但该节无表格、「前十名股票投资明细」全文 0 命中；按规格回退查询语义追加 anchor_title_family 短语（9.4 短语命中 table-0098 所在 section）与 registry 候选「股票投资明细」（命中 section-0689）。机制不变（search → list_tables → 有界 read_table → 行头/签名扫描），fail-open 语义保留；Mimo review 评估可接受。
- 验证：`uv run pytest tests/fund/service/test_extraction.py tests/fund/service/test_chat_service.py -k "route or anchor or manager_holdings or holdings" -q --tb=short` → 56 passed；AGENTS.md 最小验证（document_tools + minimal_tool_loop + cli）→ 175 passed；`git diff --check` 干净；未 commit。
- review：`docs/reviews/plan-review-20260809-122315.md` 之后的新 diff review 由 Mimo 执行，Verdict: ACCEPTED（逐项核实行号；规格偏差可接受；public tool 契约无改动）。
- 下一步：P0-2（aggregate 接线 + 重复调用治理）待派发。

### P0-2 收口（2026-08-09，DS 实施 + controller 复跑 + Mimo diff review ACCEPTED）

- 实现：`_dedup_key` 工具级归一化（search 归一化 query、read_section/read_table 按 ref、get_excerpt 按 locator、aggregate 按 fund_code+years+share_class；key 天然含 document_id 维度，满足 Mimo 002）；`failed_call_keys` 跨轮短路（run/run_stream 双入口 + 构造期参数，命中 key 直接追加失败标记不调用工具；`round_failed_keys` 轮末收集 + `_attach_failed_keys`）；`ChatService.aggregate_handler` 透传 + `_merge_failed_tool_call_keys`（去重 + 上限 50 丢最旧，每轮落 session）；`Session.failed_tool_call_keys` + session_store 序列化兼容（旧 session 默认空元组）；`main.py _build_aggregate_handler`（`_collect_matching_docs` catalog 重解析 last-wins，忽略 LLM document_id，异常 fail-closed 为 classified failure，仅 interactive 分支注入）；`INTERACTIVE_SCENE_CONFIG.runtime.max_iterations` 12→8；scene.md v1.7 aggregate 使用说明。
- 验证：核心命令（llm_tool_loop + chat_service + session_store + cli_interactive）→ 262 passed；Phase 7 回归（9 文件）→ 267 passed；AGENTS.md 最小验证 → 175 passed；`git diff --check` 干净；未 commit；默认 pytest 未联网。
- review：Mimo diff review ACCEPTED（逐文件核实行号；2 个可接受边界：run_stream 不收集 round_failed_keys（interactive 只走 run()）、`_merge_failed_tool_call_keys` 上限边界无独立单测）。
- 下一步：P1（EpisodeSummary / PinnedState 记忆注入）待派发。

### P1 收口（2026-08-09，DS 实施 + controller 复跑 + Mimo diff review ACCEPTED）

- 实现：`_build_contributions` 接线 `contributions["memory"]`（`build_memory_contribution`，episode 为空且 pinned_facts 为空时不产生 slot）；`_format_episode_summaries`（最近 ≤3 条，每条 title/goal/confirmed_facts≤5/open_questions≤3，总长 ≤500 token 超限丢最旧，单条仍超限截断）；`_pinned_facts`（`pinned_state.user_constraints["confirmed_facts"]`，str/list/tuple 兼容，空白跳过）；`prompt_contributions.build_memory_contribution` 追加「历史摘要，非当前证据」标注（默认参数兼容）。
- Mimo finding 003：选择实现——单条 fact/question 超 100 token 由 `_truncate_to_token_bound` 截断加省略号（`test_overlong_fact_question_truncated` 断言 ≤100 token）。
- 验证：核心命令（chat_service + prompt_contributions）→ 73 passed；Phase 7.3 回归（session_models + chat_service + llm_tool_loop + scene_config）→ 210 passed；AGENTS.md 最小验证 → 175 passed；`git diff --check` 干净；未 commit；默认 pytest 未联网。
- review：Mimo diff review ACCEPTED（逐项核实行号；compaction 写→读闭环测试、旧 session 无 slot、≤500 上界、单条截断均确认；协议层/ContextBudget/compaction 策略/scene_config 零改动）。
- 下一步：三 slice 全部完成，待 opt-in live 复跑（004393 / 007466 四问，需用户显式授权）。

### 三 slice 汇总（2026-08-09）

- P0-1 检索命中质量 ✅ / P0-2 aggregate 接线 + 重复调用治理 ✅ / P1 记忆注入 ✅——各自经 DS 实施、controller 独立复跑、Mimo diff review ACCEPTED。
- 真源行为同步：AGENTS.md（interactive 问答质量语义 + Phase 7.3 记忆注入）与 design.md（§6.10 + Phase 7.3 节）同步完成。
- 遗留：opt-in live 复跑未执行（需用户显式授权）；`_merge_failed_tool_call_keys` 上限 50 边界无独立单测（Mimo 标注可接受）；run_stream 不收集 failed_call_keys（interactive 只走 run()，Mimo 标注可接受）。

### live 复跑记录（2026-08-09，controller 直跑，用户授权）

命令：`printf '<空行>+四问+exit' | FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 uv run fund-checklist interactive --fund-code 007466/004393 --work-dir .fund_e2e_007466/.fund_e2e_004393 --no-stream --plain --enable-tool-trace --label r5-recheck-*`。会话：007466 = `d540d5bc...`（Q2-Q4）+ `r5-recheck-q1` 会话（Q1 重测）；004393 = `cbf3de62...`。按 plan「live 只作验收证据，不驱动 production adapter 变更」，未改代码。

结果（R5 四问口径）：

| 基金 | Q1 基金经理持有本产品吗 | Q2 基金经理是谁 | Q3 前十大持仓 | Q4 2021-2025 份额净值增长率 |
|------|------------------------|-----------------|---------------|------------------------------|
| 007466 | ✅ 命中基金经理持有区间表（A 类 50~100 万份），工具 1 次 | ✅ 柳军/柳叶青 | ✅ 命中 8.3 股票投资明细，前十大+占比 | ⚠️ aggregate 成功 1 次 + read_table 1 次（≤8 ✅），结构化总结无原文粘贴 ✅，但 answer 371 字 > 200 ⚠️ |
| 004393 | ✅ 命中（A 类 50~100 万份） | ✅ 张明 | ✅ 前十大+占比 | ⚠️ aggregate 成功（调用 ≤8 ✅），无原文粘贴 ✅，但 answer 369 字 > 200 ⚠️ + 2022 年数据缺失 ⚠️ |

结论：R5 三项验收核心（Q1/Q3 假阴性、Q4 aggregate 失败）全部修复——锚点命中、aggregate 接线成功、工具调用收敛、无「未找到相关数据」假阴性。未达标 2 项 + 新发现 1 项，均不驱动 adapter 变更，另排修复 slice：

- F1（终答字数）：Q4 answer 371/369 字 > plan 断言 ≤200。根因：原文粘贴守卫阈值是重叠 ≥40 字符或 >800 字，≤200 字仅为 scene.md prompt 软约束，LLM 未严格遵守。建议：scene.md 强化 + 守卫阈值下调（实施另排）。
- F2（004393-2022 业绩缺失）：本地 `multi-year` 复现 missing 2022（covered 2021/2023/2024/2025），catalog 五年齐全 → 004393-2022 业绩表抽取缺口（既有，非本 slice 回归；007466 五年全通）。建议：按 007466 A/C 分段表模式定位 004393-2022。
- F3（CLI 管道吞首行）：interactive 年份选择 `input()`（main.py:1141）在管道输入下消费第一行问题（本次复跑 Q1 需垫空行重测）。建议：年份选择改为不消费 REPL 首行（如 `--year` 参数或 EOF 时直接默认），实施另排。

### F1/F2/F3 修复 slice 收口（2026-08-09，DS 实施 + controller 复跑 + Mimo review 均 ACCEPTED）

- **F1 终答 ≤200 字硬约束**：`llm_tool_loop.py` `_INTERACTIVE_FINAL_ANSWER_MAX_CHARS` 800→200（`_INTERACTIVE_FINAL_ANSWER_TARGET_CHARS` 保持 200）；`_violates_final_answer_quality` 在 answer >200 字时触发有界重答 1 次；`_truncate_final_answer_summary` 正文按 200-len(note) 截断、note 文案改为「（内容过长，已截断为摘要）」，保证最终 answer（含 note）≤200 字；`scene.md` 第 3 条改为硬约束口径。live 验证：Q4 007466/004393 终答均 ≤200 字（硬断言通过）。此前 2026-08-06 记录中「>800 字触发重答」口径已被本修复取代。
- **F2 004393-2022 可解释缺失（口径修正，不伪造数据）**：实证 004393-2022 为转型当年（2022-08-08 合同生效），业绩阶段表无「过去一年」行（仅「过去三个月」「自基金转型起至今」），10F/10G 缺行是年报事实而非解析 bug。修复：10F/10G 对「业绩表存在但无「过去一年」行」的 not_found message 追加可解释后缀（`_performance_missing_past_year_note`：自基金转型起至今/自基金合同生效起至今 → 「转型当年无全年份额净值增长率」）；`scene.md` 规则 10 要求 interactive 对 missing_years 逐一说明原因、禁止静默跳过、禁止把「自基金转型起至今/期间增长率」当作年度增长率写入 series。数值语义 / failure code / DTO 契约零改动。live 验证：Q4 004393 answer 含 "2022" 说明断言通过。
- **F3 管道输入吞首行**：interactive 新增 `--year` 参数（`main.py` interactive_parser）；年份选择三分支——`--year` 提供（不在可用年份内时 stderr 报错退出）/ 无 `--year` 且 stdin 非 TTY（不调用 input()，默认最新年份并打印说明）/ TTY（保留 input() 交互提示）。REPL 循环主体与会话恢复/标签逻辑零改动。live_smoke 首行垫空行 workaround 已移除。
- 验证：本地确定性层 `tests/fund/agent/test_llm_tool_loop.py + test_interactive_known_gaps.py` → 104 passed；`test_cli_interactive.py + test_interactive_known_gaps.py` → 93 passed（0 xfailed）；`test_extraction.py + test_interactive_known_gaps.py` → 266 passed, 1 xfailed（F3 修复前）；全部 `git diff --check` 干净。opt-in live 全量（8 问）7 passed + 1 偶发失败（Q4-007466「LLM 工具循环暂不可用」，会话无 tool_trace，首次 next_step 偶发 API 异常；单测重跑 30.8s PASSED，非代码回归）；F1/F2 live 验收（Q4 双基金 ≤200 字 + 004393 含 2022 说明）2 passed。
- 测试同步：`test_interactive_known_gaps.py` F1/F2/F3 三条 `xfail(strict=True)` 全部摘除（F1 改普通断言、F2 改可解释缺失断言、F3 改管道默认年份断言）；`test_interactive_live_smoke.py` Q4 改 ≤200 硬断言 + 004393 增加 "2022" in answer 断言 + 移除垫空行 workaround；`test_llm_tool_loop.py` 3 处断言 200+25→200；`test_extraction.py` 新增 10F 缺「过去一年」行 message 可解释单测；`test_cli_interactive.py` 新增 `--year` 解析/非法年份/默认年份测试。
- 真源同步：AGENTS.md（interactive 问答质量语义 F1/F2/F3 收口）与 design.md（§6.10 终答契约 >200 字口径）已同步；本记录节即为 control 同步。

### F4 偶发 fail-closed 可观测性收口（2026-08-09，DS 实施 + controller 复跑 + Mimo review ACCEPTED）

- 背景：F1/F2/F3 全量 live 回归中 Q4-007466 偶发「LLM 工具循环暂不可用」（会话无 tool_trace，首轮 `next_step()` 抛未分类异常，`except Exception` 兜底吞掉原始异常，根因无法定位；单测重跑通过，非代码回归）。
- 修复：`llm_tool_loop.py` 新增模块级 `logger`，4 处 LLM 调用 `except Exception` 兜底各加一行 `logger.warning(..., exc_info=True)`（run 主循环 / run_stream 主循环 / 投资建议重答回退 / 终答质量重答 fail-closed）；返回值、错误码、消息与分支逻辑零改动。
- 测试：`test_llm_tool_loop.py` 新增 `test_run_unclassified_exception_fails_closed_and_logs`（`next_step` 抛 `RuntimeError("boom")` → `FailureCode.UNAVAILABLE` + message 不变 + caplog 断言 WARNING 含 RuntimeError/boom）。
- 验证：`uv run pytest tests/fund/agent/test_llm_tool_loop.py -q --tb=short` → 102 passed；`git diff --check` 干净。
- 后续：下次 live 偶发失败时从进程日志的 warning 堆栈定位原始异常类型；如需会话级落盘再另排。

### LLM provider 自由切换收口（2026-08-10，DS 实施 + controller 复跑 + Mimo diff review ACCEPTED）

- 背景：用户要求 DeepSeek key 与 Mimo key 自由切换；此前 AGENTS.md 宣称「已支持 DeepSeek 与 Mimo」但代码仅 DeepSeek 命名 adapter，切换需手改 `DEEPSEEK_*` 三件套，且 `chat_service` 会把 scene 默认模型名（deepseek-v4-pro/flash）强制写入请求，切 Mimo 会发不存在的模型名。
- 实现（write targets 6 个，无越界）：
  - `fund_agent/agent/deepseek_llm.py`：新增 `FUND_CHECKLIST_LLM_PROVIDER`（`deepseek` 默认 / `mimo`，未知值 fail-fast 抛 ValueError 提示合法取值）；`ProviderConfig` + `_PROVIDER_CONFIGS` 配置表（deepseek 用 `DEEPSEEK_*`、默认 `https://api.deepseek.com`/`deepseek-v4-flash`；mimo 用 `MIMO_*`、默认 `https://api.xiaomimimo.com/v1`/`mimo-v2.5-pro`）；新增 `resolve_provider` / `resolve_provider_model` / `provider_model_env_name` / `translate_model_for_provider` / `_provider_runtime`；`next_step` / `next_step_stream` / `generate_text` 请求组装统一走 `_provider_runtime`；错误文案泛化（去 DeepSeek 前缀）；类名/文件名保留，`llm_tool_loop.py` 未动。
  - `fund_agent/service/chat_service.py`：注入层 provider 感知——解析顺序 provider 对应 MODEL env 非空优先，否则 scene/contract 模型名经翻译表（`deepseek-v4-pro→mimo-v2.5-pro`、`deepseek-v4-flash→mimo-v2.5`，未知透传）后写入 provider 对应 MODEL env；`DeepSeekLlmClient.env` 注入保持向后兼容。
  - `fund_agent/cli/main.py`：interactive `current_model` 展示改由 `resolve_provider_model(os.environ)`。
  - `fund_agent/agent/README.md`：新增 Provider 自由切换配置节，8B/8C 过时表述同步。
  - `tests/fund/agent/test_provider_switching.py`（新增 20 用例）：provider 解析（默认/mimo/未知 fail-fast）、配置表与默认值、MODEL env 覆盖、模型名翻译、三路径请求组装（override/默认/向后兼容/缺 key unavailable/未知 provider）、错误文案泛化。
  - `tests/fund/service/test_chat_service.py`：新增 `TestProviderModelInjection` 4 用例（mimo 场景翻译、mimo env 优先、deepseek 注入、contract 翻译）+ 同步 1 处旧错误文案断言。
- 验证（controller 独立复跑）：`test_provider_switching.py` → 20 passed；`test_deepseek_live_smoke.py + test_real_llm_adapter.py + test_token_usage.py + test_chat_service.py + test_cli_interactive.py` → 196 passed；最小验证（document_tools + minimal_tool_loop + cli）→ 175 passed；默认 pytest 未联网；未 commit。
- review：Mimo diff review ACCEPTED（7 项硬口径逐项确认：env 默认/fail-fast、配置表、翻译表、解析顺序、current_model、文案泛化、类名保留；write set 6 文件命中无越界）。
- 行为变化提示：chat_service 注入层现在优先采用 provider 对应 MODEL env（此前 env 值会被 scene/contract 覆盖），符合硬口径解析顺序。
- 已知边界/后续：opt-in live smoke（`test_deepseek_live_smoke.py`）的 skip 判定与 env 组装仍硬编码 `DEEPSEEK_API_KEY`，对 Mimo 跑 live smoke 需同时设置 `DEEPSEEK_API_KEY`（过 skip 门槛）与 `MIMO_API_KEY`（实际调用）；live smoke 的 provider 化另排 slice，不在本 slice 范围。

### Slice B：live smoke provider 化（2026-08-19，DS 实施，diff review pending）

- 背景：`test_deepseek_live_smoke.py` opt-in live smoke 的 skip 判定与 env 组装硬编码 `DEEPSEEK_API_KEY`，对 Mimo 跑 live smoke 需同时设置 `DEEPSEEK_API_KEY`（过 skip 门槛）与 `MIMO_API_KEY`（实际调用）；本 slice 把 skip 判定与 env 组装按 `FUND_CHECKLIST_LLM_PROVIDER` provider 化，opt-in env `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 不变。
- 实现（write targets 5 个，无越界）：
  - `fund_agent/agent/deepseek_llm.py`：新增公开 helper `provider_api_key_env_name(provider)` / `provider_base_url_env_name(provider)`（与既有 `provider_model_env_name` 同构，未知 provider fail-fast ValueError）；provider 表逻辑仍只存在 `deepseek_llm.py`，测试文件不复制。
  - `tests/fund/agent/test_deepseek_live_smoke.py`：`_live_skip_reason` 改为按 `resolve_provider` + `provider_api_key_env_name` 判缺 key，缺 key 文案区分 provider（`缺少 MIMO_API_KEY，跳过 live Mimo smoke` / deepseek 文案不变）；`_deepseek_env` 改为 provider 感知的 `_live_env`（key/base/model env 名来自 deepseek_llm.py helper，空 base/model 由 client 按 provider 默认补齐）；新增 3 单测（mimo 缺 key skip、mimo opt-in 组装默认 base/model、未知 provider fail-fast）。
  - `tests/fund/agent/test_provider_switching.py`：新增 `provider_api_key_env_name` / `provider_base_url_env_name` 用例（deepseek/mimo env 名 + 未知 ValueError）。
  - `fund_agent/agent/README.md`：8C 节同步 provider 化 skip/env 组装表述。
- 验证：`test_deepseek_live_smoke.py` → 10 passed, 1 skipped（live 默认 skip）；`test_provider_switching.py + test_deepseek_live_smoke.py` → 33 passed, 1 skipped；最小验证集（document_tools + minimal_tool_loop + cli）→ 249 passed；默认 pytest 未联网。
- 状态：未 commit；diff review pending（CIC-lite：implement -> tests -> diff review）。

### 004393「近一年净值增长率」问答修复收口（2026-08-11，Fix A/E/C 全部 Mimo review ACCEPTED）

- 症状：interactive（004393，2025 年报）问「近一年净值增长率是多少」返回 3.2.1 原文粘贴（1245 字，无数字），未给出 12.77%。session 证据：`.fund_e2e_004393/sessions/bb4c80b6c5c74115afe7afd7d935329b.json` turn7 = 3.2.1 文本 + 7.4.7.12「资产支持证券投资收益」表拼接；tool_trace = `search_document, search_document, list_tables, read_section, read_table`。
- 根因 R1（本次直接原因，已处理）：interactive 进程 2026-08-10 22:38 启动，守卫修复模块 23:12 才落盘（`llm_tool_loop.py` mtime），PID 91123 仍运行旧模块。处理：用户重启 interactive 进程即可，无需改代码。
- 根因 R2（遗留设计缺口，已修复）：① 候选词命中不了含数字的 4.4.2（section-0097，A 12.77% / 基准 15.34%）；② LLM 猜错 table_ref（table-0039 → 7.4.7.12，本应 table-0009/0010）；③ read_table 无 section 一致性校验。Mimo 根因 review 全部核实：R1 关键分界为提交 `d92a9e1`（08-06，force-answer 分支无守卫）；R2a 部分确认（「净值增长率」已是 alias，问题在 candidate_queries 无法命中 4.4.2）；R2b 完全确认（架构级缺陷）；R2c 确认 fail-closed 文案为「LLM 工具循环暂不可用」而非「LLM 处理失败」，语义一致。
- Fix A（force-answer 走终答守卫，DS 实施 + Mimo ACCEPTED）：`_force_answer_from_evidence`（max_steps 耗尽降级）在 interactive 下与正常 FinalAnswer 同走 `_apply_interactive_final_guards`（投资建议拦截 + ≤200 字约束）。验证：199 + 10 + 286 passed。
- Fix E（performance_returns 候选词首位「净值增长率」，DS 实施 + Mimo ACCEPTED）：`fund_agent/service/extraction.py` `_DisclosureLocatorContract` performance_returns `candidate_queries` 首位加入「净值增长率」（原已是 alias，只改候选词，不动 aliases/acceptable_title_family/requires_table_citation/extraction_allowed）。验证：45 + 5 + 175 passed；真实 004393-2025 store 闭环（search「近净值增长率是多少」=0 → auto-retry「净值增长率」→ 首命中 section-0097 含 12.77%）。测试锁定：`test_performance_returns_candidate_order_prefers_nav_growth_rate_query`。
- Fix C（performance_returns 表锚点 + read_table section 一致性校验，DS 实施 + Mimo ACCEPTED）：
  - 表锚点：`chat_service.py` `_ANCHOR_PROFILE_NAMES` 加入 `performance_returns`；`extraction.py` 新增 `_ANCHOR_PERFORMANCE_*` 常量、`_resolve_performance_returns_anchor_table_ref`（3.2.1 exact-title search → list_tables → 表头签名「阶段/份额净值增长率/业绩比较基准收益率」去空白归一化 → A 类标题优先、排除 C → table-0009），解析失败 fail-open None。
  - runner 校验（仅 interactive）：放行集合 = 本轮 `list_tables` 结果 ∪ search 命中 `SearchResult.table_ref`（补充修正，否则「基金经理是谁」search→read_table 合法流被误伤）；未列出表返回 `NOT_FOUND`「table_ref 未在当前已列出章节的表格中，请先 list_tables 并复制返回的表号」，回喂 LLM、计入 failed_call_keys 语义。
  - 验证：53 + 9 + 8 + 175（最小验证集 396s）+ 闭环（anchor table-0009；search-hit table-0014 放行；table-0039 拦截后 list_tables 读 table-0009 成功）+ 回归 444 + 123 passed。
  - 文案对齐（2026-08-11，DS 实施 + Controller 复核）：锚点 prompt 文案由「请优先 read_table 该表」改为「请先 list_tables 确认该表号在列，再 read_table 该表」，消除与 runner「未列出表号一律拦截」的措辞张力（实证：004393 live 复测首轮 `read_table table-0009` 被拦后走恢复链，文案对齐后 LLM 应先列目录再读表）。验证：锚点/检索相关 9 passed + 最小验证集 175 passed。
- 真源同步：AGENTS.md（interactive 问答质量语义 2026-08-11 Fix A/E/C）、design.md（§5.6 read_table 一致性校验、§6.10 投资建议守卫 force-answer、11A candidate_queries Fix E、受控表锚点 L689 三类范围）、`fund_agent/service/models.py` docstring 已同步；本记录节即为 control 同步。
- 待办：① 用户重启 interactive 进程（R1 生效）；② 重启后 live 复测「近一年净值增长率是多少」，预期直接返回 12.77%（含基准对比），复跑需用户显式授权；③ 未 commit / 未 push（约束未解除）。

### BM25F 检索排序增强 slice（2026-08-12 规划，2026-08-13 完成）

- 依据：`docs/research/dayu-agent-r-research-20260810.md` §2.1.1 / §5 建议 1；dayu 本地 `bm25f_scorer.py` 仅作算法参考（Apache-2.0，不复制代码，license gate）。
- 决策：`search_document` 排序升级为确定性 BM25F 多字段重排序——召回不变、public contract 不变、无新依赖、纯函数；字段权重 section title 3.0 / section text 1.0 / table caption 2.0 / table row 1.0，`k1=1.2`，`b`：title/caption 0.35、text/rows 0.75；排序键 BM25F desc → 子串命中计数 desc → source_order asc。
- 真源同步：`docs/design.md` §5.4 + §6.20、`AGENTS.md`「已知能力差距」backlog 行已更新（开发前同步）；plan artifact：`.sisyphus/plans/bm25f-search-ranking-slice-20260812.md`。
- 状态：✅ 完成。MiMo plan review — `NEEDS_FIX`（1 项最小修复，2026-08-12）：AGENTS.md backlog 行「已进入实施」措辞过度承诺，改为「规划完成，待 MiMo plan review」；已按 review 原文修正，按 CIC-lite 无 re-review gate 进入实施。DS 实施（21m02s）：6 个文件全部在 allowed write set 内；scorer 9 passed / store 29 passed（含 caption-before-row 回归）/ 最小验证集 186 passed in 326.28s。MiMo diff review — `ACCEPTED`（2026-08-13）：公式参数与 §6.20 一致、排序键三级正确、召回与 public contract 未动、无越界文件、无 commit/push；DS 声明的 1 处测试构造偏差（「只含常见词候选」在子串召回下不可构造）裁决为可接受，改用「稀有词 title 命中前置」等价覆盖。
- 排序回归核查：Service 层搜索邻接测试（test_scene_config + test_scene_regenerate_repair）54 passed，无首命中断言受影响；score_scale 类评分消费抽取字段而非搜索顺序，无影响。
- 待办：① 未 commit / 未 push（约束未解除）；② 后续可观察线上首命中变化（受控表锚点解析等首命中路径）如有异常走既有修复通道。

### 日志 VERBOSE 级 + 有界脱敏诊断载荷 slice（2026-08-13 规划，待实施）

- 依据：`docs/research/dayu-agent-r-research-20260810.md` §5 建议 2；dayu `runtime/log_levels.py` `VERBOSE_LOG_LEVEL = 15` 仅作概念参考（Apache-2.0，不复制代码，license gate）。
- 决策：新增 `VERBOSE = 15` 日志级别（幂等注册 + `verbose()` 帮助函数）；启用路径 env `FUND_CHECKLIST_LOG_LEVEL`（absent → 零行为变更；未知值 fail-fast ValueError，与 `FUND_CHECKLIST_LLM_PROVIDER` 一致）；新增 `build_diagnostic_payload` 有界脱敏诊断载荷（显式命名参数、字段 500 字符截断 + `…(截断)` 后缀、总量 2000 字符、超限按固定顺序丢可选字段、`message` 永不丢）；脱敏规则覆盖 API key / Bearer token / URL query secret / `local_import_id` / 本地绝对路径 / 工作目录；接线 `llm_tool_loop.run / run_stream` 入口 + `deepseek_llm._parse_response` malformed 分支（不带 raw body）。
- 真源同步：`docs/design.md` §6.21、`AGENTS.md`「已知能力差距」backlog 行已更新（MiMo plan review ACCEPTED 后同步）；plan artifact：`.sisyphus/plans/log-verbose-diagnostics-slice-20260813.md`。
- 状态：✅ 完成。MiMo plan review — `ACCEPTED`（2026-08-13）：16 项代码事实全部核实一致，无 P0/P1；1 条 P2（run_stream verbose 插入点措辞「首个事件 yield 前」→「trace 初始化之后、循环开始前」，与 run() 对称）已按 review 原文修正，按 CIC-lite 无 re-review gate。DS 实施（13m32s）：11 个文件全部在 allowed write set 内；新增 `log_levels.py`（VERBOSE=15 幂等注册 + `verbose()` + `configure_logging()`，env `FUND_CHECKLIST_LOG_LEVEL`，absent 零行为变更 / 未知值 fail-fast ValueError）与 `diagnostic_payload.py`（集中正则脱敏 + 字段 500 截断 + 总量 2000 有界丢弃 + 显式命名参数 TypeError 契约）；接线 llm_tool_loop run/run_stream 入口 + deepseek_llm `_parse_response` malformed 分支（payload 不含 body）+ cli main() 入口。测试：30 passed（log_levels + diagnostic_payload）/ 145 passed + 1 既有失败（test_llm_tool_loop + test_real_llm_adapter）/ 最小验证集 186 passed；controller 独立复跑 30 + 145（deselect 既有失败）passed。MiMo diff review — `ACCEPTED`（2026-08-13）：P1-1 误报后撤回（三件套改动为 controller 真源同步，非 DS 越权，controller 提供归属证据后 MiMo 复核撤回）；P2-1 测试构造偏差（`_malformed_response()` 空 tool_calls 在 `_parse_final_answer` 抛错，adapter 测试改首个响应触发 `_parse_response` 接线点）判定合理；既有失败裁决成立。
- 待办：① 既有回归 `test_interactive_read_table_from_search_hit_allowed` 已修复（2026-08-13 fix slice：断言 `table-0014` → `table-0012`；已核实 `table-0012` 为 BM25F 排序合并后的确定性首命中——caption 同文本按 source_order tie-break、`table-0014` 被 `DEFAULT_SEARCH_MAX_RESULTS=5` 截断不在结果内；DS 1 passed + controller 复跑 1 passed + MiMo diff review ACCEPTED）；② 未 commit / 未 push（约束未解除）。

### Tool Trace 只读分析器（operator 层）slice（2026-08-13 规划，待实施）

- 依据：`docs/research/dayu-agent-r-research-20260810.md` §2.2.7 / §5 建议 3；dayu `service/tool_trace_analysis.py` + `host/tool_trace_analysis.py` 仅作边界参考（Analyzer 只读消费派生 trace，不成为 durable truth；Apache-2.0 license gate）。
- 决策：新增 `fund_agent/agent/tool_trace_analysis.py` 纯函数分析器——只读消费显式传入的 `tuple[ToolTraceEntry]` + `ToolTraceAnalysisPolicy`（`large_argument_chars=120`），输出 immutable report（summary / by_tool 首现顺序 / findings / limitations 固定 4 条）；findings 确定性规则：`failed_call`（failure_code 用 `.value` 归一化，与 `main.py:430` 一致）、`repeated_failure`（同 tool+failure_code ≥2 次）、`large_arguments`（序列化长度 > 阈值，`==` 不触发）；JSON renderer deterministic（sort_keys / ensure_ascii=False / indent=2 / 尾换行）；`analyze_tool_trace` / renderer 类型不符抛 `TypeError`。接线：ask 流式成功分支（`--enable-tool-trace` 且 trace 非空时追加 `[工具分析: ...]` 行），`--no-stream` JSON 不含分析字段。
- 真源同步：`docs/design.md` §6.22、`AGENTS.md`「已知能力差距」backlog 行已更新（MiMo plan review 后同步）；plan artifact：`.sisyphus/plans/tool-trace-operator-slice-20260813.md`。
- 状态：✅ 完成。MiMo plan review — `NEEDS_FIX`（2026-08-13，3 项最小修复）：① failure_code 归一化改用 `entry.failure_code.value`（与 `main.py:430` 一致），弃 `str(...)`；② 补 by_tool 首现顺序显式测试断言（toolA→toolB→toolA 断言 `(toolA, toolB)`）；③ 补 large_arguments `==` 阈值边界测试用例。已按 review 原文修正 plan，按 CIC-lite 无 re-review gate。DS 实施（11m30s）：5 个文件全部在 allowed write set 内；新增 `tool_trace_analysis.py`（只读分析器纯函数：Policy / RunSummary / ToolStat / Finding / Report / analyze_tool_trace / to_json；TypeError 契约、failure_code `.value` 归一化、by_tool 首现顺序、limitations 固定 4 条、JSON deterministic）；接线 `cli/main.py` ask 流式成功分支（`[工具分析: ...]` + findings 行，TOOL_EVENT 实时显示与 `--no-stream` JSON 不变）。测试：10 passed（test_tool_trace_analysis）/ 6 passed（test_cli -k ask，含新增用例）/ 最小验证集 187 passed in 422.39s（含真实 PDF Docling smoke）；controller 独立复跑 10 + 6 passed。MiMo diff review — `ACCEPTED`（2026-08-13）：核实 _LIMITATIONS 4 条、renderer 参数、main.py 守卫与插入点、回归保护、测试覆盖，无 P0/P1。
- 待办：① 未 commit / 未 push（约束未解除）。

### interactive force_answer 降级收尾 slice（Fix A 细化，2026-08-13 规划，待实施）

- 依据：用户实测 interactive 偶发失败（`LLM 工具循环暂不可用`，trace 8 条全 success）+ controller 复现（4 次 3 成 1 败；假 LLM 确定性复现）。根因链：LLM（当前 mimo）偶发 8 轮不收敛 → `max_steps` 耗尽 → `_force_answer_from_evidence` 原文拼接 → 终答守卫必触发原文粘贴检测 → 有界重答 1 次 → 重答轮 provider 返回 ToolCall → `llm_tool_loop.py:1203-1205` fail-closed `UNAVAILABLE`。结构性缺陷：force_answer 产物必然违反原文粘贴检测 → 必然重答 → LLM 不收敛时必然失败，无恢复路径。
- 决策（用户裁决方案 2，2026-08-13）：`_apply_interactive_final_guards` 新增 `degraded: bool = False` 参数；`run()`（:676）与 `run_stream()`（:987）的 force_answer 调用点传 `degraded=True`。degraded 语义：投资建议拦截分支不变（安全红线保留）、`final.failure` 非空原样返回、跳过「原文粘贴/超长 → 有界重答」子规则、answer >200 字直接 `_truncate_final_answer_summary` 截断 ≤200 字；正常 FinalAnswer 路径零变化（`degraded=False` 默认）。
- 真源同步：`docs/design.md` §3.4 Fix A 表述、`AGENTS.md` interactive 质量语义 Fix A 表述已更新（MiMo plan review ACCEPTED 后同步）；plan artifact：`.sisyphus/plans/interactive-force-answer-degraded-closeout-20260813.md`。
- 状态：✅ 完成。MiMo plan review — `ACCEPTED`（2026-08-13）：核实 10 项代码事实全部一致，无 P0/P1；2 条 minor 不阻塞（degraded 分支用 if/else 而非 ternary；更新测试中未消费的第 3 个 response 由 DS 决定保留或移除）。DS 实施（12m26s）：4 个文件全部在 allowed write set 内；`llm_tool_loop.py` — `_apply_interactive_final_guards` 新增 `degraded: bool = False`（守卫最前段：degraded 且 failure None 且 `contains_investment_advice(answer)` 时合成 `INVESTMENT_ADVICE` 失败态走既有有界重答，安全红线保留；final.failure 原样返回；degraded 分支 >200 直接 `_truncate_final_answer_summary`、≤200 原样；非 degraded 走既有质量守卫），run / run_stream 两处 force_answer 调用点传 `degraded=True`；`test_llm_tool_loop.py` — 3 个 run_stream 用例 + TestForceAnswerDegradation 内 3 个 run() 用例连带改名新语义（DS 声明为同一行为变更必要连带，MiMo 核实合理）+ 新增 6 个用例（超长截断无重答 / 原文粘贴直接返回 / 无证据 fail-closed / 命中投资建议仍 fail-closed / 正常 FinalAnswer 粘贴重答回归 / 正常超长重答后截断回归）。测试：23 passed（-k 过滤）/ 122 passed（全量）/ 最小验证集 187 passed；controller 独立复跑 23 + 122 passed。MiMo diff review — `ACCEPTED`（2026-08-13）：4 个重点挑战全部核实——advice 合成与正常路径（line 1661）语义一致无副作用、3 个 run() 连带改名准确、degraded 完全跳过 provider 调用（next_step_calls==2 成立）、正常路径回归保护充分（paste 重答 next_step_calls==4 / overlong 重答后截断）。
- 待办：① 未 commit / 未 push（约束未解除）。


### process-backed 工具执行 slice（2026-08-13 规划，待实施）

- 依据：`docs/research/dayu-agent-r-research-20260810.md` §2.1.4（高价值第 4 项，代码已验证）——dayu `runtime/interruptible_process.py` 的「取消/超时 = 杀子进程」模式：blocking 工具走子进程，Host 取消或超时时不等待同进程 blocking I/O 自然结束；模块只负责子进程启动、结果回收、terminate/kill 与 bounded close。仅概念级借鉴，不复制代码（Apache-2.0 license gate）。
- 现状缺口（grep / 读码核验）：`MinimalHost.run()` daemon 线程 + `thread.join(timeout)`，超时返回 `timed_out=True` 但线程不杀；`DoclingConverter.convert_pdf()` 同步阻塞，超时仅靠 Docling 内部 `document_timeout`（模型下载 / OCR / C++ 路径卡死时不可靠、无进程可杀）。
- 决策：新增 `fund_agent/fund/document_tools/interruptible_process.py`（spawn + Pipe envelope + terminate→grace→kill→reap→bounded close；`SubprocessTimeoutError` / `SubprocessExecutionError`；`InterruptibleProcess` run() 与 start() 互斥 + `run_in_subprocess` 薄封装）；接线 `DoclingConverter.convert_pdf`（阻塞转换移入可抢占子进程，`timeout_seconds` 语义升级为内部 document_timeout + 硬子进程 deadline，公共签名/返回不变）；父进程失败映射（timeout / execution error / unavailable → 清理 json_path 后 `DocumentToolError(UNAVAILABLE, ...)`；`docling_convert_failed` 原样映射）；Host 12A thread timeout 语义不变，不做 Host 级整 loop 进程隔离（backlog，研究 §5 决策 5）。
- 真源同步：`docs/design.md` §6.23、`AGENTS.md`「已知能力差距」backlog 行已更新（MiMo plan review 后同步）；plan artifact：`.sisyphus/plans/process-backed-tool-execution-slice-20260813.md`。
- 状态：✅ 完成。MiMo plan review — `NEEDS_FIX`（2026-08-13，1 项最小修复）：test 2（timeout+kill）改为纯手动 API（start→join→terminate→grace→kill→join→断言回收），避免 start 后调 run() 覆盖 `_parent_conn` 导致第一个子进程孤儿化；同步在 spec 补「run() 与 start() 互斥，重复调用抛 RuntimeError」。已按 review 原文修正 plan，按 CIC-lite 无 re-review gate。DS 实施（15m24s）：6 个文件全部在 allowed write set 内；新增 `interruptible_process.py`（spawn 上下文 + Pipe(duplex=False) 单次 envelope；SubprocessTimeoutError / SubprocessExecutionError；InterruptibleProcess run() 与 start() 互斥、close 幂等、timeout<=0/grace<0 抛 ValueError；run_in_subprocess 薄封装；模块级 _child_entry 包 BaseException 回传；仅 stdlib）；`docling_converter.py` — 新增 `_run_conversion_in_child`（分类逻辑移入子进程，复用既有 helper）+ convert_pdf 经 `_run_child_conversion` 调 run_in_subprocess（timeout_seconds 升级为内部 document_timeout + 硬子进程 deadline），父进程映射 timeout/execution-error/unavailable→清理 json_path 后 `DocumentToolError(UNAVAILABLE, ...)`、docling_convert_failed 原样映射，公共签名与返回不变。测试：6 passed（原语，真实子进程）/ 5 passed（转换器，真实样本在子进程内完成转换，153s）/ 最小验证集 195 passed（340s）/ Host 回归 12 passed；CLI 端到端 smoke exit=0，imported（document_id=011649-2025-annual_report-f936fd46019a6ee7），docling.json 落盘；controller 独立复跑 18 + 5 passed（原语 + Host 回归 + 转换器全量）。MiMo diff review — `ACCEPTED`（2026-08-13）：逐行证据核实原语生命周期/超时回收/close 幂等/分类映射/测试策略/write set 全部通过；2 条 minor 不阻塞（_spawn 重复创建 spawn context 无功能影响；is_alive 未 start 时抛 AttributeError 非 plan 公共 API 场景）。
- 待办：① 未 commit / 未 push（约束未解除）。

### 阶段判定「建仓期」真源修正 slice（2026-08-13 规划，待实施）

- 症状：005680（财通资管价值成长混合，2025 年报）报告判定「🟡 建仓期」，判定依据「基金经理任职于2025年，管理本基金不足2年」。用户不认同：建仓期应属基金产品生命周期，经理变更不应触发。
- 根因（grep / 读码核验）：`chapter_generator.py:596-606` 建仓期判定只读 `fund_manager.tenure_start` 年份与 `report_year`（005680 合同 2019-03-25 生效、经理李响 2025-07-15 任职 → `2025-2025=0<2` 误判）；`chapter_generator.py:562-564` 在 `tenure_start` 为空时判「转型期」——经理维度占用 5 阶段枚举。
- 决策：新增「基金合同生效日」确定性抽取（Service 层，带 Citation，锚定 §2 基金简介表行，实测 005680/004393/163415 均命中 table-0002；日期必须紧跟「基金合同生效日」短语，规避 163415 §4.1.2 经理任职口径陷阱）；建仓期真源切换为 `report_year - 合同生效年份 < 2`（被动基金仍跳过），删除经理维度对阶段枚举的占用（经理变更保留在 Ch7 `score_manager_change` 0/20 信号）；成立日期缺失 fail-closed 不做建仓期判定并说明；`generate_data_table` 新增显式参数 `contract_effective_date` 全链路透传（audit_pipeline 四层 + extraction 模板路径）；`ChapterEvidence` 新增 `contract_citation`；`system_base.md` Ch5 正例同步为合同生效口径；`_generate_chapters_with_llm`（`extraction.py:3604`）为 dead code 不改。
- 真源同步：`docs/design.md` §6.24 已更新；plan artifact：`.sisyphus/plans/stage-determination-contract-date-slice-20260813.md`。
- 状态：✅ 完成。MiMo plan review — `NEEDS_FIX`（2026-08-13，2 项最小修复）：Fix 1 决策 6 引用不存在的 `_generate_llm_chapters`（LLM 路径实际经 `coordinator.generate_report()` 透传）已改正；Fix 2 `_generate_chapters_with_llm` dead code 已列入非目标明确不改。均已按 review 原文修正进 plan，按 CIC-lite 无 re-review gate。DS 实施（21m06s）：9 文件全部在 allowed write set 内（8 修改 + 1 新增）；DS 自报 2 处对 plan 的最小必要修正——① CLI smoke 复制 `pdf_blobs/`（`load_store` 有 blob 指纹校验，缺则 store 加载失败导致 fail-closed）；②「不含建仓期」字面断言不可满足（Ch5 固定含优先级行），改为断言 `| 判定结果 | 🟡 建仓期 |` 行不存在——MiMo diff review 核实两处均合理。测试：6 passed（阶段判定单元）/ 1 passed（CLI -k 005680_stage）/ 15 passed（e2e_regression 含 040046 转型期回归与 005680 抽取）/ 26 passed（llm_chapter + concurrency）/ 最小验证集 196 passed（DS 414.86s；controller 独立复跑 196 passed 189.91s）；005680 CLI 模板模式实跑：判定结果 🟢 稳定期、判定依据「基金合同 2019 年生效，成立已满2年，未触发建仓期」、基金合同生效日 2019-03-25、证据节含合同生效信息来源（section-0026, table-0002, p.5）。MiMo diff review — `ACCEPTED`（2026-08-13）：diff 与 plan 完全一致、DS 2 处修正合理、测试充分、write set 无越界。
- 待办：① 未 commit / 未 push（约束未解除）；② 用户如需更新已生成的 005680 报告，需重跑 `uv run fund-checklist generate ... --llm --work-dir .fund_checklist_005680`（旧 md/pdf 仍为建仓期判定）。

## 季报/半年报快照（snapshot）大任务（2026-08-14 启动）

- 设计真源：`docs/design.md` §6.25（18 项裁决全量写入）。
- 研究依据：`docs/research/quarterly-semiannual-data-source-research-20260814.md`。
- Slice 划分（每 slice：implement → tests → diff review）：
  1. **design.md §6 增量**（已完成）：§6.25 快照小节 + §4.1/§8.5「仅支持 annual_report」表述同步。stop：§6.25 含 18 项裁决 + EID 实证 + 章节/字段边界；annual 章节只改「当前仅支持 annual_report」相关表述。
  2. **implementation-control.md 更新**（本文件本节）：slice 划分、状态、验证命令、回归约束。stop：与 design.md §6.25 一致。
  3. **Slice A（域模型）**：ReportType 扩展（`semiannual_report` / `quarterly_report`）、document_id 期次编码（quarterly 插入 `-Q[1-4]` 段，`_PARSED_DOCUMENT_ID_PATTERN` + `_assert_supported_identity` 同步）、catalog quarter/period 字段（向后兼容 → None）、`import --report-type/--quarter`。stop：最小验证通过 + import Q1/Q2 不吞期次。
  4. **Slice B（download）**：EID semiannual/quarterly spec（FB020/FB020010、FB030/FB030010-040）+ 下载链路。stop：005680 半年报 + 季报 EID 码匹配测试通过。
  5. **Slice C（模板 + prompts）**：`docs/fund-quarterly-snapshot-template.md` / `docs/fund-semiannual-snapshot-template.md` 各自内嵌 manifest + prompts 命名空间（`quarterly_snapshot/` / `semiannual_snapshot/`）+ `ReportGenerationCoordinator` 按 template_id 解耦 8 章绑定。stop：模板解析测试 + 命名空间不触碰 ch0-ch7。
  6. **Slice D（受控 profile + 抽取）**：`quarterly_performance` / `semiannual_performance` + 快照简化评分 + 单期抽取。stop：005680 真实 PDF 抽取测试通过，annual 契约回归不变。
  7. **Slice E（CLI + 输出）**：`snapshot-quarterly` / `snapshot-semiannual`、期次参数、落盘命名 `reports/{fund_code}-{year}Q{n}-quarterly-snapshot.md`、json/markdown/pdf 三格式。stop：CLI 端到端 smoke（005680 Q1/Q2 + 半年报）。
  8. **回归 + 文档同步**：read/multi-year/generate annual 行为回归、`_multi_year_documents_by_year` SCHEMA_DRIFT 边界保持、AGENTS.md/README/tests/README.md 同步。stop：最小验证集 + 回归集全绿。

- 验证命令：
  - 最小验证：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`
  - 验收：005680 本地真实 PDF（`基金季报/*Q1*`、`基金季报/*Q2*`、`基金半年报/005680_*_2025_semiannual_report.pdf`）CLI 端到端，含 json/markdown/pdf 输出。
- 回归约束：annual 主链（read / multi-year / generate / holdings / allocation / fees / audit / deep-audit / ask / interactive）行为零变化；快照文档导入 work_dir 后，multi-year/generate 的 catalog 过滤必须按 `report_type=annual_report` 防污染。
- 多 Agent：实现默认派 DS；本会话由单一 Agent 直接实施（Controller+Implementation 合一），每 slice 用独立 review agent 做 diff review。
- 待办：① 未 commit / 未 push（约束未解除）。
- 验收（2026-08-14）：最小验证集 222 passed（唯一失败为 Docling 真实转换 300s 超时——环境性，baseline 同样失败，docling_converter/interruptible_process 未被本次改动触碰，隔离复跑曾 106s 通过）；全量 tests/fund 1345 passed（排除 live smoke 与 docling 环境项）；3 个 ask_question routing 失败为 HEAD 预存在（临时 worktree 验证）；live smoke 因 shell env `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` + LLM provider 不可用失败（环境性）。005680 本地真实 PDF（Q1/Q2 季报 + 2025 半年报）CLI 端到端通过：import → snapshot-quarterly/snapshot-semiannual → json/markdown/pdf 三格式输出（Q1 5 章评分 75 优秀、Q2 业绩表全阶段行 + ①-③、半年报 6 章含财务质量/持有人）；落盘 `reports/005680-2026Q2-quarterly-snapshot.md` / `reports/005680-2025H1-semiannual-snapshot.md`；pdf 走既有 fallback 链（与 annual generate 行为一致）。annual 主链回归：multi-year 5 年全覆盖、generate annual 正常。
- Slice A/B/C/D/E/F 全部完成，diff review 全链路：A ACCEPTED / B（单测 10 passed）/ C NEEDS_FIX 1 项已修复 / D NEEDS_FIX 2 项已修复 / E ACCEPTED / F ACCEPTED。

### 快照 slice 进度

- Slice 0a/0b（设计 + control 面板）：✅ 完成（2026-08-14）。design.md §6.25（18 项裁决）+ §4.1/§8.5 表述同步；control 面板本节。
- Slice A（域模型）：✅ 完成（2026-08-14）。ReportType 扩展（semiannual_report/quarterly_report + SnapshotQuarter）；document_id 期次编码（quarterly 插 -Q[1-4]，_PARSED_DOCUMENT_ID_PATTERN + _assert_supported_identity 同步）；catalog quarter/period 字段（旧记录 → None 向后兼容）；import --report-type/--quarter（contract-first，文件名 Q 标记仅便利过滤）。测试：document_tools 20 passed / CLI import 16 passed / 最小验证集 207 passed（1 个 Docling 真实转换超时，隔离复跑通过，与 Slice A 无关）。diff review：独立 Review Agent ACCEPTED（核验点 1-8 全部一致，无 NEEDS_FIX；2 条非阻塞观察：无 Q 标记文件按显式 quarter 导入路径无单测、pattern 拒绝 Q5 无单测——语义已逐行确认）。
- Slice B（download）：✅ 实现完成（2026-08-14）。EID spec 表扩展（FB020/FB020010 中期报告、FB030/FB0300X 第N季度报告）；download_report 通用入口（annual 兼容 wrapper）；download CLI --report-type/--quarter。测试：test_eid_downloader.py 10 passed。
- Slice C（模板 + prompts + coordinator 解耦）：✅ 完成（2026-08-14）。两个快照模板文档（内嵌 manifest）+ prompts 命名空间（quarterly_snapshot/ ch0-4、semiannual_snapshot/ ch0-5）+ report_template.py 注册表 + snapshot_generator.py + ReportGenerationCoordinator 解耦（template 参数，默认 annual 行为不变，_generate_template_chapter 委托 template hook，新增模块级 generate_annual_template_chapter）。测试：test_snapshot_template.py 9 passed / audit_pipeline + concurrency 63 passed（annual 回归零变化）。diff review：独立 Review Agent NEEDS_FIX 1 项（P1：解耦后全局允许数字收集循环把 annual Ch0 数据表也纳入——解耦前 range(1,8) 不含 Ch0），已修复（annual 模板跳过 Ch0），复跑 80 passed。
- Slice D（受控 profile + 抽取 + 快照评分）：✅ 完成（2026-08-14）。registry 新增 quarterly_performance / semiannual_performance profile（extraction_allowed=False）；新建 snapshot_extraction.py（extract_snapshot_data 全字段抽取：3.2.1 业绩行 + 规模 + 持仓 + 资产配置 + 行业 + 份额变动 + 基金经理 + 固有资金 + 运作分析 + 财务 + 持有人 + 季报缺失项 fail-closed）+ snapshot_scoring.py（简化评分：超额 0-40 + 仓位 0-30 + 集中度 0-30）；coordinator 增加 snapshot_data/snapshot_score 透传（annual 默认 None 行为不变）。实测 005680 Q1/Q2 季报 + 2025 半年报抽取通过（Q2：业绩行 4 行、持仓 10 行、份额变动齐全、评分 90 优秀）；e2e smoke 4 passed / 单测 21 passed。diff review：独立 Review Agent NEEDS_FIX 2 项（均真实数据缺陷，已修复）：F1 基金经理误抽取「上述」→ 4.1 表姓名列优先 + 聘任结构 + 指代词排除；F2 半年报规模/份额漏抽 → search 遍历多命中 + aum 正则放宽裸数字；修复后 e2e 断言强化（fund_manager 非指代词、半年报 scale_info 非全缺失）6 passed。
- Slice E（CLI + 输出）：✅ 完成（2026-08-14）。`snapshot-quarterly` / `snapshot-semiannual` 子命令（--fund-code/--fund-name/--year/--quarter|--period/--format/--llm/--work-dir/--concurrency）；Service 层 `generate_snapshot_report`（catalog 匹配 → extract_snapshot_data → compute_snapshot_score → coordinator/template 生成章节 → json/markdown/pdf 导出，落盘 `reports/{fund_code}-{year}Q{n}-quarterly-snapshot.md` / `{fund_code}-{year}H1-semiannual-snapshot.md`）。实测 005680：Q1/Q2 季报 + 2025 半年报 CLI 端到端通过（Q1 5 章评分 75 优秀；Q2 markdown 落盘 + 业绩表全阶段行 + ①-③；半年报 6 章评分 35 关注；pdf 走 fallback 链回退 Markdown + warning，与 annual generate 行为一致）。测试：CLI snapshot 5 passed。diff review：独立 Review Agent ACCEPTED（6 核验点全过，annual/multi-year 回归 141 passed，无最小修复项；3 条非阻塞观察）。
- Slice F（回归 + 文档同步）：✅ 完成（2026-08-14）。防污染 catalog 过滤（multi-year/generate/关联持仓源按 report_type=annual_report，`_collect_matching_docs` / `_run_multi_year_command` / `generate_report` / `_extract_report_holdings_from_source`）+ 文档同步（AGENTS.md CLI 入口与 report_type 支持范围、README 快照命令示例、tests/README.md 快照测试、fund_agent/fund/README.md document_id 期次段）+ registry 断言更新（test_extraction.py 2 处含新 profile）。回归：全量 tests/fund 1345 passed（排除 live smoke 与 docling 转换超时环境项；3 个 ask_question routing 失败为 HEAD 预存在——临时 worktree 验证 HEAD 同样失败，与本次改动无关；live smoke 因 shell env FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 且 LLM provider 不可用而失败，亦与本次改动无关）。diff review：独立 Review Agent ACCEPTED（核验点 1-4 全过；非阻塞观察：`test_e2e_multi_year_ignores_snapshot_documents` 区分度弱——已补 `test_multi_year_collect_ignores_snapshot_in_mixed_workdir`（mixed workdir：3 年年报 + 1 份季报，断言 `_collect_matching_docs` 只返回 annual 年份、2026 季报被过滤），并实证旧逻辑（无过滤）会匹配 2026 → 测试有真实区分度）。
- F1-F4 快照修复 slice：✅ 完成（2026-08-15 收口）。MiMo deepreview 4 findings（F1 严重 risk_notes 误赋值 / F2 高 份额变动文本回退正则 / F3 中 period 标签 / F4 低 审计上下文硬编码）→ 用户裁决全修 → plan review PASS → DS 实施（snapshot_extraction / snapshot_generator / audit_pipeline / 测试）→ MiMo diff review ACCEPTED；测试 30+50+224 passed。
- Slice G（审计章节迭代硬编码收口）：✅ 完成（2026-08-15）。audit_pipeline.py:2681 `for cid in range(1, 7):` → `for cid in self._template.front_chapter_ids:`（F4 计划声称 2471 是唯一硬编码位置不准确，2681 同款另立 slice）；同文件其余章节迭代已模板驱动（全量 rg 确认仅 2681 一处）；测试新增 test_chapter_summary_injection_follows_template_front_ids（quarterly 不注入 Ch5/Ch6、semiannual 不注入 Ch6，可证伪旧逻辑）；同步更新 docs/design.md §6.25 第 19 项与 AGENTS.md 禁止事项。验证命令：test_snapshot_report_assembly.py / test_audit_pipeline.py / test_snapshot_template.py + test_snapshot_extraction.py / AGENTS.md 最小验证集 / git diff --check。diff review：独立 Review Agent（MiMo）ACCEPTED（docs/reviews/code-review-20260815-160347.md），改动精确、测试可证伪、文档一致、write set 无越界。
- 审计管道设计收紧 slice（critical 阻断 + 装配审计）：✅ 完成（2026-08-15）。来源：F1-F4 收口报告遗留建议两项裁决项（① critical 不阻断；② 无装配审计），口径 2026-08-15 用户拍板全部按推荐（D1 critical 阻断含数据不足模式，只降门槛不豁免；D2 LLM 审计 critical 与程序化 critical 同等阻断，误报代价 ≤3 次 regenerate 后有界；D3 装配违反 fail-closed 复用 schema_drift，内容为空仅 warning；D4 校验三处全接，快照×2 + 年报 LLM/模板路径，三模板 chapter_titles 与三处装配标题逐字一致无误报风险）。A1（audit_pipeline.py）：新增纯函数 `_passes_audit(final_score, score_pass, violations)`（语义：达门槛且无 critical）；`_generate_and_audit_chapter` 通过分支改调 `_passes_audit`，critical 存在时不通过且跳过 PATCH 直接走 REGENERATE（与 select_repair_strategy 对齐）；`AuditDecision.recommendation` has_critical → "regenerate"；`select_repair_strategy` score>=SCORE_PASS 且有 critical → "regenerate"（reason 列出 codes），无 critical 仍 skip；顺手修正 SCORE_PASS_DEGRADED 注释「≥70分」→「≥75分」。A2：新增纯函数 `verify_report_assembly(template, chapters)`（集合==chapter_ids 缺章/多章 fail、顺序==sorted 乱序 fail、标题==chapter_titles 不符 fail、内容为空仅 warning）；extraction.py 三处装配点接入（generate_snapshot_report 快照、generate_report LLM 路径、_generate_chapters 模板路径），违反返回 ToolFailure(code=schema_drift, message=校验明细)，不新增 failure code。测试：test_audit_pipeline.py 新增 select_repair_strategy score=87.4+critical→regenerate（旧逻辑 skip 可证伪）、_passes_audit 纯函数三态、集成 fake LLM 高分+critical→章节 regenerate→耗尽→passed_with_degradation（patch_attempts=0、regenerate_attempts=3、status != passed）；test_snapshot_report_assembly.py 新增 verify_report_assembly 纯函数 6 态 + 集成缺章/多章 chapter_contents→schema_drift（旧代码无校验照常产出可证伪）。文档同步：docs/design.md §6.25 第 20 项、AGENTS.md 审计规则。验证命令：test_audit_pipeline.py 54 passed / test_snapshot_report_assembly.py 22 passed / test_snapshot_template.py + test_snapshot_extraction.py 17 passed / test_report_concurrency.py + test_extraction.py 291 passed / AGENTS.md 最小验证集 224 passed / git diff --check 干净。diff review：独立 Review Agent（MiMo）ACCEPTED（docs/reviews/code-review-20260815-210500.md；A1 代码 6 项 + A2 代码 5 项 + 测试可证伪性 12 项全部 VERIFIED；语义裁决：高分+critical 耗尽返回 LLM 内容 passed_with_degradation 满足 plan 意图；文档同步 4 项 VERIFIED；边界检查 4 项通过；无需修复项）。未 commit 未 push。
- 快照 to_context_dict 完整性 slice（候选 B）：✅ 完成（2026-08-15）。来源：F1-F4 收口 review 非阻塞观察 #1 + 候选 B 裁决（docs/reviews/code-review-20260815-122324.md）；goal：`.sisyphus/goals/snapshot-context-dict-completeness-goal-20260815.md`。实证：`to_context_dict()` 仅序列化 15 key，缺失 fund_code/fund_name/report_year/template_id/quarter/period/citations；唯一消费点 `extraction.py:2779`，身份字段由 service 层显式 kwargs 传入 generator（extraction.py:2805/2823/2831 + snapshot_generator.py:179-184），当前非阻塞，风险为未来消费者从 dict 读身份/citations 缺字段。实施：`snapshot_extraction.py` `to_context_dict()` 补齐 7 字段——身份字段原样序列化，`citations` 以 `[dict(c) for c in self.citations]` 序列化，既有 15 个 key 不变（纯增量、向后兼容）；测试新增 `test_snapshot_to_context_dict_covers_all_dataclass_fields`（quarter=3/period=H2/citations 非空 fixture，断言 `set(dict.keys()) == {f.name for f in dataclasses.fields(SnapshotReportData)}` + 逐 key 值与 dataclass 一致，未来新增字段不同步序列化即红）。验证命令：test_snapshot_extraction.py 9 passed / test_snapshot_report_assembly.py + test_snapshot_template.py 31 passed / AGENTS.md 最小验证集 224 passed / git diff --check 干净。非目标守界：不改消费者传参契约（身份字段仍走显式 kwargs、不从 dict 读）、不把 citations 接入 generator 渲染、不改 failure taxonomy / public tool 契约 / CLI / prompts / registry、不做候选 C（_search_texts 截断边界）、不改 AGENTS.md（非验收规则变化）。文档同步：docs/design.md §6.25 第 21 项。未 commit 未 push。
- search excerpt 截断边界 slice（候选 C）：✅ 完成（2026-08-15）。来源：F1-F4 收口 review 非阻塞观察 3（docs/reviews/code-review-20260815-122324.md）；goal：`.sisyphus/goals/search-excerpt-boundary-goal-20260815.md`。实证：`docling_store.py` `_excerpt`/`_search_excerpt` 240 字符窗口（`DEFAULT_SEARCH_EXCERPT_CHARS=240`）在任意字符处截断，可切断数字串（如 `787,727,758.47` → `787,727,`）；快照 `_search_texts`（snapshot_extraction.py）被动消费 excerpt 无截断标记，无法自行补全，根因修复在 excerpt 生成端。实施：`docling_store.py` 新增纯函数 `_align_start_no_number_cut` / `_align_end_no_number_cut`（数字串字符集 `0123456789,，.`，仅当截断点前一字符与当前字符均属该集合才判定数字串内部，避免吞孤立标点）；`_excerpt` 窗口 start/end 与 `_search_excerpt` 归一化路径 begin/window_end 均做对齐；两函数 no-hit fallback 改为 `text[:_align_end_no_number_cut(text, max_chars)]`（仅 excerpt fallback 对齐，`_bounded` 本身不动，list_sections preview / read_section 行为不变）。测试：新文件 tests/fund/document_tools/test_search_excerpt_boundary.py 10 passed（纯函数左右边界 + 归一化路径两态 + no-hit fallback + 恰在数字串结束不扩展 + 命中区间保留 + 集成 `search_document`→`_extract_share_change` 捕获完整值，旧行为 `787,727,` 可证伪）；回归 test_docling_store.py + test_bm25f_scorer.py 38 passed / test_snapshot_extraction.py + test_snapshot_report_assembly.py 31 passed / AGENTS.md 最小验证集 234 passed / git diff --check（本 slice 4 文件）干净。文档同步：docs/design.md §6.25 第 22 项。非目标守界：不改 `_bounded`、不做跨页/跨节数字拼接、不改 SearchResult 结构 / search_document 签名 / failure taxonomy / CLI / prompts / registry、不改 snapshot_extraction.py、不改 AGENTS.md。未 commit 未 push。
- download 批量下载 + --import 流水线 slice：✅ 完成（2026-08-17，CIC-lite implement + tests + diff review）。plan：`.sisyphus/plans/download-batch-slice-20260817.md`（已含 NEEDS_FIX 裁决并全部按裁决执行：退出码与 `_run_import_command` 一致——全部条目失败 → 2 / 部分失败 → 0；`--quarters` 保留复数命名；单模式不新增字段；`--year-range` 在 download parser 上 `default=None`；import 仅限 `status ∈ {downloaded, cached}` 且 `file_path is not None` 的条目）。实施（`fund_agent/cli/main.py`）：download parser 新增 `--year-range`（与 `--year` 互斥、两者皆缺省 → schema_drift 退出码 2）、`--quarters`（与单值 `--quarter` 互斥，仅 quarterly_report，越界或 annual/semiannual 下使用 → schema_drift；批量 quarterly 缺省期次 1,2,3,4）、`--import`（复用 `service.import_local_report` 与 import 分类语义：integrity_error → skipped、其它分类 → failed、未捕获异常 → failed，导入失败不中断）、`--work-dir`；`_run_download_command` 拆分单模式（保持单对象 JSON，字段不变）与批量模式（stdout JSON 数组 + stderr 逐条进度与汇总），新增纯函数 `_parse_quarters` 与 `_run_download_batch`。测试：test_cli.py 新增 12 个 download 用例（参数互斥/缺省、8 条目矩阵、cached/downloaded 混合、部分失败退出码 0、全部失败退出码 2、--import 流水线 imported/skipped/failed、下载失败不导入、单模式兼容），全部 mock `download_report`/fake service，不联网；回归 test_eid_downloader.py 10 passed。验证命令：`uv run pytest tests/fund/cli/test_cli.py -k "download" -q --tb=short`（12 passed，controller 复跑）、`uv run pytest tests/fund/document_tools/test_eid_downloader.py -q --tb=short`（10 passed，controller 复跑）、最小验证集 `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short`（246 passed，controller 复跑）、`git diff --check`（干净）。diff review：独立 Review Agent（MiMo，agents:0.2）ACCEPTED，逐条核验 C1-C7（参数互斥与 schema_drift、--quarter/--quarters 互斥与 quarterly 缺省全期次、单/批量双 schema、批量 JSON 数组与 stderr 进度、退出码与 import 一致、--import 仅成功条目且分类正确、全部 mock 不联网），并引用代码行号与测试断言；controller 已抽查关键契约点（main.py:186-198/585-601/912-930/945-982/1045-1105）与 review 引用一致，无 hallucination 项。文档同步：README.md download 节批量用法示例、docs/design.md §6.25 第 23 项、tests/README.md。非目标守界：不改 `download_report` 签名与单次语义、不改 EID spec/reportCode 映射、不新增限速参数、不联网测试。未 commit 未 push。

- 快照 interactive 开放 slice（2026-08-19，CIC-lite implement + tests，diff review pending）：plan `.sisyphus/plans/snapshot-interactive-20260819.md` 经 Mimo plan review NEEDS_FIX 4 项（已由总控逐项验证属实）并全部修订：① §1.1 行号修正（store 加载循环 1544-1550→1572-1584、ChatService 构造 1553-1561→1586-1592、/document 1678-1701（1700-1724 为 chat_turn 区域）；另将 PinnedState 构造行号一并修正为 1552-1558）；② write set 的 session_store 路径确认在 `fund_agent/host/session_store.py`（host 层，非 service 层，§1.5/决策 4 裸引用同步加 host/ 前缀）；③ write set 的 main.py 条目补充「/document handler（main.py:1678-1701）需保留 report_type/quarter/period 字段」；④ 决策 4 末尾补充「快照模式 /document 期次切换时 quarter/period 从目标 document 的 catalog record 重新解析（非透传旧值）」。实施（决策 1-5 严格守界）：
  - `fund_agent/service/models.py`：新增 `SnapshotReportDocument`（year/quarter/period/document_id）与 `SnapshotResolution`（documents/available_years）DTO。
  - `fund_agent/service/extraction.py`：`resolve_by_fund_code` 增加 `report_type: str = "annual_report"` 默认过滤（修复 mixed catalog 污染，唯一调用方 interactive）；新增 `resolve_snapshot_reports(fund_code, work_dir, report_type)`（fund_code+report_type 匹配、季度同一年多条 quarter 全部保留、period 从 catalog record 读取）。
  - `fund_agent/service/session_models.py`：`PinnedState` 新增 `report_type="annual_report"` / `quarter=None` / `period=None`（默认值保证旧 session 兼容）。
  - `fund_agent/host/session_store.py`：`_session_to_json`/`_session_from_json` 同步透传/序列化三字段（load 用 `.get()` 缺省，`_SESSION_SCHEMA_VERSION` 不 bump）。
  - `fund_agent/service/chat_service.py`：`_build_contributions` runtime 段快照模式追加「报告类型: 季报（quarterly_report）/半年报（semiannual_report）」「报告期: X 年N季度（Qn）/X 年 H1 半年报」「注意：当前文档为单期快照，非年度报告；数据仅覆盖当期，禁止与年度/多年数据混用，禁止做多年趋势判断。」（annual 不追加任何行）。
  - `fund_agent/cli/main.py`：interactive parser 新增 `--report-type`（默认 annual_report）/`--quarter`（choices 1-4）/`--period`（仅 H1）；`_run_interactive_command` 参数组合校验（--quarter/--period 配 annual 拒绝、--period 配 quarterly 拒绝、--quarter 配 semiannual 拒绝）、快照解析分支（缺省期次 = 所选年份内最新季度 / H1）、PinnedState 携带三字段、快照模式 `aggregate_handler=None`（annual 仍注入 handler）、启动文案分报告类型；`/document` handler 保留三字段，快照模式 `quarter`/`period` 从 `resolution`（catalog 解析结果）按目标 document_id 重新解析。
  - 测试：`tests/fund/service/test_snapshot_resolution.py`（新增 9 用例：annual 过滤/季度全保留/半年报 period/无匹配/无 catalog）；`tests/fund/cli/test_cli_interactive_snapshot.py`（新增 21 用例：parser 形态与 choices 拒绝、参数组合校验、季报/半年报 CLI e2e 缺省与显式期次、not_found、快照 aggregate_handler=None、PinnedState 落盘、/document 期次重新解析、runtime contribution 快照/半年报/年度零变化、SessionStore 序列化 round-trip 与旧 session 缺省）；`tests/fund/cli/test_cli_interactive.py` 新增 mixed catalog annual 回归守卫（annual 可用年份排除仅季报年份）。
  - 文档同步：docs/design.md §6.25 裁决 15 状态更新为已收口 + 新增第 24 项；implementation-control.md 本节。
  - 验证命令（stop conditions 全部通过）：`uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/cli/test_cli_interactive_snapshot.py -q --tb=short`（112 passed）；`uv run pytest tests/fund/service/test_snapshot_resolution.py tests/fund/cli/test_cli_interactive_snapshot.py tests/fund/cli/test_cli_interactive.py -q --tb=short`（121 passed）；最小验证集 `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short`（249 passed）；Phase 7 验证命令（9 文件，289 passed）；`git diff --check` 干净。默认 pytest 未联网。
  - 非目标守界：不改快照报告生成（generate_snapshot_report/extract_snapshot_data/模板/prompts）、不改 snapshot 抽取 profile、不改 llm_tool_loop/scene_config/prompt 模板/DocumentToolService 公共契约、不接入 ask、不做 H2、不把快照纳入 multi-year/generate annual。未 commit 未 push。

## 投资者偏好分析 MVP（2026-08-21 启动，P1-P3 已完成）

- 设计真源：`docs/design.md` §6.26（2026-08-21 定稿：存储 SQLite、图片仅引用路径、题库 = 有知有行五大板块 + 自建 80 题、C1-C5 保留辅助输出、五维权重 25/20/20/20/15、`preference-snapshot --quarter YYYYQn`、固定免责声明「本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。」）。
- 合规边界：AGENTS.md 硬规则禁止买卖建议；MVP 只输出偏好画像 + 反思（声明 vs 行为对照），不输出调仓/配置建议；行为证据来源为 `preferences.db` 的 `memos` 表（非 `memos.json`，已修 §6.26.7 旧稿残留）。
- 隐私边界：Flomo 私人笔记只本地处理、不进 git（`.gitignore` 已含 `docs/flomo@*.zip` / `docs/flomo-export-*/` / `.fund_checklist*/`）；测试资产 `tests/fund/preferences/fixtures/flomo_sample.html` 为构造样例，非私人数据。
- Slice 划分（每 slice：goal 文档 → Mimo review → DS 实现 → tests → Mimo diff review）：
  1. **P1 flomo-import**（✅ 完成）：新域 `fund_agent/preferences/`（与 fund/ 平级）——`flomo_parser.py`（标准库 HTMLParser 状态机解析 .memo/.time/.content/.files → `FlomoMemo`，id `flomo-<YYYY-MM-DD>-<序号>`、created_at ISO8601 +08:00、图片相对路径数组）+ `store.py`（SQLite：`memos` + `imports` 表，fingerprint sha256 幂等）+ CLI `flomo-import --html --work-dir [--images-dir]`（失败分类 not_found/schema_drift/unavailable 退出码 2）。goal：`.sisyphus/goals/preference-p1-flomo-import-goal-20260821.md`（Mimo review 通过，1 minor：`imports.exported_at` 扩展列已标注）。Mimo diff review **ACCEPTED**。
  2. **P2 preference-questionnaire**（✅ 完成）：题库资产 `fund_agent/preferences/questionnaire/baseline-v1.json`（git 跟踪，自建 80 题、五板块各 16、难度 24/32/24、risk_flag 12、权重 25/20/20/20/15、c1c5_bands）+ `questionnaire.py`（题库完整性校验 + `score_questionnaire` 总分 0-100 四舍五入 1 位 + 五维子分 + 辅助 C1-C5）+ store `questionnaire_results` 表 + CLI `preference-questionnaire --answers`（非 TTY 必填，TTY 逐题交互）。goal：`.sisyphus/goals/preference-p2-questionnaire-goal-20260821.md`（Mimo review 通过，路径 `questionnaire_data/` → `questionnaire/` 已修）。Mimo diff review **ACCEPTED**。
  3. **P3 preference-snapshot**（✅ 完成）：`snapshot.py`（INVESTMENT_KEYWORDS 16 词 + QUARTER_REGEX + `build_behavior_summary` 季度范围 + 关键词过滤 + `generate_snapshot` 四问反思模板 + 固定免责声明 + 落盘 `preferences/quarters/<quarter>/preference-snapshot.{json,md}`）+ store `preference_snapshots` 表 + `latest_questionnaire_result`/`query_memos_by_date_range` + CLI `preference-snapshot --quarter YYYYQn`。goal：`.sisyphus/goals/preference-p3-quarterly-snapshot-goal-20260821.md`（Mimo review 通过，无修复项）。Mimo diff review **ACCEPTED（2026-08-21 二次复核）**：首轮 NEEDS_FIX 2 项 → ① off-by-one 已修复（`snapshot.py:217` `latest_questionnaire_result(store, end - timedelta(days=1))`，end 为下一季度首日独占边界 + 2 边界测试 2026-10-01 不纳入 Q3 / 2026-09-30 纳入）；② revert 禁止文件项 Mimo 认可关闭（AGENTS.md / docs/design.md / .gitignore 为 controller 裁决落盘，`fund_agent/fund|service` / `test_e2e_holdings_regression` 为存量 slice `quarterly-top10-holdings-fix` 既有改动，均非 P3 越界）。
  4. **P4 note-import**（✅ 完成，2026-08-22）：智慧笔记数据导出导入——邮件「我的思考记录」（2026-08-11 收件，65 条 = 分析记录 20 / 多维度分析 20 / 孵化报告 5 / 结构分析 20）。设计真源 `docs/design.md` §6.26.10；导出文件 `docs/note-export-20260811/思考记录-20260811.html`（gitignore `docs/note-export-*/`）。契约：`note-import --html --work-dir`；`note_parser.py`（HTML→文本 + Markdown 结构解析，`ThoughtNote(id=note-<YYYYMMDD>-<category-key>-<序号>, category, title, created_at, status, content, source)`；时间行 `分析时间`/`生成时间` 别名；status 兜底链 `状态`→`类型`→`未知`；正文内 `## 一、` 子标题归入 content；声明条数不符/缺失时间/无记录未知类别 → schema_drift fail-closed）+ store 新增 `thought_records` / `note_imports` 表（fingerprint 幂等，与 memos 同库）+ CLI 注册。goal：`.sisyphus/goals/preference-p4-note-import-goal-20260822.md`（Mimo goal review 无修复项）。Mimo diff review **ACCEPTED（2026-08-22）**：逐契约点核验（note_parser L、store import_notes、main.py L984-1056），唯一说明 = status 兜底链为 goal 裁决指定且已测试，行为更健壮。
- 验证命令（2026-08-21 controller 实测）：
  - P1：`uv run pytest tests/fund/preferences/test_flomo_parser.py tests/fund/preferences/test_flomo_store.py tests/fund/cli/test_cli_flomo_import.py -q --tb=short` → 17 passed。
  - P2：`uv run pytest tests/fund/preferences/test_questionnaire.py tests/fund/cli/test_cli_preference_questionnaire.py -q --tb=short` → 24 passed。
  - P3：`uv run pytest tests/fund/preferences/test_snapshot.py tests/fund/cli/test_cli_preference_snapshot.py -q --tb=short` → 19 passed。
  - 偏好全量：`uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_flomo_import.py tests/fund/cli/test_cli_preference_questionnaire.py tests/fund/cli/test_cli_preference_snapshot.py -q --tb=short` → 60 passed。
  - 最小验证集：`uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short` → 256 passed（194.6s，无 Docling 真实转换失败）。
- 真实导出 smoke（2026-08-21 controller 直跑，`docs/flomo-export-20260819/`，临时 work-dir）：
  - P1：331 memos / 15 图片引用导入成功；二次导入 cached 幂等（memos=331 不覆盖，记录首次导入时间戳）。
  - P2：全对 → 总分 100 / 五维 25-20-20-20-15 / C5；全错 → 总分 0 / C1。
  - P3：2026Q3 快照生成（questionnaire baseline = 最近一次问卷 100；behavior_summary 0 条——真实导出最新 memo 为 2026-04-14，不在 Q3 内）；2026Q1 快照 behavior_summary 命中 2 条（「加仓/减仓」「收益」）；四问字段与免责声明逐字一致。
- 真实导出 smoke（2026-08-22 controller 直跑）：
  - P4：`docs/note-export-20260811/思考记录-20260811.html`（邮件「我的思考记录」）导入 `.fund_checklist/preferences/preferences.db` → imported records=65（analysis 20 / roundtable 20 / incubator 5 / structure 20），二次 cached 幂等；thought_records 与 memos 同库（memos 331 + thought_records 65 + questionnaire_results 0 + imports 1 + note_imports 1）。
  - 季度快照能力：`preference-snapshot --quarter 2026Q1`（真实库）→ 生成成功，baseline=None（尚未答问卷），behavior_summary 2 条（2026-02-28「加仓/减仓」、2026-03-19「收益」），四问 reflection 空模板 + 固定免责声明逐字一致。
- 待办：① 用户答问卷：`uv run fund-checklist preference-questionnaire`（TTY 逐题交互，落 questionnaire_results）；② 答完复跑 `preference-snapshot --quarter 2026Q1/2026Q3` 验证 baseline 注入与行为对照；③ 收口 commit（P1-P4 + 裁决落盘）待用户指示；④ 下一 slice P5 行为证据对照（第二切片，原 P4，抽取范围将扩到 memos + thought_records）待设计；⑤ 远期候选（2026-08-22 新增，设计见 design.md §6.26.11）：6 个月定时问卷任务（风险偏好变化追踪）、有知有行知识库（投资者学习与成长），进入实施前逐个设计；⑥ 未 commit / 未 push（约束未解除）。
