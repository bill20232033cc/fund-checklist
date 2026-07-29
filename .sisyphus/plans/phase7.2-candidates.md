# Phase 7.2 开发备选方向

日期：2026-07-26
来源：Phase 7.1 集成补完完成后的用户实测反馈

---

## 问题发现

### 问题 1：路由 alias 覆盖不足

**现象：**
- "基金经理是谁" → 空结果（未命中路由）
- "结论是什么" → 空结果（未命中路由）
- "管理费率是多少" → 正常返回（命中 "管理费" alias）
- "重仓股是哪些" → 正常返回（命中 "重仓股" alias）

**根因：**
`DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 中的 alias 覆盖不完整：
- ✅ 已有：前十大持仓、重仓股、持仓明细、资产配置、费率、管理费、托管费、销售服务费、净值增长率
- ❌ 缺失：基金经理、基金类型、投资策略、风险收益特征、结论、观点

**影响：**
用户自然语言查询命中率低，体验接近"硬代码查询"而非"智能问答"。

### 问题 2：Routing Context 直返机制导致"硬编码感"

**现象：**
- "2025年收益率" → 返回原始表格数据，无 LLM 润色
- 用户感觉"不是 LLM 对话，是硬编码抽取"

**根因：**
`chat_service.py:175-195` 的 Routing Context 预取机制：

```python
# 3.5 Routing context 预取：用确定性 agent 先检索，命中则直返
if routing_context and any(kw in routing_context for kw in _DIRECT_KEYWORDS):
    return ChatTurnResponse(answer=routing_context)  # ← 直接返回，不调 LLM
```

**流程：**
1. 用户输入 → `_route_plan_for_query()` 匹配 alias
2. 确定性 agent 检索 → 命中 `_DIRECT_KEYWORDS` → **直接返回**
3. 只有未命中时 → 才调用 DeepSeek LLM

**`_DIRECT_KEYWORDS`：**
```python
['股票名称', '持仓', '净值增长率', '管理费', '托管费',
 '基金名称', '基金类型', '基金经理', '费率', '前十大']
```

**影响：**
- 结构化数据查询返回 raw text，无格式化
- 用户感知不到 LLM 存在
- 但这是 Phase 7 的设计决策：结构化数据用确定性 agent 保证准确性

### 问题 3：多轮对话效果缺失

**现象：**
- 用 `printf` 管道输入时，每次都是新进程，无上下文记忆
- 用户预期：问完"基金经理是谁"后可以追问"他管理了多久"

**根因：**
- `printf` 管道方式每次启动新进程，session 未持久化
- 真正的多轮对话需要在终端中交互式运行
- 当前 interactive 模式支持 session 持久化，但用户不知道如何使用

**影响：**
多轮对话能力已实现但未被用户感知。

### 问题 4：输出格式不直观

**现象：**
- 原始文本输出，无格式化
- 表格数据以纯文本显示，难以阅读

**根因：**
- 当前 `--no-stream` 模式输出 raw text
- Rich Markdown 渲染未在 `--no-stream` 模式下启用

**影响：**
用户体验差，信息密度低。

---

## Phase 7.2 备选方向

### 方向 A：扩展路由 alias 覆盖（P0）

**目标：** 提升自然语言查询命中率

**任务：**
1. 在 `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 中添加缺失的 alias：
   - 基金经理：`("基金经理", "基金经理是谁", "谁是基金经理", "经理信息")`
   - 基金类型：`("基金类型", "什么类型", "主动还是被动")`
   - 投资策略：`("投资策略", "投资理念", "投资方法")`
   - 风险收益：`("风险收益特征", "风险等级", "收益风险")`
   - 结论观点：`("结论", "观点", "评价", "综合评价")`

2. 为每个 alias 配置对应的 `candidate_queries` 和 `acceptable_title_family`

3. 添加测试验证 alias 命中率

**验收标准：**
- "基金经理是谁" 命中路由并返回结果
- "基金类型是什么" 命中路由并返回结果
- 现有 alias 无回退

### 方向 B：Routing Context 结果 LLM 润色（P0）

**目标：** 让确定性路径的结果也有 LLM 生成感

