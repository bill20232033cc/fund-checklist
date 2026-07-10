请对 Slice 14A 做 re-review（第二轮）。上一轮 review 的 P1×4 已全部修复，P2×3 暂不修。

**重要规则**：对每个 findings，必须先 `grep -n` 确认代码存在再评论。不要捏造不存在的代码。

## 上轮修复确认

请验证以下 4 项修复是否正确：

| 上轮 finding | 修复方式 | 验证命令 |
|-------------|---------|---------|
| P1.1 重复 `return ""` | 删除重复行 | `grep -n 'return ""' reading_service.py` |
| P1.2 重复 `_generate_template_chapter` | 删除第一份定义 | `grep -n "def _generate_template_chapter" reading_service.py` |
| P1.3 4个旧方法死代码 | 删除 `_generate_ch0_summary`、`_generate_ch3_holdings`、`_generate_ch4_allocation`、`_generate_ch5_fees` | `grep -n "_generate_ch0_summary\|_generate_ch3_holdings\|_generate_ch4_allocation\|_generate_ch5_fees" reading_service.py` |
| P1.4 投资建议措辞 | "是否值得持有——最终判断" → "综合评估与跟踪建议"；prompt 中"值得持有/建议替换" → "表现优异/表现平稳/需要关注" | `grep -n "值得持有\|建议替换" reading_service.py` |

## 本轮 review 范围

只审查修复引入的新问题，不重复审查上轮已确认的 P0 和 P2。

## 本轮变更摘要

删除约 80 行死代码：
- `_generate_ch0_summary`（~20行）
- `_generate_ch3_holdings`（~12行）
- `_generate_ch4_allocation`（~12行）
- `_generate_ch5_fees`（~8行）
- 第一份 `_generate_template_chapter`（~70行）
- 重复 `return ""`（1行）
- 章节标题"是否值得持有"→"综合评估与跟踪建议"
- LLM prompt 措辞软化

新增约 70 行（`_LLM_ANALYSIS_PROMPTS` dict 被重新定位到 `_generate_data_table` 之前）。

## 请输出

### 修复验证
每项修复的验证结果（PASS/FAIL + 证据）

### 新发现（如有）
仅列出修复引入的新问题

### 总结
一段话概括修复质量
