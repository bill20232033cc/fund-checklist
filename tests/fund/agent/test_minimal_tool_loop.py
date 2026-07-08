"""Minimal Host/Agent tool loop 的 Slice 4 测试。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fund_agent.agent import MinimalFundDocumentAgent
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import (
    Citation,
    Locator,
    ReportIdentity,
    SearchMatchKind,
    SearchResult,
    SectionContent,
    TableContent,
    TableSummary,
    ToolFailure,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.host import HostRunEventType, HostRunResult, MinimalHost


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
        document_id="004393-2024-annual_report-abc123def4567890",
    )


def _write_docling_json(path: Path) -> None:
    """写入含章节和表格的 Docling-shaped JSON，用于 Agent loop 行为测试。"""

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
                "text": "基金经理在本报告期内保持稳定。本章节用于检索基金经理信息，具体人员信息见表格。",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "7.4.7.11 前十大持仓",
                "level": 1,
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "前十大持仓信息见下表。",
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/4",
                "label": "section_header",
                "text": "8.1 风险提示",
                "level": 1,
                "prov": [{"page_no": 5}],
            },
            {
                "self_ref": "#/texts/5",
                "label": "text",
                "text": "风险提示章节只包含文字说明，不依赖表格。",
                "prov": [{"page_no": 5}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1, "bbox": {"l": 10, "t": 20, "r": 30, "b": 40}}],
                "captions": [],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "姓名",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "职务",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 2,
                            "end_col_offset_idx": 3,
                            "text": "任职日期",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "张明",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "本基金的基金经理",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 2,
                            "end_col_offset_idx": 3,
                            "text": "2022年8月8日",
                        },
                    ]
                },
            },
            {
                "self_ref": "#/tables/1",
                "label": "table",
                "prov": [{"page_no": 2, "bbox": {"l": 11, "t": 21, "r": 31, "b": 41}}],
                "captions": [{"text": "股票投资明细"}],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "证券名称",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "市值",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "贵州茅台",
                        },
                        {
                            "start_row_offset_idx": 1,
                            "end_row_offset_idx": 2,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "1000",
                        },
                    ]
                },
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service(tmp_path: Path) -> FundDocumentToolService:
    """复用 FundDocumentToolService + DoclingDocumentStore fixture，不跑真实 conversion。"""

    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir()
    _write_docling_json(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def _section_locator(section_ref: str = "section-scripted") -> Locator:
    """构造 fake service 使用的章节 locator。"""

    return Locator(
        document_id=_identity().document_id,
        locator_kind=LocatorKind.SECTION,
        section_ref=section_ref,
        table_ref=None,
        page_no=1,
        page_range=(1, 1),
        internal_ref=None,
        internal_ref_available=False,
    )


def _table_locator(table_ref: str = "table-scripted") -> Locator:
    """构造 fake service 使用的表格 locator。"""

    return Locator(
        document_id=_identity().document_id,
        locator_kind=LocatorKind.TABLE,
        section_ref="section-scripted",
        table_ref=table_ref,
        page_no=1,
        page_range=None,
        internal_ref=None,
        internal_ref_available=False,
    )


def _citation(locator: Locator) -> Citation:
    """构造 fake service 使用的 citation。"""

    identity = _identity()
    return Citation(
        document_id=identity.document_id,
        fund_code=identity.fund_code,
        fund_name=identity.fund_name,
        year=identity.year,
        report_type=identity.report_type.value,
        locator=locator,
    )


class _ScriptedTableHitService:
    """返回指定 first hit 的 fake tool service，用于 Agent 分支测试。

    参数:
        hit: search_document 返回的 first hit。

    返回:
        只实现 MinimalFundDocumentAgent 所需方法的 fake service。

    异常:
        public 方法不抛异常；不匹配输入返回 ToolFailure。
    """

    def __init__(self, hit: SearchResult) -> None:
        """保存 scripted first hit。"""

        self._hit = hit

    def search_document(self, document_id: str, query: str) -> tuple[SearchResult, ...] | ToolFailure:
        """返回 scripted search hit。"""

        if document_id != _identity().document_id or not query:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="文档不存在")
        return (self._hit,)

    def read_section(self, document_id: str, section_ref: str) -> SectionContent | ToolFailure:
        """返回固定 section content。"""

        if document_id != _identity().document_id or section_ref != "section-scripted":
            return ToolFailure(code=FailureCode.NOT_FOUND, message="章节不存在")
        locator = _section_locator(section_ref)
        return SectionContent(
            section_ref=section_ref,
            title="脚本章节",
            text="章节正文只用于回落路径。",
            truncated=False,
            locator=locator,
            citation=_citation(locator),
        )

    def list_tables(self, document_id: str) -> tuple[TableSummary, ...] | ToolFailure:
        """返回供 low-certainty 回落路径发现的表格。"""

        if document_id != _identity().document_id:
            return ToolFailure(code=FailureCode.NOT_FOUND, message="文档不存在")
        locator = _table_locator()
        return (
            TableSummary(
                table_ref="table-scripted",
                caption="脚本表格",
                section_ref="section-scripted",
                locator=locator,
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
        """返回固定 bounded table rows。"""

        del max_rows
        if document_id != _identity().document_id or table_ref != "table-scripted":
            return ToolFailure(code=FailureCode.NOT_FOUND, message="表格不存在")
        locator = _table_locator(table_ref)
        return TableContent(
            table_ref=table_ref,
            caption="脚本表格",
            section_ref="section-scripted",
            rows=(("姓名", "职务"), ("张明", "基金经理")),
            truncated=False,
            locator=locator,
            citation=_citation(locator),
        )


def test_agent_tool_loop_searches_then_reads_section(tmp_path: Path) -> None:
    """Agent loop 必须先搜索再读章节，并返回 read_section 引用。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "基金经理" in result.answer
    assert "4.1.2 基金经理简介" in result.answer
    assert len(result.citations) == 2
    assert result.citations[0].document_id == _identity().document_id
    assert result.citations[0].locator.section_ref == "section-0000"
    assert tuple(entry.tool_name for entry in result.tool_trace[:4]) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
    )
    assert tuple(entry.result_kind for entry in result.tool_trace[:4]) == ("success", "success", "success", "success")
    assert result.tool_trace[0].arguments == {"document_id": _identity().document_id, "query": "基金经理"}
    assert result.tool_trace[1].arguments == {
        "document_id": _identity().document_id,
        "section_ref": "section-0000",
    }


