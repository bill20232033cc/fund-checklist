"""DeepSeek OpenAI-compatible LLM adapter。"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from fund_agent.agent.llm_tool_loop import FinalAnswer, LlmClientFailure, ToolCall, ToolResult
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.models import Citation, Locator

DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL_ENV = "DEEPSEEK_BASE_URL"
DEEPSEEK_MODEL_ENV = "DEEPSEEK_MODEL"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_TIMEOUT_SECONDS = 30
_CHAT_COMPLETIONS_PATH = "/chat/completions"
_JSON_CONTENT_TYPE = "application/json"
_UNAVAILABLE_MESSAGE = "DeepSeek LLM provider 暂不可用"
_MALFORMED_MESSAGE = "DeepSeek LLM provider response 不符合受控结构"
_SYSTEM_PROMPT = (
    "你只能通过提供的基金年报 reading tools 取证。"
    "需要调用工具时使用 tool call。"
    "最终回答必须返回 JSON: "
    '{"answer": string, "citations": Citation[], "key_facts": string[]}。'
    "不得请求 repository/private loader、raw PDF、raw Docling JSON、本地路径、cache path、"
    "local_import_id、URL secret 或 parser private payload。"
)


@dataclass(frozen=True)
class DeepSeekChatRequest:
    """DeepSeek chat completions 传输请求。

    参数:
        url: chat completions endpoint；由 base URL 规范化后拼接。
        headers: HTTP headers，包含 Authorization 与 Content-Type。
        payload: OpenAI-compatible chat completions JSON payload。
        timeout_seconds: 单次 provider 请求超时。

    返回:
        传给 transport 的不可变请求对象。

    异常:
        本模型不抛出业务异常。
    """

    url: str
    headers: Mapping[str, str]
    payload: Mapping[str, Any]
    timeout_seconds: int


@dataclass(frozen=True)
class DeepSeekChatResponse:
    """DeepSeek chat completions 传输响应。

    参数:
        status_code: HTTP status code。
        body: provider response body 字符串；只在 adapter 内解析，不进入 public output。

    返回:
        传输层响应对象。

    异常:
        本模型不抛出业务异常。
    """

    status_code: int
    body: str


class DeepSeekTransportUnavailable(Exception):
    """传输层不可用错误。

    参数:
        message: 安全错误信息；不得包含 API key、raw body、URL secret 或本地路径。

    返回:
        可被 adapter 映射为 unavailable 的异常。

    异常:
        构造时不抛出业务异常。
    """


class DeepSeekTransportProtocol(Protocol):
    """DeepSeek adapter 使用的可注入 transport 协议。

    参数:
        request: 已组装的 chat completions 请求。

    返回:
        HTTP status 与 body。

    异常:
        auth、network、timeout、rate limit 或服务不可用时抛 DeepSeekTransportUnavailable。
    """

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        """发送一次 chat completions 请求。"""


class UrlLibDeepSeekTransport:
    """基于标准库 urllib 的默认 DeepSeek transport。

    参数:
        无。

    返回:
        可注入 DeepSeekLlmClient 的 transport。

    异常:
        send 会把 HTTP/network/timeout 错误收敛为 DeepSeekTransportUnavailable。
    """

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        """用 urllib 发送请求并返回 status/body。"""

        body = json.dumps(request.payload, ensure_ascii=False).encode("utf-8")
        urllib_request = urllib.request.Request(
            request.url,
            data=body,
            headers=dict(request.headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(urllib_request, timeout=request.timeout_seconds) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return DeepSeekChatResponse(status_code=response.status, body=response_body)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise DeepSeekTransportUnavailable(_UNAVAILABLE_MESSAGE) from exc


class DeepSeekLlmClient:
    """DeepSeek-only LlmClientProtocol adapter。

    参数:
        transport: 可注入传输层；默认使用 urllib，单元测试应注入 fake transport。
        env: 环境变量映射；默认读取 os.environ，测试可传显式 mapping 避免读取真实 key。
        timeout_seconds: 单次 provider 请求超时。

    返回:
        实现 LlmClientProtocol 的 DeepSeek adapter。

    异常:
        next_step 会把 provider 不可用映射为 LlmClientFailure(unavailable)，
        把 malformed response 映射为 LlmClientFailure(llm_malformed_response)。
    """

    def __init__(
        self,
        *,
        transport: DeepSeekTransportProtocol | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int = DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
    ) -> None:
        """保存 transport、环境变量来源和超时设置。"""

        self._transport = transport or UrlLibDeepSeekTransport()
        self._env = env
        self._timeout_seconds = timeout_seconds

    def next_step(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: tuple[ToolResult, ...],
    ) -> ToolCall | FinalAnswer:
        """调用 DeepSeek 并解析为受控 ToolCall 或 FinalAnswer。"""

        env = self._env if self._env is not None else os.environ
        api_key = env.get(DEEPSEEK_API_KEY_ENV, "").strip()
        if not api_key:
            raise LlmClientFailure(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)

        request = DeepSeekChatRequest(
            url=_chat_completions_url(env.get(DEEPSEEK_BASE_URL_ENV, DEFAULT_DEEPSEEK_BASE_URL)),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": _JSON_CONTENT_TYPE,
            },
            payload=_request_payload(
                document_id=document_id,
                query=query,
                tool_results=tool_results,
                model=env.get(DEEPSEEK_MODEL_ENV, DEFAULT_DEEPSEEK_MODEL).strip() or DEFAULT_DEEPSEEK_MODEL,
            ),
            timeout_seconds=self._timeout_seconds,
        )
        try:
            response = self._transport.send(request)
        except DeepSeekTransportUnavailable as exc:
            raise LlmClientFailure(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise LlmClientFailure(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)
        return _parse_response(response.body)

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
    ) -> str:
        """直接调用 LLM 生成文本，不走 tool-loop。

        参数:
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            temperature: 生成温度。

        返回:
            LLM 生成的文本内容。

        异常:
            provider 不可用时抛 LlmClientFailure(unavailable)。
            response 不可解析时抛 LlmClientFailure(llm_malformed_response)。
        """

        env = self._env if self._env is not None else os.environ
        api_key = env.get(DEEPSEEK_API_KEY_ENV, "").strip()
        if not api_key:
            raise LlmClientFailure(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)

        request = DeepSeekChatRequest(
            url=_chat_completions_url(env.get(DEEPSEEK_BASE_URL_ENV, DEFAULT_DEEPSEEK_BASE_URL)),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": _JSON_CONTENT_TYPE,
            },
            payload={
                "model": env.get(DEEPSEEK_MODEL_ENV, DEFAULT_DEEPSEEK_MODEL).strip() or DEFAULT_DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "stream": False,
            },
            timeout_seconds=self._timeout_seconds,
        )
        try:
            response = self._transport.send(request)
        except DeepSeekTransportUnavailable as exc:
            raise LlmClientFailure(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise LlmClientFailure(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)
        return _parse_text_content(response.body)


def _chat_completions_url(base_url: str) -> str:
    """规范化 base URL 并拼接 chat completions endpoint。"""

    normalized = (base_url or DEFAULT_DEEPSEEK_BASE_URL).strip() or DEFAULT_DEEPSEEK_BASE_URL
    split = urlsplit(normalized)
    path = split.path.rstrip("/") + _CHAT_COMPLETIONS_PATH
    return urlunsplit((split.scheme, split.netloc, path, "", ""))


def _request_payload(
    *,
    document_id: str,
    query: str,
    tool_results: tuple[ToolResult, ...],
    model: str,
) -> dict[str, Any]:
    """构造不含 raw/private payload 的 OpenAI-compatible chat completions payload。"""

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "document_id": document_id,
                        "query": query,
                        "prior_tool_results": [_safe_tool_result(result) for result in tool_results],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "tools": _tool_schemas(),
        "tool_choice": "auto",
        "temperature": 0,
        "stream": False,
    }


def _safe_tool_result(result: ToolResult) -> dict[str, Any]:
    """序列化受控工具结果，只给 provider evidence_text 与 public citations。"""

    return {
        "tool_name": result.tool_name.value,
        "evidence_text": result.evidence_text,
        "citations": [_safe_citation(citation) for citation in result.citations],
    }


def _tool_schemas() -> list[dict[str, Any]]:
    """返回 DeepSeek 可见的受控 reading tool schema。"""

    return [
        _tool_schema(
            ToolName.SEARCH_DOCUMENT,
            {
                "document_id": {"type": "string"},
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            ("document_id", "query"),
        ),
        _tool_schema(
            ToolName.READ_SECTION,
            {
                "document_id": {"type": "string"},
                "section_ref": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            ("document_id", "section_ref"),
        ),
        _tool_schema(
            ToolName.LIST_TABLES,
            {
                "document_id": {"type": "string"},
                "section_ref": {"type": "string"},
            },
            ("document_id",),
        ),
        _tool_schema(
            ToolName.READ_TABLE,
            {
                "document_id": {"type": "string"},
                "table_ref": {"type": "string"},
                "max_rows": {"type": "integer"},
            },
            ("document_id", "table_ref"),
        ),
        _tool_schema(
            ToolName.GET_EXCERPT,
            {
                "document_id": {"type": "string"},
                "locator": {"type": "object"},
                "max_chars": {"type": "integer"},
            },
            ("document_id", "locator"),
        ),
    ]


def _tool_schema(tool_name: ToolName, properties: dict[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    """构造单个 OpenAI-compatible function tool schema。"""

    return {
        "type": "function",
        "function": {
            "name": tool_name.value,
            "description": f"受控基金年报 reading tool: {tool_name.value}",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


def _parse_response(body: str) -> ToolCall | FinalAnswer:
    """解析 provider response body 为受控 ToolCall 或 FinalAnswer。"""

    try:
        payload = json.loads(body)
        message = payload["choices"][0]["message"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE) from exc

    if not isinstance(message, dict):
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE)
    tool_calls = message.get("tool_calls")
    if tool_calls:
        return _parse_tool_call(tool_calls)
    return _parse_final_answer(message.get("content"))


def _parse_tool_call(tool_calls: Any) -> ToolCall:
    """解析 OpenAI-compatible tool_calls 中的第一个 tool call。"""

    try:
        first_call = tool_calls[0]
        function = first_call["function"]
        tool_name = function["name"]
        arguments = _parse_arguments(function["arguments"])
        document_id = _required_str(arguments, "document_id")
        return ToolCall(
            tool_name=_tool_name_or_raw(tool_name),
            document_id=document_id,
            query=_optional_str(arguments, "query"),
            section_ref=_optional_str(arguments, "section_ref"),
            table_ref=_optional_str(arguments, "table_ref"),
            locator=_optional_locator(arguments.get("locator")),
            max_results=_optional_int(arguments, "max_results"),
            max_chars=_optional_int(arguments, "max_chars"),
            max_rows=_optional_int(arguments, "max_rows"),
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE) from exc


def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
    """解析 tool call arguments，要求为 JSON object。"""

    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("tool arguments malformed") from exc
    elif isinstance(raw_arguments, dict):
        parsed = raw_arguments
    else:
        raise ValueError("tool arguments malformed")
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be object")
    return parsed


def _parse_final_answer(content: Any) -> FinalAnswer:
    """解析 message.content 中的 final answer JSON。"""

    if not isinstance(content, str) or not content.strip():
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE)
    try:
        payload = json.loads(content)
        answer = _required_str(payload, "answer")
        citations = tuple(_citation_from_dict(item) for item in _required_list(payload, "citations"))
        key_facts = tuple(str(item) for item in _required_list(payload, "key_facts"))
    except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE) from exc
    return FinalAnswer(answer=answer, citations=citations, key_facts=key_facts)


def _citation_from_dict(payload: Any) -> Citation:
    """从 provider final answer JSON 还原 Citation。"""

    if not isinstance(payload, dict):
        raise ValueError("citation must be object")
    return Citation(
        document_id=_required_str(payload, "document_id"),
        fund_code=_required_str(payload, "fund_code"),
        fund_name=_required_str(payload, "fund_name"),
        year=_required_int(payload, "year"),
        report_type=_required_str(payload, "report_type"),
        locator=_locator_from_dict(payload.get("locator")),
    )


def _optional_locator(payload: Any) -> Locator | None:
    """解析可选 locator object。"""

    if payload is None:
        return None
    return _locator_from_dict(payload)


def _locator_from_dict(payload: Any) -> Locator:
    """从 JSON object 还原 Locator。"""

    if not isinstance(payload, dict):
        raise ValueError("locator must be object")
    return Locator(
        document_id=_required_str(payload, "document_id"),
        locator_kind=LocatorKind(_required_str(payload, "locator_kind")),
        section_ref=_optional_str(payload, "section_ref"),
        table_ref=_optional_str(payload, "table_ref"),
        page_no=_optional_int(payload, "page_no"),
        page_range=_optional_page_range(payload.get("page_range")),
        internal_ref=None,
        internal_ref_available=False,
        bbox=None,
    )


def _optional_page_range(value: Any) -> tuple[int, int] | None:
    """解析可选 page_range。"""

    if value is None:
        return None
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], int)
    ):
        return (value[0], value[1])
    raise ValueError("page_range must be [int, int]")


def _safe_citation(citation: Citation) -> dict[str, Any]:
    """把 Citation 转为不含 parser internal_ref/bbox 的 public JSON。"""

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


def _tool_name_or_raw(value: Any) -> ToolName | str:
    """把已知工具名转为 ToolName，未知工具保留原字符串交给 runner fail-closed。"""

    raw = str(value)
    try:
        return ToolName(raw)
    except ValueError:
        return raw


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    """读取必填字符串字段。"""

    value = payload[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty string")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    """读取可选字符串字段。"""

    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be string")
    return value


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    """读取必填整数字段。"""

    value = payload[key]
    if not isinstance(value, int):
        raise ValueError(f"{key} must be int")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    """读取可选整数字段。"""

    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{key} must be int")
    return value


def _required_list(payload: Mapping[str, Any], key: str) -> list[Any]:
    """读取必填 list 字段。"""

    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be list")
    return value


def _parse_text_content(body: str) -> str:
    """从 chat completions response 提取纯文本内容。"""

    try:
        payload = json.loads(body)
        content = payload["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE) from exc
    if not isinstance(content, str) or not content.strip():
        raise LlmClientFailure(FailureCode.LLM_MALFORMED_RESPONSE, _MALFORMED_MESSAGE)
    return content
