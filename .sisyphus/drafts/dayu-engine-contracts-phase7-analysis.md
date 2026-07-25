# Dayu Engine & Contracts → Phase 7 差距分析与补救方案

> 分析时间：2026-07-25  
> 对比基准：Dayu `engine/` + `contracts/` + `host/` vs Phase 7 的 16 Slice  
> 原则：**不追求 100% 复刻，只补真正有风险的差距**

---

## 概述

Phase 7 在高层次设计上已经对齐 Dayu 的核心链路（Scene → Fragment → Context Slot → Prompt Contribution；ContextBudget + EpisodeSummary + 三层记忆）。以下 8 项差距是在深入对比 Dayu 源码后发现的具体实现层面的缺失，按影响程度分为 Engine 层（🔴）、Contracts 层（🟡）、Memory 层（🟢）。

---

## 🔴 Engine 层差距（影响工具执行可靠性和上下文治理完整性）

### 差距 1：工具结果无统一 `ok/error/truncation` 信封

**Dayu 做了什么**（`engine/tool_result.py`）：
```python
# 成功
build_success(value, truncation=None, meta=None)
# → {"ok": True, "value": <any>, "truncation": {...}|None, "meta": {...}|None}

# 失败  
build_error(code="not_found", message="...", hint="...", meta=None)
# → {"ok": False, "error": "<code>", "message": "...", "hint": "...", "meta": {...}|None}

# LLM 投射（只给 LLM 看的部分）
project_for_llm(result)
# ok=True, dict:  {**value, "truncation": ..., "tool_calls_remaining": N}
# ok=False:       {"error": "<code>", "message": "...", "hint": "..."}
```

**我们当前的问题**：
- 工具直接返回 `str` 或 `dict`，无统一信封。LLM 无法从返回值结构区分"工具成功但结果为空"与"工具执行失败"
- 如 `search_document` 无命中时返回空 tuple → Agent 层转 `not_found`，这个二次判断容易遗漏或误判
- 截断信息（如 `_MAX_TABLE_ROWS` 限制）目前以注释形式追加到文本末尾，不是结构化元数据，LLM 不一定注意到

**不补的风险**：
- 中等。当前 7 个 reading tools 已有 `ToolFailure` 分类，但工具成功侧的截断标记非结构化，后续加 `fetch_more` 续读时需要结构化 truncation 字段

**补救方案**：在 Phase 7 的 `7A`（Session 数据模型）或 `7M`（Context Budget）的 preparation 中新增一个轻量信封

```python
# fund_agent/agent/tool_result.py (新增，~60 行)

@dataclass(frozen=True)
class ToolResult:
    ok: bool
    value: Any = None          # 成功时的结构化数据
    error_code: str | None = None  # 失败时的稳定 code
    error_message: str = ""
    truncation: dict | None = None  # {"strategy": "text_chars", "kept": 4000, "total": 12000}
    meta: dict = field(default_factory=dict)

    def project_for_llm(self) -> dict:
        """生成 LLM-facing 的投影，隐藏内部字段"""
        if self.ok:
            result = {"content": self.value} if isinstance(self.value, str) else dict(self.value)
            if self.truncation:
                result["truncation"] = self.truncation
            return result
        return {"error": self.error_code, "message": self.error_message}
```

实施成本：~60 行代码，不影响现有工具 API（信封是可选的包装层）  
建议放入：7A（Session 模型）的 preparation 阶段，作为基础设施供后续 Slice 使用

---

### 差距 2：无 TruncationManager 续读（fetch_more）机制

**Dayu 做了什么**（`engine/truncation_manager.py`）：
- 四种截断策略：`text_chars`、`text_lines`、`list_items`、`binary_bytes`
- 游标续读：工具结果被截断时生成 `cursor` + `scope_token`，LLM 可调用 `fetch_more(cursor, scope_token)` 获取下一页
- 游标 TTL 300 秒，单次消费后失效，双条件 CAS（scope_token + cursor 存在性）

**我们当前的问题**：
- 大表格（如持仓 Top 50）被硬截断到 `_MAX_TABLE_ROWS`（如 20 行），LLM 无法获取剩余数据
- 截断信息以文本注释形式追加（`... 共 50 行，已显示 20 行`），不是结构化元数据
- 如果 LLM 需要完整数据（如"列出基金持有最多的 3 只股票"需要 Top 50 排序），会因信息不全而回答错误

**不补的风险**：
- 低（Phase 7 范围）。`interactive` 模式下用户通常不会要求读取超长表格全文。但在 Phase 8（报告质量修复）中，`regenerate` 场景需要精准数据时可能触发

