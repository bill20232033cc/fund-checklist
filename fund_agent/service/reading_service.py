"""基金年报阅读 use case Service 边界。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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

PDF_BLOB_DIRNAME = "pdf_blobs"
DOCLING_JSON_DIRNAME = "docling_json"

ConverterFactory = Callable[[Path], DoclingConverter]
HostFactory = Callable[[FundDocumentToolService], MinimalHost]

_MAX_QUERY_CANDIDATES = 4
QueryRouteResultKind = Literal["success", "failure"]
_ROUTE_RESULT_SUCCESS: QueryRouteResultKind = "success"
_ROUTE_RESULT_FAILURE: QueryRouteResultKind = "failure"
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


@dataclass(frozen=True)
class _DisclosureLocatorContract:
    """Service 内部披露定位 registry contract。"""

    profile_name: str
    aliases: tuple[str, ...]
    candidate_queries: tuple[str, ...]
    acceptable_title_family: tuple[str, ...]
    requires_table_citation: bool
    extraction_allowed: bool


@dataclass(frozen=True)
class QueryRouteAttempt:
    """Service query routing 单次尝试的审计事实。

    参数:
        query: 本次传给 Host/Agent 的原始 candidate query。
        profile_name: 命中的受控 profile 名称；非受控 query 为 None。
        result_kind: 本次尝试结果，只允许 success 或 failure。
        failure_code: 失败时的稳定 failure code；成功时必须为 None。

    返回:
        不可变审计 DTO，仅属于 Service-level metadata。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    query: str
    profile_name: str | None
    result_kind: QueryRouteResultKind
    failure_code: FailureCode | None = None


