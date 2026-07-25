"""基金年报阅读工具的最小命令行入口。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence, TextIO

from fund_agent.fund.document_tools.constants import FailureCode, ReportType
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import ToolFailure
from fund_agent.fund.document_tools.eid_downloader import EidDownloadError, download_annual_report
from fund_agent.fund.document_tools.persistent_repository import (
    CATALOG_FILENAME,
    FilesystemReportRepository,
)
from fund_agent.agent.deepseek_llm import DeepSeekLlmClient
from fund_agent.agent.stream_events import StreamEventType
from fund_agent.service import (
    AggregateMultiYearAnnualPerformanceRequest,
    AnnualReportDocument,
    AskQuestionRequest,
    DeepAuditRequest,
    DisclosureAuditRequest,
    ExtractAllocationRequest,
    ExtractFeeRatesMultiYearRequest,
    ExtractHoldingsRequest,
    FundReadingService,
    GenerateReportRequest,
    ImportLocalReportRequest,
    ReadLocalReportRequest,
)

SUCCESS_EXIT_CODE = 0
UNEXPECTED_FAILURE_EXIT_CODE = 1
CLASSIFIED_FAILURE_EXIT_CODE = 2
DEFAULT_QUERY = "基金经理"
DEFAULT_WORK_DIR = ".fund_checklist"
UNEXPECTED_FAILURE_MESSAGE = "unexpected_error: CLI 执行失败"


def main(argv: Sequence[str] | None = None) -> int:
    """执行 CLI 并返回进程退出码。

    参数:
        argv: 命令行参数序列；None 时读取 sys.argv。

    返回:
        0 表示成功，2 表示已分类业务失败，1 表示未预期异常。

    异常:
        本函数捕获业务失败和未预期异常，不向调用方抛出。
    """

    return run_cli(argv, stdout=sys.stdout, stderr=sys.stderr)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """执行 CLI，允许测试注入 stdout/stderr。

    参数:
        argv: 命令行参数序列；None 时读取 sys.argv。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        进程退出码。

    异常:
        本函数捕获内部异常并转换为稳定退出码。
    """

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else UNEXPECTED_FAILURE_EXIT_CODE
    try:
        if args.command == "read":
            return _run_read_command(args, stdout=stdout, stderr=stderr)
        if args.command == "multi-year":
            return _run_multi_year_command(args, stdout=stdout, stderr=stderr)
        if args.command == "import":
            return _run_import_command(args, stdout=stdout, stderr=stderr)
        if args.command == "holdings":
            return _run_holdings_command(args, stdout=stdout, stderr=stderr)
        if args.command == "download":
            return _run_download_command(args, stdout=stdout, stderr=stderr)
        if args.command == "allocation":
            return _run_allocation_command(args, stdout=stdout, stderr=stderr)
        if args.command == "fees":
            return _run_fees_command(args, stdout=stdout, stderr=stderr)
        if args.command == "audit":
            return _run_audit_command(args, stdout=stdout, stderr=stderr)
        if args.command == "deep-audit":
            return _run_deep_audit_command(args, stdout=stdout, stderr=stderr)
        if args.command == "generate":
            return _run_generate_command(args, stdout=stdout, stderr=stderr)
        if args.command == "ask":
            return _run_ask_command(args, stdout=stdout, stderr=stderr)
        if args.command == "interactive":
            return _run_interactive_command(args, stdout=stdout, stderr=stderr)
    except DocumentToolError as exc:
        _write_classified_failure(ToolFailure(code=exc.code, message=exc.message), stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE
    except Exception:
        print(UNEXPECTED_FAILURE_MESSAGE, file=stderr)
        return UNEXPECTED_FAILURE_EXIT_CODE

    print(UNEXPECTED_FAILURE_MESSAGE, file=stderr)
    return UNEXPECTED_FAILURE_EXIT_CODE


def build_parser() -> argparse.ArgumentParser:
    """构造包含 read 和 multi-year 子命令的 argparse parser。

    参数:
        无。

    返回:
        argparse.ArgumentParser。

    异常:
        本函数不抛出业务异常。
    """

    parser = argparse.ArgumentParser(prog="fund-checklist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--pdf", required=True, type=Path)
    read_parser.add_argument("--fund-code", required=True)
    read_parser.add_argument("--fund-name", required=True)
    read_parser.add_argument("--year", required=True, type=int)
    read_parser.add_argument("--query", default=DEFAULT_QUERY)
    read_parser.add_argument("--share-class")
    read_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    multi_year_parser = subparsers.add_parser("multi-year")
    multi_year_parser.add_argument("--fund-code", required=True)
    multi_year_parser.add_argument("--years", required=True)
    multi_year_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--pdf-dir", required=True, type=Path)
    import_parser.add_argument("--fund-code", required=True)
    import_parser.add_argument("--fund-name", required=True)
    import_parser.add_argument("--year-range", default="2022-2024", help="年份范围（默认最近3年：2022-2024）")
    import_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    holdings_parser = subparsers.add_parser("holdings")
    holdings_parser.add_argument("--fund-code", required=True)
    holdings_parser.add_argument("--years", required=True)
    holdings_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("--fund-code", required=True, help="基金代码")
    download_parser.add_argument("--year", required=True, type=int, help="报告年份")
    download_parser.add_argument("--output-dir", default=Path("基金年报"), type=Path, help="PDF 输出目录")
    download_parser.add_argument("--force", action="store_true", help="强制重新下载")

    allocation_parser = subparsers.add_parser("allocation")
    allocation_parser.add_argument("--fund-code", required=True)
    allocation_parser.add_argument("--years", required=True)
    allocation_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    fees_parser = subparsers.add_parser("fees")
    fees_parser.add_argument("--fund-code", required=True)
    fees_parser.add_argument("--years", required=True)
    fees_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--fund-code", required=True)
    audit_parser.add_argument("--year", required=True, type=int)
    audit_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    deep_audit_parser = subparsers.add_parser("deep-audit")
    deep_audit_parser.add_argument("--fund-code", required=True)
    deep_audit_parser.add_argument("--year", required=True, type=int)
    deep_audit_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--fund-code", required=True)
    generate_parser.add_argument("--fund-name", required=True)
    generate_parser.add_argument("--year", required=True, type=int)
    generate_parser.add_argument("--years", default="", help="逗号分隔年份列表；留空则自动使用 catalog 中所有可用年份")
    generate_parser.add_argument("--format", dest="output_format", default="json", choices=["json", "markdown", "pdf"])
    generate_parser.add_argument("--llm", action="store_true", default=False, help="使用 LLM 生成分析文本（需要 DEEPSEEK_API_KEY）")
    generate_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("question", help="用户问题")
    ask_parser.add_argument("--document-id", required=True, help="已导入年报的 document_id")
    ask_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
    ask_parser.add_argument("--no-stream", action="store_true", default=False, help="禁用流式输出，等待完成后输出 JSON")
    ask_parser.add_argument("--enable-tool-trace", action="store_true", default=False, help="流式模式下同步输出 tool call/result")

    interactive_parser = subparsers.add_parser("interactive")
    interactive_parser.add_argument("--fund-code", required=True, help="基金代码（如 011649）")
    interactive_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
    interactive_parser.add_argument("--label", default=None, help="会话标签（用于恢复）")
    interactive_parser.add_argument("--no-stream", action="store_true", default=False, help="禁用流式输出")
    interactive_parser.add_argument("--enable-tool-trace", action="store_true", default=False, help="显示工具调用详情")
    return parser


def _collect_matching_docs(
    work_dir: Path,
    fund_code: str,
    requested_years: tuple[int, ...],
) -> list[AnnualReportDocument] | None:
    """从 catalog 中查找匹配的年报文档列表。

    参数:
        work_dir: 工作目录。
        fund_code: 基金代码。
        requested_years: 请求年度列表。

    返回:
        匹配的文档列表；无匹配时返回 None。
    """

    repository = FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME,
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    catalog_reports = repository.list_reports()

    seen_years: dict[int, str] = {}
    for report in catalog_reports:
        if report.get("fund_code") == fund_code and report.get("year") in requested_years:
            year = int(report["year"])
            doc_id = str(report["document_id"])
            seen_years[year] = doc_id

    matching_docs = [AnnualReportDocument(year=year, document_id=doc_id) for year, doc_id in sorted(seen_years.items())]
    return matching_docs if matching_docs else None


def _run_read_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """调用 Service 执行 local PDF 阅读链路。

    参数:
        args: argparse 解析出的 read 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；Agent 返回 ToolFailure 时返回 2。

    异常:
        DocumentToolError: PDF、Docling conversion、repository 或 parser health 失败时抛出已分类失败。
    """

    service = FundReadingService()
    result = service.read_local_report(
        ReadLocalReportRequest(
            pdf_path=Path(args.pdf),
            fund_code=args.fund_code,
            fund_name=args.fund_name,
            year=args.year,
            query=args.query,
            work_dir=Path(args.work_dir),
            share_class=args.share_class,
        )
    )
    agent_result = result.agent_result
    if agent_result.failure is not None:
        _write_classified_failure(agent_result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    _write_success_output(agent_result, stdout)
    return SUCCESS_EXIT_CODE


def _run_ask_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """执行 LLM 问答，默认流式输出，--no-stream 回退 JSON。

    参数:
        args: argparse 解析出的 ask 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；Agent 返回 ToolFailure 时返回 2。
    """

    service = FundReadingService()

    if args.no_stream:
        result = service.ask_question(
            AskQuestionRequest(
                document_id=args.document_id,
                question=args.question,
                work_dir=Path(args.work_dir),
            ),
        )
        if result.failure is not None:
            _write_classified_failure(result.failure, stderr)
            return CLASSIFIED_FAILURE_EXIT_CODE

        output = {
            "answer": result.answer,
            "citations": [
                {
                    "document_id": c.document_id,
                    "fund_code": c.fund_code,
                    "fund_name": c.fund_name,
                    "year": c.year,
                    "report_type": c.report_type,
                }
                for c in result.citations
            ],
            "routing_trace": [
                {
                    "query": r.query,
                    "profile_name": r.profile_name,
                    "result_kind": r.result_kind,
                    "failure_code": r.failure_code.value if r.failure_code else None,
                }
                for r in result.routing_trace
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
        return SUCCESS_EXIT_CODE

    # 流式输出模式
    show_tool_trace = getattr(args, "enable_tool_trace", False)
    failure_ref = [None]  # mutable container for callback

    def on_stream_event(event: object) -> None:
        from fund_agent.agent.stream_events import StreamEvent, StreamEventType as SE

        if not isinstance(event, StreamEvent):
            return
        if event.type == StreamEventType.CONTENT_DELTA and isinstance(event.payload, str):
            stdout.write(event.payload)
            stdout.flush()
        elif event.type == StreamEventType.TOOL_EVENT and show_tool_trace:
            phase = event.payload.get("phase", "") if isinstance(event.payload, dict) else ""
            tool_name = event.payload.get("tool_name", "") if isinstance(event.payload, dict) else ""
            if phase == "call":
                stdout.write(f"\n[TOOL] calling {tool_name}...\n")
            elif phase == "result":
                citations = event.payload.get("citation_count", 0) if isinstance(event.payload, dict) else 0
                evidence_len = event.payload.get("evidence_length", 0) if isinstance(event.payload, dict) else 0
                stdout.write(f"[TOOL] {tool_name} done ({citations} citations, {evidence_len} chars)\n")
            stdout.flush()
        elif event.type == StreamEventType.ERROR:
            msg = event.payload.get("message", "") if isinstance(event.payload, dict) else str(event.payload)
            failure_ref[0] = msg
        elif event.type == StreamEventType.DONE:
            stdout.write("\n")
            stdout.flush()

    result = service.ask_question(
        AskQuestionRequest(
            document_id=args.document_id,
            question=args.question,
            work_dir=Path(args.work_dir),
        ),
        on_event=on_stream_event,
    )

    if result.failure is not None:
        if failure_ref[0] is None:
            _write_classified_failure(result.failure, stderr)
        else:
            print(f"\nfailure_code={result.failure.code.value}", file=stderr)
            print(f"message={result.failure.message}", file=stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    return SUCCESS_EXIT_CODE


def _parse_years(years_str: str) -> tuple[int, ...]:
    """解析逗号分隔的年度字符串为升序元组。

    参数:
        years_str: 逗号分隔的年度字符串，如 "2020,2021,2022,2023,2024"；空字符串返回空元组。

    返回:
        升序排列的年度元组。

    异常:
        ValueError: 年度格式不合法时抛出。
    """

    if not years_str or not years_str.strip():
        return ()
    years = tuple(int(y.strip()) for y in years_str.split(","))
    return tuple(sorted(years))


def _parse_year_range(range_str: str) -> tuple[int, ...]:
    """解析年度范围字符串为升序元组。

    参数:
        range_str: 范围字符串，支持 "2020-2024" 或 "2020,2021,2022,2023,2024"。

    返回:
        升序排列的年度元组。

    异常:
        ValueError: 格式不合法时抛出。
    """

    if "-" in range_str:
        parts = range_str.split("-", 1)
        start = int(parts[0].strip())
        end = int(parts[1].strip())
        return tuple(range(start, end + 1))
    return _parse_years(range_str)


_YEAR_PATTERN = re.compile(r"(20\d{2})")


def _extract_year_from_filename(filename: str) -> int | None:
    """从 PDF 文件名中提取年份。

    参数:
        filename: PDF 文件名，如 "安信企业价值优选混合型证券投资基金2024年年度报告.pdf"。

    返回:
        提取到的年份；无法提取时返回 None。
    """

    match = _YEAR_PATTERN.search(filename)
    if match:
        return int(match.group(1))
    return None


_FUND_NAME_STOP_WORDS = (
    "交易型开放式", "证券投资基金", "联接基金", "灵活配置",
    "混合型", "债券型", "股票型", "指数型", "发起式",
    "纯债", "混合", "债券",
)


def _extract_fund_name_keyword(fund_name: str) -> str:
    """从基金全称中提取关键词用于文件名匹配。

    参数:
        fund_name: 基金全称，如 "安信企业价值优选混合型证券投资基金"。

    返回:
        去除通用后缀、份额类别后缀、规范化括号后的关键词。

    异常:
        ValueError: 关键词为空（基金名称全由通用后缀组成）时抛出。
    """

    # 规范化：全角括号 → 半角，去空格
    keyword = fund_name.replace("（", "(").replace("）", ")").replace(" ", "")
    for stop in _FUND_NAME_STOP_WORDS:
        keyword = keyword.replace(stop, "")
    # 去除尾部份额类别后缀（单个大写字母 A/B/C/D/E）
    keyword = re.sub(r"[A-E]$", "", keyword)
    keyword = keyword.strip()
    if not keyword:
        raise ValueError(f"基金名称无法提取关键词: {fund_name}")
    return keyword


def _matches_fund_name(filename: str, fund_name_keyword: str) -> bool:
    """检查 PDF 文件名是否包含基金名称关键词。

    参数:
        filename: PDF 文件名。
        fund_name_keyword: 从 _extract_fund_name_keyword 提取的关键词。

    返回:
        文件名包含关键词时返回 True。
    """

    # 规范化文件名：全角括号 → 半角
    normalized_filename = filename.replace("（", "(").replace("）", ")")

    if fund_name_keyword in normalized_filename:
        return True

    # 处理关键词被停用词分割的情况
    parts = [p for p in fund_name_keyword if p.strip()]
    if len(parts) >= 4:
        return all(part in normalized_filename for part in parts)

    return False


def _run_import_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """从目录批量导入 PDF 到 catalog。

    参数:
        args: argparse 解析出的 import 参数。
        stdout: 进度输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0（至少 1 份导入成功）；全部失败返回 2。

    异常:
        DocumentToolError: 目录不存在或不可读时抛出已分类失败。
    """

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.is_dir():
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"目录不存在: {pdf_dir.name}")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    year_range = _parse_year_range(args.year_range)
    year_range_set = set(year_range)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message="目录中未找到 PDF 文件")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    matching_files: list[tuple[Path, int]] = []
    try:
        fund_name_keyword = _extract_fund_name_keyword(args.fund_name)
    except ValueError as exc:
        failure = ToolFailure(code=FailureCode.SCHEMA_DRIFT, message=str(exc))
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE
    for pdf_path in pdf_files:
        year = _extract_year_from_filename(pdf_path.name)
        if year is not None and year in year_range_set and _matches_fund_name(pdf_path.name, fund_name_keyword):
            matching_files.append((pdf_path, year))

    if not matching_files:
        failure = ToolFailure(
            code=FailureCode.NOT_FOUND,
            message=f"目录中未找到年份在 {year_range[0]}-{year_range[-1]} 范围内的 PDF 文件",
        )
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    service = FundReadingService()
    work_dir = Path(args.work_dir)
    imported = 0
    skipped = 0
    failed = 0
    total = len(matching_files)

    for idx, (pdf_path, year) in enumerate(matching_files, 1):
        label = f"[{idx}/{total}] {pdf_path.name}"
        try:
            result = service.import_local_report(
                ImportLocalReportRequest(
                    pdf_path=pdf_path,
                    fund_code=args.fund_code,
                    fund_name=args.fund_name,
                    year=year,
                    work_dir=work_dir,
                    report_type=ReportType.ANNUAL_REPORT,
                )
            )
            imported += 1
            print(f"{label} -> imported (document_id={result.document_id})", file=stdout)
        except DocumentToolError as exc:
            if exc.code is FailureCode.INTEGRITY_ERROR:
                skipped += 1
                print(f"{label} -> skipped ({exc.message})", file=stdout)
            else:
                failed += 1
                print(f"{label} -> failed ({exc.code.value}: {exc.message})", file=stdout)
        except Exception:
            failed += 1
            print(f"{label} -> failed (unexpected error)", file=stdout)

    print("", file=stdout)
    print(f"Summary: {imported} imported, {skipped} skipped, {failed} failed", file=stdout)

    if imported == 0 and failed > 0:
        return CLASSIFIED_FAILURE_EXIT_CODE
    return SUCCESS_EXIT_CODE


def _run_multi_year_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """从 catalog 查找已导入年报并聚合多年度业绩。

    参数:
        args: argparse 解析出的 multi-year 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0（含 partial coverage）；not_found 返回 2。

    异常:
        DocumentToolError: catalog 不可用时抛出已分类失败。
    """

    work_dir = Path(args.work_dir)
    requested_years = _parse_years(args.years)

    repository = FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME,
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    catalog_reports = repository.list_reports()

    matching_docs: list[AnnualReportDocument] = []
    seen_years: dict[int, str] = {}
    for report in catalog_reports:
        if report.get("fund_code") == args.fund_code and report.get("year") in requested_years:
            year = int(report["year"])
            doc_id = str(report["document_id"])
            # last-wins：同一年有多条 catalog 记录时保留最后一条（catalog 按 document_id 字典序排列）
            seen_years[year] = doc_id

    for year, doc_id in sorted(seen_years.items()):
        matching_docs.append(AnnualReportDocument(year=year, document_id=doc_id))

    if len(matching_docs) < 3:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"catalog 中匹配 {args.fund_code} 的年报不足 3 年")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    service = FundReadingService()
    result = service.aggregate_multi_year_annual_performance(
        AggregateMultiYearAnnualPerformanceRequest(
            fund_code=args.fund_code,
            requested_years=requested_years,
            annual_report_documents=tuple(matching_docs),
            work_dir=work_dir,
        )
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "series": [asdict(s) for s in result.series],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _fund_name_from_catalog(work_dir: Path, fund_code: str) -> str:
    """从 catalog 中获取基金名称。"""
    repository = FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME,
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    for report in repository.list_reports():
        if report.get("fund_code") == fund_code:
            return str(report.get("fund_name", ""))
    return ""


def _run_download_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """从 EID 下载基金年报 PDF。

    参数:
        args: argparse 解析出的 download 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；失败返回 2。
    """
    try:
        result = download_annual_report(
            fund_code=args.fund_code,
            year=args.year,
            output_dir=Path(args.output_dir),
            force=args.force,
        )
        output = {
            "fund_code": result.fund_code,
            "fund_name": result.fund_name,
            "year": result.year,
            "status": result.status,
            "file_path": str(result.file_path) if result.file_path else None,
            "source_url": result.source_url,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
        return SUCCESS_EXIT_CODE
    except EidDownloadError as exc:
        # 将 EidDownloadError.code 映射到 FailureCode 枚举
        try:
            error_code = FailureCode(exc.code)
        except ValueError:
            error_code = FailureCode.UNAVAILABLE
        failure = ToolFailure(code=error_code, message=str(exc))
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE


def _run_holdings_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """从 catalog 查找已导入年报并聚合多年度持仓数据。

    参数:
        args: argparse 解析出的 holdings 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0；not_found 返回 2。

    异常:
        DocumentToolError: catalog 不可用时抛出已分类失败。
    """

    work_dir = Path(args.work_dir)
    requested_years = _parse_years(args.years)

    matching_docs = _collect_matching_docs(work_dir, args.fund_code, requested_years)
    if not matching_docs:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"catalog 中未找到 {args.fund_code} 的年报")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    # 从 catalog 获取 fund_name（用于债券基金 fallback 判断）
    fund_name = _fund_name_from_catalog(work_dir, args.fund_code)

    service = FundReadingService()
    result = service.extract_multi_year_holdings(
        ExtractHoldingsRequest(
            fund_code=args.fund_code,
            requested_years=requested_years,
            annual_report_documents=tuple(matching_docs),
            work_dir=work_dir,
            fund_name=fund_name,
        )
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "series": [asdict(result.series)],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _run_allocation_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """从 catalog 查找已导入年报并聚合多年度资产配置数据。

    参数:
        args: argparse 解析出的 allocation 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0；not_found 返回 2。
    """

    work_dir = Path(args.work_dir)
    requested_years = _parse_years(args.years)

    matching_docs = _collect_matching_docs(work_dir, args.fund_code, requested_years)
    if not matching_docs:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"catalog 中未找到 {args.fund_code} 的年报")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    service = FundReadingService()
    result = service.extract_multi_year_allocation(
        ExtractAllocationRequest(
            fund_code=args.fund_code,
            requested_years=requested_years,
            annual_report_documents=tuple(matching_docs),
            work_dir=work_dir,
        )
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "series": [asdict(result.series)],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _run_fees_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """从 catalog 查找已导入年报并聚合多年度费率数据。

    参数:
        args: argparse 解析出的 fees 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0；not_found 返回 2。
    """

    work_dir = Path(args.work_dir)
    requested_years = _parse_years(args.years)

    matching_docs = _collect_matching_docs(work_dir, args.fund_code, requested_years)
    if not matching_docs:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"catalog 中未找到 {args.fund_code} 的年报")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    service = FundReadingService()
    result = service.extract_multi_year_fee_rates(
        ExtractFeeRatesMultiYearRequest(
            fund_code=args.fund_code,
            requested_years=requested_years,
            annual_report_documents=tuple(matching_docs),
            work_dir=work_dir,
        )
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "series": [asdict(result.series)],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _run_audit_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """审计年报披露完整性。

    参数:
        args: argparse 解析出的 audit 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0；not_found 返回 2。
    """

    service = FundReadingService()
    result = service.audit_disclosure_completeness(
        DisclosureAuditRequest(
            fund_code=args.fund_code,
            year=args.year,
            work_dir=Path(args.work_dir),
        )
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "fund_code": result.fund_code,
        "year": result.year,
        "document_id": result.document_id,
        "disclosures": [asdict(d) for d in result.disclosures],
        "summary": result.summary,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _run_deep_audit_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """深度披露完整性审计（基于 search + read_section）。

    参数:
        args: argparse 解析出的 deep-audit 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0；not_found 返回 2。
    """

    service = FundReadingService()
    result = service.deep_audit_disclosure(
        DeepAuditRequest(
            fund_code=args.fund_code,
            year=args.year,
            work_dir=Path(args.work_dir),
        )
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "fund_code": result.fund_code,
        "year": result.year,
        "document_id": result.document_id,
        "audit_results": [asdict(r) for r in result.audit_results],
        "summary": result.summary,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _run_generate_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """生成基金分析报告。

    参数:
        args: argparse 解析出的 generate 参数。
        stdout: 成功输出流（JSON）。
        stderr: 失败输出流。

    返回:
        成功返回 0；not_found 返回 2。
    """

    years = _parse_years(args.years)
    service = FundReadingService()

    # 检查可用年份是否 >= 3（仅在显式指定年份时检查；自动发现模式由 service 层检查）
    if years and len(set(years)) < 3:
        stderr.write(f"错误：需要至少 3 年数据，当前仅有 {len(set(years))} 年。请使用 import 命令补充导入更多年份的 PDF。\n")
        return CLASSIFIED_FAILURE_EXIT_CODE

    llm_client = None
    if getattr(args, "llm", False):
        llm_client = DeepSeekLlmClient()
    elif args.output_format != "json":
        stderr.write("⚠ 报告以模板模式生成（无 LLM 分析），使用 --llm 启用 AI 分析\n")

    result = service.generate_report(
        GenerateReportRequest(
            fund_code=args.fund_code,
            fund_name=args.fund_name,
            report_year=args.year,
            years=years,
            work_dir=Path(args.work_dir),
            output_format=args.output_format,
        ),
        llm_client=llm_client,
    )
    if result.failure is not None:
        _write_classified_failure(result.failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    output = {
        "fund_code": result.report.fund_code,
        "fund_name": result.report.fund_name,
        "report_year": result.report.report_year,
        "chapters": [
            {
                "chapter_id": c.chapter_id,
                "title": c.title,
                "content": c.content,
                "data_sources": list(c.data_sources),
            }
            for c in result.report.chapters
        ],
        "metadata": result.report.metadata,
        "output_path": result.output_path,
        "warnings": list(result.warnings),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return SUCCESS_EXIT_CODE


def _write_success_output(result: object, stdout: TextIO) -> None:
    """输出 plain text 答案、citation 和工具 trace。"""

    print("Answer:", file=stdout)
    print(getattr(result, "answer"), file=stdout)
    print("", file=stdout)
    print("Citations:", file=stdout)
    for citation in getattr(result, "citations"):
        locator = citation.locator
        parts = [
            f"document_id={citation.document_id}",
            f"fund_code={citation.fund_code}",
            f"year={citation.year}",
            f"report_type={citation.report_type}",
            f"locator_kind={locator.locator_kind.value}",
        ]
        if locator.section_ref is not None:
            parts.append(f"section_ref={locator.section_ref}")
        if locator.table_ref is not None:
            parts.append(f"table_ref={locator.table_ref}")
        if locator.page_no is not None:
            parts.append(f"page_no={locator.page_no}")
        if locator.page_range is not None:
            parts.append(f"page_range={locator.page_range[0]}-{locator.page_range[1]}")
        parts.append(f"internal_ref_available={str(locator.internal_ref_available).lower()}")
        print("- " + " ".join(parts), file=stdout)

    print("", file=stdout)
    print("Trace:", file=stdout)
    for entry in getattr(result, "tool_trace"):
        failure_code = entry.failure_code.value if entry.failure_code else ""
        print(f"- {entry.tool_name.value} {entry.result_kind} {failure_code}".rstrip(), file=stdout)


def _run_interactive_command(
    args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO
) -> int:
    """执行 interactive 多轮对话。

    参数:
        args: argparse 解析出的 interactive 参数。
        stdout: 输出流。
        stderr: 错误输出流。

    返回:
        0 正常退出，1 异常退出。
    """
    work_dir = Path(args.work_dir)
    fund_code = args.fund_code

    # 1. 解析基金代码 → 可用年份
    print(f"正在查找基金 {fund_code} 的年报…", file=stdout)
    service = FundReadingService()
    resolution = service.resolve_by_fund_code(fund_code, work_dir)

    if resolution is None:
        print(f"未找到基金 {fund_code} 的已导入年报。请先导入年报。", file=stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    print(f"基金: {resolution.fund_name} ({fund_code})", file=stdout)
    print(f"可用年份: {', '.join(str(y) for y in resolution.available_years)}", file=stdout)

    # 2. 选择年份
    default_year = resolution.available_years[-1]
    year_str = input(f"请选择年份 [{default_year}]: ").strip()
    selected_year = int(year_str) if year_str.isdigit() else default_year

    selected_doc = next((d for d in resolution.documents if d.year == selected_year), None)
    if selected_doc is None:
        print(f"年份 {selected_year} 无对应年报。", file=stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    # 3. 创建/恢复 session（通过 MinimalHost 管理生命周期）
    from fund_agent.host.minimal_host import MinimalHost
    from fund_agent.host.session_store import SessionStore
    from fund_agent.service.session_models import PinnedState, Session

    sessions_dir = work_dir / "sessions"
    session_store = SessionStore(sessions_dir)
    host = MinimalHost(session_store=session_store)

    label = getattr(args, "label", None)
    if label:
        try:
            session = host.get_session(label)
            turn_count = len(session.turns) // 2  # user+assistant 成对
            print(f"[恢复会话 '{label}'] 已有 {turn_count} 轮对话，创建于 {session.created_at[:10]}", file=stdout)
        except FileNotFoundError:
            session = host.create_session(fund_code=fund_code, label=label)
            print(f"[新建会话 '{label}']", file=stdout)
    else:
        session = host.create_session(fund_code=fund_code)

    ps = PinnedState(
        fund_code=fund_code,
        available_document_ids=tuple(d.document_id for d in resolution.documents),
        active_document_id=selected_doc.document_id,
        active_year=selected_year,
    )
    session = session.with_pinned_state(ps)
    session_store.save(session)

    # 4. REPL 循环
    from fund_agent.service.chat_service import ChatService, ChatTurnRequest
    from fund_agent.service.chat_contract import ChatTurnContract
    from fund_agent.service.prompt_composer import PromptComposer
    from fund_agent.service.scene_config import INTERACTIVE_SCENE_CONFIG
    from fund_agent.service.investment_guard import contains_investment_advice

    template_dir = Path(__file__).parent.parent / "service" / "prompts"
    prompt_composer = PromptComposer(template_dir=template_dir)
    chat_service = ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=INTERACTIVE_SCENE_CONFIG,
    )

    print(f"\n已选择 {selected_year} 年年报。输入问题开始对话，/help 查看命令，exit 退出。", file=stdout)

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。", file=stdout)
            break

        command, text = _parse_repl_input(user_input)

        if command == "exit":
            print("再见。", file=stdout)
            break
        if command == "help":
            _print_help(stdout)
            continue
        if command == "clear":
            print("\033[2J\033[H", file=stdout, end="")  # ANSI 清屏
            continue
        if command == "label":
            new_label = text.strip() if text else None
            if not new_label:
                print("用法: /label <名称>", file=stdout)
                continue
            session = Session(
                session_id=session.session_id,
                label=new_label,
                status=session.status,
                pinned_state=session.pinned_state,
                turns=session.turns,
                episode_summaries=session.episode_summaries,
                created_at=session.created_at,
            )
            session_store.set_label(session.session_id, new_label)
            session_store.save(session)
            print(f"会话标签已更新为 '{new_label}'", file=stdout)
            continue

        if text is None:
            continue

        # 投资建议预检（用户输入）
        if contains_investment_advice(text):
            print("提示：您的输入包含投资建议关键词，请注意。", file=stdout)

        # 调用 chat_turn（通过 ChatTurnContract 传递 model/runtime 覆盖）
        try:
            result = chat_service.chat_turn(
                ChatTurnRequest(
                    session_id=session.session_id,
                    user_text=text,
                ),
                contract=ChatTurnContract(
                    scene="interactive",
                    session_id=session.session_id,
                    user_text=text,
                ),
            )
        except Exception as exc:
            print(f"处理失败: {exc}", file=stderr)
            continue

        if result.investment_advice_detected:
            print("[投资建议检测] 回答已拦截。", file=stdout)

        print(result.answer, file=stdout)
        print(file=stdout)

    return SUCCESS_EXIT_CODE


def _parse_repl_input(text: str) -> tuple[str | None, str | None]:
    """解析 REPL 用户输入。

    参数:
        text: 用户输入的原始文本。

    返回:
        (command, text) 元组；command 为 None 表示普通文本，
        text 为 None 表示空白输入。
    """
    stripped = text.strip()
    if not stripped:
        return None, None

    # 内置退出命令
    if stripped.lower() in ("exit", "quit"):
        return "exit", None

    # 斜杠命令
    if stripped.startswith("/"):
        parts = stripped[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if cmd == "help":
            return "help", None
        if cmd == "clear":
            return "clear", None
        if cmd == "exit" or cmd == "quit":
            return "exit", None
        if cmd == "label":
            return "label", arg
        # 未知命令当普通文本
        return None, stripped

    # 普通对话文本
    return None, stripped


def _print_help(stdout: TextIO) -> None:
    """输出帮助信息。"""
    print("可用命令:", file=stdout)
    print("  /help      显示帮助", file=stdout)
    print("  /clear     清屏", file=stdout)
    print("  /label     设置会话标签（/label <名称>）", file=stdout)
    print("  exit, quit 退出对话", file=stdout)
    print("  其他输入    作为问题发送给 LLM", file=stdout)


def _write_classified_failure(failure: ToolFailure, stderr: TextIO) -> None:
    """输出稳定失败分类，不包含本地路径或内部 payload。"""

    print(f"failure_code={failure.code.value}", file=stderr)
    print(f"message={failure.message}", file=stderr)


if __name__ == "__main__":
    raise SystemExit(main())
