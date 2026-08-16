"""快照简化评分（§6.25 裁决 4）。

确定性规则，不依赖多年数据：
- 当期超额收益（①-③ 列，净值增长率-基准收益率）
- 仓位（权益/股票占净值比例）
- 集中度（前十大持仓合计占净值比例）

独立于 signal_scoring.py 年报 6 指标评分。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fund_agent.service.snapshot_extraction import SnapshotReportData


@dataclass(frozen=True)
class SnapshotScore:
    """快照评分结果。

    参数:
        excess_score: 超额收益得分（0-40）。
        position_score: 仓位得分（0-30）。
        concentration_score: 集中度得分（0-30）。
        total_score: 总分（0-100）。
        grade: 综合等级（优秀/良好/关注）。
    """

    excess_score: int
    position_score: int
    concentration_score: int
    total_score: int
    grade: str


def _parse_percent(text: str) -> float | None:
    """解析百分数文本为浮点数（如 "-6.69%" → -6.69）。"""

    if not text or "缺失" in str(text) or "未披露" in str(text):
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*%", str(text))
    if not match:
        return None
    return float(match.group(1))


def _parse_shares_percent(text: str) -> float | None:
    """解析持仓占比（占净值比例；列头带 %，值可能为裸数字如 5.87）。"""

    if not text or "缺失" in str(text) or "未披露" in str(text):
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?)", str(text))
    if not match:
        return None
    return float(match.group(1))


def compute_snapshot_score(data: SnapshotReportData) -> SnapshotScore:
    """计算快照简化评分。

    参数:
        data: 快照抽取数据。

    返回:
        SnapshotScore；数据不足时各维度 0 分并声明。
    """

    # 1. 超额收益（0-40）：取「过去一年」行（如存在）的 ①-③
    excess_value: float | None = None
    one_year = next((r for r in data.performance_rows if "一年" in r.stage), None)
    if one_year is not None:
        excess_value = _parse_percent(one_year.excess_return)
        if excess_value is None:
            nav = _parse_percent(one_year.nav_growth_rate)
            bench = _parse_percent(one_year.benchmark_return_rate)
            if nav is not None and bench is not None:
                excess_value = nav - bench
    if excess_value is None:
        excess_score = 0
    elif excess_value >= 5:
        excess_score = 40
    elif excess_value >= 0:
        excess_score = 25
    elif excess_value >= -5:
        excess_score = 10
    else:
        excess_score = 0

    # 2. 仓位（0-30）：股票/权益占净值比例
    equity_ratio: float | None = None
    for row in data.allocation_rows:
        if any(kw in row.get("asset_class", "") for kw in ("股票", "权益")) and "其中" not in row.get("asset_class", ""):
            equity_ratio = _parse_shares_percent(row.get("ratio", ""))
            break
    if equity_ratio is None:
        position_score = 0
    elif equity_ratio >= 80:
        position_score = 30
    elif equity_ratio >= 60:
        position_score = 25
    elif equity_ratio >= 40:
        position_score = 15
    else:
        position_score = 5

    # 3. 集中度（0-30）：前十大合计占净值比例
    concentration: float | None = None
    ratios: list[float] = []
    for row in data.holdings_rows:
        ratio = _parse_shares_percent(row.get("ratio", ""))
        if ratio is not None:
            ratios.append(ratio)
    if ratios:
        concentration = sum(ratios)
    if concentration is None:
        concentration_score = 0
    elif concentration <= 40:
        concentration_score = 30
    elif concentration <= 60:
        concentration_score = 20
    elif concentration <= 80:
        concentration_score = 10
    else:
        concentration_score = 5

    total = excess_score + position_score + concentration_score
    if total >= 75:
        grade = "优秀"
    elif total >= 50:
        grade = "良好"
    else:
        grade = "关注"

    return SnapshotScore(
        excess_score=excess_score,
        position_score=position_score,
        concentration_score=concentration_score,
        total_score=total,
        grade=grade,
    )
