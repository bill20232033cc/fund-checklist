# Review: e2e-test-design.md + phase7.2-e2e-goal.md

**Review date**: 2026-07-27
**Reviewer**: DS (第二轮)
**Targets**:
- `docs/e2e-test-design.md` (v2, claims 12 DS findings fixed)
- `.sisyphus/goals/phase7.2-e2e-goal.md`

**Method**: 逐字段与实际 CLI 代码 (`fund_agent/cli/main.py`)、audit pipeline (`fund_agent/service/audit_pipeline.py`)、chat service 交叉验证。

---

## Document 1: e2e-test-design.md

**Verdict: NEEDS_FIX**

无法通过 — 3 个 P0 阻塞项会导致测试命令直接崩溃或断言失败。

### P0 — 阻塞项（测试无法执行）

**1-NEEDS_FIX-P0: Scene 8/9 `audit`/`deep-audit` CLI 参数不存在**

- **位置**: Section 3.3, Scene 8 (line 377-383), Scene 9 (line 414-419)
- **设计写法**:
  ```
  uv run fund-checklist audit --chapter 1,2,3,4,5,6,7 --llm ...
  uv run fund-checklist deep-audit ... --llm ...
  ```
- **实际代码**: `main.py:188-196` — `audit` parser 只有 `--fund-code`, `--year`, `--work-dir`；`deep-audit` 同理。无 `--chapter`，无 `--llm` 参数。这两个命令是**披露完整性审计**，不是章节级审计。
- **后果**: argparse 拒绝未知参数，测试直接崩溃。
- **证据**:
  ```
  main.py:188: audit_parser.add_argument("--fund-code", required=True)
  main.py:189: audit_parser.add_argument("--year", required=True, type=int)
  main.py:191: audit_parser.add_argument("--work-dir", ...)
  # 无 --chapter，无 --llm
  ```
- **修复建议**: 明确 Scene 8/9 的真实目标。若目标是测试章节级审计管道，它内嵌在 `generate` 流程中（`audit_pipeline.py:1893` `_generate_and_audit_chapter`），没有独立 CLI 入口。若目标是测试 CLI `audit`/`deep-audit` 命令，则需改写场景为披露完整性审计的参数和验证点。

**2-NEEDS_FIX-P0: Scene 1 `read` 命令缺少必需参数**

- **位置**: Section 3.1, Scene 1 (line 113-115)
- **设计写法**:
  ```bash
  uv run fund-checklist read --fund-code 004393 --work-dir ...
  ```
- **实际代码**: `main.py:147-153` — `read` parser 要求 `--pdf` (required), `--fund-name` (required), `--year` (required)。
- **后果**: argparse 拒绝，exit code ≠ 0。
- **证据**:
  ```
  main.py:147: read_parser.add_argument("--pdf", required=True, type=Path)
  main.py:148: read_parser.add_argument("--fund-code", required=True)
  main.py:149: read_parser.add_argument("--fund-name", required=True)
  main.py:150: read_parser.add_argument("--year", required=True, type=int)
  ```
- **修复建议**: 用 `multi-year` 或直接读 catalog 文件获取 `document_id`。`read` 是 PDF 解析+查询命令，不是 catalog 查看命令。

**3-NEEDS_FIX-P0: Scene 8 审计产物 JSON 字段名错误**

- **位置**: Section 3.3, Scene 8 验证点 (line 391), 自动化断言 (line 404-406)
- **设计写法**: `assert "findings" in data` / `assert "decision" in data`
- **实际代码**: `audit_pipeline.py:713-732` `save_audit_decision()` — 写入的 key 是 `violations` (list) 和 `recommendation` (string, 值为 "pass"/"patch"/"regenerate")，没有 `findings`，没有 `decision`。
- **后果**: 断言失败。
- **证据**:
  ```python
  # audit_pipeline.py:713-732
  data = {
      "chapter_id": decision.chapter_id,
      "score": decision.score,
      "programmatic_score": ...,
      "llm_score": ...,
      "recommendation": decision.recommendation,  # string, not dict
      "violations": [...],  # list, not "findings"
  }
  ```
- **修复建议**: 将断言改为 `"violations" in data` 和 `"recommendation" in data`。

### P1 — 会导致测试逻辑错误

**4-NEEDS_FIX-P1: Scene 2 `/history` 输出中角色标签不匹配**

- **位置**: Section 3.1, Scene 2 自动化断言 (line 200)
- **设计写法**: `assert "[user]" in stdout`
- **实际代码**: `main.py:2063` — 输出 `[用户]` 和 `[助手]`，不是 `[user]` 和 `[assistant]`。
- **后果**: 断言失败。`[user]` 字符串永远不会出现在输出中。
- **修复建议**: 改为 `assert "[用户]" in stdout`。

**5-NEEDS_FIX-P1: Scene 5 审计产物数量不保证为 8**

