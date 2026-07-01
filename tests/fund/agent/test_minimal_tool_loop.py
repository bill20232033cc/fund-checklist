"""Minimal Host/Agent tool loop 的 Slice 4 测试。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fund_agent.agent import MinimalFundDocumentAgent
from fund_agent.fund.document_tools.constants import FailureCode, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import ReportIdentity, ToolFailure
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.host import MinimalHost


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
                "captions": [],
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
