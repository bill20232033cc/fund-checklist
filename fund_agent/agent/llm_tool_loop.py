"""fake/injected LLM 风格的受控工具调用循环。"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Protocol, TypeAlias

from fund_agent.agent.tool_loop import (
    AgentRunResult,
    ToolArgumentValue,
    ToolResultKind,
    ToolTraceEntry,
)
from fund_agent.agent.diagnostic_payload import build_diagnostic_payload
from fund_agent.agent.log_levels import verbose
from fund_agent.fund.document_tools.constants import FailureCode, LocatorKind, ToolName
from fund_agent.fund.document_tools.models import (
    Citation,
    ExcerptContent,
    Locator,
    SearchResult,
    SectionContent,
    TableContent,
    TableSummary,
    ToolFailure,
)
from fund_agent.agent.stream_events import StreamEvent, StreamEventType
from fund_agent.agent.context_budget import ContextBudgetState
from fund_agent.agent.tool_result import ToolResult as ToolResultEnvelope, project_for_llm
from fund_agent.fund.document_tools.service import FundDocumentToolService

logger = logging.getLogger(__name__)

ControlledToolOutput: TypeAlias = (
    "tuple[SearchResult, ...] | SectionContent | tuple[TableSummary, ...] | TableContent | ExcerptContent | AggregateMultiYearAnnualPerformanceResult"
)
LlmStep: TypeAlias = "ToolCall | FinalAnswer"
FakeStepFactory: TypeAlias = Callable[[tuple["ToolResult", ...]], LlmStep]

ALLOWED_LLM_TOOL_NAMES: frozenset[ToolName] = frozenset(
    {
        ToolName.SEARCH_DOCUMENT,
        ToolName.READ_SECTION,
        ToolName.LIST_TABLES,
        ToolName.READ_TABLE,
        ToolName.GET_EXCERPT,
        ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE,
    }
)
_MAX_LLM_STEPS = 12
_MAX_TABLE_ROWS = 8
_MAX_EVIDENCE_CHARS = 4096
_EVIDENCE_HEAD_CHARS = 3072
_EVIDENCE_TAIL_CHARS = 1024
# interactive 空结果强制收敛：search 连续 2 次 0 命中后不再等待模型。
_INTERACTIVE_EMPTY_SEARCH_CONVERGE_ANSWER = "未找到相关数据"
_INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT = 2
# interactive 终答质量：原文粘贴检测（连续重叠 ≥40 字符）与 ≤200 字硬约束（含截断兜底）。
_INTERACTIVE_FINAL_ANSWER_MAX_CHARS = 200
_INTERACTIVE_FINAL_ANSWER_TARGET_CHARS = 200
_INTERACTIVE_EVIDENCE_OVERLAP_MIN_CHARS = 40
_INTERACTIVE_SUMMARY_TRUNCATE_NOTE = "\n\n（内容过长，已截断为摘要）"
_INTERACTIVE_QUALITY_RETRY_MESSAGE = (
    "你的上一条回答粘贴了工具返回原文或超过 200 字，"
    "请用自己的话概括年报事实，首次回答不超过 200 字。"
)
_TOOL_NOT_ALLOWED_MESSAGE = "LLM 工具调用不被允许"
_TOOL_ARGUMENT_MESSAGE = "LLM 工具调用参数不完整"
_FAILED_CALL_SHORT_CIRCUIT_MESSAGE = "该调用此前已失败，不再重跑；请修改参数后重试或直接收尾"
_READ_TABLE_UNLISTED_MESSAGE = (
    "table_ref 未在当前已列出章节的表格中，请先 list_tables 并复制返回的表号"
)
_NO_EVIDENCE_MESSAGE = "LLM 最终回答缺少受控工具证据"
_MISSING_CITATION_MESSAGE = "LLM 最终回答缺少受控 citation"
_UNSUPPORTED_FACT_MESSAGE = "LLM 最终回答包含未由工具结果支持的关键事实"
_STEP_LIMIT_MESSAGE = "LLM 工具调用超过限制"
_UNAVAILABLE_MESSAGE = "LLM 工具循环暂不可用"
# 强指令词：无论是否处于引用上下文都 fail-closed。
_INVESTMENT_ADVICE_STRONG_KEYWORDS: frozenset[str] = frozenset(
    {
        "建议买入", "建议卖出", "建议加仓", "建议减仓",
        "推荐买入", "推荐卖出", "强烈建议", "强烈推荐", "强烈买入", "强烈卖出",
        "目标价", "预期收益", "预计涨幅", "预期回报",
    }
)
# 弱指令词：出现在年报引用上下文（50 字符窗口内含引用关键词）时豁免。
_INVESTMENT_ADVICE_QUOTE_EXEMPT_KEYWORDS: frozenset[str] = frozenset(
    {"买入", "卖出", "增持", "减持"}
)
_INVESTMENT_ADVICE_KEYWORDS: frozenset[str] = (
    _INVESTMENT_ADVICE_STRONG_KEYWORDS | _INVESTMENT_ADVICE_QUOTE_EXEMPT_KEYWORDS
)
# 事实性上下文词（决策 A）：弱词处于这些词 ±100 字符窗口内且无指令动词时视为年报事实描述。
_INVESTMENT_ADVICE_QUOTE_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "策略", "宣称", "原文", "摘录", "运作分析",
    "报告期内", "期末", "持仓", "重仓", "股票投资明细",
    "投资范围", "财务报表附注", "买入返售", "卖出回购", "基金合同",
)
_INVESTMENT_ADVICE_QUOTE_CONTEXT_WINDOW_CHARS = 100
# 指令动词（决策 A）：弱词窗口内出现任一指令动词时优先判定为操作建议。
# 使用复合指令形式，不用裸 应（避免误命中 应付/应计/应主要投资于 等年报事实表述）。
_INVESTMENT_ADVICE_DIRECTIVE_KEYWORDS: tuple[str, ...] = (
    "建议", "应当", "可考虑", "适合", "值得持有",
    "应买入", "应卖出", "应增持", "应减持",
)
_INVESTMENT_ADVICE_MESSAGE = "LLM 最终回答包含投资建议关键词"
_INVESTMENT_ADVICE_PREDICTION_KEYWORD = "预期收益"
# 精确匹配预测句式：负向断言排除年报标准术语 预期收益率 / 预期收益及预期风险。
_INVESTMENT_ADVICE_PREDICTION_PATTERN = re.compile(r"预期收益(?!率|及)")


def contains_investment_advice(text: str) -> bool:
    """统一投资建议检测（B1 决策 A 单一真源，runner 与 chat_service 共用）。

    强指令词（建议买入/强烈推荐/目标价等；预期收益 精确匹配预测句式，
    排除年报术语 预期收益率 / 预期收益及预期风险）命中即拦截；
    弱指令词（买入/卖出/增持/减持）按决策 A 判定：
    - 出现处 ±100 字符窗口内含指令动词（建议/应当/可考虑/适合/值得持有/应买入/应卖出/应增持/应减持）→ 拦截；
    - 否则窗口内含事实性上下文词（策略/报告期内/持仓/重仓/财务报表附注/基金合同 等）→ 放行；
    - 否则 → 拦截（fail-closed 兜底）。

    参数:
        text: 待检测文本。

    返回:
        判定为投资建议时返回 True，否则 False。
    """

    for keyword in _INVESTMENT_ADVICE_STRONG_KEYWORDS:
        if keyword == _INVESTMENT_ADVICE_PREDICTION_KEYWORD:
            matched = _INVESTMENT_ADVICE_PREDICTION_PATTERN.search(text) is not None
        else:
            matched = keyword in text
        if matched:
            return True
    for keyword in _INVESTMENT_ADVICE_QUOTE_EXEMPT_KEYWORDS:
        start = 0
        while True:
            kw_idx = text.find(keyword, start)
            if kw_idx < 0:
                break
            context_start = max(0, kw_idx - _INVESTMENT_ADVICE_QUOTE_CONTEXT_WINDOW_CHARS)
            context_end = min(
                len(text),
                kw_idx + len(keyword) + _INVESTMENT_ADVICE_QUOTE_CONTEXT_WINDOW_CHARS,
            )
            context_window = text[context_start:context_end]
            if any(dk in context_window for dk in _INVESTMENT_ADVICE_DIRECTIVE_KEYWORDS):
                return True  # 弱词 + 指令动词 → 操作建议
            if any(ck in context_window for ck in _INVESTMENT_ADVICE_QUOTE_CONTEXT_KEYWORDS):
                start = kw_idx + len(keyword)  # 年报事实描述 → 放行该出现处
                continue
            return True  # 无事实上下文词 → fail-closed 兜底拦截
    return False


def matched_investment_advice_terms(text: str) -> tuple[str, ...]:
    """返回 text 中命中的投资建议词元（与 contains_investment_advice 同判据，决策 A）。

    强指令词命中即收录；弱指令词在出现处窗口内含指令动词、或窗口内无事实性
    上下文词时收录（与 contains_investment_advice 的拦截条件一致）；
    结果按文本首次命中顺序排列，同一词元只收录一次。
    判定与 contains_investment_advice 保持一致：
    bool(matched_investment_advice_terms(text)) == contains_investment_advice(text)。

    参数:
        text: 待检测文本。

    返回:
        命中词元元组；无命中时为空元组。
    """

    hits: list[tuple[int, str]] = []
    for keyword in _INVESTMENT_ADVICE_STRONG_KEYWORDS:
        if keyword == _INVESTMENT_ADVICE_PREDICTION_KEYWORD:
            match = _INVESTMENT_ADVICE_PREDICTION_PATTERN.search(text)
            if match is not None:
                hits.append((match.start(), keyword))
        else:
            index = text.find(keyword)
            if index >= 0:
                hits.append((index, keyword))
    for keyword in _INVESTMENT_ADVICE_QUOTE_EXEMPT_KEYWORDS:
        start = 0
        while True:
            kw_idx = text.find(keyword, start)
            if kw_idx < 0:
                break
            context_start = max(0, kw_idx - _INVESTMENT_ADVICE_QUOTE_CONTEXT_WINDOW_CHARS)
            context_end = min(
                len(text),
                kw_idx + len(keyword) + _INVESTMENT_ADVICE_QUOTE_CONTEXT_WINDOW_CHARS,
            )
            context_window = text[context_start:context_end]
            if any(dk in context_window for dk in _INVESTMENT_ADVICE_DIRECTIVE_KEYWORDS):
                hits.append((kw_idx, keyword))
                break  # 指令动词上下文 → 该弱词命中
            if not any(ck in context_window for ck in _INVESTMENT_ADVICE_QUOTE_CONTEXT_KEYWORDS):
                hits.append((kw_idx, keyword))
                break  # 无事实上下文词 → 该弱词命中
            start = kw_idx + len(keyword)
    hits.sort(key=lambda item: (item[0], item[1]))
    return tuple(keyword for _, keyword in hits)


@dataclass(frozen=True)
class TokenUsage:
    """LLM API 单次调用 token 用量。

    参数:
        prompt_tokens: 输入消耗 token。
        completion_tokens: 输出消耗 token。
        total_tokens: 总 token（prompt + completion），缺省自动求和。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0 and (self.prompt_tokens or self.completion_tokens):
            object.__setattr__(self, "total_tokens", self.prompt_tokens + self.completion_tokens)

    def __add__(self, other: TokenUsage) -> TokenUsage:
        if not isinstance(other, TokenUsage):
            return NotImplemented
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True)
class ChatResponse:
    """LLM next_step 返回结果，包含 step 与 token usage。

    参数:
        step: 下一步行为（ToolCall 或 FinalAnswer）。
        usage: 本次调用的 token 用量；不可用时为 None。
    """

    step: ToolCall | FinalAnswer
    usage: TokenUsage | None = None