**任务：**
1. 当 Routing Context 命中时，不直接返回 raw text
2. 将确定性 agent 的结果作为 context 传给 LLM
3. 让 LLM 基于 context 生成自然语言回答
4. 保留 citation 和 evidence

**代码变更：**
```python
# 当前逻辑（直返）
if routing_context and any(kw in routing_context for kw in _DIRECT_KEYWORDS):
    return ChatTurnResponse(answer=routing_context)

# 改进逻辑（LLM 润色）
if routing_context and any(kw in routing_context for kw in _DIRECT_KEYWORDS):
    # 将 routing_context 作为 context 传给 LLM
    llm_context = f"已找到以下相关信息：\n{routing_context}\n\n请基于以上信息回答用户问题。"
    # 调用 LLM 生成回答
    ...
```

**验收标准：**
- 确定性路径的结果有 LLM 润色
- 回答更自然，有"对话感"
- 保留 citation 和 evidence

### 方向 C：多轮对话引导优化（P1）

**目标：** 让用户感知到多轮对话能力

**任务：**
1. 在 interactive 启动时显示提示：
   ```
   已选择 2025 年年报。输入问题开始对话，/help 查看命令，exit 退出。
   提示：支持多轮对话，可以追问上一个问题的细节。
   ```

2. 在回答末尾添加追问建议：
   ```
   > 基金经理是张三
   > 
   > 您可以继续问：
   > - 他管理了多久？
   > - 他的投资风格是什么？
   > - 他管理的其他基金有哪些？
   ```

3. 添加 `/history` 命令查看对话历史

**验收标准：**
- 用户能看到多轮对话提示
- 回答末尾有追问建议
- `/history` 命令可用

### 方向 D：输出格式化（P1）

**目标：** 提升输出可读性

**任务：**
1. 在 `--no-stream` 模式下启用 Rich Markdown 渲染
2. 表格数据使用 Rich Table 格式化
3. 添加 `--plain` 参数保留原始文本模式

**验收标准：**
- 表格数据以 Rich Table 显示
- Markdown 格式正确渲染
- `--plain` 参数可用

### 方向 E：Dayu 场景借鉴（P2）

**目标：** 引入 regenerate/repair/fix/decision/compaction 5 个新场景

**任务：**
1. 实现 regenerate 场景（整章重建）
2. 实现 repair 场景（局部修复）
3. 实现 fix 场景（占位符补强）
4. 实现 decision 场景（研究决策综合）
5. 实现 conversation_compaction 场景（会话摘要压缩）

**验收标准：**
- 至少 regenerate + repair 实现且测试通过
- fix/decision/compaction 可推迟

---

## 优先级排序

| 方向 | 优先级 | 工作量 | 影响 |
|------|--------|--------|------|
| A: 扩展路由 alias | P0 | 2-3 天 | 高（提升命中率） |
| B: Routing Context LLM 润色 | P0 | 2-3 天 | 高（消除硬编码感） |
| C: 多轮对话引导 | P1 | 1-2 天 | 中（提升体验） |
| D: 输出格式化 | P1 | 2-3 天 | 中（提升可读性） |
| E: Dayu 场景借鉴 | P2 | 5-7 天 | 高（扩展能力） |

---

## 测试命令

### 当前可用的测试命令

```bash
# Agent 测试（153 passed）
uv run pytest tests/fund/agent/ -v --tb=short

# E2e 测试（1 failed, 46 passed, 300 skipped）
uv run pytest tests/fund/test_e2e_holdings_regression.py tests/fund/test_e2e_regression.py --tb=short -q

# Interactive 测试（需要终端）
uv run fund-checklist interactive --fund-code 011649 --work-dir .fund_e2e_011649
```

### Phase 7.2 验证命令（待实现）

```bash
# 路由 alias 测试
uv run pytest tests/fund/service/test_route_plan.py -v --tb=short

# 多轮对话测试
uv run pytest tests/fund/cli/test_cli_interactive.py -v --tb=short

# 格式化输出测试
uv run pytest tests/fund/cli/test_cli_output.py -v --tb=short
```

---

## 参考文件

