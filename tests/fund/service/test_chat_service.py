"""ChatService chat_turn 测试。

覆盖:
- 单轮对话：user → answer + citations
- 多轮上下文传递：近期 turns 保留在 session
- 投资建议拦截：LLM 回答含建议关键词 → 拒绝
- Session 更新：turn 追加、updated_at 刷新
- 失败轮：成对落盘（user + assistant），tool_trace / tool_calls 保留
- 被拦截回答：原始回答与触发词在 session 与 response 中保留
- 空输入/空白输入边界
"""

from pathlib import Path
from unittest import mock

import pytest

from fund_agent.agent.llm_tool_loop import (
    ChatResponse,
    FakeLlmClient,
    FinalAnswer,
    LlmToolLoopRunner,
    TokenUsage,
)
from fund_agent.agent.tool_loop import AgentRunResult, ToolTraceEntry
from fund_agent.fund.document_tools.constants import FailureCode
from fund_agent.fund.document_tools.models import Citation, ToolFailure
from fund_agent.host.session_store import SessionStore
from fund_agent.service.chat_service import (
    ChatService,
    ChatTurnRequest,
    ChatTurnResponse,
)
from fund_agent.service.prompt_composer import PromptComposer
from fund_agent.service.scene_config import ASK_SCENE_CONFIG, INTERACTIVE_SCENE_CONFIG
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


class _RecordingRunner:
    """记录 run() 参数的假 runner，返回固定成功 AgentRunResult。"""

    def __init__(self, llm_client=None, tool_service=None, max_steps: int = 8) -> None:
        """初始化并保存注入对象。"""

        self.llm_client = llm_client
        self.tool_service = tool_service
        self.max_steps = max_steps
        self.calls: list[dict] = []

    def run(
        self,
        *,
        document_id: str,
        query: str,
        scene: str = "ask",
        candidate_queries: tuple[str, ...] | None = None,
    ) -> AgentRunResult:
        """记录调用参数并返回固定成功结果。"""

        self.calls.append(
            {
                "document_id": document_id,
                "query": query,
                "scene": scene,
                "candidate_queries": candidate_queries,
            }
        )
        return _make_agent_result("根据年报，基金经理持有本基金。")


