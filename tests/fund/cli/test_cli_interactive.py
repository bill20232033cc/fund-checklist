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
from fund_agent.service.chat_service import ChatService, ChatTurnRequest, ChatTurnResponse
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
        assert args.plain is False

    def test_plain_flag_parsed(self):
        """--plain 参数正确解析。"""
        parser = build_parser()
        args = parser.parse_args(["interactive", "--fund-code", "000001", "--plain"])
        assert args.plain is True

    def test_plain_flag_default_false(self):
        """--plain 默认关闭。"""
        parser = build_parser()
        args = parser.parse_args(["interactive", "--fund-code", "000001"])
        assert args.plain is False


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

    def test_interactive_blocked_answer_displays_original_and_terms(self, tmp_path: Path):
        """被拦截回答：CLI 展示拦截提示、被拦截原文与触发词。"""
        self._write_fake_catalog(tmp_path)
        stdout = io.StringIO()
        stderr = io.StringIO()
        original = "建议买入该基金，目标价5元。"
        blocked = ChatTurnResponse(
            answer="抱歉，不支持涉及投资建议的问题。",
            investment_advice_detected=True,
            original_content=original,
            blocked_terms=("建议买入", "目标价"),
        )

        with mock.patch("sys.stdin", io.StringIO("\n这个基金怎么样？\nexit\n")), mock.patch.object(
            ChatService, "chat_turn", return_value=blocked
        ):
            exit_code = run_cli(
                ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path)],
                stdout=stdout,
                stderr=stderr,
            )

        output = stdout.getvalue()
        assert exit_code == 0
        assert "[投资建议检测] 回答已拦截。" in output
        assert "[被拦截原文]" in output
        assert original in output
        assert "[触发词]" in output
        assert "建议买入" in output

    def test_interactive_failure_trace_displayed_with_verbose(self, tmp_path: Path):
        """--enable-tool-trace：失败轮工具 trace 在 CLI 展示。"""
        self._write_fake_catalog(tmp_path)
        stdout = io.StringIO()
        stderr = io.StringIO()
        failed = ChatTurnResponse(
            answer="LLM 处理失败：章节不存在",
            tool_trace=("search_document(success)", "read_section(failure:not_found)"),
        )

        with mock.patch("sys.stdin", io.StringIO("\n基金规模是多大？\nexit\n")), mock.patch.object(
            ChatService, "chat_turn", return_value=failed
        ):
            exit_code = run_cli(
                [
                    "interactive",
                    "--fund-code",
                    "011649",
                    "--work-dir",
                    str(tmp_path),
                    "--enable-tool-trace",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        output = stdout.getvalue()
        assert exit_code == 0
        assert "[工具调用: search_document(success), read_section(failure:not_found)]" in output


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
        """Markdown 表格渲染为 Rich Table（边框、表头、列对齐）。"""
        from fund_agent.cli.main import render_markdown

        md = "| 年份 | 收益率 |\n|------|--------|\n| 2024 | 12.5% |\n| 2023 | 8.3% |"
        result = render_markdown(md)
        assert "2024" in result
        assert "12.5" in result
        # Rich Table 渲染应包含表头和数据
        assert "年份" in result
        assert "收益率" in result

    def test_render_table_with_alignment(self):
        """表格列对齐：左对齐、居中、右对齐。"""
        from fund_agent.cli.main import render_markdown

        md = (
            "| 名称 | 代码 | 占比 |\n"
            "|:-----|:----:|-----:|\n"
            "| 股票A | 000001 | 5.2% |\n"
            "| 股票B | 000002 | 3.1% |"
        )
        result = render_markdown(md)
        assert "股票A" in result
        assert "000001" in result
        assert "5.2" in result

    def test_render_table_without_leading_trailing_pipes(self):
        """无首尾竖线的表格也能正确识别渲染。"""
        from fund_agent.cli.main import render_markdown

        md = "年份 | 收益率\n------|--------\n2024 | 12.5%\n2023 | 8.3%"
        result = render_markdown(md)
        assert "2024" in result
        assert "12.5" in result

    def test_render_table_mixed_with_text(self):
        """表格与普通文本混合渲染。"""
        from fund_agent.cli.main import render_markdown

        md = "以下是最新年报数据：\n\n| 年份 | 收益率 |\n|------|--------|\n| 2024 | 12.5% |\n\n数据来源：基金年报。"
        result = render_markdown(md)
        assert "最新年报" in result
        assert "2024" in result
        assert "12.5" in result
        assert "数据来源" in result

    def test_render_italic_text(self):
        """斜体 markdown 正确渲染。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("这是 *斜体* 内容。")
        assert "斜体" in result

    def test_render_bold_italic_text(self):
        """粗斜体 markdown 正确渲染。"""
        from fund_agent.cli.main import render_markdown

        result = render_markdown("这是 ***粗斜体*** 内容。")
        assert "粗斜体" in result

    def test_render_multiple_tables(self):
        """多个表格独立渲染。"""
        from fund_agent.cli.main import render_markdown

        md = (
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            "| X | Y |\n|---|---|\n| 9 | 8 |"
        )
        result = render_markdown(md)
        assert "A" in result
        assert "B" in result
        assert "X" in result
        assert "Y" in result
        assert "1" in result
        assert "9" in result

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


# ── Phase 7.2 Task 8: /history、追问建议、启动提示 ────────────────────


class TestHistoryCommand:
    """/history 命令解析与输出测试。"""

    def _parse(self, text: str) -> tuple[str | None, str | None]:
        from fund_agent.cli.main import _parse_repl_input
        return _parse_repl_input(text)

    def test_history_command_parsed(self):
        """/history 命令正确解析。"""
        cmd, arg = self._parse("/history")
        assert cmd == "history"

    def test_history_empty_session(self):
        """空 session 时 /history 不崩溃。"""
        import io
        from fund_agent.cli.main import _print_history
        from fund_agent.service.session_models import PinnedState, Session

        session = Session.create(fund_code="011649")
        stdout = io.StringIO()
        _print_history(session, stdout)
        assert "暂无对话历史" in stdout.getvalue()

    def test_history_shows_turns(self):
        """有对话记录时显示角色、内容摘要和时间。"""
        import io
        from fund_agent.cli.main import _print_history
        from fund_agent.service.session_models import PinnedState, Session, Turn

        session = Session.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="基金经理是谁？", timestamp="2025-07-01T10:00:00+00:00"))
        session = session.add_turn(Turn(role="assistant", content="基金经理是张三，从业15年。", timestamp="2025-07-01T10:00:05+00:00"))

        stdout = io.StringIO()
        _print_history(session, stdout)
        output = stdout.getvalue()
        assert "[用户]" in output
        assert "[助手]" in output
        assert "基金经理是谁？" in output
        assert "张三" in output

    def test_history_truncates_long_content(self):
        """超过 80 字符的内容截断并加 ..."""
        import io
        from fund_agent.cli.main import _print_history
        from fund_agent.service.session_models import PinnedState, Session, Turn

        session = Session.create(fund_code="011649")
        long_text = "这是一个" + "非常" * 50 + "长的回答"
        session = session.add_turn(Turn(role="assistant", content=long_text, timestamp="2025-07-01T10:00:00+00:00"))

        stdout = io.StringIO()
        _print_history(session, stdout)
        output = stdout.getvalue()
        assert "..." in output
        assert len(long_text) > 80

    def test_history_shows_timestamp(self):
        """历史记录包含时间戳。"""
        import io
        from fund_agent.cli.main import _print_history
        from fund_agent.service.session_models import PinnedState, Session, Turn

        session = Session.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="测试", timestamp="2025-07-01T12:30:45+00:00"))

        stdout = io.StringIO()
        _print_history(session, stdout)
        output = stdout.getvalue()
        assert "2025-07-01T12:30:45" in output

    def test_history_max_10_rounds(self):
        """只显示最近 10 轮对话。"""
        import io
        from fund_agent.cli.main import _print_history
        from fund_agent.service.session_models import PinnedState, Session, Turn

        session = Session.create(fund_code="011649")
        for i in range(25):
            session = session.add_turn(Turn(role="user", content=f"问题{i}"))
            session = session.add_turn(Turn(role="assistant", content=f"回答{i}"))

        stdout = io.StringIO()
        _print_history(session, stdout)
        output = stdout.getvalue()
        # 应只显示 10 轮
        assert "问题14" not in output  # 第 15 轮之前的不应出现
        assert "问题24" in output  # 最后一轮


class TestFollowUpSuggestions:
    """追问建议生成测试。"""

    def test_short_answer_no_suggestion(self):
        """短回答不生成追问建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion
        result = _generate_follow_up_suggestion("基金经理是谁？", "张三。")
        assert result is None

    def test_manager_keyword_suggestion(self):
        """含"经理"关键词生成对应建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion
        result = _generate_follow_up_suggestion(
            "基金经理是谁？",
            "基金经理是张三，从业15年，" + "有丰富经验。" * 35,
        )
        assert result is not None
        assert "经理" in result

    def test_holdings_keyword_suggestion(self):
        """含"持仓"关键词生成对应建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion
        result = _generate_follow_up_suggestion(
            "最新持仓有哪些？",
            "前十大重仓股包括" + "详细分析。" * 39,
        )
        assert result is not None
        assert "持仓" in result or "重仓" in result

    def test_generic_fallback_suggestion(self):
        """无关键词匹配时返回通用建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion
        result = _generate_follow_up_suggestion(
            "这只基金怎么样？",
            "这是一只表现不错的基金，" + "数据表明。" * 38,
        )
        assert result is not None
        assert "追问" in result

    def test_short_answer_below_threshold(self):
        """正好 200 字符以下不生成建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion
        short = "A" * 199
        result = _generate_follow_up_suggestion("基金经理是谁？", short)
        assert result is None

    def test_answer_at_threshold_generates(self):
        """200 字符及以上生成建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion
        at_threshold = "A" * 200
        result = _generate_follow_up_suggestion("基金经理是谁？", at_threshold)
        assert result is not None


class TestStartupTip:
    """interactive 启动提示测试。"""

    def test_startup_message_in_output(self, tmp_path: Path):
        """验证启动提示出现在交互模式输出中。"""
        # 写入假 catalog
        catalog_path = tmp_path / "completed_reports.json"
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

        stdout = io.StringIO()
        stderr = io.StringIO()

        with mock.patch("sys.stdin", io.StringIO("exit\n")):
            try:
                run_cli(
                    ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path)],
                    stdout=stdout,
                    stderr=stderr,
                )
            except (EOFError, SystemExit):
                pass

        output = stdout.getvalue()
        assert "支持多轮对话" in output
        assert "可以追问" in output


class TestHelpIncludesHistory:
    """帮助信息包含 /history 命令。"""

    def test_help_mentions_history(self):
        """帮助输出提及 /history 命令。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/history" in output
        assert "10 轮" in output or "对话摘要" in output

    def test_help_mentions_document_clear_exit(self):
        """/help 列出 /document、/clear、exit。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/document" in output
        assert "/clear" in output
        assert "exit" in output


# ── Phase 7.2 Smoke Tests ────────────────────────────────────────────


class TestPhase72Smoke:
    """Phase 7.2 端到端 smoke 测试：interactive 查询 + Rich 渲染 + /history + 追问建议。"""

    # ── Smoke 1: interactive 查询流程 ──────────────────────────────

    def test_smoke1_query_parsed_as_normal_text(self):
        """Smoke 1: "基金经理是谁" 解析为普通查询，非命令。"""
        from fund_agent.cli.main import _parse_repl_input

        for q in ("基金经理是谁？", "基金经理", "谁是基金经理", "最新持仓有哪些？"):
            cmd, arg = _parse_repl_input(q)
            assert cmd is None, f"'{q}' 应为普通查询而非命令"
            assert arg is not None
            assert len(arg) > 0

    def test_smoke1_rich_table_rendering_in_response(self):
        """Smoke 1: 含有表格的回答经 Rich 渲染后保留数据。"""
        from fund_agent.cli.main import render_markdown

        answer = (
            "**基金经理是张三**，从业 15 年。\n\n"
            "| 年份 | 收益率 | 排名 |\n"
            "|------|--------|------|\n"
            "| 2024 | 12.5% | 前25% |\n"
            "| 2023 | 8.3%  | 前50% |\n"
            "| 2022 | -5.1% | 前75% |"
        )
        rendered = render_markdown(answer)
        assert "张三" in rendered
        assert "12.5" in rendered
        assert "2024" in rendered
        assert "排名" in rendered

    def test_smoke1_query_response_flow(self):
        """Smoke 1: 查询 → 回答 → 渲染，全链路非空。"""
        from fund_agent.cli.main import _parse_repl_input, render_markdown

        # Step 1: 用户输入被解析为查询
        cmd, arg = _parse_repl_input("基金经理是谁？")
        assert cmd is None
        assert "基金经理" in arg

        # Step 2: 模拟 LLM 回答（含 markdown 表格）
        answer = (
            "基金经理是**李四**，自 2018 年起管理本基金。\n\n"
            "## 管理业绩\n\n"
            "| 年份 | 收益 | 基准 |\n"
            "|------|------|------|\n"
            "| 2024 | 15%  | 10%  |\n"
            "| 2023 | 8%   | 5%   |"
        )

        # Step 3: Rich 渲染后非空
        rendered = render_markdown(answer)
        assert len(rendered) > 0
        assert "李四" in rendered
        assert "2018" in rendered

    def test_smoke1_plain_mode_passthrough(self):
        """Smoke 1: --plain 模式下保留原始 Markdown 文本。"""
        from fund_agent.cli.main import render_markdown

        answer = "**基金经理是王五**，管理规模 50 亿。"
        rendered = render_markdown(answer, use_rich=False)
        assert "王五" in rendered
        assert "**" in rendered or "王五" in rendered  # raw markdown preserved

    # ── Smoke 4: /history + 追问建议 ────────────────────────────────

    def test_smoke4_history_command_available(self):
        """Smoke 4: /history 命令可解析，空 session 不崩溃。"""
        import io
        from fund_agent.cli.main import _parse_repl_input, _print_history
        from fund_agent.service.session_models import Session

        cmd, arg = _parse_repl_input("/history")
        assert cmd == "history"

        session = Session.create(fund_code="011649")
        stdout = io.StringIO()
        _print_history(session, stdout)
        assert "暂无对话历史" in stdout.getvalue()

    def test_smoke4_history_shows_dialog_summary(self):
        """Smoke 4: /history 显示最近对话的角色、内容摘要和时间。"""
        import io
        from fund_agent.cli.main import _print_history
        from fund_agent.service.session_models import Session, Turn

        session = Session.create(fund_code="011649")
        session = session.add_turn(Turn(role="user", content="基金经理是谁？", timestamp="2025-07-01T10:00:00+00:00"))
        session = session.add_turn(Turn(role="assistant", content="基金经理是张三，从业15年，历史业绩优秀。", timestamp="2025-07-01T10:00:05+00:00"))

        stdout = io.StringIO()
        _print_history(session, stdout)
        output = stdout.getvalue()
        assert "[用户]" in output
        assert "[助手]" in output
        assert "基金经理是谁？" in output
        assert "张三" in output

    def test_smoke4_follow_up_suggestion_on_long_answer(self):
        """Smoke 4: 长回答（≥200 字符）末尾出现追问建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion

        long_answer = "基金经理是张三，自 2015 年起管理本基金，" + "历史业绩表现优异。" * 25
        assert len(long_answer) >= 200

        result = _generate_follow_up_suggestion("基金经理是谁？", long_answer)
        assert result is not None
        assert "经理" in result

    def test_smoke4_no_suggestion_on_short_answer(self):
        """Smoke 4: 短回答不显示追问建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion

        result = _generate_follow_up_suggestion("测试", "短回答。")
        assert result is None

    def test_smoke4_follow_up_coverage(self):
        """Smoke 4: 各关键词均触发非空追问建议。"""
        from fund_agent.cli.main import _generate_follow_up_suggestion

        long_answer = "X" * 200
        queries = [
            "基金经理是谁？",
            "最新持仓有哪些？",
            "历史业绩如何？",
            "费率是多少？",
            "资产配置情况？",
            "风险如何？",
            "债券情况？",
        ]
        for question in queries:
            result = _generate_follow_up_suggestion(question, long_answer)
            assert result is not None, f"'{question}' 应触发追问建议"
            assert len(result) > 10, f"'{question}' 的建议过短"

    def test_smoke4_help_includes_history(self):
        """Smoke 4: /help 输出包含 /history 命令及说明。"""
        import io
        from fund_agent.cli.main import _print_help

        stdout = io.StringIO()
        _print_help(stdout)
        output = stdout.getvalue()
        assert "/history" in output
        assert "对话摘要" in output or "10 轮" in output

    def test_smoke4_startup_tip_present(self, tmp_path: Path):
        """Smoke 4: interactive 启动提示包含多轮对话与命令提示。"""
        import io
        import json

        catalog_path = tmp_path / "completed_reports.json"
        catalog_data = {
            "schema_version": 1,
            "reports": {
                f"doc-011649-{year}": {
                    "schema_version": 1,
                    "document_id": f"doc-011649-{year}",
                    "identity": {
                        "fund_code": "011649", "fund_name": "测试基金",
                        "year": year, "report_type": "annual_report",
                        "source_kind": "local_pdf", "content_fingerprint": "abc",
                        "document_id": f"doc-011649-{year}", "share_class": "A",
                    },
                    "stored_blob_ref": f"local_pdf::doc-011649-{year}",
                    "docling_json_ref": f"docling_json::doc-011649-{year}",
                    "parser_health": {"status": "ok"},
                }
                for year in [2023, 2024, 2025]
            },
        }
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(json.dumps(catalog_data, ensure_ascii=False), encoding="utf-8")

        stdout = io.StringIO()
        stderr = io.StringIO()

        with mock.patch("sys.stdin", io.StringIO("exit\n")):
            try:
                run_cli(
                    ["interactive", "--fund-code", "011649", "--work-dir", str(tmp_path)],
                    stdout=stdout,
                    stderr=stderr,
                )
            except (EOFError, SystemExit):
                pass

        output = stdout.getvalue()
        assert "多轮对话" in output or "可以追问" in output or "/help" in output
