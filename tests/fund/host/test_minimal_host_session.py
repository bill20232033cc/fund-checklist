"""MinimalHost 多轮会话托管测试。

覆盖:
- Session 生命周期：create → ACTIVE → close → CLOSED
- get_session / list_sessions
- 重复 close 幂等
"""

from pathlib import Path

import pytest

from fund_agent.agent.llm_tool_loop import ToolCall, ToolResult
from fund_agent.agent.tool_loop import AgentRunResult, MinimalFundDocumentAgent
from fund_agent.host.minimal_host import MinimalHost
from fund_agent.host.session_store import SessionStore
from fund_agent.service.session_models import Session, PinnedState


class _FakeAgent:
    """无操作 fake agent。"""

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        return AgentRunResult(answer=f"回答: {query}", citations=(), tool_trace=(), failure=None)


class TestMinimalHostSession:
    """MinimalHost session 生命周期测试。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def host(self, session_store: SessionStore) -> MinimalHost:
        return MinimalHost(
            agent=_FakeAgent(),
            session_store=session_store,
        )

    def test_create_session_active(self, host: MinimalHost):
        """create_session → 状态 ACTIVE。"""
        session = host.create_session(fund_code="011649")
        assert session.status == "ACTIVE"
        assert session.pinned_state.fund_code == "011649"
        assert session.session_id is not None

    def test_get_session(self, host: MinimalHost):
        """get_session 返回已创建的 session。"""
        created = host.create_session(fund_code="011649")
        loaded = host.get_session(created.session_id)
        assert loaded.session_id == created.session_id
        assert loaded.pinned_state.fund_code == "011649"

    def test_list_sessions(self, host: MinimalHost):
        """list_sessions 返回所有会话摘要。"""
        host.create_session(fund_code="011649")
        host.create_session(fund_code="000001")
        sessions = host.list_sessions()
        assert len(sessions) == 2

    def test_close_session(self, host: MinimalHost):
        """close_session → 状态变为 CLOSED。"""
        session = host.create_session(fund_code="011649")
        assert session.status == "ACTIVE"

        host.close_session(session.session_id)
        closed = host.get_session(session.session_id)
        assert closed.status == "CLOSED"

    def test_close_idempotent(self, host: MinimalHost):
        """重复 close 不报错。"""
        session = host.create_session(fund_code="011649")
        host.close_session(session.session_id)
        host.close_session(session.session_id)  # 不应报错
        closed = host.get_session(session.session_id)
        assert closed.status == "CLOSED"

    def test_session_persisted_across_hosts(self, session_store: SessionStore, tmp_path: Path):
        """session 通过 SessionStore 持久化，新建 host 可以加载。"""
        host1 = MinimalHost(agent=_FakeAgent(), session_store=session_store)
        session = host1.create_session(fund_code="011649")
        host1.close_session(session.session_id)

        # 新建 host（同一 session_store）
        host2 = MinimalHost(agent=_FakeAgent(), session_store=session_store)
        loaded = host2.get_session(session.session_id)
        assert loaded.status == "CLOSED"
        assert loaded.pinned_state.fund_code == "011649"
