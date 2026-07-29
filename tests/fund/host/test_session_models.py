"""Session 数据模型测试 — ToolCallSummary + Turn.tool_calls + Session.truncate_turns。"""

import pytest

from fund_agent.service.session_models import (
    EpisodeSummary,
    PinnedState,
    Session,
    ToolCallSummary,
    Turn,
)


# ── ToolCallSummary ────────────────────────────────────────────────


class TestToolCallSummary:
    """ToolCallSummary 模型测试。"""

    def test_creation_success(self):
        """构造成功的 ToolCallSummary。"""
        tc = ToolCallSummary(
            tool_name="search_document",
            arguments_display="query=基金经理",
            success=True,
        )
        assert tc.tool_name == "search_document"
        assert tc.arguments_display == "query=基金经理"
        assert tc.success is True
        assert tc.failure_code is None

    def test_creation_failure(self):
        """构造失败的 ToolCallSummary。"""
        tc = ToolCallSummary(
            tool_name="read_section",
            arguments_display="section_ref=sec-1",
            success=False,
            failure_code="NOT_FOUND",
        )
        assert tc.tool_name == "read_section"
        assert tc.success is False
        assert tc.failure_code == "NOT_FOUND"

    def test_result_summary_success(self):
        """成功时 result_summary 返回"成功"。"""
        tc = ToolCallSummary(tool_name="search_document", success=True)
        assert tc.result_summary == "成功"

    def test_result_summary_failure_with_code(self):
        """失败时 result_summary 返回"失败: code"。"""
        tc = ToolCallSummary(tool_name="read_section", success=False, failure_code="NOT_FOUND")
        assert tc.result_summary == "失败: NOT_FOUND"

    def test_result_summary_failure_no_code(self):
        """失败但无 failure_code 时 result_summary 返回"失败"。"""
        tc = ToolCallSummary(tool_name="read_section", success=False)
        assert tc.result_summary == "失败"

    def test_frozen(self):
        """ToolCallSummary 是 frozen dataclass，不可修改。"""
        tc = ToolCallSummary(tool_name="search_document")
        with pytest.raises(Exception):
            tc.tool_name = "other"  # type: ignore[misc]


# ── Turn.tool_calls ────────────────────────────────────────────────


class TestTurnToolCalls:
    """Turn.tool_calls 字段测试。"""

    def test_turn_with_tool_calls(self):
        """Turn 可携带 tool_calls 字段。"""
        tc1 = ToolCallSummary(tool_name="search_document", success=True)
        tc2 = ToolCallSummary(tool_name="read_section", success=True)
        turn = Turn(
            role="assistant",
            content="基金经理是张三。",
            tool_calls=(tc1, tc2),
        )
        assert len(turn.tool_calls) == 2
        assert turn.tool_calls[0].tool_name == "search_document"
        assert turn.tool_calls[1].tool_name == "read_section"

    def test_default_empty_tool_calls(self):
        """Turn 默认 tool_calls 为空元组。"""
        turn = Turn(role="user", content="你好")
        assert turn.tool_calls == ()


# ── Session.truncate_turns ─────────────────────────────────────────


def _make_turn(index: int) -> Turn:
    """构造测试用 Turn。"""
    return Turn(role="user", content=f"问题 {index}")


def _make_session(turn_count: int, **kwargs) -> Session:
    """构造带指定数量 turns 的测试 Session。"""
    session = Session(
        session_id="test-session",
        label=None,
        status=kwargs.pop("status", "ACTIVE"),
        pinned_state=PinnedState(fund_code="011649"),
        turns=tuple(_make_turn(i) for i in range(turn_count)),
        **kwargs,
    )
    return session


class TestTruncateTurns:
    """Session.truncate_turns 测试。"""

    def test_short_session_unchanged(self):
        """turns 数 <= keep_last 时返回原 session。"""
        session = _make_session(turn_count=3)
        result = session.truncate_turns(keep_last=5)
        assert result is session
        assert len(result.turns) == 3

    def test_exact_unchanged(self):
        """turns 数 == keep_last 时返回原 session。"""
        session = _make_session(turn_count=4)
        result = session.truncate_turns(keep_last=4)
        assert result is session
        assert len(result.turns) == 4

    def test_trims_old_turns(self):
        """turns > keep_last 时只保留最后 keep_last 个。"""
        session = _make_session(turn_count=10)
        result = session.truncate_turns(keep_last=3)
        assert result is not session
        assert len(result.turns) == 3
        assert result.turns[0].content == "问题 7"
        assert result.turns[1].content == "问题 8"
        assert result.turns[2].content == "问题 9"

    def test_preserves_status(self):
        """truncate 后 status 保持不变。"""
        session = _make_session(turn_count=10, status="ACTIVE")
        result = session.truncate_turns(keep_last=3)
        assert result.status == "ACTIVE"

    def test_updates_updated_at(self):
        """truncate 后 updated_at 被刷新。"""
        session = _make_session(turn_count=10)
        original_updated = session.updated_at
        result = session.truncate_turns(keep_last=3)
        assert result.updated_at != original_updated

    def test_preserves_episode_summaries(self):
        """truncate 后 episode_summaries 不变。"""
        ep = EpisodeSummary(
            episode_id="ep-1",
            start_turn_id=0,
            end_turn_id=5,
            title="早期对话",
        )
        session = _make_session(turn_count=10, episode_summaries=(ep,))
        result = session.truncate_turns(keep_last=3)
        assert len(result.episode_summaries) == 1
        assert result.episode_summaries[0].title == "早期对话"

    def test_zero_keeps_all_turns(self):
        """keep_last=0 时因 Python [-0:] == [0:] 保留全部 turns。"""
        session = _make_session(turn_count=5)
        result = session.truncate_turns(keep_last=0)
        # Python 切片 [-0:] 等价于 [0:]，因此全部保留
        assert len(result.turns) == 5
