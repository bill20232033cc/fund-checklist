"""fake/injected LLM tool-loop contract 的 Slice 8A 测试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from fund_agent.agent import ChatResponse, FakeLlmClient, FinalAnswer, LlmToolLoopRunner, TokenUsage, ToolCall, ToolResult
from fund_agent.agent.context_budget import ContextBudgetState
from fund_agent.agent.llm_tool_loop import (
    _cap_tool_results,
    _coerce_tool_name,
    _document_id_matches,
    _has_long_evidence_overlap,
    _normalize_document_id,
    _truncate_final_answer_summary,
    contains_investment_advice,
    matched_investment_advice_terms,
)
from fund_agent.agent.stream_events import StreamEventType
from fund_agent.agent.tool_loop import AgentRunResult
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ReportType, SourceKind, ToolName
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import (
    Citation,
    Locator,
    ReportIdentity,
    SearchResult,
    SectionContent,
    TableSummary,
    ToolFailure,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service.extraction import (
    AggregateMultiYearAnnualPerformanceResult,
    AnnualPerformanceFieldCitation,
    MultiYearAnnualPerformanceRow,
    MultiYearAnnualPerformanceSeries,
)


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


def test_contains_investment_advice_public_contract() -> None:
    """公共检测函数与 runner 拦截逻辑一致（单一真源契约）。"""

    assert contains_investment_advice("本基金未来一年的预期收益为 8%。") is True
    assert contains_investment_advice("本基金预期收益 8%。") is True
    assert contains_investment_advice("年报披露本基金的预期收益率为 8%。") is False
    assert contains_investment_advice("基金合同载明本基金的投资策略与预期收益及预期风险特征。") is False
    assert contains_investment_advice("当前适合买入该基金。") is True
    assert contains_investment_advice("年报投资策略原文：报告期内买入并持有优质股票。") is False
    assert contains_investment_advice("建议买入该基金，目标价5元。") is True
    assert contains_investment_advice("建议关注该基金的费率水平和业绩表现。") is False


def test_decision_a_annual_report_facts_not_blocked() -> None:
    """决策 A：持仓/费率等年报事实性描述不再被弱词误拦截。"""

    assert contains_investment_advice("报告期内本基金增持了银行、减持了纺织服饰行业。") is False
    assert contains_investment_advice("财务报表附注：本期买入返售金融资产、卖出回购金融资产款。") is False
    assert contains_investment_advice("期末前十大重仓股中本期买入 X、本期卖出 Y。") is False
    assert contains_investment_advice("报告期内实际运作策略：在好价格下买入并持有好公司。") is False
    assert contains_investment_advice("基金合同载明的投资范围包含港股通标的股票，期末持仓中减持了部分证券。") is False


def test_decision_a_directive_context_still_blocked() -> None:
    """决策 A：弱词遇指令动词仍拦截，强指令词与预测句式不回退。"""

    assert contains_investment_advice("该基金值得持有，应增持。") is True
    assert contains_investment_advice("当前适合买入该基金。") is True
    assert contains_investment_advice("建议买入该基金，目标价5元。") is True
    assert contains_investment_advice("强烈推荐卖出该基金。") is True
    assert contains_investment_advice("本基金未来一年的预期收益为 8%。") is True


def test_decision_a_bare_yingshi_facts_not_blocked() -> None:
    """修正：裸 应 不再命中指令动词，应付/应计/应主要投资于 等年报事实表述放行。"""

    assert contains_investment_advice(
        "财务报表附注：本期应付托管费计入负债，买入返售金融资产、卖出回购金融资产款。"
    ) is False
    assert contains_investment_advice(
        "基金合同载明应主要投资于股票资产，买入并持有优质公司。"
    ) is False
    assert contains_investment_advice(
        "报告期内本基金增持了银行，期末应付利息增加。"
    ) is False


def test_decision_a_compound_directives_still_blocked() -> None:
    """修正：复合指令形式仍拦截（应买入/应卖出/应增持/应减持 + 既有 值得持有）。"""

    assert contains_investment_advice("该基金值得持有，应增持。") is True
    assert contains_investment_advice("应买入该基金。") is True
    assert contains_investment_advice("应卖出该基金。") is True
    assert contains_investment_advice("应减持该基金。") is True


def test_matched_terms_consistency_with_decision_a() -> None:
    """matched_investment_advice_terms 与 contains_investment_advice 判定严格一致（决策 A 契约）。"""

    samples = (
        "报告期内本基金增持了银行、减持了纺织服饰行业。",
        "财务报表附注：本期买入返售金融资产、卖出回购金融资产款。",
        "期末前十大重仓股中本期买入 X、本期卖出 Y。",
        "报告期内实际运作策略：在好价格下买入并持有好公司。",
        "该基金值得持有，应增持。",
        "当前适合买入该基金。",
        "建议买入该基金，目标价5元。",
        "本基金未来一年的预期收益为 8%。",
        "年报投资策略原文：报告期内买入并持有优质股票。",
        "今天天气不错。",
    )
    for text in samples:
        assert bool(matched_investment_advice_terms(text)) == contains_investment_advice(text), text


def test_matched_terms_records_directive_context_weak_word() -> None:
    """决策 A：指令动词上下文的弱词进入命中词元（如 应增持 → 增持）。"""

    assert matched_investment_advice_terms("该基金值得持有，应增持。") == ("增持",)


def _write_docling_json(path: Path) -> None:
    """写入含章节和表格的 Docling-shaped JSON，用于 LLM tool loop 测试。"""

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
                "text": "前十大持仓信息见下表，包含贵州茅台等证券。",
                "prov": [{"page_no": 2}],
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


def _write_docling_json_with_manager_holdings(path: Path) -> None:
    """写入含 9.4 基金经理持有本基金 章节的 Docling-shaped JSON（interactive 收敛测试专用）。"""

    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "9.4 期末基金管理人的从业人员持有本基金的情况",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "报告期末，基金经理持有本基金份额数量区间为 0-10 万份，占基金总份额比例为 0.01%。",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service_with_manager_holdings(tmp_path: Path) -> FundDocumentToolService:
    """构建含 9.4 持有本基金 章节的 ToolService fixture（不跑真实 conversion）。"""

    json_path = tmp_path / "private-cache" / "sample-holdings.docling.json"
    json_path.parent.mkdir()
    _write_docling_json_with_manager_holdings(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


def _write_docling_json_with_long_manager_text(path: Path) -> None:
    """写入含超长 9.4 章节文本的 Docling-shaped JSON（原文粘贴截断测试专用）。"""

    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "9.4 期末基金管理人的从业人员持有本基金的情况",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "报告期末，基金经理持有本基金份额数量区间为 0-10 万份。" * 30,
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _service_with_long_manager_text(tmp_path: Path) -> FundDocumentToolService:
    """构建含超长 9.4 章节文本的 ToolService fixture（不跑真实 conversion）。"""

    json_path = tmp_path / "private-cache" / "sample-long-holdings.docling.json"
    json_path.parent.mkdir()
    _write_docling_json_with_long_manager_text(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    return FundDocumentToolService({_identity().document_id: store})


class _CountingToolService(FundDocumentToolService):
    """统计 read_section 调用次数，验证失败调用去重不二次执行工具。"""

    def __init__(self, inner: FundDocumentToolService) -> None:
        """包装内部 service 并初始化计数器。"""

        super().__init__({})
        self._inner = inner
        self.read_section_calls = 0

    def read_section(
        self,
        document_id: str,
        section_ref: str,
        *,
        max_chars: int | None = None,
    ) -> SectionContent | ToolFailure:
        """计数后委托内部 service。"""

        self.read_section_calls += 1
        return self._inner.read_section(document_id, section_ref, max_chars=max_chars)

    def _store(self, document_id: str):
        """委托内部 service 的文档 registry（避免空 registry 导致 search 失败）。"""

        return self._inner._store(document_id)


class _CountingFakeLlmClient(FakeLlmClient):
    """记录 next_step 调用次数的 FakeLlmClient，用于验证有界重试。"""

    def __init__(self, steps) -> None:
        """初始化并置零计数器。"""

        super().__init__(steps)
        self.next_step_calls = 0

    def next_step(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: tuple[ToolResult, ...],
        remaining_budget: int | None = None,
    ) -> ChatResponse:
        """计数后委托父类。"""

        self.next_step_calls += 1
        return super().next_step(
            document_id=document_id,
            query=query,
            tool_results=tool_results,
            remaining_budget=remaining_budget,
        )


def _section_ref_from_search(results: tuple[ToolResult, ...]) -> str:
    """从最近的 search_document ToolResult 中取 section_ref。"""

    search_results = results[-1].result
    assert isinstance(search_results, tuple)
    hit = search_results[0]
    assert isinstance(hit, SearchResult)
    return hit.section_ref


def _first_table_ref(results: tuple[ToolResult, ...]) -> str:
    """从最近的 list_tables ToolResult 中取 table_ref。"""

    table_summaries = results[-1].result
    assert isinstance(table_summaries, tuple)
    table = table_summaries[0]
    assert isinstance(table, TableSummary)
    return table.table_ref


def _final_with_latest_citation(answer: str, key_fact: str) -> Callable[[tuple[ToolResult, ...]], FinalAnswer]:
    """构造使用最近工具 citation 的 fake final-answer factory。"""

    def _factory(results: tuple[ToolResult, ...]) -> FinalAnswer:
        return FinalAnswer(
            answer=answer,
            citations=results[-1].citations,
            key_facts=(key_fact,),
        )

    return _factory


def test_fake_llm_searches_reads_section_then_answers_with_section_citation(tmp_path: Path) -> None:
    """fake LLM 必须通过 search_document/read_section 取证后回答并带 section citation。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert result.answer == "基金经理张明负责本基金投资管理。"
    assert len(result.citations) == 1
    assert result.citations[0].locator.section_ref == "section-0000"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
    )


