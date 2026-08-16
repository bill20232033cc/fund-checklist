# 季报快照分析模板（fund-quarterly-snapshot-template）

- 版本：2.0（2026-08-15，与 design.md §6.25 同步；对齐 docs/fund-analysis-template-draft.md 的 typed chapter contract 结构）
- 定位：单期快照（latest disclosure snapshot）——单份季报 PDF → 当期分析；**非多年**。
- 报告期口径：quarterly_report，document_id 带 `-Q[1-4]` 期次段；概览/数据表格头部必须显示具体季度（如「2026 年二季度」），禁止出现「QNone」占位。
- 数据源：仅当期季报；**季报缺失项（全部持仓/财务三表/托管人报告/持有人结构/换手率/市场展望）必须 fail-closed 声明，不从年报补**。
- 滚动窗口 ≠ 日历年度：3.2.1 净值增长率各阶段行为滚动窗口，禁止与年报逐年值混用；五年系列只能来自年报 §3.2.3。
- 行标签精确匹配：3.2.1 窗口行不稳定（三个月/六个月/一年/三年/五年/过去七年/自成立等），禁止假设固定窗口集合；表存在但无某窗口行时声明该窗口未披露。

## Template Manifest

```json
TEMPLATE_CONTRACT_MANIFEST_JSON
{
  "schema_version": "typed_chapter_contract.v1",
  "template_id": "quarterly_snapshot",
  "report_period": "quarterly",
  "public_chapter_ids": [0, 1, 2, 3, 4],
  "chapter_titles": {
    "0": "概览",
    "1": "当期业绩与超额",
    "2": "持仓与资产配置",
    "3": "管理人动作",
    "4": "风险与跟踪"
  },
  "chapters": [
    {
      "chapter_id": 0,
      "title": "概览",
      "narrative_mode": "概览→结论→验证",
      "must_answer": [
        { "id": "ch0.must_answer.item_01", "text": "用一句话定义这只基金到底是什么产品（类型、经理、规模中最必要信息）。" },
        { "id": "ch0.must_answer.item_02", "text": "给出当期期末规模/份额与当期净值表现（必须标注报告期口径，如「2026 年二季度 · 过去一年」滚动窗口）。" },
        { "id": "ch0.must_answer.item_03", "text": "回答当前综合评估结论（表现优异/表现平稳/需要关注），默认只给一个结论。" },
        { "id": "ch0.must_answer.item_04", "text": "回答当期最值得盯住的变量是什么，默认只写 1 个。" },
        { "id": "ch0.must_answer.item_05", "text": "回答当期最大的风险是什么，默认只写 1 个主要风险。" },
        { "id": "ch0.must_answer.item_06", "text": "回答下一步最小验证问题是什么，默认只写 1 个。" }
      ],
      "must_not_cover": [
        { "id": "ch0.must_not_cover.item_01", "text": "不把本章写成后续章节的摘要、材料摘抄、按顺序复述。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch0.must_not_cover.item_02", "text": "不输出“证据与出处”小节（本章是封面页）。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch0.must_not_cover.item_03", "text": "不输出买入/卖出/持有等投资建议，不做未来收益预测。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch0.must_not_cover.item_04", "text": "不把滚动窗口净值增长率当作单季收益或日历年度值。", "applies_when": null, "allowed_contexts": [] }
      ],
      "required_output_items": [
        { "id": "ch0.required_output.item_01", "text": "一句话这是什么基金", "when_evidence_missing": null, "missing_evidence_reason": null },
        { "id": "ch0.required_output.item_02", "text": "期末规模与份额（报告期口径）", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "季报未披露期末规模/份额时只能输出证据缺口，不得编造规模数字。" },
        { "id": "ch0.required_output.item_03", "text": "当期净值表现（含报告期口径标注）", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "3.2.1 表缺失或未抽取到净值数据时只能输出证据缺口。" },
        { "id": "ch0.required_output.item_04", "text": "当前综合评估结论", "when_evidence_missing": null, "missing_evidence_reason": null },
        { "id": "ch0.required_output.item_05", "text": "当期最值得盯住的变量", "when_evidence_missing": null, "missing_evidence_reason": null },
        { "id": "ch0.required_output.item_06", "text": "当期最大的风险", "when_evidence_missing": null, "missing_evidence_reason": null },
        { "id": "ch0.required_output.item_07", "text": "下一步最小验证问题", "when_evidence_missing": null, "missing_evidence_reason": null }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "把本章当成单期体检封面页：最短时间内知道“这是什么基金、当期表现如何、该不该继续关注”。",
            "当前业绩状态要像首屏导语，滚动窗口口径必须显式标注，禁止与年报逐年值混用。"
          ],
          "facets_any": [],
          "priority": null
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": ["主动基金优先回答：当期超额收益是否稳定？基金经理言行与仓位是否一致？"],
          "facets_any": ["主动权益基金（价值风格）", "主动权益基金（均衡风格）", "主动权益基金（成长风格）"],
          "priority": "core"
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": ["指数基金优先回答：跟踪误差多大？规模流动性如何？"],
          "facets_any": ["宽基指数基金", "行业/主题指数基金", "策略指数基金"],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": ["债券基金优先回答：信用风险如何？久期多长？"],
          "facets_any": ["纯债基金", "二级债基/混合债基", "偏债混合基金"],
          "priority": "core"
        }
      },
      "audit_focus": ["final_judgment", "chapter_structure"],
      "consumes_chapter_conclusions": [1, 2, 3, 4],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 1,
      "title": "当期业绩与超额",
      "narrative_mode": "业绩→超额→判断",
      "must_answer": [
        { "id": "ch1.must_answer.item_01", "text": "当期净值增长率各阶段行（三个月/六个月/一年/三年/五年/过去七年/自成立等，精确按行标签，禁止假设固定窗口集合）。" },
        { "id": "ch1.must_answer.item_02", "text": "同期业绩比较基准收益率（同报告期口径、同行）。" },
        { "id": "ch1.must_answer.item_03", "text": "超额收益（①-③ 列，净值增长率-基准收益率）及正负判断。" },
        { "id": "ch1.must_answer.item_04", "text": "判断超额收益是结构性还是阶段性（仅基于当期可得窗口，不得外推）。" },
        { "id": "ch1.must_answer.item_05", "text": "声明报告期口径：滚动窗口 ≠ 日历年度，不得与年报逐年值混用。" }
      ],
      "must_not_cover": [
        { "id": "ch1.must_not_cover.item_01", "text": "不做未来收益预测。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch1.must_not_cover.item_02", "text": "不把滚动窗口值当作日历年度值，不把季报窗口外推为年度趋势。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch1.must_not_cover.item_03", "text": "不输出买入/卖出/持有等投资建议。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch1.must_not_cover.item_04", "text": "不为缺失窗口编造数值或从其他列推算补空。", "applies_when": null, "allowed_contexts": [] }
      ],
      "required_output_items": [
        { "id": "ch1.required_output.item_01", "text": "各阶段净值增长率（含报告期口径标注）", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "3.2.1 表缺失或未抽取到时只能输出证据缺口，不得编造收益数值。" },
        { "id": "ch1.required_output.item_02", "text": "同期基准收益率", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "基准列缺失时只能输出证据缺口。" },
        { "id": "ch1.required_output.item_03", "text": "超额收益（①-③）及正负判断", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "无①-③列时可由同表净值-基准推导；两列均缺失时只能输出证据缺口。" },
        { "id": "ch1.required_output.item_04", "text": "超额收益性质判断（结构性 vs 阶段性）", "when_evidence_missing": "render_minimum_verification_question", "missing_evidence_reason": "单期窗口不足以判定性质时，输出下一步最小验证问题而非下结论。" }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "核心区分：结构性超额（可持续能力）vs 阶段性超额（风格顺风/运气）。",
            "单期快照只有当期窗口：正负超额可直接判断，但“是否稳定”需标注窗口局限。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": ["指数基金核心是跟踪误差与费率，超额列仅作参考。"],
          "facets_any": ["宽基指数基金", "行业/主题指数基金", "策略指数基金"],
          "priority": "core"
        }
      },
      "audit_focus": ["r_abc", "evidence_anchors"],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 2,
      "title": "持仓与资产配置",
      "narrative_mode": "仓位→行业→持仓→变动",
      "must_answer": [
        { "id": "ch2.must_answer.item_01", "text": "当期仓位（权益/债券等资产类别占净值或总资产比例，标注口径）。" },
        { "id": "ch2.must_answer.item_02", "text": "行业配置分布（占净值比例）。" },
        { "id": "ch2.must_answer.item_03", "text": "前十大股票持仓（名称、公允价值、占净值比例），分析集中度。" },
        { "id": "ch2.must_answer.item_04", "text": "份额变动（期初/申购/赎回/期末）。" },
        { "id": "ch2.must_answer.item_05", "text": "季报缺失项声明：全部持仓/财务三表/托管人报告不在季报披露范围（fail-closed）。" }
      ],
      "must_not_cover": [
        { "id": "ch2.must_not_cover.item_01", "text": "不从年报补充季报缺失项（全部持仓/财务三表/托管人报告）。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch2.must_not_cover.item_02", "text": "不猜测基金经理的调仓动机。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch2.must_not_cover.item_03", "text": "不输出买入/卖出/持有等投资建议。", "applies_when": null, "allowed_contexts": [] }
      ],
      "required_output_items": [
        { "id": "ch2.required_output.item_01", "text": "资产配置/仓位", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "资产配置表缺失时只能输出证据缺口。" },
        { "id": "ch2.required_output.item_02", "text": "行业配置", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "行业配置表缺失时只能输出证据缺口。" },
        { "id": "ch2.required_output.item_03", "text": "前十大持仓", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "前十持仓表缺失时只能输出证据缺口。" },
        { "id": "ch2.required_output.item_04", "text": "份额变动", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "份额变动缺失时只能输出证据缺口。" },
        { "id": "ch2.required_output.item_05", "text": "季报缺失项声明", "when_evidence_missing": null, "missing_evidence_reason": null }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": ["仓位→行业→持仓→变动，每一层都引用数据表，不臆造。"],
          "facets_any": [],
          "priority": null
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": ["主动基金重点看：前十大集中度、行业暴露、仓位变化是否与运作分析一致。"],
          "facets_any": ["主动权益基金（价值风格）", "主动权益基金（均衡风格）", "主动权益基金（成长风格）"],
          "priority": "core"
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": ["指数基金重点看：仓位是否贴近满仓、前十与指数成分偏离。"],
          "facets_any": ["宽基指数基金", "行业/主题指数基金", "策略指数基金"],
          "priority": "core"
        }
      },
      "audit_focus": ["holdings", "evidence_anchors"],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 3,
      "title": "管理人动作",
      "narrative_mode": "动作→经理→利益",
      "must_answer": [
        { "id": "ch3.must_answer.item_01", "text": "报告期内的运作分析（管理人报告 §4.4 当期市场判断+操作），引用时注明据报告。" },
        { "id": "ch3.must_answer.item_02", "text": "基金经理基本信息（姓名、任职时间；季度报告期内的变动如实呈现）。" },
        { "id": "ch3.must_answer.item_03", "text": "固有资金投资本基金情况（如有披露；未披露时明确声明）。" }
      ],
      "must_not_cover": [
        { "id": "ch3.must_not_cover.item_01", "text": "不猜测基金经理的动机或意图。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch3.must_not_cover.item_02", "text": "不把运作分析原文当作分析观点（只复述并标注来源）。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch3.must_not_cover.item_03", "text": "不输出买入/卖出/持有等投资建议。", "applies_when": null, "allowed_contexts": [] }
      ],
      "required_output_items": [
        { "id": "ch3.required_output.item_01", "text": "管理人运作分析要点", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "季报未披露运作分析时只能输出证据缺口。" },
        { "id": "ch3.required_output.item_02", "text": "基金经理信息", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "经理信息缺失时只能输出证据缺口，不得编造。" },
        { "id": "ch3.required_output.item_03", "text": "固有资金投资情况（如披露）", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "未披露固有资金投资时按 fail-closed 声明未披露。" }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": ["只陈述披露的动作事实，不推断动机。"],
          "facets_any": [],
          "priority": null
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": ["主动基金重点看：当期操作与宣称策略是否一致（用前十持仓变化佐证）。"],
          "facets_any": ["主动权益基金（价值风格）", "主动权益基金（均衡风格）", "主动权益基金（成长风格）"],
          "priority": "core"
        }
      },
      "audit_focus": ["manager_consistency", "evidence_anchors"],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 4,
      "title": "风险与跟踪",
      "narrative_mode": "风险→分级→跟踪",
      "must_answer": [
        { "id": "ch4.must_answer.item_01", "text": "当期核心风险是什么（结构性 vs 阶段性）；数据不足以定性时明确声明，不得包装成风险。" },
        { "id": "ch4.must_answer.item_02", "text": "最关键的风险（1-2 个）及依据。" },
        { "id": "ch4.must_answer.item_03", "text": "风险严重程度分级（高/中/低）+ 依据。" },
        { "id": "ch4.must_answer.item_04", "text": "单一投资者持有比例 ≥20% 提示（如触发，引用披露原文）。" },
        { "id": "ch4.must_answer.item_05", "text": "持有人数/净值预警说明（如披露）。" },
        { "id": "ch4.must_answer.item_06", "text": "季报缺失项声明（fail-closed，不从年报补）。" }
      ],
      "must_not_cover": [
        { "id": "ch4.must_not_cover.item_01", "text": "不罗列所有可能风险。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch4.must_not_cover.item_02", "text": "不做风险发生概率的定量预测。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch4.must_not_cover.item_03", "text": "不把“数据缺失”本身包装为基金风险或创建“整体可评估性风险”参与分级。", "applies_when": null, "allowed_contexts": [] },
        { "id": "ch4.must_not_cover.item_04", "text": "不输出买入/卖出/持有等投资建议。", "applies_when": null, "allowed_contexts": [] }
      ],
      "required_output_items": [
        { "id": "ch4.required_output.item_01", "text": "最关键的风险", "when_evidence_missing": null, "missing_evidence_reason": null },
        { "id": "ch4.required_output.item_02", "text": "风险严重程度分级", "when_evidence_missing": null, "missing_evidence_reason": null },
        { "id": "ch4.required_output.item_03", "text": "单一投资者 ≥20% 提示", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "未触发或未披露时按 fail-closed 声明。" },
        { "id": "ch4.required_output.item_04", "text": "预警说明（如披露）", "when_evidence_missing": "render_evidence_gap", "missing_evidence_reason": "未披露时声明未披露。" },
        { "id": "ch4.required_output.item_05", "text": "下一轮先验证什么", "when_evidence_missing": null, "missing_evidence_reason": null }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": ["风险分级必须基于披露事实；数据缺失时声明评估受限，不得自创风险项。"],
          "facets_any": [],
          "priority": null
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": ["主动基金重点看：集中度风险、风格漂移风险（用当期行业/前十佐证）。"],
          "facets_any": ["主动权益基金（价值风格）", "主动权益基金（均衡风格）", "主动权益基金（成长风格）"],
          "priority": "core"
        }
      },
      "audit_focus": ["risk", "evidence_anchors"],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    }
  ]
}
```

