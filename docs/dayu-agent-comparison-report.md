# dayu-agent vs fund-checklist 比较报告

> 文档定位: 外部能力对标研究输入材料，不是已承诺 roadmap
> 比较时间: 2026-07-15
> 比较范围: Agent 问答能力、分析报告生成
> 数据来源: GitHub 代码实现 + 本地项目分析
> 使用边界: 仅用于识别能力差距与候选方向；任何用户侧新入口（`ask`、`interactive`、`streaming`）或架构变更，必须先进入 `docs/implementation-control.md` 裁决，并遵守 `AGENTS.md` 对 `dayu` 引用和新增 CLI 入口的硬约束

---

## 一、架构对比

### 1.1 整体架构

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **架构分层** | 4 层: UI → Service → Host → Agent | 4 层: UI → Service → Host → Agent |
| **设计哲学** | "宿主强约束下的 LLM in the loop" | "确定性优先、LLM 受控" |
| **Agent 驱动方式** | LLM 自主决策工具调用 | 确定性序列 + 注入式 LLM |
| **执行链路** | UI → startup → Service → Contract → Host → scene → Agent | CLI → Service → Host → Agent (固定 4 步) |

### 1.2 Agent 状态机

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **状态机** | `AsyncAgent` 完整状态机: PrepareIteration → CallRunner → HandleToolBatch/ContinueAnswer/Finalize | `MinimalFundDocumentAgent` 固定 4 步: search → read_section → list_tables → read_table |
| **迭代控制** | 动态迭代, LLM 自主决定何时停止 | 固定 4 步, 无迭代 |
| **失败恢复** | 连续失败工具批次 → fallback_mode (raise_error/force_answer) | 单次失败 → 终止 |
| **截断续写** | 支持 (ContinueAnswer 状态) | 不支持 |

### 1.3 LLM 集成

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **LLM 角色** | 核心决策者, 自主决定工具调用 | 受控参与者 (注入式), 仅在报告生成中直接调用 |
| **支持模型** | 8+ provider (Mimo/DeepSeek/Gemini/OpenAI/Anthropic/通义千问/Ollama/自定义) | 2 provider (DeepSeek/Mimo) |
| **模型配置** | 灵活: scene manifest 独立声明默认模型和允许列表 | 固定: 环境变量配置 |
| **Runner 协议** | `AsyncRunner` 协议, 支持 SSE 流式输出 | `LlmClientProtocol` 最小协议, 无流式 |

---

## 二、问答能力对比

### 2.1 单次问答

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **入口** | `dayu-cli prompt` | `fund-checklist read` |
| **问题理解** | LLM 自主理解意图 | 纯字符串匹配, 无语义理解 |
| **工具调用** | LLM 自主决策, 动态选择工具和参数 | 固定 4 步序列, 硬编码顺序 |
| **多步推理** | 支持, LLM 可根据中间结果调整策略 | 不支持, 固定流程 |
| **证据收集** | LLM 自主决定需要哪些证据 | 固定收集模式 (search → section → tables) |
| **答案生成** | LLM 生成自然语言回答 | 从表格/章节提取数据, 无自然语言生成 |

### 2.2 多轮对话

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **交互模式** | `dayu-cli interactive` 多轮对话 | 不支持 |
| **会话记忆** | 两层记忆模型: Pinned State + 单总池 | 无会话记忆 |
| **上下文压缩** | 支持: 软上限主动压缩 + 硬上限压缩重试 | 不支持 |
| **会话恢复** | 支持: pending turn lease 重发 | 不支持 |

### 2.3 微信接入

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **微信入口** | `dayu-wechat` daemon, 支持后台服务 | 不支持 |
| **消息类型** | 文本消息 (首版) | - |
| **服务管理** | install/start/stop/status/list/uninstall | - |

### 2.4 联网搜索

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **搜索工具** | `search_web` (Tavily/Serper/DuckDuckGo) | 不支持 |
| **网页抓取** | `fetch_web_page` (requests + Playwright 浏览器回退) | 不支持 |
| **实时数据** | 支持获取实时市场数据、新闻 | 不支持 |

---

## 三、报告生成对比

### 3.1 报告结构

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **章节数量** | 10 章 (Ch0-Ch9) | 8 章 (Ch0-Ch7) |
| **内容覆盖** | 生意/经营/竞争/管理层/财务/估值/风险/决策/来源 | 产品定义/收益归因/经理画像/投资者获得感/阶段变化/风险/综合评估 |
| **定性分析** | LLM 生成, 行业差异化模板 | LLM 生成, 禁止包含数字 |
| **数据表格** | LLM 生成 (可能包含幻觉) | 程序生成 (100% 准确) |

