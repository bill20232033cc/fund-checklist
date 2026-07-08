"""fund-checklist read CLI 的回归测试。"""

from __future__ import annotations

import io
import importlib
import json
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from fund_agent.agent import AgentRunResult, ToolTraceEntry
from fund_agent.cli.main import (
    CLASSIFIED_FAILURE_EXIT_CODE,
    SUCCESS_EXIT_CODE,
    UNEXPECTED_FAILURE_EXIT_CODE,
    build_parser,
    run_cli,
)
from fund_agent.fund.document_tools.constants import DOCLING_JSON_SUFFIX, FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import Citation, Locator, ToolFailure
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME
from fund_agent.service import ReadLocalReportResult

cli_module = importlib.import_module("fund_agent.cli.main")
service_module = importlib.import_module("fund_agent.service.reading_service")

REAL_SMOKE_PDF = Path("基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf")
REAL_SMOKE_FUND_CODE = "004393"
REAL_SMOKE_FUND_NAME = "安信企业价值优选混合型证券投资基金"
REAL_SMOKE_YEAR = "2024"


def _write_pdf(path: Path) -> None:
    """写入满足 magic bytes 校验的最小 PDF bytes。"""

    path.write_bytes(b"%PDF-1.4\n% minimal test pdf\n")


def _docling_payload() -> dict[str, object]:
    """返回最小 Docling-shaped JSON，用于 CLI store/agent 测试。"""

    return {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 重要提示",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理在本报告期内保持稳定。股票投资明细展示前十名股票投资明细。",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }


class _FakeConverter:
    """替代真实 DoclingConverter 的 CLI 测试转换器。"""

    calls: list[str] = []

    def __init__(self, output_root: Path) -> None:
        """记录输出根目录。"""

        self._output_root = Path(output_root)

    def convert_pdf(self, *, identity, pdf_bytes: bytes) -> object:
        """写入预置 Docling JSON，证明 CLI 已触发转换步骤。"""

        assert pdf_bytes.startswith(b"%PDF-")
        _FakeConverter.calls.append(identity.document_id)
        json_path = self._output_root / identity.document_id / f"{identity.document_id}{DOCLING_JSON_SUFFIX}"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(_docling_payload(), ensure_ascii=False), encoding="utf-8")
        return object()


