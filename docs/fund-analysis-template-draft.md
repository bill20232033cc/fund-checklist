# [基金名称]（[基金代码]）分析报告

**风险警示与免责声明**：*本文由 AI/大模型基于 [基金名称] ([基金代码]) 已公开披露的基金年报、招募说明书、定期报告及其他监管披露文件辅助生成，仅用于个人投资研究与信息交流之目的。因 AI/大模型存在幻觉，本文不可避免地会产生不完全符合年报原文的情况，阅读本文后产生的任何观点需核对原文，使用本文内容所产生的任何直接或间接后果，均由使用者自行承担。*

<!--
TEMPLATE_CONTRACT_MANIFEST_JSON
{
  "schema_version": "typed_chapter_contract.v1",
  "template_id": "fund-analysis-template-typed-v1",
  "source_template_id": "fund-analysis-template-v1",
  "source_path": "docs/fund-analysis-template-draft.md",
  "public_chapter_ids": [
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7
  ],
  "chapters": [
    {
      "chapter_id": 0,
      "title": "投资要点概览",
      "narrative_mode": "封面→动作→验证",
      "must_answer": [
        {
          "id": "ch0.must_answer.item_01",
          "text": "用一句话定义这只基金到底是什么产品。"
        },
        {
          "id": "ch0.must_answer.item_02",
          "text": "给出一个极简基金简介，帮助第一次接触这只基金的读者快速建立产品画像；只保留基金类型、基金经理、管理规模、成立时间中最必要的信息。"
        },
        {
          "id": "ch0.must_answer.item_03",
          "text": "回答当前判断应是值得持有、需要关注还是建议替换。"
        },
        {
          "id": "ch0.must_answer.item_04",
          "text": "回答这只基金当前业绩和运作处在什么状态，但只保留最能支撑当前动作判断的净值表现、超额收益或风险指标。"
        },
        {
          "id": "ch0.must_answer.item_05",
          "text": "回答支撑当前动作的最主要理由，默认压缩成 1 条；只有在第二条判断彼此独立且缺一不可时才允许写第 2 条。"
        },
        {
          "id": "ch0.must_answer.item_06",
          "text": "回答当前最值得盯住的变量是什么；先点出看这类基金时通常最先要看的东西；如果基金还有一个更能决定整份报告判断的特别情况，就把它放到最前面来写。"
        },
        {
          "id": "ch0.must_answer.item_07",
          "text": "回答当前最大的风险是什么，默认只保留一个主要风险。"
        },
        {
          "id": "ch0.must_answer.item_08",
          "text": "回答下一步最小验证问题是什么，默认先写 1 个最关键问题。"
        },
        {
          "id": "ch0.must_answer.item_09",
          "text": "回答什么变化会升级、降级或终止当前动作，优先压缩成 1 个升级阈值和 1 个降级或终止阈值。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch0.must_not_cover.item_01",
          "text": "不把本章写成后续章节的摘要、材料摘抄、按顺序复述，或信息罗列式导读。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_02",
          "text": "不把“基金简介 / 业绩概览 / 风险提示”拆成并列分栏。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_03",
          "text": "不把本章写成优点/缺点清单、投资亮点清单。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_04",
          "text": "不把“最主要的理由”写成多条优点堆砌；默认只保留 1 条。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_05",
          "text": "不把“最大风险”写成并列风险列表；默认只写一个主要风险。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_06",
          "text": "不把“下一步最小验证问题”写成愿望清单；默认先写 1 个。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_07",
          "text": "不把本章拆成“结论要点 / 详细情况 / 证据与出处”三段结构；第 0 章是封面页。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch0.must_not_cover.item_08",
          "text": "不输出“证据与出处”小节。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch0.required_output.item_01",
          "text": "一句话这是什么基金",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_02",
          "text": "基金简介",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_03",
          "text": "当前动作（🟢 值得持有 / 🟡 需要关注 / 🔴 建议替换）",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_04",
          "text": "当前业绩与运作状态",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_05",
          "text": "支撑当前动作的最主要理由",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_06",
          "text": "当前最值得盯住的变量",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_07",
          "text": "当前最大的风险",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_08",
          "text": "下一步最小验证问题",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch0.required_output.item_09",
          "text": "什么变化会升级、降级或终止当前动作",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "把本章当成基金体检封面页，读者应在最短时间内知道“这是什么基金、好不好、该不该继续持有”。",
            "默认写成三层封面：先给“一眼看懂”，再回答“为什么现在是这个动作”，最后回答“下一步怎么验证”。",
            "当前业绩状态要像给朋友的首屏导语，而不是迷你数据摘要。",
            "默认只保留 1 条最主要的理由、1 个主要风险、1 个最关键验证问题和 2 个阈值事件。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金优先回答：跟踪误差多大？费率多少？规模和流动性如何？"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "core"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金优先回答：超额收益是否稳定？基金经理是否靠谱？言行是否一致？"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金优先回答：信用风险如何？久期多长？最大回撤多少？"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "core"
        },
        "enhanced_index": {
          "fund_type": "enhanced_index",
          "statements": [
            "增强基金优先回答：超额收益是否稳定？跟踪误差多大？增强策略是什么？"
          ],
          "facets_any": [
            "指数增强基金"
          ],
          "priority": "core"
        },
        "qdii_fund": {
          "fund_type": "qdii_fund",
          "statements": [
            "QDII基金优先回答：投资哪个市场？汇率风险多大？费率是否合理？"
          ],
          "facets_any": [
            "QDII 基金"
          ],
          "priority": "core"
        },
        "fof_fund": {
          "fund_type": "fof_fund",
          "statements": [
            "FOF基金优先回答：底层基金配置策略是什么？双重收费问题如何？总费率多少？"
          ],
          "facets_any": [
            "FOF 基金"
          ],
          "priority": "core"
        }
      },
      "audit_focus": [
        "final_judgment",
        "chapter_structure"
      ],
      "consumes_chapter_conclusions": [
        7
      ],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 1,
      "title": "这只基金到底是什么产品",
      "narrative_mode": "定义→策略→基准",
      "must_answer": [
        {
          "id": "ch1.must_answer.item_01",
          "text": "用最低认知负担定义这只基金到底是什么产品。"
        },
        {
          "id": "ch1.must_answer.item_02",
          "text": "说明基金的投资目标和投资策略（从招募说明书和年报§2提取）。"
        },
        {
          "id": "ch1.must_answer.item_03",
          "text": "说明基金的业绩基准是什么，为什么选这个基准。"
        },
        {
          "id": "ch1.must_answer.item_04",
          "text": "说明基金的类型分类（按有知有行三维标签：市值×风格×管理方式）。"
        },
        {
          "id": "ch1.must_answer.item_05",
          "text": "回答看这类基金时，通常最先要看什么。"
        },
        {
          "id": "ch1.must_answer.item_06",
          "text": "如果基金有一个不太符合常规、却会直接改变你对“这是什么产品”理解的特别情况，要说明它为什么重要。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch1.must_not_cover.item_01",
          "text": "不展开基金经理选股能力的分析（属于第 3 章）。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch1.must_not_cover.item_02",
          "text": "不展开收益率的详细计算（属于第 2 章）。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch1.must_not_cover.item_03",
          "text": "不分析市场竞争或同业比较（属于横向比较模块，不在本报告范围内）。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch1.required_output.item_01",
          "text": "基金类型与分类标签",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch1.required_output.item_02",
          "text": "投资目标（一句话）",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch1.required_output.item_03",
          "text": "投资策略概述",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch1.required_output.item_04",
          "text": "业绩基准及合理性",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch1.required_output.item_05",
          "text": "看这类基金最先看什么",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch1.required_output.item_06",
          "text": "会改变产品理解的特别情况（如有）",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        }
      ],
      "preferred_lens": {
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金优先回答：跟踪什么指数？指数编制规则是什么？成分股定期调整机制？",
            "lens: 指数基金的核心是“跟踪精度”和“费率”，先回答这两个问题。"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "core"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金优先回答：基金经理的投资哲学是什么？选股标准是什么？仓位管理策略是什么？",
            "lens: 主动基金的核心是“基金经理”，先回答“这个人怎么想、怎么做”。"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金优先回答：久期策略是什么？信用下沉程度如何？是否有转债/股票仓位？",
            "lens: 债券基金的核心是“风险收益定位”，先回答“它到底有多安全”。"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "core"
        },
        "enhanced_index": {
          "fund_type": "enhanced_index",
          "statements": [
            "增强基金优先回答：增强策略是什么（打新/量化/主观）？历史超额收益稳定性如何？跟踪误差多大？",
            "lens: 增强基金的核心是“超额收益的来源和稳定性”，先回答“多出来的收益从哪来”。"
          ],
          "facets_any": [
            "指数增强基金"
          ],
          "priority": "core"
        },
        "qdii_fund": {
          "fund_type": "qdii_fund",
          "statements": [
            "QDII基金优先回答：投资哪个市场/地区？跟踪什么指数？汇率对冲策略是什么？",
            "lens: QDII基金的核心是“跨境投资风险”，先回答“汇率风险和费率”。"
          ],
          "facets_any": [
            "QDII 基金"
          ],
          "priority": "core"
        },
        "fof_fund": {
          "fund_type": "fof_fund",
          "statements": [
            "FOF基金优先回答：资产配置策略是什么？底层基金筛选标准是什么？",
            "lens: FOF基金的核心是“配置能力”，先回答“如何选基金、如何配比例”。"
          ],
          "facets_any": [
            "FOF 基金"
          ],
          "priority": "core"
        }
      },
      "audit_focus": [
        "chapter_structure",
        "evidence_anchors"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 2,
      "title": "R=A+B-C 收益归因",
      "narrative_mode": "拆解→判断→成本",
      "must_answer": [
        {
          "id": "ch2.must_answer.item_01",
          "text": "近 1 年、3 年、5 年的基金净值增长率（R）。"
        },
        {
          "id": "ch2.must_answer.item_02",
          "text": "同期业绩基准收益率（B）。"
        },
        {
          "id": "ch2.must_answer.item_03",
          "text": "计算超额收益（A = R - B）。"
        },
        {
          "id": "ch2.must_answer.item_04",
          "text": "判断超额收益是结构性的还是阶段性的。"
        },
        {
          "id": "ch2.must_answer.item_05",
          "text": "拆解成本 C：管理费 + 托管费 + 销售服务费 + 交易成本（估算）。"
        },
        {
          "id": "ch2.must_answer.item_06",
          "text": "判断超额收益是否为正且稳定、是否覆盖成本。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch2.must_not_cover.item_01",
          "text": "不展开基金经理选股能力的详细归因（属于第 3 章）。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch2.must_not_cover.item_02",
          "text": "不展开市场走势分析（不属于本报告范围）。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch2.must_not_cover.item_03",
          "text": "不做未来收益预测。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch2.required_output.item_01",
          "text": "近 1/3/5 年净值增长率",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 2 章同源已复核净值增长率与业绩基准证据不足时只能输出证据缺口，不得编造近 1/3/5 年收益数值。"
        },
        {
          "id": "ch2.required_output.item_02",
          "text": "近 1/3/5 年业绩基准收益率",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 2 章同源已复核净值增长率与业绩基准证据不足时只能输出证据缺口，不得编造近 1/3/5 年收益数值。"
        },
        {
          "id": "ch2.required_output.item_03",
          "text": "超额收益（A = R - B）及稳定性",
          "when_evidence_missing": "render_minimum_verification_question",
          "missing_evidence_reason": "第 2 章同源已复核 R 与 B 证据不足时只能输出下一步最小验证问题，不得给出 Alpha 或稳定性结论。"
        },
        {
          "id": "ch2.required_output.item_04",
          "text": "超额收益性质判断（结构性 vs 阶段性）",
          "when_evidence_missing": "render_minimum_verification_question",
          "missing_evidence_reason": "第 2 章同源已复核 R 与 B 证据不足时只能输出下一步最小验证问题，不得给出 Alpha 或稳定性结论。"
        },
        {
          "id": "ch2.required_output.item_05",
          "text": "成本拆解（管理费、托管费、交易成本）",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 2 章同源已复核费用与成本证据不足时只能输出证据缺口，不得编造费率、交易成本或成本合理性判断。"
        },
        {
          "id": "ch2.required_output.item_06",
          "text": "成本合理性判断（同类对比）",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 2 章同源已复核费用与成本证据不足时只能输出证据缺口，不得编造费率、交易成本或成本合理性判断。"
        },
        {
          "id": "ch2.required_output.item_07",
          "text": "R=A+B-C 综合评估",
          "when_evidence_missing": "render_minimum_verification_question",
          "missing_evidence_reason": "第 2 章同源已复核 R、B 与 C 证据不足时只能输出下一步最小验证问题，不得输出具体 R=A+B-C 数字闭环。"
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "核心区分：结构性超额（可持续的能力）vs 阶段性超额（风格顺风/运气）。",
            "结构性超额的特征：多年度为正、不同市场环境都为正、超额收益来源可解释。",
            "阶段性超额的特征：集中在某一年、与特定市场风格高度相关、无法解释来源。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金的核心不是超额收益，而是跟踪误差和费率。本章重点回答：跟踪误差多大？费率是否合理？"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "core"
        }
      },
      "audit_focus": [
        "r_abc",
        "evidence_anchors"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": [
        {
          "subcontract_id": "performance",
          "title": "收益表现",
          "requirement_ids": [
            "ch2.must_answer.item_01",
            "ch2.must_answer.item_02",
            "ch2.required_output.item_01",
            "ch2.required_output.item_02"
          ],
          "public_chapter_id": null
        },
        {
          "subcontract_id": "attribution",
          "title": "超额归因",
          "requirement_ids": [
            "ch2.must_answer.item_03",
            "ch2.must_answer.item_04",
            "ch2.required_output.item_03",
            "ch2.required_output.item_04"
          ],
          "public_chapter_id": null
        },
        {
          "subcontract_id": "cost",
          "title": "成本拆解",
          "requirement_ids": [
            "ch2.must_answer.item_05",
            "ch2.must_answer.item_06",
            "ch2.required_output.item_05",
            "ch2.required_output.item_06",
            "ch2.required_output.item_07"
          ],
          "public_chapter_id": null
        }
      ]
    },
    {
      "chapter_id": 3,
      "title": "基金经理画像与言行一致性",
      "narrative_mode": "画像→验证→判断",
      "must_answer": [
        {
          "id": "ch3.must_answer.item_01",
          "text": "基金经理的基本信息（从业年限、管理本基金时间、管理规模）。"
        },
        {
          "id": "ch3.must_answer.item_02",
          "text": "基金经理宣称的投资策略和风格（从年报§4提取）。"
        },
        {
          "id": "ch3.must_answer.item_03",
          "text": "基金经理实际的投资行为（从年报§8提取：行业配置、持仓集中度、换手率）。"
        },
        {
          "id": "ch3.must_answer.item_04",
          "text": "言行一致性判断：说的和做的一样吗？主动基金如缺少已复核的换手率或风格变化证据，不得据此判断言行一致。"
        },
        {
          "id": "ch3.must_answer.item_05",
          "text": "风格稳定性判断：跨期风格是否漂移？主动基金必须基于已复核的换手率或风格变化证据。"
        },
        {
          "id": "ch3.must_answer.item_06",
          "text": "利益一致性判断：基金经理是否持有本基金？"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch3.must_not_cover.item_01",
          "text": "不做基金经理性格或人品的主观评价。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch3.must_not_cover.item_02",
          "text": "不猜测基金经理的动机。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch3.must_not_cover.item_03",
          "text": "不展开选股能力的量化分析（属于第 2 章超额收益范畴）。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch3.must_not_cover.item_04",
          "text": "不在换手率或风格变化证据缺失、不可用、未复核时，推断主动基金风格稳定、风格一致或言行一致。",
          "applies_when": {
            "predicate_id": "ch3.evidence.manager_behavior_style_unreviewed",
            "requirement_ids": [
              "ch3.requirement.actual_behavior_reviewed"
            ],
            "required_statuses": [
              "missing",
              "unavailable",
              "unreviewed"
            ],
            "description": "主动基金第 3 章缺少已复核换手率或跨期风格变化证据时，禁止正向一致性推断。"
          },
          "allowed_contexts": [
            "required_label",
            "evidence_gap_statement",
            "quote",
            "anchor_caption"
          ]
        }
      ],
      "required_output_items": [
        {
          "id": "ch3.required_output.item_01",
          "text": "基金经理基本信息",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 3 章基金经理基本信息缺少已复核证据时只能输出证据缺口，不得进入未经证据支持的基金经理画像判断。"
        },
        {
          "id": "ch3.required_output.item_02",
          "text": "宣称的投资策略（§4）",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 3 章策略、实际行为、言行一致性和风格稳定性在缺少已复核证据时只能输出证据缺口。"
        },
        {
          "id": "ch3.required_output.item_03",
          "text": "实际投资行为（§8）",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 3 章策略、实际行为、言行一致性和风格稳定性在缺少已复核证据时只能输出证据缺口。"
        },
        {
          "id": "ch3.required_output.item_04",
          "text": "言行一致性判断",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 3 章策略、实际行为、言行一致性和风格稳定性在缺少已复核证据时只能输出证据缺口。"
        },
        {
          "id": "ch3.required_output.item_05",
          "text": "风格稳定性判断",
          "when_evidence_missing": "render_evidence_gap",
          "missing_evidence_reason": "第 3 章策略、实际行为、言行一致性和风格稳定性在缺少已复核证据时只能输出证据缺口。"
        },
        {
          "id": "ch3.required_output.item_06",
          "text": "利益一致性判断",
          "when_evidence_missing": "render_minimum_verification_question",
          "missing_evidence_reason": "第 3 章利益一致性证据缺失时只能输出下一步最小验证问题。"
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "核心区分：利益一致 vs 利益冲突。",
            "✅ 一致信号：持有本基金、管理年限长、风格稳定、言行一致。",
            "⚠️ 冲突信号：不持有本基金、频繁变更、风格漂移、言行不一致。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金对基金经理依赖度低，重点回答：跟踪误差是否稳定？规模是否稳定？",
            "基金经理变更对指数基金影响较小，除非导致费率调整或清盘风险。"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "low"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金的核心是“基金经理”，本章是最关键章节。",
            "重点回答：这个人怎么想？怎么做？说和做一样吗？利益绑定了吗？"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金重点回答：久期管理是否稳定？信用下沉程度是否与宣称一致？"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "high"
        },
        "enhanced_index": {
          "fund_type": "enhanced_index",
          "statements": [
            "增强基金重点回答：增强策略是否稳定？基金经理是否过度偏离指数？"
          ],
          "facets_any": [
            "指数增强基金"
          ],
          "priority": "high"
        },
        "qdii_fund": {
          "fund_type": "qdii_fund",
          "statements": [
            "QDII基金重点回答：汇率风险管理是否稳定？投资地区配置是否与宣称一致？"
          ],
          "facets_any": [
            "QDII 基金"
          ],
          "priority": "high"
        },
        "fof_fund": {
          "fund_type": "fof_fund",
          "statements": [
            "FOF基金重点回答：底层基金配置是否稳定？是否频繁更换子基金？"
          ],
          "facets_any": [
            "FOF 基金"
          ],
          "priority": "high"
        }
      },
      "audit_focus": [
        "manager_consistency",
        "evidence_anchors"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 4,
      "title": "投资者获得感",
      "narrative_mode": "数据→对比→判断",
      "must_answer": [
        {
          "id": "ch4.must_answer.item_01",
          "text": "基金产品收益（净值增长率）。"
        },
        {
          "id": "ch4.must_answer.item_02",
          "text": "投资者实际收益（盈利投资者占比、加权平均收益率）。"
        },
        {
          "id": "ch4.must_answer.item_03",
          "text": "行为损益 = 投资者实际收益 - 基金产品收益。"
        },
        {
          "id": "ch4.must_answer.item_04",
          "text": "份额变动趋势（资金是在追涨还是在抄底？）。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch4.must_not_cover.item_01",
          "text": "不分析具体投资者的交易行为。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch4.must_not_cover.item_02",
          "text": "不做未来投资者行为预测。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch4.required_output.item_01",
          "text": "基金产品收益 vs 投资者实际收益",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch4.required_output.item_02",
          "text": "盈利投资者占比",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch4.required_output.item_03",
          "text": "行为损益估算",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch4.required_output.item_04",
          "text": "份额变动趋势",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "核心公式：投资者回报 = 基金产品收益 × 基民资金进出结构。",
            "即使基金好，如果投资者追涨杀跌，实际回报也会大打折扣。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金投资者行为模式：通常在市场大跌时赎回（恐慌）、大涨时申购（追涨）。",
            "重点回答：投资者是否在低点逃离？行为损益有多大？"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "high"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金投资者行为模式：受业绩排名影响大，容易追逐短期冠军。",
            "重点回答：投资者是否在业绩高点追入？是否在业绩低谷逃离？"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金投资者行为模式：通常较稳定，但在信用风险事件时可能集中赎回。",
            "重点回答：是否有大额申赎波动？是否与债券市场波动相关？"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "medium"
        }
      },
      "audit_focus": [
        "investor_experience",
        "evidence_anchors"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 5,
      "title": "当前阶段与关键变化",
      "narrative_mode": "变化→阶段→判断",
      "must_answer": [
        {
          "id": "ch5.must_answer.item_01",
          "text": "当前阶段是什么（建仓期/稳定期/膨胀期/萎缩期/转型期）。"
        },
        {
          "id": "ch5.must_answer.item_02",
          "text": "相比上一期或历史，过去一年最关键的 1-3 个变化是什么（基金经理、规模、策略、费率、仓位或大额申赎）。"
        },
        {
          "id": "ch5.must_answer.item_03",
          "text": "这些变化是否影响原始投资假设或第 1-4 章判断。"
        },
        {
          "id": "ch5.must_answer.item_04",
          "text": "为什么偏偏是现在需要关注这只基金。"
        },
        {
          "id": "ch5.must_answer.item_05",
          "text": "下一步最小验证问题是什么。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch5.must_not_cover.item_01",
          "text": "不做市场整体走势预测。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch5.must_not_cover.item_02",
          "text": "不罗列所有变化，只保留最关键的 1-3 个。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch5.must_not_cover.item_03",
          "text": "不给最终持有/替换结论。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch5.must_not_cover.item_04",
          "text": "不展开风险清单；变化事实只有转译为风险或否决项时才进入第 6 章。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch5.must_not_cover.item_05",
          "text": "不重复基金经理长期画像或成本收益总评。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch5.required_output.item_01",
          "text": "过去一年最关键的变化（1-3 个）",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch5.required_output.item_02",
          "text": "基金当前所处阶段",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch5.required_output.item_03",
          "text": "变化是否改变前文判断",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch5.required_output.item_04",
          "text": "接下来最该跟踪的变量",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "核心区分：结构性变化 vs 阶段性变化。",
            "结构性变化：基金经理变更、策略调整、费率调整、清盘风险。",
            "阶段性变化：规模波动、市场环境变化、短期业绩波动。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金重点跟踪：规模变化（影响流动性）、跟踪误差变化、费率调整。",
            "基金经理变更影响较小，除非导致清盘风险。"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "high"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金重点跟踪：基金经理变更（最关键）、规模剧变（影响策略执行）、风格漂移。"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金重点跟踪：久期调整、信用下沉程度变化、规模剧变（影响配置能力）。"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "high"
        },
        "enhanced_index": {
          "fund_type": "enhanced_index",
          "statements": [
            "增强基金重点跟踪：增强策略调整、跟踪误差变化、基金经理变更。"
          ],
          "facets_any": [
            "指数增强基金"
          ],
          "priority": "core"
        },
        "qdii_fund": {
          "fund_type": "qdii_fund",
          "statements": [
            "QDII基金重点跟踪：汇率政策变化、投资地区配置变化、跨境政策风险。"
          ],
          "facets_any": [
            "QDII 基金"
          ],
          "priority": "high"
        },
        "fof_fund": {
          "fund_type": "fof_fund",
          "statements": [
            "FOF基金重点跟踪：底层基金更换、配置策略调整、双重费率变化。"
          ],
          "facets_any": [
            "FOF 基金"
          ],
          "priority": "high"
        }
      },
      "audit_focus": [
        "current_stage",
        "evidence_anchors"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 6,
      "title": "核心风险与否决项",
      "narrative_mode": "风险→否决→跟踪",
      "must_answer": [
        {
          "id": "ch6.must_answer.item_01",
          "text": "核心风险是什么，其中哪些是结构性风险、哪些是阶段性风险。"
        },
        {
          "id": "ch6.must_answer.item_02",
          "text": "最关键的风险或否决项（1-2 个最致命的风险）。"
        },
        {
          "id": "ch6.must_answer.item_03",
          "text": "为什么足以改变结论——这个风险推翻了哪条核心假设。"
        },
        {
          "id": "ch6.must_answer.item_04",
          "text": "是否触发一票否决，还是仍可跟踪。"
        },
        {
          "id": "ch6.must_answer.item_05",
          "text": "压力测试结论是什么。"
        },
        {
          "id": "ch6.must_answer.item_06",
          "text": "哪个信息缺口最可能改变最终判断，下一轮先验证什么。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch6.must_not_cover.item_01",
          "text": "不把本章写成所有可能风险的罗列。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch6.must_not_cover.item_02",
          "text": "不把“最大风险”写成并列列表；默认只写 1 个最致命的。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch6.must_not_cover.item_03",
          "text": "不做风险发生概率的定量预测。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch6.must_not_cover.item_04",
          "text": "不复述当前阶段事实，除非明确转译为风险、压力测试或否决项。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch6.must_not_cover.item_05",
          "text": "不给最终持有/替换结论。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch6.must_not_cover.item_06",
          "text": "不预测收益或市场走势。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch6.required_output.item_01",
          "text": "最关键的风险或否决项",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch6.required_output.item_02",
          "text": "为什么足以改变结论",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch6.required_output.item_03",
          "text": "否决 vs 跟踪判断",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch6.required_output.item_04",
          "text": "下一轮先验证什么",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "核心区分：否决项（一票否决）vs 跟踪项（持续关注）vs 一般风险（正常承受）。",
            "否决项：清盘风险、基金经理离职、严重风格漂移、费率远超同类。",
            "跟踪项：规模波动、换手率变化、集中度变化。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金否决项：清盘风险（规模<5000万）、跟踪误差>3%、费率远超同类。",
            "指数基金跟踪项：规模变化、流动性变化、成分股调整。",
            "压力测试默认阈值：-30%（正常）/ -50%（极端）/ -70%（历史最差）。"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "core"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金否决项：基金经理离职、严重风格漂移、清盘风险、费率>2%/年。",
            "主动基金跟踪项：规模剧变、换手率异常、集中度变化。",
            "压力测试默认阈值：-25%（正常）/ -45%（极端）/ -65%（历史最差）。"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金否决项：信用风险事件、清盘风险、久期严重偏离宣称。",
            "债券基金跟踪项：久期变化、信用下沉程度、规模变化。",
            "压力测试默认阈值：-5%（正常）/ -10%（极端）/ -20%（历史最差）。"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "core"
        },
        "enhanced_index": {
          "fund_type": "enhanced_index",
          "statements": [
            "增强基金否决项：清盘风险、跟踪误差>4%、增强策略失效（连续2年负超额）。",
            "增强基金跟踪项：超额收益稳定性、规模变化、基金经理变更。",
            "压力测试默认阈值：-25%（正常）/ -45%（极端）/ -60%（历史最差）。"
          ],
          "facets_any": [
            "指数增强基金"
          ],
          "priority": "core"
        },
        "qdii_fund": {
          "fund_type": "qdii_fund",
          "statements": [
            "QDII基金否决项：清盘风险、汇率严重不利、跨境政策限制、费率>2.5%/年。",
            "QDII基金跟踪项：汇率变化、投资地区配置、流动性变化。",
            "压力测试默认阈值：-35%（正常）/ -55%（极端）/ -75%（历史最差）。"
          ],
          "facets_any": [
            "QDII 基金"
          ],
          "priority": "core"
        },
        "fof_fund": {
          "fund_type": "fof_fund",
          "statements": [
            "FOF基金否决项：清盘风险、双重费率过高（>2%/年）、底层基金频繁更换。",
            "FOF基金跟踪项：配置策略变化、底层基金表现、总费率变化。",
            "压力测试默认阈值：-20%（正常）/ -40%（极端）/ -55%（历史最差）。"
          ],
          "facets_any": [
            "FOF 基金"
          ],
          "priority": "core"
        }
      },
      "audit_focus": [
        "risk",
        "evidence_anchors"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    },
    {
      "chapter_id": 7,
      "title": "是否值得持有——最终判断",
      "narrative_mode": "判断→依据→验证",
      "must_answer": [
        {
          "id": "ch7.must_answer.item_01",
          "text": "三选一明确立场：值得持有、需要关注、建议替换。"
        },
        {
          "id": "ch7.must_answer.item_02",
          "text": "为什么现在更适合这个判断，而不是另外两个。"
        },
        {
          "id": "ch7.must_answer.item_03",
          "text": "当前最容易看错的地方是什么。"
        },
        {
          "id": "ch7.must_answer.item_04",
          "text": "下一轮先核实什么（1-2 个最小验证问题）。"
        },
        {
          "id": "ch7.must_answer.item_05",
          "text": "什么变化会升级、降级或终止当前判断。"
        }
      ],
      "must_not_cover": [
        {
          "id": "ch7.must_not_cover.item_01",
          "text": "不输出具体的买入金额、卖出时机或仓位比例。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch7.must_not_cover.item_02",
          "text": "不把本章写成前 6 章的摘要复述。",
          "applies_when": null,
          "allowed_contexts": []
        },
        {
          "id": "ch7.must_not_cover.item_03",
          "text": "不把“为什么”写成多条理由堆砌；默认只保留 1-2 条核心依据。",
          "applies_when": null,
          "allowed_contexts": []
        }
      ],
      "required_output_items": [
        {
          "id": "ch7.required_output.item_01",
          "text": "最终判断（🟢 值得持有 / 🟡 需要关注 / 🔴 建议替换）",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch7.required_output.item_02",
          "text": "支撑判断的核心依据（1-2 条）",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch7.required_output.item_03",
          "text": "当前最容易看错的地方",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch7.required_output.item_04",
          "text": "下一轮最小验证计划",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        },
        {
          "id": "ch7.required_output.item_05",
          "text": "危级/降级阈值",
          "when_evidence_missing": null,
          "missing_evidence_reason": null
        }
      ],
      "preferred_lens": {
        "default": {
          "fund_type": "default",
          "statements": [
            "三选一明确立场：值得持有、需要关注、建议替换。",
            "判断依据优先级：否决项 > 核心优势 > 一般特征。"
          ],
          "facets_any": [],
          "priority": null
        },
        "index_fund": {
          "fund_type": "index_fund",
          "statements": [
            "指数基金判断依据优先级：费率 > 跟踪误差 > 规模/流动性 > 基金公司。",
            "“值得持有”的典型条件：费率低于同类中位数、跟踪误差<1%、规模>2亿。"
          ],
          "facets_any": [
            "宽基指数基金",
            "行业/主题指数基金",
            "策略指数基金"
          ],
          "priority": "core"
        },
        "active_fund": {
          "fund_type": "active_fund",
          "statements": [
            "主动基金判断依据优先级：基金经理 > 超额收益稳定性 > 言行一致性 > 费率。",
            "“值得持有”的典型条件：基金经理任职>3年、超额收益稳定为正、言行一致、持有本基金。"
          ],
          "facets_any": [
            "主动权益基金（价值风格）",
            "主动权益基金（均衡风格）",
            "主动权益基金（成长风格）"
          ],
          "priority": "core"
        },
        "bond_fund": {
          "fund_type": "bond_fund",
          "statements": [
            "债券基金判断依据优先级：信用风险 > 久期稳定性 > 最大回撤 > 费率。",
            "“值得持有”的典型条件：无信用风险事件、久期稳定、最大回撤可控、费率合理。"
          ],
          "facets_any": [
            "纯债基金",
            "二级债基/混合债基",
            "偏债混合基金"
          ],
          "priority": "core"
        },
        "enhanced_index": {
          "fund_type": "enhanced_index",
          "statements": [
            "增强基金判断依据优先级：超额收益稳定性 > 跟踪误差 > 费率 > 基金经理。",
            "“值得持有”的典型条件：连续3年正超额、跟踪误差<2%、费率合理。"
          ],
          "facets_any": [
            "指数增强基金"
          ],
          "priority": "core"
        },
        "qdii_fund": {
          "fund_type": "qdii_fund",
          "statements": [
            "QDII基金判断依据优先级：费率 > 跟踪误差 > 汇率风险 > 规模/流动性。",
            "“值得持有”的典型条件：费率合理、跟踪误差可控、汇率风险可承受、规模稳定。"
          ],
          "facets_any": [
            "QDII 基金"
          ],
          "priority": "core"
        },
        "fof_fund": {
          "fund_type": "fof_fund",
          "statements": [
            "FOF基金判断依据优先级：配置策略 > 总费率 > 底层基金质量 > 基金经理。",
            "“值得持有”的典型条件：配置策略清晰、总费率<1.5%、底层基金质量稳定。"
          ],
          "facets_any": [
            "FOF 基金"
          ],
          "priority": "core"
        }
      },
      "audit_focus": [
        "final_judgment",
        "risk"
      ],
      "consumes_chapter_conclusions": [],
      "independent_action_source": false,
      "internal_subcontracts": []
    }
  ]
}
END_TEMPLATE_CONTRACT_MANIFEST_JSON
-->

<!--
REPORT_GOAL
在公开信息范围内，快速重建基金产品全貌，并给出"值得持有 / 需要关注 / 建议替换"的初步判断框架。
核心问题：这只基金到底是什么产品？钱是怎么赚到的？基金经理靠不靠谱？投资者真的赚到钱了吗？现在最大的风险是什么？
END_REPORT_GOAL
-->
<!--
AUDIENCE_PROFILE
默认读者是普通基金投资者，具备基本投资常识，但不一定是金融专业背景。
偏好：关键指标 + 一句话判断 + 红黄绿灯信号，而非长篇大论的专业分析。
不偏好：术语堆砌、教学式解释、模糊的"基金不错但还有风险"式平衡总结。
END_AUDIENCE_PROFILE
-->
<!--
FUND_FACET_CATALOG
fund_type_candidates:
  - 宽基指数基金
  - 行业/主题指数基金
  - 策略指数基金（红利/低波/价值/质量）
  - 指数增强基金
  - 主动权益基金（价值风格）
  - 主动权益基金（均衡风格）
  - 主动权益基金（成长风格）
  - 纯债基金
  - 二级债基/混合债基
  - 偏债混合基金
  - QDII 基金
  - FOF 基金
constraint_candidates:
  - 高费率（管理费 > 1.2%）
  - 高换手率（> 500%）
  - 高集中度（前十大 > 70%）
  - 规模过小（< 5000 万，清盘风险）
  - 规模过大（> 100 亿主动 / > 500 亿指数）
  - 新基金（< 3 年，缺乏历史数据）
  - 基金经理频繁变更
  - 风格漂移风险
  - 行业集中风险（行业 ETF 前三大 > 60%）
  - 跟踪误差过大（指数基金 > 2%）
  - 港股/A股比例波动
peer_group_definition:
  说明: "同类"指用于对比的参照组，决定费率、换手率、集中度等指标的中位数计算口径
  口径选项:
    - 证监会分类：按证监会《公开募集证券投资基金运作管理办法》分类（如"股票型基金"、"混合型基金"）
    - 投资风格分类：按晨星/天天基金投资风格箱分类（如"大盘价值"、"中盘成长"）
    - 业绩基准分类：按业绩基准构成分类（如"沪深300基准"、"中证500基准"）
    - 自定义分类：按分析需要自定义（如"宽基指数基金"、"行业ETF"）
  默认口径: 投资风格分类（兼顾投资特征和可比性）
  示例:
    - 沪深300指数基金的同类 = 所有沪深300指数基金（不含增强）
    - 大盘价值主动基金的同类 = 所有大盘价值风格主动权益基金
    - 纯债基金的同类 = 所有纯债基金（不含二级债基）
END_FUND_FACET_CATALOG
-->
<!--
报告目标
1) 本报告用于基金持有/买入前的快速体检，不是深度研究报告。
2) 本报告要在尽量短的阅读时间内，帮助投资者回答三个核心问题：
  - 这只基金到底是什么产品，投资策略是什么，钱是怎么赚到的。
  - 基于公开披露，这只基金最有吸引力的地方是什么、最值得警惕或否决的地方是什么。
  - 基于当前公开披露，它是否值得持有或买入；如果值得，最该盯住什么变量；如果需要警惕，主要风险是什么。
-->
<!--
非目标
1) 不输出目标价、买卖建议、仓位比例，不把本报告写成投资决策执行文件。
2) 不把"好基金"直接等同于"现在应该买入"；买入时机由市场温度决定，不在本报告范围内。
3) 不做超出公开披露和可核查信息的因果推断或基金经理动机猜测。
4) 不以信息罗列完整为目标机械堆砌数据；凡不能服务"理解产品本质、识别投资吸引力与主要风险、判断是否值得持有"的内容，应降级、压缩或删除。
5) 不用未来目标替代当前事实；涉及基金经理展望或市场判断时，仅复述年报披露并明确其前瞻性属性。
-->
<!--
写作说明
1) 本模板保留了大量"小节标题/清单项"，用于防漏项与口径对齐；写作时只写年报/招募说明书能支撑的内容。
2) 对非条件项若基金未披露/不适用：可写'未披露/不适用'，并用【占位符】补齐；但凡注释明确标注'条件项（可选）…必须删除（不输出）'的条目，若未检索到披露则必须整段删除。
3) 默认章节应包含"结论要点 / 详细情况 / 证据与出处"三段结构；第 0 章和第 8 章不沿用这套三段结构。
4) 模板中的 HTML 注释为非输出提示：
  - 若注释标注"条件项（可选）…必须删除（不输出）"，则未检索到披露时必须删除。
  - 其他注释仅为提醒，不输出到正文。