def test_agent_table_aware_loop_answers_manager_table_information(tmp_path: Path) -> None:
    """人物类表格问题必须读取同页表格并返回 table citation。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "张明" in result.answer
    assert "2022年8月8日" in result.answer
    assert result.citations[1].locator.table_ref == "table-0000"
    assert result.citations[1].locator.page_no == 1


def test_agent_table_backed_row_first_hit_reads_table_without_list_tables(tmp_path: Path) -> None:
    """高确定性 table row first hit 必须直接读表，不经 list_tables 发现。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="张明")

    assert result.failure is None
    assert result.answer.startswith("表格内容:")
    assert "张明 | 本基金的基金经理 | 2022年8月8日" in result.answer
    assert "基金经理在本报告期内保持稳定" not in result.answer
    assert "来源章节: 4.1.2 基金经理简介" in result.answer
    assert result.citations[0].locator.table_ref == "table-0000"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.READ_TABLE,
    )


def test_agent_table_backed_caption_first_hit_reads_table_without_list_tables(tmp_path: Path) -> None:
    """高确定性 table caption first hit 必须直接读表并保留 caption 作为来源上下文。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="股票投资明细")

    assert result.failure is None
    assert result.answer.startswith("表格内容:")
    assert "贵州茅台 | 1000" in result.answer
    assert "前十大持仓信息见下表" not in result.answer
    assert "表格标题: 股票投资明细" in result.answer
    assert result.citations[0].locator.table_ref == "table-0001"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.READ_TABLE,
    )


def test_agent_low_certainty_table_backed_hit_uses_existing_table_aware_path() -> None:
    """table-backed hit 不满足 high-certainty 时沿用 section-first table-aware 路径。"""

    locator = _table_locator()
    hit = SearchResult(
        rank=1,
        section_ref="section-scripted",
        title="脚本表格",
        excerpt="不包含原始问题",
        locator=locator,
        citation=_citation(locator),
        match_kind=SearchMatchKind.TABLE_ROW,
        table_ref="table-scripted",
    )
    host = MinimalHost(MinimalFundDocumentAgent(_ScriptedTableHitService(hit)))  # type: ignore[arg-type]

    result = host.run(document_id=_identity().document_id, query="张明")

    assert result.failure is None
    assert "章节正文只用于回落路径" in result.answer
    assert "相关表格:" in result.answer
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
    )


def test_agent_table_backed_hit_without_table_ref_does_not_direct_read_table() -> None:
    """table-backed hit 缺 table_ref 时不得强行直读表。"""

    locator = _section_locator()
    hit = SearchResult(
        rank=1,
        section_ref="section-scripted",
        title="脚本表格",
        excerpt="张明",
        locator=locator,
        citation=_citation(locator),
        match_kind=SearchMatchKind.TABLE_ROW,
        table_ref=None,
    )
    host = MinimalHost(MinimalFundDocumentAgent(_ScriptedTableHitService(hit)))  # type: ignore[arg-type]

    result = host.run(document_id=_identity().document_id, query="张明")

    assert result.failure is None
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
    )
    assert result.tool_trace[3].arguments["table_ref"] == "table-scripted"


def test_agent_table_aware_loop_answers_holding_table_information(tmp_path: Path) -> None:
    """资产持仓类表格问题必须泛化到非基金经理表格。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="前十大持仓")

    assert result.failure is None
    assert "贵州茅台" in result.answer
    assert result.citations[1].locator.table_ref == "table-0001"
    assert tuple(entry.tool_name for entry in result.tool_trace[:4]) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
    )


