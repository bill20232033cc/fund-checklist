"""fund-checklist read CLI 的回归测试。"""

from __future__ import annotations

import io
import importlib
import json
from importlib.metadata import entry_points
from pathlib import Path

from fund_agent.cli.main import (
    CLASSIFIED_FAILURE_EXIT_CODE,
    SUCCESS_EXIT_CODE,
    UNEXPECTED_FAILURE_EXIT_CODE,
    build_parser,
    run_cli,
)
from fund_agent.fund.document_tools.constants import DOCLING_JSON_SUFFIX
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME

cli_module = importlib.import_module("fund_agent.cli.main")


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
                "text": "基金经理在本报告期内保持稳定。本章节用于检索基金经理信息。",
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
    """CLI happy path 必须串起导入、转换、store、service 和 Host/Agent。"""

    _FakeConverter.calls.clear()
    monkeypatch.setattr(cli_module, "DoclingConverter", _FakeConverter)
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


def test_cli_reuses_existing_docling_json_without_converter(monkeypatch, tmp_path: Path) -> None:
    """同 document_id 下已有 Docling JSON 时，CLI 不重复调用 converter。"""

    class _ForbiddenConverter:
        """若被调用则说明未复用既有 JSON。"""

        def __init__(self, output_root: Path) -> None:
            """构造即失败。"""

            raise AssertionError("converter should not run")

    _FakeConverter.calls.clear()
    monkeypatch.setattr(cli_module, "DoclingConverter", _FakeConverter)
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

    monkeypatch.setattr(cli_module, "DoclingConverter", _ForbiddenConverter)

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

    monkeypatch.setattr(cli_module, "LocalPdfSourceProvider", _raise_unexpected)
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
    monkeypatch.setattr(cli_module, "DoclingConverter", _FakeConverter)
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
