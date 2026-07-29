"""fake/injected LLM tool-loop contract 的 Slice 8A 测试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from fund_agent.agent import ChatResponse, FakeLlmClient, FinalAnswer, LlmToolLoopRunner, TokenUsage, ToolCall, ToolResult
from fund_agent.agent.context_budget import ContextBudgetState
from fund_agent.agent.llm_tool_loop import _cap_tool_results, _normalize_document_id, _document_id_matches
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import Citation, Locator, ReportIdentity, SearchResult, TableSummary, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service.extraction import (
    AggregateMultiYearAnnualPerformanceResult,
    AnnualPerformanceFieldCitation,
    MultiYearAnnualPerformanceRow,
    MultiYearAnnualPerformanceSeries,
)


def _identity() -> ReportIdentity:
    """构造测试用报告身份。"""

    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-secret-import-id",
        content_fingerprint="abc123def4567890abc123def4567890",
        document_id="004393-2024-annual_report-abc123def4567890",
    )


def _write_docling_json(path: Path) -> None:
    """写入含章节和表格的 Docling-shaped JSON，用于 LLM tool loop 测试。"""

    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "4.1.2 基金经理简介",
                "level": 1,
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理在本报告期内保持稳定。基金经理张明负责本基金投资管理。",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "7.4.7.11 前十大持仓",
                "level": 1,
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "前十大持仓信息见下表，包含贵州茅台等证券。",
                "prov": [{"page_no": 2}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1, "bbox": {"l": 10, "t": 20, "r": 30, "b": 40}}],
                "captions": [],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "姓名",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "职务",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "张明",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "本基金的基金经理",
                        },
                    ]
                },
            },
            {
                "self_ref": "#/tables/1",
                "label": "table",
                "prov": [{"page_no": 2, "bbox": {"l": 11, "t": 21, "r": 31, "b": 41}}],
                "captions": [],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "证券名称",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "市值",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "贵州茅台",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "1000",
                        },
                    ]
                },
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service(tmp_path: Path) -> FundDocumentToolService:
    """复用 FundDocumentToolService + DoclingDocumentStore fixture，不跑真实 conversion。"""

    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
    _write_docling_json(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def _section_ref_from_search(results: tuple[ToolResult, ...]) -> str:
    """从最近的 search_document ToolResult 中取 section_ref。"""

    search_results = results[-1].result
    assert isinstance(search_results, tuple)
    hit = search_results[0]
    assert isinstance(hit, SearchResult)
    return hit.section_ref


def _first_table_ref(results: tuple[ToolResult, ...]) -> str:
    """从最近的 list_tables ToolResult 中取 table_ref。"""

    table_summaries = results[-1].result
    assert isinstance(table_summaries, tuple)
    table = table_summaries[0]
    assert isinstance(table, TableSummary)
    return table.table_ref


def _final_with_latest_citation(answer: str, key_fact: str) -> Callable[[tuple[ToolResult, ...]], FinalAnswer]:
    """构造使用最近工具 citation 的 fake final-answer factory。"""

    def _factory(results: tuple[ToolResult, ...]) -> FinalAnswer:
        return FinalAnswer(
            answer=answer,
            citations=results[-1].citations,
            key_facts=(key_fact,),
        )

    return _factory


def test_fake_llm_searches_reads_section_then_answers_with_section_citation(tmp_path: Path) -> None:
    """fake LLM 必须通过 search_document/read_section 取证后回答并带 section citation。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert result.answer == "基金经理张明负责本基金投资管理。"
    assert len(result.citations) == 1
    assert result.citations[0].locator.section_ref == "section-0000"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
    )


