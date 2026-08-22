# Goal Command（可直接发送）

发送以下命令即可开启本次任务：

```
## 任务：按 .sisyphus/goals/preference-p4-note-import-goal-20260822.md 实施「Slice P4：note-import（智慧笔记数据导出 HTML → SQLite）」（设计真源：docs/design.md §6.26.10，2026-08-22 已落盘；AGENTS.md / docs/design.md / docs/implementation-control.md / .gitignore 已由 controller 同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review。实施内容：① 新增 fund_agent/preferences/note_parser.py——ThoughtNote dataclass（id/category/title/created_at/status/content/source）+ parse_note_export(html_text, source_path) -> list[ThoughtNote]（标准库实现：</div>→换行、去 HTML 标签、html.unescape 后按 Markdown 结构解析；header 解析「导出时间：YYYY-MM-DD HH:MM」「总记录数：N 条」；## 类别（分析记录/多维度分析/孵化报告/结构分析 → analysis/roundtable/incubator/structure，未知类别 schema_drift fail-closed）；### 序号. 标题；> 分析时间：/ > 状态： 元数据行；content = 该记录 ### 之后到下一个 ### 或 ## 之前的全文（保留 **原始问题：**/**分析结果：** 分节与 #### 子节，纯文本）；id = note-<导出日期 YYYYMMDD>-<category-key>-<序号>；created_at 转 ISO8601 +08:00；source = source_path 相对名；无「导出时间」/「总记录数」/「分析时间」/「状态」行或声明条数与实解析数不一致或 0 条 → 抛自定义 NoteParseError（schema_drift 语义，中文消息）；② 修改 fund_agent/preferences/store.py——_SCHEMA 追加 thought_records(id TEXT PK, category TEXT, title TEXT, created_at TEXT, status TEXT, content TEXT, source TEXT) 与 note_imports(id INTEGER PK AUTOINCREMENT, source_path TEXT, fingerprint TEXT UNIQUE, exported_at TEXT, record_count INTEGER, imported_at TEXT)（CREATE TABLE IF NOT EXISTS，老库升级自动加表不破坏 memos）；新增 ThoughtNoteRow dataclass + import_notes(notes, *, source_path, exported_at) -> ImportResult（fingerprint = sha256(exported_at + 全部记录 title+created_at+content 前 64 字符)；同指纹 → ImportResult(imported=False, cached=True, record_count=已有数, imported_at=首次时间) 不覆盖；否则单事务写 thought_records + note_imports；SQLite 失败抛 PreferencesStoreError unavailable）；③ 修改 fund_agent/cli/main.py——注册 note-import 子命令（--html 必填 Path、--work-dir 默认 .fund_checklist）+ _run_note_import_command（文件不存在 → not_found 退出码 2；NoteParseError → schema_drift 退出码 2；PreferencesStoreError → unavailable 退出码 2；成功输出 imported/cached 摘要：record 数、db 路径；不接 LLM）；④ 新增 tests/fund/preferences/fixtures/note_sample.html（构造样例，非私人数据：4 类别 5 条——分析记录 2 / 多维度分析 1 / 孵化报告 1 / 结构分析 1，div 包裹 HTML 形态，含 **原始问题：**/**分析结果：** 分节与 #### 多导师子节）+ tests/fund/preferences/test_note_parser.py（字段/类别映射/序号与 id 格式/created_at ISO8601 +08:00/声明条数不符 → NoteParseError/缺失分析时间 → NoteParseError/未知类别 → NoteParseError/0 条 → NoteParseError）+ tests/fund/preferences/test_note_store.py（幂等：同 fingerprint 二次导入 cached 不覆盖；thought_records 行数与字段；note_imports 审计行）+ tests/fund/cli/test_cli_note_import.py（CLI e2e：成功退出码 0 + db 行 + 重复导入 cached 输出；html 不存在 → 退出码 2 not_found；结构不匹配 → 退出码 2 schema_drift）。allowed write set：fund_agent/preferences/note_parser.py 新增、fund_agent/preferences/store.py、fund_agent/cli/main.py、tests/fund/preferences/ 新增、tests/fund/cli/test_cli_note_import.py 新增、fund_agent/README.md 与 tests/README.md 各补 1 句。禁止修改 AGENTS.md / docs/design.md / docs/implementation-control.md / .gitignore / .sisyphus/（本 goal 文件除外） / fund_agent/fund/ / fund_agent/service/ / fund_agent/host/ / fund_agent/agent/ / 存量未提交改动（含 P1-P3 已存在文件：只允许 store.py 与 main.py 按本 goal 追加，不得改 flomo_parser.py/questionnaire.py/snapshot.py 语义）；禁止新增第三方依赖（只用标准库）；禁止把私人导出数据写入 git 跟踪目录；禁止接 LLM；不 commit、不 push。验收：uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_note_import.py -v --tb=short 全通过，且最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 回归通过；输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/preference-p4-note-import-goal-20260822.md
```

## Goal

- goal_id: `preference-p4-note-import-20260822`
- 目标：实施投资者偏好分析 Slice P4——`note-import` 子命令（智慧笔记数据导出 HTML → SQLite，thought_records + note_imports 幂等），确定性、不接 LLM、不进 git。
- 前置条件：`docs/design.md` §6.26.10 已落盘；`.gitignore` 已含 `docs/note-export-*/`；真实导出 `docs/note-export-20260811/思考记录-20260811.html` 已保存（gitignored，65 条记录）；AGENTS.md / docs / .gitignore 已由 controller 同步，本 slice 不改真源。
- 设计来源：`docs/design.md` §6.26.10（智慧笔记数据导出导入）。
- 日期：2026-08-22

## Objective（完整命令文本）

即上文「可直接发送」代码块中的任务全文，作为本 goal 的单一执行依据。

## Scope

| 项 | 内容 |
|-------|------|
| 新增模块 | `fund_agent/preferences/note_parser.py` |
| 修改模块 | `fund_agent/preferences/store.py`（追加 thought_records / note_imports 表 + import_notes）、`fund_agent/cli/main.py`（注册 `note-import` + handler） |
| 测试资产 | `tests/fund/preferences/fixtures/note_sample.html`（非私人数据） |
| 新增测试 | `tests/fund/preferences/test_note_parser.py` / `test_note_store.py` / `tests/fund/cli/test_cli_note_import.py` |
| 文档 | `fund_agent/README.md`、`tests/README.md`（各 1 句） |
| 禁止 | AGENTS.md / docs/design.md / docs/implementation-control.md / .gitignore / .sisyphus/（本 goal 文件除外）/ fund_agent/fund|service|host|agent / 存量未提交改动语义（flomo_parser.py / questionnaire.py / snapshot.py 不改）/ 新第三方依赖 / 私人数据写入 git 跟踪目录 / LLM / commit / push |

## 验收（DoD）

- `uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_note_import.py -v --tb=short` 全通过。
- 最小验证集 `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short` 回归通过。
- 交接报告：changed files / diff 摘要 / 实际测试命令与输出。
