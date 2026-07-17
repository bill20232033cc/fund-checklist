"""14C 章节审计管道组件。

基于 dayu write_pipeline 设计，实现三层审计（程序审计+LLM审计+LLM复核）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ============================================================
# ChapterContract（章节合同）
# ============================================================


@dataclass(frozen=True)
class ChapterContract:
    """章节合同：声明式定义每章必须包含的内容。

    参数:
        chapter_id: 章节编号（0-7）。
        title: 章节标题。
        must_answer: 必须回答的问题列表。
        must_not_cover: 禁止内容列表。
        required_output_items: 必须输出的项目。
        data_sources: 必须引用的数据来源。
        narrative_mode: 叙事模式。

    返回:
        不可变章节合同 DTO。
    """

    chapter_id: int
    title: str
    must_answer: tuple[str, ...]
    must_not_cover: tuple[str, ...]
    required_output_items: tuple[str, ...]
    data_sources: tuple[str, ...]
    narrative_mode: str = ""


# 从 docs/fund-analysis-template-draft.md 提取的章节合同
CHAPTER_CONTRACTS: dict[int, ChapterContract] = {
    0: ChapterContract(
        chapter_id=0,
        title="投资要点概览",
        narrative_mode="封面→动作→验证",
        must_answer=(
            "用一句话定义这只基金到底是什么产品。",
            "给出一个极简基金简介（基金类型、基金经理、管理规模、成立时间中最必要的信息）。",
            "回答当前综合评估结论（表现优异/表现平稳/需要关注）。",
            "回答当前业绩和运作状态（最能支撑判断的净值表现、超额收益或风险指标）。",
            "回答支撑当前结论的最主要理由（默认1条）。",
            "回答当前最值得盯住的变量是什么。",
            "回答当前最大的风险是什么（默认1个）。",
            "回答下一步最小验证问题是什么（默认1个）。",
        ),
        must_not_cover=(
            "不把本章写成后续章节的摘要、材料摘抄、按顺序复述。",
            "不把基金简介/业绩概览/风险提示拆成并列分栏。",
            "不把本章写成优点/缺点清单、投资亮点清单。",
            "不把最主要的理由写成多条优点堆砌。",
            "不把最大风险写成并列风险列表。",
            "不输出证据与出处小节。",
        ),
        required_output_items=(
            "一句话这是什么基金",
            "基金简介",
            "当前综合评估结论",
            "当前业绩与运作状态",
            "支撑结论的最主要理由",
            "当前最值得盯住的变量",
            "当前最大的风险",
            "下一步最小验证问题",
        ),
        data_sources=("performance", "holdings", "fees", "fund_manager"),
    ),
    1: ChapterContract(
        chapter_id=1,
        title="这只基金到底是什么产品",
        narrative_mode="定义→策略→基准",
        must_answer=(
            "用最低认知负担定义这只基金到底是什么产品。",
            "说明基金的投资目标和投资策略。",
            "说明基金的业绩基准是什么。",
            "说明基金的类型分类。",
            "回答看这类基金时，通常最先要看什么。",
        ),
        must_not_cover=(
            "不展开基金经理选股能力的分析（属于第3章）。",
            "不展开收益率的详细计算（属于第2章）。",
            "不分析市场竞争或同业比较。",
        ),
        required_output_items=(
            "基金类型与分类标签",
            "投资目标（一句话）",
            "投资策略概述",
            "业绩基准及合理性",
            "看这类基金最先看什么",
        ),
        data_sources=("basic_info", "fund_manager"),
    ),
    2: ChapterContract(
        chapter_id=2,
        title="R=A+B-C 收益归因",
        narrative_mode="拆解→判断→成本",
        must_answer=(
            "近1年、3年、5年的基金净值增长率（R）。",
            "同期业绩基准收益率（B）。",
            "计算超额收益（A = R - B）。",
            "判断超额收益是结构性的还是阶段性的。",
            "拆解成本C：管理费+托管费+销售服务费。",
            "判断超额收益是否为正且稳定、是否覆盖成本。",
        ),
        must_not_cover=(
            "不展开基金经理选股能力的详细归因（属于第3章）。",
            "不展开市场走势分析。",
            "不做未来收益预测。",
        ),
        required_output_items=(
            "近1/3/5年净值增长率",
            "近1/3/5年业绩基准收益率",
            "超额收益（A = R - B）及稳定性",
            "超额收益性质判断（结构性 vs 阶段性）",
            "成本拆解（管理费、托管费）",
            "R=A+B-C 综合评估",
        ),
        data_sources=("performance", "fees"),
    ),
    3: ChapterContract(
        chapter_id=3,
        title="基金经理画像与言行一致性",
        narrative_mode="画像→验证→判断",
        must_answer=(
            "基金经理的基本信息（从业年限、管理本基金时间）。",
            "基金经理宣称的投资策略和风格。",
            "基金经理实际的投资行为（持仓集中度、行业分布）。",
            "言行一致性判断：说的和做的一样吗？",
            "利益一致性判断：基金经理是否持有本基金？",
        ),
        must_not_cover=(
            "不做基金经理性格或人品的主观评价。",
            "不猜测基金经理的动机。",
            "不展开选股能力的量化分析。",
        ),
        required_output_items=(
            "基金经理基本信息",
            "宣称的投资策略",
            "实际投资行为",
            "言行一致性判断",
            "利益一致性判断",
        ),
        data_sources=("fund_manager", "holdings"),
    ),
    4: ChapterContract(
        chapter_id=4,
        title="投资者获得感",
        narrative_mode="数据→对比→判断",
        must_answer=(
            "基金产品收益（净值增长率）。",
            "投资者实际收益（如有数据）。",
            "行为损益 = 投资者实际收益 - 基金产品收益。",
            "份额变动趋势。",
        ),
        must_not_cover=(
            "不分析具体投资者的交易行为。",
            "不做未来投资者行为预测。",
        ),
        required_output_items=(
            "基金产品收益 vs 投资者实际收益",
            "份额变动趋势",
        ),
        data_sources=("performance",),
    ),
    5: ChapterContract(
        chapter_id=5,
        title="当前阶段与关键变化",
        narrative_mode="变化→阶段→判断",
        must_answer=(
            "当前阶段是什么（5选1，按优先级匹配：转型期>建仓期>膨胀期>萎缩期>稳定期）。",
            "过去一年最关键的1-3个变化（从持仓变动/规模变动/费率变动3个维度筛选，阈值触发才列入）。",
            "这些变化是否影响原始投资假设（对比Ch7信号评分方向是否逆转）。",
            "接下来最该跟踪的1-3个变量（来自Ch7评分最低指标）。",
        ),
        must_not_cover=(
            "不做市场整体走势预测。",
            "不罗列所有变化，只保留阈值触发的最关键1-3个。",
            "不给最终持有/替换结论。",
        ),
        required_output_items=(
            "基金当前所处阶段（含判定依据）",
            "过去一年最关键的变化（含触发阈值）",
            "变化是否改变前文判断",
            "接下来最该跟踪的变量",
        ),
        data_sources=("performance", "allocation", "scale_info"),
    ),
    6: ChapterContract(
        chapter_id=6,
        title="核心风险与否决项",
        narrative_mode="风险→否决→跟踪",
        must_answer=(
            "核心风险是什么（结构性风险 vs 阶段性风险）。",
            "最关键的风险或否决项（1-2个最致命的）。",
            "为什么足以改变结论。",
            "是否触发一票否决，还是仍可跟踪。",
            "哪个信息缺口最可能改变最终判断。",
        ),
        must_not_cover=(
            "不把本章写成所有可能风险的罗列。",
            "不把最大风险写成并列列表。",
            "不做风险发生概率的定量预测。",
            "不给最终持有/替换结论。",
        ),
        required_output_items=(
            "最关键的风险或否决项",
            "为什么足以改变结论",
            "否决 vs 跟踪判断",
            "下一轮先验证什么",
        ),
        data_sources=("performance", "holdings"),
    ),
    7: ChapterContract(
        chapter_id=7,
        title="综合评估与跟踪建议",
        narrative_mode="判断→依据→验证",
        must_answer=(
            "给出综合评估结论。",
            "为什么现在更适合这个结论。",
            "当前最容易看错的地方是什么。",
            "下一轮先核实什么（1-2个最小验证问题）。",
            "什么变化会升级、降级或终止当前判断。",
        ),
        must_not_cover=(
            "不输出具体的买入金额、卖出时机或仓位比例。",
            "不把本章写成前6章的摘要复述。",
            "不把为什么写成多条理由堆砌。",
        ),
        required_output_items=(
            "综合评估结论",
            "支撑结论的核心依据（1-2条）",
            "当前最容易看错的地方",
            "下一轮最小验证计划",
            "升级/降级阈值",
        ),
        data_sources=("performance", "holdings", "fees", "fund_manager"),
    ),
}


def get_chapter_contract(chapter_id: int) -> ChapterContract | None:
    """获取指定章节的合同。

    参数:
        chapter_id: 章节编号（0-7）。

    返回:
        ChapterContract；未找到时返回 None。
    """

    return CHAPTER_CONTRACTS.get(chapter_id)


def get_all_chapter_contracts() -> dict[int, ChapterContract]:
    """获取所有章节合同。

    返回:
        章节编号到合同的映射。
    """

    return dict(CHAPTER_CONTRACTS)


# ============================================================
# 违规分类体系（4类22项，对齐 dayu P/E/S/C）
# ============================================================


class ViolationCategory(str, Enum):
    """违规类别。"""

    PLACEHOLDER = "P"  # 数据/幻觉
    EVIDENCE = "E"     # 证据
    STRUCTURE = "S"    # 结构
    CONTENT = "C"      # 内容


class ViolationSeverity(str, Enum):
    """违规严重程度。"""

    CRITICAL = "critical"  # 严重（<50分触发重写）
    MAJOR = "major"        # 主要（50-79分触发修复）
    MINOR = "minor"        # 次要（不扣分或少量扣分）


# 违规编码定义
VIOLATION_DEFINITIONS: dict[str, dict[str, str]] = {
    # P类：数据/幻觉
    "P1": {"category": "P", "severity": "critical", "description": "数据未获取（数据表为空）"},
    "P2": {"category": "P", "severity": "critical", "description": "数字编造（LLM输出未见数字）"},
    "P3": {"category": "P", "severity": "major", "description": "模板残留（占位符未替换）"},
    "P4": {"category": "P", "severity": "major", "description": "数据表格不匹配（表格与章节不符）"},
    # E类：证据
    "E1": {"category": "E", "severity": "critical", "description": "证据缺失（引用的数据不存在）"},
    "E2": {"category": "E", "severity": "major", "description": "来源不可引用（无数据来源标注）"},
    "E3": {"category": "E", "severity": "major", "description": "引用不准确（数据与原文不符）"},
    "E4": {"category": "E", "severity": "minor", "description": "证据锚点断裂（引用位置错误）"},
    "E5": {"category": "E", "severity": "minor", "description": "证据格式不规范"},
    # S类：结构
    "S1": {"category": "S", "severity": "critical", "description": "章节结构不完整（缺少必须小节）"},
    "S2": {"category": "S", "severity": "major", "description": "必须字段缺失（must_answer未回答）"},
    "S3": {"category": "S", "severity": "major", "description": "格式错误（Markdown格式问题）"},
    "S4": {"category": "S", "severity": "minor", "description": "标题层级不规范"},
    "S5": {"category": "S", "severity": "minor", "description": "段落过长或过短"},
    "S6": {"category": "S", "severity": "minor", "description": "列表格式不一致"},
    "S7": {"category": "S", "severity": "minor", "description": "条件标题处理不当"},
    # C类：内容
    "C1": {"category": "C", "severity": "critical", "description": "事实错误（与数据矛盾）"},
    "C2": {"category": "C", "severity": "critical", "description": "逻辑矛盾（前后不一致）"},
    "C3": {"category": "C", "severity": "critical", "description": "投资建议（违反硬边界）"},
    "C4": {"category": "C", "severity": "major", "description": "分析深度不足（过于浅显）"},
    "C5": {"category": "C", "severity": "major", "description": "must_not_cover违规"},
    "C6": {"category": "C", "severity": "minor", "description": "语言风格不专业"},
    # LLM 审计内部错误
    "LLM_ERROR": {"category": "C", "severity": "minor", "description": "LLM审计调用失败"},
    "LLM_PARSE_ERROR": {"category": "C", "severity": "minor", "description": "LLM审计响应解析失败"},
}


@dataclass(frozen=True)
class AuditViolation:
    """审计违规项。

    参数:
        code: 违规编码（P1/E1/S1/C1等）。
        category: 违规类别（P/E/S/C）。
        severity: 严重程度（critical/major/minor）。
        description: 违规描述。
        location: 违规位置（章节/段落）。
        suggested_fix: 建议修复方式。
        evidence: 违规证据（原文片段）。

    返回:
        不可变违规项 DTO。
    """

    code: str
    category: ViolationCategory
    severity: ViolationSeverity
    description: str
    location: str = ""
    suggested_fix: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class AuditDecision:
    """审计决定。

    参数:
        chapter_id: 章节编号。
        score: 综合分数（0-100）。
        violations: 违规项列表。
        programmatic_score: 程序审计分数。
        llm_score: LLM审计分数。
        recommendation: 建议（pass/patch/regenerate）。
        audit_time: 审计时间。

    返回:
        不可变审计决定 DTO。
    """

    chapter_id: int
    score: float
    violations: tuple[AuditViolation, ...]
    programmatic_score: float = 0.0
    llm_score: float = 0.0
    recommendation: str = "pass"
    audit_time: str = ""


@dataclass(frozen=True)
class RepairAction:
    """修复动作。

    参数:
        violation_code: 对应的违规编码。
        strategy: 修复策略（patch/regenerate/none）。
        target_excerpt: PATCH: 要替换的原文片段。
        replacement: PATCH: 替换后的内容。
        target_kind: PATCH: 替换类型（substring/line/bullet/paragraph）。
        target_section_heading: PATCH: 目标章节标题。
        occurrence_index: PATCH: 命中次数索引。

    返回:
        不可变修复动作 DTO。
    """

    violation_code: str
    strategy: str  # "patch" | "regenerate" | "none"
    target_excerpt: str = ""
    replacement: str = ""
    target_kind: str = "substring"
    target_section_heading: str = ""
    occurrence_index: int = 0


@dataclass(frozen=True)
class RepairPlan:
    """修复计划。

    参数:
        chapter_id: 章节编号。
        actions: 修复动作列表。
        strategy: 整体策略（patch/regenerate）。

    返回:
        不可变修复计划 DTO。
    """

    chapter_id: int
    actions: tuple[RepairAction, ...]
    strategy: str = "patch"


@dataclass
class ChapterProcessState:
    """章节过程状态（可观测性）。

    参数:
        chapter_id: 章节编号。
        write_attempts: 写入尝试次数。
        audit_attempts: 审计尝试次数。
        patch_attempts: PATCH尝试次数。
        regenerate_attempts: REGENERATE尝试次数。
        current_score: 当前分数。
        violations: 当前违规项。
        status: 状态（pending/passed/failed）。
        history: 历史记录。

    返回:
        可变过程状态。
    """

    chapter_id: int
    write_attempts: int = 0
    audit_attempts: int = 0
    patch_attempts: int = 0
    regenerate_attempts: int = 0
    current_score: float = 0.0
    violations: tuple[AuditViolation, ...] = ()
    status: str = "pending"
    history: list[dict[str, Any]] = field(default_factory=list)

    def record_event(self, event_type: str, details: dict[str, Any]) -> None:
        """记录事件到历史。

        参数:
            event_type: 事件类型。
            details: 事件详情。
        """

        self.history.append({
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "details": details,
        })

    def can_patch(self) -> bool:
        """是否可以继续 PATCH。"""
        return self.patch_attempts < 3

    def can_regenerate(self) -> bool:
        """是否可以继续 REGENERATE。"""
        return self.regenerate_attempts < 3


# ============================================================
# ArtifactStore（审计产物持久化）
# ============================================================


class ArtifactStore:
    """审计产物持久化存储。

    参数:
        work_dir: 工作目录。

    返回:
        可持久化审计产物的存储。
    """

    def __init__(self, work_dir: Path) -> None:
        """初始化存储。"""
        self._work_dir = work_dir
        self._audit_dir = work_dir / "audit_artifacts"
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    def save_audit_decision(self, decision: AuditDecision) -> str:
        """保存审计决定。

        参数:
            decision: 审计决定。

        返回:
            保存路径。
        """

        filename = f"chapter_{decision.chapter_id}_audit.json"
        filepath = self._audit_dir / filename
        data = {
            "chapter_id": decision.chapter_id,
            "score": decision.score,
            "programmatic_score": decision.programmatic_score,
            "llm_score": decision.llm_score,
            "recommendation": decision.recommendation,
            "audit_time": decision.audit_time,
            "violations": [
                {
                    "code": v.code,
                    "category": v.category.value,
                    "severity": v.severity.value,
                    "description": v.description,
                    "location": v.location,
                    "suggested_fix": v.suggested_fix,
                    "evidence": v.evidence,
                }
                for v in decision.violations
            ],
        }
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)

    def save_repair_plan(self, plan: RepairPlan) -> str:
        """保存修复计划。

        参数:
            plan: 修复计划。

        返回:
            保存路径。
        """

        filename = f"chapter_{plan.chapter_id}_repair.json"
        filepath = self._audit_dir / filename
        data = {
            "chapter_id": plan.chapter_id,
            "strategy": plan.strategy,
            "actions": [
                {
                    "violation_code": a.violation_code,
                    "strategy": a.strategy,
                    "target_excerpt": a.target_excerpt,
                    "replacement": a.replacement,
                    "target_kind": a.target_kind,
                    "target_section_heading": a.target_section_heading,
                    "occurrence_index": a.occurrence_index,
                }
                for a in plan.actions
            ],
        }
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)

    def save_process_state(self, state: ChapterProcessState) -> str:
        """保存过程状态。

        参数:
            state: 过程状态。

        返回:
            保存路径。
        """

        filename = f"chapter_{state.chapter_id}_state.json"
        filepath = self._audit_dir / filename
        data = {
            "chapter_id": state.chapter_id,
            "write_attempts": state.write_attempts,
            "audit_attempts": state.audit_attempts,
            "patch_attempts": state.patch_attempts,
            "regenerate_attempts": state.regenerate_attempts,
            "current_score": state.current_score,
            "status": state.status,
            "violations_count": len(state.violations),
            "history": state.history,
        }
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)

    def load_audit_decision(self, chapter_id: int) -> AuditDecision | None:
        """加载审计决定。

        参数:
            chapter_id: 章节编号。

        返回:
            AuditDecision；未找到时返回 None。
        """

        filename = f"chapter_{chapter_id}_audit.json"
        filepath = self._audit_dir / filename
        if not filepath.exists():
            return None
        data = json.loads(filepath.read_text(encoding="utf-8"))
        violations = tuple(
            AuditViolation(
                code=v["code"],
                category=ViolationCategory(v["category"]),
                severity=ViolationSeverity(v["severity"]),
                description=v["description"],
                location=v.get("location", ""),
                suggested_fix=v.get("suggested_fix", ""),
                evidence=v.get("evidence", ""),
            )
            for v in data.get("violations", [])
        )
        return AuditDecision(
            chapter_id=data["chapter_id"],
            score=data["score"],
            violations=violations,
            programmatic_score=data.get("programmatic_score", 0.0),
            llm_score=data.get("llm_score", 0.0),
            recommendation=data.get("recommendation", "pass"),
            audit_time=data.get("audit_time", ""),
        )


# ============================================================
# ProgrammaticAuditor（第一层：程序审计）
# ============================================================

# 禁止内容关键词
_INVESTMENT_ADVICE_KEYWORDS = (
    "买入", "卖出", "推荐买入", "推荐卖出", "建议买入", "建议卖出",
    "强烈推荐", "强烈买入", "强烈卖出", "增持", "减持",
    "目标价", "预期收益", "预计涨幅", "预期回报",
)

# 必须字段检查（基于 ChapterContract.required_output_items）
_REQUIRED_FIELD_PATTERNS = {
    "基金类型": r"(混合型|股票型|债券型|指数型|货币型|QDII|FOF)",
    "投资目标": r"(投资目标|旨在|追求|力争)",
    "投资策略": r"(投资策略|选股|配置|管理)",
    "净值增长率": r"(-?\d+\.?\d*%)",
    "超额收益": r"(超额收益|跑赢|超越基准)",
    "管理费": r"(管理费|托管费|销售服务费)",
    "基金经理": r"(基金经理|张明|管理人)",
}


class ProgrammaticAuditor:
    """程序审计器（第一层）。

    不需要 LLM，纯规则检查。检查三类问题：
    - 数据合规：数字编造、模板残留
    - 必须字段：ChapterContract 要求的字段是否出现
    - 禁止内容：投资建议关键词

    参数:
        chapter_id: 章节编号。
        chapter_content: 章节 Markdown 内容。
        data_table: 数据表格内容。
        contract: 章节合同。

    返回:
        审计违规项列表和分数。
    """

    def __init__(
        self,
        chapter_id: int,
        chapter_content: str,
        data_table: str,
        contract: ChapterContract,
        global_allowed_numbers: set[str] | None = None,
    ) -> None:
        """初始化审计器。"""
        self._chapter_id = chapter_id
        self._content = chapter_content
        self._data_table = data_table
        self._contract = contract
        self._global_allowed_numbers = global_allowed_numbers

    def audit(self) -> tuple[float, tuple[AuditViolation, ...]]:
        """执行程序审计。

        返回:
            (分数, 违规项列表)。分数范围 0-100。
        """

        violations: list[AuditViolation] = []
        base_score = 100.0

        # 1. 数据合规检查
        data_violations = self._check_data_compliance()
        violations.extend(data_violations)

        # 2. 必须字段检查
        field_violations = self._check_required_fields()
        violations.extend(field_violations)

        # 3. 禁止内容检查
        content_violations = self._check_prohibited_content()
        violations.extend(content_violations)

        # 4. 结构完整性检查
        structure_violations = self._check_structure()
        violations.extend(structure_violations)

        # 计算扣分
        for v in violations:
            if v.severity == ViolationSeverity.CRITICAL:
                base_score -= 30
            elif v.severity == ViolationSeverity.MAJOR:
                base_score -= 15
            elif v.severity == ViolationSeverity.MINOR:
                base_score -= 5

        score = max(0.0, min(100.0, base_score))
        return score, tuple(violations)

    def _check_data_compliance(self) -> list[AuditViolation]:
        """检查数据合规性。"""
        violations: list[AuditViolation] = []

        # P1: 数据表为空
        if not self._data_table or len(self._data_table.strip()) < 10:
            violations.append(AuditViolation(
                code="P1",
                category=ViolationCategory.PLACEHOLDER,
                severity=ViolationSeverity.CRITICAL,
                description="数据表为空或内容过少",
                location=f"Ch{self._chapter_id}",
            ))

        # P2: 数字编造（LLM输出包含数据表中没有的数字）
        # 使用全局 allowed_numbers（支持跨章节引用），否则用本章 data_table
        from fund_agent.service.chapter_generator import _normalize_number
        if self._global_allowed_numbers:
            data_numbers_norm = {_normalize_number(n) for n in self._global_allowed_numbers}
        else:
            data_numbers_norm = {_normalize_number(n) for n in re.findall(r'\d+\.?\d*', self._data_table)}
        content_numbers = set(re.findall(r'\d+\.?\d*', self._content))
        # 排除年份（20xx）和小数字（1-99）
        suspicious = set()
        for n in content_numbers:
            normalized = _normalize_number(n)
            if re.match(r'^(20[12]\d)$', normalized):
                continue
            if re.match(r'^[1-9]\d?$', normalized):
                continue
            if normalized not in data_numbers_norm:
                suspicious.add(n)
        if suspicious:
            violations.append(AuditViolation(
                code="P2",
                category=ViolationCategory.PLACEHOLDER,
                severity=ViolationSeverity.CRITICAL,
                description=f"发现未见数字: {', '.join(list(suspicious)[:5])}",
                location=f"Ch{self._chapter_id}",
                evidence=f"可疑数字: {', '.join(list(suspicious)[:10])}",
            ))

        # P3: 模板残留（占位符未替换）
        placeholders = re.findall(r'\{\{[^}]+\}\}', self._content)
        if placeholders:
            violations.append(AuditViolation(
                code="P3",
                category=ViolationCategory.PLACEHOLDER,
                severity=ViolationSeverity.MAJOR,
                description=f"发现未替换的占位符: {', '.join(placeholders[:5])}",
                location=f"Ch{self._chapter_id}",
                suggested_fix="替换占位符为实际数据",
            ))

        return violations

    def _check_required_fields(self) -> list[AuditViolation]:
        """检查必须字段（只检查有 pattern 的条目，跳过无法程序化检查的）。"""
        violations: list[AuditViolation] = []

        # 只检查 ChapterContract.required_output_items 中能匹配 pattern 的条目
        for item in self._contract.required_output_items:
            matched_pattern_key = None
            for pattern_key in _REQUIRED_FIELD_PATTERNS:
                if pattern_key in item:
                    matched_pattern_key = pattern_key
                    break

            # 没有匹配的 pattern key → 跳过（无法程序化检查）
            if matched_pattern_key is None:
                continue

            # 有匹配的 pattern key → 检查内容是否包含该 pattern
            pattern = _REQUIRED_FIELD_PATTERNS[matched_pattern_key]
            if not re.search(pattern, self._content) and len(self._content) > 50:
                violations.append(AuditViolation(
                    code="S2",
                    category=ViolationCategory.STRUCTURE,
                    severity=ViolationSeverity.MAJOR,
                    description=f"必须字段缺失: {item}",
                    location=f"Ch{self._chapter_id}",
                    suggested_fix=f"补充 {item} 相关内容",
                ))

        return violations

    def _check_prohibited_content(self) -> list[AuditViolation]:
        """检查禁止内容。

        只检查 ## 分析 之后的内容（LLM 生成的分析文本）。
        data_table 区域包含引用文本（如基金经理原文摘录中的买入），
        不应触发投资建议检测。
        """
        violations: list[AuditViolation] = []

        # 只检查 ## 分析 之后的内容
        analysis_marker = "## 分析"
        analysis_idx = self._content.find(analysis_marker)
        check_content = self._content[analysis_idx:] if analysis_idx >= 0 else self._content

        # C3: 投资建议
        for keyword in _INVESTMENT_ADVICE_KEYWORDS:
            if keyword in check_content:
                violations.append(AuditViolation(
                    code="C3",
                    category=ViolationCategory.CONTENT,
                    severity=ViolationSeverity.CRITICAL,
                    description=f"包含投资建议关键词: {keyword}",
                    location=f"Ch{self._chapter_id}",
                    evidence=keyword,
                    suggested_fix=f"删除或改写包含'{keyword}'的内容",
                ))
                break  # 只报第一个

        # C5: must_not_cover 违规（扫描整个章节，因为约束是章节级的）
        for prohibited in self._contract.must_not_cover:
            # 简单检查：如果禁止内容的关键短语出现
            key_phrases = [p for p in prohibited.split("，") if len(p) > 4]
            for phrase in key_phrases:
                if phrase in self._content:
                    violations.append(AuditViolation(
                        code="C5",
                        category=ViolationCategory.CONTENT,
                        severity=ViolationSeverity.MAJOR,
                        description=f"违反禁止内容: {phrase}",
                        location=f"Ch{self._chapter_id}",
                        evidence=phrase,
                        suggested_fix=f"删除或改写包含'{phrase}'的内容",
                    ))
                    break

        return violations

    def _check_structure(self) -> list[AuditViolation]:
        """检查结构完整性。"""
        violations: list[AuditViolation] = []

        # S1: 内容过短
        if len(self._content.strip()) < 20:
            violations.append(AuditViolation(
                code="S1",
                category=ViolationCategory.STRUCTURE,
                severity=ViolationSeverity.CRITICAL,
                description="章节内容过短（<20字）",
                location=f"Ch{self._chapter_id}",
                suggested_fix="补充章节内容",
            ))

        # S3: Markdown格式检查
        lines = self._content.split('\n')
        has_heading = any(line.startswith('#') for line in lines)
        if len(lines) > 5 and not has_heading:
            violations.append(AuditViolation(
                code="S3",
                category=ViolationCategory.STRUCTURE,
                severity=ViolationSeverity.MINOR,
                description="缺少Markdown标题",
                location=f"Ch{self._chapter_id}",
                suggested_fix="添加适当的标题",
            ))

        return violations


# ============================================================
# LlmAuditor（第二层：LLM 审计）
# ============================================================

_LLM_AUDIT_SYSTEM_PROMPT = """你是一位严格的基金分析报告审计专家。请审计以下章节内容，检查是否存在违规问题。

