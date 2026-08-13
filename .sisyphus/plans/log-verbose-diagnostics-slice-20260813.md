# 日志 VERBOSE 级 + 有界脱敏诊断载荷 slice（2026-08-13 规划）

## 依据

- `docs/research/dayu-agent-r-research-20260810.md` §5 建议 2：「日志 VERBOSE 级 + 有界脱敏诊断载荷：与「不记录 raw provider response」约束对齐」。
- 已验证事实（研究 §4 验证表）：dayu `runtime/log_levels.py` 定义 `VERBOSE_LOG_LEVEL = 15`（介于 DEBUG 10 / INFO 20 之间）。仅概念级借鉴（级别数值与语义），不复制 dayu 代码；Apache-2.0 license gate 记录在案。
- 本地现状（grep 验证）：
  - 仓库无任何日志级别配置：`basicConfig / dictConfig / fileConfig / setLevel / addHandler` 在 `fund_agent/` 与 `tests/` 均 0 命中；现有日志仅 4 个模块的 `logger.warning`（`llm_tool_loop.py:535/733/1052/1177`、`chapter_generator.py:57/1128`、`audit_pipeline.py:2507`、`extraction.py:1526/1802/1926/1961/2734`），无 INFO/DEBUG/VERBOSE 观测层。
  - LLM provider 异常消息已保证不包含 raw body：`_parse_response` 只抛固定 `_MALFORMED_MESSAGE`（`deepseek_llm.py:814-826`）；但缺少统一的有界脱敏诊断载荷构造器，未来新增诊断日志时无硬约束可依。
  - 环境变量惯例：`FUND_CHECKLIST_LLM_PROVIDER / FUND_CHECKLIST_CHAPTER_CONCURRENCY / FUND_CHECKLIST_RUN_LIVE_DEEPSEEK`；新增 `FUND_CHECKLIST_LOG_LEVEL` 沿用同一前缀。
  - 现有约束锚点：AGENTS.md「live provider smoke 必须显式 opt-in；默认 pytest 不得联网、不得读取真实 API key、不得记录 raw provider response 或新增 artifact」；「禁止 Service / UI / Host / 展示层 / LLM prompt 直接消费 raw PDF、raw Docling JSON、PDF cache path、本地路径、URL secret 或 parser private payload」；「禁止把显式参数塞进 extra_payload；公共参数必须显式声明」；「禁止魔法字符串/魔法数字」。

## 目标

1. 新增 VERBOSE=15 日志级别（幂等注册 + `verbose()` 帮助函数），作为 INFO 与 DEBUG 之间的诊断级。
2. 新增「有界脱敏诊断载荷」构造器 `build_diagnostic_payload`：显式命名参数、逐字段脱敏 + 截断、总量有界；任何诊断日志不得携带 raw provider response、API key、Bearer token、URL secret、本地绝对路径、工作目录、`local_import_id`。
3. 接通启用路径：`FUND_CHECKLIST_LOG_LEVEL` env（默认 absent 时零行为变更）。
4. 接线 2 个代表性生产诊断点：`llm_tool_loop` run/run_stream 入口；`deepseek_llm._parse_response` malformed 分支（显式证明「不记录 raw provider response」）。

## 非目标

- 不做 Tool Trace operator 对齐（研究 §5 建议 3，backlog 下一项）。
- 不引入 dayu 代码/模块；不复制 `runtime/log_levels.py`。
- 不改现有 `logger.warning` 语义、文案与触发点。
- 不新增 CLI 子命令；interactive `/verbose`（工具调用详情展示）与日志级别互不干扰。
- 不做日志文件 handler / 轮转 / artifact 落盘（默认 stderr）。
- 不改 `StreamEvent` / `ToolResult` / `FailureCode` 公共契约；不改 `FailureCode` 集合。

## 决策

1. VERBOSE = 15，注册名 `"VERBOSE"`（与 dayu 概念对齐；自实现）。
2. 新模块放 `fund_agent/agent/`（本仓库 runtime 层，dayu `runtime/log_levels.py` 的对应层），不新建 package。
3. 启用方式：env `FUND_CHECKLIST_LOG_LEVEL`，合法取值 `DEBUG / VERBOSE / INFO / WARNING / ERROR`；absent 或空值 → no-op（零行为变更，默认测试输出不变）；未知值 → fail-fast `ValueError` 提示合法取值（与 `FUND_CHECKLIST_LLM_PROVIDER` 一致）。
4. `build_diagnostic_payload` 只接受显式命名参数（message 必填；code / document_id / tool_name / provider / query 可选），未知 kwargs 抛 `TypeError`；返回 `dict[str, str]`（仅含非 None 字段）。
5. 有界规则：字段级截断 `MAX_DIAGNOSTIC_FIELD_CHARS = 500` + 后缀 `…(截断)`；总量上限 `MAX_DIAGNOSTIC_TOTAL_CHARS = 2000`；超限按固定顺序丢可选字段（query → provider → tool_name → document_id → code），message 永不丢。
6. 脱敏规则（正则集中定义，禁止散落）：`sk-`/`pk-` API key、`Bearer` token、URL query secret（`api_key/token/secret/signature/sig=`）、`local_import_id`、本地绝对路径（`/Users/`、`/tmp/`、`/private/`、`~`）、工作目录（`.fund_checklist_*`）；替换为 `"***"`。
7. `configure_logging` 只做根 logger `basicConfig`（level + 固定 format）；根已有 handler 时 `basicConfig` 按标准语义 no-op，不强制。
8. 接线点以「不改变现有行为」为边界：verbose 记录是纯增量；malformed 分支的异常语义与消息不变。

