"""Scene Config 测试。

覆盖:
- SceneModelSpec / SceneRuntimeSpec 构造与默认值
- SceneConfig 字段完整性
- ASK_SCENE_CONFIG vs INTERACTIVE_SCENE_CONFIG 差异
- allowed_tools scene 级过滤
- fragments 完整性
"""

import pytest

from pathlib import Path

from fund_agent.service.scene_config import (
    ASK_SCENE_CONFIG,
    FIX_SCENE_CONFIG,
    INTERACTIVE_SCENE_CONFIG,
    SceneConfig,
    SceneModelSpec,
    SceneRuntimeSpec,
)
from fund_agent.service.prompt_composer import Fragment, PromptComposer


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

    def test_uses_pro_model(self):
        """interactive scene 使用 deepseek-v4-pro 模型。"""
        assert INTERACTIVE_SCENE_CONFIG.model.default_name == "deepseek-v4-pro"

    def test_higher_temperature(self):
        """interactive scene temperature 更高（0.7）。"""
        assert INTERACTIVE_SCENE_CONFIG.model.temperature == 0.7

    def test_max_iterations_12(self):
        """interactive scene 迭代上限为 12（2026-08-05 裁决，配合空结果强制收敛）。"""
        assert INTERACTIVE_SCENE_CONFIG.runtime.max_iterations == 12

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
        """interactive 声明了 runtime、fund_context、memory、retrieval 等 slot。"""
        assert "runtime" in INTERACTIVE_SCENE_CONFIG.context_slots
        assert "fund_context" in INTERACTIVE_SCENE_CONFIG.context_slots
        assert "memory" in INTERACTIVE_SCENE_CONFIG.context_slots
        assert "retrieval" in INTERACTIVE_SCENE_CONFIG.context_slots

    def test_has_history_slot(self):
        """interactive scene 的 context_slots 包含 history。"""
        assert "history" in INTERACTIVE_SCENE_CONFIG.context_slots

    def test_interactive_has_more_tools_than_ask(self):
        """interactive 工具集严格大于 ask。"""
        assert len(INTERACTIVE_SCENE_CONFIG.allowed_tools) > len(ASK_SCENE_CONFIG.allowed_tools)


# ── helpers ──────────────────────────────────────────────────────

def _prompts_dir() -> Path:
    """Return the real prompts/ template directory."""
    return Path(__file__).resolve().parents[3] / "fund_agent" / "service" / "prompts"


class TestPromptGuidanceContent:
    """S4 prompt 引导内容测试（真实 fragment 组合后断言硬规则存在）。"""

    @pytest.fixture
    def composer(self) -> PromptComposer:
        """使用真实 prompts 目录的 PromptComposer。"""

        return PromptComposer(template_dir=_prompts_dir())

    def _compose(self, composer: PromptComposer, scene_config: SceneConfig) -> str:
        """组合 scene 的 system message。"""

        return composer.compose_from_scene(scene_config, contributions={}).system_message

    def test_interactive_no_fact_rule_hard(self, composer: PromptComposer):
        """interactive：观点类回答只陈述客观事实、拒绝判断、禁建议预测措辞。"""

        message = self._compose(composer, INTERACTIVE_SCENE_CONFIG)
        assert "禁止发起空搜索" in message
        assert "必须直接返回 JSON" in message
        assert "中性表述" in message
        assert "只陈述年报客观事实" in message
        assert "无法给出判断" in message
        assert "操作建议措辞" in message
        assert "禁止预测未来收益或市场走势" in message
        assert "示例" in message

    def test_interactive_empty_search_budget_rule(self, composer: PromptComposer):
        """interactive：连续 2 次无命中即停止搜索，不得耗尽预算。"""

        message = self._compose(composer, INTERACTIVE_SCENE_CONFIG)
        assert "连续 2 次无命中" in message
        assert "未找到相关数据" in message
        assert "耗尽预算" in message

    def test_ask_no_fact_and_ref_copy_rules(self, composer: PromptComposer):
        """ask：中性表述/拒绝判断/禁预测 + 连续 2 次无命中即停 + ref 复制。"""

        message = self._compose(composer, ASK_SCENE_CONFIG)
        assert "禁止发起空搜索" in message
        assert "中性表述" in message
        assert "只陈述年报客观事实" in message
        assert "无法给出判断" in message
        assert "禁止预测未来收益或市场走势" in message
        assert "连续 2 次无命中" in message
        assert "必须从 search_document / list_tables 结果中复制" in message


# ── Fix Scene Config ─────────────────────────────────────────────

class TestFixSceneConfig:
    """FIX_SCENE_CONFIG 测试。"""

    def test_scene_name(self):
        assert FIX_SCENE_CONFIG.scene == "fix"

    def test_fragments_include_template(self):
        paths = {f.path for f in FIX_SCENE_CONFIG.fragments}
        assert "scenes/fix.md" in paths

    def test_context_slots(self):
        assert "chapter_content" in FIX_SCENE_CONFIG.context_slots
        assert "audit_feedback" in FIX_SCENE_CONFIG.context_slots
        assert "chapter_contract" in FIX_SCENE_CONFIG.context_slots
        assert len(FIX_SCENE_CONFIG.context_slots) == 3

    def test_model_name(self):
        assert FIX_SCENE_CONFIG.model.default_name == "deepseek-v4-flash"

    def test_temperature(self):
        assert FIX_SCENE_CONFIG.model.temperature == 0.2

    def test_max_iterations(self):
        assert FIX_SCENE_CONFIG.runtime.max_iterations == 12

    def test_allowed_tools(self):
        tools = set(FIX_SCENE_CONFIG.allowed_tools)
        assert "search_document" in tools
        assert "read_section" in tools
        assert "list_tables" in tools
        assert "read_table" in tools
        assert "get_excerpt" in tools
        assert len(tools) == 5

    def test_four_fragments(self):
        assert len(FIX_SCENE_CONFIG.fragments) == 4


# ── rendering ────────────────────────────────────────────────────

class TestComposeFromSceneFixRendering:
    """PromptComposer.compose_from_scene 渲染测试 for FIX scene。"""

    @pytest.fixture
    def composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_prompts_dir())

    def test_renders_fix_scene(self, composer: PromptComposer):
        result = composer.compose_from_scene(FIX_SCENE_CONFIG, contributions={})
        assert result.system_message
        assert "占位符补强" in result.system_message
        assert result.template_name == "scene:fix"
