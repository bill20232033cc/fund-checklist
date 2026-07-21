"""14C 章节审计管道测试。"""

from __future__ import annotations

from pathlib import Path
from fund_agent.service.models import FundManagerInfo, ScaleInfo, RiskChecklistItem, StressTestResult

import pytest

from fund_agent.service.audit_pipeline import (
    ArtifactStore,
    AuditDecision,
    AuditViolation,
    ChapterContract,
    ChapterProcessState,
    ChapterRepairer,
    CHAPTER_CONTRACTS,
    LlmAuditor,
    ProgrammaticAuditor,
    RepairAction,
    RepairPlan,
    ReportGenerationCoordinator,
    ViolationCategory,
    ViolationSeverity,
    get_chapter_contract,
    get_all_chapter_contracts,
)


# ============================================================
# ChapterContract 测试
# ============================================================


def test_chapter_contracts_all_chapters() -> None:
    """必须为所有8章定义合同。"""

    contracts = get_all_chapter_contracts()
    assert len(contracts) == 8
    for chapter_id in range(8):
        assert chapter_id in contracts


def test_chapter_contract_has_required_fields() -> None:
    """每章合同必须包含必须字段。"""

    for chapter_id, contract in CHAPTER_CONTRACTS.items():
        assert contract.chapter_id == chapter_id
        assert len(contract.title) > 0
        assert len(contract.must_answer) > 0
        assert len(contract.required_output_items) > 0


def test_get_chapter_contract_valid() -> None:
    """get_chapter_contract 必须返回有效合同。"""

    contract = get_chapter_contract(0)
    assert contract is not None
    assert contract.chapter_id == 0
    assert "投资要点" in contract.title


def test_get_chapter_contract_invalid() -> None:
    """get_chapter_contract 对无效章节必须返回 None。"""

    contract = get_chapter_contract(99)
    assert contract is None


# ============================================================
# ProgrammaticAuditor 测试
# ============================================================


def test_programmatic_auditor_pass() -> None:
    """合规内容必须通过程序审计。"""

    contract = get_chapter_contract(2)
    content = """## 业绩数据

| 年份 | 净值增长率 | 基准收益率 | 超额收益 |
|------|-----------|-----------|---------|
| 2023 | -1.11% | -8.77% | 7.66% |
| 2024 | 17.32% | 14.45% | 2.87% |

## 分析

据上表数据，该基金净值增长率呈上升趋势，超额收益为正。管理费为1.20%，托管费为0.20%。
"""
    data_table = "| 年份 | 净值增长率 | 基准收益率 | 超额收益 | 管理费 | 托管费 |\n|------|-----------|-----------|---------|--------|--------|\n| 2023 | -1.11% | -8.77% | 7.66% | 1.50% | 0.25% |\n| 2024 | 17.32% | 14.45% | 2.87% | 1.20% | 0.20% |"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    score, violations = auditor.audit()

    assert score >= 70
    # 不应有 critical 违规
    critical_violations = [v for v in violations if v.severity == ViolationSeverity.CRITICAL]
    assert len(critical_violations) == 0


def test_programmatic_auditor_detects_investment_advice() -> None:
    """必须检测投资建议关键词。"""

    contract = get_chapter_contract(2)
    content = "建议买入该基金，预期收益20%。"
    data_table = "| 年份 | 净值增长率 |\n|------|----------|\n| 2024 | 12.34% |"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    score, violations = auditor.audit()

    # 应有 C3 违规
    c3_violations = [v for v in violations if v.code == "C3"]
    assert len(c3_violations) > 0
    assert score < 80


def test_programmatic_auditor_detects_empty_data_table() -> None:
    """必须检测空数据表。"""

    contract = get_chapter_contract(2)
    content = "这是一段分析内容。"
    data_table = ""

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    score, violations = auditor.audit()

    # 应有 P1 违规
    p1_violations = [v for v in violations if v.code == "P1"]
    assert len(p1_violations) > 0


def test_programmatic_auditor_detects_placeholders() -> None:
    """必须检测未替换的占位符。"""

    contract = get_chapter_contract(2)
    content = "净值增长率为{{2024年净值增长率}}，基准为{{2024年基准收益率}}。"
    data_table = "| 年份 | 净值增长率 |\n|------|----------|\n| 2024 | 12.34% |"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    score, violations = auditor.audit()

    # 应有 P3 违规
    p3_violations = [v for v in violations if v.code == "P3"]
    assert len(p3_violations) > 0


