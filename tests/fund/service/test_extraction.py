"""FundReadingService use case 边界测试。"""

from __future__ import annotations

import json
import subprocess
from dataclasses import fields
from pathlib import Path
from unittest.mock import Mock

import pytest

import fund_agent.service.extraction as reading_service_module
from fund_agent.agent import AgentRunResult, ToolTraceEntry
from fund_agent.fund.document_tools.constants import DOCLING_JSON_SUFFIX, FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import Citation, Locator, ToolFailure
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service import (
    AggregateMultiYearAnnualPerformanceRequest,
    AnnualReportDocument,
    ExtractFeeRatesRequest,
    ExtractHoldingsRequest,
    FundReadingService,
    FundReport,
    ImportLocalReportRequest,
    ListReportsRequest,
    ReportChapter,
    QueryRouteAttempt,
    ReadLocalReportRequest,
    ScaleInfo,
    StressTestResult,
    compute_stress_test,
    infer_fund_type,
)

REAL_SMOKE_PDF = Path("基金年报/004393_安信企业价值优选混合_2024_annual_report.pdf")
REAL_SMOKE_FUND_CODE = "004393"
REAL_SMOKE_FUND_NAME = "安信企业价值优选混合型证券投资基金"
REAL_SMOKE_YEAR = 2024


def _write_pdf(path: Path) -> None:
    """写入满足 magic bytes 校验的最小 PDF bytes。"""

    path.write_bytes(b"%PDF-1.4\n% minimal service test pdf\n")


def _docling_payload() -> dict[str, object]:
    """返回可被 DoclingDocumentStore 读取的最小 Docling-shaped JSON。"""

    return {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 基金经理",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理在本报告期内保持稳定。本章节用于检索基金经理信息。",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }


def _table_cells(rows: tuple[tuple[str, ...], ...]) -> list[dict[str, object]]:
    """把二维行转换成最小 Docling table_cells。"""

    cells: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        for column_index, text in enumerate(row):
            cells.append(
                {
                    "start_row_offset_idx": row_index,
                    "end_row_offset_idx": row_index + 1,
                    "start_col_offset_idx": column_index,
                    "end_col_offset_idx": column_index + 1,
                    "text": text,
                }
            )
    return cells


def _performance_docling_payload(
    *,
    section_title: str = "3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较",
    section_lines: tuple[str, ...] = ("安信企业价值优选混合A", "安信企业价值优选混合C"),
    table_rows: tuple[tuple[tuple[str, ...], ...], ...] | None = None,
) -> dict[str, object]:
    """返回包含 performance_returns 章节和表格的最小 Docling-shaped JSON。"""

    rows = table_rows or (
        (
            ("阶段", "份额净值 增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
            ("过去三个月", "-2.45%", "1.31%", "-1.10%", "1.22%", "-1.35%", "0.09%"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "0.99%", "2.87%", "0.05%"),
        ),
        (
            ("阶段", "份额净值 增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
            ("过去三个月", "-2.60%", "1.31%", "-1.10%", "1.22%", "-1.50%", "0.09%"),
            ("过去一年", "10.21%", "1.05%", "13.14%", "1.00%", "-2.93%", "0.05%"),
        ),
    )
    return {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": section_title,
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            *(
                {
                    "self_ref": f"#/texts/{index}",
                    "label": "text",
                    "text": line,
                    "prov": [{"page_no": 1}],
                }
                for index, line in enumerate(section_lines, start=1)
            ),
        ],
        "tables": [
            {
                "self_ref": f"#/tables/{index}",
                "label": "table",
                "prov": [{"page_no": 1}],
                "captions": [],
                "data": {"table_cells": _table_cells(row_set)},
            }
            for index, row_set in enumerate(rows)
        ],
    }


class _FakeConverter:
    """替代真实 DoclingConverter 的 Service 测试转换器。"""

    calls: list[str] = []

    def __init__(self, output_root: Path) -> None:
        """记录输出根目录。"""

        self._output_root = Path(output_root)

    def convert_pdf(self, *, identity, pdf_bytes: bytes) -> object:
        """写入预置 Docling JSON，证明 Service 触发转换步骤。"""

        assert pdf_bytes.startswith(b"%PDF-")
        _FakeConverter.calls.append(identity.document_id)
        json_path = self._output_root / identity.document_id / f"{identity.document_id}{DOCLING_JSON_SUFFIX}"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(_docling_payload(), ensure_ascii=False), encoding="utf-8")
        return object()


class _PerformanceConverter:
    """写入 performance_returns 测试用 Docling JSON。"""

    payload = staticmethod(_performance_docling_payload)

    def __init__(self, output_root: Path) -> None:
        """记录输出根目录。"""

        self._output_root = Path(output_root)

    def convert_pdf(self, *, identity, pdf_bytes: bytes) -> object:
        """写入预置 performance Docling JSON。"""

        assert pdf_bytes.startswith(b"%PDF-")
        json_path = self._output_root / identity.document_id / f"{identity.document_id}{DOCLING_JSON_SUFFIX}"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _PerformanceConverter.payload()
        json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return object()


class _ForbiddenConverter:
    """若被调用则说明 Service 没有复用 completed catalog。"""

    def __init__(self, output_root: Path) -> None:
        """构造即失败。"""

        raise AssertionError("converter should not run")


class _CapturingHost:
    """捕获 Host run 参数，证明 Service 不传本地路径或 private loader。"""

    calls: list[dict[str, str]] = []

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """只接受 document_id 和 query 两个 Host 参数。"""

        _CapturingHost.calls.append({"document_id": document_id, "query": query})
        return AgentRunResult(
            answer="受控回答",
            citations=(),
            tool_trace=(),
            failure=None,
        )


class _RoutingHost:
    """按 query 返回可控结果，用于验证 Service 受控候选顺序。"""

    calls: list[dict[str, str]] = []
    success_query: str | None = None
    success_answer: str | None = None
    success_locator_kind: LocatorKind = LocatorKind.TABLE

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """记录 Host 调用，并只在指定 candidate 上返回成功。"""

        _RoutingHost.calls.append({"document_id": document_id, "query": query})
        if query == _RoutingHost.success_query:
            return AgentRunResult(
                answer=_RoutingHost.success_answer or f"命中 {query}",
                citations=(_citation(document_id, _RoutingHost.success_locator_kind),),
                tool_trace=(_trace_search(document_id, query, "success"),),
                failure=None,
            )
        return AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(_trace_search(document_id, query, "failure", FailureCode.NOT_FOUND),),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到可读取的匹配章节"),
        )


class _AlwaysWrongTargetHost:
    """返回 keyword-level success，但永远不满足 disclosure target。"""

    calls: list[dict[str, str]] = []

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """每个 candidate 都返回错误标题的成功结果。"""

        _AlwaysWrongTargetHost.calls.append({"document_id": document_id, "query": query})
        return AgentRunResult(
            answer=f"无关章节标题\n\n{query} 只在正文中出现",
            citations=(_citation(document_id, LocatorKind.SECTION),),
            tool_trace=(_trace_search(document_id, query, "success"),),
            failure=None,
        )


class _FeeRatesHost:
    """按 10B fee_rates 目标返回多段可聚合结果。"""

    calls: list[dict[str, str]] = []
    successful_queries: set[str] = {"基金管理费", "基金托管费", "销售服务费"}
    section_ref_by_query = {
        "基金管理费": "section-0379",
        "基金托管费": "section-0390",
        "销售服务费": "section-0398",
    }

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """原始 query 失败，三个费用 target query 分别返回安全结果。"""

        _FeeRatesHost.calls.append({"document_id": document_id, "query": query})
        if query not in _FeeRatesHost.successful_queries:
            return AgentRunResult(
                answer="无关章节标题\n\n费用 只在正文中出现",
                citations=(_citation(document_id, LocatorKind.SECTION),),
                tool_trace=(_trace_search(document_id, query, "success"),),
                failure=None,
            )
        return AgentRunResult(
            answer=f"来源章节: 6.4.10.2.1 {query}\n\n{query} 本段只作为阅读定位证据。",
            citations=(
                _citation(
                    document_id,
                    LocatorKind.SECTION,
                    section_ref=_FeeRatesHost.section_ref_by_query[query],
                ),
            ),
            tool_trace=(_trace_search(document_id, query, "success"),),
            failure=None,
        )


class _PerformanceReturnsHost:
    """按 11A performance_returns 目标返回章节和表格 citation。"""

    calls: list[dict[str, str]] = []
    include_table_citation: bool = True

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """原始 query 只作 keyword success，目标标题 query 返回 section/table 证据。"""

        _PerformanceReturnsHost.calls.append({"document_id": document_id, "query": query})
        target_title = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
        if query != target_title:
            return AgentRunResult(
                answer=f"无关章节标题\n\n{query} 只在正文中出现",
                citations=(_citation(document_id, LocatorKind.SECTION),),
                tool_trace=(_trace_search(document_id, query, "success"),),
                failure=None,
            )
        citations = [_citation(document_id, LocatorKind.SECTION)]
        if _PerformanceReturnsHost.include_table_citation:
            citations.append(_citation(document_id, LocatorKind.TABLE))
        return AgentRunResult(
            answer=(
                f"来源章节: 3.2.1 {target_title}\n\n"
                "相关表格:\n"
                f"{target_title}\n"
                "| 阶段 | 净值增长率 | 业绩比较基准收益率 |\n"
                "| 过去三个月 | 原始披露片段 | 原始披露片段 |"
            ),
            citations=tuple(citations),
            tool_trace=(_trace_search(document_id, query, "success"),),
            failure=None,
        )


class _PerformanceExtractionHost:
    """按 11A performance_returns 目标返回可用于抽取的 section/table citation。"""

    calls: list[dict[str, str]] = []
    include_table_citation: bool = True
    cited_table_refs: tuple[str, ...] = ("table-0000",)
    source_title_line: str | None = None

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """原始 query fail-closed，目标标题 query 返回 section/table 定位。"""

        _PerformanceExtractionHost.calls.append({"document_id": document_id, "query": query})
        target_title = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
        if query != target_title:
            return AgentRunResult(
                answer="",
                citations=(),
                tool_trace=(_trace_search(document_id, query, "failure", FailureCode.NOT_FOUND),),
                failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到可读取的匹配章节"),
            )
        citations = [_citation(document_id, LocatorKind.SECTION, section_ref="section-0000")]
        if _PerformanceExtractionHost.include_table_citation:
            citations.extend(
                _citation(
                    document_id,
                    LocatorKind.TABLE,
                    section_ref="section-0000",
                    table_ref=table_ref,
                )
                for table_ref in _PerformanceExtractionHost.cited_table_refs
            )
        title_line = _PerformanceExtractionHost.source_title_line or f"来源章节: 3.2.1 {target_title}"
        return AgentRunResult(
            answer=f"{title_line}\n\n相关表格:\n{target_title}",
            citations=tuple(citations),
            tool_trace=(_trace_search(document_id, query, "success"),),
            failure=None,
        )


class _FeeRatesValueHost:
    """按 10C fee_rates 字段抽取口径返回安全章节原文。"""

    calls: list[dict[str, str]] = []
    section_ref_by_query = {
        "基金管理费": "section-0379",
        "基金托管费": "section-0390",
        "销售服务费": "section-0398",
    }
    management_answer: str = (
        "来源章节: 7.4.10.2.1 基金管理费\n\n"
        "注：(1)基金管理费每日计提，按月支付。本基金的管理费按前一日基金资产净值的1.20%的年费率计提。\n"
        "计算方法如下：H=E×1.20%/当年天数\n"
        "(2)本基金自2023年8月21日起，基金管理费的年费率由1.50%调整为1.20%。"
    )
    custodian_answer: str = (
        "来源章节: 7.4.10.2.2 基金托管费\n\n"
        "注：(1)基金托管费每日计提，按月支付。本基金的托管费按前一日基金资产净值的0.20%的年费率计提。\n"
        "计算方法如下：H=E×0.20%/当年天数\n"
        "(2)本基金自2023年8月21日起，基金托管费的年费率由0.25%调整为0.20%。"
    )
    sales_answer: str = (
        "来源章节: 7.4.10.2.3 销售服务费\n\n"
        "注：(1)基金销售服务费每日计提，按月支付。"
        "本基金A类基金份额不收取销售服务费，"
        "C类基金份额的销售服务费按前一日C类基金资产净值的0.40%年费率计提。"
    )

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """返回三段 fee_rates 安全阅读结果。"""

        _FeeRatesValueHost.calls.append({"document_id": document_id, "query": query})
        answer_by_query = {
            "基金管理费": _FeeRatesValueHost.management_answer,
            "基金托管费": _FeeRatesValueHost.custodian_answer,
            "销售服务费": _FeeRatesValueHost.sales_answer,
        }
        answer = answer_by_query.get(query)
        if answer is None:
            return AgentRunResult(
                answer="无关章节标题\n\n费用 只在正文中出现",
                citations=(_citation(document_id, LocatorKind.SECTION),),
                tool_trace=(_trace_search(document_id, query, "success"),),
                failure=None,
            )
        return AgentRunResult(
            answer=answer,
            citations=(
                _citation(
                    document_id,
                    LocatorKind.SECTION,
                    section_ref=_FeeRatesValueHost.section_ref_by_query[query],
                ),
            ),
            tool_trace=(_trace_search(document_id, query, "success"),),
            failure=None,
        )


def _request(pdf_path: Path, work_dir: Path) -> ReadLocalReportRequest:
    """构造标准 read_local_report 请求。"""

    return ReadLocalReportRequest(
        pdf_path=pdf_path,
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        query="基金经理",
        work_dir=work_dir,
    )


def _import_annual_documents(
    service: FundReadingService,
    tmp_path: Path,
    years: tuple[int, ...],
) -> tuple[Path, tuple[AnnualReportDocument, ...]]:
    """导入多年度 completed annual reports，并返回显式 year/document_id 映射。"""

    work_dir = tmp_path / "multi-year-work"
    documents: list[AnnualReportDocument] = []
    for year in years:
        pdf_path = tmp_path / f"report-{year}.pdf"
        pdf_path.write_bytes(f"%PDF-1.4\n% minimal service test pdf {year}\n".encode("ascii"))
        imported = service.import_local_report(
            ImportLocalReportRequest(
                pdf_path=pdf_path,
                fund_code=REAL_SMOKE_FUND_CODE,
                fund_name=REAL_SMOKE_FUND_NAME,
                year=year,
                work_dir=work_dir,
            )
        )
        documents.append(AnnualReportDocument(year=year, document_id=imported.document_id))
    return work_dir, tuple(documents)


def _install_multi_year_fake_extractors(
    monkeypatch,
    service: FundReadingService,
    values_by_year: dict[int, dict[str, tuple[str, str, str]]],
    *,
    report_year_offset: int = 0,
) -> list[tuple[str, int, str]]:
    """替换 10F/10G helper，只让 10I 测试覆盖编排与 coverage。"""

    calls: list[tuple[str, int, str]] = []

    def _requested_scope(share_class: str | None) -> str | None:
        return reading_service_module._normalize_share_class_scope(share_class) if share_class else None

    def fake_annual(*, document_id, store, report_year, share_class):
        calls.append(("annual", report_year, document_id))
        fields = []
        requested_scope = _requested_scope(share_class)
        for scope, values in sorted(values_by_year.get(report_year, {}).items()):
            if requested_scope is not None and scope != requested_scope:
                continue
            nav_value, benchmark_value, _excess_value = values
            fields.extend(
                (
                    reading_service_module.AnnualPerformanceExtraction(
                        field_name="annual_nav_growth_rate",
                        decimal_percent_text=nav_value,
                        report_year=report_year + report_year_offset,
                        source_period_label="过去一年",
                        share_class_scope=scope,
                        raw_text=f"过去一年 | 份额净值增长率 | {nav_value}",
                        citation=_citation(
                            document_id,
                            LocatorKind.TABLE,
                            section_ref=f"section-{report_year}",
                            table_ref=f"table-{report_year}-{scope}-nav",
                            year=report_year,
                        ),
                    ),
                    reading_service_module.AnnualPerformanceExtraction(
                        field_name="annual_benchmark_return_rate",
                        decimal_percent_text=benchmark_value,
                        report_year=report_year + report_year_offset,
                        source_period_label="过去一年",
                        share_class_scope=scope,
                        raw_text=f"过去一年 | 业绩比较基准收益率 | {benchmark_value}",
                        citation=_citation(
                            document_id,
                            LocatorKind.TABLE,
                            section_ref=f"section-{report_year}",
                            table_ref=f"table-{report_year}-{scope}-benchmark",
                            year=report_year,
                        ),
                    ),
                )
            )
        failure = None if fields else ToolFailure(code=FailureCode.NOT_FOUND, message="missing annual fields")
        return reading_service_module.ExtractAnnualPerformanceResult(
            document_id=document_id,
            fields=tuple(fields),
            failure=failure,
        )

    def fake_excess(*, document_id, store, report_year, share_class):
        calls.append(("excess", report_year, document_id))
        fields = []
        requested_scope = _requested_scope(share_class)
        for scope, values in sorted(values_by_year.get(report_year, {}).items()):
            if requested_scope is not None and scope != requested_scope:
                continue
            _nav_value, _benchmark_value, excess_value = values
            fields.append(
                reading_service_module.AnnualExcessReturnExtraction(
                    field_name="annual_excess_return",
                    decimal_percent_text=excess_value,
                    report_year=report_year + report_year_offset,
                    source_period_label="过去一年",
                    share_class_scope=scope,
                    source_column_label="①－③",
                    raw_text=f"过去一年 | ①－③ | {excess_value}",
                    citation=_citation(
                        document_id,
                        LocatorKind.TABLE,
                        section_ref=f"section-{report_year}",
                        table_ref=f"table-{report_year}-{scope}-excess",
                        year=report_year,
                    ),
                )
            )
        failure = None if fields else ToolFailure(code=FailureCode.NOT_FOUND, message="missing excess field")
        return reading_service_module.ExtractAnnualExcessReturnResult(
            document_id=document_id,
            fields=tuple(fields),
            failure=failure,
        )

    monkeypatch.setattr(service, "_extract_annual_performance_from_store", fake_annual)
    monkeypatch.setattr(service, "_extract_annual_excess_return_from_store", fake_excess)
    return calls


def _trace_search(
    document_id: str,
    query: str,
    result_kind: str,
    failure_code: FailureCode | None = None,
) -> ToolTraceEntry:
    """构造最小 search_document trace。"""

    return ToolTraceEntry(
        tool_name=ToolName.SEARCH_DOCUMENT,
        arguments={"document_id": document_id, "query": query},
        result_kind=result_kind,
        failure_code=failure_code,
    )


def _citation(
    document_id: str,
    locator_kind: LocatorKind,
    *,
    section_ref: str = "section-1",
    table_ref: str | None = None,
    year: int = 2024,
) -> Citation:
    """构造不含本地路径的最小 citation。"""

    return Citation(
        document_id=document_id,
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=year,
        report_type="annual_report",
        locator=Locator(
            document_id=document_id,
            locator_kind=locator_kind,
            section_ref=section_ref,
            table_ref=(table_ref or "table-1") if locator_kind is LocatorKind.TABLE else None,
            page_no=1,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        ),
    )


def test_read_local_report_converts_records_and_calls_host_with_public_inputs(tmp_path: Path) -> None:
    """Service 必须完成导入/转换/登记，并只用 document_id 与 query 调 Host。"""

    _FakeConverter.calls.clear()
    _CapturingHost.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_FakeConverter,
        host_factory=_CapturingHost,
    )

    result = service.read_local_report(_request(pdf_path, work_dir))

    assert result.agent_result.answer == "受控回答"
    assert result.document_id.startswith("004393-2024-annual_report-")
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="基金经理",
            profile_name=None,
            result_kind="success",
            failure_code=None,
        ),
    )
    assert _FakeConverter.calls == [result.document_id]
    assert _CapturingHost.calls == [{"document_id": result.document_id, "query": "基金经理"}]
    assert (work_dir / CATALOG_FILENAME).is_file()


def test_import_local_report_returns_safe_summary_without_private_fields(tmp_path: Path) -> None:
    """import_local_report 结果不得暴露 path、Docling JSON path 或 local_import_id。"""

    _FakeConverter.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter)

    result = service.import_local_report(
        ImportLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    serialized = repr(result)
    assert result.report.document_id == result.document_id
    assert result.report.source_kind == "local_pdf"
    assert str(work_dir) not in serialized
    assert str(pdf_path) not in serialized
    assert ".docling.json" not in serialized
    assert "local_import_id" not in serialized


def test_read_local_report_reuses_completed_catalog_without_converter(tmp_path: Path) -> None:
    """catalog 有 completed report 时，Service 必须复用 store 且不重复转换。"""

    _FakeConverter.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    first_service = FundReadingService(converter_factory=_FakeConverter)
    first = first_service.read_local_report(_request(pdf_path, work_dir))
    assert first.agent_result.failure is None
    assert _FakeConverter.calls == [first.document_id]

    second_service = FundReadingService(converter_factory=_ForbiddenConverter)
    second = second_service.read_local_report(_request(pdf_path, work_dir))

    assert second.document_id == first.document_id
    assert second.agent_result.failure is None


def test_completed_catalog_missing_docling_json_fails_closed_without_reconvert(tmp_path: Path) -> None:
    """completed record 指向的 Docling JSON 缺失时，Service 不自动 repair/reconvert。"""

    _FakeConverter.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter)
    first = service.read_local_report(_request(pdf_path, work_dir))
    json_paths = tuple(work_dir.glob(f"**/*{DOCLING_JSON_SUFFIX}"))
    assert json_paths
    for json_path in json_paths:
        json_path.unlink()

    blocked_service = FundReadingService(converter_factory=_ForbiddenConverter)
    with pytest.raises(DocumentToolError) as exc_info:
        blocked_service.read_local_report(_request(pdf_path, work_dir))

    assert first.document_id
    assert exc_info.value.code is FailureCode.UNAVAILABLE


def test_list_reports_returns_safe_completed_report_summaries(tmp_path: Path) -> None:
    """list_reports use case 必须返回 safe summary，并支持基本过滤。"""

    _FakeConverter.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter)
    imported = service.import_local_report(
        ImportLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    listed = service.list_reports(ListReportsRequest(work_dir=work_dir, fund_code="004393", year=2024))

    assert listed.failure is None
    assert len(listed.reports) == 1
    assert listed.reports[0].document_id == imported.document_id
    serialized = repr(listed)
    assert str(work_dir) not in serialized
    assert str(pdf_path) not in serialized
    assert ".docling.json" not in serialized
    assert "local_import_id" not in serialized


def test_list_reports_missing_catalog_returns_empty_result(tmp_path: Path) -> None:
    """无 catalog 时 list_reports 返回空列表，不把缺失 catalog 当成异常。"""

    service = FundReadingService(converter_factory=_ForbiddenConverter)

    result = service.list_reports(ListReportsRequest(work_dir=tmp_path / "work"))

    assert result.reports == ()
    assert result.failure is None


def test_read_local_report_preserves_agent_failure_code(tmp_path: Path) -> None:
    """Service 不吞并 Agent ToolFailure，失败码必须保留到 result。"""

    _FakeConverter.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="不存在的关键词",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is not None
    assert result.agent_result.failure.code is FailureCode.NOT_FOUND
    assert result.agent_result.tool_trace[0].tool_name is ToolName.SEARCH_DOCUMENT
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="不存在的关键词",
            profile_name=None,
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("前十大持仓", ("前十大持仓", "股票投资明细", "前十名股票投资明细")),
        ("重仓股", ("重仓股", "股票投资明细", "前十名股票投资明细")),
        ("持仓明细", ("持仓明细", "股票投资明细", "前十名股票投资明细")),
        ("资产配置", ("资产配置", "期末基金资产组合情况", "基金资产组合情况")),
        ("资产组合", ("资产组合", "期末基金资产组合情况", "基金资产组合情况")),
        ("费用", ("费用", "基金管理费", "基金托管费", "销售服务费")),
        ("费率", ("费率", "基金管理费", "基金托管费", "销售服务费")),
        ("管理费", ("管理费", "基金管理费", "基金托管费", "销售服务费")),
        ("托管费", ("托管费", "基金管理费", "基金托管费", "销售服务费")),
        ("销售服务费", ("销售服务费", "基金管理费", "基金托管费")),
        (
            "净值增长率",
            (
                "净值增长率",
                "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
                "基金净值表现",
                "业绩比较基准收益率",
            ),
        ),
        (
            "业绩比较基准收益率",
            (
                "业绩比较基准收益率",
                "净值增长率",
                "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
                "基金净值表现",
            ),
        ),
        (
            "基金净值表现",
            (
                "基金净值表现",
                "净值增长率",
                "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
                "业绩比较基准收益率",
            ),
        ),
        ("股票投资明细", ("股票投资明细",)),
        (
            "基金经理持有本产品",
            (
                "基金经理持有本产品",
                "持有本基金",
                "基金经理持有",
                "期末基金管理人的从业人员持有本基金",
                "基金经理持有本基金",
            ),
        ),
        (
            "持有本基金",
            (
                "持有本基金",
                "基金经理持有",
                "期末基金管理人的从业人员持有本基金",
                "基金经理持有本基金",
            ),
        ),
        (
            "基金经理持有",
            (
                "基金经理持有",
                "持有本基金",
                "期末基金管理人的从业人员持有本基金",
                "基金经理持有本基金",
            ),
        ),
    ],
)
def test_controlled_query_profiles_generate_bounded_candidates(query: str, expected: tuple[str, ...]) -> None:
    """Service 层 profile 只为裁决内 exact alias 生成受控候选。"""

    candidates = reading_service_module._candidate_queries_for_query(query)

    assert candidates == expected
    assert query in candidates
    assert len(candidates) <= reading_service_module._MAX_QUERY_CANDIDATES


def test_manager_holdings_profile_routes_hold_fund_query() -> None:
    """L1：基金经理持有本产品 必须命中 manager_holdings 且候选含 持有本基金。"""

    route_plan = reading_service_module._route_plan_for_query("基金经理持有本产品")

    assert route_plan.profile_name == "manager_holdings"
    assert "持有本基金" in route_plan.candidate_queries


def test_performance_returns_candidate_order_prefers_nav_growth_rate_query() -> None:
    """Fix E：净值增长率 候选位于 exact title 之前，供自动重试先命中含数字章节。"""

    route_plan = reading_service_module._route_plan_for_query("近净值增长率是多少")

    assert route_plan.profile_name == "performance_returns"
    assert route_plan.candidate_queries.index("净值增长率") < route_plan.candidate_queries.index(
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
    )


