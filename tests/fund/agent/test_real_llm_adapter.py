"""Post-MVP Slice 8B DeepSeek real LLM adapter 测试。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from fund_agent.agent import (
    DeepSeekChatRequest,
    DeepSeekChatResponse,
    DeepSeekLlmClient,
    DeepSeekTransportUnavailable,
    LlmToolLoopRunner,
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

    返回:
        DeepSeekTransportProtocol-compatible fake transport。

    异常:
        队列耗尽时抛 AssertionError，表示测试脚本错误。
    """

    def __init__(self, responses: Iterable[DeepSeekChatResponse | Exception]) -> None:
        """保存 response 队列并记录收到的 request。"""

        self._responses = list(responses)
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
        llm_client=DeepSeekLlmClient(transport=transport, env=_env(DEEPSEEK_BASE_URL="https://api.deepseek.com/v1?secret=x")),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert result.failure is None
    assert result.answer == "基金经理张明负责本基金投资管理。"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (ToolName.SEARCH_DOCUMENT, ToolName.READ_SECTION)
    assert len(transport.requests) == 3
    first_request = transport.requests[0]
    assert first_request.url == "https://api.deepseek.com/v1/chat/completions"
    assert first_request.headers["Authorization"] == f"Bearer {_TEST_API_KEY}"
    assert first_request.payload["model"] == "deepseek-chat"
    assert first_request.payload["tool_choice"] == "auto"
    assert first_request.payload["stream"] is False
    tool_names = {tool["function"]["name"] for tool in first_request.payload["tools"]}
    assert tool_names == {
        "search_document",
        "read_section",
        "list_tables",
        "read_table",
        "get_excerpt",
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
        llm_client=DeepSeekLlmClient(transport=transport, env=_env(DEEPSEEK_MODEL="unit-test-model")),
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
        DeepSeekChatResponse(status_code=200, body="{not json"),
        DeepSeekChatResponse(status_code=200, body=json.dumps({"choices": [{"message": {"tool_calls": []}}]})),
        _tool_call_response(ToolName.SEARCH_DOCUMENT.value, {"query": "基金经理"}),
        _chat_response({"role": "assistant", "content": json.dumps({"answer": "缺字段"}, ensure_ascii=False)}),
    ],
)
def test_deepseek_malformed_json_or_schema_parse_failed_maps_to_llm_malformed_response(
    tmp_path: Path,
    response: DeepSeekChatResponse,
) -> None:
    """malformed JSON/schema parse failed 必须映射为 llm_malformed_response。"""

    transport = QueueTransport([response])
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=DeepSeekLlmClient(transport=transport, env=_env()),
    )

    result = runner.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.LLM_MALFORMED_RESPONSE


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
    assert result.citations == ()


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
