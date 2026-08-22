"""Flomo HTML 解析器的单元测试（Slice P1）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fund_agent.preferences.flomo_parser import (
    FlomoParseError,
    parse_flomo_export,
    parse_flomo_html,
)

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "flomo_sample.html").read_text(
    encoding="utf-8"
)
SOURCE_NAME = "flomo_sample.html"


def test_parse_flomo_html_fixture_fields() -> None:
    memos = parse_flomo_html(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert len(memos) == 3
    first = memos[0]
    assert first.id == "flomo-2026-04-14-1"
    assert first.created_at == "2026-04-14T19:22:20+08:00"
    assert first.content == "第一条 memo 文本。\n第二段，含\n换行。"
    assert first.images == []
    assert first.source.startswith(f"{SOURCE_NAME}:")
    assert int(first.source.split(":", 1)[1]) > 0


def test_parse_flomo_html_collects_content_and_files_images() -> None:
    memos = parse_flomo_html(FIXTURE_HTML, source_path=SOURCE_NAME)
    second = memos[1]
    assert second.content == "图片 memo。"
    assert second.images == [
        "file/2026-04-14/sample-a.png",
        "file/2026-04-14/sample-b.jpg",
    ]


def test_parse_flomo_html_list_indentation() -> None:
    memos = parse_flomo_html(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert memos[2].content == "- 第一项\n  - 第二项\n  - 有序一\n结尾段落。"


def test_parse_flomo_html_same_day_id_increments() -> None:
    memos = parse_flomo_html(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert [memo.id for memo in memos] == [
        "flomo-2026-04-14-1",
        "flomo-2026-04-14-2",
        "flomo-2026-04-15-1",
    ]


def test_parse_flomo_html_created_at_iso8601_plus_0800() -> None:
    memos = parse_flomo_html(FIXTURE_HTML, source_path=SOURCE_NAME)
    for memo in memos:
        assert memo.created_at.endswith("+08:00")
        assert "T" in memo.created_at


def test_parse_flomo_export_header() -> None:
    result = parse_flomo_export(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert result.exported_at == "2026-08-19"
    assert result.declared_memo_count == 3
    assert len(result.memos) == 3


def test_parse_flomo_html_no_memo_raises() -> None:
    html = "<html><body><div class='memos'></div></body></html>"
    with pytest.raises(FlomoParseError, match=".memo"):
        parse_flomo_html(html, source_path="empty.html")


def test_parse_flomo_html_missing_time_raises() -> None:
    html = (
        "<div class='memo'>"
        "<div class='content'><p>无时间</p></div>"
        "<div class='files'></div>"
        "</div>"
    )
    with pytest.raises(FlomoParseError, match=".time"):
        parse_flomo_html(html, source_path="no_time.html")
