"""快照受控 profile + 评分 + 抽取单元测试（Slice D，§6.25 裁决 4/7/9）。"""

from __future__ import annotations

import dataclasses

from fund_agent.service.extraction import DISCLOSURE_LOCATOR_CONTRACT_REGISTRY, _validated_locator_contracts
from fund_agent.service.snapshot_extraction import (
    _QUARTERLY_MISSING_ITEMS,
    SnapshotPerformanceRow,
    SnapshotReportData,
)
from fund_agent.service.snapshot_scoring import compute_snapshot_score


def test_snapshot_profiles_in_registry() -> None:
    """quarterly_performance / semiannual_performance 必须进入受控 profile registry。"""

    profile_names = {c.profile_name for c in DISCLOSURE_LOCATOR_CONTRACT_REGISTRY}
    assert "quarterly_performance" in profile_names
    assert "semiannual_performance" in profile_names


def test_snapshot_profiles_validate() -> None:
    """快照 profile 必须通过 registry 校验（extraction_allowed=False 口径）。"""

    contracts = _validated_locator_contracts()
    snapshot_contracts = [c for c in contracts if c.profile_name in ("quarterly_performance", "semiannual_performance")]
    assert len(snapshot_contracts) == 2
    for contract in snapshot_contracts:
        assert contract.extraction_allowed is False
        assert contract.requires_table_citation is True
        assert contract.acceptable_title_family == (
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "基金净值表现",
        )
        assert contract.anchor_title_family == ("阶段", "份额净值增长率", "业绩比较基准收益率")


def test_annual_contract_registry_unchanged() -> None:
    """快照 profile 不得污染 10G annual 契约（performance_returns 保持不变）。"""

    contracts = _validated_locator_contracts()
    perf = next(c for c in contracts if c.profile_name == "performance_returns")
    assert perf.candidate_queries[0] == "净值增长率"
    assert "超额收益" in perf.aliases
    # annual 契约总数保持：既有 5 个 + 2 个快照 = 7
    assert len(contracts) == 7


def test_snapshot_score_excess_positive() -> None:
    """超额为正 → excess 高分。"""

    data = SnapshotReportData(
        fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
        template_id="quarterly_snapshot", quarter=2,
        performance_rows=(
            SnapshotPerformanceRow(stage="过去一年", nav_growth_rate="10.00%", benchmark_return_rate="5.00%", excess_return="5.00%"),
        ),
        allocation_rows=({"asset_class": "股票投资", "ratio": "85.00%"},),
        holdings_rows=({"stock_name": "A", "ratio": "3.00%"},) * 10,
    )
    score = compute_snapshot_score(data)
    assert score.excess_score == 40
    assert score.position_score == 30
    assert score.concentration_score == 30
    assert score.total_score == 100
    assert score.grade == "优秀"


def test_snapshot_score_excess_negative() -> None:
    """超额为负 → excess 低分；仓位低 → position 低分。"""

    data = SnapshotReportData(
        fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
        template_id="quarterly_snapshot", quarter=1,
        performance_rows=(
            SnapshotPerformanceRow(stage="过去一年", nav_growth_rate="-8.00%", benchmark_return_rate="-2.00%", excess_return="-6.00%"),
        ),
        allocation_rows=({"asset_class": "股票投资", "ratio": "30.00%"},),
        holdings_rows=({"stock_name": "A", "ratio": "9.00%"},) * 10,
    )
    score = compute_snapshot_score(data)
    assert score.excess_score == 0
    assert score.position_score == 5
    assert score.concentration_score == 5
    assert score.total_score == 10
    assert score.grade == "关注"


def test_snapshot_score_computes_excess_from_nav_bench() -> None:
    """excess 缺失时由 nav - bench 推导。"""

    data = SnapshotReportData(
        fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
        template_id="quarterly_snapshot", quarter=2,
        performance_rows=(
            SnapshotPerformanceRow(stage="过去一年", nav_growth_rate="7.00%", benchmark_return_rate="2.00%", excess_return="缺失"),
        ),
        allocation_rows=(), holdings_rows=(),
    )
    score = compute_snapshot_score(data)
    assert score.excess_score == 40  # 7-2=5 >= 5


def test_snapshot_data_missing_items_quarterly() -> None:
    """季报缺失项必须 fail-closed 声明（全部持仓/财务三表/托管人报告等）。"""

    missing = "\n".join(_QUARTERLY_MISSING_ITEMS)
    assert "全部持仓" in missing
    assert "财务" in missing
    assert "托管人" in missing
    assert len(_QUARTERLY_MISSING_ITEMS) >= 5


def test_snapshot_data_missing_items_semiannual_empty() -> None:
    """半年报无季报类缺失项声明。"""

    data = SnapshotReportData(
        fund_code="005680", fund_name="财通资管价值成长混合", report_year=2025,
        template_id="semiannual_snapshot", period="H1",
    )
    assert data.missing_items == ()


def test_snapshot_to_context_dict_covers_all_dataclass_fields() -> None:
    """to_context_dict 必须序列化 dataclass 字段全集（含身份字段与 citations，纯增量）。"""

    data = SnapshotReportData(
        fund_code="005680",
        fund_name="财通资管价值成长混合",
        report_year=2025,
        template_id="semiannual_snapshot",
        quarter=3,
        period="H2",
        performance_rows=(
            SnapshotPerformanceRow(stage="过去一年", nav_growth_rate="7.00%", benchmark_return_rate="2.00%", excess_return="5.00%"),
        ),
        scale_info={"期末份额": "10.00亿份"},
        holdings_rows=({"stock_name": "A", "ratio": "5.00%"},),
        allocation_rows=({"asset_class": "股票投资", "ratio": "80.00%"},),
        industry_rows=({"行业": "制造业", "ratio": "40.00%"},),
        share_change={"本期申购": "1.00亿份"},
        fund_manager={"姓名": "张三"},
        own_funds="固有资金持有 1000 万份",
        operation_analysis="报告期内保持高仓位运作。",
        financial_rows=({"科目": "营业收入", "金额": "1.00亿元"},),
        holder_structure={"机构占比": "30.00%"},
        single_investor_20pct="存在单一投资者持有 25% 份额",
        risk_notes="无重大风险事项",
        missing_items=("全部持仓",),
        latest_performance={"过去一年": "7.00%"},
        citations=({"section_ref": "3.2.1", "table_ref": "table-0002", "page": "5"},),
    )

    context = data.to_context_dict()

    # 可证伪：未来新增字段不同步序列化即红。
    assert set(context.keys()) == {f.name for f in dataclasses.fields(SnapshotReportData)}

    def _expected(field_name: str) -> object:
        value = getattr(data, field_name)
        if field_name == "performance_rows":
            return [
                {
                    "stage": row.stage,
                    "nav_growth_rate": row.nav_growth_rate,
                    "benchmark_return_rate": row.benchmark_return_rate,
                    "excess_return": row.excess_return,
                }
                for row in value
            ]
        if field_name in ("holdings_rows", "allocation_rows", "industry_rows", "financial_rows", "citations"):
            return [dict(item) for item in value]
        if field_name in ("scale_info", "share_change", "fund_manager", "holder_structure", "latest_performance"):
            return dict(value)
        if field_name == "missing_items":
            return list(value)
        return value

    for field in dataclasses.fields(SnapshotReportData):
        assert context[field.name] == _expected(field.name)
