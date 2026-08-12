"""基金年报阅读工具的最小命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
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
from fund_agent.agent.deepseek_llm import DeepSeekLlmClient, resolve_provider_model
from fund_agent.agent.stream_events import StreamEventType
from fund_agent.service import (
    AggregateMultiYearAnnualPerformanceResult,
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
        if args.command == "fix":
            return _run_fix_command(args, stdout=stdout, stderr=stderr)
        if args.command == "repair":
            return _run_repair_command(args, stdout=stdout, stderr=stderr)
        if args.command == "regenerate":
            return _run_regenerate_command(args, stdout=stdout, stderr=stderr)
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
    generate_parser.add_argument("--concurrency", type=int, default=None, help="章节生成并发数（1-8，默认 4；仅 --llm 模式生效）")
    generate_parser.add_argument("--holdings-source-fund", default="", help="关联持仓源基金代码（如 ETF 联接基金的标的 ETF 512890）")
    generate_parser.add_argument("--holdings-source-workdir", default=None, type=Path, help="关联持仓源工作目录（如 .fund_checklist_512890）")

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
    interactive_parser.add_argument("--plain", action="store_true", default=False, help="保留原始 Markdown 文本，禁用 Rich 格式化")
    interactive_parser.add_argument("--year", type=int, default=None, help="指定年报年份（默认取可用年份中最新；非交互输入自动默认）")

    fix_parser = subparsers.add_parser("fix")
    fix_parser.add_argument("--fund-code", required=True, help="基金代码")
    fix_parser.add_argument("--chapter", required=True, type=int, help="要修复的章节号（1-8）")
    fix_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
    fix_parser.add_argument("--llm", action="store_true", default=False, help="使用 LLM 执行占位符补强（需要 DEEPSEEK_API_KEY）")

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--fund-code", required=True, help="基金代码")
    repair_parser.add_argument("--year", required=True, type=int, help="报告年份")
    repair_parser.add_argument("--chapter", required=True, help="要修复的章节号，逗号分隔（如 3,5,7）")
    repair_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
    repair_parser.add_argument("--llm", action="store_true", default=False, help="使用 LLM 执行修复（需要 DEEPSEEK_API_KEY）")
    repair_parser.add_argument("--auto", action="store_true", default=False, help="基于审计分数自动选择修复策略")

    regenerate_parser = subparsers.add_parser("regenerate")
    regenerate_parser.add_argument("--fund-code", required=True, help="基金代码")
    regenerate_parser.add_argument("--year", required=True, type=int, help="报告年份")
    regenerate_parser.add_argument("--chapter", required=True, help="要重写的章节号，逗号分隔（如 3,5,7）")
    regenerate_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
    regenerate_parser.add_argument("--llm", action="store_true", default=False, help="使用 LLM 执行重写（需要 DEEPSEEK_API_KEY）")
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


def _build_aggregate_handler(work_dir: Path) -> Callable[..., AggregateMultiYearAnnualPerformanceResult]:
    """构造 interactive 场景的 aggregate_multi_year_annual_performance 回调。

    参数:
        work_dir: 现有受控 repository 工作目录。

    返回:
        handler(document_id, fund_code, requested_years, annual_report_documents,
        share_class) -> AggregateMultiYearAnnualPerformanceResult；以 catalog 重解析
        annual_report_documents（last-wins），忽略 LLM 提供的 document_id 列表
        （防幻觉 document_id 注入）。
    """

    repository = FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME,
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    service = FundReadingService()

    def handler(
        document_id: str,
        fund_code: object,
        requested_years: object,
        annual_report_documents: object,
        share_class: object,
    ) -> AggregateMultiYearAnnualPerformanceResult:
        try:
            if not isinstance(requested_years, (list, tuple)):
                return AggregateMultiYearAnnualPerformanceResult(
                    series=(),
                    failure=ToolFailure(
                        code=FailureCode.UNAVAILABLE,
                        message="multi-year annual performance 请求年度不合法",
                    ),
                )
            years = tuple(sorted(int(y) for y in requested_years))
            matching_docs = _collect_matching_docs(work_dir, str(fund_code), years)
            if not matching_docs:
                return AggregateMultiYearAnnualPerformanceResult(
                    series=(),
                    failure=ToolFailure(
                        code=FailureCode.NOT_FOUND,
                        message=f"catalog 中匹配 {fund_code} 的年报不足 3 年",
                    ),
                )
            return service.aggregate_multi_year_annual_performance(
                AggregateMultiYearAnnualPerformanceRequest(
                    fund_code=str(fund_code),
                    requested_years=years,
                    annual_report_documents=tuple(matching_docs),
                    work_dir=work_dir,
                    share_class=str(share_class) if share_class else None,
                )
            )
        except Exception:
            return AggregateMultiYearAnnualPerformanceResult(
                series=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="多年度业绩聚合暂不可用"),
            )

    return handler


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

    if getattr(args, "concurrency", None) is not None:
        if not 1 <= args.concurrency <= 8:
            stderr.write("错误：--concurrency 必须在 1..8 范围内。\n")
            return CLASSIFIED_FAILURE_EXIT_CODE
        if not getattr(args, "llm", False):
            stderr.write("⚠ --concurrency 仅 --llm 模式生效，模板模式忽略。\n")

    result = service.generate_report(
        GenerateReportRequest(
            fund_code=args.fund_code,
            fund_name=args.fund_name,
            report_year=args.year,
            years=years,
            work_dir=Path(args.work_dir),
            output_format=args.output_format,
            chapter_concurrency=args.concurrency if getattr(args, "llm", False) else None,
            holdings_source_fund=args.holdings_source_fund,
            holdings_source_workdir=Path(args.holdings_source_workdir) if args.holdings_source_workdir else None,
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
    year_arg = getattr(args, "year", None)
    if year_arg is not None:
        if year_arg not in resolution.available_years:
            print(
                f"年份 {year_arg} 不在可用年份内（可用: {', '.join(str(y) for y in resolution.available_years)}）。",
                file=stderr,
            )
            return CLASSIFIED_FAILURE_EXIT_CODE
        selected_year = year_arg
    elif not sys.stdin.isatty():
        # 管道/重定向输入：不得调用 input() 消费首行命令
        selected_year = default_year
        print(f"非交互输入，默认选择 {default_year} 年", file=stdout)
    else:
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
    # 用户输入预检与 runner 终答守卫、chat_service 第二道守卫共用 B1 单一真源
    from fund_agent.agent.llm_tool_loop import contains_investment_advice

    template_dir = Path(__file__).parent.parent / "service" / "prompts"
    prompt_composer = PromptComposer(template_dir=template_dir)

    # 构建 tool service：加载所有已解析 document 的 store
    from fund_agent.fund.document_tools.service import FundDocumentToolService
    _stores: dict[str, object] = {}
    _repo = FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME, blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    for _doc in resolution.documents:
        try:
            _stores[_doc.document_id] = _repo.load_store(_doc.document_id)
        except Exception:
            pass
    _tool_svc = FundDocumentToolService(_stores) if _stores else None

    chat_service = ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=INTERACTIVE_SCENE_CONFIG,
        tool_service=_tool_svc,
        aggregate_handler=_build_aggregate_handler(work_dir),
    )

    print(f"\n已选择 {selected_year} 年年报。输入问题开始对话，/help 查看命令，exit 退出。", file=stdout)
    print("提示：支持多轮对话，可以追问上一个问题的细节。输入 /help 查看命令。", file=stdout)

    verbose = getattr(args, "enable_tool_trace", False)
    current_model = resolve_provider_model(os.environ)

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
        if command == "history":
            _print_history(session, stdout)
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
        if command == "stats":
            turns_count = len(session.turns)
            rounds = turns_count // 2
            summaries = len(session.episode_summaries)
            print(f"会话统计:", file=stdout)
            print(f"  标签: {session.label or '无'}", file=stdout)
            print(f"  状态: {session.status}", file=stdout)
            print(f"  轮数: {rounds}", file=stdout)
            print(f"  摘要数: {summaries}", file=stdout)
            print(f"  创建时间: {session.created_at[:19] if session.created_at else '未知'}", file=stdout)
            print(f"  当前模型: {current_model}", file=stdout)
            print(f"  详细模式: {'开启' if verbose else '关闭'}", file=stdout)
            continue
        if command == "save":
            session_store.save(session)
            print("会话已保存。", file=stdout)
            continue
        if command == "export":
            fmt = (text or "json").strip().lower()
            if fmt not in ("json", "markdown", "md"):
                print("用法: /export [json|markdown]", file=stdout)
                continue
            if fmt in ("markdown", "md"):
                _export_session_markdown(session, stdout)
            else:
                _export_session_json(session, stdout)
            continue
        if command == "model":
            if text:
                current_model = text.strip()
                print(f"模型已切换为: {current_model}", file=stdout)
            else:
                print(f"当前模型: {current_model}", file=stdout)
            continue
        if command == "verbose":
            verbose = not verbose
            state = "开启" if verbose else "关闭"
            print(f"详细模式已{state}", file=stdout)
            continue
        if command == "document":
            available = session.pinned_state.available_document_ids
            if text:
                new_doc = text.strip()
                if new_doc not in available:
                    print(f"未知文档ID: {new_doc}", file=stdout)
                    print(f"可用文档: {', '.join(available) if available else '无'}", file=stdout)
                    continue
                ps = PinnedState(
                    fund_code=session.pinned_state.fund_code,
                    available_document_ids=session.pinned_state.available_document_ids,
                    active_document_id=new_doc,
                    active_year=session.pinned_state.active_year,
                )
                session = session.with_pinned_state(ps)
                session_store.save(session)
                print(f"已切换到文档: {new_doc}", file=stdout)
            else:
                active = session.pinned_state.active_document_id
                print(f"可用文档:", file=stdout)
                for doc_id in available:
                    marker = " ← 当前" if doc_id == active else ""
                    print(f"  {doc_id}{marker}", file=stdout)
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
                    model_name=current_model,
                ),
            )
        except Exception as exc:
            print(f"处理失败: {exc}", file=stderr)
            continue

        if result.investment_advice_detected:
            print("[投资建议检测] 回答已拦截。", file=stdout)
            if result.original_content:
                print(f"[被拦截原文] {result.original_content[:200]}", file=stdout)
            if result.blocked_terms:
                print(f"[触发词] {', '.join(result.blocked_terms)}", file=stdout)

        # 使用 rich Markdown 渲染输出（--plain 保留原始文本）
        use_rich = not getattr(args, "plain", False)
        rendered = render_markdown(result.answer, use_rich=use_rich)
        print(rendered, file=stdout)

        # 追问建议（分析性回答末尾）
        suggestion = _generate_follow_up_suggestion(text, result.answer)
        if suggestion:
            print(f"\n{suggestion}", file=stdout)

        if verbose and result.tool_trace:
            print(f"\n[工具调用: {', '.join(result.tool_trace)}]", file=stdout)

    return SUCCESS_EXIT_CODE


_PLACEHOLDER_RE = re.compile(r"\[(?:待补充|数据缺失|暂无数据|需补充|占位符|待补全|需人工核实|暂无)\]")


def _extract_chapter_from_markdown(md_text: str, chapter_num: int) -> str | None:
    """从 Markdown 报告中按章节号提取章节正文（1-indexed）。"""
    pattern = re.compile(r"\n---\n\n## 第 (\d+) 章：[^\n]*\n")
    matches = list(pattern.finditer(md_text))

    for i, match in enumerate(matches):
        chap_num = int(match.group(1))
        if chap_num == chapter_num:
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
            return md_text[start:end].strip()

    return None


def _run_fix_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """修复报告中指定章节的占位符。

    Wire FIX_SCENE_CONFIG -> ChatTurnContract -> ChatService for scene-aware
    context, injecting chapter content / audit feedback / chapter contract
    through PinnedState.user_constraints（chat_service._build_contributions
    透传 context slots），并用 chat_turn 的 answer 作为补强后章节正文。

    参数:
        args: argparse 解析出的 fix 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；失败返回 2。
    """
    work_dir = Path(args.work_dir)
    chapter_num = args.chapter

    reports_dir = work_dir / "reports"
    if not reports_dir.is_dir():
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message="reports 目录不存在，请先运行 generate 命令")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    pattern = f"{args.fund_code}-*-analysis.md"
    report_files = sorted(reports_dir.glob(pattern))
    if not report_files:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"未找到基金 {args.fund_code} 的分析报告")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    latest_report = report_files[-1]
    year_match = re.match(rf"{args.fund_code}-(\d{{4}})-analysis\.md", latest_report.name)
    if not year_match:
        failure = ToolFailure(code=FailureCode.SCHEMA_DRIFT, message=f"无法从文件名解析年份: {latest_report.name}")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE
    report_year = int(year_match.group(1))

    md_text = latest_report.read_text(encoding="utf-8")
    chapter_content = _extract_chapter_from_markdown(md_text, chapter_num)
    if chapter_content is None:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"未找到第 {chapter_num} 章")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    matching_docs = _collect_matching_docs(work_dir, args.fund_code, (report_year,))
    document_id = matching_docs[0].document_id if matching_docs else ""

    llm_client = DeepSeekLlmClient() if getattr(args, "llm", False) else None

    from fund_agent.fund.document_tools.service import FundDocumentToolService
    from fund_agent.host.session_store import SessionStore
    from fund_agent.service.audit_pipeline import CHAPTER_CONTRACTS, ArtifactStore
    from fund_agent.service.chat_contract import ChatTurnContract
    from fund_agent.service.chat_service import ChatService, ChatTurnRequest
    from fund_agent.service.prompt_composer import PromptComposer
    from fund_agent.service.scene_config import FIX_SCENE_CONFIG
    from fund_agent.service.session_models import PinnedState

    # 构建 workdir tool service（interactive 模式）：失败文档跳过，可为 None
    _stores: dict[str, object] = {}
    _repo = FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME,
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    for _doc in matching_docs or ():
        try:
            _stores[_doc.document_id] = _repo.load_store(_doc.document_id)
        except Exception:
            pass
    _tool_svc = FundDocumentToolService(_stores) if _stores else None

    if llm_client is None:
        print(f"第 {chapter_num} 章: 未启用 LLM（使用 --llm），跳过", file=stdout)
        return SUCCESS_EXIT_CODE

    if not document_id:
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message="未找到匹配的年报文档，无法执行占位符补强")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    template_dir = Path(__file__).parent.parent / "service" / "prompts"
    prompt_composer = PromptComposer(template_dir=template_dir)
    sessions_dir = work_dir / "sessions"
    session_store = SessionStore(sessions_dir)
    chat_service = ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=FIX_SCENE_CONFIG,
        tool_service=_tool_svc,
    )

    # 审计反馈与章节合同（镜像 regenerate 的构建方式）
    artifact_store = ArtifactStore(work_dir)
    audit_decision = artifact_store.load_audit_decision(chapter_num)
    violations = audit_decision.violations if audit_decision else ()
    audit_feedback_lines = ["## 审计违规项\n"]
    for v in violations:
        audit_feedback_lines.append(f"- [{v.code}] {v.description}")
        if v.evidence:
            audit_feedback_lines.append(f"  证据: {v.evidence}")
        if v.suggested_fix:
            audit_feedback_lines.append(f"  建议: {v.suggested_fix}")
    audit_feedback = "\n".join(audit_feedback_lines)

    contract = CHAPTER_CONTRACTS.get(chapter_num)
    chapter_contract_text = ""
    if contract:
        chapter_contract_text = "\n".join(f"- {item}" for item in contract.must_answer)

    # 创建带 user_constraints 的 session；chat_service 把三个 context slot
    # 透传进 FIX scene 的 system prompt
    session = session_store.create(
        fund_code=args.fund_code,
        label=f"fix-ch{chapter_num}",
    )
    ps = PinnedState(
        fund_code=args.fund_code,
        active_year=report_year,
        active_document_id=document_id or None,
        user_constraints={
            "chapter_content": chapter_content,
            "audit_feedback": audit_feedback,
            "chapter_contract": chapter_contract_text,
        },
    )
    session = session.with_pinned_state(ps)
    session_store.save(session)

    user_prompt = (
        f"请修复第 {chapter_num} 章中的占位符。\n\n"
        f"## 原始章节内容\n\n{chapter_content}\n\n"
        f"## 审计反馈\n\n{audit_feedback}\n\n"
        f"## 章节合同\n\n{chapter_contract_text}\n\n"
        "请直接输出补强后的完整章节正文（Markdown），不添加任何说明或前缀。"
    )

    fix_contract = ChatTurnContract(
        scene="fix",
        session_id=session.session_id,
        user_text=user_prompt,
    )

    try:
        response = chat_service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text=user_prompt),
            contract=fix_contract,
            llm_client=llm_client,
        )
    except Exception as exc:
        failure = ToolFailure(code=FailureCode.UNAVAILABLE, message=f"占位符修复失败: {exc}")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    if (
        response.investment_advice_detected
        or not response.answer.strip()
        or response.answer.startswith("LLM 处理失败")
    ):
        failure = ToolFailure(code=FailureCode.UNAVAILABLE, message="占位符修复失败")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    fixed_content = response.answer.strip()
    placeholders_before = len(_PLACEHOLDER_RE.findall(chapter_content))

    placeholders_after = len(_PLACEHOLDER_RE.findall(fixed_content))
    strengthened = placeholders_before - placeholders_after
    retained = placeholders_after

    if fixed_content and fixed_content != chapter_content:
        md_text = _replace_chapter_in_markdown(md_text, chapter_num, fixed_content)
        latest_report.write_text(md_text, encoding="utf-8")

    print(f"第 {chapter_num} 章修复完成：", file=stdout)
    print(f"补强占位符: {strengthened}", file=stdout)
    print(f"保留占位符: {retained}", file=stdout)

    return SUCCESS_EXIT_CODE


def _parse_chapters(chapters_str: str) -> list[int]:
    """Parse comma-separated chapter string into sorted unique int list."""
    return sorted({int(c.strip()) for c in chapters_str.split(",")})


def _replace_chapter_in_markdown(md_text: str, chapter_num: int, new_content: str) -> str:
    """Replace a single chapter's body content within the full Markdown report."""
    pattern = re.compile(r"\n---\n\n## 第 (\d+) 章：[^\n]*\n")
    matches = list(pattern.finditer(md_text))

    for i, match in enumerate(matches):
        chap_num = int(match.group(1))
        if chap_num == chapter_num:
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
            return md_text[:start] + new_content + "\n\n" + md_text[end:]

    return md_text