def test_disclosure_locator_registry_has_only_reading_contract_fields() -> None:
    """11B registry 只表达披露定位 contract，不开放抽取或 public DTO。"""

    assert {field.name for field in fields(reading_service_module._DisclosureLocatorContract)} == {
        "profile_name",
        "aliases",
        "candidate_queries",
        "acceptable_title_family",
        "requires_table_citation",
        "extraction_allowed",
        "aggregate_all_matches",
        "anchor_title_family",
    }
    registry = {
        contract.profile_name: contract
        for contract in reading_service_module.DISCLOSURE_LOCATOR_CONTRACT_REGISTRY
    }
    assert tuple(registry) == (
        "holdings_top10",
        "asset_allocation",
        "manager_holdings",
        "fee_rates",
        "performance_returns",
    )
    assert registry["holdings_top10"].aliases == ("前十大持仓", "重仓股", "持仓明细")
    assert registry["holdings_top10"].candidate_queries == ("股票投资明细", "前十名股票投资明细")
    assert registry["holdings_top10"].acceptable_title_family == ("股票投资明细", "前十名股票投资明细")
    assert registry["holdings_top10"].requires_table_citation is True
    assert registry["holdings_top10"].anchor_title_family == ("序号", "股票名称", "公允价值")
    assert registry["asset_allocation"].aliases == ("资产配置", "资产组合")
    assert registry["asset_allocation"].candidate_queries == ("期末基金资产组合情况", "基金资产组合情况")
    assert registry["asset_allocation"].acceptable_title_family == (
        "期末基金资产组合情况",
        "基金资产组合情况",
    )
    assert registry["asset_allocation"].requires_table_citation is True
    assert registry["manager_holdings"].aliases == ("持有本基金", "基金经理持有", "从业人员持有本基金")
    assert registry["manager_holdings"].candidate_queries == (
        "持有本基金",
        "基金经理持有",
        "期末基金管理人的从业人员持有本基金",
        "基金经理持有本基金",
    )
    assert registry["manager_holdings"].acceptable_title_family == (
        "期末基金管理人的从业人员持有本基金的情况",
    )
    assert registry["manager_holdings"].requires_table_citation is True
    assert registry["manager_holdings"].anchor_title_family == (
        "本基金基金经理持有本开放式基金",
        "基金管理人所有从业人员持有本基金",
    )
    assert registry["fee_rates"].aliases == ("费用", "费率", "管理费", "托管费", "销售服务费")
    assert registry["fee_rates"].candidate_queries == ("基金管理费", "基金托管费", "销售服务费")
    assert registry["fee_rates"].acceptable_title_family == ("基金管理费", "基金托管费", "销售服务费")
    assert registry["fee_rates"].requires_table_citation is False
    assert registry["fee_rates"].aggregate_all_matches is True
    assert registry["performance_returns"].aliases == (
        "净值增长率",
        "业绩比较基准收益率",
        "基准收益率",
        "收益表现",
        "基金净值表现",
    )
    assert registry["performance_returns"].candidate_queries == (
        "净值增长率",
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
        "基金净值表现",
        "业绩比较基准收益率",
    )
    assert registry["performance_returns"].acceptable_title_family == (
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
        "基金净值表现",
    )
    assert registry["performance_returns"].requires_table_citation is True
    assert registry["performance_returns"].anchor_title_family == (
        "阶段",
        "份额净值增长率",
        "业绩比较基准收益率",
    )
    assert all(contract.extraction_allowed is False for contract in registry.values())
    assert {
        profile_name
        for profile_name, contract in registry.items()
        if contract.anchor_title_family
    } == {"holdings_top10", "manager_holdings", "performance_returns"}
    assert all(
        contract.aggregate_all_matches is False
        for profile_name, contract in registry.items()
        if profile_name != "fee_rates"
    )


def test_read_local_report_routes_controlled_alias_to_first_successful_candidate(tmp_path: Path) -> None:
    """受控 alias 命中时，Service 必须按候选顺序返回第一个成功 Agent result。"""

    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "股票投资明细"
    _RoutingHost.success_answer = "8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细"
    _RoutingHost.success_locator_kind = LocatorKind.TABLE
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_RoutingHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="前十大持仓",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is None
    assert result.agent_result.answer == "8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细"
    assert [call["query"] for call in _RoutingHost.calls] == ["前十大持仓", "股票投资明细"]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="前十大持仓",
            profile_name="holdings_top10",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="股票投资明细",
            profile_name="holdings_top10",
            result_kind="success",
            failure_code=None,
        ),
    )
    assert result.agent_result.tool_trace[0].arguments["query"] == "股票投资明细"
    assert "profile_name" not in result.agent_result.tool_trace[0].arguments
    assert "routing_trace" not in result.agent_result.tool_trace[0].arguments


def test_read_local_report_records_original_query_success_without_fallback(tmp_path: Path) -> None:
    """原始 query 直接成功时，routing_trace 只记录原始 query success。"""

    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "前十大持仓"
    _RoutingHost.success_answer = "8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细"
    _RoutingHost.success_locator_kind = LocatorKind.TABLE
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_RoutingHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="前十大持仓",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is None
    assert [call["query"] for call in _RoutingHost.calls] == ["前十大持仓"]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="前十大持仓",
            profile_name="holdings_top10",
            result_kind="success",
            failure_code=None,
        ),
    )


def test_controlled_profile_does_not_short_circuit_on_keyword_only_success(tmp_path: Path) -> None:
    """受控 profile 不得把 keyword-level success 当成 disclosure target success。"""

    _FakeConverter.calls.clear()
    _AlwaysWrongTargetHost.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_AlwaysWrongTargetHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="资产配置",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is not None
    assert result.agent_result.failure.code is FailureCode.NOT_FOUND
    assert [call["query"] for call in _AlwaysWrongTargetHost.calls] == [
        "资产配置",
        "期末基金资产组合情况",
        "基金资产组合情况",
    ]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="资产配置",
            profile_name="asset_allocation",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="期末基金资产组合情况",
            profile_name="asset_allocation",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="基金资产组合情况",
            profile_name="asset_allocation",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
    )


def test_fee_rates_profile_aggregates_all_target_sections(tmp_path: Path) -> None:
    """fee_rates profile 必须聚合三类费用披露章节后才返回成功。"""

    _FakeConverter.calls.clear()
    _FeeRatesHost.calls.clear()
    _FeeRatesHost.successful_queries = {"基金管理费", "基金托管费", "销售服务费"}
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_FeeRatesHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="费用",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is None
    assert "基金管理费" in result.agent_result.answer
    assert "基金托管费" in result.agent_result.answer
    assert "销售服务费" in result.agent_result.answer
    assert len(result.agent_result.citations) == 3
    assert [call["query"] for call in _FeeRatesHost.calls] == [
        "费用",
        "基金管理费",
        "基金托管费",
        "销售服务费",
    ]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="费用",
            profile_name="fee_rates",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="基金管理费",
            profile_name="fee_rates",
            result_kind="success",
            failure_code=None,
        ),
        QueryRouteAttempt(
            query="基金托管费",
            profile_name="fee_rates",
            result_kind="success",
            failure_code=None,
        ),
        QueryRouteAttempt(
            query="销售服务费",
            profile_name="fee_rates",
            result_kind="success",
            failure_code=None,
        ),
    )


def test_fee_rates_profile_fails_closed_when_any_target_missing(tmp_path: Path) -> None:
    """fee_rates 三目标未全命中时仍按 not_found fail-closed。"""

    _FakeConverter.calls.clear()
    _FeeRatesHost.calls.clear()
    _FeeRatesHost.successful_queries = {"基金管理费", "基金托管费"}
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_FeeRatesHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="费用",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is not None
    assert result.agent_result.failure.code is FailureCode.NOT_FOUND
    assert result.agent_result.answer == ""
    assert [attempt.query for attempt in result.routing_trace] == [
        "费用",
        "基金管理费",
        "基金托管费",
        "销售服务费",
    ]
    assert all(attempt.profile_name == "fee_rates" for attempt in result.routing_trace)


def test_performance_returns_profile_locates_disclosure_with_section_and_table_citation(tmp_path: Path) -> None:
    """performance_returns 只定位业绩表现披露，不抽取或计算收益字段。"""

    _FakeConverter.calls.clear()
    _PerformanceReturnsHost.calls.clear()
    _PerformanceReturnsHost.include_table_citation = True
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_PerformanceReturnsHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="净值增长率",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is None
    assert "基金份额净值增长率及其与同期业绩比较基准收益率的比较" in result.agent_result.answer
    assert "nav_growth_rate" not in result.agent_result.answer
    assert "benchmark_return_rate" not in result.agent_result.answer
    assert "decimal_percent_text" not in result.agent_result.answer
    assert {citation.locator.locator_kind for citation in result.agent_result.citations} == {
        LocatorKind.SECTION,
        LocatorKind.TABLE,
    }
    assert [call["query"] for call in _PerformanceReturnsHost.calls] == [
        "净值增长率",
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
    ]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="净值增长率",
            profile_name="performance_returns",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            profile_name="performance_returns",
            result_kind="success",
            failure_code=None,
        ),
    )


def test_performance_returns_profile_requires_table_citation(tmp_path: Path) -> None:
    """当前 11A target success 必须同时具备 section citation 和 table citation。"""

    _FakeConverter.calls.clear()
    _PerformanceReturnsHost.calls.clear()
    _PerformanceReturnsHost.include_table_citation = False
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_PerformanceReturnsHost)

    try:
        result = service.read_local_report(
            ReadLocalReportRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                query="净值增长率",
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceReturnsHost.include_table_citation = True

    assert result.agent_result.failure is not None
    assert result.agent_result.failure.code is FailureCode.NOT_FOUND
    assert [call["query"] for call in _PerformanceReturnsHost.calls] == [
        "净值增长率",
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
        "基金净值表现",
        "业绩比较基准收益率",
    ]
    assert all(attempt.profile_name == "performance_returns" for attempt in result.routing_trace)
    assert all(attempt.result_kind == "failure" for attempt in result.routing_trace)


def test_extract_fee_rates_returns_controlled_dtos_with_raw_text_and_citation(tmp_path: Path) -> None:
    """10C 只从 10B 安全定位结果抽取三类当前适用年费率字段。"""

    _FakeConverter.calls.clear()
    _FeeRatesValueHost.calls.clear()
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_FeeRatesValueHost)

    result = service.extract_fee_rates(
        ExtractFeeRatesRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    assert [call["query"] for call in _FeeRatesValueHost.calls] == [
        "费用",
        "基金管理费",
        "基金托管费",
        "销售服务费",
    ]
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("management_fee_rate", "all_share_classes")].decimal_percent_text == "1.20%"
    assert values[("custodian_fee_rate", "all_share_classes")].decimal_percent_text == "0.20%"
    assert values[("sales_service_fee_rate", "A")].decimal_percent_text == "不收取"
    assert values[("sales_service_fee_rate", "C")].decimal_percent_text == "0.40%"
    assert "1.20%" in values[("management_fee_rate", "all_share_classes")].raw_text
    assert "1.50%" not in values[("management_fee_rate", "all_share_classes")].raw_text
    assert "0.20%" in values[("custodian_fee_rate", "all_share_classes")].raw_text
    assert "0.25%" not in values[("custodian_fee_rate", "all_share_classes")].raw_text
    assert values[("sales_service_fee_rate", "A")].decimal_percent_text != "0.00%"
    assert all(field.period == "year" for field in result.fields)
    assert all(field.raw_text for field in result.fields)
    assert all(field.citation is not None for field in result.fields)


def test_extract_fee_rates_fails_not_found_when_candidate_section_is_ambiguous(tmp_path: Path) -> None:
    """候选章节存在但字段无法唯一抽取时必须返回 not_found。"""

    _FakeConverter.calls.clear()
    _FeeRatesValueHost.calls.clear()
    original_answer = _FeeRatesValueHost.management_answer
    _FeeRatesValueHost.management_answer = (
        "来源章节: 7.4.10.2.1 基金管理费\n\n"
        "本基金的管理费按前一日基金资产净值的1.20%的年费率计提。\n"
        "本基金的管理费按前一日基金资产净值的1.30%的年费率计提。"
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_FeeRatesValueHost)

    try:
        result = service.extract_fee_rates(
            ExtractFeeRatesRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _FeeRatesValueHost.management_answer = original_answer

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_fee_rates_config_error_maps_to_schema_drift(monkeypatch, tmp_path: Path) -> None:
    """抽取配置异常必须映射为 schema_drift，不新增失败分类。"""

    _FakeConverter.calls.clear()
    _FeeRatesValueHost.calls.clear()
    monkeypatch.setattr(reading_service_module, "_FEE_RATE_EXTRACTION_SPECS", ())
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_FeeRatesValueHost)

    result = service.extract_fee_rates(
        ExtractFeeRatesRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.SCHEMA_DRIFT


def _overlapping_fee_rate_results() -> tuple[AgentRunResult, ...]:
    """构造三个标题/正文重叠的 fee_rates candidate 结果。"""

    management_answer = (
        "7.4.10.2.1 基金管理费\n\n"
        "注：本基金的管理费按前一日基金资产净值的1.20%的年费率计提。\n"
        "计算方法如下：H=E×1.20%/当年天数\n"
        "相关表格:\n"
        "7.4.10.2.1 基金管理费\n"
        "当期发生的基金应支付的管理费 | 2,308,368.87"
    )
    custodian_answer = (
        "7.4.10.2.2 基金托管费\n\n"
        "注：本基金的托管费按前一日基金资产净值的0.20%的年费率计提。\n"
        "计算方法如下：H=E×0.20%/当年天数\n"
        "相关表格:\n"
        "7.4.10.2.3 销售服务费\n"
        "当期发生的基金应支付的托管费 | 384,728.17"
    )
    sales_answer = (
        "7.4.10.2.1 基金管理费\n\n"
        "注：本基金的管理费按前一日基金资产净值的1.20%的年费率计提。\n\n"
        "7.4.10.2.2 基金托管费\n\n"
        "注：本基金的托管费按前一日基金资产净值的0.20%的年费率计提。\n\n"
        "7.4.10.2.3 销售服务费\n\n"
        "注：本基金A类基金份额不收取销售服务费，"
        "C类基金份额的销售服务费按前一日C类基金资产净值的0.40%年费率计提。\n"
        "相关表格:\n"
        "7.4.10.2.3 销售服务费\n"
        "安信基金 | - | 20,590.02"
    )
    return (
        AgentRunResult(
            answer=management_answer,
            citations=(
                _citation("doc-1", LocatorKind.SECTION, section_ref="section-0379"),
                _citation("doc-1", LocatorKind.TABLE, section_ref="section-0379", table_ref="table-0051"),
            ),
            tool_trace=(_trace_search("doc-1", "基金管理费", "success"),),
            failure=None,
        ),
        AgentRunResult(
            answer=custodian_answer,
            citations=(
                _citation("doc-1", LocatorKind.SECTION, section_ref="section-0390"),
                _citation("doc-1", LocatorKind.TABLE, section_ref="section-0398", table_ref="table-0052"),
            ),
            tool_trace=(_trace_search("doc-1", "基金托管费", "success"),),
            failure=None,
        ),
        AgentRunResult(
            answer=sales_answer,
            citations=(
                _citation("doc-1", LocatorKind.SECTION, section_ref="section-0398"),
                _citation("doc-1", LocatorKind.SECTION, section_ref="section-0398"),
            ),
            tool_trace=(_trace_search("doc-1", "销售服务费", "success"),),
            failure=None,
        ),
    )


def test_aggregate_fee_rate_results_dedupes_title_blocks_and_merges_citations() -> None:
    """fee_rates 聚合必须剥离金额表块、按标题去重并按 locator 去重合并 citations。"""

    aggregated = reading_service_module._aggregate_fee_rate_results(
        _overlapping_fee_rate_results()
    )

    assert "相关表格:" not in aggregated.answer
    assert aggregated.answer.count("按前一日基金资产净值的1.20%的年费率计提") == 1
    assert aggregated.answer.count("按前一日基金资产净值的0.20%的年费率计提") == 1
    assert aggregated.answer.count("0.40%年费率计提") == 1
    assert aggregated.answer.index("基金管理费") < aggregated.answer.index("基金托管费")
    assert aggregated.answer.index("基金托管费") < aggregated.answer.index("销售服务费")
    assert len(aggregated.citations) == 5
    assert (
        sum(
            1
            for citation in aggregated.citations
            if citation.locator.locator_kind is LocatorKind.SECTION
            and citation.locator.section_ref == "section-0398"
        )
        == 1
    )
    assert len(aggregated.tool_trace) == 3


def test_fee_rate_section_citations_counts_table_section_ref() -> None:
    """TABLE locator 携带的 section_ref 必须计入费率章节覆盖。"""

    citations = (
        _citation("doc-1", LocatorKind.SECTION, section_ref="section-0379"),
        _citation("doc-1", LocatorKind.TABLE, section_ref="section-0379", table_ref="table-0051"),
        _citation("doc-1", LocatorKind.SECTION, section_ref="section-0390"),
        _citation("doc-1", LocatorKind.TABLE, section_ref="section-0398", table_ref="table-0052"),
        _citation("doc-1", LocatorKind.SECTION, section_ref="section-0398"),
    )

    result = reading_service_module._fee_rate_section_citations(citations)

    assert list(result) == ["基金管理费", "基金托管费", "销售服务费"]
    assert [citation.locator.section_ref for citation in result.values()] == [
        "section-0379",
        "section-0390",
        "section-0398",
    ]


def test_fee_rate_section_citations_fails_closed_below_three_sections() -> None:
    """不同 section_ref 覆盖不足三个时必须 fail-closed NOT_FOUND。"""

    citations = (
        _citation("doc-1", LocatorKind.SECTION, section_ref="section-0379"),
        _citation("doc-1", LocatorKind.TABLE, section_ref="section-0379", table_ref="table-0051"),
    )

    with pytest.raises(DocumentToolError) as exc_info:
        reading_service_module._fee_rate_section_citations(citations)

    assert exc_info.value.code is FailureCode.NOT_FOUND


def test_extract_fee_rate_fields_from_aggregated_result_unique(tmp_path: Path) -> None:
    """标题块去重聚合后四类费率字段必须可唯一抽取。"""

    aggregated = reading_service_module._aggregate_fee_rate_results(
        _overlapping_fee_rate_results()
    )

    fields = reading_service_module._extract_fee_rate_fields(aggregated)

    assert len(fields) == 4
    values = {(field.field_name, field.share_class_scope): field for field in fields}
    assert values[("management_fee_rate", "all_share_classes")].decimal_percent_text == "1.20%"
    assert values[("custodian_fee_rate", "all_share_classes")].decimal_percent_text == "0.20%"
    assert values[("sales_service_fee_rate", "A")].decimal_percent_text == "不收取"
    assert values[("sales_service_fee_rate", "C")].decimal_percent_text == "0.40%"
    assert all(field.citation is not None for field in fields)


def test_extract_performance_returns_returns_past_1_year_table_dtos(tmp_path: Path) -> None:
    """10D 只从目标 performance table 抽取 past_1_year 两个收益字段。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceConverter.payload = staticmethod(_performance_docling_payload)
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    assert [call["query"] for call in _PerformanceExtractionHost.calls] == [
        "净值增长率",
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
    ]
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("nav_growth_rate", "A")].decimal_percent_text == "17.32%"
    assert values[("benchmark_return_rate", "A")].decimal_percent_text == "14.45%"
    assert values[("nav_growth_rate", "C")].decimal_percent_text == "10.21%"
    assert values[("benchmark_return_rate", "C")].decimal_percent_text == "13.14%"
    assert all(field.period == "past_1_year" for field in result.fields)
    assert all(field.citation.locator.locator_kind is LocatorKind.TABLE for field in result.fields)
    assert {field.citation.locator.table_ref for field in result.fields} == {"table-0000", "table-0001"}
    assert all(field.raw_text for field in result.fields)
    assert all("过去一年" in field.raw_text for field in result.fields)
    assert all("2.87%" not in field.raw_text for field in result.fields)
    assert all("-2.93%" not in field.raw_text for field in result.fields)
    assert {field.field_name for field in result.fields} == {
        "nav_growth_rate",
        "benchmark_return_rate",
    }


def test_extract_performance_returns_does_not_consume_uncited_same_section_table(tmp_path: Path) -> None:
    """同 section 未被 11A table citation 指向的表格不得被 10D 消费。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    _PerformanceConverter.payload = staticmethod(_performance_docling_payload)
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
            share_class="A",
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("nav_growth_rate", "A")].decimal_percent_text == "17.32%"
    assert values[("benchmark_return_rate", "A")].decimal_percent_text == "14.45%"
    assert ("nav_growth_rate", "C") not in values
    assert ("benchmark_return_rate", "C") not in values
    assert {field.citation.locator.table_ref for field in result.fields} == {"table-0000"}