- `fund_agent/service/extraction.py` — `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 定义
- `fund_agent/service/chat_service.py` — `chat_turn()` 路由逻辑（第 175-195 行）
- `fund_agent/cli/main.py` — `_run_interactive_command()` 实现
- `tests/fund/cli/test_cli_interactive.py` — interactive 测试


---

## 补充：确定性 Agent 设计溯源（2026-07-26）

### 设计来源

**Commit:** `22d4ce7` (2026-07-26)
```
fix(phase7): add routing context to interactive + tool_service wiring

- ChatService 新增 tool_service 参数，interactive 不再用空 tool service
- chat_turn 新增 routing context 预取：确定性 agent 先检索，命中关键词直返
- CLI interactive 构建真实 tool service（从 work_dir 加载 document store）
```

### 设计意图

| 目标 | 实现方式 |
|------|---------|
| 性能优化 | 结构化数据查询用确定性 agent，不调 LLM |
| 准确性保证 | 直接调用 `FundDocumentToolService`，避免 LLM 幻觉 |
| 成本节约 | 不消耗 DeepSeek token |

### 实现机制

```python
# chat_service.py:175-195

# 3.5 Routing context 预取：用确定性 agent 先检索，命中则直返
if self._tool_service is not None and agent_result is None:
    from fund_agent.agent import MinimalFundDocumentAgent
    from fund_agent.host import MinimalHost as _MH
    from fund_agent.service.extraction import _route_plan_for_query

    route_plan = _route_plan_for_query(user_text)
    context_parts: list[str] = []
    det_host = _MH(MinimalFundDocumentAgent(self._tool_service))
    for cq in route_plan.candidate_queries:
        r = det_host.run(document_id=document_id, query=cq)
        if r.failure is None and r.answer.strip():
            context_parts.append(f"[查询{cq}]\n{r.answer}")

    routing_context = "\n\n".join(context_parts)
    _DIRECT_KEYWORDS = [
        '股票名称', '持仓', '净值增长率', '管理费', '托管费',
        '基金名称', '基金类型', '基金经理', '费率', '前十大',
    ]
    if routing_context and any(kw in routing_context for kw in _DIRECT_KEYWORDS):
        return ChatTurnResponse(answer=routing_context)  # ← 直接返回，不调 LLM
```

### 问题分析

| 问题 | 根因 | 影响 |
|------|------|------|
| "基金经理是谁" 空结果 | `DISCLOSURE_LOCATOR_CONTRACT_REGISTRY` 无 "基金经理" alias | 用户感知为"硬编码" |
| 返回 raw text | 直返 routing_context，无 LLM 润色 | 信息密度低，难阅读 |
| 设计未文档化 | AGENTS.md 未记录此设计决策 | 用户不知道是有意设计 |

### `_DIRECT_KEYWORDS` vs `aliases` 区别

| 概念 | 用途 | 匹配对象 |
|------|------|---------|
| `aliases` | 匹配用户输入 query | `_route_plan_for_query()` 遍历 |
| `_DIRECT_KEYWORDS` | 检查 routing_context 内容 | `any(kw in routing_context ...)` |

**当前 `aliases`：**
- holdings_top10: ("前十大持仓", "重仓股", "持仓明细")
- asset_allocation: ("资产配置", "资产组合")
- fee_rates: ("费用", "费率", "管理费", "托管费", "销售服务费")
- performance_returns: ("净值增长率", "业绩比较基准收益率", "基准收益率", "收益表现", "基金净值表现")

**当前 `_DIRECT_KEYWORDS`：**
- '股票名称', '持仓', '净值增长率', '管理费', '托管费'
- '基金名称', '基金类型', '基金经理', '费率', '前十大'

**缺失的 alias：**
- 基金经理（有 `_DIRECT_KEYWORDS`，无 `alias`）
- 基金类型（有 `_DIRECT_KEYWORDS`，无 `alias`）
- 投资策略（两者都无）
- 风险收益特征（两者都无）

### Phase 7.2 优化方案

**方案 A：扩展 alias（解决问题 1）**

```python
# 在 DISCLOSURE_LOCATOR_CONTRACT_REGISTRY 中添加
_DisclosureLocatorContract(
    profile_name="fund_manager",
    aliases=("基金经理", "基金经理是谁", "谁是基金经理", "经理信息"),
    candidate_queries=("基金经理", "基金经理简介"),
    acceptable_title_family=("基金经理简介",),
    requires_table_citation=False,
    extraction_allowed=False,
),
```

**方案 B：LLM 润色（解决问题 2）**

```python
# 当前逻辑（直返 raw text）
if routing_context and any(kw in routing_context for kw in _DIRECT_KEYWORDS):
    return ChatTurnResponse(answer=routing_context)