def _run_repair_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """基于审计产物修复报告中指定章节的违规项。

    Wire REPAIR_SCENE_CONFIG -> ChatTurnContract -> ChatService for scene-aware
    context, then use ChapterRepairer for plan generation + patch application.

    参数:
        args: argparse 解析出的 repair 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；失败返回 2。
    """
    if getattr(args, "auto", False):
        return _run_auto_fix(args, stdout=stdout, stderr=stderr)

    work_dir = Path(args.work_dir)
    chapter_ids = _parse_chapters(args.chapter)

    # 查找报告文件
    reports_dir = work_dir / "reports"
    report_path = reports_dir / f"{args.fund_code}-{args.year}-analysis.md"
    if not report_path.is_file():
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"未找到报告: {report_path.name}")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    md_text = report_path.read_text(encoding="utf-8")

    # 初始化 LLM 客户端
    llm_client = DeepSeekLlmClient() if args.llm else None

    # Wire REPAIR_SCENE_CONFIG -> ChatTurnContract -> ChatService
    from fund_agent.host.session_store import SessionStore
    from fund_agent.service.chat_service import ChatService
    from fund_agent.service.chat_contract import ChatTurnContract
    from fund_agent.service.prompt_composer import PromptComposer
    from fund_agent.service.scene_config import REPAIR_SCENE_CONFIG
    from fund_agent.service.audit_pipeline import (
        CHAPTER_CONTRACTS,
        ArtifactStore,
        ChapterRepairer,
    )

    template_dir = Path(__file__).parent.parent / "service" / "prompts"
    prompt_composer = PromptComposer(template_dir=template_dir)
    sessions_dir = work_dir / "sessions"
    session_store = SessionStore(sessions_dir)
    chat_service = ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=REPAIR_SCENE_CONFIG,
        tool_service=None,
    )

    artifact_store = ArtifactStore(work_dir)

    before_scores: dict[int, float | None] = {}
    after_scores: dict[int, float | None] = {}
    repaired_count = 0
    skipped_count = 0

    for chapter_id in chapter_ids:
        chapter_content = _extract_chapter_from_markdown(md_text, chapter_id)
        if chapter_content is None:
            print(f"第 {chapter_id} 章: 未找到，跳过", file=stdout)
            skipped_count += 1
            continue

        audit_decision = artifact_store.load_audit_decision(chapter_id)
        before_score = audit_decision.score if audit_decision else None
        violations = audit_decision.violations if audit_decision else ()
        before_scores[chapter_id] = before_score

        if not violations:
            print(f"第 {chapter_id} 章: 无违规项 (score={before_score})，跳过", file=stdout)
            after_scores[chapter_id] = before_score
            skipped_count += 1
            continue

        contract = CHAPTER_CONTRACTS.get(chapter_id)
        if contract is None:
            print(f"第 {chapter_id} 章: 章节合同未找到，跳过", file=stdout)
            skipped_count += 1
            continue

        if llm_client is None:
            print(f"第 {chapter_id} 章: 未启用 LLM（使用 --llm），跳过", file=stdout)
            skipped_count += 1
            continue

        # Create repair contract aligned with scene config
        repair_contract = ChatTurnContract(
            scene="repair",
            session_id=f"repair-{args.fund_code}-{args.year}-ch{chapter_id}",
            user_text=f"修复章节 {chapter_id}",
        )

        repairer = ChapterRepairer(
            llm_client=llm_client,
            chapter_id=chapter_id,
            chapter_content=chapter_content,
            data_table="",
            contract=contract,
            violations=violations,
        )

        plan = repairer.generate_repair_plan()
        artifact_store.save_repair_plan(plan)

        if plan.strategy == "patch":
            new_content = repairer.apply_patch(plan)
            md_text = _replace_chapter_in_markdown(md_text, chapter_id, new_content)
            repaired_count += 1
            after_scores[chapter_id] = None  # would need re-audit for true after score
            print(f"第 {chapter_id} 章: 已修复 ({len(plan.actions)} 个动作, score={before_score})", file=stdout)
        elif plan.strategy == "regenerate":
            print(f"第 {chapter_id} 章: 需重新生成 (strategy=regenerate)，当前仅支持 patch", file=stdout)
            after_scores[chapter_id] = before_score
            skipped_count += 1
        else:
            print(f"第 {chapter_id} 章: 无需修复 (strategy={plan.strategy})", file=stdout)
            after_scores[chapter_id] = before_score
            skipped_count += 1

    # 写回报告
    if repaired_count > 0:
        report_path.write_text(md_text, encoding="utf-8")
        print(f"\n已更新报告: {report_path}", file=stdout)

    # 输出审计分数对比
    print("\n修复前后审计分数对比:", file=stdout)
    for chapter_id in chapter_ids:
        before = before_scores.get(chapter_id)
        after = after_scores.get(chapter_id)
        before_str = f"{before:.1f}" if before is not None else "N/A"
        after_str = f"{after:.1f}" if after is not None else "N/A"
        print(f"  第 {chapter_id} 章: {before_str} → {after_str}", file=stdout)

    print(f"\n修复: {repaired_count} 章, 跳过: {skipped_count} 章", file=stdout)
    return SUCCESS_EXIT_CODE


