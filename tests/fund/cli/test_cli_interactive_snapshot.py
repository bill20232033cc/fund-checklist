"""快照（季报/半年报）interactive 开放测试。

覆盖:
- interactive parser：--report-type / --quarter / --period 参数形态与校验
- CLI e2e：季报/半年报默认期次、显式期次、无匹配 not_found
- 快照模式 aggregate_handler=None；annual 模式仍注入 handler
- /document 期次切换：保留 report_type，quarter/period 从 catalog 重新解析
- runtime contribution：快照含报告类型/报告期/单期快照硬规则行；annual 不含
- SessionStore 序列化：新字段 round-trip + 旧 session 缺省兼容
"""

import argparse
import io
import json
from pathlib import Path
from unittest import mock

import pytest

from fund_agent.cli.main import build_parser, run_cli
from fund_agent.service.chat_service import ChatService
from fund_agent.service.prompt_composer import PromptComposer
from fund_agent.service.scene_config import INTERACTIVE_SCENE_CONFIG
from fund_agent.host.session_store import SessionStore
from fund_agent.service.session_models import PinnedState


def _write_snapshot_catalog(work_dir: Path) -> None:
    """写入季报 + 半年报混合 catalog（005680）。"""
    catalog_path = work_dir / "completed_reports.json"
    records: dict[str, dict[str, object]] = {}
    for year, quarter in ((2025, 1), (2025, 2), (2026, 4)):
        document_id = f"005680-{year}-Q{quarter}-quarterly_report-{'a' * 16}"
        records[document_id] = {
            "schema_version": 1,
            "document_id": document_id,
            "identity": {
                "fund_code": "005680",
                "fund_name": "财通资管价值成长混合",
                "year": year,
                "report_type": "quarterly_report",
                "source_kind": "local_pdf",
                "content_fingerprint": "abc123",
                "document_id": document_id,
                "quarter": quarter,
                "share_class": "A",
            },
            "stored_blob_ref": f"local_pdf::{document_id}",
            "docling_json_ref": f"docling_json::{document_id}",
            "parser_health": {"status": "ok"},
        }
    document_id = "005680-2025-semiannual_report-bbbbbbbbbbbbbbbb"
    records[document_id] = {
        "schema_version": 1,
        "document_id": document_id,
        "identity": {
            "fund_code": "005680",
            "fund_name": "财通资管价值成长混合",
            "year": 2025,
            "report_type": "semiannual_report",
            "source_kind": "local_pdf",
            "content_fingerprint": "abc123",
            "document_id": document_id,
            "period": "H1",
            "share_class": "A",
        },
        "stored_blob_ref": f"local_pdf::{document_id}",
        "docling_json_ref": f"docling_json::{document_id}",
        "parser_health": {"status": "ok"},
    }
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps({"schema_version": 1, "reports": records}, ensure_ascii=False),
        encoding="utf-8",
    )


class TestSnapshotParser:
    """快照 interactive 参数解析。"""

    def test_defaults_unchanged(self) -> None:
        """缺省参数 = annual_report，期次 None（老命令零变化）。"""
        args = build_parser().parse_args(["interactive", "--fund-code", "005680"])
        assert args.report_type == "annual_report"
        assert args.quarter is None
        assert args.period is None

    def test_report_type_quarterly_parsed(self) -> None:
        """--report-type quarterly_report + --quarter 正确解析。"""
        args = build_parser().parse_args(
            ["interactive", "--fund-code", "005680", "--report-type", "quarterly_report", "--quarter", "2"]
        )
        assert args.report_type == "quarterly_report"
        assert args.quarter == 2

    def test_quarter_out_of_range_rejected(self) -> None:
        """--quarter 5 被 argparse choices 拒绝。"""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["interactive", "--fund-code", "005680", "--report-type", "quarterly_report", "--quarter", "5"]
            )

    def test_period_h1_parsed(self) -> None:
        """--report-type semiannual_report + --period H1 正确解析。"""
        args = build_parser().parse_args(
            ["interactive", "--fund-code", "005680", "--report-type", "semiannual_report", "--period", "H1"]
        )
        assert args.report_type == "semiannual_report"
        assert args.period == "H1"

    def test_period_invalid_choice_rejected(self) -> None:
        """--period 非 H1 被 argparse choices 拒绝。"""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["interactive", "--fund-code", "005680", "--report-type", "semiannual_report", "--period", "H2"]
            )


