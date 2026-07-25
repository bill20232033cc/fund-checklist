"""Prompt Contributions 测试。

覆盖:
- build_runtime_contribution 输出格式
- build_fund_context_contribution 输出格式
- build_memory_contribution 空/非空
- select_contributions 筛选与排序
"""

import pytest

from fund_agent.service.prompt_contributions import (
    build_fund_context_contribution,
    build_memory_contribution,
    build_runtime_contribution,
    select_contributions,
)


class TestBuildRuntimeContribution:
    """build_runtime_contribution() 测试。"""

    def test_full_context(self):
        result = build_runtime_contribution(
            fund_code="011649", fund_name="XX基金", year=2025
        )
        assert "011649" in result
        assert "XX基金" in result
        assert "2025" in result

    def test_minimal_context_no_crash(self):
        """所有参数为空 → 仍产出标题。"""
        result = build_runtime_contribution()
        assert "## 运行时上下文" in result

    def test_partial_fields(self):
        """部分字段缺失，只显示有的。"""
        result = build_runtime_contribution(fund_code="000001")
        assert "000001" in result
        assert "基金名称" not in result


class TestBuildFundContextContribution:
    """build_fund_context_contribution() 测试。"""

    def test_full_context(self):
        result = build_fund_context_contribution(
            fund_code="011649",
            fund_name="XX基金",
            active_year=2025,
            available_years=(2021, 2022, 2023, 2024, 2025),
        )
        assert "011649" in result
        assert "XX基金" in result
        assert "2025" in result
        assert "2021, 2022, 2023, 2024, 2025" in result

    def test_empty_years(self):
        result = build_fund_context_contribution(
            fund_code="011649", available_years=()
        )
        assert "可用年份" not in result


class TestBuildMemoryContribution:
    """build_memory_contribution() 测试。"""

    def test_with_episode_and_facts(self):
        result = build_memory_contribution(
            episode_summaries_text="## 上一节\n讨论了持仓集中度。",
            pinned_facts=("前十大持仓占净值60%", "基金经理任期5年"),
        )
        assert "## 会话记忆" in result
        assert "讨论了持仓集中度" in result
        assert "前十大持仓占净值60%" in result
        assert "基金经理任期5年" in result

    def test_empty_both_returns_empty_string(self):
        result = build_memory_contribution()
        assert result == ""

    def test_facts_only(self):
        result = build_memory_contribution(pinned_facts=("事实A",))
        assert "事实A" in result
        assert "已确认事实" in result


class TestSelectContributions:
    """select_contributions() 测试。"""

    def test_filters_and_orders_by_slots(self):
        raw = {
            "runtime": "runtime content",
            "memory": "memory content",
            "fund_context": "fund context",
        }
        result = select_contributions(raw, context_slots=("runtime", "memory"))
        assert list(result.keys()) == ["runtime", "memory"]
        assert "fund_context" not in result

    def test_empty_slots(self):
        result = select_contributions({"runtime": "x"}, context_slots=())
        assert result == {}

    def test_missing_slot_skipped(self):
        result = select_contributions(
            {"runtime": "x"}, context_slots=("runtime", "missing")
        )
        assert list(result.keys()) == ["runtime"]

    def test_empty_content_skipped(self):
        result = select_contributions(
            {"runtime": "  "}, context_slots=("runtime",)
        )
        assert result == {}