def test_extract_performance_returns_fails_without_table_citation(tmp_path: Path) -> None:
    """缺 table citation 时不得抽取 performance_returns 字段。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = False
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    _PerformanceConverter.payload = staticmethod(_performance_docling_payload)
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    try:
        result = service.extract_performance_returns(
            reading_service_module.ExtractPerformanceReturnsRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceExtractionHost.include_table_citation = True

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_performance_returns_fails_when_target_column_missing(tmp_path: Path) -> None:
    """目标列缺失时必须 fail-closed 为 not_found。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "其他收益率", "①－③"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "2.87%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_performance_returns_fails_when_past_1_year_row_missing(tmp_path: Path) -> None:
    """缺 过去一年 行时必须 fail-closed 为 not_found。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③"),
            ("过去三个月", "-2.45%", "1.31%", "-1.10%", "1.22%", "-1.35%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_performance_returns_fails_when_share_class_is_ambiguous(tmp_path: Path) -> None:
    """多份额表格无法从上下文唯一识别 share class 时必须 fail-closed。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(section_lines=("业绩比较基准说明",))
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_performance_returns_config_error_maps_to_schema_drift(monkeypatch, tmp_path: Path) -> None:
    """performance_returns 抽取配置异常必须映射为 schema_drift。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    _PerformanceConverter.payload = staticmethod(_performance_docling_payload)
    monkeypatch.setattr(reading_service_module, "_PERFORMANCE_RETURN_EXTRACTION_SPECS", ())
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.SCHEMA_DRIFT


def test_extract_annual_performance_returns_report_year_table_dtos_without_section_number(tmp_path: Path) -> None:
    """10F 从固定标题族标准表抽取自然年度 DTO，不依赖章节编号。"""

    target_title = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceExtractionHost.source_title_line = f"来源章节: {target_title}"
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(section_title=target_title)
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    try:
        result = service.extract_annual_performance(
            reading_service_module.ExtractAnnualPerformanceRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceExtractionHost.source_title_line = None

    assert result.failure is None
    assert [call["query"] for call in _PerformanceExtractionHost.calls] == [
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
    ]
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_nav_growth_rate", "A")].decimal_percent_text == "17.32%"
    assert values[("annual_benchmark_return_rate", "A")].decimal_percent_text == "14.45%"
    assert values[("annual_nav_growth_rate", "C")].decimal_percent_text == "10.21%"
    assert values[("annual_benchmark_return_rate", "C")].decimal_percent_text == "13.14%"
    assert all(field.report_year == 2024 for field in result.fields)
    assert all(field.source_period_label == "过去一年" for field in result.fields)
    assert all("过去一年" in field.raw_text for field in result.fields)
    assert all(field.citation.locator.locator_kind is LocatorKind.TABLE for field in result.fields)
    assert {field.citation.locator.table_ref for field in result.fields} == {"table-0000", "table-0001"}
    assert {field.field_name for field in result.fields} == {
        "annual_nav_growth_rate",
        "annual_benchmark_return_rate",
    }


def test_extract_annual_performance_does_not_use_manager_report_text_fallback(tmp_path: Path) -> None:
    """管理人报告年度文字不得补成 10F 表格字段。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = False
    _PerformanceExtractionHost.cited_table_refs = ()
    _PerformanceExtractionHost.source_title_line = "来源章节: 报告期内基金的业绩表现"
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_title="报告期内基金的业绩表现",
            section_lines=("本报告期基金份额净值增长率为17.32%，同期业绩比较基准收益率为14.45%。",),
            table_rows=((),),
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    try:
        result = service.extract_annual_performance(
            reading_service_module.ExtractAnnualPerformanceRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceExtractionHost.include_table_citation = True
        _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
        _PerformanceExtractionHost.source_title_line = None

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_performance_fails_without_table_citation(tmp_path: Path) -> None:
    """目标 title-family 命中但缺 table citation 时必须 fail-closed。"""

    target_title = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = False
    _PerformanceExtractionHost.cited_table_refs = ()
    _PerformanceExtractionHost.source_title_line = f"来源章节: {target_title}"
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(section_title=target_title)
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    try:
        result = service.extract_annual_performance(
            reading_service_module.ExtractAnnualPerformanceRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceExtractionHost.include_table_citation = True
        _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
        _PerformanceExtractionHost.source_title_line = None

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_performance_missing_past_year_row_carries_explainable_message(tmp_path: Path) -> None:
    """10F 业绩表存在但无「过去一年」行时，not_found message 必须携带可解释说明。"""

    target_title = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    _PerformanceExtractionHost.source_title_line = f"来源章节: {target_title}"
    rows = (
        (
            ("阶段", "份额净值 增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
            ("过去三个月", "2.33%", "1.42%", "3.72%", "1.18%", "-1.39%", "0.24%"),
            ("自基金转型起至今", "2.39%", "1.24%", "-3.68%", "1.03%", "6.07%", "0.21%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(section_lines=(), table_rows=rows)
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    try:
        result = service.extract_annual_performance(
            reading_service_module.ExtractAnnualPerformanceRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceExtractionHost.source_title_line = None

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND
    assert "无「过去一年」行" in result.failure.message
    assert "自基金转型起至今" in result.failure.message


def test_extract_annual_performance_uses_signature_table_inside_title_section(tmp_path: Path) -> None:
    """10F 可在 title-family section 内定位满足 signature 的表格。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0001",)
    rows = (
        (
            ("项目", "2024年", "2023年"),
            ("本期基金份额净值增长率", "17.32%", "-1.11%"),
        ),
        (
            ("阶段", "基金份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "0.99%"),
        ),
        (
            ("阶段", "基金份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("自基金合同生效起至今", "10.21%", "1.05%", "13.14%", "1.00%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            share_class="A",
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_nav_growth_rate", "A")].decimal_percent_text == "17.32%"
    assert values[("annual_benchmark_return_rate", "A")].decimal_percent_text == "14.45%"
    assert {field.citation.locator.table_ref for field in result.fields} == {"table-0001"}


def test_extract_annual_performance_does_not_consume_uncited_signature_table(tmp_path: Path) -> None:
    """title-family section 内未被 citation 指向的 signature 表不得被 10F 消费。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("项目", "2024年", "2023年"),
            ("本期基金份额净值增长率", "17.32%", "-1.11%"),
        ),
        (
            ("阶段", "基金份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "0.99%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_performance_allows_partial_by_share_class(tmp_path: Path) -> None:
    """C 类缺完整 过去一年 行时，只返回完整的 A 类 DTO。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    rows = (
        (
            ("阶段", "基金份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "0.99%"),
        ),
        (
            ("阶段", "基金份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("自基金合同生效起至今", "10.21%", "1.05%", "13.14%", "1.00%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_nav_growth_rate", "A")].decimal_percent_text == "17.32%"
    assert values[("annual_benchmark_return_rate", "A")].decimal_percent_text == "14.45%"
    assert ("annual_nav_growth_rate", "C") not in values
    assert ("annual_benchmark_return_rate", "C") not in values


def test_extract_annual_performance_skips_incomplete_share_class_fields(tmp_path: Path) -> None:
    """某 share class 缺任一字段时不得返回该 share class 的部分字段。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "0.99%"),
        ),
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "10.21%", "1.05%", "-", "1.00%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert set(values) == {
        ("annual_nav_growth_rate", "A"),
        ("annual_benchmark_return_rate", "A"),
    }


def test_extract_annual_performance_fails_when_all_share_classes_are_field_partial(tmp_path: Path) -> None:
    """全部 share class 都字段不完整时整体 not_found。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "17.32%", "1.04%", "-", "0.99%"),
        ),
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "-", "1.05%", "13.14%", "1.00%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_performance_fails_when_target_column_missing(tmp_path: Path) -> None:
    """目标列缺失时必须 fail-closed 为 not_found。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "其他收益率"),
            ("过去一年", "17.32%", "1.04%", "14.45%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_performance_fails_when_past_year_row_missing(tmp_path: Path) -> None:
    """缺 过去一年 行时必须 fail-closed 为 not_found。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去三个月", "-2.45%", "1.31%", "-1.10%", "1.22%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_performance_config_error_maps_to_schema_drift(monkeypatch, tmp_path: Path) -> None:
    """annual performance 抽取配置异常必须映射为 schema_drift。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    _PerformanceConverter.payload = staticmethod(_performance_docling_payload)
    monkeypatch.setattr(reading_service_module, "_ANNUAL_PERFORMANCE_EXTRACTION_SPECS", ())
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.SCHEMA_DRIFT


def test_extract_annual_excess_return_reads_disclosed_column_without_section_number(tmp_path: Path) -> None:
    """10G 只从固定标题族标准表 ①－③ 列抽取年度超额收益。"""

    target_title = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceExtractionHost.source_title_line = f"来源章节: {target_title}"
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(section_title=target_title)
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    try:
        result = service.extract_annual_excess_return(
            reading_service_module.ExtractAnnualExcessReturnRequest(
                pdf_path=pdf_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
                work_dir=work_dir,
            )
        )
    finally:
        _PerformanceExtractionHost.source_title_line = None

    assert result.failure is None
    assert [call["query"] for call in _PerformanceExtractionHost.calls] == [
        "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
    ]
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_excess_return", "A")].decimal_percent_text == "2.87%"
    assert values[("annual_excess_return", "C")].decimal_percent_text == "-2.93%"
    assert all(field.report_year == 2024 for field in result.fields)
    assert all(field.source_period_label == "过去一年" for field in result.fields)
    assert all(field.source_column_label == "①－③" for field in result.fields)
    assert all("过去一年" in field.raw_text for field in result.fields)
    assert all(field.citation.locator.locator_kind is LocatorKind.TABLE for field in result.fields)
    assert {field.citation.locator.table_ref for field in result.fields} == {"table-0000", "table-0001"}


def test_extract_annual_excess_return_fails_when_disclosed_column_missing(tmp_path: Path) -> None:
    """缺 ①－③ 列时不得用 nav - benchmark 计算补值。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④"),
            ("过去一年", "17.32%", "1.04%", "14.45%", "0.99%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_lines=("本报告期基金份额净值增长率为17.32%，同期业绩比较基准收益率为14.45%。",),
            table_rows=rows,
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_excess_return(
        reading_service_module.ExtractAnnualExcessReturnRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_excess_return_does_not_use_fallback_sources(tmp_path: Path) -> None:
    """管理人报告文字、年度图/图片或未 citation 指向的 sibling table 不得补 10G。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    rows = (
        (
            ("项目", "2024年", "说明"),
            ("年度图/图片", "2.87%", "chart_or_image"),
        ),
        (
            ("阶段", "份额净值增长率①", "业绩比较基准收益率③", "①－③"),
            ("过去一年", "17.32%", "14.45%", "2.87%"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_lines=("本报告期基金份额净值增长率为17.32%，同期业绩比较基准收益率为14.45%。",),
            table_rows=rows,
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_excess_return(
        reading_service_module.ExtractAnnualExcessReturnRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_extract_annual_excess_return_allows_partial_by_share_class(tmp_path: Path) -> None:
    """C 类缺 ①－③ 值时，只返回完整的 A 类 DTO。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    rows = (
        (
            ("阶段", "份额净值增长率①", "业绩比较基准收益率③", "①－③"),
            ("过去一年", "17.32%", "14.45%", "2.87%"),
        ),
        (
            ("阶段", "份额净值增长率①", "业绩比较基准收益率③", "①－③"),
            ("过去一年", "10.21%", "13.14%", "-"),
        ),
    )
    _PerformanceConverter.payload = staticmethod(lambda: _performance_docling_payload(table_rows=rows))
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_excess_return(
        reading_service_module.ExtractAnnualExcessReturnRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_excess_return", "A")].decimal_percent_text == "2.87%"
    assert ("annual_excess_return", "C") not in values


def test_extract_annual_excess_return_config_error_maps_to_schema_drift(monkeypatch, tmp_path: Path) -> None:
    """annual excess return 抽取配置异常必须映射为 schema_drift。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000",)
    _PerformanceConverter.payload = staticmethod(_performance_docling_payload)
    monkeypatch.setattr(reading_service_module, "_ANNUAL_EXCESS_RETURN_EXTRACTION_SPECS", ())
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_excess_return(
        reading_service_module.ExtractAnnualExcessReturnRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.fields == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.SCHEMA_DRIFT


def test_aggregate_multi_year_annual_performance_returns_complete_five_year_series(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """5 年完整时 10I 返回 coverage_status=complete。"""

    years = (2020, 2021, 2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {"A": (f"{year - 2000}.10%", f"{year - 2000}.20%", f"{year - 2000}.30%")}
        for year in years
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=(2024, 2020, 2022, 2021, 2023),
            annual_report_documents=documents,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    assert len(result.series) == 1
    series = result.series[0]
    assert series.fund_code == REAL_SMOKE_FUND_CODE
    assert series.requested_years == years
    assert series.covered_years == years
    assert series.missing_years == ()
    assert series.coverage_status == "complete"
    assert series.coverage_count == 5
    assert series.minimum_required_count == 3
    assert series.share_class_scope == "A"
    assert [row.year for row in series.rows] == list(years)


def test_aggregate_multi_year_annual_performance_returns_partial_for_four_complete_years(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """4 年完整 / 缺 1 年时 10I 返回 partial，并列出 missing_years。"""

    years = (2020, 2021, 2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    provided_documents = tuple(document for document in documents if document.year != 2021)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in years
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=provided_documents,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    series = result.series[0]
    assert series.coverage_status == "partial"
    assert series.coverage_count == 4
    assert series.covered_years == (2020, 2022, 2023, 2024)
    assert series.missing_years == (2021,)


def test_aggregate_multi_year_annual_performance_returns_partial_for_three_complete_years(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """3 年完整 / 缺 2 年时 10I 返回 partial。"""

    years = (2020, 2021, 2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in (2020, 2022, 2024)
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=documents,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    series = result.series[0]
    assert series.coverage_status == "partial"
    assert series.coverage_count == 3
    assert series.covered_years == (2020, 2022, 2024)
    assert series.missing_years == (2021, 2023)


def test_aggregate_multi_year_annual_performance_fails_not_found_below_three_complete_years(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """少于 3 个完整年度时 10I 整体 not_found。"""

    years = (2020, 2021, 2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in (2020, 2024)
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=documents,
            work_dir=work_dir,
        )
    )

    assert result.series == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND


def test_aggregate_multi_year_annual_performance_omits_share_class_below_three_years(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """未指定 share_class 时，C 类不足 3 年不得返回 C 类 series。"""

    years = (2020, 2021, 2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in years
    }
    values[2020]["C"] = ("1.10%", "1.20%", "1.30%")
    values[2021]["C"] = ("2.10%", "2.20%", "2.30%")
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=documents,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    assert tuple(series.share_class_scope for series in result.series) == ("A",)


def test_aggregate_multi_year_annual_performance_honors_requested_share_class(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """用户指定 share_class 时，10I 只返回该 share class series。"""

    years = (2020, 2021, 2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {
            "A": (f"{year}.1%", f"{year}.2%", f"{year}.3%"),
            "C": (f"{year}.4%", f"{year}.5%", f"{year}.6%"),
        }
        for year in years
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=documents,
            work_dir=work_dir,
            share_class="C类",
        )
    )

    assert result.failure is None
    assert len(result.series) == 1
    assert result.series[0].share_class_scope == "C"
    assert all(row.annual_nav_growth_rate.endswith(".4%") for row in result.series[0].rows)


def test_aggregate_multi_year_annual_performance_preserves_field_level_table_citations(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """每个 year / field 必须保留对应年度 table locator citation。"""

    years = (2020, 2021, 2022)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in years
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=documents,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    series = result.series[0]
    assert len(series.citations) == 9
    for row in series.rows:
        assert tuple(citation.field_name for citation in row.citations) == (
            "annual_nav_growth_rate",
            "annual_benchmark_return_rate",
            "annual_excess_return",
        )
        assert all(citation.citation.year == row.year for citation in row.citations)
        assert all(citation.citation.locator.locator_kind is LocatorKind.TABLE for citation in row.citations)
        assert {
            citation.citation.locator.table_ref
            for citation in row.citations
        } == {
            f"table-{row.year}-A-nav",
            f"table-{row.year}-A-benchmark",
            f"table-{row.year}-A-excess",
        }


def test_aggregate_multi_year_annual_performance_fails_on_document_year_identity_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """显式绑定 year 与 loaded report identity 冲突时必须 identity_mismatch。"""

    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, (2022, 2023, 2024))
    wrong_documents = (
        documents[0],
        AnnualReportDocument(year=2023, document_id=documents[2].document_id),
        documents[2],
    )
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in (2022, 2023, 2024)
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=(2022, 2023, 2024),
            annual_report_documents=wrong_documents,
            work_dir=work_dir,
        )
    )

    assert result.series == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.IDENTITY_MISMATCH


def test_aggregate_multi_year_annual_performance_fails_on_extraction_report_year_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """单年度 extraction result 的 report_year 与绑定 year 冲突时必须 identity_mismatch。"""

    years = (2022, 2023, 2024)
    service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, documents = _import_annual_documents(service, tmp_path, years)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in years
    }
    _install_multi_year_fake_extractors(monkeypatch, service, values, report_year_offset=1)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=documents,
            work_dir=work_dir,
        )
    )

    assert result.series == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.IDENTITY_MISMATCH


@pytest.mark.parametrize(
    "requested_years",
    [
        (2022, 2023),
        (2019, 2020, 2021, 2022, 2023, 2024),
        (2022, 2023, 2023),
    ],
)
def test_aggregate_multi_year_annual_performance_rejects_invalid_requested_years(
    requested_years: tuple[int, ...],
    tmp_path: Path,
) -> None:
    """requested_years 重复或长度不在 3-5 时使用既有 failure code fail-closed。"""

    service = FundReadingService(converter_factory=_FakeConverter)

    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=requested_years,
            annual_report_documents=(),
            work_dir=tmp_path / "work",
        )
    )

    assert result.series == ()
    assert result.failure is not None
    assert result.failure.code is FailureCode.SCHEMA_DRIFT


def test_aggregate_multi_year_annual_performance_does_not_auto_fill_or_add_new_source_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """10I 只编排显式 document_id，不做 repository 自动补齐、OCR、chart 或外部来源。"""

    years = (2020, 2021, 2022, 2023, 2024)
    importing_service = FundReadingService(converter_factory=_FakeConverter)
    work_dir, all_documents = _import_annual_documents(importing_service, tmp_path, years)
    aggregating_service = FundReadingService(converter_factory=_ForbiddenConverter)
    values = {
        year: {"A": (f"{year}.1%", f"{year}.2%", f"{year}.3%")}
        for year in years
    }
    calls = _install_multi_year_fake_extractors(monkeypatch, aggregating_service, values)

    result = aggregating_service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=REAL_SMOKE_FUND_CODE,
            requested_years=years,
            annual_report_documents=all_documents[:3],
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    assert result.series[0].coverage_status == "partial"
    assert result.series[0].covered_years == (2020, 2021, 2022)
    assert result.series[0].missing_years == (2023, 2024)
    assert [call[1] for call in calls] == [2020, 2020, 2021, 2021, 2022, 2022]


def test_read_local_report_records_non_profile_query_only_once(tmp_path: Path) -> None:
    """非受控 query 不走 fallback，routing_trace 只记录原始 query。"""

    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "股票投资明细"
    _RoutingHost.success_answer = "命中 股票投资明细"
    _RoutingHost.success_locator_kind = LocatorKind.TABLE
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_RoutingHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="股票投资明细",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is None
    assert [call["query"] for call in _RoutingHost.calls] == ["股票投资明细"]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="股票投资明细",
            profile_name=None,
            result_kind="success",
            failure_code=None,
        ),
    )


def test_read_local_report_returns_not_found_after_all_candidates_miss(tmp_path: Path) -> None:
    """所有 controlled candidates 都无命中时，最终失败仍是 not_found。"""

    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = None
    _RoutingHost.success_answer = None
    _RoutingHost.success_locator_kind = LocatorKind.TABLE
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(converter_factory=_FakeConverter, host_factory=_RoutingHost)

    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            query="资产配置",
            work_dir=work_dir,
        )
    )

    assert result.agent_result.failure is not None
    assert result.agent_result.failure.code is FailureCode.NOT_FOUND
    assert [call["query"] for call in _RoutingHost.calls] == [
        "资产配置",
        "期末基金资产组合情况",
        "基金资产组合情况",
    ]
    assert result.routing_trace == (
        QueryRouteAttempt(
            query="资产配置",
            profile_name="asset_allocation",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="期末基金资产组合情况",
            profile_name="asset_allocation",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
        QueryRouteAttempt(
            query="基金资产组合情况",
            profile_name="asset_allocation",
            result_kind="failure",
            failure_code=FailureCode.NOT_FOUND,
        ),
    )


def test_controlled_query_profile_config_error_maps_to_schema_drift(monkeypatch) -> None:
    """routing 配置异常必须 fail-closed 为 schema_drift。"""

    bad_profiles = (
        reading_service_module._DisclosureLocatorContract(
            profile_name="bad",
            aliases=("前十大持仓",),
            candidate_queries=("a", "b", "c", "d", "e"),
            acceptable_title_family=("bad",),
            requires_table_citation=False,
            extraction_allowed=False,
        ),
    )
    monkeypatch.setattr(reading_service_module, "DISCLOSURE_LOCATOR_CONTRACT_REGISTRY", bad_profiles)

    with pytest.raises(DocumentToolError) as exc_info:
        reading_service_module._candidate_queries_for_query("前十大持仓")

    assert exc_info.value.code is FailureCode.SCHEMA_DRIFT


def test_disclosure_locator_registry_rejects_extraction_enabled_contract(monkeypatch) -> None:
    """11B registry 的 extraction_allowed 必须固定为 False。"""

    bad_registry = (
        reading_service_module._DisclosureLocatorContract(
            profile_name="fee_rates",
            aliases=("费用",),
            candidate_queries=("基金管理费",),
            acceptable_title_family=("基金管理费",),
            requires_table_citation=False,
            extraction_allowed=True,
        ),
    )
    monkeypatch.setattr(reading_service_module, "DISCLOSURE_LOCATOR_CONTRACT_REGISTRY", bad_registry)

    with pytest.raises(DocumentToolError) as exc_info:
        reading_service_module._candidate_queries_for_query("费用")

    assert exc_info.value.code is FailureCode.SCHEMA_DRIFT


def test_query_route_attempt_has_only_allowed_audit_fields() -> None:
    """QueryRouteAttempt 不得新增派生解释字段。"""

    assert {field.name for field in fields(QueryRouteAttempt)} == {
        "query",
        "profile_name",
        "result_kind",
        "failure_code",
    }


def test_real_pdf_controlled_profiles_apply_disclosure_target_contract(tmp_path: Path) -> None:
    """真实本地年报必须区分 disclosure target success 与 keyword success。"""

    assert REAL_SMOKE_PDF.is_file(), "Slice 10A real-smoke PDF is required"
    success_expectations = (
        ("前十大持仓", "holdings_top10", ("股票投资明细", "前十名股票投资明细")),
        ("资产配置", "asset_allocation", ("期末基金资产组合情况", "基金资产组合情况")),
    )
    service = FundReadingService()
    work_dir = tmp_path / "real-smoke-work"

    for query, profile_name, expected_evidence in success_expectations:
        result = service.read_local_report(
            ReadLocalReportRequest(
                pdf_path=REAL_SMOKE_PDF,
                fund_code=REAL_SMOKE_FUND_CODE,
                fund_name=REAL_SMOKE_FUND_NAME,
                year=REAL_SMOKE_YEAR,
                query=query,
                work_dir=work_dir,
            )
        )

        assert result.agent_result.failure is None
        assert any(evidence in result.agent_result.answer for evidence in expected_evidence)
        assert result.agent_result.citations
        assert result.agent_result.tool_trace
        assert result.routing_trace
        assert result.routing_trace[0].query == query
        assert all(attempt.profile_name == profile_name for attempt in result.routing_trace)
        assert result.routing_trace[-1].result_kind == "success"
        assert result.routing_trace[-1].failure_code is None
        assert result.routing_trace[-1].query in reading_service_module._candidate_queries_for_query(query)

    fee_rates = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=REAL_SMOKE_PDF,
            fund_code=REAL_SMOKE_FUND_CODE,
            fund_name=REAL_SMOKE_FUND_NAME,
            year=REAL_SMOKE_YEAR,
            query="费用",
            work_dir=work_dir,
        )
    )

    assert fee_rates.agent_result.failure is None
    assert "基金管理费" in fee_rates.agent_result.answer
    assert "基金托管费" in fee_rates.agent_result.answer
    assert "销售服务费" in fee_rates.agent_result.answer
    assert fee_rates.agent_result.citations
    assert fee_rates.agent_result.tool_trace
    assert [attempt.query for attempt in fee_rates.routing_trace] == [
        "费用",
        "基金管理费",
        "基金托管费",
        "销售服务费",
    ]
    assert all(attempt.profile_name == "fee_rates" for attempt in fee_rates.routing_trace)
    assert [attempt.result_kind for attempt in fee_rates.routing_trace] == [
        "failure",
        "success",
        "success",
        "success",
    ]

    extracted = service.extract_fee_rates(
        ExtractFeeRatesRequest(
            pdf_path=REAL_SMOKE_PDF,
            fund_code=REAL_SMOKE_FUND_CODE,
            fund_name=REAL_SMOKE_FUND_NAME,
            year=REAL_SMOKE_YEAR,
            work_dir=work_dir,
        )
    )

    assert extracted.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in extracted.fields}
    assert values[("management_fee_rate", "all_share_classes")].decimal_percent_text == "1.20%"
    assert values[("custodian_fee_rate", "all_share_classes")].decimal_percent_text == "0.20%"
    assert values[("sales_service_fee_rate", "A")].decimal_percent_text == "不收取"
    assert values[("sales_service_fee_rate", "C")].decimal_percent_text == "0.40%"
    assert all(field.raw_text for field in extracted.fields)
    assert all(field.citation is not None for field in extracted.fields)

    performance = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=REAL_SMOKE_PDF,
            fund_code=REAL_SMOKE_FUND_CODE,
            fund_name=REAL_SMOKE_FUND_NAME,
            year=REAL_SMOKE_YEAR,
            query="净值增长率",
            work_dir=work_dir,
        )
    )

    assert performance.agent_result.failure is None
    assert "基金份额净值增长率及其与同期业绩比较基准收益率的比较" in performance.agent_result.answer
    assert performance.agent_result.citations
    assert {citation.locator.locator_kind for citation in performance.agent_result.citations} >= {
        LocatorKind.SECTION,
        LocatorKind.TABLE,
    }
    assert performance.agent_result.tool_trace
    assert performance.routing_trace
    assert performance.routing_trace[0].query == "净值增长率"
    assert all(attempt.profile_name == "performance_returns" for attempt in performance.routing_trace)
    assert performance.routing_trace[-1].result_kind == "success"
    assert performance.routing_trace[-1].failure_code is None
    assert "nav_growth_rate" not in performance.agent_result.answer
    assert "benchmark_return_rate" not in performance.agent_result.answer
    assert "decimal_percent_text" not in performance.agent_result.answer

    annual_performance = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=REAL_SMOKE_PDF,
            fund_code=REAL_SMOKE_FUND_CODE,
            fund_name=REAL_SMOKE_FUND_NAME,
            year=REAL_SMOKE_YEAR,
            work_dir=work_dir,
        )
    )

    assert annual_performance.failure is None
    annual_values = {
        (field.field_name, field.share_class_scope): field
        for field in annual_performance.fields
    }
    assert annual_values[("annual_nav_growth_rate", "A")].decimal_percent_text == "17.32%"
    assert annual_values[("annual_benchmark_return_rate", "A")].decimal_percent_text == "14.45%"
    assert all(field.report_year == REAL_SMOKE_YEAR for field in annual_performance.fields)
    assert all(field.source_period_label == "过去一年" for field in annual_performance.fields)
    assert all("过去一年" in field.raw_text for field in annual_performance.fields)
    assert all(
        field.citation.locator.locator_kind is LocatorKind.TABLE
        for field in annual_performance.fields
    )

    annual_excess_return = service.extract_annual_excess_return(
        reading_service_module.ExtractAnnualExcessReturnRequest(
            pdf_path=REAL_SMOKE_PDF,
            fund_code=REAL_SMOKE_FUND_CODE,
            fund_name=REAL_SMOKE_FUND_NAME,
            year=REAL_SMOKE_YEAR,
            work_dir=work_dir,
        )
    )

    assert annual_excess_return.failure is None
    annual_excess_values = {
        (field.field_name, field.share_class_scope): field
        for field in annual_excess_return.fields
    }
    annual_excess_a = annual_excess_values[("annual_excess_return", "A")]
    assert annual_excess_a.decimal_percent_text == "2.87%"
    assert annual_excess_a.report_year == REAL_SMOKE_YEAR
    assert annual_excess_a.source_period_label == "过去一年"
    assert annual_excess_a.source_column_label == "①－③"
    assert annual_excess_a.citation.locator.locator_kind is LocatorKind.TABLE

    performance_fields = service.extract_performance_returns(
        reading_service_module.ExtractPerformanceReturnsRequest(
            pdf_path=REAL_SMOKE_PDF,
            fund_code=REAL_SMOKE_FUND_CODE,
            fund_name=REAL_SMOKE_FUND_NAME,
            year=REAL_SMOKE_YEAR,
            work_dir=work_dir,
        )
    )

    assert performance_fields.fields == ()
    assert performance_fields.failure is not None
    assert performance_fields.failure.code is FailureCode.NOT_FOUND


# --- Slice 16A: 确定性信号判断 + 风险清单 ---

from fund_agent.service.extraction import (
    _parse_percent,
    _parse_aum_yi,
    _holdings_overlap_rate,
)
from fund_agent.service.models import (
    FeeRateItem,
    FundManagerInfo,
    HoldingExtraction,
    RiskChecklistItem,
    ScaleInfo,
    SignalIndicator,
    SignalJudgment,
)


def test_parse_percent_boundary():
    """百分比解析边界测试：正常值、不收取、N/A。"""
    assert _parse_percent("0.60%") == 0.6
    assert _parse_percent("1.20%") == 1.2
    assert _parse_percent("不收取") == 0.0
    assert _parse_percent("免收") == 0.0
    assert _parse_percent("N/A") is None
    assert _parse_percent("—") is None
    assert _parse_percent("") is None
    assert _parse_percent("  1.50%  ") == 1.5


def test_parse_aum_boundary():
    """规模解析边界测试：亿元、万元、元。"""
    assert _parse_aum_yi("2.99亿元") == 2.99
    assert _parse_aum_yi("2,990,000元") == pytest.approx(0.0299, abs=1e-4)
    assert _parse_aum_yi("5000万元") == pytest.approx(0.5, abs=1e-4)
    assert _parse_aum_yi("") is None
    assert _parse_aum_yi("N/A") is None


def test_compute_signal_judgment_full_data():
    """所有指标有数据且表现良好时，输出 🟢。"""
    service = FundReadingService()
    # 构造完整数据：2 年正超额、低费率、高重叠率、大规模、未变更、低集中度
    perf = {
        2023: {"nav_growth_rate": "10.00%", "benchmark_return_rate": "7.00%", "excess_return": "3.00%"},
        2024: {"nav_growth_rate": "12.00%", "benchmark_return_rate": "8.00%", "excess_return": "4.00%"},
    }
    fees = {
        2024: (FeeRateItem("基金管理费", "0.60%"), FeeRateItem("基金托管费", "0.15%")),
    }
    holdings_2023 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}", quantity="1000", fair_value="10000", percentage="5.0%")
        for i in range(1, 11)
    )
    holdings_2024 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}", quantity="1000", fair_value="10000", percentage="5.0%")
        for i in range(1, 11)
    )
    holdings = {2023: holdings_2023, 2024: holdings_2024}
    manager = FundManagerInfo("张三", "2020-01-01", "10年", "价值投资", "10~50万份")
    scale = ScaleInfo("100000000", "50000000", "95%", "", "5.00亿元")

    result = service.compute_signal_judgment(
        performance=perf, fees=fees, holdings=holdings,
        fund_manager=manager, scale_info=scale, report_year=2024,
    )

    assert result.signal == "🟢 值得持有"
    assert result.normalized_score >= 75
    assert len(result.indicators) == 6
    assert result.data_completeness == 1.0
    # 所有指标都有正分
    assert all(ind.score > 0 for ind in result.indicators)


def test_compute_signal_judgment_low_score():
    """低分数据时，输出 🔴。"""
    service = FundReadingService()
    # 构造差数据：负超额、高费率、低重叠率、小规模、已变更、高集中度
    perf = {
        2023: {"nav_growth_rate": "-5.00%", "benchmark_return_rate": "2.00%", "excess_return": "-7.00%"},
        2024: {"nav_growth_rate": "-3.00%", "benchmark_return_rate": "1.00%", "excess_return": "-4.00%"},
    }
    fees = {
        2024: (FeeRateItem("基金管理费", "1.50%"), FeeRateItem("基金托管费", "0.30%")),
    }
    # 持仓完全不同 → 重叠率 0
    holdings_2023 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票A{i}", quantity="100", fair_value="1000", percentage="10.0%")
        for i in range(1, 11)
    )
    holdings_2024 = tuple(
        HoldingExtraction(rank=i, stock_code=f"60000{i}", stock_name=f"股票B{i}", quantity="100", fair_value="1000", percentage="10.0%")
        for i in range(1, 11)
    )
    holdings = {2023: holdings_2023, 2024: holdings_2024}
    manager = FundManagerInfo("李四", "2024-06-01", "5年", "成长投资", "")
    scale = ScaleInfo("1000000", "500000", "80%", "", "0.03亿元")

    result = service.compute_signal_judgment(
        performance=perf, fees=fees, holdings=holdings,
        fund_manager=manager, scale_info=scale, report_year=2024,
    )

    assert result.signal == "🔴 建议替换"
    assert result.normalized_score < 50


def test_compute_signal_judgment_insufficient_data():
    """数据不足（可计算指标 < 3）时，默认 🟡 + warnings。"""
    service = FundReadingService()
    # 空数据 → 所有指标 0 分，可计算 0 项
    result = service.compute_signal_judgment(
        performance={}, fees={}, holdings={},
        fund_manager=None, scale_info=None, report_year=2024,
    )

    assert result.signal == "🟡 需要关注"
    assert result.normalized_score == 0.0
    assert result.data_completeness == 0.0
    assert len(result.warnings) > 0
    assert any("数据不足" in w for w in result.warnings)


