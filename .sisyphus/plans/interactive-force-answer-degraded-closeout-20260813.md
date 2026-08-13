# interactive force_answer 降级收尾 slice（2026-08-13 规划）

## 依据

- 用户实测（2026-08-13）：`interactive --enable-tool-trace` 问「基金经理是谁」偶发返回 `LLM 处理失败：LLM 工具循环暂不可用`，trace 8 条全 success。
- Controller 复现：同一环境 4 次 3 成 1 败；失败时 trace 恰 8 条（interactive `max_iterations=8` 耗尽）。假 LLM 构造「8 轮不收敛」确定性复现同一失败路径。
- 根因链（已验证）：LLM provider（当前 mimo）偶发 8 轮内不发 FinalAnswer → `max_steps` 耗尽 → `_force_answer_from_evidence` 把工具证据原文拼接成 answer → `_apply_interactive_final_guards` 检测到原文粘贴（≥40 字符重叠）→ 触发有界重答 1 次 → 重答轮 provider 返回 ToolCall（非 FinalAnswer）→ `llm_tool_loop.py:1203-1205` fail-closed 为 `UNAVAILABLE`（无 warning 日志）；重答轮异常则 `1196` fail-closed（有 warning）。
- 结构性缺陷：force_answer 产物 = 证据原文拼接，**必然**违反原文粘贴检测 → 必然重答；重答只接受 FinalAnswer，而「8 轮不收敛」的 provider 重答轮大概率继续发 ToolCall → interactive 在 LLM 不收敛时**必然失败**，无恢复路径。
- Fix A（2026-08-11，Mimo ACCEPTED，AGENTS.md:107 / design.md:228）：force_answer 分支在 interactive 下与正常 FinalAnswer 同走终答守卫（投资建议拦截 + ≤200 字约束），不再绕过守卫。
- 用户裁决（2026-08-13，方案 2）：**降级产物跳过「原文粘贴 → 有界重答」子规则，直接截断 ≤200 字收尾；保留投资建议拦截与 ≤200 字硬约束**。这是对 Fix A 的细化（Fix A 的安全部分不变，去掉对降级产物无意义且必然失败的重答子规则）。

## 目标

1. `_apply_interactive_final_guards` 增加 `degraded: bool = False` 参数：`True` 时跳过原文粘贴/超长有界重答，超长直接 `_truncate_final_answer_summary` 截断（≤200 字含省略说明）。
2. `run()`（llm_tool_loop.py:676）与 `run_stream()`（:987）的 force_answer 调用点传 `degraded=True`。
3. degraded 语义保留：投资建议拦截分支不变（命中仍 `_retry_final_answer_advice_guard` 有界重答 1 次，仍失败 fail-closed）；`final.failure` 非空原样返回；answer ≤200 字原样返回。
4. 正常 FinalAnswer 路径零变化（`degraded=False` 默认，原文粘贴/超长仍重答 1 次）。

## 非目标

- 不改投资建议拦截语义（安全红线）。
- 不改正常 FinalAnswer 的原文粘贴/超长重答逻辑。
- 不提高 interactive `max_iterations`（8 保持）。
- 不修 provider 偶发不收敛本身（外部行为，重试/换 provider 处理）。
- 不改 ask / generate 等其他 scene（force_answer 降级语义本就不过 interactive 守卫）。
- 不 commit / push。

## 决策

1. 签名：`_apply_interactive_final_guards(..., degraded: bool = False)`；默认值保持既有调用零变化。
2. degraded 分支位置：`final.failure` 检查之后、`_violates_final_answer_quality` 检查之前：
   - `if degraded: return replace(final, answer=_truncate_final_answer_summary(final.answer)) if len(final.answer) > _INTERACTIVE_FINAL_ANSWER_MAX_CHARS else final`
   - `_truncate_final_answer_summary` 对 ≤200 字输入原样返回（其内部已有 `len(answer) <= TARGET_CHARS` 判断），但仍显式判断 `> MAX_CHARS` 避免重复语义歧义。
3. 两个 force_answer 调用点（run / run_stream）传 `degraded=True`；调用处注释更新为「降级产物跳过原文粘贴/超长重答，超长直接截断收尾（2026-08-13 方案 2）」。

## 规格

### 代码：`fund_agent/agent/llm_tool_loop.py`

- `_apply_interactive_final_guards`：新增 `degraded: bool = False` 关键字参数；docstring 更新（说明 degraded 语义：投资建议拦截保留、跳过原文粘贴/超长重答、超长直接截断；用于 max_steps 耗尽的 force_answer 降级产物）。
- 实现顺序（保持既有分支优先）：
  1. 投资建议命中 → `_retry_final_answer_advice_guard`（不变；degraded 也走，安全红线）。
  2. `final.failure` 非空 → 返回（不变）。
  3. `degraded` → 超长直接截断返回；否则原样返回。
  4. 非 degraded：既有 `_violates_final_answer_quality` → `_retry_final_answer_quality_guard` → 仍超标截断（不变）。
