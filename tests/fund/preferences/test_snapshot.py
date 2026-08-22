"""季度偏好快照的单元测试（Slice P3）。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fund_agent.preferences.snapshot import (
    DISCLAIMER,
    INVESTMENT_KEYWORDS,
    QUARTER_REGEX,
    BehaviorEvidence,
    PreferenceSnapshot,
    QuestionnaireBaseline,
    build_behavior_summary,
    generate_snapshot,
    quarter_date_range,
    render_snapshot_markdown,
    write_snapshot_files,
)
from fund_agent.preferences.store import (
    open_preferences_store,
    save_questionnaire_result,
)
from fund_agent.preferences.flomo_parser import FlomoMemo
from fund_agent.preferences.questionnaire import (
    QuestionnaireBank,
    QuestionnaireQuestion,
    score_questionnaire,
)


def _memo(created_at: str, content: str) -> dict[str, object]:
    return {"created_at": created_at, "content": content, "images": [], "source": "t.html"}


def _mini_bank() -> QuestionnaireBank:
    return QuestionnaireBank(
        version="mini-bank-v1",
        boards=["基金常识", "投前准备", "系统投资", "投资心态", "实战经验"],
        weights={"基金常识": 25, "投前准备": 20, "系统投资": 20, "投资心态": 20, "实战经验": 15},
        c1c5_bands=[[0, 19], [20, 36], [37, 53], [54, 75], [76, 100]],
        disclaimer=DISCLAIMER,
        questions=[
            QuestionnaireQuestion(
                id="q01",
                board="基金常识",
                difficulty=1,
                question="股票型基金主要投资于？",
                options=["股票", "债券", "货币市场工具", "房地产"],
                answer=0,
                risk_flag=False,
                explanation="股票型基金以股票为主要投资标的。",
            ),
            QuestionnaireQuestion(
                id="q02",
                board="投前准备",
                difficulty=1,
                question="投资前应优先了解的是？",
                options=["基金费用与风险", "基金经理长相", "市场小道消息", "同事推荐代码"],
                answer=0,
                risk_flag=False,
                explanation="投前应了解费用、风险与自身资金规划。",
            ),
            QuestionnaireQuestion(
                id="q03",
                board="系统投资",
                difficulty=1,
                question="定投的主要作用是？",
                options=["分批买入、摊平成本、淡化择时", "保证不亏损", "短期快速翻倍", "替代全部风险控制"],
                answer=0,
                risk_flag=False,
                explanation="定投通过纪律化分批投入摊薄平均成本。",
            ),
            QuestionnaireQuestion(
                id="q04",
                board="投资心态",
                difficulty=1,
                question="基金一周下跌 3%，最合理的反应是？",
                options=["按持有逻辑与计划判断", "立刻全部卖出", "立刻加倍买入", "完全不闻不问"],
                answer=0,
                risk_flag=True,
                explanation="短期波动应与持有逻辑、期限匹配判断。",
            ),
            QuestionnaireQuestion(
                id="q05",
                board="实战经验",
                difficulty=1,
                question="止盈纪律的核心是？",
                options=["按计划目标执行，不因情绪漂移", "涨一点就跑", "永远不止盈", "听消息决定"],
                answer=0,
                risk_flag=True,
                explanation="止盈纪律依赖事先计划与情绪隔离。",
            ),
        ],
    )


def test_keywords_at_least_16_words() -> None:
    assert len(INVESTMENT_KEYWORDS) >= 16
    assert len(set(INVESTMENT_KEYWORDS)) == len(INVESTMENT_KEYWORDS)


def test_quarter_regex_matches_valid_only() -> None:
    assert QUARTER_REGEX.fullmatch("2026Q1") is not None
    assert QUARTER_REGEX.fullmatch("2026Q4") is not None
    assert QUARTER_REGEX.fullmatch("2026Q5") is None
    assert QUARTER_REGEX.fullmatch("2026Q0") is None
    assert QUARTER_REGEX.fullmatch("2026Q") is None
    assert QUARTER_REGEX.fullmatch("26Q3") is None


def test_quarter_date_range() -> None:
    assert quarter_date_range("2026Q1") == (date(2026, 1, 1), date(2026, 4, 1))
    assert quarter_date_range("2026Q2") == (date(2026, 4, 1), date(2026, 7, 1))
    assert quarter_date_range("2026Q3") == (date(2026, 7, 1), date(2026, 10, 1))
    assert quarter_date_range("2026Q4") == (date(2026, 10, 1), date(2027, 1, 1))


def test_build_behavior_summary_keyword_hit_and_miss() -> None:
    memos = [
        _memo("2026-07-05T10:00:00+08:00", "今天买入了一点基金，打算长期持有。"),
        _memo("2026-07-06T09:00:00+08:00", "周末去爬山，天气很好。"),
        _memo("2026-07-07T09:00:00+08:00", "净值回撤，先不动。"),
    ]
    summary = build_behavior_summary(memos, "2026Q3")
    assert len(summary) == 2
    assert summary[0].content == "今天买入了一点基金，打算长期持有。"
    assert "买入" in summary[0].hit_keywords
    assert "基金" in summary[0].hit_keywords
    assert "净值" in summary[1].hit_keywords


def test_build_behavior_summary_quarter_boundary_excludes_other_quarters() -> None:
    memos = [
        _memo("2026-06-30T23:59:59+08:00", "6 月底买入基金，属于上季度。"),
        _memo("2026-07-01T00:00:00+08:00", "7 月 1 日定投，属于本季度。"),
        _memo("2026-10-01T00:00:00+08:00", "10 月 1 日卖出，属于下季度。"),
        _memo("2026-08-15T12:00:00+08:00", "8 月中旬止盈一笔。"),
    ]
    summary = build_behavior_summary(memos, "2026Q3")
    contents = [item.content for item in summary]
    assert contents == ["7 月 1 日定投，属于本季度。", "8 月中旬止盈一笔。"]


def test_build_behavior_summary_ordered_by_created_at() -> None:
    memos = [
        _memo("2026-07-10T08:00:00+08:00", "七月减仓"),
        _memo("2026-09-01T08:00:00+08:00", "九月加仓"),
    ]
    summary = build_behavior_summary(memos, "2026Q3")
    assert [item.created_at for item in summary] == [
        "2026-07-10T08:00:00+08:00",
        "2026-09-01T08:00:00+08:00",
    ]


def test_reflection_template_fields_present_and_empty(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        snapshot = generate_snapshot(
            store,
            "2026Q3",
            bank=_mini_bank(),
            created_at="2026-10-01T09:00:00+08:00",
        )
    finally:
        store.close()
    assert set(snapshot.reflection) == {
        "actual_actions",
        "consistent_with_statement",
        "deviation",
        "next_adjustments",
    }
    assert all(value == "" for value in snapshot.reflection.values())


def test_disclaimer_verbatim(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        snapshot = generate_snapshot(
            store,
            "2026Q3",
            bank=_mini_bank(),
            created_at="2026-10-01T09:00:00+08:00",
        )
    finally:
        store.close()
    assert snapshot.disclaimer == "本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"
    assert snapshot.disclaimer == DISCLAIMER
    assert snapshot.disclaimer in render_snapshot_markdown(snapshot)


def test_generate_snapshot_no_questionnaire_null_baseline(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        store.import_memos(
            [FlomoMemo(id="flomo-2026-07-05-1", created_at="2026-07-05T10:00:00+08:00", content="定投了 1000 元")],
            source_path="t.html",
            exported_at="2026-08-19",
        )
        snapshot = generate_snapshot(store, "2026Q3", bank=None)
    finally:
        store.close()
    assert snapshot.baseline is None
    assert len(snapshot.behavior_summary) == 1
    assert snapshot.behavior_summary[0].hit_keywords == ["定投"]


def _store_with_memos(memos: list[dict[str, object]]):
    import sqlite3

    from fund_agent.preferences.store import PreferencesStore

    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE memos (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
        "content TEXT NOT NULL, images_json TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL);"
    )
    connection.executemany(
        "INSERT INTO memos (id, created_at, content, images_json, source) VALUES (?, ?, ?, '[]', ?)",
        [
            (f"flomo-{str(memo['created_at'])}", str(memo["created_at"]), str(memo["content"]), "t.html")
            for memo in memos
        ],
    )
    connection.commit()
    return PreferencesStore(connection=connection, db_path=Path("/tmp/placeholder.db"))


def test_write_snapshot_files_json_and_md(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        store.import_memos(
            [FlomoMemo(id="flomo-2026-07-05-1", created_at="2026-07-05T10:00:00+08:00", content="今天加仓了 5000 元")],
            source_path="t.html",
            exported_at="2026-08-19",
        )
        snapshot = PreferenceSnapshot(
            quarter="2026Q3",
            created_at="2026-10-01T09:00:00+08:00",
            baseline=None,
            behavior_summary=[],
            reflection={
                "actual_actions": "",
                "consistent_with_statement": "",
                "deviation": "",
                "next_adjustments": "",
            },
            disclaimer=DISCLAIMER,
        )
        json_path, md_path = write_snapshot_files(store, snapshot)
    finally:
        store.close()

    assert json_path == tmp_path / "wd" / "preferences" / "quarters" / "2026Q3" / "preference-snapshot.json"
    assert md_path == tmp_path / "wd" / "preferences" / "quarters" / "2026Q3" / "preference-snapshot.md"
    assert json_path.is_file()
    assert md_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["quarter"] == "2026Q3"
    assert payload["created_at"] == "2026-10-01T09:00:00+08:00"
    assert payload["questionnaire"] is None
    assert payload["behavior_summary"] == []
    assert payload["reflection"] == {
        "actual_actions": "",
        "consistent_with_statement": "",
        "deviation": "",
        "next_adjustments": "",
    }
    assert payload["disclaimer"] == DISCLAIMER
    assert "季度偏好快照" in md_path.read_text(encoding="utf-8")


def test_generate_snapshot_with_questionnaire_baseline(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        bank = _mini_bank()
        answers = {q.id: q.answer for q in bank.questions}
        result = score_questionnaire(bank, answers, answered_at="2026-08-01T10:00:00+08:00")
        save_questionnaire_result(store, result)
        snapshot = generate_snapshot(store, "2026Q3", bank=bank)
    finally:
        store.close()
    assert snapshot.baseline is not None
    assert snapshot.baseline.answered_at == "2026-08-01T10:00:00+08:00"
    assert snapshot.baseline.total_score == 100.0
    assert snapshot.baseline.dimension_scores == {
        "基金常识": 25.0, "投前准备": 20.0, "系统投资": 20.0, "投资心态": 20.0, "实战经验": 15.0,
    }
    assert snapshot.baseline.risk_level == "C5"
    assert snapshot.disclaimer == DISCLAIMER


def test_latest_questionnaire_result_respects_quarter_end(tmp_path: Path) -> None:
    from fund_agent.preferences.store import latest_questionnaire_result

    store = open_preferences_store(tmp_path / "wd")
    try:
        bank = _mini_bank()
        result = score_questionnaire(bank, {q.id: q.answer for q in bank.questions}, answered_at="2026-07-01T10:00:00+08:00")
        save_questionnaire_result(store, result)
        result2 = score_questionnaire(bank, {q.id: q.answer for q in bank.questions}, answered_at="2026-10-02T10:00:00+08:00")
        save_questionnaire_result(store, result2)
        latest = latest_questionnaire_result(store, date(2026, 9, 30))
        assert latest is not None
        assert latest.answered_at == "2026-07-01T10:00:00+08:00"
    finally:
        store.close()


def test_generate_snapshot_excludes_next_quarter_first_day_questionnaire(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        bank = _mini_bank()
        answers = {q.id: q.answer for q in bank.questions}
        # 2026-10-01（2026Q3 独占边界次日 00:00）作答不纳入 2026Q3 baseline。
        result = score_questionnaire(bank, answers, answered_at="2026-10-01T00:00:00+08:00")
        save_questionnaire_result(store, result)
        snapshot = generate_snapshot(store, "2026Q3", bank=bank)
        assert snapshot.baseline is None
    finally:
        store.close()


def test_generate_snapshot_includes_quarter_last_day_questionnaire(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        bank = _mini_bank()
        answers = {q.id: q.answer for q in bank.questions}
        # 2026-09-30（2026Q3 最后一日）作答纳入 2026Q3 baseline。
        result = score_questionnaire(bank, answers, answered_at="2026-09-30T12:00:00+08:00")
        save_questionnaire_result(store, result)
        snapshot = generate_snapshot(store, "2026Q3", bank=bank)
        assert snapshot.baseline is not None
        assert snapshot.baseline.answered_at == "2026-09-30T12:00:00+08:00"
    finally:
        store.close()


def test_save_snapshot_persists_row(tmp_path: Path) -> None:
    from fund_agent.preferences.store import save_snapshot

    store = open_preferences_store(tmp_path / "wd")
    try:
        snapshot = PreferenceSnapshot(
            quarter="2026Q3",
            created_at="2026-10-01T09:00:00+08:00",
            baseline=QuestionnaireBaseline(
                answered_at="2026-08-01T10:00:00+08:00",
                total_score=88.0,
                dimension_scores={"基金常识": 22.0},
                risk_level="C4",
            ),
            behavior_summary=[
                BehaviorEvidence(
                    created_at="2026-07-05T10:00:00+08:00",
                    content="买入基金",
                    hit_keywords=["买入", "基金"],
                )
            ],
            reflection={
                "actual_actions": "",
                "consistent_with_statement": "",
                "deviation": "",
                "next_adjustments": "",
            },
            disclaimer=DISCLAIMER,
        )
        record_id = save_snapshot(store, snapshot)
    finally:
        store.close()
    assert record_id.startswith("snapshot-2026Q3-")


def test_generate_snapshot_invalid_quarter_raises(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path / "wd")
    try:
        import pytest

        with pytest.raises(ValueError):
            generate_snapshot(store, "2026Q5", bank=None)
    finally:
        store.close()
