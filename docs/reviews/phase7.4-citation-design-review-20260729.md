# Phase 7.4 Citation Design — Adversarial Review

> 日期：2026-07-29
> 评审对象：`docs/phase7.4-citation-design.md`
> 方法论：逐项检查声明与源码、Dayu 对标研究、安全性、降级路径、failure mode 覆盖

---

## 1. 方案 E 安全性 — 对话模式完全放开 citation 校验

### 结论：NEEDS_FIX

**发现 1.1：当前 base/fact_rules.md 仅有 5 条规则，与 Dayu 的 40+ 条规则差距悬殊**

`fund_agent/service/prompts/base/fact_rules.md` 目前为：
- 数据必须来自工具读取的年报原文（1 句）
- 引用数据时使用 citation（1 句）
- 数据缺失时明确告知（1 句）
- 表格数据优先于文字描述（1 句）
- 不得暴露本地路径/raw payload（1 句）

Dayu 的 `fact_rules.md` 包含：事实与分析标注（6 条细分规则）、时间表达、会计与数字呈现（单位/口径/派生指标/分部拆分各 1 条）、来源优先级、证据与出处格式（7 种来源 + 5 种缺失兜底）。

在移除结构化 citation 校验后，当前 5 条规则不足以约束 LLM 的数据准确性行为。方案 E 依赖 prompt 约束，但 prompt 本身质量远低于对标对象。

**建议**：如果采用方案 E，必须先增强 `base/fact_rules.md` 至与 Dayu 同等级别（至少补充会计数字呈现规则、时间表达规则、证据缺失兜底规则），否则 prompt 软约束是空的。

---

**发现 1.2：interactive/scene.md 第 7 条存在分类逃逸漏洞**

```markdown
7. 如果用户问题不需要调用工具（如打招呼、闲聊），直接返回 JSON: {"answer": "自然语言回复", "citations": [], "key_facts": []}
```

这条规则给了 LLM 自行裁决"是否需要工具"的权力。在方案 E 移除全部 citation 校验后，LLM 可将边缘数据问题归类为"不需要工具"并返回空 citation。用户问"这个基金表现怎么样"——LLM 可能回答"表现良好"而不调用任何工具。

**建议**：删除第 7 条的自主裁决权，改为明确列举不需要工具的场景（white list），其余一律要求工具调用；或保留工具调用要求、仅放宽 citation 格式校验。

---

**发现 1.3：投资建议检测仅靠关键词，交互模式下仍存在绕过风险**

`investment_guard.py` 的关键词集合不包含间接投资建议（例如"根据当前估值水平，当前可能是一个较好的入场时机"不含任何关键词但构成投资建议）。在 citation 校验完全移除后，LLM 有更大的自由度生成此类擦边表述。

这不是方案 E 引入的新问题（ask 模式同样存在），但在 interactive 模式下风险放大——因为没有 citation 校验作为后置拦截，关键词检测是对话模式下唯一的安全网。

**建议**：至少记录为 known residual risk；中长期考虑增加 LLM-based 投资建议分类器作为第二层检测。

---

**发现 1.4：Fund-checklist interactive 模式与 Dayu 对话模式的产品定位不同**

Dayu 的对话是"报告写作的中间步骤"——最终交付物是经过 E1-S7 审计的报告。用户从对话中得到的数据最终会经过严格校验。

Fund-checklist 的 interactive 模式本身就是最终交付物。大量用户不会触发 generate 流程，他们只在对话中查询数据。这意味着方案 E 移除的校验在 Dayu 中会被报告阶段补偿，但在 fund-checklist 中可能永远得不到补偿。

文档 §5 的方案 E 架构图（第 325-332 行）暗示用户会从对话"→ 查看报告"，但实际产品路径中这一步是可选的、且多数用户不会触发。这是一个 **产品定位差异导致的架构误用**。

**建议**：在文档中明确记录这一差异，说明为什么 fund-checklist 可以接受比 Dayu 更高的对话阶段不准确性风险（如有产品数据支撑），或调整方案。

---

## 2. 方案 E 与方案 D 的降级路径

### 结论：NEEDS_FIX

