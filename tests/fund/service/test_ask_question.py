"""Slice 19D ask_question + profile routing 测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fund_agent.agent import (
    FakeLlmClient,
    FinalAnswer,
    LlmToolLoopRunner,
    ToolCall,
)
from fund_agent.fund.document_tools.constants import (
    FailureCode,
    ReportType,
    SourceKind,
    ToolName,
)
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import ReportIdentity
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service.models import AskQuestionRequest

_DOCUMENT_ID = "004393-2024-annual_report-test19d0000000"


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
                "text": "基金管理费",
                "level": 2,
                "prov": [{"page_no": 5, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金管理费按前一日基金资产净值的 1.20% 年费率计提。",
                "prov": [{"page_no": 5}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "基金托管费",
                "level": 2,
                "prov": [{"page_no": 6, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "基金托管费按前一日基金资产净值的 0.20% 年费率计提。",
                "prov": [{"page_no": 6}],
            },
            {
                "self_ref": "#/texts/4",
                "label": "section_header",
                "text": "4.1.2 基金经理简介",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/5",
                "label": "text",
                "text": "基金经理张明负责本基金投资管理。",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_store(tmp_path: Path) -> DoclingDocumentStore:
    json_path = tmp_path / "private-cache" / "sample.docling.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    _write_docling_json(json_path)
    return DoclingDocumentStore(identity=_identity(), json_path=json_path)


def _make_runner_factory(
    *, answer: str, key_facts: tuple[str, ...], search_query: str = "管理费"
):
    """返回 runner_factory，search → read_section → final answer，citations 动态获取。"""

    def factory(tool_service: FundDocumentToolService) -> LlmToolLoopRunner:
        return LlmToolLoopRunner(
            tool_service=tool_service,
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_DOCUMENT_ID,
                    query=search_query,
                ),
                lambda tr: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_DOCUMENT_ID,
                    section_ref=tr[0].result[0].section_ref,
                ),
                lambda tr: FinalAnswer(
                    answer=answer,
                    citations=tr[1].citations,
                    key_facts=key_facts,
                ),
            ]),
        )

    return factory


# ── Fixture ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_load_store(tmp_path: Path):
    """Mock FilesystemReportRepository.load_store 返回测试 store。"""

    store = _make_store(tmp_path)
    with patch(
        "fund_agent.service.extraction.FilesystemReportRepository.load_store",
        return_value=store,
    ):
        yield


# ── Tests ────────────────────────────────────────────────────────────


def test_ask_question_routing_hits_fee_rates_profile(
    tmp_path: Path, mock_load_store: None
) -> None:
    """使用 profile alias "管理费" → 命中 fee_rates → answer 含费率信息。"""

    from fund_agent.service.extraction import FundReadingService

    svc = FundReadingService(
        runner_factory=_make_runner_factory(
            answer="该基金管理费1.20%/年，托管费0.20%/年，费率处于行业中等水平。",
            key_facts=("管理费",),
            search_query="管理费",
        ),
    )

    result = svc.ask_question(AskQuestionRequest(
        document_id=_DOCUMENT_ID,
        question="管理费",  # exact match for fee_rates alias
        work_dir=tmp_path,
    ))

    assert "1.20%" in result.answer
    assert "0.20%" in result.answer
    assert len(result.routing_trace) >= 1
    assert any(
        attempt.profile_name == "fee_rates" for attempt in result.routing_trace
    )


def test_ask_question_routing_uses_holdings_profile(
    tmp_path: Path, mock_load_store: None
) -> None:
    """使用 profile alias "前十大持仓" → 命中 holdings_top10。"""

    from fund_agent.service.extraction import FundReadingService

    svc = FundReadingService(
        runner_factory=_make_runner_factory(
            answer="前十大持仓包括贵州茅台、五粮液等，管理费1.20%/年。",
            key_facts=("管理费",),
            search_query="管理费",
        ),
    )

    result = svc.ask_question(AskQuestionRequest(
        document_id=_DOCUMENT_ID,
        question="前十大持仓",  # exact match for holdings_top10 alias
        work_dir=tmp_path,
    ))

    assert len(result.routing_trace) >= 1
    assert any(
        attempt.profile_name == "holdings_top10" for attempt in result.routing_trace
    )


def test_ask_question_routing_not_found_profile(
    tmp_path: Path, mock_load_store: None
) -> None:
    """无匹配 profile 时 routing_trace 中 profile_name 均为 None。"""

    from fund_agent.service.extraction import FundReadingService

    svc = FundReadingService(
        runner_factory=_make_runner_factory(
            answer="无法回答此问题，管理费1.20%/年。",
            key_facts=("管理费",),
            search_query="管理费",
        ),
    )

    result = svc.ask_question(AskQuestionRequest(
        document_id=_DOCUMENT_ID,
        question="今天天气怎么样？",  # no profile match
        work_dir=tmp_path,
    ))

    assert len(result.routing_trace) >= 1
    assert all(
        attempt.profile_name is None for attempt in result.routing_trace
    )


def test_ask_question_answer_non_empty(
    tmp_path: Path, mock_load_store: None
) -> None:
    """成功回答时 answer 非空，含基金经理姓名。"""

    from fund_agent.service.extraction import FundReadingService

    svc = FundReadingService(
        runner_factory=_make_runner_factory(
            answer="基金经理张明负责本基金投资管理。",
            key_facts=("张明",),
            search_query="基金经理",
        ),
    )

    result = svc.ask_question(AskQuestionRequest(
        document_id=_DOCUMENT_ID,
        question="基金经理是谁？",
        work_dir=tmp_path,
    ))

    assert result.answer != ""
    assert "张明" in result.answer


def test_ask_question_nonexistent_document_returns_failure(
    tmp_path: Path,
) -> None:
    """不存在的 document_id → failure(NOT_FOUND)。"""

    from fund_agent.service.extraction import FundReadingService
    from fund_agent.fund.document_tools.errors import DocumentToolError

    svc = FundReadingService()

    with patch(
        "fund_agent.service.extraction.FilesystemReportRepository.load_store",
        side_effect=DocumentToolError(FailureCode.NOT_FOUND, "catalog 中不存在该文档"),
    ):
        result = svc.ask_question(AskQuestionRequest(
            document_id="nonexistent-doc-id",
            question="基金经理是谁？",
            work_dir=tmp_path,
        ))

    assert result.failure is not None
    assert result.failure.code is FailureCode.NOT_FOUND
    assert result.answer == ""


def test_ask_question_investment_advice_blocked(
    tmp_path: Path, mock_load_store: None
) -> None:
    """LLM 返回投资建议关键词 → runner fail-closed → failure 非空。"""

    from fund_agent.service.extraction import FundReadingService

    # 使用不触发 routing context 直返的问题，确保走 LLM 路径
    svc = FundReadingService(
        runner_factory=_make_runner_factory(
            answer="强烈建议买入该基金，基金经理张明管理能力突出。",
            key_facts=("张明",),
            search_query="基金经理",
        ),
    )

    result = svc.ask_question(AskQuestionRequest(
        document_id=_DOCUMENT_ID,
        question="基金经理是谁？",
        work_dir=tmp_path,
    ))

    assert result.failure is not None
    assert result.answer == ""
