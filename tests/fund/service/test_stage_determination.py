"""阶段判定「建仓期」真源修正 slice 确定性单元测试（Ch5 数据表）。

覆盖：旧基金+新经理非建仓期 / 新基金建仓期 / 缺失 fail-closed / 经理 tenure
为空不触发转型期 / 被动基金跳过 / 建仓期不覆盖转型期。
"""
from __future__ import annotations

from fund_agent.service.chapter_generator import generate_data_table
from fund_agent.service.models import (
    AssetAllocationItem,
    FundManagerInfo,
    HoldingExtraction,
    FeeRateItem,
)


def _performance() -> dict[int, dict[str, str]]:
    return {
        2024: {"nav_growth_rate": "3.45%", "benchmark_return_rate": "-3.21%", "excess_return": "6.66%"},
        2025: {"nav_growth_rate": "12.34%", "benchmark_return_rate": "8.76%", "excess_return": "3.58%"},
    }


def _holdings() -> dict[int, tuple[HoldingExtraction, ...]]:
    return {}


def _allocation() -> dict[int, tuple[AssetAllocationItem, ...]]:
    return {
        2024: (AssetAllocationItem(category="股票投资", amount="1,000,000,000.00", percentage_of_net="85.23%"),),
        2025: (AssetAllocationItem(category="股票投资", amount="1,200,000,000.00", percentage_of_net="80.00%"),),
    }


def _fees() -> dict[int, tuple[FeeRateItem, ...]]:
    return {}


def _manager(tenure_start: str = "2025-07-15") -> FundManagerInfo:
    return FundManagerInfo(
        name="李响",
        tenure_start=tenure_start,
        years_of_service="10年",
        investment_strategy="",
        holds_fund="",
    )


def _ch5_table(*, contract_effective_date: str = "", fund_manager=None, fund_type: str = "", allocation=None) -> str:
    """构造 Ch5 数据表。"""

    return generate_data_table(
        5, "005680", "财通资管价值成长混合", 2025,
        _performance(), _holdings(), allocation if allocation is not None else _allocation(), _fees(),
        fund_manager=fund_manager,
        fund_type=fund_type,
        contract_effective_date=contract_effective_date,
    )


def test_old_fund_new_manager_not_building_phase() -> None:
    """旧基金（合同 2019 生效）+ 新经理（2025 任职）：稳定期，不判建仓期。"""

    table = _ch5_table(contract_effective_date="2019-03-25", fund_manager=_manager("2025-07-15"))

    assert "🟢 稳定期" in table
    assert "基金合同 2019 年生效，成立已满2年" in table
    assert "| 判定结果 | 🟡 建仓期 |" not in table


def test_new_fund_is_building_phase() -> None:
    """新基金（合同 2025 生效）：成立不足 2 年判建仓期。"""

    table = _ch5_table(contract_effective_date="2025-01-01", fund_manager=_manager())

    assert "🟡 建仓期" in table
    assert "成立不足2年" in table


def test_missing_contract_date_fail_closed() -> None:
    """合同生效日缺失：不判建仓期，明示跳过，不使用经理任期代理。"""

    table = _ch5_table(contract_effective_date="", fund_manager=_manager("2025-07-15"))

    assert "| 判定结果 | 🟡 建仓期 |" not in table
    assert "建仓期判定跳过" in table


def test_manager_tenure_missing_does_not_trigger_transformation() -> None:
    """经理 tenure_start 为空：不再触发转型期（经理变更退出 5 阶段枚举）。"""

    table = _ch5_table(contract_effective_date="2019-03-25", fund_manager=_manager(""))

    assert "| 判定结果 | 🔴 转型期（优先级最高） |" not in table
    assert "🟢 稳定期" in table


def test_passive_fund_skips_building_phase() -> None:
    """被动基金（index_etf）+ 合同 2025 生效：跳过建仓期判定。"""

    table = _ch5_table(contract_effective_date="2025-01-01", fund_type="index_etf")

    assert "| 判定结果 | 🟡 建仓期 |" not in table
    assert "🟢 稳定期" in table


def test_building_phase_does_not_override_transformation() -> None:
    """建仓期不覆盖转型期（资产配置结构转型优先级更高）。"""

    transform_allocation = {
        2024: (
            AssetAllocationItem(category="股票投资", amount="1,000,000,000.00", percentage_of_net="85.23%"),
            AssetAllocationItem(category="基金投资", amount="1,000.00", percentage_of_net="0.00%"),
        ),
        2025: (
            AssetAllocationItem(category="股票投资", amount="100,000,000.00", percentage_of_net="8.00%"),
            AssetAllocationItem(category="基金投资", amount="900,000,000.00", percentage_of_net="80.00%"),
        ),
    }
    table = _ch5_table(contract_effective_date="2025-01-01", allocation=transform_allocation)

    assert "转型期" in table
    assert "| 判定结果 | 🟡 建仓期 |" not in table
