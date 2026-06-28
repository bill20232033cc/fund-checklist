# 刘成岗近两年 dayu agent 与 AI coding 开发路线图

生成日期：2026-06-14  
研究对象：雪球用户刘成岗（`https://xueqiu.com/u/6623660105`）近两年公开可检索发帖与回复  
时间口径：2024-06-14 至 2026-06-14；当前可稳定检索到的关键材料主要集中在 2026-01 至 2026-05。  

## 0. 证据口径

- 雪球正文页存在 WAF，直接抓取不稳定；本文采用公开搜索索引可见的原帖/讨论详情片段、作者 GitHub 仓库、`learning_notes` 原文作为证据。
- 本文不是对刘成岗全部发帖的穷尽审计，而是基于可验证材料重建其开发路线图。
- 下文所有“路线图”均是从发帖、回复、仓库文档中归纳出的工程演进，不代表作者正式发布过同名路线图。

## 1. 总结论

刘成岗这轮 dayu agent / AI coding 路线不是“先做一个通用聊天 Agent”，而是从投资分析任务的第一性原理倒推：

1. 投研输出要可核查、可追溯、去主观化，所以先设计公司分析模板。
2. 财报和公告太长、噪声太多，不能直接丢给 LLM，因此要做结构化数据读取和 LLM 可喂性治理。
3. LLM 本身无状态、上下文有限、容易大海捞针，所以需要 Host / Scene / Tool / Trace / Memory 等工程层约束。
4. AI coding 的价值不是替代架构设计，而是在明确边界、明确任务、明确验证标准之后，把实现和局部修复成本大幅压低。
5. 到 2026-04 开源 dayu-agent 时，路线已经从“网页 ChatGPT 工作流”升级为“买方财报分析 Agent 系统”，并继续向 Web UI、微信入口、A/H/美股财报、电话会议、presentation、retrieval / durable memory 等方向扩展。

一句话概括：先用模板把投研问题“定型”，再用工具链把原始披露“降噪”，最后用强工程化 Agent 把 LLM 限定在可审计的执行轨道内。

## 2. 时间线

| 时间 | 里程碑 | 核心判断 |
|---|---|---|
| 2026-01-18 | 发布“公司定性分析全貌梳理（纯网页 ChatGPT 工作流）” | 先不写复杂系统，先验证模板驱动的手动工作流：只基于《定性分析模板.md》逐章写作，目标是可核查、可追溯、去主观化。 |
| 2026-01-18 | 发布“公司全貌分析加工流程（端到端）” | 从“写作模板”推进到“加工流程”：从 ticker 或披露材料出发，解析年报 section，不同章节匹配不同 section，以控制 token 并减少大海捞针。 |
| 2026-01 下旬 | 两天写完 AsyncAgent 初版 | AI 辅助开发把 Agent engine 的初始实现压到两天，但后续计划是先用它做“公司全貌梳理写作工具”和“公司投资相关新闻摘要”，再开源。 |
| 2026-02-07 | AsyncAgent 增加财报读取能力 | 技术选型耗时显著：美股用 edgartools，港/A 股用 Docling，并继续比较 MinerU；关键目标是把 HTML/PDF 转成更适合 LLM 消费的 section / JSON / 表格。 |
| 2026-03-04 | 进入 LLM 可喂性工程阶段 | 发帖展示长 prompt：对 200 家公司 filings 做 CI 评估，按结构完整性、内容充足性、检索可用性、一致性与数据质量、噪声与完整性评分；修复必须无 regression。 |
| 2026-03 | 强化投资者使用 AI 的约束 | 明确 AI 是会犯错、会走捷径、上下文有限、偏好模式匹配的推理器；必须通过证据优先级、来源约束和自定义指令降低幻觉。 |
| 2026-04-16 | 总结 vibe coding 技术债 | AI 擅长快速打补丁和加胶水层；如果缺少 review、边界和重构纪律，会堆出冗余和技术债。 |
| 2026-04-20 | dayu-agent 开源发布 | 定位为“每个投资者的助理分析师”，把 AI 读财报从整份输入的大海捞针改为按图索骥，并强调数据置信度、可审计、可追踪。 |
| 2026-05 | AI coding 工具组合稳定 | Codex 负责总控和计划，Opus / Copilot 承担主力实施，MiMo 兼做替补实施和主力 code review，DeepSeek 作为替补 review。 |
| 2026-05 | 进入多 Agent 编排式开发 | “code is cheap” 的前提是先花时间做架构和总控计划，再让多个 coding / review agent 自动跑起来。 |

