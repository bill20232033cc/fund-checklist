"""Production readiness 测试：tool schema 一致、重试、截断、投资建议拦截。"""

from __future__ import annotations

import json
from pathlib import Path

from fund_agent.agent import (
    ALLOWED_LLM_TOOL_NAMES,
    DeepSeekLlmClient,
    FinalAnswer,
    LlmToolLoopRunner,
    ToolCall,
    ToolResult,
)
from fund_agent.agent.deepseek_llm import (
    DeepSeekChatRequest,
    DeepSeekChatResponse,
    DeepSeekTransportUnavailable,
    _tool_schemas,
)
from fund_agent.agent.llm_tool_loop import (
    _final_result,
    _truncate_evidence,
)
from fund_agent.agent.stream_events import StreamEventType
from fund_agent.agent.tool_loop import ToolTraceEntry
from fund_agent.fund.document_tools.constants import (
    FailureCode,
    LocatorKind,
    ReportType,
    SourceKind,
    ToolName,
)
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import (
    Citation,
    Locator,
    ReportIdentity,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService


# ── helpers ──────────────────────────────────────────────────────────

def _identity(document_id: str = "test-doc") -> ReportIdentity:
    return ReportIdentity(
        fund_code="000001",
        fund_name="测试基金",
        year=2025,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-test-import",
        content_fingerprint="abc123",
        document_id=document_id,
    )


def _make_citation(document_id: str = "test-doc") -> Citation:
    return Citation(
        document_id=document_id,
        fund_code="000001",
        fund_name="测试基金",
        year=2025,
        report_type="annual_report",
        locator=Locator(
            document_id=document_id,
            locator_kind=LocatorKind.SECTION,
            section_ref="section-0001",
            table_ref=None,
            page_no=1,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        ),
    )


def _make_tool_result(
    tool_name: ToolName = ToolName.SEARCH_DOCUMENT,
    evidence_text: str = "test evidence",
    citations: tuple[Citation, ...] | None = None,
) -> ToolResult:
    if citations is None:
        citations = (_make_citation(),)
    return ToolResult(
        tool_name=tool_name,
        result=(),
        citations=citations,
        evidence_text=evidence_text,
    )


def _make_trace_entry() -> ToolTraceEntry:
    return ToolTraceEntry(
        tool_name=ToolName.SEARCH_DOCUMENT,
        arguments={"document_id": "test-doc", "query": "test"},
        result_kind="success",
        failure_code=None,
    )


# ── tool schema consistency ──────────────────────────────────────────

class TestToolSchemaConsistency:
    def test_all_allowed_tools_have_schemas(self):
        """ALLOWED_LLM_TOOL_NAMES 中的 6 个工具在 _tool_schemas() 中都有对应 schema。"""
        schemas = _tool_schemas()
        schema_names = {s["function"]["name"] for s in schemas}
        allowed_names = {t.value for t in ALLOWED_LLM_TOOL_NAMES}
        missing = allowed_names - schema_names
        assert not missing, f"Missing schemas: {missing}"

    def test_no_extra_schemas_beyond_allowed(self):
        """_tool_schemas() 不暴露 ALLOWED_LLM_TOOL_NAMES 之外的工具。"""
        schemas = _tool_schemas()
        schema_names = {s["function"]["name"] for s in schemas}
        allowed_names = {t.value for t in ALLOWED_LLM_TOOL_NAMES}
        extra = schema_names - allowed_names
        assert not extra, f"Extra schemas: {extra}"

    def test_aggregate_schema_has_required_params(self):
        """aggregate_multi_year_annual_performance schema 包含 fund_code / requested_years / annual_report_documents。"""
        schemas = _tool_schemas()
        agg = next(
            s for s in schemas
            if s["function"]["name"] == ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE.value
        )
        required = set(agg["function"]["parameters"]["required"])
        assert "fund_code" in required
        assert "requested_years" in required
        assert "annual_report_documents" in required
        props = agg["function"]["parameters"]["properties"]
        assert "share_class" in props
        assert "fund_code" in props


# ── next_step retry ──────────────────────────────────────────────────

class _FailingThenSuccessTransport:
    """前 N 次抛出异常，第 N+1 次返回成功。"""

    def __init__(self, fail_count: int, status_code: int = 503) -> None:
        self.fail_count = fail_count
        self.status_code = status_code
        self.calls = 0

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        self.calls += 1
        if self.calls <= self.fail_count:
            raise DeepSeekTransportUnavailable("transient", status_code=self.status_code)
        return DeepSeekChatResponse(
            status_code=200,
            body=json.dumps({
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "function": {
                                "name": "search_document",
                                "arguments": json.dumps({"document_id": "test-doc", "query": "test"}),
                            }
                        }]
                    }
                }]
            }),
        )


