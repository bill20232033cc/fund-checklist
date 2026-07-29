# Phase 7.4 设计：Interactive 模式 Citation 校验策略

> 创建时间：2026-07-29
> 状态：🟡 待评审（已融入 Dayu 对标研究）
> 前置条件：Phase 7.3 ✅

---

## 1. 问题背景

### 1.1 现象

Interactive 模式下用户提问频繁报错：
- `LLM 最终回答缺少受控 citation`
- `LLM 工具调用超过限制`
- `LLM 最终回答缺少受控工具证据`

导致 interactive 模式基本不可用。

### 1.2 已完成的修复（Phase 7.3 补丁）

| 修复 | 文件 | 效果 |
|------|------|------|
| EXCERPT locator_kind 纳入 citation 校验 | `llm_tool_loop.py:684` | search_document 返回的 citation 不再被误拒 |
| key_facts 精确子串校验移除 | `llm_tool_loop.py:693-706` | LLM 改述不再导致假阳性 |
| _parse_final_answer 支持 ```json 代码块 | `deepseek_llm.py:696-714` | LLM 返回代码块格式的 JSON 可正确解析 |
| _document_id_matches 单向前缀匹配 | `llm_tool_loop.py:805-815` | 不允许 LLM 缩短 document_id |
| interactive scene prompt 强化 JSON 指令 | `prompts/interactive/scene.md` | 明确 JSON schema 和 citations 复制要求 |

修复后 interactive 模式可基本工作，但 citation 校验仍是核心矛盾。

---

## 2. 核心矛盾

### 2.1 两个冲突目标

| 目标 | 说明 | 优先级 |
|------|------|--------|
| **对话自然性** | 不是每句话都需要 citation（追问、总结、打招呼） | 用户体验 |
| **数据准确性** | 涉及基金数据的陈述必须有据可依 | 产品底线 |

### 2.2 当前校验链（3 层）

```python
# llm_tool_loop.py: _final_result()

① evidence_texts 非空 → LLM 必须调用工具获取证据
② final_answer.citations 非空 → LLM 必须提供 citation
③ citation_key 精确匹配 → citation 必须来自工具结果
```

**问题**：这 3 层校验对所有场景一视同仁，不区分问题类型。

### 2.3 场景分析

| 场景 | 示例 | 需要 citation？ | 当前行为 |
|------|------|----------------|----------|
| 数据查询 | "费率是多少" | ✅ 必须 | 正确要求 citation |
| 追问上下文 | "刚才的数据是哪一年的" | ❌ 不需要 | 失败（无工具调用） |
| 总结归纳 | "总结一下这只基金" | ⚠️ 部分需要 | 失败（LLM 改述 citation） |
| 打招呼 | "你好" | ❌ 不需要 | 失败（无工具调用） |
| 确认理解 | "你是说费率在下降？" | ❌ 不需要 | 失败（无工具调用） |
| 比较分析 | "和去年比怎么样" | ✅ 必须 | 可能失败（多轮上下文） |

---

## 3. 根因分析

### 3.1 为什么 LLM 不按要求返回 citation？

**原因 1：interactive 是单次 Q&A 架构**

`chat_service.chat_turn()` 每次调用 `runner.run()` 是独立循环。Session.turns 存了历史，但 LLM 看不到 raw tool results，只看到 Phase 7.3 注入的文本摘要。

**原因 2：LLM 自然语言生成倾向**

LLM 在对话模式下倾向于生成流畅的自然语言回答，而不是严格按照 JSON schema 输出。尤其是当问题不需要工具调用时（如追问、总结），LLM 会跳过工具调用直接回答。

**原因 3：citation_key 是精确五元组匹配**

```python
def _citation_key(citation: Citation) -> tuple[str, str, str | None, str | None, int | None]:
    return (
        citation.document_id,
        citation.locator.locator_kind.value,
        citation.locator.section_ref,
        citation.locator.table_ref,
        citation.locator.page_no,
    )