class _RecordingSessionStore(SessionStore):
    """记录每次 save 的 Session，用于校验磁盘不序列化的完整 Turn 字段。"""

    def __init__(self, root: Path) -> None:
        """初始化并记录保存历史。"""

        super().__init__(root)
        self.saved_sessions: list[Session] = []

    def save(self, session: Session) -> None:
        """保存并记录副本。"""

        self.saved_sessions.append(session)
        super().save(session)


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

    def test_quoted_expected_return_rate_not_blocked(self, service: ChatService, session_store: SessionStore):
        """引用年报术语 预期收益率 不触发第二道投资建议守卫。"""
        session = self._create_session(session_store)
        answer = "年报披露本基金的预期收益率为 8%，风险收益特征为混合型。"

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="年报中的预期收益率是多少？"),
            agent_result=_make_agent_result(answer),
        )

        assert result.investment_advice_detected is False
        assert result.answer == answer

    def test_quoted_investment_strategy_text_not_blocked(self, service: ChatService, session_store: SessionStore):
        """引用年报投资策略原文（弱词处于引用上下文）不触发第二道守卫。"""
        session = self._create_session(session_store)
        answer = "年报投资策略原文：报告期内买入并持有优质股票，卖出部分债券兑现收益。"

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="年报投资策略是什么？"),
            agent_result=_make_agent_result(answer),
        )

        assert result.investment_advice_detected is False
        assert result.answer == answer

    def test_prediction_sentence_still_blocked(self, service: ChatService, session_store: SessionStore):
        """预测句式 预期收益为 8% 在 chat_service 层仍被拦截。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="预期收益会是多少？"),
            agent_result=_make_agent_result("本基金未来一年的预期收益为 8%。"),
        )

        assert result.investment_advice_detected is True
        assert "不支持" in result.answer or "投资建议" in result.answer

    def test_decision_a_annual_report_facts_not_blocked(self, service: ChatService, session_store: SessionStore):
        """决策 A：持仓/费率等年报事实性描述不被第二道守卫拦截。"""
        session = self._create_session(session_store)
        answer = (
            "报告期内本基金增持了银行、减持了纺织服饰行业；"
            "财务报表附注披露本期买入返售金融资产、卖出回购金融资产款；"
            "期末前十大重仓股中本期买入 X、本期卖出 Y。"
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="持仓和费率情况？"),
            agent_result=_make_agent_result(answer),
        )

        assert result.investment_advice_detected is False
        assert result.answer == answer

    def test_decision_a_directive_context_still_blocked(self, service: ChatService, session_store: SessionStore):
        """决策 A：弱词遇指令动词（如 值得持有应增持）仍被第二道守卫拦截。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="这个基金怎么样？"),
            agent_result=_make_agent_result("该基金值得持有，应增持。"),
        )

        assert result.investment_advice_detected is True
        assert "不支持" in result.answer or "投资建议" in result.answer

    def test_decision_a_bare_yingshi_facts_not_blocked(self, service: ChatService, session_store: SessionStore):
        """修正：裸 应 不再命中指令动词（应付托管费/应主要投资于），第二道守卫放行。"""
        session = self._create_session(session_store)
        answer = (
            "财务报表附注：本期应付托管费计入负债，买入返售金融资产；"
            "基金合同载明应主要投资于股票资产。"
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="费率与投资范围？"),
            agent_result=_make_agent_result(answer),
        )

        assert result.investment_advice_detected is False
        assert result.answer == answer

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
        """agent_result.failure 非 None 时 → 错误信息作为 answer 返回，失败轮成对落盘。"""
        session = self._create_session(session_store)

        failure = ToolFailure(code=FailureCode.UNAVAILABLE, message="LLM 最终回答缺少受控 citation")
        failed_result = AgentRunResult(answer="", citations=(), tool_trace=(), failure=failure)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=failed_result,
        )

        assert "LLM 处理失败" in result.answer
        assert "受控 citation" in result.answer
        # 失败轮同样成对落盘（user + assistant）
        updated = session_store.load(session.session_id)
        assert len(updated.turns) == 2
        assert updated.turns[0].role == "user"
        assert updated.turns[1].role == "assistant"
        assert "LLM 处理失败" in updated.turns[1].content

    def test_failure_tool_trace_non_empty(self, service: ChatService, session_store: SessionStore):
        """工具失败路径：ChatTurnResponse.tool_trace 非空且含失败分类，不依赖 status 字段。"""
        session = self._create_session(session_store)

        failure = ToolFailure(code=FailureCode.NOT_FOUND, message="章节不存在")
        failed_result = AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(
                ToolTraceEntry(
                    tool_name="search_document",
                    arguments={"query": "基金规模"},
                    result_kind="success",
                ),
                ToolTraceEntry(
                    tool_name="read_section",
                    arguments={"section_ref": "sec-0001"},
                    result_kind="failure",
                    failure_code=FailureCode.NOT_FOUND,
                ),
            ),
            failure=failure,
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金规模是多大？"),
            agent_result=failed_result,
        )

        assert result.tool_trace == (
            "search_document(success)",
            "read_section(failure:not_found)",
        )
        assert all(isinstance(item, str) for item in result.tool_trace)
        # 失败轮成对落盘，tool_trace 在磁盘往返后可读
        updated = session_store.load(session.session_id)
        assert len(updated.turns) == 2
        assert updated.turns[1].tool_trace == (
            "search_document(success)",
            "read_section(failure:not_found)",
        )

    def test_failure_provider_first_step_trace_empty(self, service: ChatService, session_store: SessionStore):
        """provider 首轮失败（next_step 异常，trace 为空）→ tool_trace 为空但失败轮仍落盘。"""
        session = self._create_session(session_store)

        failure = ToolFailure(
            code=FailureCode.LLM_MALFORMED_RESPONSE,
            message="DeepSeek LLM provider response 不符合受控结构",
        )
        failed_result = AgentRunResult(answer="", citations=(), tool_trace=(), failure=failure)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=failed_result,
        )

        assert result.tool_trace == ()
        updated = session_store.load(session.session_id)
        assert len(updated.turns) == 2
        assert updated.turns[1].tool_trace == ()

    def test_failure_turn_tool_calls_retained_on_session(
        self,
        tmp_path: Path,
        prompt_composer: PromptComposer,
    ):
        """失败轮 tool_calls 在保存的 Session 对象上保留（含失败分类）。"""
        store = _RecordingSessionStore(tmp_path / "sessions")
        service = ChatService(
            session_store=store,
            prompt_composer=prompt_composer,
            scene_config=ASK_SCENE_CONFIG,
        )
        session = self._create_session(store)
        failed_result = AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(
                ToolTraceEntry(
                    tool_name="read_section",
                    arguments={"section_ref": "sec-0001"},
                    result_kind="failure",
                    failure_code=FailureCode.NOT_FOUND,
                ),
            ),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message="章节不存在"),
        )

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金规模是多大？"),
            agent_result=failed_result,
        )

        saved = store.saved_sessions[-1]
        assert len(saved.turns) == 2
        tool_calls = saved.turns[1].tool_calls
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "read_section"
        assert tool_calls[0].success is False
        assert tool_calls[0].failure_code == FailureCode.NOT_FOUND.value

    def test_blocked_answer_original_and_terms_saved(
        self,
        tmp_path: Path,
        prompt_composer: PromptComposer,
    ):
        """被拦截回答：session 保存原始回答与触发词，response 同步保留。"""
        store = _RecordingSessionStore(tmp_path / "sessions")
        service = ChatService(
            session_store=store,
            prompt_composer=prompt_composer,
            scene_config=ASK_SCENE_CONFIG,
        )
        session = self._create_session(store)
        original = "建议买入该基金，目标价5元。"

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="这个基金怎么样？"),
            agent_result=_make_agent_result(original),
        )

        assert result.investment_advice_detected is True
        assert result.original_content == original
        # 弱词「买入」是强词「建议买入」的子串，独立命中后同样收录（与 contains_investment_advice 同判据）
        assert set(result.blocked_terms) == {"建议买入", "买入", "目标价"}
        # session 中保存原始回答与触发词（最短命中词元）
        saved = store.saved_sessions[-1]
        assert len(saved.turns) == 2
        assistant = saved.turns[1]
        assert assistant.content == "抱歉，不支持涉及投资建议的问题。"
        assert assistant.original_content == original
        assert set(assistant.blocked_terms) == {"建议买入", "买入", "目标价"}
        assert min(assistant.blocked_terms, key=len) == "买入"

    def test_normal_answer_no_blocked_fields(self, service: ChatService, session_store: SessionStore):
        """未拦截回答：original_content 为 None，blocked_terms 为空。"""
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁？"),
            agent_result=_make_agent_result("基金经理是张三，任期5年。"),
        )

        assert result.investment_advice_detected is False
        assert result.original_content is None
        assert result.blocked_terms == ()
        updated = session_store.load(session.session_id)
        assert updated.turns[1].original_content is None
        assert updated.turns[1].blocked_terms == ()

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


