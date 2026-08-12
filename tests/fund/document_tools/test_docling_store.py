"""DoclingDocumentStore Slice 的回归测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.constants import LocatorKind, ReportType, SourceKind
from fund_agent.fund.document_tools.docling_store import DoclingDocumentStore
from fund_agent.fund.document_tools.models import ReportIdentity, SearchMatchKind


def _identity() -> ReportIdentity:
    """构造测试用报告身份。"""

    return ReportIdentity(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        year=2024,
        report_type=ReportType.ANNUAL_REPORT,
        source_kind=SourceKind.LOCAL_PDF,
        local_import_id="local-test",
        content_fingerprint="abc123",
        document_id="004393-2024-annual_report-abc123",
    )


def _write_docling_json(
    path: Path,
    *,
    include_overflow_row: bool = False,
    caption_text: str | None = "表格标题专属词",
) -> None:
    """写入最小 Docling-shaped JSON，用于 store 行为测试。

    参数:
        path: 输出路径。
        include_overflow_row: 是否包含超出 bounded 扫描范围的行。
        caption_text: 表格 caption 文本；None 表示不提供 caption。
    """

    table_cells = [
        {
            "start_row_offset_idx": 0,
            "end_row_offset_idx": 1,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
            "text": "项目",
        },
        {
            "start_row_offset_idx": 0,
            "end_row_offset_idx": 1,
            "start_col_offset_idx": 1,
            "end_col_offset_idx": 2,
            "text": "内容",
        },
        {
            "start_row_offset_idx": 1,
            "end_row_offset_idx": 2,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
            "text": "基金名称",
        },
        {
            "start_row_offset_idx": 1,
            "end_row_offset_idx": 2,
            "start_col_offset_idx": 1,
            "end_col_offset_idx": 2,
            "text": "安信企业价值优选混合型证券投资基金",
        },
        {
            "start_row_offset_idx": 2,
            "end_row_offset_idx": 3,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
            "text": "表格行专属词",
        },
        {
            "start_row_offset_idx": 2,
            "end_row_offset_idx": 3,
            "start_col_offset_idx": 1,
            "end_col_offset_idx": 2,
            "text": "行内证据",
        },
    ]
    if include_overflow_row:
        table_cells.append(
            {
                "start_row_offset_idx": 55,
                "end_row_offset_idx": 56,
                "start_col_offset_idx": 0,
                "end_col_offset_idx": 1,
                "text": "越界行专属词",
            }
        )
    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 重要提示",
                "level": 1,
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "基金经理在本报告期内保持稳定。本章节用于检索基金经理信息。",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "§2 基金简介",
                "level": 1,
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "基金产品说明与托管人信息。",
                "prov": [{"page_no": 2}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 2, "bbox": {"l": 10, "t": 20, "r": 30, "b": 40}}],
                "captions": ([{"text": caption_text}] if caption_text is not None else []),
                "data": {
                    "table_cells": table_cells
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_docling_json_whitespace_fragments(path: Path) -> None:
    """写入正文/表头含空白碎片的 Docling JSON，用于空白归一化检索测试。"""

    payload = {
        "schema_name": "DoclingDocument",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "section_header",
                "text": "§1 净值表现",
                "level": 1,
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "text",
                "text": "本基金在本报告期内保持稳定运作，投资组合整体维持均衡配置。"
                "本基金份额净值 增长率① 为 5.23%，同期业绩比较基准收益率为 1.20%。",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "section_header",
                "text": "§2 基金简介",
                "level": 1,
                "prov": [{"page_no": 2}],
            },
            {
                "self_ref": "#/texts/3",
                "label": "text",
                "text": "基金产品说明与托管人信息。",
                "prov": [{"page_no": 2}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "table",
                "prov": [{"page_no": 1, "bbox": {"l": 10, "t": 20, "r": 30, "b": 40}}],
                "captions": [{"text": "业绩比较基准 比较"}],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "份额净值",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                            "end_col_offset_idx": 2,
                            "text": "增长率①",
                        },
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 2,
                            "end_col_offset_idx": 3,
                            "text": "5.23%",
                        },
                    ]
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_docling_json_sections(path: Path, sections: list[tuple[str, str]]) -> None:
    """写入仅含指定章节（title, text）对的最小 Docling JSON。"""

    texts: list[dict[str, object]] = []
    for index, (title, text) in enumerate(sections):
        texts.append(
            {
                "self_ref": f"#/texts/{index * 2}",
                "label": "section_header",
                "text": title,
                "level": 1,
                "prov": [{"page_no": index + 1}],
            }
        )
        texts.append(
            {
                "self_ref": f"#/texts/{index * 2 + 1}",
                "label": "text",
                "text": text,
                "prov": [{"page_no": index + 1}],
            }
        )
    payload = {"schema_name": "DoclingDocument", "texts": texts, "tables": []}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _store(tmp_path) -> DoclingDocumentStore:
    """构造已通过 parser_health 的 store。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json(json_path)
    return DoclingDocumentStore(identity=_identity(), json_path=json_path)


