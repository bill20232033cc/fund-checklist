"""上下文预算治理测试。

覆盖:
- ContextBudgetState: soft_limit(75%) / hard_limit(90%) 计算
- 预算消耗追踪与阈值判断
- ToolResultBudgetCapper: 升序公平分配裁剪
- Compaction 触发: 70% token 阈值
- 边界条件: 空输入、0 token、恰好阈值
"""

from fund_agent.agent.context_budget import (
    ContextBudgetState,
    ToolResultBudgetCapper,
)


class TestContextBudgetState:
    """ContextBudgetState 状态计算测试。"""

    def test_default_limits_with_128k_window(self):
        """128k 窗口默认 soft=75% hard=90%。"""
        budget = ContextBudgetState(model_context_window=128000)
        assert budget.soft_limit == 96000   # 75%
        assert budget.hard_limit == 115200   # 90%
        assert budget.used_tokens == 0

    def test_custom_ratios(self):
        """自定义 soft/hard 比例。"""
        budget = ContextBudgetState(
            model_context_window=100000,
            soft_limit_ratio=0.8,
            hard_limit_ratio=0.95,
        )
        assert budget.soft_limit == 80000
        assert budget.hard_limit == 95000

    def test_consume_tokens_updates_used(self):
        """消耗 token 正确累加。"""
        budget = ContextBudgetState(model_context_window=100000)
        budget = budget.consume(5000)
        assert budget.used_tokens == 5000
        budget = budget.consume(3000)
        assert budget.used_tokens == 8000

    def test_is_above_soft_limit(self):
        """超过 soft_limit 返回 True。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=80000)
        assert budget.is_above_soft_limit() is True

    def test_is_below_soft_limit(self):
        """低于 soft_limit 返回 False。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=50000)
        assert budget.is_above_soft_limit() is False

    def test_is_above_hard_limit(self):
        """超过 hard_limit 返回 True。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=95000)
        assert budget.is_above_hard_limit() is True

    def test_is_below_hard_limit(self):
        """低于 hard_limit 返回 False。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=80000)
        assert budget.is_above_hard_limit() is False

    def test_exactly_at_soft_limit(self):
        """恰好等于 soft_limit 不算超过。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=75000)
        assert budget.is_above_soft_limit() is False

    def test_exactly_at_hard_limit(self):
        """恰好等于 hard_limit 不算超过。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=90000)
        assert budget.is_above_hard_limit() is False

    def test_should_compact_at_70_percent(self):
        """70% token 消耗时触发 compaction。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=70000)
        assert budget.should_trigger_compaction() is True

    def test_no_compact_below_70_percent(self):
        """低于 70% 不触发 compaction。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=65000)
        assert budget.should_trigger_compaction() is False

    def test_usage_ratio(self):
        """usage_ratio 正确计算。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=25000)
        assert budget.usage_ratio == 0.25

    def test_remaining_budget(self):
        """remaining_budget 为 hard_limit - used。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=30000)
        assert budget.remaining_budget == 60000  # 90000 - 30000

    def test_zero_window_handled(self):
        """0 窗口时不触发任何限制。"""
        budget = ContextBudgetState(model_context_window=0, used_tokens=1000)
        assert budget.is_above_soft_limit() is False
        assert budget.is_above_hard_limit() is False
        assert budget.should_trigger_compaction() is False
        assert budget.usage_ratio == 0.0

    def test_immutable_consume(self):
        """consume 返回新实例，不修改原实例。"""
        budget = ContextBudgetState(model_context_window=100000, used_tokens=1000)
        new_budget = budget.consume(500)
        assert budget.used_tokens == 1000
        assert new_budget.used_tokens == 1500


