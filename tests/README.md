# Tests

当前 Slice 1/2/3/4 与 CLI Read Command Gate 测试覆盖本地 PDF 导入、Docling conversion、DoclingDocumentStore、FundDocumentToolService、最小 Host/Agent tool loop、Service boundary 和 `fund-checklist read`：

```bash
uv run pytest tests/fund/document_tools/test_service.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_docling_conversion.py tests/fund/document_tools/test_local_pdf_source.py
uv run pytest tests/fund/service
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
- `search_document` 只命中 table caption 或 bounded table rows 时返回 table-backed result，并带 `table_ref`、locator、citation 和受控 `match_kind`。
- table row 命中摘录只返回命中行的有界文本，不返回整表。
- public tools 捕获 `DocumentToolError` 并返回 `ToolFailure`；unknown locator 返回 `not_found`。
- `get_excerpt` 只接受 prior tools 返回的受控 `Locator`，按 section/table/excerpt locator kind 路由。
- `MinimalFundDocumentAgent` 先执行 `search_document -> read_section`，再通过 `list_tables/read_table` 补充相关表格。
- `search_document` first hit 是 high-certainty table-backed result 且带 `table_ref` 时，`MinimalFundDocumentAgent` 直接 `read_table`，不经 `list_tables` 做表格发现。
- high-certainty table-backed answer 以 bounded table rows 为主体，section title / table caption 只作来源上下文。
- `AgentRunResult.answer` 成功时只由 section/table tool result 生成。
- table-aware loop 覆盖人物表格信息、持仓表格信息和无相邻表格的 section-only answer。
- `ToolTraceEntry` 记录工具名、显式参数、success/failure 和可选失败码。
- `search_document` 无命中时返回 `AgentRunResult.failure`，不猜测章节。
- `MinimalHost` 只调用 Agent loop，不访问 Docling store、raw Docling JSON 或本地路径。
- `FundReadingService` 覆盖 `import_local_report`、`read_local_report`、`list_reports`，负责编排 import、repository-backed load、必要时 Docling conversion fallback 和 Host 调用。
- Service 调 Host 时只传 `document_id` 和 `query`；catalog 有 completed report 时复用，catalog record 指向的 Docling JSON 缺失时 fail-closed，不自动 repair/rebuild/reconvert。
- Service 对 hardcoded controlled query profiles 生成受控 candidate queries，并只在 `not_found`、disclosure target mismatch 或多目标未完成时按顺序尝试下一个 Host/Agent run。
- `fund-checklist read` 使用 argparse 参数解析，只实现 read 子命令；console script entrypoint 指向 `fund_agent.cli.main:main`。
- CLI happy path 通过 `FundReadingService` 串起 reading use case；CLI 单测用 fake converter 或 fake Service，避免重复真实 Docling conversion。
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

Post-MVP Slice 9A Service boundary 测试范围：

- `FundReadingService.read_local_report` 导入本地 PDF，必要时转换 Docling JSON，登记 completed report，并只用 `document_id` 和 `query` 调 Host。
- `FundReadingService.import_local_report` 返回不含 path、Docling JSON path、cache path 或 `local_import_id` 的 safe summary。
- completed catalog 已存在时复用 repository-backed store，不重复调用 converter。
- completed catalog record 指向的 Docling JSON 缺失时返回 `unavailable`，不自动 repair / rebuild / reconvert。
- `FundReadingService.list_reports` 返回安全 report summary，支持基本过滤；无 catalog 时返回空列表。
- Agent `ToolFailure` 通过 Service result 保留原 failure code，CLI 继续映射为 exit code 2。
- CLI 只保留 argparse 和 stdout/stderr 格式化，不直接装配 PDF provider、repository、converter、tool service 或 Host。

Slice 9A 验证命令：

```bash
uv run pytest tests/fund/service tests/fund/cli/test_cli.py tests/fund/agent/test_minimal_tool_loop.py
git diff --check
```

真实 CLI smoke：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '股票投资明细' --work-dir .fund_checklist_cli_smoke
```

Slice 9A 不测试 query normalization / synonym routing、`fund-checklist ask`、DeepSeek 真实 PDF CLI、8A/8B/8C contract 变更、UI、多轮会话、批量任务、指标计算、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 9B Evidence retrieval substrate 验证命令：

```bash
uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py
git diff --check
```

Slice 9B 不测试 query normalization / synonym routing、deterministic Agent table-only consumption、CLI table-only query success、embedding、外部搜索、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 9C table-backed first-hit consumption 测试范围：

- high-certainty table row first hit 触发 `search_document -> read_section -> read_table`，不调用 `list_tables`。
- high-certainty table caption first hit 触发 `search_document -> read_section -> read_table`，bounded table rows 是 answer 主体。
- low-certainty table-backed hit 继续走既有 section-first table-aware 路径。
- table-backed hit 缺 `table_ref` 时不得强行直读表，继续保持回落语义。

