请对 Slice 14A 做 re-review。上一轮 P1×4 已修复，P2×3 暂不修。

**规则**：先 `grep -n` 确认代码存在再评论。

## 请验证 4 项修复

1. **P1.1 重复 return ""**：执行 `grep -n 'return ""' reading_service.py`，应只有 2 处（非连续）
2. **P1.2 重复 _generate_template_chapter**：执行 `grep -n "def _generate_template_chapter" reading_service.py`，应只有 1 处
3. **P1.3 4个旧方法死代码**：执行 `grep -n "_generate_ch0_summary\|_generate_ch3_holdings\|_generate_ch4_allocation\|_generate_ch5_fees" reading_service.py`，应无结果
4. **P1.4 投资建议措辞**：执行 `grep -n "值得持有\|建议替换" reading_service.py`，应无结果

## 本轮变更

- 删除约 80 行死代码（4个旧方法 + 第一份 _generate_template_chapter + 重复 return）
- `_LLM_ANALYSIS_PROMPTS` dict 被重新定位（内容不变）
- 章节标题"是否值得持有"→"综合评估与跟踪建议"
- LLM prompt 措辞软化

## 请输出

### 修复验证
每项 PASS/FAIL + 证据

### 新发现（如有）
仅列出修复引入的新问题

### 总结
