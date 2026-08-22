"""智慧笔记偏好存储的单元测试（Slice P4）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fund_agent.preferences.flomo_parser import parse_flomo_html
from fund_agent.preferences.note_parser import ThoughtNote, parse_note_export
from fund_agent.preferences.store import PreferencesStoreError, open_preferences_store

FIXTURE_HTML = Path(__file__).parent / "fixtures" / "note_sample.html"
FLOMO_FIXTURE_HTML = Path(__file__).parent / "fixtures" / "flomo_sample.html"
SOURCE_NAME = "note_sample.html"
EXPORTED_AT = "2026-08-22"


def _sample_notes() -> list[ThoughtNote]:
    html = FIXTURE_HTML.read_text(encoding="utf-8")
    return parse_note_export(html, source_path=SOURCE_NAME)


def _connect(tmp_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(tmp_path / "preferences" / "preferences.db")


def test_import_notes_creates_rows_and_fields(tmp_path: Path) -> None:
    notes = _sample_notes()
    store = open_preferences_store(tmp_path)
    try:
        result = store.import_notes(notes, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
    finally:
        store.close()
    assert result.imported is True
    assert result.cached is False
    assert result.record_count == 5
    assert result.memo_count == 5
    assert result.imported_at is not None

    conn = _connect(tmp_path)
    try:
        rows = conn.execute(
            "SELECT id, category, title, created_at, status, content, source "
            "FROM thought_records ORDER BY id"
        ).fetchall()
        assert len(rows) == 5
        assert rows[0][0] == "note-20260822-analysis-1"
        assert rows[0][1] == "analysis"
        assert rows[0][2] == "一次关于基金定投的思考"
        assert rows[0][3] == "2026-07-01T09:30:00+08:00"
        assert rows[0][4] == "已完成"
        assert "**原始问题：**" in rows[0][5]
        assert rows[0][6] == SOURCE_NAME

        imports = conn.execute(
            "SELECT source_path, fingerprint, exported_at, record_count, imported_at "
            "FROM note_imports"
        ).fetchall()
        assert len(imports) == 1
        assert imports[0][0] == SOURCE_NAME
        assert len(imports[0][1]) == 64
        assert imports[0][2] == EXPORTED_AT
        assert imports[0][3] == 5
        assert imports[0][4] is not None
    finally:
        conn.close()


def test_import_notes_idempotent_cached_no_overwrite(tmp_path: Path) -> None:
    notes = _sample_notes()
    store = open_preferences_store(tmp_path)
    try:
        first = store.import_notes(notes, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
        second = store.import_notes(notes, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
    finally:
        store.close()
    assert first.imported is True
    assert second.imported is False
    assert second.cached is True
    assert second.record_count == 5
    assert second.imported_at == first.imported_at

    conn = _connect(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM thought_records").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM note_imports").fetchone()[0] == 1
    finally:
        conn.close()


def test_import_notes_different_content_different_fingerprint(tmp_path: Path) -> None:
    notes = _sample_notes()
    changed = [
        ThoughtNote(
            id=note.id,
            category=note.category,
            title=note.title,
            created_at=note.created_at,
            status=note.status,
            content="【修改】" + note.content,
            source=note.source,
        )
        for note in notes
    ]
    store_a = open_preferences_store(tmp_path / "a")
    store_b = open_preferences_store(tmp_path / "b")
    try:
        store_a.import_notes(notes, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
        store_b.import_notes(changed, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
    finally:
        store_a.close()
        store_b.close()

    conn_a = sqlite3.connect(tmp_path / "a" / "preferences" / "preferences.db")
    conn_b = sqlite3.connect(tmp_path / "b" / "preferences" / "preferences.db")
    try:
        fingerprint_a = conn_a.execute("SELECT fingerprint FROM note_imports").fetchone()[0]
        fingerprint_b = conn_b.execute("SELECT fingerprint FROM note_imports").fetchone()[0]
        assert fingerprint_a != fingerprint_b
    finally:
        conn_a.close()
        conn_b.close()


def test_import_notes_same_ids_different_exported_at_fails_closed(tmp_path: Path) -> None:
    notes = _sample_notes()
    store = open_preferences_store(tmp_path)
    try:
        first = store.import_notes(notes, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
        with pytest.raises(PreferencesStoreError):
            store.import_notes(notes, source_path=SOURCE_NAME, exported_at="2026-08-23")
    finally:
        store.close()
    assert first.imported is True

    conn = _connect(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM thought_records").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM note_imports").fetchone()[0] == 1
    finally:
        conn.close()


def test_import_notes_coexists_with_memos(tmp_path: Path) -> None:
    notes = _sample_notes()
    memos = parse_flomo_html(
        FLOMO_FIXTURE_HTML.read_text(encoding="utf-8"),
        source_path="flomo_sample.html",
    )
    store = open_preferences_store(tmp_path)
    try:
        note_result = store.import_notes(notes, source_path=SOURCE_NAME, exported_at=EXPORTED_AT)
        memo_result = store.import_memos(memos, source_path="flomo_sample.html", exported_at="2026-08-19")
    finally:
        store.close()
    assert note_result.imported is True
    assert memo_result.imported is True

    conn = _connect(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM thought_records").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM note_imports").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
    finally:
        conn.close()


def test_open_preferences_store_upgrades_legacy_db_keeps_memos(tmp_path: Path) -> None:
    prefs_dir = tmp_path / "preferences"
    prefs_dir.mkdir(parents=True)
    legacy = sqlite3.connect(prefs_dir / "preferences.db")
    try:
        legacy.execute(
            "CREATE TABLE memos ("
            "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, content TEXT NOT NULL, "
            "images_json TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL)"
        )
        legacy.execute(
            "INSERT INTO memos (id, created_at, content, images_json, source) "
            "VALUES ('legacy-1', '2026-01-01T00:00:00+08:00', '旧数据', '[]', 'old.html')"
        )
        legacy.commit()
    finally:
        legacy.close()

    store = open_preferences_store(tmp_path)
    try:
        result = store.import_notes(
            _sample_notes(), source_path=SOURCE_NAME, exported_at=EXPORTED_AT
        )
    finally:
        store.close()
    assert result.imported is True

    conn = _connect(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM thought_records").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM note_imports").fetchone()[0] == 1
        legacy_row = conn.execute(
            "SELECT id, content FROM memos WHERE id = 'legacy-1'"
        ).fetchone()
        assert legacy_row == ("legacy-1", "旧数据")
    finally:
        conn.close()
