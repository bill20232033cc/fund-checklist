"""Scene Config 测试。

覆盖:
- SceneModelSpec / SceneRuntimeSpec 构造与默认值
- SceneConfig 字段完整性
- ASK_SCENE_CONFIG vs INTERACTIVE_SCENE_CONFIG 差异
- allowed_tools scene 级过滤
- fragments 完整性
"""

import pytest

from fund_agent.service.scene_config import (
    ASK_SCENE_CONFIG,
    INTERACTIVE_SCENE_CONFIG,
    SceneConfig,
    SceneModelSpec,
    SceneRuntimeSpec,
)
from fund_agent.service.prompt_composer import Fragment


class TestSceneModelSpec:
    """SceneModelSpec 测试。"""

    def test_default_construction(self):
        spec = SceneModelSpec(default_name="test-model")
        assert spec.default_name == "test-model"
        assert spec.temperature == 0.7

    def test_custom_temperature(self):
        spec = SceneModelSpec(default_name="test", temperature=0.3)
        assert spec.temperature == 0.3

    def test_frozen(self):
        spec = SceneModelSpec(default_name="test")
        with pytest.raises(Exception):
            spec.default_name = "other"  # type: ignore[misc]


class TestSceneRuntimeSpec:
    """SceneRuntimeSpec 测试。"""

    def test_default_construction(self):
        spec = SceneRuntimeSpec()
        assert spec.max_iterations == 12
        assert spec.tool_timeout_seconds == 60.0

    def test_custom_values(self):
        spec = SceneRuntimeSpec(max_iterations=8, tool_timeout_seconds=30.0)
        assert spec.max_iterations == 8
        assert spec.tool_timeout_seconds == 30.0


class TestSceneConfig:
    """SceneConfig 测试。"""

    def test_minimal_construction(self):
        config = SceneConfig(
            scene="test",
            fragments=(Fragment(order=1, path="test.md"),),
        )
        assert config.scene == "test"
        assert len(config.fragments) == 1
        assert config.allowed_tools == ()  # 默认空=全部允许

    def test_with_allowed_tools(self):
        config = SceneConfig(
            scene="test",
            fragments=(Fragment(order=1, path="test.md"),),
            allowed_tools=("search_document", "read_section"),
        )
        assert "search_document" in config.allowed_tools
        assert "read_section" in config.allowed_tools

    def test_frozen(self):
        config = SceneConfig(scene="test", fragments=(Fragment(order=1, path="t.md"),))
        with pytest.raises(Exception):
            config.scene = "changed"  # type: ignore[misc]


class TestAskSceneConfig:
    """ASK_SCENE_CONFIG 预设测试。"""

    def test_uses_flash_model(self):
        """ask scene 使用 flash 模型。"""
        assert "flash" in ASK_SCENE_CONFIG.model.default_name

    def test_low_temperature(self):
        """ask scene temperature 低（0.3），追求确定性强。"""
        assert ASK_SCENE_CONFIG.model.temperature == 0.3

    def test_max_iterations_8(self):
        """ask scene 最大 8 次迭代。"""
        assert ASK_SCENE_CONFIG.runtime.max_iterations == 8

    def test_four_fragments(self):
        """ask scene 有 4 个 fragments。"""
        assert len(ASK_SCENE_CONFIG.fragments) == 4

    def test_aggregate_not_in_allowed_tools(self):
        """ask 不允许 aggregate_multi_year tool。"""
        assert "aggregate_multi_year_annual_performance" not in ASK_SCENE_CONFIG.allowed_tools

    def test_core_tools_in_allowed(self):
        """ask 有 5 个核心 reading tools。"""
        tools = set(ASK_SCENE_CONFIG.allowed_tools)
        assert "search_document" in tools
        assert "read_section" in tools
        assert "list_tables" in tools
        assert "read_table" in tools
        assert "get_excerpt" in tools
        assert len(tools) == 5


class TestInteractiveSceneConfig:
    """INTERACTIVE_SCENE_CONFIG 预设测试。"""

    def test_uses_thinking_model(self):
        """interactive scene 使用 thinking 模型。"""
        assert "thinking" in INTERACTIVE_SCENE_CONFIG.model.default_name

    def test_higher_temperature(self):
        """interactive scene temperature 更高（0.7）。"""
        assert INTERACTIVE_SCENE_CONFIG.model.temperature == 0.7

    def test_max_iterations_20(self):
        """interactive scene 允许多达 20 次迭代。"""
        assert INTERACTIVE_SCENE_CONFIG.runtime.max_iterations == 20

    def test_five_fragments(self):
        """interactive scene 比 ask 多 1 个 fragment（共 5 个）。"""
        assert len(INTERACTIVE_SCENE_CONFIG.fragments) == 5

    def test_interactive_fragment_last(self):
        """interactive/scene.md 在最后一个位置。"""
        last = INTERACTIVE_SCENE_CONFIG.fragments[-1]
        assert last.path == "interactive/scene.md"
        assert last.order == 5

    def test_aggregate_in_allowed_tools(self):
        """interactive 允许 aggregate_multi_year tool。"""
        assert "aggregate_multi_year_annual_performance" in INTERACTIVE_SCENE_CONFIG.allowed_tools

    def test_context_slots_declared(self):
        """interactive 声明了 runtime、fund_context、memory 三个 slot。"""
        assert "runtime" in INTERACTIVE_SCENE_CONFIG.context_slots
        assert "fund_context" in INTERACTIVE_SCENE_CONFIG.context_slots
        assert "memory" in INTERACTIVE_SCENE_CONFIG.context_slots

    def test_interactive_has_more_tools_than_ask(self):
        """interactive 工具集严格大于 ask。"""
        assert len(INTERACTIVE_SCENE_CONFIG.allowed_tools) > len(ASK_SCENE_CONFIG.allowed_tools)