class LlmClientFailure(Exception):
    """LLM client 可分类失败。

    参数:
        code: 稳定失败分类。
        message: 安全错误信息；不得包含 provider raw body、API key 或私有路径。

    返回:
        runner 可识别并转为 AgentRunResult.failure 的异常。

    异常:
        构造时不抛出业务异常。
    """

    def __init__(self, code: FailureCode, message: str) -> None:
        """保存稳定失败分类和安全信息。"""

        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ToolCall:
    """LLM 请求调用 reading tool 的显式模型。

    参数:
        tool_name: 请求调用的工具名；runner 会先校验是否已知且被授权。
        document_id: public reading tools 使用的内容身份，必须等于本轮 run 的 document_id。
        query: search_document 的检索词。
        section_ref: read_section 或 list_tables 的章节引用。
        table_ref: read_table 的表格引用。
        locator: get_excerpt 使用的受控 locator。
        max_results: search_document 可选最大命中数。
        max_chars: read_section/get_excerpt 可选最大字符数。
        max_rows: read_table 可选最大行数。

    返回:
        不执行工具调用的不可变请求对象。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: ToolName | str
    document_id: str
    query: str | None = None
    section_ref: str | None = None
    table_ref: str | None = None
    locator: Locator | None = None
    max_results: int | None = None
    max_chars: int | None = None
    max_rows: int | None = None
    extra: dict[str, object] | None = None


@dataclass(frozen=True)
class ToolResult:
    """返回给 injected LLM client 的受控工具结果。

    参数:
        tool_name: 成功调用的工具名；失败反馈条目为被拒绝/失败的请求工具名。
        result: public reading tool 返回的受控数据模型；失败反馈条目为 None。
        citations: 从 result 中提取的 citation 元组；失败反馈条目为空。
        evidence_text: 从 result 中提取的有界文本证据；失败反馈条目为空字符串。
        failure: 工具失败分类与安全消息；成功时为 None。

    返回:
        不包含 raw PDF、raw Docling JSON、本地路径或 private loader 字段的结果对象。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: ToolName | str
    result: ControlledToolOutput | None = None
    citations: tuple[Citation, ...] = ()
    evidence_text: str = ""
    failure: ToolFailure | None = None


@dataclass(frozen=True)
class ToolResultWithMeta:
    """携带 remaining_budget 信息的 ToolResult 包装器。

    参数:
        result: 原始受控工具结果。
        remaining_budget: 剩余调用预算；缺省为 None。

    返回:
        不可变包装器。
    """

    result: ToolResult
    remaining_budget: int | None = None


@dataclass(frozen=True)
class FinalAnswer:
    """LLM 请求结束工具循环并提交最终回答。

    参数:
        answer: 最终回答文本。
        citations: LLM 声明使用的 citation，必须来自先前成功工具结果。
        key_facts: 回答中的关键事实；每条必须出现在 answer 和受控工具 evidence_text 中。

    返回:
        不可变最终回答请求。

    异常:
        本模型不抛出业务异常。
    """

    answer: str
    citations: tuple[Citation, ...]
    key_facts: tuple[str, ...]


class LlmClientProtocol(Protocol):
    """可注入 LLM client 的最小协议。

    参数:
        document_id: 本轮阅读的 public 内容身份。
        query: 用户查询。
        tool_results: 先前成功工具调用的受控结果。

    返回:
        下一步 ToolCall 或 FinalAnswer。

    异常:
        实现可以抛出异常；runner 会 fail-closed 为 unavailable。
    """

    def next_step(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: tuple[ToolResult, ...],
        remaining_budget: int | None = None,
    ) -> ChatResponse:
        """返回下一步 LLM 行为（含 token usage）。"""


class FakeLlmClient:
    """按脚本返回 ToolCall/FinalAnswer 的测试 LLM client。

    参数:
        steps: 固定步骤；元素可以是 ToolCall/FinalAnswer，也可以是根据已有 ToolResult
            生成下一步的 callable。

    返回:
        实现 LlmClientProtocol 的 fake client。

    异常:
        steps 耗尽时抛出 RuntimeError，由 runner 收敛为 unavailable。
    """

    def __init__(self, steps: Sequence[LlmStep | FakeStepFactory]) -> None:
        """保存脚本步骤。"""

        self._steps = tuple(steps)
        self._index = 0

    def next_step(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: tuple[ToolResult, ...],
        remaining_budget: int | None = None,
    ) -> ChatResponse:
        """返回脚本中的下一步，包装为 ChatResponse。"""

        del document_id, query, remaining_budget
        if self._index >= len(self._steps):
            raise RuntimeError("fake llm steps exhausted")
        step = self._steps[self._index]
        self._index += 1
        if callable(step):
            return ChatResponse(step=step(tool_results))
        return ChatResponse(step=step)