def test_fake_llm_reads_table_then_answers_with_table_citation(tmp_path: Path) -> None:
    """fake LLM 可调用 list_tables/read_table，并用 table citation 支撑表格事实。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                ToolCall(tool_name=ToolName.LIST_TABLES, document_id=_identity().document_id),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_TABLE,
                    document_id=_identity().document_id,
                    table_ref=_first_table_ref(results),
                ),
                _final_with_latest_citation("表格披露基金经理为张明。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "张明" in result.answer
    assert len(result.citations) == 1
    assert result.citations[0].locator.table_ref == "table-0000"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
    )


def test_fake_llm_final_answer_without_evidence_fails_closed(tmp_path: Path) -> None:
    """LLM 未调用工具就直接 final answer 时必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer="基金经理是张明。",
                    citations=(),
                    key_facts=("张明",),
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.citations == ()
    assert result.tool_trace == ()


def test_fake_llm_unknown_tool_fails_closed(tmp_path: Path) -> None:
    """LLM 请求未知工具必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name="extract_fields",
                    document_id=_identity().document_id,
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.tool_trace[0].tool_name == "extract_fields"
    assert result.tool_trace[0].result_kind == "failure"


def test_fake_llm_unauthorized_tool_fails_closed(tmp_path: Path) -> None:
    """LLM 请求未授权的已知工具必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.LIST_REPORTS,
                    document_id=_identity().document_id,
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.tool_trace[0].tool_name is ToolName.LIST_REPORTS
    assert result.tool_trace[0].result_kind == "failure"


def test_fake_llm_missing_citation_fails_closed(tmp_path: Path) -> None:
    """LLM 有工具证据但 final answer 缺 citation 时必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=(),
                    key_facts=("张明",),
                ),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""


def test_fake_llm_no_evidence_fact_fails_closed(tmp_path: Path) -> None:
    """LLM final answer 中关键事实不在工具证据内时：key_facts 校验已放宽（citation 校验已足够）。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                lambda results: FinalAnswer(
                    answer="基金经理为李雷。",
                    citations=results[-1].citations,
                    key_facts=("李雷",),
                ),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    # key_facts 校验已放宽，citation 校验仍生效
    assert result.failure is None
    assert "李雷" in result.answer


