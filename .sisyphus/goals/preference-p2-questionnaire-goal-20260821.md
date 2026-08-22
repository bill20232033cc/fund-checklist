# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/goals/preference-p2-questionnaire-goal-20260821.md 实施「Slice P2：preference-questionnaire（问卷基线：有知有行板块结构 + 自建 80 题）」slice（设计真源：docs/design.md §6.26.6，2026-08-21 已定稿：题库 = 融入有知有行五大板块结构 + 自建 80 题 + 五维权重 25/20/20/20/15 + C1-C5 保留为辅助输出；AGENTS.md / docs/design.md 已由 controller 同步，禁止修改）。前置：Slice P1（flomo-import）已实现，fund_agent/preferences/ 模块存在。只走 CIC-lite implement -> tests -> diff review。实施内容：① 新增 fund_agent/preferences/questionnaire/baseline-v1.json（题库资产，git 跟踪，非私人数据）——自建 80 题中文单选题，五大板块各 16 题：基金常识 / 投前准备 / 系统投资 / 投资心态 / 实战经验；每题字段 {id: "q01".."q80", board: 板块名, difficulty: 1|2|3, question: 题干, options: [4 个选项], answer: 正确选项索引 0-3, risk_flag: bool（仅投资心态/实战经验板块可为 true，用于 C1-C5 辅助映射，全库 risk_flag=true 题数 8-16 题）, explanation: 解释}；难度三档递进（总体约 30/40/30 分布）；题型含情境题与行为题（可参考但不得照抄有知有行未公开题库；公开样题口径见 design §6.26.2：十年十倍需年化约 26%、跌 30% 回本需涨约 43%、中概股 -50% 后再跌 80% 亏损约 -60%、A 股长期年化约 9.61%）；json 顶层含 {version: "baseline-v1", boards: [5 板块名按序], weights: {"基金常识": 25, "投前准备": 20, "系统投资": 20, "投资心态": 20, "实战经验": 15}, c1c5_bands: [[0,19],[20,36],[37,53],[54,75],[76,100]], disclaimer: "本输出仅用于自我认知与组合检视，不构成投资建议，不预测收益。"}；② 新增 fund_agent/preferences/questionnaire.py——QuestionBank.load(path) 校验完整性（80 题、板块 5 选 1、每题 4 选项且 answer 0-3、weights 5 键合计 100、risk_flag 数 8-16、json 解析失败/结构非法抛 ValueError 中文消息）；score_questionnaire(bank, answers: dict[str, int]) -> QuestionnaireResult 计算板块得分率→板块得分（得分率 × 权重）→五维子分 dict + 总分（0-100，四舍五入 1 位）+ 辅助 C1-C5（risk_flag 题得分率 × 100 落入 c1c5_bands → "C1".."C5"）+ 逐题答案快照；③ 修改 fund_agent/preferences/store.py——新增 questionnaire_results 表（id TEXT PK, answered_at TEXT, dimension_scores_json TEXT, total_score REAL, risk_level TEXT, answers_json TEXT, disclaimer TEXT）+ save_questionnaire_result(store, result) 与 list_questionnaire_results(store)（按 answered_at 倒序）；④ 修改 fund_agent/cli/main.py——注册 preference-questionnaire 子命令（--work-dir 默认 .fund_checklist、--answers 可选 Path、--bank 可选 Path 默认包内 baseline-v1.json）+ _run_preference_questionnaire_command（TTY 交互逐题出题/收答案；非 TTY 必须 --answers JSON 文件 {q01: 0, ...} 否则 not_found/分类失败退出码 2；答案非法（未知题号/索引越界/缺失题）→ schema_drift 退出码 2；成功输出总分/五维子分/辅助 C1-C5 + 结果 json 路径 + db 写入确认；不接 LLM）；⑤ 新增 tests/fund/preferences/test_questionnaire.py（题库完整性：80 题/板块分布 16×5/难度分布/risk_flag 8-16/weights 合计 100；评分：满分 100、全错 0、单板块权重换算、总分=五维和、risk_flag 档位映射 C1-C5 边界、未知题号抛 ValueError；answers 缺失题抛 ValueError）；⑥ 新增 tests/fund/preferences/fixtures/mini_bank.json（小题库 fixture：6 题 3 板块，用于评分单测，非完整 80 题）+ tests/fund/cli/test_cli_preference_questionnaire.py（run_cli 端到端：--answers 合法 → 退出码 0 + results json + db 行；--answers 缺失文件 → 退出码 2；answers 结构非法 → 退出码 2）。allowed write set：fund_agent/preferences/questionnaire/ 新增、fund_agent/preferences/questionnaire.py 新增、fund_agent/preferences/store.py、fund_agent/cli/main.py、tests/fund/preferences/ 新增、tests/fund/cli/test_cli_preference_questionnaire.py 新增、fund_agent/README.md 与 tests/README.md 各补 1 句。禁止修改 AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/（本 goal 文件除外）/ fund_agent/fund|service|host|agent / 存量 quarterly-top10-holdings-fix 涉及文件 / Slice P1 已实现文件（fund_agent/preferences/flomo_parser.py、store.py 中 memos/imports 部分、flomo-import CLI）；禁止新增第三方依赖；禁止照抄有知有行未公开题库；禁止接 LLM；不 commit、不 push。验收：uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_preference_questionnaire.py -v --tb=short 全通过，且最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 回归通过；输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/preference-p2-questionnaire-goal-20260821.md
```

## Goal

- goal_id: `preference-p2-questionnaire-20260821`
- 目标：实施投资者偏好分析 MVP Slice P2——`preference-questionnaire`（自建 80 题题库 + 评分器：总分 100 + 五维子分 + 辅助 C1-C5），确定性、不接 LLM。
- 前置条件：`docs/design.md` §6.26.6 已定稿（题库 = 有知有行五大板块 + 80 题；五维权重 25/20/20/20/15；C1-C5 保留为辅助输出）；Slice P1 已完成（`fund_agent/preferences/` 模块与 `store.py` 存在）。
- 设计来源：`docs/design.md` §6.26.2（有知有行外部参考）/ §6.26.6（问卷基线设计）。
- 日期：2026-08-21

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope

| 项 | 内容 |
|-------|------|
| 新增资产 | `fund_agent/preferences/questionnaire/baseline-v1.json`（80 题题库） |
| 新增模块 | `fund_agent/preferences/questionnaire.py`（QuestionBank / score_questionnaire） |
| 修改模块 | `fund_agent/preferences/store.py`（questionnaire_results 表 + save/list）、`fund_agent/cli/main.py`（preference-questionnaire 子命令） |
| 新增测试 | `tests/fund/preferences/test_questionnaire.py`、`tests/fund/preferences/fixtures/mini_bank.json`、`tests/fund/cli/test_cli_preference_questionnaire.py` |
| 文档 | `fund_agent/README.md`、`tests/README.md`（各 1 句） |
| 禁止 | AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/（本 goal 文件除外）/ fund_agent/fund|service|host|agent / 存量 quarterly-top10-holdings-fix 涉及文件 / Slice P1 已实现文件 / 新第三方依赖 / 照抄有知有行未公开题库 / LLM / commit / push |

## 验收（DoD）

- `uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_preference_questionnaire.py -v --tb=short` 全通过。
- 最小验证集 `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short` 回归通过。
- 交接报告：changed files / diff 摘要 / 实际测试命令与输出。