class LlmToolLoopRunner:
    """执行 fake/injected LLM 的受控 reading tool loop。

    参数:
        tool_service: FundDocumentToolService，是 LLM runner 访问基金文档的唯一边界。
        llm_client: 注入式 LLM client；本 runner 不连接外部模型 API。
        max_steps: 单轮最大 LLM step 数，防止无限循环。

    返回:
        可运行 ToolCall -> ToolResult -> FinalAnswer 闭环的 runner。

    异常:
        run 方法不向 Host/UI 抛出内部异常，失败写入 AgentRunResult.failure。
    """

    def __init__(
        self,
        *,
        tool_service: FundDocumentToolService,
        llm_client: LlmClientProtocol,
        max_steps: int = _MAX_LLM_STEPS,
        aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None,
        budget: ContextBudgetState | None = None,
        failed_call_keys: frozenset[tuple] | None = None,
    ) -> None:
        """初始化受控 LLM tool loop runner。

        参数:
            aggregate_handler: 可选回调，签名 (document_id, fund_code, requested_years,
                annual_report_documents, share_class)；document_id 由 runner 用 expected 注入。
            failed_call_keys: 跨轮已失败调用去重键集合（构造期注入）；run/run_stream
                可再按调用级覆盖。
        """

        self._tool_service = tool_service
        self._llm_client = llm_client
        self._max_steps = max_steps
        self._aggregate_handler = aggregate_handler
        self._budget = budget
        self._failed_call_keys = failed_call_keys

    def run(
        self,
        *,
        document_id: str,
        query: str,
        scene: str = "ask",
        candidate_queries: tuple[str, ...] | None = None,
        failed_call_keys: frozenset[tuple] | None = None,
    ) -> AgentRunResult:
        """运行 injected LLM 工具调用循环。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 用户查询。
            scene: 调用场景（"ask"/"interactive"/"generate"），影响 citation 校验
                策略与 read_table section 一致性校验（interactive 生效）。
            candidate_queries: 受控候选检索词（Service 层路由注入，interactive 场景
                空结果时 runner 自动重试；runner 不 import service，只消费该列表）。
            failed_call_keys: 跨轮已失败调用的去重键集合；LLM 请求命中的 key 直接
                短路（不调用工具、不消耗真实调用），追加失败标记 ToolResult。

        返回:
            AgentRunResult；成功时 answer/citations 通过 evidence/citation 校验。

        异常:
            不抛出 ToolFailure 或 LLM client 内部异常；失败写入 AgentRunResult.failure。
        """

        trace: list[ToolTraceEntry] = []
        verbose(
            logger,
            "LLM tool loop run 开始: %s",
            build_diagnostic_payload(
                message="LLM tool loop run 开始",
                document_id=document_id,
                query=query,
            ),
        )
        tool_results: list[ToolResult] = []
        seen_calls: dict[tuple, ToolResult] = {}
        round_failed_keys: list[tuple] = []
        effective_failed_call_keys = (
            failed_call_keys if failed_call_keys is not None else self._failed_call_keys
        )
        total_usage = TokenUsage()
        budget = self._budget
        empty_search_count = 0
        auto_retry_rounds_used = False
        used_search_queries: set[str] = set()
        listed_table_refs: frozenset[str] = frozenset()

        def _attach_failed_keys(result: AgentRunResult) -> AgentRunResult:
            """把本轮失败调用 key 附加到 AgentRunResult（无失败时保持默认空元组）。"""

            if not round_failed_keys:
                return result
            return replace(result, failed_call_keys=tuple(dict.fromkeys(round_failed_keys)))

        for i in range(self._max_steps):
            try:
                chat_response = self._llm_client.next_step(
                    document_id=document_id,
                    query=query,
                    tool_results=tuple(tool_results),
                    remaining_budget=self._max_steps - i,
                )
            except LlmClientFailure as exc:
                return _attach_failed_keys(
                    _failed_result(tuple(trace), exc.code, exc.safe_message, token_usage=total_usage)
                )
            except Exception:
                logger.warning("LLM tool loop run 未分类异常，fail-closed 为 unavailable", exc_info=True)
                return _attach_failed_keys(
                    _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE, token_usage=total_usage)
                )

            if chat_response.usage is not None:
                total_usage += chat_response.usage
                if budget is not None:
                    budget = budget.consume(chat_response.usage.total_tokens)

            step = chat_response.step
            if isinstance(step, FinalAnswer):
                if scene == "interactive":
                    step = _unwrap_final_answer_envelope(step)
                final = _final_result(step, tuple(tool_results), tuple(trace), token_usage=total_usage, scene=scene)
                if scene == "interactive":
                    final = self._apply_interactive_final_guards(
                        final=final,
                        document_id=document_id,
                        query=query,
                        tool_results=tool_results,
                        trace=trace,
                        total_usage=total_usage,
                        budget=budget,
                        scene=scene,
                    )
                return _attach_failed_keys(final)
            if isinstance(step, ToolCall):
                call_key = _dedup_key(step)
                if effective_failed_call_keys is not None and call_key in effective_failed_call_keys:
                    # 跨轮失败短路：不调用工具、不消耗真实调用，追加失败标记回喂 LLM。
                    short_circuit_result = _failure_tool_result(
                        step,
                        ToolFailure(
                            code=FailureCode.UNAVAILABLE,
                            message=_FAILED_CALL_SHORT_CIRCUIT_MESSAGE,
                        ),
                    )
                    tool_results.append(short_circuit_result)
                    seen_calls[call_key] = short_circuit_result
                    continue
                if call_key in seen_calls:
                    tool_results.append(seen_calls[call_key])
                    if scene == "interactive" and _coerce_tool_name(step.tool_name) is ToolName.SEARCH_DOCUMENT:
                        cached = seen_calls[call_key]
                        if _is_empty_search_result(cached):
                            empty_search_count += 1
                            if empty_search_count >= _INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT:
                                return _attach_failed_keys(
                                    _empty_search_converged_result(tuple(trace), token_usage=total_usage)
                                )
                        else:
                            empty_search_count = 0
                    continue
                tool_result = self._invoke_tool_call(
                    step,
                    expected_document_id=document_id,
                    trace=trace,
                    scene=scene,
                    listed_table_refs=listed_table_refs,
                )
                if isinstance(tool_result, ToolFailure):
                    # 失败回喂：转为带 failure 标记的 ToolResult，不终止整轮
                    round_failed_keys.append(call_key)
                    tool_result = _failure_tool_result(step, tool_result)
                    tool_results.append(tool_result)
                    seen_calls[call_key] = tool_result
                    if budget is not None:
                        tool_results = _cap_tool_results(tool_results, budget)
                    continue
                tool_results.append(tool_result)
                seen_calls[call_key] = tool_result
                if budget is not None:
                    tool_results = _cap_tool_results(tool_results, budget)
                if scene == "interactive" and _coerce_tool_name(step.tool_name) is ToolName.LIST_TABLES:
                    listed_table_refs |= _listed_table_refs(tool_result)
                if scene == "interactive" and _coerce_tool_name(step.tool_name) is ToolName.SEARCH_DOCUMENT:
                    listed_table_refs |= _search_hit_table_refs(tool_result)
                    search_query = step.query or ""
                    used_search_queries.add(search_query)
                    if _is_empty_search_result(tool_result):
                        empty_search_count += 1
                        if (
                            not auto_retry_rounds_used
                            and candidate_queries
                            and empty_search_count < _INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT
                        ):
                            next_candidate = _next_auto_retry_query(
                                candidate_queries, used_search_queries, query
                            )
                            if next_candidate is not None:
                                auto_call = ToolCall(
                                    tool_name=ToolName.SEARCH_DOCUMENT,
                                    document_id=document_id,
                                    query=next_candidate,
                                    max_results=step.max_results,
                                )
                                auto_key = _dedup_key(auto_call)
                                auto_result = self._invoke_tool_call(
                                    auto_call, expected_document_id=document_id, trace=trace
                                )
                                if isinstance(auto_result, ToolFailure):
                                    round_failed_keys.append(auto_key)
                                    auto_result = _failure_tool_result(auto_call, auto_result)
                                else:
                                    listed_table_refs |= _search_hit_table_refs(auto_result)
                                tool_results.append(auto_result)
                                seen_calls[auto_key] = auto_result
                                if budget is not None:
                                    tool_results = _cap_tool_results(tool_results, budget)
                                used_search_queries.add(next_candidate)
                                auto_retry_rounds_used = True
                                if _is_empty_search_result(auto_result):
                                    empty_search_count += 1
                                else:
                                    empty_search_count = 0
                        if empty_search_count >= _INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT:
                            return _attach_failed_keys(
                                _empty_search_converged_result(tuple(trace), token_usage=total_usage)
                            )
                    else:
                        empty_search_count = 0
                continue
            return _attach_failed_keys(
                _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE, token_usage=total_usage)
            )

        # max_steps 耗尽：用已收集证据拼成回答（降级）；降级产物跳过原文粘贴/超长重答，超长直接截断收尾（2026-08-13 方案 2）。
        force_result = _force_answer_from_evidence(tuple(trace), tuple(tool_results), token_usage=total_usage)
        if scene == "interactive":
            force_result = self._apply_interactive_final_guards(
                final=force_result,
                document_id=document_id,
                query=query,
                tool_results=tool_results,
                trace=trace,
                total_usage=total_usage,
                budget=budget,
                scene=scene,
                degraded=True,
            )
        return _attach_failed_keys(force_result)

    def run_stream(
        self,
        *,
        document_id: str,
        query: str,
        scene: str = "ask",
        candidate_queries: tuple[str, ...] | None = None,
        failed_call_keys: frozenset[tuple] | None = None,
    ) -> Iterator[StreamEvent]:
        """运行 LLM 工具调用循环并产出 StreamEvent 流。

        tool call/result → TOOL_EVENT
        final answer → CONTENT_DELTA + METADATA + DONE
        失败 → ERROR

        scene 为 interactive 时，read_table 的 table_ref 必须属于本轮
        list_tables 成功结果收集的表格集合（Fix C section 一致性校验）。
        """

        seq = 0

        yield StreamEvent(
            type=StreamEventType.METADATA,
            payload={"document_id": document_id, "query": query},
            sequence=seq,
        )
        seq += 1

        trace: list[ToolTraceEntry] = []
        verbose(
            logger,
            "LLM tool loop run_stream 开始: %s",
            build_diagnostic_payload(
                message="LLM tool loop run_stream 开始",
                document_id=document_id,
                query=query,
            ),
        )
        tool_results: list[ToolResult] = []
        seen_calls: dict[tuple, ToolResult] = {}
        effective_failed_call_keys = (
            failed_call_keys if failed_call_keys is not None else self._failed_call_keys
        )
        total_usage = TokenUsage()
        budget = self._budget
        empty_search_count = 0
        auto_retry_rounds_used = False
        used_search_queries: set[str] = set()
        listed_table_refs: frozenset[str] = frozenset()
        for i in range(self._max_steps):
            try:
                chat_response = self._llm_client.next_step(
                    document_id=document_id,
                    query=query,
                    tool_results=tuple(tool_results),
                    remaining_budget=self._max_steps - i,
                )
            except LlmClientFailure as exc:
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    payload={"code": exc.code.value, "message": exc.safe_message},
                    sequence=seq,
                )
                return
            except Exception:
                logger.warning("LLM tool loop run_stream 未分类异常，fail-closed 为 unavailable", exc_info=True)
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    payload={"code": FailureCode.UNAVAILABLE.value, "message": _UNAVAILABLE_MESSAGE},
                    sequence=seq,
                )
                return

            if chat_response.usage is not None:
                total_usage += chat_response.usage
                if budget is not None:
                    budget = budget.consume(chat_response.usage.total_tokens)

            step = chat_response.step
            if isinstance(step, FinalAnswer):
                if scene == "interactive":
                    step = _unwrap_final_answer_envelope(step)
                final = _final_result(step, tuple(tool_results), tuple(trace), token_usage=total_usage, scene=scene)
                if scene == "interactive":
                    final = self._apply_interactive_final_guards(
                        final=final,
                        document_id=document_id,
                        query=query,
                        tool_results=tool_results,
                        trace=trace,
                        total_usage=total_usage,
                        budget=budget,
                        scene=scene,
                    )
                if final.failure is not None:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        payload={"code": final.failure.code.value, "message": final.failure.message},
                        sequence=seq,
                    )
                    return
                yield StreamEvent(
                    type=StreamEventType.CONTENT_DELTA,
                    payload=final.answer,
                    sequence=seq,
                )
                seq += 1
                yield StreamEvent(
                    type=StreamEventType.METADATA,
                    payload={
                        "citations": [
                            {
                                "document_id": c.document_id,
                                "fund_code": c.fund_code,
                                "fund_name": c.fund_name,
                                "year": c.year,
                                "report_type": c.report_type,
                            }
                            for c in final.citations
                        ],
                        "tool_trace_count": len(final.tool_trace),
                    },
                    sequence=seq,
                )
                seq += 1
                yield StreamEvent(type=StreamEventType.DONE, payload=None, sequence=seq)
                return

            if isinstance(step, ToolCall):
                call_key = _dedup_key(step)
                if effective_failed_call_keys is not None and call_key in effective_failed_call_keys:
                    # 跨轮失败短路：不调用工具、不消耗真实调用，追加失败标记回喂 LLM。
                    short_circuit_result = _failure_tool_result(
                        step,
                        ToolFailure(
                            code=FailureCode.UNAVAILABLE,
                            message=_FAILED_CALL_SHORT_CIRCUIT_MESSAGE,
                        ),
                    )
                    tool_results.append(short_circuit_result)
                    seen_calls[call_key] = short_circuit_result
                    yield StreamEvent(
                        type=StreamEventType.TOOL_EVENT,
                        payload={
                            "phase": "result",
                            "tool_name": str(short_circuit_result.tool_name),
                            "failure_code": FailureCode.UNAVAILABLE.value,
                            "message": _FAILED_CALL_SHORT_CIRCUIT_MESSAGE,
                        },
                        sequence=seq,
                    )
                    seq += 1
                    continue
                if call_key in seen_calls:
                    tool_results.append(seen_calls[call_key])
                    if scene == "interactive" and _coerce_tool_name(step.tool_name) is ToolName.SEARCH_DOCUMENT:
                        cached = seen_calls[call_key]
                        if _is_empty_search_result(cached):
                            empty_search_count += 1
                            if empty_search_count >= _INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT:
                                yield from _empty_search_converged_events(trace, seq)
                                return
                        else:
                            empty_search_count = 0
                    continue
                yield StreamEvent(
                    type=StreamEventType.TOOL_EVENT,
                    payload={"phase": "call", "tool_name": str(step.tool_name)},
                    sequence=seq,
                )
                seq += 1
                tool_result = self._invoke_tool_call(
                    step,
                    expected_document_id=document_id,
                    trace=trace,
                    scene=scene,
                    listed_table_refs=listed_table_refs,
                )
                if isinstance(tool_result, ToolFailure):
                    # 失败回喂：发 TOOL_EVENT(result) 并继续循环，不在此处发 ERROR
                    tool_result = _failure_tool_result(step, tool_result)
                    tool_results.append(tool_result)
                    seen_calls[call_key] = tool_result
                    if budget is not None:
                        tool_results = _cap_tool_results(tool_results, budget)
                    yield StreamEvent(
                        type=StreamEventType.TOOL_EVENT,
                        payload={
                            "phase": "result",
                            "tool_name": str(tool_result.tool_name),
                            "failure_code": tool_result.failure.code.value,
                            "message": tool_result.failure.message,
                        },
                        sequence=seq,
                    )
                    seq += 1
                    continue
                tool_results.append(tool_result)
                seen_calls[call_key] = tool_result
                if budget is not None:
                    tool_results = _cap_tool_results(tool_results, budget)
                if scene == "interactive" and _coerce_tool_name(step.tool_name) is ToolName.LIST_TABLES:
                    listed_table_refs |= _listed_table_refs(tool_result)
                yield StreamEvent(
                    type=StreamEventType.TOOL_EVENT,
                    payload={
                        "phase": "result",
                        "tool_name": str(tool_result.tool_name),
                        "citation_count": len(tool_result.citations),
                        "evidence_length": len(tool_result.evidence_text),
                    },
                    sequence=seq,
                )
                seq += 1
                if scene == "interactive" and _coerce_tool_name(step.tool_name) is ToolName.SEARCH_DOCUMENT:
                    listed_table_refs |= _search_hit_table_refs(tool_result)
                    search_query = step.query or ""
                    used_search_queries.add(search_query)
                    if _is_empty_search_result(tool_result):
                        empty_search_count += 1
                        if (
                            not auto_retry_rounds_used
                            and candidate_queries
                            and empty_search_count < _INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT
                        ):
                            next_candidate = _next_auto_retry_query(
                                candidate_queries, used_search_queries, query
                            )
                            if next_candidate is not None:
                                auto_call = ToolCall(
                                    tool_name=ToolName.SEARCH_DOCUMENT,
                                    document_id=document_id,
                                    query=next_candidate,
                                    max_results=step.max_results,
                                )
                                auto_key = _dedup_key(auto_call)
                                yield StreamEvent(
                                    type=StreamEventType.TOOL_EVENT,
                                    payload={"phase": "call", "tool_name": str(auto_call.tool_name)},
                                    sequence=seq,
                                )
                                seq += 1
                                auto_result = self._invoke_tool_call(
                                    auto_call, expected_document_id=document_id, trace=trace
                                )
                                if isinstance(auto_result, ToolFailure):
                                    auto_result = _failure_tool_result(auto_call, auto_result)
                                else:
                                    listed_table_refs |= _search_hit_table_refs(auto_result)
                                tool_results.append(auto_result)
                                seen_calls[auto_key] = auto_result
                                if budget is not None:
                                    tool_results = _cap_tool_results(tool_results, budget)
                                used_search_queries.add(next_candidate)
                                auto_retry_rounds_used = True
                                if auto_result.failure is not None:
                                    yield StreamEvent(
                                        type=StreamEventType.TOOL_EVENT,
                                        payload={
                                            "phase": "result",
                                            "tool_name": str(auto_result.tool_name),
                                            "failure_code": auto_result.failure.code.value,
                                            "message": auto_result.failure.message,
                                        },
                                        sequence=seq,
                                    )
                                else:
                                    yield StreamEvent(
                                        type=StreamEventType.TOOL_EVENT,
                                        payload={
                                            "phase": "result",
                                            "tool_name": str(auto_result.tool_name),
                                            "citation_count": len(auto_result.citations),
                                            "evidence_length": len(auto_result.evidence_text),
                                        },
                                        sequence=seq,
                                    )
                                seq += 1
                                if _is_empty_search_result(auto_result):
                                    empty_search_count += 1
                                else:
                                    empty_search_count = 0
                        if empty_search_count >= _INTERACTIVE_EMPTY_SEARCH_CONVERGE_LIMIT:
                            yield from _empty_search_converged_events(trace, seq)
                            return
                    else:
                        empty_search_count = 0
                continue

            yield StreamEvent(
                type=StreamEventType.ERROR,
                payload={"code": FailureCode.UNAVAILABLE.value, "message": _UNAVAILABLE_MESSAGE},
                sequence=seq,
            )
            return

        # max_steps 耗尽：用已收集证据拼成回答（降级）；降级产物跳过原文粘贴/超长重答，超长直接截断收尾（2026-08-13 方案 2）。
        force_result = _force_answer_from_evidence(tuple(trace), tuple(tool_results), token_usage=total_usage)
        if scene == "interactive":
            force_result = self._apply_interactive_final_guards(
                final=force_result,
                document_id=document_id,
                query=query,
                tool_results=tool_results,
                trace=trace,
                total_usage=total_usage,
                budget=budget,
                scene=scene,
                degraded=True,
            )
        if force_result.failure:
            yield StreamEvent(
                type=StreamEventType.ERROR,
                payload={"code": force_result.failure.code.value, "message": force_result.failure.message},
                sequence=seq,
            )
            return
        seq += 1
        yield StreamEvent(
            type=StreamEventType.CONTENT_DELTA,
            payload=force_result.answer,
            sequence=seq,
        )
        seq += 1
        yield StreamEvent(
            type=StreamEventType.METADATA,
            payload={
                "citations": [asdict(c) for c in force_result.citations],
                "tool_trace": [asdict(t) for t in force_result.tool_trace],
            },
            sequence=seq,
        )
        seq += 1
        yield StreamEvent(
            type=StreamEventType.DONE,
            payload={},
            sequence=seq,
        )

    def _retry_final_answer_advice_guard(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: list[ToolResult],
        trace: list[ToolTraceEntry],
        total_usage: TokenUsage,
        budget: ContextBudgetState | None,
        scene: str,
        original: AgentRunResult,
    ) -> AgentRunResult:
        """interactive 终答投资建议守卫失败时最多重试 1 次（query 追加纠正指令）。

        仅 scene == "interactive" 且失败消息为投资建议关键词命中时调用；
        用同 document_id / 同 tool_results、query 追加纠正指令重新调用 next_step，
        新 FinalAnswer 仍走同一 _final_result 守卫。重试通过则返回新结果；
        重试后仍失败、重试未产出 FinalAnswer 或 next_step 异常时返回原失败结果
        （fail-closed，不改变其它失败类型语义）。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 原用户查询。
            tool_results: 已收集的工具结果（成功与失败回喂条目）。
            trace: 工具调用轨迹。
            total_usage: 已累计 token 用量。
            budget: 上下文预算状态；None 时不做预算消费。
            scene: 调用场景（仅 interactive 触发）。
            original: 守卫失败的原 AgentRunResult。

        返回:
            重试成功的新 AgentRunResult；否则返回 original。
        """

        retry_query = (
            f"{query}\n\n你的上一条回答被判定为包含投资建议措辞，"
            "请只陈述年报客观事实，以中性表述重新回答。"
        )
        try:
            chat_response = self._llm_client.next_step(
                document_id=document_id,
                query=retry_query,
                tool_results=tuple(tool_results),
                remaining_budget=max(0, self._max_steps - 1),
            )
        except Exception:
            logger.warning("投资建议重答未分类异常，回退原始结果", exc_info=True)
            return original
        if chat_response.usage is not None:
            total_usage += chat_response.usage
            if budget is not None:
                budget = budget.consume(chat_response.usage.total_tokens)
        retry_step = chat_response.step
        if not isinstance(retry_step, FinalAnswer):
            return original
        retry_step = _unwrap_final_answer_envelope(retry_step)
        retried = _final_result(
            retry_step,
            tuple(tool_results),
            tuple(trace),
            token_usage=total_usage,
            scene=scene,
        )
        if retried.failure is not None:
            return original
        return retried

    def _apply_interactive_final_guards(
        self,
        *,
        final: AgentRunResult,
        document_id: str,
        query: str,
        tool_results: list[ToolResult],
        trace: list[ToolTraceEntry],
        total_usage: TokenUsage,
        budget: ContextBudgetState | None,
        scene: str,
        degraded: bool = False,
    ) -> AgentRunResult:
        """interactive 终答守卫：投资建议有界重答 + 原文粘贴/超长有界重答 + 摘要截断。

        投资建议守卫失败时最多重试 1 次（既有语义，重试仍失败则 fail-closed）；
        正常 FinalAnswer 原文粘贴（answer 与任一 evidence 连续重叠 ≥40 字符）或
        answer >200 字时最多重答 1 次，重答后仍超标则截断为摘要格式（含省略说明 ≤200 字）。

        degraded 为 True（max_steps 耗尽的 force-answer 降级产物，2026-08-13 方案 2）时：
        投资建议拦截保留（命中仍走有界重答 1 次，仍失败则 fail-closed）；
        final.failure 非空原样返回；跳过原文粘贴/超长有界重答；
        answer >200 字直接截断为 ≤200 字摘要（含省略说明），≤200 字原样返回。

        参数:
            final: 已过 _final_result 的终答结果（interactive 方案 E，无证据校验）。
            document_id: public reading tools 使用的内容身份。
            query: 原用户查询。
            tool_results: 已收集的工具结果。
            trace: 工具调用轨迹。
            total_usage: 已累计 token 用量。
            budget: 上下文预算状态；None 时不做预算消费。
            scene: 调用场景（仅 interactive 触发）。
            degraded: 是否为 max_steps 耗尽的 force-answer 降级产物；True 时跳过
                原文粘贴/超长有界重答，超长直接截断收尾，投资建议拦截保留。

        返回:
            通过守卫的 AgentRunResult；守卫失败时 fail-closed。
        """
        if degraded and final.failure is None and contains_investment_advice(final.answer):
            # 降级产物命中投资建议：合成失败态走同一有界重答，仍失败则 fail-closed（安全红线）。
            final = _failed_result(
                tuple(trace),
                FailureCode.UNAVAILABLE,
                _INVESTMENT_ADVICE_MESSAGE,
                token_usage=total_usage,
            )
        if final.failure is not None and final.failure.message == _INVESTMENT_ADVICE_MESSAGE:
            final = self._retry_final_answer_advice_guard(
                document_id=document_id,
                query=query,
                tool_results=tool_results,
                trace=trace,
                total_usage=total_usage,
                budget=budget,
                scene=scene,
                original=final,
            )
            if final.failure is not None:
                return final
        if final.failure is not None:
            return final

        if degraded:
            if len(final.answer) > _INTERACTIVE_FINAL_ANSWER_MAX_CHARS:
                return replace(final, answer=_truncate_final_answer_summary(final.answer))
            return final

        if not _violates_final_answer_quality(final.answer, tool_results):
            return final

        retried = self._retry_final_answer_quality_guard(
            document_id=document_id,
            query=query,
            tool_results=tool_results,
            trace=trace,
            total_usage=total_usage,
            budget=budget,
            scene=scene,
        )
        if retried.failure is not None:
            return retried
        if _violates_final_answer_quality(retried.answer, tool_results):
            return replace(retried, answer=_truncate_final_answer_summary(retried.answer))
        return retried

    def _retry_final_answer_quality_guard(
        self,
        *,
        document_id: str,
        query: str,
        tool_results: list[ToolResult],
        trace: list[ToolTraceEntry],
        total_usage: TokenUsage,
        budget: ContextBudgetState | None,
        scene: str,
    ) -> AgentRunResult:
        """interactive 终答原文粘贴/超长守卫：最多重答 1 次（query 追加纠正指令）。

        用同 document_id / 同 tool_results、query 追加纠正指令重新调用 next_step，
        新 FinalAnswer 仍走同一 JSON 信封解包、_final_result 守卫与原文粘贴检测。
        重答未产出 FinalAnswer 或 next_step 异常时返回 fail-closed 失败结果。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 原用户查询。
            tool_results: 已收集的工具结果。
            trace: 工具调用轨迹。
            total_usage: 已累计 token 用量。
            budget: 上下文预算状态；None 时不做预算消费。
            scene: 调用场景（仅 interactive 触发）。

        返回:
            重答后的 AgentRunResult（仍可能触发截断或 fail-closed）。
        """

        retry_query = f"{query}\n\n{_INTERACTIVE_QUALITY_RETRY_MESSAGE}"
        try:
            chat_response = self._llm_client.next_step(
                document_id=document_id,
                query=retry_query,
                tool_results=tuple(tool_results),
                remaining_budget=max(0, self._max_steps - 1),
            )
        except Exception:
            logger.warning("终答质量重答未分类异常，fail-closed 为 unavailable", exc_info=True)
            return _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE, token_usage=total_usage)
        if chat_response.usage is not None:
            total_usage += chat_response.usage
            if budget is not None:
                budget = budget.consume(chat_response.usage.total_tokens)
        retry_step = chat_response.step
        if not isinstance(retry_step, FinalAnswer):
            return _failed_result(tuple(trace), FailureCode.UNAVAILABLE, _UNAVAILABLE_MESSAGE, token_usage=total_usage)
        retry_step = _unwrap_final_answer_envelope(retry_step)
        return _final_result(
            retry_step,
            tuple(tool_results),
            tuple(trace),
            token_usage=total_usage,
            scene=scene,
        )

    @staticmethod
    def wrap_results_for_llm(
        results: tuple[ToolResult, ...],
        *,
        budget: int | None = None,
    ) -> list[dict]:
        """将 runner ToolResult 列表转换为新信封格式的 LLM 投影。

        每个结果经 ToolResultEnvelope.success() 包裹后通过 project_for_llm() 投射，
        附加可选的 budget 信息。

        参数:
            results: runner 收集的旧 ToolResult 列表。
            budget: 可选的剩余调用预算。

        返回:
            LLM-facing 信封投影 dict 列表。
        """
        projected: list[dict] = []
        for r in results:
            if r.failure is not None:
                envelope = ToolResultEnvelope.error(
                    code=r.failure.code.value,
                    message=r.failure.message,
                )
            else:
                envelope = ToolResultEnvelope.success(
                    value={"tool_name": str(r.tool_name), "evidence": r.evidence_text},
                )
            projected.append(project_for_llm(envelope, budget=budget))
        return projected

    def _invoke_tool_call(
        self,
        call: ToolCall,
        *,
        expected_document_id: str,
        trace: list[ToolTraceEntry],
        scene: str | None = None,
        listed_table_refs: frozenset[str] | None = None,
    ) -> ToolResult | ToolFailure:
        """校验并执行单次 LLM 工具请求。

        参数:
            call: LLM 请求的工具调用。
            expected_document_id: 本轮 run 的内容身份；缺失时补全、不匹配时拒绝。
            trace: 工具调用轨迹（调用方持有，追加本次调用结果）。
            scene: 调用场景；interactive 时对 read_table 做 section 一致性校验。
            listed_table_refs: 本轮 list_tables 成功结果收集的 table_ref 集合；
                interactive 下 read_table 的 table_ref 必须属于该集合，否则
                not_found 拒绝（防止 LLM 猜测任意表号）。

        返回:
            成功工具结果或可分类 ToolFailure。

        异常:
            不向调用方抛出业务异常；失败返回 ToolFailure。
        """

        from fund_agent.service.extraction import AggregateMultiYearAnnualPerformanceResult

        tool_name = _coerce_tool_name(call.tool_name)
        trace_arguments = _trace_arguments(call)
        if tool_name is None or tool_name not in ALLOWED_LLM_TOOL_NAMES:
            trace.append(_trace_entry(call.tool_name, trace_arguments, "failure", FailureCode.UNAVAILABLE))
            return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_NOT_ALLOWED_MESSAGE)
        # document_id 缺失/空字符串时用 expected 补全；aggregate 也需 document_id，
        # 不再豁免注入（R5 live e2e 证据：aggregate 曾以 document_id='' 调用而失败）。
        if not call.document_id:
            call = replace(call, document_id=expected_document_id)
        if not _document_id_matches(call.document_id, expected_document_id):
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", FailureCode.UNAVAILABLE))
            return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_NOT_ALLOWED_MESSAGE)

        # Fix C：read_table section 一致性校验（仅 interactive，控制 blast radius）。
        # table_ref 必须来自本轮 list_tables 成功结果；未先 list_tables 的锚点表
        # 同样被拒（「table_ref 一律复制不猜测」），回喂后 LLM 会先 list_tables。
        if (
            scene == "interactive"
            and tool_name is ToolName.READ_TABLE
            and call.table_ref is not None
            and call.table_ref not in (listed_table_refs or frozenset())
        ):
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", FailureCode.NOT_FOUND))
            return ToolFailure(code=FailureCode.NOT_FOUND, message=_READ_TABLE_UNLISTED_MESSAGE)

        result = self._call_allowed_tool(tool_name, call, aggregate_handler=self._aggregate_handler)
        if isinstance(result, ToolFailure):
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", result.code))
            return result
        if isinstance(result, AggregateMultiYearAnnualPerformanceResult) and result.failure is not None:
            trace.append(_trace_entry(tool_name, trace_arguments, "failure", result.failure.code))
            return ToolFailure(code=result.failure.code, message=result.failure.message)

        trace.append(_trace_entry(tool_name, trace_arguments, "success", None))
        return _tool_result_from_output(tool_name, result)

    def _call_allowed_tool(
        self,
        tool_name: ToolName,
        call: ToolCall,
        *,
        aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None,
    ) -> ControlledToolOutput | ToolFailure:
        """按允许工具名分发到 FundDocumentToolService。"""

        if tool_name is ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE:
            if aggregate_handler is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_UNAVAILABLE_MESSAGE)
            extra = call.extra or {}
            fund_code = extra.get("fund_code")
            requested_years = extra.get("requested_years")
            annual_report_documents = extra.get("annual_report_documents")
            if fund_code is None or requested_years is None or annual_report_documents is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return aggregate_handler(
                call.document_id,
                fund_code,
                requested_years,
                annual_report_documents,
                extra.get("share_class"),
            )
        if tool_name is ToolName.SEARCH_DOCUMENT:
            if call.query is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.search_document(
                call.document_id,
                call.query,
                max_results=call.max_results,
            )
        if tool_name is ToolName.READ_SECTION:
            if call.section_ref is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.read_section(
                call.document_id,
                call.section_ref,
                max_chars=call.max_chars,
            )
        if tool_name is ToolName.LIST_TABLES:
            return self._tool_service.list_tables(call.document_id, within_section_ref=call.section_ref)
        if tool_name is ToolName.READ_TABLE:
            if call.table_ref is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.read_table(
                call.document_id,
                call.table_ref,
                max_rows=call.max_rows or _MAX_TABLE_ROWS,
            )
        if tool_name is ToolName.GET_EXCERPT:
            if call.locator is None:
                return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_ARGUMENT_MESSAGE)
            return self._tool_service.get_excerpt(call.document_id, call.locator, max_chars=call.max_chars)
        return ToolFailure(code=FailureCode.UNAVAILABLE, message=_TOOL_NOT_ALLOWED_MESSAGE)



