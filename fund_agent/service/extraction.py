"""基金年报阅读 use case Service 边界。"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fund_agent.agent import AgentRunResult, MinimalFundDocumentAgent
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
    AnnualExcessReturnExtraction,
    AnnualFeeResult,
    AnnualHoldingsResult,
    AnnualPerformanceExtraction,
    AnnualPerformanceFieldCitation,
    AnnualReportDocument,
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
    HoldingExtraction,
    IndustryAllocationItem,
    ThresholdEvent,
    MultiYearAllocationSeries,
    MultiYearAnnualPerformanceRow,
    MultiYearAnnualPerformanceSeries,
    MultiYearFeeSeries,
    MultiYearHoldingsSeries,
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
    score_concentration,
    score_excess_returns,
    score_fee_rate,
    score_manager_change,
    score_scale_risk,
    score_style_drift,
    to_risk_item,
    to_signal_indicator,
)


HostFactory = Callable[[FundDocumentToolService], MinimalHost]

PDF_BLOB_DIRNAME = "pdf_blobs"
DOCLING_JSON_DIRNAME = "docling_json"

_MAX_QUERY_CANDIDATES = 4
_TARGET_NOT_FOUND_MESSAGE = "未找到符合受控披露目标的证据"
_TABLE_TITLE_PREFIX = "表格标题:"
_SECTION_TITLE_PREFIX = "来源章节:"
_TABLE_BLOCK_HEADER = "相关表格:"
_FEE_RATES_QUERY = "费用"
_FEE_RATE_PERIOD_YEAR = "year"
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
_HOLDINGS_TABLE_MAX_ROWS = 15


DISCLOSURE_LOCATOR_CONTRACT_REGISTRY = (
    _DisclosureLocatorContract(
        profile_name="holdings_top10",
        aliases=("前十大持仓", "重仓股", "持仓明细"),
        candidate_queries=("股票投资明细", "前十名股票投资明细"),
        acceptable_title_family=("股票投资明细", "前十名股票投资明细"),
        requires_table_citation=True,
        extraction_allowed=False,
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
        profile_name="fee_rates",
        aliases=("费用", "费率", "管理费", "托管费", "销售服务费"),
        candidate_queries=("基金管理费", "基金托管费", "销售服务费"),
        acceptable_title_family=("基金管理费", "基金托管费", "销售服务费"),
        requires_table_citation=False,
        extraction_allowed=False,
    ),
    _DisclosureLocatorContract(
        profile_name="performance_returns",
        aliases=("净值增长率", "业绩比较基准收益率", "基准收益率", "收益表现", "基金净值表现"),
        candidate_queries=(
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
            r"(?P<raw>[^。\n]*本基金的管理费按前一日基金资产净值的"
            r"(?P<rate>\d+\.\d{2}%)的年\s*费\s*率计提)"
        ),
    ),
    _FeeRateExtractionSpec(
        field_name=_FIELD_CUSTODIAN_FEE_RATE,
        title="基金托管费",
        share_class_scope=_SHARE_SCOPE_ALL,
        pattern=re.compile(
            r"(?P<raw>[^。\n]*本基金的托管费按前一日基金资产净值的"
            r"(?P<rate>\d+\.\d{2}%)的年\s*费\s*率计提)"
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
    ) -> None:
        """初始化 Service 的可注入依赖。"""

        self._converter_factory = converter_factory or DoclingConverter
        self._host_factory = host_factory or _default_host_factory

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

            for year in normalized_years:
                document = documents_by_year.get(year)
                if document is None:
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
        # equity query 失败或债券基金持仓为空时，尝试债券持仓查询
        equity_failed = routed.agent_result.failure is not None
        if (equity_failed or True) and fund_name:
            fund_type, _ = infer_fund_type(fund_name)
            if fund_type == "bond_fund" and equity_failed:
                query = _BOND_HOLDINGS_QUERY
                routed = self._run_with_query_candidates(
                    host=host,
                    document_id=document_id,
                    query=query,
                )
        if routed.agent_result.failure is not None:
            return AnnualHoldingsResult(
                document_id=document_id,
                year=report_year,
                holdings=(),
                failure=routed.agent_result.failure,
            )
        try:
            holdings = _extract_holdings_from_agent_result(
                document_id=document_id,
                result=routed.agent_result,
                tool_service=tool_service,
            )
            # equity 成功但持仓为空且为债券基金时，尝试债券持仓查询
            if not holdings and fund_name:
                fund_type, _ = infer_fund_type(fund_name)
                if fund_type == "bond_fund":
                    bond_routed = self._run_with_query_candidates(
                        host=host,
                        document_id=document_id,
                        query=_BOND_HOLDINGS_QUERY,
                    )
                    if bond_routed.agent_result.failure is None:
                        bond_holdings = _extract_holdings_from_agent_result(
                            document_id=document_id,
                            result=bond_routed.agent_result,
                            tool_service=tool_service,
                        )
                        if bond_holdings:
                            holdings = bond_holdings
        except DocumentToolError as exc:
            return AnnualHoldingsResult(
                document_id=document_id,
                year=report_year,
                holdings=(),
                failure=ToolFailure(code=exc.code, message=exc.message),
            )
        except Exception:
            return AnnualHoldingsResult(
                document_id=document_id,
                year=report_year,
                holdings=(),
                failure=ToolFailure(code=FailureCode.UNAVAILABLE, message="持仓字段抽取暂不可用"),
            )

        table_citation = None
        for citation in routed.agent_result.citations:
            if citation.locator.locator_kind is LocatorKind.TABLE:
                table_citation = citation
                break

        return AnnualHoldingsResult(
            document_id=document_id,
            year=report_year,
            holdings=holdings,
            citation=table_citation,
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
                except (DocumentToolError, Exception):
                    pass

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
        fee_queries = ("基金管理费", "基金托管费", "销售服务费")

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
            except (DocumentToolError, Exception):
                continue

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
        if routed.agent_result.failure is not None:
            return DisclosureAuditItem(name="holdings", status="missing", chapter=False, message="持仓章节未找到")

        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
        # equity 无表格且为债券基金时，尝试债券持仓查询
        if not has_table and fund_name:
            fund_type, _ = infer_fund_type(fund_name)
            if fund_type == "bond_fund":
                bond_routed = self._run_with_query_candidates(host=host, document_id=document_id, query=_BOND_HOLDINGS_QUERY)
                if bond_routed.agent_result.failure is None:
                    bond_has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in bond_routed.agent_result.citations)
                    if bond_has_table:
                        routed = bond_routed
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

        fee_queries = ("基金管理费", "基金托管费", "销售服务费")
        found_fees: list[str] = []
        chapter_found = False

        for query in fee_queries:
            routed = self._run_with_query_candidates(host=host, document_id=document_id, query=query)
            if routed.agent_result.failure is None:
                chapter_found = True
                has_section = any(c.locator.locator_kind is LocatorKind.SECTION for c in routed.agent_result.citations)
                if has_section:
                    if query == "基金管理费":
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
            # 1. 提取多年度数据
            repository = _repository(Path(request.work_dir))
            catalog_reports = repository.list_reports()

            # 查找匹配的年报（按年份去重，保留最后一条）
            docs_by_year: dict[int, str] = {}
            available_years: list[int] = []
            for report in catalog_reports:
                if report.get("fund_code") == request.fund_code:
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
            holdings_data, holdings_citations = self._extract_report_holdings_with_citations(
                request.fund_code, annual_docs, request.work_dir,
            )
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
            scale_info, scale_citation = self._extract_scale_info(request.fund_code, annual_docs, request.work_dir, request.fund_name)

            # 构建证据来源汇总
            evidence = ChapterEvidence(
                holdings_citations=holdings_citations,
                fee_citations=fee_citations,
                allocation_citations=allocation_citations,
                performance_citations=performance_citations,
                fund_manager_citation=fund_manager_citation,
                scale_citation=scale_citation,
            )

            # 计算确定性信号判断和风险清单
            signal_judgment = self.compute_signal_judgment(
                performance=performance_data,
                fees=fee_data,
                holdings=holdings_data,
                fund_manager=fund_manager,
                scale_info=scale_info,
                report_year=request.report_year,
            )
            risk_checklist = self.compute_risk_checklist(
                fees=fee_data,
                holdings=holdings_data,
                fund_manager=fund_manager,
                scale_info=scale_info,
                report_year=request.report_year,
            )

            # 3. 生成报告章节
            llm_warnings: list[str] = []
            if llm_client is not None:
                # 使用审计管道协调器（14C）
                from fund_agent.service.audit_pipeline import ReportGenerationCoordinator
                coordinator = ReportGenerationCoordinator(
                    llm_client=llm_client,
                    work_dir=Path(request.work_dir),
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
                },
            )

            # 4. 输出
            output_path = None
            warnings: list[str] = list(llm_warnings)
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

    def _extract_report_holdings_with_citations(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
    ) -> tuple[dict[int, tuple[HoldingExtraction, ...]], dict[int, Citation | None]]:
        """提取多年度持仓数据及 citation。

        返回:
            (持仓数据字典, citation 字典)。
        """

        result = self.extract_multi_year_holdings(ExtractHoldingsRequest(
            fund_code=fund_code,
            requested_years=[d.year for d in annual_docs],
            annual_report_documents=annual_docs,
            work_dir=work_dir,
        ))
        if result.series is None:
            return {}, {}
        holdings = {h.year: h.holdings for h in result.series.annual_holdings}
        citations = {h.year: h.citation for h in result.series.annual_holdings}
        return holdings, citations

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
                continue
            result = self._extract_annual_performance_from_store(
                document_id=doc.document_id,
                store=store,
                report_year=doc.year,
                share_class=None,
            )
            if result.failure or not result.fields:
                continue
            nav = ""
            bench = ""
            citation = None
            for f in result.fields:
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
                    excess = excess_result.fields[0].decimal_percent_text
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
                            data_row = table.rows[2] if len(table.rows) > 2 else table.rows[1]
                            if len(data_row) >= 5:
                                name = str(data_row[0]).strip()
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
                                    data_row = full_table.rows[2]
                                    if len(data_row) >= 5:
                                        name = str(data_row[0]).strip()
                                        tenure_start = str(data_row[2]).strip()
                                        years_of_service = str(data_row[4]).strip()
                                        matched = True
                                        break
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

        # 搜索基金经理持有本基金
        holds_fund = ""
        tables = tool_service.list_tables(doc_id)
        for t in tables:
            table = tool_service.read_table(doc_id, t.table_ref, max_rows=10)
            if hasattr(table, "rows"):
                for row in table.rows:
                    row_str = " ".join(str(cell) for cell in row)
                    if "基金经理持有" in row_str and "开放式基金" in row_str:
                        for cell in row:
                            cell_str = str(cell).strip()
                            if "~" in cell_str or "万份" in cell_str:
                                holds_fund = cell_str
                                break

        if not name:
            return None, manager_citation

        return FundManagerInfo(
            name=name,
            tenure_start=tenure_start,
            years_of_service=years_of_service,
            investment_strategy=investment_strategy,
            holds_fund=holds_fund,
        ), manager_citation

    def _extract_scale_info(
        self,
        fund_code: str,
        annual_docs: list[AnnualReportDocument],
        work_dir: Path,
        fund_name: str = "",
    ) -> tuple[ScaleInfo | None, Citation | None]:
        """从年报提取规模信息及 citation（从最新年份开始尝试，回退到更早年份）。

        从份额变动表提取份额数，从"主要财务指标"文本提取单位净值，
        两者相乘估算 AUM。

        参数:
            fund_code: 基金代码。
            annual_docs: 年报文档列表。
            work_dir: 工作目录。

        返回:
            (ScaleInfo, Citation)；未找到时返回 (None, None)。
        """

        if not annual_docs:
            return None, None

        repository = _repository(Path(work_dir))
        sorted_docs = sorted(annual_docs, key=lambda d: d.year, reverse=True)

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

            # 搜索份额变动表（§10），包含持有人结构数据
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
                    table = tool_service.read_table(doc_id, t.table_ref, max_rows=15)
                    if not hasattr(table, "rows"):
                        continue
                    for row in table.rows:
                        if len(row) < 7:
                            continue
                        row_str = " ".join(str(cell) for cell in row)
                        if "混合A" in row_str or "A类" in row_str:
                            total_shares_a = str(row[3]).strip()
                        elif "混合C" in row_str or "C类" in row_str:
                            total_shares_c = str(row[3]).strip()
                        elif "合计" in row_str:
                            individual_investor_ratio = str(row[4]).strip() if len(row) > 4 else ""

            if not (total_shares_a or total_shares_c):
                continue

            # 从"主要财务指标"文本提取单位净值，估算 AUM
            estimated_aum = ""
            nav_results = tool_service.search_document(doc_id, "基金份额净值")
            for hit in nav_results:
                if isinstance(hit, ToolFailure) or not hit.section_ref:
                    continue
                section = tool_service.read_section(doc_id, hit.section_ref)
                if not hasattr(section, "text"):
                    continue
                text = section.text
                nav_pattern = re.compile(r"(?:混合[AC]|A类|C类).*?基金份额净值\s*(?:为)?\s*([\d.]+)\s*元")
                nav_matches = nav_pattern.findall(text)
                shares_list = [total_shares_a, total_shares_c]
                total_aum = 0.0
                for i, nav_str in enumerate(nav_matches[:2]):
                    try:
                        nav = float(nav_str)
                        shares_str = shares_list[i] if i < len(shares_list) and shares_list[i] else "0"
                        shares = float(shares_str.replace(",", ""))
                        total_aum += nav * shares
                    except (ValueError, IndexError):
                        continue
                if total_aum > 0:
                    if total_aum >= 1e8:
                        estimated_aum = f"{total_aum / 1e8:.2f}亿元"
                    elif total_aum >= 1e4:
                        estimated_aum = f"{total_aum / 1e4:.2f}万元"
                    else:
                        estimated_aum = f"{total_aum:.2f}元"
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
            )
            chapters.append(ReportChapter(
                chapter_id=chapter_id,
                title=title,
                content=content,
                data_sources=data_sources,
            ))

        return chapters

    def _generate_ch2_performance(self, performance: dict[int, dict[str, str]]) -> str:
        """生成业绩分析章节。"""

        lines = ["## 业绩表现\n", "| 年份 | 净值增长率 | 基准收益率 | 超额收益 |", "|------|-----------|-----------|---------|"]
        for year in sorted(performance.keys()):
            p = performance[year]
            lines.append(f"| {year} | {p.get('nav_growth_rate', 'N/A')} | {p.get('benchmark_return_rate', 'N/A')} | {p.get('excess_return', 'N/A')} |")
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
    ) -> SignalJudgment:
        """计算确定性信号判断（6 指标评分模型，总分 135 归一化到 100）。

        参数:
            performance: 多年度业绩数据。
            fees: 多年度费率数据。
            holdings: 多年度持仓数据。
            fund_manager: 基金经理信息（可选）。
            scale_info: 规模信息（可选）。
            report_year: 报告年份。

        返回:
            SignalJudgment，包含信号、归一化分数、指标明细和警告。
        """
        scored = [
            score_excess_returns(performance),
            score_fee_rate(fees, report_year),
            score_style_drift(holdings),
            score_scale_risk(scale_info),
            score_manager_change(fund_manager, report_year),
            score_concentration(holdings),
        ]

        indicators = tuple(to_signal_indicator(s) for s in scored)
        warnings = tuple(
            f"{s.name}：{s.detail}" for s in scored if not s.calculable
        )
        calculable_count = sum(1 for s in scored if s.calculable)

        total_score = sum(s.score for s in scored)
        total_max = sum(s.max_score for s in scored)
        normalized = round(total_score / total_max * 100) if total_max > 0 else 0

        if calculable_count < 3:
            signal = "🟡 需要关注"
            warnings = (f"数据不足（可计算指标 {calculable_count}/6 < 3），默认 🟡 需要关注",) + warnings
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
            data_completeness=calculable_count / 6,
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
    ) -> tuple[RiskChecklistItem, ...]:
        """计算 6 项风险清单检查。

        参数:
            fees: 多年度费率数据。
            holdings: 多年度持仓数据。
            fund_manager: 基金经理信息（可选）。
            scale_info: 规模信息（可选）。
            report_year: 报告年份。

        返回:
            6 项 RiskChecklistItem 的 tuple。
        """
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

        items = []
        for s, name in zip(scored, risk_names):
            if s is None:
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

        返回:
            模板生成的 Markdown 文本。
        """

        # Ch1-Ch6: 统一调用 generate_data_table() 获取结构化数据表
        if 1 <= chapter_id <= 6:
            from fund_agent.service.chapter_generator import generate_data_table
            st = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name) if chapter_id == 6 else None
            data_table = generate_data_table(
                chapter_id, fund_code, fund_name, report_year,
                performance, holdings, allocation, fees,
                fund_manager, scale_info, evidence,
                stress_test=st, signal_judgment=signal_judgment,
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
                f"- **最新净值增长率**：{latest.get('nav_growth_rate', 'N/A')}\n\n"
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

        output_dir = work_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"{report.fund_code}-{report.report_year}-analysis"
        output_path = output_dir / f"{base_name}.md"
        sidecar_path = output_dir / f"{base_name}.meta.json"

        lines = [f"# {report.fund_name}（{report.fund_code}）{report.report_year} 年度分析报告\n"]
        lines.append("**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n")

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
        """使用 pandoc 导出 PDF。

        返回:
            (输出路径, 警告信息或 None)
        """

        pdf_path = md_path.replace(".md", ".pdf")
        try:
            subprocess.run(
                ["pandoc", md_path, "-o", pdf_path, "--pdf-engine=xelatex"],
                check=True,
                capture_output=True,
            )
            return pdf_path, None
        except FileNotFoundError:
            return md_path, "pandoc 未安装，已回退为 Markdown 格式"
        except subprocess.CalledProcessError:
            return md_path, "PDF 导出失败，已回退为 Markdown 格式"

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
                    if any(title not in matched_titles for title in disclosure_titles):
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
                    agent_result=_aggregate_agent_results(tuple(matched_results)),
                    routing_trace=tuple(attempts),
                )
            if matched_results:
                return _QueryRouteRun(
                    agent_result=_target_not_found_result(_aggregate_agent_results(tuple(matched_results))),
                    routing_trace=tuple(attempts),
                )

        if last_not_found is None:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 未生成候选 query")
        return _QueryRouteRun(agent_result=last_not_found, routing_trace=tuple(attempts))


