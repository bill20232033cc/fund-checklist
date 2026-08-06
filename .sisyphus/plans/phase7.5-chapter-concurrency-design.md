# Phase 7.5 设计方案：generate 报告生成章节级并发（备选命名 Slice 14D）

> 状态：🟡 设计初稿，待 review。产出物：本文件（唯一设计 artifact）。
> 范围：只读核实现有代码后给出并发改造设计；不触碰当前未提交的 Phase 7.4 改动与 F1.1 费率修复（`extraction.py` 等）。
> 依据：`fund_agent/service/audit_pipeline.py`（ReportGenerationCoordinator 全链路）、`fund_agent/agent/deepseek_llm.py`、`fund_agent/service/extraction.py`（generate_report 包装）、`fund_agent/cli/main.py`（generate 子命令）。Dayu 架构仅作参考，禁止引入其 runtime/代码。

---

## 1. 背景与现状（已核实，代码事实）

### 1.1 现有串行链路

`ReportGenerationCoordinator.generate_report`（audit_pipeline.py:1842）当前为纯串行：

1. **step 0（主线程）**：预生成 Ch1-7 的 data_table，合并出全局 `allowed_numbers`（支持跨章节数字引用）。
2. **step 1（主线程串行）**：`for chapter_id in range(1, 7)` 逐章调用 `_generate_and_audit_chapter`（audit_pipeline.py:1971）。每章内部是完整闭环：`_generate_chapter_content`（LLM 写，失败模板降级）→ 程序审计 + LLM 审计 → PATCH/REGENERATE 循环（各最多 3 次）→ `audit_exhausted` 降级。
3. **step 2（主线程）**：`all_passed` 判定（status ∈ {passed, passed_with_degradation}）；不通过则 Ch0/Ch7 用模板生成并提前返回。
4. **step 3（主线程串行）**：`for chapter_id in [0, 7]`，带 `use_chapter_summaries=True` + Ch1-6 内容摘要，逐章生成并审计。

`self._llm_client` 在章节闭环中被引用 3 处：`LlmAuditor`（audit_pipeline.py:2131）、`ChapterRepairer`（2195）、`_generate_chapter_content`（2336，`_regenerate_chapter` 经它复用）。`_process_states` 为 `dict[int, ChapterProcessState]`，按章分立 key；`ArtifactStore` 按章写 `chapter_N_state.json` / `chapter_N_audit.json` / `chapter_N_repair.json`。

### 1.2 调用链

- CLI：`main.py:198` generate parser（--llm 等）→ `_run_generate_command`（935）→ `service.generate_report(GenerateReportRequest(...), llm_client=DeepSeekLlmClient())`。
- Service：`extraction.py:2261` `FundReadingService.generate_report` → 多年度抽取 → `ReportGenerationCoordinator(llm_client, work_dir)`（2357）→ `coordinator.generate_report(...)` → 按固定 `chapter_specs`（0..7）组装 `ReportChapter`。
- `GenerateReportRequest`（models.py:972）为 frozen dataclass：fund_code/fund_name/report_year/years/work_dir/output_format。

### 1.3 Dayu 参考（仅参考量级）

Dayu 用 ThreadPoolExecutor 并行跑中间章节，每 worker 跑完整单章闭环（写→审计→重写），并发上限来自 Host governance lane（write_chapter 默认 5），主线程按模板顺序统一落盘，async agent 经 `asyncio.run` 在每 worker 线程独立事件循环运行。fc 现状的 `_generate_and_audit_chapter` 即等价 Dayu 的“单章 worker”，但缺并发调度层。

**本设计不引入 Dayu runtime/代码；不引入 async 事件循环（fc 的 DeepSeek 调用是同步 `generate_text`，ThreadPoolExecutor 直接可用）。**

---

## 2. 目标与非目标

### 2.1 目标

1. Ch1-6 并行生成（每章完整 write→audit→rewrite 闭环不变，仅调度层并发）。
2. Ch0/Ch7 在 Ch1-6 全部完成后并行收尾（二者仅依赖 Ch1-6 内容摘要，彼此独立）。
3. 并发上限可配置：新增 CLI 参数 / request 字段 / env，默认 4；`1` = 完全串行（行为等价现状）。
4. 每 worker 独立 `DeepSeekLlmClient` 实例，`_cumulative_usage` 线程隔离。
5. 单章失败不拖垮整批；`passed_with_degradation` / `audit_exhausted` 语义不变。
6. 输出稳定：`chapter_contents` 按 chapter_id 0..7 组装，warnings 按章排序，与完成顺序无关。