def _listed_table_refs(result: ToolResult) -> frozenset[str]:
    """从 list_tables 成功结果中收集 table_ref 集合（read_table section 一致性校验）。

    参数:
        result: list_tables 工具成功结果（result 为 TableSummary 元组）。

    返回:
        成功结果的 table_ref frozenset；非 list_tables 结果返回空集合。
    """

    output = result.result
    if not isinstance(output, tuple):
        return frozenset()
    return frozenset(
        summary.table_ref
        for summary in output
        if isinstance(summary, TableSummary) and summary.table_ref
    )


def _search_hit_table_refs(result: ToolResult) -> frozenset[str]:
    """从 search_document 成功结果中收集命中表的 table_ref（read_table section 一致性校验）。

    search_document 的 SearchResult 也携带合法 table_ref（table-backed first hit），
    与 list_tables 结果共用同一放行集合，避免误伤 search -> read_table 合法流。

    参数:
        result: search_document 工具成功结果（result 为 SearchResult 元组）。

    返回:
        成功结果中命中表的 table_ref frozenset；非 search 结果返回空集合。
    """

    output = result.result
    if not isinstance(output, tuple):
        return frozenset()
    return frozenset(
        hit.table_ref
        for hit in output
        if isinstance(hit, SearchResult) and hit.table_ref
    )


