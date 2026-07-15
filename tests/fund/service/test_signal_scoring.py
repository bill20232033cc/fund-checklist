"""signal_scoring helpers 测试。"""
from __future__ import annotations

import pytest

from fund_agent.service.signal_scoring import _parse_percent, score_excess_returns


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


def test_score_excess_returns_handles_negative_percent() -> None:
    """score_excess_returns 需要正确解析负百分比。"""
    performance = {
        2023: {"excess_return": "-1.11%"},
        2024: {"excess_return": "-3.21%"},
    }
    indicator = score_excess_returns(performance)
    assert indicator.detail == "连续负超额"