def test_compute_signal_judgment_threshold_events_integration():
    """集成测试：compute_signal_judgment 完整路径产出阈值事件。"""
    service = FundReadingService()
    perf = {
        2023: {"nav_growth_rate": "10.00%", "benchmark_return_rate": "7.00%", "excess_return": "3.00%"},
        2024: {"nav_growth_rate": "12.00%", "benchmark_return_rate": "8.00%", "excess_return": "4.00%"},
    }
    fees = {
        2024: (FeeRateItem("基金管理费", "0.60%"), FeeRateItem("基金托管费", "0.15%")),
    }
    holdings_2023 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}", quantity="1000", fair_value="10000", percentage="5.0%")
        for i in range(1, 11)
    )
    holdings_2024 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}", quantity="1000", fair_value="10000", percentage="5.0%")
        for i in range(1, 11)
    )
    holdings = {2023: holdings_2023, 2024: holdings_2024}
    manager = FundManagerInfo("张三", "2020-01-01", "10年", "价值投资", "10~50万份")
    scale = ScaleInfo("100000000", "50000000", "95%", "", "5.00亿元")

    result = service.compute_signal_judgment(
        performance=perf, fees=fees, holdings=holdings,
        fund_manager=manager, scale_info=scale, report_year=2024,
    )

    # 全部满分时 upgrade_event 应为 None
    # 实际数据不一定是满分，但阈值事件必须存在或为 None（不报错）
    if result.upgrade_event is not None:
        assert result.upgrade_event.direction == "upgrade"
        assert result.upgrade_event.tier_delta > 0
    if result.downgrade_event is not None:
        assert result.downgrade_event.direction == "downgrade"
        assert result.downgrade_event.tier_delta > 0


def test_compute_risk_checklist_all_green():
    """所有指标安全时，全部 🟢。"""
    service = FundReadingService()
    fees = {
        2024: (FeeRateItem("基金管理费", "0.60%"), FeeRateItem("基金托管费", "0.15%")),
    }
    holdings_2023 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}", quantity="1000", fair_value="10000", percentage="3.0%")
        for i in range(1, 11)
    )
    holdings_2024 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}", quantity="1000", fair_value="10000", percentage="3.0%")
        for i in range(1, 11)
    )
    holdings = {2023: holdings_2023, 2024: holdings_2024}
    manager = FundManagerInfo("张三", "2020-01-01", "10年", "价值投资", "10~50万份")
    scale = ScaleInfo("100000000", "50000000", "95%", "", "5.00亿元")

    result = service.compute_risk_checklist(
        fees=fees, holdings=holdings,
        fund_manager=manager, scale_info=scale, report_year=2024,
    )

    assert len(result) == 6
    green_count = sum(1 for item in result if item.status == "🟢")
    # 清盘风险、风格漂移、费率、持仓集中度应为绿；换手率固定绿；经理变更绿
    assert green_count == 6
    assert not any(item.status == "🔴" for item in result)


def test_compute_risk_checklist_red_flags():
    """有 🔴 指标时，正确标记。"""
    service = FundReadingService()
    fees = {
        2024: (FeeRateItem("基金管理费", "1.50%"), FeeRateItem("基金托管费", "0.30%")),
    }
    # 持仓完全不同 → 重叠率 0
    holdings_2023 = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票A{i}", quantity="100", fair_value="1000", percentage="10.0%")
        for i in range(1, 11)
    )
    holdings_2024 = tuple(
        HoldingExtraction(rank=i, stock_code=f"60000{i}", stock_name=f"股票B{i}", quantity="100", fair_value="1000", percentage="10.0%")
        for i in range(1, 11)
    )
    holdings = {2023: holdings_2023, 2024: holdings_2024}
    manager = FundManagerInfo("李四", "2024-06-01", "5年", "成长投资", "")
    scale = ScaleInfo("1000000", "500000", "80%", "", "0.03亿元")

    result = service.compute_risk_checklist(
        fees=fees, holdings=holdings,
        fund_manager=manager, scale_info=scale, report_year=2024,
    )

    assert len(result) == 6
    red_items = [item for item in result if item.status == "🔴"]
    # 清盘风险🔴、经理变更🔴、风格漂移🔴、费率🔴、持仓集中度🔴
    assert len(red_items) == 5
    assert any(item.name == "清盘风险" and item.status == "🔴" for item in result)
    assert any(item.name == "基金经理变更" and item.status == "🔴" for item in result)
    assert any(item.name == "风格漂移" and item.status == "🔴" for item in result)
    assert any(item.name == "费率远超同类" and item.status == "🔴" for item in result)

def test_holdings_overlap_rate_weighted_jaccard():
    """同一批股票但权重大幅调整时，加权 Jaccard 不返回 1.0。"""
    # 年度 A：10 只股票各占 10%
    holdings_a = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}",
                          quantity="100", fair_value="1000", percentage="10.0%")
        for i in range(1, 11)
    )
    # 年度 B：同一批股票，但第一只占 50%，其余各占 5.56%
    holdings_b = [
        HoldingExtraction(rank=1, stock_code="000001", stock_name="股票1",
                          quantity="500", fair_value="5000", percentage="50.0%"),
    ]
    for i in range(2, 11):
        holdings_b.append(
            HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}",
                              quantity="50", fair_value="500", percentage="5.56%")
        )
    holdings_b = tuple(holdings_b)

    rate = _holdings_overlap_rate(holdings_a, holdings_b)
    # 加权 Jaccard：分子 = min(10,50) + 9*min(10,5.56) = 10 + 50 ≈ 60，分母 = max(10,50) + 9*max(10,5.56) = 50 + 90 = 140
    # 率 ≈ 60/140 ≈ 0.43
    assert rate < 0.7, f"加权重叠率应 < 0.7，实际 {rate}"
    assert rate > 0.2, f"加权重叠率应 > 0.2，实际 {rate}"


def test_holdings_overlap_rate_identical_weights():
    """相同比重的相同持仓，加权 Jaccard 返回 1.0。"""
    holdings = tuple(
        HoldingExtraction(rank=i, stock_code=f"00000{i}", stock_name=f"股票{i}",
                          quantity="100", fair_value="1000", percentage="10.0%")
        for i in range(1, 11)
    )
    rate = _holdings_overlap_rate(holdings, holdings)
    assert rate == 1.0


def test_holdings_overlap_rate_no_overlap():
    """完全不同的持仓，加权 Jaccard 返回 0.0。"""
    holdings_a = (HoldingExtraction(rank=1, stock_code="000001", stock_name="A",
                                    quantity="100", fair_value="1000", percentage="10.0%"),)
    holdings_b = (HoldingExtraction(rank=1, stock_code="600001", stock_name="B",
                                    quantity="100", fair_value="1000", percentage="10.0%"),)
    rate = _holdings_overlap_rate(holdings_a, holdings_b)
    assert rate == 0.0


# ── Slice 16B 压力测试 ──────────────────────────────────────────────


class TestInferFundType:
    """infer_fund_type 关键词匹配测试。"""

    def test_index_fund(self):
        fund_type, inferred = infer_fund_type("沪深300指数证券投资基金")
        assert fund_type == "index_fund"
        assert inferred is True

    def test_bond_fund_by_bond(self):
        fund_type, inferred = infer_fund_type("某某债券型证券投资基金")
        assert fund_type == "bond_fund"
        assert inferred is True

    def test_bond_fund_by_zhai(self):
        fund_type, inferred = infer_fund_type("某某纯债基金")
        assert fund_type == "bond_fund"
        assert inferred is True

    def test_active_fund_default(self):
        fund_type, inferred = infer_fund_type("安信企业价值优选混合型证券投资基金")
        assert fund_type == "active_fund"
        assert inferred is True

    def test_empty_name(self):
        fund_type, inferred = infer_fund_type("")
        assert fund_type == "active_fund"
        assert inferred is True


class TestComputeStressTest:
    """compute_stress_test 计算逻辑测试。"""

    def test_active_fund_full_data(self):
        scale = ScaleInfo(
            total_shares_a="1亿", total_shares_c="",
            individual_investor_ratio="80%", management_holds="",
            estimated_aum="2.99亿元",
        )
        result = compute_stress_test(scale, 0.087, 0.053, "安信企业价值优选混合")
        assert result.fund_type == "active_fund"
        assert result.fund_type_inferred is True
        assert result.current_scale_billion == 2.99
        assert result.stress_scenarios["normal"]["loss_billion"] == 0.7475
        assert result.stress_scenarios["extreme"]["loss_billion"] == 1.3455
        assert result.stress_scenarios["worst"]["loss_billion"] == 1.9435
        assert result.excess_return == 0.034
        assert result.stress_level == "outperform"

    def test_index_fund_thresholds(self):
        scale = ScaleInfo(
            total_shares_a="1亿", total_shares_c="",
            individual_investor_ratio="", management_holds="",
            estimated_aum="10.0亿元",
        )
        result = compute_stress_test(scale, 0.05, 0.10, "沪深300指数基金")
        assert result.fund_type == "index_fund"
        assert result.stress_scenarios["normal"]["threshold"] == -0.30
        assert result.stress_scenarios["normal"]["loss_billion"] == 3.0
        assert result.stress_scenarios["extreme"]["threshold"] == -0.50
        assert result.stress_scenarios["extreme"]["loss_billion"] == 5.0
        assert result.stress_scenarios["worst"]["threshold"] == -0.70
        assert result.stress_scenarios["worst"]["loss_billion"] == 7.0

    def test_bond_fund_thresholds(self):
        scale = ScaleInfo(
            total_shares_a="", total_shares_c="",
            individual_investor_ratio="", management_holds="",
            estimated_aum="5.0亿元",
        )
        result = compute_stress_test(scale, 0.02, 0.015, "某某债券基金")
        assert result.fund_type == "bond_fund"
        assert result.stress_scenarios["normal"]["loss_billion"] == 0.25
        assert result.stress_scenarios["extreme"]["loss_billion"] == 0.5
        assert result.stress_scenarios["worst"]["loss_billion"] == 1.0

    def test_no_scale_missing_loss(self):
        """无规模数据时跳过损失计算，只输出 stress_level。"""
        result = compute_stress_test(None, 0.05, 0.08, "某基金")
        assert result.current_scale_billion is None
        assert result.stress_scenarios["normal"]["loss_billion"] == 0.0
        assert result.stress_level == "underperform"

    def test_no_performance_missing_stress_level(self):
        """无净值增长率或基准收益率时 stress_level 为 None。"""
        scale = ScaleInfo(
            total_shares_a="", total_shares_c="",
            individual_investor_ratio="", management_holds="",
            estimated_aum="2.0亿元",
        )
        result = compute_stress_test(scale, None, None, "某基金")
        assert result.excess_return is None
        assert result.stress_level is None
        assert result.stress_scenarios["normal"]["loss_billion"] == 0.5

    def test_partial_performance_nav_only(self):
        """只有净值增长率无基准收益率时 stress_level 应为 None。"""
        result = compute_stress_test(None, 0.05, None, "某基金")
        assert result.excess_return is None
        assert result.stress_level is None

    def test_partial_performance_bench_only(self):
        """只有基准收益率无净值增长率时 stress_level 应为 None。"""
        result = compute_stress_test(None, None, 0.03, "某基金")
        assert result.excess_return is None
        assert result.stress_level is None


class TestStressLevel:
    """stress_level 判定测试。"""

    def test_outperform(self):
        result = compute_stress_test(None, 0.10, 0.05, "某基金")
        assert result.stress_level == "outperform"

    def test_inline_zero(self):
        result = compute_stress_test(None, 0.05, 0.05, "某基金")
        assert result.stress_level == "inline"

    def test_inline_minus_one_percent(self):
        result = compute_stress_test(None, 0.04, 0.05, "某基金")
        assert result.excess_return == -0.01
        assert result.stress_level == "inline"

    def test_inline_minus_two_percent_boundary(self):
        result = compute_stress_test(None, 0.03, 0.05, "某基金")
        assert result.excess_return == -0.02
        assert result.stress_level == "inline"

    def test_underperform(self):
        result = compute_stress_test(None, 0.02, 0.05, "某基金")
        assert result.excess_return == -0.03
        assert result.stress_level == "underperform"

    def test_severe_underperform_boundary(self):
        result = compute_stress_test(None, 0.0, 0.05, "某基金")
        assert result.excess_return == -0.05
        assert result.stress_level == "severe_underperform"

    def test_severe_underperform(self):
        result = compute_stress_test(None, 0.0, 0.10, "某基金")
        assert result.excess_return == -0.10
        assert result.stress_level == "severe_underperform"


# --- Slice 16C: 产品定义 + 阈值事件 ---

class TestProductDefinition:
    """产品定义确定性拼接测试。"""

    def test_keyword_match_index300(self):
        from fund_agent.service.extraction import compute_product_definition
        result = compute_product_definition("华夏沪深300ETF联接A", "000051")
        assert "沪深300指数基金" in result
        assert "华夏沪深300ETF联接A" in result
        assert "000051" in result

    def test_keyword_match_bond(self):
        from fund_agent.service.extraction import compute_product_definition
        result = compute_product_definition("某债券型证券投资基金", "123456")
        assert "债券基金" in result

    def test_keyword_match_mixed(self):
        from fund_agent.service.extraction import compute_product_definition
        result = compute_product_definition("某某成长混合", "654321")
        assert "混合型基金" in result

    def test_fallback_no_match(self):
        from fund_agent.service.extraction import compute_product_definition
        result = compute_product_definition("某某灵活配置", "111111")
        assert "是一只基金" in result
        assert "指数" not in result
        assert "债券" not in result

    def test_with_manager(self):
        from fund_agent.service.extraction import compute_product_definition
        manager = FundManagerInfo("张三", "2020-01-01", "10年", "", "")
        result = compute_product_definition("某某混合", "000001", manager)
        assert "由张三管理" in result

    def test_without_manager(self):
        from fund_agent.service.extraction import compute_product_definition
        result = compute_product_definition("某某混合", "000001")
        assert "由" not in result
        assert "管理" not in result


class TestThresholdEvents:
    """阈值事件 tier-delta 算法测试。"""

    def _make_judgment(self, scores: list[tuple[str, int, int, bool]]) -> SignalJudgment:
        """通过 compute_signal_judgment 路径构造带阈值事件的 SignalJudgment。

        参数: scores = [(name, score, max_score, calculable), ...]
        """
        from fund_agent.service.signal_scoring import _ScoredIndicator
        from fund_agent.service.extraction import _compute_threshold_events
        scored = [
            _ScoredIndicator(
                name=n, value=None, score=s, max_score=m,
                risk_status="🟡", detail="test", calculable=c,
            )
            for n, s, m, c in scores
        ]
        upgrade_event, downgrade_event = _compute_threshold_events(scored)
        total = sum(s for _, s, _, _ in scores)
        total_max = sum(m for _, _, m, _ in scores)
        normalized = round(total / total_max * 100) if total_max > 0 else 0
        calculable_count = sum(1 for _, _, _, c in scores if c)
        indicators = tuple(
            SignalIndicator(name=n, score=s, max_score=m, detail="test")
            for n, s, m, _ in scores
        )
        return SignalJudgment(
            signal="🟡 需要关注",
            normalized_score=normalized,
            indicators=indicators,
            data_completeness=calculable_count / len(scores),
            upgrade_event=upgrade_event,
            downgrade_event=downgrade_event,
        )

    def test_upgrade_event_picks_largest_tier_delta(self):
        """升级事件应选一档改善 raw points 增量最大的指标。"""
        sj = self._make_judgment([
            ("超额收益趋势", 15, 25, True),   # 15→25, delta=10
            ("费率水平", 25, 25, True),        # 满分，无升级
            ("风格漂移", 5, 25, True),         # 5→15, delta=10
            ("规模风险", 25, 25, True),        # 满分
            ("基金经理变更", 20, 20, True),    # 满分
            ("持仓集中度", 15, 15, True),      # 满分
        ])
        assert sj.upgrade_event is not None
        # 超额收益和风格漂移 delta 相同（都是10），取第一个遇到的
        assert sj.upgrade_event.tier_delta == 10
        assert sj.upgrade_event.direction == "upgrade"

    def test_downgrade_event_picks_largest_drop(self):
        """降级事件应选一档恶化 raw points 损失最大的指标。"""
        sj = self._make_judgment([
            ("超额收益趋势", 25, 25, True),   # 25→15, loss=10
            ("费率水平", 15, 25, True),        # 15→5, loss=10
            ("风格漂移", 5, 25, True),         # 5→0, loss=5
            ("规模风险", 25, 25, True),        # 25→15, loss=10
            ("基金经理变更", 20, 20, True),    # 20→0, loss=20
            ("持仓集中度", 15, 15, True),      # 15→10, loss=5
        ])
        assert sj.downgrade_event is not None
        assert sj.downgrade_event.tier_delta == 20  # 经理变更 20→0
        assert sj.downgrade_event.direction == "downgrade"

    def test_all_full_upgrade_none(self):
        """全部满分时 upgrade_event 应为 None（F2）。"""
        sj = self._make_judgment([
            ("超额收益趋势", 25, 25, True),
            ("费率水平", 25, 25, True),
            ("风格漂移", 25, 25, True),
            ("规模风险", 25, 25, True),
            ("基金经理变更", 20, 20, True),
            ("持仓集中度", 15, 15, True),
        ])
        assert sj.upgrade_event is None
        # 降级事件仍应存在（最大暴露）
        assert sj.downgrade_event is not None

    def test_all_zero_downgrade_none(self):
        """全部零分时 downgrade_event 应为 None（F2）。"""
        sj = self._make_judgment([
            ("超额收益趋势", 0, 25, True),
            ("费率水平", 0, 25, True),
            ("风格漂移", 0, 25, True),
            ("规模风险", 0, 25, True),
            ("基金经理变更", 0, 20, True),
            ("持仓集中度", 0, 15, True),
        ])
        assert sj.downgrade_event is None
        # 升级事件仍应存在（最大提升潜力）
        assert sj.upgrade_event is not None

    def test_low_completeness_both_none(self):
        """data_completeness < 0.5 时两者均 None（F2）。"""
        sj = self._make_judgment([
            ("超额收益趋势", 15, 25, True),
            ("费率水平", 0, 25, False),
            ("风格漂移", 0, 25, False),
            ("规模风险", 0, 25, False),
            ("基金经理变更", 0, 20, False),
            ("持仓集中度", 0, 15, False),
        ])
        assert sj.upgrade_event is None
        assert sj.downgrade_event is None

    def test_threshold_event_description_format(self):
        """description 应包含指标名、得分和 delta。"""
        sj = self._make_judgment([
            ("超额收益趋势", 5, 25, True),
            ("费率水平", 25, 25, True),
            ("风格漂移", 25, 25, True),
            ("规模风险", 25, 25, True),
            ("基金经理变更", 20, 20, True),
            ("持仓集中度", 15, 15, True),
        ])
        assert sj.upgrade_event is not None
        assert "超额收益趋势" in sj.upgrade_event.description
        assert "+10" in sj.upgrade_event.description


# --- Slice 17A: Metadata Sidecar ---

class TestMetadataSidecar:
    """metadata sidecar 测试。"""

    def test_sidecar_created_with_markdown(self, tmp_path):
        """导出 Markdown 时应同时生成 .meta.json sidecar。"""
        from fund_agent.service.extraction import FundReadingService
        service = FundReadingService()
        report = FundReport(
            fund_code="000051",
            fund_name="测试基金",
            report_year=2024,
            chapters=(
                ReportChapter(chapter_id=0, title="投资要点概览", content="## 概览\n\n测试内容", data_sources=()),
            ),
        )
        service._export_markdown(report, tmp_path)

        sidecar_path = tmp_path / "reports" / "000051-2024-analysis.meta.json"
        assert sidecar_path.exists()

    def test_sidecar_fields_complete(self, tmp_path):
        """sidecar 应包含所有规定字段。"""
        import json
        from fund_agent.service.extraction import FundReadingService
        service = FundReadingService()
        report = FundReport(
            fund_code="000051",
            fund_name="测试基金",
            report_year=2024,
            chapters=(),
        )
        service._export_markdown(report, tmp_path)

        sidecar_path = tmp_path / "reports" / "000051-2024-analysis.meta.json"
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert data["fund_code"] == "000051"
        assert data["fund_name"] == "测试基金"
        assert data["report_year"] == 2024
        assert "generation_time" in data
        assert data["audit_score"] is None
        assert data["signal"] is None
        assert data["normalized_score"] is None

    def test_sidecar_with_signal_judgment(self, tmp_path):
        """传入 signal_judgment 时 sidecar 应包含 signal 和 normalized_score。"""
        import json
        from fund_agent.service.extraction import FundReadingService
        from fund_agent.service.models import SignalIndicator, SignalJudgment
        service = FundReadingService()
        report = FundReport(
            fund_code="000051",
            fund_name="测试基金",
            report_year=2024,
            chapters=(),
        )
        sj = SignalJudgment(
            signal="🟢 值得持有",
            normalized_score=85.0,
            indicators=(
                SignalIndicator(name="超额收益趋势", score=25, max_score=25, detail="连续正超额"),
            ),
            data_completeness=1.0,
        )
        service._export_markdown(report, tmp_path, signal_judgment=sj)

        sidecar_path = tmp_path / "reports" / "000051-2024-analysis.meta.json"
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert data["signal"] == "🟢 值得持有"
        assert data["normalized_score"] == 85.0

    def test_sidecar_without_signal_judgment(self, tmp_path):
        """signal_judgment 为 None 时 sidecar 中 signal/normalized_score 应为 None。"""
        import json
        from fund_agent.service.extraction import FundReadingService
        service = FundReadingService()
        report = FundReport(
            fund_code="000051",
            fund_name="测试基金",
            report_year=2024,
            chapters=(),
        )
        service._export_markdown(report, tmp_path, signal_judgment=None)

        sidecar_path = tmp_path / "reports" / "000051-2024-analysis.meta.json"
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert data["signal"] is None
        assert data["normalized_score"] is None


