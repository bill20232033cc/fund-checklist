"""基金年报阅读 use case Service 边界。"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
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


@dataclass(frozen=True)
class AssetAllocationItem:
    """单条资产配置记录。

    参数:
        category: 资产类别（如银行存款、股票投资、债券投资等）。
        amount: 金额。
        percentage_of_net: 占基金资产净值比例。
        percentage_of_total: 占总资产比例（可选）。

    返回:
        不可变资产配置 DTO。
    """

    category: str
    amount: str
    percentage_of_net: str
    percentage_of_total: str = ""


@dataclass(frozen=True)
class IndustryAllocationItem:
    """单条行业配置记录。

    参数:
        industry: 行业类别。
        amount: 公允价值。
        percentage: 占基金资产净值比例。

    返回:
        不可变行业配置 DTO。
    """

    industry: str
    amount: str
    percentage: str


@dataclass(frozen=True)
class FeeRateItem:
    """单条费率记录。

    参数:
        fee_name: 费率名称（如基金管理费、基金托管费、销售服务费A类等）。
        rate: 年费率。

    返回:
        不可变费率 DTO。
    """

    fee_name: str
    rate: str


@dataclass(frozen=True)
class FundManagerInfo:
    """基金经理信息。

    参数:
        name: 基金经理姓名。
        tenure_start: 任职日期文本。
        years_of_service: 证券从业年限文本。
        investment_strategy: 投资策略描述（从§4.4.1提取）。
        holds_fund: 基金经理持有本基金区间（如"10~50万份"）。

    返回:
        不可变基金经理信息 DTO。
    """

    name: str
    tenure_start: str
    years_of_service: str
    investment_strategy: str
    holds_fund: str


@dataclass(frozen=True)
class ScaleInfo:
    """基金规模信息。

    参数:
        total_shares_a: A类份额总数。
        total_shares_c: C类份额总数。
        individual_investor_ratio: 个人投资者持有比例。
        management_holds: 管理人从业人员持有比例。
        estimated_aum: 估算资产净值（如"2.99亿元"）。

    返回:
        不可变规模信息 DTO。
    """

    total_shares_a: str
    total_shares_c: str
    individual_investor_ratio: str
    management_holds: str
    estimated_aum: str = ""


@dataclass(frozen=True)
class AnnualAllocationResult:
    """单年度资产配置抽取结果。

    参数:
        document_id: 来源文档 ID。
        year: 报告年份。
        asset_allocation: 资产配置列表。
        industry_allocation: 行业配置列表。
        citation: 表格 citation。
        failure: 失败分类。
    """

    document_id: str
    year: int
    asset_allocation: tuple[AssetAllocationItem, ...]
    industry_allocation: tuple[IndustryAllocationItem, ...]
    citation: Citation | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class AnnualFeeResult:
    """单年度费率抽取结果。

    参数:
        document_id: 来源文档 ID。
        year: 报告年份。
        fees: 费率列表。
        citation: citation。
        failure: 失败分类。
    """

    document_id: str
    year: int
    fees: tuple[FeeRateItem, ...]
    citation: Citation | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class MultiYearAllocationSeries:
    """多年度资产配置 series DTO。

    参数:
        fund_code: 基金代码。
        requested_years: 请求年度列表。
        covered_years: 成功抽取的年度。
        missing_years: 未找到或抽取失败的年度。
        annual_allocations: 按年度升序排列的年度资产配置结果。
    """

    fund_code: str
    requested_years: tuple[int, ...]
    covered_years: tuple[int, ...]
    missing_years: tuple[int, ...]
    annual_allocations: tuple[AnnualAllocationResult, ...]


@dataclass(frozen=True)
class MultiYearFeeSeries:
    """多年度费率 series DTO。

    参数:
        fund_code: 基金代码。
        requested_years: 请求年度列表。
        covered_years: 成功抽取的年度。
        missing_years: 未找到或抽取失败的年度。
        annual_fees: 按年度升序排列的年度费率结果。
    """

    fund_code: str
    requested_years: tuple[int, ...]
    covered_years: tuple[int, ...]
    missing_years: tuple[int, ...]
    annual_fees: tuple[AnnualFeeResult, ...]


@dataclass(frozen=True)
class ExtractAllocationRequest:
    """资产配置多年度聚合请求。"""

    fund_code: str
    requested_years: tuple[int, ...] | list[int]
    annual_report_documents: tuple[AnnualReportDocument, ...] | list[AnnualReportDocument]
    work_dir: Path


@dataclass(frozen=True)
class ExtractAllocationResult:
    """资产配置多年度聚合结果。"""

    series: MultiYearAllocationSeries | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class ExtractFeeRatesMultiYearRequest:
    """费率多年度聚合请求。"""

    fund_code: str
    requested_years: tuple[int, ...] | list[int]
    annual_report_documents: tuple[AnnualReportDocument, ...] | list[AnnualReportDocument]
    work_dir: Path


@dataclass(frozen=True)
class ExtractFeeRatesMultiYearResult:
    """费率多年度聚合结果。"""

    series: MultiYearFeeSeries | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class DisclosureAuditItem:
    """单个披露项审计结果。

    参数:
        name: 披露项名称（如 holdings、fee_rates 等）。
        status: 状态（complete / partial / missing）。
        chapter: 章节是否存在。
        table: 表格是否存在（无表格的披露项为 None）。
        fields: 存在的字段列表。
        message: 补充说明（如缺失原因）。

    返回:
        不可变审计结果 DTO。
    """

    name: str
    status: str
    chapter: bool
    table: bool | None = None
    fields: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class DisclosureAuditRequest:
    """披露完整性审计请求。

    参数:
        fund_code: 基金代码。
        year: 审计年份。
        work_dir: 受控工作目录。

    返回:
        不可变请求 DTO。
    """

    fund_code: str
    year: int
    work_dir: Path


@dataclass(frozen=True)
class DisclosureAuditResult:
    """披露完整性审计结果。

    参数:
        fund_code: 基金代码。
        year: 审计年份。
        document_id: 审计的文档 ID。
        disclosures: 各披露项审计结果。
        summary: 汇总（complete / partial / missing 数量）。
        failure: 失败分类；成功时为 None。

    返回:
        不可变审计结果 DTO。
    """

    fund_code: str
    year: int
    document_id: str | None = None
    disclosures: tuple[DisclosureAuditItem, ...] = ()
    summary: dict[str, int] | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class DeepAuditItem:
    """深度审计单个披露项结果。

    参数:
        name: 披露项名称。
        status: 状态（pass / fail / warning）。
        completeness: 内容完整性描述。
        consistency: 数据一致性描述。
        citation_text: 引用的原文片段。
        raw_answer: 原始内容片段。

    返回:
        不可变深度审计结果 DTO。
    """

    name: str
    status: str
    completeness: str = ""
    consistency: str = ""
    citation_text: str = ""
    raw_answer: str = ""


@dataclass(frozen=True)
class DeepAuditRequest:
    """深度审计请求。

    参数:
        fund_code: 基金代码。
        year: 审计年份。
        work_dir: 受控工作目录。

    返回:
        不可变请求 DTO。
    """

    fund_code: str
    year: int
    work_dir: Path


@dataclass(frozen=True)
class DeepAuditResult:
    """深度审计结果。

    参数:
        fund_code: 基金代码。
        year: 审计年份。
        document_id: 审计的文档 ID。
        audit_results: 各披露项审计结果。
        summary: 汇总（pass / fail / warning 数量）。
        failure: 失败分类；成功时为 None。

    返回:
        不可变深度审计结果 DTO。
    """

    fund_code: str
    year: int
    document_id: str | None = None
    audit_results: tuple[DeepAuditItem, ...] = ()
    summary: dict[str, int] | None = None
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class ReportChapter:
    """报告单章节。

    参数:
        chapter_id: 章节编号（0-7）。
        title: 章节标题。
        content: 章节内容（Markdown 格式）。
        data_sources: 引用的数据来源列表。

    返回:
        不可变章节 DTO。
    """

    chapter_id: int
    title: str
    content: str
    data_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class FundReport:
    """基金分析报告。

    参数:
        fund_code: 基金代码。
        fund_name: 基金名称。
        report_year: 报告年份。
        chapters: 8 章内容。
        metadata: 报告元数据（生成时间、数据来源等）。

    返回:
        不可变报告 DTO。
    """

    fund_code: str
    fund_name: str
    report_year: int
    chapters: tuple[ReportChapter, ...]
    metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class ChapterEvidence:
    """章节证据来源汇总。

    参数:
        holdings_citations: 持仓数据 citation（按年份）。
        fee_citations: 费率数据 citation（按年份）。
        allocation_citations: 资产配置 citation（按年份）。
        performance_citations: 业绩数据 citation（按年份）。
        fund_manager_citation: 基金经理信息 citation。
        scale_citation: 规模信息 citation。

    返回:
        不可变证据来源 DTO。
    """

    holdings_citations: dict[int, Citation | None] = field(default_factory=dict)
    fee_citations: dict[int, Citation | None] = field(default_factory=dict)
    allocation_citations: dict[int, Citation | None] = field(default_factory=dict)
    performance_citations: dict[int, Citation | None] = field(default_factory=dict)
    fund_manager_citation: Citation | None = None
    scale_citation: Citation | None = None


@dataclass(frozen=True)
class GenerateReportRequest:
    """报告生成请求。

    参数:
        fund_code: 基金代码。
        fund_name: 基金名称。
        report_year: 报告年份。
        years: 需要的年度数据列表（默认 5 年）。
        work_dir: 受控工作目录。
        output_format: 输出格式（json / markdown / pdf）。

    返回:
        不可变请求 DTO。
    """

    fund_code: str
    fund_name: str
    report_year: int
    years: tuple[int, ...] | list[int] = ()
    work_dir: Path = Path(".fund_checklist")
    output_format: str = "json"


@dataclass(frozen=True)
class GenerateReportResult:
    """报告生成结果。

    参数:
        report: 生成的报告。
        output_path: 输出文件路径（Markdown/PDF 时非空）。
        warnings: 警告信息列表。
        failure: 失败分类；成功时为 None。

    返回:
        不可变结果 DTO。
    """

    report: FundReport | None = None
    output_path: str | None = None
    warnings: tuple[str, ...] = ()
    failure: ToolFailure | None = None


_LLM_CHAPTER_SYSTEM_PROMPT = (
    "你是一位专业的基金分析师。请基于提供的数据表格，撰写定性分析评论。\n\n"
    "【输出格式 - 必须严格遵守】\n"
    "1. 你的输出是纯定性分析文本，禁止包含任何数字、百分比、金额\n"
    "2. 数据表格已由系统生成，你只需要写分析评论\n"
    "3. 用'据上表''数据显示''从趋势看'等方式引用数据，不要重复数字\n"
    "4. 禁止输出投资建议（如'买入''卖出''推荐'）\n"
    "5. 禁止预测未来收益或市场走势\n"
    "6. 使用 Markdown 格式，语言简洁专业\n\n"
    "违反以上约束的输出将被拒绝。"
)

_LLM_ANALYSIS_PROMPTS: dict[int, str] = {
    0: (
        "请基于上述关键指标数据，写一段「投资要点概览」分析。要求：\n"
        "- 用一句话定义这是什么基金\n"
        "- 给出极简基金简介（类型、经理、规模中最必要的信息）\n"
        "- 回答当前综合评估结论：表现优异、表现平稳还是需要关注\n"
        "- 回答当前最值得盯住的变量是什么\n"
        "- 回答当前最大的风险是什么（只保留1个）\n"
        "- 回答下一步最小验证问题是什么（只写1个）\n"
        "- 不要包含任何数字"
    ),
    1: (
        "请基于上述基本信息和基金经理投资策略，写一段「产品定义」分析。要求：\n"
        "- 用最低认知负担定义这只基金到底是什么产品\n"
        "- 说明投资目标和投资策略\n"
        "- 说明看这类基金时通常最先要看什么\n"
        "- 不要包含任何数字"
    ),
    2: (
        "请基于上述业绩数据和成本数据，写一段「R=A+B-C 收益归因」分析。要求：\n"
        "- 分析超额收益(A=R-B)的趋势：是结构性的还是阶段性的\n"
        "- 判断超额收益是否为正且稳定\n"
        "- 用定性描述（如'上升''下降''稳定''由正转负'），不要重复数字\n"
        "- 不要包含任何数字"
    ),
    3: (
        "请基于上述基金经理信息和持仓数据，写一段「基金经理画像」分析。要求：\n"
        "- 分析基金经理的投资策略与实际持仓行为是否一致\n"
        "- 分析持仓集中度趋势、行业分布特点\n"
        "- 分析基金经理是否持有本基金（利益一致性）\n"
        "- 不做性格或人品的主观评价\n"
        "- 不猜测基金经理的动机\n"
        "- 不要包含任何数字"
    ),
    4: "投资者实际收益数据暂不可用，详见原始年报。",
    5: (
        "请基于上述规模和配置数据，写一段「当前阶段与关键变化」分析。要求：\n"
        "- 判断当前阶段（建仓期/稳定期/膨胀期/萎缩期/转型期）\n"
        "- 指出过去一年最关键的1-3个变化\n"
        "- 这些变化是否影响原始投资假设\n"
        "- 不要包含任何数字"
    ),
    6: (
        "请基于上述风险相关数据，写一段「核心风险与否决项」分析。要求：\n"
        "- 指出最关键的风险或否决项（1-2个最致命的）\n"
        "- 说明为什么足以改变结论\n"
        "- 判断是否触发一票否决，还是仍可跟踪\n"
        "- 包含标准风险声明（过往业绩不代表未来表现）\n"
        "- 不要包含任何数字"
    ),
    7: (
        "请基于上述判断依据数据和前6章分析，写一段「综合评估与跟踪建议」。要求：\n"
        "- 给出综合评估结论\n"
        "- 说明支撑结论的核心依据\n"
        "- 指出当前最容易看错的地方\n"
        "- 给出下一轮最小验证计划（1-2个）\n"
        "- 不要包含任何数字"
    ),
}


def _generate_data_table(
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
) -> str:
    """程序化生成数据表格（数字 100% 从数据 dict 提取，不经过 LLM）。

    参数:
        chapter_id: 章节编号。
        fund_code/fund_name/report_year: 基本信息。
        performance/holdings/allocation/fees: 多年度数据。
        fund_manager: 基金经理信息。
        scale_info: 规模信息。
        evidence: 证据来源汇总（可选）。

    返回:
        Markdown 格式的数据表格文本（含证据来源小节）。
    """

    base_content = ""

    # Ch0: 投资要点概览 — 汇总关键指标
    if chapter_id == 0:
        latest = performance.get(report_year, {})
        latest_nav = latest.get("nav_growth_rate", "N/A")
        latest_bench = latest.get("benchmark_return_rate", "N/A")
        latest_excess = latest.get("excess_return", "N/A")

        # 计算多年超额收益趋势
        excess_trend = ""
        excess_years = sorted(performance.keys())
        if len(excess_years) >= 2:
            excesses = [performance[y].get("excess_return", "N/A") for y in excess_years]
            excess_trend = ", ".join(f"{y}年:{e}" for y, e in zip(excess_years, excesses))

        # 最新费率
        latest_fees = fees.get(report_year, [])
        mgmt_fee = ""
        custodian_fee = ""
        for f in latest_fees:
            if "管理" in f.fee_name:
                mgmt_fee = f.rate
            elif "托管" in f.fee_name:
                custodian_fee = f.rate

        lines = [
            "## 关键指标",
            "",
            "| 指标 | 值 |",
            "|------|----|",
            f"| 基金名称 | {fund_name} |",
            f"| 基金代码 | {fund_code} |",
            f"| 报告年份 | {report_year} |",
            f"| 最新净值增长率 | {latest_nav} |",
            f"| 最新基准收益率 | {latest_bench} |",
            f"| 最新超额收益 | {latest_excess} |",
            f"| 管理费 | {mgmt_fee or 'N/A'} |",
            f"| 托管费 | {custodian_fee or 'N/A'} |",
        ]
        if fund_manager:
            lines.append(f"| 基金经理 | {fund_manager.name} |")
        if excess_trend:
            lines.append("")
            lines.append(f"**超额收益趋势**：{excess_trend}")
        base_content = "\n".join(lines)

    # Ch1: 产品定义 — 基本信息 + 基金经理
    if chapter_id == 1:
        lines = [
            "## 基本信息",
            "",
            "| 项目 | 值 |",
            "|------|----|",
            f"| 基金代码 | {fund_code} |",
            f"| 基金名称 | {fund_name} |",
            f"| 报告年份 | {report_year} |",
        ]
        if fund_manager:
            lines.extend([
                f"| 基金经理 | {fund_manager.name} |",
                f"| 任职日期 | {fund_manager.tenure_start} |",
                f"| 从业年限 | {fund_manager.years_of_service} |",
            ])
            if fund_manager.investment_strategy:
                lines.append("")
                lines.append("## 基金经理投资策略（原文摘录）")
                lines.append("")
                lines.append(fund_manager.investment_strategy[:400])
        base_content = "\n".join(lines)

    # Ch2: R=A+B-C 收益归因
    if chapter_id == 2:
        lines = [
            "## 业绩数据",
            "",
            "| 年份 | 净值增长率(R) | 基准收益率(B) | 超额收益(A=R-B) |",
            "|------|-------------|-------------|----------------|",
        ]
        for year in sorted(performance.keys()):
            p = performance[year]
            lines.append(
                f"| {year} | {p.get('nav_growth_rate', 'N/A')} | "
                f"{p.get('benchmark_return_rate', 'N/A')} | "
                f"{p.get('excess_return', 'N/A')} |"
            )
        # 费率作为成本C
        lines.extend(["", "## 成本数据(C)", ""])
        lines.extend(["| 年份 | 管理费 | 托管费 |", "|------|--------|--------|"])
        for year in sorted(fees.keys()):
            mgmt = ""
            cust = ""
            for f in fees[year]:
                if "管理" in f.fee_name:
                    mgmt = f.rate
                elif "托管" in f.fee_name:
                    cust = f.rate
            lines.append(f"| {year} | {mgmt} | {cust} |")
        base_content = "\n".join(lines)

    # Ch3: 基金经理画像
    if chapter_id == 3:
        lines = ["## 基金经理信息"]
        if fund_manager:
            lines.extend([
                "",
                "| 项目 | 值 |",
                "|------|----|",
                f"| 姓名 | {fund_manager.name} |",
                f"| 任职日期 | {fund_manager.tenure_start} |",
                f"| 从业年限 | {fund_manager.years_of_service} |",
                f"| 持有本基金 | {fund_manager.holds_fund or '未披露'} |",
            ])
            if fund_manager.investment_strategy:
                lines.extend(["", "## 宣称投资策略（原文）", "", fund_manager.investment_strategy[:600]])
        else:
            lines.append("\n基金经理信息暂不可用。")
        # 持仓变化作为实际行为
        lines.extend(["", "## 实际持仓行为"])
        for year in sorted(holdings.keys()):
            lines.append(f"\n### {year} 年前十大持仓")
            lines.append("| 排名 | 股票代码 | 股票名称 | 占净值比 |")
            lines.append("|------|---------|---------|---------|")
            for h in holdings[year][:10]:
                lines.append(f"| {h.rank} | {h.stock_code} | {h.stock_name} | {h.percentage} |")
        base_content = "\n".join(lines)

    # Ch4: 投资者获得感 — 暂不可用
    if chapter_id == 4:
        base_content = "## 投资者获得感\n\n投资者实际收益数据暂不可用，详见原始年报。"

    # Ch5: 当前阶段与关键变化
    if chapter_id == 5:
        lines = ["## 规模与配置数据"]
        if scale_info:
            lines.extend([
                "",
                "| 项目 | 值 |",
                "|------|----|",
                f"| A类份额总数 | {scale_info.total_shares_a} |",
                f"| C类份额总数 | {scale_info.total_shares_c} |",
                f"| 个人投资者持有比例 | {scale_info.individual_investor_ratio} |",
                f"| 管理人从业人员持有比例 | {scale_info.management_holds} |",
            ])
            if scale_info.estimated_aum:
                lines.append(f"| 估算资产净值 | {scale_info.estimated_aum} |")
        # 资产配置变化
        lines.extend(["", "## 资产配置变化"])
        for year in sorted(allocation.keys()):
            lines.append(f"\n### {year} 年资产配置")
            lines.append("| 资产类别 | 金额 | 占净值比 |")
            lines.append("|---------|------|---------|")
            for a in allocation[year][:8]:
                lines.append(f"| {a.category} | {a.amount} | {a.percentage_of_net} |")
        base_content = "\n".join(lines)

    # Ch6: 核心风险与否决项
    if chapter_id == 6:
        lines = ["## 风险相关数据"]
        # 持仓集中度
        for year in sorted(holdings.keys()):
            top5_pct = sum(float(h.percentage.rstrip("%") or "0") for h in holdings[year][:5])
            lines.append(f"\n{year}年前五大持仓集中度: {top5_pct:.2f}%")
        # 业绩波动
        lines.extend(["", "## 业绩波动"])
        lines.append("| 年份 | 净值增长率 | 超额收益 |")
        lines.append("|------|-----------|---------|")
        for year in sorted(performance.keys()):
            p = performance[year]
            lines.append(f"| {year} | {p.get('nav_growth_rate', 'N/A')} | {p.get('excess_return', 'N/A')} |")
        base_content = "\n".join(lines)

    # Ch7: 最终判断 — 汇总数据
    if chapter_id == 7:
        latest = performance.get(report_year, {})
        lines = [
            "## 判断依据数据",
            "",
            f"- 最新净值增长率: {latest.get('nav_growth_rate', 'N/A')}",
            f"- 最新超额收益: {latest.get('excess_return', 'N/A')}",
        ]
        if fund_manager:
            lines.append(f"- 基金经理: {fund_manager.name}（从业{fund_manager.years_of_service}）")
        # 最新费率
        latest_fees = fees.get(report_year, [])
        for f in latest_fees:
            lines.append(f"- {f.fee_name}: {f.rate}")
        base_content = "\n".join(lines)

    # 追加证据来源小节
    evidence_section = _generate_evidence_section(chapter_id, evidence)
    if evidence_section:
        return base_content + "\n" + evidence_section
    return base_content


def _format_citation(citation: Citation | None) -> str:
    """格式化单个 citation 为可读文本。

    参数:
        citation: Citation 对象或 None。

    返回:
        格式化的 citation 文本。
    """

    if citation is None:
        return ""

    locator = citation.locator
    parts = []
    if locator.section_ref:
        parts.append(f"§{locator.section_ref}")
    if locator.table_ref:
        parts.append(f"表{locator.table_ref}")
    if locator.page_no:
        parts.append(f"p.{locator.page_no}")

    ref_str = ", ".join(parts) if parts else "位置未知"
    return f"{citation.year}年报 ({ref_str})"


def _generate_evidence_section(
    chapter_id: int,
    evidence: ChapterEvidence | None,
) -> str:
    """生成章节证据来源小节。

    参数:
        chapter_id: 章节编号。
        evidence: 证据来源汇总。

    返回:
        Markdown 格式的证据来源小节。
    """

    if evidence is None:
        return ""

    lines = ["\n### 证据与出处\n"]

    # 根据章节类型列出相关证据来源
    if chapter_id in (0, 2, 7):  # 业绩相关
        if evidence.performance_citations:
            cit_lines = []
            for year, cit in sorted(evidence.performance_citations.items()):
                formatted = _format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**业绩数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (0, 3, 6, 7):  # 持仓相关
        if evidence.holdings_citations:
            cit_lines = []
            for year, cit in sorted(evidence.holdings_citations.items()):
                formatted = _format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**持仓数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (2, 5, 7):  # 费率相关
        if evidence.fee_citations:
            cit_lines = []
            for year, cit in sorted(evidence.fee_citations.items()):
                formatted = _format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**费率数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (4, 5):  # 资产配置相关
        if evidence.allocation_citations:
            cit_lines = []
            for year, cit in sorted(evidence.allocation_citations.items()):
                formatted = _format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**资产配置数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (1, 3):  # 基金经理相关
        if evidence.fund_manager_citation:
            formatted = _format_citation(evidence.fund_manager_citation)
            if formatted:
                lines.append(f"**基金经理信息来源**：{formatted}")

    if chapter_id in (0, 5, 7):  # 规模相关
        if evidence.scale_citation:
            formatted = _format_citation(evidence.scale_citation)
            if formatted:
                lines.append(f"**规模数据来源**：{formatted}")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


class LlmChapterGenerator:
    """基于 LLM 的逐章生成器（两阶段模式）。

    阶段 1：程序从数据 dict 生成表格（数字 100% 准确）。
    阶段 2：LLM 只写定性分析评论（无数字）。
    最终：表格 + LLM 分析。

    参数:
        llm_client: DeepSeekLlmClient 实例。

    返回:
        可逐章生成分析文本的生成器。

    异常:
        generate_chapter 不向调用方抛出内部异常，失败返回 None。
    """

    def __init__(self, llm_client: Any) -> None:
        """保存 LLM client。"""
        self._llm_client = llm_client

    def generate_chapter(
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
    ) -> str | None:
        """生成单个章节（程序表格 + LLM 分析）。

        参数:
            chapter_id: 章节编号（0-7）。
            fund_code/fund_name/report_year: 基本信息。
            performance/holdings/allocation/fees: 多年度数据。
            fund_manager: 基金经理信息。
            scale_info: 规模信息。
            evidence: 证据来源汇总（可选）。

        返回:
            完整的章节 Markdown；LLM 失败时返回 None（调用方应回退模板）。
        """

        # 阶段 1：程序生成数据表格
        data_table = _generate_data_table(
            chapter_id, fund_code, fund_name, report_year,
            performance, holdings, allocation, fees,
            fund_manager, scale_info, evidence,
        )

        # 阶段 2：LLM 生成定性分析
        analysis_prompt = _LLM_ANALYSIS_PROMPTS.get(chapter_id)
        if not analysis_prompt:
            return data_table if data_table else None

        user_prompt = (
            f"基金名称：{fund_name}\n"
            f"报告年份：{report_year}\n\n"
            f"## 数据表格\n\n{data_table}\n\n"
            f"## 分析要求\n\n{analysis_prompt}"
        )

        try:
            llm_analysis = self._llm_client.generate_text(
                system_prompt=_LLM_CHAPTER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            # 从数据表中提取允许的数字（这些数字来自真实数据，不是 hallucination）
            allowed_numbers = set(re.findall(r'\d+\.?\d*', data_table))
            # 检查 LLM 是否违规输出了数字
            if _contains_non_year_numbers(llm_analysis, allowed_numbers):
                return None  # hallucination，回退模板
            return f"{data_table}\n\n## 分析\n\n{llm_analysis}"
        except Exception:
            return None


def _contains_non_year_numbers(text: str, allowed_numbers: set[str] | None = None) -> bool:
    """检查文本是否包含非年份的数字（hallucination 检测）。

    参数:
        text: 待检查文本。
        allowed_numbers: 允许的数字集合（从数据表中提取）；这些数字不视为 hallucination。

    返回:
        包含可疑数字时返回 True。
    """

    numbers = re.findall(r'(?<!\d)\d+\.?\d*%?(?!\d)', text)
    for n in numbers:
        cleaned = n.rstrip('%')
        # 年份（20xx）允许
        if re.match(r'^(20[12]\d)$', cleaned):
            continue
        # 单位数字（1-9）和常见小数字（10-99）允许（从业年限、排名等）
        if re.match(r'^[1-9]\d?$', cleaned):
            continue
        # 在允许列表中的数字允许
        if allowed_numbers and cleaned in allowed_numbers:
            continue
        return True
    return False


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
            for report in catalog_reports:
                if report.get("fund_code") == request.fund_code and report.get("year") == request.year:
                    document_id = str(report["document_id"])
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

            disclosures.append(self._audit_holdings(host, document_id, request.year))
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

    def _audit_holdings(self, host: MinimalHost, document_id: str, year: int) -> DisclosureAuditItem:
        """审计持仓披露。"""

        routed = self._run_with_query_candidates(host=host, document_id=document_id, query="股票投资明细")
        if routed.agent_result.failure is not None:
            return DisclosureAuditItem(name="holdings", status="missing", chapter=False, message="持仓章节未找到")

        has_table = any(c.locator.locator_kind is LocatorKind.TABLE for c in routed.agent_result.citations)
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
                output_path = self._export_markdown(report, request.work_dir)
            elif request.output_format == "pdf":
                md_path = self._export_markdown(report, request.work_dir)
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
                tables = tool_service.list_tables(doc_id)
                for t in tables:
                    if hasattr(t, "section_ref") and t.section_ref == hit.section_ref:
                        table = tool_service.read_table(doc_id, t.table_ref, max_rows=5)
                        if hasattr(table, "rows") and len(table.rows) >= 3:
                            data_row = table.rows[2] if len(table.rows) > 2 else table.rows[1]
                            if len(data_row) >= 5:
                                name = str(data_row[0]).strip()
                                tenure_start = str(data_row[2]).strip()
                                years_of_service = str(data_row[4]).strip()
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
                        shares = float(shares_list[i]) if i < len(shares_list) and shares_list[i] else 0.0
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
    ) -> list[ReportChapter]:
        """生成 8 章报告内容（模板对齐版）。"""

        chapters: list[ReportChapter] = []

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

    def _generate_ch7_risks(
        self,
        fund_name: str,
    ) -> str:
        """生成风险提示章节。"""

        return f"""## 风险提示

