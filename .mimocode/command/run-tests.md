---
description: "运行 fund-checklist 测试套件。用法: run-tests [core|generate|audit|all|live]"
---

运行 fund-checklist 测试组。默认 `core`。

根据参数 `$ARGUMENTS`（默认 core）执行对应测试：

## core — 最小验证命令（AGENTS.md 规定）

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py -v --tb=short 2>&1
```

## generate — 报告生成相关

```bash
uv run pytest tests/fund/service/test_llm_chapter_generation.py tests/fund/cli/test_cli.py -k "generate" -x -q 2>&1
```

## audit — 审计管道

```bash
uv run pytest tests/fund/service/test_audit_pipeline.py -x -q 2>&1
```

## all — core + generate + audit 合集

```bash
uv run pytest tests/fund/document_tools tests/fund/agent/test_minimal_tool_loop.py tests/fund/cli/test_cli.py tests/fund/service/test_llm_chapter_generation.py tests/fund/service/test_audit_pipeline.py -v --tb=short 2>&1
```

## live — 真实 LLM smoke（需 opt-in，联网）

```bash
source .env && uv run python -c "
from fund_agent.service import FundReadingService, GenerateReportRequest
from pathlib import Path
service = FundReadingService()
result = service.generate_report(GenerateReportRequest(
    fund_code='004393',
    fund_name='安信企业价值优选混合型证券投资基金',
    work_dir=Path('.fund_checklist'),
))
print(f'Chapters: {len(result.chapters)}')
for ch in result.chapters:
    print(f'  Ch{ch.chapter_id}: {len(ch.content)} chars, score={ch.audit_score}')
"
```

注意：`live` 会联网调用 DeepSeek API，默认不运行。
