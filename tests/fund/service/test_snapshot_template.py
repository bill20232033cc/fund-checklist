"""快照模板与 coordinator 解耦测试（Slice C，§6.25 裁决 3/5/6）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fund_agent.service.report_template import (
    ANNUAL_TEMPLATE,
    QUARTERLY_SNAPSHOT_TEMPLATE,
    QUARTERLY_SNAPSHOT_TEMPLATE_DOC,
    SEMIANNUAL_SNAPSHOT_TEMPLATE,
    SEMIANNUAL_SNAPSHOT_TEMPLATE_DOC,
    get_report_template,
    snapshot_template_ids,
)


def test_quarterly_snapshot_template_chapters() -> None:
    """季报快照模板必须为 5 章（概览/业绩/持仓/管理人/风险）。"""

    assert QUARTERLY_SNAPSHOT_TEMPLATE.template_id == "quarterly_snapshot"
    assert QUARTERLY_SNAPSHOT_TEMPLATE.chapter_ids == (1, 2, 3, 4, 0)
    assert set(QUARTERLY_SNAPSHOT_TEMPLATE.chapter_titles) == {0, 1, 2, 3, 4}
    assert QUARTERLY_SNAPSHOT_TEMPLATE.chapter_titles[1] == "当期业绩与超额"
    assert QUARTERLY_SNAPSHOT_TEMPLATE.chapter_titles[4] == "风险与跟踪"


def test_semiannual_snapshot_template_chapters() -> None:
    """半年报快照模板必须为 6 章（多「财务质量+持有人」）。"""

    assert SEMIANNUAL_SNAPSHOT_TEMPLATE.template_id == "semiannual_snapshot"
    assert SEMIANNUAL_SNAPSHOT_TEMPLATE.chapter_ids == (1, 2, 3, 4, 5, 0)
    assert set(SEMIANNUAL_SNAPSHOT_TEMPLATE.chapter_titles) == {0, 1, 2, 3, 4, 5}
    assert SEMIANNUAL_SNAPSHOT_TEMPLATE.chapter_titles[3] == "财务质量"
    assert SEMIANNUAL_SNAPSHOT_TEMPLATE.chapter_titles[5] == "风险与持有人"


def test_snapshot_contracts_load_from_namespace() -> None:
    """快照章节契约必须从独立 prompts 命名空间解析（含 title）。"""

    for template, chapter_ids in (
        (QUARTERLY_SNAPSHOT_TEMPLATE, (0, 1, 2, 3, 4)),
        (SEMIANNUAL_SNAPSHOT_TEMPLATE, (0, 1, 2, 3, 4, 5)),
    ):
        for cid in chapter_ids:
            contract = template.load_contract(cid)
            assert contract is not None, f"{template.template_id} ch{cid} contract missing"
            assert contract.title == template.chapter_titles[cid]
            assert len(contract.must_answer) >= 3
            assert len(contract.must_not_cover) >= 1


def test_snapshot_analysis_prompts_load() -> None:
    """快照章节分析 prompt 必须从命名空间正文解析（非空）。"""

    for template, chapter_ids in (
        (QUARTERLY_SNAPSHOT_TEMPLATE, (0, 1, 2, 3, 4)),
        (SEMIANNUAL_SNAPSHOT_TEMPLATE, (0, 1, 2, 3, 4, 5)),
    ):
        for cid in chapter_ids:
            prompt = template.load_analysis_prompt(cid)
            assert prompt, f"{template.template_id} ch{cid} analysis prompt empty"
            assert "买入" not in prompt or "禁止" in prompt


def test_namespace_does_not_touch_annual_chapters() -> None:
    """快照命名空间必须不触碰年报 ch0-ch7 契约与 prompt。"""

    # 年报模板契约仍然可用
    for cid in range(8):
        contract = ANNUAL_TEMPLATE.load_contract(cid)
        assert contract is not None, f"annual ch{cid} contract missing"
    # 年报 ch0 分析 prompt 仍是原内容
    annual_prompt = ANNUAL_TEMPLATE.load_analysis_prompt(0)
    assert annual_prompt and "投资要点概览" in annual_prompt
    # 快照模板的 prompts_dir 是独立命名空间
    assert "quarterly_snapshot" in str(QUARTERLY_SNAPSHOT_TEMPLATE.prompts_dir)
    assert "semiannual_snapshot" in str(SEMIANNUAL_SNAPSHOT_TEMPLATE.prompts_dir)
    assert "quarterly_snapshot" not in str(ANNUAL_TEMPLATE.prompts_dir)


def test_annual_template_registry_default() -> None:
    """registry 必须返回年报默认模板与快照模板。"""

    assert get_report_template("annual_report") is ANNUAL_TEMPLATE
    assert get_report_template("quarterly_snapshot") is QUARTERLY_SNAPSHOT_TEMPLATE
    assert get_report_template("semiannual_snapshot") is SEMIANNUAL_SNAPSHOT_TEMPLATE
    assert get_report_template("unknown_template") is None
    assert set(snapshot_template_ids()) == {"quarterly_snapshot", "semiannual_snapshot"}


def test_snapshot_template_docs_exist() -> None:
    """快照模板设计文档必须存在且含 manifest。"""

    assert QUARTERLY_SNAPSHOT_TEMPLATE_DOC.is_file()
    assert SEMIANNUAL_SNAPSHOT_TEMPLATE_DOC.is_file()
    q_text = QUARTERLY_SNAPSHOT_TEMPLATE_DOC.read_text(encoding="utf-8")
    s_text = SEMIANNUAL_SNAPSHOT_TEMPLATE_DOC.read_text(encoding="utf-8")
    assert "TEMPLATE_CONTRACT_MANIFEST_JSON" in q_text
    assert "TEMPLATE_CONTRACT_MANIFEST_JSON" in s_text
    assert "quarterly_snapshot" in q_text
    assert "semiannual_snapshot" in s_text


def test_annual_data_table_builder_matches_generate_data_table() -> None:
    """年报 build_data_table 必须等价于既有 generate_data_table（解耦不改变行为）。"""

    from fund_agent.service.chapter_generator import generate_data_table

    kwargs = {
        "chapter_id": 2,
        "fund_code": "004393",
        "fund_name": "安信企业价值优选混合型证券投资基金",
        "report_year": 2024,
        "performance": {2024: {"nav_growth_rate": "17.32%", "benchmark_return_rate": "14.45%", "excess_return": "2.87%"}},
        "holdings": {},
        "allocation": {},
        "fees": {},
        "fund_manager": None,
        "scale_info": None,
        "evidence": None,
        "stress_test": None,
        "signal_judgment": None,
        "fund_type": "",
        "contract_effective_date": "",
    }
    via_template = ANNUAL_TEMPLATE.build_data_table(**kwargs)
    direct = generate_data_table(
        chapter_id=2,
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        report_year=2024,
        performance=kwargs["performance"],
        holdings={},
        allocation={},
        fees={},
        fund_manager=None,
        scale_info=None,
        evidence=None,
        stress_test=None,
        signal_judgment=None,
        fund_type="",
        contract_effective_date="",
    )
    assert via_template == direct


def test_annual_template_chapter_builder_matches_legacy(tmp_path) -> None:
    """年报 build_template_chapter 必须等价于解耦前 _generate_template_chapter 行为。"""

    from fund_agent.service.audit_pipeline import ReportGenerationCoordinator, generate_annual_template_chapter

    client = type("FakeClient", (), {"generate_text": staticmethod(lambda **kw: "{}")})()
    coordinator = ReportGenerationCoordinator(client, tmp_path)
    performance = {2024: {"nav_growth_rate": "17.32%"}}

    for cid in range(8):
        legacy = coordinator._generate_template_chapter(
            chapter_id=cid,
            fund_name="测试基金",
            report_year=2024,
            performance=performance,
            evidence=None,
        )
        module_fn = generate_annual_template_chapter(
            chapter_id=cid,
            fund_name="测试基金",
            report_year=2024,
            performance=performance,
            evidence=None,
        )
        assert legacy == module_fn, f"chapter {cid} mismatch"
