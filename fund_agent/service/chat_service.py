"""ChatService — 多轮对话 use case。

编排 Session → PromptComposer → LLM Agent → 投资建议检测 → Session 更新。
支持 Episode Summary 异步压缩。
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fund_agent.agent.deepseek_llm import (
    DeepSeekLlmClient,
    provider_model_env_name,
    resolve_provider,
    translate_model_for_provider,
)
from fund_agent.agent.llm_tool_loop import (
    ChatResponse,
    FinalAnswer,
    LlmClientProtocol,
    LlmToolLoopRunner,
    ToolCall,
    ToolResult,
    contains_investment_advice,
    matched_investment_advice_terms,
)
from fund_agent.agent.tool_loop import AgentRunResult
from fund_agent.fund.document_tools.constants import ToolName
from fund_agent.fund.document_tools.service import FundDocumentToolService

from .chat_contract import ChatTurnContract
from .extraction import _resolve_anchor_table_ref, _route_plan_for_query
from .models import AggregateMultiYearAnnualPerformanceResult
from .prompt_composer import PromptComposer
from .prompt_contributions import build_memory_contribution
from .session_models import EpisodeSummary, PinnedState, Session, ToolCallSummary, Turn
from fund_agent.host.session_store import SessionStore

RunnerFactory = Callable[
    [LlmClientProtocol, FundDocumentToolService],
    LlmToolLoopRunner,
]  # 实现可额外接收 max_steps 关键字参数

# D1/D2 硬口径：受控表锚点只注入这几类高误命中 profile，其余保持 LLM 自由选表。
# Fix C（Mimo 根因 review 用户已批准）：performance_returns 加入锚点范围，
# 锚点表号由 Service 层组合 public tools 解析（3.2.1 表头签名，A 类优先）。
_ANCHOR_PROFILE_NAMES = ("manager_holdings", "holdings_top10", "performance_returns")

# P1 记忆注入硬口径：最近 <=3 条 EpisodeSummary、单条 fact/question <=100 token、
# 总长 <=500 token（超限丢最旧），超长单条截断加省略号（Mimo finding 003）。
_MEMORY_MAX_EPISODES = 3
_MEMORY_MAX_TOKENS = 500
_MEMORY_ITEM_MAX_TOKENS = 100
_MEMORY_MAX_CONFIRMED_FACTS = 5
_MEMORY_MAX_OPEN_QUESTIONS = 3


@dataclass(frozen=True)
class ChatTurnRequest:
    """单轮对话请求。

    参数:
        session_id: 会话 ID。
        user_text: 用户输入文本。
        document_id: 可选，指定要查询的 document_id；None 时使用 session pinned_state。
    """

    session_id: str
    user_text: str
    document_id: str | None = None


@dataclass(frozen=True)
class ChatTurnResponse:
    """单轮对话响应。

    参数:
        answer: LLM 最终回答。
        citations: 引用列表。
        tool_trace: 工具调用轨迹摘要。
        token_usage: 累计 token 用量信息。
        investment_advice_detected: 是否检测到投资建议。
        original_content: 被拦截回答的原始文本；未拦截时为 None。
        blocked_terms: 触发拦截的命中词元；未拦截时为空元组。
    """

    answer: str
    citations: tuple[str, ...] = ()
    tool_trace: tuple[str, ...] = ()
    token_usage: dict[str, int] | None = None
    investment_advice_detected: bool = False
    original_content: str | None = None
    blocked_terms: tuple[str, ...] = ()


def _tool_call_summaries(agent_result: AgentRunResult) -> tuple[ToolCallSummary, ...]:
    """从 agent_result.tool_trace 构造 ToolCallSummary 元组。

    参数:
        agent_result: Agent 循环结果。

    返回:
        结构化工具调用摘要；无 trace 时为空元组。
    """

    if not agent_result.tool_trace:
        return ()
    return tuple(
        ToolCallSummary(
            tool_name=entry.tool_name,
            arguments_display=str(entry.arguments)[:100] if entry.arguments else "",
            success=entry.result_kind == "success",
            failure_code=entry.failure_code if entry.result_kind != "success" else None,
        )
        for entry in agent_result.tool_trace
    )


def _tool_trace_summary(agent_result: AgentRunResult) -> tuple[str, ...]:
    """从 agent_result.tool_trace 构造字符串摘要（失败轮专用）。

    格式为 `tool_name(result_kind[:failure_code])`，复用 ToolTraceEntry 的
    result_kind / failure_code 字段（该结构不存在 status 字段，禁止使用）。

    参数:
        agent_result: Agent 循环结果。

    返回:
        字符串元组；无 trace 时为空元组（如 provider 首轮失败）。
    """

    if not agent_result.tool_trace:
        return ()
    return tuple(
        f"{str(entry.tool_name)}({entry.result_kind}"
        + (f":{str(entry.failure_code)}" if entry.failure_code else "")
        + ")"
        if hasattr(entry, "tool_name")
        else str(entry)
        for entry in agent_result.tool_trace
    )


def _default_runner_factory(
    llm_client: LlmClientProtocol,
    tool_service: FundDocumentToolService,
    max_steps: int = 8,
    aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None,
    failed_call_keys: frozenset[tuple] | None = None,
) -> LlmToolLoopRunner:
    """默认 runner 工厂。"""
    return LlmToolLoopRunner(
        llm_client=llm_client,
        tool_service=tool_service,
        max_steps=max_steps,
        aggregate_handler=aggregate_handler,
        failed_call_keys=failed_call_keys,
    )


_MAX_FAILED_TOOL_CALL_KEYS = 50


def _merge_failed_tool_call_keys(
    current: tuple[tuple, ...],
    round_keys: tuple[tuple, ...],
    *,
    limit: int = _MAX_FAILED_TOOL_CALL_KEYS,
) -> tuple[tuple, ...]:
    """合并跨轮失败调用去重键（去重 + 上限，超限丢最旧）。"""

    merged: list[tuple] = []
    seen: set[tuple] = set()
    for key in (*current, *round_keys):
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
    if len(merged) > limit:
        merged = merged[-limit:]
    return tuple(merged)


class ChatService:
    """多轮对话 use case Service。

    参数:
        session_store: Session 持久化存储。
        prompt_composer: Prompt 模板渲染器。
        scene_config: Scene 配置（fragments + context_slots）。
        runner_factory: 可选 runner 工厂（测试注入）。
        aggregate_handler: 可选 aggregate_multi_year_annual_performance 回调；
            由 factory 透传给 LlmToolLoopRunner，None 时保持既有 unavailable 行为。
        enable_episode_summary: 是否启用 Episode Summary 异步压缩。
        compaction_trigger_turns: 触发压缩的最小轮数（默认 10）。
        compaction_tail_preserve_turns: 压缩时保留的最近轮数（默认 3）。
        compaction_model_context_window: 模型上下文窗口大小，用于 60% token 触发。
    """

    def __init__(
        self,
        *,
        session_store: SessionStore,
        prompt_composer: PromptComposer,
        scene_config: Any,
        runner_factory: RunnerFactory = _default_runner_factory,
        tool_service: FundDocumentToolService | None = None,
        enable_episode_summary: bool = True,
        compaction_trigger_turns: int = 10,
        compaction_tail_preserve_turns: int = 3,
        compaction_model_context_window: int = 65536,
        history_max_tokens: int = 2000,
        aggregate_handler: Callable[..., AggregateMultiYearAnnualPerformanceResult] | None = None,
    ) -> None:
        self._session_store = session_store
        self._prompt_composer = prompt_composer
        self._scene_config = scene_config
        self._runner_factory = runner_factory
        self._tool_service = tool_service
        self._enable_episode_summary = enable_episode_summary
        self._compaction_trigger_turns = compaction_trigger_turns
        self._compaction_tail_preserve_turns = compaction_tail_preserve_turns
        self._compaction_model_context_window = compaction_model_context_window
        self._history_max_tokens = history_max_tokens
        self._aggregate_handler = aggregate_handler
        self._cumulative_tokens = 0
        self._compacting: set[str] = set()  # 正在压缩的 session_id 集合
        self._injected_compaction_result: dict | None = None  # 测试用

    def chat_turn(
        self,
        request: ChatTurnRequest,
        *,
        llm_client: LlmClientProtocol | None = None,
        agent_result: AgentRunResult | None = None,
        contract: ChatTurnContract | None = None,
    ) -> ChatTurnResponse:
        """执行一轮对话。

        参数:
            request: 对话请求。
            llm_client: 可选注入 LLM client（测试用）；None 时使用默认 DeepSeek client。
            agent_result: 可选注入 AgentRunResult（测试用）；非 None 时跳过 runner。
            contract: 可选 ChatTurnContract，携带 model/runtime 覆盖。

        返回:
            ChatTurnResponse。

        异常:
            FileNotFoundError: session 不存在。
        """
        user_text = request.user_text.strip()
        if not user_text:
            return ChatTurnResponse(answer="请输入问题内容。")

        # 1. 加载 session
        session = self._session_store.load(request.session_id)

        # 2. 确定 document_id
        document_id = request.document_id or session.pinned_state.active_document_id
        if not document_id:
            return ChatTurnResponse(answer="未指定要查询的年报文档，请先选择年份。")

        # 3. 组装 system prompt（构建但仅在实际调用 LLM 时使用）
        contributions = self._build_contributions(
            session, document_id=document_id, user_query=user_text
        )
        composed = self._prompt_composer.compose_from_scene(
            self._scene_config, contributions=contributions
        )

        # 4. 运行 agent loop（或使用注入结果）
        if agent_result is None:
            if llm_client is None:
                # 从 contract 或 scene config 取 model 配置（provider 感知）
                provider = resolve_provider(os.environ)
                model_env_name = provider_model_env_name(provider)
                temperature = 0.7
                if hasattr(self._scene_config, "model"):
                    temperature = self._scene_config.model.temperature
                # 解析顺序：provider 对应 MODEL env 非空优先；
                # 否则 scene/contract 模型名经翻译后写入 provider 对应 MODEL env。
                model_name = os.environ.get(model_env_name, "").strip()
                if not model_name:
                    if contract is not None and contract.model_name:
                        model_name = contract.model_name
                    elif hasattr(self._scene_config, "model"):
                        model_name = self._scene_config.model.default_name
                    model_name = translate_model_for_provider(model_name, provider)
                # 通过环境变量临时覆盖 model（DeepSeekLlmClient 内部读取环境变量）
                llm_env: dict[str, str] | None = None
                if model_name:
                    import os as _os
                    llm_env = dict(_os.environ)
                    llm_env[model_env_name] = model_name
                llm_client = DeepSeekLlmClient(
                    system_prompt=composed.system_message,
                    env=llm_env,
                    temperature=temperature,
                )
            try:
                max_steps = 8
                if contract is not None and contract.max_iterations is not None:
                    max_steps = contract.max_iterations
                elif hasattr(self._scene_config, "runtime"):
                    max_steps = self._scene_config.runtime.max_iterations
                runner = self._runner_factory(
                    llm_client,
                    self._tool_service or _empty_tool_service(),
                    max_steps=max_steps,
                    aggregate_handler=self._aggregate_handler,
                    failed_call_keys=frozenset(session.failed_tool_call_keys),
                )
                # 受控检索路由在 Service 层（候选词随 scene context 注入），
                # 收敛执行在 Agent 层：runner 不 import service，只接收候选词。
                route_plan = _route_plan_for_query(user_text)
                agent_result = runner.run(
                    document_id=document_id,
                    query=user_text,
                    scene=self._scene_config.scene,
                    candidate_queries=(
                        route_plan.candidate_queries if route_plan.profile_name is not None else None
                    ),
                )
            except Exception:
                return ChatTurnResponse(answer="LLM 服务暂不可用，请稍后重试。")

        # 4.5 合并本轮失败调用 key（跨轮失败短路的数据基础，上限 50 条）
        merged_failed_keys = _merge_failed_tool_call_keys(
            session.failed_tool_call_keys, agent_result.failed_call_keys
        )

        # 5. 失败轮：成对落盘（user + assistant），保留 tool_calls / tool_trace
        if agent_result.failure is not None:
            failure_message = f"LLM 处理失败：{agent_result.failure.message}"
            user_turn = Turn(role="user", content=user_text)
            assistant_turn = Turn(
                role="assistant",
                content=failure_message,
                tool_trace=_tool_trace_summary(agent_result),
                tool_calls=_tool_call_summaries(agent_result),
            )
            session = session.add_turn(user_turn).add_turn(assistant_turn)
            session = session.with_failed_tool_call_keys(merged_failed_keys)
            self._session_store.save(session)
            return ChatTurnResponse(
                answer=failure_message,
                tool_trace=assistant_turn.tool_trace,
            )

        answer = agent_result.answer

        # 6. 投资建议检测（fail-closed）
        original_answer = answer
        investment_advice_detected = contains_investment_advice(answer)
        blocked_terms: tuple[str, ...] = ()
        if investment_advice_detected:
            blocked_terms = matched_investment_advice_terms(answer)
            answer = "抱歉，不支持涉及投资建议的问题。"

        # 7. 更新 session
        user_turn = Turn(role="user", content=user_text)

        tool_calls = _tool_call_summaries(agent_result)

        assistant_turn = Turn(
            role="assistant",
            content=answer,
            citations=tuple(
                c.document_id if hasattr(c, "document_id") else str(c)
                for c in agent_result.citations
            ),
            key_facts=agent_result.key_facts,
            tool_trace=tuple(
                e.tool_name if hasattr(e, "tool_name") else str(e)
                for e in agent_result.tool_trace
            ),
            tool_calls=tool_calls,
            original_content=original_answer if investment_advice_detected else None,
            blocked_terms=blocked_terms,
        )
        session = session.add_turn(user_turn).add_turn(assistant_turn)
        session = session.with_failed_tool_call_keys(merged_failed_keys)
        self._session_store.save(session)

        # 8. 检查 Episode Summary 触发条件
        if self._enable_episode_summary:
            self._maybe_trigger_compaction(session)

        return ChatTurnResponse(
            answer=answer,
            citations=assistant_turn.citations,
            tool_trace=assistant_turn.tool_trace,
            investment_advice_detected=investment_advice_detected,
            original_content=assistant_turn.original_content,
            blocked_terms=assistant_turn.blocked_terms,
        )

    def _maybe_trigger_compaction(self, session: Session) -> None:
        """检查是否满足 Episode Summary 触发条件，满足则启动后台压缩。"""
        if session.session_id in self._compacting:
            return  # 已在压缩中

        round_count = len(session.turns) // 2  # user+assistant 成对算一轮
        token_ratio = (
            self._cumulative_tokens / self._compaction_model_context_window
            if self._compaction_model_context_window > 0
            else 0.0
        )

        should_compact = (
            round_count >= self._compaction_trigger_turns
            or token_ratio >= 0.6
        )

        if not should_compact:
            return

        # 标记正在压缩，防止重复触发
        self._compacting.add(session.session_id)

        thread = threading.Thread(
            target=self._run_compaction,
            args=(session,),
            daemon=True,
        )
        thread.start()

    def _run_compaction(self, session: Session) -> None:
        """后台执行 Episode Summary 压缩（在独立线程中运行）。"""
        try:
            # 确定压缩范围：保留最近 N 轮
            preserve_turns = self._compaction_tail_preserve_turns * 2  # user+assistant
            turns_to_compress = list(session.turns)
            if len(turns_to_compress) <= preserve_turns:
                self._compacting.discard(session.session_id)
                return

            compact_turns = turns_to_compress[:-preserve_turns]
            if not compact_turns:
                self._compacting.discard(session.session_id)
                return

            # 构建压缩 prompt（通过 PromptComposer 加载 compaction.md 模板）
            turns_text = "\n".join(
                f"[{t.role}]: {t.content}" for t in compact_turns
            )

            ps = session.pinned_state
            context = {
                "fund_code": ps.fund_code or "未知",
                "active_year": str(ps.active_year) if ps.active_year else "未选择",
                "current_goal": ps.user_constraints.get("current_goal", "无"),
                "confirmed_facts": ps.user_constraints.get("confirmed_facts", "无"),
                "open_questions": ps.user_constraints.get("open_questions", "无"),
                "turns_text": turns_text,
            }

            composed = self._prompt_composer.compose("interactive/compaction.md", context)

            # 调用 LLM 生成摘要（或使用注入结果）
            if self._injected_compaction_result is not None:
                raw = json.dumps(self._injected_compaction_result, ensure_ascii=False)
            else:
                try:
                    temp = 0.3
                    if hasattr(self._scene_config, "model"):
                        temp = getattr(self._scene_config.model, "temperature", 0.3)
                    llm = DeepSeekLlmClient(temperature=temp)
                    raw = llm.generate_text(
                        system_prompt=composed.system_message,
                        user_prompt="请生成压缩摘要。",
                        temperature=0.3,
                    )
                except Exception:
                    self._compacting.discard(session.session_id)
                    return

            # 解析 JSON 响应
            parsed = self._parse_compaction_response(raw)
            if parsed is None:
                self._compacting.discard(session.session_id)
                return

            ep_data = parsed.get("episode_summary", {})
            patch_data = parsed.get("pinned_state_patch", {})

            start_idx = session.turns.index(compact_turns[0]) if compact_turns else 0
            end_idx = session.turns.index(compact_turns[-1]) if compact_turns else 0

            episode = EpisodeSummary(
                episode_id=f"ep-{session.session_id[:8]}-{len(session.episode_summaries):03d}",
                start_turn_id=start_idx,
                end_turn_id=end_idx,
                title=str(ep_data.get("title", "")),
                goal=str(ep_data.get("goal", "")),
                confirmed_facts=tuple(str(f) for f in ep_data.get("confirmed_facts", [])),
                open_questions=tuple(str(q) for q in ep_data.get("open_questions", [])),
            )

            # 更新 session
            try:
                current = self._session_store.load(session.session_id)
            except FileNotFoundError:
                self._compacting.discard(session.session_id)
                return

            current = current.add_episode_summary(episode)
            if patch_data:
                current = current.apply_pinned_state_patch(patch_data)
            current = current.truncate_turns(keep_last=self._compaction_tail_preserve_turns * 2)
            self._session_store.save(current)
        finally:
            self._compacting.discard(session.session_id)

    def inject_compaction_result(self, result: dict | None) -> None:
        """注入测试用的 compaction 结果，跳过真实 LLM 调用。"""
        self._injected_compaction_result = result

    @staticmethod
    def _parse_compaction_response(raw: str) -> dict | None:
        """解析 LLM 压缩响应 JSON。"""
        if not raw:
            return None
        text = raw.strip()
        # 尝试提取 ```json 代码块
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start) if "```" in text[start:] else len(text)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start) if "```" in text[start:] else len(text)
            text = text[start:end].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _build_history_contribution(self, session: Session) -> str | None:
        """从 session turns 构建 history contribution。

        从最近轮次向前累积，直到 token 上限。

        参数:
            session: 当前会话。

        返回:
            history 文本，或 None（无历史时）。
        """
        if not session.turns:
            return None

        lines = ["## 历史对话", ""]
        total_tokens = 0
        selected_turns: list[str] = []

        # 从最近向前累积
        for turn in reversed(session.turns):
            formatted = self._format_turn_for_history(turn)
            tokens = self._estimate_token_count(formatted)
            if total_tokens + tokens > self._history_max_tokens:
                break
            selected_turns.append(formatted)
            total_tokens += tokens

        if not selected_turns:
            return None

        # 反转回正序
        selected_turns.reverse()
        lines.extend(selected_turns)
        lines.append("")
        lines.append("---")
        lines.append("以上是历史对话。请忽略历史中的纯文本格式，以 JSON 格式回答当前用户问题。")
        return "\n".join(lines)

    def _format_turn_for_history(self, turn: Turn) -> str:
        """格式化单轮对话为 history 文本。

        参数:
            turn: 对话轮次。
        """
        role_label = "用户提问" if turn.role == "user" else "助手回答"
        parts = [f"[{role_label}]: {turn.content}"]

        # 工具调用摘要
        if turn.tool_calls:
            for tc in turn.tool_calls:
                parts.append(f"[工具调用]: {tc.tool_name}({tc.arguments_display}) → {tc.result_summary}")

        # Citation 引用
        if turn.citations:
            parts.append(f"[引用文档]: {','.join(turn.citations)}")

        return "\n".join(parts)

    def _estimate_token_count(self, text: str) -> int:
        """粗估 token 数。中文约 1.5 token/字，英文约 0.75 token/word。

        参数:
            text: 待估算文本。
        """
        cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
        other_len = len(text) - cn_chars
        return int(cn_chars * 1.5 + other_len / 4)

    def _truncate_to_token_bound(self, text: str, max_tokens: int) -> str:
        """按 _estimate_token_count 口径截断文本到 token 上界，并追加省略号。

        参数:
            text: 待截断文本。
            max_tokens: token 上界。

        返回:
            截断后文本；未超限时原样返回。
        """
        if not text or self._estimate_token_count(text) <= max_tokens:
            return text
        budget = max(max_tokens - 1, 0)  # 为省略号预留余量
        total = 0.0
        cutoff = 0
        for i, ch in enumerate(text):
            token = 1.5 if "一" <= ch <= "鿿" else 0.25
            if total + token > budget:
                break
            total += token
            cutoff = i + 1
        return text[:cutoff] + "…"

    def _format_episode_block(self, episode: EpisodeSummary) -> str:
        """格式化单条 EpisodeSummary 为注入文本块。

        每块最多包含 title / goal / confirmed_facts（<=5 条）/
        open_questions（<=3 条）；单条 fact/question 超 100 token
        截断加省略号（Mimo finding 003）。

        参数:
            episode: 待格式化的 EpisodeSummary。

        返回:
            Markdown 格式文本块；字段全空时返回空字符串。
        """
        parts: list[str] = []
        if episode.title:
            parts.append(f"- 主题: {episode.title}")
        if episode.goal:
            parts.append(f"- 目标: {episode.goal}")
        facts = [
            self._truncate_to_token_bound(f, _MEMORY_ITEM_MAX_TOKENS)
            for f in episode.confirmed_facts[:_MEMORY_MAX_CONFIRMED_FACTS]
            if f.strip()
        ]
        if facts:
            parts.append("- 已确认事实:")
            parts.extend(f"  - {f}" for f in facts)
        questions = [
            self._truncate_to_token_bound(q, _MEMORY_ITEM_MAX_TOKENS)
            for q in episode.open_questions[:_MEMORY_MAX_OPEN_QUESTIONS]
            if q.strip()
        ]
        if questions:
            parts.append("- 待解决问题:")
            parts.extend(f"  - {q}" for q in questions)
        return "\n".join(parts)

    def _format_episode_summaries(self, session: Session) -> str:
        """格式化最近 <=3 条 EpisodeSummary，总长 <=500 token。

        复用 _estimate_token_count；超限先丢最旧，仅剩单条仍超限时
        截断到上界保证 <=500。全部为空时返回空字符串（不产生 memory slot）。

        参数:
            session: 当前会话。

        返回:
            格式化后的历史摘要文本；无可注入内容时返回空字符串。
        """
        episodes = session.episode_summaries[-_MEMORY_MAX_EPISODES:]
        blocks: list[str] = []
        for ep in episodes:
            block = self._format_episode_block(ep)
            if block.strip():
                blocks.append(block)
        if not blocks:
            return ""
        while (
            len(blocks) > 1
            and self._estimate_token_count("\n\n".join(blocks)) > _MEMORY_MAX_TOKENS
        ):
            blocks.pop(0)
        text = "\n\n".join(blocks)
        if self._estimate_token_count(text) > _MEMORY_MAX_TOKENS:
            text = self._truncate_to_token_bound(text, _MEMORY_MAX_TOKENS)
        return text

    def _pinned_facts(self, session: Session) -> tuple[str, ...]:
        """从 pinned_state.user_constraints["confirmed_facts"] 读取已确认事实。

        参数:
            session: 当前会话。

        返回:
            非空已确认事实元组；缺失或为空时返回空元组（跳过注入）。
        """
        value = session.pinned_state.user_constraints.get("confirmed_facts")
        if value is None:
            return ()
        if isinstance(value, str):
            stripped = value.strip()
            return (stripped,) if stripped else ()
        if isinstance(value, (list, tuple)):
            return tuple(str(f).strip() for f in value if str(f).strip())
        return ()

    def _build_contributions(
        self,
        session: Session,
        document_id: str | None = None,
        user_query: str | None = None,
    ) -> dict[str, str]:
        """从 session 构建 prompt contributions。

        参数:
            session: 当前会话。
            document_id: 本轮已确定的 document_id；None 时回退
                session.pinned_state.active_document_id。
            user_query: 当前轮用户输入；非 None 时按受控检索路由注入候选检索词。

        返回:
            contributions 字典。
        """
        contributions: dict[str, str] = {}

        ps = session.pinned_state
        # runtime contribution
        runtime_parts = ["## 运行时上下文"]
        if ps.fund_code:
            runtime_parts.append(f"- 当前基金代码: {ps.fund_code}")
        if ps.active_year is not None:
            runtime_parts.append(f"- 查看年份: {ps.active_year}")
        active_document_id = document_id or ps.active_document_id
        if active_document_id:
            runtime_parts.append(f"- 当前文档 document_id: {active_document_id}")
        contributions["runtime"] = "\n".join(runtime_parts)

        # fund_context contribution
        if ps.fund_code:
            ctx_parts = ["## 基金上下文"]
            ctx_parts.append(f"- 基金代码: {ps.fund_code}")
            if ps.active_year is not None:
                ctx_parts.append(f"- 当前查看年份: {ps.active_year}")
            if ps.available_document_ids:
                # 从 document_ids 推算年份
                pass
            contributions["fund_context"] = "\n".join(ctx_parts)

        # Pass through context slots from user_constraints
        for key, value in ps.user_constraints.items():
            if isinstance(value, str) and value.strip():
                contributions[key] = value

        # memory contribution（P1：EpisodeSummary / PinnedState → system prompt。
        # 历史摘要仅作上下文提示，非当前证据；引用以本轮工具返回为准。）
        memory_text = build_memory_contribution(
            episode_summaries_text=self._format_episode_summaries(session),
            pinned_facts=self._pinned_facts(session),
        )
        if memory_text:
            contributions["memory"] = memory_text

        # history contribution
        history_text = self._build_history_contribution(session)
        if history_text:
            contributions["history"] = history_text

        # retrieval contribution：受控候选检索词注入（Service 层路由知识，
        # 不参与 runner 收敛执行；收敛执行只消费 runner 收到的 candidate_queries）。
        if user_query:
            route_plan = _route_plan_for_query(user_query)
            if route_plan.profile_name is not None:
                candidates = "、".join(route_plan.candidate_queries)
                retrieval_parts = [
                    "## 受控候选检索词",
                    f"- 已识别披露主题: {route_plan.profile_name}",
                    f"- 请优先按顺序尝试以下候选检索词（命中即可，不要自行改写）: {candidates}",
                ]
                # 候选表锚点：锚点为 prompt 数据，由 Service 层组合 public tools
                # 解析（runner 不 import service），解析失败 fail-open 不注入。
                if (
                    route_plan.profile_name in _ANCHOR_PROFILE_NAMES
                    and route_plan.locator_contract is not None
                    and self._tool_service is not None
                ):
                    anchor_table_ref = _resolve_anchor_table_ref(
                        active_document_id,
                        route_plan.locator_contract,
                        self._tool_service,
                    )
                    if anchor_table_ref:
                        anchor_title = "、".join(route_plan.locator_contract.anchor_title_family)
                        retrieval_parts.append(
                            f"- 候选表锚点: {anchor_table_ref}（{anchor_title}）"
                            "——请先 list_tables 确认该表号在列，再 read_table 该表，并以该表返回内容作为引用依据（勿自行猜测表号）"
                        )
                contributions["retrieval"] = "\n".join(retrieval_parts)

        return contributions


def _empty_tool_service() -> FundDocumentToolService:
    """创建空 tool service（无 document store 可用时占位）。"""
    import os
    import tempfile
    from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
    from fund_agent.fund.document_tools.models import ReportIdentity
    from fund_agent.fund.document_tools.persistent_repository import FilesystemReportRepository, CATALOG_FILENAME
    from fund_agent.fund.document_tools.errors import DocumentToolError

    # 尝试从 work_dir 加载 document store
    work_dir = Path(".fund_checklist")
    catalog_path = work_dir / CATALOG_FILENAME
    if not catalog_path.exists():
        # 无 catalog 时返回空 service
        return FundDocumentToolService({})
    try:
        repo = FilesystemReportRepository(
            catalog_path=catalog_path,
            blob_root=work_dir / "pdf_blobs",
            docling_json_root=work_dir / "docling_json",
        )
        catalog_reports = repo.list_reports()
        stores = {}
        for report in catalog_reports:
            doc_id = str(report.get("document_id", ""))
            if doc_id:
                try:
                    stores[doc_id] = repo.load_store(doc_id)
                except DocumentToolError:
                    continue
        return FundDocumentToolService(stores)
    except Exception:
        return FundDocumentToolService({})
