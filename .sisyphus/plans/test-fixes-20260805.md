# 2026-08-05 测试修复 slice：4 个基线失败 + fix CLI 断链

> 状态：🟡 待 Mimo review。来源：4 个基线失败测试根因排查（2026-08-02 确认全部失败），其中 1 个暴露主体代码断链，需一并修复。

---

## 1. 问题与根因（均已实证）

### 1.1 fixture 路径错位（测试侧）

`tests/fund/document_tools/test_docling_conversion.py:20`：
`SAMPLE_PDF = Path("基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf")` — 该文件名不存在；真实数据在 `基金年报/004393_安信企业价值优选混合_2024_annual_report.pdf` 与 `011649_易方达逆向投资混合_2021..2025_annual_report.pdf`（均存在）。

裁决（用户 2026-08-02 指示）：废弃文件名不再采纳，数据源切换为 `基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf` 及其 5 年完整年报。

### 1.2 断言错位（测试侧 ×2）

`test_cli.py::test_cli_happy_path_orchestrates_import_store_service_and_host` 与 `test_cli_reuses_existing_docling_json_without_converter` 断言 `"基金管理人" in stdout`，但当前确定性 Agent 对默认 query「基金经理」的输出为「§1 重要提示 基金经理在本报告期内保持稳定。股票投资明细展示前十名股票投资明细。」（不含「基金管理人」）。修复：断言改为 `"基金经理" in stdout`（输出文本实际包含）。

### 1.3 fix CLI 断链（主体代码问题，非纯测试问题）

`test_fix_chapter` 失败表象是 `monkeypatch.setattr(chapter_generator, "_fix_chapter_placeholders")` 引用不存在符号；但根因是主体代码：

- `fund_agent/cli/main.py:_run_fix_command`（1315 行）惰性导入 `from fund_agent.service.chapter_generator import _fix_chapter_placeholders`，该函数已被 Phase 7.2 scene 化移除（python 实证 `hasattr == False`）→ **fix CLI 运行即 ImportError，属生产断链**，不只是测试陈旧。
- Phase 7.2 已建 `FIX_SCENE_CONFIG`（scene_config.py:145，context_slots=chapter_content/audit_feedback/chapter_contract，allowed reading tools）与 `scenes/fix.md`（占位符补强 prompt），但未接线；repair/regenerate CLI 已接 REPAIR/REGENERATE_SCENE_CONFIG → ChatService，fix 未接。
- ChatService `_build_contributions` 已支持通过 `PinnedState.user_constraints` 透传 context slots（chat_service.py:570）。

## 2. 修复规格

### 2.1 fixture 切换（1.1）

- `test_docling_conversion.py`：`SAMPLE_PDF` → `基金年报/011649_易方达逆向投资混合_2025_annual_report.pdf`；import 参数改 `fund_code="011649"`、`fund_name="易方达逆向投资混合"`、`year=2025`；`_identity`（仅非 PDF 失败用例用）保持不变。
- `tests/README.md`：16 处引用废弃文件名的 smoke 命令同步改为 011649（`--fund-code 011649 --fund-name 易方达逆向投资混合 --year 2025`）。

### 2.2 断言修正（1.2）

- `test_cli.py` 两处 `assert "基金管理人" in stdout` → `assert "基金经理" in stdout`（其余断言不变）。

### 2.3 fix CLI 重新接线（1.3，主体代码）

- `_run_fix_command` 改为 FIX_SCENE_CONFIG → ChatService 模式（镜像 repair/regenerate 的 scene 接线 + interactive 的 tool_service 构建）：
  - 从 workdir 构建 tool_service（FilesystemReportRepository + 各 document store；失败文档跳过，可为 None）。
  - 创建/复用 session，PinnedState 含 `user_constraints={"chapter_content": ..., "audit_feedback": ..., "chapter_contract": ...}`（来自报告章节正文、ArtifactStore audit decision、CHAPTER_CONTRACTS）。
  - ChatService(scene_config=FIX_SCENE_CONFIG, tool_service=...)；LLM client 走 DeepSeekLlmClient（fix parser 参照 repair 增加 `--llm`，无 `--llm` 时提示跳过/退出码同 repair 语义；DS 实现可选用默认 client 方案，但必须保持现有 stdout 统计契约）。
  - 取 chat_turn 结果作为补强后章节正文；保留现有 `补强占位符/保留占位符` 统计与 exit code 语义；有内容变化时写回报告文件（复用 `_replace_chapter_in_markdown`）。
- 删除 `_run_fix_command` 内对不存在符号的引用。
- 不改 `search_document`/Service 公共契约；不改 FIX_SCENE_CONFIG 定义与 fix.md prompt。

### 2.4 test_fix_chapter 重写

- 不再 monkeypatch 不存在符号；改为注入 fake LLM（仿 `test_generate_cli_real_pdf_smoke` 的 `_FakeDeepSeekLlmClient`，含 `clone()`），`fix` 命令带 `--llm`，fake 返回把 `[待补充]→[已补充]`、`[数据缺失]→""` 的补强正文。
- 断言保持：exit 0、`补强占位符: 2`、`保留占位符: 0`、仅处理 Ch3（可经 fake 记录 user_prompt 含 Ch3 内容断言）。

## 3. 真源文档更新（Mimo review 通过后执行）

- `docs/implementation-control.md`：测试修复 slice 记录 + fix CLI 断链修复（Phase 7.2 fix 场景补接线）。
- `AGENTS.md`：如需（fix CLI 已接入 FIX_SCENE_CONFIG；011649 为测试数据源）按现状格式追加。
- `tests/README.md`：见 2.1（属于测试结构同步）。

## 4. allowed write set

- `tests/fund/document_tools/test_docling_conversion.py`
- `tests/fund/cli/test_cli.py`
- `fund_agent/cli/main.py`（仅 `_run_fix_command` + fix parser `--llm`）
- `tests/README.md`
- 真源文档：`docs/implementation-control.md`、（`AGENTS.md` 如需）

禁止：改 chapter_generator / scene_config / chat_service / audit_pipeline 主体逻辑；改 search_document 契约；触碰 Phase 7.4 / F1.1 / Phase 7.5 未提交区域。

## 5. 验证命令

```bash
uv run pytest tests/fund/document_tools/test_docling_conversion.py tests/fund/cli/test_cli.py -q --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
```

## 6. 验收口径

- 4 个基线失败测试全部转绿；其余测试不回退。
- `fix --chapter N --llm`（fake LLM）输出补强/保留占位符统计且只改目标章节。
- 011649 fixture 真实转换通过（Docling 可用缓存）；`git diff --check` 干净；不 commit / push。

## 7. stop conditions

- 触碰 §4 禁止事项 → 停止。
- 任一验证命令失败且非既有已知失败 → 停止。
- fix CLI 重接后 `--llm` 缺失时的行为语义改变 → 需先与 controller 确认。
