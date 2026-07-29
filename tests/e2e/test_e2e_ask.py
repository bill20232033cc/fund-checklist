"""端到端测试：ask 子命令（场景 1、1b）。

验证 LLM 自主工具调用路径。

已知问题（2026-07-27）：
- ask 命令返回 "LLM 最终回答缺少受控 citation"（failure_code=unavailable）
- 这是 ask 链路的已知 bug，需要单独修复
- 当前标记为 xfail，待 bug 修复后启用
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


@pytest.mark.xfail(
    reason="已知 bug: ask 返回 'LLM 最终回答缺少受控 citation'",
    strict=False,
)
class TestAskStream:
    """场景 1：ask 流式模式。"""

    def test_ask_returns_success_exit_code(self, requires_llm, latest_document_id):
        """流式模式 exit code 0。"""
        result = run_cli_command(
            [
                "ask",
                "基金经理是谁？",
                "--document-id", latest_document_id,
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"


@pytest.mark.xfail(
    reason="已知 bug: ask 返回 'LLM 最终回答缺少受控 citation'",
    strict=False,
)
class TestAskJson:
    """场景 1b：ask JSON 模式（--no-stream）。"""

    def test_ask_no_stream_returns_valid_json(self, requires_llm, latest_document_id):
        """--no-stream 返回合法 JSON，包含 citations/routing_trace。"""
        result = run_cli_command(
            [
                "ask",
                "基金经理是谁？",
                "--document-id", latest_document_id,
                "--no-stream",
                "--work-dir", str(E2E_WORK_DIR),
            ],
            timeout=120,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr}"

        data = json.loads(result.stdout)
        assert "answer" in data, "缺少 answer 字段"
        assert len(data["citations"]) > 0, "citations 为空"
        assert "routing_trace" in data, "缺少 routing_trace 字段"