**补救方案**：Phase 7M（Context Budget）中附带最小实现

```python
# fund_agent/agent/truncation_manager.py (新增，~80 行)

@dataclass 
class TruncationCursor:
    cursor_id: str          # 随机生成的游标 ID
    tool_name: str
    document_id: str
    strategy: str           # "table_rows" | "text_chars"
    offset: int             # 当前读取位置
    total: int              # 总数据量
    scope_token: str        # HMAC 防篡改
    created_at: float       # time.monotonic()
    ttl_seconds: float = 300

class TruncationManager:
    """内存游标注册表，自动清理过期游标"""
    def register(self, cursor: TruncationCursor) -> None: ...
    def consume(self, cursor_id: str, scope_token: str) -> TruncationCursor | None: ...
    def register_fetch_more_tool(self, tool_registry) -> None: ...
```

实施成本：~80 行 + 1 个新工具 `fetch_more`  
建议放入：7M 的末尾子任务（7M-2），不阻塞主 Context Budget 实现  
是否必须：否——Phase 7 可以先不做，等 Phase 8 有 `regenerate` 再补

---

### 差距 3：工具执行无 `ToolExecutionContext` 注入

**Dayu 做了什么**（`contracts/protocols.py`）：
```python
@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str | None
    iteration_id: str | None
    tool_call_id: str | None
    index_in_iteration: int
    timeout_seconds: float | None
    cancellation_token: CancellationToken | None
```

**我们当前的问题**：
- `FundDocumentToolService` 的工具方法只接收业务参数（`document_id`, `section_ref` 等），不接收执行上下文
- `ToolTraceEntry` 的 `tool_call_id` 在 `LlmToolLoopRunner` 层生成，但工具本身不知道自己属于哪个 run / iteration
- 取消信号无法传递给执行中的工具（如 `read_section` 读取大章节时无法中断）

**不补的风险**：
- 低。当前工具都是同步、短耗时操作（< 1 秒），不需要取消和超时。但如果后续加入联网搜索或大文件处理，会需要

**补救方案**：在 `LlmToolLoopRunner` 中构造 context，通过 `FundDocumentToolService` 的可选参数传入

```python
# 修改 fund_agent/agent/llm_tool_loop.py 中的 execute_tool 方法
# 不改变现有 FundDocumentToolService 的公开签名

@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str
    iteration_id: str  
    tool_call_id: str
    index_in_iteration: int = 0

# 在 LlmToolLoopRunner 执行工具时
context = ToolExecutionContext(
    run_id=self._run_id,
    iteration_id=f"iter_{self._iteration_count:03d}",
    tool_call_id=tool_call.id,
    index_in_iteration=idx,
)
# 通过 tool_trace 记录，工具本身暂不消费
self._tool_trace.record(tool_call, context)
```

实施成本：~20 行，不改工具签名，只用于 trace 增强  
建议放入：7M 或 7J（integration）的 preparation  
是否必须：**建议做**。不增加工具复杂度，但让 tool trace 从"事后拼凑"变成"执行时明确记录"

---

## 🟡 Contracts 层差距（影响跨层边界清晰度和可扩展性）

### 差距 4：Service → Host 无显式契约对象

**Dayu 做了什么**（`contracts/agent_execution.py`）：
```python
@dataclass(frozen=True)
class ExecutionContract:
    service_name: str
    scene_name: str
    host_policy: ExecutionHostPolicy       # timeout_ms, resumable
    preparation_spec: ScenePreparationSpec  # selected_toolsets, prompt_contributions
    message_inputs: ExecutionMessageInputs  # user_message, replay_from
    accepted_execution_spec: AcceptedExecutionSpec  # model, runtime, tools, infra
```

**我们当前的问题**：
- `ChatService.chat_turn(request: ChatTurnRequest)` → 直接调用 `Host.run_chat_turn(session, user_text, document_id)` 
- 参数以独立字段方式传递，未来新增参数（`model_override`、`tool_timeout`、`disable_tools`）需要改多处函数签名
- Service 和 Host 之间没有清晰的"已接受的执行决策"边界

**不补的风险**：
- 中等。当前只有 2 个 scene（ask + interactive），参数简单。但 Phase 7 新增 `max_iterations`、`model_name`、`temperature` 等配置后，参数散落会增加维护成本

**补救方案**：引入轻量 `ChatTurnContract` 作为 Service → Host 的单一契约

