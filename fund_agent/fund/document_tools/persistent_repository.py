"""本地 completed report 的 filesystem JSON catalog repository。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fund_agent.fund.document_tools.constants import (
    DOCLING_JSON_REF_PREFIX,
    DOCLING_JSON_SUFFIX,
    FailureCode,
    ReportType,
    SourceKind,
)
from fund_agent.fund.document_tools.docling_converter import make_docling_json_ref
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.local_pdf_source import PdfBlobStore, fingerprint_pdf_bytes
from fund_agent.fund.document_tools.models import ParserHealth, ReportIdentity

CATALOG_FILENAME = "completed_reports.json"
CATALOG_SCHEMA_VERSION = 1
_INTERNAL_RESTORED_IMPORT_ID = "repository-restored"


class FilesystemReportRepository:
    """用 filesystem JSON catalog 持久化已完成的本地 PDF report。

    参数:
        catalog_path: catalog JSON 文件路径；文件本身不进入 public tool 输出。
        blob_root: 受控 PDF blob 根目录。
        docling_json_root: 受控 Docling JSON 根目录。

    返回:
        repository 实例，可写入 completed record 或按 document_id 恢复 store。

    异常:
        构造函数不访问文件系统，不抛出业务异常。
    """

    def __init__(self, *, catalog_path: Path, blob_root: Path, docling_json_root: Path) -> None:
        """初始化 repository 的三个本地根路径。"""

        self._catalog_path = Path(catalog_path)
        self._blob_store = PdfBlobStore(Path(blob_root))
        self._docling_json_root = Path(docling_json_root)

    def record_completed_report(
        self,
        *,
        identity: ReportIdentity,
        stored_blob_ref: str,
        docling_json_ref: str,
        parser_health: ParserHealth,
    ) -> None:
        """写入或更新已完成 report 的 catalog record。

        参数:
            identity: 已完成 report 的内容身份。
            stored_blob_ref: 受控 PDF blob ref，不是本地路径。
            docling_json_ref: 受控 Docling JSON ref，不是本地路径。
            parser_health: 已通过的 parser health 摘要。

        返回:
            None。

        异常:
            DocumentToolError: catalog 不可写或 ref 与 identity 不一致时抛出稳定失败。
        """

        _assert_docling_json_ref(document_id=identity.document_id, docling_json_ref=docling_json_ref)
        catalog = self._read_catalog_for_write()
        reports = _reports_from_catalog(catalog)
        previous = reports.get(identity.document_id)
        now = _utc_now()
        reports[identity.document_id] = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "document_id": identity.document_id,
            "identity": _identity_to_catalog(identity),
            "stored_blob_ref": stored_blob_ref,
            "docling_json_ref": docling_json_ref,
            "parser_health": asdict(parser_health),
            "created_at": str(previous.get("created_at")) if isinstance(previous, dict) else now,
            "updated_at": now,
        }
        self._write_catalog({"schema_version": CATALOG_SCHEMA_VERSION, "reports": reports})

    def load_store(self, document_id: str) -> DoclingDocumentStore:
        """按 document_id 从 catalog 恢复已完成的 DoclingDocumentStore。

        参数:
            document_id: public reading tools 使用的内容身份。

        返回:
            已通过 parser_health 的 DoclingDocumentStore。

        异常:
            DocumentToolError: 按 Slice 6 failure mapping 返回稳定失败分类。
        """

        catalog = self._read_catalog()
        reports = _reports_from_catalog(catalog)
        record = reports.get(document_id)
        if record is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "catalog 中不存在该文档")
        if not isinstance(record, dict):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog record 结构不符合契约")

        identity = _identity_from_record(record, requested_document_id=document_id)
        stored_blob_ref = _required_str(record, "stored_blob_ref")
        docling_json_ref = _required_str(record, "docling_json_ref")
        _assert_docling_json_ref(document_id=document_id, docling_json_ref=docling_json_ref)
        _assert_blob_fingerprint(self._blob_store, stored_blob_ref, identity.content_fingerprint)

        json_path = self._docling_json_path(document_id=document_id, docling_json_ref=docling_json_ref)
        if not json_path.is_file():
            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling JSON 暂不可用")
        return DoclingDocumentStore(identity=identity, json_path=json_path)

    def _read_catalog(self) -> dict[str, object]:
        """读取并校验 catalog 顶层结构。"""

        try:
            payload = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DocumentToolError(FailureCode.NOT_FOUND, "catalog 不存在") from exc
        except OSError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "catalog 暂不可读") from exc
        except json.JSONDecodeError as exc:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog 不是有效 JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog schema 不兼容")
        return payload

    def _read_catalog_for_write(self) -> dict[str, object]:
        """读取 catalog 用于更新；不存在时返回空 catalog。"""

        if not self._catalog_path.exists():
            return {"schema_version": CATALOG_SCHEMA_VERSION, "reports": {}}
        return self._read_catalog()

    def _write_catalog(self, catalog: dict[str, object]) -> None:
        """以原子替换方式写入 catalog。"""

        try:
            self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._catalog_path.parent / f".{CATALOG_FILENAME}.{uuid4().hex}.tmp"
            temporary.write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
            os.replace(temporary, self._catalog_path)
        except OSError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "catalog 暂不可写") from exc

    def _docling_json_path(self, *, document_id: str, docling_json_ref: str) -> Path:
        """把受控 Docling JSON ref 映射为 repository 内部路径。"""

        _assert_docling_json_ref(document_id=document_id, docling_json_ref=docling_json_ref)
        return self._docling_json_root / document_id / f"{document_id}{DOCLING_JSON_SUFFIX}"


def _reports_from_catalog(catalog: dict[str, object]) -> dict[str, object]:
    """读取 catalog.reports 并校验为对象。"""

    reports = catalog.get("reports")
    if not isinstance(reports, dict):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog reports 结构不符合契约")
    return reports


def _identity_to_catalog(identity: ReportIdentity) -> dict[str, object]:
    """序列化 safe identity 字段，不写入 local_import_id。"""

    return {
        "fund_code": identity.fund_code,
        "fund_name": identity.fund_name,
        "year": identity.year,
        "report_type": identity.report_type.value,
        "source_kind": identity.source_kind.value,
        "content_fingerprint": identity.content_fingerprint,
        "document_id": identity.document_id,
        "share_class": identity.share_class,
    }


def _identity_from_record(record: dict[str, object], *, requested_document_id: str) -> ReportIdentity:
    """从 catalog record 恢复内部 ReportIdentity。"""

    if record.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog record schema 不兼容")
    if record.get("document_id") != requested_document_id:
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "catalog record identity 不匹配")
    identity_payload = record.get("identity")
    if not isinstance(identity_payload, dict):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog identity 结构不符合契约")
    if identity_payload.get("document_id") != requested_document_id:
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "catalog identity 不匹配")

    try:
        report_type = ReportType(_required_str(identity_payload, "report_type"))
        source_kind = SourceKind(_required_str(identity_payload, "source_kind"))
    except ValueError as exc:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog identity 枚举不符合契约") from exc

    return ReportIdentity(
        fund_code=_required_str(identity_payload, "fund_code"),
        fund_name=_required_str(identity_payload, "fund_name"),
        year=_required_int(identity_payload, "year"),
        report_type=report_type,
        source_kind=source_kind,
        local_import_id=_INTERNAL_RESTORED_IMPORT_ID,
        content_fingerprint=_required_str(identity_payload, "content_fingerprint"),
        document_id=requested_document_id,
        share_class=_optional_str(identity_payload.get("share_class")),
    )


def _assert_docling_json_ref(*, document_id: str, docling_json_ref: str) -> None:
    """校验 Docling JSON ref 与 document_id 一致。"""

    if docling_json_ref != make_docling_json_ref(document_id):
        prefix = f"{DOCLING_JSON_REF_PREFIX}:"
        if not docling_json_ref.startswith(prefix):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "Docling JSON ref 格式不符合契约")
        raise DocumentToolError(FailureCode.IDENTITY_MISMATCH, "Docling JSON ref identity 不匹配")


def _assert_blob_fingerprint(blob_store: PdfBlobStore, stored_blob_ref: str, expected_fingerprint: str) -> None:
    """校验 catalog 指向的 PDF blob 仍匹配内容指纹。"""

    try:
        pdf_bytes = blob_store.read_pdf(stored_blob_ref)
    except DocumentToolError as exc:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "PDF blob 暂不可用") from exc
    if fingerprint_pdf_bytes(pdf_bytes) != expected_fingerprint:
        raise DocumentToolError(FailureCode.INTEGRITY_ERROR, "PDF blob 指纹不匹配")


def _required_str(payload: dict[str, object], key: str) -> str:
    """读取必填字符串字段。"""

    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, f"catalog 缺少 {key}")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    """读取必填整数字段。"""

    value = payload.get(key)
    if not isinstance(value, int):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, f"catalog 缺少 {key}")
    return value


def _optional_str(value: object) -> str | None:
    """读取可选字符串字段。"""

    if value is None:
        return None
    if not isinstance(value, str):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog share_class 不符合契约")
    return value


def _utc_now() -> str:
    """返回 UTC ISO 时间戳。"""

    return datetime.now(UTC).isoformat(timespec="seconds")
