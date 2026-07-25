# Phase 7 端到端验收：多轮对话 + 会话记忆

## 目标

实现 `fund-checklist interactive` 多轮对话模式，支持会话持久化和上下文记忆，使用基金代码 011649（易方达逆向投资混合）进行端到端验证。

## 范围

### 输入
- **基金代码**：011649
- **基金名称**：易方达逆向投资混合
- **年报数据**：2021-2025 年度报告（5 年）
- **PDF 位置**：`基金年报/011649_易方达逆向投资混合_*.pdf`

### Phase 7 Slice 列表（待裁决确认）

| Slice | 内容 | 依赖 |
|-------|------|------|
| **7A** | Session 数据模型 + 持久化（filesystem JSON） | 无 |
| **7B** | Service 层 `chat_turn` use case | 7A |
| **7C** | Host 多轮会话托管 | 7B |
| **7D** | CLI `interactive` 子命令 | 7C |
| **7E** | 会话恢复 + label 支持 | 7D |

### 输出

1. **CLI 入口**：`fund-checklist interactive --document-id <id>`
2. **会话持久化**：`{work_dir}/sessions/{session_id}.json`
3. **多轮对话**：支持上下文记忆，最近 3 轮强制保留
4. **会话恢复**：`fund-checklist interactive --label my-session`

## 裁决前置条件

### 必须裁决项

| 裁决项 | 选项 A（推荐） | 选项 B | 选项 C |
|--------|---------------|--------|--------|
| **会话存储** | filesystem JSON（与现有 catalog 一致） | SQLite（适合复杂查询） | 不持久化（仅内存） |
| **记忆模型** | Pinned State + Recent Turns（两层） | 三层（+episode summary） | 单层（仅 Recent Turns） |
| **最近轮数** | 强制保留最近 3 轮 | 强制保留最近 5 轮 | 按 token budget 动态 |
| **会话恢复** | 支持 `--label` 恢复 | 不支持（每次新建） | 支持但不推荐 |
| **并发限制** | 不保证多进程安全 | 文件锁保证安全 | 不持久化则无此问题 |
| **上下文治理** | Phase 7 实现基础版 | 推迟到 Phase 8 | 不实现 |

### 推荐裁决方案

```yaml
会话存储: filesystem JSON
记忆模型: Pinned State + Recent Turns（两层）
最近轮数: 3 轮
会话恢复: 支持 --label
并发限制: 不保证多进程安全（单实例限制）
上下文治理: Phase 7 实现基础版（token budget 截断）
```

## 禁止事项

- 禁止破坏 Phase 5 的 `ask` 子命令行为
- 禁止破坏 Phase 6 的基金类型感知
- 禁止引入 SQLite 或其他外部依赖
- 禁止实现 episode summary（Phase 7 可选，推迟到 Phase 8）
- 禁止多进程并发写入同一 session 文件
- 禁止跳过投资建议关键词检测

## 验证标准

### 功能验证

1. **会话创建**（7A）
   - `fund-checklist interactive --document-id <id>` 成功进入 REPL
   - 会话文件 `{work_dir}/sessions/{session_id}.json` 正确创建

2. **多轮对话**（7B-C）
   - 第一轮："基金经理是谁？" → 返回基金经理信息
   - 第二轮："他的任期有多长？" → 基于上下文回答
   - 第三轮："规模有多大？" → 基于上下文回答

3. **上下文记忆**（7C）
   - Pinned State 记录 `document_id`、`fund_code`、`fund_name`
   - Recent Turns 强制保留最近 3 轮
   - 超出部分按 token budget 截断

4. **会话恢复**（7E）
   - `fund-checklist interactive --label my-session` 恢复历史会话
   - 历史 turns 正确加载
   - Pinned State 正确重建

### 端到端验证

```bash
# 1. 导入 5 年年报（如果未导入）
uv run fund-checklist import 基金年报/011649_易方达逆向投资混合_2021_annual_report.pdf
uv run fund-checklist import 基金年报/011649_易方达逆向投资混合_2022_annual_report.pdf
uv run fund-checklist import 基金年报/011649_易方达逆向投资混合_2023_annual_report.pdf
uv run fund-checklist import 基金年报/011649_易方达逆向投资混合_2024_annual_report.pdf
uv run fund-checklist import 基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf

# 2. 多轮对话测试
uv run fund-checklist interactive --document-id 011649-2025-annual_report-xxx
> 基金经理是谁？
< 基金经理是...
> 他的任期有多长？
< 任期为...
> 规模有多大？
< 规模为...
> exit

# 3. 会话恢复测试
uv run fund-checklist interactive --label test-011649
# 应显示历史对话

# 4. 会话持久化验证
cat .fund_checklist_e2e_011649/sessions/*.json
```

### 验收标准

| 检查项 | 阈值 | 验证方式 |
|--------|------|----------|
| 会话创建 | 成功 | REPL 正常进入 |
| 多轮对话 | 3 轮以上 | 上下文正确传递 |
| 会话持久化 | 文件存在 | JSON 文件非空 |
| 会话恢复 | 成功 | 历史对话正确加载 |
| 投资建议拦截 | 0 次通过 | 每轮都检测 |
| ask 命令回归 | 0 失败 | 现有测试通过 |

## 执行顺序

1. **裁决确认**：确认会话模型、记忆模型、CLI 入口等裁决项
2. **7A：Session 数据模型**：定义 Session、Turn 数据结构，实现 filesystem JSON 持久化
3. **7B：chat_turn use case**：Service 层实现多轮对话逻辑
4. **7C：Host 多轮会话托管**：Host 层管理会话生命周期
5. **7D：CLI interactive 子命令**：实现 REPL 模式
6. **7E：会话恢复 + label 支持**：实现 `--label` 参数
7. **端到端验证**：使用 011649 基金测试完整流程

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 会话文件损坏 | 原子写入（临时文件 + os.replace） |
| 上下文超限 | token budget 截断 + 强制保留 3 轮 |
| 投资建议检测 | 每轮都经过关键词检测 |
| ask 命令回归 | 完整回归测试 |

## 对标 Dayu Agent

| 能力 | Dayu | Phase 7 目标 | 差距 |
|------|------|-------------|------|
| 会话存储 | conversation_store.py | filesystem JSON | 简化版 |
| 记忆模型 | Pinned State + episode summary + compaction | Pinned State + Recent Turns（两层） | 无 episode summary |
| 会话恢复 | 支持 | 支持 --label | 对齐 |
| 上下文治理 | context_budget.py（软/硬上限） | 基础版（token budget 截断） | 简化版 |
| 多轮对话 | interactive + WeChat | interactive（CLI） | 无 WeChat |
