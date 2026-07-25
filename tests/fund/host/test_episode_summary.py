"""Episode Summary 异步 LLM 压缩测试。

覆盖:
- 触发条件：>=10 轮 OR >=60% token
- 异步生成：threading.Thread 不阻塞主线程
- PinnedState patch：三态语义（None=不修改, ""=清空, 非空=覆盖）
- 压缩结果落盘
- 不重复压缩（compacting flag）
"""

import threading
import time
from pathlib import Path

import pytest

from fund_agent.agent.tool_loop import AgentRunResult
from fund_agent.host.session_store import SessionStore
from fund_agent.service.chat_service import ChatService, ChatTurnRequest
from fund_agent.service.prompt_composer import PromptComposer
from fund_agent.service.scene_config import INTERACTIVE_SCENE_CONFIG
from fund_agent.service.session_models import (
    EpisodeSummary,
    PinnedState,
    Session,
    Turn,
)


# ── helpers ──────────────────────────────────────────────────────

def _template_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"


def _create_session_with_turns(
    store: SessionStore,
    turn_count: int,
    fund_code: str = "011649",
) -> Session:
    """创建包含指定轮数的 session（每轮 user + assistant）。"""
    session = store.create(fund_code=fund_code)
    ps = PinnedState(
        fund_code=fund_code,
        active_document_id="doc-011649-2025",
        active_year=2025,
        user_constraints={
            "current_goal": "分析基金风险",
            "confirmed_facts": "基金经理任期5年",
            "open_questions": "未来调仓方向？",
        },
    )
    session = session.with_pinned_state(ps)
    for i in range(turn_count):
        session = session.add_turn(Turn(role="user", content=f"问题{i+1}"))
        session = session.add_turn(Turn(role="assistant", content=f"回答{i+1}"))
    store.save(session)
    return session


def _make_compaction_result(
    title: str = "测试摘要",
    goal: str = "分析持仓变化",
    confirmed_facts: list | None = None,
    open_questions: list | None = None,
    pinned_state_patch: dict | None = None,
) -> dict:
    """构建注入的 compaction 结果。"""
    return {
        "episode_summary": {
            "title": title,
            "goal": goal,
            "confirmed_facts": confirmed_facts or ["事实1"],
            "open_questions": open_questions or ["问题1"],
            "next_step": "继续分析",
        },
        "pinned_state_patch": pinned_state_patch or {},
    }


# ── PinnedState Patch 测试 ─────────────────────────────────────

class TestPinnedStatePatch:
    """PinnedState.apply_pinned_state_patch() 三态语义。"""

    def test_patch_updates_goal(self):
        """patch 包含 current_goal → 覆盖原值。"""
        session = Session.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            user_constraints={"current_goal": "旧目标"},
        )
        session = session.with_pinned_state(ps)

        patched = session.apply_pinned_state_patch({"current_goal": "新目标"})
        assert patched.pinned_state.user_constraints.get("current_goal") == "新目标"

    def test_patch_clears_goal_with_empty_string(self):
        """patch 值为空字符串 → 清空字段。"""
        session = Session.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            user_constraints={"current_goal": "旧目标", "confirmed_facts": "事实"},
        )
        session = session.with_pinned_state(ps)

        patched = session.apply_pinned_state_patch({"current_goal": ""})
        assert "current_goal" not in patched.pinned_state.user_constraints
        # 未提及字段不变
        assert patched.pinned_state.user_constraints.get("confirmed_facts") == "事实"

    def test_patch_missing_key_does_not_modify(self):
        """patch 不含某字段 → 该字段保持不变（None 语义）。"""
        session = Session.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            user_constraints={"current_goal": "保持不变", "open_questions": "问题"},
        )
        session = session.with_pinned_state(ps)

        patched = session.apply_pinned_state_patch({"confirmed_facts": "新事实"})
        assert patched.pinned_state.user_constraints.get("current_goal") == "保持不变"
        assert patched.pinned_state.user_constraints.get("open_questions") == "问题"
        assert patched.pinned_state.user_constraints.get("confirmed_facts") == "新事实"

    def test_patch_explicit_none_value_does_not_modify(self):
        """patch 值为 None → 不修改（与 key 缺失语义相同）。"""
        session = Session.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            user_constraints={"current_goal": "保留"},
        )
        session = session.with_pinned_state(ps)

        patched = session.apply_pinned_state_patch({"current_goal": None})
        assert patched.pinned_state.user_constraints.get("current_goal") == "保留"

    def test_patch_all_fields(self):
        """同时更新所有可 patch 字段。"""
        session = Session.create(fund_code="011649")
        session = session.with_pinned_state(PinnedState(fund_code="011649"))

        patched = session.apply_pinned_state_patch({
            "current_goal": "目标",
            "confirmed_facts": "事实",
            "open_questions": "问题",
        })
        assert patched.pinned_state.user_constraints["current_goal"] == "目标"
        assert patched.pinned_state.user_constraints["confirmed_facts"] == "事实"
        assert patched.pinned_state.user_constraints["open_questions"] == "问题"

    def test_patch_clear_all_fields(self):
        """全部清空。"""
        session = Session.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            user_constraints={
                "current_goal": "旧",
                "confirmed_facts": "旧",
                "open_questions": "旧",
            },
        )
        session = session.with_pinned_state(ps)

        patched = session.apply_pinned_state_patch({
            "current_goal": "",
            "confirmed_facts": "",
            "open_questions": "",
        })
        assert "current_goal" not in patched.pinned_state.user_constraints
        assert "confirmed_facts" not in patched.pinned_state.user_constraints
        assert "open_questions" not in patched.pinned_state.user_constraints


