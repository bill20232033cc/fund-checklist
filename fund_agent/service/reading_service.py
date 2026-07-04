"""基金年报阅读 use case Service 边界。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fund_agent.agent import AgentRunResult, MinimalFundDocumentAgent
from fund_agent.fund.document_tools.constants import (
    DOCLING_JSON_SUFFIX,
    FailureCode,
    LocatorKind,
    ReportType,
)
from fund_agent.fund.document_tools.docling_converter import DoclingConverter, make_docling_json_ref
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.local_pdf_source import LocalPdfSourceProvider
from fund_agent.fund.document_tools.models import PdfImportRequest, PdfImportResult, ReportSummary, ToolFailure
from fund_agent.fund.document_tools.persistent_repository import (
    CATALOG_FILENAME,
    CATALOG_SCHEMA_VERSION,
    FilesystemReportRepository,
)
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.host import MinimalHost

PDF_BLOB_DIRNAME = "pdf_blobs"
DOCLING_JSON_DIRNAME = "docling_json"

ConverterFactory = Callable[[Path], DoclingConverter]
HostFactory = Callable[[FundDocumentToolService], MinimalHost]

_MAX_QUERY_CANDIDATES = 4
QueryRouteResultKind = Literal["success", "failure"]
_ROUTE_RESULT_SUCCESS: QueryRouteResultKind = "success"
_ROUTE_RESULT_FAILURE: QueryRouteResultKind = "failure"
_TARGET_NOT_FOUND_MESSAGE = "未找到符合受控披露目标的证据"
_TABLE_TITLE_PREFIX = "表格标题:"
_SECTION_TITLE_PREFIX = "来源章节:"
_TABLE_BLOCK_HEADER = "相关表格:"


@dataclass(frozen=True)
class _ControlledDisclosureTarget:
    """Service 内部受控披露目标契约。"""

    target_id: str
    allowed_evidence_kinds: tuple[LocatorKind, ...]
    acceptable_title_family: tuple[str, ...]
    expected_citation_kinds: tuple[LocatorKind, ...]


@dataclass(frozen=True)
class _ControlledQueryProfile:
    """Service 内部受控 query profile 配置。"""

    name: str
    aliases: tuple[str, ...]
    fallback_candidates: tuple[str, ...]
    disclosure_target: _ControlledDisclosureTarget
    require_all_target_candidates: bool = False


@dataclass(frozen=True)
class QueryRouteAttempt:
    """Service query routing 单次尝试的审计事实。

    参数:
        query: 本次传给 Host/Agent 的原始 candidate query。
        profile_name: 命中的受控 profile 名称；非受控 query 为 None。
        result_kind: 本次尝试结果，只允许 success 或 failure。
        failure_code: 失败时的稳定 failure code；成功时必须为 None。

    返回:
        不可变审计 DTO，仅属于 Service-level metadata。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    query: str
    profile_name: str | None
    result_kind: QueryRouteResultKind
    failure_code: FailureCode | None = None


CONTROLLED_QUERY_PROFILES = (
    _ControlledQueryProfile(
        name="holdings_top10",
        aliases=("前十大持仓", "重仓股", "持仓明细"),
        fallback_candidates=("股票投资明细", "前十名股票投资明细"),
        disclosure_target=_ControlledDisclosureTarget(
            target_id="holdings_top10",
            allowed_evidence_kinds=(LocatorKind.TABLE,),
            acceptable_title_family=("股票投资明细", "前十名股票投资明细"),
            expected_citation_kinds=(LocatorKind.TABLE,),
        ),
    ),
    _ControlledQueryProfile(
        name="asset_allocation",
        aliases=("资产配置", "资产组合"),
        fallback_candidates=("期末基金资产组合情况", "基金资产组合情况"),
        disclosure_target=_ControlledDisclosureTarget(
            target_id="asset_allocation",
            allowed_evidence_kinds=(LocatorKind.TABLE,),
            acceptable_title_family=("期末基金资产组合情况", "基金资产组合情况"),
            expected_citation_kinds=(LocatorKind.TABLE,),
        ),
    ),
    _ControlledQueryProfile(
        name="fee_rates",
        aliases=("费用", "费率", "管理费", "托管费", "销售服务费"),
        fallback_candidates=("基金管理费", "基金托管费", "销售服务费"),
        disclosure_target=_ControlledDisclosureTarget(
            target_id="fee_rates",
            allowed_evidence_kinds=(LocatorKind.SECTION, LocatorKind.TABLE),
            acceptable_title_family=("基金管理费", "基金托管费", "销售服务费"),
            expected_citation_kinds=(LocatorKind.SECTION, LocatorKind.TABLE),
        ),
        require_all_target_candidates=True,
    ),
)