def test_store_lists_sections_with_locator(tmp_path) -> None:
    """章节列表必须返回 section_ref、preview 和受控 locator。"""

    sections = _store(tmp_path).list_sections()

    assert len(sections) == 2
    assert sections[0].section_ref == "section-0000"
    assert sections[0].title == "§1 重要提示"
    assert sections[0].locator.document_id == _identity().document_id
    assert sections[0].locator.locator_kind is LocatorKind.SECTION
    assert sections[0].locator.section_ref == "section-0000"
    assert sections[0].locator.internal_ref == "#/texts/0"
    assert sections[0].locator.page_range == (1, 1)
    assert "基金经理" in sections[0].preview


def test_store_reads_section_with_bounded_text(tmp_path) -> None:
    """读取章节必须返回 bounded text、citation 和 truncated 标记。"""

    content = _store(tmp_path).read_section("section-0000", max_chars=12)

    assert content.section_ref == "section-0000"
    assert content.truncated is True
    assert len(content.text) == 12
    assert content.citation.document_id == _identity().document_id
    assert content.citation.locator.section_ref == "section-0000"


def test_store_lists_and_reads_tables(tmp_path) -> None:
    """表格列表和读取必须返回 table_ref、section_ref 和二维行投影。"""

    store = _store(tmp_path)
    tables = store.list_tables()
    table = store.read_table(tables[0].table_ref, max_rows=1)

    assert len(tables) == 1
    assert tables[0].table_ref == "table-0000"
    assert tables[0].section_ref == "section-0002"
    assert tables[0].caption == "表格标题专属词"
    assert tables[0].row_count == 3
    assert tables[0].column_count == 2
    assert table.rows == (("项目", "内容"),)
    assert table.truncated is True
    assert table.locator.locator_kind is LocatorKind.TABLE
    assert table.citation.locator.table_ref == "table-0000"


def test_store_search_returns_ranked_excerpt(tmp_path) -> None:
    """搜索必须返回 ranked excerpt、section_ref、locator 和 citation。"""

    results = _store(tmp_path).search("基金经理")

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].section_ref == "section-0000"
    assert "基金经理" in results[0].excerpt
    assert results[0].locator.locator_kind is LocatorKind.EXCERPT
    assert results[0].citation.document_id == _identity().document_id
    assert results[0].match_kind is SearchMatchKind.SECTION_TEXT
    assert results[0].table_ref is None


def test_store_search_returns_table_backed_result_for_caption_only_hit(tmp_path) -> None:
    """搜索只命中 table caption 时必须返回 table-backed result。"""

    results = _store(tmp_path).search("表格标题专属词")

    assert len(results) == 1
    assert results[0].section_ref == "section-0002"
    assert results[0].table_ref == "table-0000"
    assert "表格标题专属词" in results[0].excerpt
    assert results[0].locator.locator_kind is LocatorKind.TABLE
    assert results[0].locator.table_ref == "table-0000"
    assert results[0].citation.locator == results[0].locator
    assert results[0].match_kind is SearchMatchKind.TABLE_CAPTION


def test_store_search_returns_table_backed_result_for_bounded_row_hit(tmp_path) -> None:
    """搜索只命中 bounded table rows 时必须返回 table-backed result。"""

    results = _store(tmp_path).search("表格行专属词")

    assert len(results) == 1
    assert results[0].table_ref == "table-0000"
    assert "表格行专属词" in results[0].excerpt
    assert "项目" not in results[0].excerpt
    assert "基金名称" not in results[0].excerpt
    assert results[0].match_kind is SearchMatchKind.TABLE_ROW
    assert results[0].locator.locator_kind is LocatorKind.TABLE
    assert results[0].citation.locator.table_ref == "table-0000"


def test_store_search_orders_table_caption_before_row_for_equal_score(tmp_path) -> None:
    """同分表格候选必须按稳定 source order 排序。"""

    results = _store(tmp_path).search("专属词")

    assert len(results) == 2
    assert [result.match_kind for result in results] == [
        SearchMatchKind.TABLE_CAPTION,
        SearchMatchKind.TABLE_ROW,
    ]
    assert [result.rank for result in results] == [1, 2]


