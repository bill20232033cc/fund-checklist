# Interactive 手动测试调试记录

**日期**：2026-07-27
**测试命令**：`uv run fund-checklist interactive --fund-code 004393`
**基金**：安信企业价值优选混合型证券投资基金 (004393)，年份 2025

---

## 1. 测试过程

| 轮次 | 现象 | 根因 | 修复 |
|------|------|------|------|
| 1 | 输入问题后**完全空白**，无任何输出 | `_failed_result` 设 `answer=""`，error 写入 `failure` 字段，但 CLI/chat_service 从不检查 `failure` | `chat_service.py`: 加 `agent_result.failure` 检查，失败时展示错误信息 |
| 2 | 显示 `DeepSeek LLM provider 暂不可用` | 默认模型名 `deepseek-v4-pro-thinking` 不是合法 DeepSeek API 模型名（合法：`deepseek-v4-pro` / `deepseek-v4-flash`），API 返回 400 | `main.py:1134` → `deepseek-v4-flash`；`scene_config.py:100` → `deepseek-v4-pro` |
| 3 | API 通了，但交替出现三个错误 | interactive 的 system prompt 由 5 个 fragment 拼成，其中 `tools_scene.md` 要求 JSON+citation，`interactive/scene.md` 说"不需要 JSON 包装"——LLM 收到矛盾指令，输出 markdown → `_final_result` 校验 citations 为空 → 拒绝 | `interactive/scene.md`: 移除矛盾指令，对齐 JSON 格式；`tools_scene.md`: 明确 citation 复制规则 |
| 4 | 仍有 `缺少受控 citation` / `工具调用不被允许` | prompt 修复不够——LLM 在多轮 tool call 后仍不按 JSON 格式输出 | **架构层面问题**（见下） |

## 2. 根因分析

### 2.1 即时 bug（已修复）

三个代码级 bug：

1. **静默失败**：`_failed_result()` 返回 `answer=""` + `failure=ToolFailure(...)`，但 `chat_service.chat_turn` 只读 `answer`，CLI 打印空行
2. **模型名无效**：`deepseek-v4-pro-thinking` 不在 DeepSeek API 支持列表中
3. **prompt 自相矛盾**：`interactive/scene.md` line 12 与 `tools_scene.md` line 9 对输出格式的要求相反

### 2.2 temperature=0 硬编码（未修复）

`deepseek_llm.py:505` 的 `_request_payload` 硬编码了 `"temperature": 0`：

```python
def _request_payload(*, document_id, query, tool_results, model, stream, system_prompt, ...):
    return {
        ...
        "temperature": 0,   # ← 硬编码，忽略 SceneConfig
        ...
    }
```

但 `SceneConfig` 为 interactive 设置的是 `temperature=0.7`（`scene_config.py:100`）。`ChatService` 读了这个值（`chat_service.py:179`）：

```python
temperature = self._scene_config.model.temperature  # → 0.7
```

但 **这个 `temperature` 变量从未传递给 `DeepSeekLlmClient`** ——构造函数不接受 temperature 参数，`_request_payload` 也没有 temperature 入参。

**影响**：temperature=0 使模型极度确定性，可能降低对 tool calling 协议的遵循意愿。Interactive 场景设计为 0.7（适合对话），但实际发出的请求全部是 0。

### 2.3 "LLM 工具调用不被允许" 的具体触发路径

`llm_tool_loop.py:581-589` 的 `_invoke_tool_call` 有两个校验：

```python
# 校验 1：tool name 是否在白名单
tool_name = _coerce_tool_name(call.tool_name)
if tool_name is None or tool_name not in ALLOWED_LLM_TOOL_NAMES:
    return ToolFailure(..., _TOOL_NOT_ALLOWED_MESSAGE)

# 校验 2：document_id 是否与 runner.run() 传入的一致
if (
    tool_name is not ToolName.AGGREGATE_MULTI_YEAR_ANNUAL_PERFORMANCE
    and call.document_id != expected_document_id
):
    return ToolFailure(..., _TOOL_NOT_ALLOWED_MESSAGE)
```