def _default_host_factory(tool_service: FundDocumentToolService) -> MinimalHost:
    """按默认 deterministic Agent 装配最小 Host。"""

    return MinimalHost(MinimalFundDocumentAgent(tool_service))


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
) -> MultiYearAnnualPerformanceSeries:
    """构造单一 share class 的 10I series DTO。"""

    rows = tuple(rows_by_year[year] for year in requested_years if year in rows_by_year)
    covered_years = tuple(row.year for row in rows)
    missing_years = tuple(year for year in requested_years if year not in rows_by_year)
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
        if query in contract.aliases:
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
        matches = tuple(spec.pattern.finditer(segment))
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

    titles = ("基金管理费", "基金托管费", "销售服务费")
    positions: list[tuple[str, int]] = []
    search_start = 0
    for title in titles:
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
    """按 10B 聚合顺序为三段费率披露匹配 section citation。"""

    titles = ("基金管理费", "基金托管费", "销售服务费")
    section_citations = tuple(
        citation for citation in citations if citation.locator.locator_kind is LocatorKind.SECTION
    )
    if len(section_citations) < len(titles):
        raise DocumentToolError(FailureCode.NOT_FOUND, "fee_rates citation 不完整")
    return dict(zip(titles, section_citations, strict=False))


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
        row = _performance_past_year_row(table.rows)
        if row is None:
            continue
        indexes = _performance_column_indexes(table.rows, specs)
        if indexes is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 目标列缺失")
        share_scope = share_scopes.get(table.table_ref)
        if share_scope is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")
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
    if not header_tables:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 目标列缺失")

    share_scopes = _annual_performance_table_share_scopes(
        header_tables,
        section_text_by_ref=section_text_by_ref,
        requested_share_class=requested_share_class,
    )
    requested_scope = _normalize_share_class_scope(requested_share_class) if requested_share_class else None
    if requested_share_class and requested_scope is None:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 份额类别无法唯一识别")

    fields: list[AnnualPerformanceExtraction] = []
    for table in header_tables:
        share_scope = share_scopes.get(table.table_ref)
        if share_scope is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 份额类别无法唯一识别")
        if requested_scope is not None and share_scope != requested_scope:
            continue
        row = _performance_past_year_row(table.rows)
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

    if not fields:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance 过去一年完整字段缺失")
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
    if not header_tables:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual excess return ①－③ 列缺失")

    share_scopes = _annual_excess_return_table_share_scopes(
        header_tables,
        section_text_by_ref=section_text_by_ref,
        requested_share_class=requested_share_class,
    )
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
        row = _performance_past_year_row(table.rows)
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

    if not fields:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual excess return 过去一年 ①－③ 字段缺失")
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
    """从年度业绩表的受控行标签识别 A/C 份额类别。"""

    normalized_rows = tuple(_normalize_disclosure_text(cell) for row in rows for cell in row)
    if any("自基金转型起至今" in cell for cell in normalized_rows):
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
        return inferred


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
    """返回命中 10F 固定 title family 的 section refs。"""

    title_lines = _target_title_lines(result.answer)
    if not any(_ANNUAL_PERFORMANCE_TITLE_FAMILY in line for line in title_lines):
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
    refs: list[str] = []
    for table_ref in cited_table_refs:
        table = tool_service.read_table(document_id, table_ref, max_rows=_PERFORMANCE_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            raise DocumentToolError(table.code, table.message)
        # 回退模式下跳过 section 校验，仅校验列签名
        if strict_table_refs and table.section_ref not in source_section_refs:
            continue
        if _performance_column_indexes(table.rows, specs) is None:
            continue
        refs.append(table.table_ref)

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
    return all(keyword in normalized for keyword in spec.column_keywords) and not any(
        keyword in normalized for keyword in spec.excluded_keywords
    )


def _performance_past_year_row(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...] | None:
    """返回唯一 past_1_year 行；缺失或多行均按 not_found 处理。"""

    matches = tuple(row for row in rows[1:] if row and _normalize_disclosure_text(row[0]) == _PERFORMANCE_RETURN_PERIOD_TEXT)
    if len(matches) > 1:
        raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 过去一年行无法唯一识别")
    return matches[0] if matches else None


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
            raise DocumentToolError(FailureCode.NOT_FOUND, "performance_returns 份额类别无法唯一识别")
        for table, label in zip(section_tables, labels, strict=True):
            scopes[table.table_ref] = label
    return scopes


def _share_class_labels_from_text(text: str) -> tuple[str, ...]:
    """从安全 section 文本中按出现顺序提取可控 A/C 份额类别标签。"""

    labels: list[str] = []
    for line in text.splitlines():
        normalized = _normalize_disclosure_text(line)
        if not normalized:
            continue
        found: str | None = None
        for scope in _SHARE_CLASS_SCOPES:
            if f"{scope}类" in normalized or normalized.endswith(f"混合{scope}"):
                found = scope
                break
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

        column_indexes = _holdings_column_indexes(table.rows)
        if column_indexes is None:
            continue

        primary_table_ref = table_ref
        primary_section_ref = table.section_ref
        primary_page = table.locator.page_no

        data_rows = table.rows[1:]
        for row in data_rows:
            if len(row) <= max(column_indexes.values()):
                continue
            stock_code = row[column_indexes["stock_code"]].strip()
            stock_name = row[column_indexes["stock_name"]].strip()
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


def _holdings_column_indexes(rows: tuple[tuple[str, ...], ...]) -> dict[str, int] | None:
    """识别持仓表的列索引映射。"""

    if not rows:
        return None
    header = rows[0]
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header):
        cell_clean = cell.strip().replace(" ", "")
        if "股票代码" in cell_clean:
            mapping["stock_code"] = idx
        elif "股票名称" in cell_clean:
            mapping["stock_name"] = idx
        elif "数量" in cell_clean:
            mapping["quantity"] = idx
        elif "公允价值" in cell_clean:
            mapping["fair_value"] = idx
        elif "占基金资产净值比例" in cell_clean or "占比" in cell_clean:
            mapping["percentage"] = idx

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