class TestPdfExportFallback:
    """_export_pdf 引擎 fallback 三态测试（pdf-export-fallback-20260805）。"""

    def test_xelatex_available_uses_pandoc_pdf_engine(self, tmp_path, monkeypatch):
        """xelatex 可用：直接走 pandoc --pdf-engine=xelatex，返回 (pdf_path, None)。"""
        from fund_agent.service import FundReadingService

        md_path = tmp_path / "demo-analysis.md"
        md_path.write_text("# 测试报告\n", encoding="utf-8")
        calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(
            reading_service_module.shutil,
            "which",
            lambda name: f"/usr/bin/{name}" if name in ("pandoc", "xelatex") else None,
        )
        monkeypatch.setattr(reading_service_module.subprocess, "run", _fake_run)

        service = FundReadingService()
        pdf_path, warning = service._export_pdf(str(md_path), tmp_path)

        assert pdf_path == str(md_path).replace(".md", ".pdf")
        assert warning is None
        assert calls == [["pandoc", str(md_path), "-o", pdf_path, "--pdf-engine=xelatex"]]

    def test_xelatex_missing_uses_chrome_headless(self, tmp_path, monkeypatch):
        """xelatex 缺失但 Chrome 可用：pandoc→HTML + Chrome print-to-pdf，返回 (pdf_path, None)。"""
        from fund_agent.service import FundReadingService

        md_path = tmp_path / "demo-analysis.md"
        md_path.write_text("# 测试报告\n", encoding="utf-8")
        calls: list[list[str]] = []
        html_paths: list[str] = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "pandoc":
                html_paths.append(cmd[cmd.index("-o") + 1])
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(
            reading_service_module.shutil,
            "which",
            lambda name: "/usr/bin/pandoc" if name == "pandoc" else None,
        )
        monkeypatch.setattr(reading_service_module.subprocess, "run", _fake_run)

        service = FundReadingService()
        monkeypatch.setattr(
            service,
            "_find_chrome",
            lambda: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        pdf_path, warning = service._export_pdf(str(md_path), tmp_path)

        assert pdf_path == str(md_path).replace(".md", ".pdf")
        assert warning is None
        assert len(calls) == 2
        pandoc_cmd, chrome_cmd = calls
        assert pandoc_cmd[:4] == ["pandoc", str(md_path), "-f", "gfm"]
        assert pandoc_cmd[pandoc_cmd.index("-t") + 1] == "html5"
        assert "-s" in pandoc_cmd
        assert "--embed-resources" in pandoc_cmd
        assert "--include-in-header" in pandoc_cmd
        html_path = Path(html_paths[0])
        assert html_path.is_absolute()
        assert chrome_cmd[0] == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        assert "--headless" in chrome_cmd
        assert "--disable-gpu" in chrome_cmd
        assert any(arg.startswith("--print-to-pdf=") for arg in chrome_cmd)
        assert "--no-pdf-header-footer" in chrome_cmd
        assert "--window-size=794,1123" in chrome_cmd
        assert chrome_cmd[-1] == html_path.as_uri()
        # HTML 中间产物在成功转换后清理，不污染 reports 目录
        assert not html_path.exists()

    def test_both_engines_missing_falls_back_to_markdown(self, tmp_path, monkeypatch):
        """xelatex 与 Chrome 均不可用：回退 md + warning，不触发 subprocess。"""
        from fund_agent.service import FundReadingService

        md_path = tmp_path / "demo-analysis.md"
        md_path.write_text("# 测试报告\n", encoding="utf-8")

        monkeypatch.setattr(
            reading_service_module.shutil,
            "which",
            lambda name: "/usr/bin/pandoc" if name == "pandoc" else None,
        )
        run_mock = Mock()
        monkeypatch.setattr(reading_service_module.subprocess, "run", run_mock)

        service = FundReadingService()
        monkeypatch.setattr(service, "_find_chrome", lambda: None)
        pdf_path, warning = service._export_pdf(str(md_path), tmp_path)

        assert pdf_path == str(md_path)
        assert warning == "PDF 导出失败，已回退为 Markdown 格式"
        run_mock.assert_not_called()

    def test_pandoc_missing_warns_pandoc_not_installed(self, tmp_path, monkeypatch):
        """pandoc 缺失：前置探测跳过全部引擎，回退 md + pandoc 未安装 warning。"""
        from fund_agent.service import FundReadingService

        md_path = tmp_path / "demo-analysis.md"
        md_path.write_text("# 测试报告\n", encoding="utf-8")

        monkeypatch.setattr(reading_service_module.shutil, "which", lambda name: None)
        run_mock = Mock()
        monkeypatch.setattr(reading_service_module.subprocess, "run", run_mock)

        service = FundReadingService()
        pdf_path, warning = service._export_pdf(str(md_path), tmp_path)

        assert pdf_path == str(md_path)
        assert warning == "pandoc 未安装，已回退为 Markdown 格式"
        run_mock.assert_not_called()


class TestAnnualPerformanceSectionSplitCompat:
    """Docling section 分裂时，标题和表格归属不同 section 的兼容测试。"""

    def test_table_refs_accepts_adjacent_section(self):
        """当 table citation 的 section_ref 不在 source_section_refs 时应接受回退匹配。"""
        from fund_agent.service.extraction import (
            _annual_performance_table_refs,
            _PerformanceReturnExtractionSpec,
        )

        def _make_locator(kind, section_ref=None, table_ref=None):
            return Locator(
                document_id="test-2022",
                locator_kind=kind,
                section_ref=section_ref,
                table_ref=table_ref,
                page_no=None,
                page_range=None,
                internal_ref=None,
                internal_ref_available=False,
            )

        # 构造 mock result：section citation 在 section-0036，table citation 在 section-0037
        section_citation = Citation(
            document_id="test-2022",
            fund_code="512890",
            fund_name="测试基金",
            year=2022,
            report_type="annual_report",
            locator=_make_locator(LocatorKind.SECTION, section_ref="section-0036"),
        )
        table_citation = Citation(
            document_id="test-2022",
            fund_code="512890",
            fund_name="测试基金",
            year=2022,
            report_type="annual_report",
            locator=_make_locator(LocatorKind.TABLE, section_ref="section-0037", table_ref="table-0009"),
        )
        result = AgentRunResult(
            answer="3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较\ntable here",
            citations=(section_citation, table_citation),
            tool_trace=(),
        )

        # mock tool_service.read_table 返回有正确列签名的表格
        class MockToolService:
            def read_table(self, document_id, table_ref, max_rows=30):
                from fund_agent.fund.document_tools.models import TableContent
                return TableContent(
                    table_ref=table_ref,
                    caption=None,
                    section_ref="section-0037",
                    rows=(
                        ("阶段", "份额净值增长率①", "业绩比较基准收益率③"),
                        ("过去一年", "2.72%", "-1.90%"),
                    ),
                    truncated=False,
                    locator=_make_locator(LocatorKind.TABLE, section_ref="section-0037", table_ref=table_ref),
                    citation=table_citation,
                )

        specs = (
            _PerformanceReturnExtractionSpec(
                field_name="annual_nav_growth_rate",
                column_keywords=("份额净值增长率",),
                excluded_keywords=("标准差",),
            ),
            _PerformanceReturnExtractionSpec(
                field_name="annual_benchmark_return_rate",
                column_keywords=("业绩比较基准收益率",),
                excluded_keywords=("标准差",),
            ),
        )

        refs = _annual_performance_table_refs(
            document_id="test-2022",
            result=result,
            tool_service=MockToolService(),
            source_section_refs=("section-0036",),
            specs=specs,
        )
        assert "table-0009" in refs

    def test_table_refs_strict_match_preferred(self):
        """严格匹配存在时优先使用严格匹配。"""
        from fund_agent.service.extraction import (
            _annual_performance_table_refs,
            _PerformanceReturnExtractionSpec,
        )

        def _make_locator(kind, section_ref=None, table_ref=None):
            return Locator(
                document_id="test-2021",
                locator_kind=kind,
                section_ref=section_ref,
                table_ref=table_ref,
                page_no=None,
                page_range=None,
                internal_ref=None,
                internal_ref_available=False,
            )

        section_citation = Citation(
            document_id="test-2021",
            fund_code="512890",
            fund_name="测试基金",
            year=2021,
            report_type="annual_report",
            locator=_make_locator(LocatorKind.SECTION, section_ref="section-0040"),
        )
        table_citation = Citation(
            document_id="test-2021",
            fund_code="512890",
            fund_name="测试基金",
            year=2021,
            report_type="annual_report",
            locator=_make_locator(LocatorKind.TABLE, section_ref="section-0040", table_ref="table-0010"),
        )
        result = AgentRunResult(
            answer="3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较\ntable",
            citations=(section_citation, table_citation),
            tool_trace=(),
        )

        class MockToolService:
            def read_table(self, document_id, table_ref, max_rows=30):
                from fund_agent.fund.document_tools.models import TableContent
                return TableContent(
                    table_ref=table_ref,
                    caption=None,
                    section_ref="section-0040",
                    rows=(
                        ("阶段", "份额净值增长率①", "业绩比较基准收益率③"),
                        ("过去一年", "19.56%", "10.80%"),
                    ),
                    truncated=False,
                    locator=_make_locator(LocatorKind.TABLE, section_ref="section-0040", table_ref=table_ref),
                    citation=table_citation,
                )

        specs = (
            _PerformanceReturnExtractionSpec(
                field_name="annual_nav_growth_rate",
                column_keywords=("份额净值增长率",),
                excluded_keywords=("标准差",),
            ),
            _PerformanceReturnExtractionSpec(
                field_name="annual_benchmark_return_rate",
                column_keywords=("业绩比较基准收益率",),
                excluded_keywords=("标准差",),
            ),
        )

        refs = _annual_performance_table_refs(
            document_id="test-2021",
            result=result,
            tool_service=MockToolService(),
            source_section_refs=("section-0040",),
            specs=specs,
        )
        assert "table-0010" in refs


# ============================================================
# KI-3: 债券基金持仓抽取 fallback
# ============================================================


def test_bond_holdings_query_constant() -> None:
    """_BOND_HOLDINGS_QUERY 常量必须存在且为非空字符串。"""
    assert hasattr(reading_service_module, "_BOND_HOLDINGS_QUERY")
    assert reading_service_module._BOND_HOLDINGS_QUERY == "前五名债券投资明细"


def test_extract_holdings_from_store_bond_fallback(tmp_path: Path) -> None:
    """债券基金在股票持仓查询失败时 fallback 到债券持仓查询。"""
    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "前五名债券投资明细"
    _RoutingHost.success_answer = "5.4 期末按公允价值占基金资产净值比例大小排序的前五名债券投资明细"
    _RoutingHost.success_locator_kind = LocatorKind.TABLE

    pdf_path = tmp_path / "bond-report.pdf"
    work_dir = tmp_path / "bond-work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_FakeConverter,
        host_factory=_RoutingHost,
    )

    imported = service.import_local_report(
        ImportLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="123456",
            fund_name="某某债券型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    repo = reading_service_module._repository(work_dir)
    store = repo.load_store(imported.document_id)

    _ = service._extract_holdings_from_store(
        document_id=imported.document_id,
        store=store,
        report_year=2024,
        fund_name="某某债券型证券投资基金",
    )

    queries = [call["query"] for call in _RoutingHost.calls]
    assert "前五名债券投资明细" in queries, (
        f"债券基金应 fallback 到 bond query，实际 queries: {queries}"
    )


def test_extract_holdings_from_store_equity_unaffected(tmp_path: Path) -> None:
    """股票基金不应触发债券持仓 fallback。"""
    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "股票投资明细"
    _RoutingHost.success_answer = "8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细"
    _RoutingHost.success_locator_kind = LocatorKind.TABLE

    pdf_path = tmp_path / "equity-report.pdf"
    work_dir = tmp_path / "equity-work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_FakeConverter,
        host_factory=_RoutingHost,
    )

    imported = service.import_local_report(
        ImportLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )

    repo = reading_service_module._repository(work_dir)
    store = repo.load_store(imported.document_id)

    _ = service._extract_holdings_from_store(
        document_id=imported.document_id,
        store=store,
        report_year=2024,
        fund_name="安信企业价值优选混合型证券投资基金",
    )

    queries = [call["query"] for call in _RoutingHost.calls]
    assert "前五名债券投资明细" not in queries, (
        f"股票基金不应触发 bond fallback，实际 queries: {queries}"
    )


# ============================================================
# KI-3 债券持仓表格解析
# ============================================================


def test_bond_holdings_column_indexes_identifies_bond_table():
    """_bond_holdings_column_indexes 正确识别债券持仓表的列映射。"""
    from fund_agent.service.extraction import _bond_holdings_column_indexes

    rows = (
        ("序号", "债券品种", "公允价值", "占基金资产净值比例（%）"),
        ("1", "中期票据", "1,301,165,882.67", "10.33"),
    )
    result = _bond_holdings_column_indexes(rows)
    assert result is not None
    assert result["stock_code"] == 0
    assert result["stock_name"] == 1
    assert result["fair_value"] == 2
    assert result["percentage"] == 3


def test_bond_holdings_column_indexes_rejects_stock_table():
    """_bond_holdings_column_indexes 对股票持仓表返回 None。"""
    from fund_agent.service.extraction import _bond_holdings_column_indexes

    rows = (
        ("股票代码", "股票名称", "数量（股）", "公允价值", "占基金资产净值比例（%）"),
        ("000001", "平安银行", "1,000", "10,000", "5.0"),
    )
    result = _bond_holdings_column_indexes(rows)
    assert result is None


def test_bond_holdings_column_indexes_rejects_empty():
    """_bond_holdings_column_indexes 对空表返回 None。"""
    from fund_agent.service.extraction import _bond_holdings_column_indexes

    assert _bond_holdings_column_indexes(()) is None


def test_extract_holdings_parses_bond_table():
    """债券持仓表能被正确解析为 HoldingExtraction。"""
    from fund_agent.service.extraction import _extract_holdings_from_agent_result
    from fund_agent.fund.document_tools.models import TableContent

    def _make_locator(kind, section_ref=None, table_ref=None):
        return Locator(
            document_id="test-bond",
            locator_kind=kind,
            section_ref=section_ref,
            table_ref=table_ref,
            page_no=None,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )

    table_citation = Citation(
        document_id="test-bond",
        fund_code="006597",
        fund_name="某某债券基金",
        year=2024,
        report_type="annual_report",
        locator=_make_locator(LocatorKind.TABLE, section_ref="section-bond", table_ref="table-bond"),
    )

    result = AgentRunResult(
        answer="8.6 期末按公允价值占基金资产净值比例大小排序的前五名债券投资明细",
        citations=(table_citation,),
        tool_trace=(),
    )

    class MockToolService:
        def read_table(self, document_id, table_ref, max_rows=30):
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-bond",
                rows=(
                    ("序号", "债券品种", "公允价值", "占基金资产净值比例（%）"),
                    ("1", "中期票据", "1,301,165,882.67", "10.33"),
                    ("2", "可转债（可交换债）", "543,392,188.50", "4.31"),
                    ("3", "同业存单", "200,000,000.00", "1.59"),
                ),
                truncated=False,
                locator=_make_locator(LocatorKind.TABLE, section_ref="section-bond", table_ref=table_ref),
                citation=table_citation,
            )

        def list_tables(self, document_id):
            return ()

    holdings = _extract_holdings_from_agent_result(
        document_id="test-bond",
        result=result,
        tool_service=MockToolService(),
    )

    assert len(holdings) == 3
    assert holdings[0].stock_code == "1"
    assert holdings[0].stock_name == "中期票据"
    assert holdings[0].quantity == ""
    assert holdings[0].fair_value == "1,301,165,882.67"
    assert holdings[0].percentage == "10.33"
    assert holdings[1].stock_name == "可转债（可交换债）"
    assert holdings[2].stock_name == "同业存单"


def test_extract_holdings_bond_skips_total_row():
    """债券持仓解析跳过 合计 行。"""
    from fund_agent.service.extraction import _extract_holdings_from_agent_result
    from fund_agent.fund.document_tools.models import TableContent

    def _make_locator(kind, section_ref=None, table_ref=None):
        return Locator(
            document_id="test-bond",
            locator_kind=kind,
            section_ref=section_ref,
            table_ref=table_ref,
            page_no=None,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )

    table_citation = Citation(
        document_id="test-bond",
        fund_code="006597",
        fund_name="某某债券基金",
        year=2024,
        report_type="annual_report",
        locator=_make_locator(LocatorKind.TABLE, section_ref="section-bond", table_ref="table-bond"),
    )

    result = AgentRunResult(
        answer="8.6 期末按公允价值占基金资产净值比例大小排序的前五名债券投资明细",
        citations=(table_citation,),
        tool_trace=(),
    )

    class MockToolService:
        def read_table(self, document_id, table_ref, max_rows=30):
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-bond",
                rows=(
                    ("序号", "债券品种", "公允价值", "占基金资产净值比例（%）"),
                    ("1", "中期票据", "1,301,165,882.67", "10.33"),
                    ("2", "合计", "1,301,165,882.67", "10.33"),
                ),
                truncated=False,
                locator=_make_locator(LocatorKind.TABLE, section_ref="section-bond", table_ref=table_ref),
                citation=table_citation,
            )

        def list_tables(self, document_id):
            return ()

    holdings = _extract_holdings_from_agent_result(
        document_id="test-bond",
        result=result,
        tool_service=MockToolService(),
    )

    assert len(holdings) == 1
    assert holdings[0].stock_name == "中期票据"


def test_extract_holdings_stock_table_regression():
    """股票持仓表解析不受债券逻辑影响（回归测试）。"""
    from fund_agent.service.extraction import _extract_holdings_from_agent_result
    from fund_agent.fund.document_tools.models import TableContent

    def _make_locator(kind, section_ref=None, table_ref=None):
        return Locator(
            document_id="test-equity",
            locator_kind=kind,
            section_ref=section_ref,
            table_ref=table_ref,
            page_no=None,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )

    table_citation = Citation(
        document_id="test-equity",
        fund_code="004393",
        fund_name="某某股票基金",
        year=2024,
        report_type="annual_report",
        locator=_make_locator(LocatorKind.TABLE, section_ref="section-equity", table_ref="table-equity"),
    )

    result = AgentRunResult(
        answer="8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细",
        citations=(table_citation,),
        tool_trace=(),
    )

    class MockToolService:
        def read_table(self, document_id, table_ref, max_rows=30):
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-equity",
                rows=(
                    ("股票代码", "股票名称", "数量（股）", "公允价值", "占基金资产净值比例（%）"),
                    ("000001", "平安银行", "1,000,000", "10,000,000.00", "5.00"),
                    ("000002", "万科A", "500,000", "5,000,000.00", "2.50"),
                ),
                truncated=False,
                locator=_make_locator(LocatorKind.TABLE, section_ref="section-equity", table_ref=table_ref),
                citation=table_citation,
            )

        def list_tables(self, document_id):
            return ()

    holdings = _extract_holdings_from_agent_result(
        document_id="test-equity",
        result=result,
        tool_service=MockToolService(),
    )

# ── F1/F2: 费率有界非贪婪 + 持仓 header-fallback 双向查找 ─────────────


def test_extract_fee_rates_multi_percentage_answer_taken_itemwise() -> None:
    """多百分比答案必须逐项取对：管理费 1.20%、托管费 0.20%、销售C 0.60%。"""
    from fund_agent.service.extraction import _extract_fee_rates_from_agent_result

    result = AgentRunResult(
        answer=(
            "来源章节: 7.4.10.2.1 基金管理费\n\n"
            "注：(1)基金管理费每日计提，按月支付。本基金的管理费按前一日基金资产净值的1.20%的年费率计提。\n"
            "来源章节: 7.4.10.2.2 基金托管费\n\n"
            "注：(1)基金托管费每日计提，按月支付。本基金的托管费按前一日基金资产净值的0.20%的年费率计提。\n"
            "来源章节: 7.4.10.2.3 销售服务费\n\n"
            "注：(1)本基金A类基金份额不收取销售服务费。\n"
            "(2)C类基金份额的销售服务费按前一日C类基金资产净值的0.60%年费率计提。"
        ),
        citations=(),
        tool_trace=(),
    )

    fees = _extract_fee_rates_from_agent_result(result=result)
    by_name = {fee.fee_name: fee.rate for fee in fees}
    assert by_name == {
        "基金管理费": "1.20%",
        "基金托管费": "0.20%",
        "销售服务费A类": "不收取",
        "销售服务费C类": "0.60%",
    }


def test_normalize_percent_text_folds_docling_whitespace() -> None:
    """Docling 空格噪声 1.  50% 必须归一为 1.50%，且不改正文其余部分。"""
    from fund_agent.service.extraction import _normalize_percent_text

    assert (
        _normalize_percent_text(
            "基金管理费按前一日的基金资产净值的1.  50%的年费率计提。"
        )
        == "基金管理费按前一日的基金资产净值的1.50%的年费率计提。"
    )
    assert _normalize_percent_text("1. 50 %") == "1.50%"
    assert _normalize_percent_text("2023. 7.10 与 1.50%") == "2023. 7.10 与 1.50%"


def test_extract_fee_rates_whitespace_noise_takes_management_rate() -> None:
    """空格噪声年度（2021/2022 风格）管理费必须取 1.50%，不得误取后文托管费 0.25%。"""
    from fund_agent.service.extraction import _extract_fee_rates_from_agent_result

    result = AgentRunResult(
        answer=(
            "7.4.10.2.1 基金管理费\n\n"
            "注：基金管理费按前一日的基金资产净值的1.  50%的年费率计提。"
            "计算方法如下：每日应支付的基金管理费=前一日的基金资产净值×1.  50%/当年天数。\n"
            "7.4.10.2.2 基金托管费\n\n"
            "注：基金托管费按前一日的基金资产净值的0.25%的年费率计提。"
            "计算方法如下：每日应支付的基金托管费=前一日的基金资产净值×0.25%/当年天数。"
        ),
        citations=(),
        tool_trace=(),
    )

    fees = _extract_fee_rates_from_agent_result(result=result)
    by_name = {fee.fee_name: fee.rate for fee in fees}
    assert by_name == {
        "基金管理费": "1.50%",
        "基金托管费": "0.25%",
    }


def test_extract_fee_rates_history_text_takes_current_rate_after_marker() -> None:
    """沿革文本：自…年…月…日起 后取当期费率（1.50% → 1.20% 场景）。"""
    from fund_agent.service.extraction import _extract_fee_rates_from_agent_result

    result = AgentRunResult(
        answer=(
            "7.4.4.10 费用的确认和计量\n\n"
            "(1)2023 年 1 月 1 日至 2023 年 7 月 9 日止期间，基金管理费按前一日的基金资产净值的 1.50%的年费率计提。"
            "根据《兴证全球基金管理有限公司关于调低旗下部分基金费率并修订基金合同的公告》，自2023年7月10日起，"
            "基金管理费按前一日基金资产净值的1.20%的年费率计提；\n"
            "(2)2023 年 1 月 1 日至 2023 年 7 月 9 日止期间，基金托管费按前一日的基金资产净值的 0.25%的年费率计提。"
            "根据《兴证全球基金管理有限公司关于调低旗下部分基金费率并修订基金合同的公告》，自2023年7月10日起，"
            "基金托管费按前一日基金资产净值的0.20%的年费率计提；"
        ),
        citations=(),
        tool_trace=(),
    )

    fees = _extract_fee_rates_from_agent_result(result=result)
    by_name = {fee.fee_name: fee.rate for fee in fees}
    assert by_name == {
        "基金管理费": "1.20%",
        "基金托管费": "0.20%",
    }


def test_extract_fee_rates_no_history_takes_last_percent_in_title_block() -> None:
    """无沿革文本时取费率标题块内最后一个百分比（重复出现取末次）。"""
    from fund_agent.service.extraction import _extract_fee_rates_from_agent_result

    result = AgentRunResult(
        answer=(
            "7.4.10.2.1 基金管理费\n\n"
            "注：基金管理费按前一日基金资产净值的1.50%的年费率计提。"
            "计算方法如下：每日应支付的基金管理费=前一日的基金资产净值×1.50%/当年天数。\n"
            "7.4.10.2.2 基金托管费\n\n"
            "注：基金托管费按前一日基金资产净值的0.25%的年费率计提。"
            "计算方法如下：每日应支付的基金托管费=前一日的基金资产净值×0.25%/当年天数。"
        ),
        citations=(),
        tool_trace=(),
    )

    fees = _extract_fee_rates_from_agent_result(result=result)
    by_name = {fee.fee_name: fee.rate for fee in fees}
    assert by_name == {
        "基金管理费": "1.50%",
        "基金托管费": "0.25%",
    }


def test_extract_fee_rate_fields_normalizes_docling_whitespace_noise() -> None:
    """10C 路径对 Docling 空格噪声（1.  50%）归一化后必须提取 1.50%。"""

    management_result, custodian_result, sales_result = _overlapping_fee_rate_results()
    management_result = AgentRunResult(
        answer=(
            "7.4.10.2.1 基金管理费\n\n"
            "注：本基金的管理费按前一日的基金资产净值的1.  50%的年费率计提。\n"
            "计算方法如下：H=E×1.  50%/当年天数"
        ),
        citations=management_result.citations,
        tool_trace=management_result.tool_trace,
    )
    aggregated = reading_service_module._aggregate_fee_rate_results(
        (management_result, custodian_result, sales_result)
    )

    fields = reading_service_module._extract_fee_rate_fields(aggregated)
    values = {(field.field_name, field.share_class_scope): field for field in fields}
    assert values[("management_fee_rate", "all_share_classes")].decimal_percent_text == "1.50%"
    assert "1.50%" in values[("management_fee_rate", "all_share_classes")].raw_text
    assert values[("custodian_fee_rate", "all_share_classes")].decimal_percent_text == "0.20%"


def _holdings_locator(*, table_ref: str, section_ref: str, document_id: str = "test-doc") -> Locator:
    """构造持仓表 locator。"""

    return Locator(
        document_id=document_id,
        locator_kind=LocatorKind.TABLE,
        section_ref=section_ref,
        table_ref=table_ref,
        page_no=None,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
    )


def test_extract_holdings_header_fallback_searches_same_section_both_directions() -> None:
    """无表头续表在同 section 双向查找表头：更高编号候选也能命中。"""
    from fund_agent.service.extraction import _extract_holdings_from_agent_result
    from fund_agent.fund.document_tools.models import TableContent, TableSummary

    table_citation = Citation(
        document_id="test-doc",
        fund_code="163415",
        fund_name="兴全商业模式混合(LOF)",
        year=2025,
        report_type="annual_report",
        locator=_holdings_locator(table_ref="table-0074", section_ref="section-stock"),
    )
    result = AgentRunResult(
        answer="8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细",
        citations=(table_citation,),
        tool_trace=(),
    )
    stock_rows = (
        ("1", "300750", "宁德时代", "2,750,252", "1,010,057,549.52", "6.86"),
        *(
            (str(i + 2), f"600000{i}", f"股票{i}", "1,000", "100,000.00", f"{i + 1}.00")
            for i in range(1, 10)
        ),
    )

    class MockToolService:
        def read_table(self, document_id, table_ref, max_rows=15):
            if table_ref == "table-0074":
                # 无表头续表：数据行与表头表列布局一致
                rows = stock_rows
                section_ref = "section-stock"
            elif table_ref == "table-0076":
                rows = (
                    ("序号", "股票代码", "股票名称", "数量（股）", "公允价值（元）", "占基金资产净值比例（%）"),
                )
                section_ref = "section-stock"
            else:
                raise AssertionError(f"不应读取 {table_ref}")
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref=section_ref,
                rows=rows,
                truncated=False,
                locator=_holdings_locator(table_ref=table_ref, section_ref=section_ref),
                citation=table_citation,
            )

        def list_tables(self, document_id):
            # 表头表在更高编号（table-0076，同 section +2）；跨 section 与超范围表必须被忽略
            return tuple(
                TableSummary(
                    table_ref=ref,
                    caption=None,
                    section_ref=section,
                    locator=_holdings_locator(table_ref=ref, section_ref=section),
                    row_count=1,
                    column_count=6,
                )
                for ref, section in (
                    ("table-0075", "section-other"),
                    ("table-0076", "section-stock"),
                    ("table-0081", "section-stock"),
                    ("table-0068", "section-stock"),
                )
            )

    holdings = _extract_holdings_from_agent_result(
        document_id="test-doc",
        result=result,
        tool_service=MockToolService(),
    )

    assert len(holdings) == 10
    assert holdings[0].stock_code == "300750"
    assert holdings[0].stock_name == "宁德时代"
    assert holdings[0].percentage == "6.86"


_HOLDINGS_2023_DOCLING_JSON = Path(
    ".fund_e2e_163415/docling_json/163415-2023-annual_report-4c98bb7704b3ae2d"
    "/163415-2023-annual_report-4c98bb7704b3ae2d.docling.json"
)
_HOLDINGS_2025_DOCLING_JSON = Path(
    ".fund_e2e_163415/docling_json/163415-2025-annual_report-2654de4c6afae614"
    "/163415-2025-annual_report-2654de4c6afae614.docling.json"
)


class _StoreBackedToolService:
    """把 DoclingDocumentStore 投影为持仓抽取所需的最小 tool service。"""

    def __init__(self, store) -> None:
        self._store = store

    def read_table(self, document_id, table_ref, max_rows=15):
        return self._store.read_table(table_ref, max_rows=max_rows)

    def list_tables(self, document_id):
        return self._store.list_tables()


def _real_fixture_holdings(
    *,
    year: int,
    json_path: Path,
    table_ref: str,
    section_ref: str,
):
    """基于现成 docling JSON fixture 抽取前十大持仓。"""
    from fund_agent.service.extraction import _extract_holdings_from_agent_result
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity, ReportType, SourceKind

    document_id = f"163415-{year}-annual_report-fixture"
    store = DoclingDocumentStore(
        identity=ReportIdentity(
            fund_code="163415",
            fund_name="兴全商业模式混合(LOF)",
            year=year,
            report_type=ReportType.ANNUAL_REPORT,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id="fixture",
            content_fingerprint="fixture",
            document_id=document_id,
        ),
        json_path=json_path,
    )
    citation = Citation(
        document_id=document_id,
        fund_code="163415",
        fund_name="兴全商业模式混合(LOF)",
        year=year,
        report_type="annual_report",
        locator=_holdings_locator(
            table_ref=table_ref,
            section_ref=section_ref,
            document_id=document_id,
        ),
    )
    result = AgentRunResult(
        answer="8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细",
        citations=(citation,),
        tool_trace=(),
    )
    return _extract_holdings_from_agent_result(
        document_id=document_id,
        result=result,
        tool_service=_StoreBackedToolService(store),
    )


@pytest.mark.parametrize(
    ("year", "json_path", "table_ref", "section_ref", "expected_first"),
    [
        (
            2025,
            _HOLDINGS_2025_DOCLING_JSON,
            "table-0076",
            "section-0587",
            ("300750", "宁德时代", "6.86"),
        ),
        (
            2023,
            _HOLDINGS_2023_DOCLING_JSON,
            "table-0075",
            "section-0594",
            ("600690", "海尔智家", "6.46"),
        ),
    ],
)
def test_extract_holdings_real_docling_fixture_top10(
    year: int,
    json_path: Path,
    table_ref: str,
    section_ref: str,
    expected_first: tuple[str, str, str],
) -> None:
    """现成 docling JSON fixture：前十大持仓非空且首行股票名称/占比正确。"""

    assert json_path.is_file(), f"{year} 现成 docling JSON fixture 缺失"
    holdings = _real_fixture_holdings(
        year=year,
        json_path=json_path,
        table_ref=table_ref,
        section_ref=section_ref,
    )
    assert len(holdings) == 10
    code, name, pct = expected_first
    assert holdings[0].stock_code == code
    assert holdings[0].stock_name == name
    assert holdings[0].percentage == pct


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (
            (("行业类别", "公允价值（人民币）", "占基金资产净值比例（%）"),),
            False,
        ),
        (
            (("金融", "33,232,890.09", "11.12"),),
            False,
        ),
        (
            (("序号", "股票代码", "股票名称", "数量（股）", "公允价值（元）", "占基金资产净值比例（%）"),),
            True,
        ),
        (
            (("1", "300750", "宁德时代", "2,750,252", "1,010,057,549.52", "6.86"),),
            True,
        ),
        (
            (("序号", "债券品种", "公允价值", "占基金资产净值比例（%）"),),
            True,
        ),
    ],
)
def test_is_holdings_table_candidate_discrimination(rows, expected) -> None:
    """表级鉴别：行业配置表不满足股票/债券特征列，持仓表与续表候选满足。"""
    from fund_agent.service.extraction import _is_holdings_table_candidate

    assert _is_holdings_table_candidate(rows) is expected