### 3.2 报告生成流程

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **触发方式** | `dayu-cli write --ticker AAPL` | `fund-checklist generate` |
| **写作流程** | infer → 逐章写作 → Ch10 → Ch0 → 来源清单 | 数据抽取 → Ch1-6 独立生成 → 审计闭环 → Ch0+Ch7 |
| **章节独立性** | 每章可单独重写 | 每章独立生成和审计 |
| **生成顺序** | 先 Ch1-9, 再 Ch10, 最后 Ch0 | 先 Ch1-6, 通过后生成 Ch0+Ch7 |

### 3.3 模板系统

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **模板类型** | 定性分析模板 (三层: 文章骨架/章节骨架/条件项) | ChapterContract (must_answer/must_not_cover/required_output_items) |
| **条件渲染** | `<when_tool>` / `<when_tag>` 条件块 | 无条件渲染 |
| **行业差异化** | `preferred_lens` 行业视角 | 无行业差异化 |
| **公司特异变量** | 支持 (通过条件项) | 不支持 |

### 3.4 审计管道

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **审计层数** | 3 层 (程序 + LLM + LLM 复核) | 3 层 (程序 + LLM + LLM 复核) |
| **违规分类** | 4 类 22 项 (P1-P4/E1-E5/S1-S7/C1-C6) | 4 类 22 项 (P1-P4/E1-E5/S1-S7/C1-C6) |
| **评分权重** | 程序 30% + LLM 70% | 程序 30% + LLM 70% |
| **修复策略** | PATCH / REGENERATE, 各最多 3 次 | PATCH / REGENERATE, 各最多 3 次 |
| **幻觉检测** | 未明确 | `contains_non_year_numbers()` 检测非年份数字 |

---

## 四、工具系统对比

### 4.1 文档读取工具

| 工具 | dayu-agent | fund-checklist |
|------|------------|----------------|
| `list_sections` | ✅ | ✅ |
| `read_section` | ✅ | ✅ |
| `search_document` | ✅ | ✅ |
| `list_tables` | ✅ | ✅ |
| `read_table` | ✅ | ✅ |
| `get_excerpt` | ✅ | ✅ |
| `read_document` | ✅ | ❌ |

### 4.2 联网工具

| 工具 | dayu-agent | fund-checklist |
|------|------------|----------------|
| `search_web` | ✅ (Tavily/Serper/DuckDuckGo) | ❌ |
| `fetch_web_page` | ✅ (requests + Playwright) | ❌ |

### 4.3 财报工具

| 工具 | dayu-agent | fund-checklist |
|------|------------|----------------|
| 下载工具 | ✅ (SEC/巨潮/披露易) | ❌ |
| 上传工具 | ✅ | ❌ |
| 处理工具 | ✅ | ❌ |

### 4.4 工具约束

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **工具允许列表** | scene manifest ∩ selected_toolsets ∩ execution_permissions | `ALLOWED_LLM_TOOL_NAMES` 固定 6 个 |
| **document_id 绑定** | 无绑定, 可跨文档 | 强制绑定, 防止跨文档访问 |
| **参数校验** | 工具内部校验 | 三重校验 (工具名/document_id/参数) |

---

## 五、上下文治理对比

### 5.1 上下文预算

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **预算管理** | `context_budget.py` 完整预算治理 | 无预算治理 |
| **软上限** | 主动压缩 | - |
| **硬上限** | 压缩重试 | - |
| **工具结果截断** | 预测性截断 (宽字符感知) | 固定行数限制 (`_MAX_TABLE_ROWS`) |
| **续写** | 支持 (ContinueAnswer) | 不支持 |

### 5.2 会话记忆

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **记忆模型** | 两层: Pinned State + 单总池 | 无记忆 |
| **Pinned State** | 不可压缩的会话级反幻觉锚点 | - |
| **单总池** | budget = clamp(window*ratio, floor, cap) | - |
| **Episode summaries** | 支持 | - |
| **Raw Transcript** | 永不物理删除, 仅 compacted_turn_count 推进 | - |

---

## 六、流式输出对比

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **流式协议** | SSE (Server-Sent Events) | 不支持 |
| **事件类型** | CONTENT_DELTA / REASONING_DELTA / FINAL_ANSWER / TOOL_EVENT / WARNING / ERROR / METADATA / DONE | 无事件流 |
| **推理过程回显** | 支持 (`--thinking` / `--no-thinking`) | 不支持 |
| **工具调用追踪** | 支持 (`--enable-tool-trace`) | 支持 (tool_trace) |

---

## 七、数据源对比

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **美股** | SEC (10-K/10-Q/20-F/6-K/8-K/SC13/DEF14A) | 不支持 |
| **A 股** | 巨潮 (FY/H1/Q1-Q4) | 不支持 |
| **港股** | 披露易 (FY/H1/Q1-Q4) | 不支持 |
| **本地 PDF** | 支持 (upload_filing) | 支持 (import) |
| **文档格式** | PDF/HTML/Markdown/Docling JSON | PDF → Docling JSON |

---

## 八、渲染输出对比

