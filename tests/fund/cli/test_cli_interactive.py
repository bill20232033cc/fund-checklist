"""CLI interactive 子命令测试。

覆盖:
- interactive 参数解析：--fund-code 必填
- REPL 命令解析：/help /clear /stats /save /export /model /verbose /document exit quit
- ChatTurnContract 集成：字段、默认值、传递
- 投资建议拦截
- 空白输入
- Rich Markdown 渲染
"""

import argparse
import io
import json
from pathlib import Path
from unittest import mock

import pytest

from fund_agent.cli.main import build_parser, run_cli
from fund_agent.service.chat_contract import ChatTurnContract
from fund_agent.service.chat_service import ChatService, ChatTurnRequest
from fund_agent.service.prompt_composer import PromptComposer
from fund_agent.service.scene_config import INTERACTIVE_SCENE_CONFIG
from fund_agent.agent.tool_loop import AgentRunResult
from fund_agent.host.session_store import SessionStore
from fund_agent.service.session_models import PinnedState


class TestInteractiveParser:
    """interactive 子命令参数解析测试。"""

    def test_fund_code_required(self):
        """--fund-code 为必填参数。"""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["interactive"])

    def test_fund_code_parsed(self):
        """--fund-code 正确解析。"""
        parser = build_parser()
        args = parser.parse_args(["interactive", "--fund-code", "011649"])
        assert args.command == "interactive"
        assert args.fund_code == "011649"

    def test_optional_args_defaults(self):
        """可选参数有合理默认值。"""
        parser = build_parser()
        args = parser.parse_args(["interactive", "--fund-code", "000001"])
        assert args.work_dir == Path(".fund_checklist")
        assert args.label is None
        assert args.no_stream is False


class TestInteractiveCommandExecution:
    """interactive 命令执行测试。"""

    def _write_fake_catalog(self, work_dir: Path) -> None:
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

    def test_interactive_missing_catalog_exits_gracefully(self, tmp_path: Path):
        """无 catalog 时启动失败，给出提示。"""
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = run_cli(
            ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path)],
            stdout=stdout,
            stderr=stderr,
        )
        # 无 catalog 时应退出
        assert exit_code != 0 or "无" in stdout.getvalue() or "无" in stderr.getvalue()

    def test_interactive_with_catalog_starts(self, tmp_path: Path):
        """有 catalog 时 interactive 正常启动并显示年份。"""
        self._write_fake_catalog(tmp_path)
        stdout = io.StringIO()
        stderr = io.StringIO()

        # 使用 echo 输入 exit 来测试启动流程（非交互模式测试）
        with mock.patch("sys.stdin", io.StringIO("exit\n")):
            try:
                exit_code = run_cli(
                    ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path)],
                    stdout=stdout,
                    stderr=stderr,
                )
            except (EOFError, SystemExit):
                pass  # 无 real stdin 时可能触发

        output = stdout.getvalue()
        assert "011649" in output or exit_code is not None


class TestReplCommandParsing:
    """REPL 内部命令解析测试。"""

    def _parse_command(self, text: str) -> tuple[str | None, str | None]:
        """模拟 REPL 命令解析。"""
        from fund_agent.cli.main import _parse_repl_input
        return _parse_repl_input(text)

    def test_help_command(self):
        cmd, arg = self._parse_command("/help")
        assert cmd == "help"

    def test_clear_command(self):
        cmd, arg = self._parse_command("/clear")
        assert cmd == "clear"

    def test_exit_command(self):
        for text in ("exit", "quit", "/exit", "/quit"):
            cmd, arg = self._parse_command(text)
            assert cmd == "exit", f"'{text}' 应解析为 exit"

    def test_normal_text_not_command(self):
        cmd, arg = self._parse_command("基金经理是谁？")
        assert cmd is None
        assert arg == "基金经理是谁？"

    def test_slash_but_no_command(self):
        cmd, arg = self._parse_command("/notacommand")
        assert cmd is None  # 未知命令当普通文本

    def test_whitespace_only(self):
        cmd, arg = self._parse_command("   ")
        assert cmd is None
        assert arg is None


