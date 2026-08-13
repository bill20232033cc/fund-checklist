"""有界脱敏诊断载荷构造器的测试。"""

from __future__ import annotations

import json

import pytest

from fund_agent.agent.diagnostic_payload import (
    MAX_DIAGNOSTIC_FIELD_CHARS,
    MAX_DIAGNOSTIC_TOTAL_CHARS,
    TRUNCATION_SUFFIX,
    build_diagnostic_payload,
    redact_diagnostic_text,
)

_SENSITIVE_SAMPLES = [
    ("sk-abcdefgh12345678", "sk-abcdefgh12345678"),
    ("pk-abcdefgh12345678", "pk-abcdefgh12345678"),
    ("Bearer abcdefghij123456", "abcdefghij123456"),
    ("https://example.com/x?api_key=secret12345", "api_key=secret12345"),
    ("https://example.com/x?token=secret12345", "token=secret12345"),
    ("https://example.com/x?secret=secret12345", "secret=secret12345"),
    ("https://example.com/x?signature=secret12345", "signature=secret12345"),
    ("https://example.com/x?sig=secret12345", "sig=secret12345"),
    ("local_import_id=local-secret-import-id", "local-secret-import-id"),
    ("local_import_id: local-secret-import-id", "local-secret-import-id"),
    ("/Users/maomao/fund-checklist/private/cache", "/Users/maomao/fund-checklist"),
    ("/tmp/private-cache/sample.docling.json", "/tmp/private-cache"),
    ("/private/var/tmp/sample.json", "/private/var/tmp/sample.json"),
    ("~/.fund_checklist_cli_smoke_xxx", "~/.fund_checklist_cli_smoke_xxx"),
    (".fund_checklist_cli_smoke_xxx", ".fund_checklist_cli_smoke_xxx"),
]


@pytest.mark.parametrize(("sample", "secret_fragment"), _SENSITIVE_SAMPLES)
def test_redact_diagnostic_text_redacts_secrets(sample: str, secret_fragment: str) -> None:
    """redact_diagnostic_text 对集中定义的敏感模式逐项脱敏为 *** 且幂等。"""

    redacted = redact_diagnostic_text(sample)
    assert secret_fragment not in redacted
    assert "***" in redacted
    assert redact_diagnostic_text(redacted) == redacted


def test_build_diagnostic_payload_redacts_fields() -> None:
    """build_diagnostic_payload 逐字段脱敏敏感值，公开字段原样保留。"""

    payload = build_diagnostic_payload(
        message="诊断",
        query="Bearer abcdefgh123456",
        document_id="004393-2024-annual_report-abc123def4567890",
        provider="https://api.deepseek.com?api_key=sk-abcdefgh12345678",
    )

    assert payload["message"] == "诊断"
    assert payload["query"] == "***"
    assert payload["document_id"] == "004393-2024-annual_report-abc123def4567890"
    assert payload["provider"] == "https://api.deepseek.com?***"


def test_raw_provider_body_sample_redacted_and_structure_not_leaked() -> None:
    """raw provider body 样本含 sk- key 时被脱敏，payload 不泄漏 body 结构键。"""

    raw_body = json.dumps(
        {"choices": [{"message": {"content": "ok"}}], "api_key": "sk-abcdefgh12345678"}
    )

    redacted = redact_diagnostic_text(raw_body)
    assert "sk-abcdefgh12345678" not in redacted

    payload = build_diagnostic_payload(message="诊断", query=raw_body)
    assert set(payload.keys()) == {"message", "query"}
    serialized = str(payload)
    assert "sk-abcdefgh12345678" not in serialized
    assert "***" in serialized
    assert raw_body not in serialized


def test_field_truncation_with_suffix() -> None:
    """单字段超过 500 字符时截断并追加后缀。"""

    long_query = "q" * (MAX_DIAGNOSTIC_FIELD_CHARS + 100)
    payload = build_diagnostic_payload(message="ok", query=long_query)

    assert len(payload["query"]) == MAX_DIAGNOSTIC_FIELD_CHARS + len(TRUNCATION_SUFFIX)
    assert payload["query"].endswith(TRUNCATION_SUFFIX)
    assert payload["query"].startswith("q" * MAX_DIAGNOSTIC_FIELD_CHARS)
    assert payload["message"] == "ok"


def test_total_bound_drops_optional_fields_in_fixed_order() -> None:
    """6 字段全满时总量超 2000，按 query→provider→tool_name→document_id→code 丢弃。"""

    oversized = MAX_DIAGNOSTIC_FIELD_CHARS + 1
    payload = build_diagnostic_payload(
        message="m" * oversized,
        code="c" * oversized,
        document_id="d" * oversized,
        tool_name="t" * oversized,
        provider="p" * oversized,
        query="q" * oversized,
    )

    assert "message" in payload
    assert set(payload.keys()) == {"message", "code", "document_id"}
    assert sum(len(value) for value in payload.values()) <= MAX_DIAGNOSTIC_TOTAL_CHARS


def test_none_fields_are_omitted() -> None:
    """None 字段不进入返回载荷。"""

    assert build_diagnostic_payload(message="ok") == {"message": "ok"}
    payload = build_diagnostic_payload(message="ok", code=None, query="q")
    assert payload == {"message": "ok", "query": "q"}


def test_build_diagnostic_payload_is_deterministic() -> None:
    """同输入两次构造结果一致（确定性）。"""

    kwargs = {
        "message": "诊断",
        "code": "llm_malformed_response",
        "document_id": "004393-2024-annual_report-abc123def4567890",
        "tool_name": "search_document",
        "provider": "deepseek",
        "query": "基金经理 Bearer abcdefgh123456",
    }
    assert build_diagnostic_payload(**kwargs) == build_diagnostic_payload(**kwargs)


def test_unknown_kwargs_raise_type_error() -> None:
    """未知关键字参数抛 TypeError（显式参数契约）。"""

    with pytest.raises(TypeError):
        build_diagnostic_payload(message="ok", unknown_field="x")


def test_missing_message_raises_type_error() -> None:
    """message 缺失抛 TypeError。"""

    with pytest.raises(TypeError):
        build_diagnostic_payload()