## 数据口径边界（季报真实存在字段）

| 数据项 | 季报披露 | 抽取实现（snapshot_extraction.py） | 说明 |
|---|---|---|---|
| 净值增长率各阶段行 + ①-③ 超额列 | ✅ §3.2.1 | _extract_performance_rows | 3.2.1 表头签名「阶段/份额净值增长率/业绩比较基准收益率」；行标签精确匹配，禁止假设固定窗口集合；A 类优先 |
| 期末规模/份额 | ✅ | _extract_scale_info | 期末基金资产净值（A 类优先）；禁止把「基金份额净值 X.XXXX 元」当规模 |
| 仓位（权益/债券占比） | ✅ §5.1 | _extract_allocation_rows | 占基金资产/净值比例 |
| 行业配置 | ✅ §5.2 | _extract_industry_rows | 占净值比例 |
| 前十大股票持仓 | ✅ §5.3.1 | _extract_holdings_rows | 名称/公允价值/占净值比例；A 类优先 |
| 份额变动 | ✅ §6 | _extract_share_change | 期初/申购/赎回/期末；A 类优先 |
| 基金经理 | ✅ §4.1 | _extract_fund_manager | 姓名/任职时间；排除「上述/现任/历任」指代词 |
| 固有资金投资本基金 | ✅ §7 | _extract_text_field | 未披露时 fail-closed 声明 |
| 运作分析 | ✅ §4.4 | _extract_text_field | 复述并标注来源 |
| 单一投资者 ≥20% | ✅ §8.1 | _extract_text_field | 未触发/未披露时声明 |
| 持有人数/净值预警 | ✅ §4.6 | _extract_text_field | 如披露 |