**发现 2.1：降级路径仅有一句话，缺乏可操作标准**

第 446 行：「如果方案 E 在实践中发现对话中 LLM 幻觉过多，可叠加方案 D 的分类器（方案 E → 方案 D 渐进升级）。」

缺失内容：
- "幻觉过多"的定量定义（幻觉率 > X%？用户投诉 > Y 次/周？）
- 检测幻觉的机制（没有 telemetry/metrics 任务）
- 触发升级的决策流程（谁判断？自动化还是人工？）

**建议**：补充 `hallucination_rate > 15%` 或等效的量化阈值，并增加监控任务。

---

**发现 2.2：方案 E→D 不是简单叠加，需要新建分类器**

方案 E 的实现约 20 行（scene 参数 + prompt），方案 D 需要约 60 行（分类器 + 两级校验 + 标记逻辑）。从 E 降级到 D 意味着紧急实现 ~60 行从未写过的代码。这不是降级路径，是紧急重构。

**建议**：如果方案 E 是推荐方案，可以考虑预先实现方案 D 的分类器但默认关闭（feature flag），使降级变为一行配置切换；或在文档中诚实标注 E→D 的降级需要 1-2 个工程日。

---

**发现 2.3：缺少向前降级路径（方案 E → 完全恢复严格模式）**

如果 interactive 模式下出现严重幻觉事故（例如用户截图传播错误数据），可能需要紧急恢复全部 citation 校验。目前的方案 E 设计没有保留 force-enable 的开关。

**建议**：增加环境变量或运行时开关 `FORCE_CITATION_CHECK=1` 作为紧急熔断。

---

## 3. §4 Dayu 对标研究的结论准确性

### 结论：NEEDS_FIX（2 处事实错误，1 处关键遗漏）

**发现 3.1：E1-S7 规则集归属错误**

文档 §4.1 第 114 行：
> `fact_rules.md` 定义 E1/E2/E3/C1/C2/S1-S7 规则集，用于报告写作阶段

实际上：
- `fact_rules.md` 定义的是**写作规则**（事实标注、时间表达、会计数字、来源、证据格式）——**不含** E1-S7 审计代码
- `audit_facts_tone_json.md` 定义的是 **E1/E2/E3/C1/C2/S1-S7 审计规则**（证据充分性、内容合规性、写作风格审计口径）

这两个文件是不同层级的设计：fact_rules.md 是给写作 LLM 的 prompt，audit_facts_tone_json.md 是给审计 LLM 的 prompt。文档将它们混为一谈。

**建议**：修正为「`audit_facts_tone_json.md` 定义 E1/E2/E3/C1/C2/S1-S7 事后审计规则集；`fact_rules.md` 定义对话/写作阶段的实时事实规则」。

---

**发现 3.2：缺少 Dayu 对话阶段 prompt 的实际内容佐证**

文档 §4.1 声称「Dayu 在对话阶段不做实时 citation 校验」，其证据来自：
- `fact_rules.md`（写作规则）
- `conversation_compaction.md`（压缩规则）
- `audit_facts_tone_json.md`（事后审计）

但**缺失了最关键的证据**：Dayu 对话场景的 system prompt 文件。如果 Dayu 在对话 prompt 中注入了 `fact_rules.md` 的全部内容，那么它就是"强 prompt 软约束 + 无结构化校验"——这比方案 E 的弱 prompt + 无校验要强得多。

我检查了 fund-checklist 当前的 `scene_config.py`，interactive scene 确实注入了 `base/fact_rules.md`（第 91 行）。但没有验证 Dayu 侧是否也做了同样的注入。

**建议**：补充 Dayu 对话场景的 prompt manifest/配置文件作为证据；如果无法获取，标注此结论为"基于可用文件推断"而非确认事实。

---

**发现 3.3：缺少 Dayu 与 fund-checklist 的产品定位对比分析**

这是 §4 最关键的遗漏。文档正确描述了 Dayu 的技术架构，但没有分析技术架构背后的产品假设：