class _AuthErrorTransport:
    """始终返回 401。"""

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        return DeepSeekChatResponse(status_code=401, body="")


class _AlwaysFailTransport:
    """始终抛异常。"""

    def send(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        raise DeepSeekTransportUnavailable("down", status_code=503)


class TestNextStepRetry:
    def test_retries_on_transient_failure(self):
        """前 2 次失败（503），第 3 次成功 → 3 次调用。"""
        transport = _FailingThenSuccessTransport(fail_count=2, status_code=503)
        client = DeepSeekLlmClient(
            transport=transport,
            env={"DEEPSEEK_API_KEY": "fake-key"},
            timeout_seconds=5,
        )
        result = client.next_step(document_id="test-doc", query="test", tool_results=())
        assert isinstance(result, ToolCall)
        assert transport.calls == 3

    def test_no_retry_on_auth_error_transport_exception(self):
        """transport 抛出 status_code=401 的异常 → 不重试，立即 fail。"""
        class AuthExceptionTransport:
            def send(self, request):
                raise DeepSeekTransportUnavailable("unauthorized", status_code=401)

        client = DeepSeekLlmClient(
            transport=AuthExceptionTransport(),
            env={"DEEPSEEK_API_KEY": "fake-key"},
            timeout_seconds=5,
        )
        try:
            client.next_step(document_id="test-doc", query="test", tool_results=())
        except Exception as exc:
            assert "暂不可用" in str(exc)
        else:
            raise AssertionError("expected LlmClientFailure")

    def test_no_retry_on_auth_error_http_response(self):
        """HTTP 401 响应 → 不重试，立即 fail。"""
        client = DeepSeekLlmClient(
            transport=_AuthErrorTransport(),
            env={"DEEPSEEK_API_KEY": "fake-key"},
            timeout_seconds=5,
        )
        try:
            client.next_step(document_id="test-doc", query="test", tool_results=())
        except Exception as exc:
            assert "暂不可用" in str(exc)
        else:
            raise AssertionError("expected LlmClientFailure")

    def test_retry_exhausted(self):
        """3 次全部失败 → 最终抛出 LlmClientFailure。"""
        transport = _AlwaysFailTransport()
        client = DeepSeekLlmClient(
            transport=transport,
            env={"DEEPSEEK_API_KEY": "fake-key"},
            timeout_seconds=5,
        )
        try:
            client.next_step(document_id="test-doc", query="test", tool_results=())
        except Exception as exc:
            assert "暂不可用" in str(exc)
        else:
            raise AssertionError("expected LlmClientFailure")


# ── evidence truncation ──────────────────────────────────────────────

class TestEvidenceTruncation:
    def test_short_text_not_truncated(self):
        text = "short evidence"
        result = _truncate_evidence(text)
        assert result == text

    def test_exactly_max_chars_not_truncated(self):
        text = "x" * 4096
        result = _truncate_evidence(text)
        assert result == text
        assert len(result) == 4096

    def test_long_text_truncated(self):
        text = "A" * 4000 + "B" * 4000  # 8000 chars
        result = _truncate_evidence(text)
        assert len(result) <= 4150  # 4096 + marker overhead
        assert "[...已截断" in result
        assert result.startswith("A" * 3072)
        assert result.rstrip().endswith("B" * 1024)

    def test_truncation_marker_mentions_skipped_count(self):
        text = "X" * 3072 + "MIDDLE" * 1000 + "Y" * 1024
        result = _truncate_evidence(text)
        assert "已截断" in result
        assert "字符" in result

    def test_tool_result_truncation_applied(self):
        """通过 _tool_result_from_output 产生的 evidence_text 被截断。"""
        from fund_agent.agent.llm_tool_loop import _tool_result_from_output
        from fund_agent.fund.document_tools.models import SectionContent

        long_title = "T" * 100
        long_text = "X" * 5000
        cit = _make_citation()
        content = SectionContent(
            section_ref="section-0001",
            title=long_title,
            text=long_text,
            truncated=False,
            locator=cit.locator,
            citation=cit,
        )
        result = _tool_result_from_output(ToolName.READ_SECTION, content)
        assert len(result.evidence_text) < 5000
        assert "已截断" in result.evidence_text or len(result.evidence_text) <= 4096


# ── investment advice detection ──────────────────────────────────────

class TestInvestmentAdviceBlocked:
    def test_buy_keyword_blocked(self):
        answer = "建议买入该基金，预计有较好表现。"
        final = FinalAnswer(
            answer=answer,
            citations=(_make_citation(),),
            key_facts=("建议买入",),
        )
        tool_result = _make_tool_result(evidence_text="建议买入")
        result = _final_result(final, (tool_result,), (_make_trace_entry(),))
        assert result.failure is not None
        assert "投资建议" in result.failure.message

    def test_sell_keyword_blocked(self):
        answer = "建议卖出该基金。"
        final = FinalAnswer(
            answer=answer,
            citations=(_make_citation(),),
            key_facts=("建议卖出",),
        )
        tool_result = _make_tool_result(evidence_text="建议卖出")
        result = _final_result(final, (tool_result,), (_make_trace_entry(),))
        assert result.failure is not None
        assert "投资建议" in result.failure.message

    def test_suggest_add_position_blocked(self):
        answer = "建议加仓该基金。"
        final = FinalAnswer(
            answer=answer,
            citations=(_make_citation(),),
            key_facts=("建议加仓",),
        )
        tool_result = _make_tool_result(evidence_text="建议加仓")
        result = _final_result(final, (tool_result,), (_make_trace_entry(),))
        assert result.failure is not None

    def test_strongly_recommend_blocked(self):
        answer = "强烈建议买入该基金。"
        final = FinalAnswer(
            answer=answer,
            citations=(_make_citation(),),
            key_facts=("强烈建议",),
        )
        tool_result = _make_tool_result(evidence_text="强烈建议")
        result = _final_result(final, (tool_result,), (_make_trace_entry(),))
        assert result.failure is not None

    def test_safe_phrase_not_blocked(self):
        """建议关注 不触发投资建议拦截。"""
        answer = "建议关注该基金的费率水平和业绩表现。"
        final = FinalAnswer(
            answer=answer,
            citations=(_make_citation(),),
            key_facts=("建议关注",),
        )
        tool_result = _make_tool_result(evidence_text="建议关注")
        result = _final_result(final, (tool_result,), (_make_trace_entry(),))
        assert result.failure is None
        assert result.answer == answer

    def test_track_phrase_not_blocked(self):
        """需持续跟踪 不触发投资建议拦截。"""
        answer = "需持续跟踪该基金的规模变化。"
        final = FinalAnswer(
            answer=answer,
            citations=(_make_citation(),),
            key_facts=("需持续跟踪",),
        )
        tool_result = _make_tool_result(evidence_text="需持续跟踪")
        result = _final_result(final, (tool_result,), (_make_trace_entry(),))
        assert result.failure is None


# ── StreamEvent integration ──────────────────────────────────────────

class _ThreeStepFakeClient:
    """search → read_section → final answer 的 fake LLM client。"""

    def __init__(self):
        self._step = 0

    def next_step(self, *, document_id, query, tool_results):
        if self._step == 0:
            self._step = 1
            return ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=document_id,
                query="基金经理",
            )
        if self._step == 1:
            self._step = 2
            # 从搜索结果中取第一个 section_ref
            search_results = tool_results[-1].result
            section_ref = search_results[0].citation.locator.section_ref
            return ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=document_id,
                section_ref=section_ref,
            )
        # 从 read_section 结果取 citation
        section_citation = tool_results[-1].citations[0]
        return FinalAnswer(
            answer="该基金的基金经理是张明。",
            citations=(section_citation,),
            key_facts=("张明",),
        )


