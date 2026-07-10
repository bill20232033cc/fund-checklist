请严格审查以下 Python 代码变更（Slice 13A: fund-checklist generate 子命令）。

## 项目背景
基金年报阅读工具。核心：PDF → Docling → 7 个 reading tools → 数据抽取。
本次变更新增 `fund-checklist generate` 子命令，基于多年年报数据生成 8 章结构化分析报告。

## 硬边界（违反即 P0）
1. 禁止投资建议（买入/卖出/预测收益）
2. 所有数据必须可溯源到年报 locator
3. 禁止直接消费 raw PDF / raw Docling JSON / 本地路径
4. LLM 生成文本必须基于抽取数据，不得捏造
5. 禁止魔法字符串；failure code / tool name 集中定义

## 核心变更
- `fund_agent/cli/main.py`：新增 `_run_generate_command`，解析 CLI 参数调用 `service.generate_report()`
- `fund_agent/service/reading_service.py`：新增 `ReportChapter`、`FundReport`、`GenerateReportRequest`、`GenerateReportResult` 四个 dataclass；新增 `generate_report()` 方法（提取多年数据 → 生成 8 章 → 导出 Markdown/PDF）
- `tests/fund/cli/test_cli.py`：3 个测试（parser 接受合法参数、无数据返回 exit 2、成功输出 JSON）

## 关键代码片段

**generate_report 主流程：**
```python
def generate_report(self, request: GenerateReportRequest) -> GenerateReportResult:
    try:
        years = tuple(request.years) if request.years else tuple(range(request.report_year - 4, request.report_year + 1))
        repository = _repository(Path(request.work_dir))
        catalog_reports = repository.list_reports()
        docs_by_year: dict[int, str] = {}
        for report in catalog_reports:
            if report.get("fund_code") == request.fund_code and report.get("year") in years:
                year = int(report["year"])
                docs_by_year[year] = str(report["document_id"])
        annual_docs = [AnnualReportDocument(year=year, document_id=doc_id) for year, doc_id in sorted(docs_by_year.items())]
        if not annual_docs:
            return GenerateReportResult(failure=ToolFailure(code=FailureCode.NOT_FOUND, ...))
        # 提取数据 → 生成章节 → 导出
        ...
    except DocumentToolError as exc:
        return GenerateReportResult(failure=ToolFailure(code=exc.code, message=exc.message))
    except Exception as exc:
        return GenerateReportResult(failure=ToolFailure(code=FailureCode.UNAVAILABLE, ...))
```

**PDF 导出：**
```python
def _export_pdf(self, md_path: str, work_dir: Path) -> tuple[str, str | None]:
    pdf_path = md_path.replace(".md", ".pdf")
    try:
        subprocess.run(["pandoc", md_path, "-o", pdf_path, "--pdf-engine=xelatex"], check=True, capture_output=True)
        return pdf_path, None
    except FileNotFoundError:
        return md_path, "pandoc 未安装，已回退为 Markdown 格式"
    except subprocess.CalledProcessError:
        return md_path, "PDF 导出失败，已回退为 Markdown 格式"
```

**章节生成（8 章）：**
- Ch0 投资要点：从 performance 数据生成摘要
- Ch1 基金概况：基本信息
- Ch2 业绩分析：多年表格
- Ch3 持仓分析：多年 Top10 表格
- Ch4 资产配置：多年表格
- Ch5 费率分析：多年表格
- Ch6 分红分析：写死占位文本"暂不支持"
- Ch7 风险提示：模板化声明

**CLI 测试：**
```python
def test_generate_parser_accepts_valid_args(): ...
def test_generate_exits_2_when_no_data(monkeypatch, tmp_path): ...
def test_generate_json_output_on_success(monkeypatch, tmp_path): ...
```

## 请按以下格式输出

### P0（必须修复）
问题 + 文件:行号 + 修复建议

### P1（建议修复）
问题 + 文件:行号 + 修复建议

### P2（可选优化）
问题 + 建议

### 总结
一段话概括代码质量和主要风险。
