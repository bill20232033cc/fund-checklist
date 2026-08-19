"""基金年报阅读 use case Service 边界。"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fund_agent.agent import AgentRunResult, MinimalFundDocumentAgent, LlmToolLoopRunner, DeepSeekLlmClient, FakeLlmClient
from fund_agent.agent.stream_events import StreamEvent, StreamEventType
from fund_agent.fund.document_tools.constants import (
    DOCLING_JSON_SUFFIX,
    FailureCode,
    LocatorKind,
    ReportType,
)
from fund_agent.fund.document_tools.docling_converter import DoclingConverter, make_docling_json_ref
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.local_pdf_source import LocalPdfSourceProvider
from fund_agent.fund.document_tools.models import (
    Citation,
    Locator,
    PdfImportRequest,
    PdfImportResult,
    ReportSummary,
    TableContent,
    TableSummary,
    ToolFailure,
)
from fund_agent.fund.document_tools.persistent_repository import (
    CATALOG_FILENAME,
    CATALOG_SCHEMA_VERSION,
    FilesystemReportRepository,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.host import MinimalHost

from .models import (
    AggregateMultiYearAnnualPerformanceRequest,
    AggregateMultiYearAnnualPerformanceResult,
    AnnualAllocationResult,
    AskQuestionRequest,
    AskQuestionResult,
    AnnualExcessReturnExtraction,
    AnnualFeeResult,
    AnnualHoldingsResult,
    AnnualPerformanceExtraction,
    AnnualPerformanceFieldCitation,
    AnnualReportDocument,
    FundCodeResolution,
    SnapshotReportDocument,
    SnapshotResolution,
    AssetAllocationItem,
    ChapterEvidence,
    DeepAuditItem,
    DeepAuditRequest,
    DeepAuditResult,
    DisclosureAuditItem,
    DisclosureAuditRequest,
    DisclosureAuditResult,
    ExtractAllocationRequest,
    ExtractAllocationResult,
    ExtractAnnualExcessReturnResult,
    ExtractAnnualPerformanceResult,
    ExtractFeeRatesMultiYearRequest,
    ExtractFeeRatesMultiYearResult,
    ExtractFeeRatesResult,
    ExtractPerformanceReturnsResult,
    ExtractHoldingsRequest,
    ExtractHoldingsResult,
    FeeRateExtraction,
    FeeRateItem,
    FundManagerInfo,
    FundReport,
    GenerateReportRequest,
    GenerateReportResult,
    SnapshotReportRequest,
    SnapshotReportResult,
    HoldingExtraction,
    IndustryAllocationItem,
    ThresholdEvent,
    MultiYearAllocationSeries,
    MultiYearAnnualPerformanceRow,
    MultiYearAnnualPerformanceSeries,
    MultiYearFeeSeries,
    MultiYearHoldingsSeries,
    MultiYearMissingYearNote,
    PerformanceReturnExtraction,
    QueryRouteAttempt,
    QueryRouteResultKind,
    RiskChecklistItem,
    SignalIndicator,
    SignalJudgment,
    _ROUTE_RESULT_FAILURE,
    _ROUTE_RESULT_SUCCESS,
    ReportChapter,
    ScaleInfo,
    StressTestResult,
    _DisclosureLocatorContract,
)

from .chapter_generator import LlmChapterGenerator, generate_evidence_section
from .signal_scoring import (
    _holdings_overlap_rate,
    _parse_aum_yi,
    _parse_percent,
    _ScoredIndicator,
    score_concentration,
    score_excess_returns,
    score_fee_rate,
    score_manager_change,
    score_scale_risk,
    score_style_drift,
    to_risk_item,
    to_signal_indicator,
)


logger = logging.getLogger(__name__)


HostFactory = Callable[[FundDocumentToolService], MinimalHost]
RunnerFactory = Callable[[FundDocumentToolService], LlmToolLoopRunner]

PDF_BLOB_DIRNAME = "pdf_blobs"
DOCLING_JSON_DIRNAME = "docling_json"

# 候选上限 = 原始 query + 受控候选；manager_holdings 的候选词经 2026-08-05
# interactive 质量修复裁决扩为 4 个（design.md §6.10），故上限调整为 5。
_MAX_QUERY_CANDIDATES = 5
_TARGET_NOT_FOUND_MESSAGE = "未找到符合受控披露目标的证据"
_TABLE_TITLE_PREFIX = "表格标题:"
_SECTION_TITLE_PREFIX = "来源章节:"
_TABLE_BLOCK_HEADER = "相关表格:"
_FEE_RATES_QUERY = "费用"
_FEE_RATE_PERIOD_YEAR = "year"
_FEE_RATE_TITLES = ("基金管理费", "基金托管费", "销售服务费")
# QDII 年报把管理费表述为「管理人报酬」（正文无「基金管理费/管理费」字样），
# 该措辞只作为费率标题块查找别名；不进入 _FEE_RATE_TITLES —— 10B 三标题契约
# （_fee_rate_segments / _fee_rate_section_citations）依赖固定三标题。
_FEE_RATE_MANAGEMENT_WORDINGS = ("基金管理费", "管理人报酬")
# 回退路径 fail-closed 放行条件：仅当正文含明确 QDII 管理费费率句时，
# 允许从 section title 未命中费率名的大章节（如 7.4.9 关联方关系）抽取。
_MANAGEMENT_FEE_QDII_WORDING_RE = re.compile(r"管理人报酬[^。\n]{0,80}?\d+\.\d+%")

from .investment_guard import INVESTMENT_ADVICE_KEYWORDS, contains_investment_advice

_PDF_ENGINE_PANDOC = "pandoc"
_PDF_ENGINE_XELATEX = "xelatex"
_PDF_GOOGLE_CHROME_BIN = "google-chrome"
_PDF_CHROME_MACOS_DEFAULT = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_PDF_A4_WINDOW_SIZE = "794,1123"
_PDF_CHROME_TIMEOUT_SECONDS = 120
_PDF_XELATEX_TIMEOUT_SECONDS = 1800
_PDF_WARNING_PANDOC_MISSING = "pandoc 未安装，已回退为 Markdown 格式"
_PDF_WARNING_EXPORT_FAILED = "PDF 导出失败，已回退为 Markdown 格式"

_INVESTMENT_ADVICE_MESSAGE = "routing context 包含投资建议关键词，拒绝回答"
_PERFORMANCE_RETURNS_QUERY = "净值增长率"
_PERFORMANCE_RETURN_PERIOD_PAST_1_YEAR = "past_1_year"
_PERFORMANCE_RETURN_PERIOD_TEXT = "过去一年"
_PERFORMANCE_TABLE_MAX_ROWS = 20
_ANNUAL_PERFORMANCE_TITLE_FAMILY = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
_FEE_RATE_NO_CHARGE_TEXT = "不收取"
_FIELD_MANAGEMENT_FEE_RATE = "management_fee_rate"
_FIELD_CUSTODIAN_FEE_RATE = "custodian_fee_rate"
_FIELD_SALES_SERVICE_FEE_RATE = "sales_service_fee_rate"
_FIELD_NAV_GROWTH_RATE = "nav_growth_rate"
_FIELD_BENCHMARK_RETURN_RATE = "benchmark_return_rate"
_FIELD_ANNUAL_NAV_GROWTH_RATE = "annual_nav_growth_rate"
_FIELD_ANNUAL_BENCHMARK_RETURN_RATE = "annual_benchmark_return_rate"
_FIELD_ANNUAL_EXCESS_RETURN = "annual_excess_return"
_ANNUAL_EXCESS_RETURN_COLUMN_LABEL = "①－③"
_MULTI_YEAR_MINIMUM_COMPLETE_YEARS = 3
_MULTI_YEAR_MAXIMUM_COMPLETE_YEARS = 5
_COVERAGE_STATUS_COMPLETE = "complete"
_COVERAGE_STATUS_PARTIAL = "partial"
_SHARE_SCOPE_ALL = "all_share_classes"
_SHARE_SCOPE_A = "A"
_SHARE_SCOPE_C = "C"
_SHARE_CLASS_SCOPES = (_SHARE_SCOPE_A, _SHARE_SCOPE_C)

_HOLDINGS_TOP_N = 10
_HOLDINGS_QUERY = "股票投资明细"
_BOND_HOLDINGS_QUERY = "前五名债券投资明细"
_QDII_HOLDINGS_QUERY = "所有权益投资明细"
_HOLDINGS_TABLE_MAX_ROWS = 15

# P0-1/Fix C 受控表锚点（interactive 检索命中质量，D1/D2 硬口径）：
# manager_holdings 按 9.4/9.2 行头标题族匹配（9.4 优先、9.2 回退），
# holdings_top10 按表头签名（序号/股票名称/公允价值，row_count >= 10）匹配，
# performance_returns 按 3.2.1 表头签名（阶段/份额净值增长率/业绩比较基准
# 收益率）匹配且 A 类标题优先（Mimo 根因 review Fix C）。
_ANCHOR_TABLE_MAX_ROWS = 10
_ANCHOR_MANAGER_HOLDS_9_4_TITLE_FAMILY = "本基金基金经理持有本开放式基金"
_ANCHOR_MANAGER_HOLDS_9_2_TITLE_FAMILY = "基金管理人所有从业人员持有本基金"
_ANCHOR_MANAGER_HOLDS_TITLE_FAMILY = (
    _ANCHOR_MANAGER_HOLDS_9_4_TITLE_FAMILY,
    _ANCHOR_MANAGER_HOLDS_9_2_TITLE_FAMILY,
)
_ANCHOR_MANAGER_HOLDS_SECTION_QUERIES = (
    "期末基金管理人的从业人员持有本基金的情况",
    _ANCHOR_MANAGER_HOLDS_9_4_TITLE_FAMILY,
    _ANCHOR_MANAGER_HOLDS_9_2_TITLE_FAMILY,
)
_ANCHOR_HOLDINGS_TOP10_HEADER_SIGNATURE = ("序号", "股票名称", "公允价值")
_ANCHOR_HOLDINGS_TOP10_MIN_ROWS = 10
_ANCHOR_HOLDINGS_TOP10_SECTION_QUERIES = (
    "前十名股票投资明细",
    "股票投资明细",
)
_ANCHOR_PERFORMANCE_RETURNS_HEADER_SIGNATURE = ("阶段", "份额净值增长率", "业绩比较基准收益率")
_ANCHOR_PERFORMANCE_RETURNS_SECTION_QUERIES = (
    "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
)


DISCLOSURE_LOCATOR_CONTRACT_REGISTRY = (
    _DisclosureLocatorContract(
        profile_name="holdings_top10",
        aliases=("前十大持仓", "重仓股", "持仓明细"),
        candidate_queries=("股票投资明细", "前十名股票投资明细"),
        acceptable_title_family=("股票投资明细", "前十名股票投资明细"),
        requires_table_citation=True,
        extraction_allowed=False,
        anchor_title_family=_ANCHOR_HOLDINGS_TOP10_HEADER_SIGNATURE,
    ),
    _DisclosureLocatorContract(
        profile_name="asset_allocation",
        aliases=("资产配置", "资产组合"),
        candidate_queries=("期末基金资产组合情况", "基金资产组合情况"),
        acceptable_title_family=("期末基金资产组合情况", "基金资产组合情况"),
        requires_table_citation=True,
        extraction_allowed=False,
    ),
    _DisclosureLocatorContract(
        profile_name="manager_holdings",
        aliases=("持有本基金", "基金经理持有", "从业人员持有本基金"),
        candidate_queries=(
            "持有本基金",
            "基金经理持有",
            "期末基金管理人的从业人员持有本基金",
            "基金经理持有本基金",
        ),
        acceptable_title_family=("期末基金管理人的从业人员持有本基金的情况",),
        requires_table_citation=True,
        extraction_allowed=False,
        anchor_title_family=_ANCHOR_MANAGER_HOLDS_TITLE_FAMILY,
    ),
    _DisclosureLocatorContract(
        profile_name="fee_rates",
        aliases=("费用", "费率", "管理费", "托管费", "销售服务费"),
        candidate_queries=("基金管理费", "基金托管费", "销售服务费"),
        acceptable_title_family=("基金管理费", "基金托管费", "销售服务费"),
        requires_table_citation=False,
        extraction_allowed=False,
        aggregate_all_matches=True,
    ),
    _DisclosureLocatorContract(
        profile_name="performance_returns",
        aliases=(
            "净值增长率",
            "业绩比较基准收益率",
            "基准收益率",
            "收益表现",
            "基金净值表现",
            # 2026-08-14 第4个任务：performance 类词面收口。
            # 匹配机制为子串包含（any(alias in query ...)），「超额表现」
            # 经「超额」子串 alias 命中（非「超额收益/超额收益率」）。
            "超额收益",
            "超额收益率",
            "超额",
            "净值表现",
        ),
        candidate_queries=(
            "净值增长率",
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "基金净值表现",
            "业绩比较基准收益率",
        ),
        acceptable_title_family=(
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "基金净值表现",
        ),
        requires_table_citation=True,
        extraction_allowed=False,
        anchor_title_family=_ANCHOR_PERFORMANCE_RETURNS_HEADER_SIGNATURE,
    ),
    # 2026-08-14 快照（§6.25 裁决 9）：季报/半年报当期业绩受控 profile，
    # 独立 title-family + table anchor；不污染 10G annual 契约。
    # extraction_allowed=False 口径与 performance_returns 一致（受控检索/锚点用途），
    # 快照确定性抽取在 Service 层按 template_id 独立实现（snapshot_extraction.py）。
    _DisclosureLocatorContract(
        profile_name="quarterly_performance",
        aliases=("季报业绩", "季报净值", "当期业绩"),
        candidate_queries=(
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "净值增长率",
            "业绩比较基准收益率",
        ),
        acceptable_title_family=(
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "基金净值表现",
        ),
        requires_table_citation=True,
        extraction_allowed=False,
        anchor_title_family=_ANCHOR_PERFORMANCE_RETURNS_HEADER_SIGNATURE,
    ),
    _DisclosureLocatorContract(
        profile_name="semiannual_performance",
        aliases=("半年报业绩", "半年报净值", "中期业绩"),
        candidate_queries=(
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "净值增长率",
            "业绩比较基准收益率",
        ),
        acceptable_title_family=(
            "基金份额净值增长率及其与同期业绩比较基准收益率的比较",
            "基金净值表现",
        ),
        requires_table_citation=True,
        extraction_allowed=False,
        anchor_title_family=_ANCHOR_PERFORMANCE_RETURNS_HEADER_SIGNATURE,
    ),
)


# --- 阈值事件 tier-delta 算法 ---

# 每个指标的离散得分档位（从低到高），用于计算一档跳变的 raw points 增量。
# 与 signal_scoring.py 中的评分规则完全同源。
_INDICATOR_TIERS: dict[str, tuple[int, ...]] = {
    "超额收益趋势": (0, 5, 15, 25),
    "费率水平": (0, 5, 15, 25),
    "风格漂移": (0, 5, 15, 25),
    "规模风险": (0, 15, 25),
    "基金经理变更": (0, 20),
    "持仓集中度": (0, 5, 10, 15),
}

# 基金名称关键词 → 类型标签，first-match-wins。
PRODUCT_TYPE_RULES: list[tuple[str, str]] = [
    ("沪深300", "沪深300指数基金"),
    ("中证500", "中证500指数基金"),
    ("创业板", "创业板指数基金"),
    ("债券", "债券基金"),
    ("混合", "混合型基金"),
    ("股票", "股票型基金"),
]


def _next_tier_up(name: str, current: int) -> int | None:
    """返回当前得分的上一档分数；已满档时返回 None。"""
    tiers = _INDICATOR_TIERS.get(name)
    if tiers is None:
        return None
    for t in tiers:
        if t > current:
            return t
    return None


def _next_tier_down(name: str, current: int) -> int | None:
    """返回当前得分的下一档分数；已最低档时返回 None。"""
    tiers = _INDICATOR_TIERS.get(name)
    if tiers is None:
        return None
    for t in reversed(tiers):
        if t < current:
            return t
    return None


def _compute_threshold_events(
    scored: list,
) -> tuple[ThresholdEvent | None, ThresholdEvent | None]:
    """从评分结果计算升级/降级阈值事件（F1 + F2 修复版）。

    F1 算法：tier-delta 驱动
    - 升级：找一档改善后 raw points 增量最大的指标
    - 降级：找一档恶化后 raw points 损失最大的指标

    F2 边界：
    - data_completeness < 0.5 → 两者均 None
    - 全部满分 → upgrade_event=None
    - 全部零分 → downgrade_event=None

    参数:
        scored: _ScoredIndicator 列表。

    返回:
        (upgrade_event, downgrade_event)。
    """
    calculable = [s for s in scored if s.calculable]
    if len(calculable) / len(scored) < 0.5:
        return None, None

    # --- 升级事件 ---
    upgrade_event: ThresholdEvent | None = None
    non_full = [s for s in calculable if s.score < s.max_score]
    if not non_full:
        # 全部满分：upgrade_event = None（F2）
        upgrade_event = None
    else:
        best = None
        best_delta = 0
        for s in non_full:
            next_up = _next_tier_up(s.name, s.score)
            if next_up is not None:
                delta = next_up - s.score
                if delta > best_delta or (delta == best_delta and best is None):
                    best = s
                    best_delta = delta
        if best is not None and best_delta > 0:
            next_up = _next_tier_up(best.name, best.score)
            upgrade_event = ThresholdEvent(
                direction="upgrade",
                indicator_name=best.name,
                current_score=best.score,
                target_score=best.max_score,
                tier_delta=best_delta,
                description=(
                    f"{best.name}（{best.score}/{best.max_score}）"
                    f"跳一档至 {next_up} 可带来 +{best_delta} raw points，"
                    f"是当前对升级贡献最大的指标"
                ),
            )

    # --- 降级事件 ---
    downgrade_event: ThresholdEvent | None = None
    non_zero = [s for s in calculable if s.score > 0]
    if not non_zero:
        # 全部零分：downgrade_event = None（F2）
        downgrade_event = None
    else:
        worst = None
        worst_delta = 0
        for s in non_zero:
            next_down = _next_tier_down(s.name, s.score)
            if next_down is not None:
                delta = s.score - next_down
                if delta > worst_delta or (delta == worst_delta and worst is None):
                    worst = s
                    worst_delta = delta
        if worst is not None and worst_delta > 0:
            next_down = _next_tier_down(worst.name, worst.score)
            downgrade_event = ThresholdEvent(
                direction="downgrade",
                indicator_name=worst.name,
                current_score=worst.score,
                target_score=0,
                tier_delta=worst_delta,
                description=(
                    f"{worst.name}（{worst.score}/{worst.max_score}）"
                    f"掉一档至 {next_down} 将损失 -{worst_delta} raw points，"
                    f"是当前对降级风险最大的指标"
                ),
            )

    return upgrade_event, downgrade_event


def compute_product_definition(
    fund_name: str,
    fund_code: str,
    fund_manager: FundManagerInfo | None = None,
) -> str:
    """确定性生成一句话产品定义。

    规则:
    1. 从 fund_name 按 PRODUCT_TYPE_RULES 匹配基金类型（first-match-wins）。
    2. 拼接为 "{fund_name}（{fund_code}）是一只{类型标签}"。
    3. 有经理时追加 "，由{经理名}管理"。
    4. 无匹配时退化为 "{fund_name}（{fund_code}）是一只基金"。

    参数:
        fund_name: 基金名称。
        fund_code: 基金代码。
        fund_manager: 基金经理信息（可选）。

    返回:
        一句话产品定义字符串。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """
    fund_type = "基金"
    for keyword, label in PRODUCT_TYPE_RULES:
        if keyword in fund_name:
            fund_type = label
            break

    parts = [f"{fund_name}（{fund_code}）是一只{fund_type}"]
    if fund_manager:
        parts.append(f"，由{fund_manager.name}管理")
    return "".join(parts)


@dataclass(frozen=True)
class _FeeRateExtractionSpec:
    """Service 内部 fee_rates 字段抽取规则。"""

    field_name: str
    title: str
    share_class_scope: str
    pattern: re.Pattern[str]
    controlled_value: str | None = None


@dataclass(frozen=True)
class _PerformanceReturnExtractionSpec:
    """Service 内部 performance_returns 字段抽取规则。"""

    field_name: str
    column_keywords: tuple[str, ...]
    excluded_keywords: tuple[str, ...] = ()


_FEE_RATE_EXTRACTION_SPECS = (
    _FeeRateExtractionSpec(
        field_name=_FIELD_MANAGEMENT_FEE_RATE,
        title="基金管理费",
        share_class_scope=_SHARE_SCOPE_ALL,
        pattern=re.compile(
            r"(?P<raw>[^。\n]*?(?:本基金|基金管理人)[^。\n]*?(?:管理费|管理人报酬)[^。\n]*?"
            r"(?P<rate>\d+\.\d{2}%)[^。\n]*)"
        ),
    ),
    _FeeRateExtractionSpec(
        field_name=_FIELD_CUSTODIAN_FEE_RATE,
        title="基金托管费",
        share_class_scope=_SHARE_SCOPE_ALL,
        pattern=re.compile(
            r"(?P<raw>[^。\n]*?(?:本基金|基金托管人)[^。\n]*?托管费[^。\n]*?"
            r"(?P<rate>\d+\.\d{2}%)[^。\n]*)"
        ),
    ),
    _FeeRateExtractionSpec(
        field_name=_FIELD_SALES_SERVICE_FEE_RATE,
        title="销售服务费",
        share_class_scope=_SHARE_SCOPE_A,
        pattern=re.compile(r"(?P<raw>本基金A类基\s*金份额不收取销售服务费)"),
        controlled_value=_FEE_RATE_NO_CHARGE_TEXT,
    ),
    _FeeRateExtractionSpec(
        field_name=_FIELD_SALES_SERVICE_FEE_RATE,
        title="销售服务费",
        share_class_scope=_SHARE_SCOPE_C,
        pattern=re.compile(
            r"(?P<raw>C类基\s*金份额的销售服务费按前一日C类基金资产净值的"
            r"(?P<rate>\d+\.\d{2}%)年\s*费\s*率计提)"
        ),
    ),
)

_PERFORMANCE_RETURN_EXTRACTION_SPECS = (
    _PerformanceReturnExtractionSpec(
        field_name=_FIELD_NAV_GROWTH_RATE,
        column_keywords=("份额净值增长率",),
        excluded_keywords=("标准差",),
    ),
    _PerformanceReturnExtractionSpec(
        field_name=_FIELD_BENCHMARK_RETURN_RATE,
        column_keywords=("业绩比较基准收益率",),
        excluded_keywords=("标准差",),
    ),
)

_ANNUAL_PERFORMANCE_EXTRACTION_SPECS = (
    _PerformanceReturnExtractionSpec(
        field_name=_FIELD_ANNUAL_NAV_GROWTH_RATE,
        column_keywords=("份额净值增长率",),
        excluded_keywords=("标准差",),
    ),
    _PerformanceReturnExtractionSpec(
        field_name=_FIELD_ANNUAL_BENCHMARK_RETURN_RATE,
        column_keywords=("业绩比较基准收益率",),
        excluded_keywords=("标准差",),
    ),
)

_ANNUAL_EXCESS_RETURN_EXTRACTION_SPECS = (
    _PerformanceReturnExtractionSpec(
        field_name=_FIELD_ANNUAL_EXCESS_RETURN,
        column_keywords=(_ANNUAL_EXCESS_RETURN_COLUMN_LABEL,),
    ),
)


@dataclass(frozen=True)
class ImportLocalReportRequest:
    """登记本地基金年报 PDF 的 use case 请求。

    参数:
        pdf_path: 本地 PDF 路径，只允许 Service 内部导入使用。
        fund_code: 基金代码。
        fund_name: 基金名称。
        year: 报告年份。
        work_dir: 本地受控工作目录。
        report_type: 报告类型，当前仅 annual_report。
        share_class: 可选份额类别。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    pdf_path: Path
    fund_code: str
    fund_name: str
    year: int
    work_dir: Path
    report_type: ReportType = ReportType.ANNUAL_REPORT
    quarter: int | None = None
    share_class: str | None = None


@dataclass(frozen=True)
class ExtractFeeRatesRequest(ImportLocalReportRequest):
    """抽取 fee_rates 三类字段的 use case 请求。

    参数:
        继承本地年报导入请求字段；抽取 query 由 Service 固定为 fee_rates。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """


@dataclass(frozen=True)
class ExtractPerformanceReturnsRequest(ImportLocalReportRequest):
    """抽取 performance_returns past_1_year 字段的 use case 请求。

    参数:
        继承本地年报导入请求字段；抽取 query 由 Service 固定为 performance_returns。
        share_class 可用于显式限定单份额表格；未指定时不得猜默认份额。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """


@dataclass(frozen=True)
class ExtractAnnualPerformanceRequest(ImportLocalReportRequest):
    """抽取年度业绩表格字段的 use case 请求。

    参数:
        继承本地年报导入请求字段；Service 固定使用 performance_returns locator。
        year 同时作为 DTO 的 report_year；share_class 可显式限定 A/C。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """


@dataclass(frozen=True)
class ExtractAnnualExcessReturnRequest(ImportLocalReportRequest):
    """抽取年度超额收益显式披露字段的 use case 请求。

    参数:
        继承本地年报导入请求字段；Service 固定使用 performance comparison
        title-family locator。year 同时作为 DTO 的 report_year；share_class 可显式限定 A/C。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """


@dataclass(frozen=True)
class ImportLocalReportResult:
    """本地年报导入并完成阅读准备后的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        report: 不含本地路径和 local_import_id 的报告摘要。

    返回:
        可返回给 CLI/UI 的安全 DTO。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    report: ReportSummary


@dataclass(frozen=True)
class ReadLocalReportRequest(ImportLocalReportRequest):
    """读取本地基金年报的 use case 请求。

    参数:
        query: 交给 Host/Agent 的检索问题。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    query: str = "基金经理"


@dataclass(frozen=True)
class ReadLocalReportResult:
    """读取本地年报后的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        agent_result: Host/Agent 返回的安全阅读结果。
        routing_trace: Service-level query routing attempts 审计记录，不进入 Agent tool_trace。

    返回:
        可供 CLI 格式化的 DTO。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    agent_result: AgentRunResult
    routing_trace: tuple[QueryRouteAttempt, ...] = ()


@dataclass(frozen=True)
class ListReportsRequest:
    """列出本地 completed reports 的 use case 请求。

    参数:
        work_dir: 本地受控工作目录。
        fund_code: 可选基金代码过滤。
        year: 可选年份过滤。
        report_type: 可选报告类型过滤。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    work_dir: Path
    fund_code: str | None = None
    year: int | None = None
    report_type: ReportType | str | None = None


