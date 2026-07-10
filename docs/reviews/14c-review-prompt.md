请严格审查以下 Python 代码变更（Slice 14C: Chapter audit pipeline）。

**重要规则**：对每个 findings，必须先 `grep -n` 确认代码存在再评论。不要捏造不存在的代码。

## 项目背景
基金年报阅读工具。14C 新增章节审计管道，基于 dayu write_pipeline 设计。

## 硬边界（违反即 P0）
1. 禁止投资建议
2. 禁止数字 hallucination（数字由程序填充，LLM 只写定性分析）
3. 数据必须可溯源到年报
4. 禁止直接消费 raw PDF/Docling JSON
5. 数据表格禁止修改（审计和修复时）

## 核心变更

### 新增文件：`fund_agent/service/audit_pipeline.py`

**ChapterContract**（章节合同）：
```python
@dataclass(frozen=True)
class ChapterContract:
    chapter_id: int
    title: str
    must_answer: tuple[str, ...]
    must_not_cover: tuple[str, ...]
    required_output_items: tuple[str, ...]
    data_sources: tuple[str, ...]
    narrative_mode: str = ""
```
8章合同定义，从 `docs/fund-analysis-template-draft.md` 提取。

**违规分类体系**（4类22项）：
```python
class ViolationCategory(str, Enum):
    PLACEHOLDER = "P"  # 数据/幻觉（P1-P4）
    EVIDENCE = "E"     # 证据（E1-E5）
    STRUCTURE = "S"    # 结构（S1-S7）
    CONTENT = "C"      # 内容（C1-C6）
```

**AuditViolation / AuditDecision / RepairAction / RepairPlan**：
```python
@dataclass(frozen=True)
class AuditViolation:
    code: str
    category: ViolationCategory
    severity: ViolationSeverity
    description: str
    location: str = ""
    suggested_fix: str = ""
    evidence: str = ""

@dataclass(frozen=True)
class AuditDecision:
    chapter_id: int
    score: float  # 0-100
    violations: tuple[AuditViolation, ...]
    programmatic_score: float = 0.0
    llm_score: float = 0.0
    recommendation: str = "pass"  # "pass" | "patch" | "regenerate"
```

**ProgrammaticAuditor**（第一层：程序审计）：
- 数字合规检查（P1数据为空、P2数字编造、P3模板残留）
- 必须字段检查（S2）
- 禁止内容检查（C3投资建议、C5 must_not_cover违规）
- 结构完整性检查（S1内容过短、S3格式错误）

**LlmAuditor**（第二层：LLM 审计）：
- 调用 LLM 检查分析深度、逻辑一致性、事实准确性
- 返回结构化 JSON（score + violations）

**ChapterRepairer**（修复器）：
- PATCH 策略：精确定位修复（target_excerpt + replacement）
- REGENERATE 策略：整章重写
- 禁止修改数据表格（`_is_in_data_table` 检查）

**ReportGenerationCoordinator**（流程协调器）：
```python
class ReportGenerationCoordinator:
    def generate_report(self, ...) -> tuple[dict[int, str], list[str]]:
        # 1. Ch1-6 独立生成
        # 2. Ch1-6 独立审计闭环（每章最多3次PATCH + 3次REGENERATE）
        # 3. Ch1-6 全部通过后，生成 Ch0+Ch7
        # 4. Ch0+Ch7 审计闭环
        # 5. 全部通过 → 输出
```

**ChapterProcessState**（过程可观测性）：
```python
@dataclass
class ChapterProcessState:
    chapter_id: int
    write_attempts: int = 0
    audit_attempts: int = 0
    patch_attempts: int = 0
    regenerate_attempts: int = 0
    current_score: float = 0.0
    status: str = "pending"  # "pending" | "passed" | "failed"
```

**ArtifactStore**（审计产物持久化）：
- 保存/加载 AuditDecision（chapter_N_audit.json）
- 保存 RepairPlan（chapter_N_repair.json）
- 保存 ChapterProcessState（chapter_N_state.json）

### 修改文件：`fund_agent/service/reading_service.py`

`generate_report()` 方法集成审计管道：
```python
if llm_client is not None:
    # 使用审计管道协调器（14C）
    coordinator = ReportGenerationCoordinator(llm_client, work_dir)
    chapter_contents, warnings = coordinator.generate_report(...)
    # 转换为 ReportChapter 列表
else:
    # 模板模式
    chapters = self._generate_chapters(...)
```

### 评分体系
- 程序审计 30% + LLM 审计 70%
- ≥80分通过，50-79分需PATCH，<50分需REGENERATE
- PATCH 最多3次，REGENERATE 最多3次

## 测试
`tests/fund/service/test_audit_pipeline.py` — 22 passed：
- ChapterContract 定义和查询
- ProgrammaticAuditor（合规/投资建议/空数据表/占位符）
- AuditViolation/AuditDecision DTO
- ChapterProcessState（初始/可PATCH/可REGENERATE/事件记录）
- ArtifactStore（保存/加载审计决定/过程状态/修复计划）
- ChapterRepairer（PATCH策略/REGENERATE策略/应用PATCH/禁止修改数据表格）
- ReportGenerationCoordinator 初始化

`tests/fund/service/test_llm_chapter_generation.py` — 10 passed（适配新审计管道）

## 已知问题（不在 review 范围）
1. ProgrammaticAuditor 的 `_check_required_fields` 较严格，可能产生 S2 误报
2. LlmAuditor 依赖 LLM 返回 JSON，解析失败时返回默认分数 50
3. 修复机制（PATCH/REGENERATE）的 LLM 调用尚未真实验证

## 请输出

### P0（必须修复）
问题 + 文件:行号 + 修复建议

### P1（建议修复）
问题 + 文件:行号 + 修复建议

### P2（可选优化）
问题 + 建议

### 总结
一段话概括代码质量和主要风险。
