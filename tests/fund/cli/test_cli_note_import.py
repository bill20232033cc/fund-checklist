"""note-import CLI 端到端测试（Slice P4）。"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from fund_agent.cli.main import CLASSIFIED_FAILURE_EXIT_CODE, SUCCESS_EXIT_CODE, run_cli

FIXTURE_HTML = Path(__file__).parent.parent / "preferences" / "fixtures" / "note_sample.html"


def _run(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_note_import_success_and_db_rows(tmp_path: Path) -> None:
    code, out, err = _run(
        ["note-import", "--html", str(FIXTURE_HTML), "--work-dir", str(tmp_path)]
    )
    assert code == SUCCESS_EXIT_CODE
    assert "imported" in out
    assert "records=5" in out
    assert "preferences.db" in out
    assert err == ""

    conn = sqlite3.connect(tmp_path / "preferences" / "preferences.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM thought_records").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM note_imports").fetchone()[0] == 1
        assert conn.execute("SELECT exported_at FROM note_imports").fetchone()[0] == "2026-08-22"
    finally:
        conn.close()


def test_note_import_repeat_is_cached(tmp_path: Path) -> None:
    args = ["note-import", "--html", str(FIXTURE_HTML), "--work-dir", str(tmp_path)]
    first_code, first_out, _ = _run(args)
    second_code, second_out, _ = _run(args)
    assert first_code == SUCCESS_EXIT_CODE
    assert "imported" in first_out
    assert second_code == SUCCESS_EXIT_CODE
    assert "cached" in second_out
    assert "首次导入于" in second_out

    conn = sqlite3.connect(tmp_path / "preferences" / "preferences.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM thought_records").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM note_imports").fetchone()[0] == 1
    finally:
        conn.close()


def test_note_import_html_missing_is_not_found(tmp_path: Path) -> None:
    code, out, err = _run(
        ["note-import", "--html", str(tmp_path / "missing.html"), "--work-dir", str(tmp_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in err
    assert out == ""


def test_note_import_structure_mismatch_is_schema_drift(tmp_path: Path) -> None:
    bad_html = tmp_path / "bad.html"
    bad_html.write_text(
        "<html><body><div>no structure</div></body></html>", encoding="utf-8"
    )
    code, out, err = _run(
        ["note-import", "--html", str(bad_html), "--work-dir", str(tmp_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err
    assert out == ""
