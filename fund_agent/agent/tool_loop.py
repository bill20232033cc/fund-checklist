"""确定性的基金文档工具调用循环。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fund_agent.fund.document_tools.constants import FailureCode, ToolName
from fund_agent.fund.document_tools.models import (
    Citation,
    SearchResult,
    SearchMatchKind,
    SectionContent,
    TableContent,
    TableSummary,
    ToolFailure,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService

ToolResultKind = Literal["success", "failure"]
ToolArgumentValue = str | int | None

_NO_SEARCH_HIT_MESSAGE = "未找到可读取的匹配章节"
_TABLE_PAGE_WINDOW = 1
_MAX_TABLE_CANDIDATES = 3
_MAX_TABLE_ROWS = 15


@dataclass(frozen=True)
class ToolTraceEntry:
    """单次工具调用轨迹。

    参数:
        tool_name: 调用的 public reading tool 名称，或被拒绝的 LLM 请求工具名。
        arguments: 传给工具的显式参数；不得包含本地路径或 raw payload。
        result_kind: 工具调用结果类别，取值为 success 或 failure。
        failure_code: 工具失败时的稳定失败分类；成功时为 None。

    返回:
        不可变 trace entry。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: ToolName | str
    arguments: dict[str, ToolArgumentValue]
    result_kind: ToolResultKind
    failure_code: FailureCode | None = None


@dataclass(frozen=True)
class AgentRunResult:
    """Agent loop 的统一返回值。

    参数:
        answer: 最终回答；成功时只由 public reading tool result 生成。
        citations: section/table reading tools 返回的 citation 元组。
        tool_trace: public reading tool 调用轨迹。
        failure: 失败分类；成功时为 None。

    返回:
        Host/UI 可安全消费的 Agent run 结果。

    异常:
        本模型不抛出业务异常。
    """

    answer: str
    citations: tuple[Citation, ...]
    tool_trace: tuple[ToolTraceEntry, ...]
    failure: ToolFailure | None = None