Slice 9C 验证命令：

```bash
uv run pytest tests/fund/agent/test_minimal_tool_loop.py
uv run pytest tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py tests/fund/cli/test_cli.py
git diff --check
```

Slice 9C 不测试 top-N scan、rerank、歧义消解、query intent 分类、query normalization / synonym routing、`fund-checklist ask`、真实 LLM、embedding、外部搜索、template contract execution、calculation framework、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 9D controlled query profile routing 测试范围：

- Service 层为 `holdings_top10`、`asset_allocation`、`expenses` 三类 exact alias 生成最多 3 个 candidate queries，且包含原始 query。
- Service 按候选顺序调用既有 Host/Agent 路径，返回第一个成功 Agent result。
- 所有候选都 `not_found` 时仍返回 `not_found`，routing 配置异常映射为 `schema_drift`。
- CLI 输出格式不变，`--query 前十大持仓` 通过 Service routing 命中 `股票投资明细`。

Slice 9D 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
git diff --check
```

Slice 9D 不测试开放式 query normalization、自动分词、同义词扩散、query intent 分类、embedding、LLM intent、top-N scan、rerank、歧义消解、`fund-checklist ask`、template contract execution、calculation framework、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 9E Service routing attempts audit 测试范围：

- `ReadLocalReportResult.routing_trace` 记录 Service routing attempts，字段只包含 `query`、`profile_name`、`result_kind`、`failure_code`。
- 原始 query 直接成功时只记录原始 query success；fallback candidate 成功时记录原始 failure + fallback success。
- 所有 controlled candidates 都 `not_found` 时记录全部 attempts，最终 failure code 仍是 `not_found`。
- 非受控 query 只记录原始 query；成功 attempt 的 `failure_code` 必须为 `None`。
- CLI 默认输出格式不暴露 `routing_trace`；Agent `tool_trace` 不包含 Service routing metadata。

Slice 9E 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
git diff --check
```

Slice 9E 不测试新 profile、新召回能力、rerank、语义理解、分词、embedding、LLM intent、top-N scan、`fund-checklist ask`、template contract execution、calculation framework、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 10A controlled disclosure target contract 测试范围：

- 只使用仓库本地真实样本 PDF：`基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf`；样本缺失直接失败。
- 固定三条 smoke query：`前十大持仓`、`资产配置`、`费用`。
- `前十大持仓` 的 answer 必须包含 `股票投资明细` 或 `前十名股票投资明细`。
- `资产配置` 的 answer 必须包含 `期末基金资产组合情况` 或 `基金资产组合情况`。
- `费用` 在当前 9D candidate 下不满足 acceptable title family，必须 fail-closed 为 `not_found`，不得把无关章节 keyword success 当成 target success。
- CLI success smoke 必须 exit code 0，输出包含 Answer、Citations、Trace；`费用` smoke 必须 exit code 2 并输出 `failure_code=not_found`。
- CLI 默认输出不包含 `routing_trace`、`profile_name`、`selected_query` 或 `selected_index`。
- Service 层断言三类 profile 的 `routing_trace`，但不把 routing metadata 暴露到 Agent `tool_trace` 或 CLI 默认输出。
- Service target contract 只检查安全 Agent result 中的 section/table title 行与 citation locator kind；不改 Store / ToolService / Agent，不改 `search_document` public contract。

Slice 10A 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
git diff --check
```

Slice 10A 真实 CLI smoke：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '前十大持仓' --work-dir .fund_checklist_cli_smoke_9f
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '资产配置' --work-dir .fund_checklist_cli_smoke_9f
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '费用' --work-dir .fund_checklist_cli_smoke_9f
```

Slice 10A 不测试新增 profile、alias 覆盖矩阵、routing 规则变更、`search_document` contract 变更、Agent/Store/ToolService 变更、CLI 输出格式变更、benchmark、correctness evaluation、开放式 query normalization、自动分词、同义词扩散、query intent 分类、embedding、LLM intent、top-N scan、rerank、歧义消解、`fund-checklist ask`、template contract execution、calculation framework、字段抽取、自动报告、投资判断或 release readiness。

Post-MVP Slice 10B fee_rates reading locator 测试范围：

