# fund-checklist — 用户手册

`fund-checklist` 是面向基金投资者的多年度分析助手：下载 / 导入年报 PDF →
Docling 结构化抽取 → 多年度追踪 → 信号评分 → 8 章分析报告生成 → 三层审计
→ 修复闭环。

本文档面向最终使用者，只写安装、配置、下载、导入、阅读问答、多年度分析、
报告生成、审计修复所需的当前可用命令与示例。

## 文档更新约束【必须遵守】

- 本文档只写用户成功路径与命令示例，不展开 Host / Agent / Service / 工具层内部机制、
  状态机、测试清单或开发者迁移计划。
- 更新前必须先核对当前 CLI 入口、参数解析与用户可见输出；代码真源高于历史说明。
- 涉及开发者架构、包边界或代码阅读路径时，链接到开发文档，不在本文档展开。

开发文档入口：

- [执行规则](AGENTS.md)
- [设计真源](docs/design.md)
- [执行面板](docs/implementation-control.md)

## 1. 环境准备

项目默认 Python 3.11，推荐 `uv` 管理虚拟环境：

```bash
cd fund-checklist
uv venv --python 3.11 .venv
source .venv/bin/activate
uv sync
```

确认入口：

```bash
uv run fund-checklist --help
```

LLM 相关命令（`ask` / `interactive` / `generate --llm` / `repair` / `regenerate` / `fix`）需要配置 provider key。支持 DeepSeek 与 Mimo，经 `FUND_CHECKLIST_LLM_PROVIDER` 切换：

```bash
# DeepSeek（默认）
export DEEPSEEK_API_KEY=sk-xxx
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_MODEL=deepseek-v4-flash

# Mimo
export FUND_CHECKLIST_LLM_PROVIDER=mimo
export MIMO_API_KEY=xxx
export MIMO_BASE_URL=https://api.xiaomimimo.com/v1
export MIMO_MODEL=mimo-v2.5-pro
```

## 2. 下载年报

`download` 从公开信息披露平台（EID）下载年报 PDF，一次一年，默认输出到 `基金年报/`：

```bash
uv run fund-checklist download --fund-code 005680 --year 2025
```

循环下载 5 年年报：

```bash
for y in 2021 2022 2023 2024 2025; do
  uv run fund-checklist download --fund-code 005680 --year $y
done
```

常用参数：

- `--output-dir`：PDF 输出目录（默认 `基金年报/`）。
- `--force`：已存在时强制重新下载（默认跳过）。

## 3. 导入年报

`import` 批量导入指定年份范围的年报 PDF，执行 PDF integrity 校验 → Docling 转换 → parser health 校验，并登记到 catalog。文件名需包含基金名称和年份（如 `005680_财通资管价值成长混合_2025_annual_report.pdf`），`--fund-name` 用于自动匹配。

```bash
uv run fund-checklist import \
  --pdf-dir ./基金年报/ \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --year-range 2021-2025 \
  --work-dir .fund_checklist_005680
```

成功输出包含 `document_id`（格式 `fund_code-year-report_type-fingerprint`），后续 `ask` / `read` 等命令依赖它。`--work-dir` 存放 Docling JSON、catalog 与报告产物；同一基金的后续命令保持传入同一目录。

## 4. 阅读与问答

### 4.1 单份年报阅读（确定性检索）

`read` 走确定性的 search → read 工具链路，不需要 LLM：

```bash
uv run fund-checklist read \
  --pdf 基金年报/005680_财通资管价值成长混合_2025_annual_report.pdf \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --year 2025 \
  --query '前十大持仓' \
  --work-dir .fund_checklist_005680
```

`--query` 默认 `基金经理`；`--share-class` 可选（A/C 类）。

### 4.2 单次 LLM 自主问答

`ask` 让 LLM 自主调用检索工具并引用证据回答，需要已导入的 `document_id`：

```bash
uv run fund-checklist ask \
  '基金近一年净值增长率是多少' \
  --document-id 005680-2025-annual_report-xxxxxxxxxxxx \
  --work-dir .fund_checklist_005680
```

常用参数：

- `--no-stream`：关闭流式，完成后输出 JSON。
- `--enable-tool-trace`：流式模式下同步显示工具调用与结果。

### 4.3 多轮交互对话

`interactive` 支持多轮追问、会话持久化与上下文记忆：

```bash
uv run fund-checklist interactive \
  --fund-code 005680 \
  --work-dir .fund_checklist_005680
```

进入后输入问题开始对话；`/help` 查看命令，`exit` 退出。支持：

- `--label NAME`：会话标签（用于恢复）。
- `--year YYYY`：指定年报年份（默认最新年份）。
- `--enable-tool-trace`：显示工具调用详情。
- `--plain`：保留原始 Markdown，禁用 Rich 格式化。
- `--no-stream`：关闭流式输出。

## 5. 多年度分析

以下命令基于 catalog 中已导入的多年份年报，输出结构化分析：

```bash
# 多年度业绩聚合（3-5 年 bounded coverage）
uv run fund-checklist multi-year \
  --fund-code 005680 \
  --years 2021,2022,2023,2024,2025 \
  --work-dir .fund_checklist_005680

# 多年度持仓追踪
uv run fund-checklist holdings \
  --fund-code 005680 \
  --years 2021,2022,2023,2024,2025 \
  --work-dir .fund_checklist_005680

# 资产配置分析
uv run fund-checklist allocation \
  --fund-code 005680 \
  --years 2021,2022,2023,2024,2025 \
  --work-dir .fund_checklist_005680

# 费率分析
uv run fund-checklist fees \
  --fund-code 005680 \
  --years 2021,2022,2023,2024,2025 \
  --work-dir .fund_checklist_005680
```

