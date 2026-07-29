# Goal: Phase 7.2 端到端测试验证

**创建时间**：2026-07-27
**目标状态**：待启动
**版本**：v2（DS 二审修复版）
**关联文档**：
- `docs/e2e-test-design.md`（端到端测试设计真源，v3）
- `docs/implementation-control.md`（真源执行面板）
- `AGENTS.md`（项目规则）
- `.sisyphus/plans/phase7.2-implementation.md`（Phase 7.2 实施计划）

---

## 1. 目标定义

### 核心目标
对 Phase 7.2 + 7.1a 已交付的全部能力开展端到端测试验证，覆盖对话能力（ask/interactive）、5 年年报 LLM 写作（generate）、披露完整性审计（audit/deep-audit）、修复能力（repair/regenerate/fix）四条链路。

### 具体交付物
- `tests/e2e/` 目录：6 个测试文件 + 1 个 conftest
- 13 个端到端测试场景全部通过
- 全量回归测试不回退（768 passed 基线，8 个 pre-existing failure 不计入）
- 测试设计文档 `docs/e2e-test-design.md`（v3）已实施

### Definition of Done (DoD)

**对话能力**：
- [ ] `ask` 流式模式返回非空文本回答（exit code 0）
- [ ] `ask --no-stream` 返回合法 JSON，包含 `answer`、`citations`、`routing_trace`
- [ ] `interactive` 多轮对话上下文记忆（3 轮以上）
- [ ] Rich Table 格式化输出正确
- [ ] `--plain` 保留原始 Markdown
- [ ] `/history` 显示对话摘要（使用 `[用户]`/`[助手]` 标签）
- [ ] 追问建议在分析性回答末尾出现
- [ ] `--label` 会话恢复正常工作

**5 年年报 LLM 写作**：
- [ ] 8 章分析报告生成成功（落盘文件存在）
- [ ] JSON 输出包含完整结构（`fund_code`、`report_year`、`chapters`、`metadata`、`output_path`）
- [ ] 多年度数据聚合正确（5 年）
- [ ] 章节审计产物 Ch1-6 全部生成（`chapter_1_audit.json` 至 `chapter_6_audit.json`）
- [ ] 审计 JSON 包含 `score`、`violations`、`recommendation`

**披露完整性审计**：
- [ ] `audit` 命令返回合法 JSON，包含 `disclosures` 和 `summary`
- [ ] `deep-audit` 命令返回合法 JSON，包含 `audit_results` 和 `summary`

**修复能力**：
- [ ] `repair --chapter 3,5` 只修复指定章节
- [ ] `fix --chapter 3` 补强占位符
- [ ] `regenerate --chapter 3` 整章重建
- [ ] `repair --auto` 自动选择修复策略

**回归**：
- [ ] 全量回归 ≥768 passed（不回退，8 个 pre-existing failure 不计入）

---

## 2. 范围定义

### 包含范围（In Scope）

**阶段 1：环境准备 + conftest**：
- T1: 确认 PDF 存在 + import + document_id 从 catalog 提取
- T2: conftest.py 实现（import_setup fixture、work_dir 管理、requires_llm fixture）

**阶段 2：CLI 子命令测试**：
- T3: ask 流式 + JSON（场景 1、1b）
- T4: generate + multi-year + signal + 章节审计（场景 5、6、7）
- T5: audit + deep-audit 披露完整性（场景 8、9）
- T6: repair + fix + regenerate + auto（场景 10、11、12、13）

**阶段 3：interactive 测试**：
- T7: 多轮对话 subprocess（场景 2）
- T8: Rich Table + --plain（场景 3）

**阶段 4：集成 + 稳定性**：
- T9: --label 会话恢复（场景 4）
- T10: 全场景串联
- T11: 稳定性验证（3 次连续无 flaky）
- T12: 全量回归验证

### 排除范围（Out of Scope）

- **性能基准测试**：不在本次范围，后续单独安排
- **多基金交叉测试**：本次只用 004393
- **LLM 输出质量评分**：只验证链路通，不评判 LLM 回答质量
- **新增 CLI 子命令**：只测试已有 15 个命令
- **mock LLM 测试**：真实 LLM 场景走真实 API；key 缺失时自动 skip

---

## 3. 禁止事项（Must NOT Have / Guardrails）

