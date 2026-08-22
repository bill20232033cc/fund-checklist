"""投资者偏好问卷基线（Slice P2）。

提供自建题库的加载/校验（QuestionBank.load）与确定性评分
（score_questionnaire：总分 100 + 五维子分 + 辅助 C1-C5），不接 LLM。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

_LOCAL_TZ = timezone(timedelta(hours=8))
_EXPECTED_BOARDS = ("基金常识", "投前准备", "系统投资", "投资心态", "实战经验")
_RISK_FLAG_BOARDS = ("投资心态", "实战经验")


@dataclass(frozen=True)
class QuestionnaireQuestion:
    """一道单选题。

    参数:
        id: 题号（q01..q80）。
        board: 所属板块（五大板块之一）。
        difficulty: 难度档位 1-3。
        question: 题干。
        options: 4 个选项文本。
        answer: 正确选项索引（0-3）。
        risk_flag: 是否参与 C1-C5 辅助风险映射（仅投资心态/实战经验可为 True）。
        explanation: 答案解析。
    """

    id: str
    board: str
    difficulty: int
    question: str
    options: list[str]
    answer: int
    risk_flag: bool
    explanation: str


@dataclass(frozen=True)
class QuestionnaireBank:
    """问卷题库（已通过完整性校验）。

    参数:
        version: 题库版本标识。
        boards: 板块名列表（按序）。
        weights: 板块权重（合计 100）。
        c1c5_bands: C1-C5 档位区间列表（共 5 段覆盖 0-100）。
        disclaimer: 输出免责声明。
        questions: 题目列表。
    """

    version: str
    boards: list[str]
    weights: dict[str, int]
    c1c5_bands: list[list[int]]
    disclaimer: str
    questions: list[QuestionnaireQuestion]


@dataclass(frozen=True)
class QuestionnaireResult:
    """一次答题的评分结果。

    参数:
        answered_at: 答题时间（ISO8601 +08:00）。
        version: 题库版本标识。
        dimension_scores: 五维子分（板块得分率 × 权重，保留 1 位小数）。
        total_score: 总分（0-100，保留 1 位小数，等于五维子分之和）。
        risk_level: 辅助 C1-C5 风险等级（由 risk_flag 题得分率映射）。
        answers: 逐题答案快照 {题号: 选项索引}。
        correct: 逐题是否正确快照 {题号: bool}。
        disclaimer: 输出免责声明。
    """

    answered_at: str
    version: str
    dimension_scores: dict[str, float]
    total_score: float
    risk_level: str
    answers: dict[str, int]
    correct: dict[str, bool]
    disclaimer: str


def _now_iso() -> str:
    """返回当前本地时间（+08:00）的 ISO8601 字符串（秒精度）。"""

    return datetime.now(_LOCAL_TZ).isoformat(timespec="seconds")


def _require(condition: bool, message: str) -> None:
    """校验失败时抛出带中文说明的 ValueError。"""

    if not condition:
        raise ValueError(message)


def _validate_bank(data: object) -> None:
    """校验题库结构完整性，非法时抛 ValueError（中文消息）。"""

    _require(isinstance(data, dict), "题库结构非法：顶层必须是 JSON 对象")
    _require(isinstance(data.get("version"), str) and data["version"], "题库结构非法：version 必须是非空字符串")
    _require(isinstance(data.get("boards"), list), "题库结构非法：boards 必须是列表")
    boards = data["boards"]
    _require(
        len(boards) == 5 and set(boards) == set(_EXPECTED_BOARDS),
        "题库结构非法：boards 必须是五大板块（基金常识/投前准备/系统投资/投资心态/实战经验）",
    )
    _require(isinstance(data.get("weights"), dict), "题库结构非法：weights 必须是对象")
    weights = data["weights"]
    _require(
        set(weights.keys()) == set(_EXPECTED_BOARDS),
        "题库结构非法：weights 必须包含五大板块各一个权重",
    )
    _require(
        all(type(value) is int and value >= 0 for value in weights.values()),
        "题库结构非法：weights 值必须是非负整数",
    )
    _require(sum(weights.values()) == 100, "题库结构非法：weights 合计必须为 100")
    _require(isinstance(data.get("c1c5_bands"), list), "题库结构非法：c1c5_bands 必须是列表")
    bands = data["c1c5_bands"]
    _require(len(bands) == 5, "题库结构非法：c1c5_bands 必须为 5 段")
    prev_hi = -1
    for band in bands:
        _require(
            isinstance(band, list) and len(band) == 2
            and all(type(v) is int for v in band) and band[0] <= band[1],
            "题库结构非法：每段 c1c5_bands 必须是 [下限, 上限] 整数区间",
        )
        _require(band[0] == prev_hi + 1, "题库结构非法：c1c5_bands 各段必须连续覆盖 0-100")
        prev_hi = band[1]
    _require(prev_hi == 100, "题库结构非法：c1c5_bands 末段上限必须为 100")
    _require(
        isinstance(data.get("disclaimer"), str) and data["disclaimer"],
        "题库结构非法：disclaimer 必须是非空字符串",
    )
    _require(isinstance(data.get("questions"), list), "题库结构非法：questions 必须是列表")
    questions = data["questions"]
    _require(len(questions) == 80, f"题库结构非法：必须包含 80 题，实际 {len(questions)} 题")
    seen_ids: set[str] = set()
    risk_count = 0
    for question in questions:
        _require(isinstance(question, dict), "题库结构非法：每题必须是 JSON 对象")
        qid = question.get("id")
        _require(isinstance(qid, str) and qid, "题库结构非法：题目 id 必须是非空字符串")
        _require(qid not in seen_ids, f"题库结构非法：题目 id 重复: {qid}")
        seen_ids.add(qid)
        _require(question.get("board") in boards, f"题库结构非法：{qid} 的 board 不在五大板块中")
        _require(
            type(question.get("difficulty")) is int and question["difficulty"] in (1, 2, 3),
            f"题库结构非法：{qid} 的 difficulty 必须是 1-3",
        )
        _require(
            isinstance(question.get("question"), str) and question["question"],
            f"题库结构非法：{qid} 的 question 必须是非空字符串",
        )
        options = question.get("options")
        _require(
            isinstance(options, list) and len(options) == 4 and all(isinstance(o, str) and o for o in options),
            f"题库结构非法：{qid} 必须恰好有 4 个非空选项",
        )
        _require(
            type(question.get("answer")) is int and 0 <= question["answer"] <= 3,
            f"题库结构非法：{qid} 的 answer 必须是 0-3 的整数",
        )
        _require(
            isinstance(question.get("risk_flag"), bool),
            f"题库结构非法：{qid} 的 risk_flag 必须是布尔值",
        )
        _require(
            isinstance(question.get("explanation"), str) and question["explanation"],
            f"题库结构非法：{qid} 的 explanation 必须是非空字符串",
        )
        if question["risk_flag"]:
            risk_count += 1
            _require(
                question["board"] in _RISK_FLAG_BOARDS,
                f"题库结构非法：{qid} 的 risk_flag 仅允许在投资心态/实战经验板块",
            )
    _require(risk_count >= 8 and risk_count <= 16, f"题库结构非法：risk_flag 题数必须在 8-16 之间，实际 {risk_count}")


class QuestionBank:
    """题库加载与完整性校验入口。"""

    @staticmethod
    def load(path: Path | str) -> QuestionnaireBank:
        """从 JSON 文件加载题库并校验完整性。

        参数:
            path: 题库 JSON 文件路径。

        返回:
            校验通过的 QuestionnaireBank。

        异常:
            ValueError: JSON 解析失败或结构非法时抛出（中文消息）。
        """

        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"题库文件读取失败: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"题库文件解析失败: {exc}") from exc
        _validate_bank(data)
        return QuestionnaireBank(
            version=data["version"],
            boards=list(data["boards"]),
            weights=dict(data["weights"]),
            c1c5_bands=[list(band) for band in data["c1c5_bands"]],
            disclaimer=data["disclaimer"],
            questions=[
                QuestionnaireQuestion(
                    id=item["id"],
                    board=item["board"],
                    difficulty=item["difficulty"],
                    question=item["question"],
                    options=list(item["options"]),
                    answer=item["answer"],
                    risk_flag=item["risk_flag"],
                    explanation=item["explanation"],
                )
                for item in data["questions"]
            ],
        )


def risk_band(score: float, c1c5_bands: Sequence[Sequence[int]]) -> str:
    """把 0-100 的风险得分映射到 C1-C5 档位。

    参数:
        score: 风险得分（0-100）。
        c1c5_bands: 5 段连续区间（覆盖 0-100）。

    返回:
        "C1".."C5" 之一。

    异常:
        ValueError: 得分不在任何区间内时抛出。
    """

    for index, band in enumerate(c1c5_bands, start=1):
        if band[0] <= score <= band[1]:
            return f"C{index}"
    raise ValueError(f"风险得分 {score} 无法映射到 C1-C5 档位")


def score_questionnaire(
    bank: QuestionnaireBank,
    answers: Mapping[str, int],
    *,
    answered_at: str | None = None,
) -> QuestionnaireResult:
    """按题库评分一次作答。

    参数:
        bank: 题库（QuestionBank.load 或直接构造）。
        answers: 逐题答案 {题号: 0-3}。
        answered_at: 答题时间；缺省取当前本地时间（+08:00）。

    返回:
        QuestionnaireResult：五维子分 + 总分 + 辅助 C1-C5 + 逐题答案快照。

    异常:
        ValueError: 含未知题号、缺失题或答案索引越界时抛出（中文消息）。
    """

    bank_ids = {question.id for question in bank.questions}
    answer_ids = set(answers.keys())
    missing = bank_ids - answer_ids
    if missing:
        raise ValueError(f"答案缺失题: {sorted(missing)[:5]}")
    unknown = answer_ids - bank_ids
    if unknown:
        raise ValueError(f"答案含未知题号: {sorted(unknown)[:5]}")
    for qid, value in answers.items():
        if type(value) is not int or not (0 <= value <= 3):
            raise ValueError(f"答案非法: {qid} 的选项索引必须是 0-3 的整数")

    board_questions = {board: [] for board in bank.boards}
    for question in bank.questions:
        board_questions[question.board].append(question)

    dimension_scores: dict[str, float] = {}
    for board in bank.boards:
        questions = board_questions[board]
        correct = sum(1 for q in questions if answers[q.id] == q.answer)
        rate = correct / len(questions)
        dimension_scores[board] = round(rate * bank.weights[board], 1)

    total_score = round(sum(dimension_scores.values()), 1)

    risk_questions = [q for q in bank.questions if q.risk_flag]
    risk_correct = sum(1 for q in risk_questions if answers[q.id] == q.answer)
    risk_score = round((risk_correct / len(risk_questions)) * 100, 1)
    risk_level = risk_band(risk_score, bank.c1c5_bands)

    correct_map = {q.id: answers[q.id] == q.answer for q in bank.questions}
    return QuestionnaireResult(
        answered_at=answered_at or _now_iso(),
        version=bank.version,
        dimension_scores=dimension_scores,
        total_score=total_score,
        risk_level=risk_level,
        answers=dict(answers),
        correct=correct_map,
        disclaimer=bank.disclaimer,
    )
