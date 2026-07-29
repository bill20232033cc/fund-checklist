"""端到端测试：generate + multi-year + signal（场景 5、6、7）。

验证：
- 8 章分析报告生成 + 章节级审计产物
- 多年度数据聚合
- JSON 输出结构

注意：generate --llm 耗时较长（~15 分钟），测试会复用已有报告。
首次运行需手动执行 generate 命令。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    E2E_WORK_DIR,
    FUND_CODE,
    FUND_NAME,
    YEARS,
    run_cli_command,
)


def _report_exists(work_dir: Path, fund_code: str, year: int) -> bool:
    """检查报告是否已存在。"""
    return (work_dir / "reports" / f"{fund_code}-{year}-analysis.md").exists()


class TestGenerate:
    """场景 5：生成分析报告（含章节审计）。"""

    def test_generate_markdown_creates_report_and_audit(
        self, requires_llm, e2e_work_dir
    ):
        """generate --format markdown 生成报告 + Ch1-6 审计产物。

        如果报告已存在，跳过生成直接验证产物。
        """
        year = 2024

        if not _report_exists(e2e_work_dir, FUND_CODE, year):
            result = run_cli_command(
                [
                    "generate",
                    "--fund-code", FUND_CODE,
                    "--fund-name", FUND_NAME,
                    "--year", str(year),
                    "--years", ",".join(str(y) for y in YEARS),
                    "--format", "markdown",
                    "--llm",
                    "--work-dir", str(E2E_WORK_DIR),
                ],
                timeout=1800,
            )
            assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"

        # 验证报告文件
        report_path = e2e_work_dir / "reports" / f"{FUND_CODE}-{year}-analysis.md"
        assert report_path.exists(), f"报告文件不存在: {report_path}"

        meta_path = e2e_work_dir / "reports" / f"{FUND_CODE}-{year}-analysis.meta.json"
        assert meta_path.exists(), f"元数据文件不存在: {meta_path}"

        # 检查章节审计产物（Ch1-6 保证生成）
        for ch_id in range(1, 7):
            audit_file = e2e_work_dir / "audit_artifacts" / f"chapter_{ch_id}_audit.json"
            assert audit_file.exists(), f"缺少审计产物: {audit_file}"
            data = json.loads(audit_file.read_text(encoding="utf-8"))
            assert "score" in data, f"chapter_{ch_id}_audit.json 缺少 score"
            assert "violations" in data, f"chapter_{ch_id}_audit.json 缺少 violations"
            assert "recommendation" in data, f"chapter_{ch_id}_audit.json 缺少 recommendation"

        # 检查报告内容
        report_text = report_path.read_text(encoding="utf-8")
        assert len(report_text) > 1000, "报告内容过短"


class TestMultiYear:
    """场景 6：多年度数据聚合。"""

    def test_multi_year_returns_data(self, e2e_work_dir):
        """multi-year 输出包含多年度数据。"""
        result = run_cli_command(
            [
                "multi-year",
                "--fund-code", FUND_CODE,
                "--years", ",".join(str(y) for y in YEARS),
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"
        for year in YEARS:
            assert str(year) in result.stdout, f"输出中缺少 {year} 年数据"


class TestGenerateJson:
    """场景 7：generate JSON 输出 + 信号评分。"""

    def test_generate_json_structure(self, requires_llm, e2e_work_dir):
        """generate --format json 输出完整 JSON 结构。

        如果报告已存在，跳过生成直接验证产物。
        """
        year = 2024
        json_report = e2e_work_dir / "reports" / f"{FUND_CODE}-{year}-analysis.json"

        if not json_report.exists():
            result = run_cli_command(
                [
                    "generate",
                    "--fund-code", FUND_CODE,
                    "--fund-name", FUND_NAME,
                    "--year", str(year),
                    "--years", ",".join(str(y) for y in YEARS),
                    "--format", "json",
                    "--llm",
                    "--work-dir", str(E2E_WORK_DIR),
                ],
                timeout=1800,
            )
            assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"
            data = json.loads(result.stdout)
        else:
            # 从 stdout JSON 验证（generate json 模式输出到 stdout）
            result = run_cli_command(
                [
                    "generate",
                    "--fund-code", FUND_CODE,
                    "--fund-name", FUND_NAME,
                    "--year", str(year),
                    "--years", ",".join(str(y) for y in YEARS),
                    "--format", "json",
                    "--work-dir", str(E2E_WORK_DIR),
                ],
                timeout=120,
            )
            assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"
            data = json.loads(result.stdout)

        assert data["fund_code"] == FUND_CODE
        assert data["report_year"] == year
        assert len(data["chapters"]) == 8, f"章节数 {len(data['chapters'])}，期望 8"
        assert "metadata" in data
        assert "output_path" in data

        for ch in data["chapters"]:
            assert "chapter_id" in ch
            assert "title" in ch
            assert "content" in ch
            assert "data_sources" in ch
