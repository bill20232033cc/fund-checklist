"""Post-MVP Slice 8B DeepSeek real LLM adapter 测试。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from fund_agent.agent import (
    DeepSeekChatRequest,
    DeepSeekChatResponse,
    DeepSeekLlmClient,
    DeepSeekTransportUnavailable,
    ExecutionOptions,
    LlmClientFailure,
    LlmToolLoopRunner,
    StreamEvent,
    StreamEventType,
    ToolCall,
)
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import Citation, Locator, ReportIdentity, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService

_TEST_API_KEY = "test-deepseek-key"
_REAL_ENV_SECRET = "real-env-secret-must-not-be-read"
_DOCUMENT_ID = "004393-2024-annual_report-abc123def4567890"


class QueueTransport:
    """按队列返回 response 或抛出异常的 fake transport。

    参数:
        responses: 每次 send 要返回的 response 或抛出的 exception。
        stream_lines: send_stream 要返回的 SSE 行列表；为空时自动从 responses 转换。

    返回:
        DeepSeekTransportProtocol-compatible fake transport。

    异常:
        队列耗尽时抛 AssertionError，表示测试脚本错误。
    """

    def __init__(
        self,
        responses: Iterable[DeepSeekChatResponse | Exception] | None = None,
        stream_lines: Iterable[list[str]] | None = None,
    ) -> None:
        """保存 response 队列并记录收到的 request。"""

        self._responses = list(responses) if responses is not None else []
        self._stream_lines = list(stream_lines) if stream_lines is not None else []
        self.requests: list[DeepSeekChatRequest] = []

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        """记录 request 后返回队列中的下一项。"""

        self.requests.append(request)
        if not self._responses:
            raise AssertionError("fake transport exhausted")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def send_stream(self, request: DeepSeekChatRequest) -> "Iterator[str]":
        """记录 request 后 yield SSE 行；优先使用 stream_lines，否则从 responses 自动转换。"""

        self.requests.append(request)
        if self._stream_lines:
            yield from self._stream_lines.pop(0)
            return
        if not self._responses:
            raise AssertionError("fake stream transport exhausted")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        yield from _response_to_sse_lines(item)


def _response_to_sse_lines(response: DeepSeekChatResponse) -> Iterator[str]:
    """把非流式 DeepSeekChatResponse 转为 fake SSE 行，供 send_stream 使用。"""

    if response.status_code != 200:
        raise DeepSeekTransportUnavailable("unavailable", status_code=response.status_code)
    try:
        body = json.loads(response.body)
        message = body["choices"][0]["message"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        # 不可解析的响应体 → 把 raw body 作为 content 透传，
        # 让 _parse_response 产生 LLM_MALFORMED_RESPONSE
        chunk = {"choices": [{"delta": {"content": response.body}, "index": 0, "finish_reason": "stop"}]}
        yield f"data: {json.dumps(chunk)}\n"
        yield "data: [DONE]\n"
        return

    if message.get("tool_calls"):
        tc = message["tool_calls"][0]
        tc_chunk = {
            "choices": [{"delta": {"tool_calls": [tc]}, "index": 0, "finish_reason": "tool_calls"}],
        }
        yield f"data: {json.dumps(tc_chunk, ensure_ascii=False)}\n"
    elif message.get("content"):
        content = message["content"]
        content_chunk = {
            "choices": [{"delta": {"content": content}, "index": 0, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n"

    yield "data: [DONE]\n"


def _identity() -> ReportIdentity:
    """构造测试用报告身份。"""

    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-secret-import-id",
        content_fingerprint="abc123def4567890abc123def4567890",
        document_id=_DOCUMENT_ID,
    )


def _write_docling_json(path: Path) -> None:
    """写入含章节和表格的 Docling-shaped JSON，用于 adapter runner 测试。"""

    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "4.1.2 基金经理简介",
                "level": 1,
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理在本报告期内保持稳定。基金经理张明负责本基金投资管理。",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service(tmp_path: Path) -> FundDocumentToolService:
    """构造只包含受控 DoclingDocumentStore 的 ToolService。"""

    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
    _write_docling_json(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def _env(**overrides: str) -> dict[str, str]:
    """构造不读取真实 os.environ 的 DeepSeek 环境变量映射。"""

    env = {"DEEPSEEK_API_KEY": _TEST_API_KEY}
    env.update(overrides)
    return env


def _chat_response(message: dict[str, Any]) -> DeepSeekChatResponse:
    """构造 OpenAI-compatible chat completions response。"""

    return DeepSeekChatResponse(status_code=200, body=json.dumps({"choices": [{"message": message}]}))


def _tool_call_response(tool_name: str, arguments: dict[str, Any]) -> DeepSeekChatResponse:
    """构造 provider tool call response。"""

    return _chat_response(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            ],
        }
    )


def _final_response(answer: str, citations: tuple[Citation, ...], key_facts: tuple[str, ...]) -> DeepSeekChatResponse:
    """构造 provider final answer response。"""

    return _chat_response(
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "answer": answer,
                    "citations": [_citation_payload(citation) for citation in citations],
                    "key_facts": list(key_facts),
                },
                ensure_ascii=False,
            ),
        }
    )


def _citation_payload(citation: Citation) -> dict[str, Any]:
    """把 Citation 转为 provider final answer JSON。"""

    return {
        "document_id": citation.document_id,
        "fund_code": citation.fund_code,
        "fund_name": citation.fund_name,
        "year": citation.year,
        "report_type": citation.report_type,
        "locator": {
            "document_id": citation.locator.document_id,
            "locator_kind": citation.locator.locator_kind.value,
            "section_ref": citation.locator.section_ref,
            "table_ref": citation.locator.table_ref,
            "page_no": citation.locator.page_no,
            "page_range": list(citation.locator.page_range) if citation.locator.page_range is not None else None,
            "internal_ref": None,
            "internal_ref_available": False,
            "bbox": None,
        },
    }


def _citation_from_payload(payload: dict[str, Any]) -> Citation:
    """从 safe citation payload 还原 Citation。"""

    locator = payload["locator"]
    return Citation(
        document_id=payload["document_id"],
        fund_code=payload["fund_code"],
        fund_name=payload["fund_name"],
        year=payload["year"],
        report_type=payload["report_type"],
        locator=Locator(
            document_id=locator["document_id"],
            locator_kind=LocatorKind(locator["locator_kind"]),
            section_ref=locator["section_ref"],
            table_ref=locator["table_ref"],
            page_no=locator["page_no"],
            page_range=tuple(locator["page_range"]) if locator["page_range"] is not None else None,
            internal_ref=None,
            internal_ref_available=False,
            bbox=None,
        ),
    )


def _latest_citation_from_request(request: DeepSeekChatRequest) -> tuple[Citation, ...]:
    """从 request 中的 prior_tool_results 取最近 citation。"""

    user_message = request.payload["messages"][1]
    content = json.loads(user_message["content"])
    citations = content["prior_tool_results"][-1]["citations"]
    return tuple(_citation_from_payload(citation) for citation in citations)


def test_deepseek_adapter_parses_tool_call_response_and_enters_8a_runner(tmp_path: Path) -> None:
    """DeepSeek tool-call response 必须解析为 ToolCall 并进入既有 8A runner。"""

    class SearchReadFinalTransport(QueueTransport):
        """按 search -> read_section -> final answer 返回 provider response。"""

        def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
            """根据调用轮次返回下一步 provider response。"""

            self.requests.append(request)
            if len(self.requests) == 1:
                return _tool_call_response(
                    ToolName.SEARCH_DOCUMENT.value,
                    {"document_id": _DOCUMENT_ID, "query": "基金经理", "max_results": 1},
                )
            if len(self.requests) == 2:
                return _tool_call_response(
                    ToolName.READ_SECTION.value,
                    {"document_id": _DOCUMENT_ID, "section_ref": "section-0000"},
                )
            return _final_response("基金经理张明负责本基金投资管理。", _latest_citation_from_request(request), ("张明",))

    transport = SearchReadFinalTransport([])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(
            transport=transport,
            env=_env(DEEPSEEK_BASE_URL="https://api.deepseek.com/v1?secret=x"),
            options=ExecutionOptions(stream=False),
        ),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert result.failure is None
    assert result.answer == "基金经理张明负责本基金投资管理。"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (ToolName.SEARCH_DOCUMENT, ToolName.READ_SECTION)
    assert len(transport.requests) == 3
    first_request = transport.requests[0]
    assert first_request.url == "https://api.deepseek.com/v1/chat/completions"
    assert first_request.headers["Authorization"] == f"Bearer {_TEST_API_KEY}"
    assert first_request.payload["model"] == "deepseek-v4-flash"
    assert first_request.payload["tool_choice"] == "auto"
    assert first_request.payload["stream"] is False
    tool_names = {tool["function"]["name"] for tool in first_request.payload["tools"]}
    assert tool_names == {
        "search_document",
        "read_section",
        "list_tables",
        "read_table",
        "get_excerpt",
        "aggregate_multi_year_annual_performance",
    }


def test_deepseek_adapter_parses_final_answer_and_preserves_8a_enforcement(tmp_path: Path) -> None:
    """DeepSeek final-answer response 必须解析为 FinalAnswer，并由 8A runner 校验证据。"""

    class FinalAfterSearchTransport(QueueTransport):
        """第二次请求用 prior tool citation 生成 final answer。"""

        def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
            """先请求 search/read_section，再返回带 section citation 的 final answer。"""

            self.requests.append(request)
            if len(self.requests) == 1:
                return _tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"document_id": _DOCUMENT_ID, "query": "基金经理"})
            if len(self.requests) == 2:
                results = json.loads(request.payload["messages"][1]["content"])["prior_tool_results"]
                hit = results[-1]["evidence_text"]
                assert "张明" in hit
                return _tool_call_response(ToolName.READ_SECTION.value, {"document_id": _DOCUMENT_ID, "section_ref": "section-0000"})
            return _final_response("基金经理张明负责本基金投资管理。", _latest_citation_from_request(request), ("张明",))

    transport = FinalAfterSearchTransport([])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(
            transport=transport,
            env=_env(DEEPSEEK_MODEL="unit-test-model"),
            options=ExecutionOptions(stream=False),
        ),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert result.failure is None
    assert "张明" in result.answer
    assert result.citations[0].locator.section_ref == "section-0000"
    assert transport.requests[0].payload["model"] == "unit-test-model"


def test_deepseek_api_key_missing_returns_unavailable_without_network_call(tmp_path: Path) -> None:
    """DEEPSEEK_API_KEY 缺失时必须 unavailable，且不得调用 transport。"""

    transport = QueueTransport([])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env={}),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert transport.requests == []


@pytest.mark.parametrize(
    "response",
    [
        DeepSeekTransportUnavailable("auth"),
        DeepSeekTransportUnavailable("network"),
        DeepSeekTransportUnavailable("timeout"),
        DeepSeekChatResponse(status_code=429, body='{"error":"rate limit"}'),
    ],
)
def test_deepseek_transport_auth_network_timeout_rate_limit_map_to_unavailable(
    tmp_path: Path,
    response: DeepSeekChatResponse | Exception,
) -> None:
    """auth/network/timeout/rate-limit 必须稳定映射为 unavailable。"""

    transport = QueueTransport([response])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE


@pytest.mark.parametrize(
    "response",
    [
        DeepSeekChatResponse(status_code=200, body=json.dumps({"choices": [{"message": {"tool_calls": []}}]})),
        _tool_call_response(ToolName.SEARCH_DOCUMENT.value, None),
        DeepSeekChatResponse(status_code=200, body=json.dumps({"choices": [{"message": {}}]})),
    ],
)
def test_deepseek_content_none_or_tool_parse_failed_maps_to_llm_malformed_response(
    tmp_path: Path,
    response: DeepSeekChatResponse,
) -> None:
    """content=None 或 tool call 结构不可解析必须映射为 llm_malformed_response。

    注意：缺 document_id 已不再是 malformed（S2 由 runner 用 expected 补全），
    因此该参数化只保留真正不可解析的结构。
    """

    # S6：malformed 有界重试 1 次 → 双响应才能稳定映射为 llm_malformed_response
    transport = QueueTransport([response, response])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.LLM_MALFORMED_RESPONSE
    assert len(transport.requests) == 2


def _malformed_response() -> DeepSeekChatResponse:
    """构造结构不可解析的 provider response（空 tool_calls → _parse_tool_call 失败）。"""

    return DeepSeekChatResponse(
        status_code=200,
        body=json.dumps({"choices": [{"message": {"tool_calls": []}}]}),
    )


def test_deepseek_next_step_malformed_retried_once_then_success(tmp_path: Path) -> None:
    """非流式：第一次响应 malformed、第二次有效 → next_step 成功，共发起 2 次请求。"""

    transport = QueueTransport([
        _malformed_response(),
        _tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"document_id": _DOCUMENT_ID, "query": "基金经理"}),
    ])
    client = DeepSeekLlmClient(transport=transport, env=_env(), options=ExecutionOptions(stream=False))

    response = client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert isinstance(response.step, ToolCall)
    assert response.step.tool_name is ToolName.SEARCH_DOCUMENT
    assert len(transport.requests) == 2


def test_deepseek_next_step_double_malformed_raises_with_two_requests(tmp_path: Path) -> None:
    """非流式：连续两次 malformed → 仍抛 LLM_MALFORMED_RESPONSE，且只发起 2 次请求。"""

    transport = QueueTransport([_malformed_response(), _malformed_response()])
    client = DeepSeekLlmClient(transport=transport, env=_env(), options=ExecutionOptions(stream=False))

    with pytest.raises(LlmClientFailure) as excinfo:
        client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert excinfo.value.code is FailureCode.LLM_MALFORMED_RESPONSE
    assert len(transport.requests) == 2


def test_deepseek_next_step_stream_malformed_retried_once_then_success(tmp_path: Path) -> None:
    """流式路径：第一次响应 malformed、第二次有效 → next_step 成功，共发起 2 次请求。"""

    transport = QueueTransport([
        _malformed_response(),
        _tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"document_id": _DOCUMENT_ID, "query": "基金经理"}),
    ])
    client = DeepSeekLlmClient(transport=transport, env=_env(), options=ExecutionOptions(stream=True))

    response = client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert isinstance(response.step, ToolCall)
    assert response.step.tool_name is ToolName.SEARCH_DOCUMENT
    assert len(transport.requests) == 2


def test_deepseek_next_step_stream_double_malformed_raises_with_two_requests(tmp_path: Path) -> None:
    """流式路径：连续两次 malformed → 仍抛 LLM_MALFORMED_RESPONSE，且只发起 2 次请求。"""

    transport = QueueTransport([_malformed_response(), _malformed_response()])
    client = DeepSeekLlmClient(transport=transport, env=_env(), options=ExecutionOptions(stream=True))

    with pytest.raises(LlmClientFailure) as excinfo:
        client.next_step(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())

    assert excinfo.value.code is FailureCode.LLM_MALFORMED_RESPONSE
    assert len(transport.requests) == 2


def test_deepseek_tool_call_missing_document_id_filled_by_runner(tmp_path: Path) -> None:
    """provider tool call 缺 document_id：解析通过并由 runner 用 expected 补全。"""

    class MissingDocumentIdTransport(QueueTransport):
        """首次返回缺 document_id 的 search tool call，随后返回 read_section 与 final answer。"""

        def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
            """按轮次返回 provider response。"""

            self.requests.append(request)
            if len(self.requests) == 1:
                return _tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"query": "基金经理"})
            if len(self.requests) == 2:
                return _tool_call_response(
                    ToolName.READ_SECTION.value,
                    {"section_ref": "section-0000"},
                )
            return _final_response(
                "基金经理张明负责本基金投资管理。",
                _latest_citation_from_request(request),
                ("张明",),
            )

    transport = MissingDocumentIdTransport([])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(
            transport=transport,
            env=_env(),
            options=ExecutionOptions(stream=False),
        ),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert result.failure is None
    assert result.answer == "基金经理张明负责本基金投资管理。"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
    )
    assert len(transport.requests) == 3


def test_deepseek_malformed_json_falls_back_to_markdown_answer(tmp_path: Path) -> None:
    """Fix 1: 顶层 JSON 不可解析时应 fallback 为 markdown answer，不再报 LLM_MALFORMED_RESPONSE。"""

    transport = QueueTransport([DeepSeekChatResponse(status_code=200, body="{not json")])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    # malformed body 被 SSE 包装后变成 content="{not json"，fallback 为 markdown answer；
    # 没有工具证据 → runner fail-closed，但不再是 LLM_MALFORMED_RESPONSE
    assert not (
        isinstance(result.failure, ToolFailure) and result.failure.code is FailureCode.LLM_MALFORMED_RESPONSE
    )


@pytest.mark.parametrize(
    ("tool_name", "expected_tool_name"),
    [
        ("extract_fields", "extract_fields"),
        (ToolName.LIST_REPORTS.value, ToolName.LIST_REPORTS),
    ],
)
def test_deepseek_unknown_or_unauthorized_tool_fails_closed(
    tmp_path: Path,
    tool_name: str,
    expected_tool_name: str | ToolName,
) -> None:
    """provider 请求未知工具或未授权工具时必须复用 8A fail-closed。"""

    transport = QueueTransport([_tool_call_response(tool_name, {"document_id": _DOCUMENT_ID})])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.tool_trace[0].tool_name == expected_tool_name
    assert result.tool_trace[0].result_kind == "failure"


def test_deepseek_final_answer_without_citation_fails_closed(tmp_path: Path) -> None:
    """provider final answer 有工具证据但缺 citation 时必须由 8A runner fail-closed。"""

    transport = QueueTransport(
        [
            _tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"document_id": _DOCUMENT_ID, "query": "基金经理"}),
            _chat_response(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"answer": "基金经理张明负责本基金投资管理。", "citations": [], "key_facts": ["张明"]},
                        ensure_ascii=False,
                    ),
                }
            ),
        ]
    )
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""


def test_deepseek_final_answer_without_evidence_fails_closed(tmp_path: Path) -> None:
    """provider 未调用工具就直接 final answer 时必须由 8A runner fail-closed。"""

    transport = QueueTransport([_final_response("基金经理张明负责本基金投资管理。", (), ("张明",))])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.tool_trace == ()


def test_deepseek_default_tests_use_fake_transport_no_real_key_and_no_secret_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认单测使用 fake transport，不读取真实 key，输出不泄漏 secret 或 private payload。"""

    monkeypatch.setenv("DEEPSEEK_API_KEY", _REAL_ENV_SECRET)
    transport = QueueTransport([_tool_call_response("extract_fields", {"document_id": _DOCUMENT_ID})])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env(DEEPSEEK_MODEL="unit-test-model")),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")
    rendered = str(asdict(result))
    request_rendered = json.dumps(transport.requests[0].payload, ensure_ascii=False)

    assert isinstance(result.failure, ToolFailure)
    assert transport.requests[0].headers["Authorization"] == f"Bearer {_TEST_API_KEY}"
    assert _REAL_ENV_SECRET not in rendered
    assert _TEST_API_KEY not in rendered
    assert _REAL_ENV_SECRET not in request_rendered
    assert _TEST_API_KEY not in request_rendered
    assert "private-cache" not in request_rendered
    assert ".docling.json" not in request_rendered
    assert "schema_name" not in request_rendered
    assert _identity().local_import_id not in request_rendered
    # 默认 stream=True
    assert transport.requests[0].payload["stream"] is True