1. 本基金过往业绩不代表未来表现
2. 投资有风险，入市需谨慎
3. 基金持仓和费率数据来源于公开披露的年度报告
4. 本报告由 AI 辅助生成，仅供参考

*数据来源：{fund_name} 年度报告*
"""

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
            )

            if content is None:
                content = self._generate_template_chapter(
                    chapter_id, fund_code, fund_name, report_year,
                    performance, holdings, allocation, fees,
                    fund_manager, scale_info,
                )
                warnings.append(f"Ch{chapter_id} LLM 分析失败，已回退模板")

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

        返回:
            模板生成的 Markdown 文本。
        """

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
            base_content = self._generate_ch7_risks(fund_name)
        elif chapter_id == 7:
            latest = performance.get(report_year, {})
            base_content = (
                f"## 综合评估\n\n"
                f"基于 {report_year} 年报数据，该基金最新净值增长率为 {latest.get('nav_growth_rate', 'N/A')}，"
                f"超额收益为 {latest.get('excess_return', 'N/A')}。详见前6章分析。\n"
            )
        else:
            base_content = ""

        # 追加证据来源小节
        evidence_section = _generate_evidence_section(chapter_id, evidence)
        if evidence_section:
            return base_content + "\n" + evidence_section
        return base_content

    def _export_markdown(self, report: FundReport, work_dir: Path) -> str:
        """导出 Markdown 文件。"""

        output_dir = work_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{report.fund_code}-{report.report_year}-analysis.md"

        lines = [f"# {report.fund_name}（{report.fund_code}）{report.report_year} 年度分析报告\n"]
        lines.append("**风险警示**：本报告由 AI 辅助生成，仅供参考，不构成投资建议。\n")

        for chapter in report.chapters:
            lines.append(f"\n---\n\n## 第 {chapter.chapter_id + 1} 章：{chapter.title}\n")
            lines.append(chapter.content)

        output_path.write_text("\n".join(lines), encoding="utf-8")
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