@dataclass(frozen=True)
class ListReportsResult:
    """列出 completed reports 后的安全结果。

    参数:
        reports: 不含本地路径和 local_import_id 的报告摘要。
        failure: 下层工具服务返回的稳定失败；成功时为 None。

    返回:
        可供 CLI/UI 格式化的 DTO。

    异常:
        本模型不抛出业务异常。
    """

    reports: tuple[ReportSummary, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class _PreparedReport:
    """Service 内部已完成阅读准备的 report。"""

    import_result: PdfImportResult
    store: DoclingDocumentStore


@dataclass(frozen=True)
class _QueryRoutePlan:
    """Service 内部 query routing 执行计划。"""

    profile_name: str | None
    candidate_queries: tuple[str, ...]
    locator_contract: _DisclosureLocatorContract | None


@dataclass(frozen=True)
class _QueryRouteRun:
    """Service 内部 query routing 执行结果。"""

    agent_result: AgentRunResult
    routing_trace: tuple[QueryRouteAttempt, ...]


_MANAGER_HOLDS_INTERVAL_RE = re.compile(
    r"^(?:>=|<=|>|<)?\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?$"
)

# 基金合同生效日抽取正则：日期必须紧跟在「基金合同生效日/合同于」之后，
# 规避 163415 §4.1.2「本期 2025年4月8日（基金合同生效日）至2025年12月31日」
# 经理任职口径误取。
_CONTRACT_EFFECTIVE_DATE_RE = re.compile(
    r"基金合同生效日\s*(?:为|：|:)?\s*[（(]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
_CONTRACT_EXECUTED_RE = re.compile(
    r"基金合同于\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。]{0,8}生效"
)


def _normalize_contract_effective_date(year: str, month: str, day: str) -> str:
    """把「2019 年 03 月 25 日」归一化为 "YYYY-MM-DD"。"""

    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _normalize_cell_text(text: str) -> str:
    """去除单元格文本中的全部空白，用于 Docling 单元格噪声归一化。"""

    return re.sub(r"\s+", "", str(text or ""))


def _manager_holds_header_col(header: tuple[str, ...], keyword: str, default: int) -> int:
    """按表头关键词定位列下标；未命中时返回默认列。"""

    for index, cell in enumerate(header):
        if keyword in _normalize_cell_text(cell):
            return index
    return default


def _manager_holds_share_class(cell: str) -> str:
    """从份额级别单元格提取 A类/C类 标签；无法识别时返回空字符串。"""

    text = _normalize_cell_text(cell)
    if "A类" in text or text.endswith("A"):
        return "A类"
    if "C类" in text or text.endswith("C"):
        return "C类"
    return ""


def _manager_holds_interval(cell: str, unit: str) -> str | None:
    """校验数量区间单元格，返回空白归一化后的原文本；无效时返回 None。"""

    text = _normalize_cell_text(cell)
    if not text:
        return None
    body = text
    if unit and body.endswith(unit):
        body = body[: -len(unit)]
    if not _MANAGER_HOLDS_INTERVAL_RE.match(body):
        return None
    return text


def _manager_holds_is_zero(value: str) -> bool:
    """判断区间值是否全为零（如 "0" / ">=0"）。"""

    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return not numbers or all(float(number) == 0.0 for number in numbers)


def _extract_manager_holds_fund(rows: tuple[tuple[str, ...], ...]) -> str:
    """从 9.4 节披露表抽取基金经理持有区间文本。

    优先取「基金经理持有」类目下 A 类份额行，无 A 行取非零行，
    再退合计行；高级管理人员类目不混入；单位从表头（万份）继承。

    参数:
        rows: Docling 表格行。

    返回:
        holds_fund 文本（如 "A类>100万份"）；无有效披露时返回空字符串。
    """

    if not rows:
        return ""
    header = rows[0]
    unit = "万份" if any("万份" in _normalize_cell_text(cell) for cell in header) else ""
    project_col = _manager_holds_header_col(header, "项目", 0)
    class_col = _manager_holds_header_col(header, "份额级别", 1)
    value_col = _manager_holds_header_col(header, "数量区间", 2)

    block_start = None
    for index, row in enumerate(rows):
        row_str = " ".join(str(cell) for cell in row)
        if "基金经理持有" not in row_str or "开放式基金" not in row_str:
            continue
        if len(row) > project_col and "高级管理" in _normalize_cell_text(row[project_col]):
            continue
        block_start = index
        break
    if block_start is None:
        return ""

    block_rows: list[tuple[str, str]] = []  # (share_class, value_text)
    for row in rows[block_start:]:
        project = _normalize_cell_text(row[project_col]) if len(row) > project_col else ""
        if project and block_rows:
            break
        if len(row) <= max(class_col, value_col):
            continue
        value_text = _manager_holds_interval(row[value_col], unit)
        if value_text is None:
            continue
        block_rows.append((_manager_holds_share_class(row[class_col]), value_text))

    selected = next((item for item in block_rows if item[0] == "A类"), None)
    if selected is None:
        selected = next(
            (item for item in block_rows if not _manager_holds_is_zero(item[1])),
            None,
        )
    if selected is None:
        selected = next((item for item in block_rows if item[0] == ""), None)
    if selected is None:
        return ""
    share_class, value_text = selected
    if "万份" in value_text:
        return value_text
    return f"{share_class}{value_text}{unit}"


def _extract_manager_holds_overall(rows: tuple[tuple[str, ...], ...]) -> str:
    """从 9.2 从业人员整体持有表构造回退口径文本。

    9.4 基金经理持有区间表缺失时回退使用：年报 9.2「期末基金管理人的从业人员
    持有本基金的情况」整体表（table-80 类：「基金管理人所有从业人员持有本基金
    | 7,312.84 | 0.01」），口径说明直接嵌入返回文本（如「基金经理区间未披露；
    从业人员整体持有 7,312.84 份（0.01%）」），渲染点无需感知数据来源。

    参数:
        rows: Docling 表格行（表头 + 数据行）。

    返回:
        回退口径文本；非 9.2 从业人员整体持有表时返回空字符串。
    """

    if not rows:
        return ""
    header = rows[0]
    project_col = _manager_holds_header_col(header, "项目", 0)
    shares_col = _manager_holds_header_col(header, "持有份额总数", 1)
    ratio_col = _manager_holds_header_col(header, "占基金总份额比例", 2)
    for row in rows[1:]:
        if len(row) <= project_col:
            continue
        project = _normalize_cell_text(row[project_col])
        if "从业人员" not in project or "持有本基金" not in project:
            continue
        if len(row) <= max(shares_col, ratio_col):
            continue
        shares = _normalize_cell_text(row[shares_col])
        if not shares or shares == "-":
            continue
        ratio = _normalize_cell_text(row[ratio_col])
        if ratio in ("", "-"):
            ratio = ""
        elif not ratio.endswith("%"):
            ratio = f"{ratio}%"
        ratio_suffix = f"（{ratio}）" if ratio else ""
        return f"基金经理区间未披露；从业人员整体持有 {shares} 份{ratio_suffix}"
    return ""


class FundReadingService:
    """基金阅读 Service use case 边界。

    参数:
        converter_factory: DoclingConverter 工厂，测试可注入 fake converter。
        host_factory: Host 工厂，测试可验证 Host 只接收 document_id 和 query。

    返回:
        可执行 import/read/list 三个首批 use case 的 Service。

    异常:
        构造函数不访问本地文件系统，不抛出业务异常。
    """

    def __init__(
        self,
        *,
        converter_factory: ConverterFactory | None = None,
        host_factory: HostFactory | None = None,
        runner_factory: RunnerFactory | None = None,
    ) -> None:
        """初始化 Service 的可注入依赖。"""

        self._converter_factory = converter_factory or DoclingConverter
        self._host_factory = host_factory or _default_host_factory
        self._runner_factory = runner_factory or _default_runner_factory

    def import_local_report(self, request: ImportLocalReportRequest) -> ImportLocalReportResult:
        """导入本地 PDF，必要时转换 Docling JSON，并登记 completed report。

        参数:
            request: 本地 PDF 导入请求。

        返回:
            ImportLocalReportResult，只包含 public document_id 和安全报告摘要。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类。
        """

        prepared = self._prepare_completed_report(request)
        summary = _single_report_summary(prepared.import_result.identity.document_id, prepared.store)
        return ImportLocalReportResult(
            document_id=prepared.import_result.identity.document_id,
            report=summary,
        )

    def read_local_report(self, request: ReadLocalReportRequest) -> ReadLocalReportResult:
        """导入或复用本地 completed report，并通过 Host 读取问题答案。

        参数:
            request: 本地 PDF 阅读请求。

        返回:
            ReadLocalReportResult；Agent 业务失败保留在 agent_result.failure。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类。
        """

        prepared = self._prepare_completed_report(request)
        document_id = prepared.import_result.identity.document_id
        tool_service = FundDocumentToolService({document_id: prepared.store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=request.query,
        )
        return ReadLocalReportResult(
            document_id=document_id,
            agent_result=routed.agent_result,
            routing_trace=routed.routing_trace,
        )

    def ask_question(
        self,
        request: AskQuestionRequest,
        *,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> AskQuestionResult:
        """LLM 自主工具调用问答，含 profile routing 提供受控上下文。

        参数:
            request: 问答请求，document_id 和 question 必填。
            on_event: 可选流式事件回调，每个 StreamEvent 产出时调用。

        返回:
            AskQuestionResult，含 answer、citations、tool_trace 和 routing_trace。
        """

        from fund_agent.host import MinimalHost as MH

        document_id = request.document_id
        from fund_agent.fund.document_tools.persistent_repository import (
            FilesystemReportRepository,
            CATALOG_FILENAME as _CATALOG_FILENAME,
        )
        from fund_agent.fund.document_tools.errors import DocumentToolError

        work_dir = request.work_dir
        repo = FilesystemReportRepository(
            catalog_path=work_dir / _CATALOG_FILENAME,
            blob_root=work_dir / PDF_BLOB_DIRNAME,
            docling_json_root=work_dir / DOCLING_JSON_DIRNAME,
        )
        try:
            store = repo.load_store(document_id)
        except DocumentToolError as exc:
            return AskQuestionResult(
                answer="",
                citations=(),
                tool_trace=(),
                routing_trace=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        tool_service = FundDocumentToolService({document_id: store})

        augmented_query = request.question
        routing_trace: list[QueryRouteAttempt] = []

        # 创建 LLM runner 并通过 Host 运行
        runner = self._runner_factory(tool_service)
        llm_host = MH(runner)  # type: ignore[arg-type]

        answer_parts: list[str] = []
        citations_list: list[Citation] = []
        failure: ToolFailure | None = None

        for event in llm_host.run_agent_stream(document_id=document_id, query=augmented_query):
            if on_event is not None:
                on_event(event)
            if event.type == StreamEventType.CONTENT_DELTA:
                if isinstance(event.payload, str):
                    answer_parts.append(event.payload)
            elif event.type == StreamEventType.METADATA:
                meta_citations = (event.payload or {}).get("citations", [])
                for c in meta_citations:
                    if isinstance(c, dict):
                        try:
                            citations_list.append(
                                Citation(
                                    document_id=str(c.get("document_id", "")),
                                    fund_code=str(c.get("fund_code", "")),
                                    fund_name=str(c.get("fund_name", "")),
                                    year=int(c.get("year", 0)),
                                    report_type=str(c.get("report_type", "")),
                                    locator=None,  # type: ignore[arg-type]
                                )
                            )
                        except (ValueError, TypeError):
                            pass
            elif event.type == StreamEventType.ERROR:
                failure = ToolFailure(
                    code=FailureCode(event.payload.get("code", FailureCode.UNAVAILABLE.value))
                    if isinstance(event.payload, dict)
                    else FailureCode.UNAVAILABLE,
                    message=event.payload.get("message", "") if isinstance(event.payload, dict) else str(event.payload),
                )

        return AskQuestionResult(
            answer="".join(answer_parts),
            citations=tuple(citations_list),
            tool_trace=(),  # tool_trace 从 runner 内部 trace 获取
            routing_trace=tuple(routing_trace),
            failure=failure,
        )

    def extract_fee_rates(self, request: ExtractFeeRatesRequest) -> ExtractFeeRatesResult:
        """基于 10B fee_rates 阅读定位结果抽取当前适用年费率字段。

        参数:
            request: 本地年报 fee_rates 抽取请求；Service 固定使用 query="费用"。

        返回:
            ExtractFeeRatesResult。成功时包含管理费、托管费、A 类销售服务费、
            C 类销售服务费四条受控 DTO；失败时 fields 为空且 failure 为稳定分类。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类；字段抽取失败写入 result.failure。
        """

        reading = self.read_local_report(
            ReadLocalReportRequest(
                pdf_path=request.pdf_path,
                fund_code=request.fund_code,
                fund_name=request.fund_name,
                year=request.year,
                work_dir=request.work_dir,
                report_type=request.report_type,
                share_class=request.share_class,
                query=_FEE_RATES_QUERY,
            )
        )
        if reading.agent_result.failure is not None:
            return ExtractFeeRatesResult(
                document_id=reading.document_id,
                fields=(),
                failure=reading.agent_result.failure,
            )
        try:
            fields = _extract_fee_rate_fields(reading.agent_result)
        except DocumentToolError as exc:
            return ExtractFeeRatesResult(
                document_id=reading.document_id,
                fields=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractFeeRatesResult(
                document_id=reading.document_id,
                fields=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="fee_rates 字段抽取暂不可用"),
            )
        return ExtractFeeRatesResult(document_id=reading.document_id, fields=fields, failure=None)

    def extract_performance_returns(
        self,
        request: ExtractPerformanceReturnsRequest,
    ) -> ExtractPerformanceReturnsResult:
        """基于 11A performance_returns 定位结果抽取 past_1_year 收益字段。

        参数:
            request: 本地年报 performance_returns 抽取请求；Service 固定使用
                query="净值增长率" 进入 11A locator。

        返回:
            ExtractPerformanceReturnsResult。成功时包含可唯一识别份额类别的
            nav_growth_rate / benchmark_return_rate DTO；失败时 fields 为空且
            failure 为稳定分类。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类；字段抽取失败写入 result.failure。
        """

        prepared = self._prepare_completed_report(request)
        document_id = prepared.import_result.identity.document_id
        tool_service = FundDocumentToolService({document_id: prepared.store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=_PERFORMANCE_RETURNS_QUERY,
        )
        if routed.agent_result.failure is not None:
            return ExtractPerformanceReturnsResult(
                document_id=document_id,
                fields=(),
                failure=routed.agent_result.failure,
            )
        try:
            fields = _extract_performance_return_fields(
                document_id=document_id,
                result=routed.agent_result,
                tool_service=tool_service,
                requested_share_class=request.share_class,
            )
        except DocumentToolError as exc:
            return ExtractPerformanceReturnsResult(
                document_id=document_id,
                fields=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractPerformanceReturnsResult(
                document_id=document_id,
                fields=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="performance_returns 字段抽取暂不可用"),
            )
        return ExtractPerformanceReturnsResult(document_id=document_id, fields=fields, failure=None)

    def extract_annual_performance(
        self,
        request: ExtractAnnualPerformanceRequest,
    ) -> ExtractAnnualPerformanceResult:
        """从 title-family matched performance comparison table 抽取年度收益字段。

        参数:
            request: 本地年报年度业绩抽取请求；Service 固定使用
                performance_returns locator，并只接受标题族为
                基金份额净值增长率及其与同期业绩比较基准收益率的比较的表格证据。

        返回:
            ExtractAnnualPerformanceResult。成功时包含可唯一识别份额类别的
            annual_nav_growth_rate / annual_benchmark_return_rate DTO；失败时 fields
            为空且 failure 为稳定分类。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类；字段抽取失败写入 result.failure。
        """

        prepared = self._prepare_completed_report(request)
        document_id = prepared.import_result.identity.document_id
        return self._extract_annual_performance_from_store(
            document_id=document_id,
            store=prepared.store,
            report_year=request.year,
            share_class=request.share_class,
        )

    def _extract_annual_performance_from_store(
        self,
        *,
        document_id: str,
        store: DoclingDocumentStore,
        report_year: int,
        share_class: str | None,
    ) -> ExtractAnnualPerformanceResult:
        """基于已完成 store 执行 10F 年度业绩字段抽取。"""

        tool_service = FundDocumentToolService({document_id: store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=_ANNUAL_PERFORMANCE_TITLE_FAMILY,
        )
        if routed.agent_result.failure is not None:
            return ExtractAnnualPerformanceResult(
                document_id=document_id,
                fields=(),
                failure=routed.agent_result.failure,
            )
        try:
            fields = _extract_annual_performance_fields(
                document_id=document_id,
                result=routed.agent_result,
                tool_service=tool_service,
                report_year=report_year,
                requested_share_class=share_class,
            )
        except DocumentToolError as exc:
            return ExtractAnnualPerformanceResult(
                document_id=document_id,
                fields=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractAnnualPerformanceResult(
                document_id=document_id,
                fields=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="annual performance 字段抽取暂不可用"),
            )
        return ExtractAnnualPerformanceResult(document_id=document_id, fields=fields, failure=None)

    def extract_annual_excess_return(
        self,
        request: ExtractAnnualExcessReturnRequest,
    ) -> ExtractAnnualExcessReturnResult:
        """从 title-family matched table 抽取年报显式披露的年度超额收益。

        参数:
            request: 本地年报年度超额收益抽取请求；Service 固定使用
                基金份额净值增长率及其与同期业绩比较基准收益率的比较 title-family。

        返回:
            ExtractAnnualExcessReturnResult。成功时包含可唯一识别份额类别的
            annual_excess_return DTO；失败时 fields 为空且 failure 为稳定分类。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类；字段抽取失败写入 result.failure。
        """

        prepared = self._prepare_completed_report(request)
        document_id = prepared.import_result.identity.document_id
        return self._extract_annual_excess_return_from_store(
            document_id=document_id,
            store=prepared.store,
            report_year=request.year,
            share_class=request.share_class,
        )

    def _extract_annual_excess_return_from_store(
        self,
        *,
        document_id: str,
        store: DoclingDocumentStore,
        report_year: int,
        share_class: str | None,
    ) -> ExtractAnnualExcessReturnResult:
        """基于已完成 store 执行 10G 年度超额收益显式字段抽取。"""

        tool_service = FundDocumentToolService({document_id: store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=_ANNUAL_PERFORMANCE_TITLE_FAMILY,
        )
        if routed.agent_result.failure is not None:
            return ExtractAnnualExcessReturnResult(
                document_id=document_id,
                fields=(),
                failure=routed.agent_result.failure,
            )
        try:
            fields = _extract_annual_excess_return_fields(
                document_id=document_id,
                result=routed.agent_result,
                tool_service=tool_service,
                report_year=report_year,
                requested_share_class=share_class,
            )
        except DocumentToolError as exc:
            return ExtractAnnualExcessReturnResult(
                document_id=document_id,
                fields=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractAnnualExcessReturnResult(
                document_id=document_id,
                fields=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="annual excess return 字段抽取暂不可用"),
            )
        return ExtractAnnualExcessReturnResult(document_id=document_id, fields=fields, failure=None)

    def aggregate_multi_year_annual_performance(
        self,
        request: AggregateMultiYearAnnualPerformanceRequest,
    ) -> AggregateMultiYearAnnualPerformanceResult:
        """按显式 document_id 编排 10F/10G，聚合多年度年度业绩 series。

        参数:
            request: 10I 显式输入；Service 只按 annual_report_documents 中给出的
                document_id 加载 completed annual reports，不按 fund_code/year 自动查找。

        返回:
            AggregateMultiYearAnnualPerformanceResult。成功时返回达到 3-5 年 bounded
            coverage 的 share class series；不足 3 年时 failure 为 not_found。

        异常:
            本方法捕获聚合内稳定失败并写入 result.failure。
        """

        try:
            normalized_years = _normalized_multi_year_requested_years(request.requested_years)
            documents_by_year = _multi_year_documents_by_year(request.annual_report_documents)
            requested_scope = _normalize_multi_year_requested_share_class(request.share_class)
            repository = _repository(Path(request.work_dir))
            rows_by_share: dict[str, dict[int, MultiYearAnnualPerformanceRow]] = {}
            missing_notes: dict[int, str] = {}

            for year in normalized_years:
                document = documents_by_year.get(year)
                if document is None:
                    missing_notes[year] = "catalog 中无该年度年报（未导入或未匹配）"
                    continue
                try:
                    store = repository.load_store(document.document_id)
                    _validate_multi_year_report_identity(
                        document_id=document.document_id,
                        store=store,
                        fund_code=request.fund_code,
                        year=year,
                    )
                    annual_result = self._extract_annual_performance_from_store(
                        document_id=document.document_id,
                        store=store,
                        report_year=year,
                        share_class=request.share_class,
                    )
                    excess_result = self._extract_annual_excess_return_from_store(
                        document_id=document.document_id,
                        store=store,
                        report_year=year,
                        share_class=request.share_class,
                    )
                    row_by_share = _multi_year_complete_rows_for_year(
                        year=year,
                        annual_result=annual_result,
                        excess_result=excess_result,
                    )
                except DocumentToolError as exc:
                    if exc.code is FailureCode.IDENTITY_MISMATCH:
                        return AggregateMultiYearAnnualPerformanceResult(
                            series=(),
                            failure=ToolFailure(code=exc.code, message=exc.message),
                        )
                    if exc.code is FailureCode.SCHEMA_DRIFT:
                        return AggregateMultiYearAnnualPerformanceResult(
                            series=(),
                            failure=ToolFailure(code=exc.code, message=exc.message),
                        )
                    missing_notes[year] = exc.message
                    continue

                if requested_scope is not None:
                    row = row_by_share.get(requested_scope)
                    if row is not None:
                        rows_by_share.setdefault(requested_scope, {})[year] = row
                    continue

                if not row_by_share:
                    continue
                for share_scope, row in row_by_share.items():
                    rows_by_share.setdefault(share_scope, {})[year] = row

            candidate_scopes = (requested_scope,) if requested_scope is not None else tuple(sorted(rows_by_share))
            series = tuple(
                _multi_year_series_for_share(
                    fund_code=request.fund_code,
                    requested_years=normalized_years,
                    share_class_scope=share_scope,
                    rows_by_year=rows_by_share.get(share_scope, {}),
                    missing_notes=missing_notes,
                )
                for share_scope in candidate_scopes
                if _multi_year_complete_count(rows_by_share.get(share_scope, {}))
                >= _MULTI_YEAR_MINIMUM_COMPLETE_YEARS
            )
            if not series:
                return AggregateMultiYearAnnualPerformanceResult(
                    series=(),
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message="multi-year annual performance 覆盖不足 3 年"),
                )
            return AggregateMultiYearAnnualPerformanceResult(series=series, failure=None)
        except DocumentToolError as exc:
            return AggregateMultiYearAnnualPerformanceResult(
                series=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return AggregateMultiYearAnnualPerformanceResult(
                series=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="multi-year annual performance 聚合暂不可用"),
            )

    def _extract_holdings_from_store(
        self,
        *,
        document_id: str,
        store: DoclingDocumentStore,
        report_year: int,
        fund_name: str = "",
        repository: FilesystemReportRepository | None = None,
    ) -> AnnualHoldingsResult:
        """从单年度年报中抽取前十大持仓表。

        参数:
            document_id: 文档 ID。
            store: 已加载的 DoclingDocumentStore。
            report_year: 报告年份。
            fund_name: 基金名称，用于债券基金 fallback 判断。

        返回:
            AnnualHoldingsResult；失败时 failure 非空。
        """

        tool_service = FundDocumentToolService({document_id: store})
        host = self._host_factory(tool_service)

        query = _HOLDINGS_QUERY
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=query,
        )
        # equity query 失败时，按基金类型 fallback
        equity_failed = routed.agent_result.failure is not None
        fund_type = ""
        if equity_failed and fund_name:
            fund_type, _ = infer_fund_type(fund_name)
            if fund_type == "bond_fund":
                query = _BOND_HOLDINGS_QUERY
                routed = self._run_with_query_candidates(
                    host=host,
                    document_id=document_id,
                    query=query,
                )
            elif fund_type not in ("bond_fund", "index_feeder") and "QDII" in fund_name:
                # QDII 基金（主动/指数）持仓节标题为"所有权益投资明细"而非"股票投资明细"
                query = _QDII_HOLDINGS_QUERY
                routed = self._run_with_query_candidates(
                    host=host,
                    document_id=document_id,
                    query=query,
                )
            elif fund_type == "index_feeder":
                # 联接基金自身无持仓表，直接跳过 query 重试，走继承路径
                pass
        # index_feeder 自身无持仓表，跳过 query 直接走继承路径
        holdings: list[HoldingExtraction] = []
        _extraction_error = False  # 跟踪未分类异常
        table_citation = None
        for citation in routed.agent_result.citations:
            if citation.locator.locator_kind is LocatorKind.TABLE:
                table_citation = citation
                break
        if routed.agent_result.failure is not None:
            if fund_type != "index_feeder":
                return AnnualHoldingsResult(
                    document_id=document_id,
                    year=report_year,
                    holdings=(),
                    failure=routed.agent_result.failure,
                )
        else:
            try:
                holdings = list(_extract_holdings_from_agent_result(
                    document_id=document_id,
                    result=routed.agent_result,
                    tool_service=tool_service,
                ))
            except DocumentToolError:
                pass  # 已分类错误，继续 fallback
            except Exception:
                logger.warning("extract_holdings: 未分类异常", exc_info=True)
                _extraction_error = True  # 未分类异常，记录标记
            # equity 成功但持仓为空（或 QDII query 取到跨页续表碎片）时，按基金类型二次 fallback
            if fund_name:
                fund_type, _ = infer_fund_type(fund_name)
                if fund_type == "bond_fund":
                    if not holdings:
                        bond_routed = self._run_with_query_candidates(
                            host=host,
                            document_id=document_id,
                            query=_BOND_HOLDINGS_QUERY,
                        )
                        if bond_routed.agent_result.failure is None:
                            try:
                                bond_holdings = _extract_holdings_from_agent_result(
                                    document_id=document_id,
                                    result=bond_routed.agent_result,
                                    tool_service=tool_service,
                                )
                                if bond_holdings:
                                    holdings = list(bond_holdings)
                            except DocumentToolError:
                                pass
                elif fund_type not in ("bond_fund", "index_feeder") and "QDII" in fund_name:
                    # QDII 基金：持仓表常为跨页分裂（表头截断 + 续表碎片行），
                    # 直接扫描（含跨页合并）为权威路径；query 路径仅作兜底。
                    direct = _extract_qdii_holdings_from_tables(
                        document_id=document_id,
                        tool_service=tool_service,
                    )
                    if direct:
                        holdings, table_citation = direct
                    elif not holdings:
                        qdii_routed = self._run_with_query_candidates(
                            host=host,
                            document_id=document_id,
                            query=_QDII_HOLDINGS_QUERY,
                        )
                        if qdii_routed.agent_result.failure is None:
                            try:
                                qdii_holdings = _extract_holdings_from_agent_result(
                                    document_id=document_id,
                                    result=qdii_routed.agent_result,
                                    tool_service=tool_service,
                                )
                                if qdii_holdings:
                                    holdings = list(qdii_holdings)
                            except DocumentToolError:
                                pass
                elif fund_type not in ("bond_fund", "index_feeder") and "QDII" not in fund_name:
                    # A 股基金：agent citation 首位命中非持仓表（如行业配置表）且无后续
                    # 持仓表 citation 时，直接扫描（list_tables + 表头特征）兜底，并复用
                    # _extract_holdings_continuations 的跨页续表合并；同步校正 citation。
                    if not holdings:
                        direct = _extract_stock_holdings_from_tables(
                            document_id=document_id,
                            tool_service=tool_service,
                        )
                        if direct:
                            holdings, table_citation = direct

        # 联接基金持仓继承：从目标 ETF 年报获取持仓
        holding_source = ""
        if not holdings and fund_name and repository is not None:
            fund_type, _ = infer_fund_type(fund_name)
            if fund_type in ("index_fund", "index_feeder"):
                etf_info = _extract_target_etf_code(document_id, store)
                if etf_info is not None:
                    etf_code, etf_name = etf_info
                    etf_doc_id: str | None = None
                    own_fund_code = store._identity.fund_code
                    for report in repository.list_reports():
                        if report.get("year") != report_year:
                            continue
                        if report.get("fund_code") == own_fund_code:
                            continue  # 排除联接基金自身
                        # 按代码匹配（优先）或按名称匹配
                        if etf_code and report.get("fund_code") == etf_code:
                            etf_doc_id = str(report["document_id"])
                            if not etf_name:
                                etf_name = str(report.get("fund_name", ""))
                            break
                        elif not etf_code and etf_name:
                            # 名称匹配：规范化 "交易型开放式指数证券投资基金" ↔ "ETF"
                            repo_name = str(report.get("fund_name", ""))
                            if _fund_name_matches(etf_name, repo_name):
                                etf_doc_id = str(report["document_id"])
                                etf_code = str(report.get("fund_code", ""))
                                etf_name = repo_name  # 使用仓库中的真实名称
                                break
                    if etf_doc_id is not None:
                        try:
                            etf_store = repository.load_store(etf_doc_id)
                            etf_result = self._extract_holdings_from_store(
                                document_id=etf_doc_id,
                                store=etf_store,
                                report_year=report_year,
                                fund_name=etf_name,
                            )
                            if etf_result.holdings:
                                holdings = etf_result.holdings
                                table_citation = etf_result.citation
                                holding_source = f"持仓数据来源：目标 ETF（{etf_code}）"
                        except DocumentToolError:
                            pass
                    if not holdings:
                        return AnnualHoldingsResult(
                            document_id=document_id,
                            year=report_year,
                            holdings=(),
                            failure=ToolFailure(
                                code=FailureCode.NOT_FOUND,
                                message="目标 ETF 年报未导入，无法获取持仓数据",
                            ),
                        )

        # 所有 fallback 路径走完后，若持仓为空且有未分类异常，返回 UNAVAILABLE
        if not holdings and _extraction_error:
            return AnnualHoldingsResult(
                document_id=document_id,
                year=report_year,
                holdings=(),
                failure=ToolFailure(
                    code=FailureCode.UNAVAILABLE,
                    message="持仓抽取过程中发生未分类异常",
                ),
            )

        return AnnualHoldingsResult(
            document_id=document_id,
            year=report_year,
            holdings=holdings,
            citation=table_citation,
            holding_source=holding_source,
        )

    def extract_multi_year_holdings(
        self,
        request: ExtractHoldingsRequest,
    ) -> ExtractHoldingsResult:
        """聚合多年度持仓数据。

        参数:
            request: 持仓多年度聚合请求。

        返回:
            ExtractHoldingsResult；成功时包含 MultiYearHoldingsSeries。
        """

        try:
            normalized_years = _normalized_holdings_requested_years(request.requested_years)
            documents_by_year = _multi_year_documents_by_year(request.annual_report_documents)
            repository = _repository(Path(request.work_dir))

            annual_results: list[AnnualHoldingsResult] = []
            covered_years: list[int] = []
            missing_years: list[int] = []

            for year in normalized_years:
                document = documents_by_year.get(year)
                if document is None:
                    missing_years.append(year)
                    continue
                try:
                    store = repository.load_store(document.document_id)
                    _validate_multi_year_report_identity(
                        document_id=document.document_id,
                        store=store,
                        fund_code=request.fund_code,
                        year=year,
                    )
                    result = self._extract_holdings_from_store(
                        document_id=document.document_id,
                        store=store,
                        report_year=year,
                        fund_name=request.fund_name,
                        repository=repository,
                    )
                    if result.failure is not None:
                        missing_years.append(year)
                        continue
                    annual_results.append(result)
                    covered_years.append(year)
                except DocumentToolError:
                    missing_years.append(year)
                    continue

            if not covered_years:
                return ExtractHoldingsResult(
                    series=None,
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到任何年度的持仓数据"),
                )

            series = MultiYearHoldingsSeries(
                fund_code=request.fund_code,
                requested_years=normalized_years,
                covered_years=tuple(sorted(covered_years)),
                missing_years=tuple(sorted(missing_years)),
                annual_holdings=tuple(annual_results),
            )
            return ExtractHoldingsResult(series=series, failure=None)
        except DocumentToolError as exc:
            return ExtractHoldingsResult(
                series=None,
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractHoldingsResult(
                series=None,
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="多年度持仓聚合暂不可用"),
            )

    def _extract_allocation_from_store(
        self,
        *,
        document_id: str,
        store: DoclingDocumentStore,
        report_year: int,
    ) -> AnnualAllocationResult:
        """从单年度年报中抽取资产配置和行业配置。"""

        tool_service = FundDocumentToolService({document_id: store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query="期末基金资产组合情况",
        )
        if routed.agent_result.failure is not None:
            return AnnualAllocationResult(
                document_id=document_id,
                year=report_year,
                asset_allocation=(),
                industry_allocation=(),
                failure=routed.agent_result.failure,
            )

        try:
            asset_allocation, industry_allocation = _extract_allocation_from_agent_result(
                document_id=document_id,
                result=routed.agent_result,
                tool_service=tool_service,
            )
        except DocumentToolError as exc:
            return AnnualAllocationResult(
                document_id=document_id,
                year=report_year,
                asset_allocation=(),
                industry_allocation=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return AnnualAllocationResult(
                document_id=document_id,
                year=report_year,
                asset_allocation=(),
                industry_allocation=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="资产配置字段抽取暂不可用"),
            )

        if not industry_allocation:
            industry_routed = self._run_with_query_candidates(
                host=host,
                document_id=document_id,
                query="按行业分类的股票投资组合",
            )
            if industry_routed.agent_result.failure is None:
                try:
                    _, industry_allocation = _extract_allocation_from_agent_result(
                        document_id=document_id,
                        result=industry_routed.agent_result,
                        tool_service=tool_service,
                    )
                except DocumentToolError:
                    pass
                except Exception:
                    logger.warning("extract_allocation: 资产配置抽取异常", exc_info=True)

        table_citation = None
        for citation in routed.agent_result.citations:
            if citation.locator.locator_kind is LocatorKind.TABLE:
                table_citation = citation
                break

        return AnnualAllocationResult(
            document_id=document_id,
            year=report_year,
            asset_allocation=asset_allocation,
            industry_allocation=industry_allocation,
            citation=table_citation,
        )

    def extract_multi_year_allocation(
        self,
        request: ExtractAllocationRequest,
    ) -> ExtractAllocationResult:
        """聚合多年度资产配置数据。"""

        try:
            normalized_years = _normalized_holdings_requested_years(request.requested_years)
            documents_by_year = _multi_year_documents_by_year(request.annual_report_documents)
            repository = _repository(Path(request.work_dir))

            annual_results: list[AnnualAllocationResult] = []
            covered_years: list[int] = []
            missing_years: list[int] = []

            for year in normalized_years:
                document = documents_by_year.get(year)
                if document is None:
                    missing_years.append(year)
                    continue
                try:
                    store = repository.load_store(document.document_id)
                    _validate_multi_year_report_identity(
                        document_id=document.document_id,
                        store=store,
                        fund_code=request.fund_code,
                        year=year,
                    )
                    result = self._extract_allocation_from_store(
                        document_id=document.document_id,
                        store=store,
                        report_year=year,
                    )
                    if result.failure is not None:
                        missing_years.append(year)
                        continue
                    annual_results.append(result)
                    covered_years.append(year)
                except DocumentToolError:
                    missing_years.append(year)
                    continue

            if not covered_years:
                return ExtractAllocationResult(
                    series=None,
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到任何年度的资产配置数据"),
                )

            series = MultiYearAllocationSeries(
                fund_code=request.fund_code,
                requested_years=normalized_years,
                covered_years=tuple(sorted(covered_years)),
                missing_years=tuple(sorted(missing_years)),
                annual_allocations=tuple(annual_results),
            )
            return ExtractAllocationResult(series=series, failure=None)
        except DocumentToolError as exc:
            return ExtractAllocationResult(
                series=None,
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractAllocationResult(
                series=None,
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="多年度资产配置聚合暂不可用"),
            )

    def _extract_fee_rates_from_store(
        self,
        *,
        document_id: str,
        store: DoclingDocumentStore,
        report_year: int,
    ) -> AnnualFeeResult:
        """从单年度年报中抽取费率信息。"""

        tool_service = FundDocumentToolService({document_id: store})
        host = self._host_factory(tool_service)

        fees: list[FeeRateItem] = []
        section_citation: Citation | None = None
        fee_queries = ("基金管理费", "基金托管费", "销售服务费", "管理人报酬")

        for query in fee_queries:
            routed = self._run_with_query_candidates(
                host=host,
                document_id=document_id,
                query=query,
            )
            if routed.agent_result.failure is not None:
                continue

            if section_citation is None:
                for citation in routed.agent_result.citations:
                    if citation.locator.locator_kind is LocatorKind.SECTION:
                        section_citation = citation
                        break

            try:
                extracted_fees = _extract_fee_rates_from_agent_result(
                    result=routed.agent_result,
                )
                for fee in extracted_fees:
                    if not any(f.fee_name == fee.fee_name for f in fees):
                        fees.append(fee)
            except DocumentToolError:
                continue
            except Exception:
                logger.warning("extract_fee_rates: 费率抽取异常", exc_info=True)

        # 未披露销售服务费的年度（如 2021）会让 fee_rates 三标题聚合契约
        # 整体 not_found；回退按单标题验证查询管理费/托管费正文，
        # search_document / Agent / Store / ToolService 边界不变。
        # QDII 主循环可能只命中部分字段（如仅管理费），按缺失字段逐项回退。
        for query in ("基金管理费", "基金托管费"):
            if any(fee.fee_name == query for fee in fees):
                continue
            fallback = host.run(document_id=document_id, query=query)
            if fallback.failure is not None:
                continue
            route_plan = _route_plan_for_query(query)
            matched_titles = _matched_disclosure_titles(fallback, route_plan.locator_contract)
            if query not in matched_titles:
                # QDII 年报把管理费表述为「管理人报酬」，且该披露可能嵌套在
                # 关联方关系等大章节内（section title 不含费率名）；仅当正文
                # 含明确费率句时放行，避免弱化 fail-closed 标题绑定。
                if not (query == "基金管理费" and _MANAGEMENT_FEE_QDII_WORDING_RE.search(fallback.answer)):
                    continue
            if section_citation is None:
                for citation in fallback.citations:
                    if citation.locator.locator_kind is LocatorKind.SECTION:
                        section_citation = citation
                        break
            try:
                extracted_fees = _extract_fee_rates_from_agent_result(
                    result=fallback,
                )
                for fee in extracted_fees:
                    if not any(f.fee_name == fee.fee_name for f in fees):
                        fees.append(fee)
            except DocumentToolError:
                continue
            except Exception:
                logger.warning("extract_fee_rates: 单标题费率回退抽取异常", exc_info=True)

        if not fees:
            return AnnualFeeResult(
                document_id=document_id,
                year=report_year,
                fees=(),
                failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到费率信息"),
            )

        return AnnualFeeResult(
            document_id=document_id,
            year=report_year,
            fees=tuple(fees),
            citation=section_citation,
        )

    def extract_multi_year_fee_rates(
        self,
        request: ExtractFeeRatesMultiYearRequest,
    ) -> ExtractFeeRatesMultiYearResult:
        """聚合多年度费率数据。"""

        try:
            normalized_years = _normalized_holdings_requested_years(request.requested_years)
            documents_by_year = _multi_year_documents_by_year(request.annual_report_documents)
            repository = _repository(Path(request.work_dir))

            annual_results: list[AnnualFeeResult] = []
            covered_years: list[int] = []
            missing_years: list[int] = []

            for year in normalized_years:
                document = documents_by_year.get(year)
                if document is None:
                    missing_years.append(year)
                    continue
                try:
                    store = repository.load_store(document.document_id)
                    _validate_multi_year_report_identity(
                        document_id=document.document_id,
                        store=store,
                        fund_code=request.fund_code,
                        year=year,
                    )
                    result = self._extract_fee_rates_from_store(
                        document_id=document.document_id,
                        store=store,
                        report_year=year,
                    )
                    if result.failure is not None:
                        missing_years.append(year)
                        continue
                    annual_results.append(result)
                    covered_years.append(year)
                except DocumentToolError:
                    missing_years.append(year)
                    continue

            if not covered_years:
                return ExtractFeeRatesMultiYearResult(
                    series=None,
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message="未找到任何年度的费率数据"),
                )

            series = MultiYearFeeSeries(
                fund_code=request.fund_code,
                requested_years=normalized_years,
                covered_years=tuple(sorted(covered_years)),
                missing_years=tuple(sorted(missing_years)),
                annual_fees=tuple(annual_results),
            )
            return ExtractFeeRatesMultiYearResult(series=series, failure=None)
        except DocumentToolError as exc:
            return ExtractFeeRatesMultiYearResult(
                series=None,
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return ExtractFeeRatesMultiYearResult(
                series=None,
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="多年度费率聚合暂不可用"),
            )

    def audit_disclosure_completeness(
        self,
        request: DisclosureAuditRequest,
    ) -> DisclosureAuditResult:
        """审计年报披露完整性。

        参数:
            request: 披露完整性审计请求。

        返回:
            DisclosureAuditResult；包含各披露项审计结果和汇总。
        """

        try:
            repository = _repository(Path(request.work_dir))
            catalog_reports = repository.list_reports()

            document_id = None
            fund_name = ""
            for report in catalog_reports:
                if report.get("fund_code") == request.fund_code and report.get("year") == request.year:
                    document_id = str(report["document_id"])
                    fund_name = str(report.get("fund_name", ""))
                    break

            if document_id is None:
                return DisclosureAuditResult(
                    fund_code=request.fund_code,
                    year=request.year,
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message=f"catalog 中未找到 {request.fund_code} 的 {request.year} 年年报"),
                )

            store = repository.load_store(document_id)
            tool_service = FundDocumentToolService({document_id: store})
            host = self._host_factory(tool_service)

            disclosures: list[DisclosureAuditItem] = []

            disclosures.append(self._audit_holdings(host, document_id, request.year, fund_name))
            disclosures.append(self._audit_asset_allocation(host, document_id, request.year))
            disclosures.append(self._audit_fee_rates(host, document_id, request.year))
            disclosures.append(self._audit_performance(host, document_id, request.year))
            disclosures.append(self._audit_fund_manager(host, document_id, request.year))
            disclosures.append(self._audit_dividends(host, document_id, request.year))

            complete = sum(1 for d in disclosures if d.status == "complete")
            partial = sum(1 for d in disclosures if d.status == "partial")
            missing = sum(1 for d in disclosures if d.status == "missing")

            return DisclosureAuditResult(
                fund_code=request.fund_code,
                year=request.year,
                document_id=document_id,
                disclosures=tuple(disclosures),
                summary={"complete": complete, "partial": partial, "missing": missing},
                failure=None,
            )
        except DocumentToolError as exc:
            return DisclosureAuditResult(
                fund_code=request.fund_code,
                year=request.year,
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return DisclosureAuditResult(
                fund_code=request.fund_code,
                year=request.year,
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="披露完整性审计暂不可用"),
            )

    def _audit_holdings(self, host: MinimalHost, document_id: str, year: int, fund_name: str = "") -> DisclosureAuditItem:
        """审计持仓披露。"""

        routed = self._run_with_query_candidates(host=host, document_id=document_id, query="股票投资明细")
        if routed.agent_result.failure is not None and fund_name:
            fund_type, _ = infer_fund_type(fund_name)
            if fund_type == "bond_fund":
                routed = self._run_with_query_candidates(host=host, document_id=document_id, query=_BOND_HOLDINGS_QUERY)
            elif fund_type in ("index_etf",) or (fund_type == "index_fund" and "QDII" in fund_name):
                # QDII 基金持仓节标题为"所有权益投资明细"而非"股票投资明细"
                routed = self._run_with_query_candidates(host=host, document_id=document_id, query=_QDII_HOLDINGS_QUERY)
        if routed.agent_result.failure is not None:
            return DisclosureAuditItem(name="holdings", status="missing", chapter=False, message="持仓章节未找到")

        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
        # equity 无表格时，按基金类型 fallback
        if not has_table and fund_name:
            fund_type, _ = infer_fund_type(fund_name)
            if fund_type == "bond_fund":
                bond_routed = self._run_with_query_candidates(host=host, document_id=document_id, query=_BOND_HOLDINGS_QUERY)
                if bond_routed.agent_result.failure is None:
                    bond_has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in bond_routed.agent_result.citations)
                    if bond_has_table:
                        routed = bond_routed
                        has_table = True
            elif fund_type in ("index_etf",) or (fund_type == "index_fund" and "QDII" in fund_name):
                qdii_routed = self._run_with_query_candidates(host=host, document_id=document_id, query=_QDII_HOLDINGS_QUERY)
                if qdii_routed.agent_result.failure is None:
                    qdii_has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in qdii_routed.agent_result.citations)
                    if qdii_has_table:
                        routed = qdii_routed
                        has_table = True
        fields = []
        if has_table:
            fields = ["stock_code", "stock_name", "percentage"]
        status = "complete" if has_table else "partial"
        return DisclosureAuditItem(name="holdings", status=status, chapter=True, table=has_table, fields=tuple(fields))

    def _audit_asset_allocation(self, host: MinimalHost, document_id: str, year: int) -> DisclosureAuditItem:
        """审计资产配置披露。"""

        routed = self._run_with_query_candidates(host=host, document_id=document_id, query="期末基金资产组合情况")
        if routed.agent_result.failure is not None:
            return DisclosureAuditItem(name="asset_allocation", status="missing", chapter=False, message="资产配置章节未找到")

        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
        fields = []
        if has_table:
            fields = ["category", "amount", "percentage"]
        status = "complete" if has_table else "partial"
        return DisclosureAuditItem(name="asset_allocation", status=status, chapter=True, table=has_table, fields=tuple(fields))

    def _audit_fee_rates(self, host: MinimalHost, document_id: str, year: int) -> DisclosureAuditItem:
        """审计费率披露。"""

        fee_queries = ("基金管理费", "基金托管费", "销售服务费", "管理人报酬")
        found_fees: list[str] = []
        chapter_found = False

        for query in fee_queries:
            routed = self._run_with_query_candidates(host=host, document_id=document_id, query=query)
            if routed.agent_result.failure is None:
                chapter_found = True
                has_section = any(c.locator.locator_kind is LocatorKind.SECTION for c in routed.agent_result.citations)
                if has_section:
                    if query in ("基金管理费", "管理人报酬"):
                        found_fees.append("management_fee")
                    elif query == "基金托管费":
                        found_fees.append("custodian_fee")
                    elif query == "销售服务费":
                        found_fees.append("sales_service_fee")

        unique_fees = list(dict.fromkeys(found_fees))
        if not chapter_found:
            return DisclosureAuditItem(name="fee_rates", status="missing", chapter=False, message="费率章节未找到")
        if not unique_fees:
            return DisclosureAuditItem(name="fee_rates", status="partial", chapter=True, message="费率字段未识别到")
        if len(unique_fees) >= 3:
            return DisclosureAuditItem(name="fee_rates", status="complete", chapter=True, fields=tuple(unique_fees))
        return DisclosureAuditItem(name="fee_rates", status="partial", chapter=True, fields=tuple(unique_fees), message=f"只找到 {len(unique_fees)} 项费率")

    def _audit_performance(self, host: MinimalHost, document_id: str, year: int) -> DisclosureAuditItem:
        """审计业绩披露。"""

        routed = self._run_with_query_candidates(host=host, document_id=document_id, query="基金份额净值增长率")
        if routed.agent_result.failure is not None:
            return DisclosureAuditItem(name="performance", status="missing", chapter=False, message="业绩章节未找到")

        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
        fields = []
        if has_table:
            fields = ["nav_growth_rate", "benchmark_return_rate"]
        status = "complete" if has_table else "partial"
        return DisclosureAuditItem(name="performance", status=status, chapter=True, table=has_table, fields=tuple(fields))

    def _audit_fund_manager(self, host: MinimalHost, document_id: str, year: int) -> DisclosureAuditItem:
        """审计基金经理披露。"""

        routed = self._run_with_query_candidates(host=host, document_id=document_id, query="基金经理")
        if routed.agent_result.failure is not None:
            return DisclosureAuditItem(name="fund_manager", status="missing", chapter=False, message="基金经理章节未找到")

        has_section = any(c.locator.locator_kind is LocatorKind.SECTION for c in routed.agent_result.citations)
        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
        fields = []
        if has_section:
            fields.append("name")
        if has_table:
            fields.append("appointment_date")
        status = "complete" if has_section else "partial"
        return DisclosureAuditItem(name="fund_manager", status=status, chapter=has_section, table=has_table if has_table else None, fields=tuple(fields))

    def _audit_dividends(self, host: MinimalHost, document_id: str, year: int) -> DisclosureAuditItem:
        """审计分红披露。"""

        routed = self._run_with_query_candidates(host=host, document_id=document_id, query="利润分配")
        if routed.agent_result.failure is not None:
            routed = self._run_with_query_candidates(host=host, document_id=document_id, query="分红")
            if routed.agent_result.failure is not None:
                return DisclosureAuditItem(name="dividends", status="missing", chapter=False, message="分红章节未找到")

        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
        fields = []
        if has_table:
            fields = ["amount", "date"]
        status = "complete" if has_table else "partial"
        return DisclosureAuditItem(name="dividends", status=status, chapter=True, table=has_table, fields=tuple(fields))

    def deep_audit_disclosure(
        self,
        request: DeepAuditRequest,
    ) -> DeepAuditResult:
        """深度披露完整性审计（基于 search + read_section）。

        参数:
            request: 深度审计请求。

        返回:
            DeepAuditResult；包含各披露项审计结果和汇总。
        """

        try:
            repository = _repository(Path(request.work_dir))
            catalog_reports = repository.list_reports()

            document_id = None
            for report in catalog_reports:
                if report.get("fund_code") == request.fund_code and report.get("year") == request.year:
                    document_id = str(report["document_id"])
                    break

            if document_id is None:
                return DeepAuditResult(
                    fund_code=request.fund_code,
                    year=request.year,
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message=f"catalog 中未找到 {request.fund_code} 的 {request.year} 年年报"),
                )

            store = repository.load_store(document_id)
            tool_service = FundDocumentToolService({document_id: store})

            audit_queries = [
                ("holdings", "持仓", "股票投资明细"),
                ("asset_allocation", "资产配置", "期末基金资产组合情况"),
                ("fee_rates", "费率", "基金管理费"),
                ("performance", "业绩", "基金份额净值增长率"),
                ("fund_manager", "基金经理", "基金经理"),
                ("dividends", "分红", "利润分配"),
            ]

            results: list[DeepAuditItem] = []
            for item_name, item_desc, query in audit_queries:
                try:
                    search_results = tool_service.search_document(document_id, query)
                    if isinstance(search_results, ToolFailure):
                        results.append(DeepAuditItem(
                            name=item_name,
                            status="fail",
                            completeness=f"{item_desc}搜索失败: {search_results.message}",
                            consistency="",
                            citation_text="",
                            raw_answer="",
                        ))
                        continue

                    if not search_results:
                        results.append(DeepAuditItem(
                            name=item_name,
                            status="fail",
                            completeness=f"未找到{item_desc}相关章节",
                            consistency="",
                            citation_text="",
                            raw_answer="",
                        ))
                        continue

                    first_hit = search_results[0]
                    section_ref = first_hit.section_ref
                    citation_text = f"section_ref={section_ref}" if section_ref else ""

                    content = ""
                    if section_ref:
                        section = tool_service.read_section(document_id, section_ref)
                        if isinstance(section, ToolFailure):
                            results.append(DeepAuditItem(
                                name=item_name,
                                status="fail",
                                completeness=f"{item_desc}章节读取失败: {section.message}",
                                consistency="",
                                citation_text=citation_text,
                                raw_answer="",
                            ))
                            continue
                        content = section.text
                    else:
                        content = first_hit.excerpt or ""

                    has_content = len(content) > 20
                    has_table = any(r.table_ref for r in search_results)

                    if has_content and has_table:
                        status = "pass"
                        completeness = f"找到{item_desc}章节和相关表格"
                    elif has_content:
                        status = "warning"
                        completeness = f"找到{item_desc}章节，未找到相关表格"
                    else:
                        status = "fail"
                        completeness = f"{item_desc}内容不完整"

                    results.append(DeepAuditItem(
                        name=item_name,
                        status=status,
                        completeness=completeness,
                        consistency="通过" if status == "pass" else "需人工验证",
                        citation_text=citation_text,
                        raw_answer=content[:200] if content else "",
                    ))
                except Exception as exc:
                    results.append(DeepAuditItem(
                        name=item_name,
                        status="fail",
                        completeness=f"{item_desc}审计执行失败: {exc}",
                        consistency="",
                        citation_text="",
                        raw_answer="",
                    ))

            pass_count = sum(1 for r in results if r.status == "pass")
            fail_count = sum(1 for r in results if r.status == "fail")
            warning_count = sum(1 for r in results if r.status == "warning")

            return DeepAuditResult(
                fund_code=request.fund_code,
                year=request.year,
                document_id=document_id,
                audit_results=tuple(results),
                summary={"pass": pass_count, "fail": fail_count, "warning": warning_count},
                failure=None,
            )
        except DocumentToolError as exc:
            return DeepAuditResult(
                fund_code=request.fund_code,
                year=request.year,
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception as exc:
            return DeepAuditResult(
                fund_code=request.fund_code,
                year=request.year,
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message=f"深度审计暂不可用: {exc}"),
            )

    def generate_report(
        self,
        request: GenerateReportRequest,
        llm_client: Any | None = None,
    ) -> GenerateReportResult:
        """生成基金分析报告。

        参数:
            request: 报告生成请求。
            llm_client: 可选 LLM client（DeepSeekLlmClient），用于生成分析文本；
                为 None 时使用模板填充。

        返回:
            GenerateReportResult；成功时包含 FundReport。
        """

        try:
            report_warnings: list[str] = []

            # 1. 提取多年度数据
            repository = _repository(Path(request.work_dir))
            catalog_reports = repository.list_reports()

            # 查找匹配的年报（按年份去重，保留最后一条）
            # 防污染（§6.25 裁决 17）：只匹配 annual_report，快照文档不进 generate 系列
            docs_by_year: dict[int, str] = {}
            available_years: list[int] = []
            for report in catalog_reports:
                if (
                    report.get("fund_code") == request.fund_code
                    and report.get("report_type") == "annual_report"
                ):
                    year = int(report["year"])
                    available_years.append(year)
                    docs_by_year[year] = str(report["document_id"])

            # 用户指定年份时过滤；否则使用 catalog 中全部可用年份
            if request.years:
                target_years = set(int(y) for y in request.years)
                docs_by_year = {y: d for y, d in docs_by_year.items() if y in target_years}

            annual_docs = [
                AnnualReportDocument(year=year, document_id=doc_id)
                for year, doc_id in sorted(docs_by_year.items())
            ]

            if not annual_docs:
                return GenerateReportResult(
                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message=f"未找到 {request.fund_code} 的年报数据"),
                )

            # 2. 提取各项数据（带 citation）
            holdings_data, holdings_citations, holdings_sources = self._extract_report_holdings_with_citations(
                request.fund_code, annual_docs, request.work_dir, fund_name=request.fund_name,
            )
            holdings_source_note = ""
            if request.holdings_source_fund and request.holdings_source_workdir is not None:
                source_extraction = self._extract_report_holdings_from_source(
                    annual_docs=annual_docs,
                    source_fund=request.holdings_source_fund,
                    source_work_dir=Path(request.holdings_source_workdir),
                )
                if source_extraction is None:
                    report_warnings.append("关联持仓源不可用，持仓数据保持本基金口径")
                else:
                    source_holdings, source_citations, source_years = source_extraction
                    if not source_holdings:
                        report_warnings.append("关联持仓源未提取到持仓数据，持仓数据保持本基金口径")
                    else:
                        holdings_data = source_holdings
                        holdings_citations = source_citations
                        holdings_source_note = f"来源：标的 ETF {request.holdings_source_fund} 年报"
                        holdings_sources = {year: holdings_source_note for year in source_years}
            fee_data, fee_citations = self._extract_report_fees_with_citations(
                request.fund_code, annual_docs, request.work_dir,
            )
            performance_data, performance_citations = self._extract_report_performance_with_citations(
                request.fund_code, annual_docs, request.work_dir,
            )
            allocation_data, allocation_citations = self._extract_report_allocation_with_citations(
                request.fund_code, annual_docs, request.work_dir,
            )
            fund_manager, fund_manager_citation = self._extract_fund_manager_with_citation(
                request.fund_code, annual_docs, request.work_dir, request.fund_name,
            )
            contract_effective_date, contract_citation = self._extract_contract_effective_date_with_citation(
                request.fund_code, annual_docs, request.work_dir, request.fund_name,
            )
            scale_info, scale_citation = self._extract_scale_info(request.fund_code, annual_docs, request.work_dir, request.fund_name)

            # 构建证据来源汇总
            evidence = ChapterEvidence(
                holdings_citations=holdings_citations,
                holdings_source_note=holdings_source_note,
                fee_citations=fee_citations,
                allocation_citations=allocation_citations,
                performance_citations=performance_citations,
                fund_manager_citation=fund_manager_citation,
                scale_citation=scale_citation,
                contract_citation=contract_citation,
            )

            # 计算确定性信号判断和风险清单
            signal_judgment = self.compute_signal_judgment(
                performance=performance_data,
                fees=fee_data,
                holdings=holdings_data,
                fund_manager=fund_manager,
                scale_info=scale_info,
                report_year=request.report_year,
                fund_name=request.fund_name,
            )
            risk_checklist = self.compute_risk_checklist(
                fees=fee_data,
                holdings=holdings_data,
                fund_manager=fund_manager,
                scale_info=scale_info,
                report_year=request.report_year,
                fund_name=request.fund_name,
            )

            # 3. 生成报告章节
            llm_warnings: list[str] = []
            if llm_client is not None:
                # 使用审计管道协调器（14C）
                from fund_agent.service.audit_pipeline import ReportGenerationCoordinator
                import os
                chapter_concurrency = request.chapter_concurrency
                if chapter_concurrency is None:
                    env_value = os.environ.get("FUND_CHECKLIST_CHAPTER_CONCURRENCY", "").strip()
                    chapter_concurrency = int(env_value) if env_value else 4
                coordinator = ReportGenerationCoordinator(
                    llm_client=llm_client,
                    work_dir=Path(request.work_dir),
                    chapter_concurrency=chapter_concurrency,
                )
                chapter_contents, coordinator_warnings = coordinator.generate_report(
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    report_year=request.report_year,
                    performance=performance_data,
                    holdings=holdings_data,
                    allocation=allocation_data,
                    fees=fee_data,
                    fund_manager=fund_manager,
                    scale_info=scale_info,
                    evidence=evidence,
                    signal_judgment=signal_judgment,
                    contract_effective_date=contract_effective_date,
                )
                llm_warnings.extend(coordinator_warnings)

                # 转换为 ReportChapter 列表
                chapter_specs = [
                    (0, "投资要点概览", ("performance", "holdings", "fees")),
                    (1, "这只基金到底是什么产品", ("basic_info",)),
                    (2, "R=A+B-C 收益归因", ("performance", "fees")),
                    (3, "基金经理画像与言行一致性", ("fund_manager",)),
                    (4, "投资者获得感", ()),
                    (5, "当前阶段与关键变化", ("performance", "allocation")),
                    (6, "核心风险与否决项", ("performance", "holdings")),
                    (7, "综合评估与跟踪建议", ("performance", "holdings")),
                ]
                chapters = []
                for chapter_id, title, data_sources in chapter_specs:
                    content = chapter_contents.get(chapter_id, "")
                    chapters.append(ReportChapter(
                        chapter_id=chapter_id,
                        title=title,
                        content=content,
                        data_sources=data_sources,
                    ))

                # 获取审计状态
                process_states = coordinator.get_process_states()
                passed_count = sum(1 for s in process_states.values() if s.status == "passed")
                failed_count = sum(1 for s in process_states.values() if s.status == "failed")
                llm_warnings.append(f"审计结果: {passed_count}章通过, {failed_count}章失败")

                # 报告级装配审计：章节集合/顺序/标题与模板 manifest 一致（回归防线）
                from fund_agent.service.audit_pipeline import verify_report_assembly
                from fund_agent.service.report_template import ANNUAL_TEMPLATE
                assembly_ok, assembly_problems = verify_report_assembly(
                    ANNUAL_TEMPLATE, chapters,
                )
                if not assembly_ok:
                    return GenerateReportResult(
                        failure=ToolFailure(
                            code=FailureCode.SCHEMA_DRIFT,
                            message="年报报告装配与模板 manifest 不一致: "
                            + "; ".join(assembly_problems),
                        ),
                    )

            else:
                chapters = self._generate_chapters(
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    report_year=request.report_year,
                    holdings=holdings_data,
                    fees=fee_data,
                    performance=performance_data,
                    allocation=allocation_data,
                    fund_manager=fund_manager,
                    scale_info=scale_info,
                    evidence=evidence,
                    signal_judgment=signal_judgment,
                    risk_checklist=risk_checklist,
                    contract_effective_date=contract_effective_date,
                )

            report = FundReport(
                fund_code=request.fund_code,
                fund_name=request.fund_name,
                report_year=request.report_year,
                chapters=tuple(chapters),
                metadata={
                    "generated_at": date.today().isoformat(),
                    "data_years": sorted(docs_by_year.keys()),
                    "template_version": "v2" if llm_client else "v1",
                    "generation_mode": "llm" if llm_client else "template",
                    "holdings_sources": holdings_sources,
                },
            )

            # 4. 输出
            output_path = None
            warnings: list[str] = list(report_warnings) + list(llm_warnings)
            if request.output_format == "markdown":
                output_path = self._export_markdown(report, request.work_dir, signal_judgment)
            elif request.output_format == "pdf":
                md_path = self._export_markdown(report, request.work_dir, signal_judgment)
                output_path, pdf_warning = self._export_pdf(md_path, request.work_dir)
                if pdf_warning:
                    warnings.append(pdf_warning)

            return GenerateReportResult(
                report=report,
                output_path=output_path,
                warnings=tuple(warnings),
                failure=None,
            )

        except DocumentToolError as exc:
            return GenerateReportResult(failure=ToolFailure(code=exc.code, message=exc.message))
        except Exception as exc:
            return GenerateReportResult(failure=ToolFailure(code=FailureCode.UNAVAILABLE, message=f"报告生成暂不可用: {exc}"))


    def generate_snapshot_report(
        self,
        request: SnapshotReportRequest,
        llm_client: Any | None = None,
    ) -> SnapshotReportResult:
        """生成季报/半年报单期快照报告（§6.25 裁决 10/11/16）。

        参数:
            request: 快照报告生成请求。
            llm_client: 可选 LLM client；None 时使用模板模式（数据表 + 模板章节）。

        返回:
            SnapshotReportResult；成功时包含 FundReport 与输出路径。
        """

        try:
            from fund_agent.service.report_template import (
                QUARTERLY_SNAPSHOT_TEMPLATE,
                QUARTERLY_SNAPSHOT_TEMPLATE_ID,
                SEMIANNUAL_SNAPSHOT_TEMPLATE,
                SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
            )
            from fund_agent.service.snapshot_extraction import extract_snapshot_data
            from fund_agent.service.snapshot_scoring import compute_snapshot_score

            template_id = (
                QUARTERLY_SNAPSHOT_TEMPLATE_ID
                if request.report_type == "quarterly_report"
                else SEMIANNUAL_SNAPSHOT_TEMPLATE_ID
            )
            template = (
                QUARTERLY_SNAPSHOT_TEMPLATE
                if request.report_type == "quarterly_report"
                else SEMIANNUAL_SNAPSHOT_TEMPLATE
            )
            work_dir = Path(request.work_dir)
            repository = _repository(work_dir)
            catalog_reports = repository.list_reports()

            # 按 fund_code + report_type + year (+ quarter) 匹配 catalog 已导入文档
            matches = [
                r for r in catalog_reports
                if r.get("fund_code") == request.fund_code
                and r.get("report_type") == request.report_type
                and r.get("year") == request.report_year
                and (request.quarter is None or r.get("quarter") == request.quarter)
            ]
            if not matches:
                return SnapshotReportResult(
                    failure=ToolFailure(
                        code=FailureCode.NOT_FOUND,
                        message=f"catalog 中未找到 {request.fund_code} {request.report_type} {request.report_year}"
                        + (f" Q{request.quarter}" if request.quarter else "") + " 文档",
                    ),
                )
            document_id = str(matches[0]["document_id"])
            store = repository.load_store(document_id)

            # 1. 快照确定性抽取
            data = extract_snapshot_data(
                document_id=document_id,
                store=store,
                fund_code=request.fund_code,
                fund_name=request.fund_name,
                report_year=request.report_year,
                template_id=template_id,
                quarter=request.quarter,
                period="H1" if request.report_type == "semiannual_report" else None,
            )
            snapshot_context = data.to_context_dict()
            snapshot_score = compute_snapshot_score(data)

            # 2. 生成章节
            warnings: list[str] = []
            chapter_contents: dict[int, str] = {}
            if llm_client is not None:
                from fund_agent.service.audit_pipeline import ReportGenerationCoordinator
                chapter_concurrency = request.chapter_concurrency
                if chapter_concurrency is None:
                    env_value = os.environ.get("FUND_CHECKLIST_CHAPTER_CONCURRENCY", "").strip()
                    chapter_concurrency = int(env_value) if env_value else 4
                coordinator = ReportGenerationCoordinator(
                    llm_client=llm_client,
                    work_dir=work_dir,
                    chapter_concurrency=chapter_concurrency,
                    template=template,
                )
                chapter_contents, coordinator_warnings = coordinator.generate_report(
                    fund_code=request.fund_code,
                    fund_name=request.fund_name,
                    report_year=request.report_year,
                    performance={},
                    holdings={},
                    allocation={},
                    fees={},
                    snapshot_data=snapshot_context,
                    snapshot_score=snapshot_score,
                    # 报告期透传：LLM 路径数据表格头部必须与标题期次一致
                    # （此前缺省导致「2026 年QNone」），半年报传 period="H1"。
                    quarter=request.quarter,
                    period="H1" if request.report_type == "semiannual_report" else None,
                )
                warnings.extend(coordinator_warnings)
            else:
                # 模板模式：数据表 + 模板章节
                for cid in template.chapter_ids:
                    data_table = template.build_data_table(
                        chapter_id=cid,
                        fund_code=request.fund_code,
                        fund_name=request.fund_name,
                        report_year=request.report_year,
                        quarter=request.quarter,
                        period="H1" if request.report_type == "semiannual_report" else None,
                        snapshot_data=snapshot_context,
                        snapshot_score=snapshot_score,
                    )
                    template_chapter = template.build_template_chapter(
                        chapter_id=cid,
                        fund_name=request.fund_name,
                        report_year=request.report_year,
                        quarter=request.quarter,
                        snapshot_data=snapshot_context,
                        snapshot_score=snapshot_score,
                    )
                    chapter_contents[cid] = data_table + "\n\n## 分析\n\n" + template_chapter

            # 章节按 chapter_id 升序组装（快照 template.chapter_ids 为生成顺序
            # front(1,2,3,4)+closing(0)，概览 ch0 最后生成但必须排在最前展示；
            # 以生成结果章节集合为准，缺章/多章交由装配校验 fail-closed）
            chapters = tuple(
                ReportChapter(
                    chapter_id=cid,
                    title=template.chapter_titles.get(cid, f"章节 {cid}"),
                    content=chapter_contents[cid],
                    data_sources=(),
                )
                for cid in sorted(chapter_contents.keys())
            )
            if any(not ch.content for ch in chapters):
                warnings.append("部分快照章节内容为空")

            # 报告级装配审计：章节集合/顺序/标题与模板 manifest 一致（违反 fail-closed）
            from fund_agent.service.audit_pipeline import verify_report_assembly
            assembly_ok, assembly_problems = verify_report_assembly(template, chapters)
            if not assembly_ok:
                return SnapshotReportResult(
                    failure=ToolFailure(
                        code=FailureCode.SCHEMA_DRIFT,
                        message="快照报告装配与模板 manifest 不一致: "
                        + "; ".join(assembly_problems),
                    ),
                )

            report = FundReport(
                fund_code=request.fund_code,
                fund_name=request.fund_name,
                report_year=request.report_year,
                chapters=chapters,
                metadata={
                    "generated_at": date.today().isoformat(),
                    "template_version": "snapshot-v1",
                    "generation_mode": "llm" if llm_client else "template",
                    "report_type": request.report_type,
                    "quarter": request.quarter,
                    "snapshot_score": {
                        "excess_score": snapshot_score.excess_score,
                        "position_score": snapshot_score.position_score,
                        "concentration_score": snapshot_score.concentration_score,
                        "total_score": snapshot_score.total_score,
                        "grade": snapshot_score.grade,
                    },
                },
            )

            # 3. 输出
            output_path = None
            if request.output_format in ("markdown", "pdf"):
                output_path = self._export_snapshot_markdown(report, work_dir, template_id, snapshot_score)
                if request.output_format == "pdf":
                    output_path, pdf_warning = self._export_pdf(output_path, work_dir)
                    if pdf_warning:
                        warnings.append(pdf_warning)

            return SnapshotReportResult(
                report=report,
                output_path=output_path,
                warnings=tuple(warnings),
                failure=None,
            )
        except DocumentToolError as exc:
            return SnapshotReportResult(failure=ToolFailure(code=exc.code, message=exc.message))
        except Exception as exc:
            return SnapshotReportResult(failure=ToolFailure(code=FailureCode.UNAVAILABLE, message=f"快照报告生成暂不可用: {exc}"))

    def _export_snapshot_markdown(
        self,
        report: FundReport,
        work_dir: Path,
        template_id: str,
        snapshot_score: Any = None,
    ) -> str:
        """导出快照 Markdown 文件（命名：{fund_code}-{year}Q{quarter}-quarterly-snapshot.md）。

        参数:
            report: 快照报告。
            work_dir: 工作目录。
            template_id: 快照模板 id（用于命名与标题）。
            snapshot_score: 快照评分（可选，用于 sidecar）。

        返回:
            Markdown 文件路径。
        """

        from fund_agent.service.report_template import QUARTERLY_SNAPSHOT_TEMPLATE_ID
        output_dir = Path(work_dir) / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        quarter = int(report.metadata.get("quarter") or 0) if report.metadata else 0
        if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID:
            base_name = f"{report.fund_code}-{report.report_year}Q{quarter}-quarterly-snapshot"
            report_label = "季度快照"
        else:
            base_name = f"{report.fund_code}-{report.report_year}H1-semiannual-snapshot"
            report_label = "半年度快照"
        output_path = output_dir / f"{base_name}.md"
        sidecar_path = output_dir / f"{base_name}.meta.json"

        period_label = f"{report.report_year}Q{quarter}" if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID else f"{report.report_year}H1"
        lines = [f"# {report.fund_name}（{report.fund_code}）{period_label} {report_label}\n"]
        lines.append(
            f"**风险警示与免责声明**：本文由 AI/大模型基于 {report.fund_name}（{report.fund_code}）"
            "已公开披露且可核查的基金季报、半年度报告、招募说明书及其他监管披露文件辅助生成，"
            "仅用于个人投资研究与信息交流之目的。因 AI/大模型存在幻觉，本文不可避免地会产生不完全符合报告原文的情况，"
            "阅读本文后产生的任何观点需核对原文，使用本文内容所产生的任何直接或间接后果，均由使用者自行承担。\n\n"
            "**风险提示**：本文所提到的观点仅代表个人的意见，所涉及标的不作推荐，据此买卖，风险自负。\n"
        )
        for chapter in report.chapters:
            lines.append(f"\n---\n\n## 第 {chapter.chapter_id + 1} 章：{chapter.title}\n")
            lines.append(chapter.content)

        output_path.write_text("\n".join(lines), encoding="utf-8")

        sidecar: dict[str, object] = {
            "fund_code": report.fund_code,
            "fund_name": report.fund_name,
            "report_year": report.report_year,
            "report_type": report.metadata.get("report_type") if report.metadata else None,
            "quarter": quarter or None,
            "generation_time": datetime.now(timezone.utc).isoformat(),
            "snapshot_score": report.metadata.get("snapshot_score") if report.metadata else None,
        }
        sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(output_path)

    def _extract_report_holdings_with_citations(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
        fund_name: str = "",
    ) -> tuple[dict[int, tuple[HoldingExtraction, ...]], dict[int, Citation | None], dict[int, str]]:
        """提取多年度持仓数据及 citation。

        返回:
            (持仓数据字典, citation 字典, 持仓来源字典)。
        """

        result = self.extract_multi_year_holdings(ExtractHoldingsRequest(
            fund_code=fund_code,
            requested_years=[d.year for d in annual_docs],
            annual_report_documents=annual_docs,
            work_dir=work_dir,
            fund_name=fund_name,
        ))
        if result.series is None:
            return {}, {}, {}
        holdings = {h.year: h.holdings for h in result.series.annual_holdings}
        citations = {h.year: h.citation for h in result.series.annual_holdings}
        sources = {h.year: h.holding_source for h in result.series.annual_holdings if h.holding_source}
        return holdings, citations, sources

    def _extract_report_holdings_from_source(
        self,
        *,
        annual_docs: list[AnnualReportDocument],
        source_fund: str,
        source_work_dir: Path,
    ) -> tuple[
        dict[int, tuple[HoldingExtraction, ...]],
        dict[int, Citation | None],
        tuple[int, ...],
    ] | None:
        """从关联持仓源工作目录按年度提取 top-10 持仓。

        参数:
            annual_docs: 目标基金的多年度文档（用于对齐年份）。
            source_fund: 关联持仓源基金代码（如标的 ETF 512890）。
            source_work_dir: 关联持仓源工作目录（如 .fund_checklist_512890）。

        返回:
            (按年份持仓 dict, 按年份 citation dict, 覆盖年份)；
            源目录无匹配年报或抽取失败时返回 None。
        """

        repository = _repository(source_work_dir)
        source_docs: list[AnnualReportDocument] = []
        source_name = ""
        target_years = {doc.year for doc in annual_docs}
        for record in repository.list_reports():
            if record.get("fund_code") != source_fund:
                continue
            # 防污染（§6.25 裁决 17）：关联持仓源只取 annual_report
            if record.get("report_type") != "annual_report":
                continue
            year = int(record["year"])
            if year not in target_years:
                continue
            source_docs.append(AnnualReportDocument(year=year, document_id=str(record["document_id"])))
            if not source_name:
                source_name = str(record.get("fund_name", ""))
        if not source_docs:
            return None

        result = self.extract_multi_year_holdings(ExtractHoldingsRequest(
            fund_code=source_fund,
            requested_years=[doc.year for doc in source_docs],
            annual_report_documents=source_docs,
            work_dir=source_work_dir,
            fund_name=source_name,
        ))
        if result.series is None:
            return None
        holdings = {h.year: h.holdings for h in result.series.annual_holdings}
        citations = {h.year: h.citation for h in result.series.annual_holdings}
        return holdings, citations, tuple(sorted(holdings.keys()))

    def _extract_report_fees_with_citations(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
    ) -> tuple[dict[int, tuple[FeeRateItem, ...]], dict[int, Citation | None]]:
        """提取多年度费率数据及 citation。

        返回:
            (费率数据字典, citation 字典)。
        """

        result = self.extract_multi_year_fee_rates(ExtractFeeRatesMultiYearRequest(
            fund_code=fund_code,
            requested_years=[d.year for d in annual_docs],
            annual_report_documents=annual_docs,
            work_dir=work_dir,
        ))
        if result.series is None:
            return {}, {}
        fees = {f.year: f.fees for f in result.series.annual_fees}
        citations = {f.year: f.citation for f in result.series.annual_fees}
        return fees, citations

    def _extract_report_performance_with_citations(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
    ) -> tuple[dict[int, dict[str, str]], dict[int, Citation | None]]:
        """提取多年度业绩数据及 citation。

        返回:
            (业绩数据字典, citation 字典)。
        """

        repository = _repository(Path(work_dir))
        performance: dict[int, dict[str, str]] = {}
        citations: dict[int, Citation | None] = {}

        for doc in annual_docs:
            try:
                store = repository.load_store(doc.document_id)
            except Exception:
                logger.warning("aggregate_multi_year: 加载 store 失败 doc=%s", doc.document_id, exc_info=True)
                continue
            result = self._extract_annual_performance_from_store(
                document_id=doc.document_id,
                store=store,
                report_year=doc.year,
                share_class=None,
            )
            if result.failure or not result.fields:
                continue
            # A/C 分段表支持后单年度可能同时返回 A/C 两类字段；
            # 报告口径统一优先 A 类，避免 last-wins 把 C 类值误写入报告。
            selected = _prefer_share_scope_fields(result.fields, _SHARE_SCOPE_A)
            nav = ""
            bench = ""
            citation = None
            for f in selected:
                if f.field_name == "annual_nav_growth_rate":
                    nav = f.decimal_percent_text
                    citation = f.citation
                elif f.field_name == "annual_benchmark_return_rate":
                    bench = f.decimal_percent_text
            if nav:
                excess = ""
                excess_result = self._extract_annual_excess_return_from_store(
                    document_id=doc.document_id,
                    store=store,
                    report_year=doc.year,
                    share_class=None,
                )
                if not excess_result.failure and excess_result.fields:
                    selected_excess = _prefer_share_scope_fields(excess_result.fields, _SHARE_SCOPE_A)
                    excess = selected_excess[0].decimal_percent_text
                performance[doc.year] = {
                    "nav_growth_rate": nav,
                    "benchmark_return_rate": bench,
                    "excess_return": excess,
                }
                citations[doc.year] = citation

        return performance, citations

    def _extract_report_allocation_with_citations(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
    ) -> tuple[dict[int, tuple[AssetAllocationItem, ...]], dict[int, Citation | None]]:
        """提取多年度资产配置数据及 citation。

        返回:
            (资产配置数据字典, citation 字典)。
        """

        result = self.extract_multi_year_allocation(ExtractAllocationRequest(
            fund_code=fund_code,
            requested_years=[d.year for d in annual_docs],
            annual_report_documents=annual_docs,
            work_dir=work_dir,
        ))
        if result.series is None:
            return {}, {}
        allocation = {a.year: a.asset_allocation for a in result.series.annual_allocations}
        citations = {a.year: a.citation for a in result.series.annual_allocations}
        return allocation, citations

    @staticmethod
    def _is_numeric_text(text: str) -> bool:
        """P0-2: 检测文本是否为纯数值（如合计行的金额"2,408,575.95"）。"""
        cleaned = text.strip().replace(",", "").replace("，", "")
        if not cleaned:
            return False
        if re.match(r"^-?[\d.]+$", cleaned):
            try:
                float(cleaned)
                return True
            except ValueError:
                pass
        return False

    def _extract_fund_manager(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
        fund_name: str = "",
    ) -> FundManagerInfo | None:
        """从最新年报提取基金经理信息（仅数据，不含 citation）。"""

        result, _ = self._extract_fund_manager_with_citation(fund_code, annual_docs, work_dir, fund_name)
        return result

    def _extract_fund_manager_with_citation(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
        fund_name: str = "",
    ) -> tuple[FundManagerInfo | None, Citation | None]:
        """从最新年报提取基金经理信息及 citation。

        返回:
            (FundManagerInfo, Citation)；未找到时返回 (None, None)。
        """

        if not annual_docs:
            return None, None

        latest_doc = max(annual_docs, key=lambda d: d.year)
        repository = _repository(Path(work_dir))
        try:
            store = repository.load_store(latest_doc.document_id)
        except Exception:
            return None, None

        tool_service = FundDocumentToolService({latest_doc.document_id: store})
        doc_id = latest_doc.document_id

        # 搜索基金经理简介表
        name = ""
        tenure_start = ""
        years_of_service = ""
        manager_citation = None
        search_results = tool_service.search_document(doc_id, "基金经理")
        for hit in search_results:
            if isinstance(hit, ToolFailure):
                continue
            if "简介" in (hit.title or "") and hit.section_ref:
                # 保存 citation
                manager_citation = Citation(
                    document_id=doc_id,
                    fund_code=fund_code,
                    fund_name=fund_name,
                    year=latest_doc.year,
                    report_type="annual_report",
                    locator=hit.locator if hasattr(hit, "locator") else Locator(
                        document_id=doc_id,
                        locator_kind=LocatorKind.SECTION,
                        section_ref=hit.section_ref,
                    ),
                )
                # 按列头内容匹配基金经理简介表（Docling 可能把 table 归到相邻 section）
                # 优先匹配 section_ref，fallback 按列头关键词匹配
                tables = tool_service.list_tables(doc_id)
                matched = False
                for t in tables:
                    if hasattr(t, "section_ref") and t.section_ref == hit.section_ref:
                        table = tool_service.read_table(doc_id, t.table_ref, max_rows=5)
                        if hasattr(table, "rows") and len(table.rows) >= 3:
                            # P0-2: 遍历数据行，跳过合计行（姓名列为纯数值）
                            for row_idx in range(2, len(table.rows)):
                                data_row = table.rows[row_idx]
                                if len(data_row) >= 5:
                                    candidate_name = str(data_row[0]).strip()
                                    if not candidate_name or self._is_numeric_text(candidate_name):
                                        continue
                                    name = candidate_name
                                    tenure_start = str(data_row[2]).strip()
                                    years_of_service = str(data_row[4]).strip()
                                    matched = True
                                    break
                # fallback: 按列头关键词匹配（姓名 + 从业年限）
                # 注：表头可能跨两行（Row0: 姓名/职务/期限/证券从业年限, Row1: 任职日期/离任日期）
                if not matched:
                    for t in tables:
                        table = tool_service.read_table(doc_id, t.table_ref, max_rows=2)
                        if hasattr(table, "rows") and len(table.rows) >= 1:
                            header_all = " ".join(str(c) for c in table.rows[0])
                            if len(table.rows) >= 2:
                                header_all += " " + " ".join(str(c) for c in table.rows[1])
                            # 合并连续空格后匹配（Docling 可能在表格列头中插入空格，如"从 业年限"）
                            header_normalized = re.sub(r"\s+", "", header_all)
                            if "姓名" in header_normalized and "从业" in header_normalized:
                                full_table = tool_service.read_table(doc_id, t.table_ref, max_rows=5)
                                if hasattr(full_table, "rows") and len(full_table.rows) >= 3:
                                    # P0-2: 遍历数据行，跳过合计行（姓名列为纯数值）
                                    for row_idx in range(2, len(full_table.rows)):
                                        data_row = full_table.rows[row_idx]
                                        if len(data_row) >= 5:
                                            candidate_name = str(data_row[0]).strip()
                                            if not candidate_name or self._is_numeric_text(candidate_name):
                                                continue
                                            name = candidate_name
                                            tenure_start = str(data_row[2]).strip()
                                            years_of_service = str(data_row[4]).strip()
                                            matched = True
                                            break
                                # 相邻表检测：Docling 可能将跨页表格拆分为表头表+数据表
                                # 当前表 header 匹配但无有效数据行时，检查相邻表
                                if not matched:
                                    try:
                                        t_idx = tables.index(t)
                                    except ValueError:
                                        t_idx = -1
                                    for offset in (1, 2):
                                        next_idx = t_idx + offset
                                        if t_idx >= 0 and next_idx < len(tables):
                                            next_t = tables[next_idx]
                                            next_table = tool_service.read_table(
                                                doc_id, next_t.table_ref, max_rows=5
                                            )
                                            if hasattr(next_table, "rows"):
                                                for row in next_table.rows:
                                                    if len(row) >= 5:
                                                        candidate_name = str(row[0]).strip()
                                                        if candidate_name and not self._is_numeric_text(candidate_name):
                                                            name = candidate_name
                                                            tenure_start = str(row[2]).strip() if len(row) > 2 else ""
                                                            years_of_service = str(row[4]).strip() if len(row) > 4 else ""
                                                            matched = True
                                                            break
                                        if matched:
                                            break
                if matched:
                    break

        # 搜索投资策略
        investment_strategy = ""
        strategy_results = tool_service.search_document(doc_id, "投资策略和运作分析")
        for hit in strategy_results:
            if isinstance(hit, ToolFailure):
                continue
            if hit.section_ref:
                section = tool_service.read_section(doc_id, hit.section_ref)
                if hasattr(section, "text") and len(section.text) > 50:
                    investment_strategy = section.text[:500].strip()
                    break

        # 搜索基金经理持有本基金：9.4 节数量区间披露表优先；
        # 全文档无 9.4 时回退 9.2 从业人员整体持有表（口径嵌入 holds_fund 文本）。
        # 两遍扫描保证文档中先出现的 9.2 整体表不会抢占 9.4 区间结果。
        holds_fund = ""
        fallback_overall = ""
        tables = tool_service.list_tables(doc_id)
        for t in tables:
            table = tool_service.read_table(doc_id, t.table_ref, max_rows=10)
            if not hasattr(table, "rows"):
                continue
            holds_fund = _extract_manager_holds_fund(table.rows)
            if holds_fund:
                break
            if not fallback_overall:
                fallback_overall = _extract_manager_holds_overall(table.rows)
        if not holds_fund:
            holds_fund = fallback_overall

        if not name:
            return None, manager_citation

        return FundManagerInfo(
            name=name,
            tenure_start=tenure_start,
            years_of_service=years_of_service,
            investment_strategy=investment_strategy,
            holds_fund=holds_fund,
        ), manager_citation

    def _extract_contract_effective_date_with_citation(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
        fund_name: str = "",
    ) -> tuple[str, Citation | None]:
        """从最新年报提取基金合同生效日及 citation（建仓期判定真源）。

        主路径：search_document("基金简介") 锚定标题含「基金简介」的节，扫描该节
        section_ref 匹配的表，行文本含「基金合同生效日」且日期紧跟短语时归一化为
        "YYYY-MM-DD"，Citation locator_kind=TABLE；回退 1：search_document
        ("基金合同生效日") 逐命中节同样表行扫描；回退 2：read_section 节文本正则
        （日期必须紧跟短语，规避经理任职口径误取），Citation locator_kind=SECTION；
        全部失败返回 ("", None) fail-closed。

        参数:
            fund_code: 基金代码。
            annual_docs: 多年度年报文档列表。
            work_dir: 受控工作目录。
            fund_name: 基金名称（写入 citation）。

        返回:
            (归一化日期 "YYYY-MM-DD" 或 "", Citation 或 None)。
        """

        if not annual_docs:
            return "", None

        latest_doc = max(annual_docs, key=lambda d: d.year)
        repository = _repository(Path(work_dir))
        try:
            store = repository.load_store(latest_doc.document_id)
        except Exception:
            return "", None

        tool_service = FundDocumentToolService({latest_doc.document_id: store})
        doc_id = latest_doc.document_id

        def _scan_table_rows(tables: tuple[TableSummary, ...], section_ref: str | None) -> tuple[str, Citation | None]:
            """扫描指定节下的表行，命中「基金合同生效日」且日期紧跟短语。"""

            for t in tables:
                if t.section_ref != section_ref:
                    continue
                table = tool_service.read_table(doc_id, t.table_ref, max_rows=40)
                if not hasattr(table, "rows"):
                    continue
                for row in table.rows:
                    row_text = " ".join(str(cell) for cell in row)
                    if "基金合同生效日" not in row_text:
                        continue
                    match = _CONTRACT_EFFECTIVE_DATE_RE.search(row_text)
                    if match:
                        return _normalize_contract_effective_date(*match.groups()), table.citation
            return "", None

        def _scan_section_text(section_ref: str) -> tuple[str, Citation | None]:
            """从节正文正则提取合同生效日（日期必须紧跟短语）。"""

            section = tool_service.read_section(doc_id, section_ref)
            if not hasattr(section, "text"):
                return "", None
            match = _CONTRACT_EFFECTIVE_DATE_RE.search(section.text) or _CONTRACT_EXECUTED_RE.search(section.text)
            if match:
                return _normalize_contract_effective_date(*match.groups()), section.citation
            return "", None

        # 主路径：锚定标题含「基金简介」的节
        search_results = tool_service.search_document(doc_id, "基金简介")
        if not isinstance(search_results, ToolFailure):
            for hit in search_results:
                if "基金简介" in (hit.title or "") and hit.section_ref:
                    tables = tool_service.list_tables(doc_id)
                    if isinstance(tables, ToolFailure):
                        continue
                    date, citation = _scan_table_rows(tables, hit.section_ref)
                    if date:
                        return date, citation

        # 回退 1：search_document("基金合同生效日") 逐命中节同样表行扫描
        search_results = tool_service.search_document(doc_id, "基金合同生效日")
        if not isinstance(search_results, ToolFailure):
            for hit in search_results:
                if not hit.section_ref:
                    continue
                tables = tool_service.list_tables(doc_id)
                if isinstance(tables, ToolFailure):
                    continue
                date, citation = _scan_table_rows(tables, hit.section_ref)
                if date:
                    return date, citation

        # 回退 2：read_section 节文本正则（只取「基金简介」节，规避任职口径误取）
        search_results = tool_service.search_document(doc_id, "基金简介")
        if not isinstance(search_results, ToolFailure):
            for hit in search_results:
                if "基金简介" in (hit.title or "") and hit.section_ref:
                    date, citation = _scan_section_text(hit.section_ref)
                    if date:
                        return date, citation

        return "", None

    def _extract_scale_info(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
        fund_name: str = "",
    ) -> tuple[ScaleInfo | None, Citation | None]:
        """从年报提取规模信息及 citation（从最新年份开始尝试，回退到更早年份）。

        采用 header-first 列映射：先定位表头行构建 class→col_index，
        再找期末行按列索引读取份额，NAV 用同样类名匹配策略，
        AUM = 份额_A × NAV_A + 份额_C × NAV_C。
        """

        if not annual_docs:
            return None, None

        repository = _repository(Path(work_dir))
        sorted_docs = sorted(annual_docs, key=lambda d: d.year, reverse=True)

        _class_exclude_kw = ("NAV", "AUM", "标准差")

        for doc in sorted_docs:
            try:
                store = repository.load_store(doc.document_id)
            except Exception:
                continue

            tool_service = FundDocumentToolService({doc.document_id: store})
            doc_id = doc.document_id

            total_shares_a = ""
            total_shares_c = ""
            individual_investor_ratio = ""
            scale_citation = None

            # 搜索份额变动表（§10）
            search_results = tool_service.search_document(doc_id, "开放式基金份额变动")
            for hit in search_results:
                if isinstance(hit, ToolFailure) or not hit.section_ref:
                    continue
                if scale_citation is None:
                    scale_citation = Citation(
                        document_id=doc_id,
                        fund_code=fund_code,
                        fund_name=fund_name,
                        year=doc.year,
                        report_type="annual_report",
                        locator=hit.locator if hasattr(hit, "locator") else Locator(
                            document_id=doc_id,
                            locator_kind=LocatorKind.SECTION,
                            section_ref=hit.section_ref,
                        ),
                    )
                tables = tool_service.list_tables(doc_id)
                for t in tables:
                    if not (hasattr(t, "section_ref") and t.section_ref == hit.section_ref):
                        continue
                    table = tool_service.read_table(doc_id, t.table_ref, max_rows=20)
                    if not hasattr(table, "rows"):
                        continue

                    # header-first: 找包含"项目"的 header row，构建 {class_label: col_index}
                    col_map: dict[str, int] = {}
                    end_row: tuple[str, ...] | None = None

                    for row in table.rows:
                        if not row:
                            continue
                        row_0_norm = _normalize_disclosure_text(row[0])

                        # header row
                        if not col_map and "项目" in row_0_norm:
                            for idx, cell in enumerate(row):
                                if idx == 0:
                                    continue
                                cell_norm = _normalize_disclosure_text(cell)
                                if any(kw in cell_norm for kw in _class_exclude_kw):
                                    continue
                                cls = _detect_share_class(cell)
                                if cls == "A":
                                    col_map["A"] = idx
                                elif cls == "C":
                                    col_map["C"] = idx

                        # 期末行：匹配"期末基金份额总额"及其变体（如"报告期末基金份额总额"），
                        # 以及分级基金行（如"下属分级基金的份额总额"）
                        if row_0_norm.endswith("期末基金份额总额") or row_0_norm.endswith("级基金的份额总额"):
                            end_row = row

                    # header-first 兜底：部分基金表格第一列为空，但列头直接是份额类别名
                    if not col_map and end_row and table.rows:
                        row0 = table.rows[0]
                        for idx, cell in enumerate(row0):
                            if idx == 0:
                                continue
                            cell_norm = _normalize_disclosure_text(cell)
                            if any(kw in cell_norm for kw in _class_exclude_kw):
                                continue
                            cls = _detect_share_class(cell)
                            if cls == "A":
                                col_map["A"] = idx
                            elif cls == "C":
                                col_map["C"] = idx

                    # 列位置兜底：份额变动表固定结构 col1=A类, col2=C类
                    if not col_map and end_row:
                        if len(end_row) >= 2:
                            col_map["A"] = 1
                        if len(end_row) >= 3:
                            col_map["C"] = 2

                    # 从期末行按列索引读取份额
                    if col_map and end_row:
                        if "A" in col_map and col_map["A"] < len(end_row):
                            total_shares_a = str(end_row[col_map["A"]]).strip()
                        if "C" in col_map and col_map["C"] < len(end_row):
                            total_shares_c = str(end_row[col_map["C"]]).strip()

                    # 持有人结构：合计行
                    for row in table.rows:
                        if not row:
                            continue
                        row_0_norm = _normalize_disclosure_text(row[0])
                        if "合计" in row_0_norm and len(row) > 4:
                            individual_investor_ratio = str(row[4]).strip()

            if not (total_shares_a or total_shares_c):
                # 文本兜底：从段落中提取份额数据
                for query in ("基金份额总额", "基金份额变动"):
                    text_hits = tool_service.search_document(doc_id, query)
                    for th in text_hits:
                        if isinstance(th, ToolFailure) or not th.section_ref:
                            continue
                        section = tool_service.read_section(doc_id, th.section_ref)
                        if not hasattr(section, "text"):
                            continue
                        extracted = _extract_scale_from_text(section.text)
                        if extracted.get("total_shares_a"):
                            total_shares_a = extracted["total_shares_a"]
                        if extracted.get("total_shares_c"):
                            total_shares_c = extracted["total_shares_c"]
                        if total_shares_a or total_shares_c:
                            break
                    if total_shares_a or total_shares_c:
                        break

                # 文本兜底：持有人比例
                if not individual_investor_ratio:
                    holder_hits = tool_service.search_document(doc_id, "持有人")
                    for hh in holder_hits:
                        if isinstance(hh, ToolFailure) or not hh.section_ref:
                            continue
                        section = tool_service.read_section(doc_id, hh.section_ref)
                        if not hasattr(section, "text"):
                            continue
                        extracted = _extract_scale_from_text(section.text)
                        if extracted.get("individual_investor_ratio"):
                            individual_investor_ratio = extracted["individual_investor_ratio"]
                            break

            if not (total_shares_a or total_shares_c):
                continue

            # NAV 提取：用同样类名匹配策略
            estimated_aum = ""
            nav_results = tool_service.search_document(doc_id, "基金份额净值")
            for hit in nav_results:
                if isinstance(hit, ToolFailure) or not hit.section_ref:
                    continue
                section = tool_service.read_section(doc_id, hit.section_ref)
                if not hasattr(section, "text"):
                    continue
                text = section.text

                # 类名匹配提取 NAV
                nav_a = _extract_nav_for_class(text, "A")
                nav_c = _extract_nav_for_class(text, "C")

                total_aum = 0.0
                if nav_a is not None and total_shares_a:
                    try:
                        total_aum += nav_a * float(total_shares_a.replace(",", ""))
                    except (ValueError, IndexError):
                        pass
                if nav_c is not None and total_shares_c:
                    try:
                        total_aum += nav_c * float(total_shares_c.replace(",", ""))
                    except (ValueError, IndexError):
                        pass

                if total_aum > 0:
                    if total_aum >= 1e8:
                        estimated_aum = f"{total_aum / 1e8:.2f}亿元"
                    elif total_aum >= 1e4:
                        estimated_aum = f"{total_aum / 1e4:.2f}万元"
                    else:
                        estimated_aum = f"{total_aum:.2f}元"
                break

            # Fallback: class-specific NAV regex may fail when report writes
            # "基金份额净值 X.XX元（A类）" (NAV before class label).
            # Try class-neutral matching so shares×NAV can still produce estimated_aum.
            if not estimated_aum:
                for hit in nav_results:
                    if isinstance(hit, ToolFailure) or not hit.section_ref:
                        continue
                    section = tool_service.read_section(doc_id, hit.section_ref)
                    if not hasattr(section, "text"):
                        continue
                    text = section.text
                    m = re.search(r'基金份额净值\s*(?:为)?\s*([\d.]+)\s*元', text)
                    if m:
                        try:
                            nav_value = float(m.group(1))
                            total_shares = 0.0
                            for shares_str in (total_shares_a, total_shares_c):
                                if shares_str:
                                    try:
                                        total_shares += float(shares_str.replace(",", ""))
                                    except (ValueError, IndexError):
                                        pass
                            if total_shares > 0:
                                total_aum = nav_value * total_shares
                                if total_aum >= 1e8:
                                    estimated_aum = f"{total_aum / 1e8:.2f}亿元"
                                elif total_aum >= 1e4:
                                    estimated_aum = f"{total_aum / 1e4:.2f}万元"
                                else:
                                    estimated_aum = f"{total_aum:.2f}元"
                        except (ValueError, IndexError):
                            pass
                    if estimated_aum:
                        break

            return ScaleInfo(
                total_shares_a=total_shares_a,
                total_shares_c=total_shares_c,
                individual_investor_ratio=individual_investor_ratio,
                management_holds="",
                estimated_aum=estimated_aum,
            ), scale_citation

        return None, None

    def _generate_chapters(
        self,
        *,
        fund_code: str,
        fund_name: str,
        report_year: int,
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        performance: dict[int, dict[str, str]],
        allocation: dict[int, tuple[AssetAllocationItem, ...]],
        fund_manager: FundManagerInfo | None = None,
        scale_info: ScaleInfo | None = None,
        evidence: ChapterEvidence | None = None,
        signal_judgment: SignalJudgment | None = None,
        risk_checklist: tuple[RiskChecklistItem, ...] | None = None,
        contract_effective_date: str = "",
    ) -> list[ReportChapter]:
        """生成 8 章报告内容（模板对齐版）。"""

        chapters: list[ReportChapter] = []

        stress_test = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name)

        chapter_specs = [
            (0, "投资要点概览", ("performance", "holdings", "fees")),
            (1, "这只基金到底是什么产品", ("basic_info",)),
            (2, "R=A+B-C 收益归因", ("performance", "fees")),
            (3, "基金经理画像与言行一致性", ("fund_manager",)),
            (4, "投资者获得感", ()),
            (5, "当前阶段与关键变化", ("performance", "allocation")),
            (6, "核心风险与否决项", ("performance", "holdings")),
            (7, "综合评估与跟踪建议", ("performance", "holdings")),
        ]

        for chapter_id, title, data_sources in chapter_specs:
            content = self._generate_template_chapter(
                chapter_id, fund_code, fund_name, report_year,
                performance, holdings, allocation, fees,
                fund_manager, scale_info, evidence,
                signal_judgment, risk_checklist,
                stress_test=stress_test if chapter_id == 6 else None,
                contract_effective_date=contract_effective_date,
            )
            chapters.append(ReportChapter(
                chapter_id=chapter_id,
                title=title,
                content=content,
                data_sources=data_sources,
            ))

        # 报告级装配审计：章节集合/顺序/标题与模板 manifest 一致（模板模式同样生效）
        from fund_agent.service.audit_pipeline import verify_report_assembly
        from fund_agent.service.report_template import ANNUAL_TEMPLATE
        assembly_ok, assembly_problems = verify_report_assembly(ANNUAL_TEMPLATE, chapters)
        if not assembly_ok:
            raise DocumentToolError(
                code=FailureCode.SCHEMA_DRIFT,
                message="年报模板章节装配与模板 manifest 不一致: "
                + "; ".join(assembly_problems),
            )

        return chapters

    def _generate_ch2_performance(self, performance: dict[int, dict[str, str]]) -> str:
        """生成业绩分析章节。"""

        lines = ["## 业绩表现\n", "| 年份 | 净值增长率 | 基准收益率 | 超额收益 |", "|------|-----------|-----------|---------|"]
        for year in sorted(performance.keys()):
            p = performance[year]
            lines.append(f"| {year} | {p.get('nav_growth_rate', '缺失')} | {p.get('benchmark_return_rate', '缺失')} | {p.get('excess_return', '缺失')} |")
        return "\n".join(lines) + "\n"


    def compute_signal_judgment(
        self,
        *,
        performance: dict[int, dict[str, str]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        fund_manager: FundManagerInfo | None = None,
        scale_info: ScaleInfo | None = None,
        report_year: int = 2024,
        fund_name: str = "",
    ) -> SignalJudgment:
        """计算确定性信号判断（fund_type 感知路由）。

        被动基金（index_etf/index_fund/index_feeder）：3 指标 100 分制，
        债券基金：5 指标（无风格漂移），主动基金：6 指标 135→100。

        参数:
            performance: 多年度业绩数据。
            fees: 多年度费率数据。
            holdings: 多年度持仓数据。
            fund_manager: 基金经理信息（可选）。
            scale_info: 规模信息（可选）。
            report_year: 报告年份。
            fund_name: 基金名称（用于 fund_type 推断）。

        返回:
            SignalJudgment，包含信号、归一化分数、指标明细和警告。
        """
        from .signal_scoring import _infer_fee_kwargs, get_applicable_indicators

        # 推断基金类型
        fund_type = ""
        if fund_name:
            fund_type, _ = infer_fund_type(fund_name)

        # 被动基金路由（非增强指数基金）
        if fund_type in ("index_etf", "index_feeder") or (
            fund_type == "index_fund" and fund_name and "增强" not in fund_name
        ):
            fee_kw = _infer_fee_kwargs(fund_name, fund_type)
            return self._compute_passive_signal(
                fees=fees,
                holdings=holdings,
                scale_info=scale_info,
                report_year=report_year,
                fee_kwargs=fee_kw,
            )

        # 债券基金路由
        if fund_type == "bond_fund":
            fee_kw = _infer_fee_kwargs(fund_name, fund_type)
            return self._compute_bond_signal(
                performance=performance,
                fees=fees,
                holdings=holdings,
                fund_manager=fund_manager,
                scale_info=scale_info,
                report_year=report_year,
                fee_kwargs=fee_kw,
            )

        # 主动基金 / 增强指数基金：现有 6 指标模型
        applicable = dict(get_applicable_indicators(fund_type))
        if fund_type == "index_fund" and fund_name and "增强" in fund_name:
            applicable["超额收益趋势"] = True
            applicable["风格漂移"] = True
            applicable["基金经理变更"] = True

        return self._compute_active_signal(
            performance=performance,
            fees=fees,
            holdings=holdings,
            fund_manager=fund_manager,
            scale_info=scale_info,
            report_year=report_year,
            applicable=applicable,
        )

    def _compute_active_signal(
        self,
        *,
        performance: dict[int, dict[str, str]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        fund_manager: FundManagerInfo | None,
        scale_info: ScaleInfo | None,
        report_year: int,
        applicable: dict[str, bool],
    ) -> SignalJudgment:
        """主动基金 6 指标评分（135→100 归一化）。"""

        all_scored: list[tuple[str, _ScoredIndicator, bool]] = []
        all_scored.append(("超额收益趋势", score_excess_returns(performance), applicable.get("超额收益趋势", True)))
        all_scored.append(("费率水平", score_fee_rate(fees, report_year), applicable.get("费率水平", True)))
        all_scored.append(("风格漂移", score_style_drift(holdings), applicable.get("风格漂移", True)))
        all_scored.append(("规模风险", score_scale_risk(scale_info), applicable.get("规模风险", True)))
        all_scored.append(("基金经理变更", score_manager_change(fund_manager, report_year), applicable.get("基金经理变更", True)))
        all_scored.append(("持仓集中度", score_concentration(holdings), applicable.get("持仓集中度", True)))

        applicable_scored = [(name, s) for name, s, appl in all_scored if appl]
        skipped = [(name, s) for name, s, appl in all_scored if not appl]

        total_applicable = len(applicable_scored)
        indicators = tuple(to_signal_indicator(s) for _, s in applicable_scored)
        indicators = indicators + tuple(
            SignalIndicator(name=name, score=0, max_score=0, detail="不适用（该基金类型无需评估此指标）")
            for name, _ in skipped
        )
        warnings = tuple(
            f"{s.name}：{s.detail}" for _, s, _ in all_scored if not s.calculable
        )
        calculable_count = sum(1 for _, s, _ in all_scored if s.calculable)

        total_score = sum(s.score for _, s in applicable_scored)
        total_max = sum(s.max_score for _, s in applicable_scored)
        normalized = round(total_score / total_max * 100) if total_max > 0 else 0

        if total_applicable == 0:
            signal = "🟡 需要关注"
            warnings = ("无适用指标，默认 🟡 需要关注",) + warnings
        elif calculable_count < 3:
            signal = "🟡 需要关注"
            warnings = (f"数据不足（可计算指标 {calculable_count}/6 < 3），默认 🟡 需要关注",) + warnings
        elif normalized >= 75:
            signal = "🟢 值得持有"
        elif normalized >= 50:
            signal = "🟡 需要关注"
        else:
            signal = "🔴 建议替换"

        upgrade_event, downgrade_event = _compute_threshold_events(
            [s for _, s in applicable_scored]
        )

        return SignalJudgment(
            signal=signal,
            normalized_score=normalized,
            indicators=indicators,
            data_completeness=calculable_count / 6,
            warnings=warnings,
            upgrade_event=upgrade_event,
            downgrade_event=downgrade_event,
        )

    def _compute_passive_signal(
        self,
        *,
        fees: dict[int, tuple[FeeRateItem, ...]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        scale_info: ScaleInfo | None,
        report_year: int,
        fee_kwargs: dict,
    ) -> SignalJudgment:
        """被动基金 3 指标评分（40+30+30=100 直接分制）。"""
        fee = score_fee_rate(fees, report_year, **fee_kwargs)
        scale = score_scale_risk(scale_info, max_score=30)
        concentration = score_concentration(holdings, max_score=30)

        scored = [fee, scale, concentration]
        total_score = fee.score + scale.score + concentration.score
        total_max = fee.max_score + scale.max_score + concentration.max_score  # 100
        normalized = round(total_score / total_max * 100) if total_max > 0 else 0
        calculable_count = sum(1 for s in scored if s.calculable)

        indicators = (
            to_signal_indicator(fee),
            to_signal_indicator(scale),
            to_signal_indicator(concentration),
            SignalIndicator(name="超额收益趋势", score=0, max_score=0, detail="不适用（被动基金目标为跟踪指数）"),
            SignalIndicator(name="风格漂移", score=0, max_score=0, detail="不适用（被动基金应跟踪指数）"),
            SignalIndicator(name="基金经理变更", score=0, max_score=0, detail="不适用（经理变更对被动基金影响较小）"),
        )

        warnings = tuple(s.detail for s in scored if not s.calculable)
        if calculable_count < 2:
            signal = "🟡 需要关注"
            warnings = ("数据不足（可计算指标 < 2），默认 🟡 需要关注",) + warnings
        elif normalized >= 75:
            signal = "🟢 值得持有"
        elif normalized >= 50:
            signal = "🟡 需要关注"
        else:
            signal = "🔴 建议替换"

        upgrade_event, downgrade_event = _compute_threshold_events(scored)

        return SignalJudgment(
            signal=signal,
            normalized_score=normalized,
            indicators=indicators,
            data_completeness=calculable_count / 3,
            warnings=warnings,
            upgrade_event=upgrade_event,
            downgrade_event=downgrade_event,
        )

    def _compute_bond_signal(
        self,
        *,
        performance: dict[int, dict[str, str]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        fund_manager: FundManagerInfo | None,
        scale_info: ScaleInfo | None,
        report_year: int,
        fee_kwargs: dict,
    ) -> SignalJudgment:
        """债券基金 5 指标评分（无风格漂移，110→100 归一化）。"""
        excess = score_excess_returns(performance)
        fee = score_fee_rate(fees, report_year, **fee_kwargs)
        scale = score_scale_risk(scale_info)
        manager = score_manager_change(fund_manager, report_year)
        concentration = score_concentration(holdings)

        scored = [excess, fee, scale, manager, concentration]
        total_score = sum(s.score for s in scored)
        total_max = sum(s.max_score for s in scored)  # 110
        normalized = round(total_score / total_max * 100) if total_max > 0 else 0
        calculable_count = sum(1 for s in scored if s.calculable)

        indicators = (
            to_signal_indicator(excess),
            to_signal_indicator(fee),
            to_signal_indicator(scale),
            to_signal_indicator(manager),
            to_signal_indicator(concentration),
            SignalIndicator(name="风格漂移", score=0, max_score=0, detail="不适用（债券基金无需评估股票持仓重叠率）"),
        )

        warnings = tuple(s.detail for s in scored if not s.calculable)
        if calculable_count < 2:
            signal = "🟡 需要关注"
            warnings = ("数据不足（可计算指标 < 2），默认 🟡 需要关注",) + warnings
        elif normalized >= 75:
            signal = "🟢 值得持有"
        elif normalized >= 50:
            signal = "🟡 需要关注"
        else:
            signal = "🔴 建议替换"

        upgrade_event, downgrade_event = _compute_threshold_events(scored)

        return SignalJudgment(
            signal=signal,
            normalized_score=normalized,
            indicators=indicators,
            data_completeness=calculable_count / 5,
            warnings=warnings,
            upgrade_event=upgrade_event,
            downgrade_event=downgrade_event,
        )

    def compute_risk_checklist(
        self,
        *,
        fees: dict[int, tuple[FeeRateItem, ...]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        fund_manager: FundManagerInfo | None = None,
        scale_info: ScaleInfo | None = None,
        report_year: int = 2024,
        fund_name: str = "",
    ) -> tuple[RiskChecklistItem, ...]:
        """计算 6 项风险清单检查（fund_type 感知）。

        不适用指标标记为「🟢 不适用」。

        参数:
            fees: 多年度费率数据。
            holdings: 多年度持仓数据。
            fund_manager: 基金经理信息（可选）。
            scale_info: 规模信息（可选）。
            report_year: 报告年份。
            fund_name: 基金名称（用于 fund_type 推断）。

        返回:
            6 项 RiskChecklistItem 的 tuple。
        """
        from .signal_scoring import get_applicable_indicators

        fund_type = ""
        if fund_name:
            fund_type, _ = infer_fund_type(fund_name)
        applicable = get_applicable_indicators(fund_type)

        scored = [
            score_scale_risk(scale_info),
            score_manager_change(fund_manager, report_year),
            score_style_drift(holdings),
            score_fee_rate(fees, report_year),
            # 换手率暂不可用，固定绿
            None,
            score_concentration(holdings),
        ]
        risk_names = ["清盘风险", "基金经理变更", "风格漂移", "费率远超同类", "换手率异常", "持仓过度集中"]
        indicator_keys = ["规模风险", "基金经理变更", "风格漂移", "费率水平", None, "持仓集中度"]

        items = []
        for s, name, key in zip(scored, risk_names, indicator_keys):
            if key is not None and not applicable.get(key, True):
                items.append(RiskChecklistItem(name, "🟢", "不适用（该基金类型无需评估）"))
            elif s is None:
                items.append(RiskChecklistItem(name, "🟢", "数据暂不可用"))
            else:
                items.append(to_risk_item(s, risk_name=name))

        return tuple(items)


    def _generate_chapters_with_llm(
        self,
        *,
        llm_client: Any,
        fund_code: str,
        fund_name: str,
        report_year: int,
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        performance: dict[int, dict[str, str]],
        allocation: dict[int, tuple[AssetAllocationItem, ...]],
        fund_manager: FundManagerInfo | None,
        scale_info: ScaleInfo | None,
        signal_judgment: SignalJudgment | None = None,
        risk_checklist: tuple[RiskChecklistItem, ...] | None = None,
    ) -> tuple[list[ReportChapter], list[str]]:
        """使用 LLM 逐章生成分析文本（两阶段：程序表格 + LLM 分析）。

        数字 100% 从数据 dict 提取，LLM 只写定性分析，消除 hallucination。

        参数:
            llm_client: DeepSeekLlmClient 实例。
            fund_code: 基金代码。
            fund_name: 基金名称。
            report_year: 报告年份。
            holdings: 多年度持仓数据。
            fees: 多年度费率数据。
            performance: 多年度业绩数据。
            allocation: 多年度资产配置数据。
            fund_manager: 基金经理信息。
            scale_info: 规模信息。

        返回:
            (章节列表, 警告列表)。
        """

        generator = LlmChapterGenerator(llm_client=llm_client)
        warnings: list[str] = []
        chapters: list[ReportChapter] = []

        # 推断基金类型（用于章节条件渲染）
        fund_type = ""
        if fund_name:
            fund_type, _ = infer_fund_type(fund_name)

        # 计算压力测试
        stress_test = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name)

        chapter_specs = [
            (0, "投资要点概览", ("performance", "holdings", "fees")),
            (1, "这只基金到底是什么产品", ("basic_info",)),
            (2, "R=A+B-C 收益归因", ("performance", "fees")),
            (3, "基金经理画像与言行一致性", ("fund_manager",)),
            (4, "投资者获得感", ()),
            (5, "当前阶段与关键变化", ("performance", "allocation")),
            (6, "核心风险与否决项", ("performance", "holdings")),
            (7, "综合评估与跟踪建议", ("performance", "holdings")),
        ]

        for chapter_id, title, data_sources in chapter_specs:
            content = generator.generate_chapter(
                chapter_id=chapter_id,
                fund_code=fund_code,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                holdings=holdings,
                allocation=allocation,
                fees=fees,
                fund_manager=fund_manager,
                scale_info=scale_info,
                stress_test=stress_test if chapter_id == 6 else None,
                signal_judgment=signal_judgment,
                fund_type=fund_type,
            )

            if content is None:
                content = self._generate_template_chapter(
                    chapter_id, fund_code, fund_name, report_year,
                    performance, holdings, allocation, fees,
                    fund_manager, scale_info,
                    signal_judgment=signal_judgment,
                    risk_checklist=risk_checklist,
                )
                warnings.append(f"Ch{chapter_id} LLM 分析失败，已回退模板")
            else:
                                # LLM 成功时，追加确定性结构化区块（信号/风险）
                if chapter_id == 6 and risk_checklist:
                    risk_lines = [
                        "\n## 风险清单\n",
                        "| 风险项 | 状态 | 说明 |",
                        "|--------|------|------|",
                    ]
                    for item in risk_checklist:
                        risk_lines.append(f"| {item.name} | {item.status} | {item.detail} |")
                    content += "\n" + "\n".join(risk_lines) + "\n"
                if chapter_id == 7 and signal_judgment:
                    sj = signal_judgment
                    sig_lines = [
                        "\n### 信号判断\n",
                        f"**{sj.signal}**（归一化得分：{sj.normalized_score:.1f}/100）\n",
                        "### 评分详情\n",
                        "| 指标 | 得分 | 满分 | 说明 |",
                        "|------|------|------|------|",
                    ]
                    for ind in sj.indicators:
                        sig_lines.append(f"| {ind.name} | {ind.score} | {ind.max_score} | {ind.detail} |")
                    best = max(sj.indicators, key=lambda x: x.score)
                    worst = min(sj.indicators, key=lambda x: x.score)
                    sorted_by_score = sorted(sj.indicators, key=lambda x: x.score, reverse=True)
                    second_best = sorted_by_score[1] if len(sorted_by_score) > 1 else best
                    sig_lines.append(f"\n### 核心依据\n- **{best.name}**：{best.detail}")
                    sig_lines.append(f"\n### 为什么不是更积极的判断\n- **{worst.name}**：{worst.detail}")
                    sig_lines.append(f"\n### 为什么不是更保守的判断\n- **{second_best.name}**：{second_best.detail}")
                    content += "\n" + "\n".join(sig_lines) + "\n"

            chapters.append(ReportChapter(
                chapter_id=chapter_id,
                title=title,
                content=content,
                data_sources=data_sources,
            ))

        return chapters, warnings

    def _generate_template_chapter(
        self,
        chapter_id: int,
        fund_code: str,
        fund_name: str,
        report_year: int,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        allocation: dict[int, tuple[AssetAllocationItem, ...]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        fund_manager: FundManagerInfo | None = None,
        scale_info: ScaleInfo | None = None,
        evidence: ChapterEvidence | None = None,
        signal_judgment: SignalJudgment | None = None,
        risk_checklist: tuple[RiskChecklistItem, ...] | None = None,
        stress_test: StressTestResult | None = None,
        contract_effective_date: str = "",
    ) -> str:
        """回退用的模板章节生成（模板对齐版）。

        参数:
            chapter_id: 章节编号。
            fund_code: 基金代码。
            fund_name: 基金名称。
            report_year: 报告年份。
            performance/holdings/allocation/fees: 多年度数据。
            fund_manager: 基金经理信息。
            scale_info: 规模信息。
            evidence: 证据来源汇总（可选）。
            signal_judgment: 确定性信号判断结果（Ch7 使用）。
            risk_checklist: 风险清单检查结果（Ch6 使用）。
            stress_test: 压力测试结果（Ch6 使用）。
            contract_effective_date: 基金合同生效日（"YYYY-MM-DD"；未提取到时为空字符串）。

        返回:
            模板生成的 Markdown 文本。
        """

        # Ch1-Ch6: 统一调用 generate_data_table() 获取结构化数据表
        if 1 <= chapter_id <= 6:
            from fund_agent.service.chapter_generator import generate_data_table
            fund_type = ""
            if fund_name:
                fund_type, _ = infer_fund_type(fund_name)
            st = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name) if chapter_id == 6 else None
            data_table = generate_data_table(
                chapter_id, fund_code, fund_name, report_year,
                performance, holdings, allocation, fees,
                fund_manager, scale_info, evidence,
                stress_test=st, signal_judgment=signal_judgment,
                fund_type=fund_type,
                contract_effective_date=contract_effective_date,
            )
            if data_table:
                return data_table

        if chapter_id == 0:
            latest = performance.get(report_year, {})
            base_content = (
                f"## 一眼看懂\n\n"
                f"- **基金名称**：{fund_name}\n"
                f"- **基金代码**：{fund_code}\n"
                f"- **报告年份**：{report_year}\n"
                f"- **最新净值增长率**：{latest.get('nav_growth_rate', '缺失')}\n\n"
                f"## 投资要点\n\n"
                f"基于 {report_year} 年报数据分析，该基金业绩表现和持仓情况详见后续章节。\n"
            )
        elif chapter_id == 1:
            lines = [
                f"## 基金概况\n",
                f"- 基金代码：{fund_code}",
                f"- 基金名称：{fund_name}",
                f"- 报告年份：{report_year}",
            ]
            if fund_manager:
                lines.append(f"- 基金经理：{fund_manager.name}（从业{fund_manager.years_of_service}）")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 2:
            base_content = self._generate_ch2_performance(performance)
        elif chapter_id == 3:
            lines = ["## 基金经理信息"]
            if fund_manager:
                lines.extend([
                    f"- 姓名：{fund_manager.name}",
                    f"- 任职日期：{fund_manager.tenure_start}",
                    f"- 从业年限：{fund_manager.years_of_service}",
                    f"- 持有本基金：{fund_manager.holds_fund or '未披露'}",
                ])
            else:
                lines.append("基金经理信息暂不可用。")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 4:
            base_content = "## 投资者获得感\n\n投资者实际收益数据暂不可用，详见原始年报。\n"
        elif chapter_id == 5:
            lines = ["## 当前阶段与关键变化"]
            if scale_info:
                lines.extend([
                    f"- A类份额总数：{scale_info.total_shares_a}",
                    f"- C类份额总数：{scale_info.total_shares_c}",
                    f"- 管理人持有比例：{scale_info.management_holds}",
                ])
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 6:
            lines = []
            # 压力测试（如果有）
            if stress_test:
                fund_type_labels = {"index_fund": "指数基金", "bond_fund": "债券基金", "active_fund": "主动基金"}
                level_labels = {
                    "outperform": "跑赢基准", "inline": "基本持平",
                    "underperform": "跑输基准", "severe_underperform": "严重跑输",
                }
                lines.extend([
                    "## 压力测试\n",
                    f"- 基金类型: {fund_type_labels.get(stress_test.fund_type, stress_test.fund_type)}",
                ])
                if stress_test.current_scale_billion is not None:
                    lines.append(f"- 当前规模: {stress_test.current_scale_billion:.2f}亿元")
                    lines.extend(["", "| 场景 | 阈值 | 损失金额(亿元) |", "|------|------|--------------|"])
                    for name in ("normal", "extreme", "worst"):
                        sc = stress_test.stress_scenarios[name]
                        lines.append(f"| {name} | {sc['threshold']:.0%} | {sc['loss_billion']:.4f} |")
                if stress_test.excess_return is not None:
                    lines.append(f"\n- 超额收益: {stress_test.excess_return:.2%}")
                if stress_test.stress_level is not None:
                    lines.append(f"- 压力等级: {level_labels.get(stress_test.stress_level, stress_test.stress_level)}")
                lines.append("")
            # 风险清单
            lines.extend(["## 风险清单\n", "| 风险项 | 状态 | 说明 |", "|--------|------|------|"])
            if risk_checklist:
                for item in risk_checklist:
                    lines.append(f"| {item.name} | {item.status} | {item.detail} |")
            else:
                lines.append("| （无数据） | 🟡 | 需要补充数据 |")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 7:
            if signal_judgment:
                sj = signal_judgment
                lines = [
                    f"## 综合评估与跟踪建议\n",
                    f"### 信号判断\n",
                    f"**{sj.signal}**（归一化得分：{sj.normalized_score:.1f}/100，数据完整度：{int(sj.data_completeness * 6)}/6）\n",
                    "### 评分详情\n",
                    "| 指标 | 得分 | 满分 | 说明 |",
                    "|------|------|------|------|",
                ]
                for ind in sj.indicators:
                    lines.append(f"| {ind.name} | {ind.score} | {ind.max_score} | {ind.detail} |")

                # 支撑判断的核心依据（最高分指标）
                lines.append("\n### 核心依据\n")
                best = max(sj.indicators, key=lambda x: x.score)
                lines.append(f"- **{best.name}**（{best.score}/{best.max_score}）：{best.detail}")

                # 为什么不选更积极的判断（最低分指标）
                lines.append("\n### 为什么不是更积极的判断\n")
                worst = min(sj.indicators, key=lambda x: x.score)
                lines.append(f"- **{worst.name}**（{worst.score}/{worst.max_score}）：{worst.detail}")

                # 为什么不选更保守的判断（次高分指标）
                lines.append("\n### 为什么不是更保守的判断\n")
                sorted_by_score = sorted(sj.indicators, key=lambda x: x.score, reverse=True)
                second_best = sorted_by_score[1] if len(sorted_by_score) > 1 else best
                lines.append(f"- **{second_best.name}**（{second_best.score}/{second_best.max_score}）：{second_best.detail}")

                # 当前最容易看错的地方（数据最薄弱指标）
                lines.append("\n### 当前最容易看错的地方\n")
                weakest = min(sj.indicators, key=lambda x: x.max_score - x.score if x.score > 0 else 0)
                zero_indicators = [ind for ind in sj.indicators if ind.score == 0]
                if zero_indicators:
                    lines.append(f"- **{zero_indicators[0].name}**：{zero_indicators[0].detail}（无数据，判断基础薄弱）")
                else:
                    lines.append(f"- **{weakest.name}**（{weakest.score}/{weakest.max_score}）：{weakest.detail}")

                # 最小验证计划
                lines.append("\n### 最小验证计划\n")
                lines.append("1. 核实最新年报持仓数据完整性")
                lines.append("2. 确认基金经理未发生变更")

                # 阈值事件
                lines.append("\n### 阈值事件\n")
                lines.append(f"- **升级条件**：连续 2 年超额收益为正且规模 > 2 亿")
                lines.append(f"- **降级条件**：超额收益转负或规模跌破 5000 万")

                if sj.warnings:
                    lines.append("\n### 数据警告\n")
                    for w in sj.warnings:
                        lines.append(f"- ⚠️ {w}")
            else:
                latest = performance.get(report_year, {})
                base_content = (
                    f"## 综合评估\n\n"
                    f"基于 {report_year} 年报数据，该基金最新净值增长率为 {latest.get('nav_growth_rate', 'N/A')}，"
                    f"超额收益为 {latest.get('excess_return', 'N/A')}。详见前6章分析。\n"
                )
                return base_content
            base_content = "\n".join(lines) + "\n"
        else:
            base_content = ""

        # 追加证据来源小节
        evidence_section = generate_evidence_section(chapter_id, evidence)
        if evidence_section:
            return base_content + "\n" + evidence_section
        return base_content

    def _export_markdown(
        self,
        report: FundReport,
        work_dir: Path,
        signal_judgment: SignalJudgment | None = None,
    ) -> str:
        """导出 Markdown 文件 + metadata sidecar。

        参数:
            report: 基金分析报告。
            work_dir: 工作目录。
            signal_judgment: 信号判断结果（可选，用于 sidecar）。

        返回:
            Markdown 文件路径。
        """
        work_dir = Path(work_dir) if not isinstance(work_dir, Path) else work_dir

        output_dir = work_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"{report.fund_code}-{report.report_year}-analysis"
        output_path = output_dir / f"{base_name}.md"
        sidecar_path = output_dir / f"{base_name}.meta.json"

        lines = [f"# {report.fund_name}（{report.fund_code}）{report.report_year} 年度分析报告\n"]
        lines.append(
            f"**风险警示与免责声明**：本文由 AI/大模型基于 {report.fund_name}（{report.fund_code}）"
            "已公开披露且可核查的基金年报、半年度报告、季度报告、招募说明书及其他监管披露文件辅助生成，"
            "仅用于个人投资研究与信息交流之目的。因 AI/大模型存在幻觉，本文不可避免地会产生不完全符合年报原文的情况，"
            "严重程度视 AI/大模型的幻觉程度而定，阅读本文后产生的任何观点需核对原文，"
            "使用本文内容所产生的任何直接或间接后果，均由使用者自行承担。\n\n"
            "**风险提示**：本文所提到的观点仅代表个人的意见，所涉及标的不作推荐，据此买卖，风险自负。\n"
        )

        for chapter in report.chapters:
            lines.append(f"\n---\n\n## 第 {chapter.chapter_id + 1} 章：{chapter.title}\n")
            lines.append(chapter.content)

        output_path.write_text("\n".join(lines), encoding="utf-8")

        # 写入 metadata sidecar
        sidecar: dict[str, object] = {
            "fund_code": report.fund_code,
            "fund_name": report.fund_name,
            "report_year": report.report_year,
            "generation_time": datetime.now(timezone.utc).isoformat(),
            "audit_score": None,
            "signal": signal_judgment.signal if signal_judgment else None,
            "normalized_score": signal_judgment.normalized_score if signal_judgment else None,
        }
        sidecar_path.write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return str(output_path)

    def _export_pdf(self, md_path: str, work_dir: Path) -> tuple[str, str | None]:
        """按 xelatex → Chrome headless → Markdown 回退顺序导出 PDF。

        参数:
            md_path: 源 Markdown 文件路径。
            work_dir: 工作目录（保留参数，签名不变）。

        返回:
            (输出路径, 警告信息或 None)；PDF 导出成功时警告为 None，
            引擎均不可用或转换失败时回退 Markdown 并返回对应 warning。
        """

        pdf_path = md_path.replace(".md", ".pdf")
        pandoc_available = shutil.which(_PDF_ENGINE_PANDOC) is not None
        if pandoc_available and shutil.which(_PDF_ENGINE_XELATEX) is not None:
            try:
                subprocess.run(
                    [_PDF_ENGINE_PANDOC, md_path, "-o", pdf_path, "--pdf-engine=xelatex"],
                    check=True,
                    capture_output=True,
                    timeout=_PDF_XELATEX_TIMEOUT_SECONDS,
                )
                return pdf_path, None
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                # xelatex 失败时继续尝试 Chrome headless
                pass
        chrome_path = self._find_chrome() if pandoc_available else None
        if chrome_path is not None:
            try:
                self._export_pdf_via_chrome(md_path, pdf_path, chrome_path)
                return pdf_path, None
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                # Chrome 失败时回退 Markdown + warning
                pass
        if not pandoc_available:
            return md_path, _PDF_WARNING_PANDOC_MISSING
        return md_path, _PDF_WARNING_EXPORT_FAILED

    def _find_chrome(self) -> str | None:
        """按 PUPPETEER_EXECUTABLE_PATH → PATH google-chrome → macOS 默认路径探测 Chrome。

        返回:
            可用的 Chrome 可执行文件路径；均不可用时返回 None。
        """

        env_chrome = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
        if env_chrome and Path(env_chrome).is_file():
            return env_chrome
        path_chrome = shutil.which(_PDF_GOOGLE_CHROME_BIN)
        if path_chrome:
            return path_chrome
        if Path(_PDF_CHROME_MACOS_DEFAULT).is_file():
            return _PDF_CHROME_MACOS_DEFAULT
        return None

    def _export_pdf_via_chrome(self, md_path: str, pdf_path: str, chrome_path: str) -> None:
        """pandoc md→HTML（内嵌打印 CSS）后由 Headless Chrome 转 PDF。

        参数:
            md_path: 源 Markdown 文件路径。
            pdf_path: 输出 PDF 文件路径。
            chrome_path: Chrome 可执行文件路径。

        异常:
            subprocess.CalledProcessError / subprocess.TimeoutExpired: pandoc 或 Chrome 转换失败。
        """

        css_path = Path(__file__).parent / "assets" / "report_print.css"
        with tempfile.TemporaryDirectory(prefix="fund-checklist-export-") as tmp_dir:
            tmp = Path(tmp_dir)
            header_path = tmp / "print-header.html"
            header_path.write_text(
                "<style>\n" + css_path.read_text(encoding="utf-8") + "\n</style>",
                encoding="utf-8",
            )
            html_path = tmp / f"{Path(md_path).stem}.html"
            subprocess.run(
                [
                    _PDF_ENGINE_PANDOC,
                    md_path,
                    "-f", "gfm",
                    "-t", "html5",
                    "-s",
                    "--embed-resources",
                    "--include-in-header", str(header_path),
                    "-o", str(html_path),
                ],
                check=True,
                capture_output=True,
                timeout=_PDF_CHROME_TIMEOUT_SECONDS,
            )
            subprocess.run(
                [
                    chrome_path,
                    "--headless",
                    "--disable-gpu",
                    f"--print-to-pdf={os.path.abspath(pdf_path)}",
                    "--no-pdf-header-footer",
                    f"--window-size={_PDF_A4_WINDOW_SIZE}",
                    html_path.as_uri(),
                ],
                check=True,
                capture_output=True,
                timeout=_PDF_CHROME_TIMEOUT_SECONDS,
            )

    def resolve_by_fund_code(
        self,
        fund_code: str,
        work_dir: Path,
        report_type: str = "annual_report",
    ) -> FundCodeResolution | None:
        """按基金代码 + 报告类型查找 catalog 中所有可用文档。

        参数:
            fund_code: 基金代码。
            work_dir: 工作目录（含 completed_reports.json）。
            report_type: 报告类型过滤（默认 annual_report，与 multi-year/generate
                的防污染口径一致，见 §6.25 裁决 17）。

        返回:
            FundCodeResolution；无匹配时返回 None。
        """
        catalog_path = work_dir / CATALOG_FILENAME
        if not catalog_path.exists():
            return None

        repository = _repository(work_dir)
        catalog_reports = repository.list_reports()

        seen_years: dict[int, str] = {}
        fund_name = ""
        for report in catalog_reports:
            if (
                report.get("fund_code") == fund_code
                and report.get("report_type") == report_type
            ):
                year_val = report.get("year")
                if isinstance(year_val, int):
                    seen_years[year_val] = str(report.get("document_id", ""))
                if not fund_name:
                    fund_name = str(report.get("fund_name", ""))

        if not seen_years:
            return None

        years_sorted = tuple(sorted(seen_years.keys()))
        documents = tuple(
            AnnualReportDocument(year=y, document_id=seen_years[y])
            for y in years_sorted
        )
        return FundCodeResolution(
            fund_code=fund_code,
            fund_name=fund_name,
            documents=documents,
            available_years=years_sorted,
        )

    def resolve_snapshot_reports(
        self,
        fund_code: str,
        work_dir: Path,
        report_type: str,
    ) -> SnapshotResolution | None:
        """按基金代码 + 快照报告类型查找 catalog 中所有已导入快照文档。

        参数:
            fund_code: 基金代码。
            work_dir: 工作目录（含 completed_reports.json）。
            report_type: 快照报告类型（quarterly_report / semiannual_report）。

        返回:
            SnapshotResolution；无匹配时返回 None。季度多期同一年全部保留
            （不做 year last-wins 去重）。

        异常:
            catalog 不可读或 schema 不兼容时由 repository 抛出稳定失败分类。
        """
        catalog_path = work_dir / CATALOG_FILENAME
        if not catalog_path.exists():
            return None

        repository = _repository(work_dir)
        catalog_reports = repository.list_reports()

        by_year: dict[int, list[SnapshotReportDocument]] = {}
        fund_name = ""
        for report in catalog_reports:
            if (
                report.get("fund_code") != fund_code
                or report.get("report_type") != report_type
            ):
                continue
            year_val = report.get("year")
            if not isinstance(year_val, int):
                continue
            document_id = str(report.get("document_id", ""))
            if not document_id:
                continue
            quarter_val = report.get("quarter")
            quarter = quarter_val if isinstance(quarter_val, int) else None
            period_val = report.get("period")
            period = str(period_val) if isinstance(period_val, str) and period_val else None
            by_year.setdefault(year_val, []).append(
                SnapshotReportDocument(
                    year=year_val,
                    quarter=quarter,
                    period=period,
                    document_id=document_id,
                )
            )
            if not fund_name:
                fund_name = str(report.get("fund_name", ""))

        if not by_year:
            return None

        years_sorted = tuple(sorted(by_year.keys()))
        documents = tuple(
            doc
            for year in years_sorted
            for doc in sorted(
                by_year[year],
                key=lambda d: (d.quarter if d.quarter is not None else 0, d.period or ""),
            )
        )
        return SnapshotResolution(
            fund_code=fund_code,
            fund_name=fund_name,
            documents=documents,
            available_years=years_sorted,
        )

    def list_reports(self, request: ListReportsRequest) -> ListReportsResult:
        """列出本地 completed reports 的安全摘要。

        参数:
            request: 本地 catalog 列表请求。

        返回:
            ListReportsResult；无 catalog 时返回空列表。

        异常:
            DocumentToolError: catalog schema drift、不可读或 record 指向资源不可用时
                透传稳定失败分类。
        """

        document_ids = _catalog_document_ids(_catalog_path(request.work_dir))
        if not document_ids:
            return ListReportsResult(reports=())

        repository = _repository(request.work_dir)
        stores = {document_id: repository.load_store(document_id) for document_id in document_ids}
        tool_service = FundDocumentToolService(stores)
        reports = tool_service.list_reports(
            fund_code=request.fund_code,
            year=request.year,
            report_type=request.report_type,
        )
        if isinstance(reports, ToolFailure):
            return ListReportsResult(reports=(), failure=reports)
        return ListReportsResult(reports=reports)

    def _prepare_completed_report(self, request: ImportLocalReportRequest) -> _PreparedReport:
        """导入 PDF，并按 repository 口径恢复或创建 completed report。"""

        work_dir = Path(request.work_dir)
        provider = LocalPdfSourceProvider(_blob_root(work_dir))
        import_result = provider.import_pdf(
            PdfImportRequest(
                path=Path(request.pdf_path),
                fund_code=request.fund_code,
                fund_name=request.fund_name,
                year=request.year,
                report_type=request.report_type,
                quarter=request.quarter,
                share_class=request.share_class,
            )
        )

        repository = _repository(work_dir)
        document_id = import_result.identity.document_id
        try:
            store = repository.load_store(document_id)
        except DocumentToolError as exc:
            if exc.code is not FailureCode.NOT_FOUND:
                raise
            store = self._create_completed_store(
                request=request,
                provider=provider,
                import_result=import_result,
                repository=repository,
            )
        return _PreparedReport(import_result=import_result, store=store)

    def _create_completed_store(
        self,
        *,
        request: ImportLocalReportRequest,
        provider: LocalPdfSourceProvider,
        import_result: PdfImportResult,
        repository: FilesystemReportRepository,
    ) -> DoclingDocumentStore:
        """在 catalog missing 时复用现有 JSON 或执行一次 Docling conversion。"""

        document_id = import_result.identity.document_id
        docling_root = _docling_json_root(Path(request.work_dir))
        json_path = _docling_json_path(docling_root, document_id)
        if not json_path.exists():
            converter = self._converter_factory(docling_root)
            converter.convert_pdf(
                identity=import_result.identity,
                pdf_bytes=provider.blob_store.read_pdf(import_result.stored_blob_ref),
            )
        store = DoclingDocumentStore(identity=import_result.identity, json_path=json_path)
        repository.record_completed_report(
            identity=import_result.identity,
            stored_blob_ref=import_result.stored_blob_ref,
            docling_json_ref=make_docling_json_ref(document_id),
            parser_health=store.parser_health,
        )
        return store

    def _run_with_query_candidates(
        self,
        *,
        host: MinimalHost,
        document_id: str,
        query: str,
    ) -> _QueryRouteRun:
        """按 Service 受控 query profile 顺序调用既有 Host/Agent 路径。"""

        last_not_found: AgentRunResult | None = None
        attempts: list[QueryRouteAttempt] = []
        matched_results: list[AgentRunResult] = []
        matched_titles: set[str] = set()
        route_plan = _route_plan_for_query(query)
        for candidate_query in route_plan.candidate_queries:
            result = host.run(document_id=document_id, query=candidate_query)
            if result.failure is None:
                disclosure_titles = _matched_disclosure_titles(result, route_plan.locator_contract)
                if route_plan.locator_contract is not None and not disclosure_titles:
                    attempts.append(
                        QueryRouteAttempt(
                            query=candidate_query,
                            profile_name=route_plan.profile_name,
                            result_kind=_ROUTE_RESULT_FAILURE,
                            failure_code=FailureCode.NOT_FOUND,
                        )
                    )
                    last_not_found = _target_not_found_result(result)
                    continue
                if _requires_all_target_titles(route_plan.locator_contract):
                    attempts.append(
                        QueryRouteAttempt(
                            query=candidate_query,
                            profile_name=route_plan.profile_name,
                            result_kind=_ROUTE_RESULT_SUCCESS,
                            failure_code=None,
                        )
                    )
                    if (
                        route_plan.locator_contract.aggregate_all_matches
                        or any(title not in matched_titles for title in disclosure_titles)
                    ):
                        matched_results.append(result)
                        matched_titles.update(disclosure_titles)
                    continue
                attempts.append(
                    QueryRouteAttempt(
                        query=candidate_query,
                        profile_name=route_plan.profile_name,
                        result_kind=_ROUTE_RESULT_SUCCESS,
                        failure_code=None,
                    )
                )
                return _QueryRouteRun(agent_result=result, routing_trace=tuple(attempts))

            attempts.append(
                QueryRouteAttempt(
                    query=candidate_query,
                    profile_name=route_plan.profile_name,
                    result_kind=_ROUTE_RESULT_FAILURE,
                    failure_code=result.failure.code,
                )
            )
            if result.failure.code is not FailureCode.NOT_FOUND:
                return _QueryRouteRun(agent_result=result, routing_trace=tuple(attempts))
            last_not_found = result

        if _requires_all_target_titles(route_plan.locator_contract):
            required_titles = (
                set(route_plan.locator_contract.acceptable_title_family) if route_plan.locator_contract else set()
            )
            if required_titles and required_titles.issubset(matched_titles):
                return _QueryRouteRun(
                    agent_result=_aggregate_agent_results_for_contract(
                        route_plan.locator_contract,
                        tuple(matched_results),
                    ),
                    routing_trace=tuple(attempts),
                )
            if matched_results:
                return _QueryRouteRun(
                    agent_result=_target_not_found_result(
                        _aggregate_agent_results_for_contract(
                            route_plan.locator_contract,
                            tuple(matched_results),
                        )
                    ),
                    routing_trace=tuple(attempts),
                )

        if last_not_found is None:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 未生成候选 query")
        return _QueryRouteRun(agent_result=last_not_found, routing_trace=tuple(attempts))


def _default_host_factory(tool_service: FundDocumentToolService) -> MinimalHost:
    """按默认 deterministic Agent 装配最小 Host。"""

    return MinimalHost(MinimalFundDocumentAgent(tool_service))


def _default_runner_factory(tool_service: FundDocumentToolService) -> LlmToolLoopRunner:
    """按默认 DeepSeek LLM client 装配 LlmToolLoopRunner。"""

    return LlmToolLoopRunner(tool_service=tool_service, llm_client=DeepSeekLlmClient())


def _normalized_multi_year_requested_years(requested_years: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    """校验并返回 10I 升序 requested_years。"""

    try:
        years = tuple(int(year) for year in requested_years)
    except (TypeError, ValueError) as exc:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "multi-year requested_years 不符合契约") from exc
    if not (
        _MULTI_YEAR_MINIMUM_COMPLETE_YEARS
        <= len(years)
        <= _MULTI_YEAR_MAXIMUM_COMPLETE_YEARS
    ):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "multi-year requested_years 长度不符合契约")
    if len(set(years)) != len(years):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "multi-year requested_years 年份重复")
    return tuple(sorted(years))


def _normalized_holdings_requested_years(requested_years: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    """校验并返回持仓查询的升序 requested_years，允许 1-5 年。"""

    try:
        years = tuple(int(year) for year in requested_years)
    except (TypeError, ValueError) as exc:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "holdings requested_years 不符合契约") from exc
    if not (1 <= len(years) <= _MULTI_YEAR_MAXIMUM_COMPLETE_YEARS):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "holdings requested_years 长度不符合契约")
    if len(set(years)) != len(years):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "holdings requested_years 年份重复")
    return tuple(sorted(years))


