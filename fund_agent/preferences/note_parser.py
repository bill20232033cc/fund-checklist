"""智慧笔记数据导出 HTML 解析器（Slice P4：note-import）。

将智慧笔记小程序导出的 HTML（div 包裹的 Markdown 渲染）解析为结构化
ThoughtNote 列表；仅使用标准库（</div> 换行、去 HTML 标签、html.unescape
后按 Markdown 结构解析），不依赖第三方库。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

_LOCAL_TZ = timezone(timedelta(hours=8))

_EXPORTED_AT_RE = re.compile(r"^导出时间：(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$")
_DECLARED_COUNT_RE = re.compile(r"^总记录数：(\d+) 条$")
_CATEGORY_RE = re.compile(r"^## (.+)$")
_RECORD_RE = re.compile(r"^### (\d+)\.\s*(.+)$")
_TIME_RE = re.compile(
    r"^> (?:分析时间|生成时间)：(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})(?::(\d{2}))?$"
)
_STATUS_RE = re.compile(r"^> 状态：(.*)$")
_TYPE_RE = re.compile(r"^> 类型：(.*)$")

_CATEGORY_KEYS = {
    "分析记录": "analysis",
    "多维度分析": "roundtable",
    "孵化报告": "incubator",
    "结构分析": "structure",
}
_TOC_TITLE = "目录"
_HEADER_SCAN_LIMIT = 20


class NoteParseError(Exception):
    """智慧笔记导出 HTML 结构不匹配的解析失败（schema_drift 语义）。

    参数:
        message: 面向调用方的中文错误说明。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ThoughtNote:
    """一条结构化智慧笔记记录。

    参数:
        id: note-<导出日期 YYYYMMDD>-<category-key>-<序号>。
        category: 类别 key（analysis / roundtable / incubator / structure）。
        title: 记录标题（### 序号. 标题 的标题部分）。
        created_at: 分析时间（ISO8601 +08:00）。
        status: 状态原文（无状态行时取类型值，两者皆无为「未知」）。
        content: 记录全文（保留 **原始问题：**/**分析结果：** 分节与 #### 子节）。
        source: 导出文件相对名。
    """

    id: str
    category: str
    title: str
    created_at: str
    status: str
    content: str
    source: str


@dataclass
class _NoteAccumulator:
    """单条记录的解析中间状态。"""

    seq: int
    title: str
    category: str
    created_at: str | None = None
    status: str | None = None
    type_value: str | None = None
    content_lines: list[str] | None = None

    def __post_init__(self) -> None:
        if self.content_lines is None:
            self.content_lines = []