# 优化逻辑（LLM 润色）
if routing_context and any(kw in routing_context for kw in _DIRECT_KEYWORDS):
    # 将 routing_context 作为 context 传给 LLM
    llm_prompt = f"""基于以下已检索到的信息，用自然语言回答用户问题。

已检索信息：
{routing_context}

用户问题：{user_text}

要求：
1. 用简洁的自然语言回答
2. 保留关键数据（数字、日期、名称）
3. 不要编造信息
4. 如果信息不足，明确说明"""

    # 调用 LLM 生成回答
    llm_response = llm_client.next_step(
        document_id=document_id,
        query=llm_prompt,
        tool_results=(),
    )
    return ChatTurnResponse(answer=llm_response.step.answer)
```

**方案 C：设计文档化**

在 AGENTS.md 中添加：
```markdown
## 确定性 Agent 设计

Phase 7 引入 routing context 预取机制：
- 结构化数据查询（费率、持仓、业绩）用确定性 agent
- 命中 `_DIRECT_KEYWORDS` 时直返，不调 LLM
- 目的：性能优化、准确性保证、成本节约

当前 alias 覆盖：前十大持仓、资产配置、费率、业绩
缺失 alias：基金经理、基金类型、投资策略、风险收益
```


---

## 方向 E：修复决策引擎（generate/repair/regenerate 组合编排）

> 日期：2026-07-26
> 来源：011649 端到端实测 + Dayu 源码研究

### 问题背景

Phase 7.1 实测发现：
- 5 年数据生成的报告审计均分（84.1）低于单年报告（90.0）
- 数据量增大 → LLM 犯错概率上升 → 审计分下降
- 手动修复 5 个章节后，Ch2/Ch3/Ch5 显著提升（+7/+5/+9），但 Ch7 因全量重生成退化（-23.5）
- 核心矛盾：**generate 是全量重跑，无法只修复指定章节**

### Dayu 的解法：分层决策树

Dayu（及 fund-checklist 已实现的审计管道）用 4 层规则约束修复决策，不把决策权完全交给 LLM。

#### 第一层：分数阈值决策（程序规则）

```python
SCORE_PASS = 80.0      # ≥80 → pass（不修复）
SCORE_PATCH = 50.0     # 50-79 → patch 路径
                        # <50 → regenerate 路径
```

#### 第二层：违规严重度决策（程序规则）

```python
has_critical = any(v.severity == CRITICAL for v in violations)
if has_critical:
    strategy = "regenerate"  # 即使分数在 50-79 区间，有 CRITICAL 也走 regenerate
else:
    strategy = "patch"
```

#### 第三层：LLM 细粒度决策

LLM 收到违规列表 + 原文 + 合同约束，自行判断：
- **PATCH**：精确定位违规段落，输出 `target_excerpt → replacement` 替换对
- **REGENERATE**：输出 `{"strategy": "regenerate", "reason": "..."}`

LLM 失败时的默认策略：
```python
except Exception:
    if has_critical:
        return RepairPlan(strategy="regenerate")
    else:
        return RepairPlan(strategy="patch")
```

#### 第四层：尝试次数兜底

```
PATCH 最多 3 次 → 失败后降级为 REGENERATE
REGENERATE 最多 3 次 → 失败后降级为模板/标记 degraded
```

#### 完整流程

```
审计评分
  │
  ├─ ≥80 → PASS
  │
  ├─ 50-79 → 有 CRITICAL?
  │    ├─ 是 → REGENERATE（最多3次）
  │    └─ 否 → LLM 判断策略
  │         ├─ PATCH → 精确替换（最多3次）
  │         │    └─ 失败 → REGENERATE
  │         └─ REGENERATE → 整章重写
  │
  └─ <50 → REGENERATE（最多3次）
       └─ 失败 → 模板降级 / degraded 标记