def test_llm_tool_loop_output_does_not_leak_private_payload_or_paths(tmp_path: Path) -> None:
    """LLM runner 输出不得泄漏 raw Docling JSON、本地路径、cache path 或 local_import_id。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")
    rendered = str(asdict(result))

    assert result.failure is None
    assert str(tmp_path) not in rendered
    assert "private-cache" not in rendered
    assert ".docling.json" not in rendered
    assert "schema_name" not in rendered
    assert "texts" not in rendered
    assert "tables" not in rendered
    assert _identity().local_import_id not in rendered


def _fake_table_citation(year: int, table_ref: str) -> Citation:
    """构造用于多年度业绩测试的 fake table citation。"""

    return Citation(
        document_id=_identity().document_id,
        fund_code=_identity().fund_code,
        fund_name=_identity().fund_name,
        year=year,
        report_type=ReportType.ANNUAL_REPORT.value,
        locator=Locator(
            document_id=_identity().document_id,
            locator_kind=LocatorKind.TABLE,
            section_ref="section-0000",
            table_ref=table_ref,
            page_no=2,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        ),
    )


def _citations_from_result(result: AggregateMultiYearAnnualPerformanceResult) -> tuple[Citation, ...]:
    """从 AggregateMultiYearAnnualPerformanceResult 提取所有 Citation 对象。"""

    return tuple(
        field_citation.citation
        for series in result.series
        for field_citation in series.citations
    )


def _fake_multi_year_result(
    *,
    years: tuple[int, ...],
    missing: tuple[int, ...] = (),
) -> AggregateMultiYearAnnualPerformanceResult:
    """构造用于测试的 fake AggregateMultiYearAnnualPerformanceResult。"""

    covered = tuple(y for y in years if y not in missing)
    rows = tuple(
        MultiYearAnnualPerformanceRow(
            year=y,
            annual_nav_growth_rate="17.32%",
            annual_benchmark_return_rate="12.50%",
            annual_excess_return="4.82%",
            citations=(
                AnnualPerformanceFieldCitation(
                    field_name="annual_nav_growth_rate",
                    citation=_fake_table_citation(y, f"table-{y}-nav"),
                ),
                AnnualPerformanceFieldCitation(
                    field_name="annual_benchmark_return_rate",
                    citation=_fake_table_citation(y, f"table-{y}-bench"),
                ),
                AnnualPerformanceFieldCitation(
                    field_name="annual_excess_return",
                    citation=_fake_table_citation(y, f"table-{y}-excess"),
                ),
            ),
        )
        for y in covered
    )
    citations = tuple(field_citation for row in rows for field_citation in row.citations)
    coverage_status = "complete" if not missing else "partial"
    series = MultiYearAnnualPerformanceSeries(
        fund_code=_identity().fund_code,
        requested_years=years,
        covered_years=covered,
        missing_years=missing,
        coverage_status=coverage_status,
        coverage_count=len(covered),
        minimum_required_count=3,
        share_class_scope="A",
        rows=rows,
        citations=citations,
    )
    return AggregateMultiYearAnnualPerformanceResult(series=(series,), failure=None)


def _aggregate_tool_call(extra: dict[str, object]) -> ToolCall:
    """构造 aggregate_multi_year_annual_performance 的 ToolCall。"""

    return ToolCall(
        tool_name=ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE,
        document_id=_identity().document_id,
        extra=extra,
    )


def _aggregate_extra() -> dict[str, object]:
    """返回 5 年 partial coverage 的 fake aggregate 参数。"""

    return {
        "fund_code": _identity().fund_code,
        "requested_years": (2020, 2021, 2022, 2023, 2024),
        "annual_report_documents": [
            {"year": 2020, "document_id": "doc-2020"},
            {"year": 2021, "document_id": "doc-2021"},
            {"year": 2022, "document_id": "doc-2022"},
            {"year": 2023, "document_id": "doc-2023"},
        ],
        "share_class": "A",
    }


def test_fake_llm_aggregate_multi_year_partial_coverage_preserves_metadata(tmp_path: Path) -> None:
    """partial coverage 时 final answer 必须包含 coverage_status、covered_years、missing_years。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=partial, covered_years=2020-2023, missing_years=2024, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert "partial" in result.answer
    assert "2020" in result.answer
    assert "2023" in result.answer
    assert "2024" in result.answer
    assert len(result.citations) > 0
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE,
    )


def test_fake_llm_aggregate_multi_year_complete_coverage_no_invented_missing_years(tmp_path: Path) -> None:
    """complete coverage 时 final answer 不得虚构 missing_years。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=complete, covered_years=2020-2024, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert "complete" in result.answer
    assert "missing_years" not in result.answer


def test_fake_llm_aggregate_multi_year_tool_failure_not_found_returns_agent_failure(tmp_path: Path) -> None:
    """aggregate handler 返回 not_found failure 时 runner 必须返回 AgentRunResult.failure。"""

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return AggregateMultiYearAnnualPerformanceResult(
            series=(),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message="multi-year annual performance 覆盖不足 3 年"),
        )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            FinalAnswer(answer="不应到达", citations=(), key_facts=()),
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.NOT_FOUND
    assert result.answer == ""


def test_fake_llm_aggregate_multi_year_tool_failure_identity_mismatch_returns_agent_failure(
    tmp_path: Path,
) -> None:
    """aggregate handler 返回 identity_mismatch failure 时 runner 必须返回 AgentRunResult.failure。"""

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return AggregateMultiYearAnnualPerformanceResult(
            series=(),
            failure=ToolFailure(code=FailureCode.IDENTITY_MISMATCH, message="multi-year annual report identity 不匹配"),
        )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            FinalAnswer(answer="不应到达", citations=(), key_facts=()),
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.IDENTITY_MISMATCH
    assert result.answer == ""


def test_fake_llm_aggregate_multi_year_final_answer_includes_per_year_citations(tmp_path: Path) -> None:
    """final answer citations 必须包含 per-year per-field table locator citations。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=partial, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert len(result.citations) == 12  # 4 years * 3 fields
    for citation in result.citations:
        assert citation.locator.locator_kind is LocatorKind.TABLE
        assert citation.locator.table_ref is not None