def _multi_year_documents_by_year(
    annual_report_documents: tuple[AnnualReportDocument, ...] | list[AnnualReportDocument],
) -> dict[int, AnnualReportDocument]:
    """校验显式 year/document_id 映射并按 year 建索引。"""

    documents: dict[int, AnnualReportDocument] = {}
    for document in annual_report_documents:
        try:
            year = int(document.year)
        except (TypeError, ValueError) as exc:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual_report_documents year 不符合契约") from exc
        if not document.document_id:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual_report_documents document_id 为空")
        if year in documents:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual_report_documents 年份重复")
        documents[year] = AnnualReportDocument(year=year, document_id=document.document_id)
    return documents


def _normalize_multi_year_requested_share_class(share_class: str | None) -> str | None:
    """校验 10I 显式 share_class 输入。"""

    if share_class is None:
        return None
    normalized = _normalize_share_class_scope(share_class)
    if normalized is None:
        raise DocumentToolError(FailureCode.NOT_FOUND, "multi-year annual performance 份额类别无法唯一识别")
    return normalized


def _validate_multi_year_report_identity(
    *,
    document_id: str,
    store: DoclingDocumentStore,
    fund_code: str,
    year: int,
) -> None:
    """校验显式 document_id 指向的 report identity 与请求绑定一致。"""

    summary = _single_report_summary(document_id, store)
    if (
        summary.document_id != document_id
        or summary.fund_code != fund_code
        or summary.year != year
        or summary.report_type != ReportType.ANNUAL_REPORT.value
    ):
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "multi-year annual report identity 不匹配")


