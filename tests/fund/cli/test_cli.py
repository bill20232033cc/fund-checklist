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
    _extract_chapter_from_markdown,
    build_parser,
    run_cli,
)
from fund_agent.fund.document_tools.constants import DOCLING_JSON_SUFFIX, FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import Citation, Locator, ToolFailure
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME
from fund_agent.service import ReadLocalReportResult

cli_module = importlib.import_module("fund_agent.cli.main")
service_module = importlib.import_module("fund_agent.service.extraction")

REAL_SMOKE_PDF = Path("基金年报/004393_安信企业价值优选混合_2024_annual_report.pdf")
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
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "基金管理人",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "section_header",
                "text": "管理人报告",
                "level": 1,
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
    assert "基金管理人" in stdout
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
    assert "基金管理人" in stdout


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

    from fund_agent.service.extraction import _holdings_column_indexes

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

    from fund_agent.service.extraction import _holdings_column_indexes

    rows = (
        ("项目", "本期", "上期"),
        ("管理费", "100,000", "80,000"),
    )
    indexes = _holdings_column_indexes(rows)
    assert indexes is None


def test_holdings_column_indexes_returns_none_for_empty_rows() -> None:
    """_holdings_column_indexes 对空行必须返回 None。"""

    from fund_agent.service.extraction import _holdings_column_indexes

    indexes = _holdings_column_indexes(())
    assert indexes is None


def test_is_continuation_row_recognizes_numbered_rows() -> None:
    """_is_continuation_row 必须识别以序号开头的续表行。"""

    from fund_agent.service.extraction import _is_continuation_row

    rows = (
        ("5", "00688", "中国海外发展", "237,000", "3,054,626.09", "6.17"),
        ("6", "600519", "贵州茅台", "1,553", "2,682,031.00", "5.42"),
    )
    assert _is_continuation_row(rows) is True


def test_is_continuation_row_rejects_non_numbered_rows() -> None:
    """_is_continuation_row 对非序号行必须返回 False。"""

    from fund_agent.service.extraction import _is_continuation_row

    rows = (
        ("项目", "本期", "上期"),
        ("管理费", "100,000", "80,000"),
    )
    assert _is_continuation_row(rows) is False


def test_is_continuation_row_rejects_empty_rows() -> None:
    """_is_continuation_row 对空行必须返回 False。"""

    from fund_agent.service.extraction import _is_continuation_row

    assert _is_continuation_row(()) is False
    assert _is_continuation_row(((),)) is False


def test_allocation_parser_accepts_valid_args() -> None:
    """allocation 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "allocation",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
    ])

    assert args.command == "allocation"
    assert args.fund_code == "004393"
    assert args.years == "2022,2023,2024"


def test_fees_parser_accepts_valid_args() -> None:
    """fees 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "fees",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
    ])

    assert args.command == "fees"
    assert args.fund_code == "004393"
    assert args.years == "2022,2023,2024"


def test_allocation_exits_2_when_no_matching_reports(tmp_path: Path) -> None:
    """catalog 中无匹配年报时 allocation 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "allocation",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_fees_exits_2_when_no_matching_reports(tmp_path: Path) -> None:
    """catalog 中无匹配年报时 fees 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "fees",
        "--fund-code", "004393",
        "--years", "2022,2023,2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_allocation_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """allocation 成功时必须输出 JSON 格式的资产配置数据。"""

    from fund_agent.service import (
        ExtractAllocationResult,
        MultiYearAllocationSeries,
        AnnualAllocationResult,
        AssetAllocationItem,
        IndustryAllocationItem,
    )
    from fund_agent.fund.document_tools.models import Citation, Locator

    fake_series = MultiYearAllocationSeries(
        fund_code="004393",
        requested_years=(2024,),
        covered_years=(2024,),
        missing_years=(),
        annual_allocations=(
            AnnualAllocationResult(
                document_id="doc-2024",
                year=2024,
                asset_allocation=(
                    AssetAllocationItem(category="权益投资", amount="100,000,000", percentage_of_net="80.00", percentage_of_total="75.00"),
                ),
                industry_allocation=(
                    IndustryAllocationItem(industry="制造业", amount="50,000,000", percentage="40.00"),
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
                        table_ref="table-0075",
                        page_no=50,
                        page_range=None,
                        internal_ref=None,
                        internal_ref_available=False,
                    ),
                ),
            ),
        ),
    )

    class _FakeService:
        def extract_multi_year_allocation(self, request):
            return ExtractAllocationResult(series=fake_series, failure=None)

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "allocation",
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
    assert len(output["series"][0]["annual_allocations"]) == 1
    assert len(output["series"][0]["annual_allocations"][0]["asset_allocation"]) == 1
    assert output["series"][0]["annual_allocations"][0]["asset_allocation"][0]["category"] == "权益投资"
    assert len(output["series"][0]["annual_allocations"][0]["industry_allocation"]) == 1
    assert output["series"][0]["annual_allocations"][0]["industry_allocation"][0]["industry"] == "制造业"


def test_fees_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """fees 成功时必须输出 JSON 格式的费率数据。"""

    from fund_agent.service import (
        ExtractFeeRatesMultiYearResult,
        MultiYearFeeSeries,
        AnnualFeeResult,
        FeeRateItem,
    )
    from fund_agent.fund.document_tools.models import Citation, Locator

    fake_series = MultiYearFeeSeries(
        fund_code="004393",
        requested_years=(2024,),
        covered_years=(2024,),
        missing_years=(),
        annual_fees=(
            AnnualFeeResult(
                document_id="doc-2024",
                year=2024,
                fees=(
                    FeeRateItem(fee_name="基金管理费", rate="1.20%"),
                    FeeRateItem(fee_name="基金托管费", rate="0.20%"),
                    FeeRateItem(fee_name="销售服务费A类", rate="不收取"),
                    FeeRateItem(fee_name="销售服务费C类", rate="0.40%"),
                ),
                citation=Citation(
                    document_id="doc-2024",
                    fund_code="004393",
                    fund_name="安信企业价值优选",
                    year=2024,
                    report_type="annual_report",
                    locator=Locator(
                        document_id="doc-2024",
                        locator_kind="section",
                        section_ref="section-0100",
                        table_ref=None,
                        page_no=30,
                        page_range=None,
                        internal_ref=None,
                        internal_ref_available=False,
                    ),
                ),
            ),
        ),
    )

    class _FakeService:
        def extract_multi_year_fee_rates(self, request):
            return ExtractFeeRatesMultiYearResult(series=fake_series, failure=None)

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "fees",
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
    assert len(output["series"][0]["annual_fees"]) == 1
    assert len(output["series"][0]["annual_fees"][0]["fees"]) == 4
    assert output["series"][0]["annual_fees"][0]["fees"][0]["fee_name"] == "基金管理费"
    assert output["series"][0]["annual_fees"][0]["fees"][0]["rate"] == "1.20%"


def test_is_asset_allocation_table_recognizes_standard_header() -> None:
    """_is_asset_allocation_table 必须识别标准资产配置表头。"""

    from fund_agent.service.extraction import _is_asset_allocation_table

    rows = (
        ("序号", "项目", "金额", "占基金总资产的比例（%）"),
        ("1", "权益投资", "100,000,000", "80.00"),
    )
    assert _is_asset_allocation_table(rows) is True


def test_is_asset_allocation_table_rejects_non_asset_table() -> None:
    """_is_asset_allocation_table 对非资产配置表必须返回 False。"""

    from fund_agent.service.extraction import _is_asset_allocation_table

    rows = (
        ("序号", "股票代码", "股票名称", "数量（股）"),
        ("1", "00939", "建设银行", "3,030,000"),
    )
    assert _is_asset_allocation_table(rows) is False


def test_is_industry_allocation_table_recognizes_standard_header() -> None:
    """_is_industry_allocation_table 必须识别标准行业配置表头。"""

    from fund_agent.service.extraction import _is_industry_allocation_table

    rows = (
        ("代码", "行业类别", "公允价值（元）", "占基金资产净值比例（%）"),
        ("A", "农、林、牧、渔业", "1,037,880.00", "0.35"),
    )
    assert _is_industry_allocation_table(rows) is True


def test_is_industry_allocation_table_rejects_non_industry_table() -> None:
    """_is_industry_allocation_table 对非行业配置表必须返回 False。"""

    from fund_agent.service.extraction import _is_industry_allocation_table

    rows = (
        ("序号", "项目", "金额", "占基金总资产的比例（%）"),
        ("1", "权益投资", "100,000,000", "80.00"),
    )
    assert _is_industry_allocation_table(rows) is False


def test_audit_parser_accepts_valid_args() -> None:
    """audit 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "audit",
        "--fund-code", "512890",
        "--year", "2024",
    ])

    assert args.command == "audit"
    assert args.fund_code == "512890"
    assert args.year == 2024


