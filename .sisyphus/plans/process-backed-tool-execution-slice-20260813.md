# process-backed 工具执行（可抢占超时）slice（2026-08-13 规划）

## 依据

- `docs/research/dayu-agent-r-research-20260810.md` §2.1.4（高价值第 4 项，代码已验证）：dayu `runtime/interruptible_process.py` 的「取消/超时 = 杀子进程」模式——Doc / Fins read 与 Web blocking 工具生产路径使用子进程执行，使 Host 取消或超时时不等待同进程 blocking I/O 自然结束；模块只负责子进程启动、结果回收、terminate/kill 与 bounded close。落地风险：中。
- 仅概念级借鉴（模式语义），不复制 dayu 代码；Apache-2.0 license gate 记录在案；不引入 `dayu-agent` 作为 production runtime（AGENTS.md 硬约束）。
- 本地现状（grep / 读码验证，2026-08-13）：
  - `MinimalHost.run()`（`fund_agent/host/minimal_host.py:141`）在 daemon 线程跑 Agent loop，`thread.join(timeout=self._timeout)`；超时后返回 `timed_out=True` 空结果，但**线程不杀**——worker 继续跑到自然结束（12A 已知缺口）；`run_stream` 同构。
  - `DoclingConverter.convert_pdf()`（`fund_agent/fund/document_tools/docling_converter.py:62`）同步阻塞执行 `converter.convert(stream)`；超时仅靠 Docling 内部 `document_timeout`（`_build_docling_converter` 传入 `PdfPipelineOptions(document_timeout=...)`），模型下载 / OCR / C++ 路径卡死时内部超时不可靠、且无任何进程可杀。
  - 调用链：CLI `import`/`read` → `FundReadingService.import_local_report` / `read_local_report` → `_prepare_completed_report` → `_create_completed_store`（`fund_agent/service/extraction.py:4215-4216`）→ `converter.convert_pdf(...)`；converter 默认 `SINGLE_PDF_SMOKE_TIMEOUT_SECONDS = 300`（`constants.py:77`）。
  - 分层约束：`fund_agent/fund/` 不 import `agent` / `host` / `service` / `cli`（grep 0 命中），原语只能放 fund 层或更低，避免分层倒置。
  - 既有测试：`tests/fund/document_tools/test_docling_conversion.py` 已用真实样本 `基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf` 走真实 Docling 转换（生产路径），并用无效 bytes 验证 `docling_convert_failed` 分类。

## 目标

1. 新增自实现的进程隔离执行原语（子进程启动 / 结果回收 / terminate→grace→kill / bounded close），对应 dayu `interruptible_process.py` 的语义边界。
2. 将 `DoclingConverter.convert_pdf` 的阻塞转换移入可抢占子进程：硬 deadline 到达即 terminate + kill，父进程不再等待同进程 blocking I/O 自然结束；超时/失败按既有失败分类（`unavailable` / `docling_convert_failed`）fail-closed，不残留部分 JSON。
3. 验收必须含 Host / Agent loop 或 CLI 端到端 smoke（AGENTS.md 硬约束）：真实样本 PDF 经 CLI `import` 在子进程内完成转换并落盘。

## 非目标

- 不做 Host 级整 loop 进程隔离（把整个 Agent loop 放进子进程）。原因：Agent 持有 LLM client（httpx session）、tool service 与内存会话状态，spawn 序列化脆弱、收益集中在阻塞工具层；研究 §5 决策 5 将 wait-resume / process-backed 的架构级引入定位为「等真实异步需求」，本 slice 只在阻塞工具层落地。Host 12A 的 thread timeout 语义与 `timed_out` 契约不变。
- 不引入 `fund_agent/runtime/` 新分层；原语作为工具执行支撑放在 `fund_agent/fund/document_tools/`，架构坐标系不变。
- 不做「read / LLM 调用」的进程化（LLM 已有有界重试与 max_iterations；read 为本地快速读）。
- 不新增 CLI 子命令、不新增 CLI 参数、不新增依赖（stdlib `multiprocessing` / `pickle` 即可）。
- 不改 `FailureCode` / `DocumentToolError` / `DoclingConversionResult` / `ReportIdentity` 公共契约；不改 `MinimalHost` 公共契约。
- 不复制 dayu `interruptible_process.py` 代码。

## 决策

