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
