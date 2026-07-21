"""基金阅读 Service 层 DTO / Model 定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fund_agent.agent import AgentRunResult
from fund_agent.fund.document_tools.constants import (
    FailureCode,
    ReportType,
)
from fund_agent.fund.document_tools.models import (
    Citation,
    Locator,
    ReportSummary,
    ToolFailure,
)


QueryRouteResultKind = Literal["success", "failure"]
_ROUTE_RESULT_SUCCESS: QueryRouteResultKind = "success"
_ROUTE_RESULT_FAILURE: QueryRouteResultKind = "failure"


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
    holding_source: str = ""


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
    fund_name: str = ""


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


@dataclass(frozen=True)
class ThresholdEvent:
    """阈值事件（升级或降级）。

    参数:
        direction: 方向，"upgrade" 或 "downgrade"。
        indicator_name: 触发指标名（如"超额收益趋势"）。
        current_score: 当前得分。
        target_score: 目标得分（升级=满分，降级=0）。
        tier_delta: 一档跳变带来的 raw points 增量。
        description: 程序拼接的事件描述。

    返回:
        不可变阈值事件 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    direction: str
    indicator_name: str
    current_score: int
    target_score: int
    tier_delta: int
    description: str


@dataclass(frozen=True)
class SignalIndicator:
    """信号判断单项指标评分。

    参数:
        name: 指标名称（如"超额收益趋势"）。
        score: 本指标得分。
        max_score: 本指标满分。
        detail: 评分说明（如"连续 2+ 年正超额"）。

    返回:
        不可变指标评分 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    name: str
    score: int
    max_score: int
    detail: str


@dataclass(frozen=True)
class SignalJudgment:
    """基金综合信号判断结果。

    参数:
        signal: 三选一信号（🟢 值得持有 / 🟡 需要关注 / 🔴 建议替换）。
        normalized_score: 归一化总分（0-100）。
        indicators: 6 项指标评分明细。
        data_completeness: 数据完整度比例（0.0-1.0，如 1.0 表示 6/6）。
        warnings: 数据不足或其他警告。
        upgrade_event: 升级阈值事件（None 表示无法判断或已满分）。
        downgrade_event: 降级阈值事件（None 表示无法判断或已零分）。

    返回:
        不可变信号判断 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    signal: str
    normalized_score: float
    indicators: tuple[SignalIndicator, ...]
    data_completeness: float
    warnings: tuple[str, ...] = ()
    upgrade_event: ThresholdEvent | None = None
    downgrade_event: ThresholdEvent | None = None


@dataclass(frozen=True)
class RiskChecklistItem:
    """风险清单单条检查项。

    参数:
        name: 风险项名称（如"清盘风险"）。
        status: 三色状态（🟢 / 🟡 / 🔴）。
        detail: 状态说明。

    返回:
        不可变风险检查项 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class StressTestResult:
    """Ch6 压力测试结果。

    参数:
        fund_type: 基金类型（index_fund / bond_fund / active_fund）。
        fund_type_inferred: 类型是否由关键词推断。
        current_scale_billion: 当前规模（亿元），无数据时为 None。
        stress_scenarios: 三档压力场景（normal/extreme/worst），各含 threshold 和 loss_billion。
        nav_growth_rate: 净值增长率（小数形式），无数据时为 None。
        benchmark_return_rate: 基准收益率（小数形式），无数据时为 None。
        excess_return: 超额收益（小数形式），无数据时为 None。
        stress_level: 压力等级（outperform/inline/underperform/severe_underperform/None）。

    返回:
        不可变压力测试结果 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    fund_type: str
    fund_type_inferred: bool
    current_scale_billion: float | None
    stress_scenarios: dict[str, dict[str, float]]
    nav_growth_rate: float | None
    benchmark_return_rate: float | None
    excess_return: float | None
    stress_level: str | None
