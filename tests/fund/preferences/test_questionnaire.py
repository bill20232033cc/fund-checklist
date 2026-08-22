"""问卷基线题库与评分测试（Slice P2）。"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from fund_agent.preferences.questionnaire import (
    QuestionBank,
    QuestionnaireBank,
    QuestionnaireQuestion,
    QuestionnaireResult,
    risk_band,
    score_questionnaire,
)
from fund_agent.preferences.store import (
    PreferencesStoreError,
    list_questionnaire_results,
    open_preferences_store,
    save_questionnaire_result,
)

BANK_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "fund_agent"
    / "preferences"
    / "questionnaire"
    / "baseline-v1.json"
)
MINI_BANK_PATH = Path(__file__).parent / "fixtures" / "mini_bank.json"

EXPECTED_BOARDS = ["基金常识", "投前准备", "系统投资", "投资心态", "实战经验"]


def _mini_bank() -> QuestionnaireBank:
    """从 mini_bank fixture 直接构造题库（不经过 80 题完整性校验）。"""

    data = json.loads(MINI_BANK_PATH.read_text(encoding="utf-8"))
    return QuestionnaireBank(
        version=data["version"],
        boards=list(data["boards"]),
        weights=dict(data["weights"]),
        c1c5_bands=[list(band) for band in data["c1c5_bands"]],
        disclaimer=data["disclaimer"],
        questions=[QuestionnaireQuestion(**item) for item in data["questions"]],
    )


def _all_answers(bank: QuestionnaireBank, *, correct: bool = True) -> dict[str, int]:
    return {
        q.id: q.answer if correct else (q.answer + 1) % 4 for q in bank.questions
    }


# ---------- 题库完整性 ----------


def test_baseline_bank_integrity() -> None:
    bank = QuestionBank.load(BANK_PATH)
    assert bank.version == "baseline-v1"
    assert bank.boards == EXPECTED_BOARDS
    assert bank.weights == {"基金常识": 25, "投前准备": 20, "系统投资": 20, "投资心态": 20, "实战经验": 15}
    assert sum(bank.weights.values()) == 100
    assert bank.c1c5_bands == [[0, 19], [20, 36], [37, 53], [54, 75], [76, 100]]
    assert bank.disclaimer == "本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"

    assert len(bank.questions) == 80
    assert [q.id for q in bank.questions] == [f"q{i:02d}" for i in range(1, 81)]

    board_counts = Counter(q.board for q in bank.questions)
    assert {board: board_counts[board] for board in EXPECTED_BOARDS} == {
        "基金常识": 16,
        "投前准备": 16,
        "系统投资": 16,
        "投资心态": 16,
        "实战经验": 16,
    }

    # 难度分布约 30/40/30：24/32/24
    difficulty_counts = Counter(q.difficulty for q in bank.questions)
    assert difficulty_counts == {1: 24, 2: 32, 3: 24}

    risk_questions = [q for q in bank.questions if q.risk_flag]
    assert 8 <= len(risk_questions) <= 16
    assert all(q.board in ("投资心态", "实战经验") for q in risk_questions)

    for q in bank.questions:
        assert q.board in EXPECTED_BOARDS
        assert q.difficulty in (1, 2, 3)
        assert len(q.options) == 4
        assert 0 <= q.answer <= 3
        assert isinstance(q.risk_flag, bool)
        assert q.question
        assert q.explanation


def test_bank_load_invalid_json_raises_valueerror(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="解析失败"):
        QuestionBank.load(bad)


def test_bank_load_missing_file_raises_valueerror(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="读取失败"):
        QuestionBank.load(tmp_path / "missing.json")


def test_bank_load_structural_violations(tmp_path: Path) -> None:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))

    cases: list[tuple[Callable[[dict], None], str]] = [
        (lambda d: d["questions"].pop(), "必须包含 80 题"),
        (lambda d: d["questions"][0].__setitem__("board", "不存在的板块"), "board 不在五大板块中"),
        (lambda d: d["questions"][0].__setitem__("options", ["a", "b", "c"]), "必须恰好有 4 个非空选项"),
        (lambda d: d["questions"][0].__setitem__("answer", 4), "answer 必须是 0-3"),
        (lambda d: d["questions"][0].__setitem__("difficulty", 5), "difficulty 必须是 1-3"),
        (lambda d: d["questions"][0].__setitem__("risk_flag", True), "risk_flag 仅允许在投资心态/实战经验板块"),
        (lambda d: d["weights"].__setitem__("基金常识", 30), "weights 合计必须为 100"),
        (lambda d: d["c1c5_bands"].__setitem__(0, [1, 19]), "必须连续覆盖 0-100"),
    ]
    for mutate, message in cases:
        mutated = json.loads(json.dumps(data))
        mutate(mutated)
        path = tmp_path / "mutated.json"
        path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            QuestionBank.load(path)


def test_bank_load_risk_flag_count_out_of_range(tmp_path: Path) -> None:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    for item in data["questions"]:
        if item["board"] in ("投资心态", "实战经验") and item["id"] in ("q50", "q52", "q54", "q55", "q57", "q59", "q61"):
            item["risk_flag"] = False
    path = tmp_path / "low_risk.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="risk_flag 题数必须在 8-16"):
        QuestionBank.load(path)


# ---------- 评分 ----------


def test_score_full_marks() -> None:
    bank = _mini_bank()
    result = score_questionnaire(bank, _all_answers(bank), answered_at="2026-08-21T00:00:00+08:00")
    assert result.total_score == 100.0
    assert result.dimension_scores == {"基金常识": 40.0, "系统投资": 35.0, "投资心态": 25.0}
    assert result.risk_level == "C5"
    assert result.version == "mini-bank-v1"
    assert result.answered_at == "2026-08-21T00:00:00+08:00"
    assert all(result.correct.values())
    assert result.disclaimer == bank.disclaimer


def test_score_all_wrong() -> None:
    bank = _mini_bank()
    result = score_questionnaire(bank, _all_answers(bank, correct=False))
    assert result.total_score == 0.0
    assert result.dimension_scores == {"基金常识": 0.0, "系统投资": 0.0, "投资心态": 0.0}
    assert result.risk_level == "C1"
    assert not any(result.correct.values())


def test_score_single_board_weight_conversion() -> None:
    bank = _mini_bank()
    answers = _all_answers(bank, correct=False)
    answers["q01"] = bank.questions[0].answer
    answers["q02"] = bank.questions[1].answer
    result = score_questionnaire(bank, answers)
    assert result.dimension_scores["基金常识"] == 40.0
    assert result.dimension_scores["系统投资"] == 0.0
    assert result.dimension_scores["投资心态"] == 0.0
    assert result.total_score == 40.0


def test_score_total_equals_sum_of_dimensions() -> None:
    bank = _mini_bank()
    answers = {
        "q01": bank.questions[0].answer,
        "q02": (bank.questions[1].answer + 1) % 4,
        "q03": bank.questions[2].answer,
        "q04": (bank.questions[3].answer + 1) % 4,
        "q05": bank.questions[4].answer,
        "q06": (bank.questions[5].answer + 1) % 4,
    }
    result = score_questionnaire(bank, answers)
    assert result.dimension_scores == {"基金常识": 20.0, "系统投资": 17.5, "投资心态": 12.5}
    assert result.total_score == round(sum(result.dimension_scores.values()), 1)
    assert result.total_score == 50.0


def test_risk_band_boundaries() -> None:
    bands = [[0, 19], [20, 36], [37, 53], [54, 75], [76, 100]]
    expected = [
        (0, "C1"), (19, "C1"),
        (20, "C2"), (36, "C2"),
        (37, "C3"), (53, "C3"),
        (54, "C4"), (75, "C4"),
        (76, "C5"), (100, "C5"),
    ]
    for score, level in expected:
        assert risk_band(score, bands) == level, f"score={score}"


def test_risk_level_mapping_via_score() -> None:
    bank = _mini_bank()
    answers = _all_answers(bank, correct=False)
    # 两道 risk 题（q05/q06），只答对 q05 → 得分率 50% → C3
    answers["q05"] = bank.questions[4].answer
    result = score_questionnaire(bank, answers)
    assert result.risk_level == "C3"


def test_score_unknown_question_id_raises() -> None:
    bank = _mini_bank()
    answers = _all_answers(bank)
    answers["q99"] = 0
    with pytest.raises(ValueError, match="未知题号"):
        score_questionnaire(bank, answers)


def test_score_missing_answers_raises() -> None:
    bank = _mini_bank()
    answers = _all_answers(bank)
    del answers["q03"]
    with pytest.raises(ValueError, match="答案缺失题"):
        score_questionnaire(bank, answers)


def test_score_answer_index_out_of_range_raises() -> None:
    bank = _mini_bank()
    answers = _all_answers(bank)
    answers["q01"] = 4
    with pytest.raises(ValueError, match="选项索引必须是 0-3"):
        score_questionnaire(bank, answers)


# ---------- store 持久化 ----------


def _scored_result() -> QuestionnaireResult:
    bank = _mini_bank()
    return score_questionnaire(
        bank, _all_answers(bank), answered_at="2026-08-21T10:30:00+08:00"
    )


def test_save_and_list_questionnaire_results(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path)
    try:
        record_id = save_questionnaire_result(store, _scored_result())
        rows = list_questionnaire_results(store)
    finally:
        store.close()
    assert record_id == "2026-08-21T10:30:00+08:00"
    assert len(rows) == 1
    row = rows[0]
    assert row.id == record_id
    assert row.answered_at == "2026-08-21T10:30:00+08:00"
    assert row.dimension_scores == {"基金常识": 40.0, "系统投资": 35.0, "投资心态": 25.0}
    assert row.total_score == 100.0
    assert row.risk_level == "C5"
    assert row.answers == _scored_result().answers
    assert row.disclaimer == "本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"


def test_list_questionnaire_results_order_by_answered_at_desc(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path)
    try:
        save_questionnaire_result(
            store,
            score_questionnaire(_mini_bank(), _all_answers(_mini_bank()), answered_at="2026-08-20T00:00:00+08:00"),
        )
        save_questionnaire_result(
            store,
            score_questionnaire(_mini_bank(), _all_answers(_mini_bank(), correct=False), answered_at="2026-08-21T00:00:00+08:00"),
        )
        rows = list_questionnaire_results(store)
    finally:
        store.close()
    assert [row.answered_at for row in rows] == [
        "2026-08-21T00:00:00+08:00",
        "2026-08-20T00:00:00+08:00",
    ]


def test_save_questionnaire_result_same_second_appends_suffix(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path)
    try:
        first = save_questionnaire_result(store, _scored_result())
        second = save_questionnaire_result(store, _scored_result())
        rows = list_questionnaire_results(store)
    finally:
        store.close()
    assert first == "2026-08-21T10:30:00+08:00"
    assert second == "2026-08-21T10:30:00+08:00-2"
    assert len(rows) == 2


def test_schema_has_questionnaire_results_table(tmp_path: Path) -> None:
    store = open_preferences_store(tmp_path)
    conn = sqlite3.connect(store.db_path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(questionnaire_results)")]
    finally:
        conn.close()
        store.close()
    assert columns == [
        "id", "answered_at", "dimension_scores_json", "total_score", "risk_level",
        "answers_json", "disclaimer",
    ]
