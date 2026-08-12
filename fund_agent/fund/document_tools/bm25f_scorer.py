"""确定性 BM25F 多字段重排序打分器（标准公开算法，参数自定义）。"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from fund_agent.fund.document_tools.constants import (
    BM25F_ASCII_TOKEN_PATTERN,
    BM25F_CJK_NGRAM_SIZE,
    BM25F_CJK_RUN_PATTERN,
    BM25F_FIELD_B,
    BM25F_FIELD_WEIGHTS,
    BM25F_K1,
    BM25F_SCORE_ROUND_DIGITS,
)

_ASCII_TOKEN_RE = re.compile(BM25F_ASCII_TOKEN_PATTERN)
_CJK_RUN_RE = re.compile(BM25F_CJK_RUN_PATTERN)
_WHITESPACE_RE = re.compile(r"\s+")


def _whitespace_stripped(text: str) -> str:
    """去除全部空白字符，与 docling_store 检索口径一致。"""

    return _WHITESPACE_RE.sub("", text)


def tokenize(text: str) -> list[str]:
    """对文本做确定性分词：ASCII 单词 + CJK 二元组。

    参数:
        text: 原始文本。

    返回:
        token 列表（含重复，用于 tf 计数）。
    """

    stripped = _whitespace_stripped(text)
    tokens = list(_ASCII_TOKEN_RE.findall(stripped.lower()))
    for run in _CJK_RUN_RE.findall(stripped):
        if len(run) <= BM25F_CJK_NGRAM_SIZE:
            tokens.append(run)
        else:
            tokens.extend(
                run[index : index + BM25F_CJK_NGRAM_SIZE]
                for index in range(len(run) - BM25F_CJK_NGRAM_SIZE + 1)
            )
    return tokens


@dataclass(frozen=True)
class BM25FUnit:
    """一个可打分文档单元（section / table caption / table row）。

    参数:
        fields: 命名字段文本；字段名必须是 constants.py 中已配置的 BM25F 字段。

    返回:
        BM25FUnit 实例。

    异常:
        本模型不抛出业务异常。
    """

    fields: Mapping[str, str]


class BM25FScorer:
    """基于语料统计的确定性 BM25F 打分器。

    参数:
        units: 全部可打分文档单元。

    返回:
        BM25FScorer 实例。

    异常:
        本类不抛出业务异常。
    """

    def __init__(self, units: Sequence[BM25FUnit]) -> None:
        """构建语料统计：document frequency 与各字段平均 token 长度。"""

        self._units = tuple(units)
        self._document_frequency = _build_document_frequency(self._units)
        self._avg_lengths = _build_avg_lengths(self._units)

    def score(self, fields: Mapping[str, str], query_terms: Sequence[str]) -> float:
        """计算 query 词项对给定字段文档的 BM25F 分数。

        参数:
            fields: 候选文档的命名字段文本。
            query_terms: 查询词项（内部去重）。

        返回:
            四舍五入到 6 位小数的分数；无词项命中或空字段时返回 0.0。
        """

        field_token_counts = {name: Counter(tokenize(text)) for name, text in fields.items()}
        total = 0.0
        for term in dict.fromkeys(query_terms):
            document_frequency = self._document_frequency.get(term, 0)
            if document_frequency <= 0:
                continue
            idf = math.log(
                1.0 + (len(self._units) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            weighted_sum = 0.0
            for field_name, token_counts in field_token_counts.items():
                term_frequency = token_counts.get(term, 0)
                if term_frequency <= 0:
                    continue
                weight = BM25F_FIELD_WEIGHTS[field_name]
                b = BM25F_FIELD_B[field_name]
                average_length = self._avg_lengths.get(field_name, 0.0)
                length = sum(token_counts.values())
                normalized_length = 1.0
                if average_length > 0:
                    normalized_length = 1.0 - b + b * (length / average_length)
                weighted_sum += weight * term_frequency / normalized_length
            if weighted_sum <= 0:
                continue
            total += idf * (BM25F_K1 + 1.0) * weighted_sum / (BM25F_K1 + weighted_sum)
        return round(total, BM25F_SCORE_ROUND_DIGITS)


def _build_document_frequency(units: Sequence[BM25FUnit]) -> dict[str, int]:
    """统计每个 term 出现过的 unit 数；跨字段不拼接 token。"""

    document_frequency: dict[str, int] = {}
    for unit in units:
        terms: set[str] = set()
        for text in unit.fields.values():
            terms.update(tokenize(text))
        for term in terms:
            document_frequency[term] = document_frequency.get(term, 0) + 1
    return document_frequency


def _build_avg_lengths(units: Sequence[BM25FUnit]) -> dict[str, float]:
    """统计各字段平均 token 长度（仅统计含该字段的 unit）。"""

    length_sums: dict[str, int] = {}
    length_counts: dict[str, int] = {}
    for unit in units:
        for name, text in unit.fields.items():
            length = len(tokenize(text))
            length_sums[name] = length_sums.get(name, 0) + length
            length_counts[name] = length_counts.get(name, 0) + 1
    return {name: length_sums[name] / length_counts[name] for name in length_sums}