@dataclass(frozen=True)
class FeeRateExtraction:
    """Service 层 fee_rates 受控字段抽取 DTO。

    参数:
        field_name: 受控字段名，仅覆盖 10C 裁决的三类费率字段。
        decimal_percent_text: 披露文本值，百分数保持 "1.20%" 形式；A 类不收费保持
            "不收取"，不改写为计算值。
        period: 费率期间，10C 固定为 year。
        share_class_scope: 份额类别适用范围；管理费/托管费为 all_share_classes，
            销售服务费区分 A / C。
        raw_text: 支撑该字段的安全原文片段，来自 10B 定位后的 Agent answer。
        citation: 支撑该字段的年报 citation。

    返回:
        不可变字段抽取结果。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    field_name: str
    decimal_percent_text: str
    period: str
    share_class_scope: str
    raw_text: str
    citation: Citation


@dataclass(frozen=True)
class ExtractFeeRatesResult:
    """fee_rates 字段抽取 use case 的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        fields: 成功抽取的受控字段 DTO；失败时为空。
        failure: 稳定失败分类；成功时为 None。

    返回:
        可供 Service 调用方消费的结构化抽取结果。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    fields: tuple[FeeRateExtraction, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class PerformanceReturnExtraction:
    """Service 层 performance_returns 受控字段抽取 DTO。

    参数:
        field_name: 受控字段名，仅允许 nav_growth_rate 或 benchmark_return_rate。
        decimal_percent_text: 披露文本值，保持 "17.32%" 百分号格式。
        period: 期间，10D 首批固定为 past_1_year。
        share_class_scope: 表格上下文可唯一识别的份额类别。
        raw_text: 支撑该字段的安全表格行/单元格原文片段。
        citation: 支撑该字段的实际 table citation。

    返回:
        不可变字段抽取结果。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    field_name: str
    decimal_percent_text: str
    period: str
    share_class_scope: str
    raw_text: str
    citation: Citation


@dataclass(frozen=True)
class ExtractPerformanceReturnsResult:
    """performance_returns 字段抽取 use case 的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        fields: 成功抽取的受控字段 DTO；失败时为空。
        failure: 稳定失败分类；成功时为 None。

    返回:
        可供 Service 调用方消费的结构化抽取结果。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    fields: tuple[PerformanceReturnExtraction, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class AnnualPerformanceExtraction:
    """Service 层年度业绩表格受控字段抽取 DTO。

    参数:
        field_name: 受控字段名，仅允许 annual_nav_growth_rate 或
            annual_benchmark_return_rate。
        decimal_percent_text: 披露文本值，保持 "17.32%" 百分号格式。
        report_year: 请求指定的报告自然年度。
        source_period_label: 表格原文期间标签，10F 固定为 过去一年。
        share_class_scope: 表格上下文可唯一识别的份额类别。
        raw_text: 支撑该字段的安全表格行/单元格原文片段，必须保留 过去一年。
        citation: 支撑该字段的实际 table citation。

    返回:
        不可变字段抽取结果。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    field_name: str
    decimal_percent_text: str
    report_year: int
    source_period_label: str
    share_class_scope: str
    raw_text: str
    citation: Citation


@dataclass(frozen=True)
class ExtractAnnualPerformanceResult:
    """年度业绩字段抽取 use case 的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        fields: 成功抽取的受控字段 DTO；失败时为空。
        failure: 稳定失败分类；成功时为 None。

    返回:
        可供 Service 调用方消费的结构化抽取结果。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    fields: tuple[AnnualPerformanceExtraction, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class AnnualExcessReturnExtraction:
    """Service 层年度超额收益显式披露字段抽取 DTO。

    参数:
        field_name: 受控字段名，10G 固定为 annual_excess_return。
        decimal_percent_text: 年报表格 ①－③ 列原文百分号值，不转小数、不计算。
        report_year: 请求指定的报告自然年度。
        source_period_label: 表格原文期间标签，10G 固定为 过去一年。
        share_class_scope: 表格上下文可唯一识别的份额类别。
        source_column_label: 年报显式披露列标签，10G 固定为 ①－③。
        raw_text: 支撑该字段的安全表格行/单元格原文片段，必须保留 过去一年。
        citation: 支撑该字段的实际 table citation。

    返回:
        不可变字段抽取结果。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    field_name: str
    decimal_percent_text: str
    report_year: int
    source_period_label: str
    share_class_scope: str
    source_column_label: str
    raw_text: str
    citation: Citation


@dataclass(frozen=True)
class ExtractAnnualExcessReturnResult:
    """年度超额收益字段抽取 use case 的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        fields: 成功抽取的 annual_excess_return DTO；失败时为空。
        failure: 稳定失败分类；成功时为 None。

    返回:
        可供 Service 调用方消费的结构化抽取结果。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    fields: tuple[AnnualExcessReturnExtraction, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class AnnualReportDocument:
    """10I 多年度聚合的显式年报输入。

    参数:
        year: 调用方显式绑定的报告自然年度，不从 document_id 字符串推断。
        document_id: 已导入 completed annual report 的 public document_id。

    返回:
        不可变输入 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    year: int
    document_id: str


@dataclass(frozen=True)
class AnnualPerformanceFieldCitation:
    """多年度年度业绩 row 中单字段 citation 绑定。

    参数:
        field_name: 受控字段名。
        citation: 该字段来自原年度年报表格的 table locator citation。

    返回:
        不可变字段 citation DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    field_name: str
    citation: Citation


@dataclass(frozen=True)
class MultiYearAnnualPerformanceRow:
    """10I 多年度年度业绩单年 row。

    参数:
        year: 自然年度。
        annual_nav_growth_rate: 年报披露的年度份额净值增长率。
        annual_benchmark_return_rate: 年报披露的同期业绩比较基准收益率。
        annual_excess_return: 年报 ①－③ 显式披露的年度超额收益。
        citations: 三个字段各自的 table locator citation。

    返回:
        不可变年度 row DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    year: int
    annual_nav_growth_rate: str
    annual_benchmark_return_rate: str
    annual_excess_return: str
    citations: tuple[AnnualPerformanceFieldCitation, ...]


@dataclass(frozen=True)
class MultiYearAnnualPerformanceSeries:
    """10I 多年度年度业绩 bounded coverage DTO。

    参数:
        fund_code: 基金代码。
        requested_years: 规范化后的升序请求年度。
        covered_years: 该 share class 字段完整的年度。
        missing_years: 该 share class 缺失或字段不完整的年度。
        coverage_status: complete 或 partial；partial 是成功 metadata。
        coverage_count: 完整年度数量。
        minimum_required_count: 最小成功覆盖年度数，10I 固定为 3。
        share_class_scope: 本 series 对应的份额类别。
        rows: 按年度升序排列的年度业绩 rows。
        citations: 所有 row 的字段级 table locator citations。

    返回:
        不可变多年度 series DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    fund_code: str
    requested_years: tuple[int, ...]
    covered_years: tuple[int, ...]
    missing_years: tuple[int, ...]
    coverage_status: str
    coverage_count: int
    minimum_required_count: int
    share_class_scope: str
    rows: tuple[MultiYearAnnualPerformanceRow, ...]
    citations: tuple[AnnualPerformanceFieldCitation, ...]


@dataclass(frozen=True)
class AggregateMultiYearAnnualPerformanceRequest:
    """10I 多年度年度业绩聚合请求。

    参数:
        fund_code: 请求基金代码，用于校验显式 document_id 指向的 report identity。
        requested_years: 请求年度列表；Service 规范化为升序，长度必须为 3-5 且唯一。
        annual_report_documents: 调用方显式提供的 year/document_id 映射。
        work_dir: 现有受控 repository 工作目录，只按显式 document_id 加载。
        share_class: 可选份额类别；指定时只评估该 share class。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    fund_code: str
    requested_years: tuple[int, ...] | list[int]
    annual_report_documents: tuple[AnnualReportDocument, ...] | list[AnnualReportDocument]
    work_dir: Path
    share_class: str | None = None


@dataclass(frozen=True)
class AggregateMultiYearAnnualPerformanceResult:
    """10I 多年度年度业绩聚合结果。

    参数:
        series: 成功覆盖 3-5 年的 share class series；失败时为空。
        failure: 稳定失败分类；成功时为 None。

    返回:
        可供 Service 调用方消费的 bounded coverage 结果。

    异常:
        本模型不抛出业务异常。
    """

    series: tuple[MultiYearAnnualPerformanceSeries, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class HoldingExtraction:
    """单条持仓记录。

    参数:
        rank: 排名（从 1 开始）。
        stock_code: 股票代码。
        stock_name: 股票名称。
        quantity: 持有数量（股）。
        fair_value: 公允价值（元）。
        percentage: 占基金资产净值比例（%）。

    返回:
        不可变持仓 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    rank: int
    stock_code: str
    stock_name: str
    quantity: str
    fair_value: str
    percentage: str


@dataclass(frozen=True)
class AnnualHoldingsResult:
    """单年度持仓抽取结果。

    参数:
        document_id: 来源文档 ID。
        year: 报告年份。
        holdings: Top 10 持仓记录。
        citation: 表格 citation。

    返回:
        不可变年度持仓结果。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    document_id: str
    year: int
    holdings: tuple[HoldingExtraction, ...]
    citation: Citation | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class MultiYearHoldingsSeries:
    """多年度持仓 series DTO。

    参数:
        fund_code: 基金代码。
        requested_years: 请求年度列表。
        covered_years: 成功抽取的年度。
        missing_years: 未找到或抽取失败的年度。
        annual_holdings: 按年度升序排列的年度持仓结果。

    返回:
        不可变多年度持仓 series。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    fund_code: str
    requested_years: tuple[int, ...]
    covered_years: tuple[int, ...]
    missing_years: tuple[int, ...]
    annual_holdings: tuple[AnnualHoldingsResult, ...]


@dataclass(frozen=True)
class ExtractHoldingsRequest:
    """持仓多年度聚合请求。

    参数:
        fund_code: 基金代码。
        requested_years: 请求年度列表。
        annual_report_documents: 显式提供的 year/document_id 映射。
        work_dir: 受控工作目录。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    fund_code: str
    requested_years: tuple[int, ...] | list[int]
    annual_report_documents: tuple[AnnualReportDocument, ...] | list[AnnualReportDocument]
    work_dir: Path


@dataclass(frozen=True)
class ExtractHoldingsResult:
    """持仓多年度聚合结果。

    参数:
        series: 成功抽取的多年度持仓 series；失败时为 None。
        failure: 稳定失败分类；成功时为 None。

    返回:
        可供 CLI 消费的结果。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    series: MultiYearHoldingsSeries | None = None
    failure: ToolFailure | None = None


_HOLDINGS_TOP_N = 10
_HOLDINGS_QUERY = "股票投资明细"
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
    ) -> AnnualHoldingsResult:
        """从单年度年报中抽取前十大持仓表。

        参数:
            document_id: 文档 ID。
            store: 已加载的 DoclingDocumentStore。
            report_year: 报告年份。

        返回:
            AnnualHoldingsResult；失败时 failure 非空。
        """

        tool_service = FundDocumentToolService({document_id: store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=_HOLDINGS_QUERY,
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
            if citation.locator.locator_kind.value == "table":
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
        if table.section_ref not in source_section_refs:
            continue
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
        if table.section_ref not in source_section_refs:
            continue
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

    cited_table_refs = tuple(
        dict.fromkeys(
            citation.locator.table_ref
            for citation in result.citations
            if citation.locator.locator_kind is LocatorKind.TABLE
            and citation.locator.section_ref in source_section_refs
            and citation.locator.table_ref
        )
    )
    if not cited_table_refs:
        raise DocumentToolError(FailureCode.NOT_FOUND, "annual performance table citation 缺失")
    refs: list[str] = []
    for table_ref in cited_table_refs:
        table = tool_service.read_table(document_id, table_ref, max_rows=_PERFORMANCE_TABLE_MAX_ROWS)
        if isinstance(table, ToolFailure):
            raise DocumentToolError(table.code, table.message)
        if table.section_ref not in source_section_refs:
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
        continuation_holdings = _extract_holdings_continuations(
            document_id=document_id,
            tool_service=tool_service,
            primary_section_ref=primary_section_ref,
            primary_page=primary_page,
            primary_table_ref=primary_table_ref,
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
                quantity = row[column_indexes.get("quantity", 0)].strip() if "quantity" in column_indexes else ""
                fair_value = row[column_indexes.get("fair_value", 0)].strip() if "fair_value" in column_indexes else ""
                percentage = row[column_indexes["percentage"]].strip()
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
        cell_clean = cell.strip()
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