- `run()` force_answer 分支（676）：`_apply_interactive_final_guards(..., degraded=True)`。
- `run_stream()` force_answer 分支（987）：同样传 `degraded=True`。

### 测试：`tests/fund/agent/test_llm_tool_loop.py`

更新 3 个既有 run_stream 用例（Fix A 锁定的旧行为 → 方案 2 新行为）：
- `test_run_stream_interactive_force_answer_guard_retry_passes`（1827）：改为「force_answer 降级产物不重答，直接返回截断摘要」——`next_step_calls == 2`（不再第 3 次重答），CONTENT_DELTA 为 ≤200 字摘要（含截断说明），无 ERROR。
- `test_run_stream_interactive_force_answer_guard_truncates_summary`（1868）：改为「降级产物超长直接截断」——`next_step_calls == 2`，CONTENT_DELTA ≤200 字含「截断」，无 ERROR。
- `test_run_stream_interactive_force_answer_guard_fails_closed`（1914）：改为「降级产物直接收尾，不再 fail-closed」——无 ERROR、有 DONE、`next_step_calls == 2`（fake client 第 3 个 ToolCall 不再被消费）。

新增用例：
- `test_run_interactive_force_answer_degraded_truncates_overlong_without_retry`（run()）：max_steps 耗尽 + 证据原文超长 → failure=None、answer ≤200 字含「截断」、`next_step_calls == 2`（未触发重答）。
- `test_run_interactive_force_answer_degraded_paste_evidence_returns_directly`（run()）：降级产物为证据原文（必触发粘贴）→ 不重答直接返回（answer 为截断摘要或原样，failure=None；fake client 无多余 step 不抛异常）。
- `test_run_interactive_force_answer_degraded_no_evidence_fails_closed`（run()）：max_steps 耗尽无证据 → 保持 `_STEP_LIMIT_MESSAGE` fail-closed（降级路径无证据时不返回空答案）。
- `test_run_interactive_force_answer_degraded_advice_guard_still_fails_closed`（run()）：降级产物命中投资建议关键词 → 仍拦截 fail-closed（安全红线保留，有界重答语义不变）。
- `test_run_interactive_normal_final_answer_paste_guard_retry_unchanged`（run()）：正常 FinalAnswer 原文粘贴仍触发有界重答 1 次（`degraded=False` 回归保护，复用既有 `test_interactive_paste_guard_retried_once_then_rewritten` 断言语义）。
- `test_run_interactive_normal_final_answer_overlong_still_retries_then_truncates`（run()）：正常 FinalAnswer 超长仍重答后截断（回归保护）。

### 文档：`fund_agent/agent/README.md`

- 第 41-42 行 interactive 终答守卫表述更新：正常 FinalAnswer 原文粘贴/超长仍重答 1 次后截断；max_steps 耗尽的 force-answer 降级产物（2026-08-13 方案 2）跳过原文粘贴/超长重答，超长直接截断为 ≤200 字摘要；投资建议拦截对两者一致保留。

## Allowed write set（DS 只允许动这些）

- `fund_agent/agent/llm_tool_loop.py`（guard 加 degraded 参数 + 2 个 force_answer 调用点 + docstring）
- `fund_agent/agent/README.md`（第 41-42 行守卫表述）
- `tests/fund/agent/test_llm_tool_loop.py`（更新 3 个既有用例 + 新增 6 个用例）
- `tests/README.md`（测试范围一句话）

禁止动：AGENTS.md、docs/design.md、docs/implementation-control.md（controller 在 MiMo plan review 后回写）；禁止 commit / push；禁止新增第三方依赖；禁止改投资建议拦截语义；禁止改正常 FinalAnswer 重答逻辑；禁止改 `StreamEvent` / `ToolResult` / `FailureCode` / public 方法签名；禁止改其他 scene（ask/generate）。

## 必须运行的测试命令（跑完把输出贴进交接报告）

1. `uv run pytest tests/fund/agent/test_llm_tool_loop.py -k "force_answer or max_steps or interactive_paste or interactive_long or interactive_advice" -v --tb=short`
2. `uv run pytest tests/fund/agent/test_llm_tool_loop.py -v --tb=short`
3. `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`

## Stop condition

全部测试通过后停止（第 2 条允许存在 1 个既有失败 `test_interactive_read_table_from_search_hit_allowed` 之外的新失败？——不：该既有失败已于 2026-08-13 fix slice 修复，应全部通过；若仍有失败报告最小失败原因）。输出交接报告：changed files、diff 摘要、实际测试命令与输出。

## 交接报告格式（回复给 controller）

- changed files: 列表
- diff 摘要: 每文件 1-2 行
- 测试: 实际命令 + passed/failed 数字
- 失败/风险: 若有