```python
# fund_agent/service/chat_contract.py (新增，~30 行)

@dataclass(frozen=True)
class ChatTurnContract:
    """Service → Host 的单轮对话执行契约"""
    scene: str                          # "ask" | "interactive"
    session_id: str
    user_text: str
    document_id: str | None = None      # None 时使用 session 的 active_document_id
    model_name: str | None = None       # None 时使用 scene 默认
    max_iterations: int | None = None   # None 时使用 scene 默认
    timeout_ms: int | None = None
    disable_tools: bool = False         # 用于 regenerate 等纯文本场景

# Host 接口从
#   run_chat_turn(session, user_text, document_id) 
# 改为
#   run_chat_turn(contract: ChatTurnContract)
```

实施成本：~30 行新文件 + 调整 `ChatService` 和 `MinimalHost` 的调用方式（~20 行改动）  
建议放入：**7J（Integration）**—在串联 chat_turn → Host → CLI 全链路时自然引入  
是否必须：**建议做**。Phase 7 是引入这个契约的最佳时机，因为此时正在建立 Service → Host 的新路径

---

### 差距 5：SceneConfig 缺失 model/runtime 配置

**Dayu 做了什么**（`config/prompts/manifests/interactive.json`）：
```json
{
  "model": {
    "default_name": "mimo-v2.5-pro-thinking-plan",
    "allowed_names": ["deepseek-v4-pro-thinking", ...],
    "temperature_profile": "interactive"
  },
  "runtime": {
    "agent": { "max_iterations": 20 },
    "runner": { "tool_timeout_seconds": 90.0 }
  }
}
```

**我们当前的问题**：
- 模型名通过环境变量 `DEEPSEEK_MODEL` 全局配置，不区分 scene
- `max_iterations` 硬编码在 `LlmToolLoopRunner` 中
- temperature 在 `DeepSeekLlmClient` 中写死
- 无法做到：`ask` 用快的模型（deepseek-v4-flash），`interactive` 用思考模型（deepseek-v4-pro-thinking）

**不补的风险**：
- 低（Phase 7 范围）。当前 DeepSeek 只有一个模型在使用。但 Phase 7 的 SceneConfig 设计已经留了扩展点，不在此刻做会很可惜

**补救方案**：在 Phase 7 的 `7F`（Scene Config）中直接做，不额外增加 Slice

```python
# fund_agent/service/scene_config.py 的扩展

@dataclass(frozen=True)
class SceneModelSpec:
    default_name: str = "deepseek-v4-pro"  # 默认从环境变量读取
    temperature: float = 0.7

@dataclass(frozen=True)  
class SceneRuntimeSpec:
    max_iterations: int = 12
    tool_timeout_seconds: float = 60.0

@dataclass(frozen=True)
class SceneConfig:
    scene: str
    description: str
    fragments: tuple[FragmentSpec, ...]
    context_slots: tuple[str, ...]
    model: SceneModelSpec = field(default_factory=SceneModelSpec)       # 新增
    runtime: SceneRuntimeSpec = field(default_factory=SceneRuntimeSpec) # 新增

# 两个 scene 的差异
ASK_SCENE_CONFIG = SceneConfig(
    scene="ask",
    model=SceneModelSpec(default_name="deepseek-v4-flash", temperature=0.3),
    runtime=SceneRuntimeSpec(max_iterations=8),
    ...
)
INTERACTIVE_SCENE_CONFIG = SceneConfig(
    scene="interactive", 
    model=SceneModelSpec(default_name="deepseek-v4-pro-thinking", temperature=0.7),
    runtime=SceneRuntimeSpec(max_iterations=20),
    ...
)
```

实施成本：~30 行改动，在 7F 范围内  
是否必须：**建议做**。7F 已经定义了 SceneConfig，顺便加入 model/runtime 字段是 30 行的事，不做的话后续需要单独开 Slice 重构

---

### 差距 6：工具集合无 scene-level 过滤

**Dayu 做了什么**：
```json
// scene manifest 中声明工具选择策略
"tool_selection": {
  "mode": "select",
  "tool_tags_any": ["fins", "ingestion"]  // interactive 有 web 搜索
}
// prompt scene 不声明 web，所以 LLM 看不到 search_web 工具
```

**我们当前的问题**：
- 所有 6 个 reading tools + `aggregate_multi_year` 对所有 scene 可见
- `ask` 和 `interactive` 共享同一个工具列表
- 后续如果增加 `fetch_more`（续读）或 `search_web`（联网搜索），无法按 scene 控制可见性
- `ask` 单轮不需要 `aggregate_multi_year`，但 LLM 可能误调用