- **位置**: Section 3.2, Scene 5 (line 301-303), 成功标准 7.3 (line 710)
- **设计写法**: `for ch_id in range(8): assert audit_file.exists()` — 期望全部 8 个。
- **实际代码**: `audit_pipeline.py:1914-1944` — Ch0 和 Ch7 仅在 Ch1-6 全部 passed 时才走 `_generate_and_audit_chapter`。若 Ch1-6 有任一失败，Ch0/Ch7 走模板生成（无审计产物）。
- **后果**: 若真实数据下 Ch1-6 不完全通过，断言失败。
- **修复建议**: 断言改为 `for ch_id in range(1, 7)` (只检查 Ch1-6)，Ch0/Ch7 的审计产物作为可选验证。

**6-NEEDS_FIX-P1: Scene 1 获取 document_id 的方式根本性错误**

- **位置**: Section 3.1, Scene 1 (line 112-115)
- **问题**: 设计用 `read` 命令获取 document_id，但 `read` 是 PDF 解析+全文检索命令。正确方式是：
  - 方案 A: 从 `import` 命令的成功输出中提取
  - 方案 B: 从 work_dir 的 `catalog.json` 中读取
  - 方案 C: 用 `multi-year` 命令的 JSON 输出提取
- **修复建议**: conftest 中实现方案 B（直接读 `catalog.json`），最可靠。

**7-NEEDS_FIX-P1: Scene 5 报告内容断言可能匹配不到**

- **位置**: Section 3.2, Scene 5 (line 307-308)
- **设计写法**: `assert f"Ch{ch}" in report or f"第{ch+1}章" in report`
- **问题**: 报告使用中文标题如 `## 第 1 章：投资要点概览`，不会出现 "Ch0" 字符串。`or` 分支的 `第{ch+1}章` 可以匹配，但 `ch=0` 时 `第1章` 确实存在。整体上这个断言偏弱 — 匹配到子字符串不能证明章节内容完整。
- **修复建议**: 改为只检查中文标题格式，如 `f"第{ch+1}章" in report`。

**8-NEEDS_FIX-P1: Scene 8/9 与 CLI 实际功能概念混淆**

- **位置**: Section 3.3 标题 "LLM 审计测试场景" + Scene 8/9 整体
- **问题**: 设计将章节级审计管道（内嵌于 generate 流程的 `_generate_and_audit_chapter`）与 CLI `audit`/`deep-audit`（披露完整性审计）视为同一功能。两者是不同系统：
  - 章节审计: 内部流程，产生 `chapter_X_audit.json`，无独立 CLI
  - 披露审计: CLI `audit`/`deep-audit`，验证披露项完整性，输出 JSON 到 stdout
- **后果**: 测试设计完全对不上实际功能。
- **修复建议**: 明确两种审计的区别。若想测试章节审计，需通过 `generate --llm` 触发。若想测试披露审计，需用正确的 CLI 参数和验证点。

### P2 — 轻微问题

**9-NEEDS_FIX-P2: 风险矩阵 PDF 缺失概率自相矛盾**

- **位置**: Section 6.1 (line 671)
- **设计写法**: PDF 缺失可能性标为"高"，但缓解措施说"使用仓库已有的 004393 2024 年报"
- **问题**: 如果已有，概率不应为"高"。

**10-NEEDS_FIX-P2: Section 2.3 自动化策略表缺少 ask 子命令**

- **位置**: Section 2.3 (line 92)
- 策略表列了 CLI 子命令和 interactive，但没有 `ask`（Scene 1/1b 使用的子命令）。

**11-NEEDS_FIX-P2: Scene 4 `--label` 恢复验证字符串可能不精确**

- **位置**: Section 3.1, Scene 4 (line 260)
- **设计写法**: `assert "[恢复会话" in out2`
- **问题**: `[恢复会话` 是部分匹配，实际完整字符串为 `[恢复会话 'test-session-1'] 已有 N 轮对话，创建于 2026-07-27`。当前断言虽能通过，但无法区分"新建"和"恢复"的错误消息。

---

## Document 2: phase7.2-e2e-goal.md

**Verdict: NEEDS_FIX**

P0 阻塞项涉及基线数字错误和范围/禁止事项与实现现实的根本矛盾。

### P0 — 阻塞项

**12-NEEDS_FIX-P0: "237 passed 基线" 数字不实**

- **位置**: Section 1 DoD (line 52), Section 4.2 (line 135), Section 4.3 (line 145)
- **设计写法**: `全量回归 ≥237 passed（不回退）`
- **实际情况**: `uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ --collect-only` 收集 776 个测试。237 远低于实际收集量。
- **后果**: 若以 237 为基线，可能遗漏大量回归失败。验收标准形同虚设。
- **修复建议**: 运行一次 `uv run pytest tests/fund/cli/ tests/fund/service/ tests/fund/host/ tests/fund/agent/ -v --tb=short` 获取实际 passed 数量，替换 237。

**13-NEEDS_FIX-P0: 禁止事项 #1 "不修改 fund_agent/ 源码" 与 P0 矛盾**

