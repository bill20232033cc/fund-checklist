"""季度偏好快照（Slice P3：preference-snapshot）。

从 preferences.db 的 memos 表提取季度内投资相关行为证据，结合问卷基线
（preference_snapshots 表 + questionnaire_results 表）生成季度偏好快照：
问卷基线 + 行为证据摘要 + 四问反思模板 + 固定免责声明。确定性、不接 LLM。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

_LOCAL_TZ = timezone(timedelta(hours=8))

# 免责声明固定文案（与 docs/design.md §6.26.7 逐字一致）。
DISCLAIMER = "本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"

# 季度格式：YYYYQ[1-4]，如 2026Q3。
QUARTER_REGEX = re.compile(r"^(20\d{2})Q([1-4])$")

# 投资相关关键词（至少 16 词）：行为证据摘要的命中过滤词表。
INVESTMENT_KEYWORDS = (
    "基金",
    "买入",
    "卖出",
    "定投",
    "赎回",
    "申购",
    "加仓",
    "减仓",
    "止盈",
    "止损",
    "亏损",
    "收益",
    "回撤",
    "估值",
    "仓位",
    "净值",
    "分红",
    "持仓",
    "指数",
    "债券",
)


@dataclass(frozen=True)
class BehaviorEvidence:
    """一条季度内投资相关行为证据。

    参数:
        created_at: memo 创建时间（ISO8601 +08:00）。
        content: memo 原文（引用原文，不读原始 HTML）。
        hit_keywords: 命中的投资关键词列表。
    """

    created_at: str
    content: str
    hit_keywords: list[str]


@dataclass(frozen=True)
class QuestionnaireBaseline:
    """问卷基线（取该季度最近一次问卷结果）。

    参数:
        answered_at: 问卷作答时间（ISO8601 +08:00）。
        total_score: 总分（0-100）。
        dimension_scores: 五维子分。
        risk_level: 辅助 C1-C5 风险等级。
    """

    answered_at: str
    total_score: float
    dimension_scores: dict[str, float]
    risk_level: str


@dataclass(frozen=True)
class PreferenceSnapshot:
    """一份季度偏好快照。

    参数:
        quarter: 季度标识（YYYYQn）。
        created_at: 快照生成时间（ISO8601 +08:00）。
        baseline: 问卷基线；该季度无问卷结果时为 None。
        behavior_summary: 行为证据摘要列表。
        reflection: 四问反思模板（答案留空，由用户填写）。
        disclaimer: 固定免责声明文案。
    """

    quarter: str
    created_at: str
    baseline: QuestionnaireBaseline | None
    behavior_summary: list[BehaviorEvidence]
    reflection: dict[str, str]
    disclaimer: str


def _now_iso() -> str:
    """返回当前本地时间（+08:00）的 ISO8601 字符串（秒精度）。"""

    return datetime.now(_LOCAL_TZ).isoformat(timespec="seconds")


def quarter_date_range(quarter: str) -> tuple[date, date]:
    """计算季度日期范围 [起始日, 结束日)。

    参数:
        quarter: 季度标识（YYYYQn，如 2026Q3）。

    返回:
        (起始日, 结束日)：起始日为该季度首日；结束日为下一季度首日
        （独占边界，便于按 created_at 字符串比较过滤）。

    异常:
        ValueError: 季度格式不合法时抛出（中文消息）。
    """

    match = QUARTER_REGEX.match(quarter)
    if match is None:
        raise ValueError(f"季度格式非法: {quarter}，应为 YYYYQ[1-4] 如 2026Q3")
    year = int(match.group(1))
    q = int(match.group(2))
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 3
    start = date(year, start_month, 1)
    end_year = year + (1 if end_month > 12 else 0)
    end_month = (end_month - 1) % 12 + 1
    return start, date(end_year, end_month, 1)


def build_behavior_summary(
    memos: Sequence[Mapping[str, object]],
    quarter: str,
) -> list[BehaviorEvidence]:
    """按季度日期范围与关键词过滤，构建行为证据摘要。

    参数:
        memos: 偏好数据库 memos 表行（含 created_at/content，可含 images/source）。
        quarter: 季度标识（YYYYQn）。

    返回:
        命中的行为证据列表（按 created_at 升序）；只引用原文与时间，不读原始 HTML。

    异常:
        ValueError: 季度格式不合法或 memo 缺少必填字段时抛出（中文消息）。
    """

    start, end = quarter_date_range(quarter)
    summary: list[BehaviorEvidence] = []
    for memo in memos:
        created_at = memo.get("created_at")
        content = memo.get("content")
        if not isinstance(created_at, str) or not isinstance(content, str):
            raise ValueError("memo 行缺少 created_at/content 字段")
        if not (start.isoformat() <= created_at[:10] < end.isoformat()):
            continue
        hit_keywords = [keyword for keyword in INVESTMENT_KEYWORDS if keyword in content]
        if hit_keywords:
            summary.append(
                BehaviorEvidence(
                    created_at=created_at,
                    content=content,
                    hit_keywords=hit_keywords,
                )
            )
    return summary


def _reflection_template() -> dict[str, str]:
    """返回四问反思模板（答案留空，由用户填写）。"""

    return {
        "actual_actions": "",
        "consistent_with_statement": "",
        "deviation": "",
        "next_adjustments": "",
    }


def generate_snapshot(
    store,
    quarter: str,
    *,
    bank=None,
    created_at: str | None = None,
) -> PreferenceSnapshot:
    """生成一份季度偏好快照（不落盘，由调用方持久化）。

    参数:
        store: PreferencesStore 实例。
        quarter: 季度标识（YYYYQn）。
        bank: 题库（QuestionnaireBank）；仅用于获取免责声明，缺省使用固定文案。
        created_at: 快照生成时间；缺省取当前本地时间（+08:00）。

    返回:
        PreferenceSnapshot：问卷基线（无结果时为 None）+ 行为证据摘要 +
        四问反思模板 + 固定免责声明。

    异常:
        ValueError: 季度格式不合法时抛出（中文消息）。
    """

    from fund_agent.preferences.store import (
        latest_questionnaire_result,
        query_memos_by_date_range,
    )

    quarter_date_range(quarter)  # 提前校验季度格式
    start, end = quarter_date_range(quarter)
    memos = query_memos_by_date_range(store, start, end)
    behavior_summary = build_behavior_summary(memos, quarter)
    # end 为独占边界（下一季度首日），latest_questionnaire_result 按含当天
    # 比较，回退一天到本季度最后一日，避免下一季度首日 00:00 的作答误纳入。
    baseline_row = latest_questionnaire_result(store, end - timedelta(days=1))
    baseline = None
    if baseline_row is not None:
        baseline = QuestionnaireBaseline(
            answered_at=baseline_row.answered_at,
            total_score=baseline_row.total_score,
            dimension_scores=baseline_row.dimension_scores,
            risk_level=baseline_row.risk_level,
        )
    disclaimer = DISCLAIMER if bank is None else bank.disclaimer
    return PreferenceSnapshot(
        quarter=quarter,
        created_at=created_at or _now_iso(),
        baseline=baseline,
        behavior_summary=behavior_summary,
        reflection=_reflection_template(),
        disclaimer=disclaimer,
    )


def _snapshot_to_dict(snapshot: PreferenceSnapshot) -> dict[str, object]:
    """把快照转为可持久化的 JSON 字典。"""

    return {
        "quarter": snapshot.quarter,
        "created_at": snapshot.created_at,
        "questionnaire": (
            None
            if snapshot.baseline is None
            else {
                "answered_at": snapshot.baseline.answered_at,
                "total_score": snapshot.baseline.total_score,
                "dimension_scores": snapshot.baseline.dimension_scores,
                "risk_level": snapshot.baseline.risk_level,
            }
        ),
        "behavior_summary": [
            {
                "created_at": evidence.created_at,
                "content": evidence.content,
                "hit_keywords": evidence.hit_keywords,
            }
            for evidence in snapshot.behavior_summary
        ],
        "reflection": dict(snapshot.reflection),
        "disclaimer": snapshot.disclaimer,
    }


def render_snapshot_markdown(snapshot: PreferenceSnapshot) -> str:
    """把快照渲染为 markdown 文本。

    参数:
        snapshot: 偏好快照。

    返回:
        markdown 文本：问卷基线 + 行为证据摘要 + 四问反思模板 + 免责声明。
    """

    lines = [
        f"# 季度偏好快照 {snapshot.quarter}",
        "",
        f"生成时间：{snapshot.created_at}",
        "",
        "## 问卷基线",
    ]
    if snapshot.baseline is None:
        lines.append("（本季度无问卷结果，基线为 null）")
    else:
        baseline = snapshot.baseline
        lines.append(f"- 总分：{baseline.total_score:.1f}")
        lines.append(
            "- 五维子分："
            + "；".join(
                f"{board}={score:.1f}" for board, score in baseline.dimension_scores.items()
            )
        )
        lines.append(f"- 辅助风险等级：{baseline.risk_level}")
    lines.extend(["", "## 本季度行为证据摘要"])
    if not snapshot.behavior_summary:
        lines.append("（本季度无投资相关行为记录）")
    for evidence in snapshot.behavior_summary:
        lines.append(f"- {evidence.created_at}（命中：{'、'.join(evidence.hit_keywords)}）")
        lines.append(f"  {evidence.content}")
    lines.extend(
        [
            "",
            "## 四问反思（模板，答案留空由用户填写）",
            "",
            "1. 本季度实际做了什么：",
            "",
            "2. 与声明一致吗：",
            "",
            "3. 偏差在哪：",
            "",
            "4. 下季度调整什么：",
            "",
            snapshot.disclaimer,
            "",
        ]
    )
    return "\n".join(lines)


def write_snapshot_files(
    store,
    snapshot: PreferenceSnapshot,
) -> tuple[Path, Path]:
    """持久化快照：写 preferences/quarters/<quarter>/ 下 json + md，并入库。

    参数:
        store: PreferencesStore 实例。
        snapshot: 偏好快照。

    返回:
        (json 路径, md 路径)。

    异常:
        PreferencesStoreError: 数据库写入失败时抛出（unavailable 语义）。
    """

    from fund_agent.preferences.store import save_snapshot

    save_snapshot(store, snapshot)
    quarter_dir = Path(store.db_path).parent / "quarters" / snapshot.quarter
    quarter_dir.mkdir(parents=True, exist_ok=True)
    json_path = quarter_dir / "preference-snapshot.json"
    md_path = quarter_dir / "preference-snapshot.md"
    payload = _snapshot_to_dict(snapshot)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_snapshot_markdown(snapshot), encoding="utf-8")
    return json_path, md_path
