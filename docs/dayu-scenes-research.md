# Dayu Agent 场景研究报告

> 研究时间：2026-07-25
> 研究目的：梳理 Dayu 的 14 个场景设计，评估对 fund-checklist 的价值
> 数据来源：dayu-agent 代码库（v0.1.4）

---

## 一、Dayu 场景全景

Dayu 共有 **14 个场景**，覆盖从单轮问答到报告生成的完整流程。

| 场景 | 描述 | max_iterations | 温度配置 | 核心能力 |
|------|------|----------------|----------|----------|
| **prompt** | 单轮财报问答 | 8 | interactive | LLM 自主工具调用 |
| **prompt_mt** | 多轮财报分析 | 16 | interactive | 多轮对话 + 上下文记忆 |
| **interactive** | 交互式财报分析 | 20 | interactive | 富 REPL + 会话持久化 |
| **wechat** | 微信交互式分析 | 16 | interactive | 微信消息格式适配 |
| **write** | 写作场景 | 24 | write | 报告章节生成 |
| **audit** | 审计场景 | 12 | write | 报告质量审计 |
| **confirm** | 证据复核 | 12 | write | 审计结果复核 |
| **regenerate** | 整章重建 | 24 | write | 基于审计反馈重写整章 |
| **repair** | 局部修复 | 16 | write | 最小必要局部修复 |
| **fix** | 占位符补强 | 12 | write | 数据缺失补强 |
| **infer** | 公司业务类型判断 | 8 | write | 公司特征识别 |
| **overview** | 第0章封面页 | 8 | write | 封面生成 |
| **decision** | 研究决策综合 | 12 | decision | 继续研究/暂缓/放弃判断 |
| **conversation_compaction** | 会话摘要压缩 | 8 | write | 长对话上下文压缩 |

---

## 二、场景分类与价值评估

### 2.1 已对齐的能力

| Dayu 场景 | fund-checklist 对应 | 状态 |
|-----------|---------------------|------|
| prompt | `ask` 子命令 | ✅ Phase 5 完成 |
| prompt_mt | `interactive` 子命令 | 🔵 Phase 7 候选 |
| interactive | `interactive` 子命令 | 🔵 Phase 7 候选 |
| write | `generate` 子命令 | ✅ Phase 3.5 完成 |
| audit | `audit` 子命令 | ✅ Phase 3.5 完成 |
| confirm | `deep-audit` 子命令 | ✅ Phase 3.5 完成 |
| infer | `infer_fund_type` 函数 | ✅ Phase 6 完成 |
| overview | Ch0 封面生成 | ✅ Phase 3.5 完成 |

### 2.2 未对齐的能力（高价值）

#### regenerate（整章重建）

**场景描述**：当审计发现章节有结构性失败时，基于骨架与修复合同整章重建正文。

**执行契约**：
- 基于骨架与修复合同整章重建
- 关键断言必须同步重建证据锚点
- 不补占位符（那是 fix 的事）
- 不做局部 patch（那是 repair 的事）
- 只输出完整章节正文

**与当前 generate 的区别**：
- `generate`：从零生成，不感知审计反馈
- `regenerate`：基于审计反馈重写，保留骨架，修复结构问题

**对我们的价值**：
- 当前我们 `generate` 失败后只能整体重跑（8 章全部重新生成）
- Dayu 的 `regenerate` 只重写有问题的章节，更高效
- 审计发现 Ch3 结构错误 → 只重写 Ch3 → 节省 7/8 的 LLM 调用

**实现难度**：中等
- 需要：审计结果 → 结构化反馈 → 传入 regenerate prompt
- 不需要：新的工具、新的数据模型

---

#### repair（局部修复）

**场景描述**：当审计发现章节有小问题时，做最小必要局部修复。

**执行契约**：
- 只输出最小必要局部修复
- 不重新研究
- 不整章改写
- 不顺手优化风格
- 无法修复时说明原因，不编造

**与 regenerate 的区别**：
- `repair`：小问题，改几句话
- `regenerate`：大问题，重写整章

**对我们的价值**：
- 当前我们没有局部修复能力
- 审计发现 Ch3 某个数字错误 → 只改那一句话 → 更精准
- 避免整章重写引入新问题

**实现难度**：中等
- 需要：审计结果 → 定位具体问题 → 传入 repair prompt
- 不需要：新的工具、新的数据模型

---

#### fix（占位符补强）

**场景描述**：当审计发现章节有占位符时，补强数据缺失。

**执行契约**：
- 只处理占位符及其直接相邻上下文
- 能补证则补证
- 不能补证则保留规范化占位符
- 占位符格式：`【占位符】（缺口：{缺失信息} ｜ 需要：{来源类型} ｜ 已检索：{已检索范围} ｜ 下一步：{建议}）`

**与 repair 的区别**：
- `fix`：数据缺失，需要补证据
- `repair`：数据错误，需要修正

**对我们的价值**：
- 当前我们没有占位符机制
- 数据缺失时直接跳过或报错
- Dayu 的 fix 会保留结构化的占位符，告诉用户缺什么、怎么补
- 用户可以根据占位符提示，手动补充数据

**实现难度**：较高
- 需要：占位符数据模型、占位符检测、占位符补强逻辑
- 需要：修改生成流程，支持占位符输出