def _run_auto_fix(
    args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO
) -> int:
    """基于审计分数自动选择修复策略（--auto 模式）。

    对指定章节加载审计决定，按分数和违规严重度自动选择 skip/repair/regenerate，
    执行修复后增量重审，PATCH/REGENERATE 各最多 3 次。

    参数:
        args: argparse 解析出的 repair --auto 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；失败返回 2。
    """

    from fund_agent.service.audit_pipeline import (
        CHAPTER_CONTRACTS,
        ArtifactStore,
        ChapterProcessState,
        ChapterRepairer,
        ProgrammaticAuditor,
        SCORE_PASS,
        SCORE_PATCH,
        select_repair_strategy,
    )
    from fund_agent.service.chapter_generator import (
        LLM_ANALYSIS_PROMPTS,
        LLM_CHAPTER_SYSTEM_PROMPT,
    )

    work_dir = Path(args.work_dir)
    chapter_ids = _parse_chapters(args.chapter)

    reports_dir = work_dir / "reports"
    report_path = reports_dir / f"{args.fund_code}-{args.year}-analysis.md"
    if not report_path.is_file():
        failure = ToolFailure(
            code=FailureCode.NOT_FOUND, message=f"未找到报告: {report_path.name}"
        )
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    md_text = report_path.read_text(encoding="utf-8")
    llm_client = DeepSeekLlmClient() if args.llm else None
    artifact_store = ArtifactStore(work_dir)

    results: dict[int, dict] = {}
    modified = False

    for chapter_id in chapter_ids:
        state = ChapterProcessState(chapter_id=chapter_id)

        chapter_content = _extract_chapter_from_markdown(md_text, chapter_id)
        if chapter_content is None:
            print(f"第 {chapter_id} 章: 未找到，跳过", file=stdout)
            state.status = "skipped"
            results[chapter_id] = {"strategy": "skip", "reason": "章节未找到", "status": "skipped"}
            continue

        decision = artifact_store.load_audit_decision(chapter_id)
        strategy, reason = select_repair_strategy(decision)

        print(f"第 {chapter_id} 章: strategy={strategy} | {reason}", file=stdout)

        if strategy == "skip":
            state.status = "passed"
            results[chapter_id] = {
                "strategy": strategy, "reason": reason,
                "final_score": decision.score if decision else None, "status": "passed",
            }
            continue

        if llm_client is None:
            print(f"  未启用 LLM（使用 --llm），跳过执行", file=stdout)
            state.status = "skipped"
            results[chapter_id] = {
                "strategy": strategy, "reason": reason, "status": "skipped_no_llm",
            }
            continue

        contract = CHAPTER_CONTRACTS.get(chapter_id)
        if contract is None:
            print(f"  章节合同未找到，跳过", file=stdout)
            state.status = "skipped"
            results[chapter_id] = {"strategy": strategy, "reason": "合同缺失", "status": "skipped"}
            continue

        # 修复循环：PATCH/REGENERATE + 增量重审
        current_strategy = strategy
        current_violations = decision.violations if decision else ()
        final_score = decision.score if decision else 0.0

        while True:
            if current_strategy == "repair":
                if not state.can_patch():
                    if state.can_regenerate():
                        print(f"  PATCH 次数用尽，降级为 regenerate", file=stdout)
                        current_strategy = "regenerate"
                        continue
                    print(f"  PATCH/REGENERATE 次数均已用尽，标记降级通过", file=stdout)
                    state.status = "passed_with_degradation"
                    break

                state.patch_attempts += 1
                repairer = ChapterRepairer(
                    llm_client, chapter_id, chapter_content, "",
                    contract, current_violations,
                )
                plan = repairer.generate_repair_plan()
                artifact_store.save_repair_plan(plan)

                if plan.strategy == "patch":
                    chapter_content = repairer.apply_patch(plan)
                    md_text = _replace_chapter_in_markdown(md_text, chapter_id, chapter_content)
                    modified = True
                    print(
                        f"  PATCH #{state.patch_attempts}: {len(plan.actions)} 个动作",
                        file=stdout,
                    )
                else:
                    print(
                        f"  PATCH #{state.patch_attempts}: LLM 判断需 regenerate，切换策略",
                        file=stdout,
                    )
                    current_strategy = "regenerate"
                    continue

            elif current_strategy == "regenerate":
                if not state.can_regenerate():
                    if state.can_patch():
                        print(f"  REGENERATE 次数用尽，降级为 repair", file=stdout)
                        current_strategy = "repair"
                        continue
                    print(f"  REGENERATE 次数用尽，标记降级通过", file=stdout)
                    state.status = "passed_with_degradation"
                    break

                state.regenerate_attempts += 1
                new_content = _llm_regenerate_chapter(
                    llm_client, chapter_id, chapter_content,
                    current_violations, contract,
                )
                if new_content:
                    chapter_content = new_content
                    md_text = _replace_chapter_in_markdown(md_text, chapter_id, chapter_content)
                    modified = True
                    print(f"  REGENERATE #{state.regenerate_attempts}: 完成", file=stdout)
                else:
                    print(f"  REGENERATE #{state.regenerate_attempts}: LLM 调用失败", file=stdout)
                    if state.can_patch():
                        current_strategy = "repair"
                        continue
                    state.status = "passed_with_degradation"
                    break

            # 增量重审（程序审计）
            prog_auditor = ProgrammaticAuditor(chapter_id, chapter_content, "", contract)
            prog_score, prog_violations = prog_auditor.audit()
            state.current_score = prog_score
            current_violations = prog_violations

            if prog_score >= SCORE_PASS:
                print(f"  重审: score={prog_score:.1f} >= {SCORE_PASS} → pass", file=stdout)
                state.status = "passed"
                final_score = prog_score
                break
            elif prog_score >= SCORE_PATCH:
                print(f"  重审: score={prog_score:.1f}，继续修复", file=stdout)
                if state.can_patch():
                    current_strategy = "repair"
                elif state.can_regenerate():
                    current_strategy = "regenerate"
                else:
                    state.status = "passed_with_degradation"
                    final_score = prog_score
                    break
            else:
                print(f"  重审: score={prog_score:.1f} < {SCORE_PATCH}，需重新生成", file=stdout)
                if state.can_regenerate():
                    current_strategy = "regenerate"
                elif state.can_patch():
                    current_strategy = "repair"
                else:
                    state.status = "passed_with_degradation"
                    final_score = prog_score
                    break

        results[chapter_id] = {
            "strategy": strategy,
            "reason": reason,
            "final_score": final_score,
            "patch_attempts": state.patch_attempts,
            "regenerate_attempts": state.regenerate_attempts,
            "status": state.status,
        }

    # 写回报告
    if modified:
        report_path.write_text(md_text, encoding="utf-8")
        print(f"\n已更新报告: {report_path}", file=stdout)

    # 输出汇总
    print("\n=== 自动修复结果 ===", file=stdout)
    for chapter_id in chapter_ids:
        r = results.get(chapter_id, {})
        status = r.get("status", "unknown")
        score = r.get("final_score")
        score_str = f"{score:.1f}" if score is not None else "N/A"
        strategy = r.get("strategy", "?")
        patches = r.get("patch_attempts", 0)
        regens = r.get("regenerate_attempts", 0)
        print(
            f"  第 {chapter_id} 章: strategy={strategy} → {status} "
            f"(score={score_str}, patch={patches}, regen={regens})",
            file=stdout,
        )

    return SUCCESS_EXIT_CODE


