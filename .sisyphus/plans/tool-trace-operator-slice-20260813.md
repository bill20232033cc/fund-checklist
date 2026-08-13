# Tool Trace 只读分析器（operator 层）slice（2026-08-13 规划）

## 依据

- `docs/research/dayu-agent-r-research-20260810.md` §5 建议 3：「Tool Trace operator 对齐：只读分析器边界」。
- §2.2.7 已验证事实：dayu 路径为 `CLI -> Service path discovery/publication -> Host Analyzer -> Tool Trace projection/resolver`；Analyzer 只读消费派生 trace，不成为 durable truth。借鉴点原文：「fund-checklist 已有 `--enable-tool-trace`（AgentRunResult.tool_trace），可对照补 operator 层与「分析器只读」边界」。
- 概念参考（仅边界对齐，不复制代码；Apache-2.0 license gate 记录在案）：`dayu/service/tool_trace_analysis.py`（发布边界：Service 不解释业务语义、不读 Host durable internals）+ `dayu/host/tool_trace_analysis.py`（`analyze_tool_trace(source, policy)`：显式输入 + typed policy -> immutable report；renderer 只消费 report）。
- 本地现状（grep 验证）：
  - `AgentRunResult.tool_trace: tuple[ToolTraceEntry]`，`ToolTraceEntry` = tool_name / arguments / result_kind / failure_code（`fund_agent/agent/tool_loop.py:36`）；LLM runner 经 `_trace_entry` 构造（`llm_tool_loop.py:1938`）。
  - `AskQuestionResult.tool_trace: tuple[ToolTraceEntry]`（`fund_agent/service/models.py:1194`）；ask 流式路径 `service.ask_question(..., on_event=...)` 返回 result（`cli/main.py:465-486`）。
  - `ChatTurnResponse.tool_trace: tuple[str, ...]` 为字符串摘要（`chat_service.py:95`）；session `Turn.tool_trace` / `Turn.tool_calls` 为持久化派生视图（`session_store.py:187`）。
  - 已有只读统计先例：`MinimalHost._compute_tool_trace_summary`（total/success/failure，`minimal_host.py:423`）；CLI `--enable-tool-trace`（ask 流式 TOOL_EVENT 实时显示，`cli/main.py:439-459`；interactive 每轮 `[工具调用: ...]`，`cli/main.py:1380-1382`）。
  - 缺口：无独立「operator 层」——没有结构化 report（findings / limitations）、无 typed policy、无 deterministic JSON renderer、无「分析器只读」显式契约。

## 目标

1. 新增「Tool Trace 只读分析器」`fund_agent/agent/tool_trace_analysis.py`：纯函数集，只读消费显式传入的派生 trace（`tuple[ToolTraceEntry]`）+ typed policy，输出 immutable structured report。
2. 显式「只读分析器边界」：模块 docstring + 函数签名锁定——不读 session / durable internals、不写任何状态、不落盘、不成为 truth 源；函数只接受 `(trace, policy)` 两个参数。
3. deterministic findings：失败调用、重复失败、大参数载荷三类确定性规则；limitations 固定声明 trace 边界。
4. deterministic JSON renderer（sort_keys / ensure_ascii=False / indent=2 / 尾换行）。
5. CLI 接线（验收约束：必须包含 CLI 端到端 smoke）：ask 流式路径成功分支，`--enable-tool-trace` 开启且 trace 非空时，在现有输出后追加分析行（增量，不改现有 TOOL_EVENT 实时显示与 JSON 输出）。

## 非目标

- 不接 interactive / read / generate 路径（interactive trace 为字符串摘要 `ChatTurnResponse.tool_trace`，本 slice 不支持字符串摘要输入，留作 backlog）。
- 不支持 session `ToolCallSummary` / 字符串摘要输入；分析器只接受 `tuple[ToolTraceEntry]`。
- 不做 Markdown renderer（只做 JSON renderer）。
- 不新增 CLI 子命令。
- 不引入 dayu 代码/模块（license gate：仅概念对齐）。
- 不改 `AgentRunResult` / `ToolTraceEntry` / `AskQuestionResult` / `StreamEvent` / `ToolResult` / `FailureCode` 公共契约。
- 不改现有 `--enable-tool-trace` 的 TOOL_EVENT 实时显示、interactive `[工具调用: ...]` 打印与 ask JSON 输出。
- 不 commit / push。

## 决策

