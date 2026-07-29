"""端到端测试公共 fixtures。

提供：
- e2e_work_dir: 已导入 004393 年报的工作目录
- fund_code / fund_name: 测试基金信息
- document_id_map: year → document_id 映射
- get_document_id: 按年份获取 document_id 的 helper
- requires_llm: DEEPSEEK_API_KEY 缺失时 skip
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# e2e 工作目录（已通过 import 命令初始化）
E2E_WORK_DIR = PROJECT_ROOT / ".fund_checklist_e2e_004393"

# 测试基金信息
FUND_CODE = "004393"
FUND_NAME = "安信企业价值优选混合"
YEARS = [2021, 2022, 2023, 2024, 2025]


def _load_document_id_map(work_dir: Path) -> dict[int, str]:
    """从 completed_reports.json 加载 year → document_id 映射。"""
    catalog_path = work_dir / "completed_reports.json"
    if not catalog_path.exists():
        return {}
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    result: dict[int, str] = {}
    for doc_id, info in catalog.get("reports", {}).items():
        identity = info.get("identity", {})
        year = identity.get("year")
        if year and identity.get("fund_code") == FUND_CODE:
            result[int(year)] = doc_id
    return result


@pytest.fixture(scope="session")
def e2e_work_dir() -> Path:
    """返回已导入年报的工作目录路径。"""
    if not E2E_WORK_DIR.exists():
        pytest.skip("e2e 工作目录不存在，请先运行 import 命令")
    return E2E_WORK_DIR


@pytest.fixture(scope="session")
def fund_code() -> str:
    return FUND_CODE


@pytest.fixture(scope="session")
def fund_name() -> str:
    return FUND_NAME


@pytest.fixture(scope="session")
def document_id_map(e2e_work_dir: Path) -> dict[int, str]:
    """返回 year → document_id 映射。"""
    mapping = _load_document_id_map(e2e_work_dir)
    if not mapping:
        pytest.skip("未找到已导入的年报 document_id")
    return mapping


@pytest.fixture(scope="session")
def latest_document_id(document_id_map: dict[int, str]) -> str:
    """返回最新年份的 document_id。"""
    latest_year = max(document_id_map.keys())
    return document_id_map[latest_year]


@pytest.fixture(scope="session")
def requires_llm():
    """DEEPSEEK_API_KEY 缺失时 skip。"""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过需要 LLM 的测试")


def run_cli_command(
    args: list[str],
    *,
    timeout: int = 600,
    stdin_input: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """运行 fund-checklist CLI 命令。

    参数:
        args: CLI 参数列表（不含 'fund-checklist'）。
        timeout: 超时秒数。
        stdin_input: 通过 stdin 输入的内容（用于 interactive 模式）。
        cwd: 工作目录。

    返回:
        subprocess.CompletedProcess。
    """
    cmd = [sys.executable, "-m", "fund_agent.cli.main"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin_input,
        cwd=cwd or PROJECT_ROOT,
    )
    return result


def run_interactive_session(
    fund_code: str,
    work_dir: Path,
    inputs: list[str],
    *,
    label: str | None = None,
    plain: bool = False,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """运行 interactive 会话，通过 stdin pipe 输入。

    参数:
        fund_code: 基金代码。
        work_dir: 工作目录。
        inputs: 通过 stdin 输入的行列表。
        label: 会话标签。
        plain: 是否使用 --plain 模式。
        timeout: 超时秒数。

    返回:
        (returncode, stdout, stderr) 元组。
    """
    args = ["interactive", "--fund-code", fund_code, "--work-dir", str(work_dir)]
    if label:
        args.extend(["--label", label])
    if plain:
        args.append("--plain")

    cmd = [sys.executable, "-m", "fund_agent.cli.main"] + args
    stdin_input = "\n".join(inputs) + "\n"

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=PROJECT_ROOT,
    )
    try:
        stdout, stderr = proc.communicate(input=stdin_input, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return -1, stdout, stderr

    return proc.returncode, stdout, stderr