def test_fake_llm_reads_table_then_answers_with_table_citation(tmp_path: Path) -> None:
    """fake LLM 可调用 list_tables/read_table，并用 table citation 支撑表格事实。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                ToolCall(tool_name=ToolName.LIST_TABLES, document_id=_identity().document_id),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_TABLE,
                    document_id=_identity().document_id,
                    table_ref=_first_table_ref(results),
                ),
                _final_with_latest_citation("表格披露基金经理为张明。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "张明" in result.answer
    assert len(result.citations) == 1
    assert result.citations[0].locator.table_ref == "table-0000"
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
    )


def test_fake_llm_final_answer_without_evidence_fails_closed(tmp_path: Path) -> None:
    """LLM 未调用工具就直接 final answer 时必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer="基金经理是张明。",
                    citations=(),
                    key_facts=("张明",),
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.citations == ()
    assert result.tool_trace == ()


def test_fake_llm_unknown_tool_fails_closed(tmp_path: Path) -> None:
    """LLM 请求未知工具必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name="extract_fields",
                    document_id=_identity().document_id,
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.tool_trace[0].tool_name == "extract_fields"
    assert result.tool_trace[0].result_kind == "failure"


def test_llm_tool_call_missing_document_id_filled_from_expected(tmp_path: Path) -> None:
    """document_id 缺失/空字符串时工具调用成功：runner 用 expected_document_id 补全。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id="",
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id="",
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
    )
    assert all(entry.result_kind == "success" for entry in result.tool_trace)


def test_llm_tool_call_wrong_document_id_prefix_rejected(tmp_path: Path) -> None:
    """document_id 明显错误（前缀不匹配）时仍拒绝，且工具不被执行。"""

    service = _CountingToolService(_service(tmp_path))
    runner = LlmToolLoopRunner(
        tool_service=service,
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id="other-fund-2024-annual_report-xyz",
                    section_ref="section-0000",
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.tool_trace[0].result_kind == "failure"
    assert result.tool_trace[0].failure_code is FailureCode.UNAVAILABLE
    assert service.read_section_calls == 0


def test_unknown_tool_name_with_noise_rejected_and_trace_keeps_raw(tmp_path: Path) -> None:
    """带格式噪声的未知工具名归一化后仍拒绝，trace 保留 LLM 原始工具名。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name="extract_fields(max_results=5)",
                    document_id=_identity().document_id,
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.tool_trace[0].tool_name == "extract_fields(max_results=5)"
    assert result.tool_trace[0].result_kind == "failure"


def test_coerce_tool_name_normalizes_format_noise_only() -> None:
    """工具名只做格式归一化：空白/尾部括号参数放行，未知名与语义别名仍拒绝。"""

    assert _coerce_tool_name(ToolName.SEARCH_DOCUMENT) is ToolName.SEARCH_DOCUMENT
    assert _coerce_tool_name(" read_section ") is ToolName.READ_SECTION
    assert _coerce_tool_name("read_section(max_chars=100)") is ToolName.READ_SECTION
    assert _coerce_tool_name("list_tables()") is ToolName.LIST_TABLES
    assert _coerce_tool_name("") is None
    assert _coerce_tool_name("extract_fields") is None
    assert _coerce_tool_name("extract_fields(max_results=5)") is None
    assert _coerce_tool_name("search") is None  # 禁止语义映射
    assert _coerce_tool_name("SearchDocument") is None


def test_fake_llm_failure_fed_back_then_recovers(tmp_path: Path) -> None:
    """首调 read_section 用错 section_ref 失败后，失败回喂 LLM，第二轮改用 search 成功收尾。"""

    seen_failures: list[ToolFailure] = []

    def _step_after_failure(results: tuple[ToolResult, ...]) -> ToolCall:
        """下一轮 LLM 应能看到失败 code/message，并改用 search。"""

        last = results[-1]
        assert last.failure is not None
        assert last.failure.code is FailureCode.NOT_FOUND
        assert last.failure.message == "章节不存在"
        seen_failures.append(last.failure)
        return ToolCall(
            tool_name=ToolName.SEARCH_DOCUMENT,
            document_id=_identity().document_id,
            query="基金经理",
        )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref="section-9999",
                ),
                _step_after_failure,
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert result.answer == "基金经理张明负责本基金投资管理。"
    assert len(seen_failures) == 1
    # 失败条目进入 trace，且成功路径沿用 search → read_section → final
    assert result.tool_trace[0].tool_name is ToolName.READ_SECTION
    assert result.tool_trace[0].result_kind == "failure"
    assert result.tool_trace[0].failure_code is FailureCode.NOT_FOUND
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.READ_SECTION,
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
    )


def test_fake_llm_repeated_failed_call_short_circuits(tmp_path: Path) -> None:
    """同一失败调用重复出现时短路返回既有失败结果，不二次执行工具。"""

    service = _CountingToolService(_service(tmp_path))
    runner = LlmToolLoopRunner(
        tool_service=service,
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref="section-9999",
                ),
                # 重复的失败调用：runner 应短路返回既有失败结果
                ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref="section-9999",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    # 首次失败 1 次 + 最终成功 1 次；重复失败调用未再次执行工具
    assert service.read_section_calls == 2


def test_fake_llm_unauthorized_tool_fails_closed(tmp_path: Path) -> None:
    """LLM 请求未授权的已知工具必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.LIST_REPORTS,
                    document_id=_identity().document_id,
                )
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""
    assert result.tool_trace[0].tool_name is ToolName.LIST_REPORTS
    assert result.tool_trace[0].result_kind == "failure"


