"""Prompt Contributions — 运行时注入到 system_prompt 尾部的贡献片段。

参考 Dayu services/prompt_contributions.py 的 build + select 模式。
"""

from __future__ import annotations


def build_runtime_contribution(
    *,
    fund_code: str = "",
    fund_name: str = "",
    year: int | None = None,
) -> str:
    """构建运行时上下文贡献。

    参数:
        fund_code: 基金代码。
        fund_name: 基金名称。
        year: 当前查看年份。

    返回:
        Markdown 格式的运行时上下文片段。
    """
    parts = ["## 运行时上下文"]
    if fund_code:
        parts.append(f"- 当前基金代码: {fund_code}")
    if fund_name:
        parts.append(f"- 基金名称: {fund_name}")
    if year is not None:
        parts.append(f"- 查看年份: {year}")
    return "\n".join(parts)


def build_fund_context_contribution(
    *,
    fund_code: str = "",
    fund_name: str = "",
    active_year: int | None = None,
    available_years: tuple[int, ...] = (),
) -> str:
    """构建基金上下文贡献（interactive scene 专属）。

    参数:
        fund_code: 基金代码。
        fund_name: 基金名称。
        active_year: 当前活跃年份。
        available_years: 可用年份列表。

    返回:
        Markdown 格式的基金上下文片段。
    """
    parts = ["## 基金上下文"]
    if fund_code:
        parts.append(f"- 基金代码: {fund_code}")
    if fund_name:
        parts.append(f"- 基金名称: {fund_name}")
    if active_year is not None:
        parts.append(f"- 当前查看年份: {active_year}")
    if available_years:
        parts.append(f"- 可用年份: {', '.join(str(y) for y in available_years)}")
    return "\n".join(parts)


def build_memory_contribution(
    *,
    episode_summaries_text: str = "",
    pinned_facts: tuple[str, ...] = (),
) -> str:
    """构建记忆贡献（episodic memory + pinned facts）。

    参数:
        episode_summaries_text: episode summary 的预格式化文本。
        pinned_facts: 已确认的事实列表。

    返回:
        Markdown 格式的记忆片段。
    """
    if not episode_summaries_text and not pinned_facts:
        return ""
    parts = ["## 会话记忆"]
    if episode_summaries_text:
        parts.append(episode_summaries_text)
    if pinned_facts:
        parts.append("### 已确认事实")
        for fact in pinned_facts:
            parts.append(f"- {fact}")
    return "\n".join(parts)


def select_contributions(
    raw: dict[str, str],
    context_slots: tuple[str, ...],
) -> dict[str, str]:
    """按 context_slots 声明顺序筛选并排序 contributions。

    参数:
        raw: {slot_name: content} 全量映射。
        context_slots: scene config 声明的 slot 顺序。

    返回:
        只包含 context_slots 中声明的 slot 且 content 非空的映射。
    """
    return {slot: raw[slot] for slot in context_slots if slot in raw and raw[slot].strip()}