def _multi_year_complete_rows_for_year(
    *,
    year: int,
    annual_result: ExtractAnnualPerformanceResult,
    excess_result: ExtractAnnualExcessReturnResult,
) -> dict[str, MultiYearAnnualPerformanceRow]:
    """把 10F/10G 单年度结果收敛为该年度完整 share class rows。"""

    _raise_for_multi_year_single_year_failure(annual_result.failure)
    _raise_for_multi_year_single_year_failure(excess_result.failure)
    annual_fields = _annual_performance_fields_by_share(year=year, fields=annual_result.fields)
    excess_fields = _annual_excess_fields_by_share(year=year, fields=excess_result.fields)
    rows: dict[str, MultiYearAnnualPerformanceRow] = {}
    for share_scope in sorted(set(annual_fields) | set(excess_fields)):
        nav_field = annual_fields.get(share_scope, {}).get(_FIELD_ANNUAL_NAV_GROWTH_RATE)
        benchmark_field = annual_fields.get(share_scope, {}).get(_FIELD_ANNUAL_BENCHMARK_RETURN_RATE)
        excess_field = excess_fields.get(share_scope)
        if nav_field is None or benchmark_field is None or excess_field is None:
            continue
        citations = (
            AnnualPerformanceFieldCitation(
                field_name=_FIELD_ANNUAL_NAV_GROWTH_RATE,
                citation=nav_field.citation,
            ),
            AnnualPerformanceFieldCitation(
                field_name=_FIELD_ANNUAL_BENCHMARK_RETURN_RATE,
                citation=benchmark_field.citation,
            ),
            AnnualPerformanceFieldCitation(
                field_name=_FIELD_ANNUAL_EXCESS_RETURN,
                citation=excess_field.citation,
            ),
        )
        if not all(
            field_citation.citation.locator.locator_kind is LocatorKind.TABLE
            for field_citation in citations
        ):
            continue
        rows[share_scope] = MultiYearAnnualPerformanceRow(
            year=year,
            annual_nav_growth_rate=nav_field.decimal_percent_text,
            annual_benchmark_return_rate=benchmark_field.decimal_percent_text,
            annual_excess_return=excess_field.decimal_percent_text,
            citations=citations,
        )
    return rows