def _is_empty_search_result(result: ToolResult) -> bool:
    """判断 search_document 结果是否为 0 命中（成功但无 evidence/citation）。"""

    return not result.citations and not result.evidence_text.strip()


def _next_auto_retry_query(
    candidates: tuple[str, ...],
    used_queries: set[str],
    original_query: str,
) -> str | None:
    """返回下一个未尝试的受控候选检索词，优先非原始 query 的受控词。"""

    for candidate in candidates:
        if candidate != original_query and candidate not in used_queries:
            return candidate
    for candidate in candidates:
        if candidate not in used_queries:
            return candidate
    return None


def _empty_search_converged_result(
    trace: tuple[ToolTraceEntry, ...],
    *,
    token_usage: TokenUsage | None = None,
) -> AgentRunResult:
    """interactive 连续空结果强制收敛：返回「未找到相关数据」final（不依赖模型）。"""

    return AgentRunResult(
        answer=_INTERACTIVE_EMPTY_SEARCH_CONVERGE_ANSWER,
        citations=(),
        tool_trace=trace,
        failure=None,
        token_usage=token_usage,
    )


def _empty_search_converged_events(
    trace: tuple[ToolTraceEntry, ...],
    seq: int,
) -> Iterator[StreamEvent]:
    """interactive 空结果强制收敛的 StreamEvent 序列（CONTENT_DELTA + METADATA + DONE）。"""

    yield StreamEvent(
        type=StreamEventType.CONTENT_DELTA,
        payload=_INTERACTIVE_EMPTY_SEARCH_CONVERGE_ANSWER,
        sequence=seq,
    )
    yield StreamEvent(
        type=StreamEventType.METADATA,
        payload={"citations": [], "tool_trace_count": len(trace)},
        sequence=seq + 1,
    )
    yield StreamEvent(type=StreamEventType.DONE, payload=None, sequence=seq + 2)