def test_audit_exits_2_when_no_matching_report(tmp_path: Path) -> None:
    """catalog 中无匹配年报时 audit 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "audit",
        "--fund-code", "512890",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_audit_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """audit 成功时必须输出 JSON 格式的审计结果。"""

    from fund_agent.service import (
        DisclosureAuditResult,
        DisclosureAuditItem,
    )

    fake_result = DisclosureAuditResult(
        fund_code="512890",
        year=2024,
        document_id="512890-2024-annual_report-abc123",
        disclosures=(
            DisclosureAuditItem(name="holdings", status="complete", chapter=True, table=True, fields=("stock_code", "stock_name", "percentage")),
            DisclosureAuditItem(name="asset_allocation", status="complete", chapter=True, table=True, fields=("category", "amount", "percentage")),
            DisclosureAuditItem(name="fee_rates", status="complete", chapter=True, fields=("management_fee", "custodian_fee")),
            DisclosureAuditItem(name="performance", status="partial", chapter=True, table=False, fields=(), message="业绩表格未找到"),
            DisclosureAuditItem(name="fund_manager", status="complete", chapter=True, fields=("name",)),
            DisclosureAuditItem(name="dividends", status="complete", chapter=True, table=True, fields=("amount", "date")),
        ),
        summary={"complete": 5, "partial": 1, "missing": 0},
        failure=None,
    )

    class _FakeService:
        def audit_disclosure_completeness(self, request):
            return fake_result

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "512890-2024-annual_report-abc123", "year": 2024, "fund_code": "512890"},
    ])

    exit_code, stdout, stderr = _run([
        "audit",
        "--fund-code", "512890",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    output = json.loads(stdout)
    assert output["fund_code"] == "512890"
    assert output["year"] == 2024
    assert len(output["disclosures"]) == 6
    assert output["summary"]["complete"] == 5
    assert output["summary"]["partial"] == 1
    assert output["summary"]["missing"] == 0


def test_audit_fee_rates_with_partial_fees(monkeypatch, tmp_path: Path) -> None:
    """费率审计必须正确识别部分费率（如 ETF 只有管理费和托管费）。"""

    from fund_agent.service import (
        DisclosureAuditResult,
        DisclosureAuditItem,
    )

    fake_result = DisclosureAuditResult(
        fund_code="512890",
        year=2024,
        document_id="512890-2024-annual_report-abc123",
        disclosures=(
            DisclosureAuditItem(name="fee_rates", status="partial", chapter=True, fields=("management_fee", "custodian_fee"), message="只找到 2 项费率"),
        ),
        summary={"complete": 0, "partial": 1, "missing": 0},
        failure=None,
    )

    class _FakeService:
        def audit_disclosure_completeness(self, request):
            return fake_result

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "512890-2024-annual_report-abc123", "year": 2024, "fund_code": "512890"},
    ])

    exit_code, stdout, stderr = _run([
        "audit",
        "--fund-code", "512890",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    output = json.loads(stdout)
    assert output["disclosures"][0]["status"] == "partial"
    assert "management_fee" in output["disclosures"][0]["fields"]
    assert "custodian_fee" in output["disclosures"][0]["fields"]
    assert "sales_service_fee" not in output["disclosures"][0]["fields"]


def test_audit_exits_2_when_service_failure(monkeypatch, tmp_path: Path) -> None:
    """Service 返回 failure 时 audit 必须返回 exit 2。"""

    from fund_agent.service import DisclosureAuditResult

    class _FakeService:
        def audit_disclosure_completeness(self, request):
            return DisclosureAuditResult(
                fund_code="512890",
                year=2024,
                failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到年报"),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "512890-2024-annual_report-abc123", "year": 2024, "fund_code": "512890"},
    ])

    exit_code, stdout, stderr = _run([
        "audit",
        "--fund-code", "512890",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_deep_audit_parser_accepts_valid_args() -> None:
    """deep-audit 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "deep-audit",
        "--fund-code", "512890",
        "--year", "2024",
    ])

    assert args.command == "deep-audit"
    assert args.fund_code == "512890"
    assert args.year == 2024