```

### 设计原则

**程序规则做骨架决策，LLM 只在规则允许的空间内做细粒度决策。**

| 层 | 决策者 | 决策依据 | 决策内容 |
|---|---|---|---|
| 第一层 | 程序 | 分数阈值（80/50） | pass / patch路径 / regenerate路径 |
| 第二层 | 程序 | 违规严重度（CRITICAL） | 强制 regenerate |
| 第三层 | LLM | 违规列表 + 原文 + 合同 | 具体 patch 内容 / regenerate 理由 |
| 第四层 | 程序 | 尝试次数（各3次） | 降级 / 模板兜底 |

### 当前实现状态

fund-checklist 的 `audit_pipeline.py` 已实现完整的 4 层决策树：

- `AuditDecision.recommendation`：pass / patch / regenerate（第1层）
- `ChapterRepairer.generate_repair_plan()`：has_critical → regenerate（第2层）
- `_LLM_REPAIR_SYSTEM_PROMPT`：LLM 输出 patch/regenerate JSON（第3层）
- `ChapterProcessState.can_patch()` / `can_regenerate()`：各最多3次（第4层）
- 模板降级：score < 50 或无内容时 fallback

### 我们实测失败的原因

手动修复脚本跳过了第1-2层（分数阈值 + CRITICAL 检测），直接让 LLM 做全局决策，且：
- 无章节标题校验（LLM 把 Ch1 内容替换成 Ch3 的）
- 无尝试次数限制
- 无降级兜底
- 全量重生成覆盖了未修复章节

### Phase 7.2 待办

1. **CLI `repair` 子命令**：只修复指定章节，不重跑其他章节
   - 输入：`--fund-code --year --chapter 0,1,2,3,5 --work-dir`
   - 复用 `ChapterRepairer` + `AuditDecision` 逻辑
   - 每章独立修复 + 独立审计

2. **CLI `regenerate` 子命令**：只重生成指定章节
   - 输入：`--fund-code --year --chapter 3 --work-dir`
   - 复用 `_regenerate_chapter()` 逻辑
   - 保留其他章节不变

3. **修复策略自动选择**：基于审计分数和违规严重度自动选择 repair/regenerate
   - ≥80 → skip
   - 50-79 + 无 CRITICAL → repair
   - 50-79 + 有 CRITICAL → regenerate
   - <50 → regenerate

4. **修复后增量审计**：只重审修复过的章节，不重审全部

5. **修复效果追踪**：记录每章修复前后的分数变化，生成修复报告

### 依赖关系

```
CLI repair/regenerate 子命令
  ├── 复用 ChapterRepairer（已实现）
  ├── 复用 AuditDecision 逻辑（已实现）
  ├── 复用 _regenerate_chapter()（已实现）
  └── 需要：章节级独立修复入口（新增）