1. 新模块放 `fund_agent/agent/`（与 `ToolTraceEntry` 同层；Agent 层职责「ToolRegistry / ToolTrace / tool loop」，design.md §3.4）。
2. `analyze_tool_trace(trace, policy)` 只接受显式类型：`trace: tuple[ToolTraceEntry, ...]` + `policy: ToolTraceAnalysisPolicy`；类型不符抛 `TypeError`（与 `build_diagnostic_payload` 显式契约一致）。
3. `ToolTraceAnalysisPolicy`（frozen）：`large_argument_chars: int = 120`（arguments 确定性序列化长度阈值）；不引入多余字段。
4. arguments 确定性序列化：`json.dumps(arguments, ensure_ascii=False, sort_keys=True)`。
5. failure_code 归一化：`entry.failure_code.value`（与现有 CLI JSON 输出 `main.py:430` 的 `r.failure_code.value if r.failure_code else None` 一致），不使用 `str(entry.failure_code)`。
6. findings 确定性规则（基于现有字段，无随机/时间依赖）：
   - `failed_call`：每条 `result_kind == "failure"` 的 entry 一条，detail 含 failure_code（无则「无分类」）。
   - `repeated_failure`：同一 `(tool_name, failure_code)` 出现 ≥2 次补一条，detail 含出现次数；与 failed_call 并行不互斥。
   - `large_arguments`：arguments 序列化长度 > 阈值一条，detail 含长度与阈值。
   - 空 trace → summary 全 0、findings 空、limitations 固定 4 条。
7. `ToolTraceAnalysisReport`（frozen）：summary（total/success/failure/unique_tools）、by_tool（按首次出现顺序，failure_codes 去重保序）、findings、limitations（固定 4 条：① trace 是派生视图，不含 raw provider response / raw tool payload；② arguments 仅含 public reading tool 显式参数（契约不含本地路径 / raw payload）；③ provider 首轮失败（next_step 内）trace 为空，报告中显示为 0 次调用；④ 本分析只读消费显式传入的派生 trace，不读 session / durable internals，不写任何状态，不成为 truth 源）。
8. JSON renderer：`tool_trace_analysis_to_json(report)` → `json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2) + "\n"`；report 类型不符抛 `TypeError`。
9. CLI 接线点：`_run_ask_command` 流式分支 `result = service.ask_question(...)` 成功后（`cli/main.py` 约 477-486，`return SUCCESS_EXIT_CODE` 前）：`show_tool_trace` 为真且 `result.tool_trace` 非空时，调 `analyze_tool_trace(result.tool_trace, ToolTraceAnalysisPolicy())`，打印：
   - `[工具分析: 共 {total} 次 / 成功 {success} / 失败 {failure}]`
   - 每条 finding 一行 `[工具分析] {detail}`
   现有 TOOL_EVENT 实时显示保持不变；未开启 flag 时零新增输出（回归保护）。

## 规格

### 模块：`fund_agent/agent/tool_trace_analysis.py`（新增）

- 模块 docstring：中文，声明「Tool Trace 只读分析器（operator 层）」边界（对齐 dayu 概念；自实现；纯函数；不读 session/durable、不写状态、不成为 truth 源）。
- 组件：
  - `ToolTraceAnalysisPolicy`（frozen dataclass）：`large_argument_chars: int = 120`
  - `ToolTraceRunSummary`（frozen）：`total: int` / `success: int` / `failure: int` / `unique_tools: int`
  - `ToolTraceToolStat`（frozen）：`tool_name: str` / `total: int` / `success: int` / `failure: int` / `failure_codes: tuple[str, ...]`
  - `ToolTraceFinding`（frozen）：`kind: Literal["failed_call", "repeated_failure", "large_arguments"]` / `tool_name: str` / `detail: str`
  - `ToolTraceAnalysisReport`（frozen）：`summary: ToolTraceRunSummary` / `by_tool: tuple[ToolTraceToolStat, ...]` / `findings: tuple[ToolTraceFinding, ...]` / `limitations: tuple[str, ...]`
  - `analyze_tool_trace(trace: tuple[ToolTraceEntry, ...], policy: ToolTraceAnalysisPolicy) -> ToolTraceAnalysisReport`
  - `tool_trace_analysis_to_json(report: ToolTraceAnalysisReport) -> str`
- 内部私有归一化：`tool_name = str(entry.tool_name)`；`arguments_text = json.dumps(entry.arguments, ensure_ascii=False, sort_keys=True)`；`failure_code = entry.failure_code.value if entry.failure_code else None`（与 `main.py:430` 一致，不使用 `str(...)`）。
- 类型注解 + 中文 docstring（参数/返回/异常），符合代码规范。

