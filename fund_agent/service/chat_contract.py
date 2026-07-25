"""ChatTurnContract — Service→Host 显式契约对象。

参考 Dayu contracts/agent_execution.py 的 ExecutionContract 设计。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatTurnContract:
    """Service→Host 单轮对话执行契约。

    scene / model / runtime 默认值由 Host 从 SceneConfig 读取；
    仅在需要显式覆盖时设置对应字段。

    参数:
        scene: scene 标识名（"ask" | "interactive"）。
        session_id: 会话 ID。
        user_text: 用户输入文本。
        document_id: 可选，覆盖 session 的 active_document_id。
        model_name: 可选，覆盖 scene 默认模型。
        max_iterations: 可选，覆盖 scene 默认最大迭代次数。
        timeout_ms: 可选，单次 run 超时毫秒数。
        disable_tools: 纯文本模式，禁用工具调用（Phase 8 预留）。
    """

    scene: str
    session_id: str
    user_text: str
    document_id: str | None = None
    model_name: str | None = None
    max_iterations: int | None = None
    timeout_ms: int | None = None
    disable_tools: bool = False
