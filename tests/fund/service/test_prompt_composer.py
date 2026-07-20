"""Phase 3.6 合同架构重构测试：data_verification + P2 contract-aware。"""

from __future__ import annotations

import pytest

from fund_agent.service.audit_pipeline import (
    ChapterContract,
    DataVerificationRule,
    Metric,
    ProgrammaticAuditor,
    ViolationSeverity,
    load_chapter_contract_from_template,
)


# ============================================================
# data_verification 覆盖测试
# ============================================================


def test_all_chapters_have_data_verification() -> None:
    """Ch0-Ch7 所有章节合同必须包含 data_verification。"""
    for chapter_id in range(8):
        contract = load_chapter_contract_from_template(chapter_id)
        assert contract is not None, f"Ch{chapter_id} 合同加载失败"
        assert len(contract.data_verification) > 0, (
            f"Ch{chapter_id} data_verification 为空"
        )


def test_ch2_ch5_ch6_have_metrics() -> None:
    """Ch2/Ch5/Ch6 必须定义计算指标。"""
    for chapter_id in (2, 5, 6):
        contract = load_chapter_contract_from_template(chapter_id)
        assert contract is not None, f"Ch{chapter_id} 合同加载失败"
        assert len(contract.metrics) > 0, (
            f"Ch{chapter_id} metrics 为空"
        )


def test_ch7_has_metrics() -> None:
    """Ch7 必须定义综合评分指标。"""
    contract = load_chapter_contract_from_template(7)
    assert contract is not None, "Ch7 合同加载失败"
    assert len(contract.metrics) > 0, "Ch7 metrics 为空"
    metric_names = {m.name for m in contract.metrics}
    assert "综合评分" in metric_names, f"Ch7 缺少综合评分指标，现有: {metric_names}"
    assert "6指标评分详情" in metric_names, f"Ch7 缺少6指标评分详情指标，现有: {metric_names}"


# ============================================================
# P2 contract-aware 测试
# ============================================================


def _make_contract(
    chapter_id: int = 2,
    data_verification: tuple[DataVerificationRule, ...] = (),
) -> ChapterContract:
    """构建最小 ChapterContract，仅设 data_verification 字段。"""
    return ChapterContract(
        chapter_id=chapter_id,
        title="测试章节",
        must_answer=("测试问题",),
        must_not_cover=(),
        required_output_items=("测试输出项",),
        data_sources=("performance",),
        data_verification=data_verification,
    )


def test_p2_skipped_without_number_citation_rule() -> None:
    """合同无 number_citation 规则时，P2 检查应跳过。"""
    contract = _make_contract(data_verification=(
        DataVerificationRule(rule_type="comma_handling", description="去除逗号"),
    ))
    content = "该基金净值增长率为 99.99%。"
    data_table = "| 年份 | 净值增长率 |\n|------|----------|\n| 2024 | 12.34% |"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    _, violations = auditor.audit()

    p2_codes = [v.code for v in violations if v.code == "P2"]
    assert len(p2_codes) == 0, (
        f"无 number_citation 规则时应跳过 P2，实际仍触发: {p2_codes}"
    )


def test_p2_runs_with_number_citation_rule() -> None:
    """合同有 number_citation 规则时，P2 应正常触发。"""
    contract = _make_contract(data_verification=(
        DataVerificationRule(rule_type="number_citation", description="引用原始数字"),
        DataVerificationRule(rule_type="comma_handling", description="去除逗号"),
    ))
    # content 中 99.99 不在 data_table 中，应触发 P2
    content = "该基金净值增长率为 99.99%。"
    data_table = "| 年份 | 净值增长率 |\n|------|----------|\n| 2024 | 12.34% |"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    _, violations = auditor.audit()

    p2_codes = [v.code for v in violations if v.code == "P2"]
    assert len(p2_codes) > 0, (
        "有 number_citation 规则且内容含未见数字时，P2 应触发"
    )