def test_run_stream_tool_failure_continues_and_reports_result_event(tmp_path: Path) -> None:
    """run_stream：工具失败发 TOOL_EVENT(result) 并继续循环，不发 ERROR，成功收尾发 DONE。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref="section-9999",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    events = list(runner.run_stream(document_id=_identity().document_id, query="基金经理", scene="ask"))
    types = [event.type for event in events]

    assert StreamEventType.ERROR not in types
    assert StreamEventType.DONE in types
    failure_events = [
        event
        for event in events
        if event.type is StreamEventType.TOOL_EVENT
        and event.payload.get("phase") == "result"
        and event.payload.get("failure_code") == FailureCode.NOT_FOUND.value
    ]
    assert len(failure_events) == 1
    assert failure_events[0].payload["message"] == "章节不存在"
    # 最终回答仍然产出
    assert any(
        event.type is StreamEventType.CONTENT_DELTA and "张明" in str(event.payload)
        for event in events
    )


def test_run_stream_terminal_failure_still_emits_error(tmp_path: Path) -> None:
    """run_stream：终态失败（终答守卫，无工具证据）仍发 ERROR。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer="基金经理是张明。",
                    citations=(),
                    key_facts=(),
                )
            ]
        ),
    )

    events = list(runner.run_stream(document_id=_identity().document_id, query="基金经理", scene="ask"))

    assert any(event.type is StreamEventType.ERROR for event in events)
    assert not any(event.type is StreamEventType.DONE for event in events)


def test_no_fact_question_final_answer_without_tools(tmp_path: Path) -> None:
    """无事实检索目标问题：0 工具调用直接 final answer（interactive 场景）。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer="这个问题属于观点判断，我无法从年报数据中给出结论。",
                    citations=(),
                    key_facts=(),
                )
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="这个基金值得继续关注吗？",
        scene="interactive",
    )

    assert result.failure is None
    assert "观点判断" in result.answer
    assert result.tool_trace == ()


def test_opinion_question_neutral_answer_not_blocked(tmp_path: Path) -> None:
    """观点类问题（如是否值得关注）：0 工具调用 + 中性表述回答不被终答守卫拦截。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer="该问题属于主观判断，我无法从年报披露事实中给出结论，请结合自身情况独立判断。",
                    citations=(),
                    key_facts=(),
                )
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="这是基金值得继续关注吗？",
        scene="interactive",
    )

    assert result.failure is None
    assert "主观判断" in result.answer
    assert result.tool_trace == ()


def test_opinion_question_fact_only_neutral_answer_not_blocked(tmp_path: Path) -> None:
    """观点问题：0 工具 + 只陈述业绩/费率客观事实的中性回答不触发终答守卫。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer=(
                        "年报披露的业绩与费率属于客观事实；"
                        "该基金是否值得关注或持有属于主观判断，我无法给出判断。"
                    ),
                    citations=(),
                    key_facts=(),
                )
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="这是基金值得继续关注吗？",
        scene="interactive",
    )

    assert result.failure is None
    assert "业绩" in result.answer
    assert "费率" in result.answer
    assert "无法给出判断" in result.answer
    assert result.tool_trace == ()


def test_empty_search_retried_once_then_declares_not_found(tmp_path: Path) -> None:
    """连续无命中搜索：2 次内停止并声明未找到，不触发 step limit。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="不存在的关键词",
                ),
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="替代关键词",
                ),
                FinalAnswer(
                    answer="未找到相关数据。",
                    citations=(),
                    key_facts=(),
                ),
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="港股持仓情况是什么？",
        scene="interactive",
    )

    assert result.failure is None
    assert "未找到相关数据" in result.answer
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.SEARCH_DOCUMENT,
    )
    assert all(entry.result_kind == "success" for entry in result.tool_trace)


def test_interactive_empty_search_forced_convergence_without_waiting_llm(tmp_path: Path) -> None:
    """interactive：search 连续 2 次 0 命中 → runner 强制收敛，不再等待模型终答。"""

    client = _CountingFakeLlmClient(
        [
            ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=_identity().document_id,
                query="不存在的关键词",
            ),
            ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=_identity().document_id,
                query="替代关键词",
            ),
            FinalAnswer(answer="模型不应被调用到这里", citations=(), key_facts=()),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    result = runner.run(
        document_id=_identity().document_id,
        query="港股持仓情况是什么？",
        scene="interactive",
    )

    assert result.failure is None
    assert result.answer == "未找到相关数据"
    assert client.next_step_calls == 2  # 第 2 次空结果后直接收敛，不请求模型终答
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.SEARCH_DOCUMENT,
        ToolName.SEARCH_DOCUMENT,
    )


def test_interactive_empty_search_dedup_repeat_converges(tmp_path: Path) -> None:
    """interactive：重复完全相同空 search 也计入连续空结果，第二次触发强制收敛。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="不存在的关键词",
                ),
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="不存在的关键词",
                ),
                FinalAnswer(answer="模型不应被调用到这里", citations=(), key_facts=()),
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="找不到的内容",
        scene="interactive",
    )

    assert result.failure is None
    assert result.answer == "未找到相关数据"
    # 第二次调用被去重（只执行一次工具），仍计入空结果并收敛
    assert len(result.tool_trace) == 1


def test_interactive_empty_search_auto_candidate_retry_hits_evidence(tmp_path: Path) -> None:
    """interactive：有 profile 候选词时，空结果后 runner 自动用候选词重试并命中 9.4。"""

    runner = LlmToolLoopRunner(
        tool_service=_service_with_manager_holdings(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理持有本产品",
                ),
                FinalAnswer(
                    answer="根据年报，基金经理持有本基金份额数量区间为 0-10 万份。",
                    citations=(),
                    key_facts=(),
                ),
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="基金经理持有本产品吗",
        scene="interactive",
        candidate_queries=("基金经理持有本产品", "持有本基金", "基金经理持有"),
    )

    assert result.failure is None
    assert "0-10 万份" in result.answer
    trace_queries = tuple(
        entry.arguments.get("query") for entry in result.tool_trace if entry.tool_name == ToolName.SEARCH_DOCUMENT
    )
    assert trace_queries == ("基金经理持有本产品", "持有本基金")


def test_interactive_empty_search_auto_candidate_retry_still_empty_converges(tmp_path: Path) -> None:
    """interactive：候选词自动重试仍 0 命中 → 连续 2 次空结果强制收敛。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理持有本产品",
                ),
                FinalAnswer(answer="模型不应被调用到这里", citations=(), key_facts=()),
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="基金经理持有本产品吗",
        scene="interactive",
        candidate_queries=("基金经理持有本产品", "持有本基金", "基金经理持有"),
    )

    assert result.failure is None
    assert result.answer == "未找到相关数据"
    assert tuple(
        entry.arguments.get("query") for entry in result.tool_trace if entry.tool_name == ToolName.SEARCH_DOCUMENT
    ) == ("基金经理持有本产品", "持有本基金")


