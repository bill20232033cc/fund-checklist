# Slice: LLM provider 自由切换（DeepSeek ↔ Mimo）

controller: main thread
impl: DS（agents:0.1）
review: MiMo（agents:0.2）
模式: CIC-lite（implement -> tests -> diff review，无 plan-fix / re-review / evidence gate）

## 目标

在现有 OpenAI-compatible adapter（fund_agent/agent/deepseek_llm.py）上增加 provider 选择层，
使同一套代码可通过 env 在 DeepSeek 与 Mimo 之间自由切换。不新建第二套 adapter。

## 硬口径（必须严格遵守）

1. 新增 env `FUND_CHECKLIST_LLM_PROVIDER`，取值 `deepseek`（默认）/ `mimo`。
   未知值 fail-fast：抛 ValueError，提示合法取值；不静默回退。
2. Provider 配置表（集中在 deepseek_llm.py）：
   - deepseek: key=`DEEPSEEK_API_KEY`; base=`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`; model=`DEEPSEEK_MODEL` 默认 `deepseek-v4-flash`
   - mimo: key=`MIMO_API_KEY`; base=`MIMO_BASE_URL` 默认 `https://api.xiaomimimo.com/v1`; model=`MIMO_MODEL` 默认 `mimo-v2.5-pro`
   - 解析发生在请求组装时（与现有 env 读取点一致）；DeepSeekLlmClient 的 `env` 注入参数保持兼容（测试用）。
3. 场景模型映射（chat_service 注入层，不改 scene_config.py 硬编码）：
   - 翻译表：`deepseek-v4-pro -> mimo-v2.5-pro`、`deepseek-v4-flash -> mimo-v2.5`；未知模型名原样透传。
   - 解析顺序：provider 对应 MODEL env 非空优先；否则 scene/contract 模型名经翻译后写入 provider 对应 MODEL env。
   - 翻译 helper 放 deepseek_llm.py，chat_service 调用。
4. main.py interactive 的 current_model 展示改为 provider 感知（读对应 MODEL env + provider 默认）。
5. 错误文案泛化：`_UNAVAILABLE_MESSAGE` / `_MALFORMED_MESSAGE` 去掉 DeepSeek 前缀（如 "LLM provider 暂不可用"）。
6. 保留类名/文件名 `DeepSeekLlmClient` / `deepseek_llm.py`，不 rename。
7. 不改 llm_tool_loop.py、tool schemas、public reading tools、live smoke opt-in env 名。
8. 不联网、不读真实 key、不跑 live smoke；默认 pytest 必须 fake transport 通过。

## Allowed write set（只允许动这些）

- fund_agent/agent/deepseek_llm.py
- fund_agent/service/chat_service.py
- fund_agent/cli/main.py（仅 current_model 展示相关行）
- fund_agent/agent/README.md（provider 配置节）
- tests/fund/agent/test_provider_switching.py（新增，覆盖 provider 解析/映射/向后兼容）
- tests/fund/service/test_chat_service.py（如需要，增补注入映射用例）

禁止动：AGENTS.md、docs/*、tests/README.md（controller 最后收口）；
禁止动 scene_config.py 的 default_name；禁止 commit / push。

## 必须运行的测试命令（跑完把输出贴进交接报告）

1. uv run pytest tests/fund/agent/test_provider_switching.py -v --tb=short
2. uv run pytest tests/fund/agent/test_deepseek_live_smoke.py tests/fund/agent/test_real_llm_adapter.py tests/fund/agent/test_token_usage.py -v --tb=short
3. uv run pytest tests/fund/service/test_chat_service.py tests/fund/cli/test_cli_interactive.py -v --tb=short
4. uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py

## Stop condition

全部测试通过后停止。输出交接报告：changed files、diff 摘要、实际测试命令与输出。
失败时报告最小失败原因，不得声称完成。

## 交接报告格式（回复给 controller）

- changed files: 列表
- diff 摘要: 每文件 1-2 行
- 测试: 实际命令 + passed/failed 数字
- 失败/风险: 若有