```

LLM 必须从工具返回的 JSON 中**逐字符复制** `document_id`、`section_ref`、`table_ref`、`page_no`——任何截断或自构造都会失败。

**原因 4：ask 模式和 interactive 模式共用同一套校验**

`_final_result()` 不区分场景，对所有模式执行相同的严格校验。

---

---

## 4. Dayu Agent 对标研究

### 4.1 Dayu 的对话模式事实校验架构

研究了 Dayu Agent 在对话模式下如何处理财务报告事实来源的核验，核心发现：

**Dayu 在对话阶段不做实时 citation 校验，而是依赖事后审计。**

| 层级 | Dayu 做法 | fund-checklist 当前做法 |
|------|----------|----------------------|
| 对话阶段 | 无实时 citation 校验；对话压缩时仅要求"不要发明事实" | `_final_result()` 严格 3 层校验，失败直接阻断 |
| 事实规则 | `fact_rules.md` 定义 E1/E2/E3/C1/C2/S1-S7 规则集，用于报告写作阶段 | 无分离的规则集，citation 校验一视同仁 |
| 事后审计 | `audit_facts_tone_json.md` — LLM 审计 prompt，检查报告正文的事实/证据/风格 | 有审计管道（4 类 22 项），但在报告生成后执行 |
| 对话压缩 | `conversation_compaction.md` — "不要发明输入中没有出现的事实" | Phase 7.3 的 episode summary |

### 4.2 Dayu 的关键设计文件

**`fact_rules.md`（事实与引用规则）**：
- 只有被证据直接支持的内容才可写成确定性陈述
- 若证据不足、缺失、冲突或无法确认，不得伪造内容
- 主观判断、归因或解读不得写成硬事实
- 回答末尾必须包含"证据与出处"，使用统一引用格式

**`conversation_compaction.md`（会话压缩）**：
- 不要发明输入中没有出现的事实、偏好或任务
- `confirmed_facts` 只记录输入中已被确认的事实
- `tool_findings` 只记录工具调用带来的高价值发现
- 无法确认的字段保留为空，不编造

**`audit_facts_tone_json.md`（事后审计）**：
- E1: 正文存在关键断言但无可对应的证据条目 → high severity
- E2: 正文出现不带证据的具体数字或口径 → high severity
- E3: 证据条目指向的来源本身不可追溯或不可定位 → high severity
- C1: 大量占位符/未披露/泛化描述 → high severity
- S1-S7: 写作风格违规 → medium/low severity
- 审计结果以 JSON 输出，包含 pass/fail、class、violations 列表

### 4.3 Dayu 设计哲学的核心启示

1. **对话模式不阻断用户交互**：Dayu 认为对话是探索性的，用户可能问各种问题（包括不需要数据支撑的追问、总结、确认）。在对话阶段强制 citation 校验会破坏用户体验。
2. **事实准确性通过报告写作规则保障**：`fact_rules.md` 约束的是报告写作阶段的 LLM 输出，不是对话阶段。
3. **事后审计作为最终防线**：报告生成后，通过专门的审计 prompt 检查事实/证据/风格问题，发现问题再修复。
4. **"不发明事实"是软约束**：对话压缩时只做语义层面的约束（"不要发明"），不做结构层面的校验（citation 精确匹配）。

### 4.4 对 Phase 7.4 设计的影响

Dayu 的方案与当前设计文档中的"方案 D（混合方案）"方向一致，但有一个关键区别：

| 维度 | 方案 D | Dayu |
|------|--------|------|
| 对话阶段 | 分类器判断 + 弱校验 + 标记"未验证" | 不做 citation 校验，仅做"不发明事实"软约束 |
| 报告阶段 | 保留严格校验 | 严格事实规则 + 事后审计 |
| 核心差异 | 对话阶段仍有结构化校验 | 对话阶段完全放开，保障放在报告阶段 |

**结论**：Dayu 的实践验证了"对话模式放宽 citation、报告阶段严格保障"的可行性。Phase 7.4 应采用 Dayu 的分层思路，但保留 fund-checklist 已有的实时校验能力（在 ask 模式和报告生成模式中使用），仅在 interactive 对话模式中放宽。

---

## 5. 设计方案（修订）

### 方案 A：场景感知校验

**核心思路**：根据问题类型有条件地执行 citation 校验。

```python
def _final_result(
    final_answer: FinalAnswer,
    tool_results: tuple[ToolResult, ...],
    trace: tuple[ToolTraceEntry, ...],
    *,
    token_usage: TokenUsage | None = None,
    enforce_citation: bool = True,  # 新增参数
) -> AgentRunResult:
    # 投资建议检测（始终执行）
    ...
    
    if not enforce_citation:
        # 跳过 citation 校验，直接返回
        return AgentRunResult(
            answer=final_answer.answer,
            citations=final_answer.citations,  # 保留 LLM 提供的 citation（如有）
            tool_trace=trace,
            failure=None,
            token_usage=token_usage,
        )
    
    # 原有 citation 校验逻辑
    ...