5) 证据锚点格式统一：
  - 正文引用格式：> 📎 证据：年报§[章节] [内容描述]
  - 附录汇总格式：年报[年份]§[章节]表[编号]行[行号]
  - 示例：> 📎 证据：年报2024§3表2行5（净值增长率）
-->

---

## 第 0 章：投资要点概览

<!--
CHAPTER_GOAL
基于后续章节的结构化输入，把整份报告压缩成一页买方初筛封面：先让读者一眼知道"这是什么基金、好不好、现在该做什么"，再快速交代为什么当前是这个判断、基金当前处在什么状态、最该盯住哪个变量、最大风险是什么，以及下一步最小验证问题是什么。核心不是摘要回填，而是把这些输入收成一个可快速判断是否继续花时间的前台入口。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 0
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 一眼看懂
- **基金简介**：[基金类型] | [基金经理] | [管理规模] | [成立时间]
- **这是什么基金**：
- **现在该做什么**：🟢 值得持有 / 🟡 需要关注 / 🔴 建议替换

### 为什么现在是这个动作
- **最主要的理由**：
- **基金现在大致处在什么状态**：
- **最该先盯哪个变量**：
- **现在最大的风险是什么**：

### 下一步怎么验证
- **下一步最该先验证什么**：
- **什么变化会改变当前动作**：

