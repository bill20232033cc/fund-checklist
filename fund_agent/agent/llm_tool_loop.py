"""fake/injected LLM 风格的受控工具调用循环。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol, TypeAlias

from fund_agent.agent.tool_loop import (
    AgentRunResult,
    ToolArgumentValue,
    ToolResultKind,
    ToolTraceEntry,
)
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.models import (
    Citation,
    ExcerptContent,
    Locator,
    SearchResult,
    SectionContent,
    TableContent,
    TableSummary,
    ToolFailure,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService

ControlledToolOutput: TypeAlias = (
    "tuple[SearchResult, ...] | SectionContent | tuple[TableSummary, ...] | TableContent | ExcerptContent | AggregateMultiYearAnnualPerformanceResult"
)
LlmStep: TypeAlias = "ToolCall | FinalAnswer"
FakeStepFactory: TypeAlias = Callable[[tuple["ToolResult", ...]], LlmStep]

ALLOWED_LLM_TOOL_NAMES: frozenset[ToolName] = frozenset(
    {
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
        ToolName.GET_EXCERPT,
        ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE,
    }
)
_MAX_LLM_STEPS = 8
_MAX_TABLE_ROWS = 8
_TOOL_NOT_ALLOWED_MESSAGE = "LLM 工具调用不被允许"
_TOOL_ARGUMENT_MESSAGE = "LLM 工具调用参数不完整"
_NO_EVIDENCE_MESSAGE = "LLM 最终回答缺少受控工具证据"
_MISSING_CITATION_MESSAGE = "LLM 最终回答缺少受控 citation"
_UNSUPPORTED_FACT_MESSAGE = "LLM 最终回答包含未由工具结果支持的关键事实"
_STEP_LIMIT_MESSAGE = "LLM 工具调用超过限制"
_UNAVAILABLE_MESSAGE = "LLM 工具循环暂不可用"


class LlmClientFailure(Exception):
    """LLM client 可分类失败。

    参数:
        code: 稳定失败分类。
        message: 安全错误信息；不得包含 provider raw body、API key 或私有路径。

    返回:
        runner 可识别并转为 AgentRunResult.failure 的异常。

    异常:
        构造时不抛出业务异常。
    """

    def __init__(self, code: FailureCode, message: str) -> None:
        """保存稳定失败分类和安全信息。"""

        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ToolCall:
    """LLM 请求调用 reading tool 的显式模型。

    参数:
        tool_name: 请求调用的工具名；runner 会先校验是否已知且被授权。
        document_id: public reading tools 使用的内容身份，必须等于本轮 run 的 document_id。
        query: search_document 的检索词。
        section_ref: read_section 或 list_tables 的章节引用。
        table_ref: read_table 的表格引用。
        locator: get_excerpt 使用的受控 locator。
        max_results: search_document 可选最大命中数。
        max_chars: read_section/get_excerpt 可选最大字符数。
        max_rows: read_table 可选最大行数。

    返回:
        不执行工具调用的不可变请求对象。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: ToolName | str
    document_id: str
    query: str | None = None
    section_ref: str | None = None
    table_ref: str | None = None
    locator: Locator | None = None
    max_results: int | None = None
    max_chars: int | None = None
    max_rows: int | None = None
    extra: dict[str, object] | None = None