class MinimalFundDocumentAgent:
    """执行确定性 table-backed first-hit 与 section-first 阅读 Agent。

    参数:
        tool_service: FundDocumentToolService，是 Agent 访问基金文档的唯一边界。

    返回:
        可运行最小阅读工具循环的 Agent。

    异常:
        public run 方法不向 Host/UI 抛出内部异常，失败写入 AgentRunResult.failure。
    """

    def __init__(self, tool_service: FundDocumentToolService) -> None:
        """初始化最小 Agent。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """运行固定顺序的阅读工具循环。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 检索关键词。

        返回:
            AgentRunResult；成功时 answer 只来自 section/table tool result。

        异常:
            不抛出 ToolFailure 或 DocumentToolError；失败写入 AgentRunResult.failure。
        """

        trace: list[ToolTraceEntry] = []
        search_result = self._tool_service.search_document(document_id, query)
        if isinstance(search_result, ToolFailure):
            trace.append(_failure_trace(ToolName.SEARCH_DOCUMENT, _search_arguments(document_id, query), search_result))
            return _failed_result(tuple(trace), search_result)

        trace.append(_success_trace(ToolName.SEARCH_DOCUMENT, _search_arguments(document_id, query)))
        if not search_result:
            return _failed_result(
                tuple(trace),
                ToolFailure(code=FailureCode.NOT_FOUND, message=_NO_SEARCH_HIT_MESSAGE),
            )

        first_hit = search_result[0]
        section_ref = _section_ref_from_hit(first_hit)
        if section_ref is None:
            return _failed_result(
                tuple(trace),
                ToolFailure(code=FailureCode.NOT_FOUND, message=_NO_SEARCH_HIT_MESSAGE),
            )

        read_arguments = _read_section_arguments(document_id, section_ref)
        section_result = self._tool_service.read_section(document_id, section_ref)
        if isinstance(section_result, ToolFailure):
            trace.append(_failure_trace(ToolName.READ_SECTION, read_arguments, section_result))
            return _failed_result(tuple(trace), section_result)

        trace.append(_success_trace(ToolName.READ_SECTION, read_arguments))
        direct_table_result = self._read_high_certainty_table_hit(
            document_id=document_id,
            query=query,
            hit=first_hit,
            trace=trace,
        )
        if isinstance(direct_table_result, ToolFailure):
            return _failed_result(tuple(trace), direct_table_result)
        if direct_table_result is not None:
            return AgentRunResult(
                answer=_answer_from_table_first(section_result, direct_table_result),
                citations=(direct_table_result.citation, section_result.citation),
                tool_trace=tuple(trace),
                failure=None,
            )

        table_results = self._read_relevant_tables(
            document_id=document_id,
            query=query,
            section=section_result,
            trace=trace,
        )
        citations = (section_result.citation,) + tuple(table.citation for table in table_results)
        return AgentRunResult(
            answer=_answer_from_section_and_tables(section_result, table_results),
            citations=citations,
            tool_trace=tuple(trace),
            failure=None,
        )

    def _read_high_certainty_table_hit(
        self,
        *,
        document_id: str,
        query: str,
        hit: SearchResult,
        trace: list[ToolTraceEntry],
    ) -> TableContent | ToolFailure | None:
        """first hit 为高确定性表格命中时直接读取该表。"""

        if not _is_high_certainty_table_hit(hit, query):
            return None

        table_ref = hit.table_ref
        if table_ref is None:
            return None

        read_arguments = _read_table_arguments(document_id, table_ref, _MAX_TABLE_ROWS)
        table_result = self._tool_service.read_table(document_id, table_ref, max_rows=_MAX_TABLE_ROWS)
        if isinstance(table_result, ToolFailure):
            trace.append(_failure_trace(ToolName.READ_TABLE, read_arguments, table_result))
            return table_result
        trace.append(_success_trace(ToolName.READ_TABLE, read_arguments))
        return table_result

    def _read_relevant_tables(
        self,
        *,
        document_id: str,
        query: str,
        section: SectionContent,
        trace: list[ToolTraceEntry],
    ) -> tuple[TableContent, ...]:
        """按章节和页码邻近性读取相关表格。"""

        list_arguments = _list_tables_arguments(document_id)
        tables = self._tool_service.list_tables(document_id)
        if isinstance(tables, ToolFailure):
            trace.append(_failure_trace(ToolName.LIST_TABLES, list_arguments, tables))
            return ()
        trace.append(_success_trace(ToolName.LIST_TABLES, list_arguments))

        candidates = _rank_table_summaries(tables, section=section, query=query)
        if not candidates:
            return ()

        read_tables: list[tuple[int, TableContent]] = []
        for table in candidates[:_MAX_TABLE_CANDIDATES]:
            read_arguments = _read_table_arguments(document_id, table.table_ref, _MAX_TABLE_ROWS)
            table_result = self._tool_service.read_table(document_id, table.table_ref, max_rows=_MAX_TABLE_ROWS)
            if isinstance(table_result, ToolFailure):
                trace.append(_failure_trace(ToolName.READ_TABLE, read_arguments, table_result))
                continue
            trace.append(_success_trace(ToolName.READ_TABLE, read_arguments))
            score = _score_table_content(table_result, query=query, section=section)
            if score > 0:
                read_tables.append((score, table_result))

        read_tables.sort(key=lambda item: (-item[0], item[1].table_ref))
        return tuple(table for _, table in read_tables[:1])


def _section_ref_from_hit(hit: SearchResult) -> str | None:
    """从 search_document 命中中读取可用于 read_section 的章节引用。"""

    return hit.locator.section_ref or hit.section_ref


def _is_high_certainty_table_hit(hit: SearchResult, query: str) -> bool:
    """判断 first hit 是否可按 9C 规则直接消费表格。"""

    if not query or hit.table_ref is None:
        return False
    if hit.match_kind is SearchMatchKind.TABLE_ROW:
        return query in hit.excerpt
    if hit.match_kind is SearchMatchKind.TABLE_CAPTION:
        return query in hit.title or query in hit.excerpt
    return False


def _answer_from_table_first(section: SectionContent, table: TableContent) -> str:
    """以表格有界行作为主体组装 table-first 回答。"""

    context = [f"来源章节: {section.title}"]
    if table.caption:
        context.append(f"表格标题: {table.caption}")
    table_rows = "\n".join(_format_table_row(row) for row in table.rows)
    return "\n".join(["表格内容:", table_rows, *context]).strip()


def _answer_from_section_and_tables(section: SectionContent, tables: tuple[TableContent, ...]) -> str:
    """只使用 section/table tool 输出组装最终回答。"""

    parts = [f"{section.title}\n\n{section.text}"]
    if tables:
        parts.append("相关表格:\n" + "\n\n".join(_format_table(table) for table in tables))
    return "\n\n".join(parts)


def _format_table(table: TableContent) -> str:
    """把有界表格行格式化为可读文本。"""

    lines: list[str] = []
    if table.caption:
        lines.append(table.caption)
    lines.extend(_format_table_row(row) for row in table.rows)
    return "\n".join(line for line in lines if line)


def _format_table_row(row: tuple[str, ...]) -> str:
    """格式化单行有界表格文本。"""

    return " | ".join(cell for cell in row if cell)


def _rank_table_summaries(
    tables: tuple[TableSummary, ...],
    *,
    section: SectionContent,
    query: str,
) -> tuple[TableSummary, ...]:
    """按 query、section 和页码邻近性排序表格摘要。"""

    scored = [
        (score, table)
        for table in tables
        if (score := _score_table_summary(table, query=query, section=section)) > 0
    ]
    scored.sort(key=lambda item: (-item[0], item[1].table_ref))
    return tuple(table for _, table in scored)


def _score_table_summary(table: TableSummary, *, query: str, section: SectionContent) -> int:
    """计算表格摘要与当前章节的相关性分数。"""

    score = 0
    normalized_query = query.strip()
    if normalized_query and table.caption and normalized_query in table.caption:
        score += 8
    if table.section_ref == section.section_ref:
        score += 6
    if _same_page(table.locator.page_no, section.locator.page_no):
        score += 5
    elif _page_near(table.locator.page_no, section.locator.page_no):
        score += 3
    return score


def _score_table_content(table: TableContent, *, query: str, section: SectionContent) -> int:
    """计算读取后的表格内容相关性分数。"""

    score = _score_table_summary(
        TableSummary(
            table_ref=table.table_ref,
            caption=table.caption,
            section_ref=table.section_ref,
            locator=table.locator,
            row_count=len(table.rows),
            column_count=max((len(row) for row in table.rows), default=0),
        ),
        query=query,
        section=section,
    )
    table_text = "\n".join(" ".join(row) for row in table.rows)
    normalized_query = query.strip()
    if normalized_query:
        score += table_text.count(normalized_query) * 10
        for token in _query_tokens(normalized_query):
            if token in table_text:
                score += 2
    return score


def _query_tokens(query: str) -> tuple[str, ...]:
    """把短查询拆成保守 token，供表格内容弱匹配。"""

    if len(query) <= 2:
        return (query,)
    return tuple(query[index : index + 2] for index in range(0, len(query) - 1, 2))


def _same_page(left: int | None, right: int | None) -> bool:
    """判断两个 locator 是否位于同页。"""

    return left is not None and right is not None and left == right


def _page_near(left: int | None, right: int | None) -> bool:
    """判断表格是否位于章节相邻页范围内。"""

    return left is not None and right is not None and abs(left - right) <= _TABLE_PAGE_WINDOW


def _failed_result(trace: tuple[ToolTraceEntry, ...], failure: ToolFailure) -> AgentRunResult:
    """构造不含猜测回答的失败结果。"""

    return AgentRunResult(answer="", citations=(), tool_trace=trace, failure=failure)


def _search_arguments(document_id: str, query: str) -> dict[str, ToolArgumentValue]:
    """构造 search_document trace 参数。"""

    return {"document_id": document_id, "query": query}


def _read_section_arguments(document_id: str, section_ref: str) -> dict[str, ToolArgumentValue]:
    """构造 read_section trace 参数。"""

    return {"document_id": document_id, "section_ref": section_ref}


def _list_tables_arguments(document_id: str) -> dict[str, ToolArgumentValue]:
    """构造 list_tables trace 参数。"""

    return {"document_id": document_id}


def _read_table_arguments(document_id: str, table_ref: str, max_rows: int) -> dict[str, ToolArgumentValue]:
    """构造 read_table trace 参数。"""

    return {"document_id": document_id, "table_ref": table_ref, "max_rows": max_rows}


def _success_trace(tool_name: ToolName, arguments: dict[str, ToolArgumentValue]) -> ToolTraceEntry:
    """构造成功工具轨迹。"""

    return ToolTraceEntry(
        tool_name=tool_name,
        arguments=dict(arguments),
        result_kind="success",
        failure_code=None,
    )


def _failure_trace(
    tool_name: ToolName,
    arguments: dict[str, ToolArgumentValue],
    failure: ToolFailure,
) -> ToolTraceEntry:
    """构造失败工具轨迹。"""

    return ToolTraceEntry(
        tool_name=tool_name,
        arguments=dict(arguments),
        result_kind="failure",
        failure_code=failure.code,
    )