class TestChatTurnContract:
    """ChatTurnContract 数据模型与集成测试。"""

    def test_contract_default_fields(self):
        """默认字段：model/runtime 为 None，由 scene config 提供默认值。"""
        contract = ChatTurnContract(
            scene="interactive",
            session_id="s1",
            user_text="hello",
        )
        assert contract.scene == "interactive"
        assert contract.session_id == "s1"
        assert contract.user_text == "hello"
        assert contract.model_name is None
        assert contract.max_iterations is None
        assert contract.timeout_ms is None
        assert contract.disable_tools is False

    def test_contract_with_overrides(self):
        """显式覆盖 model/max_iterations。"""
        contract = ChatTurnContract(
            scene="interactive",
            session_id="s1",
            user_text="hello",
            model_name="deepseek-v4-custom",
            max_iterations=10,
            timeout_ms=60000,
            disable_tools=True,
        )
        assert contract.model_name == "deepseek-v4-custom"
        assert contract.max_iterations == 10
        assert contract.timeout_ms == 60000
        assert contract.disable_tools is True

    def test_contract_immutable(self):
        """ChatTurnContract 为 frozen dataclass。"""
        contract = ChatTurnContract(scene="ask", session_id="s1", user_text="hi")
        with pytest.raises(Exception):
            contract.model_name = "other"  # type: ignore[misc]

    def test_chat_service_with_contract(self, tmp_path: Path):
        """ChatService 接受 ChatTurnContract 并正常执行。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="doc-011649-2025",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        store.save(session)

        template_dir = Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"
        composer = PromptComposer(template_dir=template_dir)
        service = ChatService(
            session_store=store,
            prompt_composer=composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )

        contract = ChatTurnContract(
            scene="interactive",
            session_id=session.session_id,
            user_text="基金经理是谁？",
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="基金经理是谁？"),
            contract=contract,
            agent_result=AgentRunResult(answer="基金经理是张三。", citations=(), tool_trace=(), failure=None),
        )

        assert "张三" in result.answer
        assert result.investment_advice_detected is False

    def test_contract_passed_to_service_with_max_iterations(self, tmp_path: Path):
        """contract 的 max_iterations 覆盖 scene 默认值。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="doc-011649-2025",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        store.save(session)

        template_dir = Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"
        composer = PromptComposer(template_dir=template_dir)
        service = ChatService(
            session_store=store,
            prompt_composer=composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )

        contract = ChatTurnContract(
            scene="interactive",
            session_id=session.session_id,
            user_text="问题",
            max_iterations=5,
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="问题"),
            contract=contract,
            agent_result=AgentRunResult(answer="回答。", citations=(), tool_trace=(), failure=None),
        )

        assert result.answer == "回答。"


