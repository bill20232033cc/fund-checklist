"""Post-MVP Slice 8C opt-in live DeepSeek smoke 测试。"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from typing import Any

import pytest

from fund_agent.agent import (
    DeepSeekChatRequest,
    DeepSeekChatResponse,
    DeepSeekLlmClient,
    DeepSeekTransportUnavailable,
    LlmToolLoopRunner,
)
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.models import (
    Citation,
    ExcerptContent,
    Locator,
    SearchResult,
    SectionContent,
    TableContent,
    TableSummary,
    ToolFailure,
)

_LIVE_OPT_IN_ENV = "FUND_CHECKLIST_RUN_LIVE_DEEPSEEK"
_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
_DEEPSEEK_BASE_URL_ENV = "DEEPSEEK_BASE_URL"
_DEEPSEEK_MODEL_ENV = "DEEPSEEK_MODEL"
_DEFAULT_LIVE_BASE_URL = "https://api.deepseek.com"
_DEFAULT_LIVE_MODEL = "deepseek-v4-flash"
_LIVE_TIMEOUT_SECONDS = 300
_LIVE_MAX_RETRIES = 1
_DOCUMENT_ID = "004393-2024-annual_report-live8c0000000000"
_SECTION_REF = "section-live-0001"
_TABLE_REF = "table-live-0001"
_ANSWER_TEXT = "基金经理张明负责本基金投资管理。"
_PRIVATE_IMPORT_ID = "local-import-id-must-not-leak"


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


class SearchThenFinalTransport:
    """先返回 search_document tool call，再用 prior citation 返回 final answer。"""

    def __init__(self) -> None:
        """初始化 request 记录。"""

        self.requests: list[DeepSeekChatRequest] = []

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        """按请求轮次返回受控 provider response。"""

        self.requests.append(request)
        if len(self.requests) == 1:
            return _tool_call_response(
                ToolName.SEARCH_DOCUMENT.value,
                {"document_id": _DOCUMENT_ID, "query": "基金经理", "max_results": 1},
            )
        return _final_response(_ANSWER_TEXT, _latest_citations_from_request(request), ("张明",))


class InMemoryReadingToolService:
    """Slice 8C 使用的内存 reading tool service。

    参数:
        无。

    返回:
        提供 LlmToolLoopRunner 所需 public tool 方法的 in-memory service。

    异常:
        public 方法不抛异常；未知 document/locator 返回 ToolFailure。
    """

    def search_document(
        self,
        document_id: str,
        query: str,
        *,
        within_section_ref: str | None = None,
        max_results: int | None = None,
    ) -> tuple[SearchResult, ...] | ToolFailure:
        """返回固定 search hit，不读取 PDF、Docling 或 repository。"""

        del within_section_ref, max_results
        if document_id != _DOCUMENT_ID or "基金经理" not in query:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="未找到匹配内容")
        locator = _section_locator()
        return (
            SearchResult(
                rank=1,
                section_ref=_SECTION_REF,
                title="基金经理简介",
                excerpt=_ANSWER_TEXT,
                locator=locator,
                citation=_citation(locator),
            ),
        )

    def read_section(
        self,
        document_id: str,
        section_ref: str,
        *,
        max_chars: int | None = None,
    ) -> SectionContent | ToolFailure:
        """返回固定 section content，不读取 raw Docling JSON。"""

        del max_chars
        if document_id != _DOCUMENT_ID or section_ref != _SECTION_REF:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="章节不存在")
        locator = _section_locator()
        return SectionContent(
            section_ref=_SECTION_REF,
            title="基金经理简介",
            text=_ANSWER_TEXT,
            truncated=False,
            locator=locator,
            citation=_citation(locator),
        )

    def list_tables(
        self,
        document_id: str,
        *,
        within_section_ref: str | None = None,
    ) -> tuple[TableSummary, ...] | ToolFailure:
        """返回固定表格摘要，用于 provider 选择表格路径时继续闭环。"""

        if document_id != _DOCUMENT_ID:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="文档不存在")
        if within_section_ref not in {None, _SECTION_REF}:
            return ()
        return (
            TableSummary(
                table_ref=_TABLE_REF,
                caption="基金经理情况",
                section_ref=_SECTION_REF,
                locator=_table_locator(),
                row_count=2,
                column_count=2,
            ),
        )

    def read_table(
        self,
        document_id: str,
        table_ref: str,
        *,
        max_rows: int | None = None,
    ) -> TableContent | ToolFailure:
        """返回固定 table content，用于 live provider 表格 tool call。"""

        del max_rows
        if document_id != _DOCUMENT_ID or table_ref != _TABLE_REF:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="表格不存在")
        locator = _table_locator()
        return TableContent(
            table_ref=_TABLE_REF,
            caption="基金经理情况",
            section_ref=_SECTION_REF,
            rows=(("姓名", "职责"), ("张明", "负责本基金投资管理")),
            truncated=False,
            locator=locator,
            citation=_citation(locator),
        )

    def get_excerpt(
        self,
        document_id: str,
        locator: Locator,
        *,
        max_chars: int | None = None,
    ) -> ExcerptContent | ToolFailure:
        """返回固定 excerpt content，只接受受控 locator。"""

        del max_chars
        if document_id != _DOCUMENT_ID or locator.document_id != _DOCUMENT_ID:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="摘录不存在")
        return ExcerptContent(
            text=_ANSWER_TEXT,
            truncated=False,
            locator=locator,
            citation=_citation(locator),
        )


def test_live_smoke_skips_when_not_explicitly_opted_in() -> None:
    """未设置 FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 时必须 skip。"""

    reason = _live_skip_reason({})

    assert reason == "未设置 FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1，跳过 live DeepSeek smoke"


def test_live_smoke_skips_when_opted_in_without_api_key() -> None:
    """显式 opt-in 但缺 DEEPSEEK_API_KEY 时必须 skip，不失败。"""

    reason = _live_skip_reason({_LIVE_OPT_IN_ENV: "1"})

    assert reason == "缺少 DEEPSEEK_API_KEY，跳过 live DeepSeek smoke"


def test_live_smoke_uses_slice_8c_defaults_timeout_and_8a_runner() -> None:
    """8C live helper 必须使用裁决默认值、300 秒 timeout，并进入 8A runner。"""

    transport = SearchThenFinalTransport()
    result, attempts = _run_live_smoke(
        env={_LIVE_OPT_IN_ENV: "1", _DEEPSEEK_API_KEY_ENV: "unit-test-key"},
        transport=transport,
    )

    assert result.failure is None
    assert result.answer == _ANSWER_TEXT
    assert attempts == 1
    assert len(transport.requests) == 2
    first_request = transport.requests[0]
    assert first_request.url == "https://api.deepseek.com/chat/completions"
    assert first_request.payload["model"] == _DEFAULT_LIVE_MODEL
    assert first_request.timeout_seconds == _LIVE_TIMEOUT_SECONDS
    assert tuple(entry.tool_name for entry in result.tool_trace) == (ToolName.SEARCH_DOCUMENT,)


def test_live_smoke_allows_base_url_and_model_override() -> None:
    """DEEPSEEK_BASE_URL 与 DEEPSEEK_MODEL 必须可覆盖。"""

    transport = SearchThenFinalTransport()
    result, _ = _run_live_smoke(
        env={
            _LIVE_OPT_IN_ENV: "1",
            _DEEPSEEK_API_KEY_ENV: "unit-test-key",
            _DEEPSEEK_BASE_URL_ENV: "https://api.deepseek.com/v1",
            _DEEPSEEK_MODEL_ENV: "unit-test-model",
        },
        transport=transport,
    )

    assert result.failure is None
    assert transport.requests[0].url == "https://api.deepseek.com/v1/chat/completions"
    assert transport.requests[0].payload["model"] == "unit-test-model"


def test_live_smoke_retries_at_most_once_and_fails_closed() -> None:
    """provider unavailable 时最多 retry 一次，最终仍 fail-closed。"""

    transport = QueueTransport(
        [
            DeepSeekTransportUnavailable("network"),
            DeepSeekTransportUnavailable("rate limit"),
        ]
    )
    result, attempts = _run_live_smoke(
        env={_LIVE_OPT_IN_ENV: "1", _DEEPSEEK_API_KEY_ENV: "unit-test-key"},
        transport=transport,
    )

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert attempts == _LIVE_MAX_RETRIES + 1
    assert len(transport.requests) == _LIVE_MAX_RETRIES + 1


def test_live_smoke_malformed_provider_response_fails_without_retry() -> None:
    """provider response 不可解析时必须 fail，不用 retry 掩盖解析错误。"""

    transport = QueueTransport([DeepSeekChatResponse(status_code=200, body="{not-json")])
    result, attempts = _run_live_smoke(
        env={_LIVE_OPT_IN_ENV: "1", _DEEPSEEK_API_KEY_ENV: "unit-test-key"},
        transport=transport,
    )

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.LLM_MALFORMED_RESPONSE
    assert attempts == 1


def test_live_smoke_does_not_leak_api_key_or_write_raw_response_artifact() -> None:
    """测试输出模型不得泄漏 API key，helper 不写 provider raw response artifact。"""

    secret = "unit-secret-must-not-leak"
    transport = SearchThenFinalTransport()
    result, _ = _run_live_smoke(
        env={_LIVE_OPT_IN_ENV: "1", _DEEPSEEK_API_KEY_ENV: secret},
        transport=transport,
    )
    rendered_result = json.dumps(asdict(result), ensure_ascii=False, default=str)
    rendered_payload = json.dumps(transport.requests[-1].payload, ensure_ascii=False)

    assert result.failure is None
    assert secret not in rendered_result
    assert secret not in rendered_payload
    assert _PRIVATE_IMPORT_ID not in rendered_result
    assert _PRIVATE_IMPORT_ID not in rendered_payload


def test_opt_in_live_deepseek_returns_controlled_step_and_enters_8a_runner() -> None:
    """真实 DeepSeek opt-in smoke；默认 pytest 必须 skip 且不联网。"""

    reason = _live_skip_reason(os.environ)
    if reason is not None:
        pytest.skip(reason)

    api_key = os.environ.get(_DEEPSEEK_API_KEY_ENV, "")
    result, attempts = _run_live_smoke(env=os.environ)
    rendered_result = json.dumps(asdict(result), ensure_ascii=False, default=str)
    if api_key and api_key in rendered_result:
        pytest.fail("live DeepSeek smoke 泄漏 API key")

    assert attempts <= _LIVE_MAX_RETRIES + 1
    assert result.failure is None, _safe_failure_message(result.failure)
    assert result.tool_trace, "live DeepSeek smoke 未产生受控 tool trace"
    assert all(entry.result_kind == "success" for entry in result.tool_trace)


def _run_live_smoke(
    *,
    env: Mapping[str, str],
    transport: Any | None = None,
) -> tuple[Any, int]:
    """运行最多一次 retry 的 8C smoke，并返回结果与尝试次数。"""

    attempts = 0
    last_result = None
    for _ in range(_LIVE_MAX_RETRIES + 1):
        attempts += 1
        result = _run_live_smoke_once(env=env, transport=transport)
        if result.failure is None:
            return result, attempts
        last_result = result
        if result.failure.code is not FailureCode.UNAVAILABLE:
            break
    if last_result is None:
        raise AssertionError("live smoke did not run")
    return last_result, attempts


def _run_live_smoke_once(
    *,
    env: Mapping[str, str],
    transport: Any | None,
) -> Any:
    """执行一次 DeepSeek adapter + 8A runner smoke。"""

    client = DeepSeekLlmClient(
        transport=transport,
        env=_deepseek_env(env),
        timeout_seconds=_LIVE_TIMEOUT_SECONDS,
    )
    runner = LlmToolLoopRunner(
        tool_service=InMemoryReadingToolService(),  # type: ignore[arg-type]
        llm_client=client,
    )
    return runner.run(
        document_id=_DOCUMENT_ID,
        query="请在这份年报中先调用 search_document 查找基金经理，再基于工具证据回答。",
    )


def _live_skip_reason(env: Mapping[str, str]) -> str | None:
    """返回 live smoke skip reason；可运行时返回 None。"""

    if env.get(_LIVE_OPT_IN_ENV) != "1":
        return "未设置 FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1，跳过 live DeepSeek smoke"
    if not env.get(_DEEPSEEK_API_KEY_ENV, "").strip():
        return "缺少 DEEPSEEK_API_KEY，跳过 live DeepSeek smoke"
    return None


def _deepseek_env(env: Mapping[str, str]) -> dict[str, str]:
    """构造 Slice 8C 裁决后的 DeepSeek env，不读取其它真实环境变量。"""

    return {
        _DEEPSEEK_API_KEY_ENV: env.get(_DEEPSEEK_API_KEY_ENV, ""),
        _DEEPSEEK_BASE_URL_ENV: env.get(_DEEPSEEK_BASE_URL_ENV, _DEFAULT_LIVE_BASE_URL),
        _DEEPSEEK_MODEL_ENV: env.get(_DEEPSEEK_MODEL_ENV, _DEFAULT_LIVE_MODEL),
    }


def _section_locator() -> Locator:
    """构造 section locator。"""

    return Locator(
        document_id=_DOCUMENT_ID,
        locator_kind=LocatorKind.SECTION,
        section_ref=_SECTION_REF,
        table_ref=None,
        page_no=1,
        page_range=(1, 1),
        internal_ref=None,
        internal_ref_available=False,
        bbox=None,
    )


def _table_locator() -> Locator:
    """构造 table locator。"""

    return Locator(
        document_id=_DOCUMENT_ID,
        locator_kind=LocatorKind.TABLE,
        section_ref=_SECTION_REF,
        table_ref=_TABLE_REF,
        page_no=1,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
        bbox=None,
    )


def _citation(locator: Locator) -> Citation:
    """构造安全 citation。"""

    return Citation(
        document_id=_DOCUMENT_ID,
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type="annual_report",
        locator=locator,
    )


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


def _latest_citations_from_request(request: DeepSeekChatRequest) -> tuple[Citation, ...]:
    """从 request prior_tool_results 中取最近 citation。"""

    user_message = request.payload["messages"][1]
    content = json.loads(user_message["content"])
    citations = content["prior_tool_results"][-1]["citations"]
    return tuple(_citation_from_payload(citation) for citation in citations)


def _safe_failure_message(failure: ToolFailure | None) -> str:
    """生成不含 secret 的失败断言信息。"""

    if failure is None:
        return ""
    return f"failure_code={failure.code.value}; message={failure.message}"