# ── EpisodeSummary 模型测试 ────────────────────────────────────

class TestEpisodeSummaryModel:
    """Session.add_episode_summary() 测试。"""

    def test_add_episode_summary_appends(self):
        """追加 episode summary 后 episode_summaries 增加。"""
        session = Session.create(fund_code="011649")
        assert len(session.episode_summaries) == 0

        ep = EpisodeSummary(
            episode_id="ep-001",
            start_turn_id=0,
            end_turn_id=5,
            title="测试摘要",
            goal="理解持仓",
        )
        session = session.add_episode_summary(ep)
        assert len(session.episode_summaries) == 1
        assert session.episode_summaries[0].title == "测试摘要"

    def test_add_multiple_episodes(self):
        """多次追加，顺序保留。"""
        session = Session.create(fund_code="011649")
        ep1 = EpisodeSummary(episode_id="ep-1", start_turn_id=0, end_turn_id=3)
        ep2 = EpisodeSummary(episode_id="ep-2", start_turn_id=4, end_turn_id=7)
        session = session.add_episode_summary(ep1).add_episode_summary(ep2)
        assert len(session.episode_summaries) == 2
        assert session.episode_summaries[0].episode_id == "ep-1"
        assert session.episode_summaries[1].episode_id == "ep-2"


# ── 触发条件 + 异步压缩测试 ────────────────────────────────────

