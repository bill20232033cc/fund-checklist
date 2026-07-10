请严格审查以下变更（证据小节结构化 + 业绩/经理 citation 追踪）。

**规则**：先 `grep -n` 确认代码存在再评论。

## 变更摘要

3 个文件，+343/-40 行。

### 1. 新增 `ChapterEvidence` DTO

```python
@dataclass(frozen=True)
class ChapterEvidence:
    holdings_citations: dict[int, Citation | None] = field(default_factory=dict)
    fee_citations: dict[int, Citation | None] = field(default_factory=dict)
    allocation_citations: dict[int, Citation | None] = field(default_factory=dict)
    performance_citations: dict[int, Citation | None] = field(default_factory=dict)
    fund_manager_citation: Citation | None = None
    scale_citation: Citation | None = None
```

### 2. 新增 `_with_citations` 方法

- `_extract_report_holdings_with_citations()` → `(holdings, citations)`
- `_extract_report_fees_with_citations()` → `(fees, citations)`
- `_extract_report_allocation_with_citations()` → `(allocation, citations)`
- `_extract_report_performance_with_citations()` → `(performance, citations)`
- `_extract_fund_manager_with_citation()` → `(fund_manager, citation)`

旧方法保留向后兼容，内部委托给新方法。

### 3. 新增证据小节生成

```python
def _format_citation(citation: Citation | None) -> str:
    # 格式化为 "2025年报 (§section-0070, 表table-0010, p.8)"

def _generate_evidence_section(chapter_id: int, evidence: ChapterEvidence | None) -> str:
    # 根据 chapter_id 和数据来源生成 ### 证据与出处 小节
```

### 4. 修改 `_generate_data_table`

新增 `evidence: ChapterEvidence | None = None` 参数，末尾追加证据小节。

### 5. 修改 `_generate_template_chapter`

Ch0/Ch1/Ch2 不再早 return，统一走末尾的证据小节追加逻辑。

### 6. 修改 `LlmChapterGenerator.generate_chapter`

新增 `evidence` 参数，传递给 `_generate_data_table`。

### 7. 修改 `generate_report`

使用 `_with_citations` 方法提取数据，构建 `ChapterEvidence` 传递给章节生成。

## 请输出

### P0（必须修复）
问题 + 文件:行号 + 修复建议

### P1（建议修复）
问题 + 文件:行号 + 修复建议

### P2（可选优化）
问题 + 建议

### 总结
