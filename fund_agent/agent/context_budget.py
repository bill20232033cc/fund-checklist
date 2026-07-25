"""上下文预算治理模块。

提供:
- ContextBudgetState: 追踪 token 消耗，soft/hard 限制与 compaction 触发
- ToolResultBudgetCapper: 工具结果升序公平分配裁剪器
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

_T = TypeVar("_T")

_DEFAULT_SOFT_LIMIT_RATIO = 0.75
_DEFAULT_HARD_LIMIT_RATIO = 0.90
_DEFAULT_COMPACTION_TRIGGER_RATIO = 0.70


@dataclass(frozen=True)
class ContextBudgetState:
    """上下文预算状态追踪。

    追踪 token 消耗与预算限制，支持 soft/hard 两级限制与 compaction 触发判断。
    设计为不可变：consume() 返回新实例。

    参数:
        model_context_window: 模型上下文窗口大小（token 数）；0 表示不限。
        used_tokens: 已消耗 token 数。
        soft_limit_ratio: soft 限制比例，默认 0.75。
        hard_limit_ratio: hard 限制比例，默认 0.90。
        compaction_trigger_ratio: compaction 触发比例，默认 0.70。
    """

    model_context_window: int = 0
    used_tokens: int = 0
    soft_limit_ratio: float = _DEFAULT_SOFT_LIMIT_RATIO
    hard_limit_ratio: float = _DEFAULT_HARD_LIMIT_RATIO
    compaction_trigger_ratio: float = _DEFAULT_COMPACTION_TRIGGER_RATIO

    @property
    def soft_limit(self) -> int:
        """soft 限制 token 数（超出时警告用户）。"""
        return int(self.model_context_window * self.soft_limit_ratio)

    @property
    def hard_limit(self) -> int:
        """hard 限制 token 数（超出时拒绝输入）。"""
        return int(self.model_context_window * self.hard_limit_ratio)

    @property
    def compaction_threshold(self) -> int:
        """compaction 触发阈值 token 数。"""
        return int(self.model_context_window * self.compaction_trigger_ratio)

    @property
    def usage_ratio(self) -> float:
        """已消耗比例（0.0 ~ 1.0+）。"""
        if self.model_context_window == 0:
            return 0.0
        return self.used_tokens / self.model_context_window

    @property
    def remaining_budget(self) -> int:
        """hard_limit 下的剩余预算。"""
        return max(0, self.hard_limit - self.used_tokens)

    def is_above_soft_limit(self) -> bool:
        """是否已超过 soft 限制（严格大于）。"""
        if self.model_context_window == 0:
            return False
        return self.used_tokens > self.soft_limit

    def is_above_hard_limit(self) -> bool:
        """是否已超过 hard 限制（严格大于）。"""
        if self.model_context_window == 0:
            return False
        return self.used_tokens > self.hard_limit

    def should_trigger_compaction(self) -> bool:
        """是否应触发上下文压缩。"""
        if self.model_context_window == 0:
            return False
        return self.used_tokens >= self.compaction_threshold

    def consume(self, tokens: int) -> ContextBudgetState:
        """消耗指定 token 数，返回新实例。

        参数:
            tokens: 本次消耗 token 数。

        返回:
            更新后的 ContextBudgetState。
        """
        return ContextBudgetState(
            model_context_window=self.model_context_window,
            used_tokens=self.used_tokens + tokens,
            soft_limit_ratio=self.soft_limit_ratio,
            hard_limit_ratio=self.hard_limit_ratio,
            compaction_trigger_ratio=self.compaction_trigger_ratio,
        )


class ToolResultBudgetCapper:
    """工具结果预算裁剪器。

    对工具结果按 size 升序排列后公平分配 token 预算，
    确保小结果优先获得足额分配，大结果按比例截断。

    参数:
        total_budget: 分配给工具结果的总 token 预算。
    """

    def __init__(self, total_budget: int) -> None:
        """初始化裁剪器。

        参数:
            total_budget: 总 token 预算。
        """
        self._total_budget = total_budget

    def allocate(
        self,
        results: list[_T],
        key: callable[[_T], int],
    ) -> list[_T]:
        """升序公平分配预算，返回附加 budget 字段的结果副本。

        算法：
        1. 按 size 升序排列结果
        2. 每项基础预算 = floor(total_budget / N)
        3. 余数逐一追加到最小的结果（索引顺序）
        4. 每项分配预算 = min(项大小, 分配预算)

        参数:
            results: 待分配的工具结果列表。
            key: 从结果提取 size（token 估算）的 callable。

        返回:
            附加了 int budget 字段的结果列表，按原始 size 升序排列。
        """
        if not results:
            return []

        n = len(results)
        # 按 size 升序排列
        sorted_results = sorted(results, key=key)
        sizes = [key(r) for r in sorted_results]

        if n == 0:
            return []

        base = self._total_budget // n
        remainder = self._total_budget % n

        allocated = []
        for i, r in enumerate(sorted_results):
            # 余数追加到前 remainder 个（最小的）
            item_budget = base + (1 if i < remainder else 0)
            # 预算不可超过原始大小
            capped = min(item_budget, sizes[i])
            result = dict(r) if isinstance(r, dict) else {**r.__dict__}
            result["budget"] = capped
            allocated.append(result)

        return allocated