class TestToolResultBudgetCapper:
    """ToolResultBudgetCapper 升序公平分配裁剪测试。"""

    def test_fair_allocation_equal_distribution(self):
        """预算可均分时每项获得等额。"""
        results = [
            {"name": "r1", "size": 100},
            {"name": "r2", "size": 100},
            {"name": "r3", "size": 100},
        ]
        capper = ToolResultBudgetCapper(total_budget=300)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        assert allocated[0]["budget"] == 100
        assert allocated[1]["budget"] == 100
        assert allocated[2]["budget"] == 100

    def test_fair_allocation_remainder_to_smallest(self):
        """余数优先分配给最小的结果。"""
        results = [
            {"name": "r1", "size": 50},
            {"name": "r2", "size": 200},
            {"name": "r3", "size": 80},
        ]
        capper = ToolResultBudgetCapper(total_budget=100)
        # 排序后: r1(50), r3(80), r2(200)
        # 每项 base = 33, 余数 1 → 分给最小的 r1
        allocated = capper.allocate(results, key=lambda r: r["size"])
        # r1: 33+1=34, r3: 33, r2: 33
        assert allocated[0]["budget"] == 34  # r1 (最小)
        assert allocated[1]["budget"] == 33  # r3
        assert allocated[2]["budget"] == 33  # r2

    def test_allocation_sorted_ascending(self):
        """分配结果按原始大小升序排列。"""
        results = [
            {"name": "large", "size": 1000},
            {"name": "small", "size": 10},
            {"name": "mid", "size": 100},
        ]
        capper = ToolResultBudgetCapper(total_budget=300)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        sizes = [r["size"] for r in allocated]
        assert sizes == [10, 100, 1000]  # 升序

    def test_budget_exceeds_total_size(self):
        """预算超过总大小，不裁剪。"""
        results = [
            {"name": "r1", "size": 50},
            {"name": "r2", "size": 30},
        ]
        capper = ToolResultBudgetCapper(total_budget=200)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        # 升序排列后: r2(size=30) → r1(size=50)
        # 两项均不截断（预算充足），各自保留原始大小
        assert allocated[0]["name"] == "r2"
        assert allocated[0]["budget"] == 30
        assert allocated[1]["name"] == "r1"
        assert allocated[1]["budget"] == 50

    def test_empty_results(self):
        """空结果列表返回空列表。"""
        capper = ToolResultBudgetCapper(total_budget=100)
        allocated = capper.allocate([], key=lambda r: r["size"])
        assert allocated == []

    def test_single_result_gets_all_budget(self):
        """单个结果获得全部预算。"""
        results = [{"name": "only", "size": 500}]
        capper = ToolResultBudgetCapper(total_budget=200)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        assert allocated[0]["budget"] == 200

    def test_zero_budget(self):
        """0 预算时每项分配 0。"""
        results = [
            {"name": "r1", "size": 100},
            {"name": "r2", "size": 200},
        ]
        capper = ToolResultBudgetCapper(total_budget=0)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        assert allocated[0]["budget"] == 0
        assert allocated[1]["budget"] == 0

    def test_truncation_applied_when_budget_lt_size(self):
        """预算不足时结果被截断。"""
        results = [
            {"name": "r1", "size": 100},
            {"name": "r2", "size": 100},
        ]
        capper = ToolResultBudgetCapper(total_budget=80)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        # 每项 base=40, 余数 0, 但实际 size=100，所以被截断为 40
        assert allocated[0]["budget"] == 40
        assert allocated[1]["budget"] == 40

    def test_truncation_preserves_original_data(self):
        """原始数据不受截断影响，仅添加 budget 字段。"""
        results = [
            {"name": "r1", "size": 1000, "data": "important"},
        ]
        capper = ToolResultBudgetCapper(total_budget=100)
        allocated = capper.allocate(results, key=lambda r: r["size"])
        assert allocated[0]["name"] == "r1"
        assert allocated[0]["data"] == "important"
        assert allocated[0]["size"] == 1000  # 原始 size 保留
        assert allocated[0]["budget"] == 100  # 分配预算