**季报缺失（fail-closed 声明，不从年报补）**：全部持仓明细（仅披露前十大）、财务三表（仅披露主要指标）、托管人报告、持有人结构（户数/机构个人）、换手率（累计买入/卖出）、市场展望、五年逐年净值增长率系列（仅年报 §3.2.3）。

**禁止事项**：
- 禁止把滚动窗口值当作日历年度值；「过去五年」等窗口与年报逐年值不可混用。
- 禁止编造季报不存在的数据（缺失项只允许 fail-closed 声明）。
- 禁止遗漏已抽取并落盘的数据（上述表格列出的字段必须呈现）。

## 章节正文结构（对齐 draft 三段式）

每章按「结论要点 / 详细情况 / 证据与出处」三段写作（第 0 章概览为封面页，不沿用三段式）：

### 第 0 章：概览（封面页）
- **一眼看懂**：基金简介 / 这是什么基金 / 当期状态（🟢 表现优异 / 🟡 表现平稳 / 🔴 需要关注）
- **为什么是这个状态**：最主要的依据 / 最该先盯的变量 / 最大的风险
- **下一步怎么验证**：最小验证问题
> 📎 证据：季报[年份]Q[n]§[章节] [内容描述]

### 第 1 章：当期业绩与超额
#### 结论要点
- **各阶段净值表现**（滚动窗口口径）：
- **超额收益性质**：🟢 结构性 / 🟡 部分结构性 / 🔴 阶段性 / ⬜ 数据不足
#### 详细情况
- 各阶段净值增长率表（精确按行标签）+ 同期基准 + ①-③ 超额
- 超额性质判断与依据
> 📎 证据：季报[年份]Q[n]§3.2.1