# ── SSE streaming tests ──────────────────────────────────────────────


def _sse_content_chunked(text: str, chunk_size: int = 2) -> list[str]:
    """模拟逐 token 的 SSE content delta 行。"""

    lines: list[str] = []
    for i in range(0, len(text), chunk_size):
        chunk = {"choices": [{"delta": {"content": text[i : i + chunk_size]}, "index": 0}]}
        lines.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n")
    done_chunk = {"choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]}
    lines.append(f"data: {json.dumps(done_chunk)}\n")
    lines.append("data: [DONE]\n")
    return lines


def _sse_tool_call_stream_lines(tool_name: str, arguments: dict[str, Any]) -> list[str]:
    """模拟流式 tool call 的 SSE 行（name → arguments → finish）。"""

    args_json = json.dumps(arguments, ensure_ascii=False)
    name_chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": ""},
                        }
                    ]
                },
                "index": 0,
            }
        ]
    }
    args_chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "function": {"arguments": args_json}}
                    ]
                },
                "index": 0,
            }
        ]
    }
    finish_chunk = {"choices": [{"delta": {}, "index": 0, "finish_reason": "tool_calls"}]}
    return [
        f"data: {json.dumps(name_chunk, ensure_ascii=False)}\n",
        f"data: {json.dumps(args_chunk, ensure_ascii=False)}\n",
        f"data: {json.dumps(finish_chunk)}\n",
        "data: [DONE]\n",
    ]


