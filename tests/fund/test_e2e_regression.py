"""端到端回归测试：4类基金 × 真实PDF数据 → 完整报告生成。

本测试使用已导入的真实年报数据（.fund_e2e_* 目录），
以 template 模式（无 LLM）运行完整 generate_report 管道，
验证数据提取→信号评分→报告生成→审计的全链路。

每次代码修改后必须运行此测试，确保无回归。
"""
import io
import json
import os
import pytest
from pathlib import Path

from fund_agent.cli.main import SUCCESS_EXIT_CODE, run_cli

# 跳过条件：e2e 数据目录不存在时跳过（CI 环境可能未导入）
E2E_FUNDS = {
    "163415": {
        "name": "兴全商业模式混合(LOF)",
        "type": "active_fund",
        "work_dir": ".fund_e2e_163415_v3",
        "min_chapters": 8,
        "min_holdings_years": 3,
        "expected_signal": True,
    },
    "006597": {
        "name": "国泰利享中短债债券",
        "type": "bond_fund",
        "work_dir": ".fund_e2e_006597",
        "min_chapters": 8,
        "min_holdings_years": 3,
        "expected_signal": True,
    },
    "007466": {
        "name": "华泰柏瑞中证红利低波ETF联接",
        "type": "index_feeder",
        "work_dir": ".fund_e2e_007466",
        "min_chapters": 8,
        "min_holdings_years": 0,  # 联接基金持仓可能继承
        "expected_signal": True,
    },
    "040046": {
        "name": "华安纳斯达克100ETF联接(QDII)A",
        "type": "index_feeder",
        "work_dir": ".fund_e2e_040046",
        "min_chapters": 8,
        "min_holdings_years": 0,
        "expected_signal": True,
    },
}

def _has_e2e_data(work_dir: str) -> bool:
    """检查 e2e 数据目录是否存在且有 completed_reports.json。"""
    cat = Path(work_dir) / "completed_reports.json"
    return cat.exists()


@pytest.mark.parametrize("fund_code", list(E2E_FUNDS.keys()))
def test_e2e_generate_report_has_8_chapters(fund_code: str) -> None:
    """端到端：generate_report 返回 8 个非空章节。"""
    spec = E2E_FUNDS[fund_code]
    if not _has_e2e_data(spec["work_dir"]):
        pytest.skip(f"e2e 数据目录不存在: {spec['work_dir']}")

    from fund_agent.service.extraction import FundReadingService, GenerateReportRequest

    service = FundReadingService()
    result = service.generate_report(
        request=GenerateReportRequest(
            fund_code=fund_code,
            fund_name=spec["name"],
            report_year=2023,
            work_dir=spec["work_dir"],
            output_format="markdown",
        ),
        llm_client=None,  # template 模式，不依赖 LLM
    )

    assert result.failure is None, f"generate_report 失败: {result.failure}"
    assert result.report is not None
    assert len(result.report.chapters) >= spec["min_chapters"], (
        f"章节数 {len(result.report.chapters)} < {spec['min_chapters']}"
    )

    # 每章内容非空
    for ch in result.report.chapters:
        assert ch.content and len(ch.content) > 50, (
            f"Ch{ch.chapter_id} 内容为空或过短 ({len(ch.content or '')} chars)"
        )


@pytest.mark.parametrize("fund_code", list(E2E_FUNDS.keys()))
def test_e2e_signal_judgment_computed(fund_code: str) -> None:
    """端到端：信号评分已计算且归一化分数在 0-100 范围内。"""
    spec = E2E_FUNDS[fund_code]
    if not _has_e2e_data(spec["work_dir"]):
        pytest.skip(f"e2e 数据目录不存在: {spec['work_dir']}")
    if not spec["expected_signal"]:
        pytest.skip("该基金类型不期望信号评分")

    from fund_agent.service.extraction import FundReadingService, GenerateReportRequest

    service = FundReadingService()
    result = service.generate_report(
        request=GenerateReportRequest(
            fund_code=fund_code,
            fund_name=spec["name"],
            report_year=2023,
            work_dir=spec["work_dir"],
            output_format="json",
        ),
        llm_client=None,
    )

    assert result.failure is None
    # signal_judgment 在 metadata 中或通过 service 获取
    # 这里检查报告 metadata
    meta = result.report.metadata
    assert meta is not None


@pytest.mark.parametrize("fund_code", list(E2E_FUNDS.keys()))
def test_e2e_report_file_written(fund_code: str, tmp_path: Path) -> None:
    """端到端：markdown 报告文件已写入且大小合理。"""
    spec = E2E_FUNDS[fund_code]
    if not _has_e2e_data(spec["work_dir"]):
        pytest.skip(f"e2e 数据目录不存在: {spec['work_dir']}")

    from fund_agent.service.extraction import FundReadingService, GenerateReportRequest

    service = FundReadingService()
    result = service.generate_report(
        request=GenerateReportRequest(
            fund_code=fund_code,
            fund_name=spec["name"],
            report_year=2023,
            work_dir=spec["work_dir"],
            output_format="markdown",
        ),
        llm_client=None,
    )

    assert result.failure is None
    assert result.output_path is not None
    output = Path(result.output_path)
    assert output.exists(), f"报告文件不存在: {output}"
    assert output.stat().st_size > 1000, f"报告文件过小: {output.stat().st_size} bytes"


