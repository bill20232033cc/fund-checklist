"""Phase 7.5 generate 章节级并发测试（T1-T8 + concurrency=1 串行等价基线）。

覆盖：并发峰值与阶段 join、lane 上限、结果顺序稳定、单章失败隔离、
审计产物并发落盘、DeepSeekLlmClient.clone() 独立 usage、参数优先级与范围、
无 clone() 回退串行。
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import pytest

from fund_agent.service.audit_pipeline import ChapterProcessState, ReportGenerationCoordinator
from fund_agent.service.chapter_generator import LLM_ANALYSIS_PROMPTS
from fund_agent.service.extraction import FundReadingService
from fund_agent.service.models import (
    AssetAllocationItem,
    FeeRateItem,
    GenerateReportRequest,
    HoldingExtraction,
)


def _sample_performance() -> dict[int, dict[str, str]]:
    """构造多年度业绩样本。"""

    return {
        2022: {"nav_growth_rate": "-5.23%", "benchmark_return_rate": "-15.12%", "excess_return": "9.89%"},
        2023: {"nav_growth_rate": "3.45%", "benchmark_return_rate": "-3.21%", "excess_return": "6.66%"},
        2024: {"nav_growth_rate": "12.34%", "benchmark_return_rate": "8.76%", "excess_return": "3.58%"},
    }


def _sample_holdings() -> dict[int, tuple[HoldingExtraction, ...]]:
    """构造持仓样本。"""

    return {
        2024: (
            HoldingExtraction(rank=1, stock_code="600519", stock_name="贵州茅台", quantity="100000", fair_value="180000000.00", percentage="8.52%"),
            HoldingExtraction(rank=2, stock_code="000858", stock_name="五粮液", quantity="80000", fair_value="130000000.00", percentage="6.31%"),
        ),
    }


def _sample_allocation() -> dict[int, tuple[AssetAllocationItem, ...]]:
    """构造资产配置样本。"""

    return {
        2024: (
            AssetAllocationItem(category="股票投资", amount="1,234,567,890.00", percentage_of_net="85.23%"),
        ),
    }


def _sample_fees() -> dict[int, tuple[FeeRateItem, ...]]:
    """构造费率样本。"""

    return {
        2024: (
            FeeRateItem(fee_name="基金管理费", rate="1.20%"),
            FeeRateItem(fee_name="基金托管费", rate="0.20%"),
        ),
    }


def _sample_inputs() -> dict[str, object]:
    """构造 coordinator.generate_report 的完整输入（与既有 service 测试同源）。"""

    return {
        "fund_code": "004393",
        "fund_name": "安信企业价值优选混合型证券投资基金",
        "report_year": 2024,
        "performance": _sample_performance(),
        "holdings": _sample_holdings(),
        "allocation": _sample_allocation(),
        "fees": _sample_fees(),
        "fund_manager": None,
        "scale_info": None,
        "evidence": None,
        "signal_judgment": None,
        "fund_type": "",
    }


def _chapter_of(system_prompt: str, user_prompt: str) -> int:
    """从 prompt 识别章节编号（审计/修复带显式编号；生成为分析 prompt 匹配）。"""

    m = re.search(r"章节编号: Ch(\d+)", user_prompt)
    if m:
        return int(m.group(1))
    for cid, prompt in LLM_ANALYSIS_PROMPTS.items():
        if prompt in user_prompt:
            return cid
    raise AssertionError(f"无法从 prompt 识别章节: {system_prompt[:40]}...")


def _kind_of(system_prompt: str) -> str:
    """按 system prompt 分类调用类型。"""

    if "审计" in system_prompt:
        return "audit"
    if "修复" in system_prompt:
        return "repair"
    return "generate"


class _CallGate:
    """前 n 次调用在闸门处汇合，保证并发峰值确定可测。"""

    def __init__(self, n: int) -> None:
        self._n = n
        self._count = 0
        self._cv = threading.Condition()

    def wait(self) -> None:
        """等待前 n 次调用到齐后放行；之后调用直接通过。"""

        with self._cv:
            self._count += 1
            if self._count >= self._n:
                self._cv.notify_all()
            else:
                self._cv.wait(timeout=10)


class ConcurrencyProbe:
    """线程安全的并发探测：active/peak 计数、按章调用序列与 start/end 事件。"""

    def __init__(self, *, delay: float = 0.0, gate_count: int = 1) -> None:
        self._lock = threading.Lock()
        self._gate = _CallGate(gate_count)
        self.delay = delay
        self.active = 0
        self.peak = 0
        self.calls: list[tuple[int, str, str, str, int]] = []
        self.events: list[tuple[int, str, int]] = []
        self._seq = 0

    def record(self, chapter_id: int, kind: str, system_prompt: str, user_prompt: str) -> None:
        """记录一次 LLM 调用（start/end 事件 + 调用签名）。"""

        with self._lock:
            self._seq += 1
            seq = self._seq
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append((chapter_id, kind, system_prompt, user_prompt, seq))
            self.events.append((chapter_id, "start", seq))
        try:
            self._gate.wait()
            if self.delay:
                time.sleep(self.delay)
        finally:
            with self._lock:
                self.active -= 1
                self.events.append((chapter_id, "end", seq))


class ClonableProbeClient:
    """带 clone() 的并发探测 fake；clone 共享同一个 ConcurrencyProbe。"""

    def __init__(self, probe: ConcurrencyProbe) -> None:
        self._probe = probe

    def clone(self) -> "ClonableProbeClient":
        """返回共享探测器的独立实例。"""

        return ClonableProbeClient(self._probe)

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
        """记录调用；审计高分、修复 none、生成返回定性文本。"""

        self._probe.record(_chapter_of(system_prompt, user_prompt), _kind_of(system_prompt), system_prompt, user_prompt)
        if "审计" in system_prompt or "audit" in system_prompt.lower():
            return '{"score": 99, "violations": []}'
        if "修复" in system_prompt or "repair" in system_prompt.lower():
            return '{"strategy": "none"}'
        return "基金业绩表现稳健，超额收益持续为正。该基金投资策略清晰，风险控制合理。"


class NoCloneClient:
    """无 clone() 的 fake：触发并发回退串行路径。"""

    def __init__(self, probe: ConcurrencyProbe) -> None:
        self._probe = probe

    def generate_text(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
        """记录调用；审计高分、修复 none、生成返回定性文本。"""

        self._probe.record(_chapter_of(system_prompt, user_prompt), _kind_of(system_prompt), system_prompt, user_prompt)
        if "审计" in system_prompt or "audit" in system_prompt.lower():
            return '{"score": 99, "violations": []}'
        if "修复" in system_prompt or "repair" in system_prompt.lower():
            return '{"strategy": "none"}'
        return "基金业绩表现稳健，超额收益持续为正。该基金投资策略清晰，风险控制合理。"


def _signatures(calls: list[tuple[int, str, str, str, int]]) -> list[tuple[int, str, str, str]]:
    """去掉序号后比较调用签名。"""

    return [(cid, kind, system_prompt, user_prompt) for cid, kind, system_prompt, user_prompt, _seq in calls]


def _run_serial_baseline(coordinator: ReportGenerationCoordinator, inputs: dict[str, object]) -> tuple[dict[int, str], list[str]]:
    """复刻改造前 generate_report 的串行调度（测试基线，非生产路径）。"""

    from fund_agent.service.chapter_generator import generate_data_table
    from fund_agent.service.extraction import _compute_ch6_stress_test, infer_fund_type

    fund_code = str(inputs["fund_code"])
    fund_name = str(inputs["fund_name"])
    report_year = int(inputs["report_year"])
    performance = inputs["performance"]
    holdings = inputs["holdings"]
    allocation = inputs["allocation"]
    fees = inputs["fees"]
    fund_manager = inputs.get("fund_manager")
    scale_info = inputs.get("scale_info")
    evidence = inputs.get("evidence")
    signal_judgment = inputs.get("signal_judgment")
    fund_type, _ = infer_fund_type(fund_name) if fund_name else ("", False)

    warnings: list[str] = []
    chapter_contents: dict[int, str] = {}

    # 0. 预生成所有章节数据表，收集全局允许数字集合
    global_numbers: set[str] = set()
    for cid in range(1, 8):
        st = _compute_ch6_stress_test(performance, report_year, scale_info, fund_name) if cid == 6 else None
        dt = generate_data_table(
            cid, fund_code, fund_name, report_year,
            performance, holdings, allocation, fees,
            fund_manager, scale_info, evidence,
            stress_test=st, signal_judgment=signal_judgment,
            fund_type=fund_type,
        )
        global_numbers.update(re.findall(r"\d+\.?\d*", dt.replace(",", "")))

    # 1. 串行生成 Ch1-6
    for cid in range(1, 7):
        content = coordinator._generate_and_audit_chapter(
            chapter_id=cid,
            fund_code=fund_code,
            fund_name=fund_name,
            report_year=report_year,
            performance=performance,
            holdings=holdings,
            allocation=allocation,
            fees=fees,
            fund_manager=fund_manager,
            scale_info=scale_info,
            evidence=evidence,
            signal_judgment=signal_judgment,
            global_allowed_numbers=global_numbers,
            fund_type=fund_type,
        )
        if content:
            chapter_contents[cid] = content
        else:
            warnings.append(f"Ch{cid} 生成失败")

    # 2. 检查 Ch1-6 是否全部通过
    all_passed = all(
        (coordinator._get_state(cid) or ChapterProcessState(chapter_id=cid)).status
        in ("passed", "passed_with_degradation")
        for cid in range(1, 7)
    )

    if not all_passed:
        warnings.append("Ch1-6 未全部通过，Ch0+Ch7 使用模板生成")
        chapter_contents[0] = coordinator._generate_template_chapter(
            chapter_id=0,
            fund_name=fund_name,
            report_year=report_year,
            performance=performance,
            evidence=evidence,
            fund_code=fund_code,
            fund_manager=fund_manager,
            scale_info=scale_info,
            signal_judgment=signal_judgment,
        )
        chapter_contents[7] = coordinator._generate_template_chapter(
            chapter_id=7,
            fund_name=fund_name,
            report_year=report_year,
            performance=performance,
            evidence=evidence,
            fund_code=fund_code,
            fund_manager=fund_manager,
            scale_info=scale_info,
            signal_judgment=signal_judgment,
        )
        return chapter_contents, warnings

    # 3. 串行生成 Ch0+Ch7
    for cid in (0, 7):
        content = coordinator._generate_and_audit_chapter(
            chapter_id=cid,
            fund_code=fund_code,
            fund_name=fund_name,
            report_year=report_year,
            performance=performance,
            holdings=holdings,
            allocation=allocation,
            fees=fees,
            fund_manager=fund_manager,
            scale_info=scale_info,
            use_chapter_summaries=True,
            chapter_summaries={cid: chapter_contents.get(cid, "") for cid in range(1, 7)},
            signal_judgment=signal_judgment,
        )
        if content:
            chapter_contents[cid] = content
        else:
            warnings.append(f"Ch{cid} 生成失败")
    return chapter_contents, warnings


# ============================================================
# T1: 并发生效与阶段 join
# ============================================================


def test_t1_concurrency_active_and_phase_join(tmp_path: Path) -> None:
    """concurrency=4 + delay：peak==4；8 章全产出；Ch0/Ch7 事件晚于 Ch1-6 全部终态。"""

    probe = ConcurrencyProbe(delay=0.02, gate_count=4)
    coordinator = ReportGenerationCoordinator(ClonableProbeClient(probe), tmp_path, chapter_concurrency=4)
    contents, _warnings = coordinator.generate_report(**_sample_inputs())

    assert probe.peak == 4
    assert sorted(contents) == list(range(8))
    b_last = max(seq for cid, _phase, seq in probe.events if cid in range(1, 7))
    d_first = min(seq for cid, _phase, seq in probe.events if cid in (0, 7))
    assert b_last < d_first, "Ch0/Ch7 不得与 Ch1-6 并发（B/D 之间必须 join）"


# ============================================================
# T2: lane 上限
# ============================================================


@pytest.mark.parametrize("concurrency,expected_peak", [(1, 1), (2, 2), (8, 6)])
def test_t2_concurrency_lane_caps(tmp_path: Path, concurrency: int, expected_peak: int) -> None:
    """concurrency∈{1,2,8}：peak 分别 ==1、≤2、B 阶段 ≤6 且整体 <8。"""

    gate_count = min(concurrency, 6)  # B 阶段仅 6 个任务
    probe = ConcurrencyProbe(delay=0.01, gate_count=gate_count)
    coordinator = ReportGenerationCoordinator(ClonableProbeClient(probe), tmp_path, chapter_concurrency=concurrency)
    contents, _warnings = coordinator.generate_report(**_sample_inputs())

    assert probe.peak == expected_peak
    assert sorted(contents) == list(range(8))
    if concurrency > 1:
        assert probe.peak < 8


# ============================================================
# T3: 结果顺序稳定（warnings 按 chapter_id 排序）
# ============================================================


def test_t3_result_order_and_warnings_sorted(tmp_path: Path) -> None:
    """低编号章最后完成时，输出仍按 cid 组装、warnings 按 cid 排序。"""

    probe = ConcurrencyProbe(delay=0.0, gate_count=1)
    coordinator = ReportGenerationCoordinator(ClonableProbeClient(probe), tmp_path, chapter_concurrency=4)
    original = coordinator._generate_and_audit_chapter

    def raiser(chapter_id: int, **kwargs):
        if chapter_id == 2:
            time.sleep(0.25)  # Ch2 最后失败
            raise RuntimeError("Ch2 boom")
        if chapter_id == 5:
            raise RuntimeError("Ch5 boom")  # Ch5 先失败
        return original(chapter_id=chapter_id, **kwargs)

    coordinator._generate_and_audit_chapter = raiser
    contents, warnings = coordinator.generate_report(**_sample_inputs())

    assert sorted(contents) == [0, 1, 3, 4, 6, 7]
    assert all(contents[cid] for cid in (0, 1, 3, 4, 6, 7))
    assert warnings[:2] == ["Ch2 生成失败", "Ch5 生成失败"]
    assert warnings[2] == "Ch1-6 未全部通过，Ch0+Ch7 使用模板生成"


# ============================================================
# T4: 单章失败隔离
# ============================================================


def test_t4_single_chapter_failure_isolated(tmp_path: Path) -> None:
    """仅 Ch3 抛异常：Ch3 None + failed；其余章正常；Ch0/Ch7 仍产出。"""

    probe = ConcurrencyProbe(delay=0.0, gate_count=4)
    coordinator = ReportGenerationCoordinator(ClonableProbeClient(probe), tmp_path, chapter_concurrency=4)
    original = coordinator._generate_and_audit_chapter

    def raiser(chapter_id: int, **kwargs):
        if chapter_id == 3:
            raise RuntimeError("Ch3 boom")
        return original(chapter_id=chapter_id, **kwargs)

    coordinator._generate_and_audit_chapter = raiser
    contents, warnings = coordinator.generate_report(**_sample_inputs())

    assert 3 not in contents
    for cid in (1, 2, 4, 5, 6, 0, 7):
        assert contents.get(cid), f"Ch{cid} 缺失"
    assert coordinator.get_process_states()[3].status == "failed"
    assert "Ch3 生成失败" in warnings


# ============================================================
# T5: 审计产物并发落盘
# ============================================================


def test_t5_audit_artifacts_concurrent_write(tmp_path: Path) -> None:
    """4 worker 完整跑：chapter_0..7_state.json 与 _audit.json 全部存在且可解析。"""

    probe = ConcurrencyProbe(delay=0.01, gate_count=4)
    coordinator = ReportGenerationCoordinator(ClonableProbeClient(probe), tmp_path, chapter_concurrency=4)
    coordinator.generate_report(**_sample_inputs())

    audit_dir = tmp_path / "audit_artifacts"
    for cid in range(8):
        state_json = audit_dir / f"chapter_{cid}_state.json"
        audit_json = audit_dir / f"chapter_{cid}_audit.json"
        assert state_json.is_file(), f"{state_json} 缺失"
        assert audit_json.is_file(), f"{audit_json} 缺失"
        json.loads(state_json.read_text(encoding="utf-8"))
        json.loads(audit_json.read_text(encoding="utf-8"))


# ============================================================
# T6: DeepSeekLlmClient.clone() 独立 usage
# ============================================================


def test_t6_deepseek_llm_clone_independent_usage() -> None:
    """clone() 同配置、独立 _cumulative_usage，原实例累计不影响 clone。"""

    from fund_agent.agent import DeepSeekChatResponse, DeepSeekLlmClient, ExecutionOptions

    class _UsageTransport:
        def send(self, request):
            return DeepSeekChatResponse(status_code=200, body=json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }))

    transport = _UsageTransport()
    client = DeepSeekLlmClient(
        transport=transport,
        env={"DEEPSEEK_API_KEY": "test-key"},
        options=ExecutionOptions(stream=False),
        system_prompt="custom-system",
        temperature=0.7,
    )
    cloned = client.clone()

    assert cloned is not client
    assert cloned._transport is client._transport
    assert cloned._env == client._env
    assert cloned._timeout_seconds == client._timeout_seconds
    assert cloned._options == client._options
    assert cloned._system_prompt == client._system_prompt
    assert cloned._temperature == client._temperature
    assert cloned.cumulative_usage is not client.cumulative_usage
    assert cloned.cumulative_usage.total_tokens == 0

    client.next_step(document_id="doc", query="q", tool_results=())
    assert client.cumulative_usage.prompt_tokens == 10
    assert client.cumulative_usage.completion_tokens == 5
    assert cloned.cumulative_usage.total_tokens == 0


# ============================================================
# T7: 参数与优先级
# ============================================================


@pytest.mark.parametrize("bad", [0, 9])
def test_t7_concurrency_out_of_range_raises_value_error(tmp_path: Path, bad: int) -> None:
    """coordinator 校验 1..8，越界抛 ValueError。"""

    with pytest.raises(ValueError):
        ReportGenerationCoordinator(object(), tmp_path, chapter_concurrency=bad)


def _make_catalog(work_dir: Path, fund_code: str, year: int = 2024) -> None:
    """写入最小 completed_reports.json，供 Service 级测试使用。"""

    doc_id = f"{fund_code}-{year}-annual_report-fp"
    catalog_path = work_dir / "completed_reports.json"
    catalog_path.write_text(json.dumps({
        "schema_version": 1,
        "reports": {
            doc_id: {
                "schema_version": 1,
                "document_id": doc_id,
                "identity": {
                    "fund_code": fund_code,
                    "fund_name": "安信企业价值优选混合型证券投资基金",
                    "year": year,
                    "report_type": "annual_report",
                    "source_kind": "local_pdf",
                    "content_fingerprint": "fp",
                    "document_id": doc_id,
                },
                "stored_blob_ref": "blob",
                "docling_json_ref": "docling_json:doc",
            },
        },
    }), encoding="utf-8")


class _SpyCoordinator:
    """捕获 chapter_concurrency 的 coordinator spy。"""

    captured: list[int] = []

    def __init__(self, **kwargs) -> None:
        _SpyCoordinator.captured.append(kwargs.get("chapter_concurrency"))

    def generate_report(self, **kwargs) -> tuple[dict[int, str], list[str]]:
        """返回空结果，供解析点测试。"""

        return {}, []

    def get_process_states(self) -> dict[int, object]:
        """返回空状态。"""

        return {}


def _make_spy_service(monkeypatch: pytest.MonkeyPatch) -> FundReadingService:
    """构造提取/评分全部打桩的 Service 实例。"""

    service = FundReadingService()
    monkeypatch.setattr(service, "_extract_report_holdings_with_citations", lambda *a, **k: ({}, {}, {}))
    monkeypatch.setattr(service, "_extract_report_fees_with_citations", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(service, "_extract_report_performance_with_citations", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(service, "_extract_report_allocation_with_citations", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(service, "_extract_fund_manager", lambda *a, **k: None)
    monkeypatch.setattr(service, "_extract_fund_manager_with_citation", lambda *a, **k: (None, None))
    monkeypatch.setattr(service, "_extract_scale_info", lambda *a, **k: (None, None))
    monkeypatch.setattr(service, "compute_signal_judgment", lambda **k: None)
    monkeypatch.setattr(service, "compute_risk_checklist", lambda **k: [])
    return service


def test_t7_concurrency_priority_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """优先级：request 字段 > env > 默认 4。"""

    _SpyCoordinator.captured.clear()
    from fund_agent.service import audit_pipeline as audit_pipeline_module

    monkeypatch.setattr(audit_pipeline_module, "ReportGenerationCoordinator", _SpyCoordinator)

    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    _make_catalog(work_dir, "004393")
    service = _make_spy_service(monkeypatch)
    base = dict(
        fund_code="004393",
        fund_name="安信企业价值优选混合型证券投资基金",
        report_year=2024,
        years=[2024],
        work_dir=work_dir,
        output_format="json",
    )

    # 默认 4
    monkeypatch.delenv("FUND_CHECKLIST_CHAPTER_CONCURRENCY", raising=False)
    service.generate_report(GenerateReportRequest(**base), llm_client=object())
    assert _SpyCoordinator.captured[-1] == 4

    # env 覆盖默认
    monkeypatch.setenv("FUND_CHECKLIST_CHAPTER_CONCURRENCY", "2")
    service.generate_report(GenerateReportRequest(**base), llm_client=object())
    assert _SpyCoordinator.captured[-1] == 2

    # request 字段覆盖 env
    service.generate_report(GenerateReportRequest(**base, chapter_concurrency=6), llm_client=object())
    assert _SpyCoordinator.captured[-1] == 6


# ============================================================
# T8: 无 clone() 回退串行
# ============================================================


def test_t8_no_clone_falls_back_to_serial(tmp_path: Path) -> None:
    """无 clone() + concurrency=4：回退串行 + warning，行为与串行一致。"""

    probe = ConcurrencyProbe(delay=0.0, gate_count=1)
    coordinator = ReportGenerationCoordinator(NoCloneClient(probe), tmp_path, chapter_concurrency=4)
    contents, warnings = coordinator.generate_report(**_sample_inputs())

    assert "LLM client 不支持并发克隆，已回退串行" in warnings
    assert sorted(contents) == list(range(8))
    assert probe.peak == 1

    serial_probe = ConcurrencyProbe(delay=0.0, gate_count=1)
    serial_coordinator = ReportGenerationCoordinator(NoCloneClient(serial_probe), tmp_path / "serial", chapter_concurrency=1)
    serial_contents, serial_warnings = serial_coordinator.generate_report(**_sample_inputs())
    assert _signatures(probe.calls) == _signatures(serial_probe.calls)
    assert contents == serial_contents
    assert warnings[1:] == serial_warnings


# ============================================================
# 验收：concurrency=1 与串行基线调用序列一致
# ============================================================


def test_concurrency_one_matches_serial_baseline(tmp_path: Path) -> None:
    """chapter_concurrency=1 时 LLM 调用序列与改造前串行基线完全一致。"""

    baseline_probe = ConcurrencyProbe(delay=0.0, gate_count=1)
    baseline_coordinator = ReportGenerationCoordinator(
        ClonableProbeClient(baseline_probe), tmp_path / "baseline", chapter_concurrency=1,
    )
    baseline_contents, baseline_warnings = _run_serial_baseline(baseline_coordinator, _sample_inputs())

    new_probe = ConcurrencyProbe(delay=0.0, gate_count=1)
    new_coordinator = ReportGenerationCoordinator(
        ClonableProbeClient(new_probe), tmp_path / "new", chapter_concurrency=1,
    )
    new_contents, new_warnings = new_coordinator.generate_report(**_sample_inputs())

    assert _signatures(baseline_probe.calls) == _signatures(new_probe.calls)
    assert baseline_contents == new_contents
    assert baseline_warnings == new_warnings
    assert new_probe.peak == 1
