"""快照 interactive 文档解析测试（Service 层）。

覆盖:
- resolve_by_fund_code 加 report_type 过滤（mixed catalog 防污染）
- resolve_snapshot_reports 按 fund_code + report_type 匹配
- quarterly 同一 year 多条 quarter 全部保留
- semiannual H1 period 解析
- 无匹配 / 无 catalog → None
"""

import json
from pathlib import Path

from fund_agent.service.extraction import FundReadingService


def _write_catalog(
    work_dir: Path,
    reports: dict[str, dict[str, object]],
) -> None:
    """写入假 catalog（identity 含 quarter/period，对齐 list_reports 契约）。"""
    catalog_path = work_dir / "completed_reports.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps({"schema_version": 1, "reports": reports}, ensure_ascii=False),
        encoding="utf-8",
    )


def _report_record(
    *,
    document_id: str,
    fund_code: str,
    fund_name: str,
    year: int,
    report_type: str,
    quarter: int | None = None,
    period: str | None = None,
) -> dict[str, object]:
    """构造单条 catalog report record。"""
    identity: dict[str, object] = {
        "fund_code": fund_code,
        "fund_name": fund_name,
        "year": year,
        "report_type": report_type,
        "source_kind": "local_pdf",
        "content_fingerprint": "abc123",
        "document_id": document_id,
        "share_class": "A",
    }
    if quarter is not None:
        identity["quarter"] = quarter
    if period is not None:
        identity["period"] = period
    return {
        "schema_version": 1,
        "document_id": document_id,
        "identity": identity,
        "stored_blob_ref": f"local_pdf::{document_id}",
        "docling_json_ref": f"docling_json::{document_id}",
        "parser_health": {"status": "ok"},
    }


def _mixed_catalog(work_dir: Path) -> None:
    """同基金同年混合 catalog：annual + quarterly + semiannual。"""
    _write_catalog(
        work_dir,
        {
            "005680-2024-annual_report-aaa": _report_record(
                document_id="005680-2024-annual_report-aaa",
                fund_code="005680",
                fund_name="财通资管价值成长混合",
                year=2024,
                report_type="annual_report",
            ),
            "005680-2025-annual_report-bbb": _report_record(
                document_id="005680-2025-annual_report-bbb",
                fund_code="005680",
                fund_name="财通资管价值成长混合",
                year=2025,
                report_type="annual_report",
            ),
            "005680-2025-Q1-quarterly_report-ccc": _report_record(
                document_id="005680-2025-Q1-quarterly_report-ccc",
                fund_code="005680",
                fund_name="财通资管价值成长混合",
                year=2025,
                report_type="quarterly_report",
                quarter=1,
            ),
            "005680-2025-Q2-quarterly_report-ddd": _report_record(
                document_id="005680-2025-Q2-quarterly_report-ddd",
                fund_code="005680",
                fund_name="财通资管价值成长混合",
                year=2025,
                report_type="quarterly_report",
                quarter=2,
            ),
            "005680-2026-Q4-quarterly_report-eee": _report_record(
                document_id="005680-2026-Q4-quarterly_report-eee",
                fund_code="005680",
                fund_name="财通资管价值成长混合",
                year=2026,
                report_type="quarterly_report",
                quarter=4,
            ),
            "005680-2025-semiannual_report-fff": _report_record(
                document_id="005680-2025-semiannual_report-fff",
                fund_code="005680",
                fund_name="财通资管价值成长混合",
                year=2025,
                report_type="semiannual_report",
                period="H1",
            ),
        },
    )


class TestResolveByFundCodeAnnualFilter:
    """resolve_by_fund_code 的 report_type 过滤（mixed catalog 防污染）。"""

    def test_annual_only_returns_annual_docs(self, tmp_path: Path) -> None:
        """mixed catalog 下 annual 解析只含 annual doc id（修复 §1.2 污染）。"""
        _mixed_catalog(tmp_path)
        resolution = FundReadingService().resolve_by_fund_code("005680", tmp_path)
        assert resolution is not None
        assert [d.document_id for d in resolution.documents] == [
            "005680-2024-annual_report-aaa",
            "005680-2025-annual_report-bbb",
        ]
        assert resolution.available_years == (2024, 2025)

    def test_default_report_type_is_annual(self, tmp_path: Path) -> None:
        """默认 report_type=annual_report，不返回快照 doc。"""
        _mixed_catalog(tmp_path)
        resolution = FundReadingService().resolve_by_fund_code("005680", tmp_path)
        assert resolution is not None
        assert all("annual_report" in d.document_id for d in resolution.documents)

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        """无匹配基金返回 None。"""
        _mixed_catalog(tmp_path)
        assert FundReadingService().resolve_by_fund_code("999999", tmp_path) is None

    def test_missing_catalog_returns_none(self, tmp_path: Path) -> None:
        """无 catalog 返回 None。"""
        assert FundReadingService().resolve_by_fund_code("005680", tmp_path) is None


class TestResolveSnapshotReports:
    """resolve_snapshot_reports 的匹配与期次保留。"""

    def test_quarterly_keeps_all_quarters_per_year(self, tmp_path: Path) -> None:
        """季度同一年多条 quarter 全部保留（不做 year last-wins）。"""
        _mixed_catalog(tmp_path)
        resolution = FundReadingService().resolve_snapshot_reports(
            "005680", tmp_path, "quarterly_report"
        )
        assert resolution is not None
        assert [d.document_id for d in resolution.documents] == [
            "005680-2025-Q1-quarterly_report-ccc",
            "005680-2025-Q2-quarterly_report-ddd",
            "005680-2026-Q4-quarterly_report-eee",
        ]
        assert resolution.available_years == (2025, 2026)
        by_id = {d.document_id: d for d in resolution.documents}
        assert by_id["005680-2025-Q2-quarterly_report-ddd"].quarter == 2

    def test_semiannual_period_parsed(self, tmp_path: Path) -> None:
        """半年报解析出 period=H1。"""
        _mixed_catalog(tmp_path)
        resolution = FundReadingService().resolve_snapshot_reports(
            "005680", tmp_path, "semiannual_report"
        )
        assert resolution is not None
        assert [d.document_id for d in resolution.documents] == [
            "005680-2025-semiannual_report-fff",
        ]
        assert resolution.documents[0].period == "H1"
        assert resolution.documents[0].quarter is None

    def test_snapshot_does_not_include_annual(self, tmp_path: Path) -> None:
        """快照模式匹配不到 annual（report_type 键互斥防污染）。"""
        _mixed_catalog(tmp_path)
        resolution = FundReadingService().resolve_snapshot_reports(
            "005680", tmp_path, "quarterly_report"
        )
        assert resolution is not None
        assert all("quarterly_report" in d.document_id for d in resolution.documents)

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        """该基金无任何快照时返回 None。"""
        _write_catalog(
            tmp_path,
            {
                "005680-2024-annual_report-aaa": _report_record(
                    document_id="005680-2024-annual_report-aaa",
                    fund_code="005680",
                    fund_name="财通资管价值成长混合",
                    year=2024,
                    report_type="annual_report",
                ),
            },
        )
        assert (
            FundReadingService().resolve_snapshot_reports(
                "005680", tmp_path, "quarterly_report"
            )
            is None
        )

    def test_missing_catalog_returns_none(self, tmp_path: Path) -> None:
        """无 catalog 返回 None。"""
        assert (
            FundReadingService().resolve_snapshot_reports(
                "005680", tmp_path, "quarterly_report"
            )
            is None
        )