```

**问题分类器**：

```python
def _question_needs_citation(query: str) -> bool:
    """判断问题是否需要 citation 支持。
    
    规则：
    1. 包含数字、费率、持仓、业绩等数据类关键词 → 需要
    2. 打招呼、追问、总结、确认类 → 不需要
    3. 默认需要（fail-closed）
    """
    # 不需要 citation 的模式
    no_citation_patterns = [
        r"你好|hi|hello|hey",
        r"刚才|上一个|之前|你说的",
        r"总结|归纳|概括|简单说",
        r"明白|了解|知道|好的|对",
        r"什么意思",  # 注意："为什么/怎么理解"可能涉及数据归因，降级为 RELAXED 而非排除
    ]
    for pattern in no_citation_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False
    return True  # 默认需要
```

**优点**：
- 保持数据准确性（数据类问题仍强制 citation）
- 允许自然对话（非数据类问题不强制 citation）
- 最小改动（~30 行）

**缺点**：
- 分类器可能误判（边界情况）
- 需要维护规则列表

### 方案 B：两级 citation 校验

**核心思路**：区分"强 citation"和"弱 citation"。

- **强 citation**：必须有工具调用 + citation 精确匹配（数据类问题）
- **弱 citation**：允许无 citation，但标记为"未验证"（非数据类问题）

```python
class CitationLevel(Enum):
    STRICT = "strict"  # 必须有 citation
    RELAXED = "relaxed"  # 允许无 citation，标记为未验证

def _final_result(..., citation_level: CitationLevel = CitationLevel.STRICT):
    if citation_level == CitationLevel.RELAXED:
        # 允许无 citation，但在回答中标记
        if not final_answer.citations:
            answer = f"{final_answer.answer}\n\n> ⚠️ 以上回答未经数据验证"
            return AgentRunResult(answer=answer, citations=(), ...)
    # 原有逻辑
    ...
```

**优点**：
- 用户明确知道哪些回答已验证、哪些未验证
- 不会因为 citation 问题阻断对话

**缺点**：
- 用户体验下降（频繁看到"未验证"标记）
- 可能被用户忽略（标记疲劳）

### 方案 C：延迟 citation 校验

**核心思路**：先返回回答，异步校验 citation。

```python
def _final_result(...):
    # 先返回回答（不校验 citation）
    result = AgentRunResult(
        answer=final_answer.answer,
        citations=final_answer.citations,
        tool_trace=trace,
        failure=None,
        token_usage=token_usage,
    )
    
    # 异步校验 citation（不阻断返回）
    if not final_answer.citations:
        logger.warning("回答缺少 citation，可能不准确")
    
    return result
```

**优点**：
- 对话流畅，不会阻断
- 保留日志用于后续分析

**缺点**：
- 用户可能看到不准确的回答
- 违反 fail-closed 设计原则

### 方案 D：混合方案（Dayu 启发）

**核心思路**：结合方案 A 和方案 B。

1. **问题分类器**判断是否需要 citation
2. **需要 citation**：执行严格校验（方案 A）
3. **不需要 citation**：执行弱校验（方案 B），标记为"未验证"

```python
def _final_result(..., query: str = ""):
    needs_citation = _question_needs_citation(query)
    
    if not needs_citation:
        # 弱校验：允许无 citation，标记为未验证
        if not final_answer.citations:
            answer = f"{final_answer.answer}\n\n> ⚠️ 以上回答未经数据验证"
            return AgentRunResult(answer=answer, citations=(), ...)
    
    # 严格校验（原有逻辑）
    ...
```

### 方案 E：Dayu 分层方案（推荐）

**核心思路**：借鉴 Dayu 的分层架构，对话模式完全放开 citation 校验，报告模式保留严格校验。

```
┌─────────────────────────────────────────────┐
│              interactive 对话模式             │
│  ┌───────────────────────────────────────┐  │
│  │  "不发明事实" 软约束（system prompt）    │  │
│  │  - 无 citation 校验                    │  │
│  │  - 无 evidence 校验                    │  │
│  │  - 投资建议关键词仍 fail-closed        │  │
│  └───────────────────────────────────────┘  │
│  回答标记：无 citation → 不标记"未验证"       │
│  （Dayu 做法：对话阶段不打扰用户）            │
└─────────────────────────────────────────────┘
                    ↓ 用户查看报告