## 规格

### 模块 1：`fund_agent/agent/log_levels.py`（新增）

- 常量：`VERBOSE_LOG_LEVEL: int = 15`、`VERBOSE_LOG_NAME: str = "VERBOSE"`、`LOG_LEVEL_ENV: str = "FUND_CHECKLIST_LOG_LEVEL"`、`_ALLOWED_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "VERBOSE", "INFO", "WARNING", "ERROR")`、`_BASIC_FORMAT: str = "%(asctime)s %(levelname)s %(name)s: %(message)s"`。
- `register_verbose_log_level() -> None`：`logging.addLevelName(VERBOSE_LOG_LEVEL, VERBOSE_LOG_NAME)`，幂等。
- `verbose(logger: logging.Logger, message: str, *args, **kwargs) -> None`：先注册，再 `logger.log(VERBOSE_LOG_LEVEL, message, *args, **kwargs)`；logger 有效级别 > 15 时按标准 logging 语义静默。
- `configure_logging(*, env: Mapping[str, str] | None = None) -> None`：
  - `env` 缺省取 `os.environ`。
  - 读 `LOG_LEVEL_ENV`，strip + upper；空值 → 直接 return（no-op）。
  - 不在 `_ALLOWED_LOG_LEVELS` → `raise ValueError(f"{LOG_LEVEL_ENV} 取值必须为 ...")`。
  - `register_verbose_log_level()` 后 `logging.getLevelName(value)` 解析 level（`VERBOSE → 15`），`logging.basicConfig(level=level, format=_BASIC_FORMAT)`。
- 全部函数带中文 docstring（参数 / 返回值 / 异常）。

### 模块 2：`fund_agent/agent/diagnostic_payload.py`（新增）

- 常量：`MAX_DIAGNOSTIC_FIELD_CHARS: int = 500`、`MAX_DIAGNOSTIC_TOTAL_CHARS: int = 2000`、`TRUNCATION_SUFFIX: str = "…(截断)"`、`REDACTION_REPLACEMENT: str = "***"`。
- 脱敏正则（模块级私有元组，每项带简短中文注释说明用途）：
  - `sk-`/`pk-` 前缀 ≥8 位密钥：`(?i)\b(?:sk|pk)-[a-z0-9_-]{8,}\b`
  - Bearer token：`(?i)\bbearer\s+[a-z0-9._-]{8,}\b`
  - URL query secret：`(?i)(api[_-]?key|token|secret|signature|sig)=[^&\s"']+`
  - `local_import_id`（含值）：`local_import_id\s*[:=]?\s*[a-z0-9-]{8,}`
  - 本地绝对路径：`/Users/[A-Za-z0-9_./-]+`、`/tmp/[A-Za-z0-9_./-]+`、`/private/[A-Za-z0-9_./-]+`、`~/?[A-Za-z0-9_./-]*`
  - 工作目录：`\.fund_checklist_[A-Za-z0-9_./-]+`
- `redact_diagnostic_text(text: str) -> str`：按序 `re.sub` 全部替换为 `REDACTION_REPLACEMENT`；幂等。
- `_truncate(text: str, limit: int) -> str`：`len <= limit` 原样返回；否则 `text[:limit] + TRUNCATION_SUFFIX`。
- `build_diagnostic_payload(message: str, *, code: str | None = None, document_id: str | None = None, tool_name: str | None = None, provider: str | None = None, query: str | None = None) -> dict[str, str]`：
  1. 非 None 字段按固定顺序 `("message", "code", "document_id", "tool_name", "provider", "query")` 处理：`str()` → `redact_diagnostic_text` → `_truncate(500)`。
  2. 若总量 > 2000，按 `("query", "provider", "tool_name", "document_id", "code")` 顺序丢弃可选字段（每丢一个重新检查），直到 ≤ 2000；`message` 永不丢弃（500+后缀远小于总量上限，防御性保证）。
  3. 返回仅含非 None 字段的 `dict[str, str]`。
  4. 未知 kwargs → `TypeError`（显式参数契约）。
- 模块级 `verbose` 便捷包装可选：`verbose_diagnostic(logger, message, **fields)` = `verbose(logger, "%s", build_diagnostic_payload(message=message, **fields))`（实现若不加此包装，接线点直接用 `verbose` + `build_diagnostic_payload` 亦可，二选一，禁止两者都写）。

### 接线（不改公共契约）

