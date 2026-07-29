"""端到端测试：修复能力（场景 10、11、12、13）。

验证：
- repair --chapter：局部修复
- fix --chapter：占位符补强
- regenerate --chapter：整章重建
- repair --auto：审计分数驱动自动策略
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.conftest import (
    E2E_WORK_DIR,
    FUND_CODE,
    run_cli_command,
)


class TestRepair:
    """场景 10：repair --chapter 局部修复。"""

    def test_repair_chapters(self, requires_llm, e2e_work_dir):
        """repair --chapter 3,5 只修复指定章节，exit code 0。"""
        result = run_cli_command(
            [
                "repair",
                "--fund-code", FUND_CODE,
                "--year", "2024",
                "--chapter", "3,5",
                "--llm",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=300,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"


class TestFix:
    """场景 11：fix --chapter 占位符补强。"""

    def test_fix_chapter(self, e2e_work_dir):
        """fix --chapter 3 补强占位符，stdout 包含修复统计。"""
        result = run_cli_command(
            [
                "fix",
                "--fund-code", FUND_CODE,
                "--chapter", "3",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"
        assert "第 3 章修复完成" in result.stdout
        assert "补强占位符:" in result.stdout
        assert "保留占位符:" in result.stdout


class TestRegenerate:
    """场景 12：regenerate --chapter 整章重建。"""

    def test_regenerate_chapter(self, requires_llm, e2e_work_dir):
        """regenerate --chapter 3 整章重建，exit code 0。"""
        result = run_cli_command(
            [
                "regenerate",
                "--fund-code", FUND_CODE,
                "--year", "2024",
                "--chapter", "3",
                "--llm",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=300,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"


class TestRepairAuto:
    """场景 13：repair --auto 审计分数驱动自动策略。"""

    def test_repair_auto_selects_strategy(self, requires_llm, e2e_work_dir):
        """repair --auto 自动选择修复策略（skip/repair/regenerate）。"""
        result = run_cli_command(
            [
                "repair",
                "--fund-code", FUND_CODE,
                "--year", "2024",
                "--chapter", "1,2,3,4,5,6,7",
                "--auto",
                "--llm",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=600,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"
