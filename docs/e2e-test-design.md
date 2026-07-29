# 端到端测试验证设计

**创建时间**：2026-07-27
**目标**：对现有对话能力和 5 年年报 LLM 写作（含 LLM 审计）开展端到端测试验证
**状态**：v3（DS 二审修复版）
**审核记录**：
- DS 第一轮 NEEDS_FIX（12 项）→ v2 修复
- DS 第二轮 NEEDS_FIX（11 项，含 3 P0）→ v3 修复
- 裁决：Scene 8/9 删除独立场景，章节审计合并到 Scene 5；audit/deep-audit 改为披露完整性审计

---

## 0. 术语与口径

### 0.1 章节编号

- **代码内部**：`chapter_id` 为 0-indexed（0-7），对应 Ch0-Ch7
- **CLI 参数**：`--chapter` 为 1-indexed（1-8），对应 Ch1-Ch8
- **映射关系**：CLI `--chapter 1` = 代码 `chapter_id=0`（Ch0: 投资要点概览）
- **审计产物**：`chapter_{chapter_id}_audit.json`（0-indexed），如 `chapter_0_audit.json`

### 0.2 LLM 参数

- `--llm`：显式启用 LLM 调用（需要 `DEEPSEEK_API_KEY`）
- 不传 `--llm`：纯程序路径，不调用 LLM
- `ask` 子命令：始终走 LLM（无 `--llm` 开关）

### 0.3 审计命令澄清

- `audit` / `deep-audit`：**披露完整性审计**，检查年报是否包含必要披露项（无 `--chapter`、无 `--llm` 参数）
- **章节级审计**：嵌入在 `generate` 流程中（`audit_pipeline._generate_and_audit_chapter`），无独立 CLI 入口
- 章节审计产物由 `generate --llm` 自动生成，无需单独调用

### 0.4 环境变量检测

- 所有需要 LLM 的场景：`DEEPSEEK_API_KEY` 缺失时 `pytest.skip("DEEPSEEK_API_KEY not set")`
- conftest 提供 `requires_llm` fixture 自动检测

---

## 1. 测试目标

### 1.1 对话能力验证

验证 `interactive` 和 `ask` 子命令的多轮对话能力，包括：
- LLM 自主工具调用路径（`ask` 始终走 LLM，`interactive` 通过 ChatService 走 LLM）
- 多轮对话上下文记忆
- Rich Table 格式化输出
- `/history` 命令
- 追问建议
- 会话恢复（`--label`）

### 1.2 5 年年报 LLM 写作验证

验证 `generate` 子命令的多年度报告生成能力，包括：
- 5 年年报数据导入
- 8 章分析报告生成（Ch0-Ch7，CLI 层 Ch1-Ch8）
- LLM 定性分析（传 `--llm`）
- 章节级审计（嵌入 generate 流程，产物为 `chapter_{id}_audit.json`）
- 信号评分（基金类型感知）

### 1.3 披露完整性审计验证

验证 `audit` 和 `deep-audit` 子命令的披露完整性审计能力，包括：
- 披露项检查（年报是否包含必要披露内容）
- 完整性评分
- 审计结果 JSON 输出

### 1.4 修复能力验证

验证 `repair`、`regenerate`、`fix` 子命令的修复能力，包括：
- `repair --chapter`：局部修复（审计反馈驱动）
- `regenerate --chapter`：整章重建（审计反馈注入 prompt）
- `fix --chapter`：占位符补强（结构化数据缺失）
- 审计分数驱动的自动策略选择（`--auto`）

---

## 2. 测试环境

### 2.1 前置条件

- 本地已导入 5 年年报 PDF（2020-2024）
- 基金代码：004393（安信企业价值优选混合型证券投资基金）
- 工作目录：`.fund_checklist_e2e_004393`
- LLM provider：DeepSeek（`DEEPSEEK_API_KEY` 已配置）
- Python 环境：`uv` 可用

### 2.2 测试数据准备

```bash
# 导入 5 年年报
uv run fund-checklist import \
  --pdf-dir ./基金年报/ \
  --fund-code 004393 \
  --fund-name '安信企业价值优选混合型证券投资基金' \
  --year-range 2020-2024 \
  --work-dir .fund_checklist_e2e_004393
```

### 2.3 document_id 获取方式

`document_id` 从 import 成功后的 catalog 文件中读取，格式为 `{fund_code}-{year}-{report_type}-{fingerprint_prefix}`。

