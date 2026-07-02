"""基金年报阅读工具的最小命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import ToolFailure
from fund_agent.service import FundReadingService, ReadLocalReportRequest

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
    except DocumentToolError as exc:
        _write_classified_failure(ToolFailure(code=exc.code, message=exc.message), stderr)
        return CLASSIFIED_FAILURE_EXIT_CODE
    except Exception:
        print(UNEXPECTED_FAILURE_MESSAGE, file=stderr)
        return UNEXPECTED_FAILURE_EXIT_CODE

    print(UNEXPECTED_FAILURE_MESSAGE, file=stderr)
    return UNEXPECTED_FAILURE_EXIT_CODE


def build_parser() -> argparse.ArgumentParser:
    """构造只包含 read 子命令的 argparse parser。

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
    return parser


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