- Service 层把旧 `expenses` 收窄为 `fee_rates`，aliases 仅覆盖 `费用`、`费率`、`管理费`、`托管费`、`销售服务费`。
- `fee_rates` candidate queries 固定为原始 query、`基金管理费`、`基金托管费`、`销售服务费`；不把单独 `费率` 作为 evidence candidate。
- `fee_rates` 必须聚合 `基金管理费`、`基金托管费`、`销售服务费` 三个 disclosure sections，三目标未全命中时仍 fail-closed 为 `not_found`，不新增 `partial_success`。
- Service 层断言 `routing_trace` 记录多目标 attempts；CLI 默认输出仍只展示 Answer、Citations、Trace，不展示 `routing_trace`。
- 真实 PDF smoke 对 `--query 费用` 必须 exit code 0，answer 同时包含 `基金管理费`、`基金托管费`、`销售服务费`。

Slice 10B 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
git diff --check
```

Slice 10B 真实 CLI smoke：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '费用' --work-dir .fund_checklist_cli_smoke_10b
```

Slice 10B 不测试费率数值抽取、结构化字段输出、显性成本小计、总成本、扣费后收益率、年化收益率、开放语义理解、embedding、LLM intent、top-N scan、rerank、歧义消解、template contract execution、自动报告、投资判断或 release readiness。

Post-MVP Slice 10C fee_rates value extraction contract 测试范围：

- `FundReadingService.extract_fee_rates` 复用 10B fee_rates 阅读定位后的安全 Agent answer / citation，不读取 raw Docling JSON、本地 PDF path、cache path、repository/private loader 或 `local_import_id`。
- 抽取字段仅限 `management_fee_rate`、`custodian_fee_rate`、`sales_service_fee_rate`。
- 管理费率和托管费率只取当前报告期适用年费率，历史调整前费率不得当成当前值。
- 销售服务费必须区分 A 类 `不收取` 和 C 类 `0.40%`，不得把“不收取”改写为 `0.00%`。
- 每个字段 DTO 必须包含 `field_name`、`decimal_percent_text`、`period`、`share_class_scope`、`raw_text`、`citation`。
- 字段未找到或候选章节无法唯一抽取返回 `not_found`；抽取配置异常返回 `schema_drift`；不新增 failure code 或 `partial_success`。
- CLI 默认输出仍只展示 Answer、Citations、Trace，不展示结构化抽取 DTO 或 `routing_trace`。

Slice 10C 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
git diff --check
```

Slice 10C 真实 CLI smoke：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '费用' --work-dir .fund_checklist_cli_smoke_10c
```

Slice 10C 不测试净值增长率、基准收益率、换手率、显性成本小计、总成本、扣费后收益率、年化收益率、`R=A+B-C`、同类中位数、开放语义理解、embedding、LLM intent、top-N scan、rerank、歧义消解、template contract execution、chapter contract execution、自动报告、投资判断或 release readiness。

Post-MVP Slice 11A performance disclosure locator 测试范围：

- Service 层新增 `performance_returns` profile，aliases 仅覆盖 `净值增长率`、`业绩比较基准收益率`、`基准收益率`、`收益表现`、`基金净值表现`。
- candidate queries 固定为原始 query、`基金份额净值增长率及其与同期业绩比较基准收益率的比较`、`基金净值表现`、`业绩比较基准收益率`。
- target success 必须命中 acceptable title family：`基金份额净值增长率及其与同期业绩比较基准收益率的比较` 或 `基金净值表现`。
- 当前真实样本要求同时具备 section citation 和 table citation；缺 table citation 时 fail-closed 为 `not_found`。
- Service / CLI 真实 PDF smoke 对 `--query 净值增长率` 必须 exit code 0，answer 包含目标披露标题，CLI 默认输出仍只展示 Answer、Citations、Trace，不展示 `routing_trace`。
- 11A 不输出 `nav_growth_rate`、`benchmark_return_rate`、`period`、`decimal_percent_text` 等结构化字段，不抽值、不计算。

Slice 11A 验证命令：

```bash
uv run pytest tests/fund/service/test_reading_service.py tests/fund/cli/test_cli.py
uv run pytest tests/fund/agent/test_minimal_tool_loop.py tests/fund/document_tools/test_docling_store.py tests/fund/document_tools/test_service.py
git diff --check
```

Slice 11A 真实 CLI smoke：

```bash
uv run python -m fund_agent.cli.main read --pdf '基金年报/安信企业价值优选混合型证券投资基金2024年年度报告.pdf' --fund-code 004393 --fund-name '安信企业价值优选混合型证券投资基金' --year 2024 --query '净值增长率' --work-dir .fund_checklist_cli_smoke_11a
```

Slice 11A 不测试字段抽取、period 裁决、换手率、显性成本小计、总成本、扣费后收益率、年化收益率、`A=R-B`、`R=A+B-C`、Alpha/Beta/Cost 综合评估、同类中位数、开放语义理解、embedding、LLM intent、top-N scan、rerank、歧义消解、template contract execution、chapter contract execution、自动报告、投资判断或 release readiness。