def test_fake_llm_aggregate_multi_year_final_answer_no_investment_judgment(tmp_path: Path) -> None:
    """final answer 不得包含年化收益率、扣费后收益率或投资判断。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=partial, 年度净值增长率 17.32%, 超额收益 4.82%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert "年化收益率" not in result.answer
    assert "扣费后收益率" not in result.answer
    assert "R=A+B-C" not in result.answer
    assert "annualized" not in result.answer
    assert "fee-adjusted" not in result.answer


def test_fake_llm_aggregate_multi_year_no_leakage(tmp_path: Path) -> None:
    """输出不得泄漏 raw Docling JSON、本地路径、cache path 或 local_import_id。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩聚合完成, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")
    rendered = str(asdict(result))

    assert result.failure is None
    assert str(tmp_path) not in rendered
    assert "private-cache" not in rendered
    assert ".docling.json" not in rendered
    assert "schema_name" not in rendered
    assert "texts" not in rendered
    assert "tables" not in rendered
    assert _identity().local_import_id not in rendered


# ── Fix 3: tool call dedup ─────────────────────────────────────────────

class _DuplicateToolCallClient:
    """search → read_section → 重复 read_section → final answer。"""

    def __init__(self, document_id: str) -> None:
        self._document_id = document_id
        self._step = 0
        self._section_ref: str | None = None

    def next_step(self, *, document_id, query, tool_results, remaining_budget=None):
        if self._step == 0:
            self._step = 1
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=self._document_id,
                query="基金经理",
            ))
        if self._step == 1:
            self._step = 2
            search_results = tool_results[-1].result
            self._section_ref = search_results[0].section_ref
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=self._document_id,
                section_ref=self._section_ref,
            ))
        if self._step == 2:
            self._step = 3
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=self._document_id,
                section_ref=self._section_ref,
            ))
        section_citation = tool_results[-1].citations[0]
        return ChatResponse(step=FinalAnswer(
            answer="基金经理张明负责本基金投资管理。",
            citations=(section_citation,),
            key_facts=("张明",),
        ))


def test_duplicate_tool_call_reuses_cached_result(tmp_path: Path) -> None:
    """重复 (tool_name, arguments) 调用复用缓存结果，不重新执行。"""
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=_DuplicateToolCallClient(_identity().document_id),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "张明" in result.answer
    # trace 记录 search_document + 第一次 read_section（第二次 read_section 去重跳过）
    assert len(result.tool_trace) == 2
    trace_names = tuple(entry.tool_name for entry in result.tool_trace)
    assert trace_names == (ToolName.SEARCH_DOCUMENT, ToolName.READ_SECTION)


def test_dedup_preserves_tool_results_in_order(tmp_path: Path) -> None:
    """去重后 tool_results 保持顺序（缓存结果追加到正确位置）。"""
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=_DuplicateToolCallClient(_identity().document_id),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    # final answer 应该成功（citations 来自缓存的 read_section result）
    assert len(result.citations) >= 1
    assert result.citations[0].locator.section_ref is not None