### 第 2 章：持仓与资产配置
#### 结论要点
- **仓位**：权益 X% / 债券 X%
- **集中度**：前十大合计占净值 X%
- **份额变动**：期初→期末
#### 详细情况
- 资产配置表 / 行业配置表 / 前十大持仓表 / 份额变动表
- **季报缺失项声明**（fail-closed）
> 📎 证据：季报[年份]Q[n]§5.1 / §5.2 / §5.3.1 / §6

### 第 3 章：管理人动作
#### 结论要点
- **运作分析要点**（据 §4.4）：
- **基金经理**：
- **固有资金**：
#### 详细情况
- 运作分析复述（标注来源，不做观点化）
- 基金经理信息、固有资金投资情况
> 📎 证据：季报[年份]Q[n]§4.4 / §4.1 / §7

### 第 4 章：风险与跟踪
#### 结论要点
- **最关键的风险**：
- **风险分级**：高 / 中 / 低 + 依据
- **单一投资者 ≥20%**：
#### 详细情况
- 风险识别与分级（基于披露事实）
- 单一投资者 ≥20% 提示、预警说明
- **季报缺失项声明**（fail-closed）
> 📎 证据：季报[年份]Q[n]§8.1 / §4.6

## 附录 A：数据来源与证据锚点汇总

