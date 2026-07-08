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
from fund_agent.fund.document_tools.persistent_repository import (
    CATALOG_FILENAME,
    FilesystemReportRepository,
)
from fund_agent.service import (
    AggregateMultiYearAnnualPerformanceRequest,
    AnnualReportDocument,
    ExtractAllocationRequest,
    ExtractFeeRatesMultiYearRequest,
    ExtractHoldingsRequest,
    FundReadingService,
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
    args = parser.parse_args(argv)
    try:
        if args.command == "read":
            return _run_read_command(args, stdout=stdout, stderr=stderr)
        if args.command == "multi-year":
            return _run_multi_year_command(args, stdout=stdout, stderr=stderr)
        if args.command == "import":
            return _run_import_command(args, stdout=stdout, stderr=stderr)
        if args.command == "holdings":
            return _run_holdings_command(args, stdout=stdout, stderr=stderr)
        if args.command == "allocation":
            return _run_allocation_command(args, stdout=stdout, stderr=stderr)
        if args.command == "fees":
            return _run_fees_command(args, stdout=stdout, stderr=stderr)
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
    import_parser.add_argument("--year-range", required=True)
    import_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    holdings_parser = subparsers.add_parser("holdings")
    holdings_parser.add_argument("--fund-code", required=True)
    holdings_parser.add_argument("--years", required=True)
    holdings_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    allocation_parser = subparsers.add_parser("allocation")
    allocation_parser.add_argument("--fund-code", required=True)
    allocation_parser.add_argument("--years", required=True)
    allocation_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)

    fees_parser = subparsers.add_parser("fees")
    fees_parser.add_argument("--fund-code", required=True)
    fees_parser.add_argument("--years", required=True)
    fees_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
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


def _parse_years(years_str: str) -> tuple[int, ...]:
    """解析逗号分隔的年度字符串为升序元组。

    参数:
        years_str: 逗号分隔的年度字符串，如 "2020,2021,2022,2023,2024"。

    返回:
        升序排列的年度元组。

    异常:
        ValueError: 年度格式不合法时抛出。
    """

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
)


def _extract_fund_name_keyword(fund_name: str) -> str:
    """从基金全称中提取关键词用于文件名匹配。

    参数:
        fund_name: 基金全称，如 "安信企业价值优选混合型证券投资基金"。

    返回:
        去除通用后缀后的关键词，如 "安信企业价值优选"。

    异常:
        ValueError: 关键词为空（基金名称全由通用后缀组成）时抛出。
    """

    keyword = fund_name
    for stop in _FUND_NAME_STOP_WORDS:
        keyword = keyword.replace(stop, "")
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

    if fund_name_keyword in filename:
        return True

    # 处理关键词被停用词分割的情况（如 "交易型开放式" 在中间）
    # 将关键词拆分为单字符，检查文件名是否包含所有字符
    # 阈值 >= 4 降低短关键词误匹配概率
    parts = [p for p in fund_name_keyword if p.strip()]
    if len(parts) >= 4:
        return all(part in filename for part in parts)

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

    service = FundReadingService()
    result = service.extract_multi_year_holdings(
        ExtractHoldingsRequest(
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


def _write_classified_failure(failure: ToolFailure, stderr: TextIO) -> None:
    """输出稳定失败分类，不包含本地路径或内部 payload。"""

    print(f"failure_code={failure.code.value}", file=stderr)
    print(f"message={failure.message}", file=stderr)


if __name__ == "__main__":
    raise SystemExit(main())