def _raise_for_multi_year_single_year_failure(failure: ToolFailure | None) -> None:
    """按 10I 语义处理单年度 extraction failure。"""

    if failure is None:
        return
    if failure.code is FailureCode.NOT_FOUND:
        raise DocumentToolError(FailureCode.NOT_FOUND, failure.message)
    raise DocumentToolError(failure.code, failure.message)


def _annual_performance_fields_by_share(
    *,
    year: int,
    fields: tuple[AnnualPerformanceExtraction, ...],
) -> dict[str, dict[str, AnnualPerformanceExtraction]]:
    """按 share class 和 field_name 组织 10F 字段，并校验 report_year。"""

    grouped: dict[str, dict[str, AnnualPerformanceExtraction]] = {}
    for field in fields:
        if field.report_year != year:
            raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "annual performance report_year 不匹配")
        if field.field_name not in {
            _FIELD_ANNUAL_NAV_GROWTH_RATE,
            _FIELD_ANNUAL_BENCHMARK_RETURN_RATE,
        }:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual performance 字段名不符合契约")
        share_fields = grouped.setdefault(field.share_class_scope, {})
        if field.field_name in share_fields:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual performance 字段重复")
        share_fields[field.field_name] = field
    return grouped


def _annual_excess_fields_by_share(
    *,
    year: int,
    fields: tuple[AnnualExcessReturnExtraction, ...],
) -> dict[str, AnnualExcessReturnExtraction]:
    """按 share class 组织 10G 字段，并校验 report_year。"""

    grouped: dict[str, AnnualExcessReturnExtraction] = {}
    for field in fields:
        if field.report_year != year:
            raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "annual excess return report_year 不匹配")
        if field.field_name != _FIELD_ANNUAL_EXCESS_RETURN:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual excess return 字段名不符合契约")
        if field.share_class_scope in grouped:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual excess return 字段重复")
        grouped[field.share_class_scope] = field
    return grouped


def _multi_year_complete_count(rows_by_year: dict[int, MultiYearAnnualPerformanceRow]) -> int:
    """返回完整年度数量。"""

    return len(rows_by_year)


def _multi_year_series_for_share(
    *,
    fund_code: str,
    requested_years: tuple[int, ...],
    share_class_scope: str,
    rows_by_year: dict[int, MultiYearAnnualPerformanceRow],
    missing_notes: dict[int, str],
) -> MultiYearAnnualPerformanceSeries:
    """构造单一 share class 的 10I series DTO。"""

    rows = tuple(rows_by_year[year] for year in requested_years if year in rows_by_year)
    covered_years = tuple(row.year for row in rows)
    missing_years = tuple(year for year in requested_years if year not in rows_by_year)
    missing_year_notes = tuple(
        MultiYearMissingYearNote(
            year=year,
            reason=missing_notes.get(year, "该年度未返回完整年度业绩字段"),
        )
        for year in missing_years
    )
    coverage_count = len(covered_years)
    coverage_status = (
        _COVERAGE_STATUS_COMPLETE
        if coverage_count == _MULTI_YEAR_MAXIMUM_COMPLETE_YEARS
        else _COVERAGE_STATUS_PARTIAL
    )
    citations = tuple(field_citation for row in rows for field_citation in row.citations)
    return MultiYearAnnualPerformanceSeries(
        fund_code=fund_code,
        requested_years=requested_years,
        covered_years=covered_years,
        missing_years=missing_years,
        coverage_status=coverage_status,
        coverage_count=coverage_count,
        minimum_required_count=_MULTI_YEAR_MINIMUM_COMPLETE_YEARS,
        share_class_scope=share_class_scope,
        rows=rows,
        citations=citations,
        missing_year_notes=missing_year_notes,
    )


def _repository(work_dir: Path) -> FilesystemReportRepository:
    """按 Service 受控工作目录构造 repository。"""

    root = Path(work_dir)
    return FilesystemReportRepository(
        catalog_path=_catalog_path(root),
        blob_root=_blob_root(root),
        docling_json_root=_docling_json_root(root),
    )


def _catalog_path(work_dir: Path) -> Path:
    """返回 completed report catalog 路径。"""

    return Path(work_dir) / CATALOG_FILENAME


def _blob_root(work_dir: Path) -> Path:
    """返回受控 PDF blob 根目录。"""

    return Path(work_dir) / PDF_BLOB_DIRNAME


