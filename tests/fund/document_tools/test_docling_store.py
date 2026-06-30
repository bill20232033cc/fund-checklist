"""DoclingDocumentStore Slice 的回归测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import LocatorKind, ReportType, SourceKind
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import ReportIdentity


def _identity() -> ReportIdentity:
    """构造测试用报告身份。"""

    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-test",
        content_fingerprint="abc123",
        document_id="004393-2024-annual_report-abc123",
    )


def _write_docling_json(path: Path) -> None:
    """写入最小 Docling-shaped JSON，用于 store 行为测试。"""

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
                "captions": [],
                "data": {
                    "table_cells": [
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
                    ]
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _store(tmp_path) -> DoclingDocumentStore:
    """构造已通过 parser_health 的 store。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json(json_path)
    return DoclingDocumentStore(identity=_identity(), json_path=json_path)


def test_store_lists_sections_with_locator(tmp_path) -> None:
    """章节列表必须返回 section_ref、preview 和受控 locator。"""

    sections = _store(tmp_path).list_sections()

    assert len(sections) == 2
    assert sections[0].section_ref == "section-0000"
    assert sections[0].title == "§1 重要提示"
    assert sections[0].locator.document_id == _identity().document_id
    assert sections[0].locator.locator_kind is LocatorKind.SECTION
    assert sections[0].locator.section_ref == "section-0000"
    assert sections[0].locator.internal_ref == "#/texts/0"
    assert sections[0].locator.page_range == (1, 1)
    assert "基金经理" in sections[0].preview


def test_store_reads_section_with_bounded_text(tmp_path) -> None:
    """读取章节必须返回 bounded text、citation 和 truncated 标记。"""

    content = _store(tmp_path).read_section("section-0000", max_chars=12)

    assert content.section_ref == "section-0000"
    assert content.truncated is True
    assert len(content.text) == 12
    assert content.citation.document_id == _identity().document_id
    assert content.citation.locator.section_ref == "section-0000"


def test_store_lists_and_reads_tables(tmp_path) -> None:
    """表格列表和读取必须返回 table_ref、section_ref 和二维行投影。"""

    store = _store(tmp_path)
    tables = store.list_tables()
    table = store.read_table(tables[0].table_ref, max_rows=1)

    assert len(tables) == 1
    assert tables[0].table_ref == "table-0000"
    assert tables[0].section_ref == "section-0002"
    assert tables[0].row_count == 2
    assert tables[0].column_count == 2
    assert table.rows == (("项目", "内容"),)
    assert table.truncated is True
    assert table.locator.locator_kind is LocatorKind.TABLE
    assert table.citation.locator.table_ref == "table-0000"


def test_store_search_returns_ranked_excerpt(tmp_path) -> None:
    """搜索必须返回 ranked excerpt、section_ref、locator 和 citation。"""

    results = _store(tmp_path).search("基金经理")

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].section_ref == "section-0000"
    assert "基金经理" in results[0].excerpt
    assert results[0].locator.locator_kind is LocatorKind.EXCERPT
    assert results[0].citation.document_id == _identity().document_id