- **位置**: Section 3 (line 93)
- **设计写法**: `不修改任何 fund_agent/ 源码：本次是纯测试任务，发现 bug 记录 issue，不修复`
- **问题**: e2e-test-design.md 的 P0 #1 表明 CLI `audit`/`deep-audit` 没有 `--chapter` 和 `--llm` 参数。若不修改源码新增这些参数，Scene 8/9 的 e2e 测试根本无法编写。这不是"发现 bug 记录 issue"能解决的问题 — 是测试设计依赖的功能不存在。
- **后果**: 要么 goal 必须允许修改源码（新增 CLI 参数），要么 e2e 设计必须删除/重写 Scene 8/9。
- **修复建议**: 选项 A — 在禁止事项中增加例外条款（允许为 e2e 可测试性新增 CLI 参数）。选项 B — 删除 Scene 8/9，将章节审计验证合并到 Scene 5 的 generate 流程中。

### P1 — 会导致执行偏差

**14-NEEDS_FIX-P1: 验证标准 Scene 8 字段名与代码不一致**

- **位置**: Section 4.1 (line 121)
- **设计写法**: `8 个审计 JSON + score/findings/decision`
- **实际代码**: `violations` 和 `recommendation`（同 e2e-test-design.md P0 #3）。
- **修复建议**: 改为 `score/violations/recommendation`。

**15-NEEDS_FIX-P1: 执行策略 T5 依赖的 Scene 8 命令参数不存在**

- **位置**: Section 5.1 (line 164: T5 依赖 T4), Section 4.1 (line 121)
- **问题**: T5 (audit 测试) 依赖 T4 (generate)，但 T5 要执行的 Scene 8 使用了不存在的 CLI 参数（同 P0 #1）。T5 无法完成。
- **修复建议**: 随 P0 #1/#13 的裁决同步修复。

**16-NEEDS_FIX-P1: 排除范围"全部走真实 LLM"无 CI 兼容方案**

- **位置**: Section 2 Out of Scope (line 84), Section 3 (line 95)
- **设计写法**: `不使用 mock/fake LLM：全部走真实 DeepSeek API`
- **问题**: 所有场景都需要 `DEEPSEEK_API_KEY`。在 CI 环境或本地无 key 时，全部 13 个场景都会失败。没有 skip 策略。
- **修复建议**: 增加环境变量检测：key 缺失时 `pytest.skip("DEEPSEEK_API_KEY not set")`。或在禁止事项中明确"可在本地跳过 LLM 场景"。

**17-NEEDS_FIX-P1: 任务编号不连续（缺少 T9）**

- **位置**: Section 5.1 (line 167-173), Section 7
- **问题**: T1→T2→T3→T4→T5→T6→T7→T8→T10→T11→T12，缺少 T9。
- **修复建议**: 补回 T9 或重编号为 T1-T11。

### P2 — 轻微问题

**18-NEEDS_FIX-P2: 预计工期 11 天偏乐观**

- **位置**: Section 5.3 (line 182)
- **问题**: 未计入首次实现 conftest 的探索调试时间，以及 `subprocess.Popen` interactive 测试的稳定性调试。
- **修复建议**: 建议 13-15 天。

**19-NEEDS_FIX-P2: Goal 第 8 节 bug 处理策略与 P0 矛盾**

- **位置**: Section 8 (line 231)
- **设计写法**: `发现的 bug 记录为 issue，不回退到 Phase 7.2 代码中修复`
- **问题**: 若 e2e 测试发现的是 CLI 参数缺失（P0 #1），这不是"bug"而是"功能不存在"。记录 issue 无法使 e2e 测试通过。

---

## 关于 "12 项 findings 已修复" 的说明

e2e-test-design.md 声称是"v2（DS review 修复版）"且"已修复全部 P0/P1/P2"。但本次审查发现的 3 个 P0 问题（`audit` CLI 参数不存在、`read` 参数缺失、JSON 字段名错误）均为**与代码事实不符**的新发现，说明上一轮 review 未做代码交叉验证。这些不是"未修复"的问题，而是**上一轮未发现**的问题。

---

## 综合 Verdict

| 文档 | Verdict | P0 | P1 | P2 |
|------|---------|----|----|-----|
| e2e-test-design.md | **NEEDS_FIX** | 3 | 5 | 3 |
| phase7.2-e2e-goal.md | **NEEDS_FIX** | 2 | 4 | 2 |

**最终 Verdict: NEEDS_FIX**

核心问题链：e2e 设计中的 Scene 8/9 假设 CLI `audit`/`deep-audit` 有 `--chapter` 和 `--llm` 参数 → 实际没有 → goal 的禁止事项又不允许修改源码 → 形成死锁。

**最小修复路径**:
1. 裁决：是否允许为 e2e 测试新增 `audit --chapter` + `audit --llm` CLI 参数？（若否，则需删除/重写 Scene 8/9）
2. 修复 3 个 P0：`read` 命令参数、audit JSON 字段名、`/history` 角色标签
3. 修复基线数字（237 → 实际 passed 数）
4. P1 项可在实现阶段渐进修复
