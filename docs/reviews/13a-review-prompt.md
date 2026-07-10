# Slice 13A Code Review Prompt

## 你的角色

你是一个严格的 code reviewer。请审查以下 diff，找出 correctness、stability、maintainability 问题。

## 项目背景

这是一个基金年报阅读工具（fund-checklist），核心职责是：
- 导入基金 PDF 年报 → Docling 解析 → 结构化存储
- 提供 7 个 reading tools（list_reports、list_sections、read_section、search_document、list_tables、read_table、get_excerpt）
- 基于 reading tools 做数据抽取（持仓、费率、业绩、资产配置）和审计

本次变更（Slice 13A）新增 `fund-checklist generate` 子命令，基于多年年报数据生成 8 章结构化分析报告。

## 硬边界（违反即 P0）

1. **禁止投资建议**：工具层不得输出"买入""卖出"建议；不得预测未来收益或市场走势。
2. **禁止超出公开信息的因果推断**：不得猜测基金经理动机。
3. **所有工具输出必须可溯源到年报 locator**：数据必须能追溯到具体年报的章节/表格位置。
4. **禁止直接消费 raw PDF / raw Docling JSON / 本地路径**：所有数据必须通过 FundReadingService 统一入口。
5. **LLM 生成的分析文本必须严格基于抽取数据**：不得凭空捏造数据。
6. **Python 代码使用类型注解和 dataclass**：函数、类、模块必须有中文 docstring。
7. **禁止把显式参数塞进 extra_payload**：公共参数必须显式声明。
8. **禁止魔法字符串/魔法数字**：source kind、failure code、tool name 应集中定义。

## Review 维度

### Correctness
- 数据流是否正确？多年数据提取 → 章节生成 → 输出的链路有无断裂？
- 边界情况：某年数据缺失时是否正确处理？空数据集？
- 生成的 Markdown 表格格式是否正确？
- PDF 导出（pandoc）的错误处理是否合理？

### Stability
- 异常处理是否 fail-closed？是否有未捕获异常导致静默失败？
- subprocess 调用 pandoc 是否有注入风险？
- 文件写入是否有路径遍历风险？

### Maintainability
- 是否有重复代码可以复用现有方法？
- 命名是否清晰一致？
- docstring 是否准确？

### 与硬边界的一致性
- 报告内容是否违反"禁止投资建议"边界？
- 数据是否可溯源？chapters 的 data_sources 是否足够？
- LLM 生成的内容是否有无数据支撑的风险？

## Diff