def _has_long_evidence_overlap(answer: str, evidence: str) -> bool:
    """判断 answer 与 evidence 是否存在 ≥40 字符连续重叠（原文粘贴检测）。"""

    min_chars = _INTERACTIVE_EVIDENCE_OVERLAP_MIN_CHARS
    if len(answer) < min_chars:
        return False
    limit = len(answer) - min_chars + 1
    return any(answer[start : start + min_chars] in evidence for start in range(limit))


def _violates_final_answer_quality(
    answer: str,
    tool_results: list[ToolResult] | tuple[ToolResult, ...],
) -> bool:
    """interactive 终答质量违规：answer >200 字或与任一 evidence 连续重叠 ≥40 字符。"""

    if len(answer) > _INTERACTIVE_FINAL_ANSWER_MAX_CHARS:
        return True
    return any(
        result.evidence_text and _has_long_evidence_overlap(answer, result.evidence_text)
        for result in tool_results
    )


def _truncate_final_answer_summary(answer: str) -> str:
    """终答仍超标时截断为摘要格式，保证含省略说明 ≤200 字。

    正文截断长度为 200-len(note)，note 文案不包含具体字数（避免与截断长度不一致）。
    """

    if len(answer) <= _INTERACTIVE_FINAL_ANSWER_TARGET_CHARS:
        return answer
    body_limit = _INTERACTIVE_FINAL_ANSWER_TARGET_CHARS - len(_INTERACTIVE_SUMMARY_TRUNCATE_NOTE)
    return answer[:body_limit] + _INTERACTIVE_SUMMARY_TRUNCATE_NOTE