def _docling_json_root(work_dir: Path) -> Path:
    """返回受控 Docling JSON 根目录。"""

    return Path(work_dir) / DOCLING_JSON_DIRNAME


def _docling_json_path(docling_root: Path, document_id: str) -> Path:
    """返回 Service 内部受控 Docling JSON 路径。"""

    return Path(docling_root) / document_id / f"{document_id}{DOCLING_JSON_SUFFIX}"


def _single_report_summary(document_id: str, store: DoclingDocumentStore) -> ReportSummary:
    """通过 FundDocumentToolService 生成单份安全 report summary。"""

    reports = FundDocumentToolService({document_id: store}).list_reports()
    if isinstance(reports, ToolFailure) or not reports:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "report summary 暂不可用")
    return reports[0]


def _candidate_queries_for_query(query: str) -> tuple[str, ...]:
    """按 hardcoded profile 为用户 query 生成受控候选 query。"""

    return _route_plan_for_query(query).candidate_queries


def _route_plan_for_query(query: str) -> _QueryRoutePlan:
    """返回 query 对应的 Service routing plan，不做开放语义理解。"""

    for contract in _validated_locator_contracts():
        if any(alias in query for alias in contract.aliases):
            return _QueryRoutePlan(
                profile_name=contract.profile_name,
                candidate_queries=_bounded_unique_candidates((query, *contract.candidate_queries)),
                locator_contract=contract,
            )
    return _QueryRoutePlan(profile_name=None, candidate_queries=(query,), locator_contract=None)


def _validated_locator_contracts() -> tuple[_DisclosureLocatorContract, ...]:
    """校验 Service 内部披露定位 registry，异常时映射为 schema_drift。"""

    seen_aliases: set[str] = set()
    seen_profiles: set[str] = set()
    for contract in DISCLOSURE_LOCATOR_CONTRACT_REGISTRY:
        if not contract.profile_name or contract.profile_name in seen_profiles:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry profile 配置异常")
        seen_profiles.add(contract.profile_name)
        if (
            not contract.aliases
            or not contract.candidate_queries
            or not contract.acceptable_title_family
            or contract.extraction_allowed
        ):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry 配置不完整")
        if 1 + len(contract.candidate_queries) > _MAX_QUERY_CANDIDATES:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry 候选过多")
        if len(set(contract.candidate_queries)) != len(contract.candidate_queries):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry candidate 配置异常")
        if any(not candidate for candidate in contract.candidate_queries):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry candidate 为空")
        if len(set(contract.acceptable_title_family)) != len(contract.acceptable_title_family):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry title 配置异常")
        if any(not title for title in contract.acceptable_title_family):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry title 为空")
        if _requires_all_target_titles(contract) and set(contract.candidate_queries) != set(
            contract.acceptable_title_family
        ):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry 多目标配置异常")
        for alias in contract.aliases:
            if not alias or alias in seen_aliases:
                raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "disclosure locator registry alias 配置异常")
            seen_aliases.add(alias)
    return tuple(DISCLOSURE_LOCATOR_CONTRACT_REGISTRY)


def _resolve_anchor_table_ref(
    document_id: str | None,
    contract: _DisclosureLocatorContract,
    tool_service: FundDocumentToolService,
) -> str | None:
    """解析受控 profile 的候选表锚点 table_ref（Service 层私有，fail-open）。

    组合 public tools：search_document 定位 section → list_tables(within_section_ref)
    → read_table（有界行）扫描行头/表头签名。manager_holdings 命中 9.4 行头优先、
    9.2 行头回退；holdings_top10 按表头签名（序号/股票名称/公允价值，row_count
    >= 10）匹配；performance_returns 按 3.2.1 表头签名匹配且 A 类标题优先
    （Fix C）。解析失败 / 工具不可用 / 无候选表 / document_id 为 None 时返回
    None（fail-open 到既有候选词路径，不抛异常）。

    参数:
        document_id: public reading tools 使用的内容身份；None 时直接返回 None。
        contract: 命中的受控披露定位 contract。
        tool_service: 组合 public reading tools 的 tool service。

    返回:
        解析成功的 table_ref；否则返回 None。

    异常:
        本函数不向 public caller 抛出业务异常；工具调用失败一律视为无锚点。
    """

    if document_id is None:
        return None
    if contract.profile_name == "manager_holdings":
        return _resolve_manager_holdings_anchor_table_ref(document_id, tool_service)
    if contract.profile_name == "holdings_top10":
        return _resolve_holdings_top10_anchor_table_ref(document_id, tool_service)
    if contract.profile_name == "performance_returns":
        return _resolve_performance_returns_anchor_table_ref(document_id, tool_service)
    return None


def _anchor_section_refs(
    document_id: str,
    tool_service: FundDocumentToolService,
    queries: tuple[str, ...],
) -> tuple[str, ...]:
    """按查询顺序收集 search_document 命中的去重 section_ref。

    search_document 失败 / 工具不可用时跳过该查询，不阻断后续查询。
    """

    section_refs: list[str] = []
    seen: set[str] = set()
    for query in queries:
        try:
            hits = tool_service.search_document(document_id, query)
        except Exception:
            continue
        if isinstance(hits, ToolFailure):
            continue
        for hit in hits:
            section_ref = getattr(hit, "section_ref", None)
            if section_ref and section_ref not in seen:
                seen.add(section_ref)
                section_refs.append(section_ref)
    return tuple(section_refs)


def _anchor_row_contains_title_family(rows: tuple[tuple[str, ...], ...], family: str) -> bool:
    """判断表格行头（任意一行归一化文本）是否包含标题族短语。"""

    normalized_family = _normalize_cell_text(family)
    if not normalized_family:
        return False
    for row in rows:
        row_text = _normalize_cell_text("".join(str(cell) for cell in row))
        if normalized_family in row_text:
            return True
    return False


def _resolve_manager_holdings_anchor_table_ref(
    document_id: str,
    tool_service: FundDocumentToolService,
) -> str | None:
    """manager_holdings 锚点：9.4 行头优先、9.2 行头回退。

    先扫描全部候选 section 找 9.4 行头表；无 9.4 时返回首个 9.2 行头表
    （两遍语义：文档中先出现的 9.2 整体表不会抢占 9.4 区间结果）。
    """

    fallback: str | None = None
    for section_ref in _anchor_section_refs(
        document_id, tool_service, _ANCHOR_MANAGER_HOLDS_SECTION_QUERIES
    ):
        try:
            tables = tool_service.list_tables(document_id, within_section_ref=section_ref)
        except Exception:
            continue
        if isinstance(tables, ToolFailure):
            continue
        for summary in tables:
            try:
                content = tool_service.read_table(
                    document_id, summary.table_ref, max_rows=_ANCHOR_TABLE_MAX_ROWS
                )
            except Exception:
                continue
            if isinstance(content, ToolFailure) or not hasattr(content, "rows"):
                continue
            if _anchor_row_contains_title_family(
                content.rows, _ANCHOR_MANAGER_HOLDS_9_4_TITLE_FAMILY
            ):
                return summary.table_ref
            if fallback is None and _anchor_row_contains_title_family(
                content.rows, _ANCHOR_MANAGER_HOLDS_9_2_TITLE_FAMILY
            ):
                fallback = summary.table_ref
    return fallback


def _resolve_holdings_top10_anchor_table_ref(
    document_id: str,
    tool_service: FundDocumentToolService,
) -> str | None:
    """holdings_top10 锚点：表头签名匹配（序号/股票名称/公允价值，row_count >= 10）。"""

    for section_ref in _anchor_section_refs(
        document_id, tool_service, _ANCHOR_HOLDINGS_TOP10_SECTION_QUERIES
    ):
        try:
            tables = tool_service.list_tables(document_id, within_section_ref=section_ref)
        except Exception:
            continue
        if isinstance(tables, ToolFailure):
            continue
        for summary in tables:
            if summary.row_count < _ANCHOR_HOLDINGS_TOP10_MIN_ROWS:
                continue
            try:
                content = tool_service.read_table(
                    document_id, summary.table_ref, max_rows=_ANCHOR_TABLE_MAX_ROWS
                )
            except Exception:
                continue
            if isinstance(content, ToolFailure) or not hasattr(content, "rows"):
                continue
            for row in content.rows[:_ANCHOR_HOLDINGS_TOP10_MIN_ROWS]:
                header = _normalize_cell_text("".join(str(cell) for cell in row))
                if all(
                    _normalize_cell_text(keyword) in header
                    for keyword in _ANCHOR_HOLDINGS_TOP10_HEADER_SIGNATURE
                ):
                    return summary.table_ref
    return None


def _anchor_row_has_header_signature(
    rows: tuple[tuple[str, ...], ...],
    signature: tuple[str, ...],
) -> bool:
    """判断有界表格行中是否存在包含全部表头签名关键词的归一化行。

    Docling 单元格可能含空白（如「份额净值 增长率①」），比较前对整行与
    关键词均做去空白归一化；命中判定为关键词子串包含（与 holdings_top10
    锚点一致）。
    """

    if not signature:
        return False
    for row in rows:
        row_text = _normalize_cell_text("".join(str(cell) for cell in row))
        if all(_normalize_cell_text(keyword) in row_text for keyword in signature):
            return True
    return False


def _resolve_performance_returns_anchor_table_ref(
    document_id: str,
    tool_service: FundDocumentToolService,
) -> str | None:
    """performance_returns 锚点：3.2.1 表头签名匹配，A 类标题优先（Fix C）。

    定位流程：3.2.1 exact title 查询定位 section → list_tables(within_section_ref)
    → 逐表 read_table（有界行）扫描表头签名（阶段/份额净值增长率/业绩比较
    基准收益率，去空白归一化）→ 签名命中表中标题含 A 且不含 C 的 A 类表优先，
    无 A 类候选时返回首个签名命中表（两遍语义：非 A 类表不抢占 A 类结果）；
    任何失败 / 无候选返回 None（fail-open 到既有候选词路径，不抛异常）。

    参数:
        document_id: public reading tools 使用的内容身份。
        tool_service: 组合 public reading tools 的 tool service。

    返回:
        解析成功的 table_ref；否则返回 None。

    异常:
        本函数不向 public caller 抛出业务异常；工具调用失败一律视为无锚点。
    """

    first_signature_hit: str | None = None
    for section_ref in _anchor_section_refs(
        document_id, tool_service, _ANCHOR_PERFORMANCE_RETURNS_SECTION_QUERIES
    ):
        try:
            tables = tool_service.list_tables(document_id, within_section_ref=section_ref)
        except Exception:
            continue
        if isinstance(tables, ToolFailure):
            continue
        for summary in tables:
            try:
                content = tool_service.read_table(
                    document_id, summary.table_ref, max_rows=_ANCHOR_TABLE_MAX_ROWS
                )
            except Exception:
                continue
            if isinstance(content, ToolFailure) or not hasattr(content, "rows"):
                continue
            if not _anchor_row_has_header_signature(
                content.rows, _ANCHOR_PERFORMANCE_RETURNS_HEADER_SIGNATURE
            ):
                continue
            if first_signature_hit is None:
                first_signature_hit = summary.table_ref
            title = summary.caption or ""
            if _SHARE_SCOPE_A in title and _SHARE_SCOPE_C not in title:
                return summary.table_ref
    return first_signature_hit


def _requires_all_target_titles(contract: _DisclosureLocatorContract | None) -> bool:
    """判断 locator contract 是否要求可接受标题族全量命中。"""

    if contract is None:
        return False
    return (
        not contract.requires_table_citation
        and len(contract.acceptable_title_family) > 1
        and set(contract.candidate_queries) == set(contract.acceptable_title_family)
    )


def _matched_disclosure_titles(
    result: AgentRunResult,
    contract: _DisclosureLocatorContract | None,
) -> tuple[str, ...]:
    """返回 Agent 安全 answer 命中的受控披露标题族。"""

    if contract is None:
        return ("__uncontrolled__",)
    citation_kinds = tuple(citation.locator.locator_kind for citation in result.citations)
    if not citation_kinds:
        return ()
    if contract.requires_table_citation and LocatorKind.TABLE not in citation_kinds:
        return ()
    if contract.profile_name == "performance_returns" and LocatorKind.SECTION not in citation_kinds:
        return ()
    title_lines = _target_title_lines(result.answer)
    return tuple(
        title
        for title in contract.acceptable_title_family
        if any(title in line for line in title_lines)
    )


def _aggregate_agent_results(results: tuple[AgentRunResult, ...]) -> AgentRunResult:
    """聚合同一受控 profile 的多个安全 Agent 成功结果。"""

    if not results:
        return AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message=_TARGET_NOT_FOUND_MESSAGE),
        )
    return AgentRunResult(
        answer="\n\n".join(result.answer for result in results if result.answer),
        citations=tuple(citation for result in results for citation in result.citations),
        tool_trace=tuple(trace for result in results for trace in result.tool_trace),
        failure=None,
    )


def _aggregate_agent_results_for_contract(
    contract: _DisclosureLocatorContract | None,
    results: tuple[AgentRunResult, ...],
) -> AgentRunResult:
    """按 locator contract 的聚合语义合并多个 success 结果。

    `aggregate_all_matches=True` 的契约（fee_rates）走标题块去重聚合，
    其余契约保持简单拼接聚合。

    参数:
        contract: 命中的受控披露 contract；None 时按简单聚合处理。
        results: 同一受控 profile 的多个安全 Agent 成功结果。

    返回:
        聚合后的 AgentRunResult。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """

    if contract is not None and contract.aggregate_all_matches:
        return _aggregate_fee_rate_results(results)
    return _aggregate_agent_results(results)


def _strip_fee_rate_table_blocks(answer: str) -> str:
    """剥离 fee_rates answer 中「相关表格:」金额表引用块。

    金额表块从「相关表格:」行开始到下一个空行（`\\n\\n` 边界）结束；
    块内表格标题行（如「7.4.10.2.3 销售服务费」）不得参与正文标题定位。

    参数:
        answer: 单个 candidate query 的安全 Agent answer。

    返回:
        去除金额表引用块后的 answer 文本。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """

    lines = answer.splitlines()
    stripped: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == _TABLE_BLOCK_HEADER:
            index += 1
            while index < len(lines) and lines[index].strip():
                index += 1
            continue
        stripped.append(lines[index])
        index += 1
    return "\n".join(stripped)


def _fee_rate_title_block(stripped: str, title: str) -> str | None:
    """返回剥离金额表块后的 answer 中指定披露标题的首个完整块。

    块从标题首次出现开始，到同一 answer 中下一个披露标题或文本末尾结束；
    标题后无正文（块为空）时返回 None，交由后续结果补全。

    参数:
        stripped: 剥离金额表块后的单个 answer 文本。
        title: 目标披露标题。

    返回:
        标题的完整正文块；标题缺失或块为空时返回 None。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """

    start = stripped.find(title)
    if start < 0:
        return None
    next_positions = (
        stripped.find(other, start + len(title))
        for other in _FEE_RATE_TITLES
        if other != title
    )
    ends = tuple(position for position in next_positions if position >= 0)
    end = min(ends) if ends else len(stripped)
    block = stripped[start:end].strip()
    return block or None


def _aggregate_fee_rate_results(results: tuple[AgentRunResult, ...]) -> AgentRunResult:
    """按 10B fee_rates 标题块去重聚合多个 candidate success 结果。

    每个结果先剥离「相关表格:」金额表引用块，再按固定标题顺序取首个完整
    标题块（同一标题只保留第一个含正文的块，消除三个 query answer 的正文
    重复）；citations 按 (locator_kind, section_ref, table_ref) 去重合并，
    tool_trace 合并。

    参数:
        results: fee_rates 受控 profile 的多个安全 Agent 成功结果。

    返回:
        标题块去重聚合后的 AgentRunResult；无结果时返回 NOT_FOUND 结果。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """

    if not results:
        return AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message=_TARGET_NOT_FOUND_MESSAGE),
        )
    block_by_title: dict[str, str] = {}
    for result in results:
        stripped = _strip_fee_rate_table_blocks(result.answer)
        for title in _FEE_RATE_TITLES:
            if title in block_by_title:
                continue
            block = _fee_rate_title_block(stripped, title)
            if block is not None:
                block_by_title[title] = block
    answer = "\n\n".join(
        block_by_title[title] for title in _FEE_RATE_TITLES if title in block_by_title
    )
    citations = _dedupe_fee_rate_citations(
        tuple(citation for result in results for citation in result.citations)
    )
    return AgentRunResult(
        answer=answer,
        citations=citations,
        tool_trace=tuple(trace for result in results for trace in result.tool_trace),
        failure=None,
    )


def _dedupe_fee_rate_citations(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
    """按 (locator_kind, section_ref, table_ref) 去重合并 fee_rates citations。"""

    seen: set[tuple[object, str | None, str | None]] = set()
    deduped: list[Citation] = []
    for citation in citations:
        locator = citation.locator
        key = (locator.locator_kind, locator.section_ref, locator.table_ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return tuple(deduped)


def _target_title_lines(answer: str) -> tuple[str, ...]:
    """从 Agent 安全 answer 中提取 section/table title 行用于 Service 目标判定。"""

    lines = tuple(line.strip() for line in answer.splitlines() if line.strip())
    if not lines:
        return ()

    title_lines: list[str] = [lines[0]]
    for line in lines:
        if line.startswith(_SECTION_TITLE_PREFIX) or line.startswith(_TABLE_TITLE_PREFIX):
            title_lines.append(line)

    for index, line in enumerate(lines):
        if line == _TABLE_BLOCK_HEADER and index + 1 < len(lines):
            title_lines.append(lines[index + 1])
            break
    return tuple(dict.fromkeys(title_lines))


def _target_not_found_result(result: AgentRunResult) -> AgentRunResult:
    """把未满足 target contract 的 Agent success 转成 Service fail-closed 结果。"""

    return AgentRunResult(
        answer="",
        citations=(),
        tool_trace=result.tool_trace,
        failure=ToolFailure(code=FailureCode.NOT_FOUND, message=_TARGET_NOT_FOUND_MESSAGE),
    )


def _extract_fee_rate_fields(result: AgentRunResult) -> tuple[FeeRateExtraction, ...]:
    """从 10B fee_rates 安全 answer 中抽取受控费率字段。"""

    specs = _validated_fee_rate_specs()
    segments = _fee_rate_segments(result.answer)
    citations = _fee_rate_section_citations(result.citations)
    fields: list[FeeRateExtraction] = []
    for spec in specs:
        segment = segments.get(spec.title)
        citation = citations.get(spec.title)
        if segment is None or citation is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "fee_rates 候选章节不完整")
        # Docling 空格噪声（1.  50%）先归一化再做百分比匹配
        segment = _normalize_percent_text(segment)
        # 排除费率变更历史句（由 X% 调整/调低/变更为 Y%）
        _raw_matches = tuple(spec.pattern.finditer(segment))
        _change_re = re.compile(r'由\s*\d+\.\d{2}%\s*(?:调整|调低|调降|调升|变更|修改)')
        matches = tuple(m for m in _raw_matches if not _change_re.search(m.group("raw")))
        # 报告期内费率变更：新旧费率格式相同、均含日期（自...至.../自...起），当前费率总是最后出现
        if len(matches) > 1 and any(re.search(r'自\s*\d{4}', m.group("raw")) for m in matches):
            matches = (matches[-1],)
        if len(matches) != 1:
            raise DocumentToolError(FailureCode.NOT_FOUND, "fee_rates 字段无法唯一抽取")
        match = matches[0]
        raw_text = _compact_raw_text(match.group("raw"))
        decimal_percent_text = spec.controlled_value or match.group("rate")
        fields.append(
            FeeRateExtraction(
                field_name=spec.field_name,
                decimal_percent_text=decimal_percent_text,
                period=_FEE_RATE_PERIOD_YEAR,
                share_class_scope=spec.share_class_scope,
                raw_text=raw_text,
                citation=citation,
            )
        )
    return tuple(fields)


def _validated_fee_rate_specs() -> tuple[_FeeRateExtractionSpec, ...]:
    """校验 10C fee_rates 抽取配置，异常时映射为 schema_drift。"""

    specs = tuple(_FEE_RATE_EXTRACTION_SPECS)
    expected = (
        (_FIELD_MANAGEMENT_FEE_RATE, _SHARE_SCOPE_ALL),
        (_FIELD_CUSTODIAN_FEE_RATE, _SHARE_SCOPE_ALL),
        (_FIELD_SALES_SERVICE_FEE_RATE, _SHARE_SCOPE_A),
        (_FIELD_SALES_SERVICE_FEE_RATE, _SHARE_SCOPE_C),
    )
    actual = tuple((spec.field_name, spec.share_class_scope) for spec in specs)
    if actual != expected:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "fee_rates 抽取配置异常")
    for spec in specs:
        if not spec.title or not spec.pattern.groupindex.get("raw"):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "fee_rates 抽取配置不完整")
        if spec.controlled_value is None and not spec.pattern.groupindex.get("rate"):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "fee_rates 数值配置不完整")
    return specs


def _fee_rate_segments(answer: str) -> dict[str, str]:
    """按 10B 三个固定披露标题切分安全 answer。"""

    positions: list[tuple[str, int]] = []
    search_start = 0
    for title in _FEE_RATE_TITLES:
        position = answer.find(title, search_start)
        if position < 0:
            raise DocumentToolError(FailureCode.NOT_FOUND, "fee_rates 候选章节缺失")
        positions.append((title, position))
        search_start = position + len(title)

    segments: dict[str, str] = {}
    for index, (title, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(answer)
        segments[title] = answer[start:end]
    return segments


def _fee_rate_section_citations(citations: tuple[Citation, ...]) -> dict[str, Citation]:
    """按 section_ref 去重为三段费率披露匹配 section citation。

    TABLE locator 携带的 section_ref 也计入覆盖（table-0052 的
    section_ref=section-0398 已验证可定位到销售服务费节）；按出现顺序取
    每个 section_ref 的首个 citation，要求覆盖不少于三个不同 section，
    返回 dict 仍按固定标题顺序 zip。

    参数:
        citations: 聚合后的 fee_rates citations。

    返回:
        固定标题顺序映射到 section citation 的 dict。

    异常:
        DocumentToolError: 不同 section_ref 覆盖不足三个时抛 NOT_FOUND。
    """

    by_section_ref: dict[str, Citation] = {}
    for citation in citations:
        locator = citation.locator
        if locator.section_ref is None:
            continue
        if locator.locator_kind not in (LocatorKind.SECTION, LocatorKind.TABLE):
            continue
        by_section_ref.setdefault(locator.section_ref, citation)
    if len(by_section_ref) < len(_FEE_RATE_TITLES):
        raise DocumentToolError(FailureCode.NOT_FOUND, "fee_rates citation 不完整")
    return dict(zip(_FEE_RATE_TITLES, by_section_ref.values(), strict=False))


def _extract_performance_return_fields(
    *,
    document_id: str,
    result: AgentRunResult,
    tool_service: FundDocumentToolService,
    requested_share_class: str | None,
) -> tuple[PerformanceReturnExtraction, ...]:
    """从 11A 定位到的 performance disclosure table 中抽取受控收益字段。"""

    specs = _validated_performance_return_specs()
    cited_tables = _performance_table_citation_refs(result)
    section_refs = tuple(dict.fromkeys(section_ref for section_ref, _table_ref in cited_tables))
    candidates: list[TableContent] = []
    section_text_by_ref: dict[str, str] = {}
    for section_ref in section_refs:
        section = tool_service.read_section(document_id, section_ref)
        if isinstance(section, ToolFailure):
            raise DocumentToolError(section.code, section.message)
        section_text_by_ref[section_ref] = section.text

    for _section_ref, table_ref in cited_tables:
        table = tool_service.read_table(
            document_id,
            table_ref,
            max_rows=_PERFORMANCE_TABLE_MAX_ROWS,
        )
        if isinstance(table, ToolFailure):
            raise DocumentToolError(table.code, table.message)
        candidates.append(table)

    performance_tables = tuple(table for table in candidates if _performance_column_indexes(table.rows, specs))
    if not performance_tables:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 目标列缺失")

    share_scopes = _performance_table_share_scopes(
        performance_tables,
        section_text_by_ref=section_text_by_ref,
        requested_share_class=requested_share_class,
    )
    fields: list[PerformanceReturnExtraction] = []
    for table in performance_tables:
        indexes = _performance_column_indexes(table.rows, specs)
        if indexes is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 目标列缺失")
        share_scope = share_scopes.get(table.table_ref)
        if share_scope is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")
        row = _performance_past_year_row(table.rows, share_scope=share_scope)
        if row is None:
            continue
        for spec in specs:
            column_index = indexes[spec.field_name]
            value = _single_percent_text(row[column_index])
            fields.append(
                PerformanceReturnExtraction(
                    field_name=spec.field_name,
                    decimal_percent_text=value,
                    period=_PERFORMANCE_RETURN_PERIOD_PAST_1_YEAR,
                    share_class_scope=share_scope,
                    raw_text=_performance_raw_text(
                        period_text=row[0],
                        column_text=table.rows[0][column_index],
                        value_text=value,
                    ),
                    citation=table.citation,
                )
            )

    if not fields:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 过去一年行缺失")
    return tuple(fields)


def _extract_annual_performance_fields(
    *,
    document_id: str,
    result: AgentRunResult,
    tool_service: FundDocumentToolService,
    report_year: int,
    requested_share_class: str | None,
) -> tuple[AnnualPerformanceExtraction, ...]:
    """从 title-family matched table 中抽取年度收益字段。"""

    specs = _validated_annual_performance_specs()
    source_section_refs = _annual_performance_source_section_refs(result)
    table_refs = _annual_performance_table_refs(
        document_id=document_id,
        result=result,
        tool_service=tool_service,
        source_section_refs=source_section_refs,
        specs=specs,
    )

    section_text_by_ref: dict[str, str] = {}
    for section_ref in source_section_refs:
        section = tool_service.read_section(document_id, section_ref)
        if isinstance(section, ToolFailure):
            raise DocumentToolError(section.code, section.message)
        section_text_by_ref[section_ref] = section.text

    tables: list[TableContent] = []
    for table_ref in table_refs:
        table = tool_service.read_table(document_id, table_ref, max_rows=_PERFORMANCE_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            raise DocumentToolError(table.code, table.message)
        # section 分裂兼容：不在此处过滤，由 _annual_performance_table_refs 已处理
        tables.append(table)

    header_tables = tuple(table for table in tables if _performance_column_indexes(table.rows, specs))
    headerless_tables = tuple(
        table
        for table in tables
        if _performance_column_indexes(table.rows, specs) is None
        and _has_performance_past_year_row(table.rows)
    )
    if not header_tables:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 目标列缺失")

    try:
        share_scopes = _annual_performance_table_share_scopes(
            header_tables,
            section_text_by_ref=section_text_by_ref,
            requested_share_class=requested_share_class,
        )
    except DocumentToolError:
        # Docling 分裂跨 section 场景：share scope 无法确定时，默认所有表为 A
        share_scopes = {t.table_ref: _SHARE_SCOPE_A for t in header_tables}

    requested_scope = _normalize_share_class_scope(requested_share_class) if requested_share_class else None
    if requested_share_class and requested_scope is None:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")

    fields: list[AnnualPerformanceExtraction] = []
    for table in header_tables:
        share_scope = share_scopes.get(table.table_ref)
        if share_scope is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 份额类别无法唯一识别")
        if requested_scope is not None and share_scope != requested_scope:
            continue
        row = _performance_past_year_row(table.rows, share_scope=share_scope)
        if row is None:
            continue
        indexes = _performance_column_indexes(table.rows, specs)
        if indexes is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 目标列缺失")

        share_fields: list[AnnualPerformanceExtraction] = []
        try:
            for spec in specs:
                column_index = indexes[spec.field_name]
                value = _single_percent_text(row[column_index])
                share_fields.append(
                    AnnualPerformanceExtraction(
                        field_name=spec.field_name,
                        decimal_percent_text=value,
                        report_year=report_year,
                        source_period_label=_PERFORMANCE_RETURN_PERIOD_TEXT,
                        share_class_scope=share_scope,
                        raw_text=_performance_raw_text(
                            period_text=row[0],
                            column_text=table.rows[0][column_index],
                            value_text=value,
                        ),
                        citation=table.citation,
                    )
                )
        except DocumentToolError:
            continue
        if len(share_fields) == len(specs):
            fields.extend(share_fields)

    # 无表头部分表（A/C 分段表的后续段）：用同 section 相邻表头对齐列位置，
    # 按行内份额标签切段后逐 scope 抽取，不再整体 not_found。
    for table in headerless_tables:
        indexes = _headerless_performance_column_indexes(table, header_tables, specs)
        if indexes is None:
            continue
        if not _performance_table_has_share_labels(table.rows):
            continue
        for share_scope in _SHARE_CLASS_SCOPES:
            if requested_scope is not None and share_scope != requested_scope:
                continue
            row = _performance_past_year_row(table.rows, share_scope=share_scope)
            if row is None:
                continue
            share_fields: list[AnnualPerformanceExtraction] = []
            try:
                for spec in specs:
                    column_index = indexes[spec.field_name]
                    value = _single_percent_text(row[column_index])
                    share_fields.append(
                        AnnualPerformanceExtraction(
                            field_name=spec.field_name,
                            decimal_percent_text=value,
                            report_year=report_year,
                            source_period_label=_PERFORMANCE_RETURN_PERIOD_TEXT,
                            share_class_scope=share_scope,
                            raw_text=_performance_raw_text(
                                period_text=row[0],
                                column_text=table.rows[0][column_index],
                                value_text=value,
                            ),
                            citation=table.citation,
                        )
                    )
            except DocumentToolError:
                continue
            if len(share_fields) == len(specs):
                fields.extend(share_fields)

    if not fields:
        missing_row_note = ""
        if not any(_has_performance_past_year_row(table.rows) for table in header_tables):
            missing_row_note = (
                "：业绩阶段表存在但无「过去一年」行"
                + _performance_missing_past_year_note(header_tables)
            )
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 过去一年完整字段缺失" + missing_row_note)
    return tuple(fields)


def _extract_annual_excess_return_fields(
    *,
    document_id: str,
    result: AgentRunResult,
    tool_service: FundDocumentToolService,
    report_year: int,
    requested_share_class: str | None,
) -> tuple[AnnualExcessReturnExtraction, ...]:
    """从 title-family matched table 的 ①－③ 列抽取年度超额收益披露值。"""

    excess_specs = _validated_annual_excess_return_specs()
    signature_specs = _annual_excess_return_signature_specs(excess_specs)
    source_section_refs = _annual_performance_source_section_refs(result)
    table_refs = _annual_performance_table_refs(
        document_id=document_id,
        result=result,
        tool_service=tool_service,
        source_section_refs=source_section_refs,
        specs=signature_specs,
    )

    section_text_by_ref: dict[str, str] = {}
    for section_ref in source_section_refs:
        section = tool_service.read_section(document_id, section_ref)
        if isinstance(section, ToolFailure):
            raise DocumentToolError(section.code, section.message)
        section_text_by_ref[section_ref] = section.text

    tables: list[TableContent] = []
    for table_ref in table_refs:
        table = tool_service.read_table(document_id, table_ref, max_rows=_PERFORMANCE_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            raise DocumentToolError(table.code, table.message)
        # section 分裂兼容：不在此处过滤，由 _annual_performance_table_refs 已处理
        tables.append(table)

    header_tables = tuple(table for table in tables if _performance_column_indexes(table.rows, signature_specs))
    headerless_tables = tuple(
        table
        for table in tables
        if _performance_column_indexes(table.rows, signature_specs) is None
        and _has_performance_past_year_row(table.rows)
    )
    if not header_tables:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual excess return ①－③ 列缺失")

    try:
        share_scopes = _annual_excess_return_table_share_scopes(
            header_tables,
            section_text_by_ref=section_text_by_ref,
            requested_share_class=requested_share_class,
        )
    except DocumentToolError:
        # Docling 分裂跨 section 场景：share scope 无法唯一识别时，与 10F 一致默认所有表为 A
        share_scopes = {t.table_ref: _SHARE_SCOPE_A for t in header_tables}
    requested_scope = _normalize_share_class_scope(requested_share_class) if requested_share_class else None
    if requested_share_class and requested_scope is None:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual excess return 份额类别无法唯一识别")

    fields: list[AnnualExcessReturnExtraction] = []
    for table in header_tables:
        share_scope = share_scopes.get(table.table_ref)
        if share_scope is None:
            continue
        if requested_scope is not None and share_scope != requested_scope:
            continue
        row = _performance_past_year_row(table.rows, share_scope=share_scope)
        if row is None:
            continue
        indexes = _performance_column_indexes(table.rows, signature_specs)
        if indexes is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "annual excess return ①－③ 列缺失")

        try:
            column_index = indexes[_FIELD_ANNUAL_EXCESS_RETURN]
            value = _single_percent_text(row[column_index])
        except DocumentToolError:
            continue
        fields.append(
            AnnualExcessReturnExtraction(
                field_name=_FIELD_ANNUAL_EXCESS_RETURN,
                decimal_percent_text=value,
                report_year=report_year,
                source_period_label=_PERFORMANCE_RETURN_PERIOD_TEXT,
                share_class_scope=share_scope,
                source_column_label=_ANNUAL_EXCESS_RETURN_COLUMN_LABEL,
                raw_text=_performance_raw_text(
                    period_text=row[0],
                    column_text=table.rows[0][column_index],
                    value_text=value,
                ),
                citation=table.citation,
            )
        )

    # 无表头部分表：用同 section 相邻表头对齐列位置，按行内份额标签切段后逐 scope 抽取
    for table in headerless_tables:
        indexes = _headerless_performance_column_indexes(table, header_tables, signature_specs)
        if indexes is None:
            continue
        if not _performance_table_has_share_labels(table.rows):
            continue
        for share_scope in _SHARE_CLASS_SCOPES:
            if requested_scope is not None and share_scope != requested_scope:
                continue
            row = _performance_past_year_row(table.rows, share_scope=share_scope)
            if row is None:
                continue
            try:
                column_index = indexes[_FIELD_ANNUAL_EXCESS_RETURN]
                value = _single_percent_text(row[column_index])
            except DocumentToolError:
                continue
            fields.append(
                AnnualExcessReturnExtraction(
                    field_name=_FIELD_ANNUAL_EXCESS_RETURN,
                    decimal_percent_text=value,
                    report_year=report_year,
                    source_period_label=_PERFORMANCE_RETURN_PERIOD_TEXT,
                    share_class_scope=share_scope,
                    source_column_label=_ANNUAL_EXCESS_RETURN_COLUMN_LABEL,
                    raw_text=_performance_raw_text(
                        period_text=row[0],
                        column_text=table.rows[0][column_index],
                        value_text=value,
                    ),
                    citation=table.citation,
                )
            )

    if not fields:
        missing_row_note = ""
        if not any(_has_performance_past_year_row(table.rows) for table in header_tables):
            missing_row_note = (
                "：业绩阶段表存在但无「过去一年」行"
                + _performance_missing_past_year_note(header_tables)
            )
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual excess return 过去一年 ①－③ 字段缺失" + missing_row_note)
    return tuple(fields)


def _validated_performance_return_specs() -> tuple[_PerformanceReturnExtractionSpec, ...]:
    """校验 10D performance_returns 抽取配置，异常时映射为 schema_drift。"""

    specs = tuple(_PERFORMANCE_RETURN_EXTRACTION_SPECS)
    expected = (_FIELD_NAV_GROWTH_RATE, _FIELD_BENCHMARK_RETURN_RATE)
    actual = tuple(spec.field_name for spec in specs)
    if actual != expected:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "performance_returns 抽取配置异常")
    for spec in specs:
        if not spec.column_keywords or any(not keyword for keyword in spec.column_keywords):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "performance_returns 抽取配置不完整")
    return specs


