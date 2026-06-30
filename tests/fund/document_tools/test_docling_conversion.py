"""Docling conversion Slice 的回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import FailureCode, ReportType, SourceKind
from fund_agent.fund.document_tools.docling_converter import DoclingConverter
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.local_pdf_source import LocalPdfSourceProvider
from fund_agent.fund.document_tools.models import PdfImportRequest, ReportIdentity


SAMPLE_PDF = Path("基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf")


def _identity(document_id: str = "004393-2024-annual_report-testfingerprint") -> ReportIdentity:
    """构造测试用报告身份。"""

    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-test",
        content_fingerprint="testfingerprint",
        document_id=document_id,
    )


def test_convert_local_pdf_writes_docling_json(tmp_path, monkeypatch) -> None:
    """真实本地样本 PDF 必须通过 Docling 写出受控 JSON。"""

    cache_root = Path(".docling_cache") / "hf"
    cache_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HF_ENDPOINT", "https://huggingface.co")
    monkeypatch.setenv("HF_HOME", str(cache_root.resolve()))
    monkeypatch.setenv("XDG_CACHE_HOME", str((Path(".docling_cache") / "xdg").resolve()))
    provider = LocalPdfSourceProvider(blob_root=tmp_path / "blob")
    imported = provider.import_pdf(
        PdfImportRequest(
            path=SAMPLE_PDF,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
        )
    )
    pdf_bytes = provider.blob_store.read_pdf(imported.stored_blob_ref)
    converter = DoclingConverter(output_root=tmp_path / "docling")

    result = converter.convert_pdf(identity=imported.identity, pdf_bytes=pdf_bytes)
    store = DoclingDocumentStore(identity=imported.identity, json_path=result.json_path)

    assert result.document_id == imported.identity.document_id
    assert result.docling_json_ref == f"docling_json:{imported.identity.document_id}"
    assert result.json_path.exists()
    assert result.json_path.is_relative_to(tmp_path)
    assert result.elapsed_seconds > 0
    assert store.parser_health.readable_text_count > 0
    assert store.parser_health.section_count > 0
    payload = result.json_path.read_text(encoding="utf-8")
    assert '"texts"' in payload
    assert str(SAMPLE_PDF) not in result.docling_json_ref
    assert str(tmp_path) not in result.docling_json_ref


def test_convert_failure_returns_docling_convert_failed(tmp_path) -> None:
    """Docling API 无法转换 PDF 时必须返回 docling_convert_failed。"""

    converter = DoclingConverter(output_root=tmp_path / "docling")

    with pytest.raises(DocumentToolError) as exc_info:
        converter.convert_pdf(identity=_identity(), pdf_bytes=b"%PDF-1.7\nnot a valid pdf\n%%EOF\n")

    assert exc_info.value.code is FailureCode.DOCLING_CONVERT_FAILED
    assert "not a valid pdf" not in exc_info.value.message


def test_parser_health_fails_when_no_text_and_no_sections(tmp_path) -> None:
    """JSON 有效但无可读文本/章节索引时必须 fail-closed。"""

    json_path = tmp_path / "empty.docling.json"
    json_path.write_text('{"texts": [], "tables": []}', encoding="utf-8")

    with pytest.raises(DocumentToolError) as exc_info:
        DoclingDocumentStore(identity=_identity(), json_path=json_path)

    assert exc_info.value.code is FailureCode.PARSER_HEALTH_FAILED
