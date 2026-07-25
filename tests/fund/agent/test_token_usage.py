"""DeepSeekLlmClient token usage 追踪测试。

覆盖:
- TokenUsage 构造与计算
- API response 中 usage 字段正确解析
- cumulative_usage 累计逻辑
- usage 字段缺失时的 None 兜底
"""

import json

import pytest

from fund_agent.agent.deepseek_llm import (
    ChatResponse,
    DeepSeekLlmClient,
    TokenUsage,
)
from fund_agent.agent.llm_tool_loop import FakeLlmClient, FinalAnswer


class FakeTransportWithUsage:
    """fake transport：返回含 usage 的响应。"""

    def __init__(self, usage: dict | None = None):
        self._usage = usage
        self._call_count = 0

    def send(self, request):
        self._call_count += 1
        from fund_agent.agent.deepseek_llm import DeepSeekChatResponse

        body = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"answer": "测试回答", "citations": [], "key_facts": []}),
                }
            }],
        }
        if self._usage is not None:
            body["usage"] = self._usage

        return DeepSeekChatResponse(status_code=200, body=json.dumps(body, ensure_ascii=False))


class TestTokenUsage:
    """TokenUsage dataclass 测试。"""

    def test_basic_construction(self):
        usage = TokenUsage(prompt_tokens=150, completion_tokens=50)
        assert usage.prompt_tokens == 150
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 200

    def test_default_zero(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_cumulative_add(self):
        a = TokenUsage(prompt_tokens=100, completion_tokens=50)
        b = TokenUsage(prompt_tokens=200, completion_tokens=80)
        c = a + b
        assert c.prompt_tokens == 300
        assert c.completion_tokens == 130
        assert c.total_tokens == 430


class TestDeepSeekClientUsageTracking:
    """DeepSeekLlmClient usage 解析与累计测试。"""

    def test_parses_usage_from_response(self):
        """fake transport 含 usage → ChatResponse.usage 正确。"""
        transport = FakeTransportWithUsage(
            usage={"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
        )
        client = DeepSeekLlmClient(
            transport=transport,
            env={"DEEPSEEK_API_KEY": "sk-test", "DEEPSEEK_MODEL": "deepseek-test"},
        )
        response = client.next_step(document_id="d1", query="hello", tool_results=())
        assert response.usage is not None
        assert response.usage.prompt_tokens == 150
        assert response.usage.completion_tokens == 50
        assert response.usage.total_tokens == 200

    def test_cumulative_usage_accumulates(self):
        """两次调用 → cumulative_usage 累计。"""
        transport = FakeTransportWithUsage(
            usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}
        )
        client = DeepSeekLlmClient(
            transport=transport,
            env={"DEEPSEEK_API_KEY": "sk-test", "DEEPSEEK_MODEL": "deepseek-test"},
        )
        client.next_step(document_id="d1", query="q1", tool_results=())
        client.next_step(document_id="d1", query="q2", tool_results=())

        cumulative = client.cumulative_usage
        assert cumulative.prompt_tokens == 200
        assert cumulative.completion_tokens == 60

    def test_no_usage_field_handles_gracefully(self):
        """response 无 usage 字段 → usage=None，不崩溃。"""
        transport = FakeTransportWithUsage(usage=None)
        client = DeepSeekLlmClient(
            transport=transport,
            env={"DEEPSEEK_API_KEY": "sk-test", "DEEPSEEK_MODEL": "deepseek-test"},
        )
        response = client.next_step(document_id="d1", query="hello", tool_results=())
        assert response.usage is None

    def test_chat_response_wraps_step(self):
        """ChatResponse.step 正确包裹 ToolCall 或 FinalAnswer。"""
        transport = FakeTransportWithUsage(
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )
        client = DeepSeekLlmClient(
            transport=transport,
            env={"DEEPSEEK_API_KEY": "sk-test", "DEEPSEEK_MODEL": "deepseek-test"},
        )
        response = client.next_step(document_id="d1", query="hello", tool_results=())
        assert isinstance(response.step, FinalAnswer)
        assert response.step.answer == "测试回答"


class TestFakeLlmClientCompatibility:
    """FakeLlmClient 与 ChatResponse 兼容。"""

    def test_fake_llm_client_returns_chat_response(self):
        """FakeLlmClient.next_step 也返回 ChatResponse（向后兼容）。"""
        answer = FinalAnswer(answer="hello", citations=(), key_facts=())
        client = FakeLlmClient(steps=[answer])
        response = client.next_step(document_id="d1", query="q", tool_results=())
        assert isinstance(response, ChatResponse)
        assert isinstance(response.step, FinalAnswer)
        assert response.step.answer == "hello"
        assert response.usage is None