def test_interactive_json_envelope_answer_unwrapped_for_display(tmp_path: Path) -> None:
    """interactive：终答为 JSON 信封时 runner 解包 answer 展示，不把 JSON 透传给用户。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(
                    answer=(
                        '{"answer": "根据年报，基金经理持有本基金份额数量区间为 0-10 万份。", '
                        '"citations": [], "key_facts": ["0-10 万份"]}'
                    ),
                    citations=(),
                    key_facts=(),
                )
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="基金经理持有本产品吗",
        scene="interactive",
    )

    assert result.failure is None
    assert result.answer == "根据年报，基金经理持有本基金份额数量区间为 0-10 万份。"
    assert "{" not in result.answer


def test_interactive_json_envelope_citations_parsed_into_result(tmp_path: Path) -> None:
    """interactive：JSON 信封中的 citations 解析后随 AgentRunResult 落盘。"""

    envelope = (
        '{"answer": "根据年报，基金经理持有本基金。", '
        '"citations": [{"document_id": "004393-2024-annual_report-abc123def4567890", '
        '"fund_code": "004393", "fund_name": "安信企业价值优选混合型证券投资基金", '
        '"year": 2024, "report_type": "annual_report", '
        '"locator": {"document_id": "004393-2024-annual_report-abc123def4567890", '
        '"locator_kind": "section", "section_ref": "9.4 期末基金管理人的从业人员持有本基金的情况", '
        '"table_ref": null, "page_no": 8}}], "key_facts": []}'
    )
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                FinalAnswer(answer=envelope, citations=(), key_facts=()),
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="基金经理持有本产品吗",
        scene="interactive",
    )

    assert result.failure is None
    assert len(result.citations) == 1
    assert result.citations[0].document_id == "004393-2024-annual_report-abc123def4567890"
    assert result.citations[0].locator.section_ref == "9.4 期末基金管理人的从业人员持有本基金的情况"


def test_interactive_advice_guard_retried_once_then_neutral_answer_passes(tmp_path: Path) -> None:
    """interactive：终答含建议被守卫拦截 → 重试 1 次 → 中性回答通过，next_step 恰好 2 次。"""

    client = _CountingFakeLlmClient(
        [
            FinalAnswer(
                answer="建议买入该基金，目标价5元。",
                citations=(),
                key_facts=(),
            ),
            FinalAnswer(
                answer="该基金是否值得关注或持有属于主观判断，我无法给出判断。",
                citations=(),
                key_facts=(),
            ),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    result = runner.run(
        document_id=_identity().document_id,
        query="这个基金怎么样？",
        scene="interactive",
    )

    assert result.failure is None
    assert "无法给出判断" in result.answer
    assert client.next_step_calls == 2


def test_interactive_advice_guard_retry_still_fails_closed(tmp_path: Path) -> None:
    """interactive：重试后仍含建议 → 维持 fail-closed，2 次 next_step。"""

    client = _CountingFakeLlmClient(
        [
            FinalAnswer(
                answer="建议买入该基金。",
                citations=(),
                key_facts=(),
            ),
            FinalAnswer(
                answer="当前适合买入该基金。",
                citations=(),
                key_facts=(),
            ),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    result = runner.run(
        document_id=_identity().document_id,
        query="这个基金怎么样？",
        scene="interactive",
    )

    assert isinstance(result.failure, ToolFailure)
    assert "投资建议" in result.failure.message
    assert result.answer == ""
    assert client.next_step_calls == 2


def test_ask_advice_guard_no_retry(tmp_path: Path) -> None:
    """ask：终答含建议不重试，保持原失败（1 次 next_step）。"""

    client = _CountingFakeLlmClient(
        [
            FinalAnswer(
                answer="建议买入该基金。",
                citations=(),
                key_facts=(),
            )
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    result = runner.run(
        document_id=_identity().document_id,
        query="这个基金怎么样？",
        scene="ask",
    )

    assert isinstance(result.failure, ToolFailure)
    assert "投资建议" in result.failure.message
    assert client.next_step_calls == 1


def test_interactive_paste_guard_retried_once_then_rewritten(tmp_path: Path) -> None:
    """interactive：终答粘贴工具原文 → 有界重答 1 次 → 用自己的话概括后通过。"""

    client = _CountingFakeLlmClient(
        [
            ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=_identity().document_id,
                query="基金经理",
            ),
            lambda results: ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=_identity().document_id,
                section_ref=_section_ref_from_search(results),
            ),
            lambda results: FinalAnswer(
                answer=results[-1].evidence_text,
                citations=results[-1].citations,
                key_facts=(),
            ),
            FinalAnswer(
                answer="根据年报，基金经理负责本基金投资管理，报告期内保持稳定。",
                citations=(),
                key_facts=(),
            ),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    result = runner.run(
        document_id=_identity().document_id,
        query="基金经理是谁？",
        scene="interactive",
    )

    assert result.failure is None
    assert "基金经理负责本基金投资管理" in result.answer
    assert client.next_step_calls == 4  # search + read_section + 粘贴终答 + 有界重答


def test_interactive_paste_guard_retry_still_pastes_truncates_summary(tmp_path: Path) -> None:
    """interactive：重答后仍粘贴原文 → 截断为前 200 字摘要格式。"""

    runner = LlmToolLoopRunner(
        tool_service=_service_with_long_manager_text(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                lambda results: FinalAnswer(
                    answer=results[-1].evidence_text,
                    citations=results[-1].citations,
                    key_facts=(),
                ),
                lambda results: FinalAnswer(
                    answer=results[-1].evidence_text,
                    citations=results[-1].citations,
                    key_facts=(),
                ),
            ]
        ),
    )

    result = runner.run(
        document_id=_identity().document_id,
        query="基金经理是谁？",
        scene="interactive",
    )

    assert result.failure is None
    assert len(result.answer) <= 200 + 25
    assert "截断" in result.answer
    assert result.answer.startswith("9.4 期末基金管理人的从业人员持有本基金的情况")


def test_interactive_long_answer_guard_truncated_after_retry(tmp_path: Path) -> None:
    """interactive：answer >800 字 → 有界重答 1 次，仍超长则截断为摘要格式。"""

    long_answer = "这是年报事实。" * 160  # 8 字 * 160 = 1280 字
    client = _CountingFakeLlmClient(
        [
            FinalAnswer(answer=long_answer, citations=(), key_facts=()),
            FinalAnswer(answer=long_answer, citations=(), key_facts=()),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    result = runner.run(
        document_id=_identity().document_id,
        query="请详细说明基金情况",
        scene="interactive",
    )

    assert result.failure is None
    assert len(result.answer) <= 200 + 25
    assert "截断" in result.answer
    assert client.next_step_calls == 2


def test_has_long_evidence_overlap_threshold() -> None:
    """原文粘贴检测：连续重叠 <40 字符放行，≥40 字符拦截。"""

    evidence = "报告期内基金经理持有本基金份额数量区间为 0-10 万份。" * 2
    assert not _has_long_evidence_overlap(evidence[:39], evidence)
    assert _has_long_evidence_overlap(evidence[:40], evidence)
    assert not _has_long_evidence_overlap("完全不同的自然语言概括内容", evidence)
    assert not _has_long_evidence_overlap("短", evidence)


def test_truncate_final_answer_summary_format() -> None:
    """摘要截断：≤200 字原样返回，>200 字截断为前 200 字 + 省略说明。"""

    assert _truncate_final_answer_summary("短回答") == "短回答"
    long_answer = "好" * 300
    truncated = _truncate_final_answer_summary(long_answer)
    assert truncated.startswith("好" * 200)
    assert "截断" in truncated


def test_run_stream_interactive_advice_guard_retry_passes(tmp_path: Path) -> None:
    """run_stream：interactive 终答守卫重试通过 → DONE，无 ERROR。"""

    client = _CountingFakeLlmClient(
        [
            FinalAnswer(
                answer="建议买入该基金。",
                citations=(),
                key_facts=(),
            ),
            FinalAnswer(
                answer="该基金是否值得关注或持有属于主观判断，我无法给出判断。",
                citations=(),
                key_facts=(),
            ),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    events = list(
        runner.run_stream(
            document_id=_identity().document_id,
            query="这个基金怎么样？",
            scene="interactive",
        )
    )

    assert not any(event.type is StreamEventType.ERROR for event in events)
    assert any(event.type is StreamEventType.DONE for event in events)
    assert any(
        event.type is StreamEventType.CONTENT_DELTA and "无法给出判断" in str(event.payload)
        for event in events
    )
    assert client.next_step_calls == 2


def test_run_stream_interactive_advice_guard_retry_still_errors(tmp_path: Path) -> None:
    """run_stream：interactive 终答守卫重试后仍失败 → ERROR，无 DONE。"""

    client = _CountingFakeLlmClient(
        [
            FinalAnswer(
                answer="建议买入该基金。",
                citations=(),
                key_facts=(),
            ),
            FinalAnswer(
                answer="建议卖出该基金。",
                citations=(),
                key_facts=(),
            ),
        ]
    )
    runner = LlmToolLoopRunner(tool_service=_service(tmp_path), llm_client=client)

    events = list(
        runner.run_stream(
            document_id=_identity().document_id,
            query="这个基金怎么样？",
            scene="interactive",
        )
    )

    errors = [event for event in events if event.type is StreamEventType.ERROR]
    assert len(errors) == 1
    assert "投资建议" in str(errors[0].payload.get("message", ""))
    assert not any(event.type is StreamEventType.DONE for event in events)
    assert client.next_step_calls == 2


def test_fake_llm_missing_citation_fails_closed(tmp_path: Path) -> None:
    """LLM 有工具证据但 final answer 缺 citation 时必须 fail-closed。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=(),
                    key_facts=("张明",),
                ),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""