---

## 第 1 章：这只基金到底是什么产品

<!--
CHAPTER_GOAL
用最低认知负担定义基金到底是什么产品。回答"这只基金买的是什么、怎么赚钱、跟什么比"。
这是分析的起点——不理解产品本质，后续所有判断都建立在沙滩上。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 1
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **基金类型与标签**：
- **投资目标（一句话）**：
- **投资策略概述**：
- **业绩基准及合理性**：
- **看这类基金最先看什么**：
- **会改变产品理解的特别情况**（如有）：

### 详细情况

#### 基金基本信息
| 项目 | 信息 |
|------|------|
| 基金全称 | |
| 基金类型 | |
| 成立日期 | |
| 基金规模 | |
| 基金经理 | |
| 基金公司 | |
> 📎 证据：年报§2 基金简介

#### 投资目标与策略
- **投资目标**：
- **投资范围**：
- **投资策略**：
> 📎 证据：招募说明书"投资目标"与"投资策略"章节

#### 业绩基准
- **基准名称**：
- **基准构成**：
- **基准合理性判断**：🟢 合理 / 🟡 勉强合理 / 🔴 不合理
  - 判断理由：
> 📎 证据：招募说明书"业绩比较基准"章节

<!--
ITEM_RULE
mode: conditional
item: 指数编制规则与成分股
when: 仅对指数基金（含指数增强）输出
facets_any: [宽基指数基金, 行业/主题指数基金, 策略指数基金, 指数增强基金]
END_ITEM_RULE
-->
#### 指数编制规则与成分股（仅指数基金）
- **跟踪指数**：[指数名称]
- **指数编制规则**：
  - 选样方法：
  - 加权方式：
  - 调整频率：