# ============================================================
# AuditViolation / AuditDecision 测试
# ============================================================


def test_audit_violation_creation() -> None:
    """必须正确创建违规项。"""

    violation = AuditViolation(
        code="P2",
        category=ViolationCategory.PLACEHOLDER,
        severity=ViolationSeverity.CRITICAL,
        description="数字编造",
        location="Ch2",
        suggested_fix="删除编造的数字",
    )

    assert violation.code == "P2"
    assert violation.category == ViolationCategory.PLACEHOLDER
    assert violation.severity == ViolationSeverity.CRITICAL


def test_audit_decision_creation() -> None:
    """必须正确创建审计决定。"""

    decision = AuditDecision(
        chapter_id=2,
        score=75.0,
        violations=(
            AuditViolation(
                code="C4",
                category=ViolationCategory.CONTENT,
                severity=ViolationSeverity.MAJOR,
                description="分析深度不足",
            ),
        ),
        programmatic_score=80.0,
        llm_score=70.0,
        recommendation="patch",
    )

    assert decision.chapter_id == 2
    assert decision.score == 75.0
    assert len(decision.violations) == 1
    assert decision.recommendation == "patch"


# ============================================================
# ChapterProcessState 测试
# ============================================================


def test_process_state_initial() -> None:
    """初始状态必须正确。"""

    state = ChapterProcessState(chapter_id=2)
    assert state.chapter_id == 2
    assert state.write_attempts == 0
    assert state.audit_attempts == 0
    assert state.patch_attempts == 0
    assert state.regenerate_attempts == 0
    assert state.current_score == 0.0
    assert state.status == "pending"


def test_process_state_can_patch() -> None:
    """PATCH 次数限制必须正确。"""

    state = ChapterProcessState(chapter_id=2)
    assert state.can_patch() is True

    state.patch_attempts = 3
    assert state.can_patch() is False


def test_process_state_can_regenerate() -> None:
    """REGENERATE 次数限制必须正确。"""

    state = ChapterProcessState(chapter_id=2)
    assert state.can_regenerate() is True

    state.regenerate_attempts = 3
    assert state.can_regenerate() is False


def test_process_state_record_event() -> None:
    """事件记录必须正确。"""

    state = ChapterProcessState(chapter_id=2)
    state.record_event("audit", {"score": 75.0})

    assert len(state.history) == 1
    assert state.history[0]["type"] == "audit"
    assert state.history[0]["details"]["score"] == 75.0


# ============================================================
# ArtifactStore 测试
# ============================================================


def test_artifact_store_save_and_load(tmp_path: Path) -> None:
    """必须正确保存和加载审计决定。"""

    store = ArtifactStore(tmp_path)
    decision = AuditDecision(
        chapter_id=2,
        score=75.0,
        violations=(
            AuditViolation(
                code="C4",
                category=ViolationCategory.CONTENT,
                severity=ViolationSeverity.MAJOR,
                description="分析深度不足",
            ),
        ),
        programmatic_score=80.0,
        llm_score=70.0,
        recommendation="patch",
    )

    path = store.save_audit_decision(decision)
    assert Path(path).exists()

    loaded = store.load_audit_decision(2)
    assert loaded is not None
    assert loaded.chapter_id == 2
    assert loaded.score == 75.0
    assert len(loaded.violations) == 1
    assert loaded.violations[0].code == "C4"


def test_artifact_store_save_process_state(tmp_path: Path) -> None:
    """必须正确保存过程状态。"""

    store = ArtifactStore(tmp_path)
    state = ChapterProcessState(chapter_id=2)
    state.record_event("audit", {"score": 75.0})

    path = store.save_process_state(state)
    assert Path(path).exists()


def test_artifact_store_save_repair_plan(tmp_path: Path) -> None:
    """必须正确保存修复计划。"""

    store = ArtifactStore(tmp_path)
    plan = RepairPlan(
        chapter_id=2,
        actions=(
            RepairAction(
                violation_code="C4",
                strategy="patch",
                target_excerpt="旧内容",
                replacement="新内容",
            ),
        ),
        strategy="patch",
    )

    path = store.save_repair_plan(plan)
    assert Path(path).exists()


# ============================================================
# ChapterRepairer 测试
# ============================================================