```python
# conftest.py 中实现
catalog_path = work_dir / "catalog.json"
catalog = json.loads(catalog_path.read_text())
document_id = next(
    d["document_id"] for d in catalog["documents"]
    if d["fund_code"] == fund_code and d["year"] == year
)
```

### 2.4 自动化策略

| 场景类型 | 自动化方式 | 工具 |
|----------|-----------|------|
| CLI 子命令（ask/generate/audit/repair/fix 等） | pytest subprocess | `subprocess.run()` |
| interactive 多轮对话 | pytest subprocess + stdin pipe | `subprocess.Popen(stdin=PIPE, stdout=PIPE)` |
| 输出格式验证 | 正则匹配 + JSON 解析 | `re` / `json.loads` |
| LLM 依赖检测 | `requires_llm` fixture | `pytest.skip()` |

---

## 3. 测试场景

### 3.1 对话能力测试场景

#### 场景 1：单轮问答（ask 子命令 — 流式模式）

**目标**：验证 LLM 自主工具调用路径（默认流式输出）

**前置条件**：已导入年报，`document_id` 已从 catalog 获取

**步骤**：
```bash
# 流式模式（默认）
uv run fund-checklist ask \
  '基金经理是谁？' \
  --document-id 004393-2024-annual_report-XXXXXXXX \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 包含非空文本回答（流式逐字输出）
- 回答包含基金经理相关信息

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
assert result.returncode == 0
assert len(result.stdout.strip()) > 0
```

#### 场景 1b：单轮问答（ask 子命令 — JSON 模式）

**目标**：验证 `--no-stream` 模式的结构化输出

**步骤**：
```bash
uv run fund-checklist ask \
  '基金经理是谁？' \
  --document-id 004393-2024-annual_report-XXXXXXXX \
  --no-stream \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 为合法 JSON
- JSON 包含 `answer`（非空字符串）、`citations`（列表）、`routing_trace`（列表）
- `citations` 每项包含 `document_id`、`fund_code`、`fund_name`、`year`、`report_type`

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
assert result.returncode == 0
data = json.loads(result.stdout)
assert data["answer"]
assert len(data["citations"]) > 0
assert "routing_trace" in data
```

#### 场景 2：多轮对话（interactive 子命令）

**目标**：验证多轮对话上下文记忆

**自动化方案**：使用 `subprocess.Popen` + stdin pipe 模拟交互

**步骤**（通过 stdin pipe 输入）：
```
2024
基金经理是谁？
他有什么投资经验？
前十大持仓是什么？
/history
exit
```

**验证点**：
- 启动时显示多轮对话提示（"支持多轮对话"）
- 年份选择后显示可用年份信息
- 第一轮返回基金经理信息（非空回答）
- 第二轮基于上下文返回基金经理背景（非空回答）
- 第三轮返回前十大持仓（Rich Table 格式，包含 `│` 字符）
- `/history` 显示对话摘要（包含 `[用户]` 和 `[助手]`）
- `exit` 正常退出（exit code 0）
- 回答末尾显示追问建议（"您可以追问"）

**自动化断言**：
```python
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True)
stdout, stderr = proc.communicate(input=stdin_input, timeout=300)
assert proc.returncode == 0
assert "支持多轮对话" in stdout
assert "│" in stdout  # Rich Table 格式
assert "[用户]" in stdout  # /history 输出（注意：中文标签）
assert "您可以追问" in stdout  # 追问建议
```

#### 场景 3：Rich Table 格式化

**目标**：验证表格数据以 Rich Table 显示

**步骤**：在场景 2 中已覆盖（第三轮查询持仓）

**补充验证**：
```bash
# 对比 --plain 模式
uv run fund-checklist interactive \
  --fund-code 004393 \
  --work-dir .fund_checklist_e2e_004393 \
  --plain
# stdin: 2024\n前十大持仓是什么？\nexit
```

**验证点**：
- 默认模式：输出包含 `│`、`─`、`┌`、`┐` 等 Rich Table 字符
- `--plain` 模式：输出为原始 Markdown 表格（`|` 分隔）

#### 场景 4：--label 会话恢复

**目标**：验证 `--label` 参数的会话持久化与恢复

**自动化方案**：两次 `subprocess.Popen` 调用，第二次用 `--label` 恢复

