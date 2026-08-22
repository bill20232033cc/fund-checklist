"""Flomo 偏好存储的单元测试（Slice P1）。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from fund_agent.preferences.flomo_parser import FlomoMemo, parse_flomo_html
from fund_agent.preferences.store import PreferencesStoreError, open_preferences_store

FIXTURE_HTML = Path(__file__).parent / "fixtures" / "flomo_sample.html"
SOURCE_NAME = "flomo_sample.html"


def _sample_memos() -> list[FlomoMemo]:
    html = FIXTURE_HTML.read_text(encoding="utf-8")
    return parse_flomo_html(html, source_path=SOURCE_NAME)


def _connect(tmp_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(tmp_path / "preferences" / "preferences.db")


def test_import_memos_creates_rows_and_fields(tmp_path: Path) -> None:
    memos = _sample_memos()
    store = open_preferences_store(tmp_path)
    try:
        result = store.import_memos(memos, source_path=SOURCE_NAME, exported_at="2026-08-19")
    finally:
        store.close()
    assert result.imported is True
    assert result.cached is False
    assert result.memo_count == 3
    assert result.image_count == 2
    assert result.imported_at is not None

    conn = _connect(tmp_path)
    try:
        rows = conn.execute(
            "SELECT id, created_at, content, images_json, source FROM memos ORDER BY id"
        ).fetchall()
        assert len(rows) == 3
        assert rows[0][0] == "flomo-2026-04-14-1"
        assert rows[0][1] == "2026-04-14T19:22:20+08:00"
        assert rows[0][2] == "第一条 memo 文本。\n第二段，含\n换行。"
        assert json.loads(rows[0][3]) == []
        assert rows[0][4].startswith(f"{SOURCE_NAME}:")

        images_json = conn.execute(
            "SELECT images_json FROM memos WHERE id = 'flomo-2026-04-14-2'"
        ).fetchone()[0]
        assert json.loads(images_json) == [
            "file/2026-04-14/sample-a.png",
            "file/2026-04-14/sample-b.jpg",
        ]

        imports = conn.execute(
            "SELECT source_path, fingerprint, exported_at, memo_count, imported_at FROM imports"
        ).fetchall()
        assert len(imports) == 1
        assert imports[0][0] == SOURCE_NAME
        assert len(imports[0][1]) == 64
        assert imports[0][2] == "2026-08-19"
        assert imports[0][3] == 3
        assert imports[0][4] is not None
    finally:
        conn.close()


def test_import_memos_idempotent_cached_no_overwrite(tmp_path: Path) -> None:
    memos = _sample_memos()
    store = open_preferences_store(tmp_path)
    try:
        first = store.import_memos(memos, source_path=SOURCE_NAME, exported_at="2026-08-19")
        second = store.import_memos(memos, source_path=SOURCE_NAME, exported_at="2026-08-19")
    finally:
        store.close()
    assert first.imported is True
    assert second.imported is False
    assert second.cached is True
    assert second.memo_count == 3
    assert second.imported_at == first.imported_at

    conn = _connect(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
    finally:
        conn.close()


def test_import_memos_different_content_different_fingerprint(tmp_path: Path) -> None:
    memos = _sample_memos()
    changed = [
        FlomoMemo(
            id=memo.id,
            created_at=memo.created_at,
            content=memo.content + " 追加",
            images=list(memo.images),
            source=memo.source,
        )
        for memo in memos
    ]
    store_a = open_preferences_store(tmp_path / "a")
    store_b = open_preferences_store(tmp_path / "b")
    try:
        store_a.import_memos(memos, source_path=SOURCE_NAME, exported_at="2026-08-19")
        store_b.import_memos(changed, source_path=SOURCE_NAME, exported_at="2026-08-19")
    finally:
        store_a.close()
        store_b.close()

    conn_a = sqlite3.connect(tmp_path / "a" / "preferences" / "preferences.db")
    conn_b = sqlite3.connect(tmp_path / "b" / "preferences" / "preferences.db")
    try:
        fingerprint_a = conn_a.execute("SELECT fingerprint FROM imports").fetchone()[0]
        fingerprint_b = conn_b.execute("SELECT fingerprint FROM imports").fetchone()[0]
        assert fingerprint_a != fingerprint_b
    finally:
        conn_a.close()
        conn_b.close()


def test_open_preferences_store_work_dir_is_file_raises(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(PreferencesStoreError):
        open_preferences_store(blocker)