def _sse_reasoning_lines(reasoning: str) -> list[str]:
    """模拟 reasoning_content 的 SSE 行。"""

    chunk = {
        "choices": [
            {"delta": {"reasoning_content": reasoning}, "index": 0}
        ]
    }
    done_chunk = {"choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]}
    return [
        f"data: {json.dumps(chunk, ensure_ascii=False)}\n",
        f"data: {json.dumps(done_chunk)}\n",
        "data: [DONE]\n",
    ]


def _sse_error_lines(status_code: int) -> list[str]:
    """模拟 SSE 传输错误的异常。"""

    raise DeepSeekTransportUnavailable("unavailable", status_code=status_code)


def test_next_step_stream_content_delta() -> None:
    """stream=True 时 CONTENT_DELTA 事件逐 token 产出，并以 DONE 结束。"""

    text = "基金经理张明负责本基金投资管理。"
    sse_lines = _sse_content_chunked(text, chunk_size=3)
    transport = QueueTransport(stream_lines=[sse_lines])
    client = DeepSeekLlmClient(transport=transport, env=_env())

    events = list(
        client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())
    )

    content_events = [e for e in events if e.type == StreamEventType.CONTENT_DELTA]
    done_events = [e for e in events if e.type == StreamEventType.DONE]
    error_events = [e for e in events if e.type == StreamEventType.ERROR]

    assert len(content_events) >= 3  # chunked into at least 3 parts
    assert "".join(e.payload for e in content_events) == text
    assert len(done_events) == 1
    assert done_events[0].payload is None
    assert error_events == []