**步骤**：
```bash
# 第一次：创建会话并对话
uv run fund-checklist interactive \
  --fund-code 004393 \
  --label test-session-1 \
  --work-dir .fund_checklist_e2e_004393
# stdin: 2024\n基金经理是谁？\nexit

# 第二次：恢复会话
uv run fund-checklist interactive \
  --fund-code 004393 \
  --label test-session-1 \
  --work-dir .fund_checklist_e2e_004393
# stdin: 2024\n/history\nexit
```

**验证点**：
- 第一次启动显示 `[新建会话 'test-session-1']`
- 第二次启动显示 `[恢复会话 'test-session-1']` + "已有 N 轮对话"
- 第二次 `/history` 包含第一次的对话记录

**自动化断言**：
```python
# 第一次
out1 = run_interactive(label="test-session-1", inputs=["2024", "基金经理是谁？", "exit"])
assert "[新建会话" in out1

# 第二次
out2 = run_interactive(label="test-session-1", inputs=["2024", "/history", "exit"])
assert "[恢复会话" in out2
assert "已有" in out2 and "轮对话" in out2
assert "基金经理" in out2  # /history 包含第一次的记录
```

### 3.2 5 年年报 LLM 写作测试场景

#### 场景 5：生成 5 年年报分析报告（含章节审计）

**目标**：验证 8 章分析报告生成 + 章节级审计产物

**前置条件**：`DEEPSEEK_API_KEY` 已设置（`requires_llm` fixture）

**步骤**：
```bash
uv run fund-checklist generate \
  --fund-code 004393 \
  --fund-name '安信企业价值优选混合型证券投资基金' \
  --year 2024 \
  --years 2020,2021,2022,2023,2024 \
  --format markdown \
  --llm \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- 生成 `reports/004393-2024-analysis.md`
- 生成 `reports/004393-2024-analysis.meta.json`
- 报告包含 8 个章节（Ch0-Ch7）
- 每个章节包含数据表格 + LLM 定性分析
- 章节审计产物生成：`audit_artifacts/chapter_1_audit.json` 至 `chapter_6_audit.json`（Ch1-6 保证生成；Ch0/Ch7 仅在 Ch1-6 全部 passed 时生成）

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
assert result.returncode == 0

work_dir = Path(".fund_checklist_e2e_004393")
assert (work_dir / "reports" / "004393-2024-analysis.md").exists()
assert (work_dir / "reports" / "004393-2024-analysis.meta.json").exists()

# 检查章节审计产物（Ch1-6 保证生成）
for ch_id in range(1, 7):
    audit_file = work_dir / "audit_artifacts" / f"chapter_{ch_id}_audit.json"
    assert audit_file.exists(), f"缺少审计产物: {audit_file}"
    data = json.loads(audit_file.read_text())
    assert "score" in data
    assert "violations" in data  # 注意：不是 "findings"
    assert "recommendation" in data  # 注意：不是 "decision"

# 检查报告内容
report = (work_dir / "reports" / "004393-2024-analysis.md").read_text()
for ch in range(8):
    assert f"Ch{ch}" in report or f"第{ch+1}章" in report
```

#### 场景 6：多年度数据聚合

**目标**：验证 5 年数据聚合

**步骤**：
```bash
uv run fund-checklist multi-year \
  --fund-code 004393 \
  --years 2020,2021,2022,2023,2024 \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 包含 5 年业绩数据
- 每年数据包含对应年份标识

#### 场景 7：信号评分（JSON 输出）

**目标**：验证基金类型感知的信号评分

**前置条件**：`DEEPSEEK_API_KEY` 已设置

**步骤**：
```bash
uv run fund-checklist generate \
  --fund-code 004393 \
  --fund-name '安信企业价值优选混合型证券投资基金' \
  --year 2024 \
  --years 2020,2021,2022,2023,2024 \
  --format json \
  --llm \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 为合法 JSON
- JSON 包含 `fund_code`（值为 `"004393"`）
- JSON 包含 `report_year`（值为 `2024`）
- JSON 包含 `chapters`（长度为 8 的列表）
- JSON 包含 `metadata`（字典）
- JSON 包含 `output_path`（字符串）
- 每个 chapter 包含 `chapter_id`（0-7）、`title`、`content`、`data_sources`

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
assert result.returncode == 0
data = json.loads(result.stdout)
assert data["fund_code"] == "004393"
assert data["report_year"] == 2024
assert len(data["chapters"]) == 8
for ch in data["chapters"]:
    assert "chapter_id" in ch
    assert "title" in ch
    assert "content" in ch
    assert "data_sources" in ch
