"""基金阅读 Service 层入口。"""

from fund_agent.service.extraction import (
    ExtractFeeRatesRequest,
    ExtractAnnualExcessReturnRequest,
    ExtractAnnualPerformanceRequest,
    ExtractPerformanceReturnsRequest,
    FundReadingService,
    ImportLocalReportRequest,
    ImportLocalReportResult,
    ListReportsRequest,
    ListReportsResult,
    ReadLocalReportRequest,
    ReadLocalReportResult,
)
from fund_agent.service.chapter_generator import (
    LlmChapterGenerator,
)
from fund_agent.service.models import (
    AggregateMultiYearAnnualPerformanceRequest,
    AggregateMultiYearAnnualPerformanceResult,
    AnnualAllocationResult,
    AnnualExcessReturnExtraction,
    AnnualFeeResult,
    AnnualHoldingsResult,
    AnnualPerformanceFieldCitation,
    AnnualReportDocument,
    AssetAllocationItem,
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
    ExtractPerformanceReturnsResult,
    ExtractFeeRatesMultiYearRequest,
    ExtractFeeRatesMultiYearResult,
    ExtractFeeRatesResult,
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
    MultiYearAllocationSeries,
    MultiYearAnnualPerformanceRow,
    MultiYearAnnualPerformanceSeries,
    MultiYearFeeSeries,
    MultiYearHoldingsSeries,
    PerformanceReturnExtraction,
    QueryRouteAttempt,
    ReportChapter,
    ScaleInfo,
)


# __all__ 由所有显式 import 的公开名称自动生成，无需手工维护
__all__ = sorted(
    name for name in dir()
    if not name.startswith("_")
    and name not in ("annotations",)
)