def _optional_envelope_str(payload: dict, key: str) -> str | None:
    """从终答 JSON 信封取可选字符串字段；非空字符串才返回。"""

    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _optional_envelope_int(payload: dict, key: str) -> int | None:
    """从终答 JSON 信封取可选整数字段；bool 视为无效。"""

    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _locator_from_envelope(payload: object) -> Locator | None:
    """从终答 JSON 信封解析 locator；结构不完整时返回 None。"""

    if not isinstance(payload, dict):
        return None
    try:
        return Locator(
            document_id=str(payload["document_id"]),
            locator_kind=LocatorKind(str(payload["locator_kind"])),
            section_ref=_optional_envelope_str(payload, "section_ref"),
            table_ref=_optional_envelope_str(payload, "table_ref"),
            page_no=_optional_envelope_int(payload, "page_no"),
            page_range=None,
            internal_ref=None,
            internal_ref_available=False,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _citations_from_envelope(payload: dict) -> tuple[Citation, ...]:
    """从终答 JSON 信封解析 citation（尽力而为，跳过无法还原的条目）。"""

    raw = payload.get("citations")
    if not isinstance(raw, list):
        return ()
    citations: list[Citation] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        locator = _locator_from_envelope(item.get("locator"))
        if locator is None:
            continue
        try:
            citations.append(
                Citation(
                    document_id=str(item["document_id"]),
                    fund_code=str(item["fund_code"]),
                    fund_name=str(item["fund_name"]),
                    year=int(item["year"]),
                    report_type=str(item["report_type"]),
                    locator=locator,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(citations)


def _key_facts_from_envelope(payload: dict) -> tuple[str, ...]:
    """从终答 JSON 信封解析 key_facts（尽力而为，只收非空标量）。"""

    raw = payload.get("key_facts")
    if not isinstance(raw, list):
        return ()
    return tuple(
        str(item)
        for item in raw
        if isinstance(item, (str, int, float)) and str(item).strip()
    )


def _unwrap_final_answer_envelope(final_answer: FinalAnswer) -> FinalAnswer:
    """interactive 终答 JSON 信封解包（answer 为 JSON 且含 answer 字段时提取展示文本）。

    模型有时把整段 JSON 信封写进 answer（纯 JSON 或 ```json 代码块），
    此处兜底：提取 answer 字段作为展示文本，citations/key_facts 解析后保留在
    FinalAnswer（citations 随后随 AgentRunResult 落盘）。
    """

    content = final_answer.answer.strip()
    if not content:
        return final_answer
    candidate = content
    if content.startswith("```"):
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return final_answer
    if not isinstance(payload, dict):
        return final_answer
    answer_value = payload.get("answer")
    if not isinstance(answer_value, str) or not answer_value.strip():
        return final_answer
    citations = final_answer.citations or _citations_from_envelope(payload)
    key_facts = final_answer.key_facts or _key_facts_from_envelope(payload)
    return FinalAnswer(answer=answer_value.strip(), citations=citations, key_facts=key_facts)


def _final_result(
    final_answer: FinalAnswer,
    tool_results: tuple[ToolResult, ...],
    trace: tuple[ToolTraceEntry, ...],
    *,
    token_usage: TokenUsage | None = None,
    scene: str = "ask",
) -> AgentRunResult:
    """校验最终回答证据与 citation 后构造 AgentRunResult。

    scene == "interactive" 时跳过 evidence + citation 校验（方案 E），
    仅保留投资建议关键词检测。
    """

    # 投资建议检测（fail-closed，所有 scene 生效）
    # "建议关注"、"需持续跟踪" 不触发；
    # 强词正则与弱词引用上下文豁免逻辑见 contains_investment_advice（单一真源）。
    answer_text = final_answer.answer
    if contains_investment_advice(answer_text):
        return _failed_result(trace, FailureCode.UNAVAILABLE, _INVESTMENT_ADVICE_MESSAGE, token_usage=token_usage)

    if scene == "interactive":
        return AgentRunResult(
            answer=final_answer.answer,
            citations=tuple(_public_citation(citation) for citation in final_answer.citations),
            tool_trace=trace,
            failure=None,
            token_usage=token_usage,
            key_facts=final_answer.key_facts,
        )

    evidence_texts = tuple(result.evidence_text for result in tool_results if result.evidence_text.strip())
    if not evidence_texts:
        return _failed_result(trace, FailureCode.UNAVAILABLE, _NO_EVIDENCE_MESSAGE, token_usage=token_usage)

    if not final_answer.citations:
        return _failed_result(trace, FailureCode.UNAVAILABLE, _MISSING_CITATION_MESSAGE, token_usage=token_usage)

    citation_evidence = tuple(
        (_citation_key(citation), result.evidence_text)
        for result in tool_results
        for citation in result.citations
        if citation.locator.locator_kind in {LocatorKind.SECTION, LocatorKind.TABLE, LocatorKind.EXCERPT}
    )
    controlled_citation_keys = {key for key, _ in citation_evidence}
    final_citation_keys = {_citation_key(citation) for citation in final_answer.citations}
    if not controlled_citation_keys or any(
        _citation_key(citation) not in controlled_citation_keys for citation in final_answer.citations
    ):
        return _failed_result(trace, FailureCode.UNAVAILABLE, _MISSING_CITATION_MESSAGE, token_usage=token_usage)

    # key_facts 精确子串校验已移除：LLM 改述导致假阳性过高。citation 校验已确保回答有据可依。

    return AgentRunResult(
        answer=final_answer.answer,
        citations=tuple(_public_citation(citation) for citation in final_answer.citations),
        tool_trace=trace,
        failure=None,
        token_usage=token_usage,
        key_facts=final_answer.key_facts,
    )


def _tool_result_from_output(tool_name: ToolName, result: ControlledToolOutput) -> ToolResult:
    """从 public tool result 中提取 citations 和 evidence_text（截断至 4096 字符）。"""

    from fund_agent.service.extraction import AggregateMultiYearAnnualPerformanceResult

    tool_result: ToolResult
    if isinstance(result, AggregateMultiYearAnnualPerformanceResult):
        tool_result = ToolResult(
            tool_name=tool_name,
            result=result,
            citations=_aggregate_citations(result),
            evidence_text=_aggregate_evidence_text(result),
        )
    elif isinstance(result, tuple):
        if result and isinstance(result[0], SearchResult):
            search_results = tuple(item for item in result if isinstance(item, SearchResult))
            tool_result = ToolResult(
                tool_name=tool_name,
                result=search_results,
                citations=tuple(item.citation for item in search_results),
                evidence_text="\n".join(item.excerpt for item in search_results),
            )
        else:
            table_summaries = tuple(item for item in result if isinstance(item, TableSummary))
            tool_result = ToolResult(
                tool_name=tool_name,
                result=table_summaries,
                citations=(),
                evidence_text="\n".join(item.caption or "" for item in table_summaries),
            )
    elif isinstance(result, SectionContent):
        tool_result = ToolResult(
            tool_name=tool_name,
            result=result,
            citations=(result.citation,),
            evidence_text=f"{result.title}\n{result.text}",
        )
    elif isinstance(result, TableContent):
        tool_result = ToolResult(
            tool_name=tool_name,
            result=result,
            citations=(result.citation,),
            evidence_text=_table_evidence_text(result),
        )
    else:
        tool_result = ToolResult(
            tool_name=tool_name,
            result=result,
            citations=(result.citation,),
            evidence_text=result.text,
        )

    return ToolResult(
        tool_name=tool_result.tool_name,
        result=tool_result.result,
        citations=tool_result.citations,
        evidence_text=_truncate_evidence(tool_result.evidence_text),
    )


def _truncate_evidence(text: str) -> str:
    """截断 evidence_text 至 4096 字符，保留开头 3072 + 结尾 1024。"""
    if len(text) <= _MAX_EVIDENCE_CHARS:
        return text
    head = text[:_EVIDENCE_HEAD_CHARS]
    tail = text[-_EVIDENCE_TAIL_CHARS:]
    skipped = len(text) - _EVIDENCE_HEAD_CHARS - _EVIDENCE_TAIL_CHARS
    return f"{head}\n[...已截断 {skipped} 字符...]\n{tail}"


def _table_evidence_text(table: TableContent) -> str:
    """把表格 tool result 转换为有界证据文本。"""

    lines = [table.caption or ""]
    lines.extend(" | ".join(cell for cell in row if cell) for row in table.rows)
    return "\n".join(line for line in lines if line)


def _coerce_tool_name(tool_name: ToolName | str) -> ToolName | None:
    """把 LLM 输出的工具名转换为已知 ToolName（仅格式归一化，不做语义映射）。

    归一化规则（有界）：
    - 去除首尾空白；
    - 去除尾部括号参数（如 `search_document(max_results=5)` -> `search_document`）。
    仍不匹配已知工具名时返回 None，由调用方按未知工具 fail-closed；
    禁止做语义级别名映射（如 "search" -> search_document），防止静默扩大工具面。

    参数:
        tool_name: LLM 请求的工具名。

    返回:
        已知 ToolName；未知工具名返回 None。
    """

    if isinstance(tool_name, ToolName):
        return tool_name
    raw = str(tool_name).strip()
    if raw.endswith(")") and "(" in raw:
        # 只去除紧贴名称的尾部括号参数段
        raw = raw[: raw.find("(")].strip()
    if not raw:
        return None
    try:
        return ToolName(raw)
    except ValueError:
        return None


def _normalize_document_id(doc_id: str) -> str:
    """Normalize a document_id for prefix-matching comparison.

    Strips whitespace so that variant forms of the same document_id
    can be compared with startswith-based prefix matching.
    """
    return doc_id.strip()


def _document_id_matches(call_doc_id: str, expected_doc_id: str) -> bool:
    """Check if two document_ids match using prefix-based comparison.

    Returns True if the LLM's call_doc_id starts with expected_doc_id,
    allowing the LLM to add suffixes but not to shorten the id.
    """
    norm_call = _normalize_document_id(call_doc_id)
    norm_expected = _normalize_document_id(expected_doc_id)
    return norm_call == norm_expected or norm_call.startswith(norm_expected)


def _make_hashable(value: object) -> object:
    """递归转换 value 为 hashable 类型。"""
    if isinstance(value, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_make_hashable(item) for item in value)
    return value


_CJK_PUNCTUATION_REMOVE = str.maketrans("", "", "，。、；：？！（）［］【】《》“”‘’—…·　")


def _normalize_query_text(query: str) -> str:
    """归一化检索词（去重键单一真源，可单测）。

    去除全部空白（含全角空格）与 CJK 标点，使语义相近的不同
    措辞（如「持有本基金」「持有本基金？」）映射到同一去重键。
    """

    return "".join(query.split()).translate(_CJK_PUNCTUATION_REMOVE)


def _dedup_key(call: ToolCall) -> tuple:
    """构造 tool call 去重键（轮内 seen_calls 与跨轮 failed_call_keys 共用）。

    工具级归一化（D4-二）：
    - search_document → (tool, document_id, 归一化 query)；
    - read_section → (tool, document_id, section_ref, max_chars)；
    - read_table → (tool, document_id, table_ref, max_rows)；
    - get_excerpt → (tool, document_id, locator_key)；
    - aggregate_multi_year_annual_performance → (tool, fund_code, years, share_class)；
    其余工具保留全参数比较（兼容既有轮内去重语义）。
    """

    tool_name = _coerce_tool_name(call.tool_name)
    if tool_name is ToolName.SEARCH_DOCUMENT:
        return (str(tool_name), call.document_id, _normalize_query_text(call.query or ""))
    if tool_name is ToolName.READ_SECTION:
        return (str(tool_name), call.document_id, call.section_ref, call.max_chars)
    if tool_name is ToolName.READ_TABLE:
        return (str(tool_name), call.document_id, call.table_ref, call.max_rows)
    if tool_name is ToolName.GET_EXCERPT:
        locator_key = None
        if call.locator is not None:
            locator_key = (
                call.locator.locator_kind.value,
                call.locator.section_ref,
                call.locator.table_ref,
                call.locator.page_no,
            )
        return (str(tool_name), call.document_id, locator_key)
    if tool_name is ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE:
        extra = call.extra or {}
        requested_years = extra.get("requested_years")
        if isinstance(requested_years, (list, tuple)):
            years_key = tuple(str(year) for year in sorted(requested_years, key=str))
        else:
            years_key = (str(requested_years),)
        return (
            str(tool_name),
            extra.get("fund_code"),
            years_key,
            extra.get("share_class") or "",
        )
    locator_key = None
    if call.locator is not None:
        locator_key = (
            call.locator.locator_kind.value,
            call.locator.section_ref,
            call.locator.table_ref,
            call.locator.page_no,
        )
    extra_key = None
    if call.extra is not None:
        extra_key = tuple(sorted(
            (k, _make_hashable(v)) for k, v in call.extra.items()
        ))
    return (
        str(call.tool_name),
        call.document_id,
        call.query,
        call.section_ref,
        call.table_ref,
        call.max_results,
        call.max_chars,
        call.max_rows,
        locator_key,
        extra_key,
    )


def _trace_arguments(call: ToolCall) -> dict[str, ToolArgumentValue]:
    """构造不含 raw/private payload 的 trace 参数。"""

    arguments: dict[str, ToolArgumentValue] = {"document_id": call.document_id}
    if call.query is not None:
        arguments["query"] = call.query
    if call.section_ref is not None:
        arguments["section_ref"] = call.section_ref
    if call.table_ref is not None:
        arguments["table_ref"] = call.table_ref
    if call.max_results is not None:
        arguments["max_results"] = call.max_results
    if call.max_chars is not None:
        arguments["max_chars"] = call.max_chars
    if call.max_rows is not None:
        arguments["max_rows"] = call.max_rows
    if call.locator is not None:
        arguments["locator_kind"] = call.locator.locator_kind.value
        if call.locator.section_ref is not None:
            arguments["locator_section_ref"] = call.locator.section_ref
        if call.locator.table_ref is not None:
            arguments["locator_table_ref"] = call.locator.table_ref
    if call.extra is not None:
        for key, value in call.extra.items():
            if isinstance(value, (str, int)):
                arguments[key] = value
    return arguments


def _trace_entry(
    tool_name: ToolName | str,
    arguments: dict[str, ToolArgumentValue],
    result_kind: ToolResultKind,
    failure_code: FailureCode | None,
) -> ToolTraceEntry:
    """构造 LLM runner 的工具调用轨迹。"""

    return ToolTraceEntry(
        tool_name=tool_name,
        arguments=arguments,
        result_kind=result_kind,
        failure_code=failure_code,
    )


def _failed_result(
    trace: tuple[ToolTraceEntry, ...],
    code: FailureCode,
    message: str,
    *,
    token_usage: TokenUsage | None = None,
) -> AgentRunResult:
    """构造 fail-closed 的 AgentRunResult。"""

    return AgentRunResult(
        answer="",
        citations=(),
        tool_trace=trace,
        failure=ToolFailure(code=code, message=message),
        token_usage=token_usage,
    )




def _cap_tool_results(
    tool_results: list[ToolResult],
    budget: ContextBudgetState,
) -> list[ToolResult]:
    """当预算超过硬限制时按比例截断工具结果的 evidence_text。"""
    if not budget.is_above_hard_limit() or not tool_results:
        return tool_results

    total_chars = sum(len(r.evidence_text) for r in tool_results)
    remaining = budget.remaining_budget
    if remaining <= 0 or total_chars <= 0:
        return []

    result: list[ToolResult] = []
    for r in tool_results:
        allocated = max(0, int(len(r.evidence_text) * remaining / total_chars))
        if r.failure is not None or allocated >= len(r.evidence_text):
            # 失败反馈条目原样保留（evidence 为空且不可截断）
            result.append(r)
        elif allocated > 0:
            result.append(
                ToolResult(
                    tool_name=r.tool_name,
                    result=r.result,
                    citations=(),
                    evidence_text=r.evidence_text[:allocated],
                )
            )
    return result


def _failure_tool_result(call: ToolCall, failure: ToolFailure) -> ToolResult:
    """把 ToolFailure 转换为带 failure 标记的 ToolResult（失败回喂，不终止整轮）。

    参数:
        call: 触发失败的 LLM 工具请求。
        failure: 工具失败分类与安全消息。

    返回:
        failure 非 None、无 evidence/citation 的 ToolResult；工具名取已归一化
        结果，未知工具保留原始请求名。
    """

    return ToolResult(
        tool_name=_coerce_tool_name(call.tool_name) or str(call.tool_name),
        result=None,
        citations=(),
        evidence_text="",
        failure=failure,
    )


def _force_answer_from_evidence(
    trace: tuple[ToolTraceEntry, ...],
    tool_results: tuple[ToolResult, ...],
    *,
    token_usage: TokenUsage | None = None,
) -> AgentRunResult:
    """max_steps 耗尽时，用已收集的 tool_results 拼成回答（降级策略）。

    不报错，返回已收集的证据文本作为回答。
    citation 从所有 tool_results 中聚合（用 _citation_key 去重）。
    """
    evidence_parts: list[str] = []
    seen_keys: set[tuple] = set()
    unique_citations: list[Citation] = []
    for result in tool_results:
        if result.evidence_text.strip():
            evidence_parts.append(result.evidence_text)
        for citation in result.citations:
            key = _citation_key(citation)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_citations.append(citation)

    if not evidence_parts:
        return _failed_result(trace, FailureCode.UNAVAILABLE, _STEP_LIMIT_MESSAGE, token_usage=token_usage)

    answer = "\n\n".join(evidence_parts)
    return AgentRunResult(
        answer=answer,
        citations=tuple(unique_citations),
        tool_trace=trace,
        failure=None,
        token_usage=token_usage,
    )

def _citation_key(citation: Citation) -> tuple[str, str, str | None, str | None, int | None]:
    """构造 citation 身份键，避免 final answer 伪造 citation。"""

    return (
        citation.document_id,
        citation.locator.locator_kind.value,
        citation.locator.section_ref,
        citation.locator.table_ref,
        citation.locator.page_no,
    )


def _public_citation(citation: Citation) -> Citation:
    """移除 LLM 最终输出不需要的 parser 内部引用字段。"""

    public_locator = replace(
        citation.locator,
        internal_ref=None,
        internal_ref_available=False,
        bbox=None,
    )
    return replace(citation, locator=public_locator)


def _aggregate_citations(
    result: AggregateMultiYearAnnualPerformanceResult,  # noqa: F821
) -> tuple[Citation, ...]:
    """从 AggregateMultiYearAnnualPerformanceResult 提取所有字段级 table citations。"""

    return tuple(
        field_citation.citation
        for series in result.series
        for field_citation in series.citations
    )


def _aggregate_evidence_text(
    result: AggregateMultiYearAnnualPerformanceResult,  # noqa: F821
) -> str:
    """把 AggregateMultiYearAnnualPerformanceResult 转换为有界证据文本。"""

    lines: list[str] = []
    for series in result.series:
        lines.append(f"fund_code={series.fund_code}")
        lines.append(f"coverage_status={series.coverage_status}")
        lines.append(f"covered_years={','.join(str(y) for y in series.covered_years)}")
        if series.missing_years:
            lines.append(f"missing_years={','.join(str(y) for y in series.missing_years)}")
            for note in series.missing_year_notes:
                lines.append(f"missing_year_note={note.year}: {note.reason}")
        for row in series.rows:
            lines.append(
                f"year={row.year} | "
                f"annual_nav_growth_rate={row.annual_nav_growth_rate} | "
                f"annual_benchmark_return_rate={row.annual_benchmark_return_rate} | "
                f"annual_excess_return={row.annual_excess_return}"
            )
    return "\n".join(lines)