def _annual_performance_table_share_scopes(
    tables: tuple[TableContent, ...],
    *,
    section_text_by_ref: dict[str, str],
    requested_share_class: str | None,
) -> dict[str, str]:
    """按 10F 表格自身和 section 上下文绑定年度业绩份额类别。"""

    try:
        return _performance_table_share_scopes(
            tables,
            section_text_by_ref=section_text_by_ref,
            requested_share_class=requested_share_class,
        )
    except DocumentToolError:
        inferred = {
            table.table_ref: scope
            for table in tables
            if (scope := _annual_performance_share_scope_from_rows(table.rows)) is not None
        }
        if len(inferred) == len(tables):
            return inferred
        raise


def _annual_performance_share_scope_from_rows(rows: tuple[tuple[str, ...], ...]) -> str | None:
    """从年度业绩表的受控行标签识别 A/C 份额类别。

    判别顺序：含「自基金转型起至今」→ A（转型基金 A 类）；含「过去三年/过去五年」
    → A（非转型 A 类历史更长，多年度行存在）；仅「自基金合同生效起至今」→ C。
    """

    normalized_rows = tuple(_normalize_disclosure_text(cell) for row in rows for cell in row)
    if any("自基金转型起至今" in cell for cell in normalized_rows):
        return _SHARE_SCOPE_A
    if any(("过去三年" in cell or "过去五年" in cell) for cell in normalized_rows):
        return _SHARE_SCOPE_A
    if any("自基金合同生效起至今" in cell for cell in normalized_rows):
        return _SHARE_SCOPE_C
    return None


def _validated_annual_performance_specs() -> tuple[_PerformanceReturnExtractionSpec, ...]:
    """校验 10F annual performance 抽取配置，异常时映射为 schema_drift。"""

    specs = tuple(_ANNUAL_PERFORMANCE_EXTRACTION_SPECS)
    expected = (_FIELD_ANNUAL_NAV_GROWTH_RATE, _FIELD_ANNUAL_BENCHMARK_RETURN_RATE)
    actual = tuple(spec.field_name for spec in specs)
    if actual != expected:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual performance 抽取配置异常")
    for spec in specs:
        if not spec.column_keywords or any(not keyword for keyword in spec.column_keywords):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual performance 抽取配置不完整")
    return specs


def _validated_annual_excess_return_specs() -> tuple[_PerformanceReturnExtractionSpec, ...]:
    """校验 10G annual excess return 抽取配置，异常时映射为 schema_drift。"""

    specs = tuple(_ANNUAL_EXCESS_RETURN_EXTRACTION_SPECS)
    expected = (_FIELD_ANNUAL_EXCESS_RETURN,)
    actual = tuple(spec.field_name for spec in specs)
    if actual != expected:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual excess return 抽取配置异常")
    for spec in specs:
        if not spec.column_keywords or any(not keyword for keyword in spec.column_keywords):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "annual excess return 抽取配置不完整")
    return specs


def _annual_excess_return_signature_specs(
    excess_specs: tuple[_PerformanceReturnExtractionSpec, ...],
) -> tuple[_PerformanceReturnExtractionSpec, ...]:
    """返回 10G 表格 signature：10F 两列加显式披露 ①－③ 列。"""

    return (*_validated_annual_performance_specs(), *excess_specs)


def _annual_excess_return_table_share_scopes(
    tables: tuple[TableContent, ...],
    *,
    section_text_by_ref: dict[str, str],
    requested_share_class: str | None,
) -> dict[str, str]:
    """按 10G partial-by-share-class 口径绑定可唯一识别的份额类别。"""

    try:
        return _annual_performance_table_share_scopes(
            tables,
            section_text_by_ref=section_text_by_ref,
            requested_share_class=requested_share_class,
        )
    except DocumentToolError:
        inferred: dict[str, str] = {}
        for table in tables:
            scope = _annual_performance_share_scope_from_rows(table.rows)
            if scope is not None:
                inferred[table.table_ref] = scope
        if len(inferred) == len(tables):
            return inferred
        raise


def _performance_table_citation_refs(result: AgentRunResult) -> tuple[tuple[str, str], ...]:
    """从 11A locator result 中提取实际 table citation 的 section/table refs。"""

    table_refs = tuple(
        dict.fromkeys(
            (citation.locator.section_ref, citation.locator.table_ref)
            for citation in result.citations
            if citation.locator.locator_kind is LocatorKind.TABLE
            and citation.locator.section_ref
            and citation.locator.table_ref
        )
    )
    if not table_refs:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 缺少 table citation")
    return table_refs


def _annual_performance_source_section_refs(result: AgentRunResult) -> tuple[str, ...]:
    """返回命中 10F 固定 title family 的 section refs。

    title-family 命中 = 前缀行命中 OR answer 正文包含（raw-excerpt 兜底：Docling
    section 切分把 3.2.1 标题嵌在「3.2 基金净值表现」正文内时首行/前缀行未命中）。
    answer 为有界公开输出；下游仍要求 SECTION/TABLE citation、列签名与「过去一年」行。
    """

    title_lines = _target_title_lines(result.answer)
    title_family_hit = any(_ANNUAL_PERFORMANCE_TITLE_FAMILY in line for line in title_lines) or (
        _ANNUAL_PERFORMANCE_TITLE_FAMILY in result.answer
    )
    if not title_family_hit:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 目标 title-family 未找到")
    section_refs = tuple(
        dict.fromkeys(
            citation.locator.section_ref
            for citation in result.citations
            if citation.locator.locator_kind is LocatorKind.SECTION and citation.locator.section_ref
        )
    )
    if not section_refs:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance section citation 缺失")
    return section_refs


def _annual_performance_table_refs(
    *,
    document_id: str,
    result: AgentRunResult,
    tool_service: FundDocumentToolService,
    source_section_refs: tuple[str, ...],
    specs: tuple[_PerformanceReturnExtractionSpec, ...],
) -> tuple[str, ...]:
    """从 title-family section 内定位满足 10F signature 的候选表格。"""

    # 优先严格匹配（table section 在 source_section_refs 内）；
    # Docling section 分裂时标题和表格可能归属不同 section，回退到所有 TABLE citation
    all_table_citation_refs = tuple(
        dict.fromkeys(
            citation.locator.table_ref
            for citation in result.citations
            if citation.locator.locator_kind is LocatorKind.TABLE
            and citation.locator.table_ref
        )
    )
    strict_table_refs = tuple(
        dict.fromkeys(
            citation.locator.table_ref
            for citation in result.citations
            if citation.locator.locator_kind is LocatorKind.TABLE
            and citation.locator.section_ref in source_section_refs
            and citation.locator.table_ref
        )
    )
    cited_table_refs = strict_table_refs if strict_table_refs else all_table_citation_refs
    if not cited_table_refs:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance table citation 缺失")

    def _read_candidate_table(
        table_ref: str,
        *,
        require_header: bool = True,
    ) -> TableContent | None:
        table = tool_service.read_table(document_id, table_ref, max_rows=_PERFORMANCE_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            return None
        if strict_table_refs and table.section_ref not in source_section_refs:
            return None
        if require_header and _performance_column_indexes(table.rows, specs) is None:
            return None
        return table

    # 第一遍：收集所有列签名匹配的 cited table（含 Docling 分裂的不完整表）。
    # cited_related 标记 cited 表是否与 performance 表相关（有 header 或有"过去一年"行），
    # 用于区分「cited 表不完整需要同 section 相邻表补全」与「cited 表根本无关，
    # 不得消费未被 cite 的 signature 表」两种场景。
    refs: list[str] = []
    cited_related = False
    for table_ref in cited_table_refs:
        table = _read_candidate_table(table_ref, require_header=False)
        if table is None:
            continue
        if _performance_column_indexes(table.rows, specs) is not None:
            refs.append(table.table_ref)
        if (
            _performance_column_indexes(table.rows, specs) is not None
            or _has_performance_past_year_row(table.rows)
        ):
            cited_related = True

    # 检查已收集的表中是否有含"过去一年"行的完整表；
    # Docling 分裂场景：agent 可能只 cite 了不完整的前半段，后半段未被 cite。
    # 此时需要 fallback 扫描 section 内全部表格来补全。
    _any_complete = any(
        (_t := _read_candidate_table(r)) is not None and _has_performance_past_year_row(_t.rows)
        for r in refs
    ) if refs else False

    if not _any_complete:
        # fallback: 扫描全部表格（Docling 分裂跨 section 场景）
        all_tables = tool_service.list_tables(document_id)
        for t_meta in all_tables:
            if t_meta.table_ref in refs:
                continue
            table = tool_service.read_table(document_id, t_meta.table_ref, max_rows=_PERFORMANCE_TABLE_MAX_ROWS)
            if isinstance(table, ToolFailure):
                continue
            # source_section_refs 内的表：
            # - 无表头续表（A/C 分段表的后续段）且含"过去一年"行时纳入；
            # - 有独立 header 但未被 cite 的表，仅在 cited 表确为 performance 相关且
            #   该表含完整"过去一年"行时纳入（007466-2024 的 A 类完整表 table-15 场景）。
            if hasattr(t_meta, "section_ref") and t_meta.section_ref in source_section_refs:
                if _performance_column_indexes(table.rows, specs) is not None:
                    if not cited_related or not _has_performance_past_year_row(table.rows):
                        continue
                elif not _has_performance_past_year_row(table.rows):
                    continue
                refs.append(table.table_ref)
                continue
            # 其他 section 的表：原有逻辑
            if _performance_column_indexes(table.rows, specs) is None:
                continue
            refs.append(table.table_ref)

    # 按文档顺序排序，保证 share scope 与表按出现顺序一一绑定
    if hasattr(tool_service, "list_tables"):
        table_order = {
            t_meta.table_ref: index
            for index, t_meta in enumerate(tool_service.list_tables(document_id))
        }
        refs_tuple = tuple(dict.fromkeys(sorted(refs, key=lambda ref: table_order.get(ref, len(table_order)))))
    else:
        refs_tuple = tuple(dict.fromkeys(refs))
    if not refs_tuple:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 目标列缺失")
    return refs_tuple


def _performance_column_indexes(
    rows: tuple[tuple[str, ...], ...],
    specs: tuple[_PerformanceReturnExtractionSpec, ...],
) -> dict[str, int] | None:
    """返回收益表两类目标列的唯一列下标。"""

    if not rows:
        return None
    header = rows[0]
    indexes: dict[str, int] = {}
    for spec in specs:
        matches = tuple(
            index
            for index, cell in enumerate(header)
            if index > 0 and _header_matches_performance_spec(cell, spec)
        )
        if len(matches) != 1:
            return None
        indexes[spec.field_name] = matches[0]
    if len(set(indexes.values())) != len(indexes):
        return None
    return indexes


def _header_matches_performance_spec(cell: str, spec: _PerformanceReturnExtractionSpec) -> bool:
    """判断表头单元格是否唯一对应 10D 目标字段。"""

    normalized = _normalize_disclosure_text(cell)
    # 归一化 dash：部分年报表头使用全角 U+FF0D（﹣），与 keyword 中的 ASCII U+002D（-）不匹配
    normalized = normalized.replace("－", "-")
    return all(
        keyword.replace("－", "-") in normalized
        for keyword in spec.column_keywords
    ) and not any(
        keyword.replace("－", "-") in normalized
        for keyword in spec.excluded_keywords
    )


def _has_performance_past_year_row(rows: tuple[tuple[str, ...], ...]) -> bool:
    """非抛错判断表格是否包含 过去一年 行（用于分裂扫描）。"""

    return any(
        row and _normalize_disclosure_text(row[0]) == _PERFORMANCE_RETURN_PERIOD_TEXT
        for row in rows[1:]
    )


def _performance_missing_past_year_note(tables: tuple[TableContent, ...]) -> str:
    """构造「业绩表存在但无过去一年行」的附加可解释说明。

    参数:
        tables: 已满足 10F/10G 列签名的候选业绩表。

    返回:
        以表内受控行标签为依据的说明后缀；无转型/合同生效期间标记时返回空串。
    """

    normalized = {
        _normalize_disclosure_text(cell)
        for table in tables
        for row in table.rows
        for cell in row
    }
    if any("自基金转型起至今" in cell for cell in normalized):
        return "（表内仅披露「自基金转型起至今」等期间，转型当年无全年份额净值增长率）"
    if any("自基金合同生效起至今" in cell for cell in normalized):
        return "（表内仅披露「自基金合同生效起至今」等期间，合同生效当年无全年份额净值增长率）"
    return ""


_PERFORMANCE_SHARE_SEGMENT_RE = re.compile(r"([ACINY])(?:类)?$")


def _performance_share_segment_label(row: tuple[str, ...]) -> str | None:
    """从份额标签行首列识别份额类别（A/C/I/Y）；非标签行返回 None。"""

    if not row:
        return None
    first = _normalize_disclosure_text(row[0])
    if not first:
        return None
    match = _PERFORMANCE_SHARE_SEGMENT_RE.search(first)
    if match is None:
        return None
    # 标签行要求其余单元格为空，避免把数据行误判为份额标签
    if any(_normalize_disclosure_text(cell) for cell in row[1:]):
        return None
    return match.group(1)


def _performance_share_segment_rows(
    rows: tuple[tuple[str, ...], ...],
    share_scope: str,
) -> tuple[tuple[str, ...], ...]:
    """按行内份额标签切段，返回目标份额类别的数据行（不含标签行与段首表头）。"""

    label_indexes = [
        (index, label)
        for index, row in enumerate(rows)
        if (label := _performance_share_segment_label(row)) is not None
    ]
    if not label_indexes:
        # 无标签行的单段表：整表属于目标份额类别，按原口径跳过表头行
        return rows[1:]
    for index, (row_index, label) in enumerate(label_indexes):
        if label != share_scope:
            continue
        start = row_index + 1
        end = label_indexes[index + 1][0] if index + 1 < len(label_indexes) else len(rows)
        return tuple(
            row
            for row in rows[start:end]
            if _normalize_disclosure_text(row[0]) != "阶段"
        )
    return ()


def _performance_table_has_share_labels(rows: tuple[tuple[str, ...], ...]) -> bool:
    """判断表格是否包含可识别的份额标签行（用于无表头合并表切段）。"""

    return any(_performance_share_segment_label(row) is not None for row in rows)


def _performance_past_year_row(
    rows: tuple[tuple[str, ...], ...],
    *,
    share_scope: str | None = None,
) -> tuple[str, ...] | None:
    """返回目标份额类别的唯一 past_1_year 行；缺失或单段多行按 not_found 处理。"""

    candidates = (
        _performance_share_segment_rows(rows, share_scope)
        if share_scope is not None
        else rows[1:]
    )
    matches = tuple(
        row
        for row in candidates
        if row and _normalize_disclosure_text(row[0]) == _PERFORMANCE_RETURN_PERIOD_TEXT
    )
    if len(matches) > 1:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 过去一年行无法唯一识别")
    return matches[0] if matches else None


def _headerless_performance_column_indexes(
    table: TableContent,
    header_tables: tuple[TableContent, ...],
    specs: tuple[_PerformanceReturnExtractionSpec, ...],
) -> dict[str, int] | None:
    """为无表头续表从同 section 相邻表头表对齐目标列位置。"""

    width = max((len(row) for row in table.rows), default=0)
    candidates = (
        tuple(header for header in header_tables if header.section_ref == table.section_ref)
        or header_tables
    )
    for header in candidates:
        indexes = _performance_column_indexes(header.rows, specs)
        if indexes is None:
            continue
        if max(indexes.values(), default=0) < width:
            return indexes
    return None


def _performance_table_share_scopes(
    tables: tuple[TableContent, ...],
    *,
    section_text_by_ref: dict[str, str],
    requested_share_class: str | None,
) -> dict[str, str]:
    """按 section/table 上下文为 performance table 绑定唯一份额类别。"""

    if requested_share_class:
        normalized_requested = _normalize_share_class_scope(requested_share_class)
        if normalized_requested is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")
        if len(tables) == 1:
            return {tables[0].table_ref: normalized_requested}

    scopes: dict[str, str] = {}
    tables_by_section: dict[str, list[TableContent]] = {}
    for table in tables:
        if table.section_ref is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")
        tables_by_section.setdefault(table.section_ref, []).append(table)

    for section_ref, section_tables in tables_by_section.items():
        labels = _share_class_labels_from_text(section_text_by_ref.get(section_ref, ""))
        if len(labels) != len(section_tables):
            if not labels and len(section_tables) == 1:
                # section 文本无 A/C 标签且只有 1 个表，默认为 A
                # 场景：Docling 分裂跨 section，完整表所在 section 无份额类别标识
                scopes[section_tables[0].table_ref] = _SHARE_SCOPE_A
                continue
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")
        for table, label in zip(section_tables, labels, strict=True):
            scopes[table.table_ref] = label
    return scopes


_SHARE_CLASS_SCOPE_RE = re.compile(
    r"[一-龥）\)]([AC])(?:类)?(?:基金份额)?$|([AC])类"
)


def _share_class_labels_from_text(text: str) -> tuple[str, ...]:
    """从安全 section 文本中按出现顺序提取可控 A/C 份额类别标签。"""

    labels: list[str] = []
    for line in text.splitlines():
        normalized = _normalize_disclosure_text(line)
        if not normalized:
            continue
        m = _SHARE_CLASS_SCOPE_RE.search(normalized)
        if not m:
            continue
        found = m.group(1) or m.group(2)
        if found and found not in labels:
            labels.append(found)
    return tuple(labels)


def _normalize_share_class_scope(share_class: str) -> str | None:
    """把显式 share_class 输入收敛到 A/C；未知值不猜测。"""

    normalized = _normalize_disclosure_text(share_class).upper()
    for scope in _SHARE_CLASS_SCOPES:
        if normalized in {scope, f"{scope}类", f"{scope}类份额", f"{scope}类基金份额"}:
            return scope
    return None


def _prefer_share_scope_fields(fields, preferred_scope: str):
    """优先返回指定份额类别的字段；无该类别时回退到全部字段。"""

    scoped = tuple(
        field for field in fields
        if getattr(field, "share_class_scope", None) == preferred_scope
    )
    return scoped if scoped else tuple(fields)


def _single_percent_text(cell: str) -> str:
    """从目标表格单元格中读取唯一百分号文本，不转小数。"""

    compact = _normalize_disclosure_text(cell)
    matches = re.findall(r"-?\d+(?:\.\d+)?%", compact)
    if len(matches) != 1:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 数值无法唯一抽取")
    return matches[0]


def _performance_raw_text(*, period_text: str, column_text: str, value_text: str) -> str:
    """构造只含目标 period/列/单元格的 table-first raw_text。"""

    return " | ".join(
        (
            _compact_raw_text(period_text),
            _compact_raw_text(column_text),
            value_text,
        )
    )


def _normalize_disclosure_text(text: str) -> str:
    """去除披露文本中的排版空白，用于受控匹配。"""

    return re.sub(r"\s+", "", text)


def _normalize_percent_text(text: str) -> str:
    """折叠百分比数值内部空白（Docling 分块噪声）。

    只作用于百分比邻域：折叠数字、小数点、百分号之间的空白，
    例如 `1.  50%` -> `1.50%`、`1. 50 %` -> `1.50%`；
    正文其余部分保持不变。

    参数:
        text: 待归一化文本。

    返回:
        百分比 token 内部空白折叠后的文本。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """

    def _collapse(match: re.Match[str]) -> str:
        return re.sub(r"\s+", "", match.group(0))

    return re.sub(r"\d+\s*(?:\.\s*\d+)?\s*%", _collapse, text)


def _detect_share_class(cell_text: str) -> str | None:
    """从表头单元格文本识别份额类别。

    按 / 拆分后逐 token 匹配，支持"指数A"、"A/B"、"联接A"等格式。
    返回 "A"、"C" 或 None。
    """
    text = _normalize_disclosure_text(cell_text)
    # 联接 A / 联接 C
    m = re.search(r"联接\s*([AC])", text)
    if m:
        return m.group(1)
    for token in text.split("/"):
        token = token.strip()
        if not token:
            continue
        for label in ("A类", "C类", "A", "C"):
            if token == label:
                return label[0]
            if token.endswith(label):
                idx = len(token) - len(label) - 1
                if idx >= 0:
                    ch = token[idx]
                    if ch.isascii() and ch.isalpha():
                        continue
                return label[0]
    return None


def _extract_nav_for_class(text: str, share_class: str) -> float | None:
    """类名匹配提取单位净值：在文本中查找 share_class 关联的基金份额净值数值。"""

    escaped = re.escape(share_class)
    nav_re = re.compile(
        r"(?:联接\s*" + escaped + r"|" + escaped + r"\s*类)"
        r".*?基金份额净值\s*(?:为)?\s*([\d.]+)\s*元"
    )
    m = nav_re.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_scale_from_text(text: str) -> dict[str, str]:
    """从段落文本提取份额/持有人比例，作为表格提取的兜底。

    正则加 [^。]*? 前缀锚定，避免跨句匹配。
    """
    result: dict[str, str] = {}

    # A类份额
    m = re.search(r"[^。]*?A类(?:基金)?份额(?:总额)?\s*([\d,]+(?:\.[\d,]+)?)\s*份", text)
    if m:
        result["total_shares_a"] = m.group(1)

    # C类份额
    m = re.search(r"[^。]*?C类(?:基金)?份额(?:总额)?\s*([\d,]+(?:\.[\d,]+)?)\s*份", text)
    if m:
        result["total_shares_c"] = m.group(1)

    # 总份额（无类别前缀时兜底）
    if "total_shares_a" not in result and "total_shares_c" not in result:
        m = re.search(r"[^。]*?基金份额总额[：:\s]*([\d,]+(?:\.[\d,]+)?)\s*份", text)
        if m:
            result["total_shares_a"] = m.group(1)

    # 个人投资者比例
    m = re.search(r"[^。]*?个人投资者[^。]*?(\d+\.?\d*)\s*%", text)
    if m:
        result["individual_investor_ratio"] = m.group(1) + "%"

    return result


def _compact_raw_text(raw_text: str) -> str:
    """压缩原文片段中的排版空白，但不改写披露值。"""

    return re.sub(r"\s+", " ", raw_text).strip(" ：，。")


def _bounded_unique_candidates(candidates: tuple[str, ...]) -> tuple[str, ...]:
    """保序去重并保证候选 query 总数不超过上限。"""

    unique_candidates = tuple(dict.fromkeys(candidates))
    if not unique_candidates or len(unique_candidates) > _MAX_QUERY_CANDIDATES:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 候选不符合契约")
    return unique_candidates


def _catalog_document_ids(catalog_path: Path) -> tuple[str, ...]:
    """读取 catalog 中的 document_id 列表，不返回本地路径或 raw payload。"""

    if not Path(catalog_path).exists():
        return ()
    try:
        payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "catalog 暂不可读") from exc
    except json.JSONDecodeError as exc:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog 不是有效 JSON") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog schema 不兼容")
    reports = payload.get("reports")
    if not isinstance(reports, dict):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog reports 结构不符合契约")
    return tuple(sorted(str(document_id) for document_id in reports))


_HOLDINGS_COLUMN_NAMES = ("序号", "股票代码", "股票名称", "数量", "公允价值", "占基金资产净值比例")


def _fund_name_matches(extracted_name: str, repo_name: str) -> bool:
    """规范化匹配基金名称，处理 "交易型开放式指数" ↔ "ETF" 等等价表述。

    参数:
        extracted_name: 从报告中提取的基金名称。
        repo_name: 仓库中的基金名称。

    返回:
        匹配成功返回 True。
    """
    if extracted_name in repo_name:
        return True
    # 规范化：将长形式替换为短形式后比较
    normalized_extracted = extracted_name.replace("交易型开放式指数证券投资基金", "ETF").replace("交易型开放式指数", "ETF")
    normalized_repo = repo_name.replace("交易型开放式指数证券投资基金", "ETF").replace("交易型开放式指数", "ETF")
    if normalized_extracted in normalized_repo:
        return True
    # 反向：将短形式替换为长形式后比较
    if "ETF" in extracted_name:
        expanded = extracted_name.replace("ETF", "交易型开放式指数")
        if expanded in repo_name:
            return True
    return False


def _extract_target_etf_code(document_id: str, store: DoclingDocumentStore) -> tuple[str, str] | None:
    """从年报提取目标 ETF 代码和名称。

    搜索「投资目标」「投资范围」「基金基本情况」「基金简介」章节，
    匹配「目标ETF」「联接基金」相关描述，提取 ETF 名称或代码。

    返回:
        (etf_fund_code, etf_fund_name) 或 None。
    """
    sections = store.list_sections()
    target_refs: list[str] = []
    keywords = ("投资目标", "投资范围", "基金基本情况", "基金简介", "目标基金")
    for section in sections:
        title = section.title or ""
        if any(kw in title for kw in keywords):
            target_refs.append(section.section_ref)

    combined = ""
    for ref in target_refs:
        try:
            sec = store.read_section(ref, max_chars=5000)
            combined += sec.text + "\n"
        except DocumentToolError:
            pass
        # 读取 section 内表格内容（基金简介等信息常在表格中）
        for t_meta in store.list_tables():
            if t_meta.section_ref != ref or not t_meta.table_ref:
                continue
            try:
                tbl = store.read_table(t_meta.table_ref, max_rows=20)
                if hasattr(tbl, "rows"):
                    for row in tbl.rows:
                        combined += " ".join(str(c).strip() for c in row) + "\n"
            except (DocumentToolError, Exception):
                pass

    if not combined:
        return None

    own_code = store._identity.fund_code

    # Pattern 1: ETF name + code in parens
    m = re.search(r'([\u4e00-\u9fa5A-Za-z]+ETF)\s*[（(](\d{6})[）)]', combined)
    if m:
        code, name = m.group(2), m.group(1)
        if code != own_code:
            return code, name

    # Pattern 2: 提取「交易型开放式指数证券投资基金」完整名称
    m2 = re.search(r'([\u4e00-\u9fa5A-Za-z]+交易型开放式指数证券投资基金)', combined)
    if m2:
        etf_name = m2.group(1).replace("联接基金", "")
        return "", etf_name

    # Pattern 3: 6-digit code near ETF mention
    for cm in re.finditer(r'\b(\d{6})\b', combined):
        code = cm.group(1)
        if code == own_code:
            continue
        nearby = combined[max(0, cm.start() - 40):cm.end() + 40]
        # 跳过"下属分级基金/交易代码"上下文中的代码（C类份额代码）
        context_wide = combined[max(0, cm.start() - 80):cm.end() + 80]
        if "分级" in context_wide or "交易代码" in context_wide:
            continue
        if "ETF" in nearby:
            return code, ""

    # Pattern 4: 从表格中提取目标 ETF 信息
    # 联接基金年报的基础信息表格（如"基金简介"章节）含目标 ETF 名称和代码，
    # 先按"基金主代码"精确匹配代码，再按名称模式匹配
    all_tables = store.list_tables()
    target_section_refs = set()
    for section in sections:
        title = section.title or ""
        if any(kw in title for kw in ("目标基金", "基金简介", "基金基本情况")):
            target_section_refs.add(section.section_ref)

    # 收集目标 section 下所有表格
    target_tables_text = ""
    for table_meta in all_tables:
        if table_meta.section_ref not in target_section_refs or not table_meta.table_ref:
            continue
        try:
            table = store.read_table(table_meta.table_ref, max_rows=20)
        except (DocumentToolError, Exception):
            continue
        if not hasattr(table, "rows") or not table.rows:
            continue
        for row in table.rows:
            row_text = " ".join(str(c).strip() for c in row)
            # 精确匹配"基金主代码"行中的6位代码
            if "基金主代码" in row_text:
                code_match = re.search(r'(\d{6})', row_text)
                if code_match and code_match.group(1) != own_code:
                    return code_match.group(1), ""
            target_tables_text += " ".join(
                str(c).strip().replace(" ", "") for c in row
            ) + " "

    if target_tables_text:
        # Pattern 4a: 匹配 "xxx交易型开放式指数" 前缀
        m4 = re.search(r'([一-龥A-Za-z0-9]+交易型开放式指数)', target_tables_text)
        if m4:
            etf_name = m4.group(1).replace("联接基金", "")
            return "", etf_name
        # Pattern 4b: ETF 短名称
        m5 = re.search(r'([一-龥]+ETF)', target_tables_text)
        if m5:
            return "", m5.group(1)

    return None

def _is_qdii_header_text(header_text: str) -> bool:
    """判断拼接后的表头文本是否具备 QDII 持仓特征（含截断前缀兼容）。

    QDII 持仓表头在 Docling 输出中可能被截断（如 519696-2023 的「证券代」、
    「公司名」），完整关键词预检会漏放；这里同时接受「证券代码/证券代」与
    「公司名称/公司名」两类前缀形态。真正的表级鉴别仍由
    `_extract_qdii_table_with_continuations` 内的 `_holdings_column_indexes`
    完成，本函数只是扫描入口的低成本预筛。

    参数:
        header_text: 表头行所有单元格去空白后的拼接文本。

    返回:
        True 表示表头具备 QDII 持仓特征，可进入详情解析。
    """

    has_code = "证券代码" in header_text or "证券代" in header_text
    has_name = "公司名称" in header_text or "公司名" in header_text
    return has_code and has_name


def _extract_stock_holdings_from_tables(
    *,
    document_id: str,
    tool_service: FundDocumentToolService,
) -> tuple[tuple[HoldingExtraction, ...], Citation | None] | None:
    """直接扫描文档表格，查找 A 股持仓表并抽取数据。

    当 Agent citation 首位命中非持仓表（如行业配置表）且后续无持仓表 citation 时的兜底方案。
    按 list_tables 顺序扫描表头，命中 A 股持仓特征列（stock_code 或 quantity + stock_name +
    percentage）后解析数据行；不足 10 行时复用 _extract_holdings_continuations 做跨页续表合并。

    参数:
        document_id: 文档 ID。
        tool_service: 文档工具服务。

    返回:
        (持仓列表, 主表 citation)；未找到 A 股持仓表时返回 None。
    """

    tables = tool_service.list_tables(document_id)
    for table_meta in tables:
        if not table_meta.table_ref:
            continue
        header_table = tool_service.read_table(document_id, table_meta.table_ref, max_rows=1)
        if isinstance(header_table, ToolFailure) or not header_table.rows:
            continue
        column_indexes = _holdings_column_indexes(header_table.rows)
        if column_indexes is None:
            continue
        if "stock_code" not in column_indexes and "quantity" not in column_indexes:
            continue
        full_table = tool_service.read_table(document_id, table_meta.table_ref, max_rows=_HOLDINGS_TABLE_MAX_ROWS)
        if isinstance(full_table, ToolFailure) or not full_table.rows:
            continue

        holdings: list[HoldingExtraction] = []
        for row in full_table.rows[1:]:  # 跳过表头
            if len(row) <= max(column_indexes.values()):
                continue
            stock_code = row[column_indexes["stock_code"]].strip()
            stock_name = row[column_indexes["stock_name"]].strip()
            if not stock_code and not stock_name:
                continue
            quantity = row[column_indexes.get("quantity", 0)].strip() if "quantity" in column_indexes else ""
            fair_value = row[column_indexes.get("fair_value", 0)].strip() if "fair_value" in column_indexes else ""
            percentage = row[column_indexes["percentage"]].strip()
            holdings.append(HoldingExtraction(
                rank=len(holdings) + 1,
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
                fair_value=fair_value,
                percentage=percentage,
            ))
            if len(holdings) >= _HOLDINGS_TOP_N:
                break
        if not holdings:
            continue

        if len(holdings) < _HOLDINGS_TOP_N:
            holdings.extend(_extract_holdings_continuations(
                document_id=document_id,
                tool_service=tool_service,
                primary_section_ref=full_table.section_ref,
                primary_page=full_table.locator.page_no,
                primary_table_ref=full_table.table_ref,
                primary_column_indexes=column_indexes,
                existing_count=len(holdings),
            ))
        return tuple(holdings[:_HOLDINGS_TOP_N]), full_table.citation
    return None


def _extract_qdii_holdings_from_tables(
    *,
    document_id: str,
    tool_service: FundDocumentToolService,
) -> tuple[tuple[HoldingExtraction, ...], Citation] | None:
    """直接扫描文档表格，查找 QDII 格式持仓表并抽取数据。

    当 Agent citation 未能正确引用 QDII 持仓表时的兜底方案。
    支持跨页分裂表：主表（QDII 表头）+ 续表（碎片行 + 数据行）；
    表头被跨页截断时用续表首行碎片补齐，碎片行（首列非序号）跳过。
    命中时返回 (持仓列表, 主表 citation)；主表 citation 与 A 股 direct 分支同约定：
    跨页续表合并 / 表头截断补齐时，citation 仍以主表（表头通过 _is_qdii_header_text
    识别的那张表）为准。

    参数:
        document_id: 文档 ID。
        tool_service: 文档工具服务。

    返回:
        (持仓列表, 命中主表 citation)；未找到 QDII 表时返回 None。
    """
    tables = tool_service.list_tables(document_id)
    for table_meta in tables:
        if not table_meta.table_ref:
            continue
        # 快速检查表头是否含 QDII 特征列名
        header_table = tool_service.read_table(document_id, table_meta.table_ref, max_rows=1)
        if isinstance(header_table, ToolFailure) or not header_table.rows:
            continue
        header_text = "".join(cell.strip().replace(" ", "") for cell in header_table.rows[0])
        if not _is_qdii_header_text(header_text):
            continue
        # 命中 QDII 表，读取全部数据行
        full_table = tool_service.read_table(document_id, table_meta.table_ref, max_rows=_HOLDINGS_TABLE_MAX_ROWS)
        if isinstance(full_table, ToolFailure) or not full_table.rows:
            continue
        holdings = _extract_qdii_table_with_continuations(
            document_id=document_id,
            tool_service=tool_service,
            primary_table=full_table,
        )
        if holdings:
            return tuple(holdings[:_HOLDINGS_TOP_N]), full_table.citation
    return None


def _extract_qdii_table_with_continuations(
    *,
    document_id: str,
    tool_service: FundDocumentToolService,
    primary_table: TableContent,
) -> list[HoldingExtraction]:
    """从 QDII 主表及同章节跨页续表合并抽取持仓行。

    参数:
        document_id: 文档 ID。
        tool_service: 文档工具服务。
        primary_table: 含 QDII 特征表头的主表。

    返回:
        合并后的持仓列表（最多 _HOLDINGS_TOP_N 行）。
    """

    column_indexes = _holdings_column_indexes(primary_table.rows)
    continuation: TableContent | None = None
    data_source = primary_table
    if column_indexes is None:
        # 表头可能被跨页截断（如 2024：'占基 金资' + 续表 '产净值比例（%）'），
        # 用续表首行碎片补齐表头后再抽取。
        continuation = _find_qdii_header_continuation(
            document_id=document_id,
            tool_service=tool_service,
            primary_table=primary_table,
        )
        if continuation is None:
            return []
        merged_header = _merge_qdii_header_fragments(
            primary_table.rows[0],
            continuation.rows[0],
        )
        column_indexes = _holdings_column_indexes((merged_header,))
        if column_indexes is None:
            return []
        data_source = continuation

    holdings: list[HoldingExtraction] = []
    for row in data_source.rows[1:]:  # 跳过 header
        extracted = _holding_from_qdii_row(
            row,
            column_indexes,
            rank=len(holdings) + 1,
        )
        if extracted is not None:
            holdings.append(extracted)
            if len(holdings) >= _HOLDINGS_TOP_N:
                return holdings

    if len(holdings) < _HOLDINGS_TOP_N:
        holdings.extend(
            _extract_qdii_continuation_rows(
                document_id=document_id,
                tool_service=tool_service,
                primary_table=primary_table,
                column_indexes=column_indexes,
                existing_count=len(holdings),
            )
        )
    return holdings[:_HOLDINGS_TOP_N]


