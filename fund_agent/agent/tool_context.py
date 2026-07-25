"""ToolExecutionContext — 工具调用上下文，注入每次 tool call 的 trace 信息。

参考 Dayu contracts/protocols.py 的 ToolExecutionContext（6 字段设计）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolExecutionContext:
    """单次工具调用的执行上下文。

    在 LlmToolLoopRunner 执行工具前构造，传给 ToolTraceEntry 或日志系统。

    字段:
        run_id: 当前 Host run ID。
        iteration_id: 当前 Engine iteration ID（格式 iter_001）。
        tool_call_id: 当前工具调用唯一 ID。
        index_in_iteration: 本轮中的顺序索引（0-based），默认 0。
    """

    run_id: str
    iteration_id: str
    tool_call_id: str
    index_in_iteration: int = 0
