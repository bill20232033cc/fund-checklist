"""2026-08-09 interactive 问答改进（P0-1/P0-2/P1）live 验收 opt-in smoke 测试。

四问口径（controller 已核实，勿重复调查）：
- Q1 基金经理持有本产品吗
- Q2 基金经理是谁
- Q3 基金前十大持仓是什么
- Q4 2021-2025 份额净值增长率

默认 pytest 不得联网、不得读取真实 API key：未设置
FUND_CHECKLIST_RUN_LIVE_DEEPSEEK=1 时全部 skip；对应 work-dir
（.fund_e2e_007466 / .fund_e2e_004393，gitignored）缺席时也 skip。

执行方式为 in-process：mock sys.stdin 后直接调用 run_cli，跑完读
sessions/labels.json 定位会话 JSON，取最后一条 assistant turn 断言。
"""

from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path
from unittest import mock
from uuid import uuid4

import pytest

from fund_agent.cli.main import run_cli
from fund_agent.fund.document_tools.models import ToolFailure
from fund_agent.fund.document_tools.persistent_repository import FilesystemReportRepository
from fund_agent.fund.document_tools.service import FundDocumentToolService

_LIVE_OPT_IN_ENV = "FUND_CHECKLIST_RUN_LIVE_DEEPSEEK"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_QUESTIONS: dict[int, str] = {
    1: "基金经理持有本产品吗",
    2: "基金经理是谁",
    3: "基金前十大持仓是什么",
    4: "2021-2025 份额净值增长率",
}

_LIVE_FUND_CODES = ("007466", "004393")
_TOOL_NAME_AGGREGATE = "aggregate_multi_year_annual_performance"


def _work_dir(fund_code: str) -> Path:
    """返回对应基金的 e2e work-dir 路径。"""

    return _PROJECT_ROOT / f".fund_e2e_{fund_code}"


def _require_live_ready(fund_code: str) -> None:
    """环境门：非 opt-in 或 work-dir 缺席时 skip 本用例。"""

    if os.environ.get(_LIVE_OPT_IN_ENV) != "1":
        pytest.skip(f"需要 {_LIVE_OPT_IN_ENV}=1 才执行 live smoke（默认 pytest 不联网）")
    work_dir = _work_dir(fund_code)
    if not work_dir.is_dir():
        pytest.skip(f"work-dir {work_dir} 不存在（gitignored，允许缺席）")


def _run_interactive_turn(fund_code: str, question: str, q_index: int) -> dict:
    """in-process 跑一次 interactive 单轮问答，返回最后一条 assistant turn。

    参数:
        fund_code: 基金代码。
        question: 问题文本。
        q_index: 问题序号，用于生成唯一会话 label。

    返回:
        会话 JSON 中最后一条 role=assistant 的 turn（含 content/tool_calls/
        tool_trace 等字段）。

    异常:
        AssertionError: labels.json 或会话文件缺失、无 assistant turn。
    """

    work_dir = _work_dir(fund_code)
    label = f"suite-{fund_code}-q{q_index}-{uuid4().hex[:8]}"
    stdout = io.StringIO()
    stderr = io.StringIO()
    # F3 已修复：管道下年份选择不再消费 stdin，直接喂问题即可。
    with mock.patch("sys.stdin", io.StringIO(f"{question}\nexit\n")):
        run_cli(
            [
                "interactive",
                "--fund-code",
                fund_code,
                "--work-dir",
                str(work_dir),
                "--plain",
                "--enable-tool-trace",
                "--label",
                label,
            ],
            stdout=stdout,
            stderr=stderr,
        )
    labels_path = work_dir / "sessions" / "labels.json"
    assert labels_path.is_file(), f"labels.json 未生成: {labels_path}"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    session_id = labels["by_label"][label]
    session_path = work_dir / "sessions" / f"{session_id}.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assistant_turns = [turn for turn in session["turns"] if turn["role"] == "assistant"]
    assert assistant_turns, f"会话 {session_id} 没有 assistant turn"
    return assistant_turns[-1]


