# Tests

当前 Slice 1/2/3/4 与 CLI Read Command Gate 测试覆盖本地 PDF 导入、Docling conversion、DoclingDocumentStore、FundDocumentToolService、最小 Host/Agent tool loop 和 `fund-checklist read`：

```bash
uv run pytest tests/fund/document_tools/test_service.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_docling_conversion.py tests/fund/document_tools/test_local_pdf_source.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py
uv run pytest tests/fund/cli/test_cli.py
```

测试范围：

- report identity 与 `document_id` 规则。
- 非 PDF magic bytes 的 `integrity_error` 分类。
- 改名后同一 PDF 仍使用内容指纹生成稳定 `document_id`。
- 重复导入同一 PDF 复用 `document_id`，但 `local_import_id` 不进入 public identity route。
- 真实本地样本 PDF 通过 `DoclingConverter` 写出受控 Docling JSON。
- Docling conversion 失败分类为 `docling_convert_failed`。
- Docling JSON 无可读文本/章节索引时分类为 `parser_health_failed`。
- DoclingDocumentStore 返回带 locator 的章节、bounded section content、表格投影和 ranked search excerpt。
- FundDocumentToolService 使用内存 `document_id -> DoclingDocumentStore` registry 暴露七个 reading tools。
- `list_reports` 返回 safe source summary，不暴露 `local_import_id`、本地路径或 Docling cache path。
- `read_section`、`search_document`、`read_table` 返回 citation 和 locator，且不暴露 raw Docling JSON。
- public tools 捕获 `DocumentToolError` 并返回 `ToolFailure`；unknown locator 返回 `not_found`。
- `get_excerpt` 只接受 prior tools 返回的受控 `Locator`，按 section/table/excerpt locator kind 路由。
- `MinimalFundDocumentAgent` 先执行 `search_document -> read_section`，再通过 `list_tables/read_table` 补充相关表格。
- `AgentRunResult.answer` 成功时只由 section/table tool result 生成。
- table-aware loop 覆盖人物表格信息、持仓表格信息和无相邻表格的 section-only answer。
- `ToolTraceEntry` 记录工具名、显式参数、success/failure 和可选失败码。
- `search_document` 无命中时返回 `AgentRunResult.failure`，不猜测章节。
- `MinimalHost` 只调用 Agent loop，不访问 Docling store、raw Docling JSON 或本地路径。
- `fund-checklist read` 使用 argparse 参数解析，只实现 read 子命令；console script entrypoint 指向 `fund_agent.cli.main:main`。
- CLI happy path 串起 import、converter/store、service、host/agent；CLI 单测用 fake converter 或预置 Docling JSON，避免重复真实 Docling conversion。
- CLI classified failure 输出稳定 failure code 且退出码为 2；unexpected exception 退出码为 1。
- CLI 输出不得包含 raw Docling JSON、本地 cache path 或 `local_import_id`。

MVP 完整验证命令：

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Post-MVP Slice 6 persistent repository 测试范围：

- completed report 写入 filesystem JSON catalog 后可按 `document_id` 恢复 `DoclingDocumentStore`。
- 恢复后的 `FundDocumentToolService` 可 `search_document`、`read_section`、`list_tables`、`read_table`。
- 重复导入同一 PDF 复用 `document_id` 和 catalog record。
- catalog missing 返回 `not_found`。
- Docling JSON missing/unreadable 返回 `unavailable`。
- catalog identity mismatch 返回 `identity_mismatch`。
- blob fingerprint mismatch 返回 `integrity_error`。
- public output 不泄漏 raw Docling JSON、本地路径、Docling cache path 或 `local_import_id`。
- CLI happy path 写入 completed report catalog，后续同 `document_id` 可复用。

Slice 6 验证命令：

