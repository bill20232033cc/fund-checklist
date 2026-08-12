"""Scene Config — 描述 prompt routing 的 scene 配置（fragments + model + runtime + tools）。

参考 Dayu config/prompts/manifests/ 结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fund_agent.fund.document_tools.constants import ToolName

from .prompt_composer import Fragment


@dataclass(frozen=True)
class SceneModelSpec:
    """Scene 级模型规格。

    参数:
        default_name: 默认模型名。
        temperature: LLM temperature。
    """

    default_name: str
    temperature: float = 0.7


@dataclass(frozen=True)
class SceneRuntimeSpec:
    """Scene 级运行时规格。

    参数:
        max_iterations: 工具调用循环最大迭代次数。
        tool_timeout_seconds: 单次工具调用超时秒数。
    """

    max_iterations: int = 12
    tool_timeout_seconds: float = 60.0


@dataclass(frozen=True)
class SceneConfig:
    """单个 scene 的完整配置。

    参数:
        scene: scene 标识名（如 "ask"/"interactive"）。
        fragments: 按 order 排序的 fragment 列表。
        context_slots: 声明可注入 contribution 的 slot 名。
        model: 模型规格。
        runtime: 运行时规格。
        allowed_tools: 该 scene 允许的 tool name 集合；空元组表示全部允许。
    """

    scene: str
    fragments: tuple[Fragment, ...]
    context_slots: tuple[str, ...] = ()
    model: SceneModelSpec = field(default_factory=lambda: SceneModelSpec(default_name="deepseek-v4-flash"))
    runtime: SceneRuntimeSpec = field(default_factory=lambda: SceneRuntimeSpec())
    allowed_tools: tuple[str, ...] = ()


# ── ASK Scene ───────────────────────────────────────────────────

_ASK_FRAGMENTS = (
    Fragment(order=1, path="base/agents.md"),
    Fragment(order=2, path="base/soul.md"),
    Fragment(order=3, path="base/fact_rules.md"),
    Fragment(order=4, path="ask/tools_scene.md"),
)

ASK_SCENE_CONFIG = SceneConfig(
    scene="ask",
    fragments=_ASK_FRAGMENTS,
    context_slots=(),
    model=SceneModelSpec(default_name="deepseek-v4-flash", temperature=0.3),
    runtime=SceneRuntimeSpec(max_iterations=8),
    allowed_tools=(
        ToolName.SEARCH_DOCUMENT.value,
        ToolName.READ_SECTION.value,
        ToolName.LIST_TABLES.value,
        ToolName.READ_TABLE.value,
        ToolName.GET_EXCERPT.value,
    ),
)

# ── Interactive Scene ───────────────────────────────────────────

_INTERACTIVE_FRAGMENTS = (
    Fragment(order=1, path="base/agents.md"),
    Fragment(order=2, path="base/soul.md"),
    Fragment(order=3, path="base/fact_rules.md"),
    Fragment(order=4, path="ask/tools_scene.md"),
    Fragment(order=5, path="interactive/scene.md"),
)

INTERACTIVE_SCENE_CONFIG = SceneConfig(
    scene="interactive",
    fragments=_INTERACTIVE_FRAGMENTS,
    context_slots=("runtime", "fund_context", "memory", "history", "retrieval"),
    model=SceneModelSpec(default_name="deepseek-v4-pro", temperature=0.7),
    # 2026-08-05 裁决：interactive max_iterations 20 → 12，配合空结果强制收敛
    # 防止模型过度探索；2026-08-09 裁决（P0-2）：12 → 8，锚点收敛 + aggregate
    # 单次成功 + 跨轮失败短路消除重跑后 8 是可行下界（design.md §6.10）。
    runtime=SceneRuntimeSpec(max_iterations=8),
    allowed_tools=(
        ToolName.SEARCH_DOCUMENT.value,
        ToolName.READ_SECTION.value,
        ToolName.LIST_TABLES.value,
        ToolName.READ_TABLE.value,
        ToolName.GET_EXCERPT.value,
        ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE.value,
    ),
)

# ── Regenerate Scene ──────────────────────────────────────────────

_REGENERATE_FRAGMENTS = (
    Fragment(order=1, path="base/agents.md"),
    Fragment(order=2, path="base/soul.md"),
    Fragment(order=3, path="base/fact_rules.md"),
    Fragment(order=4, path="scenes/regenerate.md"),
)

REGENERATE_SCENE_CONFIG = SceneConfig(
    scene="regenerate",
    fragments=_REGENERATE_FRAGMENTS,
    context_slots=("chapter_content", "audit_feedback", "chapter_contract"),
    model=SceneModelSpec(default_name="deepseek-v4-pro", temperature=0.3),
    runtime=SceneRuntimeSpec(max_iterations=24),
    allowed_tools=(
        ToolName.SEARCH_DOCUMENT.value,
        ToolName.READ_SECTION.value,
        ToolName.LIST_TABLES.value,
        ToolName.READ_TABLE.value,
        ToolName.GET_EXCERPT.value,
    ),
)

# ── Fix Scene ─────────────────────────────────────────────────────

_FIX_FRAGMENTS = (
    Fragment(order=1, path="base/agents.md"),
    Fragment(order=2, path="base/soul.md"),
    Fragment(order=3, path="base/fact_rules.md"),
    Fragment(order=4, path="scenes/fix.md"),
)

FIX_SCENE_CONFIG = SceneConfig(
    scene="fix",
    fragments=_FIX_FRAGMENTS,
    context_slots=("chapter_content", "audit_feedback", "chapter_contract"),
    model=SceneModelSpec(default_name="deepseek-v4-flash", temperature=0.2),
    runtime=SceneRuntimeSpec(max_iterations=12),
    allowed_tools=(
        ToolName.SEARCH_DOCUMENT.value,
        ToolName.READ_SECTION.value,
        ToolName.LIST_TABLES.value,
        ToolName.READ_TABLE.value,
        ToolName.GET_EXCERPT.value,
    ),
)

# ── Repair Scene ──────────────────────────────────────────────────

_REPAIR_FRAGMENTS = (
    Fragment(order=1, path="base/agents.md"),
    Fragment(order=2, path="base/soul.md"),
    Fragment(order=3, path="base/fact_rules.md"),
    Fragment(order=4, path="scenes/repair.md"),
)

REPAIR_SCENE_CONFIG = SceneConfig(
    scene="repair",
    fragments=_REPAIR_FRAGMENTS,
    context_slots=("chapter_content", "audit_feedback", "chapter_contract"),
    model=SceneModelSpec(default_name="deepseek-v4-flash", temperature=0.2),
    runtime=SceneRuntimeSpec(max_iterations=16),
    allowed_tools=(
        ToolName.SEARCH_DOCUMENT.value,
        ToolName.READ_SECTION.value,
        ToolName.LIST_TABLES.value,
        ToolName.READ_TABLE.value,
        ToolName.GET_EXCERPT.value,
    ),
)