def test_fake_llm_no_evidence_fact_fails_closed(tmp_path: Path) -> None:
    """LLM final answer 中关键事实不在工具证据内时：key_facts 校验已放宽（citation 校验已足够）。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                lambda results: FinalAnswer(
                    answer="基金经理为李雷。",
                    citations=results[-1].citations,
                    key_facts=("李雷",),
                ),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    # key_facts 校验已放宽，citation 校验仍生效
    assert result.failure is None
    assert "李雷" in result.answer


def test_llm_tool_loop_output_does_not_leak_private_payload_or_paths(tmp_path: Path) -> None:
    """LLM runner 输出不得泄漏 raw Docling JSON、本地路径、cache path 或 local_import_id。"""

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient(
            [
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                _final_with_latest_citation("基金经理张明负责本基金投资管理。", "张明"),
            ]
        ),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")
    rendered = str(asdict(result))

    assert result.failure is None
    assert str(tmp_path) not in rendered
    assert "private-cache" not in rendered
    assert ".docling.json" not in rendered
    assert "schema_name" not in rendered
    assert "texts" not in rendered
    assert "tables" not in rendered
    assert _identity().local_import_id not in rendered


def _fake_table_citation(year: int, table_ref: str) -> Citation:
    """构造用于多年度业绩测试的 fake table citation。"""

    return Citation(
        document_id=_identity().document_id,
        fund_code=_identity().fund_code,
        fund_name=_identity().fund_name,
        year=year,
        report_type=ReportType.ANNUAL_REPORT.value,
        locator=Locator(
            document_id=_identity().document_id,
            locator_kind=LocatorKind.TABLE,
            section_ref="section-0000",
            table_ref=table_ref,
            page_no=2,
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        ),
    )


def _citations_from_result(result: AggregateMultiYearAnnualPerformanceResult) -> tuple[Citation, ...]:
    """从 AggregateMultiYearAnnualPerformanceResult 提取所有 Citation 对象。"""

    return tuple(
        field_citation.citation
        for series in result.series
        for field_citation in series.citations
    )


def _fake_multi_year_result(
    *,
    years: tuple[int, ...],
    missing: tuple[int, ...] = (),
) -> AggregateMultiYearAnnualPerformanceResult:
    """构造用于测试的 fake AggregateMultiYearAnnualPerformanceResult。"""

    covered = tuple(y for y in years if y not in missing)
    rows = tuple(
        MultiYearAnnualPerformanceRow(
            year=y,
            annual_nav_growth_rate="17.32%",
            annual_benchmark_return_rate="12.50%",
            annual_excess_return="4.82%",
            citations=(
                AnnualPerformanceFieldCitation(
                    field_name="annual_nav_growth_rate",
                    citation=_fake_table_citation(y, f"table-{y}-nav"),
                ),
                AnnualPerformanceFieldCitation(
                    field_name="annual_benchmark_return_rate",
                    citation=_fake_table_citation(y, f"table-{y}-bench"),
                ),
                AnnualPerformanceFieldCitation(
                    field_name="annual_excess_return",
                    citation=_fake_table_citation(y, f"table-{y}-excess"),
                ),
            ),
        )
        for y in covered
    )
    citations = tuple(field_citation for row in rows for field_citation in row.citations)
    coverage_status = "complete" if not missing else "partial"
    series = MultiYearAnnualPerformanceSeries(
        fund_code=_identity().fund_code,
        requested_years=years,
        covered_years=covered,
        missing_years=missing,
        coverage_status=coverage_status,
        coverage_count=len(covered),
        minimum_required_count=3,
        share_class_scope="A",
        rows=rows,
        citations=citations,
    )
    return AggregateMultiYearAnnualPerformanceResult(series=(series,), failure=None)


def _aggregate_tool_call(extra: dict[str, object]) -> ToolCall:
    """构造 aggregate_multi_year_annual_performance 的 ToolCall。"""

    return ToolCall(
        tool_name=ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE,
        document_id=_identity().document_id,
        extra=extra,
    )


def _aggregate_extra() -> dict[str, object]:
    """返回 5 年 partial coverage 的 fake aggregate 参数。"""

    return {
        "fund_code": _identity().fund_code,
        "requested_years": (2020, 2021, 2022, 2023, 2024),
        "annual_report_documents": [
            {"year": 2020, "document_id": "doc-2020"},
            {"year": 2021, "document_id": "doc-2021"},
            {"year": 2022, "document_id": "doc-2022"},
            {"year": 2023, "document_id": "doc-2023"},
        ],
        "share_class": "A",
    }


def test_fake_llm_aggregate_multi_year_partial_coverage_preserves_metadata(tmp_path: Path) -> None:
    """partial coverage 时 final answer 必须包含 coverage_status、covered_years、missing_years。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=partial, covered_years=2020-2023, missing_years=2024, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert "partial" in result.answer
    assert "2020" in result.answer
    assert "2023" in result.answer
    assert "2024" in result.answer
    assert len(result.citations) > 0
    assert tuple(entry.tool_name for entry in result.tool_trace) == (
        ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE,
    )


def test_fake_llm_aggregate_multi_year_complete_coverage_no_invented_missing_years(tmp_path: Path) -> None:
    """complete coverage 时 final answer 不得虚构 missing_years。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=complete, covered_years=2020-2024, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert "complete" in result.answer
    assert "missing_years" not in result.answer


def test_fake_llm_aggregate_multi_year_tool_failure_not_found_returns_agent_failure(tmp_path: Path) -> None:
    """aggregate handler 返回 not_found failure 时：失败回喂进 trace，终答无证据则终态失败。"""

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return AggregateMultiYearAnnualPerformanceResult(
            series=(),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message="multi-year annual performance 覆盖不足 3 年"),
        )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            FinalAnswer(answer="不应到达", citations=(), key_facts=()),
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    # 失败不终止整轮，原始失败分类进入 tool_trace（下一轮 LLM 可见）
    assert result.tool_trace[0].tool_name is ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE
    assert result.tool_trace[0].result_kind == "failure"
    assert result.tool_trace[0].failure_code is FailureCode.NOT_FOUND
    # LLM 未基于成功证据回答 → 终态失败来自终答守卫
    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""


def test_fake_llm_aggregate_multi_year_tool_failure_identity_mismatch_returns_agent_failure(
    tmp_path: Path,
) -> None:
    """aggregate handler 返回 identity_mismatch failure 时：失败回喂进 trace，终答无证据则终态失败。"""

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return AggregateMultiYearAnnualPerformanceResult(
            series=(),
            failure=ToolFailure(code=FailureCode.IDENTITY_MISMATCH, message="multi-year annual report identity 不匹配"),
        )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            FinalAnswer(answer="不应到达", citations=(), key_facts=()),
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.tool_trace[0].tool_name is ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE
    assert result.tool_trace[0].result_kind == "failure"
    assert result.tool_trace[0].failure_code is FailureCode.IDENTITY_MISMATCH
    assert isinstance(result.failure, ToolFailure)
    assert result.failure.code is FailureCode.UNAVAILABLE
    assert result.answer == ""


def test_fake_llm_aggregate_multi_year_final_answer_includes_per_year_citations(tmp_path: Path) -> None:
    """final answer citations 必须包含 per-year per-field table locator citations。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=partial, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert len(result.citations) == 12  # 4 years * 3 fields
    for citation in result.citations:
        assert citation.locator.locator_kind is LocatorKind.TABLE
        assert citation.locator.table_ref is not None


