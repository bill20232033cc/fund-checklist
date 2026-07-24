"""StreamEvent 数据模型 —— LLM 工具调用循环的流式输出事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(Enum):
    """流式事件类型（8 种，对齐 dayu AppEvent 设计）。"""

    CONTENT_DELTA = "content_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_EVENT = "tool_event"
    METADATA = "metadata"
    WARNING = "warning"
    ERROR = "error"
    DONE = "done"


@dataclass
class StreamEvent:
    """LLM runner 产出的单个流式事件。

    不包含 dayu 特有的 session/run 字段。
    """

    type: StreamEventType
    payload: Any
    sequence: int = 0