- **前十大成分股**：
  | 序号 | 股票代码 | 股票名称 | 权重 |
  |------|---------|---------|------|
  | 1 | | | |
  | 2 | | | |
  | ... | | | |
- **行业分布**：
  | 行业 | 权重 |
  |------|------|
  | | |
> 📎 证据：指数公司官网 + 年报§8投资组合报告

<!--
ITEM_RULE
mode: conditional
item: 基金经理投资哲学
when: 仅对主动基金输出
facets_any: [主动权益基金（价值风格）, 主动权益基金（均衡风格）, 主动权益基金（成长风格）]
END_ITEM_RULE
-->
#### 基金经理投资哲学（仅主动基金）
- **投资哲学**：[从年报§4、访谈、公开演讲提取]
- **选股标准**：
- **卖出标准**：
- **仓位管理策略**：
- **风险控制方法**：
> 📎 证据：年报§4管理人报告 + 公开访谈（如有）

### 证据与出处
- [列出本章所有关键数据的来源锚点]

---

## 第 2 章：R = A + B - C 收益归因

<!--
CHAPTER_GOAL
用 R=A+B-C 框架拆解基金的收益来源，回答"这只基金的钱是怎么赚到的"。
核心：投资者收益 = Alpha（超额收益）+ Beta（市场收益）- Cost（成本）。
关键区分：结构性超额收益 vs 阶段性超额收益。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 2
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **近 1/3/5 年收益表现**：
- **超额收益（Alpha）性质**：🟢 结构性（可持续）/ 🟡 部分结构性 / 🔴 阶段性（不可持续）/ ⬜ 不适用（指数基金）
- **成本（Cost）是否合理**：
- **R=A+B-C 综合评估**：

