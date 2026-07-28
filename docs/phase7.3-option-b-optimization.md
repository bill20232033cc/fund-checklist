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

**方案**：不改 temperature。观察后决定。

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

## 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `session_models.py` | 新增 `ToolCallSummary` + `Session.truncate_turns()` | ~30 行 |
| `chat_service.py` | `_build_history_contribution()` + `_format_turn_for_history()` + `_estimate_token_count()` + `_build_contributions` 增加 history + `_run_compaction` 增加 truncate + `chat_turn()` 填充 `ToolCallSummary` | ~60 行 |
| `scene_config.py` | `context_slots` 新增 `"history"` | 1 行 |
| 测试 | 单元测试 + e2e 测试 | ~30 行 |
| **合计** | | **~121 行** |

## DS Review 二审裁决

**有条件通过**，实施前处理 3 项：

1. **Bug（必须修）**：`truncate_turns` 补充 `status=self.status, updated_at=...`（已修复）
2. **遗漏（必须补）**：`chat_turn()` 中 Turn 构造需显式填充 `ToolCallSummary`（已补充到改动清单）
3. **建议**：ContextBudget 与 history token 的交互留 TODO，Phase 8 处理