def _run(args: list[str]) -> tuple[int, str, str]:
    """执行 CLI 并捕获 stdout/stderr。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run_cli(args, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _citation(document_id: str, locator_kind: LocatorKind) -> Citation:
    """构造 CLI 格式化所需的最小 citation。"""

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


def _trace(tool_name: ToolName) -> ToolTraceEntry:
    """构造 CLI 格式化所需的最小工具 trace。"""

    return ToolTraceEntry(
        tool_name=tool_name,
        arguments={"document_id": "doc-1"},
        result_kind="success",
        failure_code=None,
    )


def test_cli_parses_read_command_arguments(tmp_path: Path) -> None:
    """read 子命令必须解析 required 参数与默认 query/work-dir。"""

    pdf_path = tmp_path / "report.pdf"
    args = build_parser().parse_args(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
        ]
    )

    assert args.command == "read"
    assert args.pdf == pdf_path
    assert args.fund_code == "004393"
    assert args.fund_name == "安信企业价值优选混合型证券投资基金"
    assert args.year == 2024
    assert args.query == "基金经理"
    assert args.share_class is None
    assert args.work_dir == Path(".fund_checklist")


def test_cli_happy_path_orchestrates_import_store_service_and_host(monkeypatch, tmp_path: Path) -> None:
    """CLI happy path 必须通过 Service 串起读取链路并格式化输出。"""

    _FakeConverter.calls.clear()
    monkeypatch.setattr(service_module, "DoclingConverter", _FakeConverter)
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(work_dir),
        ]
    )

    combined = stdout + stderr
    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    assert _FakeConverter.calls
    assert "Answer:" in stdout
    assert "基金经理" in stdout
    assert "Citations:" in stdout
    assert "Trace:" in stdout
    assert "search_document success" in stdout
    assert "read_section success" in stdout
    assert (work_dir / CATALOG_FILENAME).is_file()
    assert "raw Docling" not in combined
    assert "schema_name" not in combined
    assert ".docling.json" not in combined
    assert str(work_dir) not in combined
    assert "local_import_id" not in combined


def test_cli_controlled_alias_query_keeps_plain_output(monkeypatch, tmp_path: Path) -> None:
    """CLI 不展示 Service routing metadata，默认 plain text 输出格式不变。"""

    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)

    class _FakeReadingService:
        """替代真实 Service，隔离 CLI 输出格式测试。"""

        def read_local_report(self, request):
            """返回带 routing_trace 的结果，CLI 不应展示该字段。"""

            assert request.query == "前十大持仓"
            return ReadLocalReportResult(
                document_id="doc-1",
                agent_result=AgentRunResult(
                    answer="8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细",
                    citations=(_citation("doc-1", LocatorKind.TABLE),),
                    tool_trace=(_trace(ToolName.SEARCH_DOCUMENT), _trace(ToolName.READ_SECTION)),
                    failure=None,
                ),
                routing_trace=(),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeReadingService)

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--query",
            "前十大持仓",
            "--work-dir",
            str(work_dir),
        ]
    )

    combined = stdout + stderr
    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    assert "Answer:" in stdout
    assert "股票投资明细" in stdout
    assert "Citations:" in stdout
    assert "Trace:" in stdout
    assert "search_document success" in stdout
    assert "read_section success" in stdout
    assert "routing_trace" not in combined
    assert "profile_name" not in combined
    assert "selected_query" not in combined
    assert "selected_index" not in combined
    assert "raw Docling" not in combined
    assert ".docling.json" not in combined
    assert str(work_dir) not in combined


def test_cli_real_pdf_controlled_profile_smokes_keep_plain_output(tmp_path: Path) -> None:
    """真实 CLI smoke 必须应用 target contract 且不展示 routing_trace。"""

    assert REAL_SMOKE_PDF.is_file(), "Slice 10A real-smoke PDF is required"
    success_expectations = (
        ("前十大持仓", ("股票投资明细", "前十名股票投资明细")),
        ("资产配置", ("期末基金资产组合情况", "基金资产组合情况")),
    )
    work_dir = tmp_path / "real-cli-smoke-work"

    for query, expected_evidence in success_expectations:
        exit_code, stdout, stderr = _run(
            [
                "read",
                "--pdf",
                str(REAL_SMOKE_PDF),
                "--fund-code",
                REAL_SMOKE_FUND_CODE,
                "--fund-name",
                REAL_SMOKE_FUND_NAME,
                "--year",
                REAL_SMOKE_YEAR,
                "--query",
                query,
                "--work-dir",
                str(work_dir),
            ]
        )

        combined = stdout + stderr
        assert exit_code == SUCCESS_EXIT_CODE
        assert stderr == ""
        assert "Answer:" in stdout
        assert any(evidence in stdout for evidence in expected_evidence)
        assert "Citations:" in stdout
        assert "- document_id=" in stdout
        assert "Trace:" in stdout
        assert "- search_document success" in stdout
        assert "routing_trace" not in combined
        assert "profile_name" not in combined
        assert "selected_query" not in combined
        assert "selected_index" not in combined
        assert "raw Docling" not in combined
        assert ".docling.json" not in combined
        assert str(work_dir) not in combined

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(REAL_SMOKE_PDF),
            "--fund-code",
            REAL_SMOKE_FUND_CODE,
            "--fund-name",
            REAL_SMOKE_FUND_NAME,
            "--year",
            REAL_SMOKE_YEAR,
            "--query",
            "费用",
            "--work-dir",
            str(work_dir),
        ]
    )
    combined = stdout + stderr
    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    assert "Answer:" in stdout
    assert "基金管理费" in stdout
    assert "基金托管费" in stdout
    assert "销售服务费" in stdout
    assert "Citations:" in stdout
    assert "- document_id=" in stdout
    assert "Trace:" in stdout
    assert "- search_document success" in stdout
    assert "routing_trace" not in combined
    assert "profile_name" not in combined
    assert "selected_query" not in combined
    assert "selected_index" not in combined

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(REAL_SMOKE_PDF),
            "--fund-code",
            REAL_SMOKE_FUND_CODE,
            "--fund-name",
            REAL_SMOKE_FUND_NAME,
            "--year",
            REAL_SMOKE_YEAR,
            "--query",
            "净值增长率",
            "--work-dir",
            str(work_dir),
        ]
    )
    combined = stdout + stderr
    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    assert "Answer:" in stdout
    assert "基金份额净值增长率及其与同期业绩比较基准收益率的比较" in stdout
    assert "Citations:" in stdout
    assert "locator_kind=section" in stdout
    assert "locator_kind=table" in stdout
    assert "Trace:" in stdout
    assert "- search_document success" in stdout
    assert "routing_trace" not in combined
    assert "profile_name" not in combined
    assert "selected_query" not in combined
    assert "selected_index" not in combined
    assert "nav_growth_rate" not in combined
    assert "benchmark_return_rate" not in combined
    assert "decimal_percent_text" not in combined


def test_cli_reuses_existing_docling_json_without_converter(monkeypatch, tmp_path: Path) -> None:
    """Service catalog 已有 completed report 时，CLI 不触发重复 converter。"""

    class _ForbiddenConverter:
        """若被调用则说明未复用既有 JSON。"""

        def __init__(self, output_root: Path) -> None:
            """构造即失败。"""

            raise AssertionError("converter should not run")

    _FakeConverter.calls.clear()
    monkeypatch.setattr(service_module, "DoclingConverter", _FakeConverter)
    pdf_path = tmp_path / "report.pdf"
    work_dir = tmp_path / "work"
    _write_pdf(pdf_path)

    first_exit, _, first_stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(work_dir),
        ]
    )
    assert first_exit == SUCCESS_EXIT_CODE
    assert first_stderr == ""
    assert _FakeConverter.calls

    monkeypatch.setattr(service_module, "DoclingConverter", _ForbiddenConverter)

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(work_dir),
        ]
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    assert "基金经理" in stdout


def test_cli_classified_failure_outputs_code_and_exit_2(tmp_path: Path) -> None:
    """已分类失败必须输出 stable failure code，退出码为 2。"""

    non_pdf = tmp_path / "report.txt"
    non_pdf.write_text("not a pdf", encoding="utf-8")

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(non_pdf),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "failure_code=integrity_error" in stderr


def test_cli_unexpected_exception_returns_exit_1(monkeypatch, tmp_path: Path) -> None:
    """未预期异常必须返回 1 且不输出 traceback。"""

    def _raise_unexpected(*args, **kwargs) -> object:
        """触发未分类异常。"""

        raise RuntimeError("private path /tmp/secret")

    monkeypatch.setattr(cli_module, "FundReadingService", _raise_unexpected)
    pdf_path = tmp_path / "report.pdf"
    _write_pdf(pdf_path)

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )

    assert exit_code == UNEXPECTED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "unexpected_error: CLI 执行失败" in stderr
    assert "Traceback" not in stderr
    assert "private path" not in stderr


def test_cli_main_uses_process_streams(monkeypatch, tmp_path: Path, capsys) -> None:
    """main() 可作为 script entry 调用并返回退出码。"""

    _FakeConverter.calls.clear()
    monkeypatch.setattr(service_module, "DoclingConverter", _FakeConverter)
    pdf_path = tmp_path / "report.pdf"
    _write_pdf(pdf_path)

    exit_code = cli_module.main(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == SUCCESS_EXIT_CODE
    assert "Answer:" in captured.out
    assert captured.err == ""


def test_cli_console_script_entrypoint_targets_main() -> None:
    """打包后的 console script 必须暴露 documented fund-checklist 入口。"""

    scripts = entry_points(group="console_scripts")
    matches = [entry_point for entry_point in scripts if entry_point.name == "fund-checklist"]

    assert matches
    assert matches[0].value == "fund_agent.cli.main:main"


def test_cli_maps_service_agent_failure_to_exit_2(monkeypatch, tmp_path: Path) -> None:
    """Service 返回 Agent ToolFailure 时，CLI 仍输出 classified failure 并返回 2。"""

    class _FailingReadingService:
        """返回可控 Agent failure 的 fake Service。"""

        def read_local_report(self, request) -> object:
            """返回失败 AgentRunResult，不读取 PDF 或 work-dir。"""

            return type(
                "Result",
                (),
                {
                    "agent_result": AgentRunResult(
                        answer="",
                        citations=(),
                        tool_trace=(),
                        failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到可读取的匹配章节"),
                    )
                },
            )()

    monkeypatch.setattr(cli_module, "FundReadingService", _FailingReadingService)
    pdf_path = tmp_path / "report.pdf"
    _write_pdf(pdf_path)

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "failure_code=not_found" in stderr


def test_cli_maps_service_document_error_to_exit_2(monkeypatch, tmp_path: Path) -> None:
    """Service 抛出的已分类 DocumentToolError 必须保持 exit 2。"""

    class _UnavailableReadingService:
        """抛出可控 repository failure 的 fake Service。"""

        def read_local_report(self, request) -> object:
            """抛出稳定分类失败。"""

            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling JSON 暂不可用")

    monkeypatch.setattr(cli_module, "FundReadingService", _UnavailableReadingService)
    pdf_path = tmp_path / "report.pdf"
    _write_pdf(pdf_path)

    exit_code, stdout, stderr = _run(
        [
            "read",
            "--pdf",
            str(pdf_path),
            "--fund-code",
            "004393",
            "--fund-name",
            "安信企业价值优选混合型证券投资基金",
            "--year",
            "2024",
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "failure_code=unavailable" in stderr


def _write_catalog(work_dir: Path, entries: list[dict[str, object]]) -> None:
    """写入包含指定 entries 的测试 catalog。"""

    work_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for entry in entries:
        doc_id = entry["document_id"]
        reports[doc_id] = {
            "schema_version": 1,
            "document_id": doc_id,
            "identity": {
                "fund_code": entry.get("fund_code", "004393"),
                "fund_name": entry.get("fund_name", "安信企业价值优选"),
                "year": entry["year"],
                "report_type": entry.get("report_type", "annual_report"),
                "source_kind": "local_pdf",
                "content_fingerprint": f"fp-{doc_id}",
                "document_id": doc_id,
            },
            "stored_blob_ref": f"blob-{doc_id}",
            "docling_json_ref": f"docling_json:{doc_id}",
        }
    catalog_path = work_dir / CATALOG_FILENAME
    catalog_path.write_text(json.dumps({
        "schema_version": 1,
        "reports": reports,
    }, ensure_ascii=False), encoding="utf-8")


def test_multi_year_parser_accepts_valid_args() -> None:
    """multi-year 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args(["multi-year", "--fund-code", "004393", "--years", "2022,2023,2024"])

    assert args.command == "multi-year"
    assert args.fund_code == "004393"
    assert args.years == "2022,2023,2024"


