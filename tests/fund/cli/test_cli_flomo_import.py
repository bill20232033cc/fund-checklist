"""flomo-import CLI 端到端测试（Slice P1）。"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from fund_agent.cli.main import CLASSIFIED_FAILURE_EXIT_CODE, SUCCESS_EXIT_CODE, run_cli

FIXTURE_HTML = Path(__file__).parent.parent / "preferences" / "fixtures" / "flomo_sample.html"


def _run(
    args: list[str],
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_cli(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_flomo_import_success_and_db_rows(tmp_path: Path) -> None:
    code, out, err = _run(
        ["flomo-import", "--html", str(FIXTURE_HTML), "--work-dir", str(tmp_path)]
    )
    assert code == SUCCESS_EXIT_CODE
    assert "imported" in out
    assert "memos=3" in out
    assert "images=2" in out
    assert "preferences.db" in out
    assert err == ""

    conn = sqlite3.connect(tmp_path / "preferences" / "preferences.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
        assert conn.execute("SELECT exported_at FROM imports").fetchone()[0] == "2026-08-19"
    finally:
        conn.close()


def test_flomo_import_repeat_is_cached(tmp_path: Path) -> None:
    args = ["flomo-import", "--html", str(FIXTURE_HTML), "--work-dir", str(tmp_path)]
    first_code, first_out, _ = _run(args)
    second_code, second_out, _ = _run(args)
    assert first_code == SUCCESS_EXIT_CODE
    assert "imported" in first_out
    assert second_code == SUCCESS_EXIT_CODE
    assert "cached" in second_out
    assert "首次导入于" in second_out

    conn = sqlite3.connect(tmp_path / "preferences" / "preferences.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
    finally:
        conn.close()


def test_flomo_import_html_missing_is_not_found(tmp_path: Path) -> None:
    code, out, err = _run(
        ["flomo-import", "--html", str(tmp_path / "missing.html"), "--work-dir", str(tmp_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in err
    assert out == ""


def test_flomo_import_structure_mismatch_is_schema_drift(tmp_path: Path) -> None:
    bad_html = tmp_path / "bad.html"
    bad_html.write_text(
        "<html><body><div class='memos'></div></body></html>", encoding="utf-8"
    )
    code, out, err = _run(
        ["flomo-import", "--html", str(bad_html), "--work-dir", str(tmp_path)]
    )
    assert code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "schema_drift" in err
    assert out == ""


def test_flomo_import_images_dir_missing_only_warns(tmp_path: Path) -> None:
    code, out, err = _run(
        [
            "flomo-import",
            "--html",
            str(FIXTURE_HTML),
            "--work-dir",
            str(tmp_path),
            "--images-dir",
            str(tmp_path / "no_images"),
        ]
    )
    assert code == SUCCESS_EXIT_CODE
    assert "imported" in out
    assert "warning: 图片文件不存在" in err
    assert "file/2026-04-14/sample-a.png" in err
