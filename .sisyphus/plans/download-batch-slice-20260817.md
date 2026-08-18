# Slice：download 批量下载 + --import 流水线（2026-08-17 设计）

## 任务界定（口径）

- 来源：快照大任务完善清单环节 1（2026-08-16 用户排期，先做 1）。
- 现状：`download` 一次一个 `--year`（季报还需 `--quarter`），README 用 shell 循环凑批量；`download` 与 `import` 分离，下载后需手动 import。
- 目标：① `download` 支持批量参数（`--year-range` × `--quarters` 矩阵）；② 可选 `--import` 流水线（下载/缓存后自动导入 catalog）。
- 性质：CLI 编排层能力扩展；不改 `download_report` 单次语义与 EID spec。
- 流程：用户拍板 D1-D5 → DS 实施 → MiMo diff review。CIC-lite，不 commit 不 push。

## 实证（2026-08-17，代码核验）

1. `fund_agent/cli/main.py:867` `_run_download_command`：单 `--year`（+`--quarter`），`download_report` 返回单 `DownloadResult`，stdout 输出单对象 JSON；`EidDownloadError.code` 映射 `FailureCode`（`integrity_error`/`not_found`/`unavailable` 等）→ 退出码 2。
2. `fund_agent/fund/document_tools/eid_downloader.py:138` `download_report`：已支持 `report_type`（annual/semiannual/quarterly）+ `quarter` 1-4（非法 fail-closed `schema_drift`）；幂等：文件已存在且非 force 且 `_looks_like_pdf` → `status="cached"` 不重下；下载内容非 PDF → `integrity_error`；文件名 `{fund_code}_{safe_name}_{year}_Q{quarter}_quarterly_report.pdf` / `{fund_code}_{safe_name}_{year}_{report_suffix}.pdf`。
3. `fund_agent/cli/main.py:555` `_parse_year_range`：支持 `2020-2024` 或逗号列表，升序元组（import 已复用）。
4. `fund_agent/cli/main.py:755` import 编排：逐文件 `service.import_local_report(ImportLocalReportRequest(...))`，`DocumentToolError` 分类（`integrity_error` → skipped、其它 → failed），汇总 imported/skipped/failed。
5. `tests/fund/document_tools/test_eid_downloader.py`：现有 9 个用例均为 spec/参数校验单测（不联网）；无批量编排测试。
6. `README.md:57-70`：`download` 一次一年 + shell 循环示例；211 行已有季报/半年报参数说明。

## 设计（决策点 D1-D5）

### D1：批量参数形态（推荐）

- 新增 `--year-range`（复用 `_parse_year_range`，`2025-2026` 或 `2021,2023` 逗号列表）；download parser 上 **无默认值**（`default=None`，区别于 import 的 `"2022-2024"`）。
- `--year` 由 `required=True` 改为 `default=None`，与 `--year-range` 组成 `add_mutually_exclusive_group`；两者皆 `None` → `schema_drift`（退出码 2）。
- 新增 `--quarters`（仅 `quarterly_report`；格式 `1-4` 或 `1,2,3` 逗号列表；与现有单值 `--quarter` 互斥）。**批量模式下**（`--year-range` 存在或 `--quarters` 显式给出）且 `report_type=quarterly_report` 且 `--quarters` 缺省 → 取 `1,2,3,4` 全部期次（批量意图即全期次，cached 幂等保证安全）。
- 单模式（无 `--year-range` 且无 `--quarters`）保持现状：`--year` 必填、quarterly 仍需 `--quarter`（缺省走既有 `schema_drift`）。
- `--quarters` 在 annual/semiannual 下给出 → `schema_drift`（与现有「quarter 仅适用于 quarterly_report」口径一致，不做静默忽略）。
- 命名裁决：保留 `--quarters` 复数命名。`--quarter` 在 download/import/snapshot-quarterly 均为单值 `choices=[1,2,3,4]`；若复用并扩展为多值会破坏现有单值契约与 argparse choices 校验。复数旗标语义自明（多值集合），与单值 `--quarter` 共存且互斥。

### D2：--import 流水线（推荐，本期含）

- 新增 `--import`（flag）+ `--work-dir`（默认 `.fund_checklist`，复用 `DEFAULT_WORK_DIR`）。
- 对每个成功条目（`status` ∈ {downloaded, cached}）调 `service.import_local_report(ImportLocalReportRequest(pdf_path=file_path, fund_code, fund_name, year, work_dir, report_type, quarter))`。
- **仅对 `status ∈ {downloaded, cached}` 且 `file_path is not None` 的条目调用 import**（`DownloadResult.status == "error"` 时 `file_path` 为 `None`，直接构造请求会传 `None`）。
- 复用 import 分类语义：`DocumentToolError` `integrity_error` → skipped；其它分类失败 → failed；未捕获异常 → failed。
- 导入失败不中断后续条目；汇总输出 imported/skipped/failed（与 `_run_import_command` 汇总格式一致）。

### D3：输出格式（推荐）

