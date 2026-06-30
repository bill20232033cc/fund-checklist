"""基金文档工具的公共数据模型。"""

from dataclasses import dataclass
from pathlib import Path

from fund_agent.fund.document_tools.constants import (
    PDF_CONTENT_TYPE,
    FailureCode,
    LocatorKind,
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


@dataclass(frozen=True)
class Locator:
    """年报内容定位信息。

    参数:
        document_id: public reading tools 使用的内容身份。
        locator_kind: locator 类型。
        section_ref: 章节引用；章节和摘录 locator 必填。
        table_ref: 表格引用；表格 locator 必填。
        page_no: 单页页码；可得时透传。
        page_range: 跨页范围；可得时透传。
        internal_ref: Docling self_ref 等内部稳定引用；可得时透传。
        internal_ref_available: 是否存在内部引用。
        bbox: 数值型边界框；不可得时为 None。

    返回:
        不暴露本地路径和 raw payload 的 locator。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    locator_kind: LocatorKind
    section_ref: str | None
    table_ref: str | None
    page_no: int | None
    page_range: tuple[int, int] | None
    internal_ref: str | None
    internal_ref_available: bool
    bbox: dict[str, float] | None = None


@dataclass(frozen=True)
class Citation:
    """阅读工具 citation metadata。

    参数:
        document_id: 内容身份。
        fund_code: 基金代码。
        fund_name: 基金名称。
        year: 报告年份。
        report_type: 报告类型。
        locator: 可回溯到年报位置的 locator。

    返回:
        上层可引用的 citation。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    fund_code: str
    fund_name: str
    year: int
    report_type: str
    locator: Locator


@dataclass(frozen=True)
class SectionSummary:
    """章节摘要。

    参数:
        section_ref: 受控章节引用。
        title: 章节标题。
        level: 章节层级。
        parent_ref: 父章节引用；不可得时为 None。
        locator: 章节 locator。
        preview: 有界预览文本。

    返回:
        不含 raw Docling payload 的章节摘要。

    异常:
        本模型不抛出业务异常。
    """

    section_ref: str
    title: str
    level: int
    parent_ref: str | None
    locator: Locator
    preview: str


@dataclass(frozen=True)
class SectionContent:
    """章节正文读取结果。

    参数:
        section_ref: 受控章节引用。
        title: 章节标题。
        text: 有界正文。
        truncated: 正文是否被截断。
        locator: 章节 locator。
        citation: citation metadata。

    返回:
        上层可安全展示或喂给 Agent 的章节正文。

    异常:
        本模型不抛出业务异常。
    """

    section_ref: str
    title: str
    text: str
    truncated: bool
    locator: Locator
    citation: Citation


@dataclass(frozen=True)
class TableSummary:
    """表格摘要。

    参数:
        table_ref: 受控表格引用。
        caption: 表格标题或说明；不可得时为 None。
        section_ref: 所属章节引用；不可得时为 None。
        locator: 表格 locator。
        row_count: 行数；不可得时为 None。
        column_count: 列数；不可得时为 None。

    返回:
        不含 raw table payload 的表格摘要。

    异常:
        本模型不抛出业务异常。
    """

    table_ref: str
    caption: str | None
    section_ref: str | None
    locator: Locator
    row_count: int | None
    column_count: int | None


@dataclass(frozen=True)
class TableContent:
    """表格读取结果。

    参数:
        table_ref: 受控表格引用。
        caption: 表格标题或说明。
        section_ref: 所属章节引用。
        rows: 有界二维文本行。
        truncated: 是否按行数截断。
        locator: 表格 locator。
        citation: citation metadata。

    返回:
        上层可安全展示或检索的表格内容。

    异常:
        本模型不抛出业务异常。
    """

    table_ref: str
    caption: str | None
    section_ref: str | None
    rows: tuple[tuple[str, ...], ...]
    truncated: bool
    locator: Locator
    citation: Citation


@dataclass(frozen=True)
class SearchResult:
    """文档搜索结果。

    参数:
        rank: 排名，从 1 开始。
        section_ref: 命中的章节引用。
        title: 命中章节标题。
        excerpt: 有界摘录。
        locator: excerpt locator。
        citation: citation metadata。

    返回:
        上层可安全使用的搜索投影。

    异常:
        本模型不抛出业务异常。
    """

    rank: int
    section_ref: str
    title: str
    excerpt: str
    locator: Locator
    citation: Citation


@dataclass(frozen=True)
class DoclingConversionResult:
    """Docling 转换成功结果。

    参数:
        document_id: 内容身份。
        docling_json_ref: 受控 JSON 引用，不是本地路径。
        json_path: Fund 层内部使用的 JSON 路径；不得进入 public tool 输出。
        elapsed_seconds: 转换耗时。

    返回:
        converter 内部交接结果。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    docling_json_ref: str
    json_path: Path
    elapsed_seconds: float


@dataclass(frozen=True)
class ParserHealth:
    """Docling JSON parser health 检查结果。

    参数:
        readable_text_count: 可读文本块数量。
        section_count: 章节数量。
        table_count: 表格数量。
        searchable_text_chars: 可检索文本字符数。

    返回:
        通过 health gate 的摘要。

    异常:
        本模型不抛出业务异常。
    """

    readable_text_count: int
    section_count: int
    table_count: int
    searchable_text_chars: int