class TestInteractiveQualityWiring:
    """interactive 质量修复：候选词注入 + runner candidate_queries 接线。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def prompt_composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_template_dir())

    def _create_session(self, store: SessionStore) -> Session:
        """创建带 active_document_id 的 interactive 测试 session。"""
        session = store.create(fund_code="004393")
        ps = PinnedState(
            fund_code="004393",
            active_document_id="004393-2024-annual_report-abc123",
            active_year=2024,
        )
        session = session.with_pinned_state(ps)
        store.save(session)
        return session

    def test_candidate_queries_passed_to_runner(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """chat_turn：manager_holdings 命中的查询把受控候选词传给 runner.run。"""

        captured: list[_RecordingRunner] = []

        def factory(llm_client, tool_service, max_steps: int = 8) -> _RecordingRunner:
            runner = _RecordingRunner(llm_client, tool_service, max_steps=max_steps)
            captured.append(runner)
            return runner

        service = ChatService(
            session_store=session_store,
            prompt_composer=prompt_composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
            runner_factory=factory,
        )
        session = self._create_session(session_store)

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理持有本产品吗"),
        )

        assert result.answer == "根据年报，基金经理持有本基金。"
        assert len(captured) == 1
        call = captured[0].calls[0]
        assert call["scene"] == "interactive"
        assert call["query"] == "基金经理持有本产品吗"
        assert call["candidate_queries"] is not None
        assert "持有本基金" in call["candidate_queries"]

    def test_candidate_queries_none_without_profile(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """chat_turn：无 profile 命中的查询不传候选词（runner 只做空结果计数收敛）。"""

        captured: list[_RecordingRunner] = []

        def factory(llm_client, tool_service, max_steps: int = 8) -> _RecordingRunner:
            runner = _RecordingRunner(llm_client, tool_service, max_steps=max_steps)
            captured.append(runner)
            return runner

        service = ChatService(
            session_store=session_store,
            prompt_composer=prompt_composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
            runner_factory=factory,
        )
        session = self._create_session(session_store)

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁"),
        )

        assert captured[0].calls[0]["candidate_queries"] is None

    def test_build_contributions_injects_retrieval_candidates(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """_build_contributions：manager_holdings 命中时注入 retrieval 候选词 slot。"""

        service = ChatService(
            session_store=session_store,
            prompt_composer=prompt_composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )
        session = self._create_session(session_store)

        contributions = service._build_contributions(
            session,
            document_id="004393-2024-annual_report-abc123",
            user_query="基金经理持有本产品吗",
        )

        assert "retrieval" in contributions
        assert "manager_holdings" in contributions["retrieval"]
        assert "持有本基金" in contributions["retrieval"]

    def test_build_contributions_skips_retrieval_without_profile(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """_build_contributions：无 profile 命中的查询不注入 retrieval slot。"""

        service = ChatService(
            session_store=session_store,
            prompt_composer=prompt_composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )
        session = self._create_session(session_store)

        contributions = service._build_contributions(
            session,
            document_id="004393-2024-annual_report-abc123",
            user_query="基金经理是谁",
        )

        assert "retrieval" not in contributions


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


# ── Runtime contribution 的 active_document_id 注入 ─────────────────────


class TestBuildContributionsRuntimeDocumentId:
    """_build_contributions runtime contribution 的 active_document_id 注入测试。"""

    @pytest.fixture
    def session_store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(tmp_path / "sessions")

    @pytest.fixture
    def prompt_composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_template_dir())

    def _service(self, session_store: SessionStore, prompt_composer: PromptComposer) -> ChatService:
        return ChatService(
            session_store=session_store,
            prompt_composer=prompt_composer,
            scene_config=ASK_SCENE_CONFIG,
        )

    def test_runtime_includes_pinned_document_id(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """session.pinned_state.active_document_id 必须注入 runtime contribution。"""
        service = self._service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="011649-2025-annual_report-abc123",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        session_store.save(session)

        contributions = service._build_contributions(session)

        assert "011649-2025-annual_report-abc123" in contributions["runtime"]

    def test_runtime_prefers_current_turn_document_id(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """本轮已确定的 document_id 优先于 pinned_state。"""
        service = self._service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="011649-2025-annual_report-pinned",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        session_store.save(session)

        contributions = service._build_contributions(
            session,
            document_id="011649-2024-annual_report-current",
        )

        assert "011649-2024-annual_report-current" in contributions["runtime"]
        assert "011649-2025-annual_report-pinned" not in contributions["runtime"]

    def test_runtime_omits_document_id_when_unset(
        self, session_store: SessionStore, prompt_composer: PromptComposer
    ) -> None:
        """pinned_state 与当前轮都无 document_id 时 runtime 不含文档行。"""
        service = self._service(session_store, prompt_composer)
        session = session_store.create(fund_code="011649")

        contributions = service._build_contributions(session)

        assert "document_id" not in contributions["runtime"]


def test_interactive_nonstream_long_answer_truncated_by_final_guard(tmp_path: Path) -> None:
    """interactive 非流式路径：chat_turn -> runner.run(scene=interactive) 时终答守卫生效。

    R5 live e2e 暴露 Q4 1705 字原文粘贴未截断；此处锁死 INTERACTIVE_SCENE_CONFIG
    场景下非流式 interactive 必须经 runner 终答守卫截断为前 200 字摘要。
    """

    long_answer = ("3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较\n" * 200)

    def factory(llm_client, tool_service, max_steps: int = 8) -> LlmToolLoopRunner:
        return LlmToolLoopRunner(
            tool_service=tool_service,
            llm_client=FakeLlmClient(
                [FinalAnswer(answer=long_answer, citations=(), key_facts=())] * 2
            ),
            max_steps=max_steps,
        )

    session_store = SessionStore(tmp_path / "sessions")
    prompt_composer = PromptComposer(template_dir=_template_dir())
    service = ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=INTERACTIVE_SCENE_CONFIG,
        runner_factory=factory,
    )
    session = session_store.create(fund_code="007466")
    ps = PinnedState(
        fund_code="007466",
        active_document_id="007466-2025-annual_report-ee23d4b8070dce1a",
        active_year=2025,
    )
    session_store.save(session.with_pinned_state(ps))

    result = service.chat_turn(
        ChatTurnRequest(session_id=session.session_id, user_text="2021-2025 份额净值增长率")
    )

    assert len(result.answer) <= 225
    assert "截断" in result.answer