## 3. 公司分析模板的演进

### 3.1 第一阶段：纯网页 ChatGPT 工作流

最早可验证的路线不是从代码开始，而是从模板开始。`learning_notes/GUIDE.md` 中的目标是：只基于《定性分析模板.md》逐章写作，得到“可核查、可追溯、去主观化”的中文公司定性分析报告。

这个阶段有三个关键约束：

- 只基于模板逐章写，不让模型自由发挥。
- 美股优先上传财报/公告或检索 SEC EDGAR；港/A 股以用户上传材料为准，不默认联网检索。
- 缺少原始披露数字、口径或单位时，先输出缺口清单并停止，不估算、不用常识补齐。

这说明模板的真实作用不是“让输出更漂亮”，而是把 LLM 的自由度压缩到可验证的路径上。

### 3.2 第二阶段：端到端加工流程

“公司全貌分析加工流程（端到端）”进一步把模板工作流工程化：

- 输入从“手工复制材料”升级为股票代码或原始披露材料。
- 处理对象限定为一份年报（10-K 或 20-F）。
- 从年报解析出 section，再按章节匹配 section，使 token 消耗更可控。

这一步的核心是把“人读材料后喂给 AI”改成“系统先把材料整理成 AI 可消费的结构”。

### 3.3 第三阶段：证据优先级和正文约束

后续帖子继续强化两类约束：

- 证据优先级：公司财报 > 公司披露 > IR 资料（含财报电话会议）> 严肃财经媒体 > 其它。
- 正文事实和数字只能来自已知证据来源，不得把模型通识里的行业份额、增长率、排名等写入正文。

这本质上是在做投资分析版的“事实防火墙”：LLM 可以组织语言和推理，但不能随意引入未授权事实。

## 4. AsyncAgent 到 dayu-agent 的工程路线

### 4.1 AsyncAgent：先做通用执行原语

公开材料显示，AsyncAgent 初版两天完成，目标是支撑后续“公司全貌梳理写作工具”和“公司投资相关新闻摘要”。GitHub 当前 Engine 文档显示，`dayu/engine` 的责任已经收敛为通用执行原语层：

- `AsyncAgent`
- `AsyncRunner`
- `ToolExecutor` / `ToolRegistry`
- `StreamEvent`
- tool loop 与工具结果回填
- 上下文预算治理、截断续写、降级
- Tool Trace
- 取消原语 `CancellationToken`

这条线的关键边界是：Engine 不理解 ticker、写作、审计等业务语义；业务参数先由 Service 收敛成 Execution Contract，再交给 Host / Scene / Agent 执行。

### 4.2 财报读取：真正耗时的不是 Agent loop，而是数据喂法

2026-02-07 的讨论详情显示，给 AsyncAgent 添加财报读取能力“搞了十几天”，技术选型花了一半时间，另一半时间用于探索 AI 在复杂工程中写代码的方法。技术选择大致为：

- 美股：edgartools，处理 SEC filings，并从 XBRL 提取财务数据。
- 港股/A 股：Docling，因开源免费而采用，同时继续比较 MinerU 的 JSON 保真度。
- 输出：尽量以 section 级、JSON、表格等低噪声结构提供给 LLM。

作者在回复中估算，一个最基础的让 AI 分析财报的功能，全部写完至少约 2 万行代码，且不包括界面。这个判断解释了为什么 dayu-agent 的路线不是“LLM 直接读 PDF”：财报 PDF / HTML 噪声太多，直接读或 RAG 都容易遗漏线索或产生幻想。

### 4.3 LLM 可喂性：从“能读”到“读得稳定”

2026-03-04 的帖子展示了更工程化的阶段：对 200 家公司 filings 做 CI 评估，评分维度包括：

- 结构完整性
- 内容充足性
- 检索可用性
- 一致性与数据质量
- 噪声与完整性

任务约束也很明确：不能改财报工具 schema，不能硬编码公司规则，不能通过修改评分标准提高 CI 得分，修复后要重跑 CI 并确认无 regression。

这说明 dayu-agent 的路线已经从“能把材料交给模型”进入“系统性提高材料可消费质量”的阶段。

### 4.4 dayu-agent：开源时的系统定位

2026-04-20 开源发布时，dayu-agent 的定位是“每个投资者的助理分析师”。README 中明确说明，它面向买方财报分析，把 AI 读财报从整份财报的大海捞针改成按图索骥，并让数据有置信度、投资结论和报告可审计、可追踪。

