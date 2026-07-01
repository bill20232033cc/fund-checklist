"""Post-MVP Slice 6 filesystem persistent repository 回归测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fund_agent.fund.document_tools.constants import FailureCode, ReportType
from fund_agent.fund.document_tools.docling_converter import make_docling_json_ref
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.local_pdf_source import LocalPdfSourceProvider
from fund_agent.fund.document_tools.models import PdfImportRequest
from fund_agent.fund.document_tools.persistent_repository import CATALOG_FILENAME, FilesystemReportRepository
from fund_agent.fund.document_tools.service import FundDocumentToolService


def _pdf_path(tmp_path: Path) -> Path:
    """写入满足 Slice 1 integrity check 的测试 PDF。"""

    path = tmp_path / "source.pdf"
    path.write_bytes(b"%PDF-1.4\npersistent repository test\n")
    return path


def _docling_payload() -> dict[str, object]:
    """返回带 section/table/search 投影的最小 Docling-shaped JSON。"""

    return {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 基金经理",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理张明负责本基金的投资管理。",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "§2 投资组合",
                "level": 1,
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "股票投资占基金资产净值比例保持稳定。",
                "prov": [{"page_no": 2}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1}],
                "captions": [],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "姓名",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "职务",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "张明",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "基金经理",
                        },
                    ]
                },
            },
        ],
    }


def _repository(tmp_path: Path) -> FilesystemReportRepository:
    """构造测试 repository。"""

    work_dir = tmp_path / "work"
    return FilesystemReportRepository(
        catalog_path=work_dir / CATALOG_FILENAME,
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )


def _import_and_record(tmp_path: Path) -> tuple[FilesystemReportRepository, str]:
    """导入 PDF、写入 Docling JSON、记录 completed catalog。"""

    work_dir = tmp_path / "work"
    provider = LocalPdfSourceProvider(work_dir / "pdf_blobs")
    import_result = provider.import_pdf(
        PdfImportRequest(
            path=_pdf_path(tmp_path),
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            year=2024,
            report_type=ReportType.ANNUAL_REPORT,
        )
    )
    document_id = import_result.identity.document_id
    json_path = work_dir / "docling_json" / document_id / f"{document_id}.docling.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(_docling_payload(), ensure_ascii=False), encoding="utf-8")
    store = DoclingDocumentStore(identity=import_result.identity, json_path=json_path)
    repository = _repository(tmp_path)
    repository.record_completed_report(
        identity=import_result.identity,
        stored_blob_ref=import_result.stored_blob_ref,
        docling_json_ref=make_docling_json_ref(document_id),
        parser_health=store.parser_health,
    )
    return repository, document_id


def _catalog_path(tmp_path: Path) -> Path:
    """返回测试 catalog 路径。"""

    return tmp_path / "work" / CATALOG_FILENAME


def _load_catalog(tmp_path: Path) -> dict[str, object]:
    """读取测试 catalog JSON。"""

    return json.loads(_catalog_path(tmp_path).read_text(encoding="utf-8"))


def test_completed_report_writes_catalog_and_loads_store_by_document_id(tmp_path: Path) -> None:
    """completed report 必须写入 filesystem JSON catalog 并可按 document_id 恢复。"""

    repository, document_id = _import_and_record(tmp_path)
    loaded_store = repository.load_store(document_id)
    catalog_text = _catalog_path(tmp_path).read_text(encoding="utf-8")

    assert loaded_store.list_sections()[0].section_ref == "section-0000"
    assert document_id in catalog_text
    assert "local_import_id" not in catalog_text
    assert str(tmp_path) not in catalog_text


def test_loaded_store_works_through_fund_document_tool_service(tmp_path: Path) -> None:
    """repository 恢复的 store 必须可通过 FundDocumentToolService 使用 reading tools。"""

    repository, document_id = _import_and_record(tmp_path)
    service = FundDocumentToolService({document_id: repository.load_store(document_id)})

    search_results = service.search_document(document_id, "基金经理")
    section = service.read_section(document_id, search_results[0].section_ref)
    tables = service.list_tables(document_id)
    table = service.read_table(document_id, tables[0].table_ref)

    assert search_results[0].section_ref == "section-0000"
    assert "张明" in section.text
    assert tables[0].table_ref == "table-0000"
    assert ("张明", "基金经理") in table.rows


def test_duplicate_same_pdf_reuses_document_id_and_catalog_record(tmp_path: Path) -> None:
    """重复导入同一 PDF 必须复用 document_id 并更新同一 catalog record。"""

    first_repository, first_document_id = _import_and_record(tmp_path)
    second_repository, second_document_id = _import_and_record(tmp_path)
    catalog = _load_catalog(tmp_path)

    assert first_document_id == second_document_id
    assert first_repository.load_store(first_document_id).list_sections()
    assert second_repository.load_store(second_document_id).list_sections()
    assert list(catalog["reports"].keys()) == [first_document_id]


def test_missing_catalog_returns_not_found(tmp_path: Path) -> None:
    """catalog 缺失必须分类为 not_found。"""

    with pytest.raises(DocumentToolError) as error:
        _repository(tmp_path).load_store("missing-document")

    assert error.value.code is FailureCode.NOT_FOUND


def test_missing_docling_json_returns_unavailable(tmp_path: Path) -> None:
    """completed record 指向缺失 Docling JSON 时必须返回 unavailable，不自动重转。"""

    repository, document_id = _import_and_record(tmp_path)
    json_path = tmp_path / "work" / "docling_json" / document_id / f"{document_id}.docling.json"
    json_path.unlink()

    with pytest.raises(DocumentToolError) as error:
        repository.load_store(document_id)

    assert error.value.code is FailureCode.UNAVAILABLE


def test_catalog_identity_mismatch_returns_identity_mismatch(tmp_path: Path) -> None:
    """catalog identity 与请求 document_id 不一致时必须返回 identity_mismatch。"""

    repository, document_id = _import_and_record(tmp_path)
    catalog = _load_catalog(tmp_path)
    catalog["reports"][document_id]["identity"]["document_id"] = "other-document"
    _catalog_path(tmp_path).write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DocumentToolError) as error:
        repository.load_store(document_id)

    assert error.value.code is FailureCode.IDENTITY_MISMATCH


def test_blob_fingerprint_mismatch_returns_integrity_error(tmp_path: Path) -> None:
    """catalog 对应 PDF blob 指纹不一致时必须返回 integrity_error。"""

    repository, document_id = _import_and_record(tmp_path)
    blob_path = tmp_path / "work" / "pdf_blobs" / document_id / "source.pdf"
    blob_path.write_bytes(b"%PDF-1.4\nchanged bytes\n")

    with pytest.raises(DocumentToolError) as error:
        repository.load_store(document_id)

    assert error.value.code is FailureCode.INTEGRITY_ERROR


def test_public_outputs_do_not_leak_raw_payload_paths_or_local_import_id(tmp_path: Path) -> None:
    """repository-backed public tool 输出不得泄漏 raw payload、本地路径或 local_import_id。"""

    repository, document_id = _import_and_record(tmp_path)
    service = FundDocumentToolService({document_id: repository.load_store(document_id)})
    reports = service.list_reports()
    search_results = service.search_document(document_id, "基金经理")
    section = service.read_section(document_id, search_results[0].section_ref)
    tables = service.list_tables(document_id)
    table = service.read_table(document_id, tables[0].table_ref)
    public_output = repr((reports, search_results, section, tables, table))

    assert "schema_name" not in public_output
    assert ".docling.json" not in public_output
    assert str(tmp_path) not in public_output
    assert "local_import_id" not in public_output
    assert "repository-restored" not in public_output
