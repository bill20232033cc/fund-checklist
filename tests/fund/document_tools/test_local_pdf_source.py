"""本地 PDF 导入 Slice 的回归测试。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import FailureCode, ReportType, SourceKind
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.local_pdf_source import LocalPdfSourceProvider
from fund_agent.fund.document_tools.models import PdfImportRequest


def _write_pdf(path, marker: bytes = b"demo") -> bytes:
    """写入最小 PDF-like bytes，用于 Slice 1 integrity 边界测试。"""

    payload = b"%PDF-1.7\n" + marker + b"\n%%EOF\n"
    path.write_bytes(payload)
    return payload


def test_import_local_pdf_preserves_report_identity(tmp_path) -> None:
    """导入本地 PDF 后保留基金、年份、报告类型和内容身份。"""

    source_path = tmp_path / "annual.pdf"
    pdf_bytes = _write_pdf(source_path)
    expected_fingerprint = hashlib.sha256(pdf_bytes).hexdigest()
    expected_document_id = f"004393-2024-annual_report-{expected_fingerprint[:16]}"
    provider = LocalPdfSourceProvider(blob_root=tmp_path / "blob")

    result = provider.import_pdf(
        PdfImportRequest(
            path=source_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
        )
    )
    duplicate = provider.import_pdf(
        PdfImportRequest(
            path=source_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
        )
    )

    assert result.identity.fund_code == "004393"
    assert result.identity.fund_name == "安信企业价值优选混合型证券投资基金"
    assert result.identity.year == 2024
    assert result.identity.report_type is ReportType.ANNUAL_REPORT
    assert result.identity.source_kind is SourceKind.LOCAL_PDF
    assert result.identity.content_fingerprint == expected_fingerprint
    assert result.identity.document_id == expected_document_id
    assert result.identity.share_class is None
    assert result.stored_blob_ref == f"local_pdf:{expected_document_id}"
    assert provider.blob_store.read_pdf(result.stored_blob_ref) == pdf_bytes
    assert duplicate.identity.document_id == result.identity.document_id
    assert duplicate.identity.local_import_id != result.identity.local_import_id
    assert result.identity.local_import_id not in result.identity.document_id
    assert result.identity.local_import_id not in result.stored_blob_ref


def test_import_local_pdf_rejects_non_pdf_magic_bytes(tmp_path) -> None:
    """非 PDF magic bytes 必须稳定分类为 integrity_error。"""

    source_path = tmp_path / "not-a-pdf.pdf"
    source_path.write_bytes(b"not a pdf")
    provider = LocalPdfSourceProvider(blob_root=tmp_path / "blob")

    with pytest.raises(DocumentToolError) as exc_info:
        provider.import_pdf(
            PdfImportRequest(
                path=source_path,
                fund_code="004393",
                fund_name="安信企业价值优选混合型证券投资基金",
                year=2024,
            )
        )

    assert exc_info.value.code is FailureCode.INTEGRITY_ERROR


def test_import_local_pdf_uses_content_fingerprint_not_filename(tmp_path) -> None:
    """同一 PDF 改名后仍复用由内容指纹生成的 document_id。"""

    pdf_bytes = _write_pdf(tmp_path / "original.pdf", marker=b"same-content")
    renamed_path = tmp_path / "renamed-by-user.pdf"
    renamed_path.write_bytes(pdf_bytes)
    changed_path = tmp_path / "renamed-by-user-v2.pdf"
    _write_pdf(changed_path, marker=b"different-content")
    provider = LocalPdfSourceProvider(blob_root=tmp_path / "blob")

    original = provider.import_pdf(
        PdfImportRequest(
            path=tmp_path / "original.pdf",
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
        )
    )
    renamed = provider.import_pdf(
        PdfImportRequest(
            path=renamed_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
        )
    )
    changed = provider.import_pdf(
        PdfImportRequest(
            path=changed_path,
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
        )
    )

    assert renamed.identity.document_id == original.identity.document_id
    assert renamed.identity.content_fingerprint == original.identity.content_fingerprint
    assert changed.identity.document_id != original.identity.document_id
    assert "original" not in original.identity.document_id
    assert "renamed" not in renamed.identity.document_id