【审计维度】
1. 分析深度：分析是否足够深入，是否只是表面描述
2. 逻辑一致性：前后是否矛盾，论证是否合理
3. 事实准确性：分析是否与提供的数据一致
4. 专业性：语言是否专业，分析框架是否合理

【输出格式】
请返回 JSON 格式的审计结果：
{
  "score": 0-100的分数,
  "violations": [
    {
      "code": "违规编码（P1-P4/E1-E5/S1-S7/C1-C6）",
      "description": "违规描述",
      "location": "违规位置",
      "suggested_fix": "建议修复方式"
    }
  ]
}

【违规编码说明】
P1: 数据未获取  P2: 数字编造  P3: 模板残留  P4: 数据表格不匹配
E1: 证据缺失  E2: 来源不可引用  E3: 引用不准确  E4: 证据锚点断裂  E5: 证据格式不规范
S1: 章节结构不完整  S2: 必须字段缺失  S3: 格式错误  S4-S7: 其他结构问题
C1: 事实错误  C2: 逻辑矛盾  C3: 投资建议  C4: 分析深度不足  C5: must_not_cover违规  C6: 语言风格不专业

【C3 投资建议判定规则 - 必须严格遵守】
以下表述不视为投资建议（C3）：
- "建议关注" — 这是分析结论，不是操作建议
- "基金仍可跟踪" — 这是分析状态描述
- "超额收益持续性有待观察" — 这是分析性不确定性
- "投资者应关注" — 这是风险提示