def _read_table_signature_ok(work_dir: Path, document_id: str, table_ref: str) -> bool:
    """读取目标表并检查行头签名是否为持仓明细表。

    参数:
        work_dir: e2e work-dir（与 main.py interactive 同路径加载 store）。
        document_id: read_table 参数中的内容身份。
        table_ref: read_table 参数中的受控表格引用。

    返回:
        表加载成功且前两行拼接文本同时含 股票名称/公允价值 时返回 True；
        加载失败、read_table 返回 ToolFailure 或行头不匹配时返回 False。
    """

    try:
        repo = FilesystemReportRepository(
            catalog_path=work_dir / "completed_reports.json",
            blob_root=work_dir / "pdf_blobs",
            docling_json_root=work_dir / "docling_json",
        )
        store = repo.load_store(document_id)
    except Exception:
        return False
    try:
        table = FundDocumentToolService({document_id: store}).read_table(document_id, table_ref)
        if isinstance(table, ToolFailure):
            return False
        header_text = "".join(table.rows[0])
        if len(table.rows) > 1:
            header_text += "".join(table.rows[1])
        return "股票名称" in header_text and "公允价值" in header_text
    except Exception:
        return False


@pytest.mark.parametrize("fund_code", _LIVE_FUND_CODES)
def test_q1_manager_holdings(fund_code: str) -> None:
    """Q1：answer 命中基金经理持有区间表（A 类 50~100 万份）。"""

    _require_live_ready(fund_code)
    answer = _run_interactive_turn(fund_code, _QUESTIONS[1], 1)["content"]
    assert "50" in answer
    assert "100" in answer
    assert "万份" in answer
    assert "未找到相关数据" not in answer


@pytest.mark.parametrize("fund_code", _LIVE_FUND_CODES)
def test_q2_manager_names(fund_code: str) -> None:
    """Q2：007466=柳军/柳叶青；004393=张明。"""

    _require_live_ready(fund_code)
    answer = _run_interactive_turn(fund_code, _QUESTIONS[2], 2)["content"]
    if fund_code == "007466":
        assert "柳军" in answer
        assert "柳叶青" in answer
    else:
        assert "张明" in answer


@pytest.mark.parametrize("fund_code", _LIVE_FUND_CODES)
def test_q3_top10_holdings(fund_code: str) -> None:
    """Q3：验证 read_table 实际读取的是持仓明细表（行头签名），不依赖 LLM 回答格式。"""

    _require_live_ready(fund_code)
    work_dir = _work_dir(fund_code)
    turn = _run_interactive_turn(fund_code, _QUESTIONS[3], 3)
    answer = turn["content"]
    assert "未找到相关数据" not in answer
    table_calls = [
        call for call in turn["tool_calls"] if call["tool_name"] == "read_table"
    ]
    if table_calls:
        verified = False
        for call in table_calls:
            # arguments_display 可能被截断到 100 字符；document_id/table_ref 值
            # 截断前已完整，用截断容忍的正则提取。
            doc_match = re.search(r"'document_id'\s*:\s*'([^']+)'", call["arguments_display"])
            ref_match = re.search(r"'table_ref'\s*:\s*'([^']+)'", call["arguments_display"])
            if not doc_match or not ref_match:
                continue
            document_id = doc_match.group(1)
            table_ref = ref_match.group(1)
            if _read_table_signature_ok(work_dir, str(document_id), str(table_ref)):
                verified = True
                break
        assert verified, "至少一个 read_table 目标表应为持仓明细表（行头含 股票名称/公允价值）"
    else:
        # 回退：turn 无 read_table 调用时用 answer 语义断言。
        assert ("前十" in answer) or ("%" in answer) or (re.search(r"\d{6}", answer) is not None)


@pytest.mark.parametrize("fund_code", _LIVE_FUND_CODES)
def test_q4_aggregate_performance(fund_code: str) -> None:
    """Q4：aggregate 至少 1 次成功、tool_calls ≤8、终答无整段表格且 ≤200 字。"""

    _require_live_ready(fund_code)
    turn = _run_interactive_turn(fund_code, _QUESTIONS[4], 4)
    answer = turn["content"]
    tool_calls = turn["tool_calls"]
    aggregate_calls = [
        call
        for call in tool_calls
        if call["tool_name"] == _TOOL_NAME_AGGREGATE
    ]
    assert any(call["success"] for call in aggregate_calls), "aggregate 工具调用必须至少 1 次成功"
    assert len(tool_calls) <= 8, f"tool_calls 总数 {len(tool_calls)} 超过 8（D5 验收锚）"
    assert "|" not in answer, "终答不得整段粘贴表格"
    assert len(answer) <= 200, "终答超过 200 字硬约束"
    assert "LLM 处理失败" not in answer, "终答不得为 fail-closed 失败消息"
    assert re.search(r"202[1-5]", answer) is not None, "终答需覆盖请求年度 2021-2025"
    if fund_code == "004393":
        assert "2022" in answer, "F2：004393 缺失年份 2022 必须在终答中说明，不得静默跳过"