1. 原语模块：新增 `fund_agent/fund/document_tools/interruptible_process.py`（fund 层，供工具执行使用；模块 docstring 声明「进程隔离执行原语：子进程启动 / 结果回收 / terminate+kill / bounded close；概念对齐 dayu runtime/interruptible_process.py，自实现不复制」）。
2. 原语 API（最小面）：
   - `SubprocessTimeoutError(TimeoutError)`：deadline 内未完成，已执行 terminate→grace→kill→reap。
   - `SubprocessExecutionError(RuntimeError)`：子进程执行异常（携带 `child_type` / `child_message`）或无结果崩溃。
   - `InterruptibleProcess`：`__init__(*, target, args=(), timeout, grace_period=2.0)`（timeout<=0 / grace<0 抛 `ValueError`）；`start()` / `join(timeout)` / `terminate()` / `kill()` / `close()` / `is_alive()` / `run()`（一站式：start→join(deadline)→未完成则 terminate→grace→kill→join→close 后抛 `SubprocessTimeoutError`；完成则回收结果→close→返回 / 抛 `SubprocessExecutionError`）。
   - `run_in_subprocess(target, args=(), *, timeout, grace_period=2.0) -> Any`：薄封装 `InterruptibleProcess.run()`。
3. 实现机制：`multiprocessing.get_context("spawn")`；模块级 `_child_entry(parent_conn, target, args)`：`try: result = target(*args); parent_conn.send(("ok", result))` / `except BaseException as exc: parent_conn.send(("error", (type(exc).__name__, str(exc))))` / `finally: parent_conn.close()`；父子用 `Pipe(duplex=False)` 传单次 envelope（picklable）。子进程 `daemon=False`，父进程显式 join 回收，不产生 zombie；kill 后 `join(timeout=5)` 再 `close()`（bounded close）。子进程崩溃（envelope 缺失 / EOFError）→ `SubprocessExecutionError`。
4. 接线点：`DoclingConverter.convert_pdf`。`timeout_seconds` 语义升级为「既是 Docling 内部 document_timeout，也是硬子进程 deadline」；公共签名与返回不变。子进程只运行转换（build converter → convert → save JSON），不碰 Agent / LLM / session。
5. 子进程入口：`docling_converter.py` 新增模块级 `_run_conversion_in_child(pdf_bytes, do_ocr, timeout_seconds, output_json_path) -> dict[str, str | None]`（返回 `{"failure_code": None, "message": None}` 或分类结果），复用既有 `_build_docling_converter` / `_build_document_stream` / `_save_docling_json` / `_is_unavailable_exception`，分类逻辑从父进程移入子进程（ImportError/OSError → `unavailable`；`has_timeout_errors`/`TimeoutError` → `unavailable`「Docling 转换超时」；`has_parse_errors`/document is None → `docling_convert_failed`；`_is_unavailable_exception` → `unavailable`；save OSError → `unavailable`）。
6. 父进程映射与清理：`SubprocessTimeoutError` → 删除 `json_path`（若存在）→ `DocumentToolError(UNAVAILABLE, "Docling 转换超时")`；`SubprocessExecutionError` → 清理 → `DocumentToolError(UNAVAILABLE, "Docling 转换子进程异常")`；`failure_code == "docling_convert_failed"` → `DocumentToolError(DOCLING_CONVERT_FAILED, message)`；`"unavailable"` → 清理 → `DocumentToolError(UNAVAILABLE, message)`。统一保证：convert_pdf 失败 ⇒ `json_path` 不残留（调用方 `_create_completed_store` 保证调用前不存在）。
7. 测试策略：原语用**真实子进程** + stdlib 顶层可调用验证（`os.getpid` 成功 / `time.sleep(60)` 超时+杀 / `int("x")` 子进程异常），不依赖测试模块可导入性；转换器边界用 fake 注入私有方法 `_run_child_conversion`（只测边界与错误，生产路径由真实转换测试证明——AGENTS.md fake fixture 规则）。

## 规格

### 模块 1：`fund_agent/fund/document_tools/interruptible_process.py`（新增）