def test_multi_year_exits_2_when_fewer_than_3_matching_years(tmp_path: Path) -> None:
    """catalog 中匹配年报不足 3 年时必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "not_found" in stderr


def test_multi_year_exits_2_when_catalog_empty(tmp_path: Path) -> None:
    """空 catalog 时 multi-year 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "not_found" in stderr


def test_multi_year_exits_2_when_fund_code_mismatch(tmp_path: Path) -> None:
    """fund_code 不匹配时必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2022", "year": 2022, "fund_code": "999999"},
        {"document_id": "doc-2023", "year": 2023, "fund_code": "999999"},
        {"document_id": "doc-2024", "year": 2024, "fund_code": "999999"},
    ])

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert stdout == ""
    assert "not_found" in stderr


def test_multi_year_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """multi-year 成功时必须输出 JSON 格式的 series。"""

    from fund_agent.fund.document_tools.models import Citation, Locator
    from fund_agent.service import (
        AggregateMultiYearAnnualPerformanceResult,
        MultiYearAnnualPerformanceSeries,
        MultiYearAnnualPerformanceRow,
        AnnualPerformanceFieldCitation,
    )

    _table_locator = Locator(
        document_id="doc-2024",
        locator_kind=LocatorKind.TABLE,
        section_ref=None,
        table_ref="table-0010",
        page_no=6,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
    )
    _table_citation = Citation(
        document_id="doc-2024",
        fund_code="004393",
        fund_name="安信企业价值优选",
        year=2024,
        report_type="annual_report",
        locator=_table_locator,
    )

    fake_series = MultiYearAnnualPerformanceSeries(
        fund_code="004393",
        requested_years=(2022, 2023, 2024),
        covered_years=(2022, 2023, 2024),
        missing_years=(),
        coverage_status="complete",
        coverage_count=3,
        minimum_required_count=3,
        share_class_scope="A",
        rows=(
            MultiYearAnnualPerformanceRow(
                year=2024,
                annual_nav_growth_rate="17.32%",
                annual_benchmark_return_rate="14.45%",
                annual_excess_return="2.87%",
                citations=(
                    AnnualPerformanceFieldCitation(
                        field_name="annual_nav_growth_rate",
                        citation=_table_citation,
                    ),
                ),
            ),
        ),
        citations=(
            AnnualPerformanceFieldCitation(
                field_name="annual_nav_growth_rate",
                citation=_table_citation,
            ),
        ),
    )

    class _FakeService:
        def aggregate_multi_year_annual_performance(self, request):
            return AggregateMultiYearAnnualPerformanceResult(
                series=(fake_series,),
                failure=None,
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2022", "year": 2022, "fund_code": "004393"},
        {"document_id": "doc-2023", "year": 2023, "fund_code": "004393"},
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    output = json.loads(stdout)
    assert "series" in output
    assert len(output["series"]) == 1
    assert output["series"][0]["fund_code"] == "004393"
    assert output["series"][0]["coverage_status"] == "complete"


def test_multi_year_deduplicates_same_year_entries(monkeypatch, tmp_path: Path) -> None:
    """multi-year 必须对同一年份的多条 catalog 记录去重。"""

    from fund_agent.service import (
        AggregateMultiYearAnnualPerformanceResult,
        MultiYearAnnualPerformanceSeries,
        MultiYearAnnualPerformanceRow,
        AnnualPerformanceFieldCitation,
    )

    class _FakeService:
        def aggregate_multi_year_annual_performance(self, request):
            years = [d.year for d in request.annual_report_documents]
            assert len(years) == len(set(years)), f"发现重复年份: {years}"
            return AggregateMultiYearAnnualPerformanceResult(series=(), failure=None)

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2022", "year": 2022, "fund_code": "004393"},
        {"document_id": "doc-2023a", "year": 2023, "fund_code": "004393"},
        {"document_id": "doc-2023b", "year": 2023, "fund_code": "004393"},
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE


def test_import_parser_accepts_valid_args() -> None:
    """import 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "import",
        "--pdf-dir", "/tmp/pdfs",
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2020-2024",
    ])

    assert args.command == "import"
    assert args.pdf_dir == Path("/tmp/pdfs")
    assert args.fund_code == "004393"
    assert args.year_range == "2020-2024"