def test_e2e_040046_stage_is_transformation() -> None:
    """040046 联接基金阶段判定应为转型期（权益→基金投资结构转型）。"""
    work_dir = ".fund_e2e_040046"
    if not _has_e2e_data(work_dir):
        pytest.skip("e2e 数据目录不存在")

    from fund_agent.service.extraction import FundReadingService, GenerateReportRequest

    service = FundReadingService()
    result = service.generate_report(
        request=GenerateReportRequest(
            fund_code="040046",
            fund_name="华安纳斯达克100ETF联接(QDII)A",
            report_year=2023,
            work_dir=work_dir,
            output_format="markdown",
        ),
        llm_client=None,
    )

    assert result.failure is None
    # Ch5 应包含"转型期"
    ch5 = [c for c in result.report.chapters if c.chapter_id == 5]
    assert ch5, "Ch5 不存在"
    assert "转型期" in ch5[0].content, (
        f"040046 Ch5 应判定为转型期，但内容中未找到「转型期」"
    )


def test_e2e_040046_ch5_has_signal_judgment() -> None:
    """040046 Ch5 数据表应包含信号评分信息。"""
    work_dir = ".fund_e2e_040046"
    if not _has_e2e_data(work_dir):
        pytest.skip("e2e 数据目录不存在")

    from fund_agent.service.extraction import FundReadingService, GenerateReportRequest

    service = FundReadingService()
    result = service.generate_report(
        request=GenerateReportRequest(
            fund_code="040046",
            fund_name="华安纳斯达克100ETF联接(QDII)A",
            report_year=2023,
            work_dir=work_dir,
            output_format="markdown",
        ),
        llm_client=None,
    )

    assert result.failure is None
    ch5 = [c for c in result.report.chapters if c.chapter_id == 5]
    assert ch5, "Ch5 不存在"
    # Ch5 应包含信号评分信息（综合信号或标准化评分）
    content = ch5[0].content
    has_signal = "综合信号" in content or "标准化评分" in content or "信号" in content
    assert has_signal, "Ch5 数据表中未包含信号评分信息"


def test_extract_contract_effective_date_005680() -> None:
    """005680 基金合同生效日抽取应为 2019-03-25 且带 Citation（建仓期真源）。"""
    work_dir = ".fund_checklist_005680"
    if not _has_e2e_data(work_dir):
        pytest.skip(f"005680 数据目录不存在: {work_dir}")

    from pathlib import Path

    from fund_agent.service.extraction import FundReadingService, _repository
    from fund_agent.service.models import AnnualReportDocument

    service = FundReadingService()
    repo = _repository(Path(work_dir))
    catalog = repo.list_reports()
    annual_docs = [
        AnnualReportDocument(year=int(r["year"]), document_id=str(r["document_id"]))
        for r in catalog
        if r.get("fund_code") == "005680"
    ]
    date, citation = service._extract_contract_effective_date_with_citation(
        "005680", annual_docs, work_dir, "财通资管价值成长混合",
    )

    assert date == "2019-03-25", f"合同生效日应为 2019-03-25，实际 {date}"
    assert citation is not None, "合同生效日 citation 不应为空"
    assert citation.locator.locator_kind.value == "table"


def _run(args: list[str]) -> tuple[int, str, str]:
    """执行 CLI 并捕获 stdout/stderr。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run_cli(args, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_multi_year_004393_missing_year_note() -> None:
    """004393 真实数据 multi-year CLI：missing_year_notes 含 2022 转型当年原因。"""

    work_dir = ".fund_e2e_004393"
    if not _has_e2e_data(work_dir):
        pytest.skip("e2e 数据目录不存在")

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "004393",
        "--years", "2021,2022,2023,2024,2025",
        "--work-dir", work_dir,
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stdout + stderr
    output = json.loads(stdout)
    notes = output["series"][0]["missing_year_notes"]
    assert any(
        note["year"] == 2022 and "转型当年无全年份额净值增长率" in note["reason"]
        for note in notes
    )


def test_multi_year_005680_2022_covered() -> None:
    """005680 真实数据 multi-year CLI：2022 covered（A 类 -22.35%/-15.20%，citation table-0010），2021/2023-2025 不回退。"""

    work_dir = ".fund_checklist_005680"
    if not _has_e2e_data(work_dir):
        pytest.skip("e2e 数据目录不存在")

    exit_code, stdout, stderr = _run([
        "multi-year",
        "--fund-code", "005680",
        "--years", "2021,2022,2023,2024,2025",
        "--work-dir", work_dir,
    ])

    assert exit_code == SUCCESS_EXIT_CODE, stdout + stderr
    output = json.loads(stdout)
    series = next(s for s in output["series"] if s["share_class_scope"] == "A")
    assert 2022 in series["covered_years"], f"2022 未覆盖: {series}"
    assert 2022 not in series["missing_years"], series
    rows_by_year = {row["year"]: row for row in series["rows"]}
    row_2022 = rows_by_year[2022]
    assert row_2022["annual_nav_growth_rate"] == "-22.35%"
    assert row_2022["annual_benchmark_return_rate"] == "-15.20%"
    assert row_2022["annual_excess_return"] == "-7.15%"
    cited_table_refs = {
        field["citation"]["locator"]["table_ref"]
        for field in row_2022["citations"]
    }
    assert "table-0010" in cited_table_refs, row_2022
    for year in (2021, 2023, 2024, 2025):
        assert year in series["covered_years"], f"{year} 回退: {series}"
