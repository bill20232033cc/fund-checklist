请严格审查 Slice 14C（Chapter audit pipeline）。

**规则**：先 `grep -n` 确认代码存在再评论。

## 核心变更
新增 `fund_agent/service/audit_pipeline.py`（约 1200 行）+ 修改 `reading_service.py` 的 `generate_report()`。

## 关键组件
1. **ChapterContract**：8章合同（must_answer/must_not_cover/required_output_items）
2. **违规分类**：4类22项（P1-P4/E1-E5/S1-S7/C1-C6）
3. **ProgrammaticAuditor**：规则审计（数字合规+必须字段+禁止内容+结构）
4. **LlmAuditor**：LLM 审计（分析深度+逻辑一致性）
5. **ChapterRepairer**：PATCH/REGENERATE 修复
6. **ReportGenerationCoordinator**：Ch1-6→审计→Ch0+Ch7 流程
7. **ChapterProcessState**：可观测性
8. **ArtifactStore**：审计产物持久化

## 评分体系
- 程序审计 30% + LLM 审计 70%
- ≥80通过，50-79需PATCH，<50需REGENERATE
- PATCH/REGENERATE 各最多3次

## 测试
- `test_audit_pipeline.py`：22 passed
- `test_llm_chapter_generation.py`：10 passed（适配新管道）

## 请输出
### P0（必须修复）
### P1（建议修复）
### P2（可选优化）
### 总结
