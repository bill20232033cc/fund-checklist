"""17B citation 验证工具测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import Citation, Locator, ReportIdentity, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService


def _identity() -> ReportIdentity:
    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-secret-import-id",
        content_fingerprint="abc123def4567890abc123def4567890",
        document_id="004393-2024-annual_report-abc123def4567890",
    )


def _write_docling_json(path: Path) -> None:
    payload = {
        "schema_name": "docling_document",
        "version": "fake",
        "name": "sample",
        "texts": [
            {"self_ref": "#/texts/0", "label": "section_header", "prov": [{"page_no": 1}], "text": "基金经理"},
            {"self_ref": "#/texts/1", "label": "text", "prov": [{"page_no": 1}], "text": "本基金管理人为张明。"},
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 2}],
                "captions": [{"text": "基金费率表"}],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "管理费",
                        },
                    ]
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service(tmp_path: Path) -> FundDocumentToolService:
    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
    _write_docling_json(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def _citation(locator: Locator) -> Citation:
    return Citation(
        document_id=_identity().document_id,
        fund_code=_identity().fund_code,
        fund_name=_identity().fund_name,
        year=_identity().year,
        report_type=_identity().report_type,
        locator=locator,
    )


@pytest.mark.parametrize(
    ("query", "expected_kind"),
    [
        ("基金经理", LocatorKind.EXCERPT),
        ("基金费率表", LocatorKind.TABLE),
    ],
)
def test_verify_citation_excerpt_returns_excerpt(tmp_path: Path, query: str, expected_kind: LocatorKind) -> None:
    service = _service(tmp_path)
    results = service.search_document(_identity().document_id, query)
    assert not isinstance(results, ToolFailure)
    assert len(results) == 1
    hit = results[0]
    assert hit.locator.locator_kind is expected_kind

    result = service.verify_citation_excerpt(_identity().document_id, _citation(hit.locator))

    assert not isinstance(result, ToolFailure)
    assert result.locator == hit.locator
    assert result.citation.locator == hit.locator


def test_verify_citation_excerpt_rejects_identity_mismatch(tmp_path: Path) -> None:
    service = _service(tmp_path)
    results = service.search_document(_identity().document_id, "基金经理")
    assert not isinstance(results, ToolFailure)
    locator = results[0].locator

    bad_locator = Locator(
        document_id="other-document-id",
        locator_kind=locator.locator_kind,
        section_ref=locator.section_ref,
        table_ref=locator.table_ref,
        page_no=locator.page_no,
        page_range=locator.page_range,
        internal_ref=locator.internal_ref,
        internal_ref_available=locator.internal_ref_available,
    )

    result = service.verify_citation_excerpt(_identity().document_id, _citation(bad_locator))

    assert isinstance(result, ToolFailure)
    assert result.code is FailureCode.IDENTITY_MISMATCH


def test_verify_citation_excerpt_rejects_unknown_locator_kind(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bad_locator = Locator(
        document_id=_identity().document_id,
        locator_kind="unknown",
        section_ref=None,
        table_ref=None,
        page_no=None,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
    )

    result = service.verify_citation_excerpt(_identity().document_id, _citation(bad_locator))

    assert isinstance(result, ToolFailure)
    assert result.code is FailureCode.IDENTITY_MISMATCH


def test_verify_citation_excerpt_returns_not_found_for_missing_ref(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bad_locator = Locator(
        document_id=_identity().document_id,
        locator_kind=LocatorKind.SECTION,
        section_ref="section-9999",
        table_ref=None,
        page_no=None,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
    )

    result = service.verify_citation_excerpt(_identity().document_id, _citation(bad_locator))

    assert isinstance(result, ToolFailure)
    assert result.code is FailureCode.NOT_FOUND
