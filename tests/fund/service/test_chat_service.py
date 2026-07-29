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
from fund_agent.fund.document_tools.constants import FailureCode
from fund_agent.fund.document_tools.models import Citation, ToolFailure
from fund_agent.host.session_store import SessionStore
from fund_agent.service.chat_service import (
    ChatService,
    ChatTurnRequest,
    ChatTurnResponse,
)
from fund_agent.service.prompt_composer import PromptComposer
from fund_agent.service.scene_config import ASK_SCENE_CONFIG
from fund_agent.service.session_models import PinnedState, Session, ToolCallSummary, Turn


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

    def test_failure_propagated_to_answer(self, service: ChatService, session_store: SessionStore):
        """agent_result.failure 非 None 时 → 错误信息作为 answer 返回，而非空字符串。"""
        session = self._create_session(session_store)

        failure = ToolFailure(code=FailureCode.UNAVAILABLE, message="LLM 最终回答缺少受控 citation")
        failed_result = AgentRunResult(answer="", citations=(), tool_trace=(), failure=failure)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=failed_result,
        )

        assert "LLM 处理失败" in result.answer
        assert "受控 citation" in result.answer
        # 失败不应更新 session turns
        updated = session_store.load(session.session_id)
        assert len(updated.turns) == 0

    def test_success_no_failure(self, service: ChatService, session_store: SessionStore):
        """agent_result.failure 为 None → 正常返回 answer。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁？"),
            agent_result=_make_agent_result("基金经理是张三。"),
        )

        assert "张三" in result.answer
        assert "LLM 处理失败" not in result.answer


# ── History Contribution ───────────────────────────────────────────


def _history_service(
    session_store: SessionStore,
    prompt_composer: PromptComposer,
    history_max_tokens: int = 2000,
) -> ChatService:
    """构造用于 history 测试的 ChatService。"""
    return ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=ASK_SCENE_CONFIG,
        history_max_tokens=history_max_tokens,
    )


class TestBuildHistoryContribution:
    """_build_history_contribution 测试。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def prompt_composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_template_dir())

    def test_empty_session_returns_none(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """空 session（无 turns）返回 None。"""
        service = _history_service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")
        result = service._build_history_contribution(session)
        assert result is None

    def test_contains_header(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """返回的 history 文本以 "## 历史对话" 开头。"""
        service = _history_service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="基金经理是谁？"))
        session = session.add_turn(Turn(role="assistant", content="基金经理是张三。"))
        session_store.save(session)

        result = service._build_history_contribution(session)
        assert result is not None
        assert result.startswith("## 历史对话")

    def test_contains_separator(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """history 末尾包含 "---" 分隔线和 JSON 格式指引。"""
        service = _history_service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="你好"))
        session = session.add_turn(Turn(role="assistant", content="你好！"))
        session_store.save(session)

        result = service._build_history_contribution(session)
        assert result is not None
        assert "---" in result
        assert "JSON 格式" in result

    def test_within_token_limit(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """token 超限时旧轮次被截断，只保留最近轮次。"""
        limit = 80
        service = _history_service(session_store, prompt_composer, history_max_tokens=limit)
        session = session_store.create(fund_code="011649")
        # 添加 30 对 turns，远超 token 限制
        for i in range(30):
            session = session.add_turn(Turn(role="user", content=f"这是第 {i} 个问题"))
            session = session.add_turn(Turn(role="assistant", content=f"这是第 {i} 个回答"))
        session_store.save(session)

        result = service._build_history_contribution(session)
        assert result is not None
        # 最近的问题应该在
        assert "第 29 个问题" in result
        # 最早的问题应该被截断
        assert "第 0 个问题" not in result

    def test_recent_first_order(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """history 中 turns 按时间正序排列（旧→新）。"""
        service = _history_service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="第一个问题"))
        session = session.add_turn(Turn(role="assistant", content="第一个回答"))
        session = session.add_turn(Turn(role="user", content="第二个问题"))
        session = session.add_turn(Turn(role="assistant", content="第二个回答"))
        session_store.save(session)

        result = service._build_history_contribution(session)
        assert result is not None
        idx1 = result.index("第一个问题")
        idx2 = result.index("第二个问题")
        assert idx1 < idx2  # 旧问题在前


class TestFormatTurnForHistory:
    """_format_turn_for_history 测试。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def prompt_composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_template_dir())

    def test_format_user_turn(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """用户轮次格式包含 [用户提问] 标签。"""
        service = _history_service(session_store, prompt_composer)
        turn = Turn(role="user", content="基金经理是谁？")
        result = service._format_turn_for_history(turn)
        assert "[用户提问]" in result
        assert "基金经理是谁？" in result

    def test_format_assistant_turn_with_tool_calls(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """带工具调用的助手轮次包含 [工具调用] 行。"""
        service = _history_service(session_store, prompt_composer)
        tc = ToolCallSummary(
            tool_name="search_document",
            arguments_display="query=基金经理",
            success=True,
        )
        turn = Turn(
            role="assistant",
            content="基金经理是张三。",
            tool_calls=(tc,),
        )
        result = service._format_turn_for_history(turn)
        assert "[助手回答]" in result
        assert "[工具调用]" in result
        assert "search_document" in result
        assert "成功" in result

    def test_format_turn_with_citations(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """带 citation 的轮次包含 [引用文档] 行。"""
        service = _history_service(session_store, prompt_composer)
        turn = Turn(
            role="assistant",
            content="基金经理是张三。",
            citations=("doc-1", "doc-2"),
        )
        result = service._format_turn_for_history(turn)
        assert "[引用文档]" in result
        assert "doc-1" in result
        assert "doc-2" in result

    def test_format_empty_tool_calls_skipped(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """空 tool_calls 不产生 [工具调用] 行。"""
        service = _history_service(session_store, prompt_composer)
        turn = Turn(role="assistant", content="你好。", tool_calls=())
        result = service._format_turn_for_history(turn)
        assert "[工具调用]" not in result


class TestEstimateTokenCount:
    """_estimate_token_count 测试。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def prompt_composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_template_dir())

    def test_estimate_chinese_text(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """中文文本估算约 1.5 token/字。"""
        service = _history_service(session_store, prompt_composer)
        tokens = service._estimate_token_count("基金经理是谁")
        # 6 个中文字符 → 6 * 1.5 = 9
        assert tokens == 9

    def test_estimate_english_text(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """英文文本估算约 0.25 token/字符。"""
        service = _history_service(session_store, prompt_composer)
        tokens = service._estimate_token_count("Hello world")
        # 11 个英文字符 → 11 / 4 = 2.75 → int = 2
        assert tokens == 2

    def test_estimate_mixed_text(self, session_store: SessionStore, prompt_composer: PromptComposer):
        """中英混合文本正确分别计算。"""
        service = _history_service(session_store, prompt_composer)
        # "你好world" = 2 中文 + 5 英文 = 2*1.5 + 5/4 = 3 + 1.25 = 4.25 → 4
        tokens = service._estimate_token_count("你好world")
        assert tokens == 4
