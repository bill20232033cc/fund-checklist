"""preference-questionnaire CLI 端到端测试（Slice P2）。"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

from fund_agent.cli.main import CLASSIFIED_FAILURE_EXIT_CODE, SUCCESS_EXIT_CODE, run_cli
from fund_agent.preferences.questionnaire import QuestionBank

BANK_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "fund_agent"
    / "preferences"
    / "questionnaire"
    / "baseline-v1.json"
)


def _run(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _full_answers() -> dict[str, int]:
    bank = QuestionBank.load(BANK_PATH)
    return {q.id: q.answer for q in bank.questions}


def _write_answers(tmp_path: Path, answers: dict[str, int], name: str = "answers.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    return path


def test_preference_questionnaire_success_writes_json_and_db(tmp_path: Path) -> None:
    answers_path = _write_answers(tmp_path, _full_answers())
    code, out, err = _run(
        ["preference-questionnaire", "--work-dir", str(tmp_path / "wd"), "--answers", str(answers_path)]
    )
    assert code == SUCCESS_EXIT_CODE
    assert err == ""
    assert "总分=100.0" in out
    assert "C1-C5=C5" in out
    assert "结果已写入" in out
    assert "已写入偏好数据库" in out
    assert "preferences.db" in out

    results_dir = tmp_path / "wd" / "preferences" / "questionnaire" / "results"
    json_files = list(results_dir.glob("*.json"))
    assert len(json_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["version"] == "baseline-v1"
    assert payload["total_score"] == 100.0
    assert payload["risk_level"] == "C5"
    assert payload["dimension_scores"] == {
        "基金常识": 25.0, "投前准备": 20.0, "系统投资": 20.0, "投资心态": 20.0, "实战经验": 15.0,
    }
    assert set(payload["answers"]) == set(_full_answers())
    assert all(payload["correct"].values())
    assert "不构成投资建议" in payload["disclaimer"]

    conn = sqlite3.connect(tmp_path / "wd" / "preferences" / "preferences.db")
    try:
        rows = conn.execute(
            "SELECT total_score, risk_level, answers_json FROM questionnaire_results"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 100.0
        assert rows[0][1] == "C5"
        assert json.loads(rows[0][2]) == _full_answers()
    finally:
        conn.close()


def test_preference_questionnaire_missing_answers_file_is_not_found(tmp_path: Path) -> None:
    code, out, err = _run(
        ["preference-questionnaire", "--work-dir", str(tmp_path / "wd"), "--answers", str(tmp_path / "missing.json")]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in err
    assert "答案文件不存在" in err
    assert out == ""


def test_preference_questionnaire_invalid_answers_is_schema_drift(tmp_path: Path) -> None:
    answers = _full_answers()
    del answers["q01"]  # 缺失题
    answers_path = _write_answers(tmp_path, answers)
    code, out, err = _run(
        ["preference-questionnaire", "--work-dir", str(tmp_path / "wd"), "--answers", str(answers_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err
    assert "答案缺失题" in err
    assert out == ""

    # 未知题号同样 schema_drift
    bad = _full_answers()
    bad["q99"] = 0
    bad_path = _write_answers(tmp_path, bad, "bad2.json")
    code, _, err2 = _run(
        ["preference-questionnaire", "--work-dir", str(tmp_path / "wd"), "--answers", str(bad_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err2
    assert "未知题号" in err2

    # 索引越界同样 schema_drift
    oob = _full_answers()
    oob["q01"] = 4
    oob_path = _write_answers(tmp_path, oob, "bad3.json")
    code, _, err3 = _run(
        ["preference-questionnaire", "--work-dir", str(tmp_path / "wd"), "--answers", str(oob_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err3


def test_preference_questionnaire_non_tty_without_answers_fails(tmp_path: Path) -> None:
    code, out, err = _run(
        ["preference-questionnaire", "--work-dir", str(tmp_path / "wd")]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in err
    assert "非 TTY" in err
    assert out == ""


def test_preference_questionnaire_custom_bank_not_found(tmp_path: Path) -> None:
    answers_path = _write_answers(tmp_path, _full_answers())
    code, out, err = _run(
        [
            "preference-questionnaire",
            "--work-dir", str(tmp_path / "wd"),
            "--answers", str(answers_path),
            "--bank", str(tmp_path / "missing-bank.json"),
        ]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in err
    assert "题库文件不存在" in err
    assert out == ""


def test_preference_questionnaire_interactive_tty(tmp_path: Path, monkeypatch) -> None:
    """TTY 交互路径：逐题输入答案后评分入库。"""

    class FakeStdin:
        def isatty(self) -> bool:
            return True

    import builtins

    bank = QuestionBank.load(BANK_PATH)
    correct_answers = [str(q.answer) for q in bank.questions]

    def fake_input(prompt: str = "") -> str:
        return correct_answers.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr("sys.stdin", FakeStdin())
    code, out, err = _run(["preference-questionnaire", "--work-dir", str(tmp_path / "wd")])
    assert code == SUCCESS_EXIT_CODE
    assert "总分=100.0" in out
    assert "C1-C5=C5" in out
    assert err == ""

    conn = sqlite3.connect(tmp_path / "wd" / "preferences" / "preferences.db")
    try:
        row = conn.execute("SELECT total_score, risk_level FROM questionnaire_results").fetchone()
        assert row == (100.0, "C5")
    finally:
        conn.close()