触发路径有两个：
- **校验 1**：LLM 返回的 tool name（如 `"search"`）不在枚举中（`search_document` / `read_section` / …）→ `_coerce_tool_name` 返回 None
- **校验 2**：LLM 返回的 `document_id` 与 `runner.run(document_id=...)` 传入的不一致

校验 2 是最可能的触发点：`document_id` 格式为 `fund_code-year-report_type-fingerprint_prefix`（16 位 hex），LLM 需要从 user message JSON 中完整复制此字符串。如果 LLM 截断或自行构造 `document_id`，校验必然失败。

### 2.4 架构矛盾（未修复）

Interactive 模式期望"多轮对话"，但底层 agent loop 设计为"单次 Q&A"：

```
interactive 场景要求：          agent loop 实际提供：
"多轮对话"                    独立 runner.run()，每轮互不可见
"上下文记忆"                  session.turns 存储但 LLM 收不到
"自然语言 Markdown"           _final_result 强制 JSON + citation 校验
```

关键证据：`deepseek_llm.py:484-506` 构造的 API messages 只有 2 条：

```python
messages = [
    {"role": "system", "content": "【5个fragment拼成的prompt】"},
    {"role": "user", "content": '{"document_id":"...", "query":"他有什么经验？", ...}'}
]
```

LLM 看不到上一轮对话，无法做代词消解、无法维持对话流。

### 2.5 跨轮工具结果不可见（未修复）

即使注入了 `session.turns` 历史轮次（作为 user/assistant messages），LLM 仍然**看不到上轮的工具调用结果**。`ToolResult` 仅存在于 `runner.run()` 的局部循环中，run 结束后即销毁。

**影响**：
- 用户追问"那托管费呢"时，LLM 看不到上轮 read_table 的结果，必须重新 search → read_section → read_table
- 重新读取可能得到不同的表格行顺序或截断结果，导致引用不一致
- 浪费工具调用预算（interactive 的 max_steps=20）

### 2.6 这不是一个对话 Agent

该 agent 的本质是 **fail-closed tool-enforced retrieval pipeline**（以 LLM 为查询规划器的受控文档检索引擎），不是 OpenAI/Anthropic 意义上的 Agent：

- 无对话历史进入 LLM context
- 无推理/反思/自我纠正
- 无通用知识或人格
- Fail-closed：任何校验失败 → 空回答 + 错误码

最匹配的使用场景是 `ask` 命令（单次受控 Q&A），不是 `interactive`（多轮对话）。

## 3. 修复方向

| 优先级 | 方向 | 说明 | 影响范围 |
|--------|------|------|---------|
| P0 | temperature 透传 | `_request_payload` 增加 `temperature` 参数，从 SceneConfig 透传 | `deepseek_llm.py`、`chat_service.py` |
| P1 | LLM context 接入 turns | 将最近 N 轮对话注入 API messages（system + [history] + current user） | `deepseek_llm.py`、`chat_service.py` |
| P1 | 跨轮证据复用 | 注入历史轮次时同时注入 assistant 回答（含 citations），避免重复工具调用 | `chat_service.py`、`session_models.py` |
| P2 | 场景感知校验 | interactive 允许无 citation FinalAnswer，ask/repair/regenerate 保持严格 | `SceneConfig` + `_final_result` |
| — | generate/audit 不受影响 | generate 使用 `llm_client.generate_text()` 直接调用，不经过 tool loop | 无 |

### 3.1 P0: temperature 透传（最小改动）

`_request_payload` 增加 `temperature: float = 0` 参数；`DeepSeekLlmClient` 从 env 或构造参数读取 temperature；`ChatService` 将 `self._scene_config.model.temperature` 传入。

改动量约 5 行，不改变任何校验逻辑，但可能显著改善 LLM 对 tool calling 协议的遵循。

### 3.2 P1: LLM context 接入 turns