```

### 3.3 披露完整性审计测试场景

#### 场景 8：披露完整性审计（audit 命令）

**目标**：验证 `audit` 命令的披露完整性审计

**说明**：`audit` 是**披露完整性审计**（检查年报是否包含必要披露项），不是章节级审计。章节级审计嵌入在 `generate` 流程中（场景 5 已覆盖）。

**前置条件**：已导入年报

**步骤**：
```bash
uv run fund-checklist audit \
  --fund-code 004393 \
  --year 2024 \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 为合法 JSON
- JSON 包含 `fund_code`、`year`、`document_id`、`disclosures`（列表）、`summary`
- `disclosures` 每项包含披露项信息

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
assert result.returncode == 0
data = json.loads(result.stdout)
assert data["fund_code"] == "004393"
assert data["year"] == 2024
assert "disclosures" in data
assert "summary" in data
```

#### 场景 9：深度披露完整性审计（deep-audit 命令）

**目标**：验证 `deep-audit` 命令的深度披露完整性审计

**步骤**：
```bash
uv run fund-checklist deep-audit \
  --fund-code 004393 \
  --year 2024 \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 为合法 JSON
- JSON 包含 `fund_code`、`year`、`document_id`、`audit_results`（列表）、`summary`

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
assert result.returncode == 0
data = json.loads(result.stdout)
assert data["fund_code"] == "004393"
assert "audit_results" in data
assert "summary" in data
```

### 3.4 修复能力测试场景

#### 场景 10：repair --chapter（局部修复）

**目标**：验证局部修复功能

**前置条件**：场景 5 已执行（报告 + 审计产物已生成）

**步骤**：
```bash
uv run fund-checklist repair \
  --fund-code 004393 \
  --year 2024 \
  --chapter 3,5 \
  --llm \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 包含修复结果（指定章节被修复）
- 修复后报告已更新

#### 场景 11：fix --chapter（占位符补强）

**目标**：验证占位符补强功能

**前置条件**：场景 5 已执行（报告已生成）

**步骤**：
```bash
uv run fund-checklist fix \
  --fund-code 004393 \
  --chapter 3 \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 包含 "第 3 章修复完成"
- stdout 包含 "补强占位符: N"（N ≥ 0）
- stdout 包含 "保留占位符: N"

**自动化断言**：
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
assert result.returncode == 0
assert "第 3 章修复完成" in result.stdout
assert "补强占位符:" in result.stdout
assert "保留占位符:" in result.stdout
```

#### 场景 12：regenerate --chapter（整章重建）

**目标**：验证整章重建功能

**前置条件**：场景 5 已执行（报告已生成）

**步骤**：
```bash
uv run fund-checklist regenerate \
  --fund-code 004393 \
  --year 2024 \
  --chapter 3 \
  --llm \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 包含重建结果
- 重建后报告已更新

#### 场景 13：repair --auto（审计分数驱动自动策略）

**目标**：验证审计分数驱动的修复策略自动选择

**前置条件**：场景 5 已执行

**步骤**：
```bash
uv run fund-checklist repair \
  --fund-code 004393 \
  --year 2024 \
  --chapter 1,2,3,4,5,6,7 \
  --auto \
  --llm \
  --work-dir .fund_checklist_e2e_004393
```

**验证点**：
- exit code 0
- stdout 显示自动策略选择（skip/repair/regenerate）
- 高分章节（≥80）标记为 skip
- 低分章节（<60）标记为 regenerate
- 中分章节（60-79）标记为 repair

---

## 4. 测试编排

### 4.1 执行顺序

```
环境准备 → 场景 6（multi-year）→ 场景 5（generate + 章节审计）
  → 场景 7（signal JSON）→ 场景 8（audit 披露完整性）
  → 场景 9（deep-audit）→ 场景 10（repair）→ 场景 11（fix）
  → 场景 12（regenerate）→ 场景 13（auto repair）
  → 场景 1（ask 流式）→ 场景 1b（ask JSON）
  → 场景 2（interactive 多轮）→ 场景 3（Rich Table）
  → 场景 4（--label 恢复）
