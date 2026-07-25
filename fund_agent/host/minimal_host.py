"""最小 Host：托管 Agent loop，记录事件，支持 timeout。"""

from __future__ import annotations

import queue
import threading
import time
import weakref
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

from fund_agent.agent.stream_events import StreamEvent, StreamEventType
from fund_agent.agent.tool_loop import AgentRunResult, MinimalFundDocumentAgent


class HostRunEventType(str, Enum):
    """Host run 事件类型枚举。"""

    STARTED = "started"
    SEARCH = "search"
    READ_SECTION = "read_section"
    LIST_TABLES = "list_tables"
    READ_TABLE = "read_table"
    GET_EXCERPT = "get_excerpt"
    AGGREGATE = "aggregate"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True)
class HostRunEvent:
    """Host run 单个事件。

    参数:
        event_type: 事件类型枚举。
        timestamp: 事件发生时间（time.monotonic）。
        tool_name: 关联的工具名称（工具调用事件时非空）。
        result_kind: 工具调用结果类别（success / failure）。
        duration: 工具调用耗时（秒）。

    返回:
        不可变事件 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    event_type: HostRunEventType
    timestamp: float
    tool_name: str | None = None
    result_kind: str | None = None
    duration: float | None = None


@dataclass(frozen=True)
class HostRunResult:
    """Host run 扩展结果。

    参数:
        agent_result: Agent 的原始结果。
        duration: 整个 run 的耗时（秒）。
        events: 运行期间的事件列表。
        tool_trace_summary: 工具调用统计（total / success / failure）。
        timeout: 配置的 timeout 值（秒）；未配置时为 None。
        timed_out: 是否因 timeout 而终止。

    返回:
        不可变 Host run 结果 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    agent_result: AgentRunResult
    duration: float
    events: tuple[HostRunEvent, ...]
    tool_trace_summary: dict[str, int]
    timeout: float | None = None
    timed_out: bool = False
    failure_reason: str | None = None

    @property
    def answer(self) -> str:
        """代理 Agent 的 answer。"""
        return self.agent_result.answer

    @property
    def citations(self) -> tuple:
        """代理 Agent 的 citations。"""
        return self.agent_result.citations

    @property
    def tool_trace(self) -> tuple:
        """代理 Agent 的 tool_trace。"""
        return self.agent_result.tool_trace

    @property
    def failure(self) -> object:
        """代理 Agent 的 failure。"""
        return self.agent_result.failure


DEFAULT_TIMEOUT_SECONDS = 300.0


