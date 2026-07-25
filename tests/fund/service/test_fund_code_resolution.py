"""FundReadingService.resolve_by_fund_code() 测试。

覆盖:
- 正常解析：多年度 document 映射
- 无匹配基金代码
- 空 catalog
- available_years 排序
"""

import json
from pathlib import Path

import pytest

from fund_agent.service.extraction import FundReadingService
from fund_agent.service.models import FundCodeResolution


def _write_fake_catalog(work_dir: Path, records: list[dict]) -> Path:
    """写入假 catalog JSON 到 work_dir。"""
    catalog_path = work_dir / "completed_reports.json"
    catalog_data = {
        "schema_version": 1,
        "reports": {r["document_id"]: r for r in records},
    }
    catalog_path.write_text(json.dumps(catalog_data, ensure_ascii=False), encoding="utf-8")
    return catalog_path


def _make_catalog_record(document_id: str, fund_code: str, fund_name: str, year: int) -> dict:
    return {
        "schema_version": 1,
        "document_id": document_id,
        "identity": {
            "fund_code": fund_code,
            "fund_name": fund_name,
            "year": year,
            "report_type": "annual_report",
            "source_kind": "local_pdf",
            "content_fingerprint": "abc123",
            "document_id": document_id,
            "share_class": "A",
        },
        "stored_blob_ref": f"local_pdf::{document_id}",
        "docling_json_ref": f"docling_json::{document_id}",
        "parser_health": {"status": "ok"},
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


class TestResolveByFundCode:
    """resolve_by_fund_code() 方法测试。"""

    def test_resolves_multiple_years(self, tmp_path: Path):
        """基金代码有多个年度 → 返回全部 mapping。"""
        records = [
            _make_catalog_record("doc-011649-2021", "011649", "XX基金", 2021),
            _make_catalog_record("doc-011649-2022", "011649", "XX基金", 2022),
            _make_catalog_record("doc-011649-2023", "011649", "XX基金", 2023),
            _make_catalog_record("doc-011649-2024", "011649", "XX基金", 2024),
            _make_catalog_record("doc-011649-2025", "011649", "XX基金", 2025),
        ]
        _write_fake_catalog(tmp_path, records)

        service = FundReadingService()
        result = service.resolve_by_fund_code("011649", tmp_path)

        assert result is not None
        assert result.fund_code == "011649"
        assert result.fund_name == "XX基金"
        assert len(result.documents) == 5
        assert result.available_years == (2021, 2022, 2023, 2024, 2025)

    def test_no_match_returns_none(self, tmp_path: Path):
        """无匹配基金代码 → None。"""
        records = [
            _make_catalog_record("doc-000001-2025", "000001", "YY基金", 2025),
        ]
        _write_fake_catalog(tmp_path, records)

        service = FundReadingService()
        result = service.resolve_by_fund_code("999999", tmp_path)
        assert result is None

    def test_empty_catalog_returns_none(self, tmp_path: Path):
        """catalog 不存在 → None。"""
        service = FundReadingService()
        result = service.resolve_by_fund_code("011649", tmp_path)
        assert result is None

    def test_partial_years_still_works(self, tmp_path: Path):
        """部分年份缺失 → 返回有的年份。"""
        records = [
            _make_catalog_record("doc-011649-2023", "011649", "XX基金", 2023),
            _make_catalog_record("doc-011649-2025", "011649", "XX基金", 2025),
        ]
        _write_fake_catalog(tmp_path, records)

        service = FundReadingService()
        result = service.resolve_by_fund_code("011649", tmp_path)

        assert result is not None
        assert result.available_years == (2023, 2025)
        assert len(result.documents) == 2

    def test_years_sorted_ascending(self, tmp_path: Path):
        """年份按升序排列。"""
        # 逆序写入
        records = [
            _make_catalog_record("doc-011649-2025", "011649", "XX基金", 2025),
            _make_catalog_record("doc-011649-2021", "011649", "XX基金", 2021),
            _make_catalog_record("doc-011649-2023", "011649", "XX基金", 2023),
        ]
        _write_fake_catalog(tmp_path, records)

        service = FundReadingService()
        result = service.resolve_by_fund_code("011649", tmp_path)

        assert result is not None
        years = [d.year for d in result.documents]
        assert years == [2021, 2023, 2025]

    def test_fund_name_from_first_match(self, tmp_path: Path):
        """fund_name 取自第一条匹配记录。"""
        records = [
            _make_catalog_record("doc-011649-2024", "011649", "测试基金名称", 2024),
        ]
        _write_fake_catalog(tmp_path, records)

        service = FundReadingService()
        result = service.resolve_by_fund_code("011649", tmp_path)

        assert result is not None
        assert result.fund_name == "测试基金名称"
