"""FundReadingService use case 边界测试。"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

import fund_agent.service.reading_service as reading_service_module
from fund_agent.agent import AgentRunResult, ToolTraceEntry
from fund_agent.fund.document_tools.constants import DOCLING_JSON_SUFFIX, FailureCode, ToolName
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import ToolFailure
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME
from fund_agent.service import (
    FundReadingService,
    ImportLocalReportRequest,
    ListReportsRequest,
    QueryRouteAttempt,
    ReadLocalReportRequest,
)


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

    def __init__(self, tool_service) -> None:
        """保存 tool service 但不访问其内部 store。"""

        self._tool_service = tool_service

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """记录 Host 调用，并只在指定 candidate 上返回成功。"""

        _RoutingHost.calls.append({"document_id": document_id, "query": query})
        if query == _RoutingHost.success_query:
            return AgentRunResult(
                answer=f"命中 {query}",
                citations=(),
                tool_trace=(_trace_search(document_id, query, "success"),),
                failure=None,
            )
        return AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(_trace_search(document_id, query, "failure", FailureCode.NOT_FOUND),),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到可读取的匹配章节"),
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
        ("费用", ("费用", "基金费用", "报告期内基金费用")),
        ("管理费", ("管理费", "基金费用", "报告期内基金费用")),
        ("托管费", ("托管费", "基金费用", "报告期内基金费用")),
        ("股票投资明细", ("股票投资明细",)),
    ],
)
def test_controlled_query_profiles_generate_bounded_candidates(query: str, expected: tuple[str, ...]) -> None:
    """Service 层 profile 只为三类 exact alias 生成最多 3 个候选。"""

    candidates = reading_service_module._candidate_queries_for_query(query)

    assert candidates == expected
    assert query in candidates
    assert len(candidates) <= 3


def test_read_local_report_routes_controlled_alias_to_first_successful_candidate(tmp_path: Path) -> None:
    """受控 alias 命中时，Service 必须按候选顺序返回第一个成功 Agent result。"""

    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "股票投资明细"
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
    assert result.agent_result.answer == "命中 股票投资明细"
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


def test_read_local_report_records_non_profile_query_only_once(tmp_path: Path) -> None:
    """非受控 query 不走 fallback，routing_trace 只记录原始 query。"""

    _FakeConverter.calls.clear()
    _RoutingHost.calls.clear()
    _RoutingHost.success_query = "股票投资明细"
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
            fallback_candidates=("a", "b", "c"),
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