以下表述视为投资建议（C3）：
- "建议买入/卖出/持有" — 直接操作建议
- "推荐该基金" — 明确推荐
- "应该加仓/减仓" — 具体操作建议

判定 C3 时，必须先引用原文再判断，禁止编造不存在的违规。

请严格审计，不要放过任何问题。"""


class LlmAuditor:
    """LLM 审计器（第二层）。

    使用 LLM 检查分析质量、逻辑一致性、事实准确性。

    参数:
        llm_client: LLM 客户端。
        chapter_id: 章节编号。
        chapter_content: 章节 Markdown 内容。
        data_table: 数据表格内容。
        contract: 章节合同。

    返回:
        审计违规项列表和分数。
    """

    def __init__(
        self,
        llm_client: Any,
        chapter_id: int,
        chapter_content: str,
        data_table: str,
        contract: ChapterContract,
    ) -> None:
        """初始化审计器。"""
        self._llm_client = llm_client
        self._chapter_id = chapter_id
        self._content = chapter_content
        self._data_table = data_table
        self._contract = contract

    def audit(self) -> tuple[float, tuple[AuditViolation, ...]]:
        """执行 LLM 审计。JSON 解析失败时重试 1 次。

        返回:
            (分数, 违规项列表)。分数范围 0-100。
        """

        max_retries = 2
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                # 构造审计 prompt
                user_prompt = self._build_audit_prompt()

                # 调用 LLM
                response = self._llm_client.generate_text(
                    system_prompt=_LLM_AUDIT_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                )

                # 解析响应
                return self._parse_audit_response(response)

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    continue

        # 所有重试失败，返回默认分数
        return 60.0, (
            AuditViolation(
                code="LLM_ERROR",
                category=ViolationCategory.CONTENT,
                severity=ViolationSeverity.MINOR,
                description=f"LLM审计失败: {str(last_error)[:100]}",
                location=f"Ch{self._chapter_id}",
            ),
        )

    def _build_audit_prompt(self) -> str:
        """构造审计 prompt。"""

        # 章节合同要求
        must_answer_text = "\n".join(f"- {item}" for item in self._contract.must_answer)
        must_not_cover_text = "\n".join(f"- {item}" for item in self._contract.must_not_cover)

        return f"""请审计以下基金分析报告章节。

