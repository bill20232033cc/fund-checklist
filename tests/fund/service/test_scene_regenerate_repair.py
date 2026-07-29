"""Regenerate / Repair Scene Config 测试。

覆盖:
- REGENERATE_SCENE_CONFIG / REPAIR_SCENE_CONFIG 存在性与字段
- fragments 包含对应 prompt 模板
- context_slots 声明正确
- max_iterations 值
- PromptComposer compose_from_scene 渲染输出
"""

from pathlib import Path

import pytest

from fund_agent.service.scene_config import (
    REGENERATE_SCENE_CONFIG,
    REPAIR_SCENE_CONFIG,
)
from fund_agent.service.prompt_composer import PromptComposer


# ── helpers ──────────────────────────────────────────────────────

def _prompts_dir() -> Path:
    """Return the real prompts/ template directory."""
    return Path(__file__).resolve().parents[3] / "fund_agent" / "service" / "prompts"


# ── existence ────────────────────────────────────────────────────

class TestRegenerateSceneConfig:
    """REGENERATE_SCENE_CONFIG 测试。"""

    def test_scene_name(self):
        assert REGENERATE_SCENE_CONFIG.scene == "regenerate"

    def test_fragments_include_template(self):
        paths = {f.path for f in REGENERATE_SCENE_CONFIG.fragments}
        assert "scenes/regenerate.md" in paths

    def test_context_slots(self):
        assert "chapter_content" in REGENERATE_SCENE_CONFIG.context_slots
        assert "audit_feedback" in REGENERATE_SCENE_CONFIG.context_slots
        assert "chapter_contract" in REGENERATE_SCENE_CONFIG.context_slots
        assert len(REGENERATE_SCENE_CONFIG.context_slots) == 3

    def test_model_name(self):
        assert REGENERATE_SCENE_CONFIG.model.default_name == "deepseek-v4-pro"

    def test_temperature(self):
        assert REGENERATE_SCENE_CONFIG.model.temperature == 0.3

    def test_max_iterations(self):
        assert REGENERATE_SCENE_CONFIG.runtime.max_iterations == 24

    def test_allowed_tools(self):
        tools = set(REGENERATE_SCENE_CONFIG.allowed_tools)
        assert "search_document" in tools
        assert "read_section" in tools
        assert "list_tables" in tools
        assert "read_table" in tools
        assert "get_excerpt" in tools
        assert len(tools) == 5

    def test_four_fragments(self):
        assert len(REGENERATE_SCENE_CONFIG.fragments) == 4


class TestRepairSceneConfig:
    """REPAIR_SCENE_CONFIG 测试。"""

    def test_scene_name(self):
        assert REPAIR_SCENE_CONFIG.scene == "repair"

    def test_fragments_include_template(self):
        paths = {f.path for f in REPAIR_SCENE_CONFIG.fragments}
        assert "scenes/repair.md" in paths

    def test_context_slots(self):
        assert "chapter_content" in REPAIR_SCENE_CONFIG.context_slots
        assert "audit_feedback" in REPAIR_SCENE_CONFIG.context_slots
        assert "chapter_contract" in REPAIR_SCENE_CONFIG.context_slots
        assert len(REPAIR_SCENE_CONFIG.context_slots) == 3

    def test_model_name(self):
        assert REPAIR_SCENE_CONFIG.model.default_name == "deepseek-v4-flash"

    def test_temperature(self):
        assert REPAIR_SCENE_CONFIG.model.temperature == 0.2

    def test_max_iterations(self):
        assert REPAIR_SCENE_CONFIG.runtime.max_iterations == 16

    def test_allowed_tools(self):
        tools = set(REPAIR_SCENE_CONFIG.allowed_tools)
        assert "search_document" in tools
        assert "read_section" in tools
        assert "list_tables" in tools
        assert "read_table" in tools
        assert "get_excerpt" in tools
        assert len(tools) == 5

    def test_four_fragments(self):
        assert len(REPAIR_SCENE_CONFIG.fragments) == 4


# ── rendering ────────────────────────────────────────────────────

class TestComposeFromSceneRendering:
    """PromptComposer.compose_from_scene 渲染测试。"""

    @pytest.fixture
    def composer(self) -> PromptComposer:
        return PromptComposer(template_dir=_prompts_dir())

    def test_renders_regenerate_scene(self, composer: PromptComposer):
        result = composer.compose_from_scene(REGENERATE_SCENE_CONFIG, contributions={})
        assert result.system_message
        assert "整章重建" in result.system_message
        assert result.template_name == "scene:regenerate"

    def test_renders_repair_scene(self, composer: PromptComposer):
        result = composer.compose_from_scene(REPAIR_SCENE_CONFIG, contributions={})
        assert result.system_message
        assert "局部修复" in result.system_message
        assert result.template_name == "scene:repair"

    def test_regenerate_differs_from_repair(self, composer: PromptComposer):
        """regenerate 和 repair 输出应不同。"""
        regen = composer.compose_from_scene(REGENERATE_SCENE_CONFIG, contributions={})
        repair = composer.compose_from_scene(REPAIR_SCENE_CONFIG, contributions={})
        assert regen.system_message != repair.system_message
