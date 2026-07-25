"""统一投资建议关键词检测测试。

覆盖:
- 买入/卖出类关键词触发
- 增持/减持/目标价触发
- 正常分析内容不触发
- 关键词含在更长词中（子串匹配）
- contains_investment_advice 边界情况
"""

import pytest

from fund_agent.service.investment_guard import (
    INVESTMENT_ADVICE_KEYWORDS,
    contains_investment_advice,
)


class TestInvestmentAdviceKeywords:
    """关键词常量完整性测试。"""

    def test_buy_sell_keywords_present(self):
        """买入/卖出基础关键词存在。"""
        assert "买入" in INVESTMENT_ADVICE_KEYWORDS
        assert "卖出" in INVESTMENT_ADVICE_KEYWORDS

    def test_recommend_keywords_present(self):
        """推荐类关键词存在。"""
        assert "推荐买入" in INVESTMENT_ADVICE_KEYWORDS
        assert "推荐卖出" in INVESTMENT_ADVICE_KEYWORDS
        assert "强烈推荐" in INVESTMENT_ADVICE_KEYWORDS
        assert "强烈建议" in INVESTMENT_ADVICE_KEYWORDS

    def test_position_keywords_present(self):
        """仓位/操作关键词存在。"""
        assert "增持" in INVESTMENT_ADVICE_KEYWORDS
        assert "减持" in INVESTMENT_ADVICE_KEYWORDS
        assert "建议加仓" in INVESTMENT_ADVICE_KEYWORDS
        assert "建议减仓" in INVESTMENT_ADVICE_KEYWORDS

    def test_target_and_return_keywords_present(self):
        """目标价/收益关键词存在。"""
        assert "目标价" in INVESTMENT_ADVICE_KEYWORDS
        assert "预期收益" in INVESTMENT_ADVICE_KEYWORDS
        assert "预计涨幅" in INVESTMENT_ADVICE_KEYWORDS
        assert "预期回报" in INVESTMENT_ADVICE_KEYWORDS

    def test_keywords_is_frozenset(self):
        """关键词集合为不可变 frozenset。"""
        assert isinstance(INVESTMENT_ADVICE_KEYWORDS, frozenset)


class TestContainsInvestmentAdvice:
    """contains_investment_advice() 功能测试。"""

    def test_detects_buy_recommendation(self):
        assert contains_investment_advice("建议买入该基金") is True

    def test_detects_sell_recommendation(self):
        assert contains_investment_advice("建议卖出该基金") is True

    def test_detects_target_price(self):
        assert contains_investment_advice("目标价 3.5 元") is True

    def test_detects_add_position(self):
        assert contains_investment_advice("建议加仓成长股") is True

    def test_analysis_content_not_triggered(self):
        assert contains_investment_advice("该基金经理管理规模 50 亿") is False

    def test_normal_attention_not_triggered(self):
        assert contains_investment_advice("建议关注费率变化") is False
        assert contains_investment_advice("投资者需注意风险") is False

    def test_empty_text(self):
        assert contains_investment_advice("") is False

    def test_partial_substring_in_longer_word(self):
        """关键词在更长词中时应触发（因为 contains 匹配）。"""
        # "目标价" 在 "目标价值投资" 中也能匹配
        assert contains_investment_advice("以目标价分析") is True

    def test_all_keywords_individually_trigger(self):
        """每个关键词独立出现都能触发。"""
        for kw in INVESTMENT_ADVICE_KEYWORDS:
            assert contains_investment_advice(f"这是一条包含{kw}的文本") is True, f"关键词 '{kw}' 未被触发"