### 2.2 非目标

- 不改 Ch0/Ch7 依赖关系、审计阈值、修复策略、章节 prompt。
- 不做跨章共享 LLM 上下文 / 会话合并。
- 不做 cancel/resume API、不做章节级进度流式输出、不做并发 benchmark gate。
- 不引入 dayu runtime/代码、不引入 asyncio 事件循环。
- 不改 `search_document` / Service reading tools 公共契约；不改既有参数语义与返回值形状。
- 不触碰当前未提交的 Phase 7.4 / F1.1 改动区域（本设计只读，实现 slice 仅允许最小增量透传，见 §8）。

---

## 3. 依赖顺序与并行阶段定义

对应 Dayu 的“前置串行 → 中间并行 → 决策 → 概览收尾”，fc 定义为四阶段：

| 阶段 | 内容 | 执行位置 | 依赖 |
|---|---|---|---|
| A（前置串行） | step 0：预生成 Ch1-7 data_table + global_numbers | 主线程 | 无（纯程序计算，无 LLM） |
| B（中间并行） | Ch1-6 各自完整闭环 | 线程池 | 仅共享只读输入（见 §5.3）；章间零依赖 |
| C（决策串行） | B join 后 all_passed 判定；不通过 → 模板 Ch0/Ch7 并返回 | 主线程 | Ch1-6 全部终态 |
| D（收尾并行） | Ch0/Ch7 带 Ch1-6 摘要并行生成 | 线程池（复用） | Ch1-6 最终内容摘要 |

依赖定义（写死，不允许动态推断）：

- Ch1-6：零依赖，可任意并发；输入全部来自共享只读数据 + 各自 data_table。
- Ch0/Ch7：`use_chapter_summaries=True`，依赖 Ch1-6 的最终 `chapter_contents`；二者彼此独立（最多 2 路并行）。
- 统一落盘/组装：所有阶段完成后主线程按 chapter_id 0..7 顺序组装 `chapter_contents` → `ReportChapter`，与 future 完成顺序无关。

---

## 4. 并发机制

### 4.1 ThreadPoolExecutor 调度

- `generate_report` 内创建一个 `ThreadPoolExecutor(max_workers=effective_concurrency)`，用 context manager 管理生命周期；A/B/C/D 四阶段复用同一 executor（不重复建线程）。
- 阶段 B：对 `range(1, 7)` 逐个 `executor.submit(_run_chapter_worker, cid)`，然后 `wait(..., return_when=ALL_COMPLETED)`；完成后再按 cid 取 `future.result()`。
- 阶段 D：join 完成后对 `[0, 7]` 再 submit 一轮，同样 wait。
- **阶段 B 与阶段 D 之间必须完全 join**，保证 Ch0/Ch7 永远看到 Ch1-6 的最终内容（不会读到半成品）。
- worker 函数 `_run_chapter_worker` 返回 `(chapter_id, content, state, chapter_warnings)` 元组；内部顶层再兜一层 try/except（防 `_generate_and_audit_chapter` 之外的新增异常把 `future.result()` 抛到主线程），任何异常收敛为 `(cid, None, failed_state, [f"Ch{cid} 生成失败"])`，与现状异常语义一致。

### 4.2 每 worker 独立 LLM client（`_cumulative_usage` 线程隔离）

- `DeepSeekLlmClient` 新增 `clone()`：以相同 transport/env/timeout/options/system_prompt/temperature 构造新实例，但 `_cumulative_usage` 独立（当前 `_cumulative_usage` 仅在 `next_step` 累计，`generate_text` 路径不累计；隔离是面向未来的硬保证，且顺带消除任何共享可变状态）。
- `UrlLibDeepSeekTransport` 无请求间可变状态（每次 `send` 构造新 Request，deepseek_llm.py:153），transport 可被 clone 共享。
- worker 启动时用 `template_client.clone()` 取自己的 client（或 `chapter_concurrency == 1` 时直接用原 client），章节闭环内的 3 处 `self._llm_client` 引用改为显式下传的局部 `llm_client` 参数（`_generate_and_audit_chapter` / `_generate_and_audit_chapter_inner` / `_generate_chapter_content`，`LlmAuditor` / `ChapterRepairer` 构造时传入；`_regenerate_chapter` 经 `_generate_chapter_content` 自动覆盖）。
- clone 数量 = 章节任务数（B 阶段最多 6、D 阶段 2），worker 结束后丢弃，不做跨章复用（保持每章 usage 账本纯净）。
- 若未来需要总 usage：所有阶段 join 后主线程对各 worker client 求和（join 后无并发，无需锁）。

