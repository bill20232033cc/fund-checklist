"""确定性的基金文档最小工具调用循环。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fund_agent.fund.document_tools.constants import FailureCode, ToolName
from fund_agent.fund.document_tools.models import Citation, SearchResult, SectionContent, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService

ToolResultKind = Literal["success", "failure"]
ToolArgumentValue = str | int | None

_NO_SEARCH_HIT_MESSAGE = "未找到可读取的匹配章节"


@dataclass(frozen=True)
class ToolTraceEntry:
    """单次工具调用轨迹。

    参数:
        tool_name: 调用的 public reading tool 名称。
        arguments: 传给工具的显式参数；不得包含本地路径或 raw payload。
        result_kind: 工具调用结果类别，取值为 success 或 failure。
        failure_code: 工具失败时的稳定失败分类；成功时为 None。

    返回:
        不可变 trace entry。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: ToolName
    arguments: dict[str, ToolArgumentValue]
    result_kind: ToolResultKind
    failure_code: FailureCode | None = None


@dataclass(frozen=True)
class AgentRunResult:
    """最小 Agent loop 的统一返回值。

    参数:
        answer: 最终回答；成功时只由 read_section 结果生成。
        citations: read_section 返回的 citation 元组。
        tool_trace: search_document/read_section 的调用轨迹。
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
    """只执行 search_document -> read_section 的确定性阅读 Agent。

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
            query: 检索关键词；Slice 4 验收使用“基金经理”。

        返回:
            AgentRunResult；成功时 answer 只来自 read_section 的 title/text/citation。

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
        return AgentRunResult(
            answer=_answer_from_section(section_result),
            citations=(section_result.citation,),
            tool_trace=tuple(trace),
            failure=None,
        )


def _section_ref_from_hit(hit: SearchResult) -> str | None:
    """从 search_document 命中中读取可用于 read_section 的章节引用。"""

    return hit.locator.section_ref or hit.section_ref


def _answer_from_section(section: SectionContent) -> str:
    """只使用 read_section 输出组装最终回答。"""

    return f"{section.title}\n\n{section.text}"


def _failed_result(trace: tuple[ToolTraceEntry, ...], failure: ToolFailure) -> AgentRunResult:
    """构造不含猜测回答的失败结果。"""

    return AgentRunResult(answer="", citations=(), tool_trace=trace, failure=failure)


def _search_arguments(document_id: str, query: str) -> dict[str, ToolArgumentValue]:
    """构造 search_document trace 参数。"""

    return {"document_id": document_id, "query": query}


def _read_section_arguments(document_id: str, section_ref: str) -> dict[str, ToolArgumentValue]:
    """构造 read_section trace 参数。"""

    return {"document_id": document_id, "section_ref": section_ref}


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