- `fund_agent/agent/llm_tool_loop.py`：
  - 顶部 import `verbose`（log_levels）与 `build_diagnostic_payload`（diagnostic_payload）。
  - `run()` 循环开始前（`trace` 初始化之后）：`verbose(logger, "LLM tool loop run 开始: %s", build_diagnostic_payload(message="LLM tool loop run 开始", document_id=document_id, query=query))`。
  - `run_stream()` trace 初始化之后、循环开始前同构一行（与 `run()` 对称；首个事件为 METADATA yield，不插入 verbose）。
- `fund_agent/agent/deepseek_llm.py`：
  - 新增模块级 `logger = logging.getLogger(__name__)`。
  - `_parse_response` 两处 `LlmClientFailure(LLM_MALFORMED_RESPONSE, ...)` raise 前：`verbose(logger, "LLM provider response malformed: %s", build_diagnostic_payload(message=_MALFORMED_MESSAGE, code=FailureCode.LLM_MALFORMED_RESPONSE.value))`。
  - 硬约束：任何路径不得把 `body` / raw response 传入日志或 payload（测试断言锁定）。
- `fund_agent/cli/main.py`：`main()` 顶部（argparse 构建前）调用 `configure_logging()`；import 时无副作用。

## 测试（新增/更新，必须覆盖）

### `tests/fund/agent/test_log_levels.py`（新增）

- `VERBOSE_LOG_LEVEL == 15`；`register_verbose_log_level()` 后 `logging.getLevelName("VERBOSE") == 15`，重复调用幂等。
- `verbose()` 在 logger 级别 ≤ 15 时产出记录（caplog，`levelno == 15`，`levelname == "VERBOSE"`），级别 > 15 时静默。
- `configure_logging`：env absent / 空值 → no-op（根 logger level 与 handlers 不变）；`VERBOSE → 15`；未知值 → `ValueError`（消息含合法取值）。

### `tests/fund/agent/test_diagnostic_payload.py`（新增）

- 脱敏用例（`redact_diagnostic_text` 与 `build_diagnostic_payload` 各覆盖）：`sk-` key、`Bearer` token、URL `api_key=` / `token=` / `secret=` / `signature=` / `sig=`、`local_import_id`、`/Users/maomao/...`、`/tmp/...`、`/private/...`、`~`、`.fund_checklist_cli_smoke_xxx`；替换为 `***`。
- raw provider body 样本（含 `"choices"` JSON 结构 + 内嵌 `sk-` key）→ 输出不含原 key，不泄漏 body 结构。
- 边界：单字段 > 500 截断 + 后缀；6 字段全满时总量 > 2000 → 按固定顺序丢可选字段、message 保留；None 字段不出现；同输入两次结果一致（确定性）。
- 契约：未知 kwargs → `TypeError`；`message` 缺失 → `TypeError`。

### `tests/fund/agent/test_llm_tool_loop.py`（增补 1 用例）

- caplog 置级别 15，fake client 跑 `run()`，断言存在 VERBOSE 记录，且 payload 含 `document_id` / `query` 键、无脱敏泄漏；既有用例不受影响。

### `tests/fund/agent/test_real_llm_adapter.py`（增补 1 用例）

- caplog 置级别 15，`QueueTransport` 双 malformed（复用 `_malformed_response()`）触发 `next_step` raise；断言存在 VERBOSE 记录含 `llm_malformed_response`，且不含 raw body 片段。

## Allowed write set（DS 只允许动这些）

- `fund_agent/agent/log_levels.py`（新增）
- `fund_agent/agent/diagnostic_payload.py`（新增）
- `fund_agent/agent/llm_tool_loop.py`（verbose 接线；不得改公共方法签名与现有 warning 行为）
- `fund_agent/agent/deepseek_llm.py`（模块 logger + malformed verbose；不得改异常语义）
- `fund_agent/cli/main.py`（仅 `main()` 入口 1 处 `configure_logging()` 调用 + import）
- `fund_agent/agent/README.md`（日志与诊断载荷一节，1-3 行）
- `tests/fund/agent/test_log_levels.py`（新增）
- `tests/fund/agent/test_diagnostic_payload.py`（新增）
- `tests/fund/agent/test_llm_tool_loop.py`（增补）
- `tests/fund/agent/test_real_llm_adapter.py`（增补）
- `tests/README.md`（测试范围一句话）

禁止动：AGENTS.md、docs/design.md、docs/implementation-control.md（controller 在 MiMo plan review ACCEPTED 后回写）；禁止 commit / push；禁止新增第三方依赖；禁止改 `StreamEvent` / `ToolResult` / `FailureCode` / public 方法签名；禁止新增 CLI 子命令；禁止把 `body` / raw provider response 写入任何日志。

## 必须运行的测试命令（跑完把输出贴进交接报告）

1. `uv run pytest tests/fund/agent/test_log_levels.py tests/fund/agent/test_diagnostic_payload.py -v --tb=short`
2. `uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_real_llm_adapter.py -v --tb=short`
3. `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`

## Stop condition

全部测试通过后停止。输出交接报告：changed files、diff 摘要、实际测试命令与输出。失败时报告最小失败原因，不得声称完成。

## 交接报告格式（回复给 controller）

- changed files: 列表
- diff 摘要: 每文件 1-2 行
- 测试: 实际命令 + passed/failed 数字
- 失败/风险: 若有
