# Goal Command（可直接发送）

发送以下命令即可开启本次任务（推荐，objective 自包含）：

```
/goal 按 .sisyphus/goals/preference-p1-flomo-import-goal-20260821.md 实施「Slice P1：flomo-import（Flomo HTML 导出 → SQLite）」slice（设计真源：docs/design.md §6.26.3/§6.26.4，2026-08-21 已落盘；AGENTS.md / docs/design.md 已由 controller 同步，禁止修改）。只走 CIC-lite implement -> tests -> diff review。实施内容：① 新增 fund_agent/preferences/ 模块（新域：投资者偏好，与 fund/ 平级）：__init__.py；flomo_parser.py——FlomoMemo dataclass（id/created_at/content/images/source）+ parse_flomo_html(html_text: str, source_path: str) -> list[FlomoMemo]，用标准库 html.parser.HTMLParser 状态机解析（.memo 容器 / .time 文本 YYYY-MM-DD HH:MM:SS / .content 内 p/br→换行、ul/ol/li→缩进项目符号、img src="file/..."→images 相对路径数组、.files 内 img 同收集），header .date 文本「于 2026-8-19 导出 331 条 MEMO」解析出 exported_at（日期）+ 声明 memo 数；id 格式 flomo-<YYYY-MM-DD>-<序号>（同日序号从 1 递增）；created_at 转 ISO8601 +08:00；source = source_path 相对名 + HTML 内字符偏移；无 .memo 或无 .time → 抛自定义 FlomoParseError（schema_drift 语义，中文消息）；② 新增 fund_agent/preferences/store.py——PreferencesStore（标准库 sqlite3）：open_preferences_store(work_dir) 建 preferences/preferences.db 与表 memos(id TEXT PK, created_at TEXT, content TEXT, images_json TEXT DEFAULT '[]', source TEXT) 和 imports(id INTEGER PK AUTOINCREMENT, source_path TEXT, fingerprint TEXT UNIQUE, exported_at TEXT, memo_count INTEGER, imported_at TEXT)（imports.exported_at 为 goal 扩展列：design §6.26.4 未显式定义，用于审计可追溯，Mimo goal review 2026-08-21 已确认标注）；fingerprint = sha256(exported_at + 全部 memo 的 created_at + content 前 64 字符)；import_memos(memos, *, source_path, exported_at) 先查 fingerprint 已存在 → 返回 ImportResult(imported=False, cached=True, memo_count=已有数, imported_at=首次时间) 不覆盖；否则单事务写 memos + imports 返回 ImportResult(imported=True, cached=False, memo_count, image_count)；SQLite 打开/写入失败抛 PreferencesStoreError（unavailable 语义）；③ 修改 fund_agent/cli/main.py——注册 flomo-import 子命令（--html 必填 Path、--work-dir 默认 .fund_checklist、--images-dir 可选 Path）+ _run_flomo_import_command（文件不存在 → not_found 分类失败退出码 2；FlomoParseError → schema_drift 退出码 2；PreferencesStoreError → unavailable 退出码 2；成功输出 imported/cached 摘要：memo 数、图片引用数、db 路径；--images-dir 提供时校验 images 引用文件存在性，缺失仅 warning 不阻断；不接 LLM）；④ 新增 tests/fund/preferences/test_flomo_parser.py（fixture 构造：含 header .date + 3 条 .memo（time/br/ul/ol/li/img/.files）验证字段与图片数组；无 .memo → FlomoParseError；无 .time → FlomoParseError；同日多 memo id 递增；created_at ISO8601 带 +08:00）；⑤ 新增 tests/fund/preferences/test_flomo_store.py（幂等：同 fingerprint 二次导入 cached 不覆盖行数；不同 content 不同 fingerprint；memos 表行数与字段；images_json 解析回数组；PreferencesStoreError 路径：work_dir 为文件路径时打开失败）；⑥ 新增 tests/fund/preferences/fixtures/flomo_sample.html（测试资产，非私人数据）+ tests/fund/cli/test_cli_flomo_import.py（run_cli 端到端：成功退出码 0 + db 行 + 重复导入 cached 输出；html 不存在 → 退出码 2 not_found；结构不匹配 → 退出码 2 schema_drift）。allowed write set：fund_agent/preferences/ 新增、fund_agent/cli/main.py、tests/fund/preferences/ 新增、tests/fund/cli/test_cli_flomo_import.py 新增、fund_agent/README.md 与 tests/README.md 各补 1 句（偏好模块/测试结构）。禁止修改 AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/（本 goal 文件除外） / fund_agent/fund/ / fund_agent/service/ / fund_agent/host/ / fund_agent/agent/ / 存量 quarterly-top10-holdings-fix 涉及文件；禁止新增第三方依赖（只用标准库 html.parser + sqlite3 + hashlib）；禁止把 memo 内容写入 git 跟踪目录（只写 --work-dir）；禁止接 LLM；不 commit、不 push。验收：uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_flomo_import.py -v --tb=short 全通过，且最小验证集 uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 回归通过；输出交接报告（changed files / diff 摘要 / 实际测试命令与输出）。
```

备选（goal 文档即 objective 载体）：

```
/goal .sisyphus/goals/preference-p1-flomo-import-goal-20260821.md
```

## Goal

- goal_id: `preference-p1-flomo-import-20260821`
- 目标：实施投资者偏好分析 MVP Slice P1——`flomo-import` 子命令（Flomo HTML 导出 → SQLite，memos + imports 幂等），确定性、不接 LLM、不进 git。
- 前置条件：`docs/design.md` §6.26.3/§6.26.4 已落盘（存储格式 = SQLite 已裁决；图片仅引用路径已确认）；`.gitignore` 已含 `docs/flomo@*.zip` / `docs/flomo-export-*/` / `.fund_checklist*/`；AGENTS.md 已由 controller 同步，本 slice 不改真源。
- 设计来源：`docs/design.md` §6.26.3（数据源与隐私边界）/ §6.26.4（Flomo 导入设计，含 2026-08-21 落盘的实现设计）。
- 日期：2026-08-21

## Objective（完整命令文本）

即上文「可直接发送」代码块中的 `/goal ...` 全文，作为本 goal 的单一执行依据。

## Scope

| 项 | 内容 |
|-------|------|
| 新增模块 | `fund_agent/preferences/`（`__init__.py` / `flomo_parser.py` / `store.py`） |
| 修改模块 | `fund_agent/cli/main.py`（注册 `flomo-import` 子命令 + `_run_flomo_import_command`） |
| 测试资产 | `tests/fund/preferences/fixtures/flomo_sample.html`（非私人数据） |
| 新增测试 | `tests/fund/preferences/test_flomo_parser.py` / `test_flomo_store.py` / `tests/fund/cli/test_cli_flomo_import.py` |
| 文档 | `fund_agent/README.md`、`tests/README.md`（各 1 句） |
| 禁止 | AGENTS.md / docs/design.md / docs/implementation-control.md / .sisyphus/（本 goal 文件除外）/ fund_agent/fund|service|host|agent / 存量 quarterly-top10-holdings-fix 涉及文件 / 新第三方依赖 / memo 写入 git 跟踪目录 / LLM / commit / push |

## 验收（DoD）

- `uv run pytest tests/fund/preferences/ tests/fund/cli/test_cli_flomo_import.py -v --tb=short` 全通过。
- 最小验证集 `uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short` 回归通过。
- 交接报告：changed files / diff 摘要 / 实际测试命令与输出。
