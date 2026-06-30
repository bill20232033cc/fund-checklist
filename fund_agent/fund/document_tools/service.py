"""基金年报阅读工具服务边界。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

from fund_agent.fund.document_tools.constants import (
    DEFAULT_SEARCH_EXCERPT_CHARS,
    FailureCode,
    LocatorKind,
    ReportType,
)
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.models import (
    Citation,
    ExcerptContent,
    Locator,
    ReportIdentity,
    ReportSummary,
    SearchResult,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
    ToolFailure,
)

_UNAVAILABLE_MESSAGE = "阅读工具暂不可用"
_NOT_FOUND_MESSAGE = "请求的文档内容不存在"


class FundDocumentToolService:
    """基金年报七个 public reading tools 的唯一入口。

    参数:
        document_stores: 内存 registry，键为 document_id，值为已通过 parser_health 的
            DoclingDocumentStore。

    返回:
        可供 Agent/Host 注册的 reading tool service。

    异常:
        构造函数不访问文件系统；public tool 方法把业务失败转换为 ToolFailure。
    """

    def __init__(self, document_stores: Mapping[str, DoclingDocumentStore] | None = None) -> None:
        """初始化内存 document store registry。"""

        self._stores: dict[str, DoclingDocumentStore] = dict(document_stores or {})

    def register_store(self, *, document_id: str, store: DoclingDocumentStore) -> None:
        """注册一个已通过 parser_health 的文档 store。

        参数:
            document_id: public reading tools 使用的内容身份。
            store: 已构造完成的 DoclingDocumentStore。

        返回:
            None。

        异常:
            本方法不抛出业务异常；后续 public tool 会按 registry 读取。
        """

        self._stores[document_id] = store

    def list_reports(
        self,
        *,
        fund_code: str | None = None,
        year: int | None = None,
        report_type: ReportType | str | None = None,
    ) -> tuple[ReportSummary, ...] | ToolFailure:
        """列出当前内存 registry 中的安全报告摘要。

        参数:
            fund_code: 可选基金代码过滤。
            year: 可选报告年份过滤。
            report_type: 可选报告类型过滤，MVP 仅 annual_report。

        返回:
            ReportSummary 元组；无匹配时返回空元组；内部失败返回 ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(
            lambda: tuple(
                summary
                for store in self._stores.values()
                if _matches_filters(
                    identity := _identity_from_store(store),
                    fund_code=fund_code,
                    year=year,
                    report_type=report_type,
                )
                for summary in (_summary_from_identity(identity),)
            )
        )

    def list_sections(self, document_id: str) -> tuple[SectionSummary, ...] | ToolFailure:
        """列出指定年报的章节摘要。

        参数:
            document_id: public reading tools 使用的内容身份。

        返回:
            SectionSummary 元组；失败时返回 ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(lambda: self._store(document_id).list_sections())

    def read_section(
        self,
        document_id: str,
        section_ref: str,
        *,
        max_chars: int | None = None,
    ) -> SectionContent | ToolFailure:
        """读取指定章节的有界正文。

        参数:
            document_id: public reading tools 使用的内容身份。
            section_ref: 由 list_sections 或 search_document 返回的受控章节引用。
            max_chars: 可选最大字符数。

        返回:
            SectionContent；失败时返回 ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(lambda: self._store(document_id).read_section(section_ref, max_chars=max_chars))

    def search_document(
        self,
        document_id: str,
        query: str,
        *,
        within_section_ref: str | None = None,
        max_results: int | None = None,
    ) -> tuple[SearchResult, ...] | ToolFailure:
        """在指定年报中检索有界摘录。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 检索关键词。
            within_section_ref: 可选章节过滤。
            max_results: 可选最大命中数。

        返回:
            SearchResult 元组；无命中时返回空元组；失败时返回 ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(
            lambda: self._store(document_id).search(
                query,
                within_section_ref=within_section_ref,
                max_results=max_results,
            )
        )

    def list_tables(
        self,
        document_id: str,
        *,
        within_section_ref: str | None = None,
    ) -> tuple[TableSummary, ...] | ToolFailure:
        """列出指定年报中的表格摘要。

        参数:
            document_id: public reading tools 使用的内容身份。
            within_section_ref: 可选章节过滤。

        返回:
            TableSummary 元组；无表格时返回空元组，不视为失败；失败时返回 ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(lambda: self._store(document_id).list_tables(within_section_ref=within_section_ref))

    def read_table(
        self,
        document_id: str,
        table_ref: str,
        *,
        max_rows: int | None = None,
    ) -> TableContent | ToolFailure:
        """读取指定表格的有界二维行内容。

        参数:
            document_id: public reading tools 使用的内容身份。
            table_ref: 由 list_tables 返回的受控表格引用。
            max_rows: 可选最大行数。

        返回:
            TableContent；失败时返回 ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(lambda: self._store(document_id).read_table(table_ref, max_rows=max_rows))

    def get_excerpt(
        self,
        document_id: str,
        locator: Locator,
        *,
        max_chars: int | None = None,
    ) -> ExcerptContent | ToolFailure:
        """按 prior tool 返回的受控 locator 读取有界摘录。

        参数:
            document_id: public reading tools 使用的内容身份。
            locator: list_sections、search_document 或 list_tables 返回的受控 locator。
            max_chars: 可选最大字符数；None 使用搜索摘录默认上限。

        返回:
            ExcerptContent；unknown locator 返回 not_found ToolFailure。

        异常:
            不向 public caller 抛出 DocumentToolError 或未分类异常。
        """

        return self._call_tool(lambda: self._get_excerpt(document_id, locator, max_chars=max_chars))

    def _store(self, document_id: str) -> DoclingDocumentStore:
        """按 document_id 读取内存 registry 中的 store。"""

        store = self._stores.get(document_id)
        if store is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, "文档不存在")
        return store

    def _get_excerpt(self, document_id: str, locator: Locator, *, max_chars: int | None) -> ExcerptContent:
        """执行 locator kind 路由并构造统一摘录模型。"""

        if locator.document_id != document_id:
            raise DocumentToolError(FailureCode.NOT_FOUND, _NOT_FOUND_MESSAGE)
        if locator.locator_kind is LocatorKind.TABLE:
            return self._table_excerpt(document_id, locator, max_chars=max_chars)
        if locator.locator_kind in {LocatorKind.SECTION, LocatorKind.EXCERPT}:
            return self._section_excerpt(document_id, locator, max_chars=max_chars)
        raise DocumentToolError(FailureCode.NOT_FOUND, _NOT_FOUND_MESSAGE)

    def _section_excerpt(self, document_id: str, locator: Locator, *, max_chars: int | None) -> ExcerptContent:
        """从 section/excerpt locator 读取章节摘录。"""

        if locator.section_ref is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, _NOT_FOUND_MESSAGE)
        content = self._store(document_id).read_section(
            locator.section_ref,
            max_chars=max_chars or DEFAULT_SEARCH_EXCERPT_CHARS,
        )
        excerpt_locator = _coerce_excerpt_locator(locator, content.locator)
        return ExcerptContent(
            text=content.text,
            truncated=content.truncated,
            locator=excerpt_locator,
            citation=_replace_citation_locator(content.citation, excerpt_locator),
        )

    def _table_excerpt(self, document_id: str, locator: Locator, *, max_chars: int | None) -> ExcerptContent:
        """从 table locator 读取表格文本摘录。"""

        if locator.table_ref is None:
            raise DocumentToolError(FailureCode.NOT_FOUND, _NOT_FOUND_MESSAGE)
        table = self._store(document_id).read_table(locator.table_ref)
        text, text_truncated = _bounded(_table_to_text(table), max_chars or DEFAULT_SEARCH_EXCERPT_CHARS)
        return ExcerptContent(
            text=text,
            truncated=table.truncated or text_truncated,
            locator=table.locator,
            citation=table.citation,
        )

    def _call_tool(self, action: Callable[[], object]) -> object:
        """统一把 public tool 内部失败转换为 ToolFailure。"""

        try:
            return action()
        except DocumentToolError as exc:
            return ToolFailure(code=exc.code, message=exc.message)
        except Exception:
            return ToolFailure(code=FailureCode.UNAVAILABLE, message=_UNAVAILABLE_MESSAGE)


def _identity_from_store(store: DoclingDocumentStore) -> ReportIdentity:
    """从 Fund 层 store 读取安全身份，不暴露 raw Docling payload。"""

    identity = getattr(store, "_identity", None)
    if not isinstance(identity, ReportIdentity):
        raise DocumentToolError(FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE)
    return identity


def _matches_filters(
    identity: ReportIdentity,
    *,
    fund_code: str | None,
    year: int | None,
    report_type: ReportType | str | None,
) -> bool:
    """判断报告身份是否满足 list_reports 过滤条件。"""

    if fund_code is not None and identity.fund_code != fund_code:
        return False
    if year is not None and identity.year != year:
        return False
    if report_type is not None and identity.report_type.value != str(report_type):
        return False
    return True


def _summary_from_identity(identity: ReportIdentity) -> ReportSummary:
    """从完整身份构造不含 local_import_id 和路径的 report summary。"""

    return ReportSummary(
        document_id=identity.document_id,
        fund_code=identity.fund_code,
        fund_name=identity.fund_name,
        year=identity.year,
        report_type=identity.report_type.value,
        source_kind=identity.source_kind.value,
        source_summary=f"{identity.source_kind.value}:sha256:{identity.content_fingerprint[:16]}",
        content_fingerprint=identity.content_fingerprint,
        share_class=identity.share_class,
    )


def _coerce_excerpt_locator(requested: Locator, fallback: Locator) -> Locator:
    """把 section locator 转换为 excerpt locator，同时保留 parser 可得定位字段。"""

    if requested.locator_kind is LocatorKind.EXCERPT:
        return requested
    return replace(fallback, locator_kind=LocatorKind.EXCERPT)


def _replace_citation_locator(citation: Citation, locator: Locator) -> Citation:
    """返回替换 locator 后的 citation。"""

    return replace(citation, locator=locator)


def _table_to_text(table: TableContent) -> str:
    """把二维表格行转换为有界摘录前的纯文本投影。"""

    return "\n".join("\t".join(cell for cell in row) for row in table.rows)


def _bounded(text: str, max_chars: int) -> tuple[str, bool]:
    """按字符数截断文本并返回 truncated 标记。"""

    if max_chars < 1:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
