"""Session 数据模型 — 三层记忆（Pinned State + Recent Turns + Episode Summary）。

参考 Dayu host/conversation_store.py 的结构设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class PinnedState:
    """会话级固定状态，不随 compaction 被压缩。

    字段:
        fund_code: 当前讨论的基金代码。
        available_document_ids: 该基金所有可用年报的 document_id。
        active_document_id: 当前选中的 document_id。
        active_year: 当前选中的年份。
        user_constraints: 用户设定的约束（如 max_tokens）。
    """

    fund_code: str
    available_document_ids: tuple[str, ...] = ()
    active_document_id: str | None = None
    active_year: int | None = None
    user_constraints: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Turn:
    """单轮对话记录。

    字段:
        role: user 或 assistant。
        content: 对话文本内容。
        citations: assistant 回答的 citation 引用列表。
        tool_trace: 工具调用轨迹摘要。
        timestamp: ISO 8601 时间戳。
    """

    role: str  # "user" | "assistant"
    content: str
    citations: tuple[str, ...] = ()
    tool_trace: tuple[str, ...] = ()
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class EpisodeSummary:
    """Episodic memory 压缩后的摘要。

    字段:
        episode_id: 摘要唯一 ID。
        start_turn_id: 被压缩的起始 turn 索引。
        end_turn_id: 被压缩的结束 turn 索引。
        title: 摘要标题。
        goal: 用户当前目标。
        confirmed_facts: 已确认的事实。
        open_questions: 待解答的问题。
    """

    episode_id: str
    start_turn_id: int
    end_turn_id: int
    title: str = ""
    goal: str = ""
    confirmed_facts: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Session:
    """多轮对话会话。

    字段:
        session_id: 唯一会话 ID。
        label: 可选用户标签。
        status: ACTIVE 或 CLOSED。
        pinned_state: 固定状态（不随 compaction 压缩）。
        turns: 对话轮次列表。
        episode_summaries: 压缩后的 episodic memory。
        created_at: 创建时间 ISO 8601。
        updated_at: 最后更新时间 ISO 8601。
    """

    session_id: str
    label: str | None
    status: str  # "ACTIVE" | "CLOSED"
    pinned_state: PinnedState
    turns: tuple[Turn, ...] = ()
    episode_summaries: tuple[EpisodeSummary, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(cls, fund_code: str, label: str | None = None) -> Session:
        """创建新会话。

        参数:
            fund_code: 基金代码。
            label: 可选标签。
        """
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            session_id=uuid4().hex,
            label=label,
            status="ACTIVE",
            pinned_state=PinnedState(fund_code=fund_code),
            created_at=now,
            updated_at=now,
        )

    def add_turn(self, turn: Turn) -> Session:
        """追加一轮对话，返回新 Session（不可变）。"""
        return Session(
            session_id=self.session_id,
            label=self.label,
            status=self.status,
            pinned_state=self.pinned_state,
            turns=self.turns + (turn,),
            episode_summaries=self.episode_summaries,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def close(self) -> Session:
        """关闭会话。"""
        return Session(
            session_id=self.session_id,
            label=self.label,
            status="CLOSED",
            pinned_state=self.pinned_state,
            turns=self.turns,
            episode_summaries=self.episode_summaries,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def with_pinned_state(self, pinned_state: PinnedState) -> Session:
        """更新 PinnedState，返回新 Session。"""
        return Session(
            session_id=self.session_id,
            label=self.label,
            status=self.status,
            pinned_state=pinned_state,
            turns=self.turns,
            episode_summaries=self.episode_summaries,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
