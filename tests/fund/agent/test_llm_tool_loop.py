"""fake/injected LLM tool-loop contract 的 Slice 8A 测试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from fund_agent.agent import FakeLlmClient, FinalAnswer, LlmToolLoopRunner, ToolCall, ToolResult
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import Citation, Locator, ReportIdentity, SearchResult, TableSummary, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service.reading_service import (
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
    assert result.citations == ()


def test_fake_llm_no_evidence_fact_fails_closed(tmp_path: Path) -> None:
    """LLM final answer 中关键事实不在工具证据内时必须 fail-closed。"""

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

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.citations == ()


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
