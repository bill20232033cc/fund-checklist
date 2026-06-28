"""基金文档工具的稳定常量定义。"""

from enum import Enum


class StrValueEnum(str, Enum):
    """提供字符串值枚举，避免公共契约中散落魔法字符串。"""

    def __str__(self) -> str:
        """返回枚举的公共字符串值。"""

        return self.value


class ReportType(StrValueEnum):
    """基金报告类型；MVP 首批只支持年报。"""

    ANNUAL_REPORT = "annual_report"


class SourceKind(StrValueEnum):
    """文档来源类型；Slice 1 只支持本地 PDF。"""

    LOCAL_PDF = "local_pdf"


class FailureCode(StrValueEnum):
    """公共失败分类，供异常和后续工具输出稳定断言。"""

    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    SCHEMA_DRIFT = "schema_drift"
    IDENTITY_MISMATCH = "identity_mismatch"
    INTEGRITY_ERROR = "integrity_error"
    DOCLING_CONVERT_FAILED = "docling_convert_failed"
    PARSER_HEALTH_FAILED = "parser_health_failed"


PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC_BYTES = b"%PDF-"
CONTENT_FINGERPRINT_ALGORITHM = "sha256"
FINGERPRINT_PREFIX_LENGTH = 16
LOCAL_PDF_BLOB_REF_PREFIX = "local_pdf"
METADATA_FILENAME = "identity_index.json"
PDF_FILENAME = "source.pdf"