class TestSnapshotCommandValidation:
    """快照 interactive 参数组合校验（执行期拒绝）。"""

    def test_quarter_with_annual_rejected(self, tmp_path: Path) -> None:
        """--quarter 配 annual（默认）被拒绝。"""
        _write_snapshot_catalog(tmp_path)
        stderr = io.StringIO()
        exit_code = run_cli(
            ["interactive", "--fund-code", "005680", "--work-dir", str(tmp_path), "--quarter", "2"],
            stdout=io.StringIO(),
            stderr=stderr,
        )
        assert exit_code != 0
        assert "annual_report 模式不支持 --quarter/--period" in stderr.getvalue()

    def test_period_with_annual_rejected(self, tmp_path: Path) -> None:
        """--period 配 annual（默认）被拒绝。"""
        _write_snapshot_catalog(tmp_path)
        stderr = io.StringIO()
        exit_code = run_cli(
            ["interactive", "--fund-code", "005680", "--work-dir", str(tmp_path), "--period", "H1"],
            stdout=io.StringIO(),
            stderr=stderr,
        )
        assert exit_code != 0
        assert "annual_report 模式不支持 --quarter/--period" in stderr.getvalue()

    def test_period_with_quarterly_rejected(self, tmp_path: Path) -> None:
        """--period 配 quarterly_report 被拒绝。"""
        _write_snapshot_catalog(tmp_path)
        stderr = io.StringIO()
        exit_code = run_cli(
            [
                "interactive",
                "--fund-code", "005680",
                "--work-dir", str(tmp_path),
                "--report-type", "quarterly_report",
                "--period", "H1",
            ],
            stdout=io.StringIO(),
            stderr=stderr,
        )
        assert exit_code != 0
        assert "quarterly_report 模式不支持 --period" in stderr.getvalue()

    def test_quarter_with_semiannual_rejected(self, tmp_path: Path) -> None:
        """--quarter 配 semiannual_report 被拒绝。"""
        _write_snapshot_catalog(tmp_path)
        stderr = io.StringIO()
        exit_code = run_cli(
            [
                "interactive",
                "--fund-code", "005680",
                "--work-dir", str(tmp_path),
                "--report-type", "semiannual_report",
                "--quarter", "1",
            ],
            stdout=io.StringIO(),
            stderr=stderr,
        )
        assert exit_code != 0
        assert "semiannual_report 模式不支持 --quarter" in stderr.getvalue()


