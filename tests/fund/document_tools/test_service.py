"""FundDocumentToolService Slice 的回归测试。"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import Locator, ReportIdentity, SearchMatchKind, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService


def _identity() -> ReportIdentity:
    """构造测试用报告身份。"""

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
    """写入最小 Docling-shaped JSON，用于 service 行为测试。"""

    table_cells = [
        {
            "start_row_offset_idx": 0,
            "end_row_offset_idx": 1,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
            "text": "项目",
        },
        {
            "start_row_offset_idx": 0,
            "end_row_offset_idx": 1,
            "start_col_offset_idx": 1,
            "end_col_offset_idx": 2,
            "text": "内容",
        },
        {
            "start_row_offset_idx": 1,
            "end_row_offset_idx": 2,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
            "text": "基金名称",
        },
        {
            "start_row_offset_idx": 1,
            "end_row_offset_idx": 2,
            "start_col_offset_idx": 1,
            "end_col_offset_idx": 2,
            "text": "安信企业价值优选混合型证券投资基金",
        },
        {
            "start_row_offset_idx": 2,
            "end_row_offset_idx": 3,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
            "text": "表格行专属词",
        },
        {
            "start_row_offset_idx": 2,
            "end_row_offset_idx": 3,
            "start_col_offset_idx": 1,
            "end_col_offset_idx": 2,
            "text": "行内证据",
        },
    ]
    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 重要提示",
                "level": 1,
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理在本报告期内保持稳定。本章节用于检索基金经理信息。",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "§2 基金简介",
                "level": 1,
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "基金产品说明与托管人信息。",
                "prov": [{"page_no": 2}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 2, "bbox": {"l": 10, "t": 20, "r": 30, "b": 40}}],
                "captions": [{"text": "表格标题专属词"}],
                "data": {
                    "table_cells": table_cells
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service(tmp_path) -> FundDocumentToolService:
    """构造带单文档 registry 的 service。"""

    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
    _write_docling_json(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def test_list_reports_returns_safe_source_summary(tmp_path) -> None:
    """list_reports 必须返回不含 local_import_id 和本地路径的安全摘要。"""

    reports = _service(tmp_path).list_reports(fund_code="004393", year=2024)

    assert not isinstance(reports, ToolFailure)
    assert len(reports) == 1
    report = reports[0]
    rendered = str(asdict(report))
    assert report.document_id == _identity().document_id
    assert report.source_summary == "local_pdf:sha256:abc123def4567890"
    assert report.content_fingerprint == _identity().content_fingerprint
    assert _identity().local_import_id not in rendered
    assert str(tmp_path) not in rendered
    assert ".docling.json" not in rendered


def test_read_section_redacts_local_paths(tmp_path) -> None:
    """read_section 输出不得包含 store 内部 JSON 路径或 parser private payload。"""

    service = _service(tmp_path)
    sections = service.list_sections(_identity().document_id)
    assert not isinstance(sections, ToolFailure)

    content = service.read_section(_identity().document_id, sections[0].section_ref)

    assert not isinstance(content, ToolFailure)
    rendered = str(asdict(content))
    assert "基金经理" in content.text
    assert str(tmp_path) not in rendered
    assert ".docling.json" not in rendered
    assert "schema_name" not in rendered


def test_search_document_returns_citation_and_locator(tmp_path) -> None:
    """search_document 必须返回 citation、section_ref 和 excerpt locator。"""

    service = _service(tmp_path)
    results = service.search_document(_identity().document_id, "基金经理")

    assert not isinstance(results, ToolFailure)
    assert len(results) == 1
    hit = results[0]
    excerpt = service.get_excerpt(_identity().document_id, hit.locator)
    assert hit.section_ref == "section-0000"
    assert hit.locator.locator_kind is LocatorKind.EXCERPT
    assert hit.locator.section_ref == "section-0000"
    assert hit.match_kind is SearchMatchKind.SECTION_TEXT
    assert hit.table_ref is None
    assert hit.citation.document_id == _identity().document_id
    assert hit.citation.locator == hit.locator
    assert "基金经理" in hit.excerpt
    assert not isinstance(excerpt, ToolFailure)
    assert excerpt.locator == hit.locator
    assert excerpt.citation.locator == hit.locator


def test_search_document_returns_table_backed_caption_result(tmp_path) -> None:
    """search_document 只命中 table caption 时返回 table_ref、locator 和 citation。"""

    service = _service(tmp_path)
    results = service.search_document(_identity().document_id, "表格标题专属词")

    assert not isinstance(results, ToolFailure)
    assert len(results) == 1
    hit = results[0]
    excerpt = service.get_excerpt(_identity().document_id, hit.locator)
    assert hit.section_ref == "section-0002"
    assert hit.table_ref == "table-0000"
    assert hit.locator.locator_kind is LocatorKind.TABLE
    assert hit.locator.table_ref == "table-0000"
    assert hit.citation.locator == hit.locator
    assert hit.match_kind is SearchMatchKind.TABLE_CAPTION
    assert "表格标题专属词" in hit.excerpt
    assert not isinstance(excerpt, ToolFailure)
    assert "表格标题专属词" in excerpt.text


def test_search_document_returns_table_backed_row_result(tmp_path) -> None:
    """search_document 只命中 bounded table rows 时返回 table-backed result。"""

    service = _service(tmp_path)
    results = service.search_document(_identity().document_id, "表格行专属词")

    assert not isinstance(results, ToolFailure)
    assert len(results) == 1
    hit = results[0]
    assert hit.table_ref == "table-0000"
    assert hit.locator.locator_kind is LocatorKind.TABLE
    assert hit.citation.locator.table_ref == "table-0000"
    assert hit.match_kind is SearchMatchKind.TABLE_ROW
    assert "表格行专属词" in hit.excerpt
    assert "项目" not in hit.excerpt
    assert "基金名称" not in hit.excerpt


def test_search_document_returns_empty_tuple_without_evidence_candidate(tmp_path) -> None:
    """无 evidence candidate 时 search_document 返回空 tuple，不扩展 failure code。"""

    results = _service(tmp_path).search_document(_identity().document_id, "不存在的检索词")

    assert results == ()


def test_read_table_returns_table_ref_and_section_ref(tmp_path) -> None:
    """read_table 必须返回 table_ref、section_ref、locator 和 citation。"""

    service = _service(tmp_path)
    tables = service.list_tables(_identity().document_id)
    assert not isinstance(tables, ToolFailure)

    table = service.read_table(_identity().document_id, tables[0].table_ref, max_rows=1)

    assert not isinstance(table, ToolFailure)
    excerpt = service.get_excerpt(_identity().document_id, table.locator)
    assert table.table_ref == "table-0000"
    assert table.section_ref == "section-0002"
    assert table.locator.table_ref == "table-0000"
    assert table.citation.locator.section_ref == "section-0002"
    assert table.rows == (("项目", "内容"),)
    assert not isinstance(excerpt, ToolFailure)
    assert "项目\t内容" in excerpt.text


def test_get_excerpt_rejects_unknown_locator(tmp_path) -> None:
    """get_excerpt 只接受 prior tools 返回的受控 locator，unknown locator 返回 not_found。"""

    unknown = Locator(
        document_id=_identity().document_id,
        locator_kind=LocatorKind.SECTION,
        section_ref="section-9999",
        table_ref=None,
        page_no=None,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
    )

    result = _service(tmp_path).get_excerpt(_identity().document_id, unknown)

    assert isinstance(result, ToolFailure)
    assert result.code is FailureCode.NOT_FOUND