def test_import_exits_2_when_directory_not_found(tmp_path: Path) -> None:
    """目录不存在时 import 必须返回 exit 2。"""

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(tmp_path / "nonexistent"),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2020-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_import_exits_2_when_no_pdf_files(tmp_path: Path) -> None:
    """目录中无 PDF 文件时 import 必须返回 exit 2。"""

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2020-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_import_exits_2_when_no_matching_years(tmp_path: Path) -> None:
    """目录中 PDF 年份不在范围内时 import 必须返回 exit 2。"""

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "基金2019年年度报告.pdf").write_bytes(b"%PDF-1.4\n")

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2020-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_import_imports_matching_pdfs(monkeypatch, tmp_path: Path) -> None:
    """import 必须导入年份匹配的 PDF 并输出进度。"""

    from fund_agent.service import ImportLocalReportResult
    from fund_agent.fund.document_tools.models import ReportSummary

    class _FakeService:
        def import_local_report(self, request):
            return ImportLocalReportResult(
                document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                report=ReportSummary(
                    document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    year=request.year,
                    report_type="annual_report",
                    source_kind="local_pdf",
                    source_summary="fake",
                    content_fingerprint="fake",
                ),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "安信企业价值优选混合型证券投资基金2022年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "安信企业价值优选混合型证券投资基金2023年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "安信企业价值优选混合型证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "安信企业价值优选混合型证券投资基金2019年年度报告.pdf").write_bytes(b"%PDF-1.4\n")

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2022-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "3 imported" in stdout
    assert "0 failed" in stdout
    assert "2022" in stdout
    assert "2023" in stdout
    assert "2024" in stdout
    assert "2019" not in stdout


def test_import_skips_failed_files_and_continues(monkeypatch, tmp_path: Path) -> None:
    """单文件失败时 import 必须跳过继续处理其余文件。"""

    from fund_agent.service import ImportLocalReportResult
    from fund_agent.fund.document_tools.models import ReportSummary

    call_count = 0

    class _FakeService:
        def import_local_report(self, request):
            nonlocal call_count
            call_count += 1
            if request.year == 2023:
                raise DocumentToolError(FailureCode.DOCLING_CONVERT_FAILED, "Docling conversion 失败")
            return ImportLocalReportResult(
                document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                report=ReportSummary(
                    document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    year=request.year,
                    report_type="annual_report",
                    source_kind="local_pdf",
                    source_summary="fake",
                    content_fingerprint="fake",
                ),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "安信企业价值优选混合型证券投资基金2022年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "安信企业价值优选混合型证券投资基金2023年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "安信企业价值优选混合型证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2022-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert call_count == 3
    assert "2 imported" in stdout
    assert "1 failed" in stdout
    assert "2023" in stdout
    assert "failed" in stdout


def test_import_exits_2_when_all_files_fail(monkeypatch, tmp_path: Path) -> None:
    """所有文件都失败时 import 必须返回 exit 2。"""

    class _FakeService:
        def import_local_report(self, request):
            raise DocumentToolError(FailureCode.DOCLING_CONVERT_FAILED, "Docling conversion 失败")

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "安信企业价值优选混合型证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2024-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "0 imported" in stdout
    assert "1 failed" in stdout


def test_import_year_range_with_comma_format(monkeypatch, tmp_path: Path) -> None:
    """import 必须支持逗号分隔的年份列表格式。"""

    from fund_agent.service import ImportLocalReportResult
    from fund_agent.fund.document_tools.models import ReportSummary

    class _FakeService:
        def import_local_report(self, request):
            return ImportLocalReportResult(
                document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                report=ReportSummary(
                    document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    year=request.year,
                    report_type="annual_report",
                    source_kind="local_pdf",
                    source_summary="fake",
                    content_fingerprint="fake",
                ),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "安信企业价值优选混合型证券投资基金2022年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "安信企业价值优选混合型证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2022,2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "2 imported" in stdout


def test_import_filters_out_wrong_fund_pdfs(monkeypatch, tmp_path: Path) -> None:
    """import 必须过滤掉不属于目标基金的 PDF。"""

    from fund_agent.service import ImportLocalReportResult
    from fund_agent.fund.document_tools.models import ReportSummary

    imported_files: list[str] = []

    class _FakeService:
        def import_local_report(self, request):
            imported_files.append(request.pdf_path.name)
            return ImportLocalReportResult(
                document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                report=ReportSummary(
                    document_id=f"{request.fund_code}-{request.year}-annual_report-fake",
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    year=request.year,
                    report_type="annual_report",
                    source_kind="local_pdf",
                    source_summary="fake",
                    content_fingerprint="fake",
                ),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "安信企业价值优选混合型证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "招商中证白酒指数证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")
    (pdf_dir / "国泰利享中短债债券型证券投资基金2024年年度报告.pdf").write_bytes(b"%PDF-1.4\n")

    exit_code, stdout, stderr = _run([
        "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year-range", "2024-2024",
        "--work-dir", str(tmp_path / "work"),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "1 imported" in stdout
    assert len(imported_files) == 1
    assert "安信企业价值优选" in imported_files[0]
    assert "招商" not in imported_files[0]
    assert "国泰" not in imported_files[0]


def test_extract_keyword_removes_all_stop_words() -> None:
    """_extract_fund_name_keyword 必须去除所有通用后缀。"""

    from fund_agent.cli.main import _extract_fund_name_keyword

    keyword = _extract_fund_name_keyword("安信企业价值优选混合型证券投资基金")
    assert keyword == "安信企业价值优选"


def test_extract_keyword_result_used_for_matching() -> None:
    """_extract_fund_name_keyword 提取的关键词必须能在文件名中匹配。"""

    from fund_agent.cli.main import _extract_fund_name_keyword, _matches_fund_name

    keyword = _extract_fund_name_keyword("国泰利享中短债债券型证券投资基金")
    assert _matches_fund_name("国泰利享中短债债券型证券投资基金2024年年度报告.pdf", keyword)
    assert not _matches_fund_name("安信企业价值优选混合型证券投资基金2024年年度报告.pdf", keyword)


def test_extract_keyword_empty_fund_name_raises() -> None:
    """纯停用词组成的基金名称必须抛出 ValueError。"""

    from fund_agent.cli.main import _extract_fund_name_keyword

    with pytest.raises(ValueError, match="无法提取关键词"):
        _extract_fund_name_keyword("灵活配置混合型证券投资基金")


def test_holdings_parser_accepts_valid_args() -> None:
    """holdings 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "holdings",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
    ])

    assert args.command == "holdings"
    assert args.fund_code == "004393"
    assert args.years == "2022,2023,2024"


def test_holdings_exits_2_when_no_matching_reports(tmp_path: Path) -> None:
    """catalog 中无匹配年报时 holdings 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "holdings",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_holdings_exits_2_when_fund_code_mismatch(tmp_path: Path) -> None:
    """fund_code 不匹配时 holdings 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "999999"},
    ])

    exit_code, stdout, stderr = _run([
        "holdings",
        "--fund-code", "004393",
        "--years", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_holdings_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """holdings 成功时必须输出 JSON 格式的持仓数据。"""

    from fund_agent.service import (
        ExtractHoldingsResult,
        MultiYearHoldingsSeries,
        AnnualHoldingsResult,
        HoldingExtraction,
    )
    from fund_agent.fund.document_tools.models import Citation, Locator

    fake_series = MultiYearHoldingsSeries(
        fund_code="004393",
        requested_years=(2024,),
        covered_years=(2024,),
        missing_years=(),
        annual_holdings=(
            AnnualHoldingsResult(
                document_id="doc-2024",
                year=2024,
                holdings=(
                    HoldingExtraction(
                        rank=1,
                        stock_code="00939",
                        stock_name="建设银行",
                        quantity="3030000",
                        fair_value="18182239.78",
                        percentage="6.08",
                    ),
                ),
                citation=Citation(
                    document_id="doc-2024",
                    fund_code="004393",
                    fund_name="安信企业价值优选",
                    year=2024,
                    report_type="annual_report",
                    locator=Locator(
                        document_id="doc-2024",
                        locator_kind="table",
                        section_ref=None,
                        table_ref="table-0010",
                        page_no=55,
                        page_range=None,
                        internal_ref=None,
                        internal_ref_available=False,
                    ),
                ),
            ),
        ),
    )

    class _FakeService:
        def extract_multi_year_holdings(self, request):
            return ExtractHoldingsResult(series=fake_series, failure=None)

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "holdings",
        "--fund-code", "004393",
        "--years", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    output = json.loads(stdout)
    assert "series" in output
    assert len(output["series"]) == 1
    assert output["series"][0]["fund_code"] == "004393"
    assert len(output["series"][0]["annual_holdings"]) == 1
    assert output["series"][0]["annual_holdings"][0]["holdings"][0]["stock_name"] == "建设银行"
    assert output["series"][0]["annual_holdings"][0]["holdings"][0]["percentage"] == "6.08"


def test_holdings_exits_2_when_service_failure(monkeypatch, tmp_path: Path) -> None:
    """Service 返回 failure 时 holdings 必须返回 exit 2。"""

    from fund_agent.service import ExtractHoldingsResult

    class _FakeService:
        def extract_multi_year_holdings(self, request):
            return ExtractHoldingsResult(
                series=None,
                failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到持仓数据"),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "holdings",
        "--fund-code", "004393",
        "--years", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_holdings_deduplicates_same_year_entries(monkeypatch, tmp_path: Path) -> None:
    """holdings 必须对同一年份的多条 catalog 记录去重。"""

    from fund_agent.service import (
        ExtractHoldingsResult,
        MultiYearHoldingsSeries,
        AnnualHoldingsResult,
    )

    class _FakeService:
        def extract_multi_year_holdings(self, request):
            years = [d.year for d in request.annual_report_documents]
            assert len(years) == len(set(years)), f"发现重复年份: {years}"
            return ExtractHoldingsResult(
                series=MultiYearHoldingsSeries(
                    fund_code="004393",
                    requested_years=tuple(years),
                    covered_years=tuple(years),
                    missing_years=(),
                    annual_holdings=tuple(
                        AnnualHoldingsResult(document_id=f"doc-{y}", year=y, holdings=())
                        for y in years
                    ),
                ),
                failure=None,
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024a", "year": 2024, "fund_code": "004393"},
        {"document_id": "doc-2024b", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "holdings",
        "--fund-code", "004393",
        "--years", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE


def test_holdings_column_indexes_recognizes_standard_header() -> None:
    """_holdings_column_indexes 必须识别标准持仓表头。"""

    from fund_agent.service.reading_service import _holdings_column_indexes

    rows = (
        ("序号", "股票代码", "股票名称", "数量（股）", "公允价值（元）", "占基金资产净值比例（%）"),
        ("1", "00939", "建设银行", "3,030,000", "18,182,239.78", "6.08"),
    )
    indexes = _holdings_column_indexes(rows)
    assert indexes is not None
    assert indexes["stock_code"] == 1
    assert indexes["stock_name"] == 2
    assert indexes["quantity"] == 3
    assert indexes["fair_value"] == 4
    assert indexes["percentage"] == 5


def test_holdings_column_indexes_returns_none_for_non_holdings_header() -> None:
    """_holdings_column_indexes 对非持仓表头必须返回 None。"""

    from fund_agent.service.reading_service import _holdings_column_indexes

    rows = (
        ("项目", "本期", "上期"),
        ("管理费", "100,000", "80,000"),
    )
    indexes = _holdings_column_indexes(rows)
    assert indexes is None


def test_holdings_column_indexes_returns_none_for_empty_rows() -> None:
    """_holdings_column_indexes 对空行必须返回 None。"""

    from fund_agent.service.reading_service import _holdings_column_indexes

    indexes = _holdings_column_indexes(())
    assert indexes is None


def test_is_continuation_row_recognizes_numbered_rows() -> None:
    """_is_continuation_row 必须识别以序号开头的续表行。"""

    from fund_agent.service.reading_service import _is_continuation_row

    rows = (
        ("5", "00688", "中国海外发展", "237,000", "3,054,626.09", "6.17"),
        ("6", "600519", "贵州茅台", "1,553", "2,682,031.00", "5.42"),
    )
    assert _is_continuation_row(rows) is True


def test_is_continuation_row_rejects_non_numbered_rows() -> None:
    """_is_continuation_row 对非序号行必须返回 False。"""

    from fund_agent.service.reading_service import _is_continuation_row

    rows = (
        ("项目", "本期", "上期"),
        ("管理费", "100,000", "80,000"),
    )
    assert _is_continuation_row(rows) is False


def test_is_continuation_row_rejects_empty_rows() -> None:
    """_is_continuation_row 对空行必须返回 False。"""

    from fund_agent.service.reading_service import _is_continuation_row

    assert _is_continuation_row(()) is False
    assert _is_continuation_row(((),)) is False
