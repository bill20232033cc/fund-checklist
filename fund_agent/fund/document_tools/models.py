"""基金文档工具的公共数据模型。"""

from dataclasses import dataclass
from pathlib import Path

from fund_agent.fund.document_tools.constants import (
    PDF_CONTENT_TYPE,
    FailureCode,
    ReportType,
    SourceKind,
)


@dataclass(frozen=True)
class PdfImportRequest:
    """本地 PDF 导入请求。

    参数:
        path: 待导入的本地 PDF 路径。
        fund_code: 基金代码，用于生成公开 document_id。
        fund_name: 基金名称，用于 citation 和 report summary。
        year: 报告年份。
        report_type: 报告类型；MVP 只接受 annual_report。
        share_class: 可选份额类别；无法明确时保持 None，不参与 document_id。
        content_type: 本地来源等价 Content-Type；默认 application/pdf。

    返回:
        dataclass 实例本身，不执行 I/O。

    异常:
        本模型不抛出业务异常；导入校验由 LocalPdfSourceProvider 执行。
    """

    path: Path
    fund_code: str
    fund_name: str
    year: int
    report_type: ReportType = ReportType.ANNUAL_REPORT
    share_class: str | None = None
    content_type: str = PDF_CONTENT_TYPE


@dataclass(frozen=True)
class ReportIdentity:
    """基金年报的内容身份。

    参数:
        fund_code: 基金代码。
        fund_name: 基金名称。
        year: 报告年份。
        report_type: 报告类型。
        source_kind: 来源类型。
        local_import_id: 本地导入事件 ID，仅用于审计 metadata。
        content_fingerprint: PDF bytes 的稳定内容指纹。
        document_id: public reading tools 使用的内容身份。
        share_class: 可选份额类别，不参与 document_id。

    返回:
        不可变身份对象。

    异常:
        本模型不抛出业务异常；一致性由导入服务保证。
    """

    fund_code: str
    fund_name: str
    year: int
    report_type: ReportType
    source_kind: SourceKind
    local_import_id: str
    content_fingerprint: str
    document_id: str
    share_class: str | None = None


@dataclass(frozen=True)
class PdfImportResult:
    """本地 PDF 导入结果。

    参数:
        identity: 导入后得到的内容身份。
        stored_blob_ref: 受控 blob 引用，不暴露本地文件系统路径。

    返回:
        dataclass 实例本身。

    异常:
        本模型不抛出业务异常。
    """

    identity: ReportIdentity
    stored_blob_ref: str


@dataclass(frozen=True)
class ToolFailure:
    """公共工具失败输出模型。

    参数:
        code: 稳定失败分类。
        message: 安全错误信息。

    返回:
        可序列化的失败描述。

    异常:
        本模型不抛出业务异常。
    """

    code: FailureCode
    message: str

