"""快照报告组装 + 抽取修复回归测试（2026-08-15）。

覆盖：
1. generate_snapshot_report 章节按 chapter_id 升序组装（概览第 1 章在前；
   此前 template.chapter_ids=(1,2,3,4,0) 导致概览排最后）。
2. LLM 路径 quarter/period 透传（此前缺省导致「2026 年QNone」）。
3. _period_label None 硬化（不再输出 QNone）。
4. 半年报份额变动标签（本报告期期初/减：前缀）与业绩跨页续页合并。
5. 财务指标表目录污染过滤。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fund_agent.service.snapshot_extraction import (
    SnapshotReportData,
    _extract_financial_rows,
    _extract_performance_rows,
    _extract_share_change,
    _looks_like_stage,
    extract_snapshot_data,
)
from fund_agent.service.snapshot_generator import (
    _period_label,
    generate_snapshot_data_table,
    generate_snapshot_template_chapter,
)
from fund_agent.service.audit_pipeline import ReportGenerationCoordinator
from fund_agent.service.report_template import (
    QUARTERLY_SNAPSHOT_TEMPLATE,
    QUARTERLY_SNAPSHOT_TEMPLATE_ID,
    SEMIANNUAL_SNAPSHOT_TEMPLATE,
    SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
)


class _FakeRowResult:
    def __init__(self, rows):
        self.rows = rows


class _FakeSearchResult:
    def __init__(self, *, excerpt="", table_ref=None, section_ref=None):
        self.excerpt = excerpt
        self.table_ref = table_ref
        self.section_ref = section_ref


class _FakeTableSummary:
    def __init__(self, table_ref, caption=""):
        self.table_ref = table_ref
        self.caption = caption


class _FakeToolService:
    """最小 fake：按 query 词返回预置 search 结果，read_table 按 table_ref 返回预置表。"""

    def __init__(self, search_map, tables):
        self._search_map = search_map
        self._tables = tables

    def search_document(self, document_id, query):
        return tuple(self._search_map.get(query, ()))

    def read_table(self, document_id, table_ref, max_rows=None):
        return self._tables.get(table_ref)

    def list_tables(self, document_id, within_section_ref=None):
        return ()


class _FakeStore:
    """store 级最小薄适配（供 FundDocumentToolService 包装 extract_snapshot_data）。

    与 _FakeToolService 同构（search_map / tables），仅方法签名对齐 store 层
    （search / list_tables / read_table），使 extract_snapshot_data 的集成测试
    走真实 FundDocumentToolService 包装路径。
    """

    def __init__(self, search_map, tables):
        self._search_map = search_map
        self._tables = tables

    def search(self, query, *, within_section_ref=None, max_results=None):
        return tuple(self._search_map.get(query, ()))

    def list_tables(self, *, within_section_ref=None):
        return ()

    def read_table(self, table_ref, *, max_rows=None):
        return self._tables.get(table_ref)


class _CapturingLlmClient:
    """捕获 generate_text user_prompt 的 fake LLM client（返回无数字文本，规避数字警告）。"""

    def __init__(self) -> None:
        self.user_prompt = ""

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        self.user_prompt = user_prompt
        return "定性分析内容"


def test_period_label_no_qnone_when_quarter_missing() -> None:
    """quarter=None 时必须降级为「报告期季度缺失」，禁止输出 QNone 占位。"""

    label = _period_label(QUARTERLY_SNAPSHOT_TEMPLATE_ID, 2026, None)
    assert "QNone" not in label
    assert "2026" in label and "缺失" in label
    assert _period_label(QUARTERLY_SNAPSHOT_TEMPLATE_ID, 2026, 2) == "2026 年二季度"
    assert _period_label(SEMIANNUAL_SNAPSHOT_TEMPLATE_ID, 2025) == "2025 年上半年"


def test_period_label_semiannual_period_mapping() -> None:
    """半年报 period 必须映射 H1/H2；period 缺失默认「上半年」（F3 回归）。"""

    assert _period_label(SEMIANNUAL_SNAPSHOT_TEMPLATE_ID, 2025, period="H1") == "2025 年上半年"
    assert _period_label(SEMIANNUAL_SNAPSHOT_TEMPLATE_ID, 2025, period="H2") == "2025 年下半年"
    assert _period_label(SEMIANNUAL_SNAPSHOT_TEMPLATE_ID, 2025) == "2025 年上半年"
    # quarterly 分支不受 period 影响
    assert _period_label(QUARTERLY_SNAPSHOT_TEMPLATE_ID, 2026, 2, period="H2") == "2026 年二季度"


def test_generate_snapshot_template_chapter_period_passthrough() -> None:
    """模板降级章节必须透传 period（H2 → 「2025 年下半年」）。"""

    text = generate_snapshot_template_chapter(
        template_id=SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
        chapter_id=0,
        fund_name="财通资管价值成长混合",
        report_year=2025,
        period="H2",
        snapshot_data={},
    )
    assert "2025 年下半年" in text
    assert "2025 年上半年" not in text


def test_generate_snapshot_data_table_period_passthrough() -> None:
    """数据表格公共头必须透传 period（_snapshot_common_header 调用链）。"""

    text = generate_snapshot_data_table(
        template_id=SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
        chapter_id=1,
        fund_code="005680",
        fund_name="财通资管价值成长混合",
        report_year=2025,
        period="H2",
        snapshot_data={},
    )
    assert "2025 年下半年" in text
    assert "2025 年上半年" not in text


def test_looks_like_stage_accepts_contract_effective_rows() -> None:
    """「自基金合同生效起至今」必须识别为阶段行（此前漏识别导致半年报自成立行丢失）。"""

    assert _looks_like_stage("自基金合同生效起至今")
    assert _looks_like_stage("过去五年")
    assert not _looks_like_stage("基金简称")


def test_extract_share_change_semiannual_labels() -> None:
    """半年报 §9 份额变动（本报告期期初/总申购/减：总赎回/期末）必须抽取（A 类优先）。"""

    rows = [
        ["基金合同生效日 (2019 年 03 月 25 日 ) 基金份额总额", "480,437,691.44", "-"],
        ["本报告期期初基金份额总额", "787,727,758.47", "61,838,880.81"],
        ["本报告期基金总申购份额", "11,119,332.39", "9,091,339.59"],
        ["减：本报告期基金总赎回份额", "98,705,228.94", "6,132,135.67"],
        ["本报告期期末基金份额总额", "700,141,861.92", "64,798,084.73"],
    ]
    ts = _FakeToolService(
        search_map={
            "期初基金份额总额": (_FakeSearchResult(table_ref="table-0075"),),
        },
        tables={"table-0075": _FakeRowResult(rows)},
    )
    result = _extract_share_change(ts, "doc1")
    assert result == {
        "beginning_shares": "787,727,758.47",
        "subscriptions": "11,119,332.39",
        "redemptions": "98,705,228.94",
        "ending_shares": "700,141,861.92",
    }


def test_extract_share_change_text_fallback_regexes() -> None:
    """纯文本回退路径：4 个份额正则必须命中（此前 d/s 字面量恒 None，F2 回归）。"""

    text = (
        "本报告期期初基金份额总额 787,727,758.47 份，"
        "本报告期基金总申购份额 11,119,332.39 份，"
        "减：本报告期基金总赎回份额 98,705,228.94 份，"
        "本报告期期末基金份额总额 700,141,861.92 份。"
    )
    ts = _FakeToolService(
        search_map={
            "份额变动": (_FakeSearchResult(excerpt=text),),
        },
        tables={},
    )
    result = _extract_share_change(ts, "doc1")
    assert result == {
        "beginning_shares": "787,727,758.47",
        "subscriptions": "11,119,332.39",
        "redemptions": "98,705,228.94",
        "ending_shares": "700,141,861.92",
    }


def test_extract_snapshot_data_risk_notes_independent_from_single_investor() -> None:
    """risk_notes 必须独立抽取「风险提示」，不得复用单一投资者文本（F1 回归）。"""

    store = _FakeStore(
        search_map={
            "风险提示": (
                _FakeSearchResult(excerpt="本基金为混合型基金，投资过程中面临市场风险、信用风险和流动性风险。"),
            ),
            "单一投资者": (
                _FakeSearchResult(excerpt="报告期内，存在单一投资者持有本基金份额比例达到或超过20%的情况。"),
            ),
        },
        tables={},
    )
    data = extract_snapshot_data(
        document_id="doc-1",
        store=store,
        fund_code="005680",
        fund_name="财通资管价值成长混合",
        report_year=2026,
        template_id=QUARTERLY_SNAPSHOT_TEMPLATE_ID,
        quarter=1,
    )
    assert data.risk_notes != data.single_investor_20pct
    assert "市场风险" in data.risk_notes
    assert "单一投资者" not in data.risk_notes
    assert "20%" in data.single_investor_20pct
    assert "风险提示" not in data.single_investor_20pct


def test_extract_snapshot_data_risk_notes_missing_degrades() -> None:
    """「风险提示」未披露时必须降级为「（风险提示未披露）」（F1 回归）。"""

    store = _FakeStore(search_map={}, tables={})
    data = extract_snapshot_data(
        document_id="doc-1",
        store=store,
        fund_code="005680",
        fund_name="财通资管价值成长混合",
        report_year=2026,
        template_id=QUARTERLY_SNAPSHOT_TEMPLATE_ID,
        quarter=1,
    )
    assert data.risk_notes == "（风险提示未披露）"
    assert data.single_investor_20pct == "（单一投资者未披露）"


def test_extract_performance_rows_merges_continuation_table() -> None:
    """3.2.1 跨页拆分（A 类主表 + 无表头续页）必须合并，阶段去重保 A 类值。"""

    main = [
        ["阶段", "净值增长率①", "净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①-③", "②-④"],
        ["过去一个月", "1.45%", "0.75%", "1.84%", "0.40%", "-0.39%", "0.35%"],
        ["过去三个月", "-3.00%", "1.27%", "1.29%", "0.75%", "-4.29%", "0.52%"],
    ]
    cont = [
        ["过去六个月", "4.69%", "1.16%", "0.12%", "0.70%", "4.57%", "0.46%"],
        ["过去一年", "25.65%", "1.74%", "10.74%", "0.96%", "14.91%", "0.78%"],
        ["自基金合同生效起至今", "101.75%", "1.46%", "5.42%", "0.78%", "96.33%", "0.68%"],
    ]
    c_class = [
        ["阶段", "净值增长率①", "净值增长率标准差②", "业绩比较基准收益率③", "业绩比较基准收益率标准差④", "①-③", "②-④"],
        ["过去一个月", "1.43%", "0.75%", "1.84%", "0.40%", "-0.41%", "0.35%"],
        ["过去六个月", "4.53%", "1.16%", "0.12%", "0.70%", "4.41%", "0.46%"],
        ["自基金合同生效起至今", "-37.00%", "1.53%", "-11.78%", "0.80%", "-25.22%", "0.73%"],
    ]
    ts = _FakeToolService(
        search_map={},
        tables={
            "table-0010": _FakeRowResult(main),
            "table-0011": _FakeRowResult(cont),
            "table-0012": _FakeRowResult(c_class),
        },
    )
    # list_tables 返回全部表（供 _find_performance_tables 扫描）
    ts.list_tables = lambda document_id, within_section_ref=None: (
        _FakeTableSummary("table-0010", "第 7 页"),
        _FakeTableSummary("table-0011", ""),
        _FakeTableSummary("table-0012", ""),
    )
    rows = _extract_performance_rows(ts, "doc1")
    stages = [r.stage for r in rows]
    assert stages == ["过去一个月", "过去三个月", "过去六个月", "过去一年", "自基金合同生效起至今"]
    by_stage = {r.stage: r for r in rows}
    # A 类值（主表+续页）优先：六个月 4.69% 而非 C 类 4.53%
    assert by_stage["过去六个月"].nav_growth_rate == "4.69%"
    assert by_stage["自基金合同生效起至今"].nav_growth_rate == "101.75%"


def test_extract_financial_rows_filters_toc_and_picks_indicators() -> None:
    """财务指标抽取必须过滤目录表，只取真实 3.1 指标行。"""

    # 真实目录行：点线引导符与页码嵌在首列（实证 005680-2025 半年报 TOC）
    toc = [
        ["1.1重要提示...............................................................2", "", ""],
        ["§3主要财务指标和基金净值表现...................................6", "", ""],
        ["3.1主要会计数据和财务指标....................................6", "", ""],
    ]
    fin = [
        ["", "混合A", "混合C"],
        ["本期已实现收益", "-42,732,436.28", "-3,813,875.66"],
        ["本期利润", "68,147,402.68", "5,209,787.83"],
        ["加权平均基金份额本期利润", "0.0896", "0.0819"],
        ["期末基金资产净值", "1,412,557,244.50", "129,342,908.04"],
    ]
    ts = _FakeToolService(
        search_map={
            "主要会计数据和财务指标": (
                _FakeSearchResult(table_ref="table-0000"),
                _FakeSearchResult(table_ref="table-0009"),
            ),
        },
        tables={
            "table-0000": _FakeRowResult(toc),
            "table-0009": _FakeRowResult(fin),
        },
    )
    rows = _extract_financial_rows(ts, "doc1")
    items = [r["item"] for r in rows]
    assert "1.1重要提示" not in items
    assert "§3主要财务指标" not in items
    assert items == ["本期已实现收益", "本期利润", "加权平均基金份额本期利润", "期末基金资产净值"]
    assert rows[0]["current"] == "-42,732,436.28"
    assert rows[0]["previous"] == "—"


def test_snapshot_report_chapters_sorted_and_quarter_propagated(monkeypatch, tmp_path: Path) -> None:
    """generate_snapshot_report（LLM 路径）：章节按 chapter_id 升序，quarter 透传到 coordinator。"""

    from fund_agent.service import SnapshotReportRequest
    from fund_agent.service.extraction import FundReadingService

    class _FakeRepo:
        def list_reports(self):
            return [{
                "fund_code": "005680",
                "report_type": "quarterly_report",
                "year": 2026,
                "quarter": 2,
                "document_id": "doc-1",
                "fund_name": "财通资管价值成长混合",
            }]

        def load_store(self, document_id):
            return object()

    captured: dict = {}

    def _fake_extract(**kwargs):
        return SnapshotReportData(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
            template_id=QUARTERLY_SNAPSHOT_TEMPLATE_ID, quarter=2,
        )

    class _FakeCoordinator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def generate_report(self, **kwargs):
            captured.update(kwargs)
            return {1: "## 业绩内容", 2: "## 持仓内容", 3: "## 管理人内容", 4: "## 风险内容", 0: "## 概览内容"}, []

    monkeypatch.setattr("fund_agent.service.extraction._repository", lambda wd: _FakeRepo())
    monkeypatch.setattr("fund_agent.service.snapshot_extraction.extract_snapshot_data", _fake_extract)
    monkeypatch.setattr("fund_agent.service.audit_pipeline.ReportGenerationCoordinator", _FakeCoordinator)

    service = FundReadingService()
    result = service.generate_snapshot_report(
        SnapshotReportRequest(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
            report_type="quarterly_report", quarter=2, work_dir=Path(tmp_path),
            output_format="json",
        ),
        llm_client=object(),
    )
    assert result.failure is None, result.failure
    chapter_ids = [c.chapter_id for c in result.report.chapters]
    assert chapter_ids == [0, 1, 2, 3, 4], chapter_ids
    assert captured.get("quarter") == 2
    assert captured.get("period") is None


def test_snapshot_report_semiannual_period_propagated(monkeypatch, tmp_path: Path) -> None:
    """半年报 LLM 路径 period 必须为 H1（数据表格报告期正确的前提）。"""

    from fund_agent.service import SnapshotReportRequest
    from fund_agent.service.extraction import FundReadingService

    class _FakeRepo:
        def list_reports(self):
            return [{
                "fund_code": "005680",
                "report_type": "semiannual_report",
                "year": 2025,
                "quarter": None,
                "document_id": "doc-2",
                "fund_name": "财通资管价值成长混合",
            }]

        def load_store(self, document_id):
            return object()

    captured: dict = {}

    def _fake_extract(**kwargs):
        return SnapshotReportData(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2025,
            template_id=SEMIANNUAL_SNAPSHOT_TEMPLATE_ID, period="H1",
        )

    class _FakeCoordinator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def generate_report(self, **kwargs):
            captured.update(kwargs)
            return {1: "## 业绩", 2: "## 持仓", 3: "## 财务", 4: "## 管理人", 5: "## 风险", 0: "## 概览"}, []

    monkeypatch.setattr("fund_agent.service.extraction._repository", lambda wd: _FakeRepo())
    monkeypatch.setattr("fund_agent.service.snapshot_extraction.extract_snapshot_data", _fake_extract)
    monkeypatch.setattr("fund_agent.service.audit_pipeline.ReportGenerationCoordinator", _FakeCoordinator)

    service = FundReadingService()
    result = service.generate_snapshot_report(
        SnapshotReportRequest(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2025,
            report_type="semiannual_report", work_dir=Path(tmp_path),
            output_format="json",
        ),
        llm_client=object(),
    )
    assert result.failure is None, result.failure
    chapter_ids = [c.chapter_id for c in result.report.chapters]
    assert chapter_ids == [0, 1, 2, 3, 4, 5], chapter_ids
    # period 由 service 按 report_type 推导为 H1 并透传 coordinator
    assert captured.get("quarter") is None
    assert captured.get("period") == "H1"


def test_chapter_summary_injection_follows_template_front_ids(tmp_path: Path) -> None:
    """摘要注入必须按 template.front_chapter_ids 驱动（quarterly 不注入 Ch5/Ch6，semiannual 不注入 Ch6）。

    旧代码 `for cid in range(1, 7)` 会把 Ch5/Ch6 摘要注入快照 prompt，本测试可证伪该逻辑。
    """

    summaries = {cid: f"摘要{cid}" for cid in range(1, 7)}

    def _run(template):
        fake = _CapturingLlmClient()
        coordinator = ReportGenerationCoordinator(
            llm_client=fake, work_dir=tmp_path, template=template,
        )
        coordinator._generate_chapter_content(
            chapter_id=0,
            fund_code="005680",
            fund_name="财通资管价值成长混合",
            report_year=2025,
            data_table="",
            performance={},
            holdings={},
            allocation={},
            fees={},
            use_chapter_summaries=True,
            chapter_summaries=summaries,
            llm_client=fake,
        )
        return fake.user_prompt

    quarterly_prompt = _run(QUARTERLY_SNAPSHOT_TEMPLATE)
    assert "### Ch4 摘要" in quarterly_prompt
    assert "### Ch5 摘要" not in quarterly_prompt
    assert "### Ch6 摘要" not in quarterly_prompt

    semiannual_prompt = _run(SEMIANNUAL_SNAPSHOT_TEMPLATE)
    assert "### Ch5 摘要" in semiannual_prompt
    assert "### Ch6 摘要" not in semiannual_prompt


# ============================================================
# 报告级装配审计（2026-08-15）：verify_report_assembly + 快照 fail-closed
# ============================================================


def _make_chapter(chapter_id: int, title: str, content: str = "章节内容") -> object:
    from fund_agent.service.models import ReportChapter
    return ReportChapter(
        chapter_id=chapter_id, title=title, content=content, data_sources=(),
    )


def test_verify_report_assembly_correct_assembly_passes() -> None:
    """正确装配（集合/顺序/标题全一致）→ pass。"""
    from fund_agent.service.audit_pipeline import verify_report_assembly

    chapters = [
        _make_chapter(0, "概览"),
        _make_chapter(1, "当期业绩与超额"),
        _make_chapter(2, "持仓与资产配置"),
        _make_chapter(3, "管理人动作"),
        _make_chapter(4, "风险与跟踪"),
    ]
    ok, problems = verify_report_assembly(QUARTERLY_SNAPSHOT_TEMPLATE, chapters)
    assert ok is True
    assert problems == []


def test_verify_report_assembly_reordered_fails() -> None:
    """乱序（展示顺序 != sorted(chapter_ids)）→ fail。"""
    from fund_agent.service.audit_pipeline import verify_report_assembly

    chapters = [
        _make_chapter(1, "当期业绩与超额"),
        _make_chapter(0, "概览"),
        _make_chapter(2, "持仓与资产配置"),
        _make_chapter(3, "管理人动作"),
        _make_chapter(4, "风险与跟踪"),
    ]
    ok, problems = verify_report_assembly(QUARTERLY_SNAPSHOT_TEMPLATE, chapters)
    assert ok is False
    assert any("顺序" in p for p in problems)


def test_verify_report_assembly_missing_chapter_fails() -> None:
    """缺章（集合 != template.chapter_ids）→ fail。"""
    from fund_agent.service.audit_pipeline import verify_report_assembly

    chapters = [
        _make_chapter(0, "概览"),
        _make_chapter(1, "当期业绩与超额"),
        _make_chapter(2, "持仓与资产配置"),
        _make_chapter(3, "管理人动作"),
    ]
    ok, problems = verify_report_assembly(QUARTERLY_SNAPSHOT_TEMPLATE, chapters)
    assert ok is False
    assert any("缺章" in p for p in problems)


def test_verify_report_assembly_extra_chapter_fails() -> None:
    """多章（超出模板章节集合）→ fail。"""
    from fund_agent.service.audit_pipeline import verify_report_assembly

    chapters = [
        _make_chapter(0, "概览"),
        _make_chapter(1, "当期业绩与超额"),
        _make_chapter(2, "持仓与资产配置"),
        _make_chapter(3, "管理人动作"),
        _make_chapter(4, "风险与跟踪"),
        _make_chapter(5, "多余章节"),
    ]
    ok, problems = verify_report_assembly(QUARTERLY_SNAPSHOT_TEMPLATE, chapters)
    assert ok is False
    assert any("多章" in p for p in problems)


def test_verify_report_assembly_wrong_title_fails() -> None:
    """标题与模板 manifest 不一致 → fail。"""
    from fund_agent.service.audit_pipeline import verify_report_assembly

    chapters = [
        _make_chapter(0, "概览"),
        _make_chapter(1, "错误标题"),
        _make_chapter(2, "持仓与资产配置"),
        _make_chapter(3, "管理人动作"),
        _make_chapter(4, "风险与跟踪"),
    ]
    ok, problems = verify_report_assembly(QUARTERLY_SNAPSHOT_TEMPLATE, chapters)
    assert ok is False
    assert any("标题" in p for p in problems)


def test_verify_report_assembly_empty_content_warns_only() -> None:
    """内容为空 → 仅 warning，不 fail。"""
    from fund_agent.service.audit_pipeline import verify_report_assembly

    chapters = [
        _make_chapter(0, "概览", content=""),
        _make_chapter(1, "当期业绩与超额"),
        _make_chapter(2, "持仓与资产配置"),
        _make_chapter(3, "管理人动作"),
        _make_chapter(4, "风险与跟踪"),
    ]
    ok, problems = verify_report_assembly(QUARTERLY_SNAPSHOT_TEMPLATE, chapters)
    assert ok is True
    assert any("内容为空" in p for p in problems)


def test_generate_snapshot_report_missing_chapter_fails_closed(monkeypatch, tmp_path: Path) -> None:
    """coordinator 返回缺章 chapter_contents → generate_snapshot_report 返回 schema_drift。

    旧行为：模板驱动装配把缺失章节落成空内容照常产出，本测试可证伪。
    """

    from fund_agent.service import SnapshotReportRequest
    from fund_agent.service.extraction import FundReadingService

    class _FakeRepo:
        def list_reports(self):
            return [{
                "fund_code": "005680",
                "report_type": "quarterly_report",
                "year": 2026,
                "quarter": 2,
                "document_id": "doc-1",
                "fund_name": "财通资管价值成长混合",
            }]

        def load_store(self, document_id):
            return object()

    def _fake_extract(**kwargs):
        return SnapshotReportData(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
            template_id=QUARTERLY_SNAPSHOT_TEMPLATE_ID, quarter=2,
        )

    class _FakeCoordinator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def generate_report(self, **kwargs):
            # 缺 Ch0 概览
            return {1: "## 业绩内容", 2: "## 持仓内容", 3: "## 管理人内容", 4: "## 风险内容"}, []

    monkeypatch.setattr("fund_agent.service.extraction._repository", lambda wd: _FakeRepo())
    monkeypatch.setattr("fund_agent.service.snapshot_extraction.extract_snapshot_data", _fake_extract)
    monkeypatch.setattr("fund_agent.service.audit_pipeline.ReportGenerationCoordinator", _FakeCoordinator)

    service = FundReadingService()
    result = service.generate_snapshot_report(
        SnapshotReportRequest(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2026,
            report_type="quarterly_report", quarter=2, work_dir=Path(tmp_path),
            output_format="json",
        ),
        llm_client=object(),
    )
    assert result.failure is not None
    assert result.failure.code == "schema_drift"
    assert "缺章" in result.failure.message
    assert result.report is None


def test_generate_snapshot_report_extra_chapter_fails_closed(monkeypatch, tmp_path: Path) -> None:
    """coordinator 返回多章 chapter_contents → generate_snapshot_report 返回 schema_drift。"""

    from fund_agent.service import SnapshotReportRequest
    from fund_agent.service.extraction import FundReadingService

    class _FakeRepo:
        def list_reports(self):
            return [{
                "fund_code": "005680",
                "report_type": "semiannual_report",
                "year": 2025,
                "quarter": None,
                "document_id": "doc-2",
                "fund_name": "财通资管价值成长混合",
            }]

        def load_store(self, document_id):
            return object()

    def _fake_extract(**kwargs):
        return SnapshotReportData(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2025,
            template_id=SEMIANNUAL_SNAPSHOT_TEMPLATE_ID, period="H1",
        )

    class _FakeCoordinator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def generate_report(self, **kwargs):
            # 半年报模板只有 0-5，多出 Ch6
            return {0: "## 概览", 1: "## 业绩", 2: "## 持仓", 3: "## 财务", 4: "## 管理人", 5: "## 风险", 6: "## 多余"}, []

    monkeypatch.setattr("fund_agent.service.extraction._repository", lambda wd: _FakeRepo())
    monkeypatch.setattr("fund_agent.service.snapshot_extraction.extract_snapshot_data", _fake_extract)
    monkeypatch.setattr("fund_agent.service.audit_pipeline.ReportGenerationCoordinator", _FakeCoordinator)

    service = FundReadingService()
    result = service.generate_snapshot_report(
        SnapshotReportRequest(
            fund_code="005680", fund_name="财通资管价值成长混合", report_year=2025,
            report_type="semiannual_report", work_dir=Path(tmp_path),
            output_format="json",
        ),
        llm_client=object(),
    )
    assert result.failure is not None
    assert result.failure.code == "schema_drift"
    assert "多章" in result.failure.message
    assert result.report is None