```diff
diff --git a/fund_agent/cli/main.py b/fund_agent/cli/main.py
index 6ddad1a..51c3855 100644
--- a/fund_agent/cli/main.py
+++ b/fund_agent/cli/main.py
@@ -26,6 +26,7 @@ from fund_agent.service import (
     ExtractFeeRatesMultiYearRequest,
     ExtractHoldingsRequest,
     FundReadingService,
+    GenerateReportRequest,
     ImportLocalReportRequest,
     ReadLocalReportRequest,
 )
@@ -93,6 +94,8 @@ def run_cli(
             return _run_audit_command(args, stdout=stdout, stderr=stderr)
         if args.command == "deep-audit":
             return _run_deep_audit_command(args, stdout=stdout, stderr=stderr)
+        if args.command == "generate":
+            return _run_generate_command(args, stdout=stdout, stderr=stderr)
     except DocumentToolError as exc:
         _write_classified_failure(ToolFailure(code=exc.code, message=exc.message), stderr)
         return CLASSIFIED_FAILURE_EXIT_CODE
@@ -165,6 +168,14 @@ def build_parser() -> argparse.ArgumentParser:
     deep_audit_parser.add_argument("--fund-code", required=True)
     deep_audit_parser.add_argument("--year", required=True, type=int)
     deep_audit_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
+
+    generate_parser = subparsers.add_parser("generate")
+    generate_parser.add_argument("--fund-code", required=True)
+    generate_parser.add_argument("--fund-name", required=True)
+    generate_parser.add_argument("--year", required=True, type=int)
+    generate_parser.add_argument("--years", default="2020,2021,2022,2023,2024")
+    generate_parser.add_argument("--format", dest="output_format", default="json", choices=["json", "markdown", "pdf"])
+    generate_parser.add_argument("--work-dir", default=Path(DEFAULT_WORK_DIR), type=Path)
     return parser


@@ -696,6 +707,54 @@ def _run_deep_audit_command(args: argparse.Namespace, *, stdout: TextIO, stderr:
     return SUCCESS_EXIT_CODE


+def _run_generate_command(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
+    """生成基金分析报告。"""
+    years = _parse_years(args.years)
+    service = FundReadingService()
+    result = service.generate_report(
+        GenerateReportRequest(
+            fund_code=args.fund_code,
+            fund_name=args.fund_name,
+            report_year=args.year,
+            years=years,
+            work_dir=Path(args.work_dir),
+            output_format=args.output_format,
+        )
+    )
+    if result.failure is not None:
+        _write_classified_failure(result.failure, stderr)
+        return CLASSIFIED_FAILURE_EXIT_CODE
+
+    output = {
+        "fund_code": result.report.fund_code,
+        "fund_name": result.report.fund_name,
+        "report_year": result.report.report_year,
+        "chapters": [
+            {
+                "chapter_id": c.chapter_id,
+                "title": c.title,
+                "content": c.content,
+                "data_sources": list(c.data_sources),
+            }
+            for c in result.report.chapters
+        ],
+        "metadata": result.report.metadata,
+        "output_path": result.output_path,
+    }
+    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
+    return SUCCESS_EXIT_CODE
+
+
diff --git a/fund_agent/service/reading_service.py b/fund_agent/service/reading_service.py
index de8c7ab..00df7c1 100644
--- a/fund_agent/service/reading_service.py
+++ b/fund_agent/service/reading_service.py
@@ -4,8 +4,10 @@ from __future__ import annotations

 import json
 import re
+import subprocess
 from collections.abc import Callable
 from dataclasses import dataclass
+from datetime import date
 from pathlib import Path
 from typing import Literal

@@ -872,6 +874,92 @@ class DeepAuditResult:
     failure: ToolFailure | None = None


+@dataclass(frozen=True)
+class ReportChapter:
+    """报告单章节。"""
+    chapter_id: int
+    title: str
+    content: str
+    data_sources: tuple[str, ...] = ()
+
+
+@dataclass(frozen=True)
+class FundReport:
+    """基金分析报告。"""
+    fund_code: str
+    fund_name: str
+    report_year: int
+    chapters: tuple[ReportChapter, ...]
+    metadata: dict[str, object] | None = None
+
+
+@dataclass(frozen=True)
+class GenerateReportRequest:
+    """报告生成请求。"""
+    fund_code: str
+    fund_name: str
+    report_year: int
+    years: tuple[int, ...] | list[int] = (2020, 2021, 2022, 2023, 2024)
+    work_dir: Path = Path(".fund_checklist")
+    output_format: str = "json"
+
+
+@dataclass(frozen=True)
+class GenerateReportResult:
+    """报告生成结果。"""
+    report: FundReport | None = None
+    output_path: str | None = None
+    warnings: tuple[str, ...] = ()
+    failure: ToolFailure | None = None
+
+
 # ... (中间省略已有代码)

+    def generate_report(self, request: GenerateReportRequest) -> GenerateReportResult:
+        """生成基金分析报告。"""
+        try:
+            years = tuple(request.years) if request.years else tuple(range(request.report_year - 4, request.report_year + 1))
+            repository = _repository(Path(request.work_dir))
+            catalog_reports = repository.list_reports()
+
+            docs_by_year: dict[int, str] = {}
+            for report in catalog_reports:
+                if report.get("fund_code") == request.fund_code and report.get("year") in years:
+                    year = int(report["year"])
+                    docs_by_year[year] = str(report["document_id"])
+
+            annual_docs = [
+                AnnualReportDocument(year=year, document_id=doc_id)
+                for year, doc_id in sorted(docs_by_year.items())
+            ]
+
+            if not annual_docs:
+                return GenerateReportResult(
+                    failure=ToolFailure(code=FailureCode.NOT_FOUND, message=f"未找到 {request.fund_code} 的年报数据"),
+                )
+
+            holdings_data = self._extract_report_holdings(request.fund_code, annual_docs, request.work_dir)
+            fee_data = self._extract_report_fees(request.fund_code, annual_docs, request.work_dir)
+            performance_data = self._extract_report_performance(request.fund_code, annual_docs, request.work_dir)
+            allocation_data = self._extract_report_allocation(request.fund_code, annual_docs, request.work_dir)
+
+            chapters = self._generate_chapters(
+                fund_code=request.fund_code,
+                fund_name=request.fund_name,
+                report_year=request.report_year,
+                holdings=holdings_data,
+                fees=fee_data,
+                performance=performance_data,
+                allocation=allocation_data,
+            )
+
+            report = FundReport(
+                fund_code=request.fund_code,
+                fund_name=request.fund_name,
+                report_year=request.report_year,
+                chapters=tuple(chapters),
+                metadata={
+                    "generated_at": date.today().isoformat(),
+                    "data_years": list(years),
+                    "template_version": "v1",
+                },
+            )
+
+            output_path = None
+            warnings: list[str] = []
+            if request.output_format == "markdown":
+                output_path = self._export_markdown(report, request.work_dir)
+            elif request.output_format == "pdf":
+                md_path = self._export_markdown(report, request.work_dir)
+                output_path, pdf_warning = self._export_pdf(md_path, request.work_dir)
+                if pdf_warning:
+                    warnings.append(pdf_warning)
+
+            return GenerateReportResult(
+                report=report,
+                output_path=output_path,
+                warnings=tuple(warnings),
+                failure=None,
+            )
+
+        except DocumentToolError as exc:
+            return GenerateReportResult(failure=ToolFailure(code=exc.code, message=exc.message))
+        except Exception as exc:
+            return GenerateReportResult(failure=ToolFailure(code=FailureCode.UNAVAILABLE, message=f"报告生成暂不可用: {exc}"))
+
+    # _extract_report_holdings, _extract_report_fees, _extract_report_performance, _extract_report_allocation
+    # 均为复用现有 multi-year 提取方法的薄包装
+
+    def _generate_chapters(self, ...) -> list[ReportChapter]:
+        """生成 8 章报告内容。"""
+        # Ch0: 投资要点概览 - 从 performance 数据生成
+        # Ch1: 基金概况 - 基本信息
+        # Ch2: 业绩分析 - 表格形式展示多年业绩
+        # Ch3: 持仓分析 - 多年 Top10 持仓表格
+        # Ch4: 资产配置 - 多年资产配置表格
+        # Ch5: 费率分析 - 多年费率表格
+        # Ch6: 分红分析 - 暂不支持，写死占位文本
+        # Ch7: 风险提示 - 模板化风险声明
+
+    def _export_markdown(self, report: FundReport, work_dir: Path) -> str:
+        """导出 Markdown 文件到 work_dir/reports/ 目录。"""
+
+    def _export_pdf(self, md_path: str, work_dir: Path) -> tuple[str, str | None]:
+        """使用 pandoc 导出 PDF，失败时回退为 Markdown。"""
+        pdf_path = md_path.replace(".md", ".pdf")
+        try:
+            subprocess.run(
+                ["pandoc", md_path, "-o", pdf_path, "--pdf-engine=xelatex"],
+                check=True,
+                capture_output=True,
+            )
+            return pdf_path, None
+        except FileNotFoundError:
+            return md_path, "pandoc 未安装，已回退为 Markdown 格式"
+        except subprocess.CalledProcessError:
+            return md_path, "PDF 导出失败，已回退为 Markdown 格式"
```