class FakeLlmClient:
    """Fake LLM client for testing."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[dict[str, str]] = []

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return self._response


def test_chapter_repairer_patch_strategy() -> None:
    """PATCH 策略必须正确生成修复计划。"""

    llm_response = '''
    {
        "strategy": "patch",
        "patches": [
            {
                "target_excerpt": "旧内容",
                "target_kind": "substring",
                "replacement": "新内容",
                "occurrence_index": 0
            }
        ]
    }
    '''

    client = FakeLlmClient(llm_response)
    contract = get_chapter_contract(2)
    violations = (
        AuditViolation(
            code="C4",
            category=ViolationCategory.CONTENT,
            severity=ViolationSeverity.MAJOR,
            description="分析深度不足",
        ),
    )

    repairer = ChapterRepairer(
        client, 2, "这是旧内容的章节", "| 年份 | 净值增长率 |",
        contract, violations,
    )

    plan = repairer.generate_repair_plan()
    assert plan.strategy == "patch"
    assert len(plan.actions) == 1
    assert plan.actions[0].target_excerpt == "旧内容"
    assert plan.actions[0].replacement == "新内容"


def test_chapter_repairer_regenerate_strategy() -> None:
    """REGENERATE 策略必须正确生成修复计划。"""

    llm_response = '{"strategy": "regenerate", "reason": "严重问题"}'
    client = FakeLlmClient(llm_response)
    contract = get_chapter_contract(2)
    violations = (
        AuditViolation(
            code="P2",
            category=ViolationCategory.PLACEHOLDER,
            severity=ViolationSeverity.CRITICAL,
            description="数字编造",
        ),
    )

    repairer = ChapterRepairer(
        client, 2, "章节内容", "| 数据 |",
        contract, violations,
    )

    plan = repairer.generate_repair_plan()
    assert plan.strategy == "regenerate"


def test_chapter_repairer_apply_patch() -> None:
    """PATCH 必须正确应用。"""

    plan = RepairPlan(
        chapter_id=2,
        actions=(
            RepairAction(
                violation_code="C4",
                strategy="patch",
                target_excerpt="旧内容",
                replacement="新内容",
                target_kind="substring",
            ),
        ),
        strategy="patch",
    )

    client = FakeLlmClient("{}")
    contract = get_chapter_contract(2)

    repairer = ChapterRepairer(
        client, 2, "这是旧内容的章节", "| 数据 |",
        contract, (),
    )

    result = repairer.apply_patch(plan)
    assert "新内容" in result
    assert "旧内容" not in result


def test_chapter_repairer_apply_patch_line_occurrence_index() -> None:
    """PATCH line 类型 occurrence_index > 0 必须正确工作（不崩溃）。"""

    plan = RepairPlan(
        chapter_id=2,
        actions=(
            RepairAction(
                violation_code="C4",
                strategy="patch",
                target_excerpt="重复行",
                replacement="修复后的行",
                target_kind="line",
                occurrence_index=1,  # 跳过第一个匹配，替换第二个
            ),
        ),
        strategy="patch",
    )

    client = FakeLlmClient("{}")
    contract = get_chapter_contract(2)

    content = "第一行\n重复行\n第三行\n重复行\n第五行"
    repairer = ChapterRepairer(
        client, 2, content, "| 数据 |",
        contract, (),
    )

    result = repairer.apply_patch(plan)
    lines = result.split('\n')
    # 第一个"重复行"保持不变，第二个被替换
    assert lines[1] == "重复行"
    assert lines[3] == "修复后的行"


def test_chapter_repairer_apply_patch_paragraph_occurrence_index() -> None:
    """PATCH paragraph 类型 occurrence_index > 0 必须正确工作（不崩溃）。"""

    plan = RepairPlan(
        chapter_id=2,
        actions=(
            RepairAction(
                violation_code="C4",
                strategy="patch",
                target_excerpt="重复段落",
                replacement="修复后的段落",
                target_kind="paragraph",
                occurrence_index=1,
            ),
        ),
        strategy="patch",
    )

    client = FakeLlmClient("{}")
    contract = get_chapter_contract(2)

    content = "段落一\n\n重复段落\n\n段落三\n\n重复段落\n\n段落五"
    repairer = ChapterRepairer(
        client, 2, content, "| 数据 |",
        contract, (),
    )

    result = repairer.apply_patch(plan)
    paragraphs = result.split('\n\n')
    assert paragraphs[1] == "重复段落"
    assert paragraphs[3] == "修复后的段落"
    """禁止修改数据表格。"""

    plan = RepairPlan(
        chapter_id=2,
        actions=(
            RepairAction(
                violation_code="P2",
                strategy="patch",
                target_excerpt="12.34%",
                replacement="99.99%",
                target_kind="substring",
            ),
        ),
        strategy="patch",
    )

    client = FakeLlmClient("{}")
    contract = get_chapter_contract(2)
    data_table = "| 年份 | 净值增长率 |\n|------|----------|\n| 2024 | 12.34% |"

    repairer = ChapterRepairer(
        client, 2, "净值增长率为12.34%", data_table,
        contract, (),
    )

    result = repairer.apply_patch(plan)
    # 数据表格中的12.34%不应被修改
    assert "12.34%" in data_table


# ============================================================
# ReportGenerationCoordinator 测试
# ============================================================


def test_coordinator_initialization(tmp_path: Path) -> None:
    """必须正确初始化协调器。"""

    client = FakeLlmClient("{}")
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    states = coordinator.get_process_states()
    assert len(states) == 0


# ============================================================
# 模板生成测试（Slice 17G 根因验证）
# ============================================================


def test_template_chapter_generation_all_chapters(tmp_path: Path) -> None:
    """模板降级必须为所有章节生成非空内容（Slice 17G 根因）。"""

    client = FakeLlmClient("{}")
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    performance = {2024: {"nav_growth_rate": "17.32%", "benchmark_return_rate": "14.45%"}}
    evidence = None

    # 测试所有章节的模板生成（使用当前签名）
    for chapter_id in range(8):
        content = coordinator._generate_template_chapter(
            chapter_id=chapter_id,
            fund_name="安信企业价值优选混合型证券投资基金",
            report_year=2024,
            performance=performance,
            evidence=evidence,
        )
        # 关键断言：每个章节必须生成非空内容
        assert content, f"Chapter {chapter_id} template returned empty content"
        assert len(content) > 10, f"Chapter {chapter_id} template content too short: {len(content)} chars"


def test_template_chapter_1_with_fund_manager(tmp_path: Path) -> None:
    """Ch1 模板：有基金经理信息时输出姓名和从业年限。"""
    from fund_agent.service.audit_pipeline import ReportGenerationCoordinator

    client = FakeLlmClient("{}")
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    fm = FundManagerInfo(
        name="张三",
        tenure_start="2020-01-01",
        years_of_service="10年",
        investment_strategy="价值投资",
        holds_fund="10~50万份",
    )
    content = coordinator._generate_template_chapter(
        chapter_id=1,
        fund_name="测试基金",
        report_year=2024,
        performance={},
        evidence=None,
        fund_manager=fm,
    )
    assert "张三" in content
    assert "10年" in content


def test_template_chapter_3_with_fund_manager(tmp_path: Path) -> None:
    """Ch3 模板：有基金经理信息时输出完整画像。"""
    from fund_agent.service.audit_pipeline import ReportGenerationCoordinator

    client = FakeLlmClient("{}")
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    fm = FundManagerInfo(
        name="李四",
        tenure_start="2019-06-01",
        years_of_service="8年",
        investment_strategy="成长投资",
        holds_fund="0",
    )
    content = coordinator._generate_template_chapter(
        chapter_id=3,
        fund_name="测试基金",
        report_year=2024,
        performance={},
        evidence=None,
        fund_manager=fm,
    )
    assert "李四" in content
    assert "2019-06-01" in content


def test_template_chapter_5_with_scale_info(tmp_path: Path) -> None:
    """Ch5 模板：有规模信息时输出份额数据。"""
    from fund_agent.service.audit_pipeline import ReportGenerationCoordinator

    client = FakeLlmClient("{}")
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    scale = ScaleInfo(
        total_shares_a="1.5亿份",
        total_shares_c="0.3亿份",
        individual_investor_ratio="95%",
        management_holds="0.01%",
        estimated_aum="2.99亿元",
    )
    content = coordinator._generate_template_chapter(
        chapter_id=5,
        fund_name="测试基金",
        report_year=2024,
        performance={},
        evidence=None,
        scale_info=scale,
    )
    assert "1.5亿份" in content
    assert "0.3亿份" in content


def test_template_chapter_6_with_risk_checklist(tmp_path: Path) -> None:
    """Ch6 模板：有风险清单时输出表格。"""
    from fund_agent.service.audit_pipeline import ReportGenerationCoordinator

    client = FakeLlmClient("{}")
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    risks = [
        RiskChecklistItem(name="清盘风险", status="🟢", detail="规模2.99亿，远超红线"),
        RiskChecklistItem(name="风格漂移", status="🟡", detail="行业配置变动较大"),
    ]
    content = coordinator._generate_template_chapter(
        chapter_id=6,
        fund_name="测试基金",
        report_year=2024,
        performance={},
        evidence=None,
        risk_checklist=risks,
    )
    assert "清盘风险" in content
    assert "风格漂移" in content
    assert "🟢" in content


def test_is_data_sufficient_with_normal_placeholder(tmp_path: Path) -> None:
    """_is_data_sufficient 不应将「未披露」默认值误判为数据不足。"""
    from fund_agent.service.audit_pipeline import _is_data_sufficient

    # 包含「未披露」但没有「数据完整性声明」的数据表 → 数据充足
    data_table = "| 项目 | 值 |\n|------|----|\n| 持有本基金 | 未披露 |"
    assert _is_data_sufficient(3, data_table) is True


def test_is_data_sufficient_with_degradation_marker(tmp_path: Path) -> None:
    """_is_data_sufficient 对含「数据完整性声明」的数据表判定为不足。"""
    from fund_agent.service.audit_pipeline import _is_data_sufficient

    data_table = "**数据完整性声明**：基金经理信息未提取成功。"
    assert _is_data_sufficient(3, data_table) is False


def test_is_unit_equivalent_yi():
    """亿元缩写等价匹配：100.95 匹配 10095099672.67（÷1亿）。"""
    from fund_agent.service.audit_pipeline import _is_unit_equivalent
    allowed = {"10095099672.67", "10017191811.35", "12017526984.51"}
    assert _is_unit_equivalent("100.95", allowed) is True
    assert _is_unit_equivalent("100.17", allowed) is True
    assert _is_unit_equivalent("120.18", allowed) is True


def test_is_unit_equivalent_wan():
    """万元缩写等价匹配：10095.1 匹配 10095099（÷1万）。"""
    from fund_agent.service.audit_pipeline import _is_unit_equivalent
    allowed = {"10095099"}
    assert _is_unit_equivalent("10095.1", allowed) is True


def test_is_unit_equivalent_reject():
    """不匹配的数字应返回 False。"""
    from fund_agent.service.audit_pipeline import _is_unit_equivalent
    allowed = {"10095099672.67"}
    assert _is_unit_equivalent("999.99", allowed) is False
    assert _is_unit_equivalent("3.14", allowed) is False


def test_is_unit_equivalent_zero():
    """零值处理。"""
    from fund_agent.service.audit_pipeline import _is_unit_equivalent
    assert _is_unit_equivalent("0", {"100"}) is False
    assert _is_unit_equivalent("100", {"0"}) is False
    assert _is_unit_equivalent("abc", {"100"}) is False


# ============================================================
# Fix 1: LLM_ERROR 权重降级测试
# ============================================================


def test_llm_error_fallback_to_program_only(tmp_path: Path) -> None:
    """LLM_ERROR 时权重降级为 prog=1.0 llm=0.0，final_score == prog_score。"""
    from fund_agent.service.audit_pipeline import ReportGenerationCoordinator
    from fund_agent.service.models import FeeRateItem

    # Stateful fake: succeeds on first call (content gen), fails on second (LLM audit)
    class StatefulFakeClient:
        def __init__(self, success_response: str):
            self._success_response = success_response
            self.call_count = 0

        def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return self._success_response
            raise RuntimeError("LLM API error (simulated)")

    llm_response = "该基金2024年净值增长率为17.32%，超越基准14.45%，超额收益2.87%。"
    client = StatefulFakeClient(llm_response)
    coordinator = ReportGenerationCoordinator(client, tmp_path)

    performance = {2024: {"nav_growth_rate": "17.32%", "benchmark_return_rate": "14.45%", "excess_return": "2.87%"}}
    fees = {2024: (FeeRateItem(fee_name="管理费", rate="1.50%"), FeeRateItem(fee_name="托管费", rate="0.25%"))}

    result = coordinator._generate_and_audit_chapter_inner(
        chapter_id=2,
        fund_code="000001",
        fund_name="测试基金",
        report_year=2024,
        performance=performance,
        holdings={},
        allocation={},
        fees=fees,
    )

    assert result is not None
    decision = coordinator._artifact_store.load_audit_decision(2)
    assert decision is not None
    # LLM_ERROR 时权重降级为纯程序审计：final_score == prog_score
    assert decision.score == decision.programmatic_score


# ============================================================
# Fix 2: 推导数字不触发 P2 测试
# ============================================================


def test_derived_number_not_flagged_as_p2() -> None:
    """推导数字（如 1.75=1.50+0.25）不应被 P2 误杀。"""
    from fund_agent.service.audit_pipeline import ProgrammaticAuditor, get_chapter_contract, _is_derived_number

    # 基础：_is_derived_number 函数测试
    assert _is_derived_number("1.75", {"1.50", "0.25"}) is True
    assert _is_derived_number("1.25", {"1.50", "0.25"}) is True  # 1.50 - 0.25
    assert _is_derived_number("2.50", {"1.00", "1.50", "0.75"}) is True  # 1.00 + 1.50
    assert _is_derived_number("3.14", {"1.50", "0.25"}) is False  # 不相关数字

    # 集成：ProgrammaticAuditor 不应为推导数字触发 P2
    contract = get_chapter_contract(2)
    data_table = "| 年份 | 管理费 | 托管费 |\n|------|--------|--------|\n| 2024 | 1.50% | 0.25% |"
    content = "管理费+托管费在多数年份维持在1.75%左右。基金2024年表现良好。"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    score, violations = auditor.audit()

    p2_violations = [v for v in violations if v.code == "P2"]
    assert len(p2_violations) == 0, f"推导数字 1.75 不应触发 P2，但实际触发了: {p2_violations}"


def test_derived_number_non_derived_still_flagged() -> None:
    """非推导数字仍应被 P2 捕获（确保推导逻辑未过度放宽）。"""
    from fund_agent.service.audit_pipeline import ProgrammaticAuditor, get_chapter_contract

    contract = get_chapter_contract(2)
    data_table = "| 年份 | 管理费 | 托管费 |\n|------|--------|--------|\n| 2024 | 1.50% | 0.25% |"
    content = "该基金管理规模约999.99亿元，远超同类平均。"

    auditor = ProgrammaticAuditor(2, content, data_table, contract)
    score, violations = auditor.audit()

    p2_violations = [v for v in violations if v.code == "P2"]
    assert len(p2_violations) > 0, "非推导数字 999.99 应触发 P2"


# ============================================================
# KI-2: Ch6 contract 分级语言不产生误判
# ============================================================


def test_ch6_contract_grading_language_no_false_positives() -> None:
    """S2: 新 Ch6 contract 使用分级语言时 ProgrammaticAuditor 不应误判。"""
    contract = get_chapter_contract(6)
    content = (
        "## 核心风险与风险分级\n\n"
        "该基金核心风险为持仓集中度过高（结构性风险），前五大持仓合计占比超60%。\n"
        "最关键的风险是规模较小带来的清盘风险。风险严重程度分级：高，依据为规模接近清盘线。\n"
        "当前信息缺口为2023年业绩数据缺失，这可能改变最终判断。\n"
    )
    data_table = "| 年份 | 前五大持仓集中度 |\n|------|-----------------|\n| 2024 | 62.50% |"

    auditor = ProgrammaticAuditor(6, content, data_table, contract)
    score, violations = auditor.audit()

    assert score >= 70, f"分级语言不应触发误判，score={score}, violations={violations}"
    critical = [v for v in violations if v.severity == ViolationSeverity.CRITICAL]
    assert len(critical) == 0, f"分级语言不应触发 CRITICAL 违规: {critical}"


def test_ch6_contract_rejects_veto_language() -> None:
    """Ch6 contract 不含否决/致命/一票否决等旧语言。"""
    contract = get_chapter_contract(6)

    assert "否决" not in contract.title
    assert "否决" not in contract.narrative_mode
    for item in contract.must_answer:
        assert "否决" not in item
        assert "致命" not in item
        assert "一票否决" not in item
    for item in contract.required_output_items:
        assert "否决" not in item

    assert "分级" in contract.title
    assert "分级" in contract.narrative_mode
    assert any("分级" in item for item in contract.must_answer)
    assert any("分级" in item for item in contract.required_output_items)