**不补的风险**：
- 低。当前工具集合固定且安全。但 Phase 7 引入了 `interactive` scene，后续 Phase 9 可能增加联网搜索——届时如果没有工具过滤，`ask` 也会获得联网能力，违反安全约束

**补救方案**：SceneConfig 增加 `allowed_tools` 字段

```python
# fund_agent/service/scene_config.py

@dataclass(frozen=True)
class SceneConfig:
    ...
    allowed_tools: tuple[str, ...] = ()  # 空 = 全部允许（向后兼容）

ASK_SCENE_CONFIG = SceneConfig(
    ...,
    allowed_tools=(
        "search_document", "read_section", "list_tables", 
        "read_table", "get_excerpt",
    )
)
INTERACTIVE_SCENE_CONFIG = SceneConfig(
    ...,
    allowed_tools=(
        "search_document", "read_section", "list_tables",
        "read_table", "get_excerpt", "aggregate_multi_year_annual_performance",
    )
)
```

在 `LlmToolLoopRunner` 中：根据 `scene_config.allowed_tools` 过滤 `tool_registry.get_schemas()` 再发送给 LLM

实施成本：~15 行改动 + ~5 行在 runner 中  
是否必须：**建议做**。安全收益大于实现成本。Phase 7 不做的话，后续加新工具时会有安全隐患

---

## 🟢 Memory 层差距（影响长对话质量和上下文保真度）

### 差距 7：Episode Summary 不生成 PinnedState 补丁

**Dayu 做了什么**（`conversation_memory.py`）：
```python
@dataclass(frozen=True)
class ConversationCompactionResult:
    episode_summary: ConversationEpisodeSummary
    pinned_state_patch: ConversationPinnedStatePatch  # 增量补丁！

@dataclass(frozen=True)  
class ConversationPinnedStatePatch:
    current_goal: str | None = None         # None = 不修改
    confirmed_subjects: tuple[str, ...] | None = None
    user_constraints: tuple[str, ...] | None = None
    open_questions: tuple[str, ...] | None = None

# 应用补丁
new_pinned = patch.apply_to(old_pinned)
```

**我们当前的问题**：
- Phase 7 的 Episode Summary（7L）只生成摘要文本，不回写 PinnedState
- 压缩后，LLM 失去对"用户当前在调查什么"的语义记忆，只能依赖结构性 PinnedState（fund_code, active_year）
- 场景：用户问了 10 轮关于"2024 年持仓变化"的问题 → 压缩后 LLM 只看到 `active_year=2024`，丢失了"用户关注持仓变化"这一语义上下文

**不补的风险**：
- 中等。会影响长对话（15+ 轮）的连贯性。用户需要反复重申关注点

**补救方案**：在 7L 的 Episode Summary 压缩 prompt 中增加输出 pinned_state_patch

```python
# fund_agent/host/minimal_host.py 中的 compaction LLM prompt 增加

COMPACTION_PROMPT = """
...
请输出严格 JSON：
{
  "episode_summary": {
    "title": "...",
    "goal": "...", 
    "confirmed_facts": [...],
    "open_questions": [...]
  },
  "pinned_state_patch": {
    "current_goal": "用户当前关注的问题是什么？如果与之前相同则省略此字段",
    "confirmed_facts": ["已确认的事实"],
    "open_questions": ["待解决的问题"]
  }
}
"""
```

并在 `Session` 模型中增加 `apply_pinned_state_patch(patch)` 方法

实施成本：~30 行改动（修改 compaction prompt + Session 模型增加 apply 方法）  
建议放入：7L 内部，不额外增加 Slice  
是否必须：**建议做**。7L 已经在做 compaction LLM 调用，让 LLM 多输出一个 `pinned_state_patch` 字段是零额外成本的改进

---

### 差距 8：WorkingMemory 无单轮溢出兜底

**Dayu 做了什么**（`conversation_memory.py`）：
```python
class DefaultWorkingMemoryPolicy:
    def _render_forced_turns(self, forced_turns, max_context_tokens, actual_forced_count):
        # 兜底阈值：max_context_tokens / max(2, actual_forced_count + 1)
        overflow_threshold = max_context_tokens // max(2, actual_forced_count + 1)
        for turn in forced_turns:
            full_view = _build_full_working_turn_view(turn)
            if _estimate_working_turn_view_tokens(full_view) <= overflow_threshold:
                rendered.append(full_view)  # 完整保留
            else:
                # 单轮过大 → 退化为最小保真视图（保留 user_text + 截断 assistant_text）
                rendered.append(_build_minimum_preserved_turn_view(turn, token_budget=overflow_threshold))
```