def test_store_search_ranks_title_hit_section_before_text_only_section(tmp_path) -> None:
    """BM25F 重排序：title 命中章节必须排在仅正文多次命中章节之前。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json_sections(
        json_path,
        [
            ("§1 重要提示", "基金经理在本报告期内保持稳定，基金经理持续履职尽责，基金经理勤勉尽责。"),
            ("§2 基金经理变动情况", "本节说明基金经理变动情况。"),
        ],
    )
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)

    results = store.search("基金经理")

    assert [result.section_ref for result in results] == ["section-0002", "section-0000"]
    assert results[0].match_kind is SearchMatchKind.SECTION_TEXT


def test_store_search_ranks_rare_term_candidate_before_common_term_multi_hit(tmp_path) -> None:
    """稀有词加权：query 含稀有词+常见词时，含稀有词的单次命中候选排在常见词多次命中候选之前。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json_sections(
        json_path,
        [
            ("§1 运作情况", "本基金托管费已计提，基金管理人尽责，基金份额稳定，基金资产正常。"),
            ("§2 托管安排", "本基金托管费已按合同约定计提。"),
            ("§3 基金净值", "基金份额净值与基金资产净值情况。"),
        ],
    )
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)

    results = store.search("基金托管费")

    assert [result.section_ref for result in results] == ["section-0002", "section-0000"]


def test_store_search_returns_empty_tuple_without_evidence_candidate(tmp_path) -> None:
    """无 evidence candidate 时 search 返回空 tuple。"""

    results = _store(tmp_path).search("不存在的检索词")

    assert results == ()


def test_store_search_does_not_scan_unbounded_table_rows(tmp_path) -> None:
    """搜索不得用 DEFAULT_TABLE_MAX_ROWS 之外的行证明命中。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json(json_path, include_overflow_row=True)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)

    results = store.search("越界行专属词")

    assert results == ()


def test_store_search_normalizes_whitespace_in_section_text(tmp_path) -> None:
    """正文检索必须对 query 与正文做空白归一化，命中后返回原文摘录。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json_whitespace_fragments(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)

    results = store.search("净值增长率")

    section_hits = [r for r in results if r.match_kind is SearchMatchKind.SECTION_TEXT]
    assert len(section_hits) == 1
    assert "份额净值 增长率" in section_hits[0].excerpt
    assert section_hits[0].locator.section_ref == "section-0000"


def test_store_search_normalizes_whitespace_in_table_row_text(tmp_path) -> None:
    """表格行检索必须对 query 与行文本做空白归一化，命中后返回原文行摘录。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json_whitespace_fragments(json_path)
    store = DoclingDocumentStore(identity=_identity(), json_path=json_path)

    results = store.search("净值增长率")

    row_hits = [r for r in results if r.match_kind is SearchMatchKind.TABLE_ROW]
    assert len(row_hits) == 1
    assert row_hits[0].table_ref == "table-0000"
    assert "份额净值" in row_hits[0].excerpt
    assert "增长率" in row_hits[0].excerpt
    assert "5.23%" in row_hits[0].excerpt


def test_store_list_tables_backfills_empty_caption_with_section_title(tmp_path) -> None:
    """caption 为空时 list_tables 必须回填所在章节标题作为 evidence。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json(json_path, caption_text=None)

    tables = DoclingDocumentStore(identity=_identity(), json_path=json_path).list_tables()

    assert len(tables) == 1
    assert tables[0].caption == "§2 基金简介"


@pytest.mark.parametrize("noise_caption", ["第 2 页", "第 58 页 共 70 页", "单位：人民币元"])
def test_store_list_tables_backfills_noise_caption_with_section_title(
    tmp_path, noise_caption: str
) -> None:
    """caption 仅含页码/单位噪声时 list_tables 必须回填章节标题。"""

    json_path = tmp_path / "sample.docling.json"
    _write_docling_json(json_path, caption_text=noise_caption)

    tables = DoclingDocumentStore(identity=_identity(), json_path=json_path).list_tables()

    assert len(tables) == 1
    assert tables[0].caption == "§2 基金简介"


@pytest.mark.parametrize(
    ("caption", "expected_semantic"),
    [
        ("第 58 页 共 70 页", False),
        ("第 2 页", False),
        ("单位：人民币元", False),
        ("8.3 期末按公允价值占基金资产净值比例大小排序的所有股票投资明细", True),
        ("表格标题专属词", True),
    ],
)
def test_is_semantic_caption_three_states(caption: str, expected_semantic: bool) -> None:
    """页码（含 共 N 页）/单位噪声判定非语义；正常 caption 判定语义。"""

    from fund_agent.fund.document_tools.docling_store import _is_semantic_caption

    assert _is_semantic_caption(caption) is expected_semantic