def _extract_markdown_text(html_text: str) -> list[str]:
    """把 div 包裹的 HTML 转成 Markdown 结构的纯文本行。"""

    text = html_text.replace("</div>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return [line.rstrip() for line in text.splitlines()]


def _to_iso(
    year: str,
    month: str,
    day: str,
    hour: str,
    minute: str,
    second: str | None = None,
) -> str:
    """把分析时间的 YYYY-MM-DD HH:MM(:SS) 转成 ISO8601 +08:00。"""

    moment = datetime(
        int(year),
        int(month),
        int(day),
        int(hour),
        int(minute),
        int(second or 0),
        tzinfo=_LOCAL_TZ,
    )
    return moment.isoformat(timespec="seconds")


def _parse_header(lines: Sequence[str]) -> tuple[str, int]:
    """解析文档头部，返回 (导出日期 YYYY-MM-DD, 声明记录数)。

    异常:
        NoteParseError: 缺少「导出时间」或「总记录数」header 行时抛出。
    """

    exported_at: str | None = None
    declared_count: int | None = None
    seen = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        seen += 1
        if seen > _HEADER_SCAN_LIMIT:
            break
        match = _EXPORTED_AT_RE.match(stripped)
        if match is not None and exported_at is None:
            year, month, day, _, _ = match.groups()
            exported_at = f"{year}-{month}-{day}"
            if declared_count is not None:
                break
            continue
        match = _DECLARED_COUNT_RE.match(stripped)
        if match is not None and declared_count is None:
            declared_count = int(match.group(1))
            if exported_at is not None:
                break
    if exported_at is None:
        raise NoteParseError(
            "未找到「导出时间：YYYY-MM-DD HH:MM」header 行，HTML 结构与智慧笔记导出不符"
        )
    if declared_count is None:
        raise NoteParseError(
            "未找到「总记录数：N 条」header 行，HTML 结构与智慧笔记导出不符"
        )
    return exported_at, declared_count


def parse_note_export(html_text: str, source_path: str) -> list[ThoughtNote]:
    """解析智慧笔记 HTML 导出文本为 ThoughtNote 列表。

    参数:
        html_text: 智慧笔记导出 HTML 全文。
        source_path: 导出文件路径，用于 source 字段的相对名。

    返回:
        按文档顺序排列的 ThoughtNote 列表。

    异常:
    NoteParseError: header 缺失、未知类别（无记录打开时）、记录缺少
        分析时间/生成时间、声明条数与实解析数不一致或解析数为 0 时
        抛出（schema_drift 语义）。
    """

    lines = _extract_markdown_text(html_text)
    exported_at, declared_count = _parse_header(lines)
    export_date_part = exported_at.replace("-", "")
    source_name = str(source_path).rsplit("/", 1)[-1]

    notes: list[ThoughtNote] = []
    category_key: str | None = None
    current: _NoteAccumulator | None = None

    def finalize() -> None:
        nonlocal current
        if current is None:
            return
        if current.created_at is None:
            raise NoteParseError(f"记录「{current.title}」缺少 > 分析时间/生成时间 元数据行")
        status = current.status
        if status is None:
            status = current.type_value if current.type_value is not None else "未知"
        content = "\n".join(current.content_lines or []).strip()
        notes.append(
            ThoughtNote(
                id=f"note-{export_date_part}-{current.category}-{current.seq}",
                category=current.category,
                title=current.title,
                created_at=current.created_at,
                status=status,
                content=content,
                source=source_name,
            )
        )
        current = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current is not None and current.content_lines is not None:
                current.content_lines.append("")
            continue

        category_match = _CATEGORY_RE.match(line)
        if category_match is not None:
            section_title = category_match.group(1).strip()
            if section_title == _TOC_TITLE:
                finalize()
                category_key = None
                continue
            if section_title in _CATEGORY_KEYS:
                finalize()
                category_key = _CATEGORY_KEYS[section_title]
                continue
            if current is None:
                raise NoteParseError(f"未知笔记类别: {section_title}")
            if current.content_lines is not None:
                current.content_lines.append(line)
            continue

        record_match = _RECORD_RE.match(line)
        if record_match is not None:
            finalize()
            if category_key is None:
                raise NoteParseError(
                    f"记录「{record_match.group(2)}」出现在已知类别之外"
                )
            current = _NoteAccumulator(
                seq=int(record_match.group(1)),
                title=record_match.group(2).strip(),
                category=category_key,
            )
            continue

        if current is None:
            continue

        time_match = _TIME_RE.match(line)
        if time_match is not None and current.created_at is None:
            try:
                current.created_at = _to_iso(*time_match.groups())
            except ValueError as exc:
                raise NoteParseError(
                    f"记录「{current.title}」的时间 非法: {line}"
                ) from exc
            continue

        status_match = _STATUS_RE.match(line)
        if status_match is not None and current.status is None:
            current.status = status_match.group(1).strip()
            continue

        type_match = _TYPE_RE.match(line)
        if type_match is not None and current.type_value is None:
            current.type_value = type_match.group(1).strip()
            continue

        if current.content_lines is not None:
            current.content_lines.append(line)

    finalize()
    if not notes:
        raise NoteParseError("未解析到任何记录（0 条）")
    if declared_count != len(notes):
        raise NoteParseError(
            f"声明记录数 {declared_count} 与实际解析数 {len(notes)} 不一致"
        )
    return notes