```

### 4.2 pytest 测试文件结构

```
tests/e2e/
  conftest.py              # 公共 fixtures（work_dir、document_id、import_setup、requires_llm）
  test_e2e_ask.py          # 场景 1、1b
  test_e2e_interactive.py  # 场景 2、3、4
  test_e2e_generate.py     # 场景 5、6、7
  test_e2e_audit.py        # 场景 8、9（披露完整性审计）
  test_e2e_repair.py       # 场景 10、11、12、13
```

---

## 5. 预期输出

### 5.1 对话能力预期输出

**场景 1（ask 流式）**：
```
基金经理是张三，具有 10 年投资经验，2015 年加入安信基金...
（流式逐字输出，无 JSON 包装）
```

**场景 1b（ask JSON）**：
```json
{
  "answer": "基金经理是张三，具有 10 年投资经验...",
  "citations": [
    {
      "document_id": "004393-2024-annual_report-abc12345",
      "fund_code": "004393",
      "fund_name": "安信企业价值优选混合型证券投资基金",
      "year": 2024,
      "report_type": "annual_report"
    }
  ],
  "routing_trace": [
    {
      "query": "基金经理是谁？",
      "profile_name": "fund_manager",
      "result_kind": "success",
      "failure_code": null
    }
  ]
}
```

**场景 2（interactive）**：
```
正在查找基金 004393 的年报…
基金: 安信企业价值优选混合型证券投资基金 (004393)
可用年份: 2020, 2021, 2022, 2023, 2024
请选择年份 [2024]: 

已选择 2024 年年报。输入问题开始对话，/help 查看命令，exit 退出。
提示：支持多轮对话，可以追问上一个问题的细节。输入 /help 查看命令。

> 基金经理是谁？
基金经理是张三，具有 10 年投资经验...
您可以追问：这位基金经理的从业经历、管理其他基金的情况、或任职以来的业绩表现。

> 他有什么投资经验？
张三曾任某基金公司研究员，2015 年加入安信基金...
您可以追问：...

> 前十大持仓是什么？
┌────────────┬──────────┬──────┐
│ 股票名称   │ 代码     │ 占比 │
├────────────┼──────────┼──────┤
│ 贵州茅台   │ 600519   │ 5.2% │
│ ...        │ ...      │ ...  │
└────────────┴──────────┴──────┘
您可以追问：重仓股的变化趋势、行业集中度、或与基准的偏离情况。

> /history
最近 10 轮对话：
1. [用户] 基金经理是谁？
2. [助手] 基金经理是张三...
3. [用户] 他有什么投资经验？
4. [助手] 张三曾任某基金公司研究员...
5. [用户] 前十大持仓是什么？
6. [助手] ┌────────────┬──────────┬──────┐...

