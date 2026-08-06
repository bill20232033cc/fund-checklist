# 2026-08-05 interactive 问答质量修复 slice（检索路由 + 工具收敛 + 终答质量）

> 状态：🟡 待 Mimo review。来源：004393 interactive 实测 4 问（2026-08-05）暴露两类问题，根因已代码实证。

---

## 1. 问题现象与根因（实证）

实测会话（`.fund_e2e_004393/sessions/d53ab6de...`，2026-08-05）：

| 问题 | 工具调用 | 现象 |
|---|---|---|
| 基金经理持有本产品吗 | 5× search | 假阴性：9.4 节存在（section-0593，`持有本基金` 检索 5 命中），LLM 用词 `基金经理持有本产品` 0 命中 → 误报未找到 |
| 基金经理是谁 | 2 | 正常 |
| 基金前十大持仓是什么 | 8 | 终答回显工具原文（章节清单堆叠），重复啰嗦 |
| 2021-2025 份额净值增长率 | 14 | 同上，且 search/list_tables/aggregate 重复调用 |

根因：

1. **检索无受控路由**：`持有本基金`/`基金经理持有`/`基金经理持有本产品` 均 `profile_name=None`（`_route_plan_for_query` 无候选扩展），LLM 自由选词。
2. **去重只认完全相同参数**：语义相近不同词不触发 `seen_calls` 去重；prompt「连续 2 次无命中停止」对空结果（成功空元组）不被模型遵守；interactive `max_iterations=20` 过度探索。
3. **终答回显原文**：interactive `_final_result` 走方案 E（跳过证据/引用校验），LLM 把 evidence 原样粘贴；prompt 无「禁止粘贴原文」显式约束。
4. **JSON 信封未解包**：prompt 要求终答返回 JSON，模型有时返回 `{"answer": ...}` 信封，runner 透传展示（Q1 用户看到整段 JSON）；有时返回纯文本，格式不一致无兜底。

## 2. 用户裁决（2026-08-05，全部按推荐）

- D1 范围：三层全做（检索路由 profile + 工具循环收敛 + 终答质量）。
- D2 空结果收敛：有 profile 的查询由 runner 自动用候选词重试（最多 1 轮），仍 0 命中或连续 2 次空结果 → 强制收敛返回「未找到相关数据」；无 profile 连续 2 次空结果直接收敛。
- D3 终答兜底：prompt 强化 + runner 轻量检测（answer 与任一 evidence 连续重叠 ≥40 字符或 >800 字 → 有界重答 1 次，仍超标截断为摘要格式）。
- D4 终答契约：保持「最终回答必须返回 JSON」，runner 解包（answer 提取展示，citations/key_facts 解析落盘），用户只见自然语言。
- D5 profile 范围：本次只做「持有本基金 / 基金经理持有」；**规模、份额、基准收益率、超额收益率、十大持仓 等 profile 排后续 slice（backlog）**。
- 附加：interactive `max_iterations` 20 → 12；interactive 方案 E（跳过 evidence/citation 校验）保持不变。

## 3. 修复规格

### L1 检索路由层（extraction.py）

- 新增 profile `manager_holdings`（命名沿用既有 profile 风格）：
  - target disclosure：9.4 期末基金管理人的从业人员持有本基金的情况（实测 `持有本基金` 检索 5 命中 section-0593）；
  - candidate_queries 覆盖：`持有本基金`、`基金经理持有`、`期末基金管理人的从业人员持有本基金`、`基金经理持有本基金`；
  - 复用既有 `_extract_manager_holding` / `_extract_manager_info` 的 9.4 定位语义（不重复实现表抽取）。
- 单测：`_route_plan_for_query("基金经理持有本产品")` 命中 `manager_holdings`，候选词包含 `持有本基金`。

### L2 工具循环层（llm_tool_loop.py / scene_config.py / chat_service.py）