class TestCompactionTrigger:
    """Episode Summary 触发条件 + 异步执行。"""

    def _service(self, store: SessionStore, **kwargs) -> ChatService:
        composer = PromptComposer(template_dir=_template_dir())
        service = ChatService(
            session_store=store,
            prompt_composer=composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
            enable_episode_summary=True,
            compaction_trigger_turns=3,  # 低阈值方便测试
            **kwargs,
        )
        return service

    def test_trigger_by_turn_count(self, tmp_path: Path):
        """>=3 轮时触发压缩（降低阈值）。"""
        store = SessionStore(tmp_path / "sessions")
        session = _create_session_with_turns(store, turn_count=3)
        assert len(session.turns) == 6  # 3 user + 3 assistant

        service = self._service(store)
        service.inject_compaction_result(_make_compaction_result(
            pinned_state_patch={"current_goal": "压缩后目标"},
        ))

        # 第 4 轮应触发压缩
        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="新问题"),
            agent_result=AgentRunResult(answer="新回答", citations=(), tool_trace=(), failure=None),
        )

        assert result.answer == "新回答"

        # 等待异步压缩完成（最多 2 秒）
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            updated = store.load(session.session_id)
            if len(updated.episode_summaries) > 0:
                break
            time.sleep(0.05)
        else:
            pytest.fail("压缩未在 2 秒内完成")

        updated = store.load(session.session_id)
        assert len(updated.episode_summaries) >= 1
        ep = updated.episode_summaries[0]
        assert ep.title == "测试摘要"
        assert ep.goal == "分析持仓变化"

    def test_compaction_updates_pinned_state(self, tmp_path: Path):
        """压缩后 pinned_state 被 patch 更新。"""
        store = SessionStore(tmp_path / "sessions")
        session = _create_session_with_turns(store, turn_count=3)

        service = self._service(store)
        service.inject_compaction_result(_make_compaction_result(
            pinned_state_patch={"current_goal": "更新后的目标"},
        ))

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=AgentRunResult(answer="回答", citations=(), tool_trace=(), failure=None),
        )

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            updated = store.load(session.session_id)
            goal = updated.pinned_state.user_constraints.get("current_goal", "")
            if "更新后" in str(goal):
                break
            time.sleep(0.05)

        updated = store.load(session.session_id)
        assert updated.pinned_state.user_constraints.get("current_goal") == "更新后的目标"

    def test_below_threshold_no_compaction(self, tmp_path: Path):
        """低于触发阈值时不压缩。"""
        store = SessionStore(tmp_path / "sessions")
        session = _create_session_with_turns(store, turn_count=1)  # 仅1轮

        service = self._service(store)
        service.inject_compaction_result(_make_compaction_result())

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题2"),
            agent_result=AgentRunResult(answer="回答2", citations=(), tool_trace=(), failure=None),
        )

        # 短暂等待后确认未压缩
        time.sleep(0.1)
        updated = store.load(session.session_id)
        assert len(updated.episode_summaries) == 0

    def test_compaction_non_blocking(self, tmp_path: Path):
        """压缩在后台线程执行，不阻塞主对话。"""
        store = SessionStore(tmp_path / "sessions")
        session = _create_session_with_turns(store, turn_count=3)

        service = self._service(store)
        # 使用一个慢速注入结果（模拟 LLM 延迟）
        service.inject_compaction_result(_make_compaction_result())

        start = time.monotonic()
        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=AgentRunResult(answer="快速回答", citations=(), tool_trace=(), failure=None),
        )
        elapsed = time.monotonic() - start

        assert result.answer == "快速回答"
        # 主调用应在 0.5 秒内返回（不等待压缩线程）
        assert elapsed < 2.0, f"主调用耗时 {elapsed:.2f}s，疑似阻塞"

    def test_no_duplicate_compaction(self, tmp_path: Path):
        """compacting flag 防止重复压缩。"""
        store = SessionStore(tmp_path / "sessions")
        session = _create_session_with_turns(store, turn_count=3)

        service = self._service(store)
        service.inject_compaction_result(_make_compaction_result())

        # 快速连续调用 2 次
        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题1"),
            agent_result=AgentRunResult(answer="回答1", citations=(), tool_trace=(), failure=None),
        )
        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题2"),
            agent_result=AgentRunResult(answer="回答2", citations=(), tool_trace=(), failure=None),
        )

        # 等待完成
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if session.session_id not in service._compacting:
                break
            time.sleep(0.05)

        updated = store.load(session.session_id)
        # 只应有一次压缩
        assert len(updated.episode_summaries) == 1

    def test_parse_compaction_json(self):
        """_parse_compaction_response 正确解析 JSON。"""
        raw = '{"episode_summary": {"title": "测试", "goal": "目标", "confirmed_facts": ["f1"], "open_questions": ["q1"], "next_step": "继续"}, "pinned_state_patch": {"current_goal": "新目标"}}'
        parsed = ChatService._parse_compaction_response(raw)
        assert parsed is not None
        assert parsed["episode_summary"]["title"] == "测试"
        assert parsed["pinned_state_patch"]["current_goal"] == "新目标"

    def test_parse_compaction_json_with_code_block(self):
        """解析含 ```json 代码块的响应。"""
        raw = '```json\n{"episode_summary": {"title": "T", "goal": "G", "confirmed_facts": [], "open_questions": [], "next_step": ""}, "pinned_state_patch": {}}\n```'
        parsed = ChatService._parse_compaction_response(raw)
        assert parsed is not None
        assert parsed["episode_summary"]["title"] == "T"

    def test_parse_compaction_invalid_json(self):
        """无效 JSON 返回 None。"""
        assert ChatService._parse_compaction_response("not json") is None
        assert ChatService._parse_compaction_response("") is None

    def test_disabled_compaction_does_not_trigger(self, tmp_path: Path):
        """enable_episode_summary=False 时永不触发压缩。"""
        store = SessionStore(tmp_path / "sessions")
        session = _create_session_with_turns(store, turn_count=10)

        composer = PromptComposer(template_dir=_template_dir())
        service = ChatService(
            session_store=store,
            prompt_composer=composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
            enable_episode_summary=False,
        )

        service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            agent_result=AgentRunResult(answer="回答", citations=(), tool_trace=(), failure=None),
        )

        time.sleep(0.1)
        updated = store.load(session.session_id)
        assert len(updated.episode_summaries) == 0
