"""preference-snapshot CLI 端到端测试（Slice P3）。"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

from fund_agent.cli.main import CLASSIFIED_FAILURE_EXIT_CODE, SUCCESS_EXIT_CODE, run_cli
from fund_agent.preferences.flomo_parser import FlomoMemo
from fund_agent.preferences.questionnaire import QuestionBank, score_questionnaire
from fund_agent.preferences.store import open_preferences_store, save_questionnaire_result

BANK_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "fund_agent"
    / "preferences"
    / "questionnaire"
    / "baseline-v1.json"
)

DISCLAIMER = "本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"


def _run(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _insert_memos(work_dir: Path) -> None:
    store = open_preferences_store(work_dir)
    try:
        store.import_memos(
            [
                FlomoMemo(
                    id="flomo-2026-07-05-1",
                    created_at="2026-07-05T10:00:00+08:00",
                    content="今天买入了一点基金。",
                ),
                FlomoMemo(
                    id="flomo-2026-06-28-1",
                    created_at="2026-06-28T10:00:00+08:00",
                    content="6 月底的 memo，不属于 2026Q3。",
                ),
                FlomoMemo(
                    id="flomo-2026-08-10-1",
                    created_at="2026-08-10T10:00:00+08:00",
                    content="周末爬山，天气很好。",
                ),
            ],
            source_path="sample.html",
            exported_at="2026-08-19",
        )
    finally:
        store.close()


def _insert_questionnaire_result(work_dir: Path, answered_at: str) -> None:
    bank = QuestionBank.load(BANK_PATH)
    answers = {q.id: q.answer for q in bank.questions}
    store = open_preferences_store(work_dir)
    try:
        result = score_questionnaire(bank, answers, answered_at=answered_at)
        save_questionnaire_result(store, result)
    finally:
        store.close()


def _snapshot_dir(work_dir: Path, quarter: str) -> Path:
    return work_dir / "preferences" / "quarters" / quarter


def test_preference_snapshot_success_with_baseline(tmp_path: Path) -> None:
    work_dir = tmp_path / "wd"
    _insert_memos(work_dir)
    _insert_questionnaire_result(work_dir, answered_at="2026-08-01T10:00:00+08:00")
    code, out, err = _run(["preference-snapshot", "--work-dir", str(work_dir), "--quarter", "2026Q3"])
    assert code == SUCCESS_EXIT_CODE
    assert err == ""
    assert "快照已生成 2026Q3" in out
    assert "preference-snapshot.json" in out
    assert "preference-snapshot.md" in out
    assert DISCLAIMER in out

    json_path = _snapshot_dir(work_dir, "2026Q3") / "preference-snapshot.json"
    md_path = _snapshot_dir(work_dir, "2026Q3") / "preference-snapshot.md"
    assert json_path.is_file()
    assert md_path.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["quarter"] == "2026Q3"
    assert payload["questionnaire"] is not None
    assert payload["questionnaire"]["answered_at"] == "2026-08-01T10:00:00+08:00"
    assert payload["questionnaire"]["total_score"] == 100.0
    assert payload["questionnaire"]["risk_level"] == "C5"
    assert set(payload["questionnaire"]["dimension_scores"]) == {
        "基金常识", "投前准备", "系统投资", "投资心态", "实战经验",
    }
    assert payload["behavior_summary"] == [
        {
            "created_at": "2026-07-05T10:00:00+08:00",
            "content": "今天买入了一点基金。",
            "hit_keywords": ["基金", "买入"],
        }
    ]
    assert payload["reflection"] == {
        "actual_actions": "",
        "consistent_with_statement": "",
        "deviation": "",
        "next_adjustments": "",
    }
    assert payload["disclaimer"] == DISCLAIMER
    assert "今天买入了一点基金。" in md_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(work_dir / "preferences" / "preferences.db")
    try:
        rows = conn.execute(
            "SELECT quarter, created_at, questionnaire_result_id, disclaimer FROM preference_snapshots"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "2026Q3"
        assert rows[0][1] is not None
        assert rows[0][2] == "2026-08-01T10:00:00+08:00"
        assert rows[0][3] == DISCLAIMER
    finally:
        conn.close()


def test_preference_snapshot_without_questionnaire_null_baseline(tmp_path: Path) -> None:
    work_dir = tmp_path / "wd"
    _insert_memos(work_dir)
    code, out, err = _run(["preference-snapshot", "--work-dir", str(work_dir), "--quarter", "2026Q3"])
    assert code == SUCCESS_EXIT_CODE
    assert err == ""
    assert "快照已生成 2026Q3" in out

    json_path = _snapshot_dir(work_dir, "2026Q3") / "preference-snapshot.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["questionnaire"] is None
    assert len(payload["behavior_summary"]) == 1


def test_preference_snapshot_invalid_quarter_schema_drift(tmp_path: Path) -> None:
    code, out, err = _run(
        ["preference-snapshot", "--work-dir", str(tmp_path / "wd"), "--quarter", "2026Q5"]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err
    assert "季度格式非法" in err
    assert out == ""

    code2, out2, err2 = _run(
        ["preference-snapshot", "--work-dir", str(tmp_path / "wd"), "--quarter", "2026"]
    )
    assert code2 == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err2
    assert out2 == ""