### 接线：`fund_agent/cli/main.py`（仅 ask 流式成功分支）

- `_run_ask_command` 流式分支，`result = service.ask_question(...)` 后、`if result.failure is not None:` 分支之后、`return SUCCESS_EXIT_CODE` 之前插入分析输出块。
- import：`from fund_agent.agent.tool_trace_analysis import ToolTraceAnalysisPolicy, analyze_tool_trace`（局部 import 或顶部 import 均可，二选一，禁止重复）。
- 硬约束：不改变 ask 流式现有输出；`--no-stream` JSON 输出不含分析字段；失败分支不输出分析行。

### 测试

#### `tests/fund/agent/test_tool_trace_analysis.py`（新增）

- summary：混合 trace（2 成功 + 1 失败）→ `total=3 / success=2 / failure=1 / unique_tools` 正确。
- by_tool：多工具聚合正确；`failure_codes` 去重保序；首次出现顺序显式断言——构造 trace 顺序 `toolA -> toolB -> toolA`，断言 `by_tool` 顺序为 `(toolA, toolB)`。
- findings：
  - `failed_call`：失败 entry 一条，detail 含 failure_code；无 failure_code 时 detail 含「无分类」。
  - `repeated_failure`：同一 `(tool_name, failure_code)` ≥2 次补一条，detail 含次数。
  - `large_arguments`：arguments 序列化超阈值一条；未超阈值不产生；边界断言——序列化长度 `== large_argument_chars` 时不产生 finding，`== large_argument_chars + 1` 时产生。
- 空 trace：summary 全 0、findings 空、limitations 恰好 4 条。
- TypeError 契约：trace 非 tuple / 元素非 `ToolTraceEntry` / policy 非 `ToolTraceAnalysisPolicy` → `TypeError`。
- 确定性：同输入两次调用 report 相等。
- JSON renderer：deterministic（两次输出一致）、`sort_keys`、`ensure_ascii=False`（中文不转义）、尾换行；report 类型不符 → `TypeError`。
- 只读边界：`analyze_tool_trace` 签名只接受 `(trace, policy)`（无 session/路径/IO 参数），模块 docstring 含只读声明。

#### `tests/fund/cli/test_cli.py`（增补 1 用例）

- `test_ask_stream_enable_tool_trace_outputs_analysis`：monkeypatch `FundReadingService.ask_question` 返回带 tool_trace（含 1 条失败、`ToolTraceEntry` 类型）的 `AskQuestionResult`（复用 `test_ask_no_stream_outputs_json_on_success` 的 fake 模式）；`_run(["ask", "问题", "--document-id", "test-doc-id", "--enable-tool-trace", "--work-dir", str(tmp_path)])`；断言 stdout 含 `[工具分析:` 行与 `[工具分析]` finding 行；不加 `--enable-tool-trace` 时 stdout 不含 `[工具分析:`（回归保护）。

## Allowed write set（DS 只允许动这些）

- `fund_agent/agent/tool_trace_analysis.py`（新增）
- `fund_agent/cli/main.py`（仅 ask 流式成功分支分析输出块 + import）
- `fund_agent/agent/README.md`（Tool Trace 只读分析器一节，1-3 行）
- `tests/fund/agent/test_tool_trace_analysis.py`（新增）
- `tests/fund/cli/test_cli.py`（增补 1 用例）
- `tests/README.md`（测试范围一句话）

禁止动：AGENTS.md、docs/design.md、docs/implementation-control.md（controller 在 MiMo plan review ACCEPTED 后回写）；禁止 commit / push；禁止新增第三方依赖；禁止改 `AgentRunResult` / `ToolTraceEntry` / `AskQuestionResult` / `StreamEvent` / `ToolResult` / `FailureCode` / public 方法签名；禁止新增 CLI 子命令；禁止改 `--no-stream` JSON 输出与 TOOL_EVENT 实时显示；禁止接 interactive / read / generate 路径。

## 必须运行的测试命令（跑完把输出贴进交接报告）

1. `uv run pytest tests/fund/agent/test_tool_trace_analysis.py -v --tb=short`
2. `uv run pytest tests/fund/cli/test_cli.py -k "ask" -v --tb=short`
3. `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`

## Stop condition

全部测试通过后停止。输出交接报告：changed files、diff 摘要、实际测试命令与输出。失败时报告最小失败原因，不得声称完成。

## 交接报告格式（回复给 controller）

- changed files: 列表
- diff 摘要: 每文件 1-2 行
- 测试: 实际命令 + passed/failed 数字
- 失败/风险: 若有