- 常量：`DEFAULT_TERMINATE_GRACE_SECONDS: float = 2.0`、`DEFAULT_JOIN_AFTER_KILL_SECONDS: float = 5.0`。
- `class SubprocessTimeoutError(TimeoutError)`：docstring 说明 deadline 语义与已执行的清理动作。
- `class SubprocessExecutionError(RuntimeError)`：字段 `child_type: str | None`、`child_message: str | None`；docstring 说明 envelope 异常 / 崩溃两种来源。
- `class InterruptibleProcess`：
  - `__init__(self, *, target: Callable[..., Any], args: tuple = (), timeout: float, grace_period: float = DEFAULT_TERMINATE_GRACE_SECONDS)`：`timeout > 0`、`grace_period >= 0` 校验（否则 `ValueError`）；`target` 必须是 spawn 可按引用序列化的顶层可调用（模块级函数 / builtin）。
  - 私有 `_spawn()`：`mp.get_context("spawn").Process(target=_child_entry, args=(self._parent_conn, self._target, self._args), daemon=False)`。
  - `run() -> Any`：spawn → `join(timeout)`；若 `is_alive()`：`terminate()` → `sleep(grace_period)` → `kill()` → `join(DEFAULT_JOIN_AFTER_KILL_SECONDS)` → `close()` → raise `SubprocessTimeoutError`；否则 `_receive_result(timeout=5.0)`（`parent_conn.poll` + `recv`；`EOFError`/`Empty` → `SubprocessExecutionError("子进程未返回结果")`；envelope `("error", (type, message))` → `SubprocessExecutionError`，`("ok", result)` → return result）→ `close()`。`run()` 与 `start()` 互斥：已 `start()`（或已 `run()`）的实例再调 `run()` 抛 `RuntimeError`，避免第二个子进程孤儿化。
  - `start()` / `join(timeout)` / `terminate()` / `kill()` / `close()` / `is_alive()`：委托内部 `mp.Process`；`close()` 幂等（重复调用不抛）；`run()` 后再次 `run()` 抛 `RuntimeError`（单次生命周期）。
- `run_in_subprocess(target, args=(), *, timeout: float, grace_period: float = DEFAULT_TERMINATE_GRACE_SECONDS) -> Any`：薄封装。
- 全部函数/类带中文 docstring（参数 / 返回值 / 异常）。

### 模块 2：`fund_agent/fund/document_tools/docling_converter.py`（修改）

- 新增模块级 `_run_conversion_in_child(pdf_bytes: bytes, do_ocr: bool, timeout_seconds: int, output_json_path: str) -> dict[str, str | None]`：按决策 5 复用既有 helper，返回 envelope dict；docstring 说明「仅在子进程内执行，父进程不直接调用」。
- `convert_pdf` 重构为：
  1. `document_dir.mkdir`（不变）。
  2. 调用新增私有方法 `self._run_child_conversion(pdf_bytes, do_ocr, json_path) -> dict[str, str | None]`（内部 `run_in_subprocess(_run_conversion_in_child, args=(pdf_bytes, do_ocr, self._timeout_seconds, str(json_path)), timeout=float(self._timeout_seconds))`）。
  3. 按决策 6 映射 `SubprocessTimeoutError` / `SubprocessExecutionError` / envelope `failure_code` → `DocumentToolError`；失败路径统一清理 `json_path`。
  4. 成功返回 `DoclingConversionResult(document_id, docling_json_ref, json_path, elapsed_seconds=time.monotonic() - started_at)`（不变）。
- 公共签名与返回不变：`DoclingConverter.__init__(output_root, *, timeout_seconds=SINGLE_PDF_SMOKE_TIMEOUT_SECONDS, do_ocr=False)`、`convert_pdf(*, identity, pdf_bytes)`。
- 既有 `_build_docling_converter` / `_build_document_stream` / `_save_docling_json` / `_is_unavailable_exception` 保留、语义不变（现在由子进程入口复用）。

### 测试

新增 `tests/fund/document_tools/test_interruptible_process.py`（真实子进程，无 fake）：
1. `test_run_in_subprocess_returns_child_result`：`run_in_subprocess(os.getpid)` 结果 != 父进程 pid。
2. `test_run_in_subprocess_timeout_raises`：`run_in_subprocess(time.sleep, args=(60,), timeout=0.3)` 一站式超时路径 → `SubprocessTimeoutError`（内部已 terminate→grace→kill→reap→close，不再残留进程）。
3. `test_interruptible_process_manual_terminate_kill_reaps`（纯手动 API，无 run() 混用）：`proc = InterruptibleProcess(target=time.sleep, args=(60,), timeout=0.3)`；`proc.start()` → `proc.join(0.3)` → 断言 `proc.is_alive()` → `proc.terminate()` → `sleep(grace)` → `proc.kill()` → `proc.join(5)` → 断言 `not proc.is_alive()` 且 exitcode 非 None（真实回收，无 zombie）→ `proc.close()`。
4. `test_run_in_subprocess_child_error_propagates`：`run_in_subprocess(int, args=("not-a-number",), timeout=10)` → `SubprocessExecutionError`，`child_type == "ValueError"`。
5. `test_interruptible_process_rejects_invalid_params`：timeout=0 / grace=-1 → `ValueError`。
6. `test_interruptible_process_bounded_close_idempotent`：`close()` 两次不抛；`run()` 后 `close()` 不抛；重复 `run()`（或 `start()` 后 `run()`）抛 `RuntimeError`。