**我们当前的问题**：
- Phase 7 强制保留最近 3 轮，"不占 budget"。但如果一轮回复包含超长表格（如持仓 Top 50），这 3 轮可能占满整个上下文窗口
- 没有 `overflow_threshold` 机制：当单轮 token 量超过 `max_context / divisor` 时，应该截断该轮而非直接撑爆窗口

**不补的风险**：
- 低。基金年报问答的典型回复长度在 500-2000 字，罕见单轮超 8000 token。但如果用户问"列出全部持仓"且 LLM 将 50 行表格全部放进回答，可能触发

**补救方案**：在 7M（Context Budget）的 `build_messages` 逻辑中增加阈值检查

```python
# fund_agent/agent/context_budget.py 或 host/minimal_host.py 中

def _build_working_memory_turns(
    turns: list[Turn], 
    max_context_tokens: int,
    forced_count: int = 3,
) -> list[dict]:
    """构建 working memory，对超大单轮降级"""
    if max_context_tokens > 0:
        overflow_threshold = max(2000, max_context_tokens // max(2, forced_count + 1))
    else:
        overflow_threshold = 8000  # 兜底
    
    messages = []
    for turn in turns[-forced_count:]:
        turn_tokens = _estimate_tokens(turn.content)
        if turn_tokens <= overflow_threshold:
            messages.append({"role": turn.role, "content": turn.content})
        else:
            # 降级：保留前 overflow_threshold 估算 token 的内容
            truncated = _truncate_to_token_budget(turn.content, overflow_threshold)
            messages.append({"role": turn.role, "content": truncated})
    return messages
```

实施成本：~25 行，在 7M 范围内  
是否必须：**建议做**。防御性编程，实现成本极低，但能防止极端边界情况

---

## 差距汇总与行动建议

| # | 差距 | 严重度 | 建议放入 | 代码量 | 是否必须 |
|---|------|--------|---------|--------|---------|
| 1 | 工具结果无统一信封 | 🔴 中 | 7A preparation | ~60行 | 推荐 |
| 2 | 无 fetch_more 续读 | 🔴 低 | 7M-2（可选） | ~80行 | 推迟到 Phase 8 |
| 3 | 无 ToolExecutionContext | 🔴 低 | 7M preparation | ~20行 | **建议做** |
| 4 | Service→Host 无契约对象 | 🟡 中 | 7J Integration | ~50行 | **建议做** |
| 5 | SceneConfig 缺 model/runtime | 🟡 低 | 7F 范围内 | ~30行 | **建议做** |
| 6 | 工具无 scene 级过滤 | 🟡 低 | 7F 范围内 | ~20行 | **建议做** |
| 7 | Episode 不生成 PinnedState 补丁 | 🟢 中 | 7L 范围内 | ~30行 | **建议做** |
| 8 | WorkingMemory 无单轮溢出兜底 | 🟢 低 | 7M 范围内 | ~25行 | 推荐 |

**总代码增量**：~315 行（全部做）/ ~175 行（仅做"建议做"的 5 项）  
**不增加新 Slice**：所有改动都在现有 Slice 范围内  
**不影响 Phase 7 总工期**：每个差距的改动量都 < 100 行，可以在对应 Slice 实现时自然纳入

---

## 关于"不对齐也无妨"的说明

以下 Dayu 概念**不需要在 Phase 7 对齐**，原因明确：

| Dayu 概念 | 不做的理由 |
|-----------|-----------|
| `ExecutionContract` + `AcceptedExecutionSpec` 完整形式化 | 单用户 CLI，不需要把 model/runtime/tools/infra 拆成四层 spec |
| `SessionRecord` 用 SQLite | filesystem JSON 与现有 catalog 一致，零新依赖 |
| `ReplyOutbox` + `PendingTurn` + `ResumeLease` | 多客户端 + 异步回复才需要，CLI 用 `--label` 恢复即可 |
| `RunRecord` 7 态状态机 | 我们的 run 是同步的，不需要 CREATED→QUEUED→RUNNING 等中间态 |
| `DurableMemoryStore` + `RetrievalIndex` | Dayu 自己也没完整实现 |
| 14 个 Scene 类型 | 基金分析只需要 ask + interactive，不需要 write/audit/repair 等独立 scene |
| `CancellationToken` 两层语义 | 同步 Host 不需要取消传播链路，timeout 足够 |
| `reasoning_protocol.py` (vendor 适配) | 只有 DeepSeek 一个 provider，不需要 Gemini thought tags |