@dataclass(frozen=True)
class ImportLocalReportRequest:
    """登记本地基金年报 PDF 的 use case 请求。

    参数:
        pdf_path: 本地 PDF 路径，只允许 Service 内部导入使用。
        fund_code: 基金代码。
        fund_name: 基金名称。
        year: 报告年份。
        work_dir: 本地受控工作目录。
        report_type: 报告类型，当前仅 annual_report。
        share_class: 可选份额类别。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    pdf_path: Path
    fund_code: str
    fund_name: str
    year: int
    work_dir: Path
    report_type: ReportType = ReportType.ANNUAL_REPORT
    share_class: str | None = None


@dataclass(frozen=True)
class ImportLocalReportResult:
    """本地年报导入并完成阅读准备后的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        report: 不含本地路径和 local_import_id 的报告摘要。

    返回:
        可返回给 CLI/UI 的安全 DTO。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    report: ReportSummary


@dataclass(frozen=True)
class ReadLocalReportRequest(ImportLocalReportRequest):
    """读取本地基金年报的 use case 请求。

    参数:
        query: 交给 Host/Agent 的检索问题。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    query: str = "基金经理"


@dataclass(frozen=True)
class ReadLocalReportResult:
    """读取本地年报后的安全结果。

    参数:
        document_id: public reading tools 使用的内容身份。
        agent_result: Host/Agent 返回的安全阅读结果。
        routing_trace: Service-level query routing attempts 审计记录，不进入 Agent tool_trace。

    返回:
        可供 CLI 格式化的 DTO。

    异常:
        本模型不抛出业务异常。
    """

    document_id: str
    agent_result: AgentRunResult
    routing_trace: tuple[QueryRouteAttempt, ...] = ()


@dataclass(frozen=True)
class ListReportsRequest:
    """列出本地 completed reports 的 use case 请求。

    参数:
        work_dir: 本地受控工作目录。
        fund_code: 可选基金代码过滤。
        year: 可选年份过滤。
        report_type: 可选报告类型过滤。

    返回:
        不可变请求 DTO。

    异常:
        本模型不执行 I/O，不抛出业务异常。
    """

    work_dir: Path
    fund_code: str | None = None
    year: int | None = None
    report_type: ReportType | str | None = None


@dataclass(frozen=True)
class ListReportsResult:
    """列出 completed reports 后的安全结果。

    参数:
        reports: 不含本地路径和 local_import_id 的报告摘要。
        failure: 下层工具服务返回的稳定失败；成功时为 None。

    返回:
        可供 CLI/UI 格式化的 DTO。

    异常:
        本模型不抛出业务异常。
    """

    reports: tuple[ReportSummary, ...]
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class _PreparedReport:
    """Service 内部已完成阅读准备的 report。"""

    import_result: PdfImportResult
    store: DoclingDocumentStore


@dataclass(frozen=True)
class _QueryRoutePlan:
    """Service 内部 query routing 执行计划。"""

    profile_name: str | None
    candidate_queries: tuple[str, ...]
    disclosure_target: _ControlledDisclosureTarget | None
    require_all_target_candidates: bool = False


@dataclass(frozen=True)
class _QueryRouteRun:
    """Service 内部 query routing 执行结果。"""

    agent_result: AgentRunResult
    routing_trace: tuple[QueryRouteAttempt, ...]


class FundReadingService:
    """基金阅读 Service use case 边界。

    参数:
        converter_factory: DoclingConverter 工厂，测试可注入 fake converter。
        host_factory: Host 工厂，测试可验证 Host 只接收 document_id 和 query。

    返回:
        可执行 import/read/list 三个首批 use case 的 Service。

    异常:
        构造函数不访问本地文件系统，不抛出业务异常。
    """

    def __init__(
        self,
        *,
        converter_factory: ConverterFactory | None = None,
        host_factory: HostFactory | None = None,
    ) -> None:
        """初始化 Service 的可注入依赖。"""

        self._converter_factory = converter_factory or DoclingConverter
        self._host_factory = host_factory or _default_host_factory

    def import_local_report(self, request: ImportLocalReportRequest) -> ImportLocalReportResult:
        """导入本地 PDF，必要时转换 Docling JSON，并登记 completed report。

        参数:
            request: 本地 PDF 导入请求。

        返回:
            ImportLocalReportResult，只包含 public document_id 和安全报告摘要。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类。
        """

        prepared = self._prepare_completed_report(request)
        summary = _single_report_summary(prepared.import_result.identity.document_id, prepared.store)
        return ImportLocalReportResult(
            document_id=prepared.import_result.identity.document_id,
            report=summary,
        )

    def read_local_report(self, request: ReadLocalReportRequest) -> ReadLocalReportResult:
        """导入或复用本地 completed report，并通过 Host 读取问题答案。

        参数:
            request: 本地 PDF 阅读请求。

        返回:
            ReadLocalReportResult；Agent 业务失败保留在 agent_result.failure。

        异常:
            DocumentToolError: 透传 PDF、repository、Docling conversion 或 parser health
                的稳定失败分类。
        """

        prepared = self._prepare_completed_report(request)
        document_id = prepared.import_result.identity.document_id
        tool_service = FundDocumentToolService({document_id: prepared.store})
        host = self._host_factory(tool_service)
        routed = self._run_with_query_candidates(
            host=host,
            document_id=document_id,
            query=request.query,
        )
        return ReadLocalReportResult(
            document_id=document_id,
            agent_result=routed.agent_result,
            routing_trace=routed.routing_trace,
        )

    def list_reports(self, request: ListReportsRequest) -> ListReportsResult:
        """列出本地 completed reports 的安全摘要。

        参数:
            request: 本地 catalog 列表请求。

        返回:
            ListReportsResult；无 catalog 时返回空列表。

        异常:
            DocumentToolError: catalog schema drift、不可读或 record 指向资源不可用时
                透传稳定失败分类。
        """

        document_ids = _catalog_document_ids(_catalog_path(request.work_dir))
        if not document_ids:
            return ListReportsResult(reports=())

        repository = _repository(request.work_dir)
        stores = {document_id: repository.load_store(document_id) for document_id in document_ids}
        tool_service = FundDocumentToolService(stores)
        reports = tool_service.list_reports(
            fund_code=request.fund_code,
            year=request.year,
            report_type=request.report_type,
        )
        if isinstance(reports, ToolFailure):
            return ListReportsResult(reports=(), failure=reports)
        return ListReportsResult(reports=reports)

    def _prepare_completed_report(self, request: ImportLocalReportRequest) -> _PreparedReport:
        """导入 PDF，并按 repository 口径恢复或创建 completed report。"""

        work_dir = Path(request.work_dir)
        provider = LocalPdfSourceProvider(_blob_root(work_dir))
        import_result = provider.import_pdf(
            PdfImportRequest(
                path=Path(request.pdf_path),
                fund_code=request.fund_code,
                fund_name=request.fund_name,
                year=request.year,
                report_type=request.report_type,
                share_class=request.share_class,
            )
        )

        repository = _repository(work_dir)
        document_id = import_result.identity.document_id
        try:
            store = repository.load_store(document_id)
        except DocumentToolError as exc:
            if exc.code is not FailureCode.NOT_FOUND:
                raise
            store = self._create_completed_store(
                request=request,
                provider=provider,
                import_result=import_result,
                repository=repository,
            )
        return _PreparedReport(import_result=import_result, store=store)

    def _create_completed_store(
        self,
        *,
        request: ImportLocalReportRequest,
        provider: LocalPdfSourceProvider,
        import_result: PdfImportResult,
        repository: FilesystemReportRepository,
    ) -> DoclingDocumentStore:
        """在 catalog missing 时复用现有 JSON 或执行一次 Docling conversion。"""

        document_id = import_result.identity.document_id
        docling_root = _docling_json_root(Path(request.work_dir))
        json_path = _docling_json_path(docling_root, document_id)
        if not json_path.exists():
            converter = self._converter_factory(docling_root)
            converter.convert_pdf(
                identity=import_result.identity,
                pdf_bytes=provider.blob_store.read_pdf(import_result.stored_blob_ref),
            )
        store = DoclingDocumentStore(identity=import_result.identity, json_path=json_path)
        repository.record_completed_report(
            identity=import_result.identity,
            stored_blob_ref=import_result.stored_blob_ref,
            docling_json_ref=make_docling_json_ref(document_id),
            parser_health=store.parser_health,
        )
        return store

    def _run_with_query_candidates(
        self,
        *,
        host: MinimalHost,
        document_id: str,
        query: str,
    ) -> _QueryRouteRun:
        """按 Service 受控 query profile 顺序调用既有 Host/Agent 路径。"""

        last_not_found: AgentRunResult | None = None
        attempts: list[QueryRouteAttempt] = []
        matched_results: list[AgentRunResult] = []
        matched_titles: set[str] = set()
        route_plan = _route_plan_for_query(query)
        for candidate_query in route_plan.candidate_queries:
            result = host.run(document_id=document_id, query=candidate_query)
            if result.failure is None:
                disclosure_titles = _matched_disclosure_titles(result, route_plan.disclosure_target)
                if route_plan.disclosure_target is not None and not disclosure_titles:
                    attempts.append(
                        QueryRouteAttempt(
                            query=candidate_query,
                            profile_name=route_plan.profile_name,
                            result_kind=_ROUTE_RESULT_FAILURE,
                            failure_code=FailureCode.NOT_FOUND,
                        )
                    )
                    last_not_found = _target_not_found_result(result)
                    continue
                if route_plan.require_all_target_candidates:
                    attempts.append(
                        QueryRouteAttempt(
                            query=candidate_query,
                            profile_name=route_plan.profile_name,
                            result_kind=_ROUTE_RESULT_SUCCESS,
                            failure_code=None,
                        )
                    )
                    if any(title not in matched_titles for title in disclosure_titles):
                        matched_results.append(result)
                        matched_titles.update(disclosure_titles)
                    continue
                attempts.append(
                    QueryRouteAttempt(
                        query=candidate_query,
                        profile_name=route_plan.profile_name,
                        result_kind=_ROUTE_RESULT_SUCCESS,
                        failure_code=None,
                    )
                )
                return _QueryRouteRun(agent_result=result, routing_trace=tuple(attempts))

            attempts.append(
                QueryRouteAttempt(
                    query=candidate_query,
                    profile_name=route_plan.profile_name,
                    result_kind=_ROUTE_RESULT_FAILURE,
                    failure_code=result.failure.code,
                )
            )
            if result.failure.code is not FailureCode.NOT_FOUND:
                return _QueryRouteRun(agent_result=result, routing_trace=tuple(attempts))
            last_not_found = result

        if route_plan.require_all_target_candidates:
            required_titles = set(route_plan.disclosure_target.acceptable_title_family) if route_plan.disclosure_target else set()
            if required_titles and required_titles.issubset(matched_titles):
                return _QueryRouteRun(
                    agent_result=_aggregate_agent_results(tuple(matched_results)),
                    routing_trace=tuple(attempts),
                )
            if matched_results:
                return _QueryRouteRun(
                    agent_result=_target_not_found_result(_aggregate_agent_results(tuple(matched_results))),
                    routing_trace=tuple(attempts),
                )

        if last_not_found is None:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 未生成候选 query")
        return _QueryRouteRun(agent_result=last_not_found, routing_trace=tuple(attempts))


def _default_host_factory(tool_service: FundDocumentToolService) -> MinimalHost:
    """按默认 deterministic Agent 装配最小 Host。"""

    return MinimalHost(MinimalFundDocumentAgent(tool_service))


def _repository(work_dir: Path) -> FilesystemReportRepository:
    """按 Service 受控工作目录构造 repository。"""

    root = Path(work_dir)
    return FilesystemReportRepository(
        catalog_path=_catalog_path(root),
        blob_root=_blob_root(root),
        docling_json_root=_docling_json_root(root),
    )


def _catalog_path(work_dir: Path) -> Path:
    """返回 completed report catalog 路径。"""

    return Path(work_dir) / CATALOG_FILENAME


def _blob_root(work_dir: Path) -> Path:
    """返回受控 PDF blob 根目录。"""

    return Path(work_dir) / PDF_BLOB_DIRNAME


def _docling_json_root(work_dir: Path) -> Path:
    """返回受控 Docling JSON 根目录。"""

    return Path(work_dir) / DOCLING_JSON_DIRNAME


def _docling_json_path(docling_root: Path, document_id: str) -> Path:
    """返回 Service 内部受控 Docling JSON 路径。"""

    return Path(docling_root) / document_id / f"{document_id}{DOCLING_JSON_SUFFIX}"


def _single_report_summary(document_id: str, store: DoclingDocumentStore) -> ReportSummary:
    """通过 FundDocumentToolService 生成单份安全 report summary。"""

    reports = FundDocumentToolService({document_id: store}).list_reports()
    if isinstance(reports, ToolFailure) or not reports:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "report summary 暂不可用")
    return reports[0]


def _candidate_queries_for_query(query: str) -> tuple[str, ...]:
    """按 hardcoded profile 为用户 query 生成受控候选 query。"""

    return _route_plan_for_query(query).candidate_queries


def _route_plan_for_query(query: str) -> _QueryRoutePlan:
    """返回 query 对应的 Service routing plan，不做开放语义理解。"""

    for profile in _validated_query_profiles():
        if query in profile.aliases:
            return _QueryRoutePlan(
                profile_name=profile.name,
                candidate_queries=_bounded_unique_candidates((query, *profile.fallback_candidates)),
                disclosure_target=profile.disclosure_target,
                require_all_target_candidates=profile.require_all_target_candidates,
            )
    return _QueryRoutePlan(profile_name=None, candidate_queries=(query,), disclosure_target=None)


def _validated_query_profiles() -> tuple[_ControlledQueryProfile, ...]:
    """校验受控 routing 配置，异常时映射为 schema_drift。"""

    seen_aliases: set[str] = set()
    seen_targets: set[str] = set()
    for profile in CONTROLLED_QUERY_PROFILES:
        if not profile.name or not profile.aliases or not profile.fallback_candidates:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 配置不完整")
        _validate_disclosure_target(profile.disclosure_target, seen_targets)
        if 1 + len(profile.fallback_candidates) > _MAX_QUERY_CANDIDATES:
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 候选过多")
        if profile.require_all_target_candidates and len(profile.fallback_candidates) != len(
            profile.disclosure_target.acceptable_title_family
        ):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 多目标配置异常")
        for alias in profile.aliases:
            if not alias or alias in seen_aliases:
                raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing alias 配置异常")
            seen_aliases.add(alias)
        if len(set(profile.fallback_candidates)) != len(profile.fallback_candidates):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing candidate 配置异常")
        if any(not candidate for candidate in profile.fallback_candidates):
            raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing candidate 为空")
    return tuple(CONTROLLED_QUERY_PROFILES)


def _validate_disclosure_target(target: _ControlledDisclosureTarget, seen_targets: set[str]) -> None:
    """校验受控披露目标契约，异常时映射为 schema_drift。"""

    if not target.target_id or target.target_id in seen_targets:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled disclosure target 配置异常")
    seen_targets.add(target.target_id)
    if not target.allowed_evidence_kinds or not target.acceptable_title_family or not target.expected_citation_kinds:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled disclosure target 配置不完整")
    allowed = set(target.allowed_evidence_kinds)
    expected = set(target.expected_citation_kinds)
    if not expected.issubset(allowed):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled disclosure target citation 配置异常")
    if any(not title for title in target.acceptable_title_family):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled disclosure target title 配置为空")


def _matched_disclosure_titles(
    result: AgentRunResult,
    target: _ControlledDisclosureTarget | None,
) -> tuple[str, ...]:
    """返回 Agent 安全 answer 命中的受控披露标题族。"""

    if target is None:
        return ("__uncontrolled__",)
    citation_kinds = tuple(citation.locator.locator_kind for citation in result.citations)
    if not any(kind in target.expected_citation_kinds for kind in citation_kinds):
        return ()
    if not any(kind in target.allowed_evidence_kinds for kind in citation_kinds):
        return ()
    title_lines = _target_title_lines(result.answer)
    return tuple(
        title
        for title in target.acceptable_title_family
        if any(title in line for line in title_lines)
    )


def _aggregate_agent_results(results: tuple[AgentRunResult, ...]) -> AgentRunResult:
    """聚合同一受控 profile 的多个安全 Agent 成功结果。"""

    if not results:
        return AgentRunResult(
            answer="",
            citations=(),
            tool_trace=(),
            failure=ToolFailure(code=FailureCode.NOT_FOUND, message=_TARGET_NOT_FOUND_MESSAGE),
        )
    return AgentRunResult(
        answer="\n\n".join(result.answer for result in results if result.answer),
        citations=tuple(citation for result in results for citation in result.citations),
        tool_trace=tuple(trace for result in results for trace in result.tool_trace),
        failure=None,
    )


def _target_title_lines(answer: str) -> tuple[str, ...]:
    """从 Agent 安全 answer 中提取 section/table title 行用于 Service 目标判定。"""

    lines = tuple(line.strip() for line in answer.splitlines() if line.strip())
    if not lines:
        return ()

    title_lines: list[str] = [lines[0]]
    for line in lines:
        if line.startswith(_SECTION_TITLE_PREFIX) or line.startswith(_TABLE_TITLE_PREFIX):
            title_lines.append(line)

    for index, line in enumerate(lines):
        if line == _TABLE_BLOCK_HEADER and index + 1 < len(lines):
            title_lines.append(lines[index + 1])
            break
    return tuple(dict.fromkeys(title_lines))


def _target_not_found_result(result: AgentRunResult) -> AgentRunResult:
    """把未满足 target contract 的 Agent success 转成 Service fail-closed 结果。"""

    return AgentRunResult(
        answer="",
        citations=(),
        tool_trace=result.tool_trace,
        failure=ToolFailure(code=FailureCode.NOT_FOUND, message=_TARGET_NOT_FOUND_MESSAGE),
    )


def _bounded_unique_candidates(candidates: tuple[str, ...]) -> tuple[str, ...]:
    """保序去重并保证候选 query 总数不超过上限。"""

    unique_candidates = tuple(dict.fromkeys(candidates))
    if not unique_candidates or len(unique_candidates) > _MAX_QUERY_CANDIDATES:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "controlled query routing 候选不符合契约")
    return unique_candidates


def _catalog_document_ids(catalog_path: Path) -> tuple[str, ...]:
    """读取 catalog 中的 document_id 列表，不返回本地路径或 raw payload。"""

    if not Path(catalog_path).exists():
        return ()
    try:
        payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise DocumentToolError(FailureCode.UNAVAILABLE, "catalog 暂不可读") from exc
    except json.JSONDecodeError as exc:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog 不是有效 JSON") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog schema 不兼容")
    reports = payload.get("reports")
    if not isinstance(reports, dict):
        raise DocumentToolError(FailureCode.SCHEMA_DRIFT, "catalog reports 结构不符合契约")
    return tuple(sorted(str(document_id) for document_id in reports))