修改 `tests/fund/document_tools/test_docling_conversion.py`：
1. 既有 `test_convert_local_pdf_writes_docling_json`（真实样本转换）保留——现在走子进程，即生产路径证明；断言不变。
2. 既有 `test_convert_failure_returns_docling_convert_failed`（无效 bytes）保留——子进程分类经 envelope 回传；断言不变。
3. 新增 `test_convert_timeout_maps_unavailable_and_cleans_json`（边界，fake）：monkeypatch `DoclingConverter._run_child_conversion` 抛 `SubprocessTimeoutError`；预写 `json_path` 假文件 → 断言 `DocumentToolError.code is FailureCode.UNAVAILABLE`、message 含「Docling 转换超时」、`json_path` 已被清理。
4. 新增 `test_convert_child_failure_code_maps`（边界，fake）：monkeypatch `_run_child_conversion` 返回 `{"failure_code": "docling_convert_failed", "message": "Docling PDF 转换失败"}` → `FailureCode.DOCLING_CONVERT_FAILED`；返回 `{"failure_code": "unavailable", "message": "Docling 转换超时"}` → `FailureCode.UNAVAILABLE` + json 清理。

### 文档

- `fund_agent/fund/README.md`：1 句（新增 interruptible_process 原语）。
- `tests/README.md`：1 句（新增原语测试文件）。

## allowed write set

- `fund_agent/fund/document_tools/interruptible_process.py`（新增）
- `fund_agent/fund/document_tools/docling_converter.py`
- `fund_agent/fund/README.md`
- `tests/fund/document_tools/test_interruptible_process.py`（新增）
- `tests/fund/document_tools/test_docling_conversion.py`
- `tests/README.md`

禁止修改：`fund_agent/host/`、`fund_agent/agent/`、`fund_agent/service/`、`fund_agent/cli/`、`docs/design.md`、`AGENTS.md`、`docs/implementation-control.md`、`.sisyphus/`、`FailureCode` / `DocumentToolError` / `DoclingConversionResult` 等公共契约。不 commit、不 push。

## 验证命令

```bash
# 1. 新增原语测试（真实子进程）
uv run pytest tests/fund/document_tools/test_interruptible_process.py -v --tb=short

# 2. 转换器测试（生产路径真实转换 + 边界）
uv run pytest tests/fund/document_tools/test_docling_conversion.py -v --tb=short

# 3. 最小验证集
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short

# 4. Host 回归（确认 12A 语义未动）
uv run pytest tests/fund/host/test_host_stream.py tests/fund/host/test_minimal_host_session.py -v --tb=short
```

## 验收口径

- 原语 5 个测试 + 转换器新增边界测试全部通过；既有真实转换 / 失败分类测试通过（生产路径在子进程内完成）。
- CLI 端到端 smoke（controller 执行，记录输出）：真实样本 PDF 经 CLI `import` 完成子进程内转换并落盘：

```bash
rm -rf /tmp/fund-checklist-pb-smoke && mkdir -p /tmp/fund-checklist-pb-smoke/pdf
cp "基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf" /tmp/fund-checklist-pb-smoke/pdf/
uv run python -m fund_agent.cli.main import --pdf-dir /tmp/fund-checklist-pb-smoke/pdf --fund-code 011649 --fund-name "易方达逆向投资混合" --year-range 2025-2025 --work-dir /tmp/fund-checklist-pb-smoke/wd
```

  期望：exit 0；stdout 含 `imported (document_id=...)`；`/tmp/fund-checklist-pb-smoke/wd` 下存在 `*.docling.json`（或 catalog 完成登记）。
- 不引入新依赖；`rg "multiprocessing|spawn" fund_agent/fund/document_tools/interruptible_process.py` 可见实现；无部分 JSON 残留（失败路径断言覆盖）。
- CIC-lite：MiMo plan review → controller 同步真源 → DS 实施 → controller 复跑 → MiMo diff review。