- 候选词注入：Service 层（chat_service）基于 `_route_plan_for_query` 把候选词列表随 scene context 注入（system prompt 或 contributions「候选检索词」），LLM 选词优先使用；**runner 不 import service 层**（分层约束：路由知识在 Service，收敛执行在 Agent）。
- 空结果强制收敛（runner）：
  - search_document 返回空结果时计数；interactive 场景连续 2 次空结果 → 不再等待模型，强制返回「未找到相关数据」final（fail-closed）；
  - 有 profile 且候选词未用尽时，runner 提示/注入候选词重试（最多 1 轮，实现方式 DS 可选：自动执行候选 search 或回填提示，验收以行为为准）。
- `INTERACTIVE_SCENE_CONFIG.runtime.max_iterations` 20 → 12。

### L3 终答质量层（llm_tool_loop.py / scene.md）

- JSON 信封解包：interactive 分支对 `final_answer.answer` 做 JSON 解析，若含 `answer` 字段则提取为展示文本；citations/key_facts 解析后随 AgentRunResult 落盘。
- 原文粘贴检测 + 有界重答：interactive 分支检测 answer 与任一 `tool_result.evidence_text` 连续重叠 ≥40 字符，或 answer >800 字 → 重答 1 次（复用/扩展 `_retry_final_answer_advice_guard` 模式，重答过同一检测）；仍超标 → 截断为摘要格式（前 200 字 + 省略说明）。
- prompt 强化（`prompts/interactive/scene.md`）：显式加「禁止把工具返回原文粘贴进 answer，必须用自己的话概括；首次回答 ≤200 字」。

## 4. 后续 backlog（不在本 slice）

规模、份额、基准收益率、超额收益率、十大持仓 等高频问题的受控 profile。

## 5. allowed write set

- `fund_agent/service/extraction.py`（route plan：新增 `manager_holdings` profile）
- `fund_agent/agent/llm_tool_loop.py`（空结果收敛、JSON 解包、原文检测/重答）
- `fund_agent/service/scene_config.py`（interactive max_iterations=12）
- `fund_agent/service/chat_service.py`（候选词注入接线）
- `fund_agent/service/prompts/interactive/scene.md`（终答简洁约束）
- 测试：`tests/fund/service/test_extraction.py`、`tests/fund/agent/test_llm_tool_loop.py`、`tests/fund/service/test_scene_config.py`、`tests/fund/service/test_chat_service.py`
- 真源文档：`docs/design.md`、`docs/implementation-control.md`、（`AGENTS.md` 如需）

禁止：改 search_document 公共契约；改方案 E 裁决口径；改 hold_fund 字段抽取逻辑本体；触碰 Phase 7.4 / F1.1 / Phase 7.5 / PDF slice 未提交区域。

## 6. 验证命令

```bash
# Phase 7 核心测试
uv run pytest tests/fund/cli/test_cli_interactive.py tests/fund/service/test_chat_service.py tests/fund/host/test_session_store.py tests/fund/agent/test_context_budget.py tests/fund/service/test_scene_config.py tests/fund/service/test_prompt_contributions.py tests/fund/service/test_prompt_composer_upgrade.py tests/fund/agent/test_tool_result.py tests/fund/agent/test_tool_context.py -v --tb=short
# 本 slice 新增单测
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_extraction.py tests/fund/service/test_scene_config.py tests/fund/service/test_chat_service.py -k "manager_holdings or 空结果 or converge or json or overlap or paste or max_iterations" -q --tb=short
```

## 7. 验收口径

- 单测全绿：route plan 命中、空结果强制收敛、JSON 解包、原文检测/有界重答、max_iterations=12 生效。
- opt-in live e2e（004393 interactive 复跑，显式授权）：Q1 命中 9.4（不再假阴性）；Q3/Q4 终答 ≤200 字、无原文粘贴（或重答后满足）；Q4 工具调用数 < 12；`max_iterations` 生效。
- `git diff --check` 干净；不 commit / push。

## 8. stop conditions

- 触碰 §5 禁止事项 → 停止。
- Phase 7 核心测试新增失败 → 停止。
- live e2e 未显式 opt-in 不得运行；默认测试出现网络调用 → 停止。