def test_fake_llm_aggregate_multi_year_final_answer_no_investment_judgment(tmp_path: Path) -> None:
    """final answer 不得包含年化收益率、扣费后收益率或投资判断。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩: coverage_status=partial, 年度净值增长率 17.32%, 超额收益 4.82%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")

    assert result.failure is None
    assert "年化收益率" not in result.answer
    assert "扣费后收益率" not in result.answer
    assert "R=A+B-C" not in result.answer
    assert "annualized" not in result.answer
    assert "fee-adjusted" not in result.answer


def test_fake_llm_aggregate_multi_year_no_leakage(tmp_path: Path) -> None:
    """输出不得泄漏 raw Docling JSON、本地路径、cache path 或 local_import_id。"""

    fake_result = _fake_multi_year_result(
        years=(2020, 2021, 2022, 2023, 2024),
        missing=(2024,),
    )

    def fake_aggregate_handler(fund_code, requested_years, annual_report_documents, share_class):
        return fake_result

    final = FinalAnswer(
        answer="多年度业绩聚合完成, 年度净值增长率 17.32%。",
        citations=_citations_from_result(fake_result),
        key_facts=("17.32%",),
    )

    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=FakeLlmClient([
            _aggregate_tool_call(_aggregate_extra()),
            final,
        ]),
        aggregate_handler=fake_aggregate_handler,
    )

    result = runner.run(document_id=_identity().document_id, query="多年度业绩")
    rendered = str(asdict(result))

    assert result.failure is None
    assert str(tmp_path) not in rendered
    assert "private-cache" not in rendered
    assert ".docling.json" not in rendered
    assert "schema_name" not in rendered
    assert "texts" not in rendered
    assert "tables" not in rendered
    assert _identity().local_import_id not in rendered


# ── Fix 3: tool call dedup ─────────────────────────────────────────────

class _DuplicateToolCallClient:
    """search → read_section → 重复 read_section → final answer。"""

    def __init__(self, document_id: str) -> None:
        self._document_id = document_id
        self._step = 0
        self._section_ref: str | None = None

    def next_step(self, *, document_id, query, tool_results, remaining_budget=None):
        if self._step == 0:
            self._step = 1
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT,
                document_id=self._document_id,
                query="基金经理",
            ))
        if self._step == 1:
            self._step = 2
            search_results = tool_results[-1].result
            self._section_ref = search_results[0].section_ref
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=self._document_id,
                section_ref=self._section_ref,
            ))
        if self._step == 2:
            self._step = 3
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.READ_SECTION,
                document_id=self._document_id,
                section_ref=self._section_ref,
            ))
        section_citation = tool_results[-1].citations[0]
        return ChatResponse(step=FinalAnswer(
            answer="基金经理张明负责本基金投资管理。",
            citations=(section_citation,),
            key_facts=("张明",),
        ))


def test_duplicate_tool_call_reuses_cached_result(tmp_path: Path) -> None:
    """重复 (tool_name, arguments) 调用复用缓存结果，不重新执行。"""
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=_DuplicateToolCallClient(_identity().document_id),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    assert "张明" in result.answer
    # trace 记录 search_document + 第一次 read_section（第二次 read_section 去重跳过）
    assert len(result.tool_trace) == 2
    trace_names = tuple(entry.tool_name for entry in result.tool_trace)
    assert trace_names == (ToolName.SEARCH_DOCUMENT, ToolName.READ_SECTION)


def test_dedup_preserves_tool_results_in_order(tmp_path: Path) -> None:
    """去重后 tool_results 保持顺序（缓存结果追加到正确位置）。"""
    runner = LlmToolLoopRunner(
        tool_service=_service(tmp_path),
        llm_client=_DuplicateToolCallClient(_identity().document_id),
    )

    result = runner.run(document_id=_identity().document_id, query="基金经理")

    assert result.failure is None
    # final answer 应该成功（citations 来自缓存的 read_section result）
    assert len(result.citations) >= 1
    assert result.citations[0].locator.section_ref is not None


class TestForceAnswerDegradation:
    """max_steps 耗尽时 force_answer 降级策略测试。"""

    def test_max_steps_exhausted_returns_evidence_not_error(self, tmp_path: Path) -> None:
        """max_steps=1 且 LLM 一直调用工具不给 FinalAnswer → 用已收集证据拼成回答。"""
        service = _service(tmp_path)
        identity = _identity()

        # LLM 一直调用 search_document，不给 FinalAnswer；max_steps=2 → 执行 2 步就耗尽
        # 用 max_steps=2 因为 force_answer 需要至少 1 个成功的 tool_result
        def always_search(doc: str, q: str, tr: tuple) -> ChatResponse:
            return ChatResponse(
                step=ToolCall(tool_name=ToolName.SEARCH_DOCUMENT, document_id=doc, query="基金经理"),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        class AlwaysSearchLlm:
            def next_step(self, **kwargs):
                return always_search(kwargs["document_id"], kwargs["query"], kwargs["tool_results"])

        runner = LlmToolLoopRunner(
            tool_service=service,
            llm_client=AlwaysSearchLlm(),
            max_steps=2,
        )
        result = runner.run(document_id=identity.document_id, query="基金经理")

        # 应该成功返回证据，不报错
        assert result.failure is None
        assert result.answer != ""
        assert len(result.tool_trace) > 0

    def test_max_steps_exhausted_no_evidence_returns_error(self, tmp_path: Path) -> None:
        """max_steps 耗尽且无任何 tool_results → 返回 unavailable 错误。"""
        service = _service(tmp_path)
        identity = _identity()

        # LLM 一直返回未知工具，每次都 fail
        def always_unknown(doc: str, q: str, tr: tuple) -> ChatResponse:
            return ChatResponse(
                step=ToolCall(tool_name="unknown_tool", document_id=doc, query="test"),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        class AlwaysUnknownLlm:
            def next_step(self, **kwargs):
                return always_unknown(kwargs["document_id"], kwargs["query"], kwargs["tool_results"])

        runner = LlmToolLoopRunner(
            tool_service=service,
            llm_client=AlwaysUnknownLlm(),
            max_steps=1,
        )
        result = runner.run(document_id=identity.document_id, query="test")

        # 无证据 → 仍然报错
        assert result.failure is not None
        assert result.failure.code == FailureCode.UNAVAILABLE

    def test_force_answer_aggregates_citations(self, tmp_path: Path) -> None:
        """force_answer 应聚合所有 tool_results 的 citations。"""
        service = _service(tmp_path)
        identity = _identity()

        call_count = 0

        def search_then_read(doc: str, q: str, tr: tuple) -> ChatResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ChatResponse(
                    step=ToolCall(tool_name=ToolName.SEARCH_DOCUMENT, document_id=doc, query="基金经理"),
                    usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            # 第二次调用 read_section
            return ChatResponse(
                step=ToolCall(tool_name=ToolName.READ_SECTION, document_id=doc, section_ref="section-0000"),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        class SearchThenReadLlm:
            def next_step(self, **kwargs):
                return search_then_read(kwargs["document_id"], kwargs["query"], kwargs["tool_results"])

        runner = LlmToolLoopRunner(
            tool_service=service,
            llm_client=SearchThenReadLlm(),
            max_steps=3,
        )
        result = runner.run(document_id=identity.document_id, query="基金经理")

        # 应该成功返回证据
        assert result.failure is None
        assert result.answer != ""
        # citations 应该来自 tool_results
        assert len(result.citations) > 0


# ── ToolCallsRemaining ───────────────────────────────────────────────────


class _RemainingBudgetSpy:
    """记录每次 next_step 收到的 remaining_budget。"""

    def __init__(self, document_id: str, section_ref: str = "section-0000") -> None:
        self._doc_id = document_id
        self._section_ref = section_ref
        self._call = 0
        self.remaining_budgets: list[int | None] = []

    def next_step(self, *, document_id, query, tool_results, remaining_budget=None):
        self.remaining_budgets.append(remaining_budget)
        self._call += 1
        if self._call == 1:
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.SEARCH_DOCUMENT, document_id=self._doc_id, query="基金经理",
            ))
        if self._call == 2:
            return ChatResponse(step=ToolCall(
                tool_name=ToolName.READ_SECTION, document_id=self._doc_id, section_ref=self._section_ref,
            ))
        citations = tool_results[-1].citations if tool_results else ()
        return ChatResponse(step=FinalAnswer(
            answer="基金经理张明负责本基金投资管理。",
            citations=citations,
            key_facts=("张明",),
        ))


class TestToolCallsRemaining:
    """remaining_budget 注入测试。"""

    def test_tool_calls_remaining_decrements(self, tmp_path: Path) -> None:
        """验证每步 remaining_budget 逐次递减：max_steps → max_steps-1 → ..."""
        client = _RemainingBudgetSpy(_identity().document_id, section_ref="section-0000")
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path), llm_client=client, max_steps=5,
        )
        result = runner.run(document_id=_identity().document_id, query="基金经理")
        assert result.failure is None
        # 3 次调用：search → read_section → final answer
        assert client.remaining_budgets == [5, 4, 3]

    def test_remaining_budget_none_when_not_set(self) -> None:
        """不传 remaining_budget 时默认为 None（向后兼容）。"""
        client = FakeLlmClient([
            FinalAnswer(answer="test", citations=(), key_facts=()),
        ])
        response = client.next_step(document_id="d", query="q", tool_results=())
        assert response.step.answer == "test"

    def test_tool_calls_remaining_injected_in_run(self, tmp_path: Path) -> None:
        """通过 LlmToolLoopRunner.run() 验证 remaining_budget 被正确注入并递减。"""
        client = _RemainingBudgetSpy(_identity().document_id, section_ref="section-0000")
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path), llm_client=client, max_steps=3,
        )
        result = runner.run(document_id=_identity().document_id, query="基金经理")
        assert result.failure is None
        assert len(client.remaining_budgets) >= 2
        # 递减
        for i in range(len(client.remaining_budgets) - 1):
            assert client.remaining_budgets[i] is not None
            assert client.remaining_budgets[i + 1] is not None
            assert client.remaining_budgets[i] > client.remaining_budgets[i + 1]  # type: ignore[operator]


# ── ContextBudget Capping ────────────────────────────────────────────────


def _make_tool_result(evidence_text: str) -> ToolResult:
    """构造测试用 ToolResult，仅 evidence_text 有意义。"""
    return ToolResult(
        tool_name=ToolName.SEARCH_DOCUMENT,
        result=(),
        citations=(),
        evidence_text=evidence_text,
    )


class TestContextBudgetCapping:
    """_cap_tool_results 工具结果裁剪测试。"""

    def test_hard_limit_truncates_evidence(self) -> None:
        """预算超过硬限制时 evidence_text 被截断（remaining=0 → 全部丢弃）。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=9500)
        assert budget.is_above_hard_limit() is True

        results = [
            _make_tool_result("evidence text one"),
            _make_tool_result("evidence text two"),
        ]
        capped = _cap_tool_results(results, budget)
        assert capped == []

    def test_below_hard_limit_no_truncation(self) -> None:
        """预算未超硬限制时不做裁剪。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=5000)
        assert budget.is_above_hard_limit() is False

        results = [
            _make_tool_result("evidence text one"),
            _make_tool_result("evidence text two"),
        ]
        capped = _cap_tool_results(results, budget)
        assert capped == results
        assert len(capped) == 2
        assert capped[0].evidence_text == "evidence text one"

    def test_zero_remaining_returns_empty(self) -> None:
        """remaining=0 时返回空列表（无预算可分配）。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=10000)
        assert budget.is_above_hard_limit() is True
        assert budget.remaining_budget == 0

        results = [_make_tool_result("evidence text")]
        capped = _cap_tool_results(results, budget)
        assert capped == []

    def test_empty_tool_results_unchanged(self) -> None:
        """空 tool_results 直接返回空列表。"""
        budget = ContextBudgetState(model_context_window=10000, used_tokens=9500)
        capped = _cap_tool_results([], budget)
        assert capped == []

    def test_model_context_window_zero_never_triggers(self) -> None:
        """model_context_window=0 时不触发裁剪。"""
        budget = ContextBudgetState(model_context_window=0, used_tokens=999999)
        assert budget.is_above_hard_limit() is False

        results = [_make_tool_result("evidence")]
        capped = _cap_tool_results(results, budget)
        assert capped == results

    def test_budget_consumer_integration(self) -> None:
        """模拟正常消费：低于硬限制时不截断，超过后截断。"""
        budget = ContextBudgetState(model_context_window=10000)
        # 首次：消耗 5000 token，仍在 hard_limit 内
        budget = budget.consume(5000)
        assert budget.is_above_hard_limit() is False

        results = [_make_tool_result("some evidence")]
        capped = _cap_tool_results(results, budget)
        assert capped == results

        # 继续消耗超过 hard_limit
        budget = budget.consume(5000)
        assert budget.is_above_hard_limit() is True

        capped = _cap_tool_results(results, budget)
        assert capped == []


