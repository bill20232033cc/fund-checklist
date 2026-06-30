"""Docling PDF 转换器。"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from fund_agent.fund.document_tools.constants import (
    DOCLING_CONVERTER_INPUT_NAME,
    DOCLING_JSON_REF_PREFIX,
    DOCLING_JSON_SUFFIX,
    SINGLE_PDF_SMOKE_TIMEOUT_SECONDS,
    FailureCode,
)
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import DoclingConversionResult, ReportIdentity


class DoclingConverter:
    """把受控 PDF bytes 转换为受控 Docling JSON 文件。

    参数:
        output_root: Docling JSON 输出根目录；测试应使用 tmp_path 或忽略目录。
        timeout_seconds: 单 PDF 转换超时预算，默认 300 秒。
        do_ocr: 是否启用 Docling OCR；本地文本型 PDF smoke 默认关闭。

    返回:
        DoclingConverter 实例。

    异常:
        构造函数不导入 Docling，不抛出业务异常。
    """

    def __init__(
        self,
        output_root: Path,
        *,
        timeout_seconds: int = SINGLE_PDF_SMOKE_TIMEOUT_SECONDS,
        do_ocr: bool = False,
    ) -> None:
        """初始化转换输出目录和 Docling pipeline 选项。"""

        self._output_root = Path(output_root)
        self._timeout_seconds = timeout_seconds
        self._do_ocr = do_ocr

    def convert_pdf(self, *, identity: ReportIdentity, pdf_bytes: bytes) -> DoclingConversionResult:
        """执行真实 Docling PDF 转换并写出受控 JSON。

        参数:
            identity: PDF 对应的报告内容身份。
            pdf_bytes: 已通过 integrity check 的 PDF bytes。

        返回:
            DoclingConversionResult，包含受控 JSON 引用、Fund 内部路径和耗时。

        异常:
            DocumentToolError: Docling 依赖、模型资源或写入目录不可用时返回
                unavailable；Docling PDF 转换失败时返回 docling_convert_failed。
        """

        started_at = time.monotonic()
        document_dir = self._output_root / identity.document_id
        json_path = document_dir / f"{identity.document_id}{DOCLING_JSON_SUFFIX}"

        try:
            document_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling JSON 输出目录不可用") from exc

        try:
            converter = _build_docling_converter(
                timeout_seconds=self._timeout_seconds,
                do_ocr=self._do_ocr,
            )
        except ImportError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling 依赖不可用") from exc
        except OSError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling runtime 资源不可用") from exc

        try:
            stream = _build_document_stream(pdf_bytes)
            result = converter.convert(stream, raises_on_error=True)
            if result.has_timeout_errors():
                raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling 转换超时")
            if result.has_parse_errors() or result.document is None:
                raise DocumentToolError(FailureCode.DOCLING_CONVERT_FAILED, "Docling PDF 转换失败")
        except DocumentToolError:
            raise
        except TimeoutError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling 转换超时") from exc
        except Exception as exc:
            if _is_unavailable_exception(exc):
                raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling runtime 资源不可用") from exc
            raise DocumentToolError(FailureCode.DOCLING_CONVERT_FAILED, "Docling PDF 转换失败") from exc

        try:
            _save_docling_json(result.document, json_path)
        except DocumentToolError:
            raise
        except OSError as exc:
            raise DocumentToolError(FailureCode.UNAVAILABLE, "Docling JSON 写入失败") from exc

        return DoclingConversionResult(
            document_id=identity.document_id,
            docling_json_ref=make_docling_json_ref(identity.document_id),
            json_path=json_path,
            elapsed_seconds=time.monotonic() - started_at,
        )


def make_docling_json_ref(document_id: str) -> str:
    """生成不暴露本地路径的 Docling JSON 引用。

    参数:
        document_id: public content identity。

    返回:
        形如 `docling_json:<document_id>` 的受控引用。

    异常:
        本函数不抛出业务异常。
    """

    return f"{DOCLING_JSON_REF_PREFIX}:{document_id}"


def _build_docling_converter(*, timeout_seconds: int, do_ocr: bool):
    """延迟构造 Docling DocumentConverter，避免模块导入期依赖失败。"""

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions(
        document_timeout=float(timeout_seconds),
        do_ocr=do_ocr,
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
    )


def _build_document_stream(pdf_bytes: bytes):
    """把 PDF bytes 包装成 Docling 支持的内存输入流。"""

    from docling_core.types.io import DocumentStream

    return DocumentStream(name=DOCLING_CONVERTER_INPUT_NAME, stream=BytesIO(pdf_bytes))


def _save_docling_json(document, json_path: Path) -> None:
    """按受控 JSON 文件保存 DoclingDocument，不嵌入图片 payload。"""

    from docling_core.types.doc import ImageRefMode

    document.save_as_json(json_path, image_mode=ImageRefMode.PLACEHOLDER, indent=2)


def _is_unavailable_exception(exc: Exception) -> bool:
    """判断异常是否来自临时依赖、模型资源或网络资源不可用。"""

    module = exc.__class__.__module__
    message = str(exc).lower()
    if module.startswith("huggingface_hub"):
        return True
    unavailable_markers = (
        "hub",
        "internet",
        "connection",
        "download",
        "local cache",
        "offline",
        "timeout",
        "timed out",
        "temporarily unavailable",
    )
    return any(marker in message for marker in unavailable_markers)
