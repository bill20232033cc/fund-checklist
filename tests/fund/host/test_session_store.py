"""Session 数据模型 + SessionStore 持久化测试。

覆盖:
- PinnedState / Turn / EpisodeSummary / Session 模型构造
- SessionStore: create / save / load / list / delete
- 原子写入防损坏
- label 双向映射
"""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from fund_agent.host.session_store import SessionStore
from fund_agent.service.session_models import (
    EpisodeSummary,
    PinnedState,
    Session,
    ToolCallSummary,
    Turn,
)


class TestPinnedState:
    """PinnedState 数据模型测试。"""

    def test_default_values(self):
        """所有字段有合理默认值。"""
        ps = PinnedState(fund_code="011649")
        assert ps.fund_code == "011649"
        assert ps.available_document_ids == ()
        assert ps.active_document_id is None
        assert ps.active_year is None
        assert ps.user_constraints == {}

    def test_full_construction(self):
        """完整字段构造。"""
        ps = PinnedState(
            fund_code="011649",
            available_document_ids=("id-2021", "id-2022"),
            active_document_id="id-2022",
            active_year=2022,
            user_constraints={"max_tokens": 8000},
        )
        assert ps.active_year == 2022
        assert len(ps.available_document_ids) == 2


class TestTurn:
    """Turn 数据模型测试。"""

    def test_user_turn(self):
        """user turn 构造。"""
        turn = Turn(role="user", content="基金经理是谁？")
        assert turn.role == "user"
        assert turn.content == "基金经理是谁？"
        assert turn.tool_trace == ()
        assert turn.timestamp is not None

    def test_assistant_turn_with_citations(self):
        """assistant turn 含 citations 和 tool_trace。"""
        turn = Turn(
            role="assistant",
            content="基金经理是张三，任期5年。",
            citations=("sec_3.1",),
            tool_trace=("search_document",),
        )
        assert turn.role == "assistant"
        assert len(turn.citations) == 1
        assert len(turn.tool_trace) == 1

    def test_turn_blocked_fields_defaults(self):
        """未拦截轮次：original_content 为 None，blocked_terms 为空元组。"""
        turn = Turn(role="assistant", content="基金经理是张三。")
        assert turn.original_content is None
        assert turn.blocked_terms == ()
        assert turn.tool_calls == ()


class TestEpisodeSummary:
    """EpisodeSummary 数据模型测试。"""

    def test_construction(self):
        ep = EpisodeSummary(
            episode_id="ep-001",
            start_turn_id=0,
            end_turn_id=5,
            title="持仓分析讨论",
            goal="了解基金持仓变化",
            confirmed_facts=("前十大持仓集中度60%",),
            open_questions=("未来调仓方向？",),
        )
        assert ep.start_turn_id == 0
        assert ep.end_turn_id == 5
        assert len(ep.confirmed_facts) == 1


class TestSession:
    """Session 数据模型测试。"""

    def test_create_session(self):
        """Session 创建时生成 session_id 和时间戳。"""
        session = Session.create(fund_code="011649")
        assert session.session_id is not None
        assert len(session.session_id) > 0
        assert session.status == "ACTIVE"
        assert session.pinned_state.fund_code == "011649"
        assert session.created_at is not None

    def test_add_turn_appends(self):
        """add_turn 追加 turn 并更新 updated_at。"""
        session = Session.create(fund_code="011649")
        assert len(session.turns) == 0
        session = session.add_turn(Turn(role="user", content="hello"))
        assert len(session.turns) == 1

    def test_close_session(self):
        """close 变更状态为 CLOSED。"""
        session = Session.create(fund_code="011649")
        assert session.status == "ACTIVE"
        session = session.close()
        assert session.status == "CLOSED"


