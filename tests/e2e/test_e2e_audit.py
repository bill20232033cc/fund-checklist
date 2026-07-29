"""端到端测试：披露完整性审计（场景 8、9）。

验证：
- audit 命令：披露完整性审计
- deep-audit 命令：深度披露完整性审计

注意：audit/deep-audit 是披露完整性审计（检查年报是否包含必要披露项），
不是章节级审计。章节级审计嵌入在 generate 流程中。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    E2E_WORK_DIR,
    FUND_CODE,
    run_cli_command,
)


class TestAudit:
    """场景 8：披露完整性审计。"""

    def test_audit_returns_valid_json(self, e2e_work_dir):
        """audit 返回合法 JSON，包含 disclosures 和 summary。"""
        result = run_cli_command(
            [
                "audit",
                "--fund-code", FUND_CODE,
                "--year", "2024",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"

        data = json.loads(result.stdout)
        assert data["fund_code"] == FUND_CODE
        assert data["year"] == 2024
        assert "disclosures" in data
        assert "summary" in data
        assert isinstance(data["disclosures"], list)


class TestDeepAudit:
    """场景 9：深度披露完整性审计。"""

    def test_deep_audit_returns_valid_json(self, e2e_work_dir):
        """deep-audit 返回合法 JSON，包含 audit_results 和 summary。"""
        result = run_cli_command(
            [
                "deep-audit",
                "--fund-code", FUND_CODE,
                "--year", "2024",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"

        data = json.loads(result.stdout)
        assert data["fund_code"] == FUND_CODE
        assert "audit_results" in data
        assert "summary" in data
        assert isinstance(data["audit_results"], list)