- 单模式（无 `--year-range` 且无 `--quarters`）→ 保持现有单对象 JSON 输出（字段不变：fund_code/fund_name/year/status/file_path/source_url，**不新增** report_type/quarter），向后兼容成立。
- 批量模式（`--year-range` 存在**或** `--quarters` 存在）→ stdout 输出 JSON 数组（每条目：fund_code/year/quarter/report_type/status/file_path/source_url 或 failure{code,message}）；stderr 输出逐条进度与失败汇总。
- 两种模式 schema 不同是有意设计（新能力新 schema）；批量模式为新增入口，不存在既有 JSON 断言回归（`test_cli.py` 当前无 download 用例）。
- 退出码：全部成功（含全部 cached）→ 0；**全部条目失败 → 2；部分失败 → 0**（与 `_run_import_command` 语义一致：`imported == 0 and failed > 0` → 2；stderr 汇总报告失败明细）。

### D4：失败语义（推荐）

- 单条目 `EidDownloadError` → 记入失败清单（code/message），继续其余条目；最终退出码按 D3（全部失败 → 2，部分失败 → 0）。
- `--import` 下：下载失败条目不导入；导入失败计入汇总（不改变下载成功状态）。

### D5：幂等与限速（推荐）

- 幂等：复用 `download_report` 既有 cached 语义；`--force` 批量强制重下。
- 限速：批量保持默认 `sleep_seconds=0.2`，不透传新参数（避免参数膨胀；确需调速可后续加 `--sleep`）。

## 测试计划

- `tests/fund/cli/test_cli.py`（新增 download 批量用例，mock `download_report` 或注入 fake）：
  - 参数解析：`--year-range`/`--quarters` 合法组合（2 年 × 4 季 = 8 条目矩阵）；`--year` 与 `--year-range` 互斥 → 退出码 2；`--quarters` 越界/非 quarterly 使用 → `schema_drift`；批量模式 quarterly 缺省 quarters = 1-4；`--quarter` 与 `--quarters` 互斥。
  - 批量编排：mock 下载返回 cached/downloaded 混合 → 汇总正确、全部成功退出码 0；单条目 `EidDownloadError` → 不中断、失败清单含 code/message；**退出码显式断言为 0（部分失败，与 import 语义一致）**；全部条目失败 → 退出码 2。
  - `--import` 流水线：mock `import_local_report`（fake service 或 monkeypatch）→ 成功条目逐个导入、integrity 失败 skipped、汇总 imported/skipped/failed；导入失败不中断。
  - 单模式兼容：无 `--year-range`/`--quarters` 时输出仍为单对象 JSON（字段不变，新增回归用例）。
- 回归：`tests/fund/document_tools/test_eid_downloader.py` 9 个用例全量保持通过。
- 退出码语义声明：download 批量与 `_run_import_command` 一致（全部失败 → 2，部分失败 → 0），不得与 import 既有「部分失败 → 0」测试预期冲突。
- 不联网：所有新用例 mock/fake，不触真实 EID。

## NEEDS_FIX 处置（2026-08-17 controller 裁决）

plan review（`docs/reviews/plan-review-20260817-120000.md`）结论 NEEDS_FIX，以下为逐项裁决（最小修复，无 re-review 门）：

- **P0 退出码**：D3/D4 改为与 `_run_import_command` 一致——全部条目失败 → 2，部分失败 → 0；理由：同项目内单一语义，CI/用户 shell 判断一致。
- **P1 `--quarters` 命名**：保留复数旗标，理由见 D1（避免破坏现有单值 `--quarter` 契约）。
- **P1 输出 schema**：单模式不新增字段，向后兼容成立；批量模式新 schema 属新增入口，无既有断言回归。
- **P1 `--year-range` 默认值**：download parser 上 `default=None`，`--year` 改 `default=None` 并互斥；两者皆无 → `schema_drift`。
- **P2 import 边界**：仅 `status ∈ {downloaded, cached}` 且 `file_path is not None` 的条目进入 import。
- **P2 退出码测试**：测试计划显式声明批量退出码与 import 一致，并加「全部失败 → 2 / 部分失败 → 0」双向用例。

## 验证命令

```bash
uv run pytest tests/fund/cli/test_cli.py -k "download" -q --tb=short
uv run pytest tests/fund/document_tools/test_eid_downloader.py -q --tb=short
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -q --tb=short
git diff --check
```

## 文档同步

1. `README.md` download 节：批量用法示例（`--year-range`/`--quarters`/`--import`），替换/补充 shell 循环示例。
2. `docs/design.md` §6.25 追加裁决：download 批量参数（`--year-range` × `--quarters`，quarterly 缺省全期次，`--year` 互斥）+ `--import` 流水线（复用 import_local_report 与分类语义）。
3. `docs/implementation-control.md` 追加本 slice 记录。
4. `tests/README.md`（如测试命令变化）。

## 非目标（明确）

- 不改 `download_report` 签名与单次语义、不改 EID spec/reportCode 映射。
- 不做多 provider matrix / 仓储协议拆分（design.md 既有边界）。
- 不改 `import` 命令 CLI 契约（`--import` 只复用 service 层）。
- 不新增 `--sleep` 等限速参数（本期）。
- 不联网测试。
- 不 commit / 不 push。

## allowed write set（DS 执行边界，禁止越界）

- `fund_agent/cli/main.py`（download parser + `_run_download_command` 批量编排；可提取纯函数便于单测）
- `tests/fund/cli/test_cli.py`
- `README.md`
- `docs/design.md`
- `docs/implementation-control.md`
- `tests/README.md`（按需）

（plan / diff-review artifact 由 controller / reviewer 产出，不在 DS write set。）