## 章节信息
- 章节编号: Ch{self._chapter_id}
- 章节标题: {self._contract.title}
- 叙事模式: {self._contract.narrative_mode}

## 章节合同要求

### 必须回答的问题
{must_answer_text}

### 禁止内容
{must_not_cover_text}

## 数据表格（参考）
{self._data_table[:3000]}

## 章节内容（待审计）
{self._content}

请严格审计上述内容，检查是否存在违规问题。"""

    def _parse_audit_response(self, response: str) -> tuple[float, tuple[AuditViolation, ...]]:
        """解析 LLM 审计响应。"""

        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return 50.0, (
                    AuditViolation(
                        code="LLM_PARSE_ERROR",
                        category=ViolationCategory.CONTENT,
                        severity=ViolationSeverity.MINOR,
                        description="LLM响应无法解析为JSON",
                        location=f"Ch{self._chapter_id}",
                    ),
                )

            data = json.loads(json_match.group())
            score = float(data.get("score", 50))
            violations_data = data.get("violations", [])

            violations = []
            for v in violations_data:
                code = v.get("code", "C4")
                # 验证违规编码
                if code not in VIOLATION_DEFINITIONS:
                    code = "C4"  # 默认为分析深度不足

                violations.append(AuditViolation(
                    code=code,
                    category=ViolationCategory(VIOLATION_DEFINITIONS[code]["category"]),
                    severity=ViolationSeverity(VIOLATION_DEFINITIONS[code]["severity"]),
                    description=v.get("description", ""),
                    location=v.get("location", f"Ch{self._chapter_id}"),
                    suggested_fix=v.get("suggested_fix", ""),
                ))

            return max(0.0, min(100.0, score)), tuple(violations)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return 50.0, (
                AuditViolation(
                    code="LLM_PARSE_ERROR",
                    category=ViolationCategory.CONTENT,
                    severity=ViolationSeverity.MINOR,
                    description=f"LLM响应解析失败: {str(e)[:100]}",
                    location=f"Ch{self._chapter_id}",
                ),
            )


# ============================================================
# ChapterRepairer（修复器：PATCH/REGENERATE）
# ============================================================

_LLM_REPAIR_SYSTEM_PROMPT = """你是一位基金分析报告修复专家。请根据审计发现的违规问题，生成修复方案。

