"""FundReadingService use case 边界测试。"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

import fund_agent.service.reading_service as reading_service_module
from fund_agent.agent import AgentRunResult, ToolTraceEntry
from fund_agent.fund.document_tools.constants import DOCLING_JSON_SUFFIX, FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import Citation, Locator, ToolFailure
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME
from fund_agent.service import (
    ExtractFeeRatesRequest,
    FundReadingService,
    ImportLocalReportRequest,
    ListReportsRequest,
    QueryRouteAttempt,
    ReadLocalReportRequest,
)

REAL_SMOKE_PDF = Path("基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf")
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
            citations=(_citation(document_id, LocatorKind.SECTION),),
            tool_trace=(_trace_search(document_id, query, "success"),),
            failure=None,
        )


class _FeeRatesValueHost:
    """按 10C fee_rates 字段抽取口径返回安全章节原文。"""

    calls: list[dict[str, str]] = []
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
            citations=(_citation(document_id, LocatorKind.SECTION),),
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


def _citation(document_id: str, locator_kind: LocatorKind) -> Citation:
    """构造不含本地路径的最小 citation。"""

    return Citation(
        document_id=document_id,
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type="annual_report",
        locator=Locator(
            document_id=document_id,
            locator_kind=locator_kind,
            section_ref="section-1",
            table_ref="table-1" if locator_kind is LocatorKind.TABLE else None,
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
        ("股票投资明细", ("股票投资明细",)),
    ],
)
def test_controlled_query_profiles_generate_bounded_candidates(query: str, expected: tuple[str, ...]) -> None:
    """Service 层 profile 只为裁决内 exact alias 生成受控候选。"""

    candidates = reading_service_module._candidate_queries_for_query(query)

    assert candidates == expected
    assert query in candidates
    assert len(candidates) <= 4


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
        reading_service_module._ControlledQueryProfile(
            name="bad",
            aliases=("前十大持仓",),
            fallback_candidates=("a", "b", "c", "d"),
            disclosure_target=reading_service_module._ControlledDisclosureTarget(
                target_id="bad",
                allowed_evidence_kinds=(LocatorKind.SECTION,),
                acceptable_title_family=("bad",),
                expected_citation_kinds=(LocatorKind.SECTION,),
            ),
        ),
    )
    monkeypatch.setattr(reading_service_module, "CONTROLLED_QUERY_PROFILES", bad_profiles)

    with pytest.raises(DocumentToolError) as exc_info:
        reading_service_module._candidate_queries_for_query("前十大持仓")

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
