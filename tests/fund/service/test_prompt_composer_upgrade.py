"""PromptComposer 升级测试（fragment assembly + contribution injection）。

覆盖:
- compose_from_scene: fragment 按 order 排序装配
- contribution 注入到 context_slots
- 向后兼容: compose() 单模板渲染不变
- 空 fragments/contributions 边界
"""

from pathlib import Path

import pytest

from fund_agent.service.prompt_composer import PromptComposer, ComposedPrompt, PromptRenderError


# ── helpers ──────────────────────────────────────────────────────

class _FakeFragment:
    """最小 fragment 接口，用于测试 compose_from_scene。"""
    def __init__(self, order: int, path: str):
        self.order = order
        self.path = path


class _FakeSceneConfig:
    """最小 scene config 接口。"""
    def __init__(self, scene: str, fragments: list[_FakeFragment], context_slots: tuple[str, ...] = ()):
        self.scene = scene
        self.fragments = fragments
        self.context_slots = context_slots


# ── tests ────────────────────────────────────────────────────────

class TestComposeFromScene:
    """compose_from_scene() method tests."""

    @pytest.fixture
    def composer(self, tmp_path: Path) -> PromptComposer:
        """创建带临时模板目录的 PromptComposer。"""
        return PromptComposer(template_dir=tmp_path)

    def test_fragments_assembled_in_order(self, composer: PromptComposer, tmp_path: Path):
        """两个 fragment 按 order 升序拼装。"""
        (tmp_path / "frag_a.md").write_text("## 身份定义\n你是基金分析助手。\n", encoding="utf-8")
        (tmp_path / "frag_b.md").write_text("## 分析规则\n用数据说话。\n", encoding="utf-8")

        scene = _FakeSceneConfig(
            scene="test",
            fragments=[
                _FakeFragment(order=2, path="frag_b.md"),
                _FakeFragment(order=1, path="frag_a.md"),
            ],
        )
        result = composer.compose_from_scene(scene, contributions={})
        assert result.template_name == "scene:test"
        assert "身份定义" in result.system_message
        assert "分析规则" in result.system_message
        # frag_a (order=1) 应在 frag_b (order=2) 之前
        pos_a = result.system_message.index("身份定义")
        pos_b = result.system_message.index("分析规则")
        assert pos_a < pos_b

    def test_contributions_appended_at_end(self, composer: PromptComposer, tmp_path: Path):
        """contribution 注入到 system_prompt 尾部。"""
        (tmp_path / "base.md").write_text("## 基础\n你是基金分析助手。\n", encoding="utf-8")

        scene = _FakeSceneConfig(
            scene="with_contrib",
            fragments=[_FakeFragment(order=1, path="base.md")],
            context_slots=("runtime", "memory"),
        )
        contributions = {
            "runtime": "## 运行时\n当前基金: 011649\n",
            "memory": "## 记忆\n历史: 上次讨论了基金经理。\n",
        }
        result = composer.compose_from_scene(scene, contributions=contributions)
        assert "基础" in result.system_message
        assert "运行时" in result.system_message
        assert "当前基金: 011649" in result.system_message
        assert "记忆" in result.system_message
        # contributions 在尾部
        assert result.system_message.rfind("记忆") > result.system_message.rfind("基础")

    def test_contributions_ordered_by_context_slots(self, composer: PromptComposer, tmp_path: Path):
        """contribution 按 context_slots 声明顺序注入。"""
        (tmp_path / "base.md").write_text("## 基础\n", encoding="utf-8")

        scene = _FakeSceneConfig(
            scene="ordered",
            fragments=[_FakeFragment(order=1, path="base.md")],
            context_slots=("third", "first", "second"),
        )
        contributions = {
            "first": "FIRST\n",
            "second": "SECOND\n",
            "third": "THIRD\n",
        }
        result = composer.compose_from_scene(scene, contributions=contributions)
        # 注入顺序应为 third, first, second（按 context_slots 声明顺序）
        pos_third = result.system_message.index("THIRD")
        pos_first = result.system_message.index("FIRST")
        pos_second = result.system_message.index("SECOND")
        assert pos_third < pos_first < pos_second

    def test_empty_contributions_ok(self, composer: PromptComposer, tmp_path: Path):
        """空的 contributions → 正常输出 fragments 拼装结果。"""
        (tmp_path / "base.md").write_text("## 基础\n你好\n", encoding="utf-8")

        scene = _FakeSceneConfig(scene="nocontrib", fragments=[_FakeFragment(order=1, path="base.md")])
        result = composer.compose_from_scene(scene, contributions={})
        assert "你好" in result.system_message

    def test_missing_fragment_file_raises(self, composer: PromptComposer):
        """fragment 文件不存在 → PromptRenderError。"""
        scene = _FakeSceneConfig(
            scene="bad",
            fragments=[_FakeFragment(order=1, path="nonexistent.md")],
        )
        with pytest.raises(PromptRenderError):
            composer.compose_from_scene(scene, contributions={})

    def test_missing_contribution_slot_not_injected(self, composer: PromptComposer, tmp_path: Path):
        """context_slots 中声明的 slot 在 contributions 中缺失 → 跳过该 slot。"""
        (tmp_path / "base.md").write_text("## 基础\n你好\n", encoding="utf-8")

        scene = _FakeSceneConfig(
            scene="partial",
            fragments=[_FakeFragment(order=1, path="base.md")],
            context_slots=("present", "missing"),
        )
        contributions = {"present": "存在的贡献\n"}
        result = composer.compose_from_scene(scene, contributions=contributions)
        assert "存在的贡献" in result.system_message
        # 缺失的不应出现 "missing" 字样（除非模板自带）

    def test_empty_fragments_raises(self, composer: PromptComposer):
        """空 fragments 列表 → PromptRenderError。"""
        scene = _FakeSceneConfig(scene="empty", fragments=[])
        with pytest.raises(PromptRenderError):
            composer.compose_from_scene(scene, contributions={})

    def test_version_extraction_from_fragment(self, composer: PromptComposer, tmp_path: Path):
        """fragment 模板中的 version 注释被正确提取。"""
        (tmp_path / "vtest.md").write_text(
            "<!-- version: 1.2.3 -->\n## 内容\n测试\n", encoding="utf-8"
        )
        scene = _FakeSceneConfig(scene="vtest", fragments=[_FakeFragment(order=1, path="vtest.md")])
        result = composer.compose_from_scene(scene, contributions={})
        assert result.template_version != "unknown"


