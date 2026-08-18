"""EID 下载器半年报/季报 spec 与匹配逻辑测试（2026-08-14 实证口径；
2026-08-17 直连 EID 实测修正季报 reportDesp 为中文数字）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.eid_downloader import (
    QUARTERLY_REPORT_CODE_BY_QUARTER,
    QUARTERLY_REPORT_DESP_BY_QUARTER,
    REPORT_SPECS,
    EidDownloadError,
    _candidate_matches,
    _search_report,
    _spec_for,
    _strict_match,
    download_report,
)


def test_specs_cover_empirical_eid_codes() -> None:
    """EID 实证码必须全部进入 spec 表（§6.25 裁决 14）。"""

    assert REPORT_SPECS["annual_report"] == {
        "report_type": "FB010",
        "report_code": "FB010010",
        "report_desp": "年度报告",
    }
    assert REPORT_SPECS["semiannual_report"] == {
        "report_type": "FB020",
        "report_code": "FB020010",
        "report_desp": "中期报告",
    }
    assert QUARTERLY_REPORT_CODE_BY_QUARTER == {
        1: "FB030010",
        2: "FB030020",
        3: "FB030030",
        4: "FB030040",
    }
    assert QUARTERLY_REPORT_DESP_BY_QUARTER == {
        1: "第一季度报告",
        2: "第二季度报告",
        3: "第三季度报告",
        4: "第四季度报告",
    }


def test_spec_for_quarterly_uses_quarter_code_and_desp() -> None:
    """quarterly spec 必须按 quarter 选择 FB0300X + 中文数字季度报告。"""

    spec = _spec_for("quarterly_report", 2)
    assert spec == {
        "report_type": "FB030",
        "report_code": "FB030020",
        "report_desp": "第二季度报告",
    }


def test_spec_for_semiannual_uses_midterm_code() -> None:
    """semiannual spec 必须使用 FB020/FB020010/中期报告。"""

    spec = _spec_for("semiannual_report", None)
    assert spec == {
        "report_type": "FB020",
        "report_code": "FB020010",
        "report_desp": "中期报告",
    }


def test_candidate_matches_quarterly_row() -> None:
    """_candidate_matches 必须命中实证季报行（FB030020，2026，Q2，reportDesp 中文数字）。"""

    row = {
        "fundCode": "005680",
        "fundId": "11314",
        "reportYear": "2026",
        "reportCode": "FB030020",
        "reportDesp": "第二季度报告",
        "tableName": "PDF",
        "reportName": "005680_财通资管价值成长混合_2026年第二季度报告",
        "uploadInfoId": "1534983",
    }
    assert _candidate_matches(
        row=row,
        fund_code="005680",
        fund_id="11314",
        year=2026,
        report_code="FB030020",
        report_desp="第二季度报告",
    )


def test_candidate_matches_semiannual_row() -> None:
    """_candidate_matches 必须命中实证半年报行（FB020010，2025，中期报告）。"""

    row = {
        "fundCode": "005680",
        "fundId": "11314",
        "reportYear": "2025",
        "reportCode": "FB020010",
        "reportDesp": "中期报告",
        "tableName": "PDF",
        "reportName": "005680_财通资管价值成长混合_2025年中期报告",
        "uploadInfoId": "1341853",
    }
    assert _candidate_matches(
        row=row,
        fund_code="005680",
        fund_id="11314",
        year=2025,
        report_code="FB020010",
        report_desp="中期报告",
    )


def test_strict_match_falls_back_without_fund_code() -> None:
    """_strict_match 必须支持 fundId+年份+报告类型回退匹配（忽略 fundCode 不一致）。"""

    row = {
        "fundId": "11314",
        "reportYear": "2026",
        "reportCode": "FB030010",
        "reportDesp": "第一季度报告",
        "tableName": "PDF",
        "reportName": "005680_财通资管价值成长混合_2026年第一季度报告",
        "uploadInfoId": "1473543",
    }
    assert _strict_match(row, "11314", 2026, "FB030010", "第一季度报告")
    # 摘要行必须排除
    summary_row = dict(row)
    summary_row["reportName"] = "005680_财通资管价值成长混合_2026年第一季度报告摘要"
    assert not _strict_match(summary_row, "11314", 2026, "FB030010", "第一季度报告")


def test_candidate_matches_rejects_wrong_quarter() -> None:
    """quarter 不匹配的报告码必须拒绝。"""

    row = {
        "fundCode": "005680",
        "fundId": "11314",
        "reportYear": "2026",
        "reportCode": "FB030010",
        "reportDesp": "第一季度报告",
        "tableName": "PDF",
        "reportName": "005680_财通资管价值成长混合_2026年第一季度报告",
        "uploadInfoId": "1473543",
    }
    assert not _candidate_matches(
        row=row,
        fund_code="005680",
        fund_id="11314",
        year=2026,
        report_code="FB030020",
        report_desp="第二季度报告",
    )


@pytest.mark.parametrize(
    ("report_type", "quarter", "expected_label"),
    [
        ("annual_report", None, "年报"),
        ("semiannual_report", None, "中期报告"),
        ("quarterly_report", 2, "第2季度报告"),
    ],
)
def test_search_report_not_found_message_includes_report_type(
    monkeypatch: pytest.MonkeyPatch,
    report_type: str,
    quarter: int | None,
    expected_label: str,
) -> None:
    """not_found 消息必须按报告类型参数化（季报示例：未找到 007466 的 2025 年第2季度报告）。"""

    def _empty_search(url: str, **kwargs: object) -> dict[str, object]:
        return {"aaData": [], "iTotalRecords": 0}

    monkeypatch.setattr(
        "fund_agent.fund.document_tools.eid_downloader._request_json",
        _empty_search,
    )
    with pytest.raises(EidDownloadError) as exc_info:
        _search_report(
            fund_code="007466",
            fund_id="12345",
            year=2025,
            spec=_spec_for(report_type, quarter),
        )
    assert exc_info.value.code == "not_found"
    assert f"未找到 007466 的 2025 年{expected_label}" in str(exc_info.value)


def test_download_report_validates_quarter_for_quarterly(tmp_path) -> None:
    """quarterly 缺 quarter / quarter 越界必须 fail-closed 为 schema_drift。"""

    with pytest.raises(EidDownloadError) as exc_info:
        download_report("005680", 2026, tmp_path, report_type="quarterly_report")
    assert exc_info.value.code == "schema_drift"

    with pytest.raises(EidDownloadError) as exc_info:
        download_report("005680", 2026, tmp_path, report_type="quarterly_report", quarter=5)
    assert exc_info.value.code == "schema_drift"


def test_download_report_rejects_unknown_report_type(tmp_path) -> None:
    """未知 report_type 必须 fail-closed 为 schema_drift。"""

    with pytest.raises(EidDownloadError) as exc_info:
        download_report("005680", 2026, tmp_path, report_type="monthly_report")
    assert exc_info.value.code == "schema_drift"


def test_download_report_quarter_ignored_for_annual(tmp_path) -> None:
    """annual 带 quarter 必须 fail-closed（参数契约一致性）。"""

    with pytest.raises(EidDownloadError) as exc_info:
        download_report("005680", 2026, tmp_path, report_type="annual_report", quarter=2)
    assert exc_info.value.code == "schema_drift"
