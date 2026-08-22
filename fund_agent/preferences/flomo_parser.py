"""Flomo HTML 导出解析器（Slice P1：flomo-import）。

将 Flomo 导出的 HTML 解析为结构化 memo 列表；仅使用标准库
html.parser.HTMLParser 状态机，不依赖第三方库。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence

_TIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$")
_HEADER_DATE_RE = re.compile(r"于\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*导出\s*(\d+)\s*条\s*MEMO")


class FlomoParseError(Exception):
    """Flomo HTML 结构不匹配的解析失败（schema_drift 语义）。

    参数:
        message: 面向调用方的中文错误说明。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class FlomoMemo:
    """一条结构化 Flomo memo。

    参数:
        id: flomo-<YYYY-MM-DD>-<序号>；同日序号从 1 递增。
        created_at: ISO8601 时间（+08:00）。
        content: 纯文本正文；段落/换行转 \\n，列表层级转缩进项目符号。
        images: 图片相对路径数组（相对导出根目录，保留原文件名）。
        source: 导出文件相对名 + HTML 内字符偏移，供溯源。
    """

    id: str
    created_at: str
    content: str
    images: list[str] = field(default_factory=list)
    source: str = ""


@dataclass(frozen=True)
class FlomoParseResult:
    """Flomo 导出解析结果。

    参数:
        memos: 解析出的 memo 列表（按文档顺序）。
        exported_at: header .date 声明的导出日期（YYYY-MM-DD）；缺失为 None。
        declared_memo_count: header .date 声明的 memo 条数；缺失为 None。
    """

    memos: tuple[FlomoMemo, ...]
    exported_at: str | None = None
    declared_memo_count: int | None = None


@dataclass
class _MemoAccumulator:
    """单条 memo 的解析中间状态。"""

    content_parts: list[str] = field(default_factory=list)
    time_parts: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    offset: int = 0