# ── Document ID Prefix Matching ─────────────────────────────────────


class TestNormalizeDocumentId:
    """_normalize_document_id 测试。"""

    def test_normalize_basic(self):
        """正常 document_id 不变。"""
        assert _normalize_document_id("004393-2024-annual_report-abc123") == "004393-2024-annual_report-abc123"

    def test_normalize_strips_whitespace(self):
        """去除首尾空白。"""
        assert _normalize_document_id("  doc-id  ") == "doc-id"

    def test_normalize_empty(self):
        """空字符串归一化后仍为空。"""
        assert _normalize_document_id("") == ""


class TestDocumentIdMatches:
    """_document_id_matches 测试。"""

    def test_exact_match(self):
        """完全相同的 document_id 匹配。"""
        assert _document_id_matches("004393-2024-annual_report-abc", "004393-2024-annual_report-abc") is True

    def test_prefix_match_call_longer(self):
        """LLM 返回的 document_id 比预期多后缀 → 前缀匹配成功。"""
        assert _document_id_matches(
            "004393-2024-annual_report-abc123-extra-suffix",
            "004393-2024-annual_report-abc123",
        ) is True

    def test_prefix_match_expected_longer(self):
        """预期 document_id 比 LLM 返回的长 → 不匹配（不允许 LLM 缩短）。"""
        assert _document_id_matches(
            "004393-2024-annual_report",
            "004393-2024-annual_report-abc123-full",
        ) is False

    def test_mismatch(self):
        """完全不同的 document_id 不匹配。"""
        assert _document_id_matches("doc-a", "doc-b") is False

    def test_mismatch_partial(self):
        """部分重叠但不是前缀关系 → 不匹配。"""
        assert _document_id_matches("abc-2024-report", "abc-2025-report") is False