### 详细情况

#### B — 市场收益（Beta）
- 业绩基准：[基准名称]
- 近 1 年基准收益率：
- 近 3 年基准收益率：
- 近 5 年基准收益率：
> 📎 证据：年报§3 主要财务指标

#### A — 超额收益（Alpha）

<!--
ITEM_RULE
mode: conditional
item: 超额收益分年度拆解
when: 对主动基金和指数增强基金输出；纯指数基金跳过此项
facets_any: [主动权益基金（价值风格）, 主动权益基金（均衡风格）, 主动权益基金（成长风格）, 指数增强基金]
END_ITEM_RULE
-->
| 年度 | 净值增长率 R | 基准收益率 B | 超额收益 A | 判断 |
|------|-------------|-------------|-----------|------|
| 2025 | | | | 🟢/🔴 |
| 2024 | | | | 🟢/🔴 |
| 2023 | | | | 🟢/🔴 |
| 2022 | | | | 🟢/🔴 |
| 2021 | | | | 🟢/🔴 |

- **超额收益稳定性**：[X/5 年为正]
- **超额收益性质判断**：
  - [结构性依据：...]
  - [阶段性风险：...]
> 📎 证据：计算 A=R-B 输入:年报§3表2

<!--
ITEM_RULE
mode: conditional
item: 跟踪误差分析
when: 仅对指数基金（含指数增强）输出
facets_any: [宽基指数基金, 行业/主题指数基金, 策略指数基金, 指数增强基金]
END_ITEM_RULE
-->
#### 跟踪误差分析（仅指数基金）
| 指标 | 数值 | 同类中位数 | 判定 |
|------|------|-----------|------|
| 跟踪误差（近1年） | X.XX% | X.XX% | 🟢/🟡/🔴 |
| 跟踪误差（近3年） | X.XX% | X.XX% | 🟢/🟡/🔴 |
| 信息比率 | X.XX | X.XX | 🟢/🟡/🔴 |
| 日均偏离度 | X.XX% | — | — |

