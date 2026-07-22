"""确定性信号评分与风险评估共享逻辑。

本模块提供 6 个评分指标的共享 helper，消除 compute_signal_judgment 与
compute_risk_checklist 之间的重复阈值逻辑。

每个 helper 返回 _ScoredIndicator，包含：
- value: 计算出的原始值（如费率百分比、重叠率）
- score: 信号评分（0-max）
- max_score: 满分
- risk_status: 风险清单状态（🟢/🟡/🔴）
- detail: 人类可读说明
- calculable: 是否有足够数据计算
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fund_agent.service.models import (
    FeeRateItem,
    FundManagerInfo,
    HoldingExtraction,
    RiskChecklistItem,
    ScaleInfo,
    SignalIndicator,
)


@dataclass(frozen=True)
class _ScoredIndicator:
    """单项评分结果，同时服务于信号评分和风险清单。"""
    name: str
    value: float | None
    score: int
    max_score: int
    risk_status: str  # "🟢" / "🟡" / "🔴"
    detail: str
    calculable: bool


def _parse_percent(text: str) -> float | None:
    """解析百分比字符串为 float。

    参数:
        text: 百分比文本，如 "0.60%"、"不收取"、"N/A"。

    返回:
        百分比数值；无法解析时返回 None。
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    if "不收取" in text or "免收" in text:
        return 0.0
    if text.upper() in ("N/A", "—", "-", "暂无数据"):
        return None
    # 支持带负号的百分比，如 "-3.2%"
    m = re.search(r"-?[\d.]+\s*%", text)
    if m:
        return float(m.group(0).replace(" ","").rstrip("%"))
    # 无 % 号时尝试直接解析纯数字（如持仓占比表中的 "6.08"）
    try:
        return float(text.replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_aum_yi(text: str) -> float | None:
    """解析规模文本为亿元数值。

    参数:
        text: 规模文本，如 "2.99亿元"、"2,990,000元"。

    返回:
        亿元数值；无法解析时返回 None。
    """
    if not text or not text.strip():
        return None
    text = text.strip().replace(",", "")
    if text.upper() in ("N/A", "—", "-", "暂无数据"):
        return None
    if "亿元" in text:
        m = re.search(r"([\d.]+)\s*亿元", text)
        if m:
            return float(m.group(1))
    if "万元" in text:
        m = re.search(r"([\d.]+)\s*万元", text)
        if m:
            return float(m.group(1)) / 10000.0
    if "元" in text:
        m = re.search(r"([\d.]+)\s*元", text)
        if m:
            return float(m.group(1)) / 1e8
    return None


def _holdings_overlap_rate(
    holdings_a: tuple[HoldingExtraction, ...],
    holdings_b: tuple[HoldingExtraction, ...],
) -> float:
    """按加权 Jaccard 计算两个年度持仓重叠率。

    使用占基金资产净值比例作为权重。

    参数:
        holdings_a: 年度 A 的持仓记录。
        holdings_b: 年度 B 的持仓记录。

    返回:
        加权重叠率（0.0 ~ 1.0）；任一为空时返回 0.0。
    """
    if not holdings_a or not holdings_b:
        return 0.0

    def _parse_pct(h: HoldingExtraction) -> float:
        try:
            return float(h.percentage.rstrip("%")) if h.percentage else 0.0
        except (ValueError, AttributeError):
            return 0.0

    weights_a: dict[str, float] = {}
    weights_b: dict[str, float] = {}
    for h in holdings_a:
        if h.stock_code:
            weights_a[h.stock_code] = weights_a.get(h.stock_code, 0.0) + _parse_pct(h)
    for h in holdings_b:
        if h.stock_code:
            weights_b[h.stock_code] = weights_b.get(h.stock_code, 0.0) + _parse_pct(h)

    if not weights_a or not weights_b:
        return 0.0

    all_codes = set(weights_a) | set(weights_b)
    numerator = sum(min(weights_a.get(c, 0.0), weights_b.get(c, 0.0)) for c in all_codes)
    denominator = sum(max(weights_a.get(c, 0.0), weights_b.get(c, 0.0)) for c in all_codes)
    return numerator / denominator if denominator > 0 else 0.0


# --- fund_type → 适用指标映射 ---

# 每个基金类型对应哪些指标适用（True=参与评分，False=不适用）
_INDICATOR_APPLICABILITY: dict[str, dict[str, bool]] = {
    "active_fund": {
        "超额收益趋势": True,
        "费率水平": True,
        "风格漂移": True,
        "规模风险": True,
        "基金经理变更": True,
        "持仓集中度": True,
    },
    "index_fund": {
        # 被动指数基金：同 ETF，不适用超额/漂移/经理变更
        # 注意：增强指数基金在 compute_signal_judgment 中单独恢复全部指标
        "超额收益趋势": False,
        "费率水平": True,
        "风格漂移": False,
        "规模风险": True,
        "基金经理变更": False,
        "持仓集中度": True,
    },
    "index_etf": {
        # 被动 ETF：无超额收益概念（目标为跟踪指数）
        "超额收益趋势": False,
        "费率水平": True,
        # 不应漂移，应跟踪指数
        "风格漂移": False,
        "规模风险": True,
        # 经理变更对被动基金影响小
        "基金经理变更": False,
        "持仓集中度": True,
    },
    "index_feeder": {
        # 联接基金：继承目标 ETF，同被动 ETF
        "超额收益趋势": False,
        "费率水平": True,
        "风格漂移": False,
        "规模风险": True,
        "基金经理变更": False,
        "持仓集中度": True,
    },
    "bond_fund": {
        "超额收益趋势": True,
        "费率水平": True,
        # 股票持仓重叠率对债券基金无意义
        "风格漂移": False,
        "规模风险": True,
        "基金经理变更": True,
        "持仓集中度": True,
    },
}


def get_applicable_indicators(fund_type: str) -> dict[str, bool]:
    """返回指定基金类型的指标适用性映射。

    参数:
        fund_type: 基金类型（active_fund/index_fund/index_etf/index_feeder/bond_fund）。

    返回:
        {指标名称: 是否适用} 的字典。未知类型默认全部适用。
    """
    return _INDICATOR_APPLICABILITY.get(
        fund_type,
        _INDICATOR_APPLICABILITY["active_fund"],
    )


# --- 费率阈值按基金类型分档 ---

# (green_max, yellow_max) 键为基金类型
_FEE_THRESHOLD_MAP: dict[str, tuple[float, float]] = {
    "index_etf": (0.20, 0.50),       # A 股 ETF
    "index_fund": (0.20, 0.50),      # 纯指数基金（同 ETF）
    "index_feeder": (0.50, 1.00),    # 联接基金
    "qdii": (0.80, 1.20),            # QDII 基金
    "bond_fund": (0.30, 0.60),       # 债券基金
}

# 被动评分框架权重（3 指标 100 分制）
_PASSIVE_SCORING_WEIGHTS = {
    "费率水平": 40,
    "规模风险": 30,
    "持仓集中度": 30,
}


def _infer_fee_kwargs(fund_name: str, fund_type: str) -> dict:
    """根据基金名称和类型返回 score_fee_rate 的定制参数。

    参数:
        fund_name: 基金名称（用于 QDII 检测）。
        fund_type: 基金类型（index_etf/index_feeder/index_fund/bond_fund/active_fund）。

    返回:
        kwargs dict 传给 score_fee_rate(*, ...)。
    """
    # QDII 优先（名称含 QDII 走 QDII 阈值）
    if "QDII" in fund_name.upper():
        green_max, yellow_max = _FEE_THRESHOLD_MAP["qdii"]
        return {"green_max": green_max, "yellow_max": yellow_max, "max_score": 40}

    # 按 fund_type 查表
    if fund_type in _FEE_THRESHOLD_MAP:
        green_max, yellow_max = _FEE_THRESHOLD_MAP[fund_type]
        max_score = _PASSIVE_SCORING_WEIGHTS.get("费率水平", 40) if fund_type in ("index_etf", "index_feeder", "index_fund") else 25
        return {"green_max": green_max, "yellow_max": yellow_max, "max_score": max_score}

    # 默认：主动基金阈值
    return {"green_max": 1.0, "yellow_max": 1.5, "max_score": 25}


# --- 6 个评分指标 helper ---

def score_excess_returns(
    performance: dict[int, dict[str, str]],
) -> _ScoredIndicator:
    """指标 1：超额收益趋势（满分 25）。"""
    excess_years = []
    for year in sorted(performance.keys()):
        val = _parse_percent(performance[year].get("excess_return", ""))
        if val is not None:
            excess_years.append((year, val))

    if len(excess_years) >= 2:
        positive = sum(1 for _, v in excess_years if v > 0)
        negative = sum(1 for _, v in excess_years if v < 0)
        if positive >= 2 and negative == 0:
            return _ScoredIndicator("超额收益趋势", excess_years[-1][1], 25, 25, "🟢", "连续 2+ 年正超额", True)
        if positive > 0 and negative > 0:
            return _ScoredIndicator("超额收益趋势", excess_years[-1][1], 15, 25, "🟡", "有正有负", True)
        return _ScoredIndicator("超额收益趋势", excess_years[-1][1], 5, 25, "🔴", "连续负超额", True)
    if len(excess_years) == 1:
        val = excess_years[0][1]
        if val > 0:
            return _ScoredIndicator("超额收益趋势", val, 15, 25, "🟡", "仅 1 年数据且为正", True)
        return _ScoredIndicator("超额收益趋势", val, 5, 25, "🔴", "仅 1 年数据且为负", True)
    return _ScoredIndicator("超额收益趋势", None, 0, 25, "🟡", "无数据", False)


def score_fee_rate(
    fees: dict[int, tuple[FeeRateItem, ...]],
    report_year: int,
    *,
    green_max: float = 1.0,
    yellow_max: float = 1.5,
    max_score: int = 25,
) -> _ScoredIndicator:
    """指标 2：费率水平。

    参数:
        fees: 多年度费率数据。
        report_year: 报告年份。
        green_max: 🟢 档阈值上界（综合费率 < 此值满分）。
        yellow_max: 🟡 档阈值上界（综合费率 ≤ 此值部分分）。
        max_score: 本指标满分。
    """
    green_score = max_score
    yellow_score = round(max_score * 0.6)
    red_score = round(max_score * 0.2)

    latest_fees = fees.get(report_year) or (
        fees[max(y for y in fees if y <= report_year)]
        if fees and any(y <= report_year for y in fees) else None
    )
    if not latest_fees:
        return _ScoredIndicator("费率水平", None, 0, max_score, "🟡", "无数据", False)

    total_rate = 0.0
    has_data = False
    for fi in latest_fees:
        parsed = _parse_percent(fi.rate)
        if parsed is not None:
            total_rate += parsed
            has_data = True

    if not has_data:
        return _ScoredIndicator("费率水平", None, 0, max_score, "🟡", "费率数据不可解析", False)

    if total_rate < green_max:
        return _ScoredIndicator("费率水平", total_rate, green_score, max_score, "🟢", f"综合费率 {total_rate:.2f}% < {green_max}%", True)
    if total_rate <= yellow_max:
        return _ScoredIndicator("费率水平", total_rate, yellow_score, max_score, "🟡", f"综合费率 {total_rate:.2f}%（{green_max}-{yellow_max}%）", True)
    return _ScoredIndicator("费率水平", total_rate, red_score, max_score, "🔴", f"综合费率 {total_rate:.2f}% > {yellow_max}%", True)


def score_style_drift(
    holdings: dict[int, tuple[HoldingExtraction, ...]],
) -> _ScoredIndicator:
    """指标 3：风格漂移（满分 25，基于多年度加权 Jaccard 重叠率）。"""
    sorted_years = sorted(holdings.keys())
    overlap_rates = [
        _holdings_overlap_rate(holdings[sorted_years[i]], holdings[sorted_years[i + 1]])
        for i in range(len(sorted_years) - 1)
    ]

    if not overlap_rates:
        return _ScoredIndicator("风格漂移", None, 0, 25, "🟡", "不足 2 年持仓数据", False)

    avg = sum(overlap_rates) / len(overlap_rates)
    if avg > 0.70:
        return _ScoredIndicator("风格漂移", avg, 25, 25, "🟢", f"持仓重叠率 {avg:.0%} > 70%，风格稳定", True)
    if avg >= 0.50:
        return _ScoredIndicator("风格漂移", avg, 15, 25, "🟡", f"持仓重叠率 {avg:.0%}（50-70%）", True)
    return _ScoredIndicator("风格漂移", avg, 5, 25, "🔴", f"持仓重叠率 {avg:.0%} < 50%，风格漂移", True)


def score_scale_risk(
    scale_info: ScaleInfo | None,
    *,
    max_score: int = 25,
) -> _ScoredIndicator:
    """指标 4：规模风险。

    参数:
        scale_info: 规模信息。
        max_score: 本指标满分。
    """
    green_score = max_score
    yellow_score = round(max_score * 0.6)

    if not scale_info or not scale_info.estimated_aum:
        return _ScoredIndicator("规模风险", None, 0, max_score, "🟡", "无数据", False)

    aum = _parse_aum_yi(scale_info.estimated_aum)
    if aum is None:
        return _ScoredIndicator("规模风险", None, 0, max_score, "🟡", "规模数据不可解析", False)

    if aum > 2.0:
        return _ScoredIndicator("规模风险", aum, green_score, max_score, "🟢", f"规模 {aum:.2f} 亿 > 2 亿", True)
    if aum >= 0.5:
        return _ScoredIndicator("规模风险", aum, yellow_score, max_score, "🟡", f"规模 {aum:.2f} 亿（0.5-2 亿）", True)
    return _ScoredIndicator("规模风险", aum, 0, max_score, "🔴", f"规模 {aum:.2f} 亿 < 5000 万", True)


def score_manager_change(
    fund_manager: FundManagerInfo | None,
    report_year: int,
) -> _ScoredIndicator:
    """指标 5：基金经理变更（满分 20）。"""
    if not fund_manager or not fund_manager.tenure_start:
        return _ScoredIndicator("基金经理变更", None, 0, 20, "🟡", "无数据", False)

    year_match = re.search(r"(\d{4})", fund_manager.tenure_start)
    if not year_match:
        return _ScoredIndicator("基金经理变更", None, 0, 20, "🟡", "任职日期不可解析", False)

    tenure_year = int(year_match.group(1))
    if tenure_year < report_year:
        return _ScoredIndicator("基金经理变更", float(tenure_year), 20, 20, "🟢", f"任职 {tenure_year} 年 < 报告年份 {report_year}，未变更", True)
    return _ScoredIndicator("基金经理变更", float(tenure_year), 0, 20, "🔴", f"任职 {tenure_year} 年 >= 报告年份 {report_year}，已变更", True)


def score_concentration(
    holdings: dict[int, tuple[HoldingExtraction, ...]],
    *,
    max_score: int = 15,
) -> _ScoredIndicator:
    """指标 6：持仓集中度。

    参数:
        holdings: 多年度持仓数据。
        max_score: 本指标满分。
    """
    green_score = max_score
    yellow_score = round(max_score * 2 / 3)
    red_score = round(max_score / 3)

    latest_year = max(holdings.keys()) if holdings else None
    if latest_year is None or not holdings[latest_year]:
        return _ScoredIndicator("持仓集中度", None, 0, max_score, "🟡", "无数据", False)

    top10 = holdings[latest_year][:10]
    total_pct = 0.0
    for h in top10:
        pct = _parse_percent(h.percentage)
        if pct is not None:
            total_pct += pct

    if total_pct <= 0:
        return _ScoredIndicator("持仓集中度", None, 0, max_score, "🟡", "持仓占比数据不可解析", False)

    if total_pct < 50.0:
        return _ScoredIndicator("持仓集中度", total_pct, green_score, max_score, "🟢", f"前 10 占比 {total_pct:.1f}% < 50%", True)
    if total_pct <= 70.0:
        return _ScoredIndicator("持仓集中度", total_pct, yellow_score, max_score, "🟡", f"前 10 占比 {total_pct:.1f}%（50-70%）", True)
    return _ScoredIndicator("持仓集中度", total_pct, red_score, max_score, "🔴", f"前 10 占比 {total_pct:.1f}% > 70%", True)


# --- 转换 helper ---

def to_signal_indicator(ind: _ScoredIndicator) -> SignalIndicator:
    """将 _ScoredIndicator 转换为 SignalIndicator DTO。"""
    return SignalIndicator(ind.name, ind.score, ind.max_score, ind.detail)


def to_risk_item(ind: _ScoredIndicator, risk_name: str | None = None) -> RiskChecklistItem:
    """将 _ScoredIndicator 转换为 RiskChecklistItem DTO。"""
    return RiskChecklistItem(risk_name or ind.name, ind.risk_status, ind.detail)
