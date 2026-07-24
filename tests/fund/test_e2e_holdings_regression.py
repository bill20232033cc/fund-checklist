"""多类型基金 × 多年度持仓抽取端到端回归测试。

使用 `基金年报/` 目录中的真实 PDF，不使用 mock。
数据来源：`基金年报/code_20260519.csv`（56 只基金）+ 2 只场内 ETF。
CI 前置：`uv run python scripts/setup_e2e_data.py`。

本测试文件必须在 CI 中运行，防止新增基金类型引入回归。
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from fund_agent.fund.document_tools.persistent_repository import FilesystemReportRepository
from fund_agent.service.extraction import FundReadingService

# E2E 测试标记：CI 中应使用 `pytest -m e2e` 或 `pytest -ra` 确保不静默跳过
pytestmark = pytest.mark.e2e

_E2E_DIR = Path(__file__).resolve().parents[2]
_CSV_PATH = _E2E_DIR / "基金年报" / "code_20260519.csv"
YEARS = [2021, 2022, 2023, 2024, 2025]

# 已知失败的 (fund_code, year) 组合
_KNOWN_FAILURES: set[tuple[str, int]] = {
    ("512890", 2022),   # Docling 将持仓表格错放到错误 section
    ("512890", 2024),   # 年报披露"本基金本报告期末未持有股票"
    ("040046", 2021),   # 前身基金，非联接基金结构
    ("007466", 2021),   # 目标 ETF 2021 年持仓仅 4 条
    ("017641", 2023),   # QDII 标普500指数，持仓仅 3 条
    ("017641", 2024),   # QDII 标普500指数，持仓仅 3 条
}

# 债券基金 / 货币基金不要求 stock_code
_BOND_CODES: set[str] = set()
_NO_STOCK_CODE_CODES: set[str] = set()


def _load_fund_matrix() -> list[dict]:
    """从 CSV 加载基金列表，生成测试矩阵。"""
    if not _CSV_PATH.exists():
        return []

    matrix = []
    with open(_CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 3 or not row[1].strip():
                continue
            code = row[1].strip()
            name = row[0].strip()
            category = row[2].strip() if len(row) > 2 else ""

            is_bond = "债券" in category or "债" in name
            is_money = "货币" in category
            if is_bond or is_money:
                _BOND_CODES.add(code)
                _NO_STOCK_CODE_CODES.add(code)

            matrix.append({
                "label": f"{code} {name[:20]}",
                "work_dir": _E2E_DIR / f".fund_checklist_e2e_{code}",
                "fund_code": code,
                "fund_name": name,
                "years": YEARS,
                "min_holdings": 1 if (is_bond or is_money) else 5,
                "require_stock_code": not (is_bond or is_money),
                "min_fees": 1,
            })

    return matrix


_FUND_MATRIX = _load_fund_matrix()


def _find_document_id(
    work_dir: Path,
    fund_code: str,
    year: int,
) -> str | None:
    """从 completed_reports.json 查找匹配的 document_id。"""
    catalog_path = work_dir / "completed_reports.json"
    if not catalog_path.exists():
        return None
    catalog = json.loads(catalog_path.read_text())
    for doc_id, report in catalog["reports"].items():
        id_data = report.get("identity", {})
        if id_data.get("fund_code") != fund_code:
            continue
        if id_data.get("year") != year:
            continue
        return doc_id
    return None


def _collect_test_cases() -> list[tuple[dict, int]]:
    cases = []
    for fund_info in _FUND_MATRIX:
        for year in fund_info["years"]:
            cases.append((fund_info, year))
    return cases


_TEST_CASES = _collect_test_cases()
_TEST_IDS = [f"{fi['label']}_{y}" for fi, y in _TEST_CASES]


@pytest.mark.parametrize("fund_info,year", _TEST_CASES, ids=_TEST_IDS)
def test_holdings_extraction(fund_info: dict, year: int) -> None:
    """单只基金 × 单年度：持仓抽取成功且数量符合预期。"""
    service = FundReadingService()
    work_dir: Path = fund_info["work_dir"]
    fund_code: str = fund_info["fund_code"]
    fund_name: str = fund_info["fund_name"]
    min_holdings: int = fund_info["min_holdings"]
    require_stock_code: bool = fund_info["require_stock_code"]

    if not work_dir.exists():
        if os.environ.get("CI"):
            assert False, f"e2e 目录不存在（CI 环境不允许跳过）: {work_dir}"
        pytest.skip(f"e2e 目录不存在: {work_dir}")

    doc_id = _find_document_id(work_dir, fund_code, year)
    if doc_id is None:
        if os.environ.get("CI"):
            assert False, f"未导入 {fund_code} {year}（CI 环境不允许跳过）"
        pytest.skip(f"未导入 {fund_code} {year}")

    repo = FilesystemReportRepository(
        catalog_path=work_dir / "completed_reports.json",
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    store = repo.load_store(doc_id)
    result = service._extract_holdings_from_store(
        document_id=doc_id,
        store=store,
        report_year=year,
        fund_name=fund_name,
        repository=repo,
    )

    is_known = (fund_code, year) in _KNOWN_FAILURES

    if result.failure is not None:
        if is_known:
            pytest.xfail(f"已知 gap: {fund_code} {year} {result.failure.message}")
        assert False, f"{fund_code} {year} 持仓抽取失败: {result.failure.message}"

    if len(result.holdings) < min_holdings:
        if is_known:
            pytest.xfail(
                f"已知 gap: {fund_code} {year} 持仓 {len(result.holdings)} < {min_holdings}"
            )
        assert False, f"{fund_code} {year} 持仓 {len(result.holdings)} < {min_holdings}"

    if require_stock_code:
        for h in result.holdings[:3]:
            assert h.stock_code, f"{fund_code} {year} stock_code 为空"
            assert h.stock_name, f"{fund_code} {year} stock_name 为空"
            assert h.percentage, f"{fund_code} {year} percentage 为空"


@pytest.mark.parametrize(
    "fund_info",
    _FUND_MATRIX,
    ids=[f["label"] for f in _FUND_MATRIX],
)
def test_fee_rates_extraction(fund_info: dict) -> None:
    """每类基金 × 最新年份：费率抽取成功。"""
    service = FundReadingService()
    work_dir: Path = fund_info["work_dir"]
    fund_code: str = fund_info["fund_code"]
    min_fees: int = fund_info["min_fees"]

    if not work_dir.exists():
        if os.environ.get("CI"):
            assert False, f"e2e 目录不存在（CI 环境不允许跳过）: {work_dir}"
        pytest.skip(f"e2e 目录不存在: {work_dir}")

    latest_year = max(fund_info["years"])
    doc_id = _find_document_id(work_dir, fund_code, latest_year)
    if doc_id is None:
        if os.environ.get("CI"):
            assert False, f"未找到 {fund_code} {latest_year}（CI 环境不允许跳过）"
        pytest.skip(f"未找到 {fund_code} {latest_year}")

    repo = FilesystemReportRepository(
        catalog_path=work_dir / "completed_reports.json",
        blob_root=work_dir / "pdf_blobs",
        docling_json_root=work_dir / "docling_json",
    )
    store = repo.load_store(doc_id)

    result = service._extract_fee_rates_from_store(
        document_id=doc_id,
        store=store,
        report_year=latest_year,
    )

    assert result.failure is None, (
        f"{fund_code} {latest_year} 费率抽取失败: {result.failure.message}"
    )
    assert len(result.fees) >= min_fees, (
        f"{fund_code} {latest_year} 费率 {len(result.fees)} < {min_fees}"
    )