- **跟踪误差判断**：
  - 🟢 < 1%：跟踪精度优秀
  - 🟡 1%-2%：跟踪精度一般
  - 🔴 > 2%：跟踪精度较差，需关注
> 📎 证据：年报§3主要财务指标 + 年报§8投资组合报告

#### C — 成本侵蚀
| 费用类型 | 费率 | 同类中位数 | 判定 |
|---------|------|-----------|------|
| 管理费 | X.XX%/年 | X.XX%/年 | 🟢/🟡/🔴 |
| 托管费 | X.XX%/年 | X.XX%/年 | 🟢/🟡/🔴 |
| 销售服务费 | X.XX%/年 | — | — |
| **显性成本小计** | **X.XX%/年** | | |
| 换手率 | XXX% | XXX% | 🟢/🟡/🔴 |
| 隐性交易成本（估算） | X.XX%/年 | — | — |
| **总成本 C** | **X.XX%/年** | | |

> 📎 证据：管理费/托管费来源:招募说明书第X页；换手率来源:年报§8投资组合报告

#### R = A + B - C 综合评估
| 指标 | 近 1 年 | 近 3 年 | 近 5 年 |
|------|--------|--------|--------|
| R（净值增长率） | | | |
| B（基准收益率） | | | |
| A（超额收益） | | | |
| C（总成本） | | | |
| A - C（净超额） | | | |