def test_next_step_stream_tool_call() -> None:
    """stream=True 时 tool call delta 转换为 TOOL_EVENT + DONE。"""

    sse_lines = _sse_tool_call_stream_lines(
        "search_document",
        {"document_id": _DOCUMENT_ID, "query": "基金经理", "max_results": 1},
    )
    transport = QueueTransport(stream_lines=[sse_lines])
    client = DeepSeekLlmClient(transport=transport, env=_env())

    events = list(
        client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())
    )

    tool_events = [e for e in events if e.type == StreamEventType.TOOL_EVENT]
    done_events = [e for e in events if e.type == StreamEventType.DONE]

    assert len(tool_events) == 1
    assert tool_events[0].payload["phase"] == "call"
    assert tool_events[0].payload["tool_name"] == "search_document"
    assert tool_events[0].payload["call_id"] == "call-1"
    arguments = json.loads(tool_events[0].payload["arguments"])
    assert arguments["document_id"] == _DOCUMENT_ID
    assert arguments["query"] == "基金经理"
    assert len(done_events) == 1


def test_next_step_stream_reasoning_delta() -> None:
    """stream=True 时 reasoning_content 转换为 REASONING_DELTA。"""

    sse_lines = _sse_reasoning_lines("需要先搜索基金经理相关信息")
    transport = QueueTransport(stream_lines=[sse_lines])
    client = DeepSeekLlmClient(transport=transport, env=_env())

    events = list(
        client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())
    )

    reasoning_events = [e for e in events if e.type == StreamEventType.REASONING_DELTA]
    assert len(reasoning_events) == 1
    assert reasoning_events[0].payload == "需要先搜索基金经理相关信息"
    assert any(e.type == StreamEventType.DONE for e in events)