`_request_payload` 构造 messages 时，在 system 和当前 user 之间插入历史轮次：

```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "第1轮用户问题"},
    {"role": "assistant", "content": "第1轮回答"},
    # ...
    {"role": "user", "content": '{"document_id":"...", "query":"当前问题", ...}'},
]
```

`DeepSeekLlmClient.next_step()` 新增 `history_messages` 参数；`ChatService.chat_turn()` 从 `session.turns` 收集最近 N 轮（如 6 轮），格式化后传入。

**注意**：注入的 assistant 回答应保留原始 answer 文本（不含 JSON 封装），保持格式一致。

### 3.3 P1: 跨轮证据复用

注入历史 assistant 回答时，可以附带上轮的 citations 列表作为上下文，使 LLM 知道之前引用了哪些 locator。但不需要注入完整的 tool results（token 太大）。

或者更简单的做法：在 session turns 的 assistant content 中已经存了 answer 文本，这段文本本身就是从工具结果生成的，已经包含了事实信息。如果 LLM 能看到这些回答，它就能引用之前提到的数据，虽然无法直接获取 citation locator。

### 3.4 P2: 场景感知校验

`_final_result` 中的 citation 校验可以根据 scene 类型做差异化：
- `ask` / `repair` / `regenerate`：严格要求 citations
- `interactive`：对非事实陈述（追问、确认、导航）豁免 citations，对事实陈述仍要求

但需要注意：**仅豁免 citation 校验无法解决代词消解和上下文连贯问题**——必须先完成 P1（注入 turns）才有意义。

## 4. 涉及文件

### 4.1 已修复项

| 文件 | 改动 |
|------|------|
| `fund_agent/service/chat_service.py:197-202` | 加 failure 检查 |
| `fund_agent/cli/main.py` | 默认模型 → deepseek-v4-flash |
| `fund_agent/service/scene_config.py:100` | interactive 模型 → deepseek-v4-pro |
| `fund_agent/service/prompts/interactive/scene.md` | 移除"不需要 JSON 包装"，对齐 JSON 格式 |
| `fund_agent/service/prompts/ask/tools_scene.md` | 明确 citation 复制规则 |
| `tests/fund/service/test_chat_service.py` | failure 传播测试 |

### 4.2 待修复项

| 文件 | 改动 |
|------|------|
| `fund_agent/agent/deepseek_llm.py:472-507` | `_request_payload` 增加 `temperature` 参数 |
| `fund_agent/agent/deepseek_llm.py:222-242` | `DeepSeekLlmClient.__init__` 增加 `temperature` 参数 |
| `fund_agent/agent/deepseek_llm.py:249-327` | `next_step()` 透传 temperature |
| `fund_agent/agent/deepseek_llm.py:472-507` | `_request_payload` 增加 `history_messages` 参数 |
| `fund_agent/service/chat_service.py:155-197` | 从 session.turns 收集历史轮次，传入 runner/llm_client |
| `fund_agent/agent/llm_tool_loop.py:659-709` | `_final_result` 增加 scene-aware 校验（可选） |

## 5. 补充：分析方法论说明

本调试记录的分析路径：

1. **直接代码阅读**：逐层追踪 `CLI → ChatService → LlmToolLoopRunner → DeepSeekLlmClient → _request_payload`，确认数据流
2. **prompt 模板比对**：阅读 `prompts/base/`、`prompts/ask/`、`prompts/interactive/` 下所有 fragment，确认指令是否一致
3. **约束层反向追踪**：从两个错误消息出发，定位 `_invoke_tool_call` 和 `_final_result` 的具体校验逻辑
4. **跨轮分析**：确认 `session.turns` 存储但未注入 LLM context 的事实
5. **遗漏项识别**：发现 temperature 硬编码、跨轮工具结果不可见等问题

分析结论验证：`docs/design.md` 和 `fund_agent/agent/README.md` 中均未提到 temperature 参数透传或 turns 注入机制，与代码事实一致。