def _llm_regenerate_chapter(
    llm_client: object,
    chapter_id: int,
    chapter_content: str,
    violations: tuple,
    contract: object,
) -> str | None:
    """使用 LLM 重新生成章节分析内容。

    保留原有数据表格，仅重新生成 ## 分析 部分。

    参数:
        llm_client: LLM 客户端。
        chapter_id: 章节编号。
        chapter_content: 完整章节 Markdown。
        violations: 审计违规项列表。
        contract: 章节合同。

    返回:
        重新生成后的完整章节内容；失败返回 None。
    """

    from fund_agent.service.chapter_generator import (
        LLM_ANALYSIS_PROMPTS,
        LLM_CHAPTER_SYSTEM_PROMPT,
    )

    analysis_prompt = LLM_ANALYSIS_PROMPTS.get(chapter_id)
    if not analysis_prompt:
        return None

    # 提取数据表格（## 分析 之前的部分）
    parts = chapter_content.split("## 分析", 1)
    data_table = parts[0].strip() if len(parts) > 1 else chapter_content

    # 构建审计反馈
    feedback_lines = []
    for v in violations:
        line = f"- [{v.code}] {v.description}"
        if v.suggested_fix:
            line += f"（建议: {v.suggested_fix}）"
        feedback_lines.append(line)
    audit_feedback = "\n".join(feedback_lines) if feedback_lines else "无违规项"

    user_prompt = (
        f"## 数据表格\n\n{data_table}\n\n"
        f"## 审计违规项（必须修复）\n\n{audit_feedback}\n\n"
        f"## 分析要求\n\n{analysis_prompt}\n\n"
        f"请重新生成 ## 分析 部分的完整内容，修复所有审计违规项。"
    )

    try:
        analysis = llm_client.generate_text(
            system_prompt=LLM_CHAPTER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        if not analysis or not isinstance(analysis, str):
            return None
        return f"{data_table}\n\n## 分析\n\n{analysis}"
    except Exception:
        return None


def _run_regenerate_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    """基于审计反馈重新生成报告中指定章节。

    Wire REGENERATE_SCENE_CONFIG -> ChatTurnContract -> ChatService for scene-aware
    context, injecting audit violations as prompt context.

    参数:
        args: argparse 解析出的 regenerate 参数。
        stdout: 成功输出流。
        stderr: 失败输出流。

    返回:
        成功返回 0；失败返回 2。
    """
    work_dir = Path(args.work_dir)
    chapter_ids = _parse_chapters(args.chapter)

    reports_dir = work_dir / "reports"
    report_path = reports_dir / f"{args.fund_code}-{args.year}-analysis.md"
    if not report_path.is_file():
        failure = ToolFailure(code=FailureCode.NOT_FOUND, message=f"未找到报告: {report_path.name}")
        _write_classified_failure(failure, stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE

    md_text = report_path.read_text(encoding="utf-8")

    llm_client = DeepSeekLlmClient(temperature=0.3) if args.llm else None

    from fund_agent.host.session_store import SessionStore
    from fund_agent.service.chat_service import ChatService, ChatTurnRequest
    from fund_agent.service.chat_contract import ChatTurnContract
    from fund_agent.service.prompt_composer import PromptComposer
    from fund_agent.service.scene_config import REGENERATE_SCENE_CONFIG
    from fund_agent.service.audit_pipeline import (
        CHAPTER_CONTRACTS,
        ArtifactStore,
    )
    from fund_agent.service.session_models import PinnedState

    template_dir = Path(__file__).parent.parent / "service" / "prompts"
    prompt_composer = PromptComposer(template_dir=template_dir)
    sessions_dir = work_dir / "sessions"
    session_store = SessionStore(sessions_dir)
    chat_service = ChatService(
        session_store=session_store,
        prompt_composer=prompt_composer,
        scene_config=REGENERATE_SCENE_CONFIG,
        tool_service=None,
    )

    artifact_store = ArtifactStore(work_dir)

    before_scores: dict[int, float | None] = {}
    after_scores: dict[int, float | None] = {}
    regenerated_count = 0
    skipped_count = 0

    for chapter_id in chapter_ids:
        chapter_content = _extract_chapter_from_markdown(md_text, chapter_id)
        if chapter_content is None:
            print(f"第 {chapter_id} 章: 未找到，跳过", file=stdout)
            skipped_count += 1
            continue

        audit_decision = artifact_store.load_audit_decision(chapter_id)
        before_score = audit_decision.score if audit_decision else None
        violations = audit_decision.violations if audit_decision else ()
        before_scores[chapter_id] = before_score

        if not violations:
            print(f"第 {chapter_id} 章: 无违规项 (score={before_score})，跳过", file=stdout)
            after_scores[chapter_id] = before_score
            skipped_count += 1
            continue

        if llm_client is None:
            print(f"第 {chapter_id} 章: 未启用 LLM（使用 --llm），跳过", file=stdout)
            skipped_count += 1
            continue

        # Build audit feedback from violations
        audit_feedback_lines = ["## 审计违规项\n"]
        for v in violations:
            audit_feedback_lines.append(f"- [{v.code}] {v.description}")
            if v.evidence:
                audit_feedback_lines.append(f"  证据: {v.evidence}")
            if v.suggested_fix:
                audit_feedback_lines.append(f"  建议: {v.suggested_fix}")
        audit_feedback = "\n".join(audit_feedback_lines)

        # Build chapter contract text
        contract = CHAPTER_CONTRACTS.get(chapter_id)
        chapter_contract_text = ""
        if contract:
            chapter_contract_text = "\n".join(
                f"- {item}" for item in contract.must_answer
            )

        # Create session with regenerate context in user_constraints
        session = session_store.create(
            fund_code=args.fund_code,
            label=f"regenerate-ch{chapter_id}",
        )
        ps = PinnedState(
            fund_code=args.fund_code,
            active_year=args.year,
            user_constraints={
                "chapter_content": chapter_content,
                "audit_feedback": audit_feedback,
                "chapter_contract": chapter_contract_text,
            },
        )
        session = session.with_pinned_state(ps)
        session_store.save(session)

        # Build user prompt for regeneration
        user_prompt = (
            f"请基于以下审计反馈，重新生成第 {chapter_id} 章的完整内容。\n\n"
            f"## 原始章节内容\n\n{chapter_content}\n\n"
            f"## 审计反馈\n\n{audit_feedback}\n\n"
            f"## 章节合同\n\n{chapter_contract_text}\n\n"
            "请重新生成完整的章节内容（包含数据表格和分析部分），"
            "修复所有审计违规项。"
        )

        regenerate_contract = ChatTurnContract(
            scene="regenerate",
            session_id=session.session_id,
            user_text=user_prompt,
        )

        try:
            response = chat_service.chat_turn(
                ChatTurnRequest(
                    session_id=session.session_id,
                    user_text=user_prompt,
                ),
                contract=regenerate_contract,
            )
            new_content = response.answer
        except Exception as exc:
            print(f"第 {chapter_id} 章: 重新生成失败 ({exc})", file=stderr)
            after_scores[chapter_id] = before_score
            skipped_count += 1
            continue

        md_text = _replace_chapter_in_markdown(md_text, chapter_id, new_content)
        regenerated_count += 1
        after_scores[chapter_id] = None  # would need re-audit for true after score
        print(f"第 {chapter_id} 章: 已重新生成 (score={before_score})", file=stdout)

    # Write back report
    if regenerated_count > 0:
        report_path.write_text(md_text, encoding="utf-8")
        print(f"\n已更新报告: {report_path}", file=stdout)

    # Output audit score comparison
    print("\n重写前后审计分数对比:", file=stdout)
    for chapter_id in chapter_ids:
        before = before_scores.get(chapter_id)
        after = after_scores.get(chapter_id)
        before_str = f"{before:.1f}" if before is not None else "N/A"
        after_str = f"{after:.1f}" if after is not None else "N/A"
        print(f"  第 {chapter_id} 章: {before_str} → {after_str}", file=stdout)

    print(f"\n重写: {regenerated_count} 章, 跳过: {skipped_count} 章", file=stdout)
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

        known_commands = {
            "help", "clear", "exit", "quit", "label",
            "stats", "save", "export", "model", "verbose", "document", "history",
        }
        if cmd in known_commands:
            # 统一 exit/quit 为 exit
            if cmd in ("exit", "quit"):
                return "exit", None
            return cmd, arg
        # 未知命令当普通文本
        return None, stripped

    # 普通对话文本
    return None, stripped


def _generate_follow_up_suggestion(question: str, answer: str) -> str | None:
    """基于当前查询上下文生成追问建议。"""
    if len(answer) < 200:
        return None
    keywords = {
        "经理": "您可以追问：这位基金经理的从业经历、管理其他基金的情况、或任职以来的业绩表现。",
        "持仓": "您可以追问：重仓股的变化趋势、行业集中度、或与基准的偏离情况。",
        "业绩": "您可以追问：与同类基金对比、不同时间区间的表现、或风险调整后收益。",
        "费率": "您可以追问：费率变动原因、与同类基金对比、或对长期收益的影响。",
        "配置": "您可以追问：资产配置变化趋势、仓位调整逻辑、或与市场环境的匹配度。",
        "风险": "您可以追问：最大回撤、波动率、或与基准的风险对比。",
        "债券": "您可以追问：信用评级分布、久期策略、或利率风险管理。",
    }
    for keyword, suggestion in keywords.items():
        if keyword in question:
            return suggestion
    return "您可以追问：请求更详细的数据、对比其他年份、或深入了解某个具体方面。"


def _print_history(session: object, stdout: TextIO) -> None:
    """显示最近 10 轮对话摘要（角色 + 内容前 80 字符 + 时间）。"""
    turns = getattr(session, "turns", ())
    if not turns:
        print("暂无对话历史。", file=stdout)
        return

    recent = turns[-20:]  # 最多 20 个 turn = 10 轮
    max_rounds = min(len(recent) // 2 + (1 if len(recent) % 2 else 0), 10)
    print(f"\n对话历史（最近 {max_rounds} 轮）:", file=stdout)
    idx = 1
    for i in range(0, len(recent), 2):
        user_turn = recent[i]
        asst_turn = recent[i + 1] if i + 1 < len(recent) else None
        user_content = user_turn.content[:80] + "..." if len(user_turn.content) > 80 else user_turn.content
        ts = getattr(user_turn, "timestamp", "")[:19]
        print(f"  {idx}. [用户] {user_content} ({ts})", file=stdout)
        if asst_turn:
            asst_content = asst_turn.content[:80] + "..." if len(asst_turn.content) > 80 else asst_turn.content
            ts_a = getattr(asst_turn, "timestamp", "")[:19]
            print(f"     [助手] {asst_content} ({ts_a})", file=stdout)
        idx += 1
        if idx > 10:
            break


def _print_help(stdout: TextIO) -> None:
    """输出帮助信息。"""
    print("可用命令:", file=stdout)
    print("  /help       显示帮助", file=stdout)
    print("  /history    显示最近 10 轮对话摘要", file=stdout)
    print("  /clear      清屏", file=stdout)
    print("  /document   切换或列出可用年报文档（/document [文档ID]）", file=stdout)
    print("  /label      设置会话标签（/label <名称>）", file=stdout)
    print("  /stats      显示会话统计信息", file=stdout)
    print("  /save       手动保存当前会话", file=stdout)
    print("  /export     导出会话（/export [json|markdown]）", file=stdout)
    print("  /model      查看或切换模型（/model [模型名]）", file=stdout)
    print("  /verbose    切换详细模式（显示工具调用详情）", file=stdout)
    print("  exit, quit  退出对话", file=stdout)
    print("  其他输入     作为问题发送给 LLM", file=stdout)


def _write_classified_failure(failure: ToolFailure, stderr: TextIO) -> None:
    """输出稳定失败分类，不包含本地路径或内部 payload。"""

    print(f"failure_code={failure.code.value}", file=stderr)
    print(f"message={failure.message}", file=stderr)


_MD_TABLE_ROW_RE = re.compile(r"\|.+")

_MD_TABLE_SEP_RE = re.compile(
    r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$"
)


def _split_table_row(row: str) -> list[str]:
    """Split a markdown table row into cells, stripping surrounding whitespace."""
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _parse_separator_alignment(cell: str) -> str:
    """Return Rich-compatible justify string from a separator cell like ':---:'."""
    c = cell.strip()
    if c.startswith(":") and c.endswith(":"):
        return "center"
    if c.endswith(":"):
        return "right"
    return "left"


def _try_extract_table(lines: list[str], start: int) -> tuple[list[str], int] | None:
    """Try to parse a markdown table starting at the given line index.

    Returns (table_lines, consumed_count) or None.
    """
    if start >= len(lines) - 1:
        return None

    header = lines[start]
    if not _MD_TABLE_ROW_RE.match(header):
        return None

    sep = lines[start + 1]
    if not _MD_TABLE_SEP_RE.match(sep):
        return None

    header_cells = _split_table_row(header)
    sep_cells = _split_table_row(sep)
    if len(header_cells) < 2 or len(header_cells) != len(sep_cells):
        return None

    # Separator cells must consist only of :, -, and whitespace
    for cell in sep_cells:
        if cell and not re.match(r"^:?-+:?$", cell):
            return None

    table_lines = [header, sep]
    col_count = len(header_cells)
    j = start + 2

    while j < len(lines):
        row = lines[j]
        if _MD_TABLE_ROW_RE.match(row):
            row_cells = _split_table_row(row)
            if len(row_cells) == col_count:
                table_lines.append(row)
                j += 1
                continue
        if row.strip() == "":
            # skip blank line within table
            j += 1
            continue
        break

    if len(table_lines) < 3:
        return None  # need at least header + sep + 1 data row

    return table_lines, j - start


def _build_rich_table(md_table_lines: list[str]) -> "Table":
    """Convert markdown table lines into a Rich Table with borders and alignment."""
    from rich.table import Table
    from rich import box

    headers = _split_table_row(md_table_lines[0])
    sep_cells = _split_table_row(md_table_lines[1])
    data = [_split_table_row(line) for line in md_table_lines[2:]]
    col_count = len(headers)

    # Pad shorter data rows to match header column count
    for row in data:
        while len(row) < col_count:
            row.append("")

    table = Table(
        show_header=True,
        header_style="bold",
        box=box.ROUNDED,
        expand=False,
        padding=(0, 1),
    )

    for i, (header, sep) in enumerate(zip(headers, sep_cells)):
        justify = _parse_separator_alignment(sep)
        table.add_column(header, justify=justify)

    for row in data:
        table.add_row(*row)

    return table


def _split_markdown_by_table(text: str) -> list[tuple[bool, str]]:
    """Split markdown text into (is_table, content) segments."""
    lines = text.split("\n")
    segments: list[tuple[bool, str]] = []
    i = 0
    buf: list[str] = []

    while i < len(lines):
        result = _try_extract_table(lines, i)
        if result:
            if buf:
                segments.append((False, "\n".join(buf)))
                buf = []
            table_lines, consumed = result
            segments.append((True, "\n".join(table_lines)))
            i += consumed
        else:
            buf.append(lines[i])
            i += 1

    if buf:
        segments.append((False, "\n".join(buf)))

    return segments


def render_markdown(text: str, *, use_rich: bool = True) -> str:
    """将 Markdown 文本渲染为终端可显示的字符串。

    检测 Markdown 表格并转换为 Rich Table（边框、表头粗体、列对齐），
    其余内容使用 Rich Markdown 渲染（粗体、斜体、代码块等）。

    参数:
        text: Markdown 格式文本。
        use_rich: True 时使用 rich 库渲染；False 时返回原文。

    返回:
        渲染后的字符串（含 ANSI 转义序列）。
    """
    if not text:
        return ""
    if not use_rich:
        return text
    try:
        from rich.console import Console
        from rich.markdown import Markdown

        console = Console(force_terminal=True, color_system="auto")

        with console.capture() as capture:
            segments = _split_markdown_by_table(text)
            for is_table, content in segments:
                if is_table:
                    table = _build_rich_table(content.split("\n"))
                    console.print(table)
                elif content.strip():
                    md = Markdown(content, code_theme="monokai")
                    console.print(md)
        return capture.get()
    except ImportError:
        return text


def _export_session_json(session: object, stdout: TextIO) -> None:
    """导出会话为 JSON 格式。

    参数:
        session: Session 对象。
        stdout: 输出流。
    """
    from dataclasses import asdict as _asdict

    turns_data = []
    for t in getattr(session, "turns", ()):
        turns_data.append({
            "role": t.role,
            "content": t.content,
            "timestamp": getattr(t, "timestamp", None),
        })
    data = {
        "session_id": getattr(session, "session_id", ""),
        "label": getattr(session, "label", None),
        "turns": turns_data,
    }
    print(json.dumps(data, ensure_ascii=False, indent=2), file=stdout)


def _export_session_markdown(session: object, stdout: TextIO) -> None:
    """导出会话为 Markdown 格式。

    参数:
        session: Session 对象。
        stdout: 输出流。
    """
    label = getattr(session, "label", "未命名") or "未命名"
    sid = getattr(session, "session_id", "")
    print(f"# 会话: {label}", file=stdout)
    print(f"session_id: {sid}", file=stdout)
    print(file=stdout)
    for t in getattr(session, "turns", ()):
        role_label = "用户" if t.role == "user" else "助手"
        print(f"## {role_label}", file=stdout)
        print(file=stdout)
        print(t.content, file=stdout)
        print(file=stdout)


if __name__ == "__main__":
    raise SystemExit(main())