┌─────────────────────────────────────────────┐
│           generate 报告生成模式              │
│  ┌───────────────────────────────────────┐  │
│  │  严格 citation 校验（现有逻辑不变）     │  │
│  │  + 事后审计管道（E1/E2/E3/C1/S1-S7）  │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**实现要点**：

1. `_final_result()` 增加 `scene: str` 参数（非 `enforce_citation: bool`）
2. `scene == "interactive"` 时：
   - 跳过 evidence_texts 校验
   - 跳过 citations 校验
   - 保留投资建议关键词校验（fail-closed）
   - 保留 key_facts 校验（如有）
3. `scene == "ask"` 或 `scene == "generate"` 时：保持现有严格校验
4. 新增 system prompt 片段注入 interactive 模式：

```markdown
## 事实与引用规则
- 只有被工具返回的证据直接支持的内容，才可以写成确定性陈述。
- 若证据不足或无法确认，不得伪造数据；应明确说明"根据已有信息"或"未找到相关数据"。
- 不要发明输入中没有出现的事实、数字或偏好。
```

**优点**：
- 对话最流畅（完全不阻断）
- 与 Dayu 架构对齐，降低维护成本
- 报告阶段保障不变（严格校验 + 审计管道）

**缺点**：
- 对话中用户可能看到不准确的数据回答（无标记）
- 需要在 system prompt 中强化"不发明事实"约束
- 需要确保 ask 模式不被意外降级

**与方案 D 的对比**：

| 维度 | 方案 D | 方案 E |
|------|--------|--------|
| 对话阶段 | 分类器 + 弱校验 + 标记 | 完全放开 + 软约束 |
| 报告阶段 | 严格校验 | 严格校验 + 事后审计 |
| 用户体验 | 中等（标记疲劳） | 最佳（无阻断无标记） |
| 安全性 | 中（分类器可能误判） | 中（依赖 prompt 约束） |
| 实现复杂度 | 中（分类器 + 两级校验） | 低（scene 参数 + prompt） |
| Dayu 对齐度 | 部分 | 完全 |

---

## 6. 影响评估

### 6.1 对 ask 模式的影响

**无影响**。ask 模式始终执行严格 citation 校验（`enforce_citation=True`）。

### 6.2 对 interactive 模式的影响

| 场景 | 当前行为 | 方案 A | 方案 B | 方案 D | 方案 E |
|------|----------|--------|--------|--------|
| 数据查询 | ✅ 正确 | ✅ 正确 | ✅ 正确 | ✅ 正确 | ✅ 正确 |
| 追问上下文 | ❌ 失败 | ✅ 成功 | ✅ 成功 | ✅ 成功 | ✅ 成功 |
| 总结归纳 | ❌ 失败 | ✅ 成功 | ✅ 成功（标记） | ✅ 成功（标记） | ✅ 成功 |
| 打招呼 | ❌ 失败 | ✅ 成功 | ✅ 成功 | ✅ 成功 | ✅ 成功 |
| 确认理解 | ❌ 失败 | ✅ 成功 | ✅ 成功 | ✅ 成功 | ✅ 成功 |

### 6.3 安全性评估

| 风险 | 方案 A | 方案 B | 方案 D | 方案 E |
|------|--------|--------|--------|
| LLM 幻觉无拦截 | 中（分类器可能误判） | 低（标记提醒） | 低（分类+标记） | 中（依赖 prompt） |
| 违反 fail-closed | 中（非数据类问题） | 低（标记为未验证） | 低（分类+标记） | 中（仅对话模式） |
| 用户信任度下降 | 低 | 中（频繁标记） | 低（仅非数据类） | 低（无标记干扰） |

---

## 7. 实施计划

### 7.1 Phase 7.4 任务分解

**方案 E（Dayu 分层方案）**，无分类器、无未验证标记，用 `scene` 参数直接决定校验级别。