当前公开 README 描述的能力包括：

- 财报数据管线：美股 / A 股 / 港股财报下载与上传。
- 投研问答：单次 prompt、多轮 interactive、微信提问。
- 买方分析报告写作。
- Markdown 报告渲染为 HTML / PDF / Word。

仍在扩展的方向包括 GUI、Web UI 完善、微信更多功能、财报电话会议记录转录与信息提取、财报 presentation 信息提取、Anthropic 原生 API、Durable memory / Retrieval layer、FMP 工具等。

## 5. AI coding 的优势

### 5.1 初始实现速度极快

AsyncAgent 初版两天完成，是 AI coding 在清晰目标下的典型优势：当模块边界、接口形态、任务目标足够明确时，模型可以快速产出大量样板、工具、状态机和测试骨架。

### 5.2 架构确定后，代码变便宜

2026-05 的“code is cheap”帖把路线说得更清楚：先花三天和 Codex 讨论并确定架构，再精心规划总控计划，然后让多个 Agent 分工执行：

- Codex Agent 总控。
- Codex / Opus Claude Agent 编码和修 bug。
- MiMo 和 DeepSeek Agent 做 review。

这里的“cheap”不是说代码没有成本，而是说在架构和验收标准已经收敛后，代码生产和局部修复的边际成本显著下降。

### 5.3 编程 Agent 适合执行“可执行性强”的长任务

2026-03-04 的 LLM 可喂性 prompt 虽然很长，但任务结构清晰：

- 背景、目标、成功标准、命令、并发规则、禁止事项都明确。
- 每一步都有产物：报告文件、下载结果、基线分、问题分类、修复、验证。
- 验收条件是可运行的 CI 和 regression 对比。

作者回复里指出，这类 prompt 不到 2K 且“可执行性很强”；真正不够的是任务复杂但 prompt 模糊，需要 AI 自己补上下文。

### 5.4 多模型分工能放大单个模型能力

2026-05 的工具组合显示，作者没有把某个模型当万能模型，而是按角色分工：

- Codex Pro：总控和计划。
- GitHub Copilot Pro+ / Opus：主力按计划实施。
- MiMo：替补实施和主力 code review。
- DeepSeek：替补 code review。

这和 dayu-agent 的架构思路一致：不要让一个模型独自理解全部上下文，而是用流程和角色分工降低单点失误。

## 6. AI coding 的踩坑

### 6.1 模型无状态，上下文窗口很小

作者反复强调，大模型本身是无状态的，历史对话依赖编程 Agent 的能力；上下文窗口通常也有限。结论是：不要指望模型自然理解整个复杂工程，尤其不要让它在大项目里大海捞针。

对开发路线的影响：

- 必须写 AGENTS.md、design.md、实施计划、验收条件。
- 必须显式约束模块边界和 forbidden changes。
- 大任务要切片，给模型明确的输入、输出和停止条件。

### 6.2 直接让 LLM 读 HTML/PDF 或 RAG 财报会幻想

在财报读取讨论中，作者的判断是：HTML/PDF 干扰信息太多，直接让 LLM 读，或者简单 RAG，都会产生严重幻想或遗漏。财报 PDF 还会有批注、脚注、跨页表格、排版噪声、字体和 OCR 等问题。

因此他选择自己做解析、去噪、section 化、JSON 化，再把结构化数据喂给模型。

### 6.3 Vibe coding 容易给人“廉价完成感”

作者把 vibe coding 分成两种：

- 坏路径：Vibe Coding -> 用提示词捏几个 Demo -> 误以为做产品很简单 -> 廉价完成感。
- 好路径：需求 -> 设计 -> 架构 -> Vibe Coding -> 再回到需求/设计/架构调整。

这说明 AI coding 不能跳过产品和工程设计；它只是在设计之后加速实现。

### 6.4 AI 擅长打补丁和加胶水层

2026-04-16 的讨论中，作者认可一个风险：vibe coding 如果不 review，会欠技术债，因为 AI 很擅长用补丁和胶水层满足眼前需求。人工 review 又很难覆盖大量生成代码；如果完全靠人工 review，不如只让模型做函数内局部修改。

可迁移教训：

- 对中大型项目，review 不能只看风格，要看边界、依赖方向、重复逻辑、隐式兼容层。
- 一旦有“屎山倾向”，要小范围重构，而不是继续补丁叠补丁。
- review Agent 也要有明确的 severity、证据和 stopping rule。

