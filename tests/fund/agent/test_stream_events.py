"""StreamEvent 数据模型测试。"""

from __future__ import annotations

from fund_agent.agent.stream_events import StreamEvent, StreamEventType


class TestStreamEventCreation:
    def test_all_event_types_exist(self):
        """验证全部 8 种事件类型已定义。"""
        expected = {
            "content_delta",
            "reasoning_delta",
            "tool_event",
            "metadata",
            "warning",
            "error",
            "done",
        }
        actual = {e.value for e in StreamEventType}
        assert actual == expected

    def test_content_delta_event(self):
        event = StreamEvent(type=StreamEventType.CONTENT_DELTA, payload="Hello", sequence=1)
        assert event.type == StreamEventType.CONTENT_DELTA
        assert event.payload == "Hello"
        assert event.sequence == 1

    def test_tool_event(self):
        payload = {"phase": "call", "tool_name": "search_document"}
        event = StreamEvent(type=StreamEventType.TOOL_EVENT, payload=payload, sequence=2)
        assert event.type == StreamEventType.TOOL_EVENT
        assert event.payload == payload
        assert event.sequence == 2

    def test_metadata_event(self):
        payload = {"document_id": "test-001", "query": "test query"}
        event = StreamEvent(type=StreamEventType.METADATA, payload=payload, sequence=0)
        assert event.type == StreamEventType.METADATA
        assert event.payload["document_id"] == "test-001"

    def test_error_event(self):
        payload = {"code": "unavailable", "message": "test error"}
        event = StreamEvent(type=StreamEventType.ERROR, payload=payload, sequence=5)
        assert event.type == StreamEventType.ERROR
        assert event.payload["code"] == "unavailable"

    def test_done_event(self):
        event = StreamEvent(type=StreamEventType.DONE, payload=None, sequence=10)
        assert event.type == StreamEventType.DONE
        assert event.payload is None

    def test_warning_event(self):
        event = StreamEvent(type=StreamEventType.WARNING, payload="warning msg", sequence=3)
        assert event.type == StreamEventType.WARNING

    def test_reasoning_delta_event(self):
        event = StreamEvent(type=StreamEventType.REASONING_DELTA, payload="thinking...", sequence=1)
        assert event.type == StreamEventType.REASONING_DELTA

    def test_default_sequence_is_zero(self):
        event = StreamEvent(type=StreamEventType.DONE, payload=None)
        assert event.sequence == 0