def _extract_fee_rates_from_agent_result(
    *,
    result: AgentRunResult,
) -> tuple[FeeRateItem, ...]:
    """从 Agent 结果中抽取费率信息。"""

    fees: list[FeeRateItem] = []
    answer = result.answer
    fee_patterns = [
        (r"基金管理费[^\d]*?(\d+\.?\d*%)", "基金管理费"),
        (r"基金托管费[^\d]*?(\d+\.?\d*%)", "基金托管费"),
        (r"销售服务费[^\d]*?A类[^\d]*?不收取", "销售服务费A类"),
        (r"销售服务费[^\d]*?A类[^\d]*?(\d+\.?\d*%)", "销售服务费A类"),
        (r"C类[^\d]*?销售服务费[^\d]*?(\d+\.?\d*%)", "销售服务费C类"),
        (r"销售服务费[^\d]*?C类[^\d]*?(\d+\.?\d*%)", "销售服务费C类"),
    ]

    for pattern, name in fee_patterns:
        match = re.search(pattern, answer)
        if match:
            rate = match.group(1) if match.lastindex else "不收取"
            if not any(f.fee_name == name for f in fees):
                fees.append(FeeRateItem(fee_name=name, rate=rate))

    if not fees:
        management_match = re.search(r"管理费[^\d]*?(\d+\.?\d*%)", answer)
        custodian_match = re.search(r"托管费[^\d]*?(\d+\.?\d*%)", answer)

        if management_match:
            fees.append(FeeRateItem(fee_name="基金管理费", rate=management_match.group(1)))
        if custodian_match:
            fees.append(FeeRateItem(fee_name="基金托管费", rate=custodian_match.group(1)))

        if "不收取" in answer and "销售服务费" in answer:
            fees.append(FeeRateItem(fee_name="销售服务费A类", rate="不收取"))

        sales_c_match = re.search(r"C[^\d]*?(\d+\.?\d*%)[^\d]*?销售服务费", answer)
        if sales_c_match:
            fees.append(FeeRateItem(fee_name="销售服务费C类", rate=sales_c_match.group(1)))

    return tuple(fees)


# ── Slice 16B 压力测试 ──────────────────────────────────────────────

STRESS_THRESHOLDS: dict[str, tuple[float, float, float]] = {
    "index_fund": (-0.30, -0.50, -0.70),
    "bond_fund": (-0.05, -0.10, -0.20),
    "active_fund": (-0.25, -0.45, -0.65),
}


def infer_fund_type(fund_name: str) -> tuple[str, bool]:
    """基于基金名称关键词推断基金类型。

    参数:
        fund_name: 基金名称。

    返回:
        (fund_type, inferred) — fund_type 为 index_fund/bond_fund/active_fund，
        inferred 为 True 表示由关键词匹配推断。
    """
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
