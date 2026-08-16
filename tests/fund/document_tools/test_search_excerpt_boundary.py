"""search excerpt 截断边界（候选 C）测试：窗口边缘对齐数字串边界。

背景：`_excerpt`/`_search_excerpt` 的 240 字符窗口在任意字符处截断，可能切断
数字串（如 `787,727,758.47` 被切成 `787,727,`），导致快照份额回退正则
`\\d[\\d,，.]*` 捕获不完整值。本文件覆盖纯函数左右边界对齐、空白归一化路径、
no-hit fallback、不扩展边界、命中区间保留，以及 `search_document` -> 快照
`_extract_share_change` 文本回退的端到端集成。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import ReportType, SourceKind
from fund_agent.fund.document_tools.docling_store import (
    DoclingDocumentStore,
    _align_end_no_number_cut,
    _align_start_no_number_cut,
    _excerpt,
    _search_excerpt,
)
from fund_agent.fund.document_tools.models import ReportIdentity
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service.snapshot_extraction import _extract_share_change


def _identity() -> ReportIdentity:
    """构造测试用报告身份。"""

    return ReportIdentity(
        fund_code="004393",
        fund_name="测试基金",
        year=2025,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-test",
        content_fingerprint="abc123",
        document_id="004393-2025-annual_report-abc123",
    )


def test_excerpt_right_edge_aligns_number_string() -> None:
    """字面路径右边界切在数字串中间时，摘录末尾必须为完整数字。"""

    text = "x" * 115 + "份额变动" + "x" * 100 + "期初基金份额总额 787,727,758.47" + "y" * 200

    excerpt = _excerpt(text, "份额变动", 240)

    assert excerpt.endswith("787,727,758.47")
    assert "份额变动" in excerpt
    # 旧行为：窗口右边界切在 `787,727,758.4`，本断言可证伪


def test_excerpt_left_edge_aligns_number_string() -> None:
    """字面路径左边界切在数字串中间时，摘录开头必须为完整数字。"""

    text = "12,345,678.90" + "x" * 115 + "份额变动" + "x" * 300

    excerpt = _excerpt(text, "份额变动", 240)

    assert excerpt.startswith("12,345,678.90")
    assert "份额变动" in excerpt
    # 旧行为：窗口左边界切在 `7,345,678.90` 中间，开头为半截数字 `7`


def test_search_excerpt_normalized_right_edge_aligns_number_string() -> None:
    """空白归一化路径右边界切在数字串中间时，摘录末尾必须为完整数字。"""

    text = "x" * 115 + "份 额 变 动" + "x" * 100 + "期初基金份额总额 787,727,758.47" + "y" * 200

    excerpt = _search_excerpt(text, "份额变动", 240)

    assert excerpt.endswith("787,727,758.47")
    assert "份 额 变 动" in excerpt
    # 旧行为：归一化命中但右边界仍切在数字串中间


def test_search_excerpt_normalized_left_edge_aligns_number_string() -> None:
    """空白归一化路径左边界切在数字串中间时，摘录开头必须为完整数字。"""

    text = "12,345,678.90" + "x" * 115 + "份 额 变 动" + "x" * 300

    excerpt = _search_excerpt(text, "份额变动", 240)

    assert excerpt.startswith("12,345,678.90")
    assert "份 额 变 动" in excerpt


def test_excerpt_no_hit_fallback_aligns_right_edge() -> None:
    """无命中 fallback 右边界切在数字串中间时，摘录末尾必须为完整数字。"""

    text = "x" * 227 + "787,727,758.47" + "y" * 100

    excerpt = _excerpt(text, "无命中查询词", 240)

    assert excerpt.endswith("787,727,758.47")
    # 旧行为：fallback 为 text[:240]，末尾为 `787,727,758.4`


def test_search_excerpt_no_hit_fallback_aligns_right_edge() -> None:
    """`_search_excerpt` 无命中 fallback 同样对齐右边界。"""

    text = "x" * 227 + "787,727,758.47" + "y" * 100

    excerpt = _search_excerpt(text, "无命中查询词", 240)

    assert excerpt.endswith("787,727,758.47")


def test_excerpt_window_end_at_number_end_no_extension() -> None:
    """窗口恰在数字串结束处时不扩展（截断点后字符不在数字串字符集）。"""

    text = "x" * 226 + "787,727,758.47" + "y" * 100

    assert _align_end_no_number_cut(text, 240) == 240


def test_excerpt_window_keeps_bounded_width_when_no_cut() -> None:
    """窗口边缘未切数字串时保持原窗口宽度（240 字符，不额外扩展）。"""

    text = "x" * 130 + "份额变动" + "x" * 102 + "787,727,758.47" + "y" * 100

    excerpt = _excerpt(text, "份额变动", 240)

    assert len(excerpt) == 240
    assert excerpt.endswith("787,727,758.47")


def test_align_functions_leave_non_number_boundaries_untouched() -> None:
    """截断点两侧非数字串字符（含孤立标点）时不调整；文本边界安全。"""

    text = "abc, def"
    # text[3]=',' 与 text[4]=' ' 非数字串字符 → 不判定数字串内部
    assert _align_start_no_number_cut(text, 4) == 4
    assert _align_end_no_number_cut(text, 4) == 4
    # 窗口边缘在文本边界时原样返回
    assert _align_start_no_number_cut(text, 0) == 0
    assert _align_end_no_number_cut(text, len(text)) == len(text)


def test_search_document_excerpt_and_snapshot_fallback_capture_full_number(tmp_path) -> None:
    """集成：240 字符窗口左/右边缘切入数字串时，search 摘录无半截数字，快照回退捕获完整值。"""

    section_text = (
        "12,345,678.90"
        + "x" * 115
        + "份额变动"
        + "x" * 100
        + "期初基金份额总额 787,727,758.47"
        + "y" * 300
    )
    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 基金份额变化",
                "level": 1,
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": section_text,
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
    }
    json_path = tmp_path / "sample.docling.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)
    tool_service = FundDocumentToolService({_identity().document_id: store})

    results = tool_service.search_document(_identity().document_id, "份额变动")

    assert isinstance(results, tuple) and results
    excerpt = str(results[0].excerpt)
    # 左边缘对齐：完整左边界数字必须出现在摘录中（旧行为窗口左边界切在 `12,345,678` 中间）
    assert "12,345,678.90" in excerpt
    assert excerpt.endswith("787,727,758.47")
    # 快照份额回退路径捕获完整值（旧行为：excerpt 末尾 `787,727,` 被正则捕获为不完整值）
    share_change = _extract_share_change(tool_service, _identity().document_id)
    assert share_change["beginning_shares"] == "787,727,758.47"
