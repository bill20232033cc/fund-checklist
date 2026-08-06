# 2026-08-05 PDF 导出引擎 fallback slice（xelatex → Chrome headless）

> 状态：🟡 待 Mimo review。前置验证已完成：dayu 渲染管线（md→HTML+打印 CSS→Chrome print-to-pdf）已核实；本机 pandoc 3.9 在、Chrome 150 在、无任何 LaTeX 引擎；手动 `pandoc md→html && Chrome --print-to-pdf` 已实测通过（含中文）。

---

## 1. 问题

`FundReadingService._export_pdf`（extraction.py:3770）单一路径：pandoc `--pdf-engine=xelatex`。当前环境无 xelatex/pdflatex/lualatex/tectonic/weasyprint/typst → `generate --format pdf` 必然走 `CalledProcessError` 回退为 Markdown（warning「PDF 导出失败，已回退为 Markdown 格式」），用户拿不到 PDF。

## 2. 参考事实（dayu，已核实，仅借鉴思路）

`dayu/render/render.py`（本地参考代码，**不复制**，复制需过 license gate）：

- md → HTML：pandoc（gfm → html5，`--embed-resources`，github-markdown.css + before/after.html 打印 CSS：`@page` A4、`@media print`、中英文换行、表格/代码块防溢出）。
- HTML → PDF：Headless Chrome，A4 794×1123px，`--print-to-pdf` + `--print-to-pdf-no-header`/`--no-pdf-header-footer`，`--virtual-time-budget=10000`。
- Chrome 查找：`PUPPETEER_EXECUTABLE_PATH` → PATH `google-chrome` → macOS 默认 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。
- Word：pandoc `--reference-doc`（本 slice 不做，列为后续可选）。

## 3. 修复规格

### 3.1 `_export_pdf` 引擎 fallback 链

按顺序尝试，任一成功即返回 `(pdf_path, None)`：

1. **xelatex 可用**：现行 pandoc `--pdf-engine=xelatex`（`shutil.which("xelatex")` 探测，避免无谓 subprocess 失败）。
2. **Chrome 可用**：pandoc md → HTML（`-f gfm -t html5 -s --embed-resources` + 内嵌打印 CSS，`--include-in-header` 注入 `<style>`）→ Chrome headless print-to-pdf：
   - Chrome flags：`--headless --disable-gpu --print-to-pdf=<out> --no-pdf-header-footer --window-size=794,1123 <file://uri>`（A4 794×1123 常量；subprocess timeout 120s）。
   - Chrome 探测顺序：`PUPPETEER_EXECUTABLE_PATH` → PATH `google-chrome` → macOS 默认路径。
3. **两者都不可用/都失败**：回退 md + warning（保留现有 warning 文案语义）。

### 3.2 打印 CSS（原创，不复制 dayu 文件）

新增 `fund_agent/service/assets/report_print.css`（或内嵌 header html 文件），内容：

- `@page { size: A4; margin: ... }` 与 `@media print` 规则（移除屏幕布局约束）；
- 中英文换行（`word-break`/`overflow-wrap`）、表格与代码块防溢出（`table { table-layout: fixed; word-wrap: break-word }` 等）；
- 基础 GitHub 风格排版（标题层级、表格边框）仅打印所需最小集。

### 3.3 边界与失败语义

- 不改 `generate_report` 主链路、不改 `--format` choices、不改公共契约与返回值形状。
- `_export_pdf` 返回签名不变：`(output_path, warning_or_None)`；三种结局都显式分类（xelatex 成功 / chrome 成功 / 回退 md+warning）。
- HTML 中间产物放临时目录（`tempfile`），成功转 PDF 后清理；不污染 reports 目录。

## 4. allowed write set

- `fund_agent/service/extraction.py`（`_export_pdf` 重写 + 小 helper）
- 新增 `fund_agent/service/assets/report_print.css`（或同名 header 文件）
- `tests/fund/service/test_extraction.py`（`-k export` 新增 fallback 单测）
- 真源文档：`docs/design.md`（报告输出渲染节）、`docs/implementation-control.md`（slice 记录）、`AGENTS.md`（如需一行）

禁止：改 generate 主链路 / `--format` 契约 / 公共 DTO；复制 dayu 文件内容（含 css/html）；引入新第三方依赖。

## 5. 验证命令

```bash
uv run pytest tests/fund/service/test_extraction.py -k "export" -q --tb=short
uv run pytest tests/fund/service/test_extraction.py -q --tb=short
```

实数据 smoke（当前环境应走 Chrome 分支）：

```bash
python -c "from pathlib import Path; from fund_agent.service.extraction import FundReadingService; s=FundReadingService(); p,w=s._export_pdf('.fund_e2e_163415/reports/163415-2025-analysis.md', Path('.fund_e2e_163415')); print(p, w)"
```

## 6. 验收口径

- 单测覆盖三态：xelatex 成功 / xelatex 缺→Chrome 成功 / 两者缺→md 回退+warning（mock subprocess 与探测）。
- 实数据 smoke：当前环境 `_export_pdf` 产出真实 PDF（>0 字节，路径含 `.pdf`），warning 为 None。
- `git diff --check` 干净；不 commit / push。

## 7. stop conditions

- 触碰 §4 禁止事项 → 停止。
- 任一验证命令失败 → 停止。
- 实数据 smoke 未产出 PDF（本机 Chrome 可用却失败）→ 停止排查。
