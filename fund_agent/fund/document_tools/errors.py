"""基金文档工具的稳定失败异常。"""

from fund_agent.fund.document_tools.constants import FailureCode


class DocumentToolError(Exception):
    """携带稳定失败分类的异常。

    参数:
        code: 可断言的公共失败分类。
        message: 面向调用方的安全错误信息，不包含本地路径或内部 payload。

    异常:
        本类用于 fail-closed 地表达已分类失败；不包装未分类的内部异常。
    """

    def __init__(self, code: FailureCode, message: str) -> None:
        """初始化带失败分类的异常。"""

        super().__init__(message)
        self.code = code
        self.message = message