class TestForceAnswerDegradation:
    """max_steps 耗尽时 force_answer 降级策略测试。"""

    def test_max_steps_exhausted_returns_evidence_not_error(self, tmp_path: Path) -> None:
        """max_steps=1 且 LLM 一直调用工具不给 FinalAnswer → 用已收集证据拼成回答。"""
        service = _service(tmp_path)
        identity = _identity()

        # LLM 一直调用 search_document，不给 FinalAnswer；max_steps=2 → 执行 2 步就耗尽
        # 用 max_steps=2 因为 force_answer 需要至少 1 个成功的 tool_result
        def always_search(doc: str, q: str, tr: tuple) -> ChatResponse:
            return ChatResponse(
                step=ToolCall(tool_name=ToolName.SEARCH_DOCUMENT, document_id=doc, query="基金经理"),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        class AlwaysSearchLlm:
            def next_step(self, **kwargs):
                return always_search(kwargs["document_id"], kwargs["query"], kwargs["tool_results"])

        runner = LlmToolLoopRunner(
            tool_service=service,
            llm_client=AlwaysSearchLlm(),
            max_steps=2,
        )
        result = runner.run(document_id=identity.document_id, query="基金经理")

        # 应该成功返回证据，不报错
        assert result.failure is None
        assert result.answer != ""
        assert len(result.tool_trace) > 0

    def test_max_steps_exhausted_no_evidence_returns_error(self, tmp_path: Path) -> None:
        """max_steps 耗尽且无任何 tool_results → 返回 unavailable 错误。"""
        service = _service(tmp_path)
        identity = _identity()

        # LLM 一直返回未知工具，每次都 fail
        def always_unknown(doc: str, q: str, tr: tuple) -> ChatResponse:
            return ChatResponse(
                step=ToolCall(tool_name="unknown_tool", document_id=doc, query="test"),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        class AlwaysUnknownLlm:
            def next_step(self, **kwargs):
                return always_unknown(kwargs["document_id"], kwargs["query"], kwargs["tool_results"])

        runner = LlmToolLoopRunner(
            tool_service=service,
            llm_client=AlwaysUnknownLlm(),
            max_steps=1,
        )
        result = runner.run(document_id=identity.document_id, query="test")

        # 无证据 → 仍然报错
        assert result.failure is not None
        assert result.failure.code == FailureCode.UNAVAILABLE

    def test_force_answer_aggregates_citations(self, tmp_path: Path) -> None:
        """force_answer 应聚合所有 tool_results 的 citations。"""
        service = _service(tmp_path)
        identity = _identity()

        call_count = 0

        def search_then_read(doc: str, q: str, tr: tuple) -> ChatResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ChatResponse(
                    step=ToolCall(tool_name=ToolName.SEARCH_DOCUMENT, document_id=doc, query="基金经理"),
                    usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            # 第二次调用 read_section
            return ChatResponse(
                step=ToolCall(tool_name=ToolName.READ_SECTION, document_id=doc, section_ref="section-0000"),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        class SearchThenReadLlm:
            def next_step(self, **kwargs):
                return search_then_read(kwargs["document_id"], kwargs["query"], kwargs["tool_results"])

        runner = LlmToolLoopRunner(
            tool_service=service,
            llm_client=SearchThenReadLlm(),
            max_steps=3,
        )
        result = runner.run(document_id=identity.document_id, query="基金经理")

        # 应该成功返回证据
        assert result.failure is None
        assert result.answer != ""
        # citations 应该来自 tool_results
        assert len(result.citations) > 0


# ── ToolCallsRemaining ───────────────────────────────────────────────────


class _RemainingBudgetSpy:
    """记录每次 next_step 收到的 remaining_budget。"""

    def __init__(self, document_id: str, section_ref: str = "section-0000") -> None:
        self._doc_id = document_id
        self._section_ref = section_ref
        self._call = 0
        self.remaining_budgets: list[int | None] = []

    def next_step(self, *, document_id, query, tool_results, remaining_budget=None):
        self.remaining_budgets.append(remaining_budget)
        self._call += 1
        if self._call == 1:
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT, document_id=self._doc_id, query="基金经理",
            ))
        if self._call == 2:
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.READ_SECTION, document_id=self._doc_id, section_ref=self._section_ref,
            ))
        citations = tool_results[-1].citations if tool_results else ()
        return ChatResponse(step=FinalAnswer(
            answer="基金经理张明负责本基金投资管理。",
            citations=citations,
            key_facts=("张明",),
        ))