### 6.5 模型会偷懒，需求没写细的地方不会自动补齐

对 Opus 的阶段性评价是：效率提升很多，但经常偷懒；需求没有说细的地方不会自己补上；模块之间接口经常对不上，写完多数还需要调整。

这条经验对应的工程动作是：

- 不把“理解隐含需求”交给模型。
- Request DTO、schema、接口、错误语义、测试入口都要明确。
- 任务描述必须写清不能改什么、必须验证什么、什么情况停止。

## 7. 可迁移开发原则

1. 先模板，后 Agent。先证明人机工作流能产出可验证结果，再把流程自动化。
2. 先降噪，后推理。财报、公告、网页必须先变成低噪声、结构化、可引用的数据。
3. 先架构，后生成。AI coding 的高杠杆发生在架构和验收标准明确之后。
4. 让模型按图索骥，不要大海捞针。用 section、scene、tool、trace、contract 控制模型的搜索空间。
5. 证据优先级必须前置。模型可以总结，不能随意创造事实来源。
6. 所有生成都要有审计痕迹。报告、CI、trace、source anchor、review artifact 都是防止幻觉和技术债的工具。
7. 多 Agent 不是多写几份代码，而是分工：计划、实现、修复、review、验收各有边界。
8. 看到胶水层就重构。AI 写代码越快，越需要更早识别重复、补丁化和跨层依赖。

## 8. 对 fund-agent 的启示

结合本仓库当前边界，dayu-agent 的公开路线可迁移的是方法论，不应直接引入外部 dayu runtime：

- 可迁移：模板驱动、证据优先级、文档仓库接口、LLM 可喂性评分、trace / review / no-regression gate。
- 不应迁移：直接依赖外部 dayu-agent Host / Engine / tool loop，或让基金分析链路绕开本仓库既有 UI / Application / Runtime / Service / Engine / Capability 边界。
- 最小下一步：若要吸收刘成岗这一路线，优先做“基金年报 section 到 CHAPTER_CONTRACT 的低噪声映射”和“证据锚点可审计性评分”，而不是先接通一个更大的通用 Agent runtime。

## 9. 关键资料链接

- 雪球用户主页：<https://xueqiu.com/u/6623660105>
- 公司定性分析全貌梳理（纯网页 ChatGPT 工作流）：<https://xueqiu.com/6623660105/371546162>
- 公司全貌分析加工流程（端到端）：<https://xueqiu.com/6623660105/371546363>
- AsyncAgent 初版与后续开源计划：<https://xueqiu.com/6623660105/372852116>
- AsyncAgent 财报读取能力、edgartools / Docling / MinerU、上下文与复杂工程提醒：<https://xueqiu.com/6623660105/372852116/396317911>
- Vibe Coding 后期长任务与 LLM 可喂性 CI：<https://xueqiu.com/6623660105/377549111/398241284>
- 两种 Vibe Coding：<https://xueqiu.com/6623660105/377549111>
- 一个严肃的投资者怎么用好 AI：<https://xueqiu.com/6623660105/380097642>
- 证据优先级讨论：<https://xueqiu.com/6623660105/380310515>
- 正文事实和数字来源约束：<https://xueqiu.com/6623660105/380346463>
- Opus / vibe coding 阶段性评价：<https://xueqiu.com/6623660105/382740159>
- AI 好用/不好用的判断框架：<https://xueqiu.com/6623660105/385851739>
- Vibe coding 技术债与 glue layer 讨论：<https://xueqiu.com/6623660105/384120853/403031404>
- dayu-agent 开源发布：<https://xueqiu.com/6623660105/384467237>
- AI coding 工具组合：<https://xueqiu.com/6623660105/388016672>
- Claude Code Agent View / 多子 Agent：<https://xueqiu.com/6623660105/388357929>
- code is cheap / 多 Agent 总控与 review：<https://xueqiu.com/6623660105/389026719>
- dayu-agent GitHub：<https://github.com/noho/dayu-agent>
- dayu-agent 用户手册：<https://github.com/noho/dayu-agent/blob/main/README.md>
- dayu-agent Engine 手册：<https://github.com/noho/dayu-agent/blob/main/dayu/engine/README.md>
- dayu-agent 总览开发手册：<https://github.com/noho/dayu-agent/blob/main/dayu/README.md>
- learning_notes GUIDE：<https://github.com/noho/learning_notes/blob/main/GUIDE.md>