### 4.3 并发上限来源（lane 概念）与优先级

- fc 独立命名：`chapter_concurrency`（语义 = 同时执行完整“写→审计→重写”闭环的 worker 数，与 Dayu governance lane 对齐；`write_chapter` 命名仅为参考量级，不照搬）。
- 生效优先级（高 → 低）：
  1. CLI `generate --concurrency N`（main.py，仅 `--llm` 模式有意义；模板模式忽略并提示）。
  2. `GenerateReportRequest.chapter_concurrency: int | None = None`（models.py 新增可选字段，frozen dataclass 向后兼容）。
  3. env `FUND_CHECKLIST_CHAPTER_CONCURRENCY`（沿用仓库 `FUND_CHECKLIST_*` 前缀约定，如 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK`）。
  4. 默认 `4`。
- 解析位置：`FundReadingService.generate_report`（extraction.py，唯一解析点），把解析出的 int 显式传给 coordinator；coordinator 校验 `1..8`，非法值 `ValueError`。
- 默认 4 的理由：Dayu write_chapter=5 为量级参考；fc 每 worker 闭环包含多次 LLM 调用（生成 + 审计 + 可能的 patch/regenerate），4 路并发对 API rate limit 更保守。`1` 为显式串行等价模式（测试与排障用）。

### 4.4 兼容性回退

- `chapter_concurrency > 1` 但 `llm_client` 无 `clone()`（自定义 client / 测试注入 fake）：**回退串行**（effective=1）并 append warning「LLM client 不支持并发克隆，已回退串行」。生产 `DeepSeekLlmClient` 必有 `clone()`，回退仅发生在第三方注入；选择“降级 + warning”而非 raise，是为了不破坏既有调用方（含现有 FakeLlmClient 测试），且回退目标 = 当前完全等价行为。并发相关测试必须使用带 `clone()` 的 fake 显式断言，不得依赖回退路径。
- `ReportGenerationCoordinator.__init__` 默认 `chapter_concurrency=1`（直接构造者保持现状）；生产并发由 Service 解析层显式传入（§4.3）。

---

## 5. 线程安全审计

### 5.1 `_process_states` 并发写

- 每个 worker 只写自己的 chapter key（`self._process_states[chapter_id] = state`），key 集合不相交；GIL 下单键赋值原子。`get_process_states()` 只在所有阶段 join 后由主线程调用（extraction.py:2399 之后），不存在并发读。
- 仍加一个 `threading.Lock` 保护 dict 写入（防御未来跨章共享状态的演进）；`get_process_states` 读时也过同一锁（join 后成本可忽略）。
- `ChapterProcessState.record_event` 只 mut 自己 worker 的 state 实例，无共享对象。

### 5.2 ArtifactStore 并发落盘

- 文件名按章分文件（`chapter_{id}_state.json` / `_audit.json` / `_repair.json`），同一路径只有唯一 writer（同一章的 worker 串行重写自己文件），无跨章冲突、无交错写。
- `_audit_dir.mkdir` 在 `ArtifactStore.__init__`（主线程）完成，先于任何 worker。
- `Path.write_text` 非原子，但对唯一 writer 无影响；本 slice 不做 temp+rename 硬化（列为可选后续项）。

### 5.3 共享只读数据

- `performance / holdings / allocation / fees / fund_manager / scale_info / evidence / signal_judgment / global_numbers / fund_type` 全阶段只读，跨线程安全。
- 每章 `data_table` 在 worker 内独立重算（现状即如此，`_generate_and_audit_chapter_inner` 内调用 `generate_data_table`），无共享写；step 0 的预生成仅为 `global_numbers`，不缓存复用，避免引入新的共享可变状态。

### 5.4 warnings 收集

- worker 不直接 append 共享 list；各 worker 把章节级 warning 放进返回值，主线程 join 后按 chapter_id 排序 append（输出稳定）。
- 现有 `logging.warning`（“LLM 输出包含可疑数字”，audit_pipeline.py:2352）走标准 logging，其 Handler 自带锁，跨线程安全，无需改动。

### 5.5 进度输出交错

- 现状 generate 路径无逐章 stdout，CLI 仅在全部完成后打印一次 JSON（main.py:993），天然无交错。
- 约束（写死）：任何未来进度输出必须经主线程（如 queue + 消费循环或完成后按 cid 打印），禁止 worker 直接 print。

---

## 6. 失败语义与 cancel 收敛

### 6.1 单章失败不拖垮整批

- 每章闭环已有异常包装（`_generate_and_audit_chapter` 的 try/except → state.failed + None）；worker 顶层再兜一层（§4.1），保证一个 worker 抛异常不影响其他 future 与主线程。
- 失败章返回 None → `chapter_contents` 缺该章 → warning「Ch{cid} 生成失败」；其余章节照常。

### 6.2 既有降级语义不变

- `passed` / `passed_with_degradation` / `audit_exhausted`（低分模板降级、中分保留 LLM 内容）全部在 worker 闭环内逐章判定，与串行完全一致。
- 阶段 C 的 `all_passed` 判定与“Ch1-6 未全部通过 → Ch0/Ch7 模板生成并提前返回”路径保持现状，只是输入来自 join 后的 states。

### 6.3 cancel 收敛

- 不新增 cancel/resume API。`KeyboardInterrupt` 或主线程异常时：`executor.shutdown(wait=True, cancel_futures=True)`，已运行 worker 自然结束（其内部 LLM 调用带超时），未开始的 future 被取消；主线程不再组装/落盘报告（报告文件只在阶段 D join 后写）。
- 审计 artifact 按章保留（部分完成的章节仍有 `chapter_N_state.json`），可作后续排查；不产生“半个报告”文件。

### 6.4 确定性口径

- 并发不改变每章 prompt 与内部 LLM 调用序列（同一 data_table、同一 prompt、同一闭环逻辑），仅执行顺序交错。
- 输出稳定性 = 章节集合与顺序稳定（按 chapter_id 组装、warnings 按章排序）；不承诺跨运行逐字一致（与现状一致，LLM 本身非确定）。

---

## 7. 测试方案

### 7.1 新测试（`tests/fund/service/test_report_concurrency.py`，或并入 test_audit_pipeline.py）

**并发探测 fake**：`FakeLlmClient` 支持 `clone()`，clone 共享一个 `ConcurrencyProbe`（`threading.Lock` 保护的 `active/peak` 计数 + 线程安全 `calls` 记录 + 可选 `delay`），每实例独立记录可区分。按既有 fake 约定：审计类 system_prompt 返回高分 JSON、修复类返回 `{"strategy": "none"}`。

| # | 用例 | 断言 |
|---|---|---|
| T1 | 并发生效：chapter_concurrency=4 + delay 制造重叠 | peak ≥ 2 且 ≤ 4；8 章全部产出；Ch1-6 全部有终态后才出现 Ch0/Ch7 的 worker 事件 |
| T2 | lane 上限：concurrency ∈ {1, 2, 8} | peak == 1（串行等价）；peak ≤ 2；B 阶段 peak ≤ 6（仅 6 个任务）且整体 peak < 8 |
| T3 | 结果顺序稳定：fake 让低编号章最后完成 | `chapter_contents` 按 0..7 组装；warnings 按 chapter_id 排序 |
| T4 | 失败隔离：仅 Ch3 抛异常 | Ch3 content None + state.failed + warning「Ch3 生成失败」；其余章正常；Ch0/Ch7 仍基于摘要生成 |
| T5 | 审计产物并发落盘：4 worker 完整跑 | `audit_artifacts/chapter_0..7_state.json` 与 `_audit.json` 全部存在且 JSON 可解析，无损坏 |
| T6 | clone 契约：`DeepSeekLlmClient.clone()`（注入 fake transport） | 新实例独立 `_cumulative_usage`；env/options/temperature 与原实例一致 |
| T7 | 参数与优先级 | concurrency=0/9 → ValueError；request 字段覆盖 env；env 覆盖默认 4 |
| T8 | 回退路径：fake 无 `clone()` + concurrency=4 | 有效并发降为 1，warnings 含回退提示；行为与串行一致 |

### 7.2 既有测试不回退

- `tests/fund/service/test_audit_pipeline.py`（coordinator / repairer / ArtifactStore 全量）
- `tests/fund/service/test_llm_chapter_generation.py`（service.generate_report LLM/模板两条路径）
- `tests/fund/cli/test_cli.py`（generate 子命令）
- AGENTS.md 最小验证命令（`tests/fund/document_tools` + `test_minimal_tool_loop.py` + `test_cli.py`）

### 7.3 约束

- fake 只测并发调度/边界/失败隔离，不得用于证明 production 链路（与仓库规则一致）；production 并发正确性由 clone + executor 单测 + opt-in live smoke 覆盖。
- live smoke（`generate --llm --concurrency 4` 跑真实 PDF 数据）显式 opt-in；默认 pytest 不联网、不读真实 key。

---

## 8. 真源文档更新点

1. `docs/design.md`：新增小节（建议 §6.8“章节级并发”）：四阶段依赖顺序、`chapter_concurrency` lane 语义与默认 4、线程安全边界（§5 摘要）、失败语义（§6 摘要）、与 Dayu 的差异（不使用 async 事件循环、命名独立）。
2. `docs/implementation-control.md`：Phase 7.5 记录（命名 Phase 7.5，备选 Slice 14D；含裁决、实现、验证命令与结果、stop conditions），按既有 Phase 7.3/7.4 记录格式追加。
3. `AGENTS.md`：如需（Phase 7.5 状态行 + 并发约束摘要），按现有 Phase 记录格式追加。

---

## 9. allowed write set（实现 slice）

- `fund_agent/service/audit_pipeline.py`：coordinator 并发改造（§3/§4.1/§4.2）、`llm_client` 显式下传、worker 包装、锁。
- `fund_agent/agent/deepseek_llm.py`：仅新增 `clone()`。
- `fund_agent/service/models.py`：`GenerateReportRequest` 新增可选 `chapter_concurrency: int | None = None`。
- `fund_agent/service/extraction.py`：仅 `generate_report` 内 1-2 行透传（解析优先级 → coordinator 参数）；**不得触碰 F1.1 费率逻辑与 Phase 7.4 未提交改动区域**。
- `fund_agent/cli/main.py`：generate parser 新增 `--concurrency` + `_run_generate_command` 透传 + 范围校验（1..8）。
- `tests/fund/service/test_report_concurrency.py`（或并入 `test_audit_pipeline.py`）+ 既有测试如需的 fake clone 扩展。
- 真源文档：`docs/design.md`、`docs/implementation-control.md`、（`AGENTS.md` 如需）。

## 10. 验证命令

```bash
# Phase 7.5 核心测试
uv run pytest tests/fund/service/test_report_concurrency.py tests/fund/service/test_audit_pipeline.py -q --tb=short

