"""2026-08-09 interactive 已知缺口注册表（F1 已修复/F2/F3）与常量防漂移测试。

- F1: 终答 ≤200 字硬约束（runner 守卫 200 + 截断兜底 ≤200，已修复，test_f1 为普通断言）。
- F2: 004393 aggregate 缺 2022 年（covered=(2021,2023,2024,2025)），单年度 message 含
  可解释说明（业绩表存在但无「过去一年」行）。
- F3: interactive 年份选择 input() 在管道输入下消费首行，/history 被吞（已修复：
  非 TTY 下默认年份、不调用 input()，`--year` 可显式指定）。

F1/F2/F3 已修复，其测试为普通断言。其余测试固定当前常量/机制，防止漂移。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest import mock

import pytest

from fund_agent.agent.llm_tool_loop import (
    _INTERACTIVE_EVIDENCE_OVERLAP_MIN_CHARS,
    _INTERACTIVE_FINAL_ANSWER_MAX_CHARS,
    _INTERACTIVE_FINAL_ANSWER_TARGET_CHARS,
)
from fund_agent.cli.main import _build_aggregate_handler, run_cli

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _write_fake_catalog(work_dir: Path) -> None:
    """写入假 catalog 供 fund code 解析。"""

    catalog_path = work_dir / "completed_reports.json"
    catalog_data = {
        "schema_version": 1,
        "reports": {
            f"doc-011649-{year}": {
                "schema_version": 1,
                "document_id": f"doc-011649-{year}",
                "identity": {
                    "fund_code": "011649",
                    "fund_name": "测试基金",
                    "year": year,
                    "report_type": "annual_report",
                    "source_kind": "local_pdf",
                    "content_fingerprint": "abc123",
                    "document_id": f"doc-011649-{year}",
                    "share_class": "A",
                },
                "stored_blob_ref": f"local_pdf::doc-011649-{year}",
                "docling_json_ref": f"docling_json::doc-011649-{year}",
                "parser_health": {"status": "ok"},
            }
            for year in [2021, 2022, 2023, 2024, 2025]
        },
    }
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog_data, ensure_ascii=False), encoding="utf-8")


def test_f1_final_answer_target_is_hard_bound() -> None:
    """F1 已修复：硬守卫必须不高于软目标（runner 硬约束 200 == 目标 200）。"""

    assert _INTERACTIVE_FINAL_ANSWER_MAX_CHARS <= _INTERACTIVE_FINAL_ANSWER_TARGET_CHARS


def test_f2_aggregate_covers_2022() -> None:
    """F2：004393 五年度请求 2022 缺失但结果可解释，其余年份 covered。"""

    work_dir = _PROJECT_ROOT / ".fund_e2e_004393"
    if not work_dir.is_dir():
        pytest.skip(f"work-dir {work_dir} 不存在（gitignored，允许缺席）")
    handler = _build_aggregate_handler(work_dir)
    result = handler("", "004393", [2021, 2022, 2023, 2024, 2025], (), "A")
    assert result.failure is None
    series = result.series[0]
    assert series.covered_years == (2021, 2023, 2024, 2025)
    assert series.missing_years == (2022,)
    reason = _f2_missing_2022_reason(work_dir)
    assert "无「过去一年」行" in reason, reason
    assert "自基金转型起至今" in reason, reason


def _f2_missing_2022_reason(work_dir: Path) -> str:
    """返回 004393-2022 单年度 10F 失败 message（缺失原因说明）。"""

    from fund_agent.service.extraction import FundReadingService, _repository

    repository = _repository(work_dir)
    catalog = json.loads((work_dir / "completed_reports.json").read_text(encoding="utf-8"))["reports"]
    document_id = next(
        report["identity"]["document_id"]
        for report in catalog.values()
        if report["identity"]["fund_code"] == "004393" and int(report["identity"]["year"]) == 2022
    )
    annual = FundReadingService()._extract_annual_performance_from_store(
        document_id=document_id,
        store=repository.load_store(document_id),
        report_year=2022,
        share_class="A",
    )
    assert annual.failure is not None
    return annual.failure.message


def test_f3_history_not_consumed_by_year_prompt(tmp_path: Path) -> None:
    """F3 已修复：管道输入下年份选择默认年份，首行 /history 命令不被吞。"""

    _write_fake_catalog(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO("/history\nexit\n")):
        exit_code = run_cli(
            ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path), "--plain"],
            stdout=stdout,
            stderr=stderr,
        )
    output = stdout.getvalue()
    assert "非交互输入，默认选择 2025 年" in output
    assert "暂无对话历史。" in output
    assert exit_code == 0


def test_interactive_constants_pinned() -> None:
    """interactive 常量钉死（防漂移）。"""

    assert _INTERACTIVE_EVIDENCE_OVERLAP_MIN_CHARS == 40
    assert _INTERACTIVE_FINAL_ANSWER_MAX_CHARS == 200
    assert _INTERACTIVE_FINAL_ANSWER_TARGET_CHARS == 200


def test_f3_mechanism_year_prompt_consumes_first_line(tmp_path: Path) -> None:
    """F3 机制：管道 stdin 下年份选择不调用 input()，首行命令不被吞，exit 退出码 0。"""

    _write_fake_catalog(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO("exit\n")):
        exit_code = run_cli(
            ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path), "--plain"],
            stdout=stdout,
            stderr=stderr,
        )
    output = stdout.getvalue()
    assert "非交互输入，默认选择 2025 年" in output
    assert "已选择 2025 年年报" in output
    assert "输入问题开始对话" in output
    assert exit_code == 0
