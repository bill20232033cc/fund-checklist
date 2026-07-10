# Repository Agent Rules

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

当前优先方向是 **基金年报阅读工具层**。

目标主链路：

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

这条主线的目标是让 Agent 稳定阅读基金年报、检索章节/表格、返回可引用片段；不是字段抽取、自动报告、投资判断、报告渲染或发布就绪判定。

## 硬边界

- 对基金文档的存取必须通过统一 Fund documents / tool service 边界。
- 禁止 Service / UI / Host / 展示层 / LLM prompt 直接消费 raw PDF、raw Docling JSON、PDF cache path、本地路径、URL secret 或 parser private payload。
- Dayu 只能作为架构参考和能力来源；禁止直接引入 `dayu-agent`、`dayu.host`、`dayu.engine` 作为生产 runtime。
- 复制或改写 Dayu 代码必须先经过 license/compliance gate。
- Docling production path for local-PDF MVP 已准入：PDF 通过 integrity check 后进入 `DoclingConverter`，Docling JSON 通过 parser_health 后进入 `DoclingDocumentStore`。
- 禁止把 Docling 改回 candidate-only、benchmark-before-admission 或 `pdfplumber` fallback 路线。
- 禁止做与 `pdfplumber` 的替代路线比较；禁止做字段抽取 correctness benchmark。
- 若未来要走 `Docling JSON -> 字段抽取 -> 自动报告/判断`，必须另开设计与准入 gate，不得塞进阅读工具 MVP。
- 真实 LLM 接入必须位于已实现的 fake/injected LLM tool-loop contract 之后；不得让 LLM provider、prompt 或 adapter 直接读取 raw PDF、raw Docling JSON、本地路径、cache path、repository/private loader、`local_import_id` 或 secret。
- Post-MVP Slice 8B 只接 DeepSeek OpenAI-compatible API；Mimo / MiMo 与多 provider 后置，不得在 8B 混入。
- live provider smoke 必须显式 opt-in；默认 pytest 不得联网、不得读取真实 API key、不得记录 raw provider response 或新增 artifact。
- 真实 LLM slice 默认不新增 CLI 用户入口；`fund-checklist ask`、streaming、多 provider、prompt framework、richer QA/eval 必须另开裁决。

## 身份与失败分类

- `document_id` 表示内容身份，用于 public reading tools，格式固定为 `fund_code-year-report_type-fingerprint_prefix`。
- `fingerprint_prefix` 使用 `content_fingerprint` 前 16 位 hex。
- `local_import_id` 表示导入事件身份，仅用于审计 metadata，不作为 public tool 输入；重复导入相同 PDF 时复用 `document_id`。
- `share_class` 为可选 metadata；MVP 不强制解析，不参与 `document_id`；无法明确 A/C 类时记录为 `null`，不得从文件名或标题猜测。
- `report_type` MVP 首批仅支持 `annual_report`；`semiannual_report` / `quarterly_report` 保留为未来扩展，不进入当前实现。
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

## MVP 验收

阅读工具 MVP acceptance requires:

- local PDF import
- PDF integrity failure classification
- Docling conversion
- DoclingDocumentStore parser health
- seven FundDocumentToolService tools
- locator + citation + redaction
- minimal Host/Agent tool loop smoke

MVP 不接受 only ToolService tests。MVP closeout 必须同时通过：

1. `FundDocumentToolService` 离线工具 smoke。
2. `test_agent_tool_loop_searches_then_reads_section`。

最小 Host / Agent loop 期望 trace：

```text
1. Agent 调用 search_document(document_id, query="基金经理")
2. Agent 拿到 section_ref / locator
3. Agent 调用 read_section(document_id, section_ref)
4. 最终回答只引用 tool result，不泄漏本地路径或 raw Docling JSON
```

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
- 禁止任何 Agent 用“逻辑上完成”“应该通过”“已按计划完成”替代测试输出。
- 若调用 code-is-cheap 相关 skill，必须显式声明本项目使用 CIC-lite；不得启用完整 gateflow / phaseflow / release-readiness。

## Review 规则

- LLM reviewer（DeepSeek 等）处理大 diff 时可能捏造不存在的代码并给出"修复建议"。
- 对 review findings 中的 P0/P1 项，必须先 `grep -n` 确认代码存在再行动。
- review prompt 应要求 reviewer 先列出代码行号和实际内容，再给出判断。
- 不要盲目信任 review 结论——reviewer 也会 hallucinate。

## 测试规则

- 每次代码修改必须同步新增或更新测试。
- 新阅读工具 MVP plan 至少列出以下测试文件和测试名：

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
- test_agent_tool_loop_does_not_receive_raw_docling_json
```

- MVP 必须包含至少一个仓库内真实本地样本 PDF 的 Docling conversion smoke。
- fake fixture 只能测试边界和错误；不得用于证明 production conversion path。
- 最小验证命令固定为：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py
```

## 代码与文档同步

- Python 代码使用类型注解和 dataclass / Protocol 等现代特性。
- 函数、类、模块必须有中文 docstring，说明参数、返回值、异常。
- 复杂逻辑使用简短中文注释说明意图。
- 禁止把显式参数塞进 `extra_payload`；公共参数必须显式声明。
- 禁止魔法字符串/魔法数字；source kind、failure code、tool name、locator kind 应集中定义。
- 修改 `fund_agent/fund/` 时同步更新 `fund_agent/fund/README.md`。
- 修改 `fund_agent/agent/` 时同步更新 `fund_agent/agent/README.md`。
- 修改 `fund_agent/host/` 时同步更新 `fund_agent/host/README.md`。
- 修改分层关系、Service/Host/Agent/Fund 边界时同步更新 `fund_agent/README.md` 和 `docs/design.md`。
- 修改测试结构或命令时同步更新 `tests/README.md`。
- 项目根 `README.md` 只写用户成功路径，不展开内部机制。

## 禁止事项

- 禁止把阅读工具 MVP 扩大成字段抽取、自动报告、投资判断、数据仓库晋升或发布就绪判定。
- 禁止直接输出“买入”“卖出”建议；阅读工具层默认不输出判断。
- 禁止预测未来收益或市场走势。
- 禁止超出公开披露信息的因果推断。
- 禁止基金经理动机猜测。
- 禁止删除或覆盖未明确属于当前任务的修改。

## 必须事项

- 先判断当前任务属于“阅读工具路径”还是“后续报告/字段抽取/投资判断路径”。
- root cause 必须逻辑/数据同源，禁止用间接证据代替。
- 所有工具输出必须可溯源到年报 locator。
- 所有外部来源、PDF、Docling、parser 失败必须 fail-closed 或显式分类。
- 输出下一步时必须给出最小可执行验证问题或命令。
