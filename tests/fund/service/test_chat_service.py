"""ChatService chat_turn 测试。

覆盖:
- 单轮对话：user → answer + citations
- 多轮上下文传递：近期 turns 保留在 session
- 投资建议拦截：LLM 回答含建议关键词 → 拒绝
- Session 更新：turn 追加、updated_at 刷新
- 空输入/空白输入边界
"""

from pathlib import Path
from unittest import mock

import pytest

from fund_agent.agent.llm_tool_loop import (
    ChatResponse,
    FinalAnswer,
    TokenUsage,
)
from fund_agent.agent.tool_loop import AgentRunResult
from fund_agent.fund.document_tools.models import Citation
from fund_agent.host.session_store import SessionStore
from fund_agent.service.chat_service import (
    ChatService,
    ChatTurnRequest,
    ChatTurnResponse,
)
from fund_agent.service.prompt_composer import PromptComposer
from fund_agent.service.scene_config import ASK_SCENE_CONFIG
from fund_agent.service.session_models import PinnedState, Session, Turn


# ── helpers ──────────────────────────────────────────────────────

def _ok_answer(answer_text: str, citations: tuple[str, ...] = ()) -> FinalAnswer:
    """构建成功的 FinalAnswer。"""
    return FinalAnswer(
        answer=answer_text,
        citations=tuple(
            Citation(
                document_id="doc-1",
                fund_code="011649",
                fund_name="测试基金",
                year=2025,
                report_type="annual_report",
                locator=None,
                evidence_text=answer_text,
            )
            for _ in citations
        ) if citations else (),
        key_facts=(),
    )


def _make_agent_result(answer: str) -> AgentRunResult:
    """构建成功的 AgentRunResult。"""
    return AgentRunResult(
        answer=answer,
        citations=(),
        tool_trace=(),
        failure=None,
    )


def _template_dir() -> Path:
    """返回真实的 prompt 模板目录。"""
    return Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"


# ── tests ────────────────────────────────────────────────────────

class TestChatTurn:
    """chat_turn() 核心逻辑测试。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def prompt_composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_template_dir())

    @pytest.fixture
    def service(self, session_store: SessionStore, prompt_composer: PromptComposer) -> ChatService:
        return ChatService(
            session_store=session_store,
            prompt_composer=prompt_composer,
            scene_config=ASK_SCENE_CONFIG,
        )

    def _create_session(self, store: SessionStore, fund_code: str = "011649", active_document_id: str = "doc-011649-2025") -> Session:
        """创建带 active_document_id 的测试 session。"""
        session = store.create(fund_code=fund_code)
        ps = PinnedState(
            fund_code=fund_code,
            active_document_id=active_document_id,
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        store.save(session)
        return session

    def test_single_turn_answer(self, service: ChatService, session_store: SessionStore):
        """单轮对话：返回 answer 且 session 更新。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁？"),
            agent_result=_make_agent_result("基金经理是张三，任期5年。"),
        )

        assert "张三" in result.answer
        assert result.investment_advice_detected is False
        updated = session_store.load(session.session_id)
        assert len(updated.turns) == 2
        assert updated.turns[0].role == "user"
        assert updated.turns[1].role == "assistant"

    def test_multi_turn_context_preserved(self, service: ChatService, session_store: SessionStore):
        """多轮对话：前轮 turns 保留在 session 中。"""
        session = self._create_session(session_store)

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁？"),
            agent_result=_make_agent_result("基金经理是张三，任期5年。"),
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="他任期多久？"),
            agent_result=_make_agent_result("张三从2020年开始管理该基金。"),
        )

        assert "2020" in result.answer
        updated = session_store.load(session.session_id)
        assert len(updated.turns) == 4

    def test_investment_advice_blocked(self, service: ChatService, session_store: SessionStore):
        """LLM 输出含投资建议关键词 → 被拦截。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="这个基金怎么样？"),
            agent_result=_make_agent_result("建议买入该基金，目标价5元。"),
        )

        assert result.investment_advice_detected is True
        assert "不支持" in result.answer or "投资建议" in result.answer

    def test_empty_user_text(self, service: ChatService, session_store: SessionStore):
        """空白用户输入 → 返回提示，不调用 LLM。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="   "),
            agent_result=_make_agent_result("不应被调用"),
        )

        assert "输入" in result.answer

    def test_session_not_found(self, service: ChatService):
        """不存在的 session_id → FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            service.chat_turn(
                ChatTurnRequest(session_id="nonexistent", user_text="hello"),
            )

    def test_session_updated_after_turn(self, service: ChatService, session_store: SessionStore):
        """每次 chat_turn 后 session 的 turns 增加。"""
        session = self._create_session(session_store)

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=_make_agent_result("回答内容"),
        )

        updated = session_store.load(session.session_id)
        assert len(updated.turns) > len(session.turns)
        assert updated.turns[0].content == "问题"
        assert updated.turns[1].content == "回答内容"

    def test_missing_document_id_error(self, service: ChatService, session_store: SessionStore):
        """session 无 active_document_id 且未传 document_id → 提示错误。"""
        session = session_store.create(fund_code="011649")

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=_make_agent_result("不应被调用"),
        )

        assert "年报" in result.answer or "年份" in result.answer

    def test_runner_invoked_when_no_agent_result(self, service: ChatService, session_store: SessionStore):
        """未注入 agent_result → 使用 runner 执行 LLM。由于无真实 LLM，应返回错误。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            # 不注入 agent_result → 会尝试调用真实 runner（无 API key → 失败）
        )

        assert result.answer is not None  # 应返回错误提示而非崩溃