@dataclass(frozen=True)
class ToolResult:
    """返回给 injected LLM client 的受控工具结果。

    参数:
        tool_name: 成功调用的工具名。
        result: public reading tool 返回的受控数据模型。
        citations: 从 result 中提取的 citation 元组。
        evidence_text: 从 result 中提取的有界文本证据。

    返回:
        不包含 raw PDF、raw Docling JSON、本地路径或 private loader 字段的结果对象。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: ToolName
    result: ControlledToolOutput
    citations: tuple[Citation, ...]
    evidence_text: str


@dataclass(frozen=True)
class FinalAnswer:
    """LLM 请求结束工具循环并提交最终回答。

    参数:
        answer: 最终回答文本。
        citations: LLM 声明使用的 citation，必须来自先前成功工具结果。
        key_facts: 回答中的关键事实；每条必须出现在 answer 和受控工具 evidence_text 中。

    返回:
        不可变最终回答请求。

    异常:
        本模型不抛出业务异常。
    """

    answer: str
    citations: tuple[Citation, ...]
    key_facts: tuple[str, ...]


class LlmClientProtocol(Protocol):
    """可注入 LLM client 的最小协议。

    参数:
        document_id: 本轮阅读的 public 内容身份。
        query: 用户查询。
        tool_results: 先前成功工具调用的受控结果。

    返回:
        下一步 ToolCall 或 FinalAnswer。

    异常:
        实现可以抛出异常；runner 会 fail-closed 为 unavailable。
    """

    def next_step(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: tuple[ToolResult, ...],
    ) -> LlmStep:
        """返回下一步 LLM 行为。"""


class FakeLlmClient:
    """按脚本返回 ToolCall/FinalAnswer 的测试 LLM client。

    参数:
        steps: 固定步骤；元素可以是 ToolCall/FinalAnswer，也可以是根据已有 ToolResult
            生成下一步的 callable。

    返回:
        实现 LlmClientProtocol 的 fake client。

    异常:
        steps 耗尽时抛出 RuntimeError，由 runner 收敛为 unavailable。
    """

    def __init__(self, steps: Sequence[LlmStep | FakeStepFactory]) -> None:
        """保存脚本步骤。"""

        self._steps = tuple(steps)
        self._index = 0

    def next_step(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: tuple[ToolResult, ...],
    ) -> LlmStep:
        """返回脚本中的下一步。"""

        del document_id, query
        if self._index >= len(self._steps):
            raise RuntimeError("fake llm steps exhausted")
        step = self._steps[self._index]
        self._index += 1
        if callable(step):
            return step(tool_results)
        return step


class LlmToolLoopRunner:
    """执行 fake/injected LLM 的受控 reading tool loop。

    参数:
        tool_service: FundDocumentToolService，是 LLM runner 访问基金文档的唯一边界。
        llm_client: 注入式 LLM client；本 runner 不连接外部模型 API。
        max_steps: 单轮最大 LLM step 数，防止无限循环。

    返回:
        可运行 ToolCall -> ToolResult -> FinalAnswer 闭环的 runner。

    异常:
        run 方法不向 Host/UI 抛出内部异常，失败写入 AgentRunResult.failure。
    """

    def __init__(
        self,
        *,
        tool_service: FundDocumentToolService,
        llm_client: LlmClientProtocol,
        max_steps: int = _MAX_LLM_STEPS,
        aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None,
    ) -> None:
        """初始化受控 LLM tool loop runner。"""

        self._tool_service = tool_service
        self._llm_client = llm_client
        self._max_steps = max_steps
        self._aggregate_handler = aggregate_handler

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """运行 injected LLM 工具调用循环。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 用户查询。

        返回:
            AgentRunResult；成功时 answer/citations 通过 evidence/citation 校验。

        异常:
            不抛出 ToolFailure 或 LLM client 内部异常；失败写入 AgentRunResult.failure。
        """

        trace: list[ToolTraceEntry] = []
        tool_results: list[ToolResult] = []
        for _ in range(self._max_steps):
            try:
                step = self._llm_client.next_step(
                    document_id=document_id,
                    query=query,
                    tool_results=tuple(tool_results),
                )
            except LlmClientFailure as exc:
                return _failed_result(tuple(trace), exc.code, exc.safe_message)
            except Exception:
                return _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)

            if isinstance(step, FinalAnswer):
                return _final_result(step, tuple(tool_results), tuple(trace))
            if isinstance(step, ToolCall):
                tool_result = self._invoke_tool_call(step, expected_document_id=document_id, trace=trace)
                if isinstance(tool_result, ToolFailure):
                    return _failed_result(tuple(trace), tool_result.code, tool_result.message)
                tool_results.append(tool_result)
                continue
            return _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)

        return _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _STEP_LIMIT_MESSAGE)

    def _invoke_tool_call(
        self,
        call: ToolCall,
        *,
        expected_document_id: str,
        trace: list[ToolTraceEntry],
    ) -> ToolResult | ToolFailure:
        """校验并执行单次 LLM 工具请求。"""

        from fund_agent.service.reading_service import AggregateMultiYearAnnualPerformanceResult

        tool_name = _coerce_tool_name(call.tool_name)
        trace_arguments = _trace_arguments(call)
        if tool_name is None or tool_name not in ALLOWED_LLM_TOOL_NAMES:
            trace.append(_trace_entry(call.tool_name, trace_arguments, "failure", FailureCode.UNAVAILABLE))
            return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_NOT_ALLOWED_MESSAGE)
        if (
            tool_name is not ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE
            and call.document_id != expected_document_id
        ):
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", FailureCode.UNAVAILABLE))
            return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_NOT_ALLOWED_MESSAGE)

        result = self._call_allowed_tool(tool_name, call, aggregate_handler=self._aggregate_handler)
        if isinstance(result, ToolFailure):
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", result.code))
            return result
        if isinstance(result, AggregateMultiYearAnnualPerformanceResult) and result.failure is not None:
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", result.failure.code))
            return ToolFailure(code=result.failure.code, message=result.failure.message)

        trace.append(_trace_entry(tool_name, trace_arguments, "success", None))
        return _tool_result_from_output(tool_name, result)

    def _call_allowed_tool(
        self,
        tool_name: ToolName,
        call: ToolCall,
        *,
        aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None,
    ) -> ControlledToolOutput | ToolFailure:
        """按允许工具名分发到 FundDocumentToolService。"""

        if tool_name is ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE:
            if aggregate_handler is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_UNAVAILABLE_MESSAGE)
            extra = call.extra or {}
            fund_code = extra.get("fund_code")
            requested_years = extra.get("requested_years")
            annual_report_documents = extra.get("annual_report_documents")
            if fund_code is None or requested_years is None or annual_report_documents is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return aggregate_handler(
                fund_code,
                requested_years,
                annual_report_documents,
                extra.get("share_class"),
            )
        if tool_name is ToolName.SEARCH_DOCUMENT:
            if call.query is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.search_document(
                call.document_id,
                call.query,
                max_results=call.max_results,
            )
        if tool_name is ToolName.READ_SECTION:
            if call.section_ref is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.read_section(
                call.document_id,
                call.section_ref,
                max_chars=call.max_chars,
            )
        if tool_name is ToolName.LIST_TABLES:
            return self._tool_service.list_tables(call.document_id, within_section_ref=call.section_ref)
        if tool_name is ToolName.READ_TABLE:
            if call.table_ref is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.read_table(
                call.document_id,
                call.table_ref,
                max_rows=call.max_rows or _MAX_TABLE_ROWS,
            )
        if tool_name is ToolName.GET_EXCERPT:
            if call.locator is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.get_excerpt(call.document_id, call.locator, max_chars=call.max_chars)
        return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_NOT_ALLOWED_MESSAGE)


def _final_result(
    final_answer: FinalAnswer,
    tool_results: tuple[ToolResult, ...],
    trace: tuple[ToolTraceEntry, ...],
) -> AgentRunResult:
    """校验最终回答证据与 citation 后构造 AgentRunResult。"""

    evidence_texts = tuple(result.evidence_text for result in tool_results if result.evidence_text.strip())
    if not evidence_texts:
        return _failed_result(trace, FailureCode.UNAVAILABLE, _NO_EVIDENCE_MESSAGE)
    if not final_answer.citations:
        return _failed_result(trace, FailureCode.UNAVAILABLE, _MISSING_CITATION_MESSAGE)

    citation_evidence = tuple(
        (_citation_key(citation), result.evidence_text)
        for result in tool_results
        for citation in result.citations
        if citation.locator.locator_kind in {LocatorKind.SECTION, LocatorKind.TABLE}
    )
    controlled_citation_keys = {key for key, _ in citation_evidence}
    final_citation_keys = {_citation_key(citation) for citation in final_answer.citations}
    if not controlled_citation_keys or any(
        _citation_key(citation) not in controlled_citation_keys for citation in final_answer.citations
    ):
        return _failed_result(trace, FailureCode.UNAVAILABLE, _MISSING_CITATION_MESSAGE)

    if not final_answer.key_facts:
        return _failed_result(trace, FailureCode.UNAVAILABLE, _UNSUPPORTED_FACT_MESSAGE)
    for key_fact in final_answer.key_facts:
        fact = key_fact.strip()
        if not fact or fact not in final_answer.answer or not any(
            key in final_citation_keys and fact in evidence for key, evidence in citation_evidence
        ):
            return _failed_result(trace, FailureCode.UNAVAILABLE, _UNSUPPORTED_FACT_MESSAGE)

    return AgentRunResult(
        answer=final_answer.answer,
        citations=tuple(_public_citation(citation) for citation in final_answer.citations),
        tool_trace=trace,
        failure=None,
    )


def _tool_result_from_output(tool_name: ToolName, result: ControlledToolOutput) -> ToolResult:
    """从 public tool result 中提取 citations 和 evidence_text。"""

    from fund_agent.service.reading_service import AggregateMultiYearAnnualPerformanceResult

    if isinstance(result, AggregateMultiYearAnnualPerformanceResult):
        return ToolResult(
            tool_name=tool_name,
            result=result,
            citations=_aggregate_citations(result),
            evidence_text=_aggregate_evidence_text(result),
        )
    if isinstance(result, tuple):
        if result and isinstance(result[0], SearchResult):
            search_results = tuple(item for item in result if isinstance(item, SearchResult))
            return ToolResult(
                tool_name=tool_name,
                result=search_results,
                citations=tuple(item.citation for item in search_results),
                evidence_text="\n".join(item.excerpt for item in search_results),
            )
        table_summaries = tuple(item for item in result if isinstance(item, TableSummary))
        return ToolResult(
            tool_name=tool_name,
            result=table_summaries,
            citations=(),
            evidence_text="\n".join(item.caption or "" for item in table_summaries),
        )
    if isinstance(result, SectionContent):
        return ToolResult(
            tool_name=tool_name,
            result=result,
            citations=(result.citation,),
            evidence_text=f"{result.title}\n{result.text}",
        )
    if isinstance(result, TableContent):
        return ToolResult(
            tool_name=tool_name,
            result=result,
            citations=(result.citation,),
            evidence_text=_table_evidence_text(result),
        )
    return ToolResult(
        tool_name=tool_name,
        result=result,
        citations=(result.citation,),
        evidence_text=result.text,
    )


def _table_evidence_text(table: TableContent) -> str:
    """把表格 tool result 转换为有界证据文本。"""

    lines = [table.caption or ""]
    lines.extend(" | ".join(cell for cell in row if cell) for row in table.rows)
    return "\n".join(line for line in lines if line)


def _coerce_tool_name(tool_name: ToolName | str) -> ToolName | None:
    """把 LLM 输出的工具名转换为已知 ToolName。"""

    if isinstance(tool_name, ToolName):
        return tool_name
    try:
        return ToolName(str(tool_name))
    except ValueError:
        return None


def _trace_arguments(call: ToolCall) -> dict[str, ToolArgumentValue]:
    """构造不含 raw/private payload 的 trace 参数。"""

    arguments: dict[str, ToolArgumentValue] = {"document_id": call.document_id}
    if call.query is not None:
        arguments["query"] = call.query
    if call.section_ref is not None:
        arguments["section_ref"] = call.section_ref
    if call.table_ref is not None:
        arguments["table_ref"] = call.table_ref
    if call.max_results is not None:
        arguments["max_results"] = call.max_results
    if call.max_chars is not None:
        arguments["max_chars"] = call.max_chars
    if call.max_rows is not None:
        arguments["max_rows"] = call.max_rows
    if call.locator is not None:
        arguments["locator_kind"] = call.locator.locator_kind.value
        if call.locator.section_ref is not None:
            arguments["locator_section_ref"] = call.locator.section_ref
        if call.locator.table_ref is not None:
            arguments["locator_table_ref"] = call.locator.table_ref
    if call.extra is not None:
        for key, value in call.extra.items():
            if isinstance(value, (str, int)):
                arguments[key] = value
    return arguments


def _trace_entry(
    tool_name: ToolName | str,
    arguments: dict[str, ToolArgumentValue],
    result_kind: ToolResultKind,
    failure_code: FailureCode | None,
) -> ToolTraceEntry:
    """构造 LLM runner 的工具调用轨迹。"""

    return ToolTraceEntry(
        tool_name=tool_name,
        arguments=arguments,
        result_kind=result_kind,
        failure_code=failure_code,
    )


def _failed_result(
    trace: tuple[ToolTraceEntry, ...],
    code: FailureCode,
    message: str,
) -> AgentRunResult:
    """构造 fail-closed 的 AgentRunResult。"""

    return AgentRunResult(
        answer="",
        citations=(),
        tool_trace=trace,
        failure=ToolFailure(code=code, message=message),
    )


def _citation_key(citation: Citation) -> tuple[str, str, str | None, str | None, int | None]:
    """构造 citation 身份键，避免 final answer 伪造 citation。"""

    return (
        citation.document_id,
        citation.locator.locator_kind.value,
        citation.locator.section_ref,
        citation.locator.table_ref,
        citation.locator.page_no,
    )


def _public_citation(citation: Citation) -> Citation:
    """移除 LLM 最终输出不需要的 parser 内部引用字段。"""

    public_locator = replace(
        citation.locator,
        internal_ref=None,
        internal_ref_available=False,
        bbox=None,
    )
    return replace(citation, locator=public_locator)


def _aggregate_citations(
    result: AggregateMultiYearAnnualPerformanceResult,  # noqa: F821
) -> tuple[Citation, ...]:
    """从 AggregateMultiYearAnnualPerformanceResult 提取所有字段级 table citations。"""

    return tuple(
        field_citation.citation
        for series in result.series
        for field_citation in series.citations
    )


def _aggregate_evidence_text(
    result: AggregateMultiYearAnnualPerformanceResult,  # noqa: F821
) -> str:
    """把 AggregateMultiYearAnnualPerformanceResult 转换为有界证据文本。"""

    lines: list[str] = []
    for series in result.series:
        lines.append(f"fund_code={series.fund_code}")
        lines.append(f"coverage_status={series.coverage_status}")
        lines.append(f"covered_years={','.join(str(y) for y in series.covered_years)}")
        if series.missing_years:
            lines.append(f"missing_years={','.join(str(y) for y in series.missing_years)}")
        for row in series.rows:
            lines.append(
                f"year={row.year} | "
                f"annual_nav_growth_rate={row.annual_nav_growth_rate} | "
                f"annual_benchmark_return_rate={row.annual_benchmark_return_rate} | "
                f"annual_excess_return={row.annual_excess_return}"
            )
    return "\n".join(lines)