【修复策略】
- PATCH：精确定位并修复特定段落，不修改数据表格
- REGENERATE：重新生成整个章节

【PATCH 输出格式】
请返回 JSON 格式的修复方案：
{
  "strategy": "patch",
  "patches": [
    {
      "target_excerpt": "要替换的原文片段",
      "target_kind": "substring/line/bullet/paragraph",
      "target_section_heading": "目标章节标题（可选）",
      "occurrence_index": 0,
      "replacement": "替换后的内容"
    }
  ]
}

【REGENERATE 输出格式】
请返回 JSON 格式的修复方案：
{
  "strategy": "regenerate",
  "reason": "重写原因"
}

【重要约束】
1. 禁止修改数据表格部分
2. 禁止保留违规原文
3. 修复后内容必须符合章节合同要求"""


class ChapterRepairer:
    """章节修复器。

    支持两种修复策略：
    - PATCH：精确定位并修复特定段落
    - REGENERATE：重新生成整个章节

    参数:
        llm_client: LLM 客户端。
        chapter_id: 章节编号。
        chapter_content: 章节 Markdown 内容。
        data_table: 数据表格内容。
        contract: 章节合同。
        violations: 审计发现的违规项。

    返回:
        修复后的内容和修复计划。
    """

    def __init__(
        self,
        llm_client: Any,
        chapter_id: int,
        chapter_content: str,
        data_table: str,
        contract: ChapterContract,
        violations: tuple[AuditViolation, ...],
    ) -> None:
        """初始化修复器。"""
        self._llm_client = llm_client
        self._chapter_id = chapter_id
        self._content = chapter_content
        self._data_table = data_table
        self._contract = contract
        self._violations = violations

    def generate_repair_plan(self) -> RepairPlan:
        """生成修复计划。

        返回:
            修复计划。
        """

        # 判断修复策略
        has_critical = any(v.severity == ViolationSeverity.CRITICAL for v in self._violations)
        if has_critical:
            strategy = "regenerate"
        else:
            strategy = "patch"

        try:
            # 调用 LLM 生成修复方案
            response = self._llm_client.generate_text(
                system_prompt=_LLM_REPAIR_SYSTEM_PROMPT,
                user_prompt=self._build_repair_prompt(),
            )

            # 解析响应
            return self._parse_repair_response(response, strategy)

        except Exception:
            # LLM 调用失败，返回 REGENERATE 策略
            return RepairPlan(
                chapter_id=self._chapter_id,
                actions=(
                    RepairAction(
                        violation_code="REPAIR_FAILED",
                        strategy="regenerate",
                    ),
                ),
                strategy="regenerate",
            )

    def apply_patch(self, plan: RepairPlan) -> str:
        """应用 PATCH 修复。

        参数:
            plan: 修复计划。

        返回:
            修复后的内容。
        """

        if plan.strategy == "regenerate":
            return self._content  # REGENERATE 由上层处理

        result = self._content
        for action in plan.actions:
            if action.strategy == "patch" and action.target_excerpt:
                # 校验：禁止修改数据表格
                if self._is_in_data_table(action.target_excerpt):
                    continue

                # 校验：禁止保留违规原文
                if action.target_excerpt == action.replacement:
                    continue

                # 应用替换
                if action.target_kind == "substring":
                    result = result.replace(
                        action.target_excerpt,
                        action.replacement,
                        action.occurrence_index + 1,
                    )
                elif action.target_kind == "line":
                    remaining = action.occurrence_index
                    lines = result.split('\n')
                    for i, line in enumerate(lines):
                        if action.target_excerpt in line:
                            if remaining == 0:
                                lines[i] = action.replacement
                                break
                            remaining -= 1
                    result = '\n'.join(lines)
                elif action.target_kind == "paragraph":
                    remaining = action.occurrence_index
                    paragraphs = result.split('\n\n')
                    for i, para in enumerate(paragraphs):
                        if action.target_excerpt in para:
                            if remaining == 0:
                                paragraphs[i] = action.replacement
                                break
                            remaining -= 1
                    result = '\n\n'.join(paragraphs)

        # 清理残片
        result = self._cleanup_fragments(result)
        return result

    def _is_in_data_table(self, excerpt: str) -> bool:
        """检查片段是否在数据表格中。"""
        return excerpt in self._data_table

    def _cleanup_fragments(self, content: str) -> str:
        """清理修复残片。"""
        # 清理空 bullet
        content = re.sub(r'^\s*[-*]\s*$', '', content, flags=re.MULTILINE)
        # 清理连续空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def _build_repair_prompt(self) -> str:
        """构造修复 prompt。"""

        violations_text = "\n".join(
            f"- [{v.code}] {v.description} (位置: {v.location})"
            for v in self._violations
        )

        return f"""请修复以下章节的违规问题。

## 章节信息
- 章节编号: Ch{self._chapter_id}
- 章节标题: {self._contract.title}

## 违规问题
{violations_text}

## 数据表格（禁止修改）
{self._data_table[:500]}

## 章节内容（待修复）
{self._content}

