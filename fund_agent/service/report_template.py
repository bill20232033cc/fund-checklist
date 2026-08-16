"""报告模板注册表：按 template_id 提供章节契约与 prompt（§6.25 裁决 3/6）。

年报（annual_report）为默认模板，绑定既有 ch0-ch7 契约与 prompts/ch0.md..ch7.md；
季报（quarterly_snapshot）与半年报（semiannual_snapshot）为快照模板，
契约与 prompt 位于独立命名空间，不触碰年报 ch0-ch7。

本模块只做模板解析与装配，不依赖 LLM 运行时或业务逻辑。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fund_agent.service.audit_pipeline import ChapterContract, _dict_to_chapter_contract, get_chapter_contract
from fund_agent.service.prompt_composer import extract_contract_from_template

ANNUAL_TEMPLATE_ID = "annual_report"
QUARTERLY_SNAPSHOT_TEMPLATE_ID = "quarterly_snapshot"
SEMIANNUAL_SNAPSHOT_TEMPLATE_ID = "semiannual_snapshot"

# 快照模板目录（prompts 命名空间）
_QUARTERLY_SNAPSHOT_PROMPTS_DIR = Path(__file__).parent / "prompts" / "quarterly_snapshot"
_SEMIANNUAL_SNAPSHOT_PROMPTS_DIR = Path(__file__).parent / "prompts" / "semiannual_snapshot"

# 快照模板设计文档（内嵌 manifest，仅文档与校验用途）
QUARTERLY_SNAPSHOT_TEMPLATE_DOC = Path(__file__).resolve().parents[2] / "docs" / "fund-quarterly-snapshot-template.md"
SEMIANNUAL_SNAPSHOT_TEMPLATE_DOC = Path(__file__).resolve().parents[2] / "docs" / "fund-semiannual-snapshot-template.md"

_CONTRACT_BLOCK_PATTERN = re.compile(
    r"<!--\s*\n?CHAPTER_CONTRACT\s*\n(.*?)\nEND_CHAPTER_CONTRACT\s*\n?\s*-->",
    re.DOTALL,
)


@dataclass(frozen=True)
class ReportTemplate:
    """报告模板描述符。

    参数:
        template_id: 模板标识（annual_report / quarterly_snapshot / semiannual_snapshot）。
        front_chapter_ids: 先行生成章节（各章完整 write→audit→rewrite 闭环）。
        closing_chapter_ids: 收尾生成章节（读取 front 章节摘要后生成）。
        chapter_titles: 章节编号到标题的映射。
        prompts_dir: prompt 模板目录（命名空间）。
        system_prompt: LLM 分析 system prompt。
        template_doc: 模板设计文档路径（内嵌 manifest）。
    """

    template_id: str
    front_chapter_ids: tuple[int, ...]
    closing_chapter_ids: tuple[int, ...]
    chapter_titles: dict[int, str]
    prompts_dir: Path
    system_prompt: str
    template_doc: Path | None = None

    @property
    def chapter_ids(self) -> tuple[int, ...]:
        """返回全部章节编号（front + closing，保持生成顺序）。"""

        return tuple(self.front_chapter_ids) + tuple(self.closing_chapter_ids)

    def load_contract(self, chapter_id: int) -> ChapterContract | None:
        """按章节编号加载章节契约。

        参数:
            chapter_id: 章节编号。

        返回:
            ChapterContract；模板中无该章节合同时返回 None。
        """

        raise NotImplementedError

    def build_data_table(self, **kwargs: object) -> str:
        """按章节生成数据表格。

        参数:
            kwargs: 数据表格生成参数（annual 与 snapshot 模板各自定义契约）。

        返回:
            程序生成的数据表格 Markdown 文本。
        """

        raise NotImplementedError

    def build_template_chapter(self, **kwargs: object) -> str:
        """按章节生成模板降级章节（LLM 失败时 fallback）。

        参数:
            kwargs: 模板章节生成参数。

        返回:
            模板章节 Markdown 文本。
        """

        raise NotImplementedError


@dataclass(frozen=True)
class AnnualReportTemplate(ReportTemplate):
    """年报模板：契约来自 get_chapter_contract（ch0-ch7），prompt 来自 LLM_ANALYSIS_PROMPTS。"""

    def load_contract(self, chapter_id: int) -> ChapterContract | None:
        return get_chapter_contract(chapter_id)

    def load_analysis_prompt(self, chapter_id: int) -> str | None:
        from fund_agent.service.chapter_generator import LLM_ANALYSIS_PROMPTS
        return LLM_ANALYSIS_PROMPTS.get(chapter_id)

    def build_data_table(self, **kwargs: object) -> str:
        """年报数据表格：委托 generate_data_table（8 章 specs）。"""

        from fund_agent.service.chapter_generator import generate_data_table
        return generate_data_table(
            chapter_id=int(kwargs["chapter_id"]),
            fund_code=str(kwargs["fund_code"]),
            fund_name=str(kwargs["fund_name"]),
            report_year=int(kwargs["report_year"]),
            performance=kwargs["performance"],
            holdings=kwargs["holdings"],
            allocation=kwargs["allocation"],
            fees=kwargs["fees"],
            fund_manager=kwargs.get("fund_manager"),
            scale_info=kwargs.get("scale_info"),
            evidence=kwargs.get("evidence"),
            stress_test=kwargs.get("stress_test"),
            signal_judgment=kwargs.get("signal_judgment"),
            fund_type=str(kwargs.get("fund_type", "")),
            contract_effective_date=str(kwargs.get("contract_effective_date", "")),
        )

    def build_template_chapter(self, **kwargs: object) -> str:
        """年报模板降级章节：委托 audit_pipeline 的模板生成逻辑。"""

        from fund_agent.service.audit_pipeline import generate_annual_template_chapter
        return generate_annual_template_chapter(**kwargs)


@dataclass(frozen=True)
class SnapshotReportTemplate(ReportTemplate):
    """快照模板：契约与 prompt 来自独立 prompts 命名空间。"""

    def load_contract(self, chapter_id: int) -> ChapterContract | None:
        template_path = self.prompts_dir / f"ch{chapter_id}.md"
        if not template_path.exists():
            return None
        raw = extract_contract_from_template(template_path.read_text(encoding="utf-8"))
        if not raw:
            return None
        contract = _dict_to_chapter_contract(chapter_id, raw)
        title = self.chapter_titles.get(chapter_id, "")
        # _dict_to_chapter_contract 不设置 title，这里从 chapter_titles 补
        return ChapterContract(
            chapter_id=contract.chapter_id,
            title=title,
            narrative_mode=contract.narrative_mode,
            must_answer=contract.must_answer,
            must_not_cover=contract.must_not_cover,
            required_output_items=contract.required_output_items,
            data_sources=contract.data_sources,
            metrics=contract.metrics,
            cross_chapter_refs=contract.cross_chapter_refs,
            data_verification=contract.data_verification,
            item_rules=contract.item_rules,
        )

    def load_analysis_prompt(self, chapter_id: int) -> str | None:
        template_path = self.prompts_dir / f"ch{chapter_id}.md"
        if not template_path.exists():
            return None
        text = template_path.read_text(encoding="utf-8")
        contract_match = _CONTRACT_BLOCK_PATTERN.search(text)
        body = text[contract_match.end():].strip() if contract_match else text.strip()
        return body or None

    def build_data_table(self, **kwargs: object) -> str:
        """快照数据表格：委托 snapshot_generator（Slice D 实现）。"""

        from fund_agent.service.snapshot_generator import generate_snapshot_data_table
        return generate_snapshot_data_table(template_id=self.template_id, **kwargs)

    def build_template_chapter(self, **kwargs: object) -> str:
        """快照模板降级章节：委托 snapshot_generator（Slice D 实现）。"""

        from fund_agent.service.snapshot_generator import generate_snapshot_template_chapter
        return generate_snapshot_template_chapter(template_id=self.template_id, **kwargs)


def _annual_system_prompt() -> str:
    """年报模板 LLM 系统提示词。"""

    from fund_agent.service.chapter_generator import LLM_CHAPTER_SYSTEM_PROMPT
    return LLM_CHAPTER_SYSTEM_PROMPT


def _snapshot_common_system_prompt() -> str:
    """快照模板 LLM 系统提示词（与年报同守则：禁止投资建议/未来预测）。"""

    return (
        "你是一位专业的基金分析师。请基于提供的数据表格，撰写当期快照定性分析。\n\n"
        "【输出格式 - 必须严格遵守】\n"
        "1. 引用数据表格中的数字时需注明据数据表格\n"
        "2. 禁止编造数据表格中不存在的数字\n"
        "3. 数据表格已由系统生成，你只需要写分析评论\n"
        "4. 禁止输出投资建议关键词（如'买入''卖出''推荐''建议关注'等）\n"
        "5. 禁止预测未来收益或市场走势\n"
        "6. 报告期口径必须标注（滚动窗口≠日历年度，季报缺失项 fail-closed 声明）\n"
        "7. 使用 Markdown 格式，语言简洁专业\n\n"
        "违反以上约束的输出将被拒绝。"
    )


ANNUAL_TEMPLATE = AnnualReportTemplate(
    template_id=ANNUAL_TEMPLATE_ID,
    front_chapter_ids=(1, 2, 3, 4, 5, 6),
    closing_chapter_ids=(0, 7),
    chapter_titles={
        0: "投资要点概览",
        1: "这只基金到底是什么产品",
        2: "R=A+B-C 收益归因",
        3: "基金经理画像与言行一致性",
        4: "投资者获得感",
        5: "当前阶段与关键变化",
        6: "核心风险与否决项",
        7: "综合评估与跟踪建议",
    },
    prompts_dir=Path(__file__).parent / "prompts",
    system_prompt=_annual_system_prompt(),
)

QUARTERLY_SNAPSHOT_TEMPLATE = SnapshotReportTemplate(
    template_id=QUARTERLY_SNAPSHOT_TEMPLATE_ID,
    front_chapter_ids=(1, 2, 3, 4),
    closing_chapter_ids=(0,),
    chapter_titles={
        0: "概览",
        1: "当期业绩与超额",
        2: "持仓与资产配置",
        3: "管理人动作",
        4: "风险与跟踪",
    },
    prompts_dir=_QUARTERLY_SNAPSHOT_PROMPTS_DIR,
    system_prompt=_snapshot_common_system_prompt(),
    template_doc=QUARTERLY_SNAPSHOT_TEMPLATE_DOC,
)

SEMIANNUAL_SNAPSHOT_TEMPLATE = SnapshotReportTemplate(
    template_id=SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
    front_chapter_ids=(1, 2, 3, 4, 5),
    closing_chapter_ids=(0,),
    chapter_titles={
        0: "概览",
        1: "当期业绩与超额",
        2: "持仓与资产配置",
        3: "财务质量",
        4: "管理人动作",
        5: "风险与持有人",
    },
    prompts_dir=_SEMIANNUAL_SNAPSHOT_PROMPTS_DIR,
    system_prompt=_snapshot_common_system_prompt(),
    template_doc=SEMIANNUAL_SNAPSHOT_TEMPLATE_DOC,
)

_REPORT_TEMPLATES: dict[str, ReportTemplate] = {
    ANNUAL_TEMPLATE_ID: ANNUAL_TEMPLATE,
    QUARTERLY_SNAPSHOT_TEMPLATE_ID: QUARTERLY_SNAPSHOT_TEMPLATE,
    SEMIANNUAL_SNAPSHOT_TEMPLATE_ID: SEMIANNUAL_SNAPSHOT_TEMPLATE,
}


def get_report_template(template_id: str) -> ReportTemplate | None:
    """按 template_id 返回报告模板；未知模板返回 None。"""

    return _REPORT_TEMPLATES.get(template_id)


def snapshot_template_ids() -> tuple[str, ...]:
    """返回全部快照模板 id（quarterly_snapshot / semiannual_snapshot）。"""

    return (QUARTERLY_SNAPSHOT_TEMPLATE_ID, SEMIANNUAL_SNAPSHOT_TEMPLATE_ID)