| 维度 | Dayu | fund-checklist |
|------|------|---------------|
| 对话的最终交付物 | 报告（经过审计） | 对话回答本身 |
| 是否有事后审计补偿 | 是（每个报告章节） | 否（审计仅用于 generate 流程） |
| 用户在对话中获取数据的频率 | 低（对话是引导） | 高（对话是主要使用方式） |

这使得"Dayu 验证了对话模式可以完全放开"的结论在产品层面不成立——Dayu 验证的是"当有事后审计时，对话可以放开放"，但 fund-checklist 的 interactive 用户没有事后审计保护。

**建议**：在 §4.4 或新增 §4.5 中补充产品定位差异分析，并据此调整结论的确定性程度。

---

## 4. 实施计划的任务分解完整性

### 结论：NEEDS_FIX（推荐方案与任务列表不一致）

**发现 4.1：§5.5 推荐方案 E，但 §7.1 任务列表是方案 D**

这是文档最严重的一致性问题：

- **推荐方案 E**（第 439 行）：scene 参数 + prompt 片段，~20 行，无需分类器
- **任务列表**（第 406-414 行）：Task 1 实现 `_question_needs_citation()` 分类器、Task 2-5 实现 `enforce_citation` + 弱校验 + 未验证标记

方案 E 不需要分类器，不需要 `enforce_citation` 参数，不需要"未验证"标记。这两个方案需要的是**完全不同的任务分解**。

**建议**：为方案 E 重写 §7.1 的任务分解，或明确说明先实施方案 D、方案 E 为远期目标。

---

**发现 4.2：方案 E 实际需要的任务（文档缺失）**

如果实施方案 E，至少需要以下任务：

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 1 | 增强 `base/fact_rules.md` | `prompts/base/fact_rules.md` | 对齐 Dayu 规则密度（见发现 1.1） |
| 2 | 修改 interactive/scene.md 移除自主裁决漏洞 | `prompts/interactive/scene.md` | 见发现 1.2 |
| 3 | `_final_result()` 增加 `scene` 参数 ± early return | `llm_tool_loop.py` | ~15 行 |
| 4 | `LlmToolLoopRunner.run()` 透传 scene | `llm_tool_loop.py` | ~5 行 |
| 5 | `ChatService.chat_turn()` 传入 scene="interactive" | `chat_service.py` | ~5 行 |
| 6 | 投资建议检测独立验证（不受 scene 影响） | `llm_tool_loop.py` | 确认逻辑 |
| 7 | 增加 `FORCE_CITATION_CHECK` 熔断开关 | `llm_tool_loop.py` | 见发现 2.3 |
| 8 | 单元测试 | `tests/` | ~50 行 |
| 9 | e2e 测试 | `tests/e2e/` | ~20 行 |

---

**发现 4.3：缺少监控/可观测性任务**

无论采用哪个方案，移除或放宽 citation 校验都需要能观测到影响：
- 轮次级别的 citation 命中率统计
- LLM 声称"不需要工具"但用户实际问了数据问题的比例
- 用户反馈/投诉中与数据准确性相关的占比

**建议**：增加一个轻量级 telemetry 任务（日志级别指标即可）。

---

**发现 4.4：stop condition 不够全面**

当前 stop conditions（§7.3）只有 3 条，缺少：
- interactive 模式幻觉率抽样 > X% → 停止（需先定义幻觉检测方案）
- ask 模式用户投诉数据错误增加 > Y% → 停止（防止非 interactive 用户被影响）
- 缺少"回滚验证"条件：确保可以干净回退到 Phase 7.3 行为

---

## 5. 遗漏的 Failure Mode

### 结论：NEEDS_FIX（8 个遗漏）

**FM1：Citation 洗钱（Citation Laundering via History）**

场景：Turn 1: LLM 调用工具获取数据 A、B、C（citation 校验通过）。Turn 2: 用户追问"那 D 呢？"LLM 未调用工具，直接回答"根据之前的分析，D 是 1.5%"——D 是 LLM 编造的，但用户会因为 Turn 1 有 citation 而信任 Turn 2。

根因：Phase 7.3 history injection 提供文本摘要（无 structured citation），LLM 可以混入编造数据。移除 citation 校验后，Turn 2 不再被拦截。

