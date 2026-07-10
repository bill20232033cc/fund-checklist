"""Post-MVP Slice 13B LLM chapter generation 测试（两阶段模式）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fund_agent.service.models import (
    AssetAllocationItem,
    FeeRateItem,
    GenerateReportRequest,
    HoldingExtraction,
)
from fund_agent.service.extraction import FundReadingService
from fund_agent.service.chapter_generator import (
    LlmChapterGenerator,
    contains_non_year_numbers,
    generate_data_table,
)
from fund_agent.fund.document_tools.constants import FailureCode
from fund_agent.fund.document_tools.models import ToolFailure


class FakeLlmClient:
    """按预设返回文本或抛异常的 fake LLM client。"""

    def __init__(self, responses: list[str | Exception] | str = "") -> None:
        if isinstance(responses, str):
            # 单一响应模式：所有调用返回相同内容
            self._responses = []
            self._default_response = responses
        else:
            self._responses = list(responses)
            self._default_response = ""
        self.calls: list[dict[str, str]] = []

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
        """记录调用并返回预设响应。"""

        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})

        # 审计调用返回高分 JSON（确保通过审计）
        if "审计" in system_prompt or "audit" in system_prompt.lower():
            return '{"score": 99, "violations": []}'

        # 修复调用返回 JSON
        if "修复" in system_prompt or "repair" in system_prompt.lower():
            return '{"strategy": "none"}'

        if self._responses:
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        if self._default_response:
            return self._default_response
        raise RuntimeError("fake llm exhausted")


def _sample_performance() -> dict[int, dict[str, str]]:
    return {
        2022: {"nav_growth_rate": "-5.23%", "benchmark_return_rate": "-15.12%", "excess_return": "9.89%"},
        2023: {"nav_growth_rate": "3.45%", "benchmark_return_rate": "-3.21%", "excess_return": "6.66%"},
        2024: {"nav_growth_rate": "12.34%", "benchmark_return_rate": "8.76%", "excess_return": "3.58%"},
    }


def _sample_holdings() -> dict[int, tuple[HoldingExtraction, ...]]:
    return {
        2024: (
            HoldingExtraction(rank=1, stock_code="600519", stock_name="贵州茅台", quantity="100000", fair_value="180000000.00", percentage="8.52%"),
            HoldingExtraction(rank=2, stock_code="000858", stock_name="五粮液", quantity="80000", fair_value="130000000.00", percentage="6.31%"),
        ),
    }


def _sample_allocation() -> dict[int, tuple[AssetAllocationItem, ...]]:
    return {
        2024: (
            AssetAllocationItem(category="股票投资", amount="1,234,567,890.00", percentage_of_net="85.23%"),
        ),
    }


def _sample_fees() -> dict[int, tuple[FeeRateItem, ...]]:
    return {
        2024: (
            FeeRateItem(fee_name="基金管理费", rate="1.20%"),
            FeeRateItem(fee_name="基金托管费", rate="0.20%"),
        ),
    }


def test_generate_data_table_ch2_performance() -> None:
    """Ch2 R=A+B-C 表格必须包含真实业绩和费率数字。"""

    table = generate_data_table(2, "004393", "测试基金", 2024, _sample_performance(), {}, {}, _sample_fees())

    assert "12.34%" in table
    assert "8.76%" in table
    assert "1.20%" in table  # 费率数据也在 Ch2


def test_generate_data_table_ch3_holdings() -> None:
    """Ch3 基金经理画像表格必须包含真实持仓数据。"""

    table = generate_data_table(3, "004393", "测试基金", 2024, {}, _sample_holdings(), {}, {})

    assert "600519" in table
    assert "贵州茅台" in table
    assert "8.52%" in table


def test_generate_data_table_ch5_scale() -> None:
    """Ch5 当前阶段表格必须包含资产配置数据。"""

    table = generate_data_table(5, "004393", "测试基金", 2024, {}, {}, _sample_allocation(), {})

    assert "股票投资" in table
    assert "85.23%" in table


def test_contains_non_year_numbers_detects() -> None:
    """非年份数字必须被检测到。"""

    assert contains_non_year_numbers("净值增长率为12.34%") is True
    assert contains_non_year_numbers("占比8.52%") is True


def test_contains_non_year_numbers_allows_years() -> None:
    """年份数字不应被视为 hallucination。"""

    assert contains_non_year_numbers("据2024年报数据显示") is False
    assert contains_non_year_numbers("从2022年到2024年") is False


def test_contains_non_year_numbers_allows_text() -> None:
    """纯文本不应触发 hallucination 检测。"""

    assert contains_non_year_numbers("基金表现稳健，超额收益持续为正") is False


def test_llm_chapter_generator_success() -> None:
    """LLM 正常返回定性分析时，输出必须包含数据表格 + LLM 分析。"""

    client = FakeLlmClient(["基金业绩表现稳健，超额收益持续为正。"])
    generator = LlmChapterGenerator(llm_client=client)

    result = generator.generate_chapter(
        chapter_id=2,
        fund_code="004393",
        fund_name="测试基金",
        report_year=2024,
        performance=_sample_performance(),
        holdings={},
        allocation={},
        fees={},
    )

    assert result is not None
    assert "12.34%" in result  # 数据表格中的真实数字
    assert "基金业绩表现稳健" in result  # LLM 分析文本
    assert "## 分析" in result  # 分析标题


def test_llm_chapter_generator_hallucination_rejected() -> None:
    """LLM 输出未见数字时必须被拒绝，返回 None。"""

    # 使用一个不在数据表中的数字（99.99%）
    client = FakeLlmClient(["净值增长率为99.99%，表现优异。"])
    generator = LlmChapterGenerator(llm_client=client)

    result = generator.generate_chapter(
        chapter_id=2,
        fund_code="004393",
        fund_name="测试基金",
        report_year=2024,
        performance=_sample_performance(),
        holdings={},
        allocation={},
        fees={},
    )

    assert result is None


def test_llm_chapter_generator_failure_returns_none() -> None:
    """LLM 调用失败时必须返回 None。"""

    client = FakeLlmClient([RuntimeError("network error")])
    generator = LlmChapterGenerator(llm_client=client)

    result = generator.generate_chapter(
        chapter_id=2,
        fund_code="004393",
        fund_name="测试基金",
        report_year=2024,
        performance=_sample_performance(),
        holdings={},
        allocation={},
        fees={},
    )

    assert result is None


def test_generate_report_with_llm_uses_data_tables(monkeypatch, tmp_path: Path) -> None:
    """generate_report 接入 LLM 时，数据表格必须包含真实数字。"""

    # 使用单一响应模式：所有 LLM 调用返回相同的定性分析
    fake_llm = FakeLlmClient("基金业绩表现稳健，超额收益持续为正。该基金投资策略清晰，风险控制合理。")

    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    doc_id = "doc-2024"
    catalog_path = work_dir / "completed_reports.json"
    catalog_path.write_text(json.dumps({
        "schema_version": 1,
        "reports": {
            doc_id: {
                "schema_version": 1,
                "document_id": doc_id,
                "identity": {
                    "fund_code": "004393",
                    "fund_name": "安信企业价值优选",
                    "year": 2024,
                    "report_type": "annual_report",
                    "source_kind": "local_pdf",
                    "content_fingerprint": "fp-doc-2024",
                    "document_id": doc_id,
                },
                "stored_blob_ref": "blob-doc-2024",
                "docling_json_ref": "docling_json:doc-2024",
            },
        },
    }), encoding="utf-8")

    service = FundReadingService()

    monkeypatch.setattr(service, "_extract_report_holdings_with_citations", lambda *a, **k: (_sample_holdings(), {}))
    monkeypatch.setattr(service, "_extract_report_fees_with_citations", lambda *a, **k: (_sample_fees(), {}))
    monkeypatch.setattr(service, "_extract_report_performance_with_citations", lambda *a, **k: (_sample_performance(), {}))
    monkeypatch.setattr(service, "_extract_report_allocation_with_citations", lambda *a, **k: (_sample_allocation(), {}))
    monkeypatch.setattr(service, "_extract_fund_manager", lambda *a, **k: None)
    monkeypatch.setattr(service, "_extract_fund_manager_with_citation", lambda *a, **k: (None, None))
    monkeypatch.setattr(service, "_extract_scale_info", lambda *a, **k: (None, None))

    result = service.generate_report(
        GenerateReportRequest(
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            report_year=2024,
            years=[2024],
            work_dir=work_dir,
            output_format="json",
        ),
        llm_client=fake_llm,
    )

    assert result.failure is None
    assert result.report is not None
    assert result.report.metadata["generation_mode"] == "llm"

    # 验证数据表格包含真实数字
    ch2 = result.report.chapters[2].content
    assert "12.34%" in ch2
    assert "8.76%" in ch2
    assert "1.20%" in ch2  # 费率在 Ch2 R=A+B-C

    ch3 = result.report.chapters[3].content
    assert "600519" in ch3
    assert "贵州茅台" in ch3

    ch5 = result.report.chapters[5].content
    assert "股票投资" in ch5
    assert "85.23%" in ch5


def test_generate_report_llm_fallback_to_template(monkeypatch, tmp_path: Path) -> None:
    """LLM 失败时 generate_report 必须回退到模板填充。"""

    fake_llm = FakeLlmClient([RuntimeError("error")] * 100)

    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    doc_id = "doc-2024"
    catalog_path = work_dir / "completed_reports.json"
    catalog_path.write_text(json.dumps({
        "schema_version": 1,
        "reports": {
            doc_id: {
                "schema_version": 1,
                "document_id": doc_id,
                "identity": {
                    "fund_code": "004393",
                    "fund_name": "安信企业价值优选",
                    "year": 2024,
                    "report_type": "annual_report",
                    "source_kind": "local_pdf",
                    "content_fingerprint": "fp-doc-2024",
                    "document_id": doc_id,
                },
                "stored_blob_ref": "blob-doc-2024",
                "docling_json_ref": "docling_json:doc-2024",
            },
        },
    }), encoding="utf-8")

    service = FundReadingService()

    monkeypatch.setattr(service, "_extract_report_holdings_with_citations", lambda *a, **k: (_sample_holdings(), {}))
    monkeypatch.setattr(service, "_extract_report_fees_with_citations", lambda *a, **k: (_sample_fees(), {}))
    monkeypatch.setattr(service, "_extract_report_performance_with_citations", lambda *a, **k: (_sample_performance(), {}))
    monkeypatch.setattr(service, "_extract_report_allocation_with_citations", lambda *a, **k: (_sample_allocation(), {}))
    monkeypatch.setattr(service, "_extract_fund_manager", lambda *a, **k: None)
    monkeypatch.setattr(service, "_extract_fund_manager_with_citation", lambda *a, **k: (None, None))
    monkeypatch.setattr(service, "_extract_scale_info", lambda *a, **k: (None, None))

    result = service.generate_report(
        GenerateReportRequest(
            fund_code="004393",
            fund_name="安信企业价值优选混合型证券投资基金",
            report_year=2024,
            years=[2024],
            work_dir=work_dir,
            output_format="json",
        ),
        llm_client=fake_llm,
    )

    assert result.failure is None
    assert result.report is not None
    assert len(result.report.chapters) == 8
    # 应该有警告（生成失败或审计失败）
    assert len(result.warnings) > 0
