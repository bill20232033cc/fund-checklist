"""signal_scoring helpers 测试。"""
from __future__ import annotations

import pytest

from fund_agent.service.models import FeeRateItem, HoldingExtraction, ScaleInfo
from fund_agent.service.signal_scoring import (
    _parse_percent,
    _infer_fee_kwargs,
    score_excess_returns,
    score_fee_rate,
    score_scale_risk,
    score_concentration,
)


# --- parse_percent ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8.52%", 8.52),
        ("-3.2%", -3.2),
        ("-5.23%", -5.23),
        ("不收取", 0.0),
        ("N/A", None),
        ("—", None),
        ("暂无数据", None),
        ("6.08", 6.08),
    ],
)
def test_parse_percent(text: str, expected: float | None) -> None:
    assert _parse_percent(text) == expected


# --- score_excess_returns ---


def test_score_excess_returns_handles_negative_percent() -> None:
    performance = {
        2023: {"excess_return": "-1.11%"},
        2024: {"excess_return": "-3.21%"},
    }
    indicator = score_excess_returns(performance)
    assert indicator.detail == "连续负超额"


# --- score_fee_rate: parameterized ---


def test_score_fee_rate_active_defaults() -> None:
    """主动基金费率：默认阈值 1.0/1.5，满分 25。"""
    fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.80%"),)}

    # <1.0% → green, 25/25
    ind = score_fee_rate(fees, 2025)
    assert ind.score == 25
    assert ind.max_score == 25
    assert ind.risk_status == "🟢"

    # <1.0% but changing max_score
    ind2 = score_fee_rate(fees, 2025, max_score=40)
    assert ind2.score == 40
    assert ind2.max_score == 40


def test_score_fee_rate_passive_etf_threshold() -> None:
    """A 股 ETF 费率阈值：<0.20 绿，0.20-0.50 黄，>0.50 红，满分 40。"""
    # 0.15% → green
    fees_low = {2025: (FeeRateItem(fee_name="管理费", rate="0.15%"),)}
    ind = score_fee_rate(fees_low, 2025, green_max=0.20, yellow_max=0.50, max_score=40)
    assert ind.score == 40
    assert ind.risk_status == "🟢"

    # 0.35% → yellow
    fees_mid = {2025: (FeeRateItem(fee_name="管理费", rate="0.35%"),)}
    ind = score_fee_rate(fees_mid, 2025, green_max=0.20, yellow_max=0.50, max_score=40)
    assert ind.score == 24  # round(40*0.6)
    assert ind.risk_status == "🟡"

    # 0.60% → red
    fees_high = {2025: (FeeRateItem(fee_name="管理费", rate="0.60%"),)}
    ind = score_fee_rate(fees_high, 2025, green_max=0.20, yellow_max=0.50, max_score=40)
    assert ind.score == 8  # round(40*0.2)
    assert ind.risk_status == "🔴"


def test_score_fee_rate_qdii_threshold() -> None:
    """QDII 费率阈值：<0.80 绿，0.80-1.20 黄，>1.20 红。"""
    fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.90%"),)}
    ind = score_fee_rate(fees, 2025, green_max=0.80, yellow_max=1.20, max_score=40)
    assert ind.score == 24  # yellow
    assert ind.risk_status == "🟡"


def test_score_fee_rate_bond_threshold() -> None:
    """债券基金费率阈值：<0.30 绿，0.30-0.60 黄，>0.60 红。"""
    fees = {2025: (FeeRateItem(fee_name="管理费", rate="0.25%"),)}
    ind = score_fee_rate(fees, 2025, green_max=0.30, yellow_max=0.60, max_score=25)
    assert ind.score == 25  # green
    assert ind.risk_status == "🟢"


# --- score_scale_risk: parameterized ---


def test_score_scale_risk_passive_max30() -> None:
    """规模风险 passive max_score=30。"""
    # 5 亿 → green
    ind = score_scale_risk(
        ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="5亿元"),
        max_score=30,
    )
    assert ind.score == 30
    assert ind.max_score == 30
    assert ind.risk_status == "🟢"

    # 1 亿 → yellow
    ind = score_scale_risk(
        ScaleInfo(total_shares_a="", total_shares_c="", individual_investor_ratio="", management_holds="", estimated_aum="1亿元"),
        max_score=30,
    )
    assert ind.score == 18  # round(30*0.6)
    assert ind.risk_status == "🟡"


# --- score_concentration: parameterized ---


def test_score_concentration_passive_max30() -> None:
    """持仓集中度 passive max_score=30。"""
    holdings = {
        2025: (
            HoldingExtraction(rank=1, stock_code="000001", stock_name="A", quantity="100", fair_value="5000", percentage="7.0%"),
        ),
    }
    ind = score_concentration(holdings, max_score=30)
    assert ind.score == 30
    assert ind.max_score == 30
    assert ind.risk_status == "🟢"


# --- _infer_fee_kwargs ---


def test_infer_fee_kwargs_a_share_etf() -> None:
    """A 股 ETF 使用 A 股 ETF 费率阈值。"""
    kw = _infer_fee_kwargs("华泰柏瑞中证红利低波动交易型开放式指数证券投资基金", "index_etf")
    assert kw["green_max"] == 0.20
    assert kw["yellow_max"] == 0.50
    assert kw["max_score"] == 40


def test_infer_fee_kwargs_qdii() -> None:
    """QDII ETF 优先使用 QDII 阈值。"""
    kw = _infer_fee_kwargs("华安纳斯达克100ETF（QDII）", "index_etf")
    assert kw["green_max"] == 0.80
    assert kw["yellow_max"] == 1.20
    assert kw["max_score"] == 40


def test_infer_fee_kwargs_feeder() -> None:
    """联接基金使用联接基金阈值。"""
    kw = _infer_fee_kwargs("某某 ETF 联接基金", "index_feeder")
    assert kw["green_max"] == 0.50
    assert kw["yellow_max"] == 1.00
    assert kw["max_score"] == 40


def test_infer_fee_kwargs_bond() -> None:
    """债券基金使用债券费率阈值（max_score=25，5 指标 110→100）。"""
    kw = _infer_fee_kwargs("某某债券型证券投资基金", "bond_fund")
    assert kw["green_max"] == 0.30
    assert kw["yellow_max"] == 0.60
    assert kw["max_score"] == 25


def test_infer_fee_kwargs_active_default() -> None:
    """未知类型默认主动基金阈值。"""
    kw = _infer_fee_kwargs("某某基金", "active_fund")
    assert kw["green_max"] == 1.0
    assert kw["yellow_max"] == 1.5
    assert kw["max_score"] == 25