| 维度 | dayu-agent | fund-checklist |
|------|------------|----------------|
| **渲染入口** | `dayu-render` | 无独立渲染工具 |
| **输出格式** | HTML / PDF / Word (.docx) | Markdown |
| **渲染引擎** | Pandoc + Chrome (Headless) | - |

---

## 九、关键差距总结

### 9.1 Agent 问答能力候选差距（对照观察）

> 颜色仅为 dayu-agent 有而 fund-checklist 无的存在性标记，不表示实施优先级。

| 差距 | 存在性 | 说明 |
|------|--------|------|
| **无 LLM 自主工具调用** | 无 | dayu-agent 的 LLM 自主决策工具调用, fund-checklist 当前用户链路偏确定性，但内部已有 `LlmToolLoopRunner` |
| **无多轮对话** | 无 | dayu-agent 支持 interactive 多轮对话, fund-checklist 当前无用户侧多轮问答 |
| **无会话记忆** | 无 | dayu-agent 有两层记忆模型, fund-checklist 当前无会话记忆 |
| **无上下文治理** | 无 | dayu-agent 有完整预算治理, fund-checklist 当前无上下文预算管理 |
| **无流式输出** | 无 | dayu-agent 支持 SSE 流式, fund-checklist 当前无用户侧流式输出 |
| **无联网搜索** | 无 | dayu-agent 支持实时数据获取, fund-checklist 当前仅限本地 PDF 分析 |
| **无问题理解能力** | 有差异 | 当前主链路不依赖 LLM 意图理解，更偏受控工具调用与结构化抽取 |
| **模型支持有限** | 有差异 | dayu-agent 覆盖更多 provider；fund-checklist 当前只需 DeepSeek/Mimo |

### 9.2 报告生成候选差距（对照观察）

| 差距 | 存在性 | 说明 |
|------|--------|------|
| **无行业差异化** | 无 | dayu-agent 有 preferred_lens 行业视角, fund-checklist 当前无行业区分模板 |
| **无公司特异变量** | 无 | dayu-agent 支持条件项渲染, fund-checklist 当前无公司特异性变量驱动渲染 |
| **定性分析模板弱** | 有差异 | dayu-agent 三层模板系统；fund-checklist 当前更依赖 ChapterContract + 数据表格 + 审计约束 |
| **无渲染输出** | 无 | dayu-agent 支持 HTML/PDF/Word, fund-checklist 当前仅 Markdown |

### 9.3 fund-checklist 优势

| 优势 | 说明 |
|------|------|
| **数据表格 100% 准确** | 程序生成, 不经过 LLM, 无幻觉风险 |
| **幻觉检测** | `contains_non_year_numbers()` 检测 LLM 输出中的非年份数字 |
| **Citation 严格校验** | 四层校验: evidence check → citation presence → citation identity → key fact evidence |
| **document_id 强绑定** | 防止 LLM 跨文档访问, 更安全 |
| **确定性信号评分** | 6 指标, 135→100 归一化, 无 LLM 依赖 |
| **结构化字段抽取** | 费率/业绩/持仓/资产配置的确定性抽取 |
| **多年度聚合** | 3-5 年 bounded coverage |

---

## 十、候选观察方向

### 10.1 候选能力（需先裁决）

1. **实现 LLM 自主工具调用**: 将 `LlmToolLoopRunner` 暴露为用户问答入口
2. **实现多轮对话**: 添加 interactive mode, 支持会话恢复
3. **实现流式输出**: SSE 流式返回, 提升用户体验

### 10.2 候选能力（需先裁决）

1. **实现会话记忆**: 两层记忆模型 (Pinned State + 单总池)
2. **实现上下文预算治理**: 软上限压缩 + 硬上限重试
3. **添加联网搜索**: 集成 Tavily/Serper, 获取实时市场数据
4. **增强问题理解**: query 改写、意图识别

### 10.3 候选能力（需先裁决）

1. **行业差异化模板**: 按行业/公司动态组装报告内容
2. **渲染输出**: HTML/PDF/Word 多格式支持
3. **微信接入**: WeChat daemon, 支持后台服务
4. **更多数据源**: FMP、Yahoo Finance 等

---

## 十一、结论与使用边界

fund-checklist 的当前优势在于：关键数据表格由程序生成，主链路强调 citation / evidence 约束，报告生成环节对 LLM 数字 hallucination 有专门拦截机制。与 dayu-agent 相比，当前更明显的差异体现在：

1. **LLM 自主工具调用** vs 固定序列
2. **多轮对话 + 会话记忆** vs 单次问答
3. **流式输出** vs 同步返回
4. **联网搜索** vs 仅限本地 PDF

本报告可用于识别体验差距，但不能直接作为已裁决 roadmap。是否优先推进 LLM 自主工具调用、多轮对话或其他方向，必须先进入 `docs/implementation-control.md` 裁决，且不得违反 `AGENTS.md` 对 `ask/streaming/interactive` 的单独裁决要求。
