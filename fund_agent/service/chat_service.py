"""ChatService — 多轮对话 use case。

编排 Session → PromptComposer → LLM Agent → 投资建议检测 → Session 更新。
"""

from __future__ import annotations

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

from .investment_guard import contains_investment_advice
from .prompt_composer import PromptComposer
from .session_models import Session, Turn
from fund_agent.host.session_store import SessionStore

RunnerFactory = Callable[
    [LlmClientProtocol, FundDocumentToolService],
    LlmToolLoopRunner,
]


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
    """

    def __init__(
        self,
        *,
        session_store: SessionStore,
        prompt_composer: PromptComposer,
        scene_config: Any,
        runner_factory: RunnerFactory = _default_runner_factory,
    ) -> None:
        self._session_store = session_store
        self._prompt_composer = prompt_composer
        self._scene_config = scene_config
        self._runner_factory = runner_factory

    def chat_turn(
        self,
        request: ChatTurnRequest,
        *,
        llm_client: LlmClientProtocol | None = None,
        agent_result: AgentRunResult | None = None,
    ) -> ChatTurnResponse:
        """执行一轮对话。

        参数:
            request: 对话请求。
            llm_client: 可选注入 LLM client（测试用）；None 时使用默认 DeepSeek client。
            agent_result: 可选注入 AgentRunResult（测试用）；非 None 时跳过 runner。

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
                llm_client = DeepSeekLlmClient(system_prompt=composed.system_message)
            try:
                runner = self._runner_factory(llm_client, _empty_tool_service())
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

        return ChatTurnResponse(
            answer=answer,
            citations=assistant_turn.citations,
            tool_trace=assistant_turn.tool_trace,
            investment_advice_detected=investment_advice_detected,
        )

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
