"""基金阅读 Service 层入口。"""

from fund_agent.service.reading_service import (
    FundReadingService,
    ImportLocalReportRequest,
    ImportLocalReportResult,
    ListReportsRequest,
    ListReportsResult,
    ReadLocalReportRequest,
    ReadLocalReportResult,
)

__all__ = [
    "FundReadingService",
    "ImportLocalReportRequest",
    "ImportLocalReportResult",
    "ListReportsRequest",
    "ListReportsResult",
    "ReadLocalReportRequest",
    "ReadLocalReportResult",
]