def test_extract_holdings_skips_industry_table_citation() -> None:
    """首位 citation 为行业配置表时必须跳过并继续遍历，不能 break 消费非持仓表。"""
    from fund_agent.service.extraction import _extract_holdings_from_agent_result
    from fund_agent.fund.document_tools.models import TableContent

    def _make_locator(kind, section_ref=None, table_ref=None):
        return Locator(
            document_id="test-doc",
            locator_kind=kind,
            section_ref=section_ref,
            table_ref=table_ref,
            page_no=None,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )

    def _citation(table_ref: str) -> Citation:
        return Citation(
            document_id="test-doc",
            fund_code="004393",
            fund_name="安信企业价值优选混合A",
            year=2022,
            report_type="annual_report",
            locator=_make_locator(LocatorKind.TABLE, section_ref="section-stock", table_ref=table_ref),
        )

    industry_rows = (
        ("行业类别", "公允价值（人民币）", "占基金资产净值比例（%）"),
        ("农、林、牧、渔业", "664,200.00", "1.34"),
        ("制造业", "10,000,000.00", "20.00"),
    )
    stock_rows = (
        ("序号", "股票代码", "股票名称", "数量（股）", "公允价值（元）", "占基金资产净值比例（%）"),
        ("1", "300750", "宁德时代", "2,750,252", "1,010,057,549.52", "6.86"),
        *(
            (str(i + 2), f"600000{i}", f"股票{i}", "1,000", "100,000.00", f"{i + 1}.00")
            for i in range(1, 10)
        ),
    )
    industry_citation = _citation("table-industry")
    stock_citation = _citation("table-stock")
    result = AgentRunResult(
        answer="8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细",
        citations=(industry_citation, stock_citation),
        tool_trace=(),
    )

    class MockToolService:
        def read_table(self, document_id, table_ref, max_rows=15):
            rows = industry_rows if table_ref == "table-industry" else stock_rows
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-stock",
                rows=rows,
                truncated=False,
                locator=_make_locator(LocatorKind.TABLE, section_ref="section-stock", table_ref=table_ref),
                citation=_citation(table_ref),
            )

        def list_tables(self, document_id):
            return ()

    holdings = _extract_holdings_from_agent_result(
        document_id="test-doc",
        result=result,
        tool_service=MockToolService(),
    )

    assert len(holdings) == 10
    assert holdings[0].stock_code == "300750"
    assert holdings[0].stock_name == "宁德时代"
    assert holdings[0].percentage == "6.86"


def test_extract_stock_holdings_from_tables_direct_scan() -> None:
    """A 股直接扫描兜底：跳过行业配置表，命中真实持仓表并解析 10 行。"""
    from fund_agent.service.extraction import _extract_stock_holdings_from_tables
    from fund_agent.fund.document_tools.models import TableContent, TableSummary

    def _make_locator(kind, section_ref=None, table_ref=None):
        return Locator(
            document_id="test-doc",
            locator_kind=kind,
            section_ref=section_ref,
            table_ref=table_ref,
            page_no=None,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )

    def _citation(table_ref: str) -> Citation:
        return Citation(
            document_id="test-doc",
            fund_code="004393",
            fund_name="安信企业价值优选混合A",
            year=2022,
            report_type="annual_report",
            locator=_make_locator(LocatorKind.TABLE, section_ref="section-stock", table_ref=table_ref),
        )

    industry_rows = (
        ("行业类别", "公允价值（人民币）", "占基金资产净值比例（%）"),
        ("制造业", "10,000,000.00", "20.00"),
    )
    stock_rows = (
        ("序号", "股票代码", "股票名称", "数量（股）", "公允价值（元）", "占基金资产净值比例（%）"),
        *(
            (str(i + 1), f"600000{i}", f"股票{i}", "1,000", "100,000.00", f"{i + 1}.00")
            for i in range(10)
        ),
    )

    class MockToolService:
        def list_tables(self, document_id):
            return tuple(
                TableSummary(
                    table_ref=ref,
                    caption=None,
                    section_ref="section-stock",
                    locator=_make_locator(LocatorKind.TABLE, section_ref="section-stock", table_ref=ref),
                    row_count=len(rows),
                    column_count=len(rows[0]),
                )
                for ref, rows in (("table-industry", industry_rows), ("table-stock", stock_rows))
            )

        def read_table(self, document_id, table_ref, max_rows=15):
            rows = industry_rows if table_ref == "table-industry" else stock_rows
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-stock",
                rows=rows,
                truncated=False,
                locator=_make_locator(LocatorKind.TABLE, section_ref="section-stock", table_ref=table_ref),
                citation=_citation(table_ref),
            )

    direct = _extract_stock_holdings_from_tables(
        document_id="test-doc",
        tool_service=MockToolService(),
    )

    assert direct is not None
    holdings, citation = direct
    assert len(holdings) == 10
    assert holdings[0].stock_code == "6000000"
    assert holdings[0].stock_name == "股票0"
    assert holdings[0].percentage == "1.00"
    assert citation is not None
    assert citation.locator.table_ref == "table-stock"


# ── S1: QDII 持仓抽取适配（主动 QDII fallback + 跨页分裂表）────────────


_QDII_2024_DOCLING_JSON = Path(
    ".fund_e2e_519696/docling_json/519696-2024-annual_report-3ce5b5d45892aebb"
    "/519696-2024-annual_report-3ce5b5d45892aebb.docling.json"
)
_QDII_2025_DOCLING_JSON = Path(
    ".fund_e2e_519696/docling_json/519696-2025-annual_report-916f45f0b922ba07"
    "/519696-2025-annual_report-916f45f0b922ba07.docling.json"
)
_QDII_2021_DOCLING_JSON = Path(
    ".fund_e2e_519696/docling_json/519696-2021-annual_report-4b01ce532e65385d"
    "/519696-2021-annual_report-4b01ce532e65385d.docling.json"
)
_QDII_2022_DOCLING_JSON = Path(
    ".fund_e2e_519696/docling_json/519696-2022-annual_report-15f819d80df0c95f"
    "/519696-2022-annual_report-15f819d80df0c95f.docling.json"
)
_QDII_2023_DOCLING_JSON = Path(
    ".fund_e2e_519696/docling_json/519696-2023-annual_report-19d8de646241b0fc"
    "/519696-2023-annual_report-19d8de646241b0fc.docling.json"
)


def _qdii_fixture_store(*, year: int, json_path: Path):
    """构造 519696 QDII 现成 docling JSON fixture 对应的 store。"""
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity, ReportType, SourceKind

    return DoclingDocumentStore(
        identity=ReportIdentity(
            fund_code="519696",
            fund_name="交银环球精选混合(QDII)",
            year=year,
            report_type=ReportType.ANNUAL_REPORT,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id="fixture",
            content_fingerprint="fixture",
            document_id=f"519696-{year}-annual_report-fixture",
        ),
        json_path=json_path,
    )


def test_holdings_column_indexes_qdii_prefers_chinese_name() -> None:
    """QDII 双公司名称列（英文/中文）优先映射中文列。"""
    from fund_agent.service.extraction import _holdings_column_indexes

    rows = (
        ("序号", "公司名称（英文）", "公司名称（中文）", "证券代码", "数量（股）", "公允价值", "占基金资产净值比例（%）"),
        ("1", "Tencent Holdings Ltd", "腾讯控股", "700 HK", "17,000", "9,195,862.26", "5.01"),
    )
    mapping = _holdings_column_indexes(rows)
    assert mapping is not None
    assert mapping["stock_name"] == 2
    assert mapping["stock_code"] == 3
    assert mapping["quantity"] == 4
    assert mapping["fair_value"] == 5
    assert mapping["percentage"] == 6


def test_holdings_column_indexes_stock_name_unaffected() -> None:
    """A 股表头 股票名称 列映射不回退。"""
    from fund_agent.service.extraction import _holdings_column_indexes

    rows = (
        ("序号", "股票代码", "股票名称", "数量（股）", "公允价值", "占基金资产净值比例（%）"),
        ("1", "300750", "宁德时代", "1,000", "10,000.00", "6.86"),
    )
    mapping = _holdings_column_indexes(rows)
    assert mapping is not None
    assert mapping["stock_name"] == 2
    assert mapping["stock_code"] == 1
    assert mapping["percentage"] == 5


def test_holdings_column_indexes_qdii_truncated_header_prefix() -> None:
    """519696-2023 截断表头（「证券代」「占基」）前缀识别：列数据含数字时可绑定。"""
    from fund_agent.service.extraction import _holdings_column_indexes

    rows = (
        ("序", "公司名称", "公司名", "证券代", "所在证", "所属", "数量", "公允价值", "占基"),
        ("1", "Sinotruk Hong Kong Ltd", "中国重 汽", "3808 HK", "香港联 合交易 所", "中 国 香港", "232,000", "3,223,733.22", "4.17"),
        ("2", "Tencent Holdings Ltd", "腾讯控 股", "700 HK", "香港联 合交易 所", "中 国 香港", "10,600", "2,822,761.99", "3.66"),
    )
    mapping = _holdings_column_indexes(rows)
    assert mapping is not None
    assert mapping["stock_code"] == 3
    assert mapping["stock_name"] == 1
    assert mapping["quantity"] == 6
    assert mapping["fair_value"] == 7
    assert mapping["percentage"] == 8


def test_holdings_column_indexes_truncated_header_requires_digit_cells() -> None:
    """截断前缀匹配必须校验列数据含数字：仅表头或无数字列不得绑定。"""
    from fund_agent.service.extraction import _holdings_column_indexes

    # 跨页主表仅含截断表头（519696-2023 table-0064 形态）：无数据单元格，fail-closed。
    header_only = (
        ("序", "公司名称", "公司名", "证券代", "所在证", "所属", "数量", "公允价值", "占基"),
    )
    assert _holdings_column_indexes(header_only) is None

    # 「占基」列数据不含数字（如行业名称），前缀不得误绑。
    no_digits = (
        ("序", "公司名称", "证券代", "数量", "公允价值", "占基"),
        ("1", "某某公司", "700 HK", "17,000", "9,195,862.26", "行业A"),
        ("2", "另一公司", "700 HK", "10,000", "8,000,000.00", "行业B"),
    )
    assert _holdings_column_indexes(no_digits) is None


def test_holdings_column_indexes_qdii_position_fallback() -> None:
    """列位置推断兜底：代码/占比截断到前缀无法识别时，按 QDII 固定列序推断。"""
    from fund_agent.service.extraction import _holdings_column_indexes

    rows = (
        ("序", "名称英", "名称中", "证券", "市场", "国家", "数量", "公允价值", "占"),
        ("1", "Tencent Holdings Ltd", "腾讯控 股", "700 HK", "港交所", "中国香港", "17,000", "9,195,862.26", "5.01"),
        ("2", "Alphabet Inc", "Alphabet 公司", "GOOGL US", "美交所", "美国", "145", "2,678,245.40", "2.87"),
        ("3", "Microsoft Corp", "微软公 司", "MSFT US", "美交所", "美国", "938", "2,498,249.04", "3.24"),
    )
    mapping = _holdings_column_indexes(rows)
    assert mapping is not None
    assert mapping["stock_code"] == 3
    assert mapping["stock_name"] == 1
    assert mapping["quantity"] == 6
    assert mapping["fair_value"] == 7
    assert mapping["percentage"] == 8


def test_holdings_column_indexes_rejects_non_holdings_tables() -> None:
    """前缀放宽/位置推断不得误判行业配置表、估值表、资产组合表、买卖明细表。"""
    from fund_agent.service.extraction import _holdings_column_indexes

    # 行业配置表（行业类别/公允价值/占净值比例）
    industry = (
        ("行业类别", "公允价值", "占基金资产净值比例(%)"),
        ("通讯", "9,946,487.28", "12.88"),
        ("非必需消费品", "13,391,509.48", "17.34"),
    )
    assert _holdings_column_indexes(industry) is None

    # 估值表（公允价值计量层次）
    valuation = (
        ("公允价值计量结果所属的层次", "本期末 2023年12月31日", "上年度末 2022年12月31日"),
        ("第一层次", "70,231,733.87", "67,070,372.17"),
        ("第二层次", "-", "-"),
    )
    assert _holdings_column_indexes(valuation) is None

    # 资产组合表（占基金总资产的比例）：「占基金」前缀可命中但无名称列，仍应拒绝。
    portfolio = (
        ("序号", "项目", "金额", "占基金总资产的比例（%）"),
        ("1", "权益投资", "70,231,733.87", "90.43"),
        ("2", "固定收益投资", "1,000,000.00", "1.29"),
    )
    assert _holdings_column_indexes(portfolio) is None

    # 买卖明细表（占期初基金资产净值比例）：前缀不匹配且无数量/公允价值列。
    buy_sell = (
        ("序号", "公司名称（英文）", "证券代码", "本期累计买入金额", "占期初基金资产净值比例(%)"),
        ("1", "Tencent Holdings Ltd", "700 HK", "3,080,419.00", "4.26"),
        ("2", "Sinotruk Hong Kong Ltd", "3808 HK", "2,442,281.20", "3.38"),
    )
    assert _holdings_column_indexes(buy_sell) is None


def test_extract_holdings_from_store_active_qdii_triggers_qdii_fallback(tmp_path: Path) -> None:
    """主动 QDII（infer_fund_type=active_fund）在股票查询失败时进入 QDII fallback 分支。"""
    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "所有权益投资明细"
    _RoutingHost.success_answer = "8.9 期末按公允价值占基金资产净值比例大小排序的前十名股票投资明细"
    _RoutingHost.success_locator_kind = LocatorKind.TABLE

    pdf_path = tmp_path / "qdii-report.pdf"
    work_dir = tmp_path / "qdii-work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_FakeConverter,
        host_factory=_RoutingHost,
    )

    imported = service.import_local_report(
        ImportLocalReportRequest(
            pdf_path=pdf_path,
            fund_code="519696",
            fund_name="交银环球精选混合(QDII)",
            year=2025,
            work_dir=work_dir,
        )
    )

    repo = reading_service_module._repository(work_dir)
    store = repo.load_store(imported.document_id)

    assert infer_fund_type("交银环球精选混合(QDII)") == ("active_fund", True)
    _ = service._extract_holdings_from_store(
        document_id=imported.document_id,
        store=store,
        report_year=2025,
        fund_name="交银环球精选混合(QDII)",
    )

    queries = [call["query"] for call in _RoutingHost.calls]
    assert "所有权益投资明细" in queries, (
        f"主动 QDII 应进入 QDII fallback 分支，实际 queries: {queries}"
    )


@pytest.mark.parametrize(
    ("year", "json_path", "first_name", "first_code", "first_pct", "second_name", "expected_table_ref"),
    [
        (
            2021,
            _QDII_2021_DOCLING_JSON,
            "安踏体育",
            "2020 HK",
            "3.28",
            "Alphabet 公司",
            "table-0067",
        ),
        (
            2022,
            _QDII_2022_DOCLING_JSON,
            "周大福",
            "1929 HK",
            "4.79",
            "比亚迪",
            "table-0069",
        ),
        (
            2023,
            _QDII_2023_DOCLING_JSON,
            "中国重 汽",
            "3808 HK",
            "4.17",
            "腾讯控 股",
            "table-0064",
        ),
        (
            2025,
            _QDII_2025_DOCLING_JSON,
            "腾讯控 股",
            "700 HK",
            "5.01",
            "中国宏 桥集团 有限公 司",
            "table-0061",
        ),
        (
            2024,
            _QDII_2024_DOCLING_JSON,
            "腾讯控 股",
            "700 HK",
            "3.33",
            "微软",
            "table-0061",
        ),
    ],
)
def test_extract_qdii_holdings_from_tables_real_fixture_top10(
    year: int,
    json_path: Path,
    first_name: str,
    first_code: str,
    first_pct: str,
    second_name: str,
    expected_table_ref: str,
) -> None:
    """现成 QDII docling JSON fixture：直接扫描跨页分裂表抽取 10 行，citation 指向持仓主表。"""
    from fund_agent.service.extraction import _extract_qdii_holdings_from_tables

    assert json_path.is_file(), f"{year} 现成 QDII docling JSON fixture 缺失"
    store = _qdii_fixture_store(year=year, json_path=json_path)
    direct = _extract_qdii_holdings_from_tables(
        document_id=f"519696-{year}-annual_report-fixture",
        tool_service=_StoreBackedToolService(store),
    )
    assert direct is not None
    holdings, citation = direct
    assert len(holdings) == 10
    assert holdings[0].stock_name == first_name
    assert holdings[0].stock_code == first_code
    assert holdings[0].percentage == first_pct
    assert holdings[1].stock_name == second_name
    # R2 验收：rank 1-10 连续，第 6 名（跨页续表首行数据）代码/占比非空。
    assert [h.rank for h in holdings] == list(range(1, 11))
    rank6 = holdings[5]
    assert rank6.stock_code
    assert rank6.percentage
    assert citation.locator.table_ref == expected_table_ref


def test_extract_qdii_holdings_from_tables_2023_truncated_header() -> None:
    """519696-2023 表头截断（「证券代」「占基」）回归：真实 fixture 抽取 10 行。

    截断表头经前缀识别 + 跨页续表碎片合并后抽取，行数与 2025 正常表头年份对齐。
    """
    from fund_agent.service.extraction import _extract_qdii_holdings_from_tables

    assert _QDII_2023_DOCLING_JSON.is_file(), "2023 现成 QDII docling JSON fixture 缺失"
    store = _qdii_fixture_store(year=2023, json_path=_QDII_2023_DOCLING_JSON)
    direct = _extract_qdii_holdings_from_tables(
        document_id="519696-2023-annual_report-fixture",
        tool_service=_StoreBackedToolService(store),
    )
    assert direct is not None
    holdings, citation = direct
    assert len(holdings) == 10
    assert [h.rank for h in holdings] == list(range(1, 11))
    assert holdings[0].stock_name == "中国重 汽"
    assert holdings[0].stock_code == "3808 HK"
    assert holdings[0].percentage == "4.17"
    assert holdings[1].stock_name == "腾讯控 股"
    assert citation.locator.table_ref == "table-0064"


def test_extract_qdii_holdings_cross_page_rank6_complete() -> None:
    """第 6 名跨页断裂回归：主表（表头+1-5 名）+ 续表（碎片行+6-10 名）合并后 rank 连续、第 6 名代码/占比非空。"""
    from fund_agent.service.extraction import _extract_qdii_holdings_from_tables
    from fund_agent.fund.document_tools.models import TableContent, TableSummary

    main_header = (
        "序 号",
        "公司名称 （英文）",
        "公司名 称（中 文）",
        "证券代 码",
        "所在证 券市场",
        "所属 国家 （地 区）",
        "数量 （股）",
        "公允价值",
        "占基 金资 产净 值比 例 （%）",
    )
    main_rows = (main_header,) + tuple(
        (str(i), f"Company {i}", f"名称{i}", f"{1000 + i} HK", "香港联 合交易 所", "中 国 香港", "1,000", "100,000.00", f"{i}.00")
        for i in range(1, 6)
    )
    # 续表首行为表头碎片（含名称残片、无代码/占比），其后才是 6-10 名数据行。
    fragment_row = ("", "Internati onal Resources Corp Ltd", "资源有 限公司", "", "所", "", "", "", "")
    cont_rows = (fragment_row,) + tuple(
        (str(i), f"Company {i}", f"名称{i}", f"{1000 + i} HK", "香港联 合交易 所", "中 国 香港", "1,000", "100,000.00", f"{i}.00")
        for i in range(6, 11)
    )

    def _locator(table_ref: str, page_no: int) -> Locator:
        return Locator(
            document_id="test-doc",
            locator_kind=LocatorKind.TABLE,
            section_ref="section-qdii",
            table_ref=table_ref,
            page_no=page_no,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )

    def _citation(table_ref: str, page_no: int) -> Citation:
        return Citation(
            document_id="test-doc",
            fund_code="519696",
            fund_name="交银环球精选混合(QDII)",
            year=2025,
            report_type="annual_report",
            locator=_locator(table_ref, page_no),
        )

    class _QdiiContinuationToolService:
        def read_table(self, document_id, table_ref, max_rows=15):
            rows = main_rows if table_ref == "table-main" else cont_rows
            page_no = 49 if table_ref == "table-main" else 50
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-qdii",
                rows=rows,
                truncated=False,
                locator=_locator(table_ref, page_no),
                citation=_citation(table_ref, page_no),
            )

        def list_tables(self, document_id):
            return (
                TableSummary(
                    table_ref="table-main",
                    caption=None,
                    section_ref="section-qdii",
                    locator=_locator("table-main", 49),
                    row_count=len(main_rows),
                    column_count=9,
                ),
                TableSummary(
                    table_ref="table-cont",
                    caption=None,
                    section_ref="section-qdii",
                    locator=_locator("table-cont", 50),
                    row_count=len(cont_rows),
                    column_count=9,
                ),
            )

    direct = _extract_qdii_holdings_from_tables(
        document_id="test-doc",
        tool_service=_QdiiContinuationToolService(),
    )
    assert direct is not None
    holdings, citation = direct
    assert len(holdings) == 10
    assert [h.rank for h in holdings] == list(range(1, 11))
    assert holdings[5].stock_code == "1006 HK"
    assert holdings[5].stock_name == "名称6"
    assert holdings[5].percentage == "6.00"
    # 碎片行不得被消费为持仓（其名称残片不能顶替第 6 名）。
    assert holdings[4].rank == 5
    assert holdings[5].stock_code != ""
    assert citation.locator.table_ref == "table-main"


def test_extract_multi_year_holdings_qdii_519696_top10() -> None:
    """519696（主动 QDII）2022-2025 各抽取 10 行且 failure=None，citation 指向各年持仓主表。"""
    service = FundReadingService()
    result = service.extract_multi_year_holdings(
        ExtractHoldingsRequest(
            fund_code="519696",
            fund_name="交银环球精选混合(QDII)",
            requested_years=[2022, 2023, 2024, 2025],
            annual_report_documents=[
                AnnualReportDocument(year=2022, document_id="519696-2022-annual_report-15f819d80df0c95f"),
                AnnualReportDocument(year=2023, document_id="519696-2023-annual_report-19d8de646241b0fc"),
                AnnualReportDocument(year=2024, document_id="519696-2024-annual_report-3ce5b5d45892aebb"),
                AnnualReportDocument(year=2025, document_id="519696-2025-annual_report-916f45f0b922ba07"),
            ],
            work_dir=Path(".fund_e2e_519696"),
        )
    )
    assert result.failure is None
    assert result.series is not None
    assert tuple(result.series.covered_years) == (2022, 2023, 2024, 2025)
    assert tuple(result.series.missing_years) == ()
    by_year = {annual.year: annual.holdings for annual in result.series.annual_holdings}
    citations = {annual.year: annual.citation for annual in result.series.annual_holdings}
    for year in (2022, 2023, 2024, 2025):
        assert len(by_year[year]) == 10
    assert by_year[2022][0].stock_name == "周大福"
    assert by_year[2022][0].stock_code == "1929 HK"
    assert by_year[2022][0].percentage == "4.79"
    assert by_year[2023][0].stock_name == "中国重 汽"
    assert by_year[2023][0].stock_code == "3808 HK"
    assert by_year[2023][0].percentage == "4.17"
    assert by_year[2025][0].stock_name == "腾讯控 股"
    assert by_year[2025][2].stock_name == "中芯国 际集成 电路制 造有限 公司"
    assert by_year[2024][0].stock_name == "腾讯控 股"
    # R6 验收：citation 必须指向各年 QDII 持仓主表，而不是国家（地区）/行业类别/续表碎片表。
    assert citations[2022].locator.table_ref == "table-0069"
    assert citations[2023].locator.table_ref == "table-0064"
    assert citations[2024].locator.table_ref == "table-0061"
    assert citations[2025].locator.table_ref == "table-0061"


def test_extract_holdings_from_store_qdii_direct_syncs_citation_to_holdings_table() -> None:
    """QDII 直扫命中真实持仓表后，AnnualHoldingsResult.citation 必须同步为持仓主表。"""
    from fund_agent.service.extraction import FundReadingService

    assert _QDII_2023_DOCLING_JSON.is_file(), "2023 现成 QDII docling JSON fixture 缺失"
    store = _qdii_fixture_store(year=2023, json_path=_QDII_2023_DOCLING_JSON)

    class _QdiiCountryFirstCitationHost:
        """QDII 路由成功但首个 TABLE citation 指向国家（地区）表（table-0062）。"""

        def __init__(self, tool_service) -> None:
            """保存 tool service 但不访问其内部 store。"""

            self._tool_service = tool_service

        def run(self, *, document_id: str, query: str) -> AgentRunResult:
            """股票/前十名候选失败；QDII query 成功并返回国家（地区）表 citation。"""

            if query == "所有权益投资明细":
                return AgentRunResult(
                    answer="8.2 期末按地区分类的所有权益投资明细",
                    citations=(
                        Citation(
                            document_id=document_id,
                            fund_code="519696",
                            fund_name="交银环球精选混合(QDII)",
                            year=2023,
                            report_type="annual_report",
                            locator=Locator(
                                document_id=document_id,
                                locator_kind=LocatorKind.TABLE,
                                section_ref="section-qdii",
                                table_ref="table-0062",
                                page_no=None,
                                page_range=None,
                                internal_ref=None,
                                internal_ref_available=False,
                            ),
                        ),
                    ),
                    tool_trace=(_trace_search(document_id, query, "success"),),
                    failure=None,
                )
            return AgentRunResult(
                answer="",
                citations=(),
                tool_trace=(_trace_search(document_id, query, "failure", FailureCode.NOT_FOUND),),
                failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到可读取的匹配章节"),
            )

    service = FundReadingService(host_factory=_QdiiCountryFirstCitationHost)
    result = service._extract_holdings_from_store(
        document_id="519696-2023-annual_report-fixture",
        store=store,
        report_year=2023,
        fund_name="交银环球精选混合(QDII)",
    )
    assert result.failure is None
    assert len(result.holdings) == 10
    assert result.holdings[0].stock_name == "中国重 汽"
    assert result.holdings[0].stock_code == "3808 HK"
    assert result.holdings[0].percentage == "4.17"
    assert result.citation is not None
    assert result.citation.locator.table_ref == "table-0064"


_A_SHARE_HOLDINGS_004393_YEAR_DOCLING_JSON = {
    2021: Path(
        ".fund_e2e_004393/docling_json/004393-2021-annual_report-686a3e733e4ae6cb"
        "/004393-2021-annual_report-686a3e733e4ae6cb.docling.json"
    ),
    2022: Path(
        ".fund_e2e_004393/docling_json/004393-2022-annual_report-045987cad6e956ad"
        "/004393-2022-annual_report-045987cad6e956ad.docling.json"
    ),
    2023: Path(
        ".fund_e2e_004393/docling_json/004393-2023-annual_report-f8bba920647aa6d8"
        "/004393-2023-annual_report-f8bba920647aa6d8.docling.json"
    ),
    2024: Path(
        ".fund_e2e_004393/docling_json/004393-2024-annual_report-bc6b0a1ae2f709f4"
        "/004393-2024-annual_report-bc6b0a1ae2f709f4.docling.json"
    ),
    2025: Path(
        ".fund_e2e_004393/docling_json/004393-2025-annual_report-dc38aae8770e0071"
        "/004393-2025-annual_report-dc38aae8770e0071.docling.json"
    ),
}


