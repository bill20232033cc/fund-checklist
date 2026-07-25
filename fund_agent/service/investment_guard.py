"""统一投资建议关键词检测 — 单一真源。

合并自:
- extraction.py 的 pre-LLM routing guard 关键词
- audit_pipeline.py 的 C3 审计关键词
- llm_tool_loop.py 的 post-LLM answer guard 关键词
"""

from __future__ import annotations

# 统一投资建议关键词（frozenset 不可变）
INVESTMENT_ADVICE_KEYWORDS: frozenset[str] = frozenset(
    {
        # 基础买卖
        "买入",
        "卖出",
        # 建议/推荐操作
        "建议买入",
        "建议卖出",
        "建议加仓",
        "建议减仓",
        "推荐买入",
        "推荐卖出",
        "强烈建议",
        "强烈推荐",
        "强烈买入",
        "强烈卖出",
        # 仓位调整
        "增持",
        "减持",
        # 价格/收益预测
        "目标价",
        "预期收益",
        "预计涨幅",
        "预期回报",
    }
)


def contains_investment_advice(text: str) -> bool:
    """检查文本是否包含投资建议关键词。

    参数:
        text: 待检测文本。

    返回:
        包含任一关键词时返回 True，否则 False。
    """
    return any(kw in text for kw in INVESTMENT_ADVICE_KEYWORDS)
