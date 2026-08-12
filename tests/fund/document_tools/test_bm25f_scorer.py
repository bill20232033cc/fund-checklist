"""BM25FScorer 分词、权重、idf、长度归一化与确定性的单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.bm25f_scorer import BM25FScorer, BM25FUnit, tokenize


def test_tokenize_cjk_bigram() -> None:
    """CJK 连续段必须产出 2-gram。"""

    assert tokenize("基金经理") == ["基金", "金经", "经理"]


def test_tokenize_ascii_words_lowercased() -> None:
    """ASCII/数字必须按 [a-z0-9]+ 提取单词并 lowercase。"""

    assert tokenize("Alpha%12.77%beta") == ["alpha", "12", "77", "beta"]


def test_tokenize_mixed_chinese_ascii() -> None:
    """中英混合段必须各自提取后拼接。"""

    assert tokenize("12.77%净值") == ["12", "77", "净值"]


def test_tokenize_single_char_cjk_fallback() -> None:
    """单字符 CJK 段必须回退为 1-gram。"""

    assert tokenize("基") == ["基"]
    assert tokenize("基运作") == ["基运", "运作"]


def test_title_weight_scores_higher_than_text_for_equal_tf() -> None:
    """同 query 同 tf 时 title 字段命中分必须高于 text 字段。"""

    scorer = BM25FScorer(
        [
            BM25FUnit(fields={"title": "基金"}),
            BM25FUnit(fields={"text": "基金"}),
        ]
    )

    title_score = scorer.score({"title": "基金"}, ["基金"])
    text_score = scorer.score({"text": "基金"}, ["基金"])

    assert title_score > text_score


def test_rare_term_idf_higher_than_common_term() -> None:
    """稀有 term 的 idf 必须高于常见 term。"""

    scorer = BM25FScorer(
        [
            BM25FUnit(fields={"title": "托管"}),
            BM25FUnit(fields={"title": "基金"}),
            BM25FUnit(fields={"title": "基金"}),
            BM25FUnit(fields={"title": "基金"}),
        ]
    )

    rare_score = scorer.score({"title": "托管"}, ["托管"])
    common_score = scorer.score({"title": "基金"}, ["基金"])

    assert rare_score > common_score


def test_shorter_field_scores_higher_for_equal_tf() -> None:
    """同 tf 下长度低于平均的短字段必须得分高于长字段。"""

    scorer = BM25FScorer(
        [
            BM25FUnit(fields={"title": "基金"}),
            BM25FUnit(fields={"title": "基金.运作.报告"}),
        ]
    )

    short_score = scorer.score({"title": "基金"}, ["基金"])
    long_score = scorer.score({"title": "基金.运作.报告"}, ["基金"])

    assert short_score > long_score


def test_empty_corpus_and_unmatched_terms_score_zero() -> None:
    """空语料、无 term 命中或空字段必须返回 0.0。"""

    empty = BM25FScorer([])
    assert empty.score({"title": "基金"}, ["基金"]) == 0.0

    scorer = BM25FScorer([BM25FUnit(fields={"title": "基金"})])
    assert scorer.score({"title": "基金"}, ["不存在"]) == 0.0
    assert scorer.score({}, ["基金"]) == 0.0


def test_score_is_deterministic() -> None:
    """相同输入两次调用必须产出相同分数。"""

    scorer = BM25FScorer(
        [
            BM25FUnit(fields={"title": "基金经理", "text": "基金经理变动情况"}),
            BM25FUnit(fields={"caption": "表格标题专属词"}),
            BM25FUnit(fields={"rows": "表格行专属词"}),
        ]
    )
    fields = {"title": "基金经理", "text": "基金经理变动情况"}

    assert scorer.score(fields, tokenize("基金经理")) == scorer.score(fields, tokenize("基金经理"))