```

### 验收标准

- `repair --chapter 0,1,2,3,5` 只修复指定章节，其他章节不变
- 修复后分数提升 ≥ 5 分（被修复章节的平均）
- 全量回归无回退
- 修复耗时 < generate 耗时的 1/3（只修指定章节）

---

## DS 审查结果（2026-07-26）

审查方式：4 个 Explore agents 交叉验证代码（audit_pipeline.py / chat_service.py / extraction.py / scene_config.py / CLI 入口）

### 总体评价

文档技术描述整体准确，核心诊断（alias 覆盖不足 + routing context 直返导致硬编码感）与代码一致。存在少量行号漂移和一个设计层面的重要遗漏（方向 B 与 Phase 7 设计意图的冲突未被讨论）。

### 逐方向核查

#### 方向 A：扩展路由 alias 覆盖 — ✅ 准确

| 断言 | 验证 |
|------|------|
| DISCLOSURE_LOCATOR_CONTRACT_REGISTRY 只有 4 个 contract | ✅ extraction.py:175-213 |
| 现有 alias：前十大持仓、重仓股、持仓明细、资产配置… | ✅ 与代码完全一致 |
| 缺失：基金经理、基金类型、投资策略、风险收益、结论 | ✅ grep 确认全部缺失 |
| _DIRECT_KEYWORDS 含 '基金经理' 但 alias 不含 | ✅ 诊断准确 |

纳入建议：**纳入 P0**

#### 方向 B：Routing Context LLM 润色 — ⚠️ 部分准确

| 断言 | 验证 |
|------|------|
| routing context 直返逻辑存在 | ✅ chat_service.py:175-195 |
| _DIRECT_KEYWORDS 内容 | ✅ 与代码一致 |
| 直返设计是"问题" | ❌ **这是 Phase 7 的有意设计** |

**重大遗漏**：文档未讨论方向 B 与 Phase 7 设计意图的冲突。routing context 直返的三项目标：
- 性能优化：结构化数据查询不调 LLM
- 准确性保证：直接调用 FundDocumentToolService，避免 LLM 幻觉
- 成本节约：不消耗 DeepSeek token

方向 B 会将这三项目标全部推翻。

**三个选项**：
1. LLM 润色 → 失去性能/准确性/成本优势
2. 改进 routing_context 文本格式化（加章节标题、分段、数字对齐）→ 保留三项目标
3. 新增 scene_config 控制是否启用 LLM 润色 → 按场景灵活切换

纳入建议：**推迟，需用户确认 tradeoff**

#### 方向 C：多轮对话引导优化 — ⚠️ 部分准确

| 断言 | 验证 |
|------|------|
| Session 持久化已实现 | ✅ main.py 中 SessionStore/MinimalHost/Session 均有使用 |
| /history 命令存在 | ❌ 代码中完全没有 /history |
| test_cli_interactive.py 存在 | ✅ |
| test_route_plan.py 存在 | ❌ 不存在 |

纳入建议：**纳入 P1**（/history 需新建）

#### 方向 D：输出格式化 — ⚠️ 部分准确

| 断言 | 验证 |
|------|------|
| --no-stream 无 Rich 渲染 | ✅ |
| Rich 未在依赖中 | ❌ Rich 已在 pyproject.toml 依赖中 |
| 需要新增 Rich 依赖 | ❌ 不需要，已有 |

纳入建议：**纳入 P0**

#### 方向 E：修复决策引擎 — ⚠️ 部分准确

| 断言 | 验证 |
|------|------|
| SCORE_PASS = 80.0 / SCORE_PATCH = 50.0 | ✅ audit_pipeline.py:1751-1752 |
| ChapterRepairer 存在 | ✅ audit_pipeline.py:1497 |
| AuditDecision 存在 | ✅ audit_pipeline.py:559 |
| ChapterProcessState 存在 | ✅ audit_pipeline.py:629 |
| _regenerate_chapter() 存在 | ✅ audit_pipeline.py:2316 |
| MAX_PATCH_ATTEMPTS = 3 | ✅ audit_pipeline.py:1763 |
| MAX_REGENERATE_ATTEMPTS = 3 | ✅ audit_pipeline.py:1764 |
| 4 层决策树完整串联 | ⚠️ 组件都存在，但需验证是否已完整串联 |

范围漂移：原始方向 E 描述的是"5 个新场景"，补充章节收敛为两个 CLI 子命令加策略自动选择。补充章节更务实。

纳入建议：**纳入 CLI 子命令部分（P1），推迟完整 5 场景**

### 优先级排序（DS 建议）

| 优先级 | 方向 | 理由 | 工作量 |
|--------|------|------|--------|
| P0 | A: 扩展 alias | 根因修复，直接解决"空结果"问题 | 2-3 天 |
| P0 | D: 输出格式化 | 提升所有场景可读性，与 A 并行无依赖 | 1-2 天 |
| P1 | C: 多轮对话引导 | 快速 UX 提升 | 1-2 天 |
| P1 | E: CLI repair/regenerate | 复用已有组件，解决单章修复痛点 | 3-5 天 |
| P2 | B: LLM 润色 | 需先确认 tradeoff | 2-3 天 |

### 遗漏项（DS 补充）

1. `_DIRECT_KEYWORDS` 应提升为模块常量：当前是 `chat_turn()` 局部变量，每次调用重建。如果方向 B 被纳入，这个重构是必要的前置步骤。
2. 路由命中率监控：文档未讨论如何度量 alias 覆盖改进的效果（如命中率日志、未命中 query 收集）。
3. `test_route_plan.py` 不存在：文档引用了不存在的测试文件，建议在方向 A 实施时一并创建。
