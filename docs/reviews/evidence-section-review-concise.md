请严格审查证据小节结构化变更。先 `grep -n` 确认代码存在再评论。

## 变更（3文件，+343/-40）

1. **ChapterEvidence DTO**：持仓/费率/资产配置/业绩/经理 citation 汇总
2. **5个 `_with_citations` 方法**：从抽取结果中保留 citation
3. **`_format_citation()` + `_generate_evidence_section()`**：生成 `### 证据与出处` 小节
4. **`_generate_data_table()`**：新增 evidence 参数，末尾追加证据小节
5. **`_generate_template_chapter()`**：Ch0/1/2 不再早 return
6. **`generate_report()`**：使用 `_with_citations` 构建 ChapterEvidence

## 关键代码

```python
# 证据小节生成
def _generate_evidence_section(chapter_id, evidence):
    # 根据 chapter_id 列出相关 citation
    # Ch0/2/7: 业绩 citation
    # Ch0/3/6/7: 持仓 citation
    # Ch2/5/7: 费率 citation
    # Ch4/5: 资产配置 citation
    # Ch1/3: 基金经理 citation

# citation 格式化
def _format_citation(citation):
    # → "2025年报 (§section-0070, 表table-0010, p.8)"

# generate_report 中构建证据
fund_manager, fund_manager_citation = self._extract_fund_manager_with_citation(...)
evidence = ChapterEvidence(
    holdings_citations=holdings_citations,
    performance_citations=performance_citations,
    fund_manager_citation=fund_manager_citation,
    ...
)
```

## 测试
- `test_llm_chapter_generation.py`：12 passed（mock 更新）
- 真实 smoke：8/8 章都有证据小节

## 请输出
P0 / P1 / P2 + 总结
