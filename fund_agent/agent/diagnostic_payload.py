"""有界脱敏诊断载荷构造器。"""

from __future__ import annotations

import re

MAX_DIAGNOSTIC_FIELD_CHARS: int = 500
MAX_DIAGNOSTIC_TOTAL_CHARS: int = 2000
TRUNCATION_SUFFIX: str = "…(截断)"
REDACTION_REPLACEMENT: str = "***"

# 脱敏正则集中定义：诊断载荷/日志中出现下列模式时一律替换为 ***，禁止散落。
_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # sk-/pk- 前缀 API key（≥8 位）。
    re.compile(r"(?i)\b(?:sk|pk)-[a-z0-9_-]{8,}\b"),
    # Bearer token。
    re.compile(r"(?i)\bbearer\s+[a-z0-9._-]{8,}\b"),
    # URL query secret（api_key/token/secret/signature/sig=）。
    re.compile(r'(?i)(api[_-]?key|token|secret|signature|sig)=[^&\s"\']+'),
    # local_import_id（含值）。
    re.compile(r"local_import_id\s*[:=]?\s*[a-z0-9-]{8,}"),
    # 本地绝对路径。
    re.compile(r"/Users/[A-Za-z0-9_./-]+"),
    re.compile(r"/tmp/[A-Za-z0-9_./-]+"),
    re.compile(r"/private/[A-Za-z0-9_./-]+"),
    re.compile(r"~/?[A-Za-z0-9_./-]*"),
    # 工作目录。
    re.compile(r"\.fund_checklist_[A-Za-z0-9_./-]+"),
)


def redact_diagnostic_text(text: str) -> str:
    """按集中定义的脱敏规则替换敏感片段为 ***（幂等）。

    参数:
        text: 原始文本。

    返回:
        脱敏后的文本。

    异常:
        不抛出业务异常。
    """

    for pattern in _REDACTION_PATTERNS:
        text = pattern.sub(REDACTION_REPLACEMENT, text)
    return text


def _truncate(text: str, limit: int) -> str:
    """字段级截断：超过 limit 时保留前 limit 字符并追加截断后缀。"""

    if len(text) <= limit:
        return text
    return text[:limit] + TRUNCATION_SUFFIX


def build_diagnostic_payload(
    message: str,
    *,
    code: str | None = None,
    document_id: str | None = None,
    tool_name: str | None = None,
    provider: str | None = None,
    query: str | None = None,
) -> dict[str, str]:
    """构造有界脱敏诊断载荷（显式命名参数，逐字段脱敏 + 截断，总量有界）。

    参数:
        message: 必填诊断消息，永不丢弃。
        code: 可选失败码/分类码。
        document_id: 可选文档内容身份。
        tool_name: 可选工具名。
        provider: 可选 LLM provider 名。
        query: 可选查询文本。

    返回:
        仅含非 None 字段的 dict[str, str]；超总量上限时按
        query → provider → tool_name → document_id → code 顺序丢弃可选字段。

    异常:
        未知关键字参数抛 TypeError（显式参数契约）；message 缺失抛 TypeError。
    """

    fields: list[tuple[str, str]] = [("message", message)]
    for name, value in (
        ("code", code),
        ("document_id", document_id),
        ("tool_name", tool_name),
        ("provider", provider),
        ("query", query),
    ):
        if value is not None:
            fields.append((name, str(value)))

    payload: dict[str, str] = {}
    for name, value in fields:
        payload[name] = _truncate(redact_diagnostic_text(value), MAX_DIAGNOSTIC_FIELD_CHARS)

    drop_order = ("query", "provider", "tool_name", "document_id", "code")
    while sum(len(value) for value in payload.values()) > MAX_DIAGNOSTIC_TOTAL_CHARS:
        for name in drop_order:
            if name in payload:
                del payload[name]
                break
        else:
            # 只剩 message 仍超限的防御性兜底（正常不可能发生），停止避免死循环。
            break
    return payload