请生成修复方案。"""

    def _parse_repair_response(self, response: str, default_strategy: str) -> RepairPlan:
        """解析 LLM 修复响应。"""

        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return RepairPlan(
                    chapter_id=self._chapter_id,
                    actions=(
                        RepairAction(
                            violation_code="PARSE_FAILED",
                            strategy="regenerate",
                        ),
                    ),
                    strategy="regenerate",
                )

            data = json.loads(json_match.group())
            strategy = data.get("strategy", default_strategy)

            if strategy == "regenerate":
                return RepairPlan(
                    chapter_id=self._chapter_id,
                    actions=(
                        RepairAction(
                            violation_code="REGENERATE",
                            strategy="regenerate",
                        ),
                    ),
                    strategy="regenerate",
                )

            # PATCH 策略
            patches = data.get("patches", [])
            actions = []
            for patch in patches:
                actions.append(RepairAction(
                    violation_code=patch.get("violation_code", "PATCH"),
                    strategy="patch",
                    target_excerpt=patch.get("target_excerpt", ""),
                    replacement=patch.get("replacement", ""),
                    target_kind=patch.get("target_kind", "substring"),
                    target_section_heading=patch.get("target_section_heading", ""),
                    occurrence_index=patch.get("occurrence_index", 0),
                ))

            if not actions:
                actions.append(RepairAction(
                    violation_code="NO_PATCHES",
                    strategy="none",
                ))

            return RepairPlan(
                chapter_id=self._chapter_id,
                actions=tuple(actions),
                strategy="patch",
            )

        except (json.JSONDecodeError, KeyError, ValueError):
            return RepairPlan(
                chapter_id=self._chapter_id,
                actions=(
                    RepairAction(
                        violation_code="PARSE_FAILED",
                        strategy="regenerate",
                    ),
                ),
                strategy="regenerate",
            )


def _is_data_sufficient(chapter_id: int, data_table: str, contract: Any = None) -> bool:
    """检测章节数据是否充足。

    判定规则：仅当数据表中包含「**数据完整性声明**」精确标记时判定为数据不足。
    「未披露」「暂不可用」等属于正常字段默认值，不作为降级依据。

    参数:
        chapter_id: 章节编号。
        data_table: 程序生成的数据表。
        contract: 章节合同（预留，当前未使用）。

    返回:
        数据充足返回 True，不足返回 False。
    """
    if not data_table:
        return False
    # 只检查精确降级标记（chapter_generator 中的 **数据完整性声明**）
    return "数据完整性声明" not in data_table


# ============================================================
# ReportGenerationCoordinator（流程协调器）
# ============================================================

# 评分阈值
SCORE_PASS = 80.0      # ≥80分通过
SCORE_PATCH = 50.0     # 50-79分需修复
# <50分需重写

# 数据不足场景的评分调整
SCORE_PASS_DEGRADED = 70.0   # 数据不足时 ≥70分通过
WEIGHT_PROG_NORMAL = 0.3     # 数据充足时程序审计权重
WEIGHT_LLM_NORMAL = 0.7      # 数据充足时 LLM 审计权重
WEIGHT_PROG_DEGRADED = 0.5   # 数据不足时程序审计权重
WEIGHT_LLM_DEGRADED = 0.5    # 数据不足时 LLM 审计权重

# 最大修复次数
MAX_PATCH_ATTEMPTS = 3
MAX_REGENERATE_ATTEMPTS = 3


class ReportGenerationCoordinator:
    """报告生成协调器。

    流程：
    1. Ch1-6 独立生成（数据表格 + LLM 分析）
    2. Ch1-6 独立审计闭环（每章最多3次PATCH + 3次REGENERATE）
    3. Ch1-6 全部通过后，生成 Ch0+Ch7
    4. Ch0+Ch7 审计闭环
    5. 全部通过 → 输出

    参数:
        llm_client: LLM 客户端。
        work_dir: 工作目录。

    返回:
        协调器实例。
    """

    def __init__(
        self,
        llm_client: Any,
        work_dir: Path,
    ) -> None:
        """初始化协调器。"""
        self._llm_client = llm_client
        self._work_dir = work_dir
        self._artifact_store = ArtifactStore(work_dir)
        self._process_states: dict[int, ChapterProcessState] = {}

    def generate_report(
        self,
        fund_code: str,
        fund_name: str,
        report_year: int,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[Any, ...]],
        allocation: dict[int, tuple[Any, ...]],
        fees: dict[int, tuple[Any, ...]],
        fund_manager: Any = None,
        scale_info: Any = None,
        evidence: Any = None,
        signal_judgment: Any = None,
    ) -> tuple[dict[int, str], list[str]]:
        """生成报告。

        参数:
            fund_code: 基金代码。
            fund_name: 基金名称。
            report_year: 报告年份。
            performance/holdings/allocation/fees: 多年度数据。
            fund_manager: 基金经理信息。
            scale_info: 规模信息。
            evidence: 证据来源汇总。

        返回:
            (章节内容字典, 警告列表)。
        """

        warnings: list[str] = []
        chapter_contents: dict[int, str] = {}

        # 0. 预生成所有章节数据表，收集全局允许数字集合（支持跨章节引用）
        from fund_agent.service.chapter_generator import generate_data_table
        from fund_agent.service.extraction import _compute_ch6_stress_test
        global_numbers: set[str] = set()
        for cid in range(1, 8):
            st = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name) if cid == 6 else None
            dt = generate_data_table(
                cid, fund_code, fund_name, report_year,
                performance, holdings, allocation, fees,
                fund_manager, scale_info, evidence,
                stress_test=st, signal_judgment=signal_judgment,
            )
            global_numbers.update(re.findall(r'\d+\.?\d*', dt))

        # 1. 生成 Ch1-6
        for chapter_id in range(1, 7):
            content = self._generate_and_audit_chapter(
                chapter_id=chapter_id,
                fund_code=fund_code,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                holdings=holdings,
                allocation=allocation,
                fees=fees,
                fund_manager=fund_manager,
                scale_info=scale_info,
                evidence=evidence,
                signal_judgment=signal_judgment,
                global_allowed_numbers=global_numbers,
            )
            if content:
                chapter_contents[chapter_id] = content
            else:
                warnings.append(f"Ch{chapter_id} 生成失败")

        # 2. 检查 Ch1-6 是否全部通过（含数据不足时的降级通过）
        all_passed = all(
            self._process_states.get(cid, ChapterProcessState(chapter_id=cid)).status in ("passed", "passed_with_degradation")
            for cid in range(1, 7)
        )

        if not all_passed:
            warnings.append("Ch1-6 未全部通过，Ch0+Ch7 使用模板生成")
            # 使用模板生成 Ch0+Ch7
            chapter_contents[0] = self._generate_template_chapter(
                chapter_id=0,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                evidence=evidence,
                fund_code=fund_code,
                fund_manager=fund_manager,
                scale_info=scale_info,
                signal_judgment=signal_judgment,
            )
            chapter_contents[7] = self._generate_template_chapter(
                chapter_id=7,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                evidence=evidence,
                fund_code=fund_code,
                fund_manager=fund_manager,
                scale_info=scale_info,
                signal_judgment=signal_judgment,
            )
            return chapter_contents, warnings

        # 3. Ch1-6 全部通过，生成 Ch0+Ch7
        for chapter_id in [0, 7]:
            content = self._generate_and_audit_chapter(
                chapter_id=chapter_id,
                fund_code=fund_code,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                holdings=holdings,
                allocation=allocation,
                fees=fees,
                fund_manager=fund_manager,
                scale_info=scale_info,
                use_chapter_summaries=True,
                chapter_summaries={cid: chapter_contents.get(cid, "") for cid in range(1, 7)},
                signal_judgment=signal_judgment,
            )
            if content:
                chapter_contents[chapter_id] = content
            else:
                warnings.append(f"Ch{chapter_id} 生成失败")

        return chapter_contents, warnings

    def _generate_and_audit_chapter(
        self,
        chapter_id: int,
        fund_code: str,
        fund_name: str,
        report_year: int,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[Any, ...]],
        allocation: dict[int, tuple[Any, ...]],
        fees: dict[int, tuple[Any, ...]],
        fund_manager: Any = None,
        scale_info: Any = None,
        evidence: Any = None,
        use_chapter_summaries: bool = False,
        chapter_summaries: dict[int, str] | None = None,
        signal_judgment: Any = None,
        global_allowed_numbers: set[str] | None = None,
    ) -> str | None:
        """生成并审计单个章节。

        参数:
            chapter_id: 章节编号。
            其他参数同 generate_report。

        返回:
            审计通过的章节内容；失败时返回 None。
        """

        try:
            return self._generate_and_audit_chapter_inner(
                chapter_id=chapter_id,
                fund_code=fund_code, fund_name=fund_name,
                report_year=report_year,
                performance=performance, holdings=holdings,
                allocation=allocation, fees=fees,
                fund_manager=fund_manager, scale_info=scale_info,
                evidence=evidence,
                use_chapter_summaries=use_chapter_summaries,
                chapter_summaries=chapter_summaries,
                signal_judgment=signal_judgment,
                global_allowed_numbers=global_allowed_numbers,
            )
        except Exception:
            state = ChapterProcessState(chapter_id=chapter_id)
            state.status = "failed"
            state.record_event("generate_failed", {"chapter_id": chapter_id, "reason": "unhandled_exception"})
            self._process_states[chapter_id] = state
            return None

    def _generate_and_audit_chapter_inner(
        self,
        chapter_id: int,
        fund_code: str,
        fund_name: str,
        report_year: int,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[Any, ...]],
        allocation: dict[int, tuple[Any, ...]],
        fees: dict[int, tuple[Any, ...]],
        fund_manager: Any = None,
        scale_info: Any = None,
        evidence: Any = None,
        global_allowed_numbers: set[str] | None = None,
        use_chapter_summaries: bool = False,
        chapter_summaries: dict[int, str] | None = None,
        signal_judgment: Any = None,
    ) -> str | None:
        """内部实现，由 _generate_and_audit_chapter 包装异常处理。"""

        # 初始化过程状态
        state = ChapterProcessState(chapter_id=chapter_id)
        self._process_states[chapter_id] = state
        contract = get_chapter_contract(chapter_id)

        if not contract:
            return None

        # 生成数据表格
        from fund_agent.service.chapter_generator import generate_data_table
        from fund_agent.service.extraction import _compute_ch6_stress_test
        stress_test = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name) if chapter_id == 6 else None
        data_table = generate_data_table(
            chapter_id, fund_code, fund_name, report_year,
            performance, holdings, allocation, fees,
            fund_manager, scale_info, evidence,
            stress_test=stress_test,
            signal_judgment=signal_judgment,
        )

        # 生成章节内容（LLM 或模板）
        content = self._generate_chapter_content(
            chapter_id=chapter_id,
            fund_code=fund_code,
            fund_name=fund_name,
            report_year=report_year,
            data_table=data_table,
            performance=performance,
            holdings=holdings,
            allocation=allocation,
            fees=fees,
            fund_manager=fund_manager,
            scale_info=scale_info,
            use_chapter_summaries=use_chapter_summaries,
            chapter_summaries=chapter_summaries,
            global_allowed_numbers=global_allowed_numbers,
        )

        if not content:
            # LLM 生成失败，尝试模板降级
            content = self._generate_template_chapter(
                chapter_id=chapter_id,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                evidence=evidence,
                fund_code=fund_code,
                fund_manager=fund_manager,
                scale_info=scale_info,
                signal_judgment=signal_judgment,
                risk_checklist=None,  # 审计管道中不传 risk_checklist
                stress_test=stress_test,
            )
            if content:
                # 模板降级成功，标记为 passed_with_degradation
                state.status = "passed_with_degradation"
                state.record_event("template_fallback", {"chapter_id": chapter_id})
                self._artifact_store.save_process_state(state)
                return content
            state.status = "failed"
            state.record_event("generate_failed", {"chapter_id": chapter_id})
            self._artifact_store.save_process_state(state)
            return None

        state.write_attempts += 1

        # 审计用数据表：Ch0/Ch7 需要额外提供 Ch1-6 的摘要作为审计上下文
        audit_data_table = data_table
        if use_chapter_summaries and chapter_summaries:
            summary_parts = [data_table, "\n\n## 前序章节摘要\n"]
            for cid in range(1, 7):
                summary = chapter_summaries.get(cid, "")
                if summary:
                    summary_parts.append(f"### Ch{cid}\n{summary[:1000]}\n")
            audit_data_table = "\n".join(summary_parts)

        # 审计闭环
        last_valid_content = content  # 保留初始生成的内容
        for attempt in range(MAX_PATCH_ATTEMPTS + MAX_REGENERATE_ATTEMPTS):
            state.audit_attempts += 1

            # 程序审计
            prog_auditor = ProgrammaticAuditor(chapter_id, content, audit_data_table, contract, global_allowed_numbers=global_allowed_numbers)
            prog_score, prog_violations = prog_auditor.audit()

            # LLM 审计
            llm_auditor = LlmAuditor(self._llm_client, chapter_id, content, audit_data_table, contract)
            llm_score, llm_violations = llm_auditor.audit()

            # 数据充足性检测
            data_sufficient = _is_data_sufficient(chapter_id, data_table, contract)

            # 综合分数（根据数据充足性调整权重）
            if data_sufficient:
                weight_prog = WEIGHT_PROG_NORMAL
                weight_llm = WEIGHT_LLM_NORMAL
                score_pass = SCORE_PASS
            else:
                weight_prog = WEIGHT_PROG_DEGRADED
                weight_llm = WEIGHT_LLM_DEGRADED
                score_pass = SCORE_PASS_DEGRADED

            final_score = prog_score * weight_prog + llm_score * weight_llm
            all_violations = prog_violations + llm_violations

            # 记录审计决定
            decision = AuditDecision(
                chapter_id=chapter_id,
                score=final_score,
                violations=all_violations,
                programmatic_score=prog_score,
                llm_score=llm_score,
                recommendation="pass" if final_score >= score_pass else "patch" if final_score >= SCORE_PATCH else "regenerate",
                audit_time=datetime.now().isoformat(),
            )
            self._artifact_store.save_audit_decision(decision)

            state.current_score = final_score
            state.violations = all_violations
            state.record_event("audit", {
                "attempt": state.audit_attempts,
                "score": final_score,
                "violations_count": len(all_violations),
                "recommendation": decision.recommendation,
                "data_sufficient": data_sufficient,
                "weight_prog": weight_prog,
                "weight_llm": weight_llm,
                "score_pass_threshold": score_pass,
            })

            # 判断是否通过
            if final_score >= score_pass:
                state.status = "passed_with_degradation" if not data_sufficient else "passed"
                state.record_event(state.status, {"score": final_score, "data_sufficient": data_sufficient})
                self._artifact_store.save_process_state(state)
                return content

            # 需要修复
            if final_score >= SCORE_PATCH:
                # PATCH 策略
                if state.can_patch():
                    state.patch_attempts += 1
                    repairer = ChapterRepairer(
                        self._llm_client, chapter_id, content, data_table,
                        contract, all_violations,
                    )
                    plan = repairer.generate_repair_plan()
                    self._artifact_store.save_repair_plan(plan)

                    if plan.strategy == "patch":
                        content = repairer.apply_patch(plan)
                        state.record_event("patched", {
                            "attempt": state.patch_attempts,
                            "actions_count": len(plan.actions),
                        })
                    else:
                        # PATCH 失败，尝试 REGENERATE
                        if state.can_regenerate():
                            state.regenerate_attempts += 1
                            content = self._regenerate_chapter(
                                chapter_id, fund_code, fund_name, report_year,
                                data_table, performance, holdings, allocation,
                                fees, fund_manager, scale_info,
                            )
                            state.record_event("regenerated", {
                                "attempt": state.regenerate_attempts,
                            })
                else:
                    # PATCH 次数用完，尝试 REGENERATE
                    if state.can_regenerate():
                        state.regenerate_attempts += 1
                        regen = self._regenerate_chapter(
                            chapter_id, fund_code, fund_name, report_year,
                            data_table, performance, holdings, allocation,
                            fees, fund_manager, scale_info,
                        )
                        if regen:
                            content = regen
                            last_valid_content = regen
                        state.record_event("regenerated", {
                            "attempt": state.regenerate_attempts,
                        })
            else:
                # REGENERATE 策略
                if state.can_regenerate():
                    state.regenerate_attempts += 1
                    content = self._regenerate_chapter(
                        chapter_id, fund_code, fund_name, report_year,
                        data_table, performance, holdings, allocation,
                        fees, fund_manager, scale_info,
                    )
                    state.record_event("regenerated", {
                        "attempt": state.regenerate_attempts,
                    })

        # 所有修复尝试用完：得分 < 50 返回模板，≥ 50 返回 LLM 内容（标记降级）
        final_score = state.current_score or 0
        if final_score < 50 or not content:
            # 低分或无内容 → 模板降级
            template_content = self._generate_template_chapter(
                chapter_id=chapter_id,
                fund_name=fund_name,
                report_year=report_year,
                performance=performance,
                evidence=evidence,
                fund_code=fund_code,
                fund_manager=fund_manager,
                scale_info=scale_info,
                signal_judgment=signal_judgment,
            )
            state.status = "passed_with_degradation"
            state.record_event("template_fallback", {
                "reason": "audit_exhausted_low_score",
                "final_score": final_score,
            })
            self._artifact_store.save_process_state(state)
            return template_content
        else:
            # 中等分数 → 返回 LLM 内容，标记降级
            state.status = "passed_with_degradation"
            state.record_event("passed_with_degradation", {
                "reason": "audit_exhausted_medium_score",
                "final_score": final_score,
            })
            self._artifact_store.save_process_state(state)
            return content if content else last_valid_content

    def _generate_chapter_content(
        self,
        chapter_id: int,
        fund_code: str,
        fund_name: str,
        report_year: int,
        data_table: str,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[Any, ...]],
        allocation: dict[int, tuple[Any, ...]],
        fees: dict[int, tuple[Any, ...]],
        fund_manager: Any = None,
        scale_info: Any = None,
        use_chapter_summaries: bool = False,
        chapter_summaries: dict[int, str] | None = None,
        global_allowed_numbers: set[str] | None = None,
    ) -> str | None:
        """生成章节内容。"""

        from fund_agent.service.chapter_generator import LLM_ANALYSIS_PROMPTS, LLM_CHAPTER_SYSTEM_PROMPT

        analysis_prompt = LLM_ANALYSIS_PROMPTS.get(chapter_id)
        if not analysis_prompt:
            return None

        # 构造 user prompt
        user_prompt_parts = [
            f"基金名称：{fund_name}",
            f"报告年份：{report_year}",
            "",
            "## 数据表格",
            "",
            data_table,
            "",
        ]

        # 如果是 Ch0/Ch7，添加 Ch1-6 的分析摘要
        if use_chapter_summaries and chapter_summaries:
            user_prompt_parts.append("## 前序章节分析摘要")
            user_prompt_parts.append("")
            for cid in range(1, 7):
                summary = chapter_summaries.get(cid, "")
                if summary:
                    # 只取前500字作为摘要
                    user_prompt_parts.append(f"### Ch{cid} 摘要")
                    user_prompt_parts.append(summary[:1500])
                    user_prompt_parts.append("")

        user_prompt_parts.extend([
            "## 分析要求",
            "",
            analysis_prompt,
        ])

        user_prompt = "\n".join(user_prompt_parts)

        try:
            llm_analysis = self._llm_client.generate_text(
                system_prompt=LLM_CHAPTER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            if not llm_analysis or not isinstance(llm_analysis, str):
                return None

            # 检查 hallucination（优先使用全局允许列表，支持跨章节数字引用）
            from fund_agent.service.chapter_generator import contains_non_year_numbers
            if global_allowed_numbers:
                allowed_numbers = global_allowed_numbers
            else:
                allowed_numbers = set(re.findall(r'\d+\.?\d*', data_table))
            if contains_non_year_numbers(llm_analysis, allowed_numbers):
                return None

            return f"{data_table}\n\n## 分析\n\n{llm_analysis}"

        except Exception:
            return None

    def _regenerate_chapter(
        self,
        chapter_id: int,
        fund_code: str,
        fund_name: str,
        report_year: int,
        data_table: str,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[Any, ...]],
        allocation: dict[int, tuple[Any, ...]],
        fees: dict[int, tuple[Any, ...]],
        fund_manager: Any = None,
        scale_info: Any = None,
    ) -> str | None:
        """重新生成章节。"""

        return self._generate_chapter_content(
            chapter_id=chapter_id,
            fund_code=fund_code,
            fund_name=fund_name,
            report_year=report_year,
            data_table=data_table,
            performance=performance,
            holdings=holdings,
            allocation=allocation,
            fees=fees,
            fund_manager=fund_manager,
            scale_info=scale_info,
        )

    def _generate_template_chapter(
        self,
        chapter_id: int,
        fund_name: str,
        report_year: int,
        performance: dict[int, dict[str, str]],
        evidence: Any = None,
        fund_code: str = "",
        fund_manager: Any = None,
        scale_info: Any = None,
        signal_judgment: Any = None,
        risk_checklist: Any = None,
        stress_test: Any = None,
    ) -> str:
        """生成模板章节（fallback）。

        参数:
            chapter_id: 章节编号。
            fund_name: 基金名称。
            report_year: 报告年份。
            performance: 多年度业绩数据。
            evidence: 证据来源汇总（可选）。
            fund_code: 基金代码（可选）。
            fund_manager: 基金经理信息（可选）。
            scale_info: 规模信息（可选）。
            signal_judgment: 信号判断结果（可选）。
            risk_checklist: 风险清单（可选）。
            stress_test: 压力测试结果（可选）。

        返回:
            模板生成的 Markdown 文本（含证据来源小节）。
        """

        if chapter_id == 0:
            latest = performance.get(report_year, {})
            base_content = (
                f"## 一眼看懂\n\n"
                f"- **基金名称**：{fund_name}\n"
                f"- **基金代码**：{fund_code}\n"
                f"- **报告年份**：{report_year}\n"
                f"- **最新净值增长率**：{latest.get('nav_growth_rate', 'N/A')}\n\n"
                f"## 投资要点\n\n"
                f"基于 {report_year} 年报数据分析，该基金业绩表现和持仓情况详见后续章节。\n"
            )
        elif chapter_id == 1:
            lines = [
                f"## 基金概况\n",
                f"- 基金代码：{fund_code}",
                f"- 基金名称：{fund_name}",
                f"- 报告年份：{report_year}",
            ]
            if fund_manager:
                lines.append(f"- 基金经理：{fund_manager.name}（从业{fund_manager.years_of_service}）")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 2:
            lines = ["## 业绩数据\n"]
            if report_year in performance:
                perf = performance[report_year]
                lines.extend([
                    "| 年份 | 净值增长率 | 基准收益率 | 超额收益 |",
                    "|------|-----------|-----------|---------|",
                    f"| {report_year} | {perf.get('nav_growth_rate', 'N/A')} | {perf.get('benchmark_return_rate', 'N/A')} | {perf.get('excess_return', 'N/A')} |",
                ])
            else:
                lines.append("暂无业绩数据。")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 3:
            lines = ["## 基金经理信息"]
            if fund_manager:
                lines.extend([
                    f"- 姓名：{fund_manager.name}",
                    f"- 任职日期：{fund_manager.tenure_start}",
                    f"- 从业年限：{fund_manager.years_of_service}",
                    f"- 持有本基金：{fund_manager.holds_fund or '未披露'}",
                ])
            else:
                lines.append("基金经理信息暂不可用。")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 4:
            base_content = "## 投资者获得感\n\n投资者实际收益数据暂不可用，详见原始年报。\n"
        elif chapter_id == 5:
            lines = ["## 当前阶段与关键变化"]
            if scale_info:
                lines.extend([
                    f"- A类份额总数：{scale_info.total_shares_a}",
                    f"- C类份额总数：{scale_info.total_shares_c}",
                    f"- 管理人持有比例：{scale_info.management_holds}",
                ])
            else:
                lines.append("规模信息暂不可用。")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 6:
            lines = ["## 核心风险与否决项\n"]
            # 压力测试（如果有）
            if stress_test:
                fund_type_labels = {"index_fund": "指数基金", "bond_fund": "债券基金", "active_fund": "主动基金"}
                lines.extend([
                    "### 压力测试\n",
                    f"- 基金类型: {fund_type_labels.get(stress_test.fund_type, stress_test.fund_type)}",
                ])
                if stress_test.current_scale_billion is not None:
                    lines.append(f"- 当前规模: {stress_test.current_scale_billion:.2f}亿元")
                if stress_test.excess_return is not None:
                    lines.append(f"- 超额收益: {stress_test.excess_return:.2%}")
                lines.append("")
            # 风险清单
            lines.extend(["### 风险清单\n", "| 风险项 | 状态 | 说明 |", "|--------|------|------|"])
            if risk_checklist:
                for item in risk_checklist:
                    lines.append(f"| {item.name} | {item.status} | {item.detail} |")
            else:
                lines.append("| （无数据） | 🟡 | 需要补充数据 |")
            base_content = "\n".join(lines) + "\n"
        elif chapter_id == 7:
            latest = performance.get(report_year, {})
            base_content = (
                f"## 综合评估\n\n"
                f"基于 {report_year} 年报数据，该基金最新净值增长率为 {latest.get('nav_growth_rate', 'N/A')}。"
                f"详见前6章分析。\n"
            )
        else:
            base_content = ""

        # 追加证据来源小节
        from fund_agent.service.chapter_generator import generate_evidence_section
        evidence_section = generate_evidence_section(chapter_id, evidence)
        if evidence_section:
            return base_content + "\n" + evidence_section
        return base_content

    def get_process_states(self) -> dict[int, ChapterProcessState]:
        """获取所有章节的过程状态。"""
        return dict(self._process_states)