**一句话判断**：[这只基金的超额收益能否覆盖成本？净超额收益是多少？]

### 证据与出处
- [列出本章所有关键数据的来源锚点]

---

## 第 3 章：基金经理画像与言行一致性

<!--
CHAPTER_GOAL
回答"基金经理靠不靠谱"。
通过年报§4（说）和年报§8（做）的交叉验证，判断基金经理的投资策略是否清晰、言行是否一致、风格是否稳定。
核心区分：利益一致 vs 利益冲突。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 3
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **基金经理画像**：
- **言行一致性**：🟢 一致 / 🟡 部分一致 / 🔴 不一致
- **风格稳定性**：🟢 稳定 / 🟡 轻微漂移 / 🔴 明显漂移
- **利益一致性**：🟢 持有本基金 / 🔴 未持有

### 详细情况

#### 基金经理基本信息
| 项目 | 信息 |
|------|------|
| 姓名 | |
| 从业年限 | X 年 |
| 管理本基金时间 | X 年（自 XXXX-XX 起） |
| 管理总规模 | X 亿 |
| 是否持有本基金 | 🟢 是（X 万份）/ 🔴 否 |
| 历史管理基金数量 | X 只 |
> 📎 证据：年报§9 基金份额持有人情况 + 天天基金

#### 投资策略与风格（§4 管理人报告 — "说"）
- 宣称的投资策略：
- 宣称的风格定位：
- 对后市的看法（仅复述年报原文，标注为前瞻性表述）：
> 📎 证据：年报§4 管理人报告

#### 实际投资行为（§8 投资组合报告 — "做"）
| 指标 | 本期 | 上期 | 变化 |
|------|------|------|------|
| 股票仓位 | X% | X% | — |
| 前十大重仓集中度 | X% | X% | — |
| 第一大重仓股 | [名称] [X%] | [名称] [X%] | 变化/不变 |
| 前三大行业 | [行业1/2/3] | [行业1/2/3] | 变化/不变 |
| 换手率 | X% | X% | — |
> 📎 证据：年报§8 投资组合报告

#### 言行一致性检验
| 检验维度 | 宣称（§4） | 实际（§8） | 判定 |
|---------|-----------|-----------|------|
| 投资风格 | | | 🟢/🟡/🔴 |
| 行业偏好 | | | 🟢/🟡/🔴 |
| 仓位管理 | | | 🟢/🟡/🔴 |
| 换手水平 | | | 🟢/🟡/🔴 |

### 证据与出处
- [列出本章所有关键数据的来源锚点]

---

## 第 4 章：投资者获得感

<!--
CHAPTER_GOAL
回答"买了这只基金的人真的赚到钱了吗"。
核心公式：投资者回报 = 基金产品收益 × 基民资金进出结构。
即使基金好，如果投资者追涨杀跌，实际回报也会大打折扣。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 4
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **投资者获得感**：🟢 大部分人赚到钱 / 🟡 体验一般 / 🔴 大部分人亏钱
- **行为损益**：投资者实际收益比基金收益低约 X%

### 详细情况

#### 产品收益 vs 投资者收益
| 指标 | 近 1 年 | 近 3 年 |
|------|--------|--------|
| 基金净值增长率 | X% | X% |
| 加权平均投资者收益率 | X% | X% |
| **行为损益** | **X%** | **X%** |
| 盈利投资者占比 | X% | X% |
> 📎 证据：年报§3 主要财务指标（2026 新规要求披露）

#### 份额变动趋势
| 时期 | 期末份额 | 期间申购 | 期间赎回 | 净变动 | 判断 |
|------|---------|---------|---------|--------|------|
| 本期 | | | | | 追涨/抄底/正常 |
| 上期 | | | | | |
> 📎 证据：年报§10 份额变动

**资金流向判断**：[资金是在净值高点大量流入（追涨信号），还是在净值低点流入（抄底信号）？]

### 证据与出处
- [列出本章所有关键数据的来源锚点]

---

## 第 5 章：当前阶段与关键变化

<!--
CHAPTER_GOAL
回答"为什么偏偏是现在"——把基金放在时间轴上，判断当前所处的阶段。
核心区分：结构性变化 vs 阶段性变化。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 5
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **过去一年最关键的变化**：
- **基金当前所处阶段**：
- **变化是否改变前文判断**：🟢 未改变 / 🟡 需要重新评估 / 🔴 推翻前文判断
- **接下来最该跟踪什么**：

### 详细情况

#### 关键变化清单
| # | 变化内容 | 发生时间 | 对基金的影响 | 是否改变判断 |
|---|---------|---------|-------------|-------------|
| 1 | | | | 🟢/🟡/🔴 |
| 2 | | | | 🟢/🟡/🔴 |
| 3 | | | | 🟢/🟡/🔴 |

#### 当前阶段判断
> [这只基金目前处于什么阶段？这个阶段对投资者意味着什么？]