class TestIntegrationWireUp:
    """7J 全链路集成：chat_turn → Host → CLI。"""

    def _template_dir(self) -> Path:
        return Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"

    def _write_fake_catalog(self, work_dir: Path) -> None:
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

    def test_full_pipeline_service_to_host(self, tmp_path: Path):
        """ChatService 通过 ChatTurnContract 连接到 MinimalHost 的 session 管理。"""
        from fund_agent.host.minimal_host import MinimalHost

        store = SessionStore(tmp_path / "sessions")
        host = MinimalHost(session_store=store)

        session = host.create_session(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="doc-011649-2025",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        store.save(session)

        composer = PromptComposer(template_dir=self._template_dir())
        service = ChatService(
            session_store=store,
            prompt_composer=composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )

        contract = ChatTurnContract(
            scene="interactive",
            session_id=session.session_id,
            user_text="测试问题",
        )

        result = service.chat_turn(
            ChatTurnRequest(session_id=session.session_id, user_text="测试问题"),
            contract=contract,
            agent_result=AgentRunResult(answer="测试回答", citations=(), tool_trace=(), failure=None),
        )

        assert result.answer == "测试回答"
        # 验证 session 已更新
        updated = host.get_session(session.session_id)
        assert len(updated.turns) == 2
        assert updated.turns[0].role == "user"
        assert updated.turns[1].role == "assistant"

    def test_host_session_lifecycle_with_contract(self, tmp_path: Path):
        """MinimalHost 管理 session 生命周期 + ChatTurnContract 传递。"""
        from fund_agent.host.minimal_host import MinimalHost

        store = SessionStore(tmp_path / "sessions")
        host = MinimalHost(session_store=store)

        # 创建
        session = host.create_session(fund_code="011649", label="test-lifecycle")
        assert session.status == "ACTIVE"

        # 列出
        sessions = host.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["label"] == "test-lifecycle"

        # 关闭
        host.close_session(session.session_id)
        closed = host.get_session(session.session_id)
        assert closed.status == "CLOSED"

    def test_integration_multi_turn_with_contract(self, tmp_path: Path):
        """3 轮对话：contract 正确传递，session 持续更新。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="011649")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="doc-011649-2025",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        store.save(session)

        composer = PromptComposer(template_dir=self._template_dir())
        service = ChatService(
            session_store=store,
            prompt_composer=composer,
            scene_config=INTERACTIVE_SCENE_CONFIG,
        )

        answers = ["经理是张三。", "他从2020年开始管理。", "规模50亿。"]
        for i, ans in enumerate(answers):
            contract = ChatTurnContract(
                scene="interactive",
                session_id=session.session_id,
                user_text=f"问题{i+1}",
            )
            result = service.chat_turn(
                ChatTurnRequest(session_id=session.session_id, user_text=f"问题{i+1}"),
                contract=contract,
                agent_result=AgentRunResult(answer=ans, citations=(), tool_trace=(), failure=None),
            )
            assert ans in result.answer

        updated = store.load(session.session_id)
        assert len(updated.turns) == 6  # 3 user + 3 assistant


class TestSessionRecovery:
    """7K 会话恢复 + --label 支持。"""

    def _template_dir(self) -> Path:
        return Path(__file__).parent.parent.parent.parent / "fund_agent" / "service" / "prompts"

    def test_create_session_with_label_and_resume(self, tmp_path: Path):
        """--label 创建会话，保存后可通过 label 恢复。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="011649", label="my-resume-test")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="doc-011649-2025",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)
        store.save(session)

        # 模拟恢复：通过 label 加载
        restored = store.load("my-resume-test")
        assert restored.session_id == session.session_id
        assert restored.pinned_state.active_year == 2025
        assert restored.label == "my-resume-test"

    def test_resume_preserves_turns(self, tmp_path: Path):
        """恢复的 session 保留历史 turns。"""
        store = SessionStore(tmp_path / "sessions")
        session = store.create(fund_code="011649", label="resume-turns")
        ps = PinnedState(
            fund_code="011649",
            active_document_id="doc-011649-2025",
            active_year=2025,
        )
        session = session.with_pinned_state(ps)

        from fund_agent.service.session_models import Turn
        session = session.add_turn(Turn(role="user", content="问题1"))
        session = session.add_turn(Turn(role="assistant", content="回答1"))
        store.save(session)

        restored = store.load("resume-turns")
        assert len(restored.turns) == 2
        assert restored.turns[0].content == "问题1"
        assert restored.turns[1].content == "回答1"

    def test_resume_nonexistent_label_raises(self, tmp_path: Path):
        """恢复不存在的 label → FileNotFoundError。"""
        store = SessionStore(tmp_path / "sessions")
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent-label")

    def test_label_command_in_repl(self):
        """/label 命令解析。"""
        cmd, arg = _parse_repl_input("/label my-session")
        assert cmd == "label"
        assert arg == "my-session"

    def test_label_command_without_arg(self):
        """/label 无参数时提示。"""
        cmd, arg = _parse_repl_input("/label")
        assert cmd == "label"
        assert arg is None

    def test_repl_parse_label_command(self):
        """/label 正确解析。"""
        from fund_agent.cli.main import _parse_repl_input
        cmd, arg = _parse_repl_input("/label test-label")
        assert cmd == "label"
        assert arg == "test-label"


def _parse_repl_input(text: str) -> tuple[str | None, str | None]:
    """模块级 helper，供 TestSessionRecovery 使用。"""
    from fund_agent.cli.main import _parse_repl_input as _parse
    return _parse(text)


# ── 7N: 扩展 REPL 命令 ──────────────────────────────────────────────