class TestToolCallsRemaining:
    """remaining_budget 注入测试。"""

    def test_tool_calls_remaining_decrements(self, tmp_path: Path) -> None:
        """验证每步 remaining_budget 逐次递减：max_steps → max_steps-1 → ..."""
        client = _RemainingBudgetSpy(_identity().document_id, section_ref="section-0000")
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path), llm_client=client, max_steps=5,
        )
        result = runner.run(document_id=_identity().document_id, query="基金经理")
        assert result.failure is None
        # 3 次调用：search → read_section → final answer
        assert client.remaining_budgets == [5, 4, 3]

    def test_remaining_budget_none_when_not_set(self) -> None:
        """不传 remaining_budget 时默认为 None（向后兼容）。"""
        client = FakeLlmClient([
            FinalAnswer(answer="test", citations=(), key_facts=()),
        ])
        response = client.next_step(document_id="d", query="q", tool_results=())
        assert response.step.answer == "test"

    def test_tool_calls_remaining_injected_in_run(self, tmp_path: Path) -> None:
        """通过 LlmToolLoopRunner.run() 验证 remaining_budget 被正确注入并递减。"""
        client = _RemainingBudgetSpy(_identity().document_id, section_ref="section-0000")
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path), llm_client=client, max_steps=3,
        )
        result = runner.run(document_id=_identity().document_id, query="基金经理")
        assert result.failure is None
        assert len(client.remaining_budgets) >= 2
        # 递减
        for i in range(len(client.remaining_budgets) - 1):
            assert client.remaining_budgets[i] is not None
            assert client.remaining_budgets[i + 1] is not None
            assert client.remaining_budgets[i] > client.remaining_budgets[i + 1]  # type: ignore[operator]


# ── ContextBudget Capping ────────────────────────────────────────────────


def _make_tool_result(evidence_text: str) -> ToolResult:
    """构造测试用 ToolResult，仅 evidence_text 有意义。"""
    return ToolResult(
        tool_name=ToolName.SEARCH_DOCUMENT,
        result=(),
        citations=(),
        evidence_text=evidence_text,
    )


class TestContextBudgetCapping:
    """_cap_tool_results 工具结果裁剪测试。"""

    def test_hard_limit_truncates_evidence(self) -> None:
        """预算超过硬限制时 evidence_text 被截断（remaining=0 → 全部丢弃）。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=9500)
        assert budget.is_above_hard_limit() is True

        results = [
            _make_tool_result("evidence text one"),
            _make_tool_result("evidence text two"),
        ]
        capped = _cap_tool_results(results, budget)
        assert capped == []

    def test_below_hard_limit_no_truncation(self) -> None:
        """预算未超硬限制时不做裁剪。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=5000)
        assert budget.is_above_hard_limit() is False

        results = [
            _make_tool_result("evidence text one"),
            _make_tool_result("evidence text two"),
        ]
        capped = _cap_tool_results(results, budget)
        assert capped == results
        assert len(capped) == 2
        assert capped[0].evidence_text == "evidence text one"

    def test_zero_remaining_returns_empty(self) -> None:
        """remaining=0 时返回空列表（无预算可分配）。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=10000)
        assert budget.is_above_hard_limit() is True
        assert budget.remaining_budget == 0

        results = [_make_tool_result("evidence text")]
        capped = _cap_tool_results(results, budget)
        assert capped == []

    def test_empty_tool_results_unchanged(self) -> None:
        """空 tool_results 直接返回空列表。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=9500)
        capped = _cap_tool_results([], budget)
        assert capped == []

    def test_model_context_window_zero_never_triggers(self) -> None:
        """model_context_window=0 时不触发裁剪。"""
        budget = ContextBudgetState(model_context_window=0, used_tokens=999999)
        assert budget.is_above_hard_limit() is False

        results = [_make_tool_result("evidence")]
        capped = _cap_tool_results(results, budget)
        assert capped == results

    def test_budget_consumer_integration(self) -> None:
        """模拟正常消费：低于硬限制时不截断，超过后截断。"""
        budget = ContextBudgetState(model_context_window=10000)
        # 首次：消耗 5000 token，仍在 hard_limit 内
        budget = budget.consume(5000)
        assert budget.is_above_hard_limit() is False

        results = [_make_tool_result("some evidence")]
        capped = _cap_tool_results(results, budget)
        assert capped == results

        # 继续消耗超过 hard_limit
        budget = budget.consume(5000)
        assert budget.is_above_hard_limit() is True

        capped = _cap_tool_results(results, budget)
        assert capped == []