### 证据与出处
- [列出本章所有关键数据的来源锚点]

---

## 第 6 章：核心风险与否决项

<!--
CHAPTER_GOAL
整个分析的"安全阀"——回答"什么情况下应该直接放弃这只基金"。
核心区分：否决项（一票否决）vs 跟踪项（持续关注）vs 一般风险（正常承受）。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 6
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **最关键的风险或否决项**：
- **否决 vs 跟踪**：🔴 一票否决 / 🟡 需要验证 / 🟢 持续跟踪
- **下一轮先验证什么**：

### 详细情况

#### 基金安全检查
| 检查项 | 当前值 | 安全阈值 | 判定 |
|--------|--------|---------|------|
| 基金规模 | X 亿 | > 2 亿 | 🟢/🟡/🔴 |
| 基金公司管理总规模 | X 亿 | > 1000 亿 | 🟢/🟡/🔴 |
| 基金成立年限 | X 年 | > 3 年 | 🟢/🟡/🔴 |
| 基金经理管理本基金时间 | X 年 | > 2 年 | 🟢/🟡/🔴 |
> 📎 证据：年报§2 基金简介 + 天天基金数据

#### 历史最大回撤
| 时间段 | 最大回撤 | 恢复时间 | 同期基准回撤 |
|--------|---------|---------|-------------|
| 近 1 年 | -XX% | X 个月 | -XX% |
| 近 3 年 | -XX% | X 个月 | -XX% |
| 历史最大 | -XX% | X 个月 | -XX% |

#### 否决项清单
| 风险项 | 当前状态 | 判定 | 说明 |
|--------|---------|------|------|
| 清盘风险（规模 < 5000 万） | | 🟢/🔴 | |
| 基金经理离职/变更 | | 🟢/🔴 | |
| 风格严重漂移 | | 🟢/🟡/🔴 | |
| 费率远超同类 | | 🟢/🟡/🔴 | |
| 换手率异常飙升 | | 🟢/🟡/🔴 | |
| 行业/持仓过度集中 | | 🟢/🟡/🔴 | |

#### 压力测试（借鉴 E大网格策略）
> "压力测试是最重要的。" —— E大
> 
> **阈值说明**：不同基金类型使用不同压力测试阈值（已在 preferred_lens 中定义）
> - 指数基金：-30%（正常）/ -50%（极端）/ -70%（历史最差）
> - 主动基金：-25%（正常）/ -45%（极端）/ -65%（历史最差）
> - 债券基金：-5%（正常）/ -10%（极端）/ -20%（历史最差）
> - 增强基金：-25%（正常）/ -45%（极端）/ -60%（历史最差）
> - QDII基金：-35%（正常）/ -55%（极端）/ -75%（历史最差）
> - FOF基金：-20%（正常）/ -40%（极端）/ -55%（历史最差）

假设投入 [X] 万元：
| 场景 | 跌幅 | 账户余额 | 浮亏金额 | 能否承受？ |
|------|------|---------|---------|-----------|
| 正常波动 | [按基金类型填写] | X 万 | X 万 | ✅ |
| 极端下跌 | [按基金类型填写] | X 万 | X 万 | ✅/⚠️/❌ |
| 历史最差 | [按基金类型填写] | X 万 | X 万 | ✅/⚠️/❌ |

### 证据与出处
- [列出本章所有关键数据的来源锚点]

---

## 第 7 章：是否值得持有——最终判断

<!--
CHAPTER_GOAL
整份报告的"出口"——收敛到明确的行动建议。
基于前 6 章的分析，给出"值得持有 / 需要关注 / 建议替换"的三选一判断，并说明支撑依据、最大风险点和最小验证计划。
END_CHAPTER_GOAL
-->
<!--
CHAPTER_CONTRACT_REF
chapter_id: 7
source: TEMPLATE_CONTRACT_MANIFEST_JSON
END_CHAPTER_CONTRACT_REF
-->

### 结论要点
- **最终判断**：🟢 值得持有 / 🟡 需要关注 / 🔴 建议替换
- **支撑判断的核心依据**：
- **当前最容易看错的地方**：
- **下一轮最小验证计划**：
- **什么变化会改变判断**：

### 详细情况

#### 为什么是这个判断（而不是另外两个）
- **为什么不选更积极的判断**：[如果选"值得持有"，什么阻止了更积极的结论？]
- **为什么不选更保守的判断**：[如果选"建议替换"，什么支撑了不至于更悲观？]

#### 最容易看错的地方
> [投资者最可能误判这只基金的哪个方面？]

#### 最小验证计划
| # | 验证问题 | 验证方式 | 验证周期 |
|---|---------|---------|---------|
| 1 | | | 下次年报 |
| 2 | | | 季度跟踪 |

#### 阈值事件
| 方向 | 触发条件 | 动作 |
|------|---------|------|
| ⬆️ 升级 | [什么情况下从"需要关注"升级为"值得持有"] | |
| ⬇️ 降级 | [什么情况下从"值得持有"降级为"需要关注"或"建议替换"] | |

---

## 附录 A：数据来源与证据锚点汇总

### 证据锚点格式规范
- **正文引用格式**：`> 📎 证据：年报§[章节] [内容描述]`
- **附录汇总格式**：`年报[年份]§[章节]表[编号]行[行号]`
- **示例**：`> 📎 证据：年报2024§3表2行5（净值增长率）`

### 数据来源对照表
| 数据项 | 来源 | 锚点格式 |
|--------|------|---------|
| 净值增长率 | 年报§3 | 年报[年份]§3表2行X |
| 业绩基准收益率 | 年报§3 | 年报[年份]§3表2行X |
| 管理费率 | 招募说明书 | 招募说明书第X页 |
| 托管费率 | 招募说明书 | 招募说明书第X页 |
| 换手率 | 年报§8 | 年报[年份]§8 |
| 基金经理持有 | 年报§9 | 年报[年份]§9 |
| 投资策略 | 年报§4 | 年报[年份]§4 |
| 持仓明细 | 年报§8 | 年报[年份]§8表X |
| 份额变动 | 年报§10 | 年报[年份]§10 |
| 盈利投资者占比 | 年报§3 | 年报[年份]§3（2026新规） |
| 投资目标 | 招募说明书 | 招募说明书"投资目标"章节 |
| 业绩基准 | 招募说明书 | 招募说明书"业绩比较基准"章节 |

---

## 附录 B：审计规则速查

| 规则码 | 含义 | 阻断级别 | 本报告适用场景 |
|--------|------|----------|--------------|
| P1 | 章节结构不匹配 | 阻断 | 缺少必要章节 |
| P2 | 内容过短（<10字符） | 阻断 | 关键字段为空 |
| E1 | 证据锚点不精确 | 可复核 | 数据来源未标注到具体位置 |
| E2 | 证据与断言不匹配 | 可复核 | 计算结果与原始数据不一致 |
| E3 | 证据完全缺失 | 需重建 | 关键数据无法从年报中找到 |
| C1 | 内容违规（幻觉） | 阻断 | 编造了年报中不存在的基金经理观点 |
| L1 | R=A+B-C 计算错误 | 阻断 | 数值计算不闭合 |
| L2 | 百分位/排名计算错误 | 可复核 | 同类排名计算有误 |
| R1 | 检查清单规则应用错误 | 阻断 | 信号判定与规则不一致 |
| R2 | 判定与评分不一致 | 阻断 | 最终判断与各章信号矛盾 |
