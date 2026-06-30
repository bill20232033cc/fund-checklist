"""最小 Host：只托管并调用 Agent loop。"""

from __future__ import annotations

from fund_agent.agent.tool_loop import AgentRunResult, MinimalFundDocumentAgent


class MinimalHost:
    """不理解基金领域的最小 Host。

    参数:
        agent: 已装配好工具服务的最小 Agent。

    返回:
        只负责转发运行请求的 Host。

    异常:
        本 Host 不访问 PDF、Docling store 或基金领域数据；Agent 失败通过
        AgentRunResult.failure 返回。
    """

    def __init__(self, agent: MinimalFundDocumentAgent) -> None:
        """初始化最小 Host。"""

        self._agent = agent

    def run(self, *, document_id: str, query: str) -> AgentRunResult:
        """调用 Agent loop 并返回原始 AgentRunResult。

        参数:
            document_id: public reading tools 使用的内容身份。
            query: 由上层传入的检索关键词。

        返回:
            AgentRunResult，不做基金领域解析或内容改写。

        异常:
            不抛出基金文档内部异常。
        """

        return self._agent.run(document_id=document_id, query=query)
