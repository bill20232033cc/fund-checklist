"""LLM provider 自由切换（DeepSeek ↔ Mimo）测试。

覆盖:
- FUND_CHECKLIST_LLM_PROVIDER 解析（默认 deepseek / mimo / 未知值 fail-fast）
- provider 配置表解析（key/base/model env 与默认值）
- scene/contract 模型名翻译 helper
- DeepSeekLlmClient 请求组装按 provider 路由（next_step / next_step_stream / generate_text）
- env 注入参数向后兼容与错误文案泛化
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

import pytest

from fund_agent.agent.deepseek_llm import (
    _collect_sse_full_response,
    _parse_response,
    DEEPSEEK_API_KEY_ENV,
    DEEPSEEK_BASE_URL_ENV,
    DEEPSEEK_MODEL_ENV,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_MIMO_BASE_URL,
    DEFAULT_MIMO_MODEL,
    LLM_PROVIDER_ENV,
    MIMO_API_KEY_ENV,
    MIMO_BASE_URL_ENV,
    MIMO_MODEL_ENV,
    DeepSeekChatRequest,
    DeepSeekChatResponse,
    DeepSeekLlmClient,
    DeepSeekTransportUnavailable,
    ExecutionOptions,
    LlmClientFailure,
    provider_api_key_env_name,
    provider_base_url_env_name,
    provider_model_env_name,
    resolve_provider,
    resolve_provider_model,
    translate_model_for_provider,
)
from fund_agent.agent import ToolCall
from fund_agent.fund.document_tools.constants import FailureCode, ToolName

_DOCUMENT_ID = "004393-2024-annual_report-abc123def4567890"
_ANSWER_TEXT = "根据年报，基金经理张明负责本基金投资管理。"


class RecordingTransport:
    """记录 request 并返回固定 response 的 fake transport。

    参数:
        responses: 每次 send / send_stream 要返回的 response 或抛出的 exception。

    返回:
        DeepSeekTransportProtocol-compatible fake transport。

    异常:
        队列耗尽时抛 AssertionError，表示测试脚本错误。
    """

    def __init__(self, responses: Iterable[DeepSeekChatResponse | Exception] | None = None) -> None:
        """保存 response 队列并初始化 request 记录。"""

        self._responses = list(responses) if responses is not None else []
        self.requests: list[DeepSeekChatRequest] = []

    def _next(self) -> DeepSeekChatResponse:
        """弹出队列中的下一项。"""

        if not self._responses:
            raise AssertionError("fake transport exhausted")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        """记录 request 后返回队列中的下一项。"""

        self.requests.append(request)
        return self._next()

    def send_stream(self, request: DeepSeekChatRequest) -> Iterator[str]:
        """记录 request 后 yield SSE 行。"""

        self.requests.append(request)
        yield from _response_to_sse_lines(self._next())


def _response_to_sse_lines(response: DeepSeekChatResponse) -> Iterator[str]:
    """把非流式 response 转为 fake SSE 行（content delta + DONE）。"""

    body = json.loads(response.body)
    message = body["choices"][0]["message"]
    content = message.get("content") or ""
    chunk = {"choices": [{"delta": {"content": content}, "index": 0, "finish_reason": "stop"}]}
    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n"
    yield "data: [DONE]\n"


def _final_response(answer: str = _ANSWER_TEXT) -> DeepSeekChatResponse:
    """构造 provider final answer response。"""

    return DeepSeekChatResponse(
        status_code=200,
        body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"answer": answer, "citations": [], "key_facts": []},
                                ensure_ascii=False,
                            ),
                        }
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )


# ── provider 解析 ────────────────────────────────────────────────


def test_resolve_provider_defaults_to_deepseek() -> None:
    """未设置 FUND_CHECKLIST_LLM_PROVIDER 时必须默认 deepseek。"""

    assert resolve_provider({}) == "deepseek"


def test_resolve_provider_mimo() -> None:
    """显式设置 mimo 时解析为 mimo。"""

    assert resolve_provider({LLM_PROVIDER_ENV: "mimo"}) == "mimo"


def test_resolve_provider_unknown_fails_fast() -> None:
    """未知 provider 值必须抛 ValueError 并提示合法取值，不静默回退。"""

    with pytest.raises(ValueError, match="deepseek.*mimo"):
        resolve_provider({LLM_PROVIDER_ENV: "ollama"})


# ── provider 配置表 ──────────────────────────────────────────────


def test_resolve_provider_model_deepseek_default() -> None:
    """deepseek provider 默认模型为 deepseek-v4-flash。"""

    assert resolve_provider_model({}) == DEFAULT_DEEPSEEK_MODEL


def test_resolve_provider_model_mimo_default() -> None:
    """mimo provider 默认模型为 mimo-v2.5-pro。"""

    assert resolve_provider_model({LLM_PROVIDER_ENV: "mimo"}) == DEFAULT_MIMO_MODEL


def test_resolve_provider_model_env_override() -> None:
    """MODEL env 非空时优先于默认值。"""

    assert resolve_provider_model({LLM_PROVIDER_ENV: "mimo", MIMO_MODEL_ENV: "mimo-custom"}) == "mimo-custom"
    assert resolve_provider_model({DEEPSEEK_MODEL_ENV: "ds-custom"}) == "ds-custom"


def test_provider_model_env_name() -> None:
    """provider_model_env_name 返回对应 MODEL 环境变量名。"""

    assert provider_model_env_name("deepseek") == DEEPSEEK_MODEL_ENV
    assert provider_model_env_name("mimo") == MIMO_MODEL_ENV
    with pytest.raises(ValueError):
        provider_model_env_name("unknown")


def test_provider_api_key_env_name() -> None:
    """provider_api_key_env_name 返回对应 API key 环境变量名。"""

    assert provider_api_key_env_name("deepseek") == DEEPSEEK_API_KEY_ENV
    assert provider_api_key_env_name("mimo") == MIMO_API_KEY_ENV
    with pytest.raises(ValueError):
        provider_api_key_env_name("unknown")


def test_provider_base_url_env_name() -> None:
    """provider_base_url_env_name 返回对应 base URL 环境变量名。"""

    assert provider_base_url_env_name("deepseek") == DEEPSEEK_BASE_URL_ENV
    assert provider_base_url_env_name("mimo") == MIMO_BASE_URL_ENV
    with pytest.raises(ValueError):
        provider_base_url_env_name("unknown")


# ── 模型名翻译 ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("deepseek-v4-pro", "mimo-v2.5-pro"),
        ("deepseek-v4-flash", "mimo-v2.5"),
        ("custom-model", "custom-model"),
    ],
)
def test_translate_model_for_provider_mimo(model_name: str, expected: str) -> None:
    """mimo provider 下 scene/contract 模型名按翻译表映射，未知模型原样透传。"""

    assert translate_model_for_provider(model_name, "mimo") == expected


def test_translate_model_for_provider_deepseek_identity() -> None:
    """deepseek provider 下模型名原样透传。"""

    assert translate_model_for_provider("deepseek-v4-flash", "deepseek") == "deepseek-v4-flash"
    assert translate_model_for_provider("anything", "deepseek") == "anything"


# ── DeepSeekLlmClient 请求组装 ───────────────────────────────────


def test_next_step_uses_mimo_config_override() -> None:
    """mimo provider 下请求按 MIMO env 组装（base/model/key）。"""

    transport = RecordingTransport([_final_response()])
    client = DeepSeekLlmClient(
        transport=transport,
        env={
            LLM_PROVIDER_ENV: "mimo",
            MIMO_API_KEY_ENV: "test-mimo-key",
            MIMO_BASE_URL_ENV: "https://mimo.example.com/v2",
            MIMO_MODEL_ENV: "mimo-custom-model",
        },
        options=ExecutionOptions(stream=False),
    )

    result = client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert result.step.answer == _ANSWER_TEXT
    request = transport.requests[0]
    assert request.url == "https://mimo.example.com/v2/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-mimo-key"
    assert request.payload["model"] == "mimo-custom-model"


def test_next_step_uses_mimo_defaults() -> None:
    """mimo provider 未显式配置时使用默认 base URL 与默认模型。"""

    transport = RecordingTransport([_final_response()])
    client = DeepSeekLlmClient(
        transport=transport,
        env={LLM_PROVIDER_ENV: "mimo", MIMO_API_KEY_ENV: "test-mimo-key"},
        options=ExecutionOptions(stream=False),
    )

    client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    request = transport.requests[0]
    assert request.url == f"{DEFAULT_MIMO_BASE_URL}/chat/completions"
    assert request.payload["model"] == DEFAULT_MIMO_MODEL


def test_next_step_deepseek_backward_compatible() -> None:
    """不设置 provider env 时保持既有 deepseek 行为（向后兼容）。"""

    transport = RecordingTransport([_final_response()])
    client = DeepSeekLlmClient(
        transport=transport,
        env={
            DEEPSEEK_API_KEY_ENV: "test-ds-key",
            DEEPSEEK_BASE_URL_ENV: "https://ds.example.com",
            DEEPSEEK_MODEL_ENV: "ds-custom-model",
        },
        options=ExecutionOptions(stream=False),
    )

    client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    request = transport.requests[0]
    assert request.url == "https://ds.example.com/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-ds-key"
    assert request.payload["model"] == "ds-custom-model"


def test_next_step_unknown_provider_fails_fast() -> None:
    """请求组装时遇到未知 provider 值必须抛 ValueError。"""

    client = DeepSeekLlmClient(
        transport=RecordingTransport(),
        env={LLM_PROVIDER_ENV: "ollama", DEEPSEEK_API_KEY_ENV: "test-ds-key"},
        options=ExecutionOptions(stream=False),
    )

    with pytest.raises(ValueError):
        client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())


def test_next_step_mimo_missing_key_unavailable() -> None:
    """mimo provider 下 MIMO_API_KEY 缺失必须 unavailable，且不调用 transport。"""

    transport = RecordingTransport()
    client = DeepSeekLlmClient(
        transport=transport,
        env={LLM_PROVIDER_ENV: "mimo"},
        options=ExecutionOptions(stream=False),
    )

    with pytest.raises(LlmClientFailure) as excinfo:
        client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert excinfo.value.code is FailureCode.UNAVAILABLE
    assert transport.requests == []


def test_next_step_stream_uses_mimo_config() -> None:
    """流式路径同样按 provider 配置组装请求。"""

    transport = RecordingTransport([_final_response()])
    client = DeepSeekLlmClient(
        transport=transport,
        env={LLM_PROVIDER_ENV: "mimo", MIMO_API_KEY_ENV: "test-mimo-key", MIMO_MODEL_ENV: "mimo-stream-model"},
    )

    events = list(client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=()))

    assert events
    request = transport.requests[0]
    assert request.url == f"{DEFAULT_MIMO_BASE_URL}/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-mimo-key"
    assert request.payload["model"] == "mimo-stream-model"


def test_generate_text_uses_mimo_config() -> None:
    """generate_text 路径同样按 provider 配置组装请求。"""

    transport = RecordingTransport(
        [
            DeepSeekChatResponse(
                status_code=200,
                body=json.dumps(
                    {"choices": [{"message": {"role": "assistant", "content": _ANSWER_TEXT}}]},
                    ensure_ascii=False,
                ),
            )
        ]
    )
    client = DeepSeekLlmClient(
        transport=transport,
        env={LLM_PROVIDER_ENV: "mimo", MIMO_API_KEY_ENV: "test-mimo-key", MIMO_MODEL_ENV: "mimo-gen-model"},
        options=ExecutionOptions(stream=False),
    )

    text = client.generate_text(system_prompt="system", user_prompt="user")

    assert text == _ANSWER_TEXT
    request = transport.requests[0]
    assert request.url == f"{DEFAULT_MIMO_BASE_URL}/chat/completions"
    assert request.payload["model"] == "mimo-gen-model"


# ── 错误文案泛化 ─────────────────────────────────────────────────


def test_unavailable_message_is_provider_generic() -> None:
    """unavailable 错误文案不得带 DeepSeek 前缀。"""

    transport = RecordingTransport([DeepSeekTransportUnavailable("auth", status_code=401)])
    client = DeepSeekLlmClient(
        transport=transport,
        env={DEEPSEEK_API_KEY_ENV: "test-ds-key"},
        options=ExecutionOptions(stream=False),
    )

    with pytest.raises(LlmClientFailure) as excinfo:
        client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert excinfo.value.code is FailureCode.UNAVAILABLE
    assert "DeepSeek" not in excinfo.value.safe_message
    assert excinfo.value.safe_message == "LLM provider 暂不可用"


def test_malformed_message_is_provider_generic() -> None:
    """malformed 错误文案不得带 DeepSeek 前缀。"""

    malformed = DeepSeekChatResponse(status_code=200, body="not-a-json-body")
    transport = RecordingTransport([malformed, malformed])
    client = DeepSeekLlmClient(
        transport=transport,
        env={DEEPSEEK_API_KEY_ENV: "test-ds-key"},
        options=ExecutionOptions(stream=False),
    )

    with pytest.raises(LlmClientFailure) as excinfo:
        client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert excinfo.value.code is FailureCode.LLM_MALFORMED_RESPONSE
    assert "DeepSeek" not in excinfo.value.safe_message
    assert excinfo.value.safe_message == "LLM provider response 不符合受控结构"


def test_stream_tool_call_name_survives_null_name_delta() -> None:
    """mimo 流式 chunk 后续段 name=null 不得覆盖首个 chunk 的工具名。"""

    lines = [
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"search_document","arguments":""}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":null,"arguments":"{\\"document_id\\": \\"004393-2024-annual_report-abc123def4567890\\", \\"query\\": \\"基金经理\\", \\"max_results\\": 5}"}}]}}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
        "data: [DONE]",
    ]
    body = json.dumps(_collect_sse_full_response(iter(lines)), ensure_ascii=False)
    response = _parse_response(body)
    assert isinstance(response.step, ToolCall)
    assert response.step.tool_name == ToolName.SEARCH_DOCUMENT
    assert response.step.document_id == "004393-2024-annual_report-abc123def4567890"
    assert response.step.query == "基金经理"
