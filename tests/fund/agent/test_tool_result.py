"""ToolResult 统一信封测试。

覆盖:
- success/error 工厂构造
- project_for_llm() 投影（dict value / str value / error）
- truncation 元数据注入
- frozen 不可变性
"""

import pytest

from fund_agent.agent.tool_result import ToolResult, project_for_llm


class TestToolResultSuccess:
    """ToolResult.success() 工厂测试。"""

    def test_success_with_dict_value(self):
        """dict value → ok=True, project_for_llm 展开 dict。"""
        result = ToolResult.success(value={"name": "张三", "tenure": "5年"})
        assert result.ok is True
        assert result.error_code is None
        assert result.error_message == ""
        assert result.truncation is None
        assert result.meta == {}

    def test_success_with_string_value(self):
        """str value → ok=True, project_for_llm 包装为 content。"""
        result = ToolResult.success(value="基金经理：张三，任期5年")
        assert result.ok is True
        assert result.value == "基金经理：张三，任期5年"

    def test_success_with_truncation_meta(self):
        """截断场景：truncation + meta 正确写入。"""
        result = ToolResult.success(
            value={"rows": [1, 2, 3]},
            truncation={"strategy": "row_limit", "kept": 20, "total": 50},
            meta={"source": "annual_report_2025"},
        )
        assert result.truncation == {"strategy": "row_limit", "kept": 20, "total": 50}
        assert result.meta == {"source": "annual_report_2025"}

    def test_success_frozen(self):
        """ToolResult 是不可变的 frozen dataclass。"""
        result = ToolResult.success(value={"k": "v"})
        with pytest.raises(Exception):
            result.ok = False  # type: ignore[misc]


class TestToolResultError:
    """ToolResult.error() 工厂测试。"""

    def test_error_basic(self):
        """error 工厂：ok=False, 错误码和消息正确。"""
        result = ToolResult.error(code="not_found", message="未找到基金经理章节")
        assert result.ok is False
        assert result.error_code == "not_found"
        assert result.error_message == "未找到基金经理章节"
        assert result.value is None
        assert result.truncation is None


class TestProjectForLlm:
    """project_for_llm() 投影测试。"""

    def test_dict_value_flattened(self):
        """dict value → 展开为顶层字段，truncation 注入。"""
        result = ToolResult.success(
            value={"name": "张三", "tenure": "5年"},
            truncation={"strategy": "none", "kept": 2, "total": 2},
        )
        llm_view = project_for_llm(result)
        assert llm_view["name"] == "张三"
        assert llm_view["tenure"] == "5年"
        assert llm_view["truncation"] == {"strategy": "none", "kept": 2, "total": 2}

    def test_internal_fields_not_exposed(self):
        """ok / error_code / error_message 不暴露给 LLM。"""
        result = ToolResult.success(value={"data": "ok"})
        llm_view = project_for_llm(result)
        assert "ok" not in llm_view
        assert "error_code" not in llm_view
        assert "error_message" not in llm_view

    def test_string_value_wrapped_in_content(self):
        """str value → {"content": ..., "truncation": None}。"""
        result = ToolResult.success(value="纯文本结果")
        llm_view = project_for_llm(result)
        assert llm_view == {"content": "纯文本结果", "truncation": None}

    def test_error_projection(self):
        """错误 → {"error": code, "message": message}。"""
        result = ToolResult.error(code="unavailable", message="文档暂不可用")
        llm_view = project_for_llm(result)
        assert llm_view == {"error": "unavailable", "message": "文档暂不可用"}

    def test_dict_value_without_truncation(self):
        """truncation=None 时仍注入 truncation: None。"""
        result = ToolResult.success(value={"x": 1})
        llm_view = project_for_llm(result)
        assert llm_view["x"] == 1
        assert llm_view["truncation"] is None


class TestProjectForLlmBudget:
    """project_for_llm budget 参数测试。"""

    def test_budget_injected_on_success(self):
        """budget 非 None 时注入 tool_calls_remaining。"""
        result = ToolResult.success(value={"data": "test"})
        llm_view = project_for_llm(result, budget=5)
        assert llm_view["tool_calls_remaining"] == 5

    def test_budget_injected_on_error(self):
        """错误结果也注入 budget。"""
        result = ToolResult.error(code="unavailable", message="暂不可用")
        llm_view = project_for_llm(result, budget=3)
        assert llm_view["tool_calls_remaining"] == 3
        assert llm_view["error"] == "unavailable"

    def test_budget_none_not_injected(self):
        """budget=None 时不出现 tool_calls_remaining。"""
        result = ToolResult.success(value="test")
        llm_view = project_for_llm(result)
        assert "tool_calls_remaining" not in llm_view

    def test_budget_zero(self):
        """budget=0 时注入 0。"""
        result = ToolResult.success(value="test")
        llm_view = project_for_llm(result, budget=0)
        assert llm_view["tool_calls_remaining"] == 0