# 既有路径回归
uv run pytest tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py -q --tb=short

# AGENTS.md 最小验证命令
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short

# opt-in live smoke（显式授权后）
uv run fund-checklist generate --fund-code <code> --fund-name "<name>" --year <year> --format json --llm --concurrency 4 --work-dir <work_dir>
```

## 11. 验收口径

- `chapter_concurrency=1` 时章节 LLM 调用序列与改造前完全一致（fake 记录比对串行基线）。
- `chapter_concurrency=N` 时并发峰值 ≤ N；章节集合/顺序稳定；warnings 按章排序。
- 单章失败仅影响该章，不改变其他章产出与降级语义。
- `clone()` 独立 usage；默认 pytest 无网络。
- `git diff --check` 干净；不 commit / push。

## 12. 禁止事项

- 不改 `search_document` / Service reading tools 公共契约；不改既有参数语义与返回值形状（仅新增可选参数）。
- 不引入 dayu runtime/代码/async 事件循环；复制 Dayu 代码需先过 license gate。
- 不扩大 scope：不做 cancel/resume API、章节级进度流、跨章上下文合并、审计阈值/修复策略调整。
- 不覆盖/删除当前未提交的 Phase 7.4 与 F1.1 改动。
- 禁止用 mock/fake 证明 production 转换链路；并发正确性测试必须基于带 clone 的确定性 fake 显式断言。

## 13. stop conditions

- 触碰 §12 任一禁止事项 → 停止。
- Phase 7.5 核心测试或 AGENTS.md 最小验证命令失败 → 停止。
- `chapter_concurrency=1` 与串行基线调用序列不一致 → 停止（等价性破坏）。
- live smoke 未显式 opt-in 不得运行；默认测试出现网络调用 → 停止并修复。
