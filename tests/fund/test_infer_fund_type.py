"""infer_fund_type 参数化测试。

覆盖5类基金 × 至少2种命名变体，确保关键词顺序依赖有回归保护。
"""
from __future__ import annotations

import pytest

from fund_agent.service.extraction import infer_fund_type


@pytest.mark.parametrize(
    "fund_name, expected_type",
    [
        # A股 ETF
        ("华泰柏瑞中证红利低波动交易型开放式指数证券投资基金", "index_etf"),
        ("易方达沪深300交易型开放式指数发起式证券投资基金", "index_etf"),
        # QDII ETF
        ("华安纳斯达克100ETF（QDII）", "index_etf"),
        ("博时标普500ETF联接(QDII)A", "index_feeder"),
        # 联接基金
        ("华泰柏瑞中证红利低波动交易型开放式指数证券投资基金联接基金", "index_feeder"),
        ("华安纳斯达克100ETF联接(QDII)A", "index_feeder"),
        ("易方达沪深300交易型开放式指数发起式证券投资基金联接基金", "index_feeder"),
        # 普通指数基金
        ("招商中证1000指数增强型证券投资基金", "index_fund"),
        ("天弘中证500指数增强型证券投资基金", "index_fund"),
        # 债券基金
        ("国泰利享中短债债券型证券投资基金", "bond_fund"),
        ("招商招悦纯债债券型证券投资基金", "bond_fund"),
        # 主动权益
        ("兴全商业模式优选混合型证券投资基金（LOF）", "active_fund"),
        ("东方红京东大数据混合型证券投资基金", "active_fund"),
    ],
)
def test_infer_fund_type(fund_name: str, expected_type: str) -> None:
    """验证基金名称 → 类型推断的正确性。"""
    fund_type, inferred = infer_fund_type(fund_name)
    assert fund_type == expected_type, (
        f"期望 {expected_type}，实际 {fund_type}：{fund_name}"
    )
    assert inferred is True