### 证据锚点格式规范
- **正文引用格式**：`> 📎 证据：季报[年份]Q[n]§[章节] [内容描述]`
- **附录汇总格式**：`季报[年份]Q[n]§[章节]表[编号]行[行号]`
- **示例**：`> 📎 证据：季报2026Q2§3.2.1（过去一年净值增长率 33.28%）`

### 数据来源对照表
| 数据项 | 来源 | 锚点格式 |
|---|---|---|
| 净值增长率各阶段行 | 季报§3.2.1 | 季报[年份]Q[n]§3.2.1表X行Y |
| 业绩比较基准收益率 | 季报§3.2.1 | 同上 |
| 超额收益（①-③） | 季报§3.2.1 | 同上 |
| 期末规模/份额 | 季报§5 或报告期末 | 季报[年份]Q[n]§[章节] |
| 资产配置/仓位 | 季报§5.1 | 季报[年份]Q[n]§5.1 |
| 行业配置 | 季报§5.2 | 季报[年份]Q[n]§5.2 |
| 前十大持仓 | 季报§5.3.1 | 季报[年份]Q[n]§5.3.1 |
| 份额变动 | 季报§6 | 季报[年份]Q[n]§6 |
| 基金经理 | 季报§4.1 | 季报[年份]Q[n]§4.1 |
| 运作分析 | 季报§4.4 | 季报[年份]Q[n]§4.4 |
| 固有资金 | 季报§7 | 季报[年份]Q[n]§7 |
| 单一投资者 ≥20% | 季报§8.1 | 季报[年份]Q[n]§8.1 |

