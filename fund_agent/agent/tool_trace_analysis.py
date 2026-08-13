"""Tool Trace 只读分析器（operator 层）。

只读消费显式传入的派生 tool trace（``tuple[ToolTraceEntry]``）与 typed policy，
输出不可变结构化 report；不读 session / durable internals、不写任何状态、不落盘、
不成为 truth 源。概念对齐 dayu Host Analyzer 的只读边界（仅概念参考，不复制代码），
本模块为自实现纯函数集。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

from fund_agent.agent.tool_loop import ToolTraceEntry

# 固定 4 条 limitations：声明 trace 派生视图边界，与报告一起输出。
_LIMITATIONS: tuple[str, ...] = (
    "trace 是派生视图，不含 raw provider response / raw tool payload。",
    "arguments 仅含 public reading tool 显式参数（契约不含本地路径 / raw payload）。",
    "provider 首轮失败（next_step 内）trace 为空，报告中显示为 0 次调用。",
    "本分析只读消费显式传入的派生 trace，不读 session / durable internals，不写任何状态，不成为 truth 源。",
)


@dataclass(frozen=True)
class ToolTraceAnalysisPolicy:
    """Tool Trace 分析策略。

    参数:
        large_argument_chars: arguments 确定性序列化长度阈值；序列化长度严格大于
            该值时产生 ``large_arguments`` finding（相等不触发）。

    返回:
        不可变分析策略。

    异常:
        本模型不抛出业务异常。
    """

    large_argument_chars: int = 120


@dataclass(frozen=True)
class ToolTraceRunSummary:
    """单次 trace 的运行汇总。

    参数:
        total: 工具调用总次数。
        success: 成功调用次数。
        failure: 失败调用次数。
        unique_tools: 去重后的工具数。

    返回:
        不可变运行汇总。

    异常:
        本模型不抛出业务异常。
    """

    total: int
    success: int
    failure: int
    unique_tools: int


@dataclass(frozen=True)
class ToolTraceToolStat:
    """按工具的聚合统计。

    参数:
        tool_name: 归一化后的工具名。
        total: 该工具调用总次数。
        success: 该工具成功调用次数。
        failure: 该工具失败调用次数。
        failure_codes: 该工具失败分类的字符串值，按首次出现顺序去重保序。

    返回:
        不可变工具统计。

    异常:
        本模型不抛出业务异常。
    """

    tool_name: str
    total: int
    success: int
    failure: int
    failure_codes: tuple[str, ...]


@dataclass(frozen=True)
class ToolTraceFinding:
    """确定性 finding。

    参数:
        kind: finding 类别，取值为 failed_call / repeated_failure / large_arguments。
        tool_name: 归一化后的工具名。
        detail: 人类可读说明。

    返回:
        不可变 finding。

    异常:
        本模型不抛出业务异常。
    """

    kind: Literal["failed_call", "repeated_failure", "large_arguments"]
    tool_name: str
    detail: str


@dataclass(frozen=True)
class ToolTraceAnalysisReport:
    """Tool Trace 分析报告。

    参数:
        summary: 运行汇总。
        by_tool: 按工具首次出现顺序排列的聚合统计。
        findings: 确定性 findings，顺序由 trace 输入顺序决定。
        limitations: 固定 4 条 trace 边界声明。

    返回:
        不可变分析报告，可直接序列化为 JSON。

    异常:
        本模型不抛出业务异常。
    """

    summary: ToolTraceRunSummary
    by_tool: tuple[ToolTraceToolStat, ...]
    findings: tuple[ToolTraceFinding, ...]
    limitations: tuple[str, ...]


def _normalize_failure_code(entry: ToolTraceEntry) -> str | None:
    """归一化 failure_code：取枚举字符串值，无分类时为 None。

    与 main.py 既有 JSON 输出（``r.failure_code.value if r.failure_code else None``）
    保持一致，不使用 ``str(entry.failure_code)``。
    """

    return entry.failure_code.value if entry.failure_code else None


def _serialize_arguments(arguments: dict[str, str | int | None]) -> str:
    """确定性序列化 arguments：``json.dumps(ensure_ascii=False, sort_keys=True)``。"""

    return json.dumps(arguments, ensure_ascii=False, sort_keys=True)


def analyze_tool_trace(
    trace: tuple[ToolTraceEntry, ...],
    policy: ToolTraceAnalysisPolicy,
) -> ToolTraceAnalysisReport:
    """分析派生 tool trace，产出不可变结构化报告（纯函数，无 IO）。

    参数:
        trace: 显式传入的派生工具调用轨迹，只接受 ``tuple[ToolTraceEntry, ...]``。
        policy: 分析策略，控制 large_arguments 阈值。

    返回:
        ToolTraceAnalysisReport：summary / by_tool（首次出现顺序）/ findings /
        limitations（固定 4 条）；同输入两次调用结果相等。

    异常:
        TypeError: trace 非 tuple、trace 元素非 ToolTraceEntry、或 policy 非
            ToolTraceAnalysisPolicy 时抛出。
    """

    if not isinstance(trace, tuple):
        raise TypeError("trace 必须是 tuple[ToolTraceEntry, ...]")
    if not isinstance(policy, ToolTraceAnalysisPolicy):
        raise TypeError("policy 必须是 ToolTraceAnalysisPolicy")
    for entry in trace:
        if not isinstance(entry, ToolTraceEntry):
            raise TypeError("trace 元素必须是 ToolTraceEntry")

    stats: dict[str, dict[str, int]] = {}
    failure_codes_by_tool: dict[str, list[str | None]] = {}
    repeated_failures: dict[tuple[str, str | None], int] = {}
    findings: list[ToolTraceFinding] = []

    for entry in trace:
        tool_name = str(entry.tool_name)
        arguments_text = _serialize_arguments(entry.arguments)
        failure_code = _normalize_failure_code(entry)

        stat = stats.setdefault(tool_name, {"total": 0, "success": 0, "failure": 0})
        stat["total"] += 1
        if entry.result_kind == "failure":
            stat["failure"] += 1
            failure_codes_by_tool.setdefault(tool_name, []).append(failure_code)
            findings.append(
                ToolTraceFinding(
                    kind="failed_call",
                    tool_name=tool_name,
                    detail=f"调用失败：工具 {tool_name} 失败，分类 {failure_code or '无分类'}",
                )
            )
            key = (tool_name, failure_code)
            repeated_failures[key] = repeated_failures.get(key, 0) + 1
        else:
            stat["success"] += 1

        if len(arguments_text) > policy.large_argument_chars:
            findings.append(
                ToolTraceFinding(
                    kind="large_arguments",
                    tool_name=tool_name,
                    detail=(
                        f"arguments 序列化长度 {len(arguments_text)} "
                        f"超过阈值 {policy.large_argument_chars}"
                    ),
                )
            )

    for (tool_name, failure_code), count in repeated_failures.items():
        if count >= 2:
            findings.append(
                ToolTraceFinding(
                    kind="repeated_failure",
                    tool_name=tool_name,
                    detail=f"工具 {tool_name} 同一失败分类 {failure_code or '无分类'} 出现 {count} 次",
                )
            )

    by_tool = tuple(
        ToolTraceToolStat(
            tool_name=tool_name,
            total=stat["total"],
            success=stat["success"],
            failure=stat["failure"],
            failure_codes=tuple(
                code for code in dict.fromkeys(failure_codes_by_tool.get(tool_name, [])) if code is not None
            ),
        )
        for tool_name, stat in stats.items()
    )

    return ToolTraceAnalysisReport(
        summary=ToolTraceRunSummary(
            total=sum(stat["total"] for stat in stats.values()),
            success=sum(stat["success"] for stat in stats.values()),
            failure=sum(stat["failure"] for stat in stats.values()),
            unique_tools=len(stats),
        ),
        by_tool=by_tool,
        findings=tuple(findings),
        limitations=_LIMITATIONS,
    )


def tool_trace_analysis_to_json(report: ToolTraceAnalysisReport) -> str:
    """确定性序列化分析报告为 JSON 文本。

    参数:
        report: 待序列化的 ToolTraceAnalysisReport。

    返回:
        ``json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2)``
        加尾换行的字符串；同输入两次输出一致，中文不转义。

    异常:
        TypeError: report 非 ToolTraceAnalysisReport 时抛出。
    """

    if not isinstance(report, ToolTraceAnalysisReport):
        raise TypeError("report 必须是 ToolTraceAnalysisReport")
    return json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
