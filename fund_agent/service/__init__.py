"""基金阅读 Service 层入口。"""

from fund_agent.service.reading_service import (
    AnnualExcessReturnExtraction,
    ExtractFeeRatesRequest,
    ExtractFeeRatesResult,
    ExtractAnnualExcessReturnRequest,
    ExtractAnnualExcessReturnResult,
    FeeRateExtraction,
    FundReadingService,
    ImportLocalReportRequest,
    ImportLocalReportResult,
    ListReportsRequest,
    ListReportsResult,
    QueryRouteAttempt,
    ReadLocalReportRequest,
    ReadLocalReportResult,
)

__all__ = [
    "AnnualExcessReturnExtraction",
    "ExtractAnnualExcessReturnRequest",
    "ExtractAnnualExcessReturnResult",
    "ExtractFeeRatesRequest",
    "ExtractFeeRatesResult",
    "FeeRateExtraction",
    "FundReadingService",
    "ImportLocalReportRequest",
    "ImportLocalReportResult",
    "ListReportsRequest",
    "ListReportsResult",
    "QueryRouteAttempt",
    "ReadLocalReportRequest",
    "ReadLocalReportResult",
]
