# Codex Agent 断连事故修复记录（2026-08-08）

## 摘要

2026-08-08 凌晨，tmux 中两个 codex agent（AgentController / AgentCodex）突然无法连接 LLM（上游 404），此前一直正常。根因是 **cc-switch 自动接管 codex 配置** 时把 `~/.codex/config.toml` 的 `base_url` 改写为本地代理（`127.0.0.1:15721`），而 cc-switch 代理转发 OpenCode Go 时路径拼接错误导致上游 404。旧进程因持有接管前（直连）配置而正常；进程重启后加载代理配置即断连。

修复方式：恢复直连 `base_url`，保持 `wire_api = "responses"` 不变，停用 cc-switch 对 codex 的代理接管。

## 时间线（2026-08-08）

| 时间 | 事件 |
|---|---|
| 23:48 / 23:49 | 两个 codex 启动，读取【直连 opencode.ai】配置 → 正常（44 条 200） |
| 23:56:01 | cc-switch 启动 → 自动接管 codex → 改写 `config.toml` base_url 为 `http://127.0.0.1:15721/v1`（日志：`检测到上次异常退出（存在接管残留），正在恢复 Live 配置...Codex Live 配置已接管`） |
| 00:00 | 已启动的 codex 进程仍持有直连连接（PID 直连 `172.65.90.23:443` = opencode.ai），不受影响 |
| 00:01:29 | cc-switch 代理首次收到转发请求 → 上游 `https://opencode.ai/zen/go/v1` 返回 **404**（HTML 页面） |
| 00:03 后 | 重启 codex（新进程）→ 加载代理配置 → 全部 404 → 断连 |
| 00:05+ | 排查确认根因（直连 200 / 代理 404 对照） |
| ~00:10 | 修复：恢复直连 + 停用接管；重启两个 agent → 连接恢复（"Hello." 正常返回） |

## 根因分析

### 直接原因

`~/.codex/config.toml` 的 `[model_providers.custom]` 段 `base_url` 被 cc-switch 接管改写：

```toml
# 接管后（错误，走代理）
base_url = "http://127.0.0.1:15721/v1"
```

cc-switch 代理把请求转发到 `https://opencode.ai/zen/go/v1` 时返回 404（HTML 页面而非 API 响应），所有经代理的请求失败。

### 验证证据（实测对照）

| 路径 | 结果 |
|---|---|
| 直连 `https://opencode.ai/zen/go/v1/responses`（Responses API, deepseek-v4-flash） | **HTTP 200**，标准 `object: "response"` |
| 直连 `https://opencode.ai/zen/go/v1/chat/completions`（OpenAI-compatible） | **HTTP 200**（仅连通性测试，非修复目标） |
| 经代理 `http://127.0.0.1:15721/v1/responses` | **HTTP 404**（上游 HTML 页面） |
| 经代理 `http://127.0.0.1:15721/v1/chat/completions` | **HTTP 404**（同上） |

### 与官方文档核对（https://opencode.ai/docs/zh-cn/go/）

- OpenCode Go 支持 Responses API 端点 `https://opencode.ai/zen/go/v1/responses`（GPT 5.6 Luna 等模型）
- DeepSeek 系列官方列出的端点是 `.../chat/completions`，但 **Responses 端点实测同样可用**（200）
- Codex 原生走 Responses API，因此 **`wire_api = "responses"` 配置正确，无需改动**
- 唯一错误是 base_url 被改写为本地代理，且代理转发本身有 bug

### 深层机制

- codex 进程在启动时读取一次配置，运行期间不重读。接管前启动的进程持直连配置 → 正常
- 重启后加载已被改写的代理配置 → 断连
- cc-switch 的 `live_takeover_active` 标记在异常退出后残留，重启时自动恢复接管（`检测到上次异常退出`）
- `auth.json` 被改写为 `{"OPENAI_API_KEY": "PROXY_MANAGED"}`

## 修复内容

| 文件/对象 | 修复前 | 修复后 |
|---|---|---|
| `~/.codex/config.toml` `[model_providers.custom]` base_url | `http://127.0.0.1:15721/v1`（代理） | `https://opencode.ai/zen/go/v1`（直连） |
| `wire_api` | `responses` | `responses`（未动） |
| `~/.codex/auth.json` | `PROXY_MANAGED` | 真实 token |
| cc-switch DB `proxy_config` codex 行 | `proxy_enabled=1, enabled=1, live_takeover_active=1` | `proxy_enabled=0, enabled=0, live_takeover_active=0` |

备份：`~/.codex/config.toml.bak-20260808-before-fix`

## 验证结果

- 两个 codex agent（pane 0 / pane 1）重启后正常启动（v0.147.0, deepseek-v4-flash）
- 实际请求返回 "Hello."，token 正常消耗（24,640 input + 3 output）
- 无 404 错误

## 复盘要点 / 后续注意

1. **cc-switch 应用仍在运行**（PID 2727）。本次已停用数据库里的接管标记，但若 cc-switch 重启，可能重新接管。若再次断连，优先检查 `config.toml` 的 base_url 是否又被改成 `127.0.0.1:15721`。
2. 建议在 cc-switch GUI 里彻底关闭 codex 的代理接管（或删除 codex 代理配置），避免复发。
3. 若后续仍想用 cc-switch 代理 + 用量统计，需先修复 cc-switch 的转发 bug（把请求拼到 `opencode.ai/zen/go/v1` 根路径导致 404）——这是 cc-switch 自身问题，与本仓库代码无关。
4. **教训**：cc-switch 的 Live 接管会静默改写 codex 配置；依赖 cc-switch 切换 provider 时，进程重启时机与接管时机之间的配置不一致是断连高风险点。

## 验证命令（如需复测）

```bash
# 直连 opencode-go Responses 端点
curl -s -m 20 -o /dev/null -w "HTTP %{http_code}\n" \
  "https://opencode.ai/zen/go/v1/responses" -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"model":"deepseek-v4-flash","input":"hi","max_output_tokens":16}'

# 检查 codex 配置是否被代理接管
grep base_url ~/.codex/config.toml
```