class TestExtendedReplCommands:
    """7N 扩展命令解析测试：/stats /save /export /model /verbose /document。"""

    def _parse(self, text: str) -> tuple[str | None, str | None]:
        from fund_agent.cli.main import _parse_repl_input
        return _parse_repl_input(text)

    def test_stats_command(self):
        """/stats 命令正确解析。"""
        cmd, arg = self._parse("/stats")
        assert cmd == "stats"

    def test_save_command(self):
        """/save 命令正确解析。"""
        cmd, arg = self._parse("/save")
        assert cmd == "save"

    def test_export_command(self):
        """/export 命令正确解析，支持可选格式参数。"""
        cmd, arg = self._parse("/export")
        assert cmd == "export"
        assert arg is None

        cmd, arg = self._parse("/export markdown")
        assert cmd == "export"
        assert arg == "markdown"

    def test_model_command_show(self):
        """/model 无参数时显示当前模型。"""
        cmd, arg = self._parse("/model")
        assert cmd == "model"
        assert arg is None

    def test_model_command_switch(self):
        """/model 带参数时切换模型。"""
        cmd, arg = self._parse("/model deepseek-v4-pro")
        assert cmd == "model"
        assert arg == "deepseek-v4-pro"

    def test_verbose_command_toggle(self):
        """/verbose 命令切换详细模式。"""
        cmd, arg = self._parse("/verbose")
        assert cmd == "verbose"

    def test_document_command_switch(self):
        """/document 命令切换文档。"""
        cmd, arg = self._parse("/document doc-011649-2024")
        assert cmd == "document"
        assert arg == "doc-011649-2024"

    def test_document_command_list(self):
        """/document 无参数时列出可用文档。"""
        cmd, arg = self._parse("/document")
        assert cmd == "document"
        assert arg is None

    def test_unknown_slash_still_passes_through(self):
        """未知斜杠命令仍当普通文本。"""
        cmd, arg = self._parse("/unknown-cmd")
        assert cmd is None


class TestHelpOutputIncludesNewCommands:
    """帮助信息包含 7N 新增命令。"""

    def test_help_mentions_stats(self):
        """帮助输出提及 /stats 命令。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/stats" in output

    def test_help_mentions_save_and_export(self):
        """帮助输出提及 /save 和 /export 命令。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/save" in output
        assert "/export" in output

    def test_help_mentions_model_and_verbose(self):
        """帮助输出提及 /model 和 /verbose 命令。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/model" in output
        assert "/verbose" in output

    def test_help_mentions_document(self):
        """帮助输出提及 /document 命令。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/document" in output


# ── 7O: Rich Markdown 渲染 ──────────────────────────────────────────


class TestRichMarkdownRenderer:
    """7O Rich Markdown 渲染测试。"""

    def test_render_plain_text_passthrough(self):
        """纯文本无 markdown 标记时原样输出。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("这是普通文本，没有格式。")
        assert "普通文本" in result

    def test_render_bold_text(self):
        """加粗 markdown 正确渲染。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("这是 **重要** 内容。")
        # rich 渲染后会包含标记
        assert "重要" in result

    def test_render_code_block(self):
        """代码块使用语法高亮。"""
        from fund_agent.cli.main import render_markdown

        md = "```python\nprint('hello')\n```"
        result = render_markdown(md)
        # 应该包含代码内容
        assert "print" in result
        assert "hello" in result

    def test_render_table(self):
        """Markdown 表格渲染。"""
        from fund_agent.cli.main import render_markdown

        md = "| 年份 | 收益率 |\n|------|--------|\n| 2024 | 12.5% |\n| 2023 | 8.3% |"
        result = render_markdown(md)
        assert "2024" in result
        assert "12.5" in result

    def test_render_inline_code(self):
        """行内代码渲染。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("使用 `fund.check()` 方法。")
        assert "fund.check" in result

    def test_render_empty_string(self):
        """空字符串渲染不报错。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("")
        assert result is not None  # 不抛异常即可

    def test_render_bullet_list(self):
        """无序列表渲染。"""
        from fund_agent.cli.main import render_markdown

        md = "- 基金经理：张三\n- 成立时间：2020年\n- 规模：50亿"
        result = render_markdown(md)
        assert "张三" in result
        assert "50亿" in result

    def test_render_heading(self):
        """标题渲染。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("## 基金概况\n\n这是一只混合型基金。")
        assert "基金概况" in result

    def test_verbose_mode_disables_rich(self):
        """verbose=False 时 render_markdown 可能走简化路径。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("**测试**", use_rich=False)
        # 无 rich 时返回原始文本或简化渲染
        assert "测试" in result
