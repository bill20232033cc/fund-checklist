"""智慧笔记导出 HTML 解析器的单元测试（Slice P4）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fund_agent.preferences.note_parser import NoteParseError, parse_note_export

FIXTURE_HTML = (
    Path(__file__).parent / "fixtures" / "note_sample.html"
).read_text(encoding="utf-8")
SOURCE_NAME = "note_sample.html"


def _render(body: str, *, exported_at: str = "2026-08-22 10:00", count: str = "5") -> str:
    """构造最小 div 包裹导出 HTML，用于错误路径测试。"""

    return (
        "<div># 智慧笔记 - 数据导出</div>"
        f"<div>导出时间：{exported_at}</div>"
        f"<div>总记录数：{count} 条</div>"
        "<div>## 分析记录</div>"
        f"{body}"
    )


def _record(
    title: str,
    *,
    analysis_time: str | None = "2026-07-01 09:30",
    status: str | None = "已完成",
) -> str:
    """构造一条最小记录块。"""

    parts = [f"<div>### 1. {title}</div>"]
    if analysis_time is not None:
        parts.append(f"<div>> 分析时间：{analysis_time}</div>")
    if status is not None:
        parts.append(f"<div>> 状态：{status}</div>")
    parts.extend(
        [
            "<div>**原始问题：**</div>",
            "<div>问题文本</div>",
            "<div>**分析结果：**</div>",
            "<div>结果文本</div>",
        ]
    )
    return "".join(parts)


def test_parse_note_export_fields_and_category_mapping() -> None:
    notes = parse_note_export(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert len(notes) == 5
    assert [note.category for note in notes] == [
        "analysis",
        "analysis",
        "roundtable",
        "incubator",
        "structure",
    ]
    first = notes[0]
    assert first.title == "一次关于基金定投的思考"
    assert first.created_at == "2026-07-01T09:30:00+08:00"
    assert first.status == "已完成"
    assert first.source == SOURCE_NAME


def test_parse_note_export_ids() -> None:
    notes = parse_note_export(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert [note.id for note in notes] == [
        "note-20260822-analysis-1",
        "note-20260822-analysis-2",
        "note-20260822-roundtable-1",
        "note-20260822-incubator-1",
        "note-20260822-structure-1",
    ]


def test_parse_note_export_created_at_iso8601_plus_0800() -> None:
    notes = parse_note_export(FIXTURE_HTML, source_path=SOURCE_NAME)
    for note in notes:
        assert note.created_at.endswith("+08:00")
        assert "T" in note.created_at


def test_parse_note_export_content_keeps_sections_and_subsections() -> None:
    notes = parse_note_export(FIXTURE_HTML, source_path=SOURCE_NAME)
    roundtable = notes[2]
    assert "**原始问题：**" in roundtable.content
    assert "**分析结果：**" in roundtable.content
    assert roundtable.content.index("**原始问题：**") < roundtable.content.index(
        "**分析结果：**"
    )
    assert "#### 导师一" in roundtable.content
    assert "#### 导师二" in roundtable.content
    assert roundtable.content.index("#### 导师一") > roundtable.content.index(
        "**分析结果：**"
    )


def test_parse_note_export_declared_count_mismatch_raises() -> None:
    html = FIXTURE_HTML.replace("总记录数：5 条", "总记录数：4 条")
    with pytest.raises(NoteParseError, match="不一致"):
        parse_note_export(html, source_path=SOURCE_NAME)


def test_parse_note_export_missing_analysis_time_raises() -> None:
    html = _render(_record("无分析时间", analysis_time=None), count="1")
    with pytest.raises(NoteParseError, match="分析时间"):
        parse_note_export(html, source_path=SOURCE_NAME)


def test_parse_note_export_missing_status_defaults_unknown() -> None:
    html = _render(_record("无状态", status=None), count="1")
    notes = parse_note_export(html, source_path=SOURCE_NAME)
    assert len(notes) == 1
    assert notes[0].status == "未知"


def test_parse_note_export_generated_time_alias() -> None:
    html = _render(
        "<div>### 1. 孵化报告样例</div>"
        "<div>> 生成时间：2026-07-04 12:00</div>"
        "<div>**分析结果：**</div>",
        count="1",
    )
    notes = parse_note_export(html, source_path=SOURCE_NAME)
    assert len(notes) == 1
    assert notes[0].created_at == "2026-07-04T12:00:00+08:00"
    assert notes[0].status == "未知"


def test_parse_note_export_type_line_used_as_status() -> None:
    html = _render(
        "<div>### 1. 结构分析样例</div>"
        "<div>> 分析时间：2026-07-05 15:45</div>"
        "<div>> 类型：product</div>"
        "<div>**分析结果：**</div>",
        count="1",
    )
    notes = parse_note_export(html, source_path=SOURCE_NAME)
    assert len(notes) == 1
    assert notes[0].status == "product"


def test_parse_note_export_content_heading_does_not_end_record() -> None:
    notes = parse_note_export(FIXTURE_HTML, source_path=SOURCE_NAME)
    assert len(notes) == 5
    incubator = notes[3]
    assert incubator.category == "incubator"
    assert incubator.created_at == "2026-07-04T12:00:00+08:00"
    assert incubator.status == "未知"
    assert "## 一、想法内核" in incubator.content
    assert "极简记录是核心，先跑通再扩展。" in incubator.content
    structure = notes[4]
    assert structure.category == "structure"
    assert structure.status == "product"
    assert "## 一、天（外部压力）" in structure.content


def test_parse_note_export_unknown_category_raises() -> None:
    html = (
        "<div># 智慧笔记 - 数据导出</div>"
        "<div>导出时间：2026-08-22 10:00</div>"
        "<div>总记录数：1 条</div>"
        "<div>## 未知类别</div>"
        "<div>### 1. 标题</div>"
        "<div>> 分析时间：2026-07-01 09:30</div>"
        "<div>> 状态：已完成</div>"
    )
    with pytest.raises(NoteParseError, match="未知笔记类别"):
        parse_note_export(html, source_path=SOURCE_NAME)


def test_parse_note_export_zero_records_raises() -> None:
    html = _render("", count="0")
    with pytest.raises(NoteParseError, match="0 条"):
        parse_note_export(html, source_path=SOURCE_NAME)


def test_parse_note_export_missing_header_raises() -> None:
    with pytest.raises(NoteParseError, match="导出时间"):
        parse_note_export("<div>无 header 内容</div>", source_path=SOURCE_NAME)
    html = (
        "<div># 智慧笔记 - 数据导出</div>"
        "<div>总记录数：1 条</div>"
        "<div>## 分析记录</div>"
    )
    with pytest.raises(NoteParseError, match="导出时间"):
        parse_note_export(html, source_path=SOURCE_NAME)
    html = (
        "<div># 智慧笔记 - 数据导出</div>"
        "<div>导出时间：2026-08-22 10:00</div>"
        "<div>## 分析记录</div>"
    )
    with pytest.raises(NoteParseError, match="总记录数"):
        parse_note_export(html, source_path=SOURCE_NAME)