```bash
uv run pytest tests/fund/document_tools/test_persistent_repository.py
uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

Slice 6 暂不测试 schema migration、concurrent writes、repair/rebuild、batch、downloader、delete/update lifecycle、SQLite performance、true LLM 或 release readiness。

Post-MVP Slice 7 CLI packaging 验证命令：

```bash
uv sync
uv run fund-checklist read --help
uv run python -m fund_agent.cli.main read --help
uv run pytest tests/fund/cli/test_cli.py
```

Slice 7 只验证 documented console script entrypoint 和 Python module fallback；不新增 CLI 子命令，不做 release packaging、installer、shell completion、downloader、batch 或 true LLM。

Post-MVP Slice 8A fake/injected LLM tool-loop 测试范围：

- fake LLM 正常调用 `search_document` / `read_section` 后回答，并携带 section citation。
- fake LLM 调用 `list_tables` / `read_table` 后回答表格问题，并携带 table citation。
- fake LLM 直接给出无 evidence final answer 时 fail-closed。
- fake LLM 请求未知工具或越权工具时 fail-closed。
- fake LLM 输出不泄漏 raw Docling JSON、本地路径、Docling cache path 或 `local_import_id`。
- deterministic `fund-checklist read` CLI 旧路径不回退。

Slice 8A 最小验证命令：

```bash
uv run pytest tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
```

当前已知结果：`20 passed`。

Slice 8A broader regression：

```bash
uv run pytest tests/fund/document_tools/test_persistent_repository.py tests/fund/document_tools/test_service.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/agent/test_llm_tool_loop.py tests/fund/cli/test_cli.py
```

当前已知结果：`33 passed`。

Slice 8A 不测试真实 OpenAI / Claude / 外部模型 API、provider auth、streaming、rate limit、cost tracking、prompt framework、`fund-checklist ask`、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 8B DeepSeek real LLM adapter 测试范围：

- DeepSeek adapter 使用 injected fake transport，将合法 tool-call response 解析为 `ToolCall` 并进入 8A runner。
- DeepSeek adapter 使用 injected fake transport，将合法 final-answer response 解析为 `FinalAnswer`，并保留 8A citation/evidence enforcement。
- DeepSeek adapter 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 组装 OpenAI-compatible request，默认 base URL 为 `https://api.deepseek.com`。
- API key 缺失、network/timeout、auth/rate-limit 类错误稳定映射为 `unavailable`。
- malformed provider response 稳定映射为 `llm_malformed_response` 或等价稳定 failure code。
- provider 请求未知工具、越权工具、无 citation answer 或无 evidence answer 时 fail-closed。
- 默认测试不访问网络，不读取真实 API key，不泄漏 secret。
- 默认测试不依赖真实 DeepSeek model 值。
- deterministic `fund-checklist read` CLI、minimal deterministic Agent 和 fake 8A loop 旧路径不回退。

Slice 8B 最小验证命令：

```bash
uv run pytest tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

当前已知结果：`36 passed`；`git diff --check` passed。

Slice 8B 不测试 live DeepSeek 默认路径、Mimo / MiMo、streaming、多 provider matrix、prompt framework、`fund-checklist ask`、richer QA/eval、字段抽取、自动报告、投资判断或 release readiness。live provider smoke 必须显式 opt-in，不能进入默认 pytest gate。

Post-MVP Slice 8C opt-in live DeepSeek smoke 测试范围：

- 默认 pytest no-network；未设置 `FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1` 时 live test 自动 skip。
- 设置 opt-in 但缺 `DEEPSEEK_API_KEY` 时 skip，不失败。
- `DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，可覆盖。
- `DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`，可覆盖。
- 使用 fake/in-memory tool service 或现有测试 fixture，不跑真实 PDF、CLI、Docling conversion 或 repository-backed loader。
- live DeepSeek 返回一次合法 `ToolCall` 或合法 `FinalAnswer`，并最终进入 8A runner/enforcement。
- live smoke 最多 1 个 run、timeout 300 秒、最多 1 次 retry。
- opt-in 后 provider 返回不可解析、8A enforcement fail、network/429/auth error 均为 test fail。
- pytest output、trace、assert message 不泄漏 API key。
- 不记录 provider raw response，不新增 artifact。
- 默认测试用 fake transport 覆盖 skip helper、默认 base/model、override、timeout、retry 上限、malformed response fail-closed、secret redaction 和 8A runner 入口；真实 live 分支默认 skip。

Slice 8C 默认验证命令：

```bash
uv run pytest tests/fund/agent/test_deepseek_live_smoke.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_llm_tool_loop.py tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

当前已知结果：`43 passed, 1 skipped`；`git diff --check` passed。

Slice 8C live smoke 命令：

```bash
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 DEEPSEEK_API_KEY=... uv run pytest tests/fund/agent/test_deepseek_live_smoke.py
```

Slice 8C 不测试 `fund-checklist ask`、真实 PDF/Docling/repository e2e、Mimo / MiMo、streaming、多 provider matrix、retry/backoff hardening、prompt injection hardening、richer QA/eval、字段抽取、自动报告、投资判断或 release readiness。