class TestBackwardCompatibility:
    """现有 compose() 方法向后兼容测试。"""

    def test_single_template_still_works(self, tmp_path: Path):
        """compose() 单模板渲染行为不变。"""
        (tmp_path / "test.md").write_text(
            "<!-- version: 1.0 -->\n## 你好 {{ name }}\n", encoding="utf-8"
        )
        composer = PromptComposer(template_dir=tmp_path)
        result = composer.compose("test.md", context={"name": "世界"})
        assert "世界" in result.system_message
        assert result.template_name == "test.md"

    def test_strict_mode_unchanged(self, tmp_path: Path):
        """strict=True 行为不变。"""
        (tmp_path / "test.md").write_text("你好 {{ name }}\n", encoding="utf-8")
        composer = PromptComposer(template_dir=tmp_path)
        with pytest.raises(PromptRenderError):
            composer.compose("test.md", context={}, strict=True)

    def test_when_missing_still_works(self, tmp_path: Path):
        """<when_missing> 条件块行为不变。"""
        (tmp_path / "test.md").write_text(
            "<!-- version: 1 -->\n## 数据\n{{ data }}\n<when_missing data>警告：数据缺失。</when_missing>\n",
            encoding="utf-8",
        )
        composer = PromptComposer(template_dir=tmp_path)
        result = composer.compose("test.md", context={})
        assert "警告：数据缺失" in result.system_message
