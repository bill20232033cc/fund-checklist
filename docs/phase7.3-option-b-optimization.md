# Phase 7.3 方案 B 优化设计 v2

> 设计时间：2026-07-28
> DS Review 状态：有条件通过（二审）
> 关联文档：docs/agent-evolution-design.md §8.2

## 设计原则

1. 不改动 `LlmClientProtocol` 签名（方案 B 核心约束）
2. 最小侵入：只改 `chat_service.py` + `session_models.py` + `scene_config.py`
3. 历史轮次以 "enriched summary" 形式注入 system prompt，不注入 raw tool results

## 失败模式与缓解方案

### FM1：Context Window 溢出

**方案**：`_build_history_contribution()` 加 token 上限（默认 2000），从最近轮次向前累积截断。
- `max_tokens` 作为 `ChatService.__init__` 参数，可配置

### FM2：LLM 分不清历史/当前

**方案**：结构化格式 + 分隔标记。

```
## 历史对话

[用户提问]: 004393 最大回撤是多少？
[助手回答]: 根据年报数据，004393 最大回撤为 -12.3%。
[引用文档]: 004393-2024-annual_report-abc123
[工具调用]: search_documents(004393, 最大回撤) → 成功

---
以上是历史对话。请忽略历史中的纯文本格式，以 JSON 格式回答当前用户问题。
```

### FM3：跨轮 Tool Results 可见性（B1 方案）

**问题**：`agent_result.answer` 是聚合回答，无法反推单工具结果。`ToolTraceEntry` 只有 `tool_name/arguments/result_kind/failure_code`。

**方案**：`ToolCallSummary.result_summary` 仅从 `result_kind + failure_code` 推导。

```python
@dataclass(frozen=True)
class ToolCallSummary:
    """工具调用摘要。"""
    tool_name: str
    arguments_display: str   # 仅用于展示的关键参数拼接
    success: bool            # result_kind == "success"
    failure_code: str | None # 失败分类，成功时为 None

    @property
    def result_summary(self) -> str:
        """从 success + failure_code 推导摘要。"""
        if self.success:
            return "成功"
        return f"失败: {self.failure_code}" if self.failure_code else "失败"
```

### FM4：Scene Config Slot 适配

**方案**：`INTERACTIVE_SCENE_CONFIG.context_slots` 新增 `"history"`。

### FM5：Compaction 交互

**方案**：`Session.truncate_turns(keep_last)` + compaction 后调用。

```python
# session_models.py Session 类
def truncate_turns(self, keep_last: int) -> Session:
    """保留最近 keep_last 个 turns，删除更早的。"""
    if len(self.turns) <= keep_last:
        return self
    return Session(
        session_id=self.session_id,
        label=self.label,
        status=self.status,
        turns=self.turns[-keep_last:],
        pinned_state=self.pinned_state,
        episode_summaries=self.episode_summaries,
        created_at=self.created_at,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
```

### FM6：Temperature

**方案**：不改 temperature 取值逻辑，但修复 5 处 temperature 未透传的 bug（见 §Bug 修复：Temperature 透传 + §新分析审核 > 审核项 2）。

### FM10：document_id 严格相等 → 前缀匹配

**问题**：`_invoke_tool_call()` 对 `call.document_id != expected_document_id` 做严格相等校验，但 LLM 可能在 tool call 中传递变体 ID（如多出后缀），导致合法工具调用被拒绝。

**方案**：新增 `_normalize_document_id(call_doc_id, expected_doc_id)`：
1. 完全匹配 → 直接通过
2. `fund_code-year-report_type` 前缀一致 → 接受并使用 `expected_doc_id`，记录 warning
3. 前缀不匹配 → 拒绝

### FM7：空 tool_trace

**方案**：`_format_turn_for_history()` 中 `tool_calls` 为空时跳过工具行。

### FM8：Token 估算

**方案**：中英文混合估算函数。

```python
def _estimate_token_count(text: str) -> int:
    """粗估 token 数。中文约 1.5 token/字，英文约 0.75 token/word。"""
    cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_len = len(text) - cn_chars
    return int(cn_chars * 1.5 + other_len / 4)
```

