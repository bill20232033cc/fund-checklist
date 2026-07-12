# Repository Agent Rules

更新时间：2026-07-12

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
 -> 确定性信号评分 (6 指标，135→100 归一化)
 -> 8 章分析报告生成 (程序数据表格 + LLM 定性分析)
 -> 三层审计管道 (程序+LLM+复核，4 类 22 项)
```

已实现的 CLI 入口详见当前阶段节。

验收约束（适用于所有阶段）：
- 不接受仅 Service / ToolService 层测试；任何阶段的验收必须包含 Host / Agent loop 或 CLI 端到端 smoke。

当前已知能力差距（来自 dayu-agent 对标研究，2026-07-11），以下能力当前不存在，Agent 不得假装具备：
- **多轮对话**：无 interactive mode，无会话记忆
- **LLM 自主工具调用**：Agent loop 仍为确定性序列，非 LLM-driven
- **多模型支持**：已支持 DeepSeek 与 Mimo（OpenAI-compatible adapter）；暂不需要接入 Gemini/OpenAI/Anthropic 等
- **Streaming**：无流式输出
- **上下文治理**：无 budget/truncation/compaction
- **联网搜索**：无法获取实时市场数据

这些差距将在后续 phase 中按优先级解决，不影响当前已实现功能的使用。

## 硬边界

- 对基金文档的存取必须通过统一 Fund documents / tool service 边界。
- 禁止 Service / UI / Host / 展示层 / LLM prompt 直接消费 raw PDF、raw Docling JSON、PDF cache path、本地路径、URL secret 或 parser private payload。
- Dayu 只能作为架构参考和能力来源；禁止直接引入 `dayu-agent`、`dayu.host`、`dayu.engine` 作为生产 runtime。
- 复制或改写 Dayu 代码必须先经过 license/compliance gate。
- Docling 为当前 production path：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback 路线。
- 禁止做与 `pdfplumber` 的替代路线比较。
- 结构化字段抽取、自动报告、信号评分已通过正式 Slice 准入（10C/10F/10G/11C/11D/13A/13B/14A/14C），不再受 MVP 禁止条款约束。
- 真实 LLM 接入必须位于已实现的 fake/injected LLM tool-loop contract 之后；不得让 LLM provider、prompt 或 adapter 直接读取 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、`local_import_id` 或 secret。
- 当前 LLM provider 支持 DeepSeek 与 Mimo（OpenAI-compatible adapter）；暂不需要接入 Gemini/OpenAI/Anthropic 等其他 provider。
- live provider smoke 必须显式 opt-in；默认 pytest 不得联网、不得读取真实 API key、不得记录 raw provider response 或新增 artifact。
- 新增 LLM 驱动的 CLI 用户入口（如 `fund-checklist ask`、streaming、interactive mode）必须另开裁决。

## 身份与失败分类

- `document_id` 表示内容身份，用于 public reading tools，格式固定为 `fund_code-year-report_type-fingerprint_prefix`。
- `fingerprint_prefix` 使用 `content_fingerprint` 前 16 位 hex。
- `local_import_id` 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入；重复导入相同 PDF 时复用 `document_id`。
- `share_class` 为可选 metadata；当前不强制解析，不参与 `document_id`；无法明确 A/C 类时记录为 `null`，不得从文件名或标题猜测。
- `report_type` 当前仅支持 `annual_report`；`semiannual_report` / `quarterly_report` 保留为未来扩展，不进入当前实现。
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
- 确定性信号评分 (6 指标, 135→100 归一化)
- 8 章分析报告生成 (13A 模板填充 + 13B LLM 定性分析)
- 三层审计管道 (14C: 程序+LLM+复核, 4 类 22 项)
- Host 生命周期 (12A: timeout/event tracing)
- 披露完整性审计 (12B/12C)
- CLI 9 个子命令：`read` / `multi-year` / `import` / `holdings` / `allocation` / `fees` / `audit` / `deep-audit` / `generate`

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
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

## 代码与文档同步

- Python 代码使用类型注解和 dataclass / Protocol 等现代特性。
- 函数、类、模块必须有中文 docstring，说明参数、返回值、异常。
- 复杂逻辑使用简短中文注释说明意图。
- 修改 `fund_agent/fund/` 时同步更新 `fund_agent/fund/README.md`。
- 修改 `fund_agent/agent/` 时同步更新 `fund_agent/agent/README.md`。
- 修改 `fund_agent/host/` 时同步更新 `fund_agent/host/README.md`。
- 修改分层关系、Service/Host/Agent/Fund 边界时同步更新 `fund_agent/README.md` 和 `docs/design.md`。
- 修改测试结构或命令时同步更新 `tests/README.md`。
- 项目根 `README.md` 只写用户成功路径，不展开内部机制。

## 禁止事项

- 禁止直接输出“买入”“卖出”投资建议。
- 禁止预测未来收益或市场走势。
- 禁止超出公开披露信息的因果推断。
- 禁止基金经理动机猜测。
- 禁止删除或覆盖未明确属于当前任务的修改。

## 代码规范

- 禁止把显式参数塞进 `extra_payload`；公共参数必须显式声明。
- 禁止魔法字符串/魔法数字；source kind、failure code、tool name、locator kind 应集中定义。
- 禁止任何 Agent 用“逻辑上完成”“应该通过”“已按计划完成”替代测试输出。

## 必须事项

- root cause 必须逻辑/数据同源，禁止用间接证据代替。
- 所有工具输出必须可溯源到年报 locator。
- 所有外部来源、PDF、Docling、parser 失败必须 fail-closed 或显式分类。
- 输出下一步时必须给出最小可执行验证问题或命令。
