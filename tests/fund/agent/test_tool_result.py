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


class TestToolResultWithMeta:
    """ToolResultWithMeta 包装器测试。"""

    def test_wrapper_carries_remaining_budget(self) -> None:
        """包装器正确携带 remaining_budget。"""
        from fund_agent.agent.llm_tool_loop import ToolResultWithMeta, ToolResult as LoopToolResult
        from fund_agent.fund.document_tools.constants import ToolName as Tn

        inner = LoopToolResult(
            tool_name=Tn.SEARCH_DOCUMENT,
            result=(),
            citations=(),
            evidence_text="",
        )
        wrapper = ToolResultWithMeta(result=inner, remaining_budget=5)
        assert wrapper.remaining_budget == 5
        assert wrapper.result is inner

    def test_wrapper_preserves_original_result(self) -> None:
        """包装器不修改原始 ToolResult。"""
        from fund_agent.agent.llm_tool_loop import ToolResultWithMeta, ToolResult as LoopToolResult
        from fund_agent.fund.document_tools.constants import ToolName as Tn

        inner = LoopToolResult(
            tool_name=Tn.READ_SECTION,
            result=(),
            citations=(),
            evidence_text="some evidence",
        )
        wrapper = ToolResultWithMeta(result=inner)
        assert wrapper.result.tool_name is Tn.READ_SECTION
        assert wrapper.result.evidence_text == "some evidence"
        assert wrapper.remaining_budget is None


class TestFailureFeedbackProjection:
    """S1 失败回喂的 LLM-facing 投影测试（复用 Envelope.error / ok=False 投影）。"""

    @staticmethod
    def _failure_result():
        """构造带 failure 标记的 runner ToolResult。"""
        from fund_agent.agent.llm_tool_loop import ToolResult as LoopToolResult
        from fund_agent.fund.document_tools.constants import FailureCode, ToolName
        from fund_agent.fund.document_tools.models import ToolFailure

        return LoopToolResult(
            tool_name=ToolName.READ_SECTION,
            result=None,
            citations=(),
            evidence_text="",
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message="章节不存在"),
        )

    def test_safe_tool_result_projects_error_envelope(self):
        """DeepSeek _safe_tool_result 对失败项输出 error+message 信封。"""
        from fund_agent.agent.deepseek_llm import _safe_tool_result

        projected = _safe_tool_result(self._failure_result())
        assert projected == {"error": "not_found", "message": "章节不存在"}

    def test_safe_tool_result_failure_with_budget(self):
        """失败投影同样注入 tool_calls_remaining。"""
        from fund_agent.agent.deepseek_llm import _safe_tool_result

        projected = _safe_tool_result(self._failure_result(), remaining_budget=5)
        assert projected == {
            "error": "not_found",
            "message": "章节不存在",
            "tool_calls_remaining": 5,
        }

    def test_wrap_results_for_llm_projects_failure(self):
        """wrap_results_for_llm 对失败项输出 error+message 信封。"""
        from fund_agent.agent.llm_tool_loop import LlmToolLoopRunner

        projected = LlmToolLoopRunner.wrap_results_for_llm((self._failure_result(),))
        assert projected == [{"error": "not_found", "message": "章节不存在"}]

    def test_safe_tool_result_success_shape_unchanged(self):
        """成功条目投影保持既有形状（tool_name / evidence_text / citations / truncation）。"""
        from fund_agent.agent.deepseek_llm import _safe_tool_result
        from fund_agent.agent.llm_tool_loop import ToolResult as LoopToolResult
        from fund_agent.fund.document_tools.constants import ToolName

        success = LoopToolResult(
            tool_name=ToolName.SEARCH_DOCUMENT,
            result=(),
            citations=(),
            evidence_text="证据文本",
        )
        projected = _safe_tool_result(success)
        assert projected["tool_name"] == "search_document"
        assert projected["evidence_text"] == "证据文本"
        assert projected["truncation"] is None