### FM9：History 与 JSON 指令冲突

**方案**：分隔标记明确引导 LLM 使用 JSON 格式。

## Bug 修复：document_id 前缀匹配

### 背景

`llm_tool_loop.py:584-589` 中 `_invoke_tool_call()` 对 `call.document_id != expected_document_id` 做严格相等校验。LLM 可能在 tool call 中传递变体 document_id（如 LLM 自行拼接后缀），导致合法工具调用被误拒。

### 方案

在 `_invoke_tool_call()` 中新增 `_normalize_document_id(call_doc_id, expected_doc_id)` 静态方法：

```python
@staticmethod
def _normalize_document_id(call_doc_id: str, expected_doc_id: str) -> str | None:
    """规范化 document_id，支持前缀匹配。
    
    返回:
        - expected_doc_id: 匹配成功（精确或前缀）
        - None: 不匹配，应拒绝
    """
    if call_doc_id == expected_doc_id:
        return expected_doc_id
    # 前缀格式: fund_code-year-report_type
    prefix = "-".join(expected_doc_id.split("-")[:3])
    if call_doc_id.startswith(prefix):
        logger.warning(
            "document_id prefix match: call=%s, expected=%s, using expected",
            call_doc_id, expected_doc_id,
        )
        return expected_doc_id
    return None
```

调用处替换：

```python
# Before:
if (
    tool_name is not ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE
    and call.document_id != expected_document_id
):
    ...

# After:
if (
    tool_name is not ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE
    and _normalize_document_id(call.document_id, expected_document_id) is None
):
    ...
```

### 影响范围

- 改动量：~15 行 + 单元测试
- 风险：低。前缀匹配仅在 `fund_code-year-report_type` 层级，不会跨基金/跨报告类型错误放行

## Bug 修复：Temperature 透传

### 背景

存在 3 处 temperature 未被正确透传的 bug，导致 LLM 调用使用错误的 temperature 值。

### Bug A：`next_step_stream()` 未传 temperature

**位置**：`deepseek_llm.py:364-372`

`next_step_stream()` 调用 `_request_payload()` 时遗漏 `temperature=self._temperature`，导致 `_request_payload()` 使用默认值 `temperature=0`，而 `next_step()`（line 290）已正确传入：

```python
# Before (next_step_stream, line 364-372):
payload=_request_payload(
    document_id=document_id,
    query=query,
    tool_results=tool_results,
    model=...,
    stream=True,
    system_prompt=self._system_prompt,
    remaining_budget=remaining_budget,
    # BUG: 缺 temperature=self._temperature
),

# After: 加 temperature=self._temperature
```

**影响**：stream 路径 temperature 始终为 0，与 `DeepSeekLlmClient.__init__` 传入的 `temperature` 参数不一致。

### Bug B：contract 分支 temperature 硬编码

**位置**：`chat_service.py:174-179`

contract 分支指定 `model_name` 时 temperature 硬编码为 `0.7`，不读取 scene config：

```python
# Before:
if contract is not None and contract.model_name:
    model_name = contract.model_name
elif hasattr(self._scene_config, "model"):
    model_name = self._scene_config.model.default_name
    temperature = self._scene_config.model.temperature

# After: 统一从 scene config 读取
temperature = 0.7  # 默认值
if contract is not None and contract.model_name:
    model_name = contract.model_name
if hasattr(self._scene_config, "model"):
    model_name = model_name or self._scene_config.model.default_name
    temperature = self._scene_config.model.temperature
```

**影响**：contract 模式下忽略 scene config 配置的 temperature。

### Bug C：compaction 路径未传 temperature

**位置**：`chat_service.py:307`

compaction 路径 `DeepSeekLlmClient()` 无 temperature 参数，默认 0：

```python
# Before:
llm = DeepSeekLlmClient()

# After:
llm = DeepSeekLlmClient(temperature=self._scene_config.model.temperature)
```

