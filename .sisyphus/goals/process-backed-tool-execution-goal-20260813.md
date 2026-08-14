# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/plans/process-backed-tool-execution-slice-20260813.md 实施「process-backed 工具执行（可抢占超时）」slice（plan 已于 2026-08-13 经 MiMo plan review，NEEDS_FIX 1 项最小修复已按 review 原文修正进 plan：test 2 改为纯手动 API 避免 start 后 run 孤儿子进程，且 spec 明确 run() 与 start() 互斥、重复调用抛 RuntimeError；docs/design.md §6.23、AGENTS.md、docs/implementation-control.md 已由 controller 先行同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review。实施内容：① 新增 fund_agent/fund/document_tools/interruptible_process.py（进程隔离执行原语，模块 docstring 声明「子进程启动 / 结果回收 / terminate+kill / bounded close；概念对齐 dayu runtime/interruptible_process.py，自实现不复制」）：SubprocessTimeoutError(TimeoutError) / SubprocessExecutionError(RuntimeError，含 child_type/child_message)；InterruptibleProcess 用 multiprocessing.get_context("spawn") + Pipe(duplex=False) 单次 envelope，模块级 _child_entry(parent_conn, target, args) 包 try/except BaseException 回传 ("ok", result) / ("error", (type, message))；run() 一站式 start→join(timeout)→未完成则 terminate→sleep(grace_period=2.0)→kill→join(5.0)→close 后抛 SubprocessTimeoutError，完成则 poll+recv（EOFError/Empty→SubprocessExecutionError）→close；run() 与 start() 互斥（已 start/已 run 再 run 抛 RuntimeError）；start/join/terminate/kill/close/is_alive 委托 mp.Process，close 幂等；timeout<=0 或 grace<0 抛 ValueError；run_in_subprocess(target, args=(), *, timeout, grace_period=2.0) 薄封装；全部中文 docstring；不新增第三方依赖）。② 修改 fund_agent/fund/document_tools/docling_converter.py：新增模块级 _run_conversion_in_child(pdf_bytes, do_ocr, timeout_seconds, output_json_path) -> dict[str, str | None]（复用既有 _build_docling_converter/_build_document_stream/_save_docling_json/_is_unavailable_exception，分类逻辑移入子进程：build ImportError/OSError→unavailable；has_timeout_errors/TimeoutError→unavailable 超时；has_parse_errors/document is None→docling_convert_failed；_is_unavailable_exception→unavailable；save OSError→unavailable；成功 {"failure_code": None, "message": None}）；convert_pdf 改为经私有方法 self._run_child_conversion(pdf_bytes, do_ocr, json_path) 调 run_in_subprocess(_run_conversion_in_child, args=(...), timeout=float(self._timeout_seconds))，父进程映射 SubprocessTimeoutError→清理 json_path 后 DocumentToolError(UNAVAILABLE, "Docling 转换超时")、SubprocessExecutionError→清理后 DocumentToolError(UNAVAILABLE, "Docling 转换子进程异常")、failure_code docling_convert_failed→DocumentToolError(DOCLING_CONVERT_FAILED, message)、unavailable→清理后 DocumentToolError(UNAVAILABLE, message)；失败路径统一保证 json_path 不残留；公共签名与返回不变（DoclingConverter.__init__(output_root, *, timeout_seconds=SINGLE_PDF_SMOKE_TIMEOUT_SECONDS, do_ocr=False)；convert_pdf(*, identity, pdf_bytes)）。③ 新增 tests/fund/document_tools/test_interruptible_process.py（真实子进程，无 fake）：run_in_subprocess(os.getpid) 结果 != 父 pid；run_in_subprocess(time.sleep, args=(60,), timeout=0.3) 抛 SubprocessTimeoutError；纯手动 API test（proc.start→join(0.3)→断言 is_alive→terminate→sleep(grace)→kill→join(5)→断言 not alive 且 exitcode 非 None→close）；run_in_subprocess(int, args=("not-a-number",), timeout=10) 抛 SubprocessExecutionError 且 child_type=="ValueError"；timeout=0/grace=-1 抛 ValueError；close 幂等、run 后 close 不抛、重复 run 或 start 后 run 抛 RuntimeError。④ 修改 tests/fund/document_tools/test_docling_conversion.py：既有真实样本转换测试与无效 bytes 失败分类测试断言不变（现在走子进程，即生产路径证明）；新增边界测试（monkeypatch DoclingConverter._run_child_conversion 抛 SubprocessTimeoutError → DocumentToolError code is UNAVAILABLE 且 message 含「Docling 转换超时」且预写 json_path 被清理；monkeypatch 返回 {"failure_code": "docling_convert_failed", ...} → DOCLING_CONVERT_FAILED；返回 {"failure_code": "unavailable", ...} → UNAVAILABLE 且 json 清理）。⑤ 文档：fund_agent/fund/README.md 与 tests/README.md 各 1 句。allowed write set 严格按 plan 清单（6 文件：interruptible_process.py 新增 / docling_converter.py / fund_agent/fund/README.md / test_interruptible_process.py 新增 / test_docling_conversion.py / tests/README.md），禁止动 AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/ / fund_agent/host/ / fund_agent/agent/ / fund_agent/service/ / fund_agent/cli/ / FailureCode / DocumentToolError / DoclingConversionResult / ReportIdentity 等公共契约；禁止新增 CLI 子命令与参数；禁止引入新依赖；禁止把子进程用于 Agent/LLM/session；不 commit、不 push。验收：uv run pytest tests/fund/document_tools/test_interruptible_process.py -v --tb=short、uv run pytest tests/fund/document_tools/test_docling_conversion.py -v --tb=short、最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short、Host 回归 uv run pytest tests/fund/host/test_host_stream.py tests/fund/host/test_minimal_host_session.py -v --tb=short 全部通过，输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/process-backed-tool-execution-goal-20260813.md
```

---

## /goal 命令特性（设计依据）

基于 Codex goal 存储（`~/.codex/goals_1.sqlite`，表 `thread_goals`）与现有 `.sisyphus/goals/` 产物格式：

| 特性 | 设计影响 |
|------|---------|
| 单线程单 active goal（`thread_id` 主键，存在未完成 goal 时新建失败） | objective 必须是**一条自包含、可独立完成的表述**；不能拆成多条 /goal |
| `objective` 是唯一执行依据文本，agent 收到后自主持续推进（可跨压缩） | 表述内必须自带：真源计划路径、slice 边界、allowed write set、验证命令、验收口径、禁止事项；不依赖追加说明 |
| 状态流 `active -> blocked/paused -> complete`（另有 usage/budget 限制态） | 本 slice 无阻塞依赖；实施完成后由 diff review 判定 |
| `token_budget` 可选，仅在显式要求时设置 | 本命令不设 budget |
| 完成判定由 objective 的验收标准驱动 | DoD 写死可执行验证命令与禁止事项，不用模糊措辞 |

## Goal

- goal_id: `process-backed-tool-execution-20260813`
- 目标：实施「process-backed 工具执行（可抢占超时）」（dayu-agent-r 研究 §2.1.4），按已 review 计划完成实现 + 测试。
- 前置条件：`.sisyphus/plans/process-backed-tool-execution-slice-20260813.md` 已 review（MiMo plan review，2026-08-13，NEEDS_FIX 1 项已按 review 原文修正进 plan）；真源三件套已由 controller 先行同步（AGENTS.md / docs/design.md §6.23 / docs/implementation-control.md）。
- 设计来源：`.sisyphus/plans/process-backed-tool-execution-slice-20260813.md`（唯一计划真源）+ `docs/research/dayu-agent-r-research-20260810.md` §2.1.4。
- 日期：2026-08-13

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope（源自 plan）

| 项 | 内容 |
|-------|------|
| 新增模块 | `fund_agent/fund/document_tools/interruptible_process.py`（进程隔离原语：异常 ×2 / InterruptibleProcess / run_in_subprocess） |
| 修改模块 | `fund_agent/fund/document_tools/docling_converter.py`（子进程入口 `_run_conversion_in_child` + `convert_pdf` 接线 + 失败映射与 json 清理） |
| 文档 | `fund_agent/fund/README.md`、`tests/README.md`（各 1 句） |
| 测试 | 新增 `test_interruptible_process.py`（真实子进程 6 用例）；修改 `test_docling_conversion.py`（既有断言不变 + 边界 2 用例） |
| 禁止 | AGENTS.md / design.md / implementation-control.md / .sisyphus/ / host/agent/service/cli / 公共契约 / 新 CLI 子命令与参数 / 新依赖 / 子进程跑 Agent·LLM·session / commit / push |
