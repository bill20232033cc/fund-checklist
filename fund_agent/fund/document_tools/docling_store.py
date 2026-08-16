"""Docling JSON 的受控文档存储与读取投影。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from fund_agent.fund.document_tools.bm25f_scorer import BM25FScorer, BM25FUnit, tokenize
from fund_agent.fund.document_tools.constants import (
    BM25F_FIELD_CAPTION,
    BM25F_FIELD_ROWS,
    BM25F_FIELD_TEXT,
    BM25F_FIELD_TITLE,
    DEFAULT_SEARCH_EXCERPT_CHARS,
    DEFAULT_SEARCH_MAX_RESULTS,
    DEFAULT_SECTION_MAX_CHARS,
    DEFAULT_SECTION_PREVIEW_CHARS,
    DEFAULT_TABLE_MAX_ROWS,
    SECTION_HEADER_LABEL,
    FailureCode,
    LocatorKind,
)
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import (
    Citation,
    Locator,
    ParserHealth,
    ReportIdentity,
    SearchMatchKind,
    SearchResult,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)

_TABLE_SEARCH_SOURCE_ORDER_OFFSET = 10_000
_TABLE_SEARCH_ROW_ORDER_OFFSET = 100


@dataclass(frozen=True)
class _ParsedSection:
    """Docling texts[] 解析出的内部章节模型。"""

    section_ref: str
    title: str
    level: int
    parent_ref: str | None
    text: str
    locator: Locator
    source_index: int


@dataclass(frozen=True)
class _ParsedTable:
    """Docling tables[] 解析出的内部表格模型。"""

    table_ref: str
    caption: str | None
    section_ref: str | None
    rows: tuple[tuple[str, ...], ...]
    locator: Locator
    source_index: int


@dataclass(frozen=True)
class _SearchCandidate:
    """内部搜索候选，统一 section 和 table 投影。"""

    score: int
    source_order: int
    section_ref: str
    table_ref: str | None
    title: str
    excerpt: str
    locator: Locator
    match_kind: SearchMatchKind
    row_index: int | None = None


class DoclingDocumentStore:
    """从 Docling JSON 构建受控 section/table/search 读取模型。

    参数:
        identity: 年报内容身份，用于 citation。
        json_path: Fund 层内部 Docling JSON 路径；不得暴露给上层。

    返回:
        已通过 parser_health 的 store 实例。

    异常:
        DocumentToolError: JSON 不可读、schema drift 或 parser health 失败时抛出稳定
            failure code。
    """

    def __init__(self, *, identity: ReportIdentity, json_path: Path) -> None:
        """加载 Docling JSON，并立即执行 parser_health。"""

        self._identity = identity
        self._raw = _load_docling_json(Path(json_path))
        self._texts = _require_docling_list(self._raw, "texts")
        self._tables = _require_docling_list(self._raw, "tables")
        self._sections = _parse_sections(identity, self._texts)
        self._tables_model = _parse_tables(identity, self._tables, self._texts, self._sections)
        self._health = _build_parser_health(self._texts, self._sections, self._tables_model)
        self._bm25f_scorer = BM25FScorer(
            _build_bm25f_units(self._sections, self._tables_model)
        )

    @property
    def identity(self) -> ReportIdentity:
        return self._identity

    @property
    def parser_health(self) -> ParserHealth:
        """返回已通过的 parser health 摘要。

        参数:
            无。

        返回:
            ParserHealth，不包含 raw Docling payload。

        异常:
            本属性不抛出业务异常；构造期已 fail-closed。
        """

        return self._health

    def list_sections(self) -> tuple[SectionSummary, ...]:
        """列出受控章节摘要。

        参数:
            无。

        返回:
            SectionSummary 元组，包含 locator 和有界 preview。

        异常:
            本方法不抛出业务异常。
        """

        return tuple(
            SectionSummary(
                section_ref=section.section_ref,
                title=section.title,
                level=section.level,
                parent_ref=section.parent_ref,
                locator=section.locator,
                preview=_bounded(section.text, DEFAULT_SECTION_PREVIEW_CHARS)[0],
            )
            for section in self._sections
        )

    def read_section(self, section_ref: str, *, max_chars: int | None = None) -> SectionContent:
        """读取单个章节的有界正文。

        参数:
            section_ref: 受控章节引用。
            max_chars: 最大返回字符数；None 使用默认上限。

        返回:
            SectionContent，包含 citation 和 truncated 标记。

        异常:
            DocumentToolError: 章节不存在时返回 not_found。
        """

        section = self._find_section(section_ref)
        text, truncated = _bounded(section.text, max_chars or DEFAULT_SECTION_MAX_CHARS)
        return SectionContent(
            section_ref=section.section_ref,
            title=section.title,
            text=text,
            truncated=truncated,
            locator=section.locator,
            citation=self._citation(section.locator),
        )

    def list_tables(self, *, within_section_ref: str | None = None) -> tuple[TableSummary, ...]:
        """列出表格摘要。

        参数:
            within_section_ref: 可选章节过滤。

        返回:
            TableSummary 元组；表格可为空。

        异常:
            DocumentToolError: 指定章节不存在时返回 not_found。
        """

        if within_section_ref is not None:
            self._find_section(within_section_ref)
        tables = (
            table
            for table in self._tables_model
            if within_section_ref is None or table.section_ref == within_section_ref
        )
        return tuple(
            TableSummary(
                table_ref=table.table_ref,
                caption=table.caption,
                section_ref=table.section_ref,
                locator=table.locator,
                row_count=len(table.rows),
                column_count=max((len(row) for row in table.rows), default=0),
            )
            for table in tables
        )

    def read_table(self, table_ref: str, *, max_rows: int | None = None) -> TableContent:
        """读取单个表格的有界行内容。

        参数:
            table_ref: 受控表格引用。
            max_rows: 最大返回行数；None 使用默认上限。

        返回:
            TableContent，包含 citation 和 truncated 标记。

        异常:
            DocumentToolError: 表格不存在时返回 not_found。
        """

        table = self._find_table(table_ref)
        limit = max_rows or DEFAULT_TABLE_MAX_ROWS
        rows = table.rows[:limit]
        return TableContent(
            table_ref=table.table_ref,
            caption=table.caption,
            section_ref=table.section_ref,
            rows=rows,
            truncated=len(table.rows) > limit,
            locator=table.locator,
            citation=self._citation(table.locator),
        )

    def search(
        self,
        query: str,
        *,
        within_section_ref: str | None = None,
        max_results: int | None = None,
    ) -> tuple[SearchResult, ...]:
        """在章节和有界表格投影中做简单可解释文本检索。

        参数:
            query: 查询字符串。
            within_section_ref: 可选章节过滤。
            max_results: 最大返回条数；None 使用默认上限。

        返回:
            SearchResult 元组，按命中次数和章节顺序排序。

        异常:
            DocumentToolError: 指定章节不存在时返回 not_found。
        """

        normalized_query = query.strip()
        if not normalized_query:
            return ()
        if within_section_ref is not None:
            self._find_section(within_section_ref)
        candidates = _section_search_candidates(
            self._identity.document_id,
            self._sections,
            normalized_query,
            within_section_ref=within_section_ref,
        )
        candidates.extend(
            _table_search_candidates(
                self._tables_model,
                normalized_query,
                within_section_ref=within_section_ref,
            )
        )
        query_terms = tokenize(normalized_query)
        candidates.sort(
            key=lambda item: (
                -self._bm25f_score(item, query_terms),
                -item.score,
                item.source_order,
            )
        )

        results: list[SearchResult] = []
        for rank, candidate in enumerate(candidates[: max_results or DEFAULT_SEARCH_MAX_RESULTS], start=1):
            results.append(
                SearchResult(
                    rank=rank,
                    section_ref=candidate.section_ref,
                    title=candidate.title,
                    excerpt=candidate.excerpt,
                    locator=candidate.locator,
                    citation=self._citation(candidate.locator),
                    match_kind=candidate.match_kind,
                    table_ref=candidate.table_ref,
                )
            )
        return tuple(results)

    def _find_section(self, section_ref: str) -> _ParsedSection:
        """按 section_ref 查找内部章节模型。"""

        for section in self._sections:
            if section.section_ref == section_ref:
                return section
        raise DocumentToolError(FailureCode.NOT_FOUND, "章节不存在")

    def _find_table(self, table_ref: str) -> _ParsedTable:
        """按 table_ref 查找内部表格模型。"""

        for table in self._tables_model:
            if table.table_ref == table_ref:
                return table
        raise DocumentToolError(FailureCode.NOT_FOUND, "表格不存在")

    def _bm25f_score(self, candidate: _SearchCandidate, query_terms: list[str]) -> float:
        """按候选命中字段计算 BM25F 重排序分数；无法解析字段时返回 0.0。"""

        fields: dict[str, str] = {}
        if candidate.match_kind is SearchMatchKind.SECTION_TEXT:
            section = self._find_section(candidate.section_ref)
            fields = {BM25F_FIELD_TITLE: section.title, BM25F_FIELD_TEXT: section.text}
        elif candidate.match_kind is SearchMatchKind.TABLE_CAPTION:
            table = self._find_table(candidate.table_ref)
            fields = {BM25F_FIELD_CAPTION: table.caption or ""}
        elif candidate.match_kind is SearchMatchKind.TABLE_ROW and candidate.row_index is not None:
            table = self._find_table(candidate.table_ref)
            fields = {BM25F_FIELD_ROWS: _table_row_text(table.rows[candidate.row_index])}
        return self._bm25f_scorer.score(fields, query_terms)

    def _citation(self, locator: Locator) -> Citation:
        """基于身份和 locator 组装 citation。"""

        return Citation(
            document_id=self._identity.document_id,
            fund_code=self._identity.fund_code,
            fund_name=self._identity.fund_name,
            year=self._identity.year,
            report_type=self._identity.report_type.value,
            locator=locator,
        )


def _load_docling_json(json_path: Path) -> dict[str, object]:
    """读取 Docling JSON 并校验顶层对象类型。"""

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DocumentToolError(FailureCode.NOT_FOUND, "Docling JSON 不存在") from exc
    except OSError as exc:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling JSON 暂不可读") from exc
    except json.JSONDecodeError as exc:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling JSON 不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling JSON 顶层结构不符合契约")
    return payload


def _require_docling_list(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    """读取顶层列表字段，并要求元素为对象。"""

    value = payload.get(key)
    if not isinstance(value, list):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, f"Docling JSON 缺少 {key}[]")
    if not all(isinstance(item, dict) for item in value):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, f"Docling JSON {key}[] 元素不是对象")
    return value


def _parse_sections(identity: ReportIdentity, texts: list[dict[str, object]]) -> tuple[_ParsedSection, ...]:
    """从 Docling texts[] 解析章节；无标题时用全文替代索引。"""

    readable_indexes = [index for index, item in enumerate(texts) if _text_of(item)]
    header_indexes = [
        index for index in readable_indexes if str(texts[index].get("label") or "") == SECTION_HEADER_LABEL
    ]
    if not readable_indexes:
        return ()
    if not header_indexes:
        text = "\n".join(_text_of(texts[index]) for index in readable_indexes)
        locator = _locator_from_item(
            identity.document_id,
            LocatorKind.SECTION,
            texts[readable_indexes[0]],
            section_ref="section-0000",
            table_ref=None,
        )
        return (
            _ParsedSection(
                section_ref="section-0000",
                title="全文",
                level=1,
                parent_ref=None,
                text=text,
                locator=locator,
                source_index=readable_indexes[0],
            ),
        )

    sections: list[_ParsedSection] = []
    parent_stack: list[tuple[int, str]] = []
    for header_position, text_index in enumerate(header_indexes):
        header = texts[text_index]
        level = _positive_int(header.get("level"), default=1)
        while parent_stack and parent_stack[-1][0] >= level:
            parent_stack.pop()
        parent_ref = parent_stack[-1][1] if parent_stack else None
        section_ref = f"section-{text_index:04d}"
        end_index = _section_end_index(texts, header_indexes, header_position, level)
        section_text = "\n".join(
            _text_of(item)
            for item in texts[text_index:end_index]
            if _text_of(item)
        )
        locator = _locator_from_item(
            identity.document_id,
            LocatorKind.SECTION,
            header,
            section_ref=section_ref,
            table_ref=None,
            page_range=_page_range(texts[text_index:end_index]),
        )
        sections.append(
            _ParsedSection(
                section_ref=section_ref,
                title=_text_of(header),
                level=level,
                parent_ref=parent_ref,
                text=section_text,
                locator=locator,
                source_index=text_index,
            )
        )
        parent_stack.append((level, section_ref))
    return tuple(sections)


def _section_end_index(
    texts: list[dict[str, object]],
    header_indexes: list[int],
    header_position: int,
    level: int,
) -> int:
    """返回当前章节在 texts[] 中的结束下标。"""

    for next_header_index in header_indexes[header_position + 1 :]:
        next_level = _positive_int(texts[next_header_index].get("level"), default=1)
        if next_level <= level:
            return next_header_index
    return len(texts)


def _parse_tables(
    identity: ReportIdentity,
    tables: list[dict[str, object]],
    texts: list[dict[str, object]],
    sections: tuple[_ParsedSection, ...],
) -> tuple[_ParsedTable, ...]:
    """从 Docling tables[] 解析有界表格投影。"""

    ref_text = {str(item.get("self_ref")): _text_of(item) for item in texts if item.get("self_ref")}
    parsed: list[_ParsedTable] = []
    for index, item in enumerate(tables):
        rows = _table_rows(item)
        page_no = _first_page_no(item)
        table_ref = f"table-{index:04d}"
        section_ref = _section_ref_for_page(sections, page_no)
        locator = _locator_from_item(
            identity.document_id,
            LocatorKind.TABLE,
            item,
            section_ref=section_ref,
            table_ref=table_ref,
        )
        section_title = _section_title_for_ref(sections, section_ref)
        current = _ParsedTable(
            table_ref=table_ref,
            caption=_table_caption(item, ref_text, fallback_title=section_title),
            section_ref=section_ref,
            rows=rows,
            locator=locator,
            source_index=index,
        )
        if parsed and _is_continuation_of(current, parsed[-1]):
            prev = parsed[-1]
            merged_rows = prev.rows + current.rows
            merged_locator = _merge_locator(prev.locator, current.locator)
            parsed[-1] = _ParsedTable(
                table_ref=prev.table_ref,
                caption=prev.caption,
                section_ref=prev.section_ref,
                rows=merged_rows,
                locator=merged_locator,
                source_index=prev.source_index,
            )
        else:
            parsed.append(current)
    return tuple(parsed)


def _build_parser_health(
    texts: list[dict[str, object]],
    sections: tuple[_ParsedSection, ...],
    tables: tuple[_ParsedTable, ...],
) -> ParserHealth:
    """构建并校验 parser health。"""

    readable_text_count = sum(1 for item in texts if _text_of(item))
    searchable_text_chars = sum(len(section.text) for section in sections)
    health = ParserHealth(
        readable_text_count=readable_text_count,
        section_count=len(sections),
        table_count=len(tables),
        searchable_text_chars=searchable_text_chars,
    )
    if readable_text_count == 0 or health.section_count == 0 or searchable_text_chars == 0:
        raise DocumentToolError(FailureCode.PARSER_HEALTH_FAILED, "Docling JSON 无可读文本或章节索引")
    return health


def _build_bm25f_units(
    sections: tuple[_ParsedSection, ...],
    tables: tuple[_ParsedTable, ...],
) -> tuple[BM25FUnit, ...]:
    """构建 BM25F 索引单元：section（title+text）、table caption、bounded table row。"""

    units: list[BM25FUnit] = []
    for section in sections:
        units.append(
            BM25FUnit(fields={BM25F_FIELD_TITLE: section.title, BM25F_FIELD_TEXT: section.text})
        )
    for table in tables:
        if table.caption:
            units.append(BM25FUnit(fields={BM25F_FIELD_CAPTION: table.caption}))
        for row in table.rows[:DEFAULT_TABLE_MAX_ROWS]:
            units.append(BM25FUnit(fields={BM25F_FIELD_ROWS: _table_row_text(row)}))
    return tuple(units)


def _section_search_candidates(
    document_id: str,
    sections: tuple[_ParsedSection, ...],
    query: str,
    *,
    within_section_ref: str | None,
) -> list[_SearchCandidate]:
    """构造章节正文搜索候选。"""

    candidates: list[_SearchCandidate] = []
    normalized_query = _whitespace_stripped(query)
    for section in sections:
        if within_section_ref is not None and section.section_ref != within_section_ref:
            continue
        score = _whitespace_stripped(section.text).count(normalized_query)
        if score <= 0:
            continue
        locator = Locator(
            document_id=document_id,
            locator_kind=LocatorKind.EXCERPT,
            section_ref=section.section_ref,
            table_ref=None,
            page_no=section.locator.page_no,
            page_range=section.locator.page_range,
            internal_ref=section.locator.internal_ref,
            internal_ref_available=section.locator.internal_ref_available,
            bbox=section.locator.bbox,
        )
        candidates.append(
            _SearchCandidate(
                score=score,
                source_order=section.source_index,
                section_ref=section.section_ref,
                table_ref=None,
                title=section.title,
                excerpt=_search_excerpt(section.text, query, DEFAULT_SEARCH_EXCERPT_CHARS),
                locator=locator,
                match_kind=SearchMatchKind.SECTION_TEXT,
            )
        )
    return candidates


def _table_search_candidates(
    tables: tuple[_ParsedTable, ...],
    query: str,
    *,
    within_section_ref: str | None,
) -> list[_SearchCandidate]:
    """构造表格标题和有界行搜索候选。"""

    candidates: list[_SearchCandidate] = []
    for table in tables:
        if within_section_ref is not None and table.section_ref != within_section_ref:
            continue
        candidates.extend(_table_caption_search_candidates(table, query))
        candidates.extend(_table_row_search_candidates(table, query))
    return candidates


def _table_caption_search_candidates(table: _ParsedTable, query: str) -> list[_SearchCandidate]:
    """构造表格标题搜索候选。"""

    if not table.caption:
        return []
    score = table.caption.count(query)
    if score <= 0:
        return []
    return [
        _SearchCandidate(
            score=score,
            source_order=_table_source_order(table, row_index=None),
            section_ref=table.section_ref or "",
            table_ref=table.table_ref,
            title=table.caption,
            excerpt=_excerpt(table.caption, query, DEFAULT_SEARCH_EXCERPT_CHARS),
            locator=table.locator,
            match_kind=SearchMatchKind.TABLE_CAPTION,
        )
    ]


def _table_row_search_candidates(table: _ParsedTable, query: str) -> list[_SearchCandidate]:
    """构造有界表格行搜索候选，摘录只返回命中行。"""

    candidates: list[_SearchCandidate] = []
    normalized_query = _whitespace_stripped(query)
    for row_index, row in enumerate(table.rows[:DEFAULT_TABLE_MAX_ROWS]):
        row_text = _table_row_text(row)
        score = _whitespace_stripped(row_text).count(normalized_query)
        if score <= 0:
            continue
        candidates.append(
            _SearchCandidate(
                score=score,
                source_order=_table_source_order(table, row_index=row_index),
                row_index=row_index,
                section_ref=table.section_ref or "",
                table_ref=table.table_ref,
                title=table.caption or f"表格 {table.table_ref}",
                excerpt=_search_excerpt(row_text, query, DEFAULT_SEARCH_EXCERPT_CHARS),
                locator=table.locator,
                match_kind=SearchMatchKind.TABLE_ROW,
            )
        )
    return candidates


def _table_source_order(table: _ParsedTable, *, row_index: int | None) -> int:
    """返回 table candidate 的稳定排序键。"""

    base = _TABLE_SEARCH_SOURCE_ORDER_OFFSET + (table.source_index * _TABLE_SEARCH_ROW_ORDER_OFFSET)
    return base if row_index is None else base + row_index + 1


def _table_row_text(row: tuple[str, ...]) -> str:
    """把一行表格单元格转换为安全检索文本。"""

    return "\t".join(cell for cell in row if cell)


def _locator_from_item(
    document_id: str,
    locator_kind: LocatorKind,
    item: dict[str, object],
    *,
    section_ref: str | None,
    table_ref: str | None,
    page_range: tuple[int, int] | None = None,
) -> Locator:
    """从 Docling item 的 self_ref/prov[] 组装受控 locator。"""

    internal_ref = item.get("self_ref") if isinstance(item.get("self_ref"), str) else None
    return Locator(
        document_id=document_id,
        locator_kind=locator_kind,
        section_ref=section_ref,
        table_ref=table_ref,
        page_no=_first_page_no(item),
        page_range=page_range,
        internal_ref=internal_ref,
        internal_ref_available=internal_ref is not None,
        bbox=_first_bbox(item),
    )


def _first_page_no(item: dict[str, object]) -> int | None:
    """读取 prov[0].page_no。"""

    prov = item.get("prov")
    if not isinstance(prov, list) or not prov or not isinstance(prov[0], dict):
        return None
    page_no = prov[0].get("page_no")
    return page_no if isinstance(page_no, int) else None


def _first_bbox(item: dict[str, object]) -> dict[str, float] | None:
    """读取 prov[0].bbox 中的数值字段。"""

    prov = item.get("prov")
    if not isinstance(prov, list) or not prov or not isinstance(prov[0], dict):
        return None
    bbox = prov[0].get("bbox")
    if not isinstance(bbox, dict):
        return None
    numeric_bbox = {
        key: float(value)
        for key, value in bbox.items()
        if key in {"l", "t", "r", "b"} and isinstance(value, int | float)
    }
    return numeric_bbox or None


def _page_range(items: list[dict[str, object]]) -> tuple[int, int] | None:
    """从一组 Docling items 中计算页码范围。"""

    pages = [page_no for item in items if (page_no := _first_page_no(item)) is not None]
    if not pages:
        return None
    return min(pages), max(pages)


def _text_of(item: dict[str, object]) -> str:
    """读取并标准化 Docling item.text。"""

    text = item.get("text")
    return text.strip() if isinstance(text, str) else ""


def _positive_int(value: object, *, default: int) -> int:
    """把 Docling level 等字段收敛为正整数。"""

    return value if isinstance(value, int) and value > 0 else default


def _table_rows(item: dict[str, object]) -> tuple[tuple[str, ...], ...]:
    """从 data.table_cells[] 构造二维文本行。"""

    data = item.get("data")
    if not isinstance(data, dict):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling table 缺少 data")
    cells = data.get("table_cells")
    if not isinstance(cells, list):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling table 缺少 data.table_cells[]")
    matrix: dict[tuple[int, int], str] = {}
    max_row = 0
    max_col = 0
    for cell in cells:
        if not isinstance(cell, dict):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling table cell 不是对象")
        row_index = _zero_based_int(cell.get("start_row_offset_idx"))
        col_index = _zero_based_int(cell.get("start_col_offset_idx"))
        end_row = _positive_int(cell.get("end_row_offset_idx"), default=row_index + 1)
        end_col = _positive_int(cell.get("end_col_offset_idx"), default=col_index + 1)
        max_row = max(max_row, end_row)
        max_col = max(max_col, end_col)
        matrix[(row_index, col_index)] = str(cell.get("text") or "").strip()
    return tuple(
        tuple(matrix.get((row_index, col_index), "") for col_index in range(max_col))
        for row_index in range(max_row)
    )


def _zero_based_int(value: object) -> int:
    """读取零基下标；无效时按 schema drift 处理。"""

    if not isinstance(value, int) or value < 0:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling table cell 下标不符合契约")
    return value


_PAGE_NOISE_PATTERN = (
    r"第\s*[0-9一二三四五六七八九十百千万]+\s*页"
    r"(?:\s*共\s*[0-9一二三四五六七八九十百千万]+\s*页)?"
)
_UNIT_NOISE_PATTERN = r"单位\s*[：:]\s*(?:人民币元|人民币|元)"
_NO_SEMANTIC_CAPTION_RE = re.compile(
    rf"^(?:{_PAGE_NOISE_PATTERN}|{_UNIT_NOISE_PATTERN})"
    rf"(?:\s+(?:{_PAGE_NOISE_PATTERN}|{_UNIT_NOISE_PATTERN}))*$"
)


def _is_semantic_caption(caption: str) -> bool:
    """判断 caption 是否包含语义文本（非仅页码/单位噪声）。"""

    return _NO_SEMANTIC_CAPTION_RE.match(caption.strip()) is None


def _section_title_for_ref(
    sections: tuple[_ParsedSection, ...],
    section_ref: str | None,
) -> str | None:
    """按 section_ref 查找章节标题，缺失时返回 None。"""

    if section_ref is None:
        return None
    for section in sections:
        if section.section_ref == section_ref:
            return section.title
    return None


def _table_caption(
    item: dict[str, object],
    ref_text: dict[str, str],
    *,
    fallback_title: str | None = None,
) -> str | None:
    """解析 captions[] 引用或直接文本；缺失或仅含无语义噪声时回填章节标题。"""

    captions = item.get("captions")
    if not isinstance(captions, list):
        return fallback_title
    values: list[str] = []
    for caption in captions:
        if isinstance(caption, dict) and isinstance(caption.get("$ref"), str):
            text = ref_text.get(caption["$ref"])
            if text:
                values.append(text)
        elif isinstance(caption, dict) and isinstance(caption.get("text"), str):
            text = caption["text"].strip()
            if text:
                values.append(text)
        elif isinstance(caption, str) and caption.strip():
            values.append(caption.strip())
    caption_text = " ".join(values) or None
    if caption_text is None or not _is_semantic_caption(caption_text):
        return fallback_title
    return caption_text


def _section_ref_for_page(sections: tuple[_ParsedSection, ...], page_no: int | None) -> str | None:
    """按页码把表格归属到最近的前序章节。"""

    if page_no is None:
        return sections[0].section_ref if sections else None
    best: _ParsedSection | None = None
    for section in sections:
        section_page = section.locator.page_no
        if section_page is not None and section_page <= page_no:
            best = section
    return best.section_ref if best else (sections[0].section_ref if sections else None)


_HEADER_KEYWORDS = frozenset({"序号", "代码", "名称", "金额", "比例", "项目", "日期", "数量", "备注"})


def _first_cell_is_integer(row: tuple[str, ...]) -> bool:
    """检查首列是否为整数（序号的典型特征，表示数据行而非表头）。"""

    if not row:
        return False
    try:
        int(row[0].strip().replace(",", ""))
        return True
    except (ValueError, IndexError):
        return False


def _row_has_header_keywords(row: tuple[str, ...]) -> bool:
    """检查行中是否包含常见中文表头关键词。"""

    for cell in row:
        for kw in _HEADER_KEYWORDS:
            if kw in cell:
                return True
    return False


def _has_header_row(rows: tuple[tuple[str, ...], ...]) -> bool:
    """判断表格第一行是否为表头。"""

    if not rows:
        return False
    first_row = rows[0]
    if _first_cell_is_integer(first_row):
        return False
    if _row_has_header_keywords(first_row):
        return True
    short_cells = sum(1 for cell in first_row if len(cell.strip()) <= 12)
    return short_cells >= max(len(first_row) * 0.6, 3)


def _data_rows(rows: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
    """返回数据行（跳过表头行）。"""

    if not rows:
        return rows
    if _has_header_row(rows):
        return rows[1:]
    return rows


def _column_type_signature(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    """返回每列的数据类型签名，用于比较两个表格的列格式是否一致。

    每列归类为 'numeric'（多数单元格可解析为数字）、'text' 或 'empty'。
    """

    if not rows:
        return ()
    num_cols = len(rows[0])
    sig: list[str] = []
    for col_idx in range(num_cols):
        numeric = 0
        text = 0
        empty = 0
        for row in rows:
            cell = row[col_idx].strip() if col_idx < len(row) else ""
            if not cell:
                empty += 1
                continue
            cleaned = cell.replace(",", "").replace("%", "").replace("￥", "").replace("$", "").strip()
            try:
                float(cleaned)
                numeric += 1
            except ValueError:
                text += 1
        total = numeric + text + empty
        if empty > total * 0.5:
            sig.append("empty")
        elif numeric >= text:
            sig.append("numeric")
        else:
            sig.append("text")
    return tuple(sig)


def _is_continuation_of(current: _ParsedTable, previous: _ParsedTable) -> bool:
    """判断 current 是否为 previous 的跨页续表。"""

    if _has_header_row(current.rows):
        return False
    # 同 section 检查：跨 section 的连续表格不应合并
    if current.section_ref and previous.section_ref:
        if current.section_ref != previous.section_ref:
            return False
    cur_page = current.locator.page_no
    prev_page = previous.locator.page_no
    if cur_page is not None and prev_page is not None and cur_page <= prev_page:
        return False
    cur_cols = len(current.rows[0]) if current.rows else 0
    prev_cols = len(previous.rows[0]) if previous.rows else 0
    if cur_cols > prev_cols + 1 or cur_cols < prev_cols - 1:
        return False
    # 列格式一致性检查：前表数据行与当前表的列类型签名应一致
    prev_data = _data_rows(previous.rows)
    if prev_data and current.rows:
        if _column_type_signature(prev_data) != _column_type_signature(current.rows):
            return False
    return True


def _merge_locator(base: Locator, continuation: Locator) -> Locator:
    """合并跨页续表后的 locator，扩展 page_range。"""

    pages: list[int] = []
    if base.page_no is not None:
        pages.append(base.page_no)
    if continuation.page_no is not None:
        pages.append(continuation.page_no)
    if base.page_range:
        pages.extend(base.page_range)
    if continuation.page_range:
        pages.extend(continuation.page_range)
    page_range = (min(pages), max(pages)) if pages else base.page_range
    return Locator(
        document_id=base.document_id,
        locator_kind=base.locator_kind,
        section_ref=base.section_ref,
        table_ref=base.table_ref,
        page_no=base.page_no,
        page_range=page_range,
        internal_ref=base.internal_ref,
        internal_ref_available=base.internal_ref_available,
        bbox=base.bbox,
    )


def _bounded(text: str, max_chars: int) -> tuple[str, bool]:
    """按字符数截断文本并返回 truncated 标记。"""

    if max_chars < 1:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


_NUMBER_STRING_CHARS = frozenset("0123456789,，.")


def _align_start_no_number_cut(text: str, start: int) -> int:
    """把窗口左边界对齐到数字串起点，避免截断数字串。

    参数:
        text: 原文。
        start: 窗口左边界下标。

    返回:
        对齐后的左边界；仅当截断点前一字符与当前字符均属数字串字符集
        （`0123456789,，.`）时向前回退至数字串起点，其余情况原样返回。
    """

    if not 0 < start < len(text):
        return start
    if text[start - 1] not in _NUMBER_STRING_CHARS or text[start] not in _NUMBER_STRING_CHARS:
        return start
    while start > 0 and text[start - 1] in _NUMBER_STRING_CHARS:
        start -= 1
    return start


def _align_end_no_number_cut(text: str, end: int) -> int:
    """把窗口右边界对齐到数字串结束，避免截断数字串。

    参数:
        text: 原文。
        end: 窗口右边界下标。

    返回:
        对齐后的右边界；仅当截断点前一字符与当前字符均属数字串字符集
        （`0123456789,，.`）时向后扩展至数字串结束，其余情况原样返回。
    """

    if not 0 < end < len(text):
        return end
    if text[end - 1] not in _NUMBER_STRING_CHARS or text[end] not in _NUMBER_STRING_CHARS:
        return end
    while end < len(text) and text[end] in _NUMBER_STRING_CHARS:
        end += 1
    return end


def _excerpt(text: str, query: str, max_chars: int) -> str:
    """围绕首次命中构造有界摘录，窗口边缘对齐数字串边界。"""

    index = text.find(query)
    if index < 0:
        return text[: _align_end_no_number_cut(text, max_chars)]
    half_window = max(max_chars // 2, len(query))
    start = max(index - half_window, 0)
    end = min(start + max_chars, len(text))
    start = _align_start_no_number_cut(text, start)
    end = _align_end_no_number_cut(text, end)
    return text[start:end]


def _whitespace_stripped(text: str) -> str:
    """去除所有空白字符，用于空白归一化匹配。"""

    return re.sub(r"\s+", "", text)


def _map_normalized_index(original: str, normalized_index: int) -> int:
    """把去除空白后的字符下标映射回原文下标。

    参数:
        original: 原始文本。
        normalized_index: 去除空白后文本中的字符下标。

    返回:
        对应原文下标；超出末尾时返回 len(original)。
    """

    cursor = 0
    for original_index, char in enumerate(original):
        if char.isspace():
            continue
        if cursor == normalized_index:
            return original_index
        cursor += 1
    return len(original)


def _search_excerpt(text: str, query: str, max_chars: int) -> str:
    """构造搜索命中摘录：优先字面定位，其次按空白归一化定位原文；窗口边缘对齐数字串边界。"""

    if text.find(query) >= 0:
        return _excerpt(text, query, max_chars)
    normalized_text = _whitespace_stripped(text)
    normalized_query = _whitespace_stripped(query)
    index = normalized_text.find(normalized_query)
    if index < 0:
        return text[: _align_end_no_number_cut(text, max_chars)]
    start = _map_normalized_index(text, index)
    end = _map_normalized_index(text, index + len(normalized_query))
    half_window = max(max_chars // 2, end - start)
    begin = max(start - half_window, 0)
    window_end = min(begin + max_chars, len(text))
    begin = _align_start_no_number_cut(text, begin)
    window_end = _align_end_no_number_cut(text, window_end)
    return text[begin:window_end]
