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

from fund_agent.agent.deepseek_llm import DeepSeekLlmClient
from fund_agent.agent.llm_tool_loop import (
    ChatResponse,
    FinalAnswer,
    LlmClientProtocol,
    LlmToolLoopRunner,
    ToolCall,
    ToolResult,
)
from fund_agent.agent.tool_loop import AgentRunResult
from fund_agent.fund.document_tools.constants import ToolName
from fund_agent.fund.document_tools.service import FundDocumentToolService

from .chat_contract import ChatTurnContract
from .investment_guard import contains_investment_advice
from .prompt_composer import PromptComposer
from .session_models import EpisodeSummary, PinnedState, Session, Turn
from fund_agent.host.session_store import SessionStore

RunnerFactory = Callable[
    [LlmClientProtocol, FundDocumentToolService],
    LlmToolLoopRunner,
]  # 实现可额外接收 max_steps 关键字参数


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
    """

    answer: str
    citations: tuple[str, ...] = ()
    tool_trace: tuple[str, ...] = ()
    token_usage: dict[str, int] | None = None
    investment_advice_detected: bool = False


def _default_runner_factory(
    llm_client: LlmClientProtocol,
    tool_service: FundDocumentToolService,
    max_steps: int = 8,
) -> LlmToolLoopRunner:
    """默认 runner 工厂。"""
    return LlmToolLoopRunner(
        llm_client=llm_client,
        tool_service=tool_service,
        max_steps=max_steps,
    )


class ChatService:
    """多轮对话 use case Service。

    参数:
        session_store: Session 持久化存储。
        prompt_composer: Prompt 模板渲染器。
        scene_config: Scene 配置（fragments + context_slots）。
        runner_factory: 可选 runner 工厂（测试注入）。
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
        enable_episode_summary: bool = True,
        compaction_trigger_turns: int = 10,
        compaction_tail_preserve_turns: int = 3,
        compaction_model_context_window: int = 65536,
    ) -> None:
        self._session_store = session_store
        self._prompt_composer = prompt_composer
        self._scene_config = scene_config
        self._runner_factory = runner_factory
        self._enable_episode_summary = enable_episode_summary
        self._compaction_trigger_turns = compaction_trigger_turns
        self._compaction_tail_preserve_turns = compaction_tail_preserve_turns
        self._compaction_model_context_window = compaction_model_context_window
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
        contributions = self._build_contributions(session)
        composed = self._prompt_composer.compose_from_scene(
            self._scene_config, contributions=contributions
        )

        # 4. 运行 agent loop（或使用注入结果）
        if agent_result is None:
            if llm_client is None:
                # 从 contract 或 scene config 取 model 配置
                model_name = os.environ.get("DEEPSEEK_MODEL", "")
                temperature = 0.7
                if contract is not None and contract.model_name:
                    model_name = contract.model_name
                elif hasattr(self._scene_config, "model"):
                    model_name = self._scene_config.model.default_name
                    temperature = self._scene_config.model.temperature
                # 通过环境变量临时覆盖 model（DeepSeekLlmClient 内部读取环境变量）
                llm_env: dict[str, str] | None = None
                if model_name:
                    import os as _os
                    llm_env = dict(_os.environ)
                    llm_env["DEEPSEEK_MODEL"] = model_name
                llm_client = DeepSeekLlmClient(
                    system_prompt=composed.system_message,
                    env=llm_env,
                )
            try:
                max_steps = 8
                if contract is not None and contract.max_iterations is not None:
                    max_steps = contract.max_iterations
                elif hasattr(self._scene_config, "runtime"):
                    max_steps = self._scene_config.runtime.max_iterations
                runner = self._runner_factory(llm_client, _empty_tool_service(), max_steps=max_steps)
                agent_result = runner.run(document_id=document_id, query=user_text)
            except Exception:
                return ChatTurnResponse(answer="LLM 服务暂不可用，请稍后重试。")

        answer = agent_result.answer

        # 5. 投资建议检测（fail-closed）
        investment_advice_detected = contains_investment_advice(answer)
        if investment_advice_detected:
            answer = "抱歉，不支持涉及投资建议的问题。"

        # 6. 更新 session
        user_turn = Turn(role="user", content=user_text)
        assistant_turn = Turn(
            role="assistant",
            content=answer,
            citations=tuple(
                c.document_id if hasattr(c, "document_id") else str(c)
                for c in agent_result.citations
            ),
            tool_trace=tuple(
                e.tool_name if hasattr(e, "tool_name") else str(e)
                for e in agent_result.tool_trace
            ),
        )
        session = session.add_turn(user_turn).add_turn(assistant_turn)
        self._session_store.save(session)

        # 7. 检查 Episode Summary 触发条件
        if self._enable_episode_summary:
            self._maybe_trigger_compaction(session)

        return ChatTurnResponse(
            answer=answer,
            citations=assistant_turn.citations,
            tool_trace=assistant_turn.tool_trace,
            investment_advice_detected=investment_advice_detected,
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

            # 构建压缩 prompt
            turns_text = "\n".join(
                f"[{t.role}]: {t.content}" for t in compact_turns
            )

            ps = session.pinned_state
            user_prompt = f"""## 当前固定状态
- 基金代码: {ps.fund_code}
- 当前年份: {ps.active_year or '未选择'}
- 当前目标: {ps.user_constraints.get('current_goal', '无')}
- 已确认事实: {ps.user_constraints.get('confirmed_facts', '无')}
- 待解决问题: {ps.user_constraints.get('open_questions', '无')}

## 对话记录（待压缩）
{turns_text}"""

            system_prompt = (
                "你是一个对话记忆压缩助手。请阅读对话片段，生成紧凑的记忆摘要。"
                "严格按照 JSON 格式输出，不要包含其他文本。"
                '格式: {"episode_summary": {"title": "...", "goal": "...", '
                '"confirmed_facts": [...], "open_questions": [...], "next_step": "..."}, '
                '"pinned_state_patch": {"current_goal": "..."|null, '
                '"confirmed_facts": "..."|null, "open_questions": "..."|null}}'
            )

            # 调用 LLM 生成摘要（或使用注入结果）
            if self._injected_compaction_result is not None:
                raw = json.dumps(self._injected_compaction_result, ensure_ascii=False)
            else:
                try:
                    llm = DeepSeekLlmClient()
                    raw = llm.generate_text(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
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

    def _build_contributions(self, session: Session) -> dict[str, str]:
        """从 session 构建 prompt contributions。"""
        contributions: dict[str, str] = {}

        ps = session.pinned_state
        # runtime contribution
        runtime_parts = ["## 运行时上下文"]
        if ps.fund_code:
            runtime_parts.append(f"- 当前基金代码: {ps.fund_code}")
        if ps.active_year is not None:
            runtime_parts.append(f"- 查看年份: {ps.active_year}")
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