**影响**：compaction 摘要生成 temperature 始终为 0，不受配置控制。

### 影响范围

- 改动量：3 处各 1 行，共 ~3 行
- 风险：极低。仅恢复 temperature 透传，不改变调用方的 temperature 取值逻辑

## 新分析审核（2026-07-28）

### 审核项 1：document_id 自动修正 vs 前缀匹配

新分析提出"自动修正"方案：当 `call.document_id != expected_document_id` 时直接静默替换为 `expected_document_id`，不做前缀检查。

**论证**：expected_document_id 来自 runner 参数，已经过 repository 校验；LLM 不应调用不同文档的工具（system prompt 已约束）；自动修正比失败更符合用户意图；line 370 直接返回 failure 不给 LLM 第二次机会。

**裁决：维持前缀匹配方案，不采纳自动修正。**

理由：
1. 前缀匹配已覆盖自动修正的核心收益（处理 variant ID），无需放弃安全边界
2. 自动修正的风险：若 LLM 对基金 A 发起工具调用但被静默替换为基金 B，工具返回的是基金 B 的数据，LLM 会将其当作基金 A 的数据呈现给用户，产生**静默错误答案**
3. 前缀匹配在同基金同报告类型内宽松（接受 variant），跨基金/跨报告类型严格执行 fail-closed，是正确的安全边界
4. 新分析指出的"不可恢复失败"问题恰恰是前缀匹配存在的理由 — 正是因为失败不可重试，才需要用前缀匹配减少误拒，而不是取消所有校验

**补充记录**：`_invoke_tool_call()` 对 document_id 不匹配直接 `return ToolFailure`，`run()` line 368-370 收到 ToolFailure 后直接 `return _failed_result(...)`，无重试。这进一步强调了前缀匹配的必要性：能匹配的尽量匹配放行，确实不匹配的理应终止。

### 审核项 2：Temperature 透传 — 新发现路径

新分析发现 2 个未覆盖路径，均绕过 `chat_service.chat_turn`，不受现有 Bug A/B/C 修复影响。

#### Bug D：`ask_question` → `_default_runner_factory` 未传 temperature

**位置**：`extraction.py:3878-3881`

`_default_runner_factory` 创建 `DeepSeekLlmClient()` 时未传 temperature，默认 0。`ask_question`（line 859）通过 `self._runner_factory(tool_service)` 创建 runner，全程不经过 `chat_service.chat_turn`，无法读取 `ASK_SCENE_CONFIG` 的 temperature=0.3。

**方案**：`_default_runner_factory` 新增 `temperature: float = 0` 参数，透传至 `DeepSeekLlmClient(temperature=temperature)`。`ExtractionService` 或 CLI 层注入正确的 temperature 值（ASK 场景为 0.3）。

```python
# Before:
def _default_runner_factory(tool_service: FundDocumentToolService) -> LlmToolLoopRunner:
    return LlmToolLoopRunner(tool_service=tool_service, llm_client=DeepSeekLlmClient())

# After:
def _default_runner_factory(
    tool_service: FundDocumentToolService,
    temperature: float = 0,
) -> LlmToolLoopRunner:
    return LlmToolLoopRunner(
        tool_service=tool_service,
        llm_client=DeepSeekLlmClient(temperature=temperature),
    )
```

**影响**：ask 场景 tool-loop LLM 调用使用 temperature=0 而非配置的 0.3。

#### Bug E：CLI `regenerate` 内部 `generate_text` 未传 temperature

**位置**：`main.py:1807-1811`（regenerate 命令内部的 chapter repair helper）

```python
analysis = llm_client.generate_text(
    system_prompt=LLM_CHAPTER_SYSTEM_PROMPT,
    user_prompt=user_prompt,
)
```

此 `llm_client` 来自 line 1845 的 `DeepSeekLlmClient()`（默认 temperature=0），用于 report re-coordination 和 chapter repair 的 `generate_text` 调用。这些调用属于 regenerate 流程，应使用 `REGENERATE_SCENE_CONFIG.model.temperature`（0.3）。