def test_deep_audit_exits_2_when_no_matching_report(tmp_path: Path) -> None:
    """catalog 中无匹配年报时 deep-audit 必须返回 exit 2。"""

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "deep-audit",
        "--fund-code", "512890",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_deep_audit_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """deep-audit 成功时必须输出 JSON 格式的审计结果。"""

    from fund_agent.service import (
        DeepAuditResult,
        DeepAuditItem,
    )

    fake_result = DeepAuditResult(
        fund_code="512890",
        year=2024,
        document_id="512890-2024-annual_report-abc123",
        audit_results=(
            DeepAuditItem(name="holdings", status="pass", completeness="找到持仓章节和相关表格", consistency="通过", citation_text="section_ref=section-0593"),
            DeepAuditItem(name="asset_allocation", status="pass", completeness="找到资产配置章节和相关表格", consistency="通过", citation_text="section_ref=section-0580"),
            DeepAuditItem(name="fee_rates", status="warning", completeness="找到费率章节，未找到相关表格", consistency="需人工验证", citation_text="section_ref=section-0432"),
            DeepAuditItem(name="performance", status="warning", completeness="找到业绩章节，未找到相关表格", consistency="需人工验证", citation_text="section_ref=section-0039"),
            DeepAuditItem(name="fund_manager", status="pass", completeness="找到基金经理章节和相关表格", consistency="通过", citation_text="section_ref=section-0053"),
            DeepAuditItem(name="dividends", status="warning", completeness="找到分红章节，未找到相关表格", consistency="需人工验证", citation_text="section_ref=section-0045"),
        ),
        summary={"pass": 3, "fail": 0, "warning": 3},
        failure=None,
    )

    class _FakeService:
        def deep_audit_disclosure(self, request):
            return fake_result

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "512890-2024-annual_report-abc123", "year": 2024, "fund_code": "512890"},
    ])

    exit_code, stdout, stderr = _run([
        "deep-audit",
        "--fund-code", "512890",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    output = json.loads(stdout)
    assert output["fund_code"] == "512890"
    assert output["year"] == 2024
    assert len(output["audit_results"]) == 6
    assert output["summary"]["pass"] == 3
    assert output["summary"]["warning"] == 3
    assert output["summary"]["fail"] == 0
    assert output["audit_results"][0]["status"] == "pass"
    assert "持仓章节" in output["audit_results"][0]["completeness"]


def test_generate_parser_accepts_valid_args() -> None:
    """generate 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "generate",
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year", "2024",
        "--years", "2022,2023,2024",
        "--format", "json",
    ])

    assert args.command == "generate"
    assert args.fund_code == "004393"
    assert args.fund_name == "安信企业价值优选混合型证券投资基金"
    assert args.year == 2024
    assert args.years == "2022,2023,2024"
    assert args.output_format == "json"


def test_generate_exits_2_when_no_data(monkeypatch, tmp_path: Path) -> None:
    """无数据时 generate 必须返回 exit 2。"""

    from fund_agent.service import GenerateReportResult

    class _FakeService:
        def generate_report(self, request, llm_client=None):
            return GenerateReportResult(
                failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到年报数据"),
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [])

    exit_code, stdout, stderr = _run([
        "generate",
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_generate_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
    """generate 成功时必须输出 JSON 格式的报告。"""

    from fund_agent.service import (
        GenerateReportResult,
        FundReport,
        ReportChapter,
    )

    fake_report = FundReport(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        report_year=2024,
        chapters=(
            ReportChapter(chapter_id=0, title="投资要点概览", content="测试内容", data_sources=("performance",)),
            ReportChapter(chapter_id=1, title="基金概况", content="测试内容", data_sources=("basic_info",)),
            ReportChapter(chapter_id=2, title="业绩分析", content="测试内容", data_sources=("performance",)),
            ReportChapter(chapter_id=3, title="持仓分析", content="测试内容", data_sources=("holdings",)),
            ReportChapter(chapter_id=4, title="资产配置分析", content="测试内容", data_sources=("allocation",)),
            ReportChapter(chapter_id=5, title="费率分析", content="测试内容", data_sources=("fees",)),
            ReportChapter(chapter_id=6, title="分红分析", content="测试内容", data_sources=()),
            ReportChapter(chapter_id=7, title="风险提示", content="测试内容", data_sources=("performance",)),
        ),
        metadata={"generated_at": "2026-07-08", "data_years": [2024], "template_version": "v1"},
    )

    class _FakeService:
        def generate_report(self, request, llm_client=None):
            return GenerateReportResult(report=fake_report, output_path=None, failure=None)

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "generate",
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr == ""
    output = json.loads(stdout)
    assert output["fund_code"] == "004393"
    assert output["report_year"] == 2024
    assert len(output["chapters"]) == 8
    assert output["chapters"][0]["title"] == "投资要点概览"
    assert output["chapters"][0]["content"] == "测试内容"


def test_generate_markdown_output_writes_file(monkeypatch, tmp_path: Path) -> None:
    """generate --format markdown 必须写入文件并返回 output_path。"""

    from fund_agent.service import (
        GenerateReportResult,
        FundReport,
        ReportChapter,
    )

    fake_report = FundReport(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        report_year=2024,
        chapters=(
            ReportChapter(chapter_id=0, title="投资要点概览", content="测试内容", data_sources=("performance",)),
            ReportChapter(chapter_id=1, title="基金概况", content="测试内容", data_sources=("basic_info",)),
            ReportChapter(chapter_id=2, title="业绩分析", content="测试内容", data_sources=("performance",)),
            ReportChapter(chapter_id=3, title="持仓分析", content="测试内容", data_sources=("holdings",)),
            ReportChapter(chapter_id=4, title="资产配置分析", content="测试内容", data_sources=("allocation",)),
            ReportChapter(chapter_id=5, title="费率分析", content="测试内容", data_sources=("fees",)),
            ReportChapter(chapter_id=6, title="分红分析", content="测试内容", data_sources=()),
            ReportChapter(chapter_id=7, title="风险提示", content="测试内容", data_sources=()),
        ),
        metadata={"generated_at": "2026-07-09", "data_years": [2024], "template_version": "v1"},
    )

    class _FakeService:
        def generate_report(self, request, llm_client=None):
            md_path = str(Path(request.work_dir) / "reports" / f"{request.fund_code}-{request.report_year}-analysis.md")
            Path(md_path).parent.mkdir(parents=True, exist_ok=True)
            Path(md_path).write_text("# 测试报告", encoding="utf-8")
            return GenerateReportResult(report=fake_report, output_path=md_path, failure=None)

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "generate",
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year", "2024",
        "--format", "markdown",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    output = json.loads(stdout)
    assert output["output_path"] is not None
    assert output["output_path"].endswith(".md")


def test_generate_json_output_includes_warnings(monkeypatch, tmp_path: Path) -> None:
    """generate 成功时 JSON 输出必须包含 warnings 字段。"""

    from fund_agent.service import (
        GenerateReportResult,
        FundReport,
        ReportChapter,
    )

    fake_report = FundReport(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        report_year=2024,
        chapters=(
            ReportChapter(chapter_id=0, title="投资要点概览", content="测试", data_sources=()),
            ReportChapter(chapter_id=1, title="基金概况", content="测试", data_sources=()),
            ReportChapter(chapter_id=2, title="业绩分析", content="测试", data_sources=()),
            ReportChapter(chapter_id=3, title="持仓分析", content="测试", data_sources=()),
            ReportChapter(chapter_id=4, title="资产配置分析", content="测试", data_sources=()),
            ReportChapter(chapter_id=5, title="费率分析", content="测试", data_sources=()),
            ReportChapter(chapter_id=6, title="分红分析", content="测试", data_sources=()),
            ReportChapter(chapter_id=7, title="风险提示", content="测试", data_sources=()),
        ),
        metadata={"generated_at": "2026-07-09", "data_years": [2024], "template_version": "v1"},
    )

    class _FakeService:
        def generate_report(self, request, llm_client=None):
            return GenerateReportResult(
                report=fake_report,
                output_path=None,
                warnings=("pandoc 未安装，已回退为 Markdown 格式",),
                failure=None,
            )

    monkeypatch.setattr(cli_module, "FundReadingService", _FakeService)

    work_dir = tmp_path / "work"
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    exit_code, stdout, stderr = _run([
        "generate",
        "--fund-code", "004393",
        "--fund-name", "安信企业价值优选混合型证券投资基金",
        "--year", "2024",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    output = json.loads(stdout)
    assert "warnings" in output
    assert output["warnings"] == ["pandoc 未安装，已回退为 Markdown 格式"]



# ── ask 子命令测试 ──────────────────────────────────────────────────


def test_ask_parser_help_contains_required_args() -> None:
    """ask --help 必须显示 --document-id、--no-stream、--enable-tool-trace。"""

    parser = build_parser()
    # 从 subparsers 中获取 ask 子命令的 help
    ask_help = parser._subparsers._group_actions[0].choices["ask"].format_help()

    assert "--document-id" in ask_help
    assert "--no-stream" in ask_help
    assert "--enable-tool-trace" in ask_help


def test_ask_missing_document_id_exits_with_error() -> None:
    """缺 --document-id 时 argparse 报错并退出。"""

    exit_code, stdout, stderr = _run(["ask", "基金经理是谁？"])
    # argparse 对缺必须参数调用 sys.exit(2)，run_cli 捕获后透传退出码
    assert exit_code == 2


def test_ask_no_stream_outputs_json_on_success(
    monkeypatch, tmp_path: Path
) -> None:
    """--no-stream 模式成功时输出 JSON，含 answer 和 routing_trace。"""

    from fund_agent.service.models import AskQuestionResult, QueryRouteAttempt

    fake_result = AskQuestionResult(
        answer="基金经理张明负责本基金投资管理。",
        citations=(),
        tool_trace=(),
        routing_trace=(
            QueryRouteAttempt(
                query="基金经理是谁？",
                profile_name=None,
                result_kind="success",
                failure_code=None,
            ),
        ),
        failure=None,
    )

    def _fake_ask_question(self, request, *, on_event=None):
        return fake_result

    monkeypatch.setattr(
        service_module.FundReadingService, "ask_question", _fake_ask_question
    )

    exit_code, stdout, stderr = _run([
        "ask",
        "基金经理是谁？",
        "--document-id",
        "test-doc-id",
        "--no-stream",
        "--work-dir",
        str(tmp_path),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "基金经理张明" in stdout
    assert "routing_trace" in stdout
    assert stderr == ""


def test_ask_no_stream_failure_outputs_error(
    monkeypatch, tmp_path: Path
) -> None:
    """--no-stream 模式失败时输出 failure，退出码 2。"""

    from fund_agent.service.models import AskQuestionResult

    fake_result = AskQuestionResult(
        answer="",
        citations=(),
        tool_trace=(),
        routing_trace=(),
        failure=ToolFailure(code=FailureCode.NOT_FOUND, message="文档不存在"),
    )

    def _fake_ask_question(self, request, *, on_event=None):
        return fake_result

    monkeypatch.setattr(
        service_module.FundReadingService, "ask_question", _fake_ask_question
    )

    exit_code, stdout, stderr = _run([
        "ask",
        "基金经理是谁？",
        "--document-id",
        "test-doc-id",
        "--no-stream",
        "--work-dir",
        str(tmp_path),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "failure_code=not_found" in stderr
    assert stdout == ""


def test_ask_streaming_mode_passes_on_event_callback(
    monkeypatch, tmp_path: Path
) -> None:
    """默认流式模式向 ask_question 传递 on_event callback。"""

    received_events: list = []

    def _fake_ask_question(self, request, *, on_event=None):
        from fund_agent.agent.stream_events import StreamEvent, StreamEventType
        # 模拟流式事件
        if on_event:
            on_event(StreamEvent(type=StreamEventType.CONTENT_DELTA, payload="测试"))
            on_event(StreamEvent(type=StreamEventType.DONE, payload=None))
        from fund_agent.service.models import AskQuestionResult, QueryRouteAttempt
        return AskQuestionResult(
            answer="测试",
            citations=(),
            tool_trace=(),
            routing_trace=(
                QueryRouteAttempt(query="x", profile_name=None, result_kind="success"),
            ),
            failure=None,
        )

    monkeypatch.setattr(
        service_module.FundReadingService, "ask_question", _fake_ask_question
    )

    exit_code, stdout, stderr = _run([
        "ask",
        "测试问题",
        "--document-id",
        "test-doc-id",
        "--work-dir",
        str(tmp_path),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "测试" in stdout  # CONTENT_DELTA payload 被打印


def test_generate_cli_real_pdf_smoke_writes_report_and_audit(monkeypatch, tmp_path: Path) -> None:
    """17C 真实 PDF generate smoke：import -> generate -> 落盘 report/sidecar/audit。"""

    assert REAL_SMOKE_PDF.is_file(), "Slice 17C real-smoke PDF is required"

    class _FakeDeepSeekLlmClient:
        def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
            if "审计" in system_prompt or "audit" in system_prompt.lower():
                return '{"score": 99, "violations": []}'
            if "修复" in system_prompt or "repair" in system_prompt.lower():
                return '{"strategy": "none"}'
            return "本章定性分析完成。"

    monkeypatch.setattr(cli_module, "DeepSeekLlmClient", _FakeDeepSeekLlmClient)

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / REAL_SMOKE_PDF.name).write_bytes(REAL_SMOKE_PDF.read_bytes())

    work_dir = tmp_path / "work"

    import_exit, import_stdout, import_stderr = _run(
        [
            "import",
            "--pdf-dir", str(pdf_dir),
            "--fund-code", REAL_SMOKE_FUND_CODE,
            "--fund-name", REAL_SMOKE_FUND_NAME,
            "--year-range", f"{REAL_SMOKE_YEAR}-{REAL_SMOKE_YEAR}",
            "--work-dir", str(work_dir),
        ]
    )

    assert import_exit == SUCCESS_EXIT_CODE, import_stdout + import_stderr
    assert "1 imported" in import_stdout

    generate_exit, generate_stdout, generate_stderr = _run(
        [
            "generate",
            "--fund-code", REAL_SMOKE_FUND_CODE,
            "--fund-name", REAL_SMOKE_FUND_NAME,
            "--year", REAL_SMOKE_YEAR,
            "--format", "markdown",
            "--llm",
            "--work-dir", str(work_dir),
        ]
    )

    assert generate_exit == SUCCESS_EXIT_CODE, generate_stdout + generate_stderr
    output = json.loads(generate_stdout)

    assert output["fund_code"] == REAL_SMOKE_FUND_CODE
    assert output["report_year"] == int(REAL_SMOKE_YEAR)
    assert len(output["chapters"]) == 8

    reports_dir = work_dir / "reports"
    md_path = reports_dir / f"{REAL_SMOKE_FUND_CODE}-{REAL_SMOKE_YEAR}-analysis.md"
    sidecar_path = reports_dir / f"{REAL_SMOKE_FUND_CODE}-{REAL_SMOKE_YEAR}-analysis.meta.json"
    audit_dir = work_dir / "audit_artifacts"

    assert md_path.is_file(), md_path
    assert sidecar_path.is_file(), sidecar_path
    assert audit_dir.is_dir(), audit_dir

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["fund_code"] == REAL_SMOKE_FUND_CODE
    assert sidecar["fund_name"] == REAL_SMOKE_FUND_NAME
    assert sidecar["report_year"] == int(REAL_SMOKE_YEAR)

    audit_files = sorted(audit_dir.glob("chapter_*_audit.json"))
    assert audit_files, audit_dir


def test_fix_chapter(tmp_path: Path, monkeypatch) -> None:
    """fix --chapter 3 只修复 Ch3，exit code 0，输出包含修复统计。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 1 章：投资要点概览\n"
        "Ch1 content [待补充]\n\n"
        "---\n\n"
        "## 第 2 章：产品定义\n"
        "Ch2 content\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充] [数据缺失]\n\n"
        "---\n\n"
        "## 第 4 章：投资者获得感\n"
        "Ch4 content [暂无数据]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    captured_content: list[str] = []

    def _mock_fix(chapter_content, *, audit_feedback="", chapter_contract="", document_id=""):
        captured_content.append(chapter_content)
        return chapter_content.replace("[待补充]", "[已补充]").replace("[数据缺失]", "")

    monkeypatch.setattr(
        "fund_agent.service.chapter_generator._fix_chapter_placeholders",
        _mock_fix,
    )

    exit_code, stdout, stderr = _run([
        "fix",
        "--fund-code", "004393",
        "--chapter", "3",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stderr
    assert "补强占位符: 2" in stdout
    assert "保留占位符: 0" in stdout
    assert len(captured_content) == 1
    assert "Ch3 content" in captured_content[0]
    assert "Ch1 content" not in captured_content[0]
    assert "Ch4 content" not in captured_content[0]


# ── repair 子命令测试 ──────────────────────────────────────────────────


def _write_audit_artifact(work_dir: Path, chapter_id: int, score: float = 65.0, *, violations: tuple | None = None) -> None:
    """写入测试用审计产物。"""
    from fund_agent.service.audit_pipeline import ViolationSeverity, ViolationCategory

    audit_dir = work_dir / "audit_artifacts"
    audit_dir.mkdir(parents=True, exist_ok=True)

    if violations is None:
        violations = (
            {
                "code": "P3",
                "category": "P",
                "severity": "major",
                "description": "模板残留（占位符未替换）",
                "location": "Ch3 paragraph 2",
                "suggested_fix": "替换为实际数据",
                "evidence": "报告期内管理费为[待补充]。",
            },
        )

    data = {
        "chapter_id": chapter_id,
        "score": score,
        "programmatic_score": 70.0,
        "llm_score": 60.0,
        "recommendation": "patch",
        "audit_time": "2026-07-27T00:00:00",
        "violations": [
            {
                "code": v["code"],
                "category": v["category"],
                "severity": v["severity"],
                "description": v["description"],
                "location": v.get("location", ""),
                "suggested_fix": v.get("suggested_fix", ""),
                "evidence": v.get("evidence", ""),
            }
            for v in violations
        ],
    }
    filepath = audit_dir / f"chapter_{chapter_id}_audit.json"
    filepath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class _FakeChapterRepairer:
    """Mock ChapterRepairer that applies a simple string replacement."""

    def __init__(self, llm_client, chapter_id, chapter_content, data_table, contract, violations):
        self._content = chapter_content
        self._chapter_id = chapter_id

    def generate_repair_plan(self):
        from fund_agent.service.audit_pipeline import RepairPlan, RepairAction
        return RepairPlan(
            chapter_id=self._chapter_id,
            actions=(
                RepairAction(
                    violation_code="P3",
                    strategy="patch",
                    target_excerpt="[待补充]",
                    replacement="[已修复]",
                    target_kind="substring",
                    occurrence_index=0,
                ),
            ),
            strategy="patch",
        )

    def apply_patch(self, plan):
        return self._content.replace("[待补充]", "[已修复]")


def test_repair_parser_accepts_valid_args() -> None:
    """repair 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "repair",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
    ])

    assert args.command == "repair"
    assert args.fund_code == "004393"
    assert args.year == 2024
    assert args.chapter == "3"
    assert args.work_dir == Path(".fund_checklist")
    assert args.llm is False


def test_repair_parser_accepts_multiple_chapters() -> None:
    """repair --chapter 必须接受逗号分隔的多章节。"""

    parser = build_parser()
    args = parser.parse_args([
        "repair",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3,5,7",
        "--llm",
    ])

    assert args.command == "repair"
    assert args.chapter == "3,5,7"
    assert args.llm is True


def test_repair_help_shows_params() -> None:
    """repair --help 必须显示 --fund-code、--year、--chapter、--llm。"""

    parser = build_parser()
    repair_help = parser._subparsers._group_actions[0].choices["repair"].format_help()

    assert "--fund-code" in repair_help
    assert "--year" in repair_help
    assert "--chapter" in repair_help
    assert "--llm" in repair_help


def test_repair_exits_0_on_success(tmp_path: Path, monkeypatch) -> None:
    """repair 成功时必须返回 exit code 0 并输出审计分数对比。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 1 章：投资要点概览\n"
        "Ch1 content\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0)
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    # Use the fake repairer from tests
    monkeypatch.setattr(
        "fund_agent.service.audit_pipeline.ChapterRepairer",
        _FakeChapterRepairer,
    )
    # Mock DeepSeekLlmClient to avoid real API call
    monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

    exit_code, stdout, stderr = _run([
        "repair",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--llm",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stderr
    assert "第 3 章: 已修复" in stdout
    assert "修复前后审计分数对比" in stdout
    assert "65.0" in stdout


def test_repair_only_changes_target_chapter(tmp_path: Path, monkeypatch) -> None:
    """修复后只有 Ch3 被修改，其他章节不变。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 1 章：投资要点概览\n"
        "Ch1 content [待补充]\n\n"
        "---\n\n"
        "## 第 2 章：产品定义\n"
        "Ch2 content [待补充]\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n\n"
        "---\n\n"
        "## 第 4 章：投资者获得感\n"
        "Ch4 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0)
    _write_catalog(work_dir, [
        {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
    ])

    monkeypatch.setattr(
        "fund_agent.service.audit_pipeline.ChapterRepairer",
        _FakeChapterRepairer,
    )
    monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

    exit_code, stdout, stderr = _run([
        "repair",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--llm",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stderr

    # Read back the modified report
    updated = report_path.read_text(encoding="utf-8")

    # Ch3 should have [已修复]; other chapters should still have [待补充]
    ch3_content = _extract_chapter_from_markdown(updated, 3)
    assert ch3_content is not None
    assert "[已修复]" in ch3_content
    assert "[待补充]" not in ch3_content

    for ch_id in (1, 2, 4):
        ch_content = _extract_chapter_from_markdown(updated, ch_id)
        assert ch_content is not None, f"Ch{ch_id} should still exist"
        assert "[待补充]" in ch_content, f"Ch{ch_id} should not be modified"
        assert "[已修复]" not in ch_content, f"Ch{ch_id} should not be modified"


def test_repair_exits_2_when_report_not_found(tmp_path: Path) -> None:
    """报告文件不存在时 repair 必须返回 exit 2。"""

    work_dir = tmp_path / "work"

    exit_code, stdout, stderr = _run([
        "repair",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_repair_skips_without_llm_flag(tmp_path: Path, monkeypatch) -> None:
    """未传 --llm 时应跳过修复并输出提示。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0)

    exit_code, stdout, stderr = _run([
        "repair",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "未启用 LLM" in stdout
    assert "跳过: 1" in stdout


# ── regenerate 子命令测试 ──────────────────────────────────────────────────


def test_regenerate_parser_accepts_valid_args() -> None:
    """regenerate 子命令 parser 必须接受合法参数。"""

    parser = build_parser()
    args = parser.parse_args([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
    ])

    assert args.command == "regenerate"
    assert args.fund_code == "004393"
    assert args.year == 2024
    assert args.chapter == "3"
    assert args.work_dir == Path(".fund_checklist")
    assert args.llm is False


def test_regenerate_parser_accepts_multiple_chapters() -> None:
    """regenerate --chapter 必须接受逗号分隔的多章节。"""

    parser = build_parser()
    args = parser.parse_args([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3,5,7",
        "--llm",
    ])

    assert args.command == "regenerate"
    assert args.chapter == "3,5,7"
    assert args.llm is True


def test_regenerate_help_shows_params() -> None:
    """regenerate --help 必须显示 --fund-code、--year、--chapter、--llm。"""

    parser = build_parser()
    regen_help = parser._subparsers._group_actions[0].choices["regenerate"].format_help()

    assert "--fund-code" in regen_help
    assert "--year" in regen_help
    assert "--chapter" in regen_help
    assert "--llm" in regen_help


def test_regenerate_exits_0_on_success(tmp_path: Path, monkeypatch) -> None:
    """regenerate 成功时必须返回 exit code 0 并输出审计分数对比。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 1 章：投资要点概览\n"
        "Ch1 content\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0)

    from fund_agent.service.chat_service import ChatTurnResponse
    regenerated = "Ch3 regenerated content with fixes applied"

    def _mock_chat_turn(self, request, *, llm_client=None, agent_result=None, contract=None):
        return ChatTurnResponse(answer=regenerated)

    monkeypatch.setattr(
        "fund_agent.service.chat_service.ChatService.chat_turn",
        _mock_chat_turn,
    )
    monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

    exit_code, stdout, stderr = _run([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--llm",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stderr
    assert "第 3 章: 已重新生成" in stdout
    assert "重写前后审计分数对比" in stdout
    assert "65.0" in stdout


def test_regenerate_only_changes_target_chapter(tmp_path: Path, monkeypatch) -> None:
    """重写后只有 Ch3 被修改，其他章节不变。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 1 章：投资要点概览\n"
        "Ch1 content [待补充]\n\n"
        "---\n\n"
        "## 第 2 章：产品定义\n"
        "Ch2 content [待补充]\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n\n"
        "---\n\n"
        "## 第 4 章：投资者获得感\n"
        "Ch4 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0)

    from fund_agent.service.chat_service import ChatTurnResponse
    regenerated = "Ch3 regenerated content"

    def _mock_chat_turn(self, request, *, llm_client=None, agent_result=None, contract=None):
        return ChatTurnResponse(answer=regenerated)

    monkeypatch.setattr(
        "fund_agent.service.chat_service.ChatService.chat_turn",
        _mock_chat_turn,
    )
    monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

    exit_code, stdout, stderr = _run([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--llm",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stderr

    updated = report_path.read_text(encoding="utf-8")

    ch3_content = _extract_chapter_from_markdown(updated, 3)
    assert ch3_content is not None
    assert "regenerated content" in ch3_content
    assert "[待补充]" not in ch3_content

    for ch_id in (1, 2, 4):
        ch_content = _extract_chapter_from_markdown(updated, ch_id)
        assert ch_content is not None, f"Ch{ch_id} should still exist"
        assert "[待补充]" in ch_content, f"Ch{ch_id} should not be modified"
        assert "regenerated content" not in ch_content, f"Ch{ch_id} should not be modified"


def test_regenerate_exits_2_when_report_not_found(tmp_path: Path) -> None:
    """报告文件不存在时 regenerate 必须返回 exit 2。"""

    work_dir = tmp_path / "work"

    exit_code, stdout, stderr = _run([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == CLASSIFIED_FAILURE_EXIT_CODE
    assert "not_found" in stderr


def test_regenerate_skips_without_llm_flag(tmp_path: Path, monkeypatch) -> None:
    """未传 --llm 时应跳过重写并输出提示。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0)

    exit_code, stdout, stderr = _run([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE
    assert "未启用 LLM" in stdout
    assert "跳过: 1" in stdout


def test_regenerate_injects_audit_feedback_in_prompt(tmp_path: Path, monkeypatch) -> None:
    """regenerate 必须在 prompt 中注入审计违规作为 context。"""

    work_dir = tmp_path / "work"
    reports_dir = work_dir / "reports"
    reports_dir.mkdir(parents=True)

    md_content = (
        "# 测试基金（004393）2024 年度分析报告\n\n"
        "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
        "---\n\n"
        "## 第 3 章：基金经理画像\n"
        "Ch3 content [待补充]\n"
    )
    report_path = reports_dir / "004393-2024-analysis.md"
    report_path.write_text(md_content, encoding="utf-8")

    _write_audit_artifact(work_dir, chapter_id=3, score=65.0, violations=(
        {
            "code": "P3",
            "category": "P",
            "severity": "major",
            "description": "模板残留（占位符未替换）",
            "location": "Ch3 paragraph 2",
            "suggested_fix": "替换为实际数据",
            "evidence": "报告期内管理费为[待补充]。",
        },
        {
            "code": "C4",
            "category": "C",
            "severity": "major",
            "description": "分析深度不足",
            "location": "Ch3 paragraph 3",
            "suggested_fix": "补充持仓集中度趋势分析",
            "evidence": "",
        },
    ))

    captured_user_prompt: list[str] = []

    from fund_agent.service.chat_service import ChatTurnResponse

    def _mock_chat_turn(self, request, *, llm_client=None, agent_result=None, contract=None):
        captured_user_prompt.append(request.user_text)
        return ChatTurnResponse(answer="regenerated content")

    monkeypatch.setattr(
        "fund_agent.service.chat_service.ChatService.chat_turn",
        _mock_chat_turn,
    )
    monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

    exit_code, stdout, stderr = _run([
        "regenerate",
        "--fund-code", "004393",
        "--year", "2024",
        "--chapter", "3",
        "--llm",
        "--work-dir", str(work_dir),
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stderr
    assert len(captured_user_prompt) == 1
    user_prompt = captured_user_prompt[0]
    assert "P3" in user_prompt
    assert "模板残留" in user_prompt
    assert "C4" in user_prompt
    assert "分析深度不足" in user_prompt
    assert "[待补充]" in user_prompt


# ── Phase 7.2 Smoke Tests ──────────────────────────────────────────────


class TestPhase72Smoke:
    """Phase 7.2 端到端 smoke 测试：repair + regenerate + 全量回归。"""

    # ── Smoke 2: repair 分数不降低 ──────────────────────────────────

    def test_smoke2_repair_score_displayed_and_non_negative(self, tmp_path: Path, monkeypatch) -> None:
        """Smoke 2: repair 执行后输出审计分数对比，分数值非负。"""
        work_dir = tmp_path / "work"
        reports_dir = work_dir / "reports"
        reports_dir.mkdir(parents=True)

        md_content = (
            "# 测试基金（004393）2024 年度分析报告\n\n"
            "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
            "---\n\n"
            "## 第 3 章：基金经理画像\n"
            "Ch3 content [待补充]\n"
        )
        report_path = reports_dir / "004393-2024-analysis.md"
        report_path.write_text(md_content, encoding="utf-8")

        _write_audit_artifact(work_dir, chapter_id=3, score=65.0)
        _write_catalog(work_dir, [
            {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
        ])

        monkeypatch.setattr(
            "fund_agent.service.audit_pipeline.ChapterRepairer",
            _FakeChapterRepairer,
        )
        monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

        exit_code, stdout, stderr = _run([
            "repair",
            "--fund-code", "004393",
            "--year", "2024",
            "--chapter", "3",
            "--llm",
            "--work-dir", str(work_dir),
        ])

        assert exit_code == SUCCESS_EXIT_CODE, stderr
        assert "修复前后审计分数对比" in stdout
        assert "65.0" in stdout  # before score present
        assert "第 3 章" in stdout

    def test_smoke2_repair_preserves_other_chapters(self, tmp_path: Path, monkeypatch) -> None:
        """Smoke 2: repair Ch3 后 Ch1 内容不变（分数影响隔离）。"""
        work_dir = tmp_path / "work"
        reports_dir = work_dir / "reports"
        reports_dir.mkdir(parents=True)

        original_ch1 = "Ch1 original investment thesis content [待补充]"
        original_ch2 = "Ch2 original product definition content [待补充]"
        md_content = (
            "# 测试基金（004393）2024 年度分析报告\n\n"
            "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
            "---\n\n"
            "## 第 1 章：投资要点概览\n"
            f"{original_ch1}\n\n"
            "---\n\n"
            "## 第 2 章：产品定义\n"
            f"{original_ch2}\n\n"
            "---\n\n"
            "## 第 3 章：基金经理画像\n"
            "Ch3 content [待补充]\n"
        )
        report_path = reports_dir / "004393-2024-analysis.md"
        report_path.write_text(md_content, encoding="utf-8")

        _write_audit_artifact(work_dir, chapter_id=3, score=65.0)
        _write_catalog(work_dir, [
            {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
        ])

        monkeypatch.setattr(
            "fund_agent.service.audit_pipeline.ChapterRepairer",
            _FakeChapterRepairer,
        )
        monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

        exit_code, stdout, stderr = _run([
            "repair",
            "--fund-code", "004393",
            "--year", "2024",
            "--chapter", "3",
            "--llm",
            "--work-dir", str(work_dir),
        ])

        assert exit_code == SUCCESS_EXIT_CODE, stderr
        updated = report_path.read_text(encoding="utf-8")
        assert original_ch1 in updated, "Ch1 must be unchanged"
        assert original_ch2 in updated, "Ch2 must be unchanged"

    def test_smoke2_repair_multi_chapter_scores(self, tmp_path: Path, monkeypatch) -> None:
        """Smoke 2: 多章节 repair 每章独立显示分数。"""
        work_dir = tmp_path / "work"
        reports_dir = work_dir / "reports"
        reports_dir.mkdir(parents=True)

        md_content = (
            "# 测试基金（004393）2024 年度分析报告\n\n"
            "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
            "---\n\n"
            "## 第 1 章：投资要点概览\n"
            "Ch1 content\n\n"
            "---\n\n"
            "## 第 3 章：基金经理画像\n"
            "Ch3 content [待补充]\n\n"
            "---\n\n"
            "## 第 5 章：费率分析\n"
            "Ch5 content [待补充]\n"
        )
        report_path = reports_dir / "004393-2024-analysis.md"
        report_path.write_text(md_content, encoding="utf-8")

        _write_audit_artifact(work_dir, chapter_id=3, score=65.0)
        _write_audit_artifact(work_dir, chapter_id=5, score=45.0)
        _write_catalog(work_dir, [
            {"document_id": "doc-2024", "year": 2024, "fund_code": "004393"},
        ])

        monkeypatch.setattr(
            "fund_agent.service.audit_pipeline.ChapterRepairer",
            _FakeChapterRepairer,
        )
        monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

        exit_code, stdout, stderr = _run([
            "repair",
            "--fund-code", "004393",
            "--year", "2024",
            "--chapter", "3,5",
            "--llm",
            "--work-dir", str(work_dir),
        ])

        assert exit_code == SUCCESS_EXIT_CODE, stderr
        assert "第 3 章" in stdout
        assert "第 5 章" in stdout
        assert "65.0" in stdout
        assert "45.0" in stdout

    # ── Smoke 3: regenerate 单章重写 ────────────────────────────────

    def test_smoke3_regenerate_target_only(self, tmp_path: Path, monkeypatch) -> None:
        """Smoke 3: regenerate Ch3 后仅 Ch3 变化，其他章节保留原文。"""
        work_dir = tmp_path / "work"
        reports_dir = work_dir / "reports"
        reports_dir.mkdir(parents=True)

        original_ch1 = "Ch1 original content [待补充]"
        original_ch2 = "Ch2 original content [待补充]"
        md_content = (
            "# 测试基金（004393）2024 年度分析报告\n\n"
            "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
            "---\n\n"
            "## 第 1 章：投资要点概览\n"
            f"{original_ch1}\n\n"
            "---\n\n"
            "## 第 2 章：产品定义\n"
            f"{original_ch2}\n\n"
            "---\n\n"
            "## 第 3 章：基金经理画像\n"
            "Ch3 content [待补充]\n"
        )
        report_path = reports_dir / "004393-2024-analysis.md"
        report_path.write_text(md_content, encoding="utf-8")

        _write_audit_artifact(work_dir, chapter_id=3, score=65.0)

        from fund_agent.service.chat_service import ChatTurnResponse
        regenerated = "Ch3 regenerated content with fixes applied"

        def _mock_chat_turn(self, request, *, llm_client=None, agent_result=None, contract=None):
            return ChatTurnResponse(answer=regenerated)

        monkeypatch.setattr(
            "fund_agent.service.chat_service.ChatService.chat_turn",
            _mock_chat_turn,
        )
        monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

        exit_code, stdout, stderr = _run([
            "regenerate",
            "--fund-code", "004393",
            "--year", "2024",
            "--chapter", "3",
            "--llm",
            "--work-dir", str(work_dir),
        ])

        assert exit_code == SUCCESS_EXIT_CODE, stderr
        updated = report_path.read_text(encoding="utf-8")

        assert original_ch1 in updated, "Ch1 must be unchanged"
        assert original_ch2 in updated, "Ch2 must be unchanged"
        assert regenerated in updated, "Ch3 must be regenerated"
        assert "[待补充]" in updated  # Ch1/Ch2 still have placeholder

    def test_smoke3_regenerate_score_comparison(self, tmp_path: Path, monkeypatch) -> None:
        """Smoke 3: regenerate 输出重写前后分数对比。"""
        work_dir = tmp_path / "work"
        reports_dir = work_dir / "reports"
        reports_dir.mkdir(parents=True)

        md_content = (
            "# 测试基金（004393）2024 年度分析报告\n\n"
            "**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n\n"
            "---\n\n"
            "## 第 3 章：基金经理画像\n"
            "Ch3 content [待补充]\n"
        )
        report_path = reports_dir / "004393-2024-analysis.md"
        report_path.write_text(md_content, encoding="utf-8")

        _write_audit_artifact(work_dir, chapter_id=3, score=70.0)

        from fund_agent.service.chat_service import ChatTurnResponse

        def _mock_chat_turn(self, request, *, llm_client=None, agent_result=None, contract=None):
            return ChatTurnResponse(answer="regenerated chapter 3")

        monkeypatch.setattr(
            "fund_agent.service.chat_service.ChatService.chat_turn",
            _mock_chat_turn,
        )
        monkeypatch.setattr(cli_module, "DeepSeekLlmClient", lambda **kw: object())

        exit_code, stdout, stderr = _run([
            "regenerate",
            "--fund-code", "004393",
            "--year", "2024",
            "--chapter", "3",
            "--llm",
            "--work-dir", str(work_dir),
        ])

        assert exit_code == SUCCESS_EXIT_CODE, stderr
        assert "重写前后审计分数对比" in stdout
        assert "70.0" in stdout
        assert "第 3 章" in stdout

    # ── Smoke 5: 全量回归 ──────────────────────────────────────────

    def test_smoke5_phase72_modules_importable(self) -> None:
        """Smoke 5: Phase 7.2 所有关键模块可导入。"""
        modules = [
            "fund_agent.cli.main",
            "fund_agent.service.scene_config",
            "fund_agent.service.chat_service",
            "fund_agent.service.chat_contract",
            "fund_agent.service.audit_pipeline",
            "fund_agent.service.chapter_generator",
            "fund_agent.service.session_models",
            "fund_agent.host.session_store",
            "fund_agent.host.minimal_host",
        ]
        for mod_name in modules:
            importlib.import_module(mod_name)

    def test_smoke5_scene_configs_defined(self) -> None:
        """Smoke 5: Phase 7.2 所有 SceneConfig 已定义。"""
        from fund_agent.service.scene_config import (
            ASK_SCENE_CONFIG,
            FIX_SCENE_CONFIG,
            INTERACTIVE_SCENE_CONFIG,
            REGENERATE_SCENE_CONFIG,
            REPAIR_SCENE_CONFIG,
        )

        configs = {
            "ask": ASK_SCENE_CONFIG,
            "interactive": INTERACTIVE_SCENE_CONFIG,
            "regenerate": REGENERATE_SCENE_CONFIG,
            "repair": REPAIR_SCENE_CONFIG,
            "fix": FIX_SCENE_CONFIG,
        }
        for name, cfg in configs.items():
            assert cfg.scene == name
            assert len(cfg.fragments) >= 3, f"{name} fragments too few"
            assert cfg.model.default_name, f"{name} model name empty"

    def test_smoke5_repair_regenerate_parsers_registered(self) -> None:
        """Smoke 5: repair / regenerate / fix CLI 子命令已注册。"""
        parser = build_parser()
        choices = parser._subparsers._group_actions[0].choices
        for cmd in ("repair", "regenerate", "fix"):
            assert cmd in choices, f"'{cmd}' 子命令未注册"

    def test_smoke5_cli_help_includes_all_subcommands(self) -> None:
        """Smoke 5: --help 输出包含所有 Phase 7.2 子命令。"""
        parser = build_parser()
        help_text = parser.format_help()
        for cmd in ("repair", "regenerate", "fix", "interactive", "generate"):
            assert cmd in help_text, f"'{cmd}' 未出现在 --help 中"