# ── Document ID Prefix Matching ─────────────────────────────────────


class TestNormalizeDocumentId:
    """_normalize_document_id 测试。"""

    def test_normalize_basic(self):
        """正常 document_id 不变。"""
        assert _normalize_document_id("004393-2024-annual_report-abc123") == "004393-2024-annual_report-abc123"

    def test_normalize_strips_whitespace(self):
        """去除首尾空白。"""
        assert _normalize_document_id("  doc-id  ") == "doc-id"

    def test_normalize_empty(self):
        """空字符串归一化后仍为空。"""
        assert _normalize_document_id("") == ""


class TestDocumentIdMatches:
    """_document_id_matches 测试。"""

    def test_exact_match(self):
        """完全相同的 document_id 匹配。"""
        assert _document_id_matches("004393-2024-annual_report-abc", "004393-2024-annual_report-abc") is True

    def test_prefix_match_call_longer(self):
        """LLM 返回的 document_id 比预期多后缀 → 前缀匹配成功。"""
        assert _document_id_matches(
            "004393-2024-annual_report-abc123-extra-suffix",
            "004393-2024-annual_report-abc123",
        ) is True

    def test_prefix_match_expected_longer(self):
        """预期 document_id 比 LLM 返回的长 → 不匹配（不允许 LLM 缩短）。"""
        assert _document_id_matches(
            "004393-2024-annual_report",
            "004393-2024-annual_report-abc123-full",
        ) is False

    def test_mismatch(self):
        """完全不同的 document_id 不匹配。"""
        assert _document_id_matches("doc-a", "doc-b") is False

    def test_mismatch_partial(self):
        """部分重叠但不是前缀关系 → 不匹配。"""
        assert _document_id_matches("abc-2024-report", "abc-2025-report") is False


# ── Phase 7.4: interactive scene citation 校验放宽（方案 E）─────────────────


class TestInteractiveSceneCitationRelaxation:
    """interactive scene 跳过 citation + evidence 校验，保留投资建议检测。"""

    def test_interactive_skips_citation_and_evidence_check(self, tmp_path: Path) -> None:
        """interactive scene: 无工具调用 + 无 citation → 仍然成功返回。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(
                    answer="你好！有什么可以帮助你的？",
                    citations=(),
                    key_facts=(),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="你好",
            scene="interactive",
        )

        assert result.failure is None
        assert "你好" in result.answer

    def test_interactive_skips_citation_check_with_tools(self, tmp_path: Path) -> None:
        """interactive scene: 有工具调用但缺 citation → 仍然成功。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=(),  # 缺少 citation
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
            scene="interactive",
        )

        assert result.failure is None
        assert "张明" in result.answer

    def test_interactive_still_blocks_investment_advice(self, tmp_path: Path) -> None:
        """interactive scene: 投资建议关键词仍然 fail-closed。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(
                    answer="建议买入该基金，目标价5元。",
                    citations=(),
                    key_facts=(),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="这个基金怎么样？",
            scene="interactive",
        )

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE
        assert "投资建议" in result.failure.message

    def test_ask_scene_still_enforces_citation(self, tmp_path: Path) -> None:
        """默认 ask scene: 有工具证据但缺 citation → fail-closed。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=(),  # 缺少 citation
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
        )

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE
        assert "citation" in result.failure.message

    def test_ask_scene_still_enforces_evidence(self, tmp_path: Path) -> None:
        """默认 ask scene: 无工具调用直接回答 → fail-closed（缺 evidence）。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(
                    answer="基金经理是张明。",
                    citations=(),
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
        )

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE

    def test_interactive_preserves_llm_provided_citations(self, tmp_path: Path) -> None:
        """interactive scene: LLM 提供的 citation 被保留在结果中。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                lambda results: FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=results[-1].citations,
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
            scene="interactive",
        )

        assert result.failure is None
        assert len(result.citations) == 1
        assert result.citations[0].locator.section_ref == "section-0000"
