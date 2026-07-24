"""Slice 19C MinimalHost.run_agent_stream() 测试。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from fund_agent.agent import (
    FakeLlmClient,
    FinalAnswer,
    LlmToolLoopRunner,
    StreamEvent,
    StreamEventType,
    ToolCall,
)
from fund_agent.fund.document_tools.constants import LocatorKind, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import Citation, Locator, ReportIdentity
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.host.minimal_host import MinimalHost

_DOCUMENT_ID = "004393-2024-annual_report-test19c1234567"


def _identity() -> ReportIdentity:
    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-import-id",
        content_fingerprint="abc123def4567890",
        document_id=_DOCUMENT_ID,
    )


def _write_docling_json(path: Path) -> None:
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
                "text": "基金经理张明负责本基金投资管理。",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service(tmp_path: Path) -> FundDocumentToolService:
    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
    _write_docling_json(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def _streaming_agent(tmp_path: Path) -> LlmToolLoopRunner:
    """创建带 FakeLlmClient 的 LlmToolLoopRunner，search → read_section → final answer。

    read_section 提供 SECTION 类型 citation，满足 _final_result 校验。
    """

    return LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=_DOCUMENT_ID,
                query="基金经理",
            ),
            lambda tr: ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=_DOCUMENT_ID,
                section_ref=tr[0].result[0].section_ref,
            ),
            lambda tr: FinalAnswer(
                answer="基金经理张明负责本基金投资管理。",
                citations=tr[1].citations,  # READ_SECTION citations (SECTION type)
                key_facts=("张明",),
            ),
        ]),
    )


# ── Tests ────────────────────────────────────────────────────────────


def test_run_agent_stream_forwards_content_delta_and_done(tmp_path: Path) -> None:
    """流式 Host 正确转发 CONTENT_DELTA 和 DONE 事件。"""

    agent = _streaming_agent(tmp_path)
    host = MinimalHost(agent)  # type: ignore[arg-type]

    events = list(host.run_agent_stream(document_id=_DOCUMENT_ID, query="基金经理"))

    event_types = [e.type for e in events]
    assert StreamEventType.METADATA in event_types  # Host-level metadata
    assert StreamEventType.CONTENT_DELTA in event_types
    assert StreamEventType.DONE in event_types
    assert StreamEventType.ERROR not in event_types


def test_run_agent_stream_forwards_tool_events(tmp_path: Path) -> None:
    """流式 Host 正确转发 TOOL_EVENT（call + result）。"""

    agent = _streaming_agent(tmp_path)
    host = MinimalHost(agent)  # type: ignore[arg-type]

    events = list(host.run_agent_stream(document_id=_DOCUMENT_ID, query="基金经理"))

    tool_events = [e for e in events if e.type == StreamEventType.TOOL_EVENT]
    assert len(tool_events) >= 2  # call + result
    assert any(e.payload.get("phase") == "call" for e in tool_events)
    assert any(e.payload.get("phase") == "result" for e in tool_events)
    assert any(e.type == StreamEventType.DONE for e in events)


def test_run_agent_stream_no_stream_method_yields_error(tmp_path: Path) -> None:
    """Agent 不支持 run_stream 时产出 ERROR 事件。"""

    from fund_agent.agent.tool_loop import MinimalFundDocumentAgent

    agent = MinimalFundDocumentAgent(_service(tmp_path))
    host = MinimalHost(agent)

    events = list(host.run_agent_stream(document_id=_DOCUMENT_ID, query="基金经理"))

    assert len(events) == 1
    assert events[0].type == StreamEventType.ERROR
    assert "does not support streaming" in events[0].payload["message"]


def test_run_agent_stream_timeout_yields_error() -> None:
    """超时时产出 ERROR 事件。"""

    class SlowAgent:
        def run_stream(self, *, document_id: str, query: str) -> Iterator[StreamEvent]:
            import time as _time

            _time.sleep(10)  # 远超 timeout
            yield StreamEvent(type=StreamEventType.DONE, payload=None)
            return

    host = MinimalHost(SlowAgent(), timeout=0.1)  # type: ignore[arg-type]

    events = list(host.run_agent_stream(document_id=_DOCUMENT_ID, query="基金经理"))

    error_events = [e for e in events if e.type == StreamEventType.ERROR]
    assert len(error_events) == 1
    assert "timed out" in error_events[0].payload["message"]


def test_run_agent_stream_done_has_null_payload(tmp_path: Path) -> None:
    """DONE 事件 payload 为 None。"""

    agent = _streaming_agent(tmp_path)
    host = MinimalHost(agent)  # type: ignore[arg-type]

    events = list(host.run_agent_stream(document_id=_DOCUMENT_ID, query="基金经理"))

    done_events = [e for e in events if e.type == StreamEventType.DONE]
    assert len(done_events) == 1
    assert done_events[0].payload is None


def test_run_agent_stream_preserves_host_run_backward_compat(tmp_path: Path) -> None:
    """现有的 run() 方法行为不变（向后兼容）。"""

    from fund_agent.agent.tool_loop import MinimalFundDocumentAgent

    agent = MinimalFundDocumentAgent(_service(tmp_path))
    host = MinimalHost(agent)

    result = host.run(document_id=_DOCUMENT_ID, query="基金经理")

    assert "张明" in result.answer
    assert len(result.citations) >= 1
    assert result.timed_out is False
    assert result.events[0].event_type.value == "started"
    assert result.events[-1].event_type.value in ("completed", "failed")
