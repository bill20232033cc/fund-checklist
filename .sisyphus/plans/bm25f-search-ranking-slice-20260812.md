# Slice: BM25F 检索排序增强（search_document 确定性重排序）

controller: main thread
impl: DS（agents:0.1）
review: MiMo（agents:0.2）
模式: CIC-lite（implement -> tests -> diff review，无 plan-fix / re-review / evidence gate）
依据: `docs/research/dayu-agent-r-research-20260810.md` §2.1.1 / §5 建议 1（研究观点）；本地 dayu `bm25f_scorer.py` 仅作算法参考，不复制代码（Apache-2.0，license gate）
真源同步: 本轮已完成 `docs/design.md` §5.4 + §6.20、`docs/implementation-control.md`、`AGENTS.md` backlog 行更新（开发前同步，controller 维护）

## 目标

把 `search_document` 的排序从「字面子串命中计数 + source_order」升级为「确定性 BM25F 多字段重排序」。只改排序，不改召回，public contract 不变。

## 现状（已验证代码事实）

- 召回：`_section_search_candidates`（docling_store.py:502）+ `_table_search_candidates`（:544）按子串命中构建候选。
- 排序：`candidates.sort(key=lambda item: (-item.score, item.source_order))`（docling_store.py:271）；score = 空白归一化后的子串命中计数。
- 字段现状：section 只匹配 text（:510），不匹配 title；table caption 用原始 count（:566）；row 用归一化计数（:585）。
- `SearchResult` 公共契约不含 score，只有 rank/section_ref/title/excerpt/locator/citation/match_kind/table_ref（models.py:328）。
- 依赖：pyproject.toml 仅 docling + rich；无 jieba / rank_bm25 等检索依赖。本 slice 不新增依赖。

## 硬口径（必须严格遵守）

1. 召回不变：候选集完全来自现有子串命中逻辑（section text、table caption、bounded table rows、within_section_ref 过滤、DEFAULT_TABLE_MAX_ROWS 有界扫描）；BM25F 只对候选重排序。
2. 公共契约不变：`search_document` 签名、`SearchResult` 字段、match_kind、locator/citation、失败分类全部不变；不新增公共字段、不新增 failure code；0 命中仍返回空 tuple。
3. 确定性：纯函数；不联网、不接 LLM、无随机；同 store 同 query 必须产出相同排序；分数统一 round 到 6 位小数后再排序。
4. 无新依赖：分词用内置实现（ASCII 单词 `[a-z0-9]+` + CJK 二元组，单字符段回退一元组），不引入 jieba / rank_bm25。
5. 常量集中：字段权重、b 参数、k1、n-gram 大小、token pattern 全部进 `constants.py`，禁止魔法数字散落。
6. 新模块：新建 `fund_agent/fund/document_tools/bm25f_scorer.py`（自行实现标准 BM25F；公式为公开算法，参数自定义，不复制 dayu 代码）。
7. 排序键：主键 BM25F 分数 desc → 次键现有子串命中计数 desc → 次键 source_order asc（保留现有行为作稳定 tiebreak）。
8. 只改排序：不触碰 `_search_excerpt`、excerpt 生成、citation/locator 组装、`_ParsedSection` / `_ParsedTable` 模型。
9. 文档：`fund_agent/fund/README.md` 检索节同步加 BM25F 一句话；docs 三件套（AGENTS.md / design.md / implementation-control.md）由 controller 维护，本 slice 已先行同步。
10. 不 commit / 不 push。

## 字段与参数（设计）

候选级字段权重：

- section 候选：title 3.0、text 1.0
- table caption 候选：caption 2.0
- table row 候选：rows（单行文本）1.0

BM25F 参数：

- k1 = 1.2
- b：title/caption 0.35，text/rows 0.75

索引（每个 store 构建一次，构建时一次性计算；纯内存）：

- document unit = 每个 section + 每个 table caption + 每个 bounded table row
- document_frequency = term 出现的 unit 数
- avg_field_length = 各字段 token 长度均值（仅统计含该字段的 unit）

分词（沿用 `_whitespace_stripped` 语义，先去空白再处理）：

- ASCII/数字：`[a-z0-9]+` 提取单词（lowercase）
- CJK：对连续非空白段做 2-gram；段长 1 时用 1-gram
- 中英混合段各自提取后拼接（如 `12.77%净值` → `["12","77"]` + CJK bigrams）

打分（标准 BM25F）：

- idf = ln(1 + (N - df + 0.5) / (df + 0.5))
- term score = idf × (k1+1) × Σ_f w_f·tf_f / (1 - b_f + b_f·len_f/avg_f) / (k1 + Σ_f w_f·tf_f / (1 - b_f + b_f·len_f/avg_f))
- 全部 term 求和后 round(score, 6)

## 测试（新增/更新，必须覆盖）

新建 `tests/fund/document_tools/test_bm25f_scorer.py`（scorer 单测）：

- 分词：CJK bigram、ASCII 单词、中英混合、单字符 fallback
- 字段权重：title 命中分 > text 命中分（同 query 同 tf）
- idf：稀有 term 的 idf > 常见 term 的 idf
- 长度归一化：同 tf 下短字段得分高于长字段
- 空语料 / 无 term 命中 → 0.0
- 确定性：相同输入两次调用结果一致

扩展 `tests/fund/document_tools/test_docling_store.py`：

- title 命中排在正文命中之前（新行为，当前实现相反）
- 稀有词加权端到端：query 同时含稀有词+常见词时，含稀有词的单次命中候选排在只含常见词多次命中候选之前（当前子串排序会把后者排前）
- 同分同命中时 source_order tiebreak 保持：既有 `test_store_search_orders_table_caption_before_row_for_equal_score` 必须仍 caption 在前（权重 2.0 > 1.0 保证，若长度归一化翻转需先与 controller 确认再改测试）
- 既有回归全部保持通过：ranked excerpt、caption-only、bounded row、0 命中空 tuple、越界行不扫描、空白归一化（section/row）

## Allowed write set（DS 只允许动这些）

- `fund_agent/fund/document_tools/bm25f_scorer.py`（新增）
- `fund_agent/fund/document_tools/docling_store.py`（索引构建 + 排序集成；不得改 public 方法签名）
- `fund_agent/fund/document_tools/constants.py`（BM25F 常量）
- `fund_agent/fund/README.md`（检索节一句话）
- `tests/fund/document_tools/test_bm25f_scorer.py`（新增）
- `tests/fund/document_tools/test_docling_store.py`（增补排序用例）

禁止动：AGENTS.md、docs/design.md、docs/implementation-control.md（controller 已先行同步，收口状态由 controller 回写）；禁止 commit / push；禁止新增依赖；禁止改 SearchResult / 公共契约 / public 方法签名。

## 必须运行的测试命令（跑完把输出贴进交接报告）

1. `uv run pytest tests/fund/document_tools/test_bm25f_scorer.py -v --tb=short`
2. `uv run pytest tests/fund/document_tools/test_docling_store.py -v --tb=short`
3. `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py`

## Stop condition

全部测试通过后停止。输出交接报告：changed files、diff 摘要、实际测试命令与输出。失败时报告最小失败原因，不得声称完成。

## 交接报告格式（回复给 controller）

- changed files: 列表
- diff 摘要: 每文件 1-2 行
- 测试: 实际命令 + passed/failed 数字
- 失败/风险: 若有