def _find_qdii_header_continuation(
    *,
    document_id: str,
    tool_service: FundDocumentToolService,
    primary_table: TableContent,
) -> TableContent | None:
    """查找同章节下一页、列数一致的续表，用于补齐截断表头。

    参数:
        document_id: 文档 ID。
        tool_service: 文档工具服务。
        primary_table: 表头截断的 QDII 主表。

    返回:
        续表内容；未找到时返回 None。
    """

    primary_col_count = len(primary_table.rows[0]) if primary_table.rows else 0
    for table_meta in tool_service.list_tables(document_id):
        if table_meta.table_ref == primary_table.table_ref:
            continue
        if table_meta.section_ref != primary_table.section_ref:
            continue
        if (
            table_meta.locator.page_no is not None
            and primary_table.locator.page_no is not None
            and table_meta.locator.page_no <= primary_table.locator.page_no
        ):
            continue
        if table_meta.column_count != primary_col_count:
            continue
        table = tool_service.read_table(document_id, table_meta.table_ref, max_rows=1)
        if isinstance(table, ToolFailure) or not table.rows:
            continue
        if _is_qdii_rank_row(table.rows[0]):
            continue  # 首行已是数据行，不是表头碎片
        return table
    return None


def _merge_qdii_header_fragments(
    header: tuple[str, ...],
    fragments: tuple[str, ...],
) -> tuple[str, ...]:
    """按列拼接主表表头与续表碎片行文本。"""

    return tuple(
        (header[idx] if idx < len(header) else "").strip()
        + (fragments[idx] if idx < len(fragments) else "").strip()
        for idx in range(max(len(header), len(fragments)))
    )


def _extract_qdii_continuation_rows(
    *,
    document_id: str,
    tool_service: FundDocumentToolService,
    primary_table: TableContent,
    column_indexes: dict[str, int],
    existing_count: int,
) -> list[HoldingExtraction]:
    """抽取同章节跨页续表的数据行（跳过碎片行）。"""

    primary_col_count = len(primary_table.rows[0]) if primary_table.rows else 0
    holdings: list[HoldingExtraction] = []
    for table_meta in tool_service.list_tables(document_id):
        if table_meta.table_ref == primary_table.table_ref:
            continue
        if table_meta.section_ref != primary_table.section_ref:
            continue
        if (
            table_meta.locator.page_no is not None
            and primary_table.locator.page_no is not None
            and table_meta.locator.page_no <= primary_table.locator.page_no
        ):
            continue
        if table_meta.column_count != primary_col_count:
            continue
        table = tool_service.read_table(document_id, table_meta.table_ref, max_rows=_HOLDINGS_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure) or not table.rows:
            continue
        for row in table.rows:
            if len(holdings) + existing_count >= _HOLDINGS_TOP_N:
                return holdings
            if not _is_qdii_rank_row(row):
                continue  # 跳过跨页碎片行
            extracted = _holding_from_qdii_row(
                row,
                column_indexes,
                rank=existing_count + len(holdings) + 1,
            )
            if extracted is not None:
                holdings.append(extracted)
    return holdings


def _is_qdii_rank_row(row: tuple[str, ...]) -> bool:
    """判断行是否为 QDII 持仓数据行（首列为序号数字）。"""

    if not row:
        return False
    try:
        int(row[0].strip())
    except (ValueError, AttributeError):
        return False
    return True


def _holding_from_qdii_row(
    row: tuple[str, ...],
    column_indexes: dict[str, int],
    *,
    rank: int,
) -> HoldingExtraction | None:
    """按列索引把单行映射为持仓抽取结果；无效行返回 None。"""

    if len(row) <= max(column_indexes.values()):
        return None
    stock_code = row[column_indexes["stock_code"]].strip()
    stock_name = row[column_indexes["stock_name"]].strip()
    if not stock_code and not stock_name:
        return None
    quantity = row[column_indexes.get("quantity", 0)].strip() if "quantity" in column_indexes else ""
    fair_value = row[column_indexes.get("fair_value", 0)].strip() if "fair_value" in column_indexes else ""
    percentage = row[column_indexes["percentage"]].strip()
    return HoldingExtraction(
        rank=rank,
        stock_code=stock_code,
        stock_name=stock_name,
        quantity=quantity,
        fair_value=fair_value,
        percentage=percentage,
    )


def _extract_holdings_from_agent_result(
    *,
    document_id: str,
    result: AgentRunResult,
    tool_service: FundDocumentToolService,
) -> tuple[HoldingExtraction, ...]:
    """从 Agent 结果中抽取前十大持仓数据，支持跨页表格合并。"""

    table_citation_refs = [
        citation for citation in result.citations
        if citation.locator.locator_kind is LocatorKind.TABLE and citation.locator.table_ref
    ]
    if not table_citation_refs:
        raise DocumentToolError(FailureCode.NOT_FOUND, "持仓表格 citation 缺失")

    holdings: list[HoldingExtraction] = []
    primary_table_ref = None
    primary_section_ref = None
    primary_page = None

    for citation in table_citation_refs:
        table_ref = citation.locator.table_ref
        if not table_ref:
            continue
        table = tool_service.read_table(document_id, table_ref, max_rows=_HOLDINGS_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            raise DocumentToolError(table.code, table.message)

        if not _is_holdings_table_candidate(table.rows):
            # 表级鉴别：自身表头无股票/债券特征列的表格（如行业配置表）不得被当作持仓表消费，
            # 跳过该 citation 继续遍历，而非 break。
            continue

        column_indexes = _holdings_column_indexes(table.rows)
        if column_indexes is None:
            column_indexes = _bond_holdings_column_indexes(table.rows)
            is_bond_table = column_indexes is not None
        else:
            is_bond_table = False

        # 表格无 header 时（如跨页续表），搜索相邻表格的 header
        # 限制：同 section 内双向查找，table_ref 编号在 [当前-5, 当前+5] 范围内
        header_from_other_table = False
        if column_indexes is None and not is_bond_table:
            try:
                current_num = int(table_ref.split("-")[-1])
            except (ValueError, IndexError):
                current_num = 0
            all_tables = tool_service.list_tables(document_id)

            def _same_section_nearby(candidate: TableSummary) -> bool:
                """候选表必须与当前表同 section 且编号在双向 5 表范围内。"""

                try:
                    cand_num = int(candidate.table_ref.split("-")[-1])
                except (ValueError, IndexError):
                    return False
                return (
                    cand_num != current_num
                    and abs(cand_num - current_num) <= 5
                    and candidate.section_ref == table.section_ref
                )

            # 优先找含 股票名称+占基金资产净值比例 表头的表
            for candidate in all_tables:
                if not _same_section_nearby(candidate):
                    continue
                candidate_table = tool_service.read_table(document_id, candidate.table_ref, max_rows=1)
                if isinstance(candidate_table, ToolFailure):
                    continue
                stock_idx = _holdings_column_indexes(candidate_table.rows)
                if stock_idx is not None:
                    column_indexes = stock_idx
                    is_bond_table = False
                    header_from_other_table = True
                    break

            # 其次才找债券持仓表头
            if column_indexes is None:
                for candidate in all_tables:
                    if not _same_section_nearby(candidate):
                        continue
                    candidate_table = tool_service.read_table(document_id, candidate.table_ref, max_rows=1)
                    if isinstance(candidate_table, ToolFailure):
                        continue
                    bond_idx = _bond_holdings_column_indexes(candidate_table.rows)
                    if bond_idx is not None:
                        column_indexes = bond_idx
                        is_bond_table = True
                        header_from_other_table = True
                        break

        if column_indexes is None:
            continue

        primary_table_ref = table_ref
        primary_section_ref = table.section_ref
        primary_page = table.locator.page_no

        # header 来自其他表时（续表无 header），从第一行开始
        data_start = 0 if header_from_other_table else 1
        data_rows = table.rows[data_start:]
        for row in data_rows:
            if len(row) <= max(column_indexes.values()):
                continue
            stock_code = row[column_indexes["stock_code"]].strip()
            stock_name = row[column_indexes["stock_name"]].strip()
            if is_bond_table and stock_name == "合计":
                continue
            quantity = row[column_indexes.get("quantity", 0)].strip() if "quantity" in column_indexes else ""
            fair_value = row[column_indexes.get("fair_value", 0)].strip() if "fair_value" in column_indexes else ""
            percentage = row[column_indexes["percentage"]].strip()
            if not stock_code and not stock_name:
                continue
            holdings.append(HoldingExtraction(
                rank=len(holdings) + 1,
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
                fair_value=fair_value,
                percentage=percentage,
            ))
        break

    if primary_table_ref and primary_section_ref and len(holdings) < _HOLDINGS_TOP_N:
        primary_column_indexes = None
        for citation in table_citation_refs:
            table = tool_service.read_table(document_id, citation.locator.table_ref, max_rows=1)
            if not isinstance(table, ToolFailure):
                primary_column_indexes = _holdings_column_indexes(table.rows)
                break

        continuation_holdings = _extract_holdings_continuations(
            document_id=document_id,
            tool_service=tool_service,
            primary_section_ref=primary_section_ref,
            primary_page=primary_page,
            primary_table_ref=primary_table_ref,
            primary_column_indexes=primary_column_indexes,
            existing_count=len(holdings),
        )
        holdings.extend(continuation_holdings)

    return tuple(holdings[:_HOLDINGS_TOP_N])


def _extract_holdings_continuations(
    *,
    document_id: str,
    tool_service: FundDocumentToolService,
    primary_section_ref: str,
    primary_page: int | None,
    primary_table_ref: str,
    primary_column_indexes: dict[str, int] | None,
    existing_count: int,
) -> list[HoldingExtraction]:
    """查找并提取持仓表的跨页续表。"""

    all_tables = tool_service.list_tables(document_id)
    continuation_tables: list[TableContent] = []

    for t in all_tables:
        if t.table_ref == primary_table_ref:
            continue
        table = tool_service.read_table(document_id, t.table_ref, max_rows=_HOLDINGS_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            continue
        if table.section_ref != primary_section_ref:
            continue
        if primary_page and table.locator.page_no and table.locator.page_no <= primary_page:
            continue
        column_indexes = _holdings_column_indexes(table.rows)
        if column_indexes is None:
            if _is_continuation_row(table.rows):
                continuation_tables.append(table)
            continue
        continuation_tables.append(table)

    holdings: list[HoldingExtraction] = []
    for table in continuation_tables:
        column_indexes = _holdings_column_indexes(table.rows)
        if column_indexes:
            data_rows = table.rows[1:]
        else:
            data_rows = table.rows

        for row in data_rows:
            if len(holdings) + existing_count >= _HOLDINGS_TOP_N:
                break
            if column_indexes:
                if len(row) <= max(column_indexes.values()):
                    continue
                stock_code = row[column_indexes["stock_code"]].strip()
                stock_name = row[column_indexes["stock_name"]].strip()
                quantity = row[column_indexes["quantity"]].strip() if "quantity" in column_indexes else ""
                fair_value = row[column_indexes["fair_value"]].strip() if "fair_value" in column_indexes else ""
                percentage = row[column_indexes["percentage"]].strip()
            elif primary_column_indexes:
                if len(row) <= max(primary_column_indexes.values()):
                    continue
                stock_code = row[primary_column_indexes["stock_code"]].strip()
                stock_name = row[primary_column_indexes["stock_name"]].strip()
                quantity = row[primary_column_indexes["quantity"]].strip() if "quantity" in primary_column_indexes else ""
                fair_value = row[primary_column_indexes["fair_value"]].strip() if "fair_value" in primary_column_indexes else ""
                percentage = row[primary_column_indexes["percentage"]].strip()
            else:
                if len(row) < 4:
                    continue
                stock_code = row[1].strip() if len(row) > 1 else ""
                stock_name = row[2].strip() if len(row) > 2 else ""
                quantity = row[3].strip() if len(row) > 3 else ""
                fair_value = row[4].strip() if len(row) > 4 else ""
                percentage = row[5].strip() if len(row) > 5 else ""

            if not stock_code and not stock_name:
                continue
            holdings.append(HoldingExtraction(
                rank=existing_count + len(holdings) + 1,
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
                fair_value=fair_value,
                percentage=percentage,
            ))

    return holdings


def _is_continuation_row(rows: tuple[tuple[str, ...], ...]) -> bool:
    """检查是否为持仓表续表（无表头，第一列是序号）。"""

    if not rows:
        return False
    first_row = rows[0]
    if len(first_row) < 3:
        return False
    try:
        int(first_row[0].strip())
        return True
    except (ValueError, IndexError):
        return False


def _is_holdings_table_candidate(rows: tuple[tuple[str, ...], ...]) -> bool:
    """表级鉴别：判断表格是否可作为持仓表候选被消费。

    规则：自身表头必须满足其一——
    1. A 股持仓表：stock_code 或 quantity 特征列 + stock_name + percentage；
    2. 债券持仓表（_bond_holdings_column_indexes 可识别）；
    3. 无表头续表（首列为序号），允许经相邻表头查找后消费。

    行业配置表（行业类别/公允价值/占净值比例）无股票特征列，返回 False。

    参数:
        rows: 表格有界行（首行视为表头）。

    返回:
        True 表示可作为持仓表候选；False 表示应跳过该表。
    """

    if not rows:
        return False
    indexes = _holdings_column_indexes(rows)
    if indexes is not None:
        return "stock_code" in indexes or "quantity" in indexes
    if _bond_holdings_column_indexes(rows) is not None:
        return True
    return _is_continuation_row(rows)


def _holdings_column_indexes(rows: tuple[tuple[str, ...], ...]) -> dict[str, int] | None:
    """识别持仓表的列索引映射。

    除完整子串匹配外，支持截断表头前缀识别（519696-2023 的「证券代」「占基」）：
    `stock_code` 接受「证券代」前缀、`percentage` 接受「占基」「占基金」前缀；
    前缀匹配必须校验该列数据单元格含数字，防止行业配置表/估值表等误绑。
    前缀识别仍失败时，按 QDII 固定列序做位置推断兜底。

    参数:
        rows: 表格有界行（首行视为表头）。

    返回:
        列索引映射（至少含 stock_name 与 percentage）；无法识别时返回 None。
    """

    if not rows:
        return None
    header = rows[0]
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header):
        cell_clean = cell.strip().replace(" ", "")
        if "股票代码" in cell_clean or "证券代码" in cell_clean:
            mapping["stock_code"] = idx
        elif cell_clean.startswith("证券代") and _column_has_digits(rows, idx):
            # 截断表头（如「证券代」）前缀识别；要求列数据含数字防误绑。
            mapping["stock_code"] = idx
        elif "股票名称" in cell_clean:
            mapping["stock_name"] = idx
        elif "数量" in cell_clean:
            mapping["quantity"] = idx
        elif "公允价值" in cell_clean:
            mapping["fair_value"] = idx
        elif "占基金资产净值比例" in cell_clean or "占比" in cell_clean:
            mapping["percentage"] = idx
        elif (
            (cell_clean.startswith("占基") or cell_clean.startswith("占基金"))
            and _column_has_digits(rows, idx)
        ):
            # 截断表头（如「占基」「占基金」）前缀识别；要求列数据含数字防误绑。
            mapping["percentage"] = idx

    if "stock_name" not in mapping:
        # QDII 持仓表列名：公司名称（中文）/ 公司名称（英文）——优先中文列
        company_name_indexes = [
            idx for idx, cell in enumerate(header)
            if "公司名称" in cell.strip().replace(" ", "")
        ]
        if company_name_indexes:
            mapping["stock_name"] = next(
                (
                    idx for idx in company_name_indexes
                    if "中文" in header[idx].strip().replace(" ", "")
                ),
                company_name_indexes[0],
            )

    # 注意：不将 stock_name 映射到 stock_code，避免语义错误。
    # QDII 表若无"证券代码"列，stock_code 留空由上层处理。

    required = ("stock_name", "percentage")
    if all(k in mapping for k in required):
        return mapping
    return _infer_qdii_column_indexes_by_position(rows)


def _column_has_digits(rows: tuple[tuple[str, ...], ...], idx: int) -> bool:
    """检查表格列中是否存在含数字的数据单元格（排除表头行）。

    截断表头前缀匹配的防误绑校验：仅当该列其余单元格含数字时才允许放宽绑定。
    表头行之外无数据单元格（如表头仅有一行的跨页主表）时返回 False，保持 fail-closed。

    参数:
        rows: 表格有界行（首行视为表头）。
        idx: 待校验列索引。

    返回:
        True 表示该列存在含数字的数据单元格。
    """

    for row in rows[1:]:
        if idx < len(row) and row[idx].strip():
            return any(ch.isdigit() for ch in row[idx])
    return False


def _infer_qdii_column_indexes_by_position(
    rows: tuple[tuple[str, ...], ...],
) -> dict[str, int] | None:
    """按 QDII 固定列序推断持仓列索引（截断前缀识别失败时的兜底）。

    仅在表头可确认 QDII 持仓结构时启用：首列为序号、存在「数量」「公允价值」相邻
    列、占比为末列且含数字、代码列数据匹配「短 token + 两位大写交易所后缀」
    （QDII 代码形如 700 HK / MSFT US）。任一条件不满足即返回 None，
    避免行业配置表/估值表/买卖明细表被位置推断误判。

    参数:
        rows: 表格有界行（首行视为表头）。

    返回:
        完整列索引映射（stock_code/stock_name/quantity/fair_value/percentage）；
        无法确认时返回 None。
    """

    if not rows:
        return None
    header = rows[0]
    if not header or header[0].strip() not in ("序号", "序"):
        return None

    quantity_idx: int | None = None
    fair_value_idx: int | None = None
    for idx, cell in enumerate(header):
        cell_clean = cell.strip().replace(" ", "")
        if "数量" in cell_clean:
            quantity_idx = idx
        elif "公允价值" in cell_clean:
            fair_value_idx = idx
    if quantity_idx is None or fair_value_idx is None:
        return None
    if fair_value_idx != quantity_idx + 1:
        return None

    percentage_idx = fair_value_idx + 1
    if percentage_idx != len(header) - 1:
        return None
    if not _column_has_digits(rows, percentage_idx):
        return None

    name_idx: int | None = None
    for idx in range(1, quantity_idx):
        cell_clean = header[idx].strip().replace(" ", "")
        if "名称" in cell_clean or "公司" in cell_clean:
            name_idx = idx
            break
    if name_idx is None:
        return None

    # 代码列位于数量列之前，数据形如「700 HK」「MSFT US」（短 token + 两位大写
    # 交易所后缀）；名称/市场/国家列不满足该模式，避免误绑。
    code_pattern = re.compile(r"^\S+ [A-Z]{2}$")
    code_idx: int | None = None
    for idx in range(1, quantity_idx):
        cells = [row[idx] for row in rows[1:] if idx < len(row) and row[idx].strip()]
        if sum(1 for cell in cells if code_pattern.match(cell)) >= 2:
            code_idx = idx
            break
    if code_idx is None:
        return None

    return {
        "stock_code": code_idx,
        "stock_name": name_idx,
        "quantity": quantity_idx,
        "fair_value": fair_value_idx,
        "percentage": percentage_idx,
    }


def _bond_holdings_column_indexes(rows: tuple[tuple[str, ...], ...]) -> dict[str, int] | None:
    """识别债券持仓表的列索引映射。

    支持两种格式：
    1. 汇总表：序号 | 债券品种 | 公允价值 | 占基金资产净值比例
    2. 明细表：序号 | 债券代码 | 债券名称 | 数量(张) | 公允价值 | 占净值比例

    映射到 HoldingExtraction：stock_code=债券代码(或序号), stock_name=债券名称(或债券品种), quantity=数量, fair_value=公允价值, percentage=占比
    """
    if not rows:
        return None
    header = rows[0]
    mapping: dict[str, int] = {}
    has_bond_code = False
    for idx, cell in enumerate(header):
        cell_clean = cell.strip().replace(" ", "")
        if "债券代码" in cell_clean:
            mapping["stock_code"] = idx
            has_bond_code = True
        elif "债券名称" in cell_clean:
            mapping["stock_name"] = idx
        elif "债券品种" in cell_clean and "stock_name" not in mapping:
            mapping["stock_name"] = idx
        elif "数量" in cell_clean:
            mapping["quantity"] = idx
        elif "公允价值" in cell_clean and "占基金资产净值比例" not in cell_clean:
            mapping["fair_value"] = idx
        elif "占基金资产净值比例" in cell_clean or "占比" in cell_clean:
            mapping["percentage"] = idx
    # 无债券代码时用序号作为 stock_code（汇总表格式）
    if not has_bond_code:
        for idx, cell in enumerate(header):
            if cell.strip() == "序号":
                mapping["stock_code"] = idx
                break

    required = ("stock_code", "stock_name", "percentage")
    if all(k in mapping for k in required):
        return mapping
    return None


def _extract_allocation_from_agent_result(
    *,
    document_id: str,
    result: AgentRunResult,
    tool_service: FundDocumentToolService,
) -> tuple[tuple[AssetAllocationItem, ...], tuple[IndustryAllocationItem, ...]]:
    """从 Agent 结果中抽取资产配置和行业配置。"""

    asset_allocation: list[AssetAllocationItem] = []
    industry_allocation: list[IndustryAllocationItem] = []

    table_citation_refs = [
        citation for citation in result.citations
        if citation.locator.locator_kind is LocatorKind.TABLE and citation.locator.table_ref
    ]

    for citation in table_citation_refs:
        table_ref = citation.locator.table_ref
        if not table_ref:
            continue
        table = tool_service.read_table(document_id, table_ref, max_rows=30)
        if isinstance(table, ToolFailure):
            continue

        if _is_asset_allocation_table(table.rows):
            asset_allocation = _parse_asset_allocation_table(table.rows)
            break

    if not asset_allocation:
        # citation 错绑 caption 含查询词的非资产配置表时（如 519696-2023 估值表），
        # 全表扫描兜底：命中表头 项目/金额/占基金总资产 的资产配置表即解析。
        all_tables = tool_service.list_tables(document_id)
        for t in all_tables:
            table = tool_service.read_table(document_id, t.table_ref, max_rows=30)
            if isinstance(table, ToolFailure):
                continue
            if _is_asset_allocation_table(table.rows):
                asset_allocation = _parse_asset_allocation_table(table.rows)
                break

    if not industry_allocation:
        all_tables = tool_service.list_tables(document_id)
        for t in all_tables:
            table = tool_service.read_table(document_id, t.table_ref, max_rows=30)
            if isinstance(table, ToolFailure):
                continue
            if _is_industry_allocation_table(table.rows):
                industry_allocation = _parse_industry_allocation_table(table.rows)
                break

    return tuple(asset_allocation), tuple(industry_allocation)


def _is_asset_allocation_table(rows: tuple[tuple[str, ...], ...]) -> bool:
    """判断是否为资产配置表。"""

    if not rows:
        return False
    header = rows[0]
    header_text = " ".join(str(c) for c in header)
    return "项目" in header_text and "金额" in header_text and ("占基金总资产" in header_text or "占总资产" in header_text)


def _is_industry_allocation_table(rows: tuple[tuple[str, ...], ...]) -> bool:
    """判断是否为行业配置表。"""

    if not rows:
        return False
    header = rows[0]
    header_text = " ".join(str(c) for c in header)
    return "行业类别" in header_text and "公允价值" in header_text


def _is_numeric_amount(value: str) -> bool:
    """检查字符串是否为有效数字金额（排除表头文字、全角减号等非数字内容）。"""
    if not value:
        return False
    # 全角减号单独出现（无后续数字）
    if value in ("－", "−", "—", "-", "–"):
        return False
    # 包含中文字符的表头文字（如"数量（份）"）
    if any("一" <= c <= "鿿" for c in value):
        return False
    return True


def _parse_asset_allocation_table(rows: tuple[tuple[str, ...], ...]) -> list[AssetAllocationItem]:
    """解析资产配置表。"""

    items: list[AssetAllocationItem] = []
    header = rows[0]

    category_idx = None
    amount_idx = None
    net_pct_idx = None
    total_pct_idx = None

    for idx, cell in enumerate(header):
        cell_str = str(cell).strip()
        if "项目" in cell_str:
            category_idx = idx
        elif "金额" in cell_str:
            amount_idx = idx
        elif "占基金资产净值" in cell_str:
            net_pct_idx = idx
        elif "占基金总资产" in cell_str or "占总资产" in cell_str:
            total_pct_idx = idx

    if category_idx is None or amount_idx is None:
        return items

    for row in rows[1:]:
        if len(row) <= max(category_idx, amount_idx):
            continue
        category = str(row[category_idx]).strip()
        amount = str(row[amount_idx]).strip()
        if not category or not amount:
            continue
        # 过滤表头文字和全角减号等非数字内容
        if not _is_numeric_amount(amount):
            continue
        net_pct = str(row[net_pct_idx]).strip() if net_pct_idx is not None and len(row) > net_pct_idx else ""
        total_pct = str(row[total_pct_idx]).strip() if total_pct_idx is not None and len(row) > total_pct_idx else ""
        items.append(AssetAllocationItem(
            category=category,
            amount=amount,
            percentage_of_net=net_pct,
            percentage_of_total=total_pct,
        ))

    return items


def _parse_industry_allocation_table(rows: tuple[tuple[str, ...], ...]) -> list[IndustryAllocationItem]:
    """解析行业配置表。"""

    items: list[IndustryAllocationItem] = []
    header = rows[0]

    industry_idx = None
    amount_idx = None
    pct_idx = None

    for idx, cell in enumerate(header):
        cell_str = str(cell).strip()
        if "行业类别" in cell_str:
            industry_idx = idx
        elif "公允价值" in cell_str:
            amount_idx = idx
        elif "占基金资产净值" in cell_str:
            pct_idx = idx

    if industry_idx is None or amount_idx is None:
        return items

    for row in rows[1:]:
        if len(row) <= max(industry_idx, amount_idx):
            continue
        industry = str(row[industry_idx]).strip()
        amount = str(row[amount_idx]).strip()
        if not industry or not amount:
            continue
        pct = str(row[pct_idx]).strip() if pct_idx is not None and len(row) > pct_idx else ""
        items.append(IndustryAllocationItem(
            industry=industry,
            amount=amount,
            percentage=pct,
        ))

    return items


_FEE_RATE_HISTORY_MARKER_RE = re.compile(
    r"自\s*\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*起"
)
_FEE_RATE_PERCENT_RE = re.compile(r"(\d+\.\d+%)")


def _fee_rate_from_title_block(answer: str, fee_name: str) -> str | None:
    """从费率标题块抽取当期适用费率。

    标题块从费率名称首次出现到下一个费率名称或文本末尾；块内含
    「自…年…月…日起」时取标记后首个百分比，否则取块内最后一个
    百分比（年报注文以当期费率结尾）。

    参数:
        answer: 百分比归一化后的 Agent 安全 answer。
        fee_name: 费率名称（基金管理费 / 基金托管费）。

    返回:
        当期适用费率；无法唯一确定时返回 None。

    异常:
        本函数不执行 I/O，不抛出业务异常。
    """

    start = answer.find(fee_name)
    if start < 0:
        return None
    end = len(answer)
    for other in _FEE_RATE_TITLES:
        if other == fee_name:
            continue
        position = answer.find(other, start + len(fee_name))
        if position > start:
            end = min(end, position)
    block = answer[start:end]
    marker = _FEE_RATE_HISTORY_MARKER_RE.search(block)
    if marker is not None:
        after_marker = block[marker.end():]
        after = _FEE_RATE_PERCENT_RE.search(after_marker)
        if after is not None:
            return after.group(1)
        return None
    percentages = _FEE_RATE_PERCENT_RE.findall(block)
    return percentages[-1] if percentages else None


def _extract_fee_rates_from_agent_result(
    *,
    result: AgentRunResult,
) -> tuple[FeeRateItem, ...]:
    """从 Agent 结果中抽取费率信息。

    先做百分比数值归一化（Docling 空格噪声）；管理费/托管费按费率标题块
    取当期适用费率：块内含「自…年…月…日起」时取标记后首个百分比，否则
    取块内最后一个百分比。
    """

    fees: list[FeeRateItem] = []
    answer = _normalize_percent_text(result.answer)

    for fee_name in ("基金管理费", "基金托管费"):
        rate = _fee_rate_from_title_block(answer, fee_name)
        if rate is not None:
            fees.append(FeeRateItem(fee_name=fee_name, rate=rate))

    # QDII 措辞兼容：年报正文以「管理人报酬」表述管理费（「基金管理费/管理费」
    # 均不出现），标题块命中后仍输出 基金管理费 字段。
    if not any(fee.fee_name == "基金管理费" for fee in fees):
        rate = _fee_rate_from_title_block(answer, _FEE_RATE_MANAGEMENT_WORDINGS[1])
        if rate is not None:
            fees.append(FeeRateItem(fee_name="基金管理费", rate=rate))

    fee_patterns = [
        (r"销售服务费.{0,80}?A类.{0,80}?不收取", "销售服务费A类"),
        (r"销售服务费.{0,80}?A类.{0,80}?(\d+\.\d+%)", "销售服务费A类"),
        (r"C类.{0,80}?销售服务费.{0,80}?(\d+\.\d+%)", "销售服务费C类"),
        (r"销售服务费.{0,80}?C类.{0,80}?(\d+\.\d+%)", "销售服务费C类"),
    ]

    for pattern, name in fee_patterns:
        match = re.search(pattern, answer, re.DOTALL)
        if match:
            rate = match.group(1) if match.lastindex else "不收取"
            if not any(f.fee_name == name for f in fees):
                fees.append(FeeRateItem(fee_name=name, rate=rate))

    if not fees:
        for fee_name, label in (
            ("管理费", "基金管理费"),
            ("托管费", "基金托管费"),
            (_FEE_RATE_MANAGEMENT_WORDINGS[1], "基金管理费"),
        ):
            rate = _fee_rate_from_title_block(answer, fee_name)
            if rate is not None:
                fees.append(FeeRateItem(fee_name=label, rate=rate))

        if "不收取" in answer and "销售服务费" in answer:
            fees.append(FeeRateItem(fee_name="销售服务费A类", rate="不收取"))

        sales_c_match = re.search(r"C.*?(\d+\.\d+%).*?销售服务费", answer, re.DOTALL)
        if sales_c_match:
            fees.append(FeeRateItem(fee_name="销售服务费C类", rate=sales_c_match.group(1)))

    return tuple(fees)


# ── Slice 16B 压力测试 ──────────────────────────────────────────────

STRESS_THRESHOLDS: dict[str, tuple[float, float, float]] = {
    "index_fund": (-0.30, -0.50, -0.70),
    "index_etf": (-0.30, -0.50, -0.70),
    "index_feeder": (-0.30, -0.50, -0.70),
    "bond_fund": (-0.05, -0.10, -0.20),
    "active_fund": (-0.25, -0.45, -0.65),
}


def infer_fund_type(fund_name: str) -> tuple[str, bool]:
    """基于基金名称关键词推断基金类型。

    参数:
        fund_name: 基金名称。

    返回:
        (fund_type, inferred) — fund_type 为 index_etf/index_feeder/index_fund/bond_fund/active_fund，
        inferred 为 True 表示由关键词匹配推断。
    """
    if "ETF联接" in fund_name or "ETF联接" in fund_name.replace(" ", ""):
        return "index_feeder", True
    if "ETF" in fund_name:
        return "index_etf", True
    if "联接" in fund_name:
        return "index_feeder", True
    # "交易型开放式" 是 ETF 的法定名称特征，必须在 "指数" 之前检查
    # 例：华泰柏瑞中证红利低波动交易型开放式指数证券投资基金
    if "交易型开放式" in fund_name:
        return "index_etf", True
    if "指数" in fund_name:
        return "index_fund", True
    if "债券" in fund_name or "债" in fund_name:
        return "bond_fund", True
    return "active_fund", True


def compute_stress_test(
    scale_info: ScaleInfo | None,
    nav_growth_rate: float | None,
    benchmark_return_rate: float | None,
    fund_name: str = "",
) -> StressTestResult:
    """计算 Ch6 压力测试结果。

    参数:
        scale_info: 规模信息（含 estimated_aum）。
        nav_growth_rate: 净值增长率（小数形式，如 0.087 表示 8.7%）。
        benchmark_return_rate: 基准收益率（小数形式）。
        fund_name: 基金名称（用于类型推断）。

    返回:
        StressTestResult，含三档损失金额和 stress_level。
    """
    fund_type, fund_type_inferred = infer_fund_type(fund_name)

    # 解析规模
    current_scale_billion: float | None = None
    if scale_info and scale_info.estimated_aum:
        current_scale_billion = _parse_aum_yi(scale_info.estimated_aum)

    # 计算三档损失金额
    thresholds = STRESS_THRESHOLDS[fund_type]
    scenario_names = ("normal", "extreme", "worst")
    stress_scenarios: dict[str, dict[str, float]] = {}
    for i, name in enumerate(scenario_names):
        t = thresholds[i]
        loss = None
        if current_scale_billion is not None:
            loss = round(current_scale_billion * abs(t), 6)
        stress_scenarios[name] = {
            "threshold": t,
            "loss_billion": loss if loss is not None else 0.0,
        }

    # 计算超额收益
    excess_return: float | None = None
    if nav_growth_rate is not None and benchmark_return_rate is not None:
        excess_return = round(nav_growth_rate - benchmark_return_rate, 6)

    # 判定 stress_level
    stress_level: str | None = None
    if excess_return is not None:
        if excess_return > 0:
            stress_level = "outperform"
        elif excess_return >= -0.02:
            stress_level = "inline"
        elif excess_return > -0.05:
            stress_level = "underperform"
        else:
            stress_level = "severe_underperform"

    return StressTestResult(
        fund_type=fund_type,
        fund_type_inferred=fund_type_inferred,
        current_scale_billion=current_scale_billion,
        stress_scenarios=stress_scenarios,
        nav_growth_rate=nav_growth_rate,
        benchmark_return_rate=benchmark_return_rate,
        excess_return=excess_return,
        stress_level=stress_level,
    )


def _compute_ch6_stress_test(
    performance: dict[int, dict[str, str]],
    report_year: int,
    scale_info: ScaleInfo | None,
    fund_name: str,
) -> StressTestResult | None:
    """从 report 数据中提取最新年份的净值增长率和基准收益率，计算压力测试。

    参数:
        performance: 多年度业绩数据（字符串百分比格式）。
        report_year: 报告年份。
        scale_info: 规模信息。
        fund_name: 基金名称。

    返回:
        StressTestResult，数据不足时返回 None。
    """
    latest = performance.get(report_year, {})
    nav_str = latest.get("nav_growth_rate", "")
    bench_str = latest.get("benchmark_return_rate", "")

    nav_rate = _parse_percent(nav_str)
    bench_rate = _parse_percent(bench_str)

    # 转换为小数
    nav_float = nav_rate / 100.0 if nav_rate is not None else None
    bench_float = bench_rate / 100.0 if bench_rate is not None else None

    if nav_float is None and bench_float is None and (scale_info is None or not scale_info.estimated_aum):
        return None

    return compute_stress_test(scale_info, nav_float, bench_float, fund_name)