class TestSnapshotCommandExecution:
    """快照 interactive 执行（CLI e2e，非交互 stdin）。"""

    def _run(self, args: list[str], tmp_path: Path, stdin_text: str = "exit\n"):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_text)):
            exit_code = run_cli(args, stdout=stdout, stderr=stderr)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_quarterly_default_latest_quarter(self, tmp_path: Path) -> None:
        """季报缺省期次 = 所选年份内最新季度（2026 → Q4）。"""
        _write_snapshot_catalog(tmp_path)
        exit_code, output, _ = self._run(
            ["interactive", "--fund-code", "005680", "--work-dir", str(tmp_path), "--report-type", "quarterly_report"],
            tmp_path,
        )
        assert exit_code == 0
        assert "已选择 2026 年 Q4 季报" in output
        assert "可用年份: 2025, 2026" in output

    def test_quarterly_default_quarter_with_year(self, tmp_path: Path) -> None:
        """--year 2025 + 缺省期次 = 2025 年内最大季度（Q2）。"""
        _write_snapshot_catalog(tmp_path)
        exit_code, output, _ = self._run(
            [
                "interactive",
                "--fund-code", "005680",
                "--work-dir", str(tmp_path),
                "--report-type", "quarterly_report",
                "--year", "2025",
            ],
            tmp_path,
        )
        assert exit_code == 0
        assert "已选择 2025 年 Q2 季报" in output

    def test_quarterly_explicit_quarter(self, tmp_path: Path) -> None:
        """--year 2025 --quarter 1 显式选择 Q1。"""
        _write_snapshot_catalog(tmp_path)
        exit_code, output, _ = self._run(
            [
                "interactive",
                "--fund-code", "005680",
                "--work-dir", str(tmp_path),
                "--report-type", "quarterly_report",
                "--year", "2025",
                "--quarter", "1",
            ],
            tmp_path,
        )
        assert exit_code == 0
        assert "已选择 2025 年 Q1 季报" in output

    def test_quarterly_missing_quarter_in_year(self, tmp_path: Path) -> None:
        """所选年份无该期次 → not_found 文案与退出码。"""
        _write_snapshot_catalog(tmp_path)
        exit_code, _, stderr = self._run(
            [
                "interactive",
                "--fund-code", "005680",
                "--work-dir", str(tmp_path),
                "--report-type", "quarterly_report",
                "--year", "2025",
                "--quarter", "3",
            ],
            tmp_path,
        )
        assert exit_code != 0
        assert "无 Q3 季报" in stderr

    def test_semiannual_default_h1(self, tmp_path: Path) -> None:
        """半年报缺省期次 = H1。"""
        _write_snapshot_catalog(tmp_path)
        exit_code, output, _ = self._run(
            ["interactive", "--fund-code", "005680", "--work-dir", str(tmp_path), "--report-type", "semiannual_report"],
            tmp_path,
        )
        assert exit_code == 0
        assert "已选择 2025 年 H1 半年报" in output

    def test_no_snapshot_docs_not_found(self, tmp_path: Path) -> None:
        """基金无季报 → not_found 文案与退出码。"""
        catalog_path = tmp_path / "completed_reports.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "reports": {},
                }
            ),
            encoding="utf-8",
        )
        exit_code, _, stderr = self._run(
            ["interactive", "--fund-code", "005680", "--work-dir", str(tmp_path), "--report-type", "quarterly_report"],
            tmp_path,
        )
        assert exit_code != 0
        assert "未找到基金 005680 的已导入季报" in stderr

    def test_snapshot_aggregate_handler_is_none(self, tmp_path: Path) -> None:
        """快照模式 ChatService 的 aggregate_handler=None（fail-closed）。"""
        _write_snapshot_catalog(tmp_path)
        captured: dict[str, object] = {}
        original_init = ChatService.__init__

        def patched_init(self_, **kwargs):
            captured.update(kwargs)
            original_init(self_, **kwargs)

        with mock.patch("sys.stdin", io.StringIO("exit\n")), mock.patch.object(
            ChatService, "__init__", patched_init
        ):
            run_cli(
                [
                    "interactive",
                    "--fund-code", "005680",
                    "--work-dir", str(tmp_path),
                    "--report-type", "quarterly_report",
                ],
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

        assert captured.get("aggregate_handler") is None

    def test_snapshot_pinned_state_carries_period_fields(self, tmp_path: Path) -> None:
        """快照模式 PinnedState 携带 report_type/quarter/period 并落盘。"""
        _write_snapshot_catalog(tmp_path)
        exit_code, _, _ = self._run(
            [
                "interactive",
                "--fund-code", "005680",
                "--work-dir", str(tmp_path),
                "--report-type", "quarterly_report",
                "--year", "2025",
                "--quarter", "1",
            ],
            tmp_path,
        )
        assert exit_code == 0
        session_data = self._load_single_session(tmp_path)
        pinned = session_data["pinned_state"]
        assert pinned["report_type"] == "quarterly_report"
        assert pinned["quarter"] == 1
        assert pinned["period"] is None

    def test_document_switch_reparses_quarter(self, tmp_path: Path) -> None:
        """快照 /document 期次切换：quarter 从目标 catalog record 重新解析。"""
        _write_snapshot_catalog(tmp_path)
        new_doc = "005680-2025-Q1-quarterly_report-aaaaaaaaaaaaaaaa"
        exit_code, output, _ = self._run(
            ["interactive", "--fund-code", "005680", "--work-dir", str(tmp_path), "--report-type", "quarterly_report"],
            tmp_path,
            stdin_text=f"/document {new_doc}\nexit\n",
        )
        assert exit_code == 0
        assert f"已切换到文档: {new_doc}" in output
        pinned = self._load_single_session(tmp_path)["pinned_state"]
        # 启动默认 2026 Q4 → 切换到 Q1 文档后 quarter 重新解析为 1，非透传旧值 4
        assert pinned["report_type"] == "quarterly_report"
        assert pinned["active_document_id"] == new_doc
        assert pinned["quarter"] == 1
        assert pinned["period"] is None

    @staticmethod
    def _load_single_session(work_dir: Path) -> dict[str, object]:
        """读取 sessions 目录下唯一 session JSON。"""
        sessions_dir = work_dir / "sessions"
        candidates = [p for p in sessions_dir.glob("*.json") if p.name != "labels.json"]
        assert len(candidates) == 1
        return json.loads(candidates[0].read_text(encoding="utf-8"))


class TestSnapshotRuntimeContribution:
    """runtime contribution 报告期注入（annual 零变化守卫）。"""

    def _service(self, tmp_path: Path) -> ChatService:
        store = SessionStore(tmp_path / "sessions")
        template_dir = Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"
        return ChatService(
            session_store=store,
            prompt_composer=PromptComposer(template_dir=template_dir),
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )

    def test_quarterly_runtime_has_snapshot_lines(self, tmp_path: Path) -> None:
        """季报 runtime contribution 含报告类型/报告期/单期快照硬规则行。"""
        session = SessionStore(tmp_path / "sessions").create(fund_code="005680").with_pinned_state(
            PinnedState(
                fund_code="005680",
                available_document_ids=("005680-2025-Q2-quarterly_report-ccc",),
                active_document_id="005680-2025-Q2-quarterly_report-ccc",
                active_year=2025,
                report_type="quarterly_report",
                quarter=2,
            )
        )
        runtime = self._service(tmp_path)._build_contributions(session)["runtime"]
        assert "- 报告类型: 季报（quarterly_report）" in runtime
        assert "- 报告期: 2025 年二季度（Q2）" in runtime
        assert "单期快照，非年度报告" in runtime
        assert "禁止做多年趋势判断" in runtime

    def test_semiannual_runtime_has_snapshot_lines(self, tmp_path: Path) -> None:
        """半年报 runtime contribution 含 H1 报告期行。"""
        session = SessionStore(tmp_path / "sessions").create(fund_code="005680").with_pinned_state(
            PinnedState(
                fund_code="005680",
                available_document_ids=("005680-2025-semiannual_report-fff",),
                active_document_id="005680-2025-semiannual_report-fff",
                active_year=2025,
                report_type="semiannual_report",
                period="H1",
            )
        )
        runtime = self._service(tmp_path)._build_contributions(session)["runtime"]
        assert "- 报告类型: 半年报（semiannual_report）" in runtime
        assert "- 报告期: 2025 年 H1 半年报" in runtime
        assert "单期快照，非年度报告" in runtime

    def test_annual_runtime_has_no_snapshot_lines(self, tmp_path: Path) -> None:
        """annual runtime contribution 无报告类型/报告期/单期快照行（零变化守卫）。"""
        session = SessionStore(tmp_path / "sessions").create(fund_code="005680").with_pinned_state(
            PinnedState(
                fund_code="005680",
                available_document_ids=("005680-2025-annual_report-aaa",),
                active_document_id="005680-2025-annual_report-aaa",
                active_year=2025,
            )
        )
        runtime = self._service(tmp_path)._build_contributions(session)["runtime"]
        assert "报告类型" not in runtime
        assert "报告期" not in runtime
        assert "单期快照" not in runtime


class TestSnapshotSessionSerialization:
    """SessionStore pinned_state 新字段序列化。"""

    def test_round_trip_preserves_fields(self, tmp_path: Path) -> None:
        """快照 pinned_state 序列化 round-trip 完整。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="005680").with_pinned_state(
            PinnedState(
                fund_code="005680",
                available_document_ids=("005680-2025-Q2-quarterly_report-ccc",),
                active_document_id="005680-2025-Q2-quarterly_report-ccc",
                active_year=2025,
                report_type="quarterly_report",
                quarter=2,
                period=None,
            )
        )
        store.save(session)
        loaded = store.load(session.session_id)
        assert loaded.pinned_state.report_type == "quarterly_report"
        assert loaded.pinned_state.quarter == 2
        assert loaded.pinned_state.period is None

    def test_old_session_defaults_to_annual(self, tmp_path: Path) -> None:
        """旧 session（schema v1 无新字段）缺省为 annual_report。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="005680")
        json_path = tmp_path / "sessions" / f"{session.session_id}.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["pinned_state"].pop("report_type", None)
        data["pinned_state"].pop("quarter", None)
        data["pinned_state"].pop("period", None)
        json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        loaded = store.load(session.session_id)
        assert loaded.pinned_state.report_type == "annual_report"
        assert loaded.pinned_state.quarter is None
        assert loaded.pinned_state.period is None
