"""从 CSRC EID（证监会电子信息披露平台）下载基金年报。

仅使用 Python 标准库，无外部依赖。

参数:
    fund_code: 基金代码（如 "159632"）。
    year: 报告年份（如 2025）。
    output_dir: PDF 输出目录。

返回:
    下载结果（文件路径或错误信息）。

异常:
    网络失败、基金代码无效、报告未找到时抛出 EidDownloadError。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_URL = "http://eid.csrc.gov.cn/fund"
VALIDATE_PATH = "/disclose/validate_fund.do"
SEARCH_PATH = "/disclose/advanced_search_report.do"
PDF_PATH = "/disclose/instance_show_pdf_id.do"

ANNUAL_REPORT_SPEC = {
    "report_type": "FB010",
    "report_code": "FB010010",
    "report_desp": "年度报告",
}

# 2026-08-14 EID 实证（docs/research/quarterly-semiannual-data-source-research-20260814.md；
# 2026-08-17 直连 EID 实测修正季报 reportDesp 为中文数字）：
# 半年报 reportType=FB020 / reportCode=FB020010 / reportDesp=中期报告；
# 季报 reportType=FB030 / reportCode=FB0300X / reportDesp=中文数字季度报告
# （"第一季度报告"…"第四季度报告"，N=1..4）。
SEMIANNUAL_REPORT_SPEC = {
    "report_type": "FB020",
    "report_code": "FB020010",
    "report_desp": "中期报告",
}
QUARTERLY_REPORT_CODE_BY_QUARTER = {
    1: "FB030010",
    2: "FB030020",
    3: "FB030030",
    4: "FB030040",
}
QUARTERLY_REPORT_DESP_BY_QUARTER = {
    1: "第一季度报告",
    2: "第二季度报告",
    3: "第三季度报告",
    4: "第四季度报告",
}
REPORT_SPECS = {
    "annual_report": ANNUAL_REPORT_SPEC,
    "semiannual_report": SEMIANNUAL_REPORT_SPEC,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class EidDownloadError(Exception):
    """EID 下载失败。"""

    def __init__(self, message: str, *, code: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DownloadResult:
    """下载结果。"""

    fund_code: str
    fund_name: str
    year: int
    file_path: Path | None
    source_url: str | None
    status: str  # "downloaded" | "cached" | "error"
    error: str | None = None


def download_annual_report(
    fund_code: str,
    year: int,
    output_dir: Path,
    *,
    force: bool = False,
    sleep_seconds: float = 0.2,
) -> DownloadResult:
    """下载单只基金的年报 PDF（annual 兼容入口）。

    参数:
        fund_code: 基金代码。
        year: 报告年份。
        output_dir: 输出目录。
        force: 是否强制重新下载。
        sleep_seconds: 请求间隔（秒）。

    返回:
        DownloadResult。

    异常:
        EidDownloadError: 基金代码无效、报告未找到、网络失败。
    """

    return download_report(
        fund_code=fund_code,
        year=year,
        output_dir=output_dir,
        report_type="annual_report",
        force=force,
        sleep_seconds=sleep_seconds,
    )


def download_report(
    fund_code: str,
    year: int,
    output_dir: Path,
    *,
    report_type: str = "annual_report",
    quarter: int | None = None,
    force: bool = False,
    sleep_seconds: float = 0.2,
) -> DownloadResult:
    """下载单只基金的指定报告类型 PDF（年报/半年报/季报）。

    参数:
        fund_code: 基金代码。
        year: 报告年份。
        output_dir: 输出目录。
        report_type: 报告类型（annual_report / semiannual_report / quarterly_report）。
        quarter: 季报期次 1-4；仅 report_type=quarterly_report 必填。
        force: 是否强制重新下载。
        sleep_seconds: 请求间隔（秒）。

    返回:
        DownloadResult。

    异常:
        EidDownloadError: 基金代码无效、报告未找到、网络失败或参数不合法。
    """
    fund_code = _normalize_fund_code(fund_code)
    if report_type not in ("annual_report", "semiannual_report", "quarterly_report"):
        raise EidDownloadError(f"不支持的 report_type: {report_type}", code="schema_drift")
    if report_type == "quarterly_report":
        if quarter not in (1, 2, 3, 4):
            raise EidDownloadError("quarterly_report 必须指定 quarter 1-4", code="schema_drift")
    elif quarter is not None:
        raise EidDownloadError("quarter 仅适用于 quarterly_report", code="schema_drift")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 验证基金代码（获取 eid 内部 fundId）
    fund_id = _validate_fund(fund_code)
    time.sleep(sleep_seconds)

    # 2. 搜索目标报告（同时获取基金简称）
    spec = _spec_for(report_type, quarter)
    candidate, fund_short_name = _search_report(
        fund_code=fund_code,
        fund_id=fund_id,
        year=year,
        spec=spec,
    )
    upload_info_id = str(candidate["uploadInfoId"])
    time.sleep(sleep_seconds)

    # 3. 下载 PDF
    pdf_url = _pdf_url(upload_info_id)
    safe_name = _safe_filename(fund_short_name)[:60]
    if report_type == "quarterly_report":
        file_path = output_dir / f"{fund_code}_{safe_name}_{year}_Q{quarter}_quarterly_report.pdf"
    else:
        report_suffix = "semiannual_report" if report_type == "semiannual_report" else "annual_report"
        file_path = output_dir / f"{fund_code}_{safe_name}_{year}_{report_suffix}.pdf"

    if file_path.exists() and not force and _looks_like_pdf(file_path.read_bytes()):
        return DownloadResult(
            fund_code=fund_code,
            fund_name=fund_short_name,
            year=year,
            file_path=file_path,
            source_url=pdf_url,
            status="cached",
        )

    content = _request_bytes(pdf_url)
    if not _looks_like_pdf(content):
        raise EidDownloadError(
            f"下载内容不是 PDF: {fund_code}",
            code="integrity_error",
        )
    file_path.write_bytes(content)

    return DownloadResult(
        fund_code=fund_code,
        fund_name=fund_short_name,
        year=year,
        file_path=file_path,
        source_url=pdf_url,
        status="downloaded",
    )


def _spec_for(report_type: str, quarter: int | None) -> dict[str, str]:
    """返回 EID 搜索 spec（reportType/reportCode/reportDesp）。"""

    if report_type == "quarterly_report":
        return {
            "report_type": "FB030",
            "report_code": QUARTERLY_REPORT_CODE_BY_QUARTER[quarter],  # type: ignore[index]
            "report_desp": QUARTERLY_REPORT_DESP_BY_QUARTER[quarter],  # type: ignore[index]
        }
    return dict(REPORT_SPECS[report_type])


# -- 内部函数 --


def _validate_fund(fund_code: str) -> str:
    """验证基金代码，返回 EID 内部 fundId。

    EID validate_fund.do 接口：
    - POST cFundCode=<基金代码>
    - 返回 {"fundId": 11314, "isSuccess": true}
    """
    url = _url(VALIDATE_PATH)
    payload = _request_json(url, data={"cFundCode": fund_code})
    if not isinstance(payload, dict) or payload.get("isSuccess") is not True:
        raise EidDownloadError(
            f"基金代码无效或未找到: {fund_code}",
            code="not_found",
        )
    fund_id = payload.get("fundId")
    if fund_id is None:
        raise EidDownloadError(
            f"基金代码验证返回无 fundId: {fund_code}",
            code="not_found",
        )
    return str(fund_id)


def _report_display_label(spec: dict[str, str]) -> str:
    """返回报告类型的展示标签（not_found 消息用）。

    年报 → 年报；半年报 → 中期报告；季报 → 第N季度报告（期次由
    report_code 反查 QUARTERLY_REPORT_CODE_BY_QUARTER，2026-08-17 EID 实测修正）。
    """
    report_code = spec["report_code"]
    if report_code in QUARTERLY_REPORT_CODE_BY_QUARTER.values():
        quarter = next(
            q
            for q, code in QUARTERLY_REPORT_CODE_BY_QUARTER.items()
            if code == report_code
        )
        return f"第{quarter}季度报告"
    if report_code == SEMIANNUAL_REPORT_SPEC["report_code"]:
        return "中期报告"
    return "年报"


def _search_report(
    *,
    fund_code: str,
    fund_id: str,
    year: int,
    spec: dict[str, str],
) -> tuple[dict[str, Any], str]:
    """搜索指定报告类型（年报/半年报/季报），返回 (candidate_dict, fund_short_name)。

    EID advanced_search_report.do 接口：
    - GET params: aoData=[{name, value}, ...]（JSON 数组）
    - 返回 {"aaData": [...], "iTotalRecords": N, ...}
    """
    ao_data = [
        {"name": "iDisplayStart", "value": 0},
        {"name": "iDisplayLength", "value": 50},
        {"name": "fundType", "value": ""},
        {"name": "reportType", "value": spec["report_type"]},
        {"name": "reportYear", "value": str(year)},
        {"name": "fundCompanyShortName", "value": ""},
        {"name": "fundCode", "value": fund_code},
        {"name": "fundShortName", "value": ""},
        {"name": "startUploadDate", "value": ""},
        {"name": "endUploadDate", "value": ""},
    ]
    payload = _request_json(
        _url(SEARCH_PATH),
        params={"aoData": json.dumps(ao_data, ensure_ascii=False, separators=(",", ":"))},
    )
    if not isinstance(payload, dict):
        raise EidDownloadError(
            f"搜索返回格式异常: {fund_code}",
            code="unavailable",
        )

    rows = payload.get("aaData")
    if not isinstance(rows, list):
        raise EidDownloadError(
            f"搜索返回无 aaData: {fund_code}",
            code="unavailable",
        )

    # 按 fundCode + fundId 精确匹配
    fund_short_name = fund_code  # 默认值
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("fundShortName", "")):
            fund_short_name = str(row["fundShortName"])
        if _candidate_matches(
            row=row,
            fund_code=fund_code,
            fund_id=fund_id,
            year=year,
            report_code=spec["report_code"],
            report_desp=spec["report_desp"],
        ):
            return row, fund_short_name

    # 回退：仅按 fundId + 年份 + 报告类型匹配（fundCode 可能不一致）
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _strict_match(row, fund_id, year, spec["report_code"], spec["report_desp"]):
            return row, str(row.get("fundShortName", fund_code))

    raise EidDownloadError(
        f"未找到 {fund_code} 的 {year} 年{_report_display_label(spec)}",
        code="not_found",
    )


def _candidate_matches(
    *,
    row: dict[str, Any],
    fund_code: str,
    fund_id: str,
    year: int,
    report_code: str,
    report_desp: str,
) -> bool:
    """精确匹配：fundCode + fundId + 年份 + 报告类型。"""
    report_name = str(row.get("reportName") or "")
    return (
        str(row.get("fundCode")) == fund_code
        and str(row.get("fundId")) == fund_id
        and str(row.get("reportYear")) == str(year)
        and str(row.get("reportCode")) == report_code
        and str(row.get("reportDesp")) == report_desp
        and str(row.get("tableName")) == "PDF"
        and "摘要" not in report_name
        and row.get("uploadInfoId") is not None
    )


def _strict_match(
    row: dict[str, Any],
    fund_id: str,
    year: int,
    report_code: str,
    report_desp: str,
) -> bool:
    """回退匹配：fundId + 年份 + 报告类型（忽略 fundCode）。"""
    report_name = str(row.get("reportName") or "")
    return (
        str(row.get("fundId")) == fund_id
        and str(row.get("reportYear")) == str(year)
        and str(row.get("reportCode")) == report_code
        and str(row.get("reportDesp")) == report_desp
        and str(row.get("tableName")) == "PDF"
        and "摘要" not in report_name
        and row.get("uploadInfoId") is not None
    )


def _normalize_fund_code(code: str) -> str:
    return code.strip().zfill(6)


def _safe_filename(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\s]+", "_", value.strip())
    return value.strip("._") or "unknown"


def _url(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _pdf_url(instance_id: str) -> str:
    return _url(PDF_PATH) + "?" + urllib.parse.urlencode({"instanceid": instance_id})


def _request_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    timeout: float = 25,
    retries: int = 3,
) -> Any:
    raw = _request_bytes(url, params=params, data=data, timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8"))


def _request_bytes(
    url: str,
    *,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    timeout: float = 60,
    retries: int = 3,
) -> bytes:
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)
    encoded_data = urllib.parse.urlencode(data).encode("utf-8") if data else None
    request = urllib.request.Request(url, data=encoded_data, headers=HEADERS)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise urllib.error.HTTPError(url, response.status, "unexpected HTTP status", response.headers, None)
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * attempt)
    raise EidDownloadError(
        f"请求失败 ({retries} 次重试后): {url}: {last_error}",
        code="unavailable",
    )


def _looks_like_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF-")