## 附录 B：审计规则速查

| 规则码 | 含义 | 阻断级别 | 本报告适用场景 |
|---|---|---|---|
| P1 | 章节结构不匹配 | 阻断 | 缺少必要章节/报告期占位（如 QNone） |
| P2 | 内容过短（<10字符） | 阻断 | 关键字段为空 |
| P3 | 模板残留 | 可复核 | 数据表格模板标题混入分析正文 |
| E1 | 证据锚点不精确 | 可复核 | 数据来源未标注到具体位置 |
| E2 | 证据与断言不匹配 | 可复核 | 计算结果与原始数据不一致 |
| E3 | 证据完全缺失 | 需重建 | 关键数据无法从季报中找到 |
| C1 | 内容违规（幻觉） | 阻断 | 编造季报中不存在的数字/观点 |
| C2 | 逻辑矛盾 | 阻断 | 结论与数据表矛盾（如超额单调放大与数据不符） |
| C4 | 分析深度不足 | 可复核 | 仅复述数据表未做判断 |
| L1 | 计算错误 | 阻断 | 超额收益计算不闭合 |
| R1 | 检查清单规则应用错误 | 阻断 | 风险分级与披露事实不一致 |

## 输出落盘

- reports/{fund_code}-{year}Q{quarter}-quarterly-snapshot.md（json / markdown / pdf 三格式）
- 章节按 chapter_id 0..4 升序组装输出（概览第 1 章永远在报告最前）。
