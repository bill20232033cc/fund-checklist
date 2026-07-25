"""ToolResult 统一信封 — 所有工具输出经 ok/error/truncation/meta 包装后投射给 LLM。

参考 Dayu engine/tool_result.py 的 build_success / build_error / project_for_llm 模式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果的统一信封。

    字段:
        ok: 工具执行是否成功。
        value: 成功时的结构化数据（dict 或 str）。
        error_code: 失败时的稳定错误码（复用 FailureCode 枚举值）。
        error_message: 人类可读错误信息。
        truncation: 截断元数据 {strategy, kept, total} 或 None。
        meta: 额外元数据（如 source、run_id 等）。
    """

    ok: bool
    value: Any | None = None
    error_code: str | None = None
    error_message: str = ""
    truncation: dict | None = None
    meta: dict | None = None

    @classmethod
    def success(
        cls,
        value: Any,
        truncation: dict | None = None,
        meta: dict | None = None,
    ) -> ToolResult:
        """构造成功结果。

        参数:
            value: 工具返回的结构化数据。
            truncation: 可选截断元数据。
            meta: 可选额外元数据。
        """
        return cls(
            ok=True,
            value=value,
            error_code=None,
            error_message="",
            truncation=truncation,
            meta=meta or {},
        )

    @classmethod
    def error(cls, code: str, message: str) -> ToolResult:
        """构造错误结果。

        参数:
            code: 稳定错误码。
            message: 人类可读错误描述。
        """
        return cls(
            ok=False,
            value=None,
            error_code=code,
            error_message=message,
            truncation=None,
            meta={},
        )


def project_for_llm(result: ToolResult) -> dict:
    """生成 ToolResult 的 LLM-facing 投影。

    - ok=True + value 是 dict → {**value, "truncation": ...}
    - ok=True + value 是 str → {"content": value, "truncation": ...}
    - ok=False → {"error": code, "message": message}

    内部字段 (ok / error_code / error_message) 不暴露给 LLM。
    """
    if result.ok:
        value = result.value
        truncation = result.truncation
        if isinstance(value, dict):
            projected: dict = {**value, "truncation": truncation}
            return projected
        return {"content": value, "truncation": truncation}
    return {"error": result.error_code, "message": result.error_message}