# ── _is_continuation_of / _column_type_signature 单元测试 ──────────────────


def _make_table(
    rows: tuple[tuple[str, ...], ...],
    *,
    page_no: int = 1,
    section_ref: str = "section-0000",
    table_ref: str = "table-0000",
    source_index: int = 0,
) -> object:
    """构造 _ParsedTable 用于单元测试。"""
    from fund_agent.fund.document_tools.docling_store import _ParsedTable
    from fund_agent.fund.document_tools.constants import LocatorKind

    return _ParsedTable(
        table_ref=table_ref,
        caption=None,
        section_ref=section_ref,
        rows=rows,
        locator=type(
            "Locator",
            (),
            {
                "document_id": "test-doc",
                "locator_kind": LocatorKind.TABLE,
                "section_ref": section_ref,
                "table_ref": table_ref,
                "page_no": page_no,
                "page_range": None,
                "internal_ref": None,
                "internal_ref_available": False,
                "bbox": None,
            },
        )(),
        source_index=source_index,
    )


def test_continuation_rejects_different_sections() -> None:
    """跨 section 的连续表格不得合并。"""
    from fund_agent.fund.document_tools.docling_store import _is_continuation_of

    prev = _make_table(
        (("序号", "债券代码", "债券名称", "数量", "公允价值", "占比"),),
        page_no=1,
        section_ref="section-0001",
    )
    cur = _make_table(
        (("4", "019709", "21国债09", "100,000", "10,050,000.00", "5.23%"),),
        page_no=2,
        section_ref="section-0002",
    )
    assert _is_continuation_of(cur, prev) is False


def test_continuation_rejects_different_column_signatures() -> None:
    """列类型签名不同的表格不得合并。"""
    from fund_agent.fund.document_tools.docling_store import _is_continuation_of

    prev = _make_table(
        (
            ("序号", "债券代码", "债券名称"),
            ("1", "019709", "21国债09"),
            ("2", "019710", "21国债10"),
        ),
        page_no=1,
    )
    cur = _make_table(
        (
            ("重要说明", "详见附表"),
            ("风险提示", "投资有风险"),
        ),
        page_no=2,
    )
    assert _is_continuation_of(cur, prev) is False


def test_continuation_allows_same_section_and_signature() -> None:
    """同 section 且列签名一致的续表应正常合并。"""
    from fund_agent.fund.document_tools.docling_store import _is_continuation_of

    prev = _make_table(
        (
            ("序号", "债券代码", "债券名称"),
            ("1", "019709", "21国债09"),
            ("2", "019710", "21国债10"),
        ),
        page_no=1,
    )
    cur = _make_table(
        (
            ("3", "019711", "21国债11"),
            ("4", "019712", "21国债12"),
        ),
        page_no=2,
    )
    assert _is_continuation_of(cur, prev) is True


def test_continuation_rejects_cur_with_header() -> None:
    """current 有表头时不得作为续表合并。"""
    from fund_agent.fund.document_tools.docling_store import _is_continuation_of

    prev = _make_table(
        (
            ("序号", "债券代码", "债券名称"),
            ("1", "019709", "21国债09"),
        ),
        page_no=1,
    )
    cur = _make_table(
        (("序号", "证券代码", "证券名称"),),
        page_no=2,
    )
    assert _is_continuation_of(cur, prev) is False


def test_column_type_signature_classifies_cells() -> None:
    """_column_type_signature 正确归类 numeric / text / empty 列。"""
    from fund_agent.fund.document_tools.docling_store import _column_type_signature

    rows: tuple[tuple[str, ...], ...] = (
        ("1", "茅台", "1,000.50", ""),
        ("2", "五粮液", "500.00", ""),
        ("3", "泸州老窖", "200.00", ""),
    )
    assert _column_type_signature(rows) == ("numeric", "text", "numeric", "empty")


def test_data_rows_skips_header() -> None:
    """_data_rows 跳过表头行，保留数据行。"""
    from fund_agent.fund.document_tools.docling_store import _data_rows

    rows: tuple[tuple[str, ...], ...] = (
        ("序号", "名称", "金额"),
        ("1", "项目A", "100"),
        ("2", "项目B", "200"),
    )
    assert _data_rows(rows) == (("1", "项目A", "100"), ("2", "项目B", "200"))


def test_data_rows_all_data_when_no_header() -> None:
    """无表头时 _data_rows 返回全部行。"""
    from fund_agent.fund.document_tools.docling_store import _data_rows

    rows: tuple[tuple[str, ...], ...] = (
        ("1", "数据A"),
        ("2", "数据B"),
    )
    assert _data_rows(rows) == rows