### 硬性禁止
1. **不修改 `fund_agent/` 核心业务代码**：本次是测试任务。允许例外：为 e2e 可测试性新增 CLI 参数（如 `--chapter`、`--llm`）属于测试基础设施，不算核心业务代码修改
2. **不新增 CLI 子命令**：只测试已有 15 个命令
3. **不修改现有测试文件**：新增 `tests/e2e/` 目录，不触碰 `tests/fund/`
4. **不删除或覆盖已有 work-dir**：每个场景用独立 work-dir 避免数据污染
5. **不评判 LLM 输出质量**：只验证链路通，不评判回答准确性

### 测试规范
6. **每个测试场景必须可独立运行**：不依赖其他场景的执行顺序
7. **每个测试必须有 timeout**：CLI 命令 600s，interactive 300s
8. **测试失败必须有清晰错误信息**：assert 失败时打印实际输出
9. **禁止用 sleep 代替状态检查**：使用 `subprocess.communicate()` 而非 `time.sleep()`
10. **DEEPSEEK_API_KEY 缺失时自动 skip**：不硬编码 API key

---

## 4. 验证标准（Acceptance Criteria）

### 4.1 场景级验收

| 场景 | 验收标准 | 自动化断言 |
|------|---------|-----------|
| 1 (ask 流式) | exit code 0 + stdout 非空 | `assert returncode == 0 and len(stdout) > 0` |
| 1b (ask JSON) | 合法 JSON + answer/citations/routing_trace | `json.loads()` + key check |
| 2 (interactive 多轮) | 3 轮对话 + /history + exit 0 | stdout 关键词匹配（`[用户]`/`[助手]`） |
| 3 (Rich Table) | `│` 字符出现 | `assert "│" in stdout` |
| 4 (--label 恢复) | 新建 + 恢复 + 历史保留 | stdout `[新建会话]` + `[恢复会话]` |
| 5 (generate + 章节审计) | 8 章报告 + Ch1-6 审计 JSON | 文件存在 + `score`/`violations`/`recommendation` key check |
| 6 (multi-year) | 5 年数据 | stdout 年份匹配 |
| 7 (signal JSON) | 合法 JSON + 8 chapters | `json.loads()` + len check |
| 8 (audit 披露) | 合法 JSON + disclosures + summary | `json.loads()` + key check |
| 9 (deep-audit 披露) | 合法 JSON + audit_results + summary | `json.loads()` + key check |
| 10 (repair) | exit 0 + 指定章节修复 | returncode + stdout check |
| 11 (fix) | exit 0 + "修复完成" | stdout 关键词匹配 |
| 12 (regenerate) | exit 0 + 章节重建 | returncode check |
| 13 (auto repair) | 策略自动选择 | stdout 包含 skip/repair/regenerate |

### 4.2 最终验收命令

```bash
# e2e 测试全部通过
uv run pytest tests/e2e/ -v --tb=short

# 全量回归不回退
uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ -v --tb=short

# 落盘文件检查
ls -la .fund_checklist_e2e_004393/reports/
ls -la .fund_checklist_e2e_004393/audit_artifacts/
```

### 4.3 Final Checklist

- [ ] 13 个场景全部 PASS
- [ ] 全量回归 ≥768 passed（8 个 pre-existing failure 不计入）
- [ ] 无 flaky（3 次连续运行结果一致）
- [ ] 测试文件结构符合 `tests/e2e/` 规划
- [ ] conftest.py 有中文 docstring
- [ ] 每个测试函数有中文 docstring

---

## 5. 执行策略

### 5.1 任务分组

**阶段 1（串行）**：
- T1（quick）: PDF 确认 + import + document_id 提取
- T2（quick）: conftest.py 实现（依赖 T1）

**阶段 2（3 个并行）**：
- T3（quick）: ask 测试（依赖 T2）
- T4（quick）: generate 测试（依赖 T2）
- T5（quick）: audit 披露完整性测试（依赖 T2）

**阶段 3（2 个并行）**：
- T6（quick）: repair/fix/regenerate 测试（依赖 T4）
- T7（quick）: interactive 多轮测试（依赖 T2）
- T8（quick）: Rich Table 测试（依赖 T7）

**阶段 4（串行）**：
- T9（quick）: --label 会话恢复（依赖 T7）
- T10（quick）: 全场景串联
- T11（quick）: 稳定性验证
- T12（quick）: 全量回归

### 5.2 关键路径