def test_next_step_stream_transport_error() -> None:
    """HTTP/network error 时产出 ERROR 事件，不产出 DONE。"""

    transport = QueueTransport(
        stream_lines=[[DeepSeekTransportUnavailable("network", status_code=503)]],  # type: ignore[list-item]
    )
    # QueueTransport.send_stream pops from stream_lines, gets the exception, raises it
    client = DeepSeekLlmClient(transport=transport, env=_env())

    events = list(
        client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())
    )

    error_events = [e for e in events if e.type == StreamEventType.ERROR]
    done_events = [e for e in events if e.type == StreamEventType.DONE]
    assert len(error_events) >= 1
    assert done_events == []


def test_next_step_stream_api_key_missing() -> None:
    """API key 缺失时产出 ERROR 事件。"""

    transport = QueueTransport()
    client = DeepSeekLlmClient(transport=transport, env={})

    events = list(
        client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())
    )

    error_events = [e for e in events if e.type == StreamEventType.ERROR]
    assert len(error_events) == 1
    assert error_events[0].payload["code"] == FailureCode.UNAVAILABLE.value


def test_next_step_stream_auth_error_no_retry() -> None:
    """401/403 不重试，立即产出 ERROR。"""

    transport = QueueTransport(
        stream_lines=[[DeepSeekTransportUnavailable("auth", status_code=401)]],  # type: ignore[list-item]
    )
    client = DeepSeekLlmClient(transport=transport, env=_env())

    events = list(
        client.next_step_stream(document_id=_DOCUMENT_ID, query="基金经理", tool_results=())
    )

    error_events = [e for e in events if e.type == StreamEventType.ERROR]
    assert len(error_events) == 1


def test_next_step_with_stream_true_default(tmp_path: Path) -> None:
    """默认 stream=True 时 next_step() 内部收集 SSE 并返回 ToolCall/FinalAnswer。"""

    sse_lines = _sse_tool_call_stream_lines(
        "search_document",
        {"document_id": _DOCUMENT_ID, "query": "基金经理", "max_results": 1},
    )
    transport = QueueTransport(stream_lines=[sse_lines])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert result.tool_trace[0].tool_name == ToolName.SEARCH_DOCUMENT
    assert transport.requests[0].payload["stream"] is True


def test_next_step_with_stream_false_uses_non_streaming(tmp_path: Path) -> None:
    """stream=False 时使用传统非流式路径。"""

    transport = QueueTransport(
        [_tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"document_id": _DOCUMENT_ID, "query": "基金经理"})]
    )
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(
            transport=transport,
            env=_env(),
            options=ExecutionOptions(stream=False),
        ),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert result.tool_trace[0].tool_name == ToolName.SEARCH_DOCUMENT
    assert transport.requests[0].payload["stream"] is False