| # | 任务 | 文件 | 行数 | 依赖 |
|---|------|------|------|------|
| 1 | `_final_result()` 增加 `scene: str` 参数 | `llm_tool_loop.py` | ~10 行 | 无 |
| 2 | `scene == "interactive"` 时跳过 citation + evidence 校验 | `llm_tool_loop.py` | ~15 行 | Task 1 |
| 3 | `LlmToolLoopRunner.run()` 透传 `scene` | `llm_tool_loop.py` | ~5 行 | Task 1 |
| 4 | `chat_service.chat_turn()` 透传 `scene` 到 runner | `chat_service.py` | ~10 行 | Task 3 |
| 5 | interactive system prompt 注入"不发明事实"规则 | `scene.md` | ~10 行 | 无 |
| 6 | 单元测试 | `tests/` | ~50 行 | Task 1-5 |
| 7 | e2e 测试 | `tests/e2e/` | ~20 行 | Task 6 |

### 7.2 验证命令

```bash
# 单元测试
uv run pytest tests/fund/agent/test_llm_tool_loop.py -v --tb=short

# interactive 模式手动验证
uv run fund-checklist interactive --fund-code 163415 --work-dir .fund_e2e_163415_v3

# 测试场景：
# 1. "费率是多少" → 应成功（interactive 跳过 citation 校验）
# 2. "刚才的数据是哪一年的" → 应成功（追问场景）
# 3. "你好" → 应成功（非数据类问题）
# 4. ask 模式同样问题 → 应严格校验 citation
```

### 7.3 Stop Conditions

- ask 模式 citation 校验被绕过 → 停止（违反设计约束）
- 全量回归 < 900 passed → 停止
- interactive 模式仍报"缺少受控 citation" → 停止（修复未生效）

### 7.4 DS Review 问题处理

| # | 问题 | 处理 |
|---|------|------|
| C2 | LLM 虚假审计通过风险 | 方案 E 设计如此：对话阶段不阻断，依赖事后审计（generate + audit 管道）。已在 §5.5 缺点中说明。 |
| C3 | multi_turn 连带豁免 | 方案 E 不用 multi_turn，用 scene 参数。interactive/ask/generate 是独立 scene，不存在连带豁免。 |
| S1 | 方案 E 有隐式分类器 | 是。scene 判定是架构级分类（不是问题级分类），开销可忽略，在 §5.5 实现要点已说明。 |
| S2 | multi_turn 判定条件 | 方案 E 不用 multi_turn，此问题不适用。 |
| M1 | 降级路径形同虚设 | 已修正。降级路径改为：如果对话中 LLM 幻觉过多 → 在 interactive prompt 中增加更严格的约束（而非切换到方案 D）。 |
| P1 | §8 待讨论过时 | 已更新，移除分类器相关问题。 |

### 7.5 降级路径

如果方案 E 在实践中发现 interactive 模式 LLM 幻觉过多（用户反馈明显不准确）：
1. **短期**：在 `scene.md` prompt 中增加更严格的约束规则
2. **中期**：考虑对特定工具（如 `read_table`）的结果做格式校验（非 citation 校验）
3. **长期**：如仍不足，可渐进升级到方案 D（增加问题分类器）

---

## 8. 待讨论

1. **是否需要用户可控**：用户能否手动开启/关闭 citation 校验？
2. **与 Phase 7.3 history injection 的交互**：历史轮次的 citation 如何处理？
3. **事后审计何时触发**：interactive 会话结束后是否自动触发审计？
4. **审计结果如何反馈**：如果发现对话中有不准确内容，如何通知用户？

---

## 9. 参考文档

- `docs/debug/interactive-manual-test-20260727.md` — 已知问题清单
- `docs/phase7.3-option-b-optimization.md` — Phase 7.3 方案 B 优化设计
- `docs/agent-evolution-design.md` — Agent 演进记录
- `fund_agent/agent/llm_tool_loop.py:675-710` — 当前 citation 校验逻辑
- `/Users/maomao/dayu-workspace/dayu-agent/workspace/config/prompts/base/fact_rules.md` — Dayu 事实与引用规则
- `/Users/maomao/dayu-workspace/dayu-agent/workspace/config/prompts/scenes/conversation_compaction.md` — Dayu 会话压缩规则
- `/Users/maomao/dayu-workspace/dayu-agent/workspace/config/prompts/tasks/audit_facts_tone_json.md` — Dayu 事后审计 prompt