class TestSessionStore:
    """SessionStore 持久化测试。"""

    @pytest.fixture
    def store_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "sessions"

    @pytest.fixture
    def store(self, store_dir: Path) -> SessionStore:
        return SessionStore(store_dir)

    def test_create_and_save(self, store: SessionStore, store_dir: Path):
        """create→save 后 JSON 文件存在且可加载。"""
        session = store.create(fund_code="011649")
        assert session.session_id is not None
        json_path = store_dir / f"{session.session_id}.json"
        assert json_path.exists()

        loaded = store.load(session.session_id)
        assert loaded.session_id == session.session_id
        assert loaded.pinned_state.fund_code == "011649"

    def test_create_with_label(self, store: SessionStore):
        """带 label 创建：labels.json 双向映射建立。"""
        session = store.create(fund_code="011649", label="my-session")
        loaded = store.load("my-session")
        assert loaded.session_id == session.session_id

    def test_list_sessions(self, store: SessionStore):
        """list_sessions 返回所有会话摘要。"""
        store.create(fund_code="011649")
        store.create(fund_code="000001")
        sessions = store.list_sessions()
        assert len(sessions) == 2

    def test_list_empty(self, store: SessionStore):
        """无会话时返回空列表。"""
        assert store.list_sessions() == []

    def test_delete_session(self, store: SessionStore, store_dir: Path):
        """delete 移除 JSON 文件和 label 映射。"""
        session = store.create(fund_code="011649", label="test")
        assert (store_dir / f"{session.session_id}.json").exists()
        store.delete(session.session_id)
        assert not (store_dir / f"{session.session_id}.json").exists()
        # label 映射也应清理
        labels_path = store_dir / "labels.json"
        if labels_path.exists():
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            assert session.session_id not in labels.get("by_id", {})

    def test_save_and_load_preserves_turns(self, store: SessionStore):
        """保存后加载，turns 和 pinned_state 完整保留。"""
        session = store.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="Q1"))
        session = session.add_turn(Turn(role="assistant", content="A1"))
        store.save(session)

        loaded = store.load(session.session_id)
        assert len(loaded.turns) == 2
        assert loaded.turns[0].content == "Q1"

    def test_old_format_session_json_loads_with_new_turn_fields(self, store: SessionStore, store_dir: Path):
        """旧格式 session JSON（无 original_content/blocked_terms/tool_calls）仍可加载。"""
        session_id = "old-format-session"
        payload = {
            "schema_version": 1,
            "session_id": session_id,
            "label": None,
            "status": "ACTIVE",
            "pinned_state": {"fund_code": "011649"},
            "turns": [
                {
                    "role": "user",
                    "content": "问题",
                    "citations": [],
                    "tool_trace": [],
                    "timestamp": "2026-01-01T00:00:00+00:00",
                },
                {
                    "role": "assistant",
                    "content": "回答",
                    "citations": [],
                    "tool_trace": ["search_document"],
                    "timestamp": "2026-01-01T00:00:01+00:00",
                },
            ],
            "episode_summaries": [],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / f"{session_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        loaded = store.load(session_id)
        assert len(loaded.turns) == 2
        assert loaded.turns[1].original_content is None
        assert loaded.turns[1].blocked_terms == ()
        assert loaded.turns[1].tool_calls == ()
        assert loaded.turns[1].key_facts == ()
        assert loaded.turns[1].tool_trace == ("search_document",)

    def test_round_trip_preserves_key_facts(self, store: SessionStore):
        """磁盘往返后 key_facts 完整保留（interactive 落盘验收）。"""
        session = store.create(fund_code="011649")
        assistant = Turn(
            role="assistant",
            content="根据年报，基金经理持有本基金份额数量区间为 0-10 万份。",
            key_facts=("0-10 万份", "从业人员整体持有"),
        )
        session = session.add_turn(Turn(role="user", content="基金经理持有本产品吗")).add_turn(assistant)
        store.save(session)

        loaded = store.load(session.session_id)
        assert len(loaded.turns) == 2
        assert loaded.turns[1].key_facts == ("0-10 万份", "从业人员整体持有")

    def test_round_trip_preserves_blocked_fields_and_tool_calls(self, store: SessionStore):
        """磁盘往返后 original_content / blocked_terms / tool_calls 完整保留。"""
        session = store.create(fund_code="011649")
        assistant = Turn(
            role="assistant",
            content="抱歉，不支持涉及投资建议的问题。",
            tool_trace=("read_section(failure:not_found)",),
            tool_calls=(
                ToolCallSummary(
                    tool_name="read_section",
                    arguments_display="section_ref=sec-0001",
                    success=False,
                    failure_code="not_found",
                ),
            ),
            original_content="建议买入该基金，目标价5元。",
            blocked_terms=("建议买入", "买入", "目标价"),
        )
        session = session.add_turn(Turn(role="user", content="这个基金怎么样？")).add_turn(assistant)
        store.save(session)

        loaded = store.load(session.session_id)
        assert len(loaded.turns) == 2
        restored = loaded.turns[1]
        assert restored.original_content == "建议买入该基金，目标价5元。"
        assert restored.blocked_terms == ("建议买入", "买入", "目标价")
        assert len(restored.tool_calls) == 1
        tc = restored.tool_calls[0]
        assert tc.tool_name == "read_section"
        assert tc.arguments_display == "section_ref=sec-0001"
        assert tc.success is False
        assert tc.failure_code == "not_found"
        assert restored.tool_trace == ("read_section(failure:not_found)",)

    def test_load_nonexistent_raises(self, store: SessionStore):
        """加载不存在的 session 抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent-id")

    def test_atomic_write_no_corruption(self, store: SessionStore, store_dir: Path):
        """原子写入：临时文件先写入再 os.replace。"""
        session = store.create(fund_code="011649")
        json_path = store_dir / f"{session.session_id}.json"
        content_before = json_path.read_text(encoding="utf-8")

        # 模拟写入中途崩溃（在 os.replace 之前）
        original_replace = os.replace
        def _fake_replace(src, dst):
            if dst == str(json_path):
                raise KeyboardInterrupt("模拟中断")
            return original_replace(src, dst)

        session2 = session.add_turn(Turn(role="user", content="bad write"))
        with mock.patch("os.replace", side_effect=_fake_replace):
            try:
                store.save(session2)
            except KeyboardInterrupt:
                pass

        # 原文件应保持完整
        assert json_path.exists()
        content_after = json_path.read_text(encoding="utf-8")
        data = json.loads(content_after)
        assert data["session_id"] == session.session_id

    # ── 7K: label 过滤 + set_label ────────────────────────────

    def test_list_sessions_filter_by_label(self, store: SessionStore):
        """list_sessions(label=...) 按 label 过滤。"""
        store.create(fund_code="011649", label="session-a")
        store.create(fund_code="000001", label="session-b")
        store.create(fund_code="000002")  # 无 label

        all_sessions = store.list_sessions()
        assert len(all_sessions) == 3

        filtered = store.list_sessions(label="session-a")
        assert len(filtered) == 1
        assert filtered[0]["label"] == "session-a"

        no_match = store.list_sessions(label="nonexistent")
        assert len(no_match) == 0

    def test_list_sessions_filter_by_label_case_sensitive(self, store: SessionStore):
        """label 过滤大小写敏感。"""
        store.create(fund_code="011649", label="MySession")
        store.create(fund_code="000001", label="mysession")

        assert len(store.list_sessions(label="MySession")) == 1
        assert len(store.list_sessions(label="mysession")) == 1

    def test_set_label_new(self, store: SessionStore):
        """为已有 session 设置新 label。"""
        session = store.create(fund_code="011649")
        assert session.label is None

        store.set_label(session.session_id, "new-label")
        # 通过 label 能加载到
        loaded = store.load("new-label")
        assert loaded.session_id == session.session_id

    def test_set_label_update(self, store: SessionStore):
        """更新已有 label：旧 label 映射移除。"""
        session = store.create(fund_code="011649", label="old-label")
        store.set_label(session.session_id, "new-label")

        loaded = store.load("new-label")
        assert loaded.session_id == session.session_id

        # 旧 label 不可用
        with pytest.raises(FileNotFoundError):
            store.load("old-label")

    def test_set_label_same_value(self, store: SessionStore):
        """设置相同的 label 不报错。"""
        session = store.create(fund_code="011649", label="mylabel")
        store.set_label(session.session_id, "mylabel")
        loaded = store.load("mylabel")
        assert loaded.session_id == session.session_id