class MinimalHost:
    """支持生命周期管理的最小 Host。

    参数:
        agent: 已装配好工具服务的最小 Agent。
        timeout: run 超时时间（秒）；默认 300 秒。

    返回:
        托管 Agent loop 的 Host，记录事件并支持 timeout。

    异常:
        本 Host 不访问 PDF、Docling store 或基金领域数据。
    """

    def __init__(
        self,
        agent: MinimalFundDocumentAgent,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """初始化 Host。"""

        self._agent = agent
        self._timeout = timeout

    def run(self, *, document_id: str, query: str) -> HostRunResult:
        """调用 Agent loop 并返回扩展结果。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 由上层传入的检索关键词。

        返回:
            HostRunResult，包含 Agent 结果、耗时、事件和统计。

        异常:
            timeout 时返回 timed_out=True 的 HostRunResult。
        """

        events: list[HostRunEvent] = []
        start_time = time.monotonic()

        events.append(HostRunEvent(
            event_type=HostRunEventType.STARTED,
            timestamp=start_time,
        ))

        agent_result: AgentRunResult | None = None
        timed_out = False
        agent_error: str | None = None

        agent_ref = weakref.ref(self._agent)

        def _run_agent() -> None:
            nonlocal agent_result, agent_error
            agent = agent_ref()
            if agent is None:
                return
            try:
                agent_result = agent.run(
                    document_id=document_id,
                    query=query,
                )
            except Exception as exc:
                agent_error = f"{type(exc).__name__}: {exc}"

        thread = threading.Thread(target=_run_agent, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)

        if thread.is_alive():
            timed_out = True
            end_time = time.monotonic()
            events.append(HostRunEvent(
                event_type=HostRunEventType.FAILED,
                timestamp=end_time,
            ))
            return HostRunResult(
                agent_result=AgentRunResult(
                    answer="",
                    citations=(),
                    tool_trace=(),
                    failure=None,
                ),
                duration=end_time - start_time,
                events=tuple(events),
                tool_trace_summary={"total": 0, "success": 0, "failure": 0},
                timeout=self._timeout,
                timed_out=True,
            )

        end_time = time.monotonic()

        if agent_result is None:
            if agent_error:
                events.append(HostRunEvent(
                    event_type=HostRunEventType.ERROR,
                    timestamp=end_time,
                ))
            else:
                events.append(HostRunEvent(
                    event_type=HostRunEventType.FAILED,
                    timestamp=end_time,
                ))
            return HostRunResult(
                agent_result=AgentRunResult(
                    answer="",
                    citations=(),
                    tool_trace=(),
                    failure=None,
                ),
                duration=end_time - start_time,
                events=tuple(events),
                tool_trace_summary={"total": 0, "success": 0, "failure": 0},
                timeout=self._timeout,
                timed_out=False,
                failure_reason=agent_error,
            )

        for entry in agent_result.tool_trace:
            event_type = _tool_name_to_event_type(entry.tool_name)
            events.append(HostRunEvent(
                event_type=event_type,
                timestamp=end_time,
                tool_name=entry.tool_name if isinstance(entry.tool_name, str) else entry.tool_name.value,
                result_kind=entry.result_kind,
            ))

        if agent_result.failure is not None:
            events.append(HostRunEvent(
                event_type=HostRunEventType.FAILED,
                timestamp=end_time,
            ))
        else:
            events.append(HostRunEvent(
                event_type=HostRunEventType.COMPLETED,
                timestamp=end_time,
            ))

        tool_trace_summary = _compute_tool_trace_summary(agent_result)

        return HostRunResult(
            agent_result=agent_result,
            duration=end_time - start_time,
            events=tuple(events),
            tool_trace_summary=tool_trace_summary,
            timeout=self._timeout,
            timed_out=False,
        )

    def run_agent_stream(
        self, *, document_id: str, query: str
    ) -> Iterator[StreamEvent]:
        """运行 Agent 流式循环并转发 StreamEvent，支持 timeout。

        内部通过后台线程调用 agent.run_stream()，
        主线程从队列拉取事件，超时时产出 ERROR 并终止。
        """

        run_stream = getattr(self._agent, "run_stream", None)
        if run_stream is None:
            yield StreamEvent(
                type=StreamEventType.ERROR,
                payload={"code": "unavailable", "message": "Agent does not support streaming"},
            )
            return

        event_queue: queue.Queue[StreamEvent | None] = queue.Queue()
        agent_error: str | None = None

        def _run() -> None:
            nonlocal agent_error
            try:
                for event in run_stream(document_id=document_id, query=query):
                    event_queue.put(event)
            except Exception as exc:
                agent_error = f"{type(exc).__name__}: {exc}"
            finally:
                event_queue.put(None)  # sentinel

        start_time = time.monotonic()
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        seq = 0
        yield StreamEvent(
            type=StreamEventType.METADATA,
            payload={"host_started_at": start_time, "document_id": document_id, "query": query},
            sequence=seq,
        )
        seq += 1

        deadline = start_time + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    payload={"code": "unavailable", "message": "Host run timed out"},
                    sequence=seq,
                )
                return

            try:
                event = event_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue

            if event is None:
                break

            yield event

        if agent_error:
            yield StreamEvent(
                type=StreamEventType.ERROR,
                payload={"code": "unavailable", "message": agent_error},
                sequence=seq,
            )


_TOOL_NAME_MAP: dict[str, HostRunEventType] = {
    "search_document": HostRunEventType.SEARCH,
    "read_section": HostRunEventType.READ_SECTION,
    "list_tables": HostRunEventType.LIST_TABLES,
    "read_table": HostRunEventType.READ_TABLE,
    "get_excerpt": HostRunEventType.GET_EXCERPT,
    "aggregate_multi_year_annual_performance": HostRunEventType.AGGREGATE,
}


def _tool_name_to_event_type(tool_name: object) -> HostRunEventType:
    """把工具名称映射到事件类型。"""

    name_str = str(tool_name)
    return _TOOL_NAME_MAP.get(name_str, HostRunEventType.SEARCH)


def _compute_tool_trace_summary(agent_result: AgentRunResult) -> dict[str, int]:
    """计算工具调用统计。"""

    total = len(agent_result.tool_trace)
    success = sum(1 for entry in agent_result.tool_trace if entry.result_kind == "success")
    failure = total - success
    return {"total": total, "success": success, "failure": failure}