class _FlomoHtmlParser(HTMLParser):
    """基于状态机的 Flomo HTML 解析器。

    状态：header .date / 当前 .memo 容器 / .time / .content / .files /
    列表嵌套深度；结构不匹配时抛出 FlomoParseError。
    """

    def __init__(self, source_path: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source_path = source_path
        self._line_starts: list[int] | None = None
        self._header_date_parts: list[str] = []
        self._in_header_date = False
        self._memo_div_depth = 0
        self._in_time = False
        self._in_content = False
        self._in_files = False
        self._list_depth = 0
        self._memo: _MemoAccumulator | None = None
        self.memos: list[FlomoMemo] = []

    def _char_offset(self) -> int:
        """返回当前解析位置在 HTML 文本中的字符偏移。"""

        if self._line_starts is None:
            line_starts: list[int] = []
            position = 0
            for line in self.rawdata.splitlines(keepends=True):
                line_starts.append(position)
                position += len(line)
            self._line_starts = line_starts
        lineno, column = self.getpos()
        if lineno - 1 < len(self._line_starts):
            return self._line_starts[lineno - 1] + column
        return 0

    def _emit_newline(self) -> None:
        """在 content 缓冲末尾追加换行（若尚未以换行结尾）。"""

        if self._memo is None:
            return
        parts = self._memo.content_parts
        if parts and not parts[-1].endswith("\n"):
            parts.append("\n")

    def _emit_bullet(self) -> None:
        """按列表层级追加缩进项目符号。"""

        if self._memo is None:
            return
        parts = self._memo.content_parts
        if parts and not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.append("  " * self._list_depth + "- ")

    def _emit_text(self, text: str) -> None:
        """追加纯文本片段，相邻片段以单空格连接。"""

        if self._memo is None:
            return
        parts = self._memo.content_parts
        if parts and not parts[-1].endswith((" ", "\n")):
            parts.append(" ")
        parts.append(text)

    def _finalize_memo(self) -> None:
        """收尾当前 memo：校验 .time 并生成 FlomoMemo。"""

        if self._memo is None:
            return
        time_text = "".join(self._memo.time_parts).strip()
        match = _TIME_RE.match(time_text)
        if not match:
            raise FlomoParseError(
                f"memo 缺少合法 .time 时间（要求 YYYY-MM-DD HH:MM:SS）: {time_text or '<空>'}"
            )
        year, month, day, hour, minute, second = match.groups()
        content = "".join(self._memo.content_parts).strip()
        self.memos.append(
            FlomoMemo(
                id="",
                created_at=f"{year}-{month}-{day}T{hour}:{minute}:{second}+08:00",
                content=content,
                images=list(self._memo.images),
                source=f"{Path(self._source_path).name}:{self._memo.offset}",
            )
        )
        self._memo = None
        self._in_time = False
        self._in_content = False
        self._in_files = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理开始标签，维护 memo/time/content/files 状态。"""

        classes = {value for key, value in attrs if key == "class" and value}
        if tag == "div":
            if "memo" in classes:
                if self._memo_div_depth > 0:
                    self._finalize_memo()
                self._memo_div_depth = 1
                self._memo = _MemoAccumulator(offset=self._char_offset())
            elif "date" in classes:
                self._in_header_date = True
            elif self._memo_div_depth > 0:
                self._memo_div_depth += 1
                if "time" in classes:
                    self._in_time = True
                elif "content" in classes:
                    self._in_content = True
                elif "files" in classes:
                    self._in_files = True
        elif tag in ("ul", "ol"):
            if self._in_content:
                self._list_depth += 1
        elif tag == "li":
            if self._in_content:
                self._emit_bullet()
        elif tag == "br":
            if self._in_content:
                self._emit_newline()
        elif tag == "p":
            if self._in_content:
                self._emit_newline()
        elif tag == "img":
            if self._memo is not None and (self._in_content or self._in_files):
                for key, value in attrs:
                    if key == "src" and value:
                        src = value[2:] if value.startswith("./") else value
                        self._memo.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        """处理结束标签，收尾容器状态。"""

        if tag == "div":
            if self._in_header_date:
                self._in_header_date = False
            elif self._memo_div_depth > 0:
                if self._in_time:
                    self._in_time = False
                elif self._in_content:
                    self._in_content = False
                elif self._in_files:
                    self._in_files = False
                self._memo_div_depth -= 1
                if self._memo_div_depth == 0:
                    self._finalize_memo()
        elif tag in ("ul", "ol") and self._list_depth > 0:
            self._list_depth -= 1

    def handle_data(self, data: str) -> None:
        """按当前状态收集文本数据。"""

        if self._in_header_date:
            self._header_date_parts.append(data)
        elif self._in_time and self._memo is not None:
            self._memo.time_parts.append(data)
        elif self._in_content and self._memo is not None:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self._emit_text(text)

    def close(self) -> None:
        """结束解析：收尾未闭合 memo 并分配 memo id。"""

        super().close()
        if self._memo is not None:
            self._finalize_memo()
        if not self.memos:
            raise FlomoParseError("未找到 .memo 容器，HTML 结构与 Flomo 导出不符")
        counters: dict[str, int] = {}
        assigned: list[FlomoMemo] = []
        for memo in self.memos:
            date = memo.created_at[:10]
            counters[date] = counters.get(date, 0) + 1
            assigned.append(replace(memo, id=f"flomo-{date}-{counters[date]}"))
        self.memos = assigned

    def export_header(self) -> tuple[str | None, int | None]:
        """解析 header .date 文本，返回 (exported_at, declared_memo_count)。"""

        text = "".join(self._header_date_parts).strip()
        match = _HEADER_DATE_RE.search(text)
        if not match:
            return None, None
        year, month, day, count = match.groups()
        exported_at = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return exported_at, int(count)


def _parse(html_text: str, source_path: str) -> FlomoParseResult:
    """执行一次完整解析并返回结果。"""

    parser = _FlomoHtmlParser(source_path)
    parser.feed(html_text)
    parser.close()
    exported_at, declared_memo_count = parser.export_header()
    return FlomoParseResult(
        memos=tuple(parser.memos),
        exported_at=exported_at,
        declared_memo_count=declared_memo_count,
    )


def parse_flomo_html(html_text: str, source_path: str) -> list[FlomoMemo]:
    """解析 Flomo HTML 导出文本为 memo 列表。

    参数:
        html_text: Flomo 导出 HTML 全文。
        source_path: 导出文件路径，用于 source 字段的相对名。

    返回:
        按文档顺序排列的 FlomoMemo 列表。

    异常:
        FlomoParseError: 未找到 .memo 容器或 memo 缺少 .time 时抛出。
    """

    return list(_parse(html_text, source_path).memos)


def parse_flomo_export(html_text: str, source_path: str) -> FlomoParseResult:
    """解析 Flomo HTML 导出文本为完整解析结果。

    参数:
        html_text: Flomo 导出 HTML 全文。
        source_path: 导出文件路径，用于 source 字段的相对名。

    返回:
        FlomoParseResult，含 memo 列表与 header 声明的导出日期/条数。

    异常:
        FlomoParseError: 未找到 .memo 容器或 memo 缺少 .time 时抛出。
    """

    return _parse(html_text, source_path)
