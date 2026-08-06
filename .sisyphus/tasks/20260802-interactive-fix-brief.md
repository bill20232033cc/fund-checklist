# 2026-08-02 DS 任务简报：interactive e2e 失败修复计划细化

## 任务

细化 interactive e2e 失败修复计划，产出**唯一计划产物**。本任务只写计划，不写代码、不改测试、不 commit、不 push、不写 review。

## 产出约束

- 唯一 artifact：`.sisyphus/plans/interactive-e2e-fix-20260802.md`
- 除该文件外，禁止修改或新增任何文件（可只读浏览仓库）。

## 背景（证据，来自 08-01 23:51 e2e：`uv run fund-checklist interactive --fund-code 004393 --work-dir .fund_e2e_004393 --enable-tool-trace`，9 问）

成功 4 问（基金经理是谁 / 投资策略 / 净值增长率 / 业绩基准收益率），失败 5 问，误拦截 2 问。

### 失败分类（含代码证据，需在计划中逐条对应）

1. 「基金规模是多大」「港股持仓情况是什么」→ `LLM 处理失败：章节不存在`
   - 该错误只产生于 `docling_store._find_section`（fund_agent/fund/document_tools/docling_store.py:295）。
   - runner 对 search_document 不传 `within_section_ref`（fund_agent/agent/llm_tool_loop.py:684）→ 入口只能是 read_section / list_tables(within_section_ref) 用了 LLM 猜测的 section_ref。
   - 根因：首个 ToolFailure 即整轮失败（llm_tool_loop.py:424-425、534-535），失败不回喂 LLM 修正。
2. 「对比2021-2024年的策略，有哪些变化吗？」→ `DeepSeek LLM provider response 不符合受控结构`
   - `_parse_tool_call` 要求 arguments 必含非空 document_id（fund_agent/agent/deepseek_llm.py:648 起），缺失/空参数 → LLM_MALFORMED_RESPONSE。
   - 多年度比较最可能触发 AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE 工具调用且参数不全。
3. 「这是基金值得继续关注吗」→ `LLM 工具调用超过限制`
   - interactive `max_iterations=20`（fund_agent/service/scene_config.py:101）；耗尽后 `_force_answer_from_evidence` 无 evidence → _STEP_LIMIT（llm_tool_loop.py:1042）。
   - 无可检索事实目标的问题，LLM 反复空搜索耗尽预算。
4. 「基金管理费、托管费、销售服务费分别是多少」→ `LLM 工具调用不被允许`
   - 工具名严格白名单（llm_tool_loop.py:638）+ document_id 前缀一致校验（:644），LLM 一次偏差即整轮失败。
5. 「前十大重仓股有哪些？」「基金风格一致？」→ 回答被投资建议检测拦截（误拦截）
   - `contains_investment_advice` 弱词（买入/卖出/增持/减持）豁免窗口只认 策略/宣称/原文/摘录/运作分析（llm_tool_loop.py:83-133）。
   - 持仓/风格事实描述（本期买入/本期卖出/增持/减持/重仓）不在豁免内 → 误判。本次运行发生时 WIP B1 豁免逻辑已在场仍被拦（WIP 修改 17:18 早于运行 23:51），证明是结构性误判。
   - 被拦截回答原文未持久化（session 只存替换后文本），具体触发词无法确证。

### 调试盲区（计划中作为辅助项，必须先解决）

- 失败轮不写入 session（fund_agent/service/chat_service.py:205 failure 分支提前 return）。
- 失败 tool_trace 传递被 c4e5e71 revert（HEAD 就是该 revert），失败轮内部工具调用不可见。
- e276ff3 曾实现失败 tool_trace 传递，3 分钟后被撤销，无书面原因。恢复需明确边界：工具失败路径 trace 非空；provider 首轮失败发生在 next_step 内（llm_tool_loop.py:406-408），trace 为空。

## 现状基线（工作区未提交 WIP，计划必须纳入，不得重复规划）

- B1：投资建议强弱词豁免（llm_tool_loop.py `contains_investment_advice`，引用上下文豁免）。
- B2：document_id 注入 runtime contribution（chat_service.py `_build_contributions`，修复 LLM 截断 document_id 的输入侧）。
- 已实现测试基线：B1/B2 相关单测 92 passed + 生产就绪/最小循环/CLI 124 passed（DS 已验证）。
- 注意：main.py:1104/1243 用户输入预检仍用旧 naive `investment_guard.contains_investment_advice`，与 B1 单一真源不一致，需合一。

## 修复方向（供细化，非终稿；允许 DS 按代码事实修正）

- P0-a ToolFailure 回喂：失败作为下一轮 tool result 输入，允许 LLM 修正 section_ref / 工具名 / document_id。覆盖 run / run_stream / FakeLlmClient 契约 / prompt。
- P0-b 失败可观测性：恢复失败 tool_trace（撤销 c4e5e71，补两条测试：trace 非空、trace 为空）+ 失败轮持久化（含被拦截回答原文与触发词）。
- P1-a 投资建议判据：持仓/风格事实描述（本期买入/增持/减持/重仓）不拦截；main.py 用户输入预检改用单一真源；涉及 B1 口径，需标注该 slice 依赖口径确认。
- P1-b tool call 容错：document_id 缺失时用 expected 补全；未知工具名先归一化再拒绝。
- P2 prompt 引导：无事实目标问题尽早 final answer，避免耗尽预算；空搜索结果的处理策略。

## 计划产物必须包含（按 slice 组织）

- 每个 slice：目标、allowed write set、禁止事项、验证命令、stop conditions、非目标。
- slice 依赖顺序 + 总控验收口径（CIC-lite：implement -> tests -> diff review）。
- 末尾一节：真源文档与 AGENTS.md 同步清单（哪些文档、哪些章节要改，作为通过 review 后的 doc-sync 依据）。
- 计划只规划不实现；标注哪些 slice 依赖 B1 口径 owner 确认。

## 现状验证命令（DS 只核对现状，不执行修复）

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/service/test_chat_service.py -q --tb=short
```

## 禁止事项

- 不实现代码、不改测试、不 commit、不 push、不写 review。
- 不产生计划产物之外的任何文件写入。
- 不扩大范围到 generate/audit/评分等非 interactive 链路。

## 完成信号

产出计划文件后，回复：文件路径 + slice 列表摘要 + PLAN_READY（最后一行）。