def test_agent_table_aware_loop_keeps_section_only_answer_when_no_nearby_table(tmp_path: Path) -> None:
    """纯章节文本问题没有相邻表格时不得硬拼不相关表格。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="风险提示")

    assert result.failure is None
    assert "风险提示章节只包含文字说明" in result.answer
    assert "张明" not in result.answer
    assert "贵州茅台" not in result.answer
    assert len(result.citations) == 1
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
    )


def test_agent_tool_loop_does_not_receive_raw_docling_json(tmp_path: Path) -> None:
    """AgentRunResult 不得泄漏 raw Docling JSON、本地路径、cache path 或 local_import_id。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="不存在的关键词")
    rendered = str(asdict(result))

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.NOT_FOUND
    assert result.answer == ""
    assert tuple(entry.tool_name for entry in result.tool_trace) == (ToolName.SEARCH_DOCUMENT,)
    assert result.tool_trace[0].result_kind == "success"
    assert str(tmp_path) not in rendered
    assert ".docling.json" not in rendered
    assert "schema_name" not in rendered
    assert "texts" not in rendered
    assert _identity().local_import_id not in rendered


def test_host_run_result_contains_duration_and_events(tmp_path: Path) -> None:
    """HostRunResult 必须包含耗时和事件列表。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result, HostRunResult)
    assert result.duration > 0
    assert len(result.events) > 0
    assert result.events[0].event_type == HostRunEventType.STARTED
    assert result.events[-1].event_type == HostRunEventType.COMPLETED
    assert result.timed_out is False
    assert result.timeout == 300.0


def test_host_run_result_contains_tool_trace_summary(tmp_path: Path) -> None:
    """HostRunResult 必须包含工具调用统计。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="基金经理")

    assert "total" in result.tool_trace_summary
    assert "success" in result.tool_trace_summary
    assert "failure" in result.tool_trace_summary
    assert result.tool_trace_summary["total"] > 0
    assert result.tool_trace_summary["success"] > 0
    assert result.tool_trace_summary["failure"] == 0


def test_host_run_result_provides_backward_compatible_access(tmp_path: Path) -> None:
    """HostRunResult 必须通过属性代理提供向后兼容的访问。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "基金经理" in result.answer
    assert len(result.citations) > 0
    assert len(result.tool_trace) > 0


def test_host_run_records_search_and_read_events(tmp_path: Path) -> None:
    """HostRunResult 必须记录 search 和 read_section 事件。"""

    host = MinimalHost(MinimalFundDocumentAgent(_service(tmp_path)))
    result = host.run(document_id=_identity().document_id, query="基金经理")

    event_types = [e.event_type for e in result.events]
    assert HostRunEventType.SEARCH in event_types
    assert HostRunEventType.READ_SECTION in event_types


def test_host_timeout_returns_timed_out_result(tmp_path: Path) -> None:
    """timeout 时 HostRunResult 必须标记 timed_out=True。"""

    class _SlowAgent:
        def run(self, **kwargs):
            import time
            time.sleep(10)
            return AgentRunResult(answer="", citations=(), tool_trace=(), failure=None)

    host = MinimalHost(_SlowAgent(), timeout=0.1)
    result = host.run(document_id=_identity().document_id, query="test")

    assert result.timed_out is True
    assert result.duration < 1.0
    assert result.events[-1].event_type == HostRunEventType.FAILED
