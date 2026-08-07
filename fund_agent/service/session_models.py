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
class ToolCallSummary:
    """工具调用摘要，用于 history 注入。

    字段:
        tool_name: 工具名。
        arguments_display: 仅用于展示的关键参数拼接。
        success: 是否成功（result_kind == "success"）。
        failure_code: 失败分类，成功时为 None。
    """

    tool_name: str
    arguments_display: str = ""
    success: bool = True
    failure_code: str | None = None

    @property
    def result_summary(self) -> str:
        """从 success + failure_code 推导摘要。"""
        if self.success:
            return "成功"
        return f"失败: {self.failure_code}" if self.failure_code else "失败"


@dataclass(frozen=True)
class Turn:
    """单轮对话记录。

    字段:
        role: user 或 assistant。
        content: 对话文本内容。
        citations: assistant 回答的 citation 引用列表。
        key_facts: assistant 回答解析出的关键事实元组。
        tool_trace: 工具调用轨迹摘要。
        tool_calls: 结构化工具调用摘要列表。
        original_content: 被投资建议检测拦截前的原始回答；未拦截时为 None。
        blocked_terms: 触发投资建议拦截的词元（按文本首次命中顺序）；
            未拦截时为空元组。
        timestamp: ISO 8601 时间戳。
    """

    role: str  # "user" | "assistant"
    content: str
    citations: tuple[str, ...] = ()
    key_facts: tuple[str, ...] = ()
    tool_trace: tuple[str, ...] = ()
    tool_calls: tuple[ToolCallSummary, ...] = ()
    original_content: str | None = None
    blocked_terms: tuple[str, ...] = ()
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

    def add_episode_summary(self, episode: EpisodeSummary) -> Session:
        """追加 EpisodeSummary，返回新 Session。"""
        return Session(
            session_id=self.session_id,
            label=self.label,
            status=self.status,
            pinned_state=self.pinned_state,
            turns=self.turns,
            episode_summaries=self.episode_summaries + (episode,),
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def truncate_turns(self, keep_last: int) -> Session:
        """保留最近 keep_last 个 turns，删除更早的。

        参数:
            keep_last: 保留的最近轮次数。
        """
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

    def apply_pinned_state_patch(self, patch: dict) -> Session:
        """应用 PinnedState patch，返回新 Session。

        patch 三态语义：
        - key 不存在或值为 None → 不修改
        - 值为空字符串 → 显式清空
        - 值为非空 → 覆盖

        参数:
            patch: {"current_goal": str | None, "confirmed_facts": str | None,
                     "open_questions": str | None}
        """
        constraints = dict(self.pinned_state.user_constraints)

        new_goal: str | None = self.pinned_state.user_constraints.get("current_goal")
        new_facts: str | None = self.pinned_state.user_constraints.get("confirmed_facts")
        new_questions: str | None = self.pinned_state.user_constraints.get("open_questions")

        if "current_goal" in patch:
            val = patch["current_goal"]
            if val is not None:
                new_goal = val if val != "" else None  # None
        if "confirmed_facts" in patch:
            val = patch["confirmed_facts"]
            if val is not None:
                new_facts = val if val != "" else None  # None
        if "open_questions" in patch:
            val = patch["open_questions"]
            if val is not None:
                new_questions = val if val != "" else None  # None

        if new_goal is not None:
            constraints["current_goal"] = new_goal
        elif "current_goal" in constraints:
            del constraints["current_goal"]
        if new_facts is not None:
            constraints["confirmed_facts"] = new_facts
        elif "confirmed_facts" in constraints:
            del constraints["confirmed_facts"]
        if new_questions is not None:
            constraints["open_questions"] = new_questions
        elif "open_questions" in constraints:
            del constraints["open_questions"]

        new_ps = PinnedState(
            fund_code=self.pinned_state.fund_code,
            available_document_ids=self.pinned_state.available_document_ids,
            active_document_id=self.pinned_state.active_document_id,
            active_year=self.pinned_state.active_year,
            user_constraints=constraints,
        )
        return self.with_pinned_state(new_ps)