---

### 2.3 未对齐的能力（中低价值）

#### wechat（微信交互式分析）

**场景描述**：与 interactive 几乎相同，但针对微信消息格式优化。

**与 interactive 的区别**：
- 输出格式：微信卡片 vs CLI Markdown
- 消息长度：微信有字数限制
- 交互方式：微信异步 vs CLI 同步

**对我们的价值**：
- 如果未来做微信 bot，需要这个场景
- 现阶段只做 CLI，不需要

**实现难度**：低（如果已有 interactive，只需调整输出格式）

---

#### decision（研究决策综合）

**场景描述**：基于前文章节的结构化输入，形成最终的继续研究/暂缓/放弃判断。

**执行契约**：
- 以前文章节为主上下文
- 只有判断链有缺口时才用工具补最小必要事实
- 不写信息罗列式摘要
- 不为了显得完整而宽泛研究
- 输出：研究决策正文 + 证据与出处

**与我们 Ch7 的区别**：
- 我们的 Ch7：信号评分（确定性） + 定性分析（LLM）
- Dayu 的 decision：投资决策（继续研究/暂缓/放弃），更主观

**对我们的价值**：
- AGENTS.md 禁止我们输出"买入/卖出"投资建议
- 但"是否值得继续研究"不违反这个约束
- 如果未来要做投资决策辅助，这个场景有价值

**实现难度**：中等
- 需要：前文章节结构化输入、决策 prompt 设计
- 需要：明确的投资决策框架（继续研究/暂缓/放弃的标准）

---

#### conversation_compaction（会话摘要压缩）

**场景描述**：长对话时，把历史轮次压缩成自然语言摘要，节省 token。

**触发条件**：
- ≥10 轮 OR ≥60% token

**执行方式**：
- threading.Thread 后台 LLM 异步
- 压缩最近 N 轮为 Episode Summary
- 丢弃原始轮次，保留摘要

**对我们的价值**：
- 典型使用场景 <5 轮，不需要
- 如果用户习惯长对话（>10 轮），需要
- Phase 7 可选实现

**实现难度**：中等
- 需要：Episode Summary 数据模型、异步 LLM 调用、触发条件检测
- 需要：修改上下文截断逻辑，优先保留摘要

---

## 三、场景依赖关系

```
prompt (单轮问答)
  ↓
prompt_mt (多轮分析)
  ↓
interactive (交互式)
  ↓
wechat (微信适配)

write (写作)
  ↓
audit (审计)
  ↓
confirm (复核)
  ↓
regenerate (整章重建)
  ↓
repair (局部修复)
  ↓
fix (占位符补强)

infer (公司判断)
  ↓
decision (研究决策)
```

---

## 四、实现优先级建议

### Phase 7（当前）

| 优先级 | 场景 | 理由 |
|--------|------|------|
| P0 | interactive | 多轮对话是核心能力 |
| P0 | conversation_compaction | 长对话的必要前提 |

### Phase 8（报告质量）

| 优先级 | 场景 | 理由 |
|--------|------|------|
| P1 | regenerate | 审计后精准修复，避免整体重生成 |
| P1 | repair | 小问题局部修复，更精准 |
| P2 | fix | 占位符机制，提升数据完整性 |

### Phase 9（扩展）

| 优先级 | 场景 | 理由 |
|--------|------|------|
| P3 | decision | 投资决策辅助，需明确框架 |
| P3 | wechat | 微信入口，需产品方向确认 |

---

## 五、技术要点

### 5.1 Scene Manifest 结构

```json
{
  "scene": "interactive",
  "model": {
    "default_name": "mimo-v2.5-pro-thinking-plan",
    "allowed_names": [...],
    "temperature_profile": "interactive"
  },
  "runtime": {
    "agent": { "max_iterations": 20 },
    "runner": { "tool_timeout_seconds": 90.0 }
  },
  "fragments": [
    { "id": "base_agents", "type": "AGENTS", "path": "base/agents.md", "order": 100 },
    { "id": "base_soul", "type": "SOUL", "path": "base/soul.md", "order": 200 },
    { "id": "interactive_scene", "type": "SCENE", "path": "scenes/interactive.md", "order": 500 }
  ],
  "context_slots": ["fins_default_subject", "base_user"]
}
```

### 5.2 Fragments 装配

```
Scene Manifest.fragments
  ↓ 按 order 排序
  ↓ 加载每个 fragment 文件
  ↓ 拼接成 system_prompt
最终 system_prompt
```

### 5.3 Context Slots 填充

```
Scene Manifest.context_slots
  ↓ 声明可注入的 slot
  ↓ 运行时填充实际数据
  ↓ 注入到 system_prompt
最终 system_prompt + context
```

---

## 六、结论

Dayu 的 14 个场景覆盖了从单轮问答到报告生成的完整流程。我们已对齐 8 个，还有 6 个未对齐。

**高价值场景**：
- regenerate：审计后精准修复
- repair：小问题局部修复

**中价值场景**：
- fix：占位符补强
- conversation_compaction：长对话压缩

**低价值场景**：
- wechat：微信入口
- decision：投资决策

建议按优先级逐步实现，先完成 Phase 7（interactive + conversation_compaction），再进入 Phase 8（regenerate + repair + fix）。