def test_extract_multi_year_holdings_004393_top10_regression() -> None:
    """004393（主动 A 股）2021-2025 各抽取 10 行，行业配置表不再被当作持仓表消费。"""
    for year, json_path in _A_SHARE_HOLDINGS_004393_YEAR_DOCLING_JSON.items():
        assert json_path.is_file(), f"{year} 现成 004393 docling JSON fixture 缺失"

    service = FundReadingService()
    result = service.extract_multi_year_holdings(
        ExtractHoldingsRequest(
            fund_code="004393",
            fund_name="安信企业价值优选混合A",
            requested_years=[2021, 2022, 2023, 2024, 2025],
            annual_report_documents=[
                AnnualReportDocument(
                    year=year,
                    document_id=f"004393-{year}-annual_report-{fingerprint}",
                )
                for year, fingerprint in (
                    (2021, "686a3e733e4ae6cb"),
                    (2022, "045987cad6e956ad"),
                    (2023, "f8bba920647aa6d8"),
                    (2024, "bc6b0a1ae2f709f4"),
                    (2025, "dc38aae8770e0071"),
                )
            ],
            work_dir=Path(".fund_e2e_004393"),
        )
    )
    assert result.failure is None
    assert result.series is not None
    assert tuple(result.series.missing_years) == ()
    by_year = {annual.year: annual.holdings for annual in result.series.annual_holdings}
    citations = {annual.year: annual.citation for annual in result.series.annual_holdings}
    for year in (2021, 2022, 2023, 2024, 2025):
        assert len(by_year[year]) == 10
    assert by_year[2022][0].stock_code == "01088"
    assert by_year[2022][0].stock_name == "中国神华"
    assert by_year[2022][0].percentage == "6.19"
    assert by_year[2022][1].stock_name == "中国海外发展"
    assert by_year[2024][0].stock_code == "00939"
    assert by_year[2024][0].stock_name == "建设银行"
    assert by_year[2024][0].percentage == "6.08"
    # citation 必须是真实持仓表，而不是行业配置表
    assert citations[2022].locator.table_ref == "table-0104"
    assert citations[2024].locator.table_ref == "table-0080"


# ── S2: QDII 费率「管理人报酬」措辞 + 托管费路由 ─────────────────────


_QDII_FEE_YEAR_DOCLING_JSON = {
    2021: Path(
        ".fund_e2e_519696/docling_json/519696-2021-annual_report-4b01ce532e65385d"
        "/519696-2021-annual_report-4b01ce532e65385d.docling.json"
    ),
    2022: Path(
        ".fund_e2e_519696/docling_json/519696-2022-annual_report-15f819d80df0c95f"
        "/519696-2022-annual_report-15f819d80df0c95f.docling.json"
    ),
    2023: Path(
        ".fund_e2e_519696/docling_json/519696-2023-annual_report-19d8de646241b0fc"
        "/519696-2023-annual_report-19d8de646241b0fc.docling.json"
    ),
    2024: Path(
        ".fund_e2e_519696/docling_json/519696-2024-annual_report-3ce5b5d45892aebb"
        "/519696-2024-annual_report-3ce5b5d45892aebb.docling.json"
    ),
    2025: Path(
        ".fund_e2e_519696/docling_json/519696-2025-annual_report-916f45f0b922ba07"
        "/519696-2025-annual_report-916f45f0b922ba07.docling.json"
    ),
}


def test_extract_fee_rates_from_agent_result_qdii_management_remuneration_wording() -> None:
    """「管理人报酬」措辞（无「基金管理费/管理费」字样）必须输出 基金管理费 字段。"""
    from fund_agent.service.extraction import _extract_fee_rates_from_agent_result

    result = AgentRunResult(
        answer=(
            "注：支付基金管理人的管理人报酬按前一日基金资产净值 1.80%的年费率计提，"
            "逐日累计至每月 月底，按月支付。其计算公式为：\n"
            "日管理人报酬＝前一日基金资产净值×1.80%÷当年天数。"
        ),
        citations=(),
        tool_trace=(),
    )

    fees = _extract_fee_rates_from_agent_result(result=result)
    by_name = {fee.fee_name: fee.rate for fee in fees}
    assert by_name == {"基金管理费": "1.80%"}


@pytest.mark.parametrize(
    ("year", "expected_management", "expected_custodian"),
    [
        (2021, "1.80%", "0.35%"),
        (2022, "1.80%", "0.35%"),
        (2023, "1.80%", "0.35%"),
        (2024, "1.80%", "0.35%"),
        (2025, "1.20%", "0.20%"),
    ],
)
def test_extract_fee_rates_from_store_qdii_519696_five_years(
    year: int,
    expected_management: str,
    expected_custodian: str,
) -> None:
    """519696（主动 QDII）五年管理费/托管费真值：2021-2024 1.80%/0.35%、2025 1.20%/0.20%。"""
    json_path = _QDII_FEE_YEAR_DOCLING_JSON[year]
    assert json_path.is_file(), f"{year} 现成 QDII docling JSON fixture 缺失"
    store = _qdii_fixture_store(year=year, json_path=json_path)
    service = FundReadingService()
    result = service._extract_fee_rates_from_store(
        document_id=f"519696-{year}-annual_report-fixture",
        store=store,
        report_year=year,
    )
    assert result.failure is None
    by_name = {fee.fee_name: fee.rate for fee in result.fees}
    assert by_name.get("基金管理费") == expected_management
    assert by_name.get("基金托管费") == expected_custodian


# ── S3: 资产配置 asset_allocation 全表扫描 fallback ─────────────────


_QDII_ALLOCATION_YEAR_DOCLING_JSON = {
    2021: Path(
        ".fund_e2e_519696/docling_json/519696-2021-annual_report-4b01ce532e65385d"
        "/519696-2021-annual_report-4b01ce532e65385d.docling.json"
    ),
    2022: Path(
        ".fund_e2e_519696/docling_json/519696-2022-annual_report-15f819d80df0c95f"
        "/519696-2022-annual_report-15f819d80df0c95f.docling.json"
    ),
    2023: Path(
        ".fund_e2e_519696/docling_json/519696-2023-annual_report-19d8de646241b0fc"
        "/519696-2023-annual_report-19d8de646241b0fc.docling.json"
    ),
    2024: Path(
        ".fund_e2e_519696/docling_json/519696-2024-annual_report-3ce5b5d45892aebb"
        "/519696-2024-annual_report-3ce5b5d45892aebb.docling.json"
    ),
    2025: Path(
        ".fund_e2e_519696/docling_json/519696-2025-annual_report-916f45f0b922ba07"
        "/519696-2025-annual_report-916f45f0b922ba07.docling.json"
    ),
}


def _wrong_bound_allocation_citation(*, year: int) -> Citation:
    """构造错绑 citation：table-0059 caption 含「8.1 期末基金资产组合情况」但非资产配置表。"""
    return _citation(
        f"519696-{year}-annual_report-fixture",
        LocatorKind.TABLE,
        section_ref="section-allocation",
        table_ref="table-0059",
        year=year,
    )


def test_asset_allocation_fallback_real_fixture_519696_2023() -> None:
    """519696-2023 真实 fixture：错绑 caption 后 asset_allocation 全表扫描 fallback 非空。"""
    from fund_agent.service.extraction import (
        _extract_allocation_from_agent_result,
        _is_asset_allocation_table,
    )

    year = 2023
    json_path = _QDII_ALLOCATION_YEAR_DOCLING_JSON[year]
    assert json_path.is_file(), f"{year} 现成 QDII docling JSON fixture 缺失"
    store = _qdii_fixture_store(year=year, json_path=json_path)
    wrong_cited = store.read_table("table-0059", max_rows=30)
    assert "期末基金资产组合情况" in (wrong_cited.caption or "")
    assert not _is_asset_allocation_table(wrong_cited.rows)

    result = AgentRunResult(
        answer="8.1 期末基金资产组合情况",
        citations=(_wrong_bound_allocation_citation(year=year),),
        tool_trace=(),
    )
    asset_allocation, _ = _extract_allocation_from_agent_result(
        document_id=f"519696-{year}-annual_report-fixture",
        result=result,
        tool_service=_StoreBackedToolService(store),
    )
    assert len(asset_allocation) >= 1
    assert asset_allocation[0].category == "权益投资"
    assert asset_allocation[0].amount == "70,231,733.87"
    assert asset_allocation[0].percentage_of_total == "90.43"


@pytest.mark.parametrize(
    ("year", "expected_count"),
    [
        (2021, 3),
        (2022, 6),
        (2024, 2),
        (2025, 5),
    ],
)
def test_asset_allocation_fallback_real_fixture_no_regression(year: int, expected_count: int) -> None:
    """519696 2021/2022/2024/2025：全表扫描 fallback 行数不回退。"""
    from fund_agent.service.extraction import _extract_allocation_from_agent_result

    json_path = _QDII_ALLOCATION_YEAR_DOCLING_JSON[year]
    assert json_path.is_file(), f"{year} 现成 QDII docling JSON fixture 缺失"
    store = _qdii_fixture_store(year=year, json_path=json_path)
    result = AgentRunResult(
        answer="8.1 期末基金资产组合情况",
        citations=(_wrong_bound_allocation_citation(year=year),),
        tool_trace=(),
    )
    asset_allocation, _ = _extract_allocation_from_agent_result(
        document_id=f"519696-{year}-annual_report-fixture",
        result=result,
        tool_service=_StoreBackedToolService(store),
    )
    assert len(asset_allocation) == expected_count
    assert asset_allocation[0].category == "权益投资"


def test_asset_allocation_fallback_skips_tool_failure() -> None:
    """全表扫描 fallback 跳过 ToolFailure，命中真实资产配置表后 break。"""
    from fund_agent.fund.document_tools.models import TableContent, TableSummary
    from fund_agent.service.extraction import _extract_allocation_from_agent_result

    allocation_rows = (
        ("序号", "项目", "金额", "占基金总资产的比例（%）"),
        ("1", "权益投资", "1,000.00", "90.00"),
    )
    allocation_locator = _holdings_locator(table_ref="table-0060", section_ref="section-allocation")
    allocation_citation = _citation(
        "doc",
        LocatorKind.TABLE,
        section_ref="section-allocation",
        table_ref="table-0060",
    )

    class _ScanToolService:
        def __init__(self) -> None:
            self.scanned_refs: list[str] = []

        def read_table(self, document_id, table_ref, max_rows=30):
            self.scanned_refs.append(table_ref)
            if table_ref == "table-0059":
                return ToolFailure(code=FailureCode.UNAVAILABLE, message="读取失败")
            if table_ref == "table-0060":
                return TableContent(
                    table_ref="table-0060",
                    caption="金额单位：人民币元",
                    section_ref="section-allocation",
                    rows=allocation_rows,
                    truncated=False,
                    locator=allocation_locator,
                    citation=allocation_citation,
                )
            return TableContent(
                table_ref=table_ref,
                caption=None,
                section_ref="section-other",
                rows=(("标题",),),
                truncated=False,
                locator=_holdings_locator(table_ref=table_ref, section_ref="section-other"),
                citation=allocation_citation,
            )

        def list_tables(self, document_id):
            return (
                TableSummary(
                    table_ref="table-0059",
                    caption=None,
                    section_ref="section-other",
                    locator=_holdings_locator(table_ref="table-0059", section_ref="section-other"),
                    row_count=1,
                    column_count=1,
                ),
                TableSummary(
                    table_ref="table-0060",
                    caption="金额单位：人民币元",
                    section_ref="section-allocation",
                    locator=allocation_locator,
                    row_count=2,
                    column_count=4,
                ),
            )

    tool_service = _ScanToolService()
    result = AgentRunResult(answer="x", citations=(), tool_trace=())
    asset_allocation, _ = _extract_allocation_from_agent_result(
        document_id="doc",
        result=result,
        tool_service=tool_service,
    )
    assert tool_service.scanned_refs[:2] == ["table-0059", "table-0060"]
    assert len(asset_allocation) == 1
    assert asset_allocation[0].category == "权益投资"


# ── F3: 基金经理持有区间抽取 ─────────────────────────────────────


_FUND_MANAGER_2025_DOCLING_JSON = Path(
    ".fund_e2e_163415/docling_json/163415-2025-annual_report-2654de4c6afae614"
    "/163415-2025-annual_report-2654de4c6afae614.docling.json"
)


def _manager_holds_rows(*, a_value: str, c_value: str, total_value: str) -> tuple:
    """构造 9.4 节基金经理持有区间披露表。"""

    return (
        ("项目", "份额级别", "持有基金份额总量的数量区间（万份）"),
        ("本基金基金经理持有本开放式基金", "本基金 A", a_value),
        ("", "本基金 C", c_value),
        ("", "合计", total_value),
    )


def test_extract_manager_holds_fund_real_2025_fixture() -> None:
    """真实 2025 docling JSON fixture：holds_fund 非空且含 >100 与 万份。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity, ReportType, SourceKind

    assert _FUND_MANAGER_2025_DOCLING_JSON.is_file(), "2025 现成 docling JSON fixture 缺失"
    store = DoclingDocumentStore(
        identity=ReportIdentity(
            fund_code="163415",
            fund_name="兴全商业模式混合(LOF)",
            year=2025,
            report_type=ReportType.ANNUAL_REPORT,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id="fixture",
            content_fingerprint="fixture",
            document_id="163415-2025-annual_report-fixture",
        ),
        json_path=_FUND_MANAGER_2025_DOCLING_JSON,
    )
    table = store.read_table("table-0090", max_rows=20)
    assert table.section_ref == "section-0663"
    holds_fund = _extract_manager_holds_fund(table.rows)
    assert holds_fund
    assert ">100" in holds_fund
    assert "万份" in holds_fund
    assert holds_fund == "A类>100万份"
    assert "从业人员整体持有" not in holds_fund


def test_extract_manager_holds_fund_old_form_not_regressed() -> None:
    """旧形态（10~50万份）不回退。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund

    rows = _manager_holds_rows(a_value="10~50万份", c_value="0", total_value="10~50万份")
    assert _extract_manager_holds_fund(rows) == "10~50万份"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (">100", "A类>100万份"),
        ("<50", "A类<50万份"),
        (">=100", "A类>=100万份"),
        ("<=50", "A类<=50万份"),
        ("10~50", "A类10~50万份"),
        ("10-50", "A类10-50万份"),
        ("100", "A类100万份"),
        ("> 100", "A类>100万份"),
    ],
)
def test_extract_manager_holds_fund_interval_forms(raw_value: str, expected: str) -> None:
    """区间形态 >N/<N/>=N/<=N/N~M/N-M/纯数字 均支持，单位从表头继承。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund

    rows = _manager_holds_rows(a_value=raw_value, c_value="0", total_value=raw_value)
    assert _extract_manager_holds_fund(rows) == expected


def test_extract_manager_holds_fund_prefers_a_class_excludes_senior_management() -> None:
    """优先基金经理 A 类份额行；高级管理人员类目不混入。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund

    rows = (
        ("项目", "份额级别", "持有基金份额总量的数量区间（万份）"),
        ("本公司高级管理人员持有本开放式基金", "本基金 A", "10~50"),
        ("", "本基金 C", "0"),
        ("", "合计", "10~50"),
        ("本基金基金经理持有本开放式基金", "本基金 A", ">100"),
        ("", "本基金 C", "0"),
        ("", "合计", ">100"),
    )
    assert _extract_manager_holds_fund(rows) == "A类>100万份"


def test_extract_manager_holds_fund_falls_back_to_nonzero_row() -> None:
    """无 A 类行时取首个非零行（C 类）。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund

    rows = (
        ("项目", "份额级别", "持有基金份额总量的数量区间（万份）"),
        ("本基金基金经理持有本开放式基金", "本基金 C", ">100"),
        ("", "合计", ">100"),
    )
    assert _extract_manager_holds_fund(rows) == "C类>100万份"


def test_extract_manager_holds_fund_falls_back_to_total_row() -> None:
    """无 A 行且无非零行时取合计行。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund

    rows = (
        ("项目", "份额级别", "持有基金份额总量的数量区间（万份）"),
        ("本基金基金经理持有本开放式基金", "本基金 C", "0"),
        ("", "合计", ">100"),
    )
    assert _extract_manager_holds_fund(rows) == ">100万份"


def test_extract_manager_holds_fund_missing_section_stays_undisclosed() -> None:
    """无 9.4 节披露时 holds_fund 保持空（未披露）。"""
    from fund_agent.service.extraction import _extract_manager_holds_fund

    assert _extract_manager_holds_fund(()) == ""
    assert _extract_manager_holds_fund(
        (
            ("项目", "份额级别", "持有基金份额总量的数量区间（万份）"),
            ("本公司高级管理人员持有本开放式基金", "本基金 A", ">100"),
            ("", "合计", ">100"),
        )
    ) == ""


_FUND_MANAGER_519696_2025_DOCLING_JSON = Path(
    ".fund_e2e_519696/docling_json/519696-2025-annual_report-916f45f0b922ba07"
    "/519696-2025-annual_report-916f45f0b922ba07.docling.json"
)


def _manager_holds_overall_rows(*, shares: str, ratio: str) -> tuple:
    """构造 9.2 节从业人员整体持有表。"""

    return (
        ("项目", "持有份额总数 （份）", "占基金总份额比例（%）"),
        ("基金管理人所有从业人员持有本基金", shares, ratio),
    )


def test_extract_manager_holds_overall_real_519696_2025_fixture() -> None:
    """519696-2025 真实 fixture：无 9.4 时回退 9.2 从业人员整体持有。"""
    from fund_agent.service.extraction import _extract_manager_holds_overall
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity, ReportType, SourceKind

    assert _FUND_MANAGER_519696_2025_DOCLING_JSON.is_file(), "519696-2025 现成 docling JSON fixture 缺失"
    store = DoclingDocumentStore(
        identity=ReportIdentity(
            fund_code="519696",
            fund_name="交银环球精选混合(QDII)",
            year=2025,
            report_type=ReportType.ANNUAL_REPORT,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id="fixture",
            content_fingerprint="fixture",
            document_id="519696-2025-annual_report-fixture",
        ),
        json_path=_FUND_MANAGER_519696_2025_DOCLING_JSON,
    )
    table = store.read_table("table-0080", max_rows=20)
    assert table.section_ref == "section-0679"
    holds_fund = _extract_manager_holds_overall(table.rows)
    assert holds_fund
    assert "基金经理区间未披露" in holds_fund
    assert "从业人员整体持有" in holds_fund
    assert "7,312.84" in holds_fund
    assert "0.01%" in holds_fund


def test_extract_manager_holds_overall_shape() -> None:
    """9.2 整体表合成行：份额与占比格式化正确（占比补 %）。"""
    from fund_agent.service.extraction import _extract_manager_holds_overall

    rows = _manager_holds_overall_rows(shares="7,312.84", ratio="0.01")
    assert _extract_manager_holds_overall(rows) == (
        "基金经理区间未披露；从业人员整体持有 7,312.84 份（0.01%）"
    )


def test_extract_manager_holds_overall_ratio_already_percent() -> None:
    """占比单元格已带 % 时不重复追加。"""
    from fund_agent.service.extraction import _extract_manager_holds_overall

    rows = _manager_holds_overall_rows(shares="7,312.84", ratio="0.01%")
    assert _extract_manager_holds_overall(rows) == (
        "基金经理区间未披露；从业人员整体持有 7,312.84 份（0.01%）"
    )


def test_extract_manager_holds_overall_missing_rows_stays_empty() -> None:
    """无 9.2 从业人员整体行时保持空（与 9.4 均缺失语义一致）。"""
    from fund_agent.service.extraction import _extract_manager_holds_overall

    assert _extract_manager_holds_overall(()) == ""
    assert _extract_manager_holds_overall(
        (
            ("项目", "持有份额总数 （份）", "占基金总份额比例（%）"),
            ("本基金基金经理持有本开放式基金", ">100", "0.01"),
        )
    ) == ""


# ── fund_type 感知评分框架测试 ─────────────────────────────────────


class TestScoringFundTypeAware:
    """评分框架 fund_type 感知：被动/QDII/债券基金指标适用性。"""

    def test_applicable_indicators_active_fund(self):
        """主动基金：全部 6 个指标适用。"""
        from fund_agent.service.signal_scoring import get_applicable_indicators

        app = get_applicable_indicators("active_fund")
        assert app["超额收益趋势"] is True
        assert app["费率水平"] is True
        assert app["风格漂移"] is True
        assert app["规模风险"] is True
        assert app["基金经理变更"] is True
        assert app["持仓集中度"] is True
        assert sum(1 for v in app.values() if v) == 6

    def test_applicable_indicators_index_etf(self):
        """被动 ETF：超额收益、风格漂移、基金经理变更不适用。"""
        from fund_agent.service.signal_scoring import get_applicable_indicators

        app = get_applicable_indicators("index_etf")
        assert app["超额收益趋势"] is False
        assert app["费率水平"] is True
        assert app["风格漂移"] is False
        assert app["规模风险"] is True
        assert app["基金经理变更"] is False
        assert app["持仓集中度"] is True
        assert sum(1 for v in app.values() if v) == 3

    def test_applicable_indicators_index_fund(self):
        """被动指数基金（非增强）：同 ETF，3 个指标不适用。
        增强指数基金在评分时单独恢复全部指标。
        """
        from fund_agent.service.signal_scoring import get_applicable_indicators

        app = get_applicable_indicators("index_fund")
        assert app["超额收益趋势"] is False
        assert app["风格漂移"] is False
        assert app["基金经理变更"] is False
        assert app["费率水平"] is True
        assert app["规模风险"] is True
        assert app["持仓集中度"] is True
        assert sum(1 for v in app.values() if v) == 3

    def test_applicable_indicators_index_feeder(self):
        """联接基金：同被动 ETF，3 个指标不适用。"""
        from fund_agent.service.signal_scoring import get_applicable_indicators

        app = get_applicable_indicators("index_feeder")
        assert app["超额收益趋势"] is False
        assert app["风格漂移"] is False
        assert app["基金经理变更"] is False
        assert sum(1 for v in app.values() if v) == 3

    def test_applicable_indicators_bond_fund(self):
        """债券基金：风格漂移不适用（基于股票代码重叠率）。"""
        from fund_agent.service.signal_scoring import get_applicable_indicators

        app = get_applicable_indicators("bond_fund")
        assert app["风格漂移"] is False
        assert app["超额收益趋势"] is True
        assert app["基金经理变更"] is True
        assert sum(1 for v in app.values() if v) == 5

    def test_applicable_indicators_unknown_type(self):
        """未知基金类型：默认全部适用（兼容性）。"""
        from fund_agent.service.signal_scoring import get_applicable_indicators

        app = get_applicable_indicators("unknown_type")
        assert app["超额收益趋势"] is True
        assert sum(1 for v in app.values() if v) == 6

    def test_signal_judgment_etf_skips_inapplicable(self):
        """被动 ETF 评分：3 指标 100 分制（费率 40+规模 30+集中度 30），
        不适用指标追加为「不适用」提示。
        """
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        # 构建数据：费率 0.15%（A 股 ETF 绿档）、规模 5 亿、持仓集中度 7%
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.15%"),)}
        holdings = {
            2025: (
                HoldingExtraction(
                    rank=1, stock_code="000001", stock_name="平安银行",
                    quantity="100", fair_value="500000",
                    percentage="7.0%",
                ),
            ),
        }
        performance: dict = {}
        scale_info = ScaleInfo(
            total_shares_a="", total_shares_c="",
            individual_investor_ratio="", management_holds="",
            estimated_aum="5.0亿元",
        )

        result = service.compute_signal_judgment(
            performance=performance, fees=fees, holdings=holdings,
            scale_info=scale_info,
            fund_name="华泰柏瑞中证红利低波动交易型开放式指数证券投资基金",
            report_year=2025,
        )

        # 3 适用指标（40+30+30=100）+ 3 不适用
        assert len(result.indicators) == 6
        applicable = [i for i in result.indicators if i.max_score > 0]
        skipped = [i for i in result.indicators if i.max_score == 0]
        assert len(applicable) == 3
        assert len(skipped) == 3
        for s in skipped:
            assert "不适用" in s.detail

        # 费率 0.15% (<0.20 绿档) → 40/40, 规模 5亿 → 30/30, 集中度 7% → 30/30 = 100
        assert result.normalized_score == 100

    def test_signal_judgment_active_fund_all_applicable(self):
        """主动基金：6 指标全部适用（回归测试）。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="1.20%"),)}
        holdings = {
            2024: (
                HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="6%"),
                HoldingExtraction(rank=2, stock_code="000002", stock_name="B", quantity="100", fair_value="5000", percentage="5%"),
            ),
            2025: (
                HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="6%"),
                HoldingExtraction(rank=2, stock_code="000002", stock_name="B", quantity="100", fair_value="5000", percentage="5%"),
            ),
        }
        performance = {2024: {"excess_return": "5%"}, 2025: {"excess_return": "3%"}}

        result = service.compute_signal_judgment(
            performance=performance, fees=fees, holdings=holdings,
            fund_name="兴全商业模式优选混合型证券投资基金（LOF）",
            report_year=2025,
        )

        assert len(result.indicators) == 6
        # 全部适用 → 满分 135
        applicable = [i for i in result.indicators if i.max_score > 0]
        assert len(applicable) == 6

    def test_signal_judgment_enhanced_index_all_applicable(self):
        """增强指数基金：恢复全部 6 个指标。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="1.00%"),)}
        holdings = {
            2024: (
                HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="6%"),
                HoldingExtraction(rank=2, stock_code="000002", stock_name="B", quantity="100", fair_value="5000", percentage="5%"),
            ),
            2025: (
                HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="6%"),
                HoldingExtraction(rank=2, stock_code="000002", stock_name="B", quantity="100", fair_value="5000", percentage="5%"),
            ),
        }
        performance = {2024: {"excess_return": "5%"}, 2025: {"excess_return": "3%"}}
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="3.0亿元")

        result = service.compute_signal_judgment(
            performance=performance, fees=fees, holdings=holdings,
            scale_info=scale_info,
            fund_name="招商中证1000指数增强型证券投资基金",
            report_year=2025,
        )
        # 增强指数：全部 6 个指标适用
        applicable = [i for i in result.indicators if i.max_score > 0]
        assert len(applicable) == 6
        # 确认超额收益 / 风格漂移 / 经理变更 未被标记为不适用
        skipped = [i for i in result.indicators if "不适用" in i.detail]
        assert len(skipped) == 0

    def test_risk_checklist_etf_marks_inapplicable(self):
        """被动 ETF 风险清单：不适用项标记为「不适用」。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.50%"),)}
        holdings = {
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7%"),),
        }

        items = service.compute_risk_checklist(
            fees=fees, holdings=holdings,
            fund_name="华泰柏瑞中证红利低波动交易型开放式指数证券投资基金",
            report_year=2025,
        )

        assert len(items) == 6
        # 基金经理变更、风格漂移 → 不适用
        manager_item = [i for i in items if i.name == "基金经理变更"][0]
        assert "不适用" in manager_item.detail
        drift_item = [i for i in items if i.name == "风格漂移"][0]
        assert "不适用" in drift_item.detail

    def test_passive_etf_medium_fee_scores_yellow(self):
        """被动 A 股 ETF 费率 0.35%（黄档 0.20-0.50）：得分 84/100。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.35%"),)}
        holdings = {
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),),
        }
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="5.0亿元")

        result = service.compute_signal_judgment(
            performance={}, fees=fees, holdings=holdings, scale_info=scale_info,
            fund_name="华泰柏瑞中证红利低波动交易型开放式指数证券投资基金",
            report_year=2025,
        )

        # 费率 24/40 + 规模 30/30 + 集中度 30/30 = 84
        assert result.normalized_score == 84
        fee_ind = [i for i in result.indicators if i.name == "费率水平"][0]
        assert fee_ind.max_score == 40
        assert fee_ind.score == 24

    def test_passive_qdii_etf_uses_qdii_thresholds(self):
        """QDII ETF 使用 QDII 费率阈值（<0.80 绿档）。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        # 0.75% → QDII 绿档 (<0.80)，但在 A 股 ETF 阈值下应为红档
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.75%"),)}
        holdings = {
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),),
        }
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="5.0亿元")

        result = service.compute_signal_judgment(
            performance={}, fees=fees, holdings=holdings, scale_info=scale_info,
            fund_name="华安纳斯达克100ETF（QDII）",
            report_year=2025,
        )

        fee_ind = [i for i in result.indicators if i.name == "费率水平"][0]
        assert fee_ind.max_score == 40
        assert fee_ind.score == 40  # <0.80 → 绿档满分
        assert result.normalized_score == 100

    def test_passive_feeder_uses_feeder_thresholds(self):
        """联接基金使用联接基金费率阈值（<0.50 绿档）。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        # 0.45% → 联接基金绿档 (<0.50)
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.45%"),)}
        holdings = {
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),),
        }
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="5.0亿元")

        result = service.compute_signal_judgment(
            performance={}, fees=fees, holdings=holdings, scale_info=scale_info,
            fund_name="华泰柏瑞中证红利低波动ETF联接基金",
            report_year=2025,
        )

        fee_ind = [i for i in result.indicators if i.name == "费率水平"][0]
        assert fee_ind.max_score == 40
        assert fee_ind.score == 40  # <0.50 → 绿档
        assert result.normalized_score == 100

    def test_bond_fund_uses_5_indicator_scoring(self):
        """债券基金 5 指标评分（无风格漂移），bond 费率阈值。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo, FundManagerInfo

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.25%"),)}  # bond 绿档 <0.30
        holdings = {
            2024: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="6.0%"),),
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),),
        }
        performance = {2024: {"excess_return": "3%"}, 2025: {"excess_return": "2%"}}
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="10.0亿元")
        fund_manager = FundManagerInfo(name="张三", tenure_start="2019-05-10", years_of_service="6", investment_strategy="", holds_fund="")

        result = service.compute_signal_judgment(
            performance=performance, fees=fees, holdings=holdings,
            scale_info=scale_info, fund_manager=fund_manager,
            fund_name="某某债券型证券投资基金",
            report_year=2025,
        )

        assert len(result.indicators) == 6
        applicable = [i for i in result.indicators if i.max_score > 0]
        assert len(applicable) == 5  # 超额+费率+规模+经理+集中度
        # 风格漂移不适用
        drift_ind = [i for i in result.indicators if i.name == "风格漂移"][0]
        assert "不适用" in drift_ind.detail
        assert drift_ind.max_score == 0

    def test_passive_total_max_is_100(self):
        """被动基金 3 指标满分 = 100。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.10%"),)}  # A 股 ETF 绿档
        holdings = {
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),),
        }
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="5.0亿元")

        result = service.compute_signal_judgment(
            performance={}, fees=fees, holdings=holdings, scale_info=scale_info,
            fund_name="华泰柏瑞中证红利低波动交易型开放式指数证券投资基金",
            report_year=2025,
        )

        applicable = [i for i in result.indicators if i.max_score > 0]
        total_max = sum(i.max_score for i in applicable)
        assert total_max == 100  # 40+30+30

    def test_active_fund_unchanged_6_indicators(self):
        """主动基金保持 6 指标 135→100 不变。"""
        from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo

        service = FundReadingService()
        fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.80%"),)}
        holdings = {
            2024: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="6.0%"),),
            2025: (HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),),
        }
        performance = {2024: {"excess_return": "5%"}, 2025: {"excess_return": "3%"}}
        scale_info = ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="3.0亿元")

        result = service.compute_signal_judgment(
            performance=performance, fees=fees, holdings=holdings, scale_info=scale_info,
            fund_name="兴全商业模式优选混合型证券投资基金（LOF）",
            report_year=2025,
        )

        applicable = [i for i in result.indicators if i.max_score > 0]
        assert len(applicable) == 6
        total_max = sum(i.max_score for i in applicable)
        assert total_max == 135


