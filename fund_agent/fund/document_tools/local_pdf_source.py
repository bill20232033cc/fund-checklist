"""本地 PDF 导入、内容指纹和受控 blob 存储。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from fund_agent.fund.document_tools.constants import (
    CONTENT_FINGERPRINT_ALGORITHM,
    FINGERPRINT_PREFIX_LENGTH,
    LOCAL_PDF_BLOB_REF_PREFIX,
    METADATA_FILENAME,
    PDF_CONTENT_TYPE,
    PDF_FILENAME,
    PDF_MAGIC_BYTES,
    FailureCode,
    ReportType,
    SourceKind,
)
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import PdfImportRequest, PdfImportResult, ReportIdentity

_ACCEPTED_CONTENT_TYPES = frozenset({PDF_CONTENT_TYPE})
_DOCUMENT_ID_FUND_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class PdfBlobStore:
    """受控 PDF blob 存储。

    参数:
        root_dir: 受控 blob 根目录。调用方可选择临时目录或应用私有目录。

    返回:
        PdfBlobStore 实例。

    异常:
        写入失败时由调用方转换为稳定 failure code。
    """

    def __init__(self, root_dir: Path) -> None:
        """初始化 blob 根目录但不立即暴露文件系统路径。"""

        self._root_dir = Path(root_dir)

    def write_pdf(self, document_id: str, pdf_bytes: bytes) -> str:
        """以原子替换方式写入 PDF bytes。

        参数:
            document_id: 内容身份，用于组织私有存储目录。
            pdf_bytes: 已通过完整性校验的 PDF bytes。

        返回:
            不含本地路径的 blob 引用。

        异常:
            OSError: 目录创建、临时写入、fsync 或原子替换失败。
        """

        document_dir = self._root_dir / document_id
        document_dir.mkdir(parents=True, exist_ok=True)
        destination = document_dir / PDF_FILENAME
        if destination.exists() and destination.read_bytes() == pdf_bytes:
            return make_blob_ref(document_id)

        temporary = document_dir / f".{PDF_FILENAME}.{uuid4().hex}.tmp"
        with temporary.open("wb") as file_handle:
            file_handle.write(pdf_bytes)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary, destination)
        return make_blob_ref(document_id)

    def read_pdf(self, stored_blob_ref: str) -> bytes:
        """读取受控 blob 引用对应的 PDF bytes。

        参数:
            stored_blob_ref: import_pdf 返回的受控 blob 引用。

        返回:
            PDF bytes。

        异常:
            DocumentToolError: blob 引用不存在或格式不受支持时返回 not_found。
        """

        document_id = parse_blob_ref(stored_blob_ref)
        path = self._root_dir / document_id / PDF_FILENAME
        if not path.exists():
            raise DocumentToolError(FailureCode.NOT_FOUND, "PDF blob 不存在")
        return path.read_bytes()


class LocalPdfSourceProvider:
    """本地 PDF source provider。

    参数:
        blob_root: 受控 blob 根目录。

    返回:
        可执行本地 PDF 导入的 provider。

    异常:
        构造函数不执行导入，不抛出业务异常。
    """

    def __init__(self, blob_root: Path) -> None:
        """初始化 provider 与同根目录的 blob store。"""

        self._blob_root = Path(blob_root)
        self._blob_store = PdfBlobStore(self._blob_root)

    @property
    def blob_store(self) -> PdfBlobStore:
        """返回受控 blob store，供测试或后续 converter 读取 blob。"""

        return self._blob_store

    def import_pdf(self, request: PdfImportRequest) -> PdfImportResult:
        """导入本地 PDF 并返回稳定内容身份。

        参数:
            request: 本地 PDF 导入请求，包含路径、基金身份和报告类型。

        返回:
            PdfImportResult，包含 public document_id 和受控 blob 引用。

        异常:
            DocumentToolError: Content-Type、空内容、PDF magic bytes、身份冲突、
                原子写入失败或写后校验失败时抛出稳定 failure code。
        """

        normalized = _normalize_request(request)
        pdf_bytes = _read_local_pdf_bytes(normalized.path)
        _assert_pdf_integrity(normalized.content_type, pdf_bytes)

        content_fingerprint = fingerprint_pdf_bytes(pdf_bytes)
        document_id = build_document_id(
            fund_code=normalized.fund_code,
            year=normalized.year,
            report_type=normalized.report_type,
            content_fingerprint=content_fingerprint,
        )
        _assert_known_identity(
            index=_read_identity_index(self._blob_root),
            request=normalized,
            content_fingerprint=content_fingerprint,
            document_id=document_id,
        )

        try:
            stored_blob_ref = self._blob_store.write_pdf(document_id, pdf_bytes)
            if fingerprint_pdf_bytes(self._blob_store.read_pdf(stored_blob_ref)) != content_fingerprint:
                raise DocumentToolError(FailureCode.INTEGRITY_ERROR, "PDF 原子写入后校验失败")
            _write_identity_index(
                self._blob_root,
                _next_identity_index_entry(
                    index=_read_identity_index(self._blob_root),
                    request=normalized,
                    content_fingerprint=content_fingerprint,
                    document_id=document_id,
                ),
            )
        except DocumentToolError:
            raise
        except OSError as exc:
            raise DocumentToolError(FailureCode.INTEGRITY_ERROR, "PDF 原子写入失败") from exc

        identity = ReportIdentity(
            fund_code=normalized.fund_code,
            fund_name=normalized.fund_name,
            year=normalized.year,
            report_type=normalized.report_type,
            source_kind=SourceKind.LOCAL_PDF,
            local_import_id=f"local-{uuid4().hex}",
            content_fingerprint=content_fingerprint,
            document_id=document_id,
            share_class=normalized.share_class,
        )
        return PdfImportResult(identity=identity, stored_blob_ref=stored_blob_ref)


def fingerprint_pdf_bytes(pdf_bytes: bytes) -> str:
    """计算 PDF bytes 的稳定内容指纹。

    参数:
        pdf_bytes: PDF 文件 bytes。

    返回:
        sha256 十六进制字符串。

    异常:
        本函数不抛出业务异常。
    """

    hasher = hashlib.new(CONTENT_FINGERPRINT_ALGORITHM)
    hasher.update(pdf_bytes)
    return hasher.hexdigest()


def build_document_id(
    *,
    fund_code: str,
    year: int,
    report_type: ReportType,
    content_fingerprint: str,
) -> str:
    """按裁决规则构造 public document_id。

    参数:
        fund_code: ASCII 基金代码。
        year: 报告年份。
        report_type: 报告类型。
        content_fingerprint: PDF 内容指纹。

    返回:
        `fund_code-year-report_type-fingerprint_prefix` 格式的 document_id。

    异常:
        DocumentToolError: fund_code 或 report_type 不满足 MVP 身份约束。
    """

    _assert_supported_identity(fund_code=fund_code, report_type=report_type)
    fingerprint_prefix = content_fingerprint[:FINGERPRINT_PREFIX_LENGTH]
    return f"{fund_code}-{year}-{report_type.value}-{fingerprint_prefix}"


def make_blob_ref(document_id: str) -> str:
    """生成不暴露本地路径的 blob 引用。

    参数:
        document_id: public content identity。

    返回:
        形如 `local_pdf:<document_id>` 的受控引用。

    异常:
        本函数不抛出业务异常。
    """

    return f"{LOCAL_PDF_BLOB_REF_PREFIX}:{document_id}"


def parse_blob_ref(stored_blob_ref: str) -> str:
    """解析受控 blob 引用。

    参数:
        stored_blob_ref: 受控 blob 引用。

    返回:
        document_id。

    异常:
        DocumentToolError: 引用格式不支持时返回 not_found。
    """

    prefix = f"{LOCAL_PDF_BLOB_REF_PREFIX}:"
    if not stored_blob_ref.startswith(prefix):
        raise DocumentToolError(FailureCode.NOT_FOUND, "PDF blob 引用不存在")
    return stored_blob_ref[len(prefix) :]


def _normalize_request(request: PdfImportRequest) -> PdfImportRequest:
    """标准化导入请求中的 Path 与字符串字段。"""

    return PdfImportRequest(
        path=Path(request.path),
        fund_code=request.fund_code.strip(),
        fund_name=request.fund_name.strip(),
        year=request.year,
        report_type=_coerce_report_type(request.report_type),
        share_class=request.share_class.strip() if request.share_class else None,
        content_type=request.content_type.strip().lower(),
    )


def _coerce_report_type(report_type: ReportType) -> ReportType:
    """把外部同值输入收敛为 MVP 支持的 ReportType。"""

    try:
        return ReportType(report_type)
    except ValueError as exc:
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "report_type 不在 MVP 支持范围") from exc


def _read_local_pdf_bytes(path: Path) -> bytes:
    """读取本地 PDF bytes，并把文件 I/O 失败分类为 not_found。"""

    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise DocumentToolError(FailureCode.NOT_FOUND, "PDF 文件不存在") from exc
    except OSError as exc:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "PDF 文件暂不可读") from exc


def _assert_pdf_integrity(content_type: str, pdf_bytes: bytes) -> None:
    """校验 Content-Type、非空内容和 PDF magic bytes。"""

    if content_type not in _ACCEPTED_CONTENT_TYPES:
        raise DocumentToolError(FailureCode.INTEGRITY_ERROR, "PDF Content-Type 校验失败")
    if not pdf_bytes:
        raise DocumentToolError(FailureCode.INTEGRITY_ERROR, "PDF 内容为空")
    if not pdf_bytes.startswith(PDF_MAGIC_BYTES):
        raise DocumentToolError(FailureCode.INTEGRITY_ERROR, "PDF magic bytes 校验失败")


def _assert_supported_identity(*, fund_code: str, report_type: ReportType) -> None:
    """校验 Slice 1 支持的 public identity 输入。"""

    if report_type is not ReportType.ANNUAL_REPORT:
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "report_type 不在 MVP 支持范围")
    if not fund_code or not _DOCUMENT_ID_FUND_CODE_PATTERN.fullmatch(fund_code):
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "fund_code 不满足 document_id 规则")


def _identity_fields_for_match(request: PdfImportRequest, document_id: str) -> dict[str, object]:
    """提取同 fingerprint 下必须一致的身份字段。"""

    return {
        "document_id": document_id,
        "fund_code": request.fund_code,
        "fund_name": request.fund_name,
        "year": request.year,
        "report_type": request.report_type.value,
        "source_kind": SourceKind.LOCAL_PDF.value,
    }


def _assert_known_identity(
    *,
    index: dict[str, dict[str, object]],
    request: PdfImportRequest,
    content_fingerprint: str,
    document_id: str,
) -> None:
    """校验同一内容指纹未被登记为冲突身份。"""

    existing = index.get(content_fingerprint)
    if existing is None:
        return
    expected = _identity_fields_for_match(request, document_id)
    for key, value in expected.items():
        if existing.get(key) != value:
            raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "PDF 内容指纹已绑定不同报告身份")


def _next_identity_index_entry(
    *,
    index: dict[str, dict[str, object]],
    request: PdfImportRequest,
    content_fingerprint: str,
    document_id: str,
) -> dict[str, dict[str, object]]:
    """返回追加或复用后的身份索引。"""

    next_index = dict(index)
    next_index[content_fingerprint] = {
        **_identity_fields_for_match(request, document_id),
        "content_fingerprint": content_fingerprint,
        "share_class": request.share_class,
    }
    return next_index


def _read_identity_index(root_dir: Path) -> dict[str, dict[str, object]]:
    """读取本地受控身份索引；缺失时返回空索引。"""

    path = Path(root_dir) / METADATA_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "PDF 身份索引不可用") from exc
    if not isinstance(data, dict):
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "PDF 身份索引格式错误")
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _write_identity_index(root_dir: Path, index: dict[str, dict[str, object]]) -> None:
    """以原子替换方式写入受控身份索引。"""

    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / METADATA_FILENAME
    temporary = root / f".{METADATA_FILENAME}.{uuid4().hex}.tmp"
    payload = json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2)
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)