## 测试 Diff

```diff
diff --git a/tests/fund/cli/test_cli.py b/tests/fund/cli/test_cli.py
index 7c64e34..db1f29b 100644
--- a/tests/fund/cli/test_cli.py
+++ b/tests/fund/cli/test_cli.py
@@ -1963,3 +1963,107 @@ def test_deep_audit_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
+
+def test_generate_parser_accepts_valid_args() -> None:
+    """generate 子命令 parser 必须接受合法参数。"""
+    parser = build_parser()
+    args = parser.parse_args([
+        "generate", "--fund-code", "004393",
+        "--fund-name", "安信企业价值优选混合型证券投资基金",
+        "--year", "2024", "--years", "2022,2023,2024", "--format", "json",
+    ])
+    assert args.command == "generate"
+    assert args.fund_code == "004393"
+    assert args.year == 2024
+    assert args.output_format == "json"
+
+def test_generate_exits_2_when_no_data(monkeypatch, tmp_path: Path) -> None:
+    """无数据时 generate 必须返回 exit 2。"""
+    # 使用 monkeypatch 替换 FundReadingService，返回 NOT_FOUND failure
+    # 验证 exit_code == CLASSIFIED_FAILURE_EXIT_CODE
+    # 验证 stderr 包含 "not_found"
+
+def test_generate_json_output_on_success(monkeypatch, tmp_path: Path) -> None:
+    """generate 成功时必须输出 JSON 格式的报告。"""
+    # 使用 monkeypatch 替换 FundReadingService，返回包含 8 章的 fake_report
+    # 验证 exit_code == SUCCESS_EXIT_CODE
+    # 验证 JSON 输出包含 fund_code, report_year, 8 chapters
+    # 验证 chapters[0].title == "投资要点概览"
```

## 请输出

按以下格式输出 review 结果：

### P0（必须修复）
- 问题描述 + 文件:行号 + 修复建议

### P1（建议修复）
- 问题描述 + 文件:行号 + 修复建议

### P2（可选优化）
- 问题描述 + 建议

### 总结
一段话概括代码质量和主要风险。