T1 → T2 → T4 → T6 → T10 → T12

### 5.3 预计工期

13-15 天（阶段 1: 2 天，阶段 2: 4 天，阶段 3: 3 天，阶段 4: 4 天）

---

## 6. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| PDF 缺失导致 import 失败 | 高 | T1 阻塞 | 使用仓库已有 004393 2024 年报；缺失年份 pytest.skip() |
| LLM API 限流/超时 | 中 | T3-T6 flaky | timeout=600s；失败时记录错误码重试 1 次 |
| interactive subprocess 不稳定 | 中 | T7-T8 flaky | 固定输入序列；communicate(timeout=300) |
| 章节审计产物 Ch0/Ch7 可能不存在 | 中 | T4 断言失败 | 只断言 Ch1-6（保证生成）；Ch0/Ch7 可选验证 |
| 章节编号混淆 | 低 | 参数错误 | conftest 提供 chapter_id 映射 helper |
| DEEPSEEK_API_KEY 缺失 | 中 | LLM 场景全部 skip | requires_llm fixture 检测 + pytest.skip() |
| 全量回归基线漂移 | 低 | T12 误报 | 记录 768 基线；只检查 ≥ 不检查 == |

---

## 7. 进度追踪

### 任务状态

**阶段 1**：
- [ ] T1: PDF 确认 + import + document_id 提取
- [ ] T2: conftest.py 实现

**阶段 2**：
- [ ] T3: ask 流式 + JSON 测试
- [ ] T4: generate + multi-year + signal + 章节审计测试
- [ ] T5: audit + deep-audit 披露完整性测试

**阶段 3**：
- [ ] T6: repair + fix + regenerate + auto 测试
- [ ] T7: interactive 多轮测试
- [ ] T8: Rich Table 测试

**阶段 4**：
- [ ] T9: --label 会话恢复测试
- [ ] T10: 全场景串联
- [ ] T11: 稳定性验证
- [ ] T12: 全量回归验证

---

## 8. 与 Phase 7.2 的关系

本 Goal 是 Phase 7.2 实施完成后的验证阶段：

- Phase 7.2 实施（10 个实现任务 + 2 个测试任务）→ ✅ 已完成
- Phase 7.1a 集成补完（4 项 P0）→ ✅ 已完成
- **本 Goal：端到端测试验证（13 个场景）** → 待启动

发现的 bug 记录为 issue。允许例外：为 e2e 可测试性新增 CLI 参数（如 audit --chapter/--llm）属于测试基础设施，不算核心业务代码修改。

---

## 9. 使用方法

### 启动 Goal
```
/goal phase7.2-e2e
```

### 查看进度
```
/goal status
```

### 完成任务
```
/goal complete <task-id>
```

### 完成 Goal
当所有任务完成且验证通过后：
```
/goal done
```

---

## 10. DS 审核记录

### 第一轮审核（2026-07-27）

**审核人**：AgentDS
**审核结论**：NEEDS_FIX（12 项，含 3 P0）

**P0 项**：
1. 场景 1 ask 命令参数错误 → v2 已修复
2. 场景 1 预期输出格式与代码不一致 → v2 已修复
3. 缺少 fix 子命令测试场景 → v2 已修复（新增场景 11）

### 第二轮审核（2026-07-27）

**审核人**：AgentDS
**审核结论**：NEEDS_FIX（11 项，含 5 P0）

**P0 项**：
1. Scene 8/9 audit CLI 参数不存在 → v2 裁决：删除独立场景，章节审计合并到 Scene 5；audit 改为披露完整性审计
2. Scene 1 read 命令缺少必需参数 → v2 改用 catalog 提取 document_id
3. Scene 8 审计 JSON 字段名错误 → v2 改为 violations/recommendation
4. "237 passed 基线" 不符 → v2 改为 768 passed
5. 禁止事项与 P0 矛盾 → v2 增加例外条款

**P1 项**：
- /history 角色标签 → v2 改为 `[用户]`/`[助手]`
- 审计产物数量 → v2 改为只断言 Ch1-6
- document_id 获取方式 → v2 改用 catalog
- 任务编号不连续 → v2 补回 T9

**最终状态**：v2 待 DS 三审

---

**Goal 创建者**：AgentCodex
**最后更新**：2026-07-27（v2，DS 二审修复版）
**审核状态**：待 DS 三审
