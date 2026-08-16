"""快照数据确定性抽取（§6.25 裁决 7/8/9）。

季报/半年报单期快照的受控抽取：
- 只覆盖真实存在字段（净值增长率各阶段行 + ①-③、期末规模/份额、仓位、前十大
  （季报）/全部持仓+重大变动（半年报）、行业配置、基金经理、份额变动、固有资金；
  半年报加财务三表关键科目「未经审计」）。
- 季报缺失项（全部持仓/财务三表/托管人报告）必须 fail-closed 声明，不从年报补。
- 份额默认 A 类优先；share_class 显式限定；无法明确记 None，不从文件名猜测。

本模块经 FundDocumentToolService（public reading tools）读取已导入 store，
不直接消费 raw PDF / Docling JSON / 本地路径。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from fund_agent.fund.document_tools.constants import FailureCode
from fund_agent.fund.document_tools.errors import DocumentToolError
from fund_agent.fund.document_tools.service import FundDocumentToolService
from fund_agent.service.report_template import (
    QUARTERLY_SNAPSHOT_TEMPLATE_ID,
    SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
)

_PERFORMANCE_HEADER_SIGNATURE = ("阶段", "净值增长率", "业绩比较基准收益率")
_PERFORMANCE_SECTION_QUERY = "基金份额净值增长率及其与同期业绩比较基准收益率的比较"
_SCALE_QUERIES = ("期末基金资产净值", "期末基金份额总额", "基金份额净值")
_HOLDINGS_QUERY_QUARTERLY = "前十名股票投资明细"
_HOLDINGS_QUERY_SEMIANNUAL = "股票投资明细"
_ALLOCATION_QUERY = "期末基金资产组合情况"
_ALLOCATION_TABLE_QUERY = "占基金总资产"
_MANAGER_QUERY = "基金经理"
_SHARE_CHANGE_QUERY = "份额变动"
_OWN_FUNDS_QUERY = "固有资金"
_FINANCIAL_QUERY = "主要财务指标"
_HOLDER_QUERY = "持有人"
_OPERATION_QUERY = "运作分析"
_SINGLE_INVESTOR_QUERY = "单一投资者"
_RISK_NOTES_QUERY = "风险提示"

# 季报缺失项（fail-closed 声明，不从年报补）
_QUARTERLY_MISSING_ITEMS = (
    "全部持仓明细不在季报披露范围（仅披露前十大）",
    "完整财务报表不在季报披露范围（仅披露主要指标）",
    "托管人报告不在季报披露范围",
    "持有人结构不在季报披露范围",
    "换手率（累计买入/卖出）不在季报披露范围",
    "市场展望不在季报披露范围",
)


@dataclass(frozen=True)
class SnapshotPerformanceRow:
    """当期净值增长率单阶段行（3.2.1 表，滚动窗口口径）。"""

    stage: str
    nav_growth_rate: str
    benchmark_return_rate: str
    excess_return: str = ""


@dataclass(frozen=True)
class SnapshotReportData:
    """单期快照抽取结果（供快照报告数据表格与评分消费）。"""

    fund_code: str
    fund_name: str
    report_year: int
    template_id: str
    quarter: int | None = None
    period: str | None = None
    performance_rows: tuple[SnapshotPerformanceRow, ...] = ()
    scale_info: dict[str, str] = field(default_factory=dict)
    holdings_rows: tuple[dict[str, str], ...] = ()
    allocation_rows: tuple[dict[str, str], ...] = ()
    industry_rows: tuple[dict[str, str], ...] = ()
    share_change: dict[str, str] = field(default_factory=dict)
    fund_manager: dict[str, str] = field(default_factory=dict)
    own_funds: str = ""
    operation_analysis: str = ""
    financial_rows: tuple[dict[str, str], ...] = ()
    holder_structure: dict[str, str] = field(default_factory=dict)
    single_investor_20pct: str = ""
    risk_notes: str = ""
    missing_items: tuple[str, ...] = ()
    latest_performance: dict[str, str] = field(default_factory=dict)
    citations: tuple[dict[str, str], ...] = ()

    def to_context_dict(self) -> dict[str, object]:
        """转换为 snapshot_generator 消费的上下文 dict。"""

        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "report_year": self.report_year,
            "template_id": self.template_id,
            "quarter": self.quarter,
            "period": self.period,
            "performance_rows": [
                {
                    "stage": r.stage,
                    "nav_growth_rate": r.nav_growth_rate,
                    "benchmark_return_rate": r.benchmark_return_rate,
                    "excess_return": r.excess_return,
                }
                for r in self.performance_rows
            ],
            "scale_info": dict(self.scale_info),
            "holdings_rows": [dict(r) for r in self.holdings_rows],
            "allocation_rows": [dict(r) for r in self.allocation_rows],
            "industry_rows": [dict(r) for r in self.industry_rows],
            "share_change": dict(self.share_change),
            "fund_manager": dict(self.fund_manager),
            "own_funds": self.own_funds,
            "operation_analysis": self.operation_analysis,
            "financial_rows": [dict(r) for r in self.financial_rows],
            "holder_structure": dict(self.holder_structure),
            "single_investor_20pct": self.single_investor_20pct,
            "risk_notes": self.risk_notes,
            "missing_items": list(self.missing_items),
            "latest_performance": dict(self.latest_performance),
            "citations": [dict(c) for c in self.citations],
        }


def extract_snapshot_data(
    *,
    document_id: str,
    store: object,
    fund_code: str,
    fund_name: str,
    report_year: int,
    template_id: str,
    quarter: int | None = None,
    period: str | None = None,
) -> SnapshotReportData:
    """从已导入 store 抽取单期快照数据。

    参数:
        document_id: public reading tools 内容身份。
        store: 已完成 parser health 的 DoclingDocumentStore。
        fund_code / fund_name / report_year: 报告身份。
        template_id: quarterly_snapshot / semiannual_snapshot。
        quarter: 季报期次（quarterly 使用）。
        period: 半年报期次（semiannual 使用，H1）。

    返回:
        SnapshotReportData；缺数据字段以「缺失」占位，季报缺失项 fail-closed 声明。

    异常:
        DocumentToolError: store 读取失败时透传稳定失败分类。
    """

    tool_service = FundDocumentToolService({document_id: store})

    performance_rows = _extract_performance_rows(tool_service, document_id)
    scale_info = _extract_scale_info(tool_service, document_id)
    holdings_rows = _extract_holdings_rows(tool_service, document_id, template_id)
    allocation_rows = _extract_allocation_rows(tool_service, document_id)
    industry_rows = _extract_industry_rows(tool_service, document_id)
    share_change = _extract_share_change(tool_service, document_id)
    fund_manager = _extract_fund_manager(tool_service, document_id)
    own_funds = _extract_text_field(tool_service, document_id, _OWN_FUNDS_QUERY, "固有资金")
    operation_analysis = _extract_text_field(tool_service, document_id, _OPERATION_QUERY, "运作分析")
    single_investor = _extract_text_field(tool_service, document_id, _SINGLE_INVESTOR_QUERY, "单一投资者")
    risk_notes_text = _extract_text_field(tool_service, document_id, _RISK_NOTES_QUERY, "风险提示")

    financial_rows: tuple[dict[str, str], ...] = ()
    holder_structure: dict[str, str] = {}
    if template_id == SEMIANNUAL_SNAPSHOT_TEMPLATE_ID:
        financial_rows = _extract_financial_rows(tool_service, document_id)
        holder_structure = _extract_holder_structure(tool_service, document_id)

    missing_items = _QUARTERLY_MISSING_ITEMS if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID else ()

    # A 类优先一致性（§6.25 裁决 8）：概览期末份额与份额变动表同源。
    # 基金资料表「报告期末基金份额总额」为 A+C 合计，份额变动表「报告期期末
    # 基金份额总额」首列为 A 类值；两者并存时以份额变动表 A 类为准，
    # 避免概览（合计）与份额变动（A 类）显示不一致。
    ending = share_change.get("ending_shares")
    if ending and ending != "缺失" and scale_info.get("shares"):
        scale_info["shares"] = f"{ending} 份"

    latest_performance: dict[str, str] = {}
    if performance_rows:
        # 概览用「过去一年」行（如存在）；否则取第一行
        one_year = next((r for r in performance_rows if "一年" in r.stage), performance_rows[0])
        latest_performance = {
            "nav_growth_rate": one_year.nav_growth_rate,
            "benchmark_return_rate": one_year.benchmark_return_rate,
            "excess_return": one_year.excess_return,
        }

    return SnapshotReportData(
        fund_code=fund_code,
        fund_name=fund_name,
        report_year=report_year,
        template_id=template_id,
        quarter=quarter,
        period=period,
        performance_rows=performance_rows,
        scale_info=scale_info,
        holdings_rows=holdings_rows,
        allocation_rows=allocation_rows,
        industry_rows=industry_rows,
        share_change=share_change,
        fund_manager=fund_manager,
        own_funds=own_funds,
        operation_analysis=operation_analysis,
        financial_rows=financial_rows,
        holder_structure=holder_structure,
        single_investor_20pct=single_investor,
        risk_notes=risk_notes_text,
        missing_items=missing_items,
        latest_performance=latest_performance,
    )


def _normalized_cells(rows: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
    """去空白归一化表格行。"""

    return tuple(tuple(str(cell).replace(" ", "").replace("\u3000", "") for cell in row) for row in rows)


def _is_performance_header(header: tuple[str, ...]) -> bool:
    """判断表头是否命中 3.2.1 业绩比较表签名（阶段/净值增长率/业绩比较基准收益率）。"""

    return (
        all(any(sig in cell for cell in header) for sig in _PERFORMANCE_HEADER_SIGNATURE)
        and _index_of_containing(header, "阶段") is not None
        and _index_of_containing(header, "净值增长率") is not None
        and _index_of_containing(header, "业绩比较基准收益率") is not None
    )


def _find_performance_tables(tool_service: FundDocumentToolService, document_id: str) -> list[object]:
    """定位 3.2.1 业绩比较表集合（表头签名 + A 类标题优先 + 续页合并）。

    返回按 docling 顺序排列的表内容列表：首个为 A 类主表（表头签名命中且
    标题含 A 排除 C；无 A/C 标题时取首个命中表），其后可能追加同表的续页
    （表头缺失但首行即阶段行的跨页拆分，实证：005680-2025 半年报 A 类
    3.2.1 拆成 table-0010（表头+两个月/三个月）与 table-0011（无表头续页））。

    参数:
        tool_service: FundDocumentToolService 实例。
        document_id: 文档内容身份。

    返回:
        表内容对象列表（无命中时为空列表）。
    """

    listed = tool_service.list_tables(document_id)
    if isinstance(listed, object) and not isinstance(listed, tuple):
        return []
    candidates: list[tuple[object, object]] = []
    continuation: list[tuple[object, object]] = []
    for table in listed or ():
        if not hasattr(table, "table_ref"):
            continue
        content = tool_service.read_table(document_id, table.table_ref)
        if isinstance(content, object) and not hasattr(content, "rows"):
            continue
        rows = _normalized_cells(content.rows)
        if not rows:
            continue
        if _is_performance_header(rows[0]):
            candidates.append((table, content))
        elif _looks_like_stage(str(rows[0][0]).strip()) and _has_stage_rows(rows):
            # 无表头续页：首行即为阶段行（跨页拆分的 3.2.1 表）
            continuation.append((table, content))
    if not candidates:
        return []
    # A 类标题优先（含 A 排除 C）
    a_class = [c for c in candidates if _table_caption_mentions_a(c[0])]
    chosen = a_class[0] if a_class else candidates[0]
    # 合并：A 类主表 + 全部续页（按 docling 顺序，阶段去重保 A 类值）
    ordered: list[object] = [chosen[1]]
    for _, cont in continuation:
        if cont in ordered:
            continue
        ordered.append(cont)
    return ordered


def _has_stage_rows(rows: tuple[tuple[str, ...], ...]) -> bool:
    """判断表格数据行是否含阶段行（防把无关表当续页）。"""

    return any(len(row) > 1 and _looks_like_stage(str(row[0]).strip()) for row in rows[1:])


def _table_caption_mentions_a(table: object) -> bool:
    """判断表格 caption/标题是否提及 A 类（含 A 排除 C）。"""

    caption = str(getattr(table, "caption", "") or "")
    return "A" in caption and "C" not in caption


def _extract_performance_rows(tool_service: FundDocumentToolService, document_id: str) -> tuple[SnapshotPerformanceRow, ...]:
    """从 3.2.1 表抽取各阶段行 + ①-③（行标签精确匹配，禁止假设固定窗口集合）。

    支持跨页拆分合并（A 类主表 + 无表头续页），阶段行按 docling 顺序去重，
    保持 A 类优先（实证：005680-2025 半年报 A 类 3.2.1 拆两张表）。
    """

    tables = _find_performance_tables(tool_service, document_id)
    if not tables:
        return ()
    # 列匹配以首个表头命中表为准（净值增长率/基准收益率排除标准差列、①-③）
    main_rows = _normalized_cells(tables[0].rows)
    if not main_rows:
        return ()
    header = main_rows[0]
    nav_idx = _first_non_stddev_index(header, "净值增长率")
    bench_idx = _first_non_stddev_index(header, "业绩比较基准收益率")
    excess_idx = _index_of_containing(header, "①-③")
    if excess_idx is None:
        # 半年报/季报部分报告只有两列时，从原始表头找「超额」
        excess_idx = _index_of_containing(header, "超额")
    if nav_idx is None or bench_idx is None:
        return ()

    results: list[SnapshotPerformanceRow] = []
    seen_stages: set[str] = set()
    for table_idx, table in enumerate(tables):
        rows = _normalized_cells(table.rows)
        # 主表首行为表头需跳过；无表头续页首行即为阶段行（实证：跨页拆分后
        # 续页直接从「过去五年/过去六个月」开始，跳过会丢行）
        data_rows = rows[1:] if table_idx == 0 else rows
        for row in data_rows:
            stage = str(row[0]).strip()
            if not stage or "阶段" in stage or not _looks_like_stage(stage):
                continue
            if stage in seen_stages:
                # 同阶段重复（A/C 双份额表）：保留先出现的 A 类值
                continue
            seen_stages.add(stage)
            nav = row[nav_idx] if nav_idx < len(row) else "缺失"
            bench = row[bench_idx] if bench_idx < len(row) else "缺失"
            excess = row[excess_idx] if excess_idx is not None and excess_idx < len(row) else "缺失"
            results.append(SnapshotPerformanceRow(
                stage=stage,
                nav_growth_rate=nav or "缺失",
                benchmark_return_rate=bench or "缺失",
                excess_return=excess or "缺失",
            ))
    return tuple(results)


def _looks_like_stage(stage: str) -> bool:
    """判断是否为净值增长率阶段行（过去/近/自成立/自基金合同生效起至今等）。"""

    return any(kw in stage for kw in (
        "过去", "近", "今年以来", "自成立", "自基金合同生效", "生效起至今", "至今",
        "本月以来", "本季以来", "当年",
    ))


def _index_of_containing(row: tuple[str, ...], keyword: str) -> int | None:
    """返回行中第一个包含关键词的列索引。"""

    for idx, cell in enumerate(row):
        if keyword in cell:
            return idx
    return None


def _first_non_stddev_index(row: tuple[str, ...], keyword: str) -> int | None:
    """返回行中第一个包含关键词但不含「标准差」的列索引（避免命中标准差列）。"""

    for idx, cell in enumerate(row):
        if keyword in cell and "标准差" not in cell:
            return idx
    return None


def _extract_scale_info(tool_service: FundDocumentToolService, document_id: str) -> dict[str, str]:
    """抽取期末规模/份额（遍历 search 命中直至抽到数据）。

    期末基金资产净值锚定「期末基金资产净值」标签后的首个数字（A 类优先，
    实证：季报/半年报表格该列无「元」后缀，旧正则误把「基金份额净值 X.XXXX 元」
    当规模）。份额同样按标签锚定，避免与业绩表/份额变动表数值混淆。
    """

    result: dict[str, str] = {}
    for query in _SCALE_QUERIES:
        for text in _search_texts(tool_service, document_id, query):
            if not text:
                continue
            # aum：仅接受「期末基金资产净值」标签后的数字（元/亿元后缀或裸数字）
            aum = _search_pattern(text, r"期末基金资产净值[^\d]{0,12}(\d[\d,，.]*(?:\.\d+)?)")
            if aum and "aum" not in result:
                result["aum"] = f"{aum} 元"
            # shares：仅接受「期末基金份额总额/基金份额总额」标签后的份额数
            shares = _search_pattern(text, r"(?:期末)?基金份额总额[^\d]{0,12}(\d[\d,，.]*(?:\.\d+)?)")
            if shares and "shares" not in result:
                result["shares"] = f"{shares} 份"
            if "nav" not in result:
                nav = _search_pattern(text, r"净值\s*[^\d]{0,6}(\d+\.\d{4})")
                if nav:
                    result["nav"] = nav
            if result.get("aum") and result.get("shares"):
                return result
    if not result:
        result = {"aum": "缺失", "shares": "缺失"}
    return result


def _extract_holdings_rows(
    tool_service: FundDocumentToolService,
    document_id: str,
    template_id: str,
) -> tuple[dict[str, str], ...]:
    """抽取持仓（季报前十大 / 半年报全部持仓）。"""

    query = _HOLDINGS_QUERY_QUARTERLY if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID else _HOLDINGS_QUERY_SEMIANNUAL
    # 先按「股票名称」定位持仓表（实证：section 命中无 table_ref，需表头签名匹配）
    tables = _search_tables(tool_service, document_id, "股票名称")
    if not tables:
        tables = _search_tables(tool_service, document_id, query)
    for table in tables:
        rows = _normalized_cells(table.rows)
        if not rows:
            continue
        header = rows[0]
        name_idx = _index_of_containing(header, "股票名称") or _index_of_containing(header, "名称")
        value_idx = _index_of_containing(header, "公允价值")
        ratio_idx = _index_of_containing(header, "占基金资产净值比例") or _index_of_containing(header, "净值比例")
        if name_idx is None:
            continue
        result: list[dict[str, str]] = []
        for row in rows[1:]:
            if len(row) <= name_idx:
                continue
            result.append({
                "stock_name": str(row[name_idx]),
                "fair_value": str(row[value_idx]) if value_idx is not None and value_idx < len(row) else "缺失",
                "ratio": str(row[ratio_idx]) if ratio_idx is not None and ratio_idx < len(row) else "缺失",
            })
            if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID and len(result) >= 10:
                break
        if result:
            return tuple(result)
    return ()


def _extract_allocation_rows(tool_service: FundDocumentToolService, document_id: str) -> tuple[dict[str, str], ...]:
    """抽取资产配置/仓位。"""

    tables = _search_tables(tool_service, document_id, _ALLOCATION_TABLE_QUERY)
    if not tables:
        tables = _search_tables(tool_service, document_id, _ALLOCATION_QUERY)
    for table in tables:
        rows = _normalized_cells(table.rows)
        if not rows:
            continue
        header = rows[0]
        category_idx = _index_of_containing(header, "项目") or _index_of_containing(header, "类别")
        ratio_idx = _index_of_containing(header, "占基金资产") or _index_of_containing(header, "比例")
        if category_idx is None:
            continue
        result: list[dict[str, str]] = []
        for row in rows[1:]:
            if len(row) <= category_idx:
                continue
            category = str(row[category_idx]).strip()
            if not category or "合计" in category:
                continue
            result.append({
                "asset_class": category,
                "ratio": str(row[ratio_idx]) if ratio_idx is not None and ratio_idx < len(row) else "缺失",
            })
        if result:
            return tuple(result)
    return ()


def _extract_industry_rows(tool_service: FundDocumentToolService, document_id: str) -> tuple[dict[str, str], ...]:
    """抽取行业配置。"""

    tables = _search_tables(tool_service, document_id, "行业分类")
    for table in tables:
        rows = _normalized_cells(table.rows)
        if not rows:
            continue
        header = rows[0]
        industry_idx = _index_of_containing(header, "行业") or _index_of_containing(header, "类别")
        ratio_idx = _index_of_containing(header, "占基金资产净值比例") or _index_of_containing(header, "比例")
        if industry_idx is None:
            continue
        result: list[dict[str, str]] = []
        for row in rows[1:]:
            if len(row) <= industry_idx:
                continue
            industry = str(row[industry_idx]).strip()
            if not industry or "合计" in industry:
                continue
            result.append({
                "industry": industry,
                "ratio": str(row[ratio_idx]) if ratio_idx is not None and ratio_idx < len(row) else "缺失",
            })
        if result:
            return tuple(result)
    return ()


def _extract_share_change(tool_service: FundDocumentToolService, document_id: str) -> dict[str, str]:
    """抽取份额变动（期初/申购/赎回/期末；A 类优先）。

    季报 §6 标签为「期初基金份额总额/本期基金总申购份额/本期基金总赎回份额/
    期末基金份额总额」；半年报 §9 标签为「本报告期期初基金份额总额/本报告期
    基金总申购份额/减：本报告期基金总赎回份额/本报告期期末基金份额总额」。
    Docling section 归属可能错位，「份额变动」query 可能只命中目录与相邻表
    （实证 005680-2025 半年报：真实表为 table-0075，需「期初基金份额总额」
    查询才命中），故扩大查询集合并做标签归一化。
    """

    # 扫描全部表格找份额变动表（实证 caption「单位：份」，Docling section 归属可能错位；
    # 「份额变动」可能只命中目录与相邻表，真实表需「期初基金份额总额」命中，
    # 故累积全部查询结果去重后统一甄别，不因首个查询非空而短路）
    tables = _collect_tables(tool_service, document_id, (
        "份额变动",
        "期初基金份额总额",
        "开放式基金份额变动",
        "单位：份",
    ))
    for table in tables:
        rows = _normalized_cells(table.rows)
        if not rows:
            continue
        labels = [str(row[0]).strip() for row in rows if row]
        if not any("期初" in label and "份额" in label for label in labels):
            continue
        result: dict[str, str] = {}
        for row in rows:
            if not row:
                continue
            label = str(row[0]).strip()
            # 归一化「减：本报告期基金总赎回份额」等前缀（值本身为正数，取原文）
            a_value = str(row[1]) if len(row) > 1 else ""
            if "期初" in label and "期初" not in result:
                result["beginning_shares"] = a_value or "缺失"
            elif "申购" in label and "subscriptions" not in result:
                result["subscriptions"] = a_value or "缺失"
            elif "赎回" in label and "redemptions" not in result:
                result["redemptions"] = a_value or "缺失"
            elif "期末" in label and "期末" not in result:
                result["ending_shares"] = a_value or "缺失"
        if result:
            return result

    result: dict[str, str] = {}
    for text in _search_texts(tool_service, document_id, _SHARE_CHANGE_QUERY):
        if not text:
            continue
        patterns = {
            "beginning_shares": r"(?:本报告期|报告期)?期初\s*基金份额总额[^\d]{0,8}(\d[\d,，.]*(?:\.\d+)?)",
            "subscriptions": r"(?:本报告期)?基金总申购份额[^\d]{0,8}(\d[\d,，.]*(?:\.\d+)?)",
            "redemptions": r"(?:减[:：]?\s*)?(?:本报告期)?基金总赎回份额[^\d]{0,8}(\d[\d,，.]*(?:\.\d+)?)",
            "ending_shares": r"(?:本报告期|报告期)?期末\s*基金份额总额[^\d]{0,8}(\d[\d,，.]*(?:\.\d+)?)",
        }
        for key, pattern in patterns.items():
            if key in result:
                continue
            match = re.search(pattern, text)
            if match:
                result[key] = match.group(1)
    if not result:
        result = {"ending_shares": "缺失"}
    return result


def _extract_fund_manager(tool_service: FundDocumentToolService, document_id: str) -> dict[str, str]:
    """抽取基金经理信息。

    优先从 4.1 基金经理简介表读「姓名」列；再匹配「聘任X为本基金基金经理」结构
    （实证：「2025年7月15日聘任李响为本基金基金经理」）；并排除指代词
    （上述/现任/历任/本基金/本报告）避免 4.1.2 节「上述任职日期」误抽取。
    """

    result: dict[str, str] = {}
    # 1. 4.1 基金经理简介表（姓名列）
    tables = _search_tables(tool_service, document_id, "基金经理（或基金经理小组）简介")
    for table in tables:
        rows = _normalized_cells(table.rows)
        if not rows:
            continue
        header = rows[0]
        name_idx = _index_of_containing(header, "姓名")
        if name_idx is None:
            continue
        for row in rows[1:]:
            if len(row) <= name_idx:
                continue
            name = str(row[name_idx]).strip()
            if name and name not in ("上述", "现任", "历任", "本基金", "本报告"):
                result["name"] = name
                return result
    # 2. 文本路径（聘任结构 + 通用 + 基金经理前缀）
    for text in _search_texts(tool_service, document_id, _MANAGER_QUERY):
        if not text:
            continue
        name = _search_pattern(text, r"聘任([\u4e00-\u9fa5]{2,4})(?:先生|女士)?(?:担任|为|为本基金基金经理)")
        if not name:
            name = _search_pattern(text, r"([\u4e00-\u9fa5]{2,4})(?:先生|女士)?(?:担任|任职)")
        if not name:
            name = _search_pattern(text, r"基金经理\s*[:：]?\s*([\u4e00-\u9fa5]{2,4})")
        if name and name not in ("上述", "现任", "历任", "本基金", "本报告"):
            result["name"] = name
            break
    if not result:
        result = {"name": "缺失"}
    return result


def _extract_financial_rows(tool_service: FundDocumentToolService, document_id: str) -> tuple[dict[str, str], ...]:
    """抽取主要财务指标（半年报，未经审计）。

    「主要财务指标」query 可能命中目录表（实证 005680-2025 半年报 TOC 行
    「§3主要财务指标和基金净值表现......6」），必须先过滤目录表并按指标行
    特征（本期/期末/利润/净值等）甄别；真实 3.1 表列结构为 指标|A类|C类
    （无上期列），单期快照无上期可比，previous 标「—」。
    """

    queries = ("主要会计数据和财务指标", _FINANCIAL_QUERY, "基金份额累计净值增长率", "加权平均基金份额本期利润")
    seen_tables: set[str] = set()
    for query in queries:
        for table in _search_tables(tool_service, document_id, query):
            rows = _normalized_cells(table.rows)
            if not rows or len(rows) < 2:
                continue
            # 目录表过滤：首列含点线引导符（....）+ 页码，或首列是章节编号目录项
            first_col = [str(row[0]).strip() for row in rows if row]
            if any(re.search(r"[.．]{3,}\d+\s*$", cell) or (re.match(r"^[§\d]", cell) and "......" in cell) for cell in first_col):
                continue
            # 指标行特征：含 本期/期末/利润/净值增长率/已实现 等财务指标关键词
            if not any(kw in cell for cell in first_col for kw in ("本期", "期末", "利润", "已实现", "净值", "收益率", "加权")):
                continue
            result: list[dict[str, str]] = []
            for row in rows[1:]:
                if not row or not str(row[0]).strip():
                    continue
                # 跳过「3.1.2 期末数据和指标」「报告期末(...)」这类小节行
                item = str(row[0]).strip()
                if re.match(r"^3\.1\.\d", item) or "报告期末" in item or "报告期" in item and "指标" not in item:
                    continue
                current = str(row[1]) if len(row) > 1 else "缺失"
                # 半年报 3.1 表列为 指标|A类|C类：A 类优先（row[1]），
                # 单期快照无上期可比，previous 恒为「—」（不臆造上期值）
                result.append({
                    "item": item,
                    "current": current,
                    "previous": "—",
                })
            if result:
                return tuple(result)
    return ()


def _extract_holder_structure(tool_service: FundDocumentToolService, document_id: str) -> dict[str, str]:
    """抽取持有人结构（半年报 §8.1；A 类优先）。

    8.1 表列为 名称|持有人户数|户均持有份额|机构持有份额|机构占比|个人持有份额|
    个人占比（实证 005680-2025 半年报 table-0070，Docling 单元格含空格噪声）。
    文本 query 首命中是节标题（无「户」字），必须走表格路径。
    """

    tables = _collect_tables(tool_service, document_id, (
        "期末基金份额持有人户数及持有人结构",
        "持有人结构",
        _HOLDER_QUERY,
    ))
    for table in tables:
        rows = _normalized_cells(table.rows)
        if not rows:
            continue
        a_row: list[str] | None = None
        first_data: list[str] | None = None
        for row in rows:
            if not row or not str(row[0]).strip():
                continue
            first = str(row[0]).strip()
            if "份额" in first and "级别" in first:
                continue  # 表头行
            if "合计" in first or "户均" in first:
                continue
            if first_data is None:
                first_data = row
            if "A" in first and "C" not in first and any(ch.isdigit() for ch in "".join(str(c) for c in row)):
                a_row = row
        chosen = a_row or first_data
        if chosen is None or len(chosen) < 5:
            continue
        # 列位：名称|户数|户均份额|机构份额|机构占比|个人份额|个人占比
        count = str(chosen[1]).strip() if len(chosen) > 1 else ""
        institutional = str(chosen[4]).strip() if len(chosen) > 4 else ""
        individual = str(chosen[6]).strip() if len(chosen) > 6 else ""
        result: dict[str, str] = {}
        if count:
            result["holder_count"] = f"{count} 户"
        if institutional and "%" in institutional:
            result["institutional_ratio"] = institutional
        if individual and "%" in individual:
            result["individual_ratio"] = individual
        if result:
            return result

    # 文本兜底（无 8.1 表时）
    text = _search_first_text(tool_service, document_id, "持有人户数")
    result = {}
    if text:
        count = _search_pattern(text, r"(\d[\d,，.]*\s*户)")
        institutional = _search_pattern(text, r"机构投资者[^\d]*(\d+\.?\d*\s*%)")
        individual = _search_pattern(text, r"个人投资者[^\d]*(\d+\.?\d*\s*%)")
        if count:
            result["holder_count"] = count
        if institutional:
            result["institutional_ratio"] = institutional
        if individual:
            result["individual_ratio"] = individual
    if not result:
        result = {"holder_count": "缺失"}
    return result


def _extract_text_field(tool_service: FundDocumentToolService, document_id: str, query: str, label: str) -> str:
    """抽取单字段文本（search 首命中片段）。"""

    text = _search_first_text(tool_service, document_id, query)
    if not text:
        return f"（{label}未披露）"
    return text[:200]


def _search_first_text(tool_service: FundDocumentToolService, document_id: str, query: str) -> str:
    """search 首个命中摘要。"""

    results = tool_service.search_document(document_id, query)
    if isinstance(results, tuple) and results:
        return str(results[0].excerpt or "")
    return ""


def _search_texts(tool_service: FundDocumentToolService, document_id: str, query: str) -> tuple[str, ...]:
    """search 全部命中摘要（前 5 条，供字段抽取遍历直至抽到数据）。"""

    results = tool_service.search_document(document_id, query)
    if not isinstance(results, tuple):
        return ()
    return tuple(str(r.excerpt or "") for r in results[:5] if getattr(r, "excerpt", None))


def _search_tables(tool_service: FundDocumentToolService, document_id: str, query: str) -> list[object]:
    """search 命中的表格内容列表（含 section 命中时其内部的表格）。"""

    results = tool_service.search_document(document_id, query)
    if not isinstance(results, tuple):
        return []
    tables: list[object] = []
    seen: set[str] = set()
    for result in results:
        table_ref = getattr(result, "table_ref", None)
        if table_ref:
            if table_ref in seen:
                continue
            seen.add(table_ref)
            table = tool_service.read_table(document_id, table_ref, max_rows=50)
            if hasattr(table, "rows"):
                tables.append(table)
        section_ref = getattr(result, "section_ref", None)
        if section_ref:
            # section 命中：列出其内部表格（实证 Docling caption 可能错位，表格仍可取）
            listed = tool_service.list_tables(document_id, within_section_ref=section_ref)
            if isinstance(listed, tuple):
                for summary in listed:
                    tref = getattr(summary, "table_ref", None)
                    if not tref or tref in seen:
                        continue
                    seen.add(tref)
                    table = tool_service.read_table(document_id, tref, max_rows=50)
                    if hasattr(table, "rows"):
                        tables.append(table)
    return tables


def _collect_tables(
    tool_service: FundDocumentToolService,
    document_id: str,
    queries: tuple[str, ...],
) -> list[object]:
    """跨多个查询累积表格并去重（按 table_ref）。

    单查询可能只命中目录/相邻表，而真实数据表需另一查询词命中
    （实证：005680-2025 半年报份额变动真实表 table-0075 仅
    「期初基金份额总额」命中）；累积后统一由调用方甄别。

    参数:
        tool_service: FundDocumentToolService 实例。
        document_id: 文档内容身份。
        queries: 查询词集合。

    返回:
        去重后的表内容对象列表。
    """

    seen: set[str] = set()
    tables: list[object] = []
    for query in queries:
        for table in _search_tables(tool_service, document_id, query):
            table_ref = getattr(table, "table_ref", "")
            if table_ref in seen:
                continue
            seen.add(table_ref)
            tables.append(table)
    return tables


def _search_pattern(text: str, pattern: str) -> str:
    """在文本中搜索首个正则命中。"""

    match = re.search(pattern, text)
    return match.group(1) if match else ""