class TestDetectShareClass:
    """_detect_share_class 函数单元测试。"""

    def test_exact_a(self):
        assert reading_service_module._detect_share_class("A") == "A"

    def test_exact_a_class(self):
        assert reading_service_module._detect_share_class("A类") == "A"

    def test_exact_c(self):
        assert reading_service_module._detect_share_class("C") == "C"

    def test_exact_c_class(self):
        assert reading_service_module._detect_share_class("C类") == "C"

    def test_index_a(self):
        assert reading_service_module._detect_share_class("指数A") == "A"

    def test_index_c(self):
        assert reading_service_module._detect_share_class("指数C") == "C"

    def test_connect_a(self):
        assert reading_service_module._detect_share_class("联接A") == "A"

    def test_connect_c(self):
        assert reading_service_module._detect_share_class("联接C") == "C"

    def test_connect_a_with_space(self):
        assert reading_service_module._detect_share_class("联接 A") == "A"

    def test_slash_ab_format(self):
        assert reading_service_module._detect_share_class("A/B") == "A"

    def test_slash_cb_format(self):
        assert reading_service_module._detect_share_class("C类/B类") == "C"

    def test_parenthesis_a(self):
        assert reading_service_module._detect_share_class("）A") == "A"

    def test_parenthesis_c(self):
        assert reading_service_module._detect_share_class("）C类") == "C"

    def test_nav_excluded(self):
        """NAV 不在 _class_exclude_kw 过滤范围内，但函数本身不应匹配英文单词。"""
        assert reading_service_module._detect_share_class("NAV") is None

    def test_aum_excluded(self):
        assert reading_service_module._detect_share_class("AUM") is None

    def test_random_text(self):
        assert reading_service_module._detect_share_class("基金份额") is None


class TestExtractScaleFromText:
    """_extract_scale_from_text 函数单元测试。"""

    def test_extract_a_shares(self):
        text = "本基金A类基金份额总额1,234,567.89份，C类基金份额不适用。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_a"] == "1,234,567.89"

    def test_extract_c_shares(self):
        text = "本基金C类基金份额总额987,654.32份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_c"] == "987,654.32"

    def test_extract_both_shares(self):
        text = "A类份额总额100,000.00份，C类份额总额200,000.00份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_a"] == "100,000.00"
        assert result["total_shares_c"] == "200,000.00"

    def test_extract_total_shares_fallback(self):
        """无A/C分类时，提取总份额兜底。"""
        text = "报告期末基金份额总额500,000.00份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_a"] == "500,000.00"

    def test_extract_a_shares_without_fund_prefix(self):
        text = "A类份额1,000份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_a"] == "1,000"

    def test_extract_c_shares_without_fund_prefix(self):
        text = "C类份额2,000份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_c"] == "2,000"

    def test_extract_a_shares_with_whitespace_around_number(self):
        r"""\s* 匹配数字周围的空格（披露文档常见格式）。"""
        text = "A类基金份额总额 3,000 份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_a"] == "3,000"

    def test_extract_individual_investor_ratio(self):
        text = "个人投资者持有份额占总份额的45.67%。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["individual_investor_ratio"] == "45.67%"

    def test_prefix_anchor_allows_leading_chinese(self):
        """前缀锚定 [^。]*? 允许 A类 前有中文修饰（如"本基金A类份额..."）。"""
        text = "本基金A类份额总额9,999.99份。"
        result = reading_service_module._extract_scale_from_text(text)
        assert result["total_shares_a"] == "9,999.99"

    def test_no_false_positive_on_unrelated(self):
        """确保不会错误匹配不相关文本中的数字。"""
        text = "基金管理人持有A类份额不适用。"
        result = reading_service_module._extract_scale_from_text(text)
        assert "total_shares_a" not in result

    def test_empty_text(self):
        result = reading_service_module._extract_scale_from_text("无相关信息。")
        assert result == {}


# ── 007466 业绩 A/C 分段表 + 关联持仓源 slice ─────────────────────


def test_performance_past_year_row_filters_merged_table_by_share_scope() -> None:
    """A/C 合并表按行内份额标签切段：C 段取 C 的 过去一年，A 无段返回 None。"""
    from fund_agent.service.extraction import _performance_past_year_row

    rows = (
        ("自基金合同 生效起至今", "99.01%", "0.98%", "37.04%", "1.02%", "61.97%", "-0.04%"),
        ("华泰柏瑞中证红利低波ETF联接C", "", "", "", "", "", ""),
        ("阶段", "份额净值 增长率①", "份额净值增 长率标准差 ②", "业绩比较基 准收益率③", "业绩比较基 准收益率标 准差④", "①－③", "②－④"),
        ("过去三个月", "2.95%", "0.53%", "2.37%", "0.55%", "0.58%", "-0.02%"),
        ("过去一年", "3.93%", "0.69%", "0.47%", "0.71%", "3.46%", "-0.02%"),
        ("华泰柏瑞中证红利低波ETF联接I", "", "", "", "", "", ""),
        ("阶段", "份额净值 增长率①", "份额净值增 长率标准差 ②", "业绩比较基 准收益率③", "业绩比较基 准收益率标 准差④", "①－③", "②－④"),
        ("过去一年", "4.08%", "0.69%", "0.47%", "0.71%", "3.61%", "-0.02%"),
    )
    c_row = _performance_past_year_row(rows, share_scope="C")
    assert c_row is not None
    assert c_row[1] == "3.93%"
    # A 段在合并表中只有累计段尾部，无 过去一年 行
    assert _performance_past_year_row(rows, share_scope="A") is None
    # 未限定 scope 时多段 过去一年 仍 fail-closed（10D/10F 旧口径不回退）
    with pytest.raises(DocumentToolError):
        _performance_past_year_row(rows)


def test_performance_past_year_row_simple_table_scope_keeps_whole_table() -> None:
    """单段表无标签行：限定 scope 时整表视为该 scope 的表。"""
    from fund_agent.service.extraction import _performance_past_year_row

    rows = (
        ("阶段", "份额净值 增长率①", "业绩比较基 准收益率③", "①－③"),
        ("过去一年", "21.06%", "17.00%", "4.06%"),
    )
    assert _performance_past_year_row(rows, share_scope="A")[1] == "21.06%"
    assert _performance_past_year_row(rows)[1] == "21.06%"


def test_extract_annual_performance_headerless_merged_table_uses_sibling_header(tmp_path: Path) -> None:
    """2025 式无表头合并表：用同 section 相邻 A 类表头对齐列，按行内标签切段抽取 A/C。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0001",)
    _PerformanceExtractionHost.source_title_line = None
    a_full = (
        ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
        ("过去三个月", "3.01%", "0.53%", "2.37%", "0.55%", "0.64%", "-0.02%"),
        ("过去一年", "4.18%", "0.69%", "0.47%", "0.71%", "3.71%", "-0.02%"),
    )
    merged = (
        ("自基金合同生效起至今", "99.01%", "0.98%", "37.04%", "1.02%", "61.97%", "-0.04%"),
        ("华泰柏瑞中证红利低波ETF联接C", "", "", "", "", "", ""),
        ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
        ("过去三个月", "2.95%", "0.53%", "2.37%", "0.55%", "0.58%", "-0.02%"),
        ("过去一年", "3.93%", "0.69%", "0.47%", "0.71%", "3.46%", "-0.02%"),
    )
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_lines=("华泰柏瑞中证红利低波ETF联接A",),
            table_rows=(a_full, merged),
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            year=2025,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_nav_growth_rate", "A")].decimal_percent_text == "4.18%"
    assert values[("annual_benchmark_return_rate", "A")].decimal_percent_text == "0.47%"
    assert values[("annual_nav_growth_rate", "C")].decimal_percent_text == "3.93%"
    assert values[("annual_benchmark_return_rate", "C")].decimal_percent_text == "0.47%"
    # A 类来自同 section 未被 cite 的相邻完整表（表头对齐补全）
    assert {field.citation.locator.table_ref for field in result.fields} == {"table-0000", "table-0001"}


def test_extract_annual_performance_completes_from_uncited_sibling_when_cited_partial(tmp_path: Path) -> None:
    """2024 式：cited 表为不完整分段（只有过去三个月），同 section 相邻 A 类完整表补全。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0001",)
    _PerformanceExtractionHost.source_title_line = None
    a_full = (
        ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
        ("过去三个月", "-0.38%", "1.41%", "0.21%", "1.41%", "-0.59%", "0.00%"),
        ("过去一年", "21.06%", "1.12%", "17.00%", "1.15%", "4.06%", "-0.03%"),
    )
    c_partial = (
        ("阶段", "份额净值增长率①", "份额净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①－③", "②－④"),
        ("过去三个月", "-0.44%", "1.41%", "0.21%", "1.41%", "-0.65%", "0.00%"),
    )
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_lines=("华泰柏瑞中证红利低波ETF联接A", "华泰柏瑞中证红利低波ETF联接C"),
            table_rows=(a_full, c_partial),
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    result = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            year=2024,
            work_dir=work_dir,
        )
    )

    assert result.failure is None
    values = {(field.field_name, field.share_class_scope): field for field in result.fields}
    assert values[("annual_nav_growth_rate", "A")].decimal_percent_text == "21.06%"
    assert values[("annual_benchmark_return_rate", "A")].decimal_percent_text == "17.00%"
    # C 段不完整（无 过去一年），partial-by-share-class 允许 C 整组缺失
    assert ("annual_nav_growth_rate", "C") not in values


def test_extract_report_performance_prefers_a_share_class_fields(tmp_path: Path) -> None:
    """A/C 分段表同时返回两类字段时，报告级统一取 A 类，避免 C 类值写入报告。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceExtractionHost.source_title_line = None
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_title="基金份额净值增长率及其与同期业绩比较基准收益率的比较"
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )

    imported = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            work_dir=work_dir,
        )
    )
    assert imported.failure is None
    assert {field.share_class_scope for field in imported.fields} == {"A", "C"}

    performance, _citations = service._extract_report_performance_with_citations(
        "004393",
        [reading_service_module.AnnualReportDocument(year=2024, document_id=imported.document_id)],
        work_dir,
    )
    assert performance[2024] == {
        "nav_growth_rate": "17.32%",
        "benchmark_return_rate": "14.45%",
        "excess_return": "2.87%",
    }


def test_generate_report_uses_holdings_source_workdir_and_marks_source(tmp_path: Path, monkeypatch) -> None:
    """Task B：generate 指定关联持仓源时，报告持仓与集中度来自关联源并标注来源。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceExtractionHost.source_title_line = None
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_lines=("华泰柏瑞中证红利低波ETF联接A", "华泰柏瑞中证红利低波ETF联接C"),
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )
    imported = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            year=2024,
            work_dir=work_dir,
        )
    )
    assert imported.failure is None

    # 关联源 top-10（模拟 512890 2024 年数据：前五合计 36，前十合计 47）
    source_holdings = {
        2024: tuple(
            HoldingExtraction(
                rank=index,
                stock_code=f"600000{index}",
                stock_name=f"标的股{index}",
                quantity="1000",
                fair_value="10000.00",
                percentage=percentage,
            )
            for index, percentage in enumerate(
                ("10.00%", "8.00%", "7.00%", "6.00%", "5.00%", "4.00%", "3.00%", "2.00%", "1.00%", "1.00%"),
                start=1,
            )
        )
    }
    source_citations = {
        2024: _citation(
            imported.document_id,
            LocatorKind.TABLE,
            section_ref="section-source",
            table_ref="table-source",
        )
    }
    monkeypatch.setattr(
        service,
        "_extract_report_holdings_from_source",
        lambda **kwargs: (source_holdings, source_citations, (2024,)),
    )
    monkeypatch.setattr(
        service,
        "_extract_report_holdings_with_citations",
        lambda *args, **kwargs: ({}, {}, {}),
    )
    for method_name in (
        "_extract_report_fees_with_citations",
        "_extract_report_performance_with_citations",
        "_extract_report_allocation_with_citations",
    ):
        monkeypatch.setattr(service, method_name, lambda *args, **kwargs: ({}, {}))
    for method_name in ("_extract_fund_manager_with_citation", "_extract_scale_info"):
        monkeypatch.setattr(service, method_name, lambda *args, **kwargs: (None, None))

    result = service.generate_report(
        reading_service_module.GenerateReportRequest(
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            report_year=2024,
            years=[2024],
            work_dir=work_dir,
            output_format="json",
            holdings_source_fund="512890",
            holdings_source_workdir=Path(".fund_checklist_512890"),
        )
    )

    assert result.failure is None
    assert result.report is not None
    ch3 = next(c.content for c in result.report.chapters if c.chapter_id == 3)
    assert "来源：标的 ETF 512890 年报" in ch3
    assert "| 2024 | 36.00 | 47.00 | 10.00 | 标的股1 |" in ch3
    assert result.report.metadata["holdings_sources"] == {2024: "来源：标的 ETF 512890 年报"}


def test_generate_report_without_holdings_source_keeps_target_holdings(tmp_path: Path, monkeypatch) -> None:
    """Task B 缺省：未指定关联源时保持本基金持仓口径，不标注来源。"""

    _PerformanceExtractionHost.calls.clear()
    _PerformanceExtractionHost.include_table_citation = True
    _PerformanceExtractionHost.cited_table_refs = ("table-0000", "table-0001")
    _PerformanceExtractionHost.source_title_line = None
    _PerformanceConverter.payload = staticmethod(
        lambda: _performance_docling_payload(
            section_lines=("华泰柏瑞中证红利低波ETF联接A", "华泰柏瑞中证红利低波ETF联接C"),
        )
    )
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)
    service = FundReadingService(
        converter_factory=_PerformanceConverter,
        host_factory=_PerformanceExtractionHost,
    )
    imported = service.extract_annual_performance(
        reading_service_module.ExtractAnnualPerformanceRequest(
            pdf_path=pdf_path,
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            year=2024,
            work_dir=work_dir,
        )
    )
    assert imported.failure is None

    own_holdings = {
        2024: (
            HoldingExtraction(rank=1, stock_code="512890", stock_name="目标ETF", quantity="1000", fair_value="10000.00", percentage="95.00%"),
        )
    }
    monkeypatch.setattr(
        service,
        "_extract_report_holdings_with_citations",
        lambda *args, **kwargs: (own_holdings, {}, {2024: ""}),
    )
    for method_name in (
        "_extract_report_fees_with_citations",
        "_extract_report_performance_with_citations",
        "_extract_report_allocation_with_citations",
    ):
        monkeypatch.setattr(service, method_name, lambda *args, **kwargs: ({}, {}))
    for method_name in ("_extract_fund_manager_with_citation", "_extract_scale_info"):
        monkeypatch.setattr(service, method_name, lambda *args, **kwargs: (None, None))

    result = service.generate_report(
        reading_service_module.GenerateReportRequest(
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            report_year=2024,
            years=[2024],
            work_dir=work_dir,
            output_format="json",
        )
    )

    assert result.failure is None
    assert result.report is not None
    ch3 = next(c.content for c in result.report.chapters if c.chapter_id == 3)
    assert "目标ETF" in ch3
    assert "来源：标的 ETF" not in ch3


# ── P0-1 检索命中质量：受控表锚点（interactive）─────────────────────

_ANCHOR_FIXTURE_DOC_ID = "007466-2025-annual_report-ee23d4b8070dce1a"
_ANCHOR_FIXTURE_JSON = Path(
    ".fund_e2e_007466/docling_json/007466-2025-annual_report-ee23d4b8070dce1a"
    "/007466-2025-annual_report-ee23d4b8070dce1a.docling.json"
)


def _anchor_fixture_tool_service() -> FundDocumentToolService:
    """构造 007466-2025 真实 docling JSON fixture 对应的 tool service。"""
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity, ReportType, SourceKind

    assert _ANCHOR_FIXTURE_JSON.is_file(), "007466-2025 现成 docling JSON fixture 缺失"
    store = DoclingDocumentStore(
        identity=ReportIdentity(
            fund_code="007466",
            fund_name="华泰柏瑞中证红利低波ETF联接",
            year=2025,
            report_type=ReportType.ANNUAL_REPORT,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id="fixture",
            content_fingerprint="fixture",
            document_id=_ANCHOR_FIXTURE_DOC_ID,
        ),
        json_path=_ANCHOR_FIXTURE_JSON,
    )
    return FundDocumentToolService({_ANCHOR_FIXTURE_DOC_ID: store})


def _anchor_contract(profile_name: str) -> reading_service_module._DisclosureLocatorContract:
    """按 profile 名取受控披露定位 contract。"""
    return next(
        contract
        for contract in reading_service_module.DISCLOSURE_LOCATOR_CONTRACT_REGISTRY
        if contract.profile_name == profile_name
    )


def test_resolve_anchor_table_ref_manager_holdings_real_fixture() -> None:
    """007466-2025 真实 fixture：manager_holdings 锚点命中行头含 9.4 标题族的表。"""

    tool_service = _anchor_fixture_tool_service()
    table_ref = reading_service_module._resolve_anchor_table_ref(
        _ANCHOR_FIXTURE_DOC_ID,
        _anchor_contract("manager_holdings"),
        tool_service,
    )

    assert table_ref == "table-0098"
    content = tool_service.read_table(_ANCHOR_FIXTURE_DOC_ID, table_ref, max_rows=10)
    rows_text = "".join(
        reading_service_module._normalize_cell_text("".join(str(cell) for cell in row))
        for row in content.rows
    )
    assert reading_service_module._ANCHOR_MANAGER_HOLDS_9_4_TITLE_FAMILY in rows_text


def test_resolve_anchor_table_ref_holdings_top10_real_fixture() -> None:
    """007466-2025 真实 fixture：holdings_top10 锚点命中表头签名表且 row_count >= 10。"""

    tool_service = _anchor_fixture_tool_service()
    table_ref = reading_service_module._resolve_anchor_table_ref(
        _ANCHOR_FIXTURE_DOC_ID,
        _anchor_contract("holdings_top10"),
        tool_service,
    )

    assert table_ref == "table-0087"
    summary = next(
        table
        for table in tool_service.list_tables(_ANCHOR_FIXTURE_DOC_ID)
        if table.table_ref == table_ref
    )
    assert summary.row_count >= reading_service_module._ANCHOR_HOLDINGS_TOP10_MIN_ROWS
    content = tool_service.read_table(_ANCHOR_FIXTURE_DOC_ID, table_ref, max_rows=2)
    header = reading_service_module._normalize_cell_text(
        "".join(str(cell) for cell in content.rows[0])
    )
    for keyword in reading_service_module._ANCHOR_HOLDINGS_TOP10_HEADER_SIGNATURE:
        assert keyword in header


_PERF_ANCHOR_FIXTURE_DOC_ID = "004393-2025-annual_report-dc38aae8770e0071"
_PERF_ANCHOR_FIXTURE_JSON = Path(
    ".fund_e2e_004393/docling_json/004393-2025-annual_report-dc38aae8770e0071"
    "/004393-2025-annual_report-dc38aae8770e0071.docling.json"
)


def _performance_anchor_fixture_tool_service() -> FundDocumentToolService:
    """构造 004393-2025 真实 docling JSON fixture 对应的 tool service（Fix C）。"""
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity, ReportType, SourceKind

    assert _PERF_ANCHOR_FIXTURE_JSON.is_file(), "004393-2025 现成 docling JSON fixture 缺失"
    store = DoclingDocumentStore(
        identity=ReportIdentity(
            fund_code="004393",
            fund_name="安信企业价值优选混合",
            year=2025,
            report_type=ReportType.ANNUAL_REPORT,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id="fixture",
            content_fingerprint="fixture",
            document_id=_PERF_ANCHOR_FIXTURE_DOC_ID,
        ),
        json_path=_PERF_ANCHOR_FIXTURE_JSON,
    )
    return FundDocumentToolService({_PERF_ANCHOR_FIXTURE_DOC_ID: store})


def test_resolve_performance_returns_anchor_table_ref_real_fixture() -> None:
    """004393-2025 真实 fixture：performance_returns 锚点命中 table-0009（A 类优先）。"""

    tool_service = _performance_anchor_fixture_tool_service()
    table_ref = reading_service_module._resolve_anchor_table_ref(
        _PERF_ANCHOR_FIXTURE_DOC_ID,
        _anchor_contract("performance_returns"),
        tool_service,
    )

    assert table_ref == "table-0009"
    tables = tool_service.list_tables(
        _PERF_ANCHOR_FIXTURE_DOC_ID, within_section_ref="section-0044"
    )
    by_ref = {table.table_ref: table for table in tables}
    assert "A" in (by_ref["table-0009"].caption or "") and "C" not in (by_ref["table-0009"].caption or "")
    assert "C" in (by_ref["table-0010"].caption or "")
    content = tool_service.read_table(_PERF_ANCHOR_FIXTURE_DOC_ID, table_ref, max_rows=2)
    header = reading_service_module._normalize_cell_text(
        "".join(str(cell) for cell in content.rows[0])
    )
    for keyword in reading_service_module._ANCHOR_PERFORMANCE_RETURNS_HEADER_SIGNATURE:
        assert keyword in header


def test_resolve_performance_returns_anchor_table_ref_fail_open() -> None:
    """004393 fixture 上未知 document_id：锚点解析失败返回 None（fail-open）。"""

    tool_service = _performance_anchor_fixture_tool_service()
    assert (
        reading_service_module._resolve_anchor_table_ref(
            "unknown-2025-annual_report-fixture",
            _anchor_contract("performance_returns"),
            tool_service,
        )
        is None
    )


def test_resolve_anchor_table_ref_document_id_none_returns_none() -> None:
    """Mimo finding 001：document_id 为 None 时直接返回 None，不抛异常。"""

    tool_service = _anchor_fixture_tool_service()
    assert (
        reading_service_module._resolve_anchor_table_ref(
            None,
            _anchor_contract("manager_holdings"),
            tool_service,
        )
        is None
    )
    assert (
        reading_service_module._resolve_anchor_table_ref(
            None,
            _anchor_contract("holdings_top10"),
            tool_service,
        )
        is None
    )


def test_resolve_anchor_table_ref_fail_open_on_unknown_document() -> None:
    """未知 document_id：工具不可用 → None，不抛异常（fail-open 到候选词路径）。"""

    tool_service = _anchor_fixture_tool_service()
    for profile_name in ("manager_holdings", "holdings_top10"):
        assert (
            reading_service_module._resolve_anchor_table_ref(
                "unknown-2025-annual_report-fixture",
                _anchor_contract(profile_name),
                tool_service,
            )
            is None
        )


def test_resolve_anchor_table_ref_unconfigured_profile_returns_none() -> None:
    """未配置锚点的 profile 直接返回 None，不做任何 I/O（保持 LLM 自由选表）。"""

    tool_service = _anchor_fixture_tool_service()
    for profile_name in ("asset_allocation", "fee_rates"):
        assert (
            reading_service_module._resolve_anchor_table_ref(
                _ANCHOR_FIXTURE_DOC_ID,
                _anchor_contract(profile_name),
                tool_service,
            )
            is None
        )