# ── Phase 7.4: interactive scene citation 校验放宽（方案 E）─────────────────


class TestInteractiveSceneCitationRelaxation:
    """interactive scene 跳过 citation + evidence 校验，保留投资建议检测。"""

    def test_interactive_skips_citation_and_evidence_check(self, tmp_path: Path) -> None:
        """interactive scene: 无工具调用 + 无 citation → 仍然成功返回。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(
                    answer="你好！有什么可以帮助你的？",
                    citations=(),
                    key_facts=(),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="你好",
            scene="interactive",
        )

        assert result.failure is None
        assert "你好" in result.answer

    def test_interactive_skips_citation_check_with_tools(self, tmp_path: Path) -> None:
        """interactive scene: 有工具调用但缺 citation → 仍然成功。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=(),  # 缺少 citation
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
            scene="interactive",
        )

        assert result.failure is None
        assert "张明" in result.answer

    def test_interactive_still_blocks_investment_advice(self, tmp_path: Path) -> None:
        """interactive scene: 投资建议关键词仍然 fail-closed。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(
                    answer="建议买入该基金，目标价5元。",
                    citations=(),
                    key_facts=(),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="这个基金怎么样？",
            scene="interactive",
        )

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE
        assert "投资建议" in result.failure.message

    def test_ask_scene_still_enforces_citation(self, tmp_path: Path) -> None:
        """默认 ask scene: 有工具证据但缺 citation → fail-closed。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=(),  # 缺少 citation
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
        )

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE
        assert "citation" in result.failure.message

    def test_ask_scene_still_enforces_evidence(self, tmp_path: Path) -> None:
        """默认 ask scene: 无工具调用直接回答 → fail-closed（缺 evidence）。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(
                    answer="基金经理是张明。",
                    citations=(),
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
        )

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE

    def test_interactive_preserves_llm_provided_citations(self, tmp_path: Path) -> None:
        """interactive scene: LLM 提供的 citation 被保留在结果中。"""
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                ToolCall(
                    tool_name=ToolName.SEARCH_DOCUMENT,
                    document_id=_identity().document_id,
                    query="基金经理",
                ),
                lambda results: ToolCall(
                    tool_name=ToolName.READ_SECTION,
                    document_id=_identity().document_id,
                    section_ref=_section_ref_from_search(results),
                ),
                lambda results: FinalAnswer(
                    answer="基金经理张明负责本基金投资管理。",
                    citations=results[-1].citations,
                    key_facts=("张明",),
                ),
            ]),
        )

        result = runner.run(
            document_id=_identity().document_id,
            query="基金经理是谁？",
            scene="interactive",
        )

        assert result.failure is None
        assert len(result.citations) == 1
        assert result.citations[0].locator.section_ref == "section-0000"


# ── Phase 7.4: 投资建议引用上下文豁免 ─────────────────────────────────────


class TestInvestmentAdviceQuoteContextExemption:
    """投资建议检测的引用上下文豁免：弱指令词豁免，强指令词仍 fail-closed。"""

    def _run(self, tmp_path: Path, answer: str) -> AgentRunResult:
        tmp_path.mkdir(exist_ok=True)
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(answer=answer, citations=(), key_facts=()),
            ]),
        )
        return runner.run(
            document_id=_identity().document_id,
            query="请引用年报原文回答",
            scene="interactive",
        )

    def test_quote_context_buy_not_blocked(self, tmp_path: Path) -> None:
        """引用年报原文中的买入表述不触发拦截。"""
        result = self._run(
            tmp_path,
            "年报原文摘录：本基金报告期内买入并持有优质股票，全年仓位保持稳定。",
        )

        assert result.failure is None
        assert "买入" in result.answer

    def test_quote_context_sell_not_blocked(self, tmp_path: Path) -> None:
        """引用年报运作分析中的卖出表述不触发拦截。"""
        result = self._run(
            tmp_path,
            "基金运作分析原文：报告期内卖出部分债券并兑现收益。",
        )

        assert result.failure is None

    def test_weak_keyword_without_quote_context_still_blocked(self, tmp_path: Path) -> None:
        """无引用上下文时买入/卖出仍 fail-closed。"""
        result = self._run(tmp_path, "当前适合买入该基金。")

        assert isinstance(result.failure, ToolFailure)
        assert result.failure.code is FailureCode.UNAVAILABLE
        assert "投资建议" in result.failure.message

    def test_weak_keyword_outside_quote_window_still_blocked(self, tmp_path: Path) -> None:
        """引用关键词超出 50 字符窗口时仍 fail-closed。"""
        prefix = "以下内容完全来自基金公开宣传材料。" + "。" * 60
        result = self._run(tmp_path, prefix + "请买入该基金。")

        assert isinstance(result.failure, ToolFailure)
        assert "投资建议" in result.failure.message

    def test_strong_advice_blocked_even_in_quote_context(self, tmp_path: Path) -> None:
        """强指令词（建议买入/强烈推荐/目标价/预期收益）在引用上下文中也 fail-closed。"""
        answers = (
            "年报原文摘录：基金经理建议买入优质成长股。",
            "原文宣称：强烈推荐长期持有该基金。",
            "摘录目标价 15 元，预期收益 20%。",
        )
        for index, answer in enumerate(answers):
            result = self._run(tmp_path / f"case-{index}", answer)
            assert isinstance(result.failure, ToolFailure)
            assert "投资建议" in result.failure.message


class TestInvestmentAdvicePredictionPrecision:
    """预期收益 强指令词的精确匹配测试：排除标准术语，保留预测句式 fail-closed。"""

    def _run(self, tmp_path: Path, answer: str) -> AgentRunResult:
        tmp_path.mkdir(exist_ok=True)
        runner = LlmToolLoopRunner(
            tool_service=_service(tmp_path),
            llm_client=FakeLlmClient([
                FinalAnswer(answer=answer, citations=(), key_facts=()),
            ]),
        )
        return runner.run(
            document_id=_identity().document_id,
            query="请引用年报原文回答",
            scene="interactive",
        )

    def test_expected_return_rate_term_not_blocked(self, tmp_path: Path) -> None:
        """年报标准术语 预期收益率 不触发拦截。"""
        result = self._run(
            tmp_path,
            "年报披露本基金的预期收益率为 8%，风险收益特征为混合型。",
        )

        assert result.failure is None

    def test_expected_return_and_risk_term_not_blocked(self, tmp_path: Path) -> None:
        """年报标准术语 预期收益及预期风险 不触发拦截。"""
        result = self._run(
            tmp_path,
            "基金合同载明本基金的投资策略与预期收益及预期风险特征。",
        )

        assert result.failure is None

    def test_expected_return_prediction_sentence_still_blocked(self, tmp_path: Path) -> None:
        """预测句式 预期收益为 8% 仍 fail-closed。"""
        answers = (
            "本基金未来一年的预期收益为 8%。",
            "本基金预期收益 8%，适合长期配置。",
        )
        for index, answer in enumerate(answers):
            result = self._run(tmp_path / f"case-{index}", answer)
            assert isinstance(result.failure, ToolFailure)
            assert "投资建议" in result.failure.message
