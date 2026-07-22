#!/usr/bin/env python3
"""CI E2E 数据准备脚本。

从 EID 下载 `基金年报/code_20260519.csv` 中全部基金 × 5 年年报 PDF，
导入到 e2e 工作目录，供 `test_e2e_holdings_regression.py` 使用。

用法:
    uv run python scripts/setup_e2e_data.py

前置条件:
    - EID API 可访问 (http://eid.csrc.gov.cn)
    - Docling 已安装 (uv sync)

覆盖范围:
    - CSV 中 56 只基金（国内股票/债券、海外股票/债券、黄金、货币）
    - 加上 2 只场内 ETF（512890/159632，作为联接基金的目标 ETF）
    - 每只基金 × 5 年（2021-2025），部分基金因成立时间晚于 2021 而年份更少
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "基金年报" / "code_20260519.csv"
PDF_DIR = PROJECT_ROOT / "基金年报"
YEARS = [2021, 2022, 2023, 2024, 2025]
YEAR_RANGE = f"{min(YEARS)}-{max(YEARS)}"

# 场内 ETF（CSV 中不含，但联接基金继承持仓需要）
EXTRA_ETFS: list[dict] = [
    {
        "code": "512890",
        "name": "华泰柏瑞中证红利低波动交易型开放式指数证券投资基金",
        "target_of": ["007466", "009051"],  # 被这些联接基金引用
    },
    {
        "code": "159632",
        "name": "华安纳斯达克100ETF（QDII）",
        "target_of": ["040046"],
    },
]


def run_cmd(args: list[str], cwd: Path = PROJECT_ROOT) -> tuple[int, str]:
    """运行子进程，返回 (returncode, combined_output)。"""
    r = subprocess.run(args, capture_output=True, text=True, cwd=str(cwd))
    return r.returncode, r.stdout + r.stderr


def download_pdf(fund_code: str, year: int, output_dir: Path) -> bool:
    """从 EID 下载单只基金单年度年报。"""
    code, out = run_cmd([
        sys.executable, "-m", "fund_agent.cli.main", "download",
        "--fund-code", fund_code, "--year", str(year),
        "--output-dir", str(output_dir),
    ])
    if code == 0:
        return True
    if "not_found" in out:
        return False
    print(f"    ✗ {fund_code} {year}: {out[:150]}")
    return False


def import_pdfs(
    pdf_dir: Path, fund_code: str, fund_name: str,
    year_range: str, work_dir: Path,
) -> bool:
    """将 PDF 导入到 e2e 工作目录。"""
    code, out = run_cmd([
        sys.executable, "-m", "fund_agent.cli.main", "import",
        "--pdf-dir", str(pdf_dir),
        "--fund-code", fund_code,
        "--fund-name", fund_name,
        "--year-range", year_range,
        "--work-dir", str(work_dir),
    ])
    if code == 0:
        return True
    print(f"    ✗ import {fund_code}: {out[:150]}")
    return False


def e2e_dir_name(fund_code: str) -> str:
    """生成 e2e 目录名。"""
    return f".fund_checklist_e2e_{fund_code}"


def is_already_imported(e2e_dir: Path, fund_code: str) -> bool:
    """检查是否已导入足够年份。"""
    catalog_path = e2e_dir / "completed_reports.json"
    if not catalog_path.exists():
        return False
    catalog = json.loads(catalog_path.read_text())
    imported = {
        r["identity"]["year"]
        for r in catalog.get("reports", {}).values()
        if r["identity"]["fund_code"] == fund_code
    }
    return set(YEARS) <= imported


def setup_fund(fund_code: str, fund_name: str) -> None:
    """设置单只基金的 e2e 数据。"""
    e2e_dir = PROJECT_ROOT / e2e_dir_name(fund_code)

    if is_already_imported(e2e_dir, fund_code):
        return

    # 下载 PDF
    dl_dir = e2e_dir / "_downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for year in YEARS:
        if download_pdf(fund_code, year, dl_dir):
            downloaded += 1

    if downloaded == 0:
        print(f"    ⚠ {fund_code}: 无可用年报，跳过")
        shutil.rmtree(dl_dir, ignore_errors=True)
        return

    # 导入
    import_pdfs(dl_dir, fund_code, fund_name, YEAR_RANGE, e2e_dir)
    shutil.rmtree(dl_dir, ignore_errors=True)


def setup_etf_for_feeder(etf: dict) -> None:
    """将目标 ETF 导入到引用它的联接基金目录。"""
    for feeder_code in etf["target_of"]:
        e2e_dir = PROJECT_ROOT / e2e_dir_name(feeder_code)
        if not e2e_dir.exists():
            continue

        # 检查 ETF 是否已导入
        catalog_path = e2e_dir / "completed_reports.json"
        if catalog_path.exists():
            catalog = json.loads(catalog_path.read_text())
            etf_imported = any(
                r["identity"]["fund_code"] == etf["code"]
                for r in catalog.get("reports", {}).values()
            )
            if etf_imported:
                continue

        # 下载 ETF PDF
        dl_dir = e2e_dir / f"_downloads_{etf['code']}"
        dl_dir.mkdir(parents=True, exist_ok=True)
        for year in YEARS:
            download_pdf(etf["code"], year, dl_dir)

        # 导入到联接基金的 e2e 目录
        import_pdfs(dl_dir, etf["code"], etf["name"], YEAR_RANGE, e2e_dir)
        shutil.rmtree(dl_dir, ignore_errors=True)


def main() -> None:
    print("=" * 60)
    print("  E2E 数据准备：从 CSV 全量下载 + 导入")
    print("=" * 60)

    # 读取 CSV
    if not CSV_PATH.exists():
        print(f"✗ CSV 文件不存在: {CSV_PATH}")
        sys.exit(1)

    funds: list[tuple[str, str]] = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                funds.append((row[1].strip(), row[0].strip()))

    print(f"CSV 中 {len(funds)} 只基金")

    # EID 可达性检查
    import urllib.request
    try:
        urllib.request.urlopen("http://eid.csrc.gov.cn", timeout=5)
        print("✓ EID API 可达")
    except Exception:
        print("⚠ EID API 不可达，将仅使用已有的本地 PDF")

    # 第一轮：下载并导入 CSV 中所有基金
    print(f"\n--- 第一轮：CSV 基金 ({len(funds)} 只) ---")
    for i, (code, name) in enumerate(funds, 1):
        print(f"[{i}/{len(funds)}] {code} {name}")
        setup_fund(code, name)

    # 第二轮：为联接基金导入目标 ETF
    print(f"\n--- 第二轮：目标 ETF 共导入 ---")
    for etf in EXTRA_ETFS:
        print(f"  ETF {etf['code']} → 联接基金 {etf['target_of']}")
        setup_etf_for_feeder(etf)

    # 验证
    print(f"\n{'=' * 60}")
    print("  验证结果")
    print(f"{'=' * 60}")
    ok = 0
    fail = 0
    for code, name in funds:
        e2e_dir = PROJECT_ROOT / e2e_dir_name(code)
        catalog_path = e2e_dir / "completed_reports.json"
        if catalog_path.exists():
            catalog = json.loads(catalog_path.read_text())
            count = sum(
                1 for r in catalog.get("reports", {}).values()
                if r["identity"]["fund_code"] == code
            )
            print(f"  ✓ {code} {name[:25]:25s} {count}年")
            ok += 1
        else:
            print(f"  ✗ {code} {name[:25]:25s} 未导入")
            fail += 1

    print(f"\n完成: {ok} 成功, {fail} 失败")
    print("\n运行测试:")
    print("  uv run pytest tests/fund/test_e2e_holdings_regression.py -v")


if __name__ == "__main__":
    main()
