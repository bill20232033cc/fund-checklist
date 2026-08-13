"""Tool Trace 只读分析器的单元测试。"""

from __future__ import annotations

import inspect
import json

import pytest

from fund_agent.agent.tool_loop import ToolTraceEntry
from fund_agent.agent.tool_trace_analysis import (
    ToolTraceAnalysisPolicy,
    analyze_tool_trace,
    tool_trace_analysis_to_json,
)
from fund_agent.fund.document_tools.constants import FailureCode, ToolName


def _entry(
    tool_name: ToolName,
    *,
    result_kind: str = "success",
    arguments: dict[str, str | int | None] | None = None,
    failure_code: FailureCode | None = None,
) -> ToolTraceEntry:
    """构造最小 ToolTraceEntry。"""

    return ToolTraceEntry(
        tool_name=tool_name,
        arguments=arguments or {},
        result_kind=result_kind,
        failure_code=failure_code,
    )


def test_summary_mixed_trace_counts() -> None:
    """混合 trace（2 成功 + 1 失败）汇总计数正确。"""

    trace = (
        _entry(ToolName.SEARCH_DOCUMENT),
        _entry(ToolName.SEARCH_DOCUMENT, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
        _entry(ToolName.READ_SECTION),
    )

    report = analyze_tool_trace(trace, ToolTraceAnalysisPolicy())

    assert report.summary.total == 3
    assert report.summary.success == 2
    assert report.summary.failure == 1
    assert report.summary.unique_tools == 2


def test_by_tool_first_appearance_order_and_failure_codes() -> None:
    """by_tool 按首次出现顺序聚合，failure_codes 去重保序。"""

    trace = (
        _entry(ToolName.SEARCH_DOCUMENT, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
        _entry(ToolName.READ_SECTION),
        _entry(ToolName.SEARCH_DOCUMENT, result_kind="failure", failure_code=FailureCode.UNAVAILABLE),
        _entry(ToolName.SEARCH_DOCUMENT, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
    )

    report = analyze_tool_trace(trace, ToolTraceAnalysisPolicy())

    # toolA -> toolB -> toolA：by_tool 顺序保持 (toolA, toolB)
    assert [stat.tool_name for stat in report.by_tool] == [
        ToolName.SEARCH_DOCUMENT.value,
        ToolName.READ_SECTION.value,
    ]

    tool_a = report.by_tool[0]
    assert tool_a.total == 3
    assert tool_a.success == 0
    assert tool_a.failure == 3
    assert tool_a.failure_codes == (FailureCode.NOT_FOUND.value, FailureCode.UNAVAILABLE.value)

    tool_b = report.by_tool[1]
    assert tool_b.total == 1
    assert tool_b.success == 1
    assert tool_b.failure == 0
    assert tool_b.failure_codes == ()


def test_failed_call_findings_with_and_without_code() -> None:
    """failed_call：每条失败 entry 一条，detail 含 failure_code 或「无分类」。"""

    trace = (
        _entry(ToolName.READ_SECTION, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
        _entry(ToolName.READ_TABLE, result_kind="failure", failure_code=None),
    )

    report = analyze_tool_trace(trace, ToolTraceAnalysisPolicy())

    failed = [finding for finding in report.findings if finding.kind == "failed_call"]
    assert len(failed) == 2
    assert failed[0].tool_name == ToolName.READ_SECTION.value
    assert FailureCode.NOT_FOUND.value in failed[0].detail
    assert failed[1].tool_name == ToolName.READ_TABLE.value
    assert "无分类" in failed[1].detail


def test_repeated_failure_finding_threshold() -> None:
    """repeated_failure：同一 (tool_name, failure_code) 出现 ≥2 次补一条。"""

    trace = (
        _entry(ToolName.READ_SECTION, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
        _entry(ToolName.READ_SECTION, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
        _entry(ToolName.READ_SECTION, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
    )

    report = analyze_tool_trace(trace, ToolTraceAnalysisPolicy())

    repeated = [finding for finding in report.findings if finding.kind == "repeated_failure"]
    assert len(repeated) == 1
    assert "3 次" in repeated[0].detail

    single = (_entry(ToolName.READ_SECTION, result_kind="failure", failure_code=FailureCode.NOT_FOUND),)
    single_report = analyze_tool_trace(single, ToolTraceAnalysisPolicy())
    assert [finding for finding in single_report.findings if finding.kind == "repeated_failure"] == []


def test_large_arguments_boundary() -> None:
    """large_arguments：序列化长度 == 阈值不触发，== 阈值 + 1 触发。"""

    args_exact = {"query": "abc"}
    threshold = len(json.dumps(args_exact, ensure_ascii=False, sort_keys=True))

    exact_report = analyze_tool_trace(
        (_entry(ToolName.SEARCH_DOCUMENT, arguments=args_exact),),
        ToolTraceAnalysisPolicy(large_argument_chars=threshold),
    )
    assert [finding for finding in exact_report.findings if finding.kind == "large_arguments"] == []

    args_over = {"query": "abcd"}
    over_report = analyze_tool_trace(
        (_entry(ToolName.SEARCH_DOCUMENT, arguments=args_over),),
        ToolTraceAnalysisPolicy(large_argument_chars=threshold),
    )
    large = [finding for finding in over_report.findings if finding.kind == "large_arguments"]
    assert len(large) == 1
    assert str(threshold + 1) in large[0].detail
    assert str(threshold) in large[0].detail


def test_empty_trace_summary_and_fixed_limitations() -> None:
    """空 trace：summary 全 0、findings 空、limitations 恰好 4 条。"""

    report = analyze_tool_trace((), ToolTraceAnalysisPolicy())

    assert report.summary.total == 0
    assert report.summary.success == 0
    assert report.summary.failure == 0
    assert report.summary.unique_tools == 0
    assert report.by_tool == ()
    assert report.findings == ()
    assert len(report.limitations) == 4


def test_type_error_contract() -> None:
    """trace 非 tuple / 元素非 ToolTraceEntry / policy 非 ToolTraceAnalysisPolicy → TypeError。"""

    with pytest.raises(TypeError):
        analyze_tool_trace([], ToolTraceAnalysisPolicy())
    with pytest.raises(TypeError):
        analyze_tool_trace(("not-an-entry",), ToolTraceAnalysisPolicy())
    with pytest.raises(TypeError):
        analyze_tool_trace((), None)
    with pytest.raises(TypeError):
        analyze_tool_trace((), object())


def test_determinism_same_input_same_report() -> None:
    """同输入两次调用 report 相等。"""

    trace = (
        _entry(ToolName.SEARCH_DOCUMENT),
        _entry(ToolName.READ_SECTION, result_kind="failure", failure_code=FailureCode.NOT_FOUND),
        _entry(ToolName.SEARCH_DOCUMENT, result_kind="failure", failure_code=FailureCode.UNAVAILABLE),
    )

    report1 = analyze_tool_trace(trace, ToolTraceAnalysisPolicy())
    report2 = analyze_tool_trace(trace, ToolTraceAnalysisPolicy())

    assert report1 == report2
    assert report1.findings == report2.findings


def test_json_renderer_deterministic_and_utf8() -> None:
    """JSON renderer：确定性、sort_keys、中文不转义、尾换行。"""

    report = analyze_tool_trace(
        (_entry(ToolName.SEARCH_DOCUMENT, result_kind="failure", failure_code=FailureCode.NOT_FOUND),),
        ToolTraceAnalysisPolicy(),
    )

    text1 = tool_trace_analysis_to_json(report)
    text2 = tool_trace_analysis_to_json(report)

    assert text1 == text2
    assert text1.endswith("\n")
    assert json.loads(text1) == json.loads(text2)
    assert "只读消费显式传入的派生 trace" in text1  # ensure_ascii=False：中文原文
    # sort_keys：顶层 key 按字典序排列
    assert text1.index('"by_tool"') < text1.index('"findings"')
    assert text1.index('"findings"') < text1.index('"limitations"')
    assert text1.index('"limitations"') < text1.index('"summary"')

    with pytest.raises(TypeError):
        tool_trace_analysis_to_json({"summary": {}})


def test_read_only_signature_and_docstring() -> None:
    """analyze_tool_trace 签名只接受 (trace, policy)，模块 docstring 含只读声明。"""

    assert tuple(inspect.signature(analyze_tool_trace).parameters) == ("trace", "policy")
    module_doc = inspect.getmodule(analyze_tool_trace).__doc__ or ""
    assert "只读" in module_doc