`multi-year` 输出对每个缺失年份附 `missing_year_notes` 原因说明（如转型当年无全年份额净值增长率、catalog 未导入），不伪造年度数据。

## 5.5 季报/半年报快照（snapshot）

对已导入的单期季报/半年报生成当期快照分析（5 章 / 6 章，非多年；季报缺失项 fail-closed 声明）：

```bash
# 导入季报（contract-first：显式 --report-type + --quarter）
uv run fund-checklist import \
  --pdf-dir 基金季报 \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --report-type quarterly_report \
  --quarter 2 \
  --year-range 2026-2026 \
  --work-dir .fund_checklist_005680_snapshot

# 生成季报快照
uv run fund-checklist snapshot-quarterly \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --year 2026 \
  --quarter 2 \
  --format markdown \
  --work-dir .fund_checklist_005680_snapshot

# 生成半年报快照（--period H1）
uv run fund-checklist snapshot-semiannual \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --year 2025 \
  --period H1 \
  --format markdown \
  --work-dir .fund_checklist_005680_snapshot
```

- 落盘：`reports/{fund_code}-{year}Q{n}-quarterly-snapshot.md` / `reports/{fund_code}-{year}H1-semiannual-snapshot.md`；`--format json | markdown | pdf`。
- 快照文档（quarterly/semiannual）**不会**进入 `multi-year` / `generate` 的 annual 系列（catalog 过滤按 `report_type=annual_report` 防污染）。
- 从 EID 下载季报/半年报：`download --report-type quarterly_report --quarter 2` / `download --report-type semiannual_report`。

## 6. 生成基金分析报告

`generate` 生成 8 章分析报告（程序数据表格 + LLM 定性分析）：

```bash
uv run fund-checklist generate \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --year 2025 \
  --years 2021,2022,2023,2024,2025 \
  --llm \
  --concurrency 4 \
  --work-dir .fund_checklist_005680
```

- `--year`：主报告年份；`--years`：多年度聚合年份列表（**逗号分隔**，如 `2021,2022,2023,2024,2025`；留空自动使用 catalog 全部年份）。
- `--format`：`json`（默认，仅 stdout）/ `markdown`（落盘 `reports/005680-2025-analysis.md`）/ `pdf`（渲染 PDF）。
- `--concurrency`：章节生成并发数（1-8，默认 4；仅 `--llm` 模式生效）。
- `--llm`：使用 LLM 生成分析文本（需 provider key）。
- ETF 联接基金场景可指定标的 ETF 作为持仓源：`--holdings-source-fund 512890 --holdings-source-workdir .fund_checklist_512890`。

输出 PDF 格式：

```bash
uv run fund-checklist generate \
  --fund-code 005680 \
  --fund-name '财通资管价值成长混合' \
  --year 2025 \
  --years 2021,2022,2023,2024,2025 \
  --llm \
  --concurrency 4 \
  --format pdf \
  --work-dir .fund_checklist_005680
```

PDF 渲染走 `xelatex` → Chrome headless（pandoc md→HTML + 内置打印 CSS，A4）→ 回退 Markdown 的 fallback 链；本机缺 `xelatex` / pandoc / Chrome 时自动回退并提示。

## 7. 审计与修复

### 7.1 审计

```bash
# 披露完整性审计（程序 + LLM + 复核，4 类 22 项）
uv run fund-checklist audit \
  --fund-code 005680 \
  --year 2025 \
  --work-dir .fund_checklist_005680

# 深度审计
uv run fund-checklist deep-audit \
  --fund-code 005680 \
  --year 2025 \
  --work-dir .fund_checklist_005680
```

审计产物落盘 `audit_artifacts/chapter_*_audit.json`；审计分数驱动修复策略选择。

### 7.2 修复

三类修复场景（均需 `--llm`）：

```bash
# repair：审计发现小问题时最小必要局部修复；--auto 按审计分数自动选策略
uv run fund-checklist repair \
  --fund-code 005680 --year 2025 --chapter 3,5,7 \
  --llm --auto --work-dir .fund_checklist_005680

# regenerate：基于审计反馈整章重建
uv run fund-checklist regenerate \
  --fund-code 005680 --year 2025 --chapter 3,5,7 \
  --llm --work-dir .fund_checklist_005680

# fix：结构化占位符补强
uv run fund-checklist fix \
  --fund-code 005680 --chapter 4 \
  --llm --work-dir .fund_checklist_005680
```

`--chapter`：章节号（1-8），逗号分隔多个。

## 8. 常见问题

### PDF 无法导入

确认文件名包含可识别的基金名称与年份，且 PDF 通过 integrity 校验（Content-Type、magic bytes、非空）；Docling 转换失败会以分类错误提示，可按 `--work-dir` 内日志定位。

### LLM 命令报 provider 错误

检查 `FUND_CHECKLIST_LLM_PROVIDER` 对应 key 是否配置（DeepSeek：`DEEPSEEK_API_KEY`；Mimo：`MIMO_API_KEY`）；未知 provider 值会 fail-fast 提示合法取值。

### 报告生成没有落盘 PDF

`--format pdf` 依赖本机 `xelatex` / pandoc / Chrome（`shutil.which` 前置探测）；三者都缺失时回退为 Markdown 输出并打印 warning。

### 工作目录混乱

每个基金使用独立 `--work-dir`（如 `.fund_checklist_005680`）；导入、问答、生成、审计保持同一目录，否则 catalog 与报告产物对不上。

## 测试命令

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

## 非目标

- 不实现 UI / Web / 微信入口。
- 不提供联网实时资讯（产品边界决策）。
- 不做投资判断与买卖建议；不预测未来收益。
- 不声明 release ready。

本地样本 PDF、`.fund_checklist*` 工作目录、Docling/model cache、虚拟环境和测试 cache 不纳入 git。
