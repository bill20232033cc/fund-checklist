"""ToolExecutionContext 测试。

覆盖:
- 字段完整性与默认值
- frozen 不可变性
- index_in_iteration 默认值
"""

import pytest

from fund_agent.agent.tool_context import ToolExecutionContext


class TestToolExecutionContext:
    """ToolExecutionContext 构造与字段测试。"""

    def test_all_fields_present(self):
        """六个字段全部存在且可读。"""
        ctx = ToolExecutionContext(
            run_id="run-001",
            iteration_id="iter_003",
            tool_call_id="call-abc",
            index_in_iteration=2,
        )
        assert ctx.run_id == "run-001"
        assert ctx.iteration_id == "iter_003"
        assert ctx.tool_call_id == "call-abc"
        assert ctx.index_in_iteration == 2

    def test_default_index(self):
        """index_in_iteration 默认值为 0。"""
        ctx = ToolExecutionContext(
            run_id="run-001",
            iteration_id="iter_001",
            tool_call_id="call-xyz",
        )
        assert ctx.index_in_iteration == 0

    def test_frozen_immutable(self):
        """ToolExecutionContext 是不可变的。"""
        ctx = ToolExecutionContext(
            run_id="run-001",
            iteration_id="iter_001",
            tool_call_id="call-xyz",
        )
        with pytest.raises(Exception):
            ctx.run_id = "run-002"  # type: ignore[misc]

    def test_iteration_id_format_example(self):
        """iteration_id 支持 iter_001 格式。"""
        ctx = ToolExecutionContext(
            run_id="r-abc",
            iteration_id="iter_007",
            tool_call_id="tc-42",
        )
        assert ctx.iteration_id == "iter_007"