**方案**：创建 `DeepSeekLlmClient` 时传入 `temperature=0.3`，或从 `REGENERATE_SCENE_CONFIG` 读取。

```python
# Before:
llm_client = DeepSeekLlmClient()

# After:
from fund_agent.service.scene_config import REGENERATE_SCENE_CONFIG
llm_client = DeepSeekLlmClient(temperature=REGENERATE_SCENE_CONFIG.model.temperature)
```

**影响**：regenerate 流程中的 chapter repair `generate_text` 调用使用 temperature=0 而非配置的 0.3。

#### 非 Bug：CLI `generate` 命令

**位置**：`main.py:955-957`

```python
if getattr(args, "llm", False):
    llm_client = DeepSeekLlmClient()
```

此路径创建 `DeepSeekLlmClient()` 并传入 `ReportGenerationCoordinator`，仅用于 `generate_text()` 调用（`audit_pipeline.py:1346, 1541, 2336`）。报告生成是确定性任务，temperature=0 可能是有意为之。且无对应的 SceneConfig（不存在 "generate" scene）。**不视为 bug，不纳入修复范围。**

### 后续优化：generate_text temperature 按场景区分

`generate_text()` 当前默认 `temperature=0`，所有调用方均未显式传 temperature。分析调用方需求后，建议按场景区分而非统一设为固定值：

| 调用方 | 推荐温度 | 原因 |
|---|---|---|
| 审计评分（`audit_pipeline.py:1346`） | 0（默认） | 同一份报告每次评分必须一致 |
| 章节分析写作（`chapter_generator.py:1022`） | 0.3 | 需要语言多样性，但不能偏离数据太远 |
| 章节修复（`main.py:1807`, `audit_pipeline.py:1541`） | 0.3 | 需要一致性，但过低可能重复同一错误模式 |

**优先级**：后续 phase 处理（非 Bug，不纳入 Phase 7.3 范围）。

### Temperature 路径完整覆盖总览

| Bug | 路径 | 文件 | 状态 |
|-----|------|------|------|
| A | `next_step_stream()` 未传 temperature | `deepseek_llm.py` | 已有方案 |
| B | contract 分支硬编码 0.7 | `chat_service.py` | 已有方案 |
| C | compaction 路径未传 temperature | `chat_service.py` | 已有方案 |
| D | `ask_question` → `_default_runner_factory` | `extraction.py` | **新增** |
| E | CLI regenerate helper `generate_text` | `main.py` | **新增** |

## 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `session_models.py` | 新增 `ToolCallSummary` + `Session.truncate_turns()` | ~30 行 |
| `chat_service.py` | `_build_history_contribution()` + `_format_turn_for_history()` + `_estimate_token_count()` + `_build_contributions` 增加 history + `_run_compaction` 增加 truncate + `chat_turn()` 填充 `ToolCallSummary` + Bug B & C temperature 修复 | ~63 行 |
| `scene_config.py` | `context_slots` 新增 `"history"` | 1 行 |
| `deepseek_llm.py` | Bug A: `next_step_stream()` 加 `temperature=self._temperature` | 1 行 |
| `llm_tool_loop.py` | 新增 `_normalize_document_id()` + 调用处替换 | ~15 行 |
| `extraction.py` | Bug D: `_default_runner_factory` 新增 `temperature` 参数 | ~3 行 |
| `main.py` | Bug E: regenerate helper `DeepSeekLlmClient(temperature=0.3)` | 1 行 |
| 测试 | 单元测试（含 document_id 前缀匹配 + temperature 透传 A~E） | ~50 行 |
| **合计** | | **~164 行** |

## DS Review 二审裁决

**有条件通过**，实施前处理 3 项：

1. **Bug（必须修）**：`truncate_turns` 补充 `status=self.status, updated_at=...`（已修复）
2. **遗漏（必须补）**：`chat_turn()` 中 Turn 构造需显式填充 `ToolCallSummary`（已补充到改动清单）
3. **建议**：ContextBudget 与 history token 的交互留 TODO，Phase 8 处理