**FM2：多轮幻觉累积（Multi-Turn Hallucination Accumulation）**

场景：10 轮对话中，每轮 LLM 编造一个小数据点（不会触发用户怀疑），第 10 轮用户基于前 9 轮的累计错误做决策。

根因：无跨轮次一致性校验。方案 E 移除了唯一的跨轮次数据准确性保障。

**FM3：Excerpt 选择性引用（Excerpt Cherry-Picking for Hallucination）**

场景：LLM 调用 GET_EXCERPT 获取一段文本，在回答中声称该 excerpt 支持某个结论，但摘录内容实际说的是另一件事。Phase 7.3 已加入 EXCERPT locator_kind，使 LLM 更容易利用摘录构建似是而非的引用。

当前校验只检查 citation key 是否来自工具返回，并不检查 answer 的语义是否与 evidence_text 一致。移除 citation 校验后，连 key 匹配这一层也没有了。

**FM4：Scene 参数误传（Scene Parameter Misrouting）**

场景：ask 模式的某条路径意外将 scene 传递为 "interactive"，导致严格校验被绕过。Python 的字符串参数没有编译时类型安全——`scene: str` 接受任何字符串。

建议：使用 `Literal["ask", "interactive", "generate"]` 类型 + mypy 校验。

**FM5：投资建议擦边球（Investment Advice Boundary Blurring）**

场景：interactive 模式下，LLM 生成"根据当前管理费率和历史表现，该基金在同类中性价比突出，值得持续关注"——不含关键词，不触发投资建议检测，但实质上是软性推荐。

方案 E 移除 citation 校验后，LLM 回答自由度增大，这类擦边球概率上升。

**FM6：回退时的数据一致性问题（Rollback Data Inconsistency）**

场景：方案 E 上线 2 周后因幻觉问题熔断恢复严格模式。同期 Session 中有历史轮次是方案 E 下产生的（可能有未检测到的错误数据），后续轮次在严格模式下处理，产生"旧错新对"的不一致体验。

**FM7：Prompt 约束过拟合（Prompt Constraint Overfitting）**

场景：增强后的 fact_rules.md 在测试中有效，但随着模型版本升级（如 DeepSeek v5），prompt 约束效果可能退化。与结构化校验不同，prompt 约束的效果无法通过断言测试（assertion test）验证。

**FM8：用户信任静默侵蚀（Silent Trust Erosion）**

场景：方案 E 移除了所有 citation 错误提示（不再有"LLM 最终回答缺少受控 citation"报错）。用户不会看到任何错误，但数据准确性下降。问题不会以 bug report 形式暴露，而是以用户逐渐不再使用产品的方式体现。

这是最难检测的 failure mode——所有指标都是绿的（无错误、无崩溃），但数据质量在下降。

---

## 总结

| 评审项 | 结论 | 严重度 |
|--------|------|--------|
| 1. 方案 E 安全性 | NEEDS_FIX | High — prompt 约束基础薄弱 + 分类逃逸漏洞 |
| 2. 降级路径 | NEEDS_FIX | Medium — 不可操作的单句描述 + 需新建代码 |
| 3. Dayu 对标准确性 | NEEDS_FIX | Medium — 2 处事实错误 + 产品定位差异未分析 |
| 4. 任务分解完整性 | NEEDS_FIX | High — 推荐方案与任务列表不匹配 |
| 5. Failure Mode 覆盖 | NEEDS_FIX | High — 8 个遗漏，FM1/FM8 最危险 |

**根本问题**：文档推荐了最激进的方案（E），但没有为方案 E 准备相应的安全基础设施增强（prompt 质量、监控、熔断），且任务列表写的是另一个方案。

**核心建议**：
1. 优先解决 §4.1 的方案/任务不匹配问题——要么任务列表改为配套方案 E，要么推荐改为方案 D
2. 如果坚持方案 E，必须先增强 `base/fact_rules.md` 和修补 `interactive/scene.md` 的逃逸漏洞
3. 补充量化降级标准和检测手段，否则方案 E 的"试运行"无法做出数据驱动的降级决策
4. 增加 `FORCE_CITATION_CHECK` 熔断开关作为最低成本的保险