class TestRunStream:
    def test_stream_produces_events(self):
        """run_stream 产出 METADATA / TOOL_EVENT / CONTENT_DELTA / DONE 事件。"""
        store = _make_docling_store("test-doc")
        tool_service = FundDocumentToolService({"test-doc": store})
        client = _ThreeStepFakeClient()
        runner = LlmToolLoopRunner(tool_service=tool_service, llm_client=client)

        events = list(runner.run_stream(document_id="test-doc", query="基金经理是谁？"))

        event_types = [e.type for e in events]
        assert StreamEventType.METADATA in event_types
        assert StreamEventType.TOOL_EVENT in event_types
        assert StreamEventType.CONTENT_DELTA in event_types
        assert StreamEventType.DONE in event_types

    def test_stream_final_answer_in_content_delta(self):
        """最终回答在 CONTENT_DELTA 中。"""
        store = _make_docling_store("test-doc")
        tool_service = FundDocumentToolService({"test-doc": store})
        client = _ThreeStepFakeClient()
        runner = LlmToolLoopRunner(tool_service=tool_service, llm_client=client)

        events = list(runner.run_stream(document_id="test-doc", query="基金经理是谁？"))
        content_events = [e for e in events if e.type == StreamEventType.CONTENT_DELTA]
        assert len(content_events) == 1
        assert "张明" in content_events[0].payload

    def test_stream_done_has_null_payload(self):
        """DONE 事件 payload 为 None。"""
        store = _make_docling_store("test-doc")
        tool_service = FundDocumentToolService({"test-doc": store})
        client = _ThreeStepFakeClient()
        runner = LlmToolLoopRunner(tool_service=tool_service, llm_client=client)

        events = list(runner.run_stream(document_id="test-doc", query="test"))
        done_events = [e for e in events if e.type == StreamEventType.DONE]
        assert len(done_events) == 1
        assert done_events[0].payload is None

    def test_stream_error_on_investment_advice(self):
        """投资建议关键词 → ERROR 事件而非 DONE。"""
        store = _make_docling_store("test-doc")
        tool_service = FundDocumentToolService({"test-doc": store})

        class AdviceClient:
            def next_step(self, *, document_id, query, tool_results):
                return FinalAnswer(
                    answer="建议买入该基金。",
                    citations=(_make_citation(document_id),),
                    key_facts=("建议买入",),
                )

        runner = LlmToolLoopRunner(tool_service=tool_service, llm_client=AdviceClient())
        events = list(runner.run_stream(document_id="test-doc", query="test"))

        error_events = [e for e in events if e.type == StreamEventType.ERROR]
        assert len(error_events) >= 1
        assert "投资建议" in error_events[0].payload["message"]
        done_events = [e for e in events if e.type == StreamEventType.DONE]
        assert len(done_events) == 0

    def test_stream_sequences_increment(self):
        """sequence 逐事件递增。"""
        store = _make_docling_store("test-doc")
        tool_service = FundDocumentToolService({"test-doc": store})
        client = _ThreeStepFakeClient()
        runner = LlmToolLoopRunner(tool_service=tool_service, llm_client=client)

        events = list(runner.run_stream(document_id="test-doc", query="test"))
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # no duplicates on seq


# ── store helper ─────────────────────────────────────────────────────

def _make_docling_store(document_id: str = "test-doc") -> DoclingDocumentStore:
    """构造包含可搜索内容的 DoclingDocumentStore。"""
    import tempfile
    tmp = tempfile.mkdtemp()
    json_path = Path(tmp) / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
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
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return DoclingDocumentStore(identity=_identity(document_id), json_path=json_path)