> exit
再见。
```

### 5.2 5 年年报 LLM 写作预期输出

**场景 5（generate markdown）**：
```
（stdout 包含 JSON 格式的生成结果）
exit code 0
```

**落盘文件**：
- `reports/004393-2024-analysis.md` — 完整 8 章报告
- `reports/004393-2024-analysis.meta.json` — 元数据
- `audit_artifacts/chapter_1_audit.json` — Ch1 审计结果（保证）
- `audit_artifacts/chapter_2_audit.json` — Ch2 审计结果（保证）
- ...
- `audit_artifacts/chapter_6_audit.json` — Ch6 审计结果（保证）
- `audit_artifacts/chapter_0_audit.json` — Ch0 审计结果（可选，Ch1-6 全 passed 时生成）
- `audit_artifacts/chapter_7_audit.json` — Ch7 审计结果（可选，Ch1-6 全 passed 时生成）

**审计 JSON 结构**：
```json
{
  "chapter_id": 1,
  "score": 85,
  "programmatic_score": 90,
  "llm_score": 80,
  "recommendation": "pass",
  "audit_time": "2026-07-27T10:00:00",
  "violations": [
    {
      "code": "V001",
      "category": "data_consistency",
      "severity": "warning",
      "description": "...",
      "location": "...",
      "suggested_fix": "...",
      "evidence": "..."
    }
  ]
}
```

### 5.3 披露完整性审计预期输出

**场景 8（audit）**：
```json
{
  "fund_code": "004393",
  "year": 2024,
  "document_id": "004393-2024-annual_report-XXXXXXXX",
  "disclosures": [
    {
      "item_name": "...",
      "is_present": true,
      "location": "..."
    }
  ],
  "summary": {
    "total_items": 22,
    "present_items": 20,
    "missing_items": 2
  }
}
```

### 5.4 修复能力预期输出

**场景 11（fix）**：
```
第 3 章修复完成：
补强占位符: 2
保留占位符: 0
```

---

## 6. 风险与缓解

### 6.1 风险矩阵

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| LLM API 调用失败（网络/key） | 中 | 测试中断 | `requires_llm` fixture 自动 skip；设置 timeout=600s |
| 5 年年报 PDF 缺失 | 高 | 测试不完整 | conftest 检查 PDF 存在性，缺失时 `pytest.skip()` |
| interactive 场景自动化不稳定 | 中 | 测试 flaky | 固定输入序列；`communicate(timeout=300)` |
| ask 命令需要 document_id | 高 | 场景 1 阻塞 | conftest 从 catalog 自动提取 document_id |
| 章节审计产物 Ch0/Ch7 可能不存在 | 中 | 场景 5 断言失败 | 只断言 Ch1-6（保证生成）；Ch0/Ch7 可选验证 |
| 章节编号混淆（0-indexed vs 1-indexed） | 低 | 参数错误 | conftest 提供 chapter_id 映射 helper |
| DEEPSEEK_API_KEY 缺失 | 中 | LLM 场景全部 skip | `requires_llm` fixture 检测 + `pytest.skip()` |

---

## 7. 成功标准

### 7.1 对话能力

- [ ] `ask` 子命令流式模式返回非空文本回答（exit code 0）
- [ ] `ask --no-stream` 返回合法 JSON，包含 `answer`、`citations`、`routing_trace`
- [ ] `interactive` 子命令支持多轮对话上下文记忆（3 轮以上）
- [ ] Rich Table 格式化输出正确（包含 `│` 字符）
- [ ] `--plain` 参数保留原始 Markdown 文本
- [ ] `/history` 命令显示对话摘要（使用 `[用户]`/`[助手]` 标签）
- [ ] 追问建议在分析性回答末尾出现
- [ ] `--label` 会话恢复正常工作

### 7.2 5 年年报 LLM 写作

- [ ] 5 年年报数据导入成功
- [ ] 8 章分析报告生成成功（落盘文件存在）
- [ ] 每个章节包含数据表格 + LLM 定性分析
- [ ] 多年度数据聚合正确（5 年数据）
- [ ] JSON 输出包含完整结构（`fund_code`、`report_year`、`chapters`、`metadata`、`output_path`）
- [ ] 章节审计产物 Ch1-6 全部生成（`chapter_1_audit.json` 至 `chapter_6_audit.json`）
- [ ] 审计 JSON 包含 `score`、`violations`、`recommendation`

### 7.3 披露完整性审计

- [ ] `audit` 命令返回合法 JSON，包含 `disclosures` 和 `summary`
- [ ] `deep-audit` 命令返回合法 JSON，包含 `audit_results` 和 `summary`

### 7.4 修复能力

- [ ] `repair --chapter 3,5` 只修复指定章节（exit code 0）
- [ ] `fix --chapter 3` 补强占位符（stdout 包含修复统计）
- [ ] `regenerate --chapter 3` 整章重建（exit code 0）
- [ ] `repair --auto` 自动选择修复策略（skip/repair/regenerate）

---

## 8. 实施计划

### 8.1 阶段 1：环境准备 + conftest（2 天）

- 确认 PDF 存在 + import + document_id 从 catalog 提取
- 实现 `conftest.py`（import_setup fixture、work_dir 管理、requires_llm fixture）
- 验证 import 链路

### 8.2 阶段 2：CLI 子命令测试（4 天）

- 实现场景 1、1b（ask 流式 + JSON）
- 实现场景 5、6、7（generate + multi-year + signal + 章节审计）
- 实现场景 8、9（audit + deep-audit 披露完整性）
- 实现场景 10、11、12、13（repair + fix + regenerate + auto）

### 8.3 阶段 3：interactive 测试（3 天）

- 实现场景 2（多轮对话 subprocess）
- 实现场景 3（Rich Table + --plain 对比）
- 实现场景 4（--label 会话恢复）

### 8.4 阶段 4：集成 + 稳定性（3 天）

- 全场景串联测试
- 稳定性验证（3 次连续运行无 flaky）
- 性能基线记录

---

**设计者**：AgentCodex
**最后更新**：2026-07-27（v3，DS 二审修复版）
**状态**：待 DS 三审
