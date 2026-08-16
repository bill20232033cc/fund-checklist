"""快照报告数据表格与模板降级章节生成（§6.25 裁决 4/5/7）。

季报 5 章 / 半年报 6 章的程序化数据表格与 LLM 失败时的模板降级章节。
数据来自 Slice D 的受控抽取（quarterly_performance / semiannual_performance profile），
以 snapshot_data 上下文 dict 传入（见 extract_snapshot_data 契约）。

本模块只做数据表格渲染与模板降级，不做抽取，不依赖 LLM。
"""
from __future__ import annotations

from fund_agent.service.report_template import (
    QUARTERLY_SNAPSHOT_TEMPLATE_ID,
    SEMIANNUAL_SNAPSHOT_TEMPLATE_ID,
)


def _period_label(
    template_id: str,
    report_year: int,
    quarter: int | None = None,
    period: str | None = None,
) -> str:
    """返回报告期口径标签（如「2026 年二季度」/「2025 年上半年」）。

    quarter 为 None 时不得输出「QNone」占位（历史缺陷：LLM 路径未透传期次），
    显式降级为「报告期缺失」并保留年份。period 映射半年报期次（H1/H2），
    未知值默认「上半年」。
    """

    if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID:
        if quarter is None:
            return f"{report_year} 年（报告期季度缺失）"
        quarter_names = {1: "一季度", 2: "二季度", 3: "三季度", 4: "四季度"}
        return f"{report_year} 年{quarter_names.get(quarter, f'Q{quarter}')}"
    half_map = {"H1": "上半年", "H2": "下半年"}
    return f"{report_year} 年{half_map.get(period, '上半年')}"


def _snapshot_common_header(
    *,
    fund_code: str,
    fund_name: str,
    report_year: int,
    template_id: str,
    quarter: int | None = None,
    period: str | None = None,
) -> str:
    """快照数据表公共头（基金信息 + 报告期口径）。"""

    return (
        "## 快照基本信息\n\n"
        f"- 基金代码：{fund_code}\n"
        f"- 基金名称：{fund_name}\n"
        f"- 报告期：{_period_label(template_id, report_year, quarter, period=period)}\n"
        f"- 报告类型：{'季报' if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID else '半年报'}\n"
    )


def _render_performance_table(snapshot_data: dict[str, object]) -> str:
    """渲染当期业绩与超额数据表（3.2.1 各阶段行 + ①-③）。"""

    rows = snapshot_data.get("performance_rows")
    if not isinstance(rows, list) or not rows:
        return "| 阶段 | 份额净值增长率 | 业绩比较基准收益率 | ①-③超额 |\n|------|--------------|------------------|---------|\n| （无数据） | - | - | - |\n"
    lines = ["| 阶段 | 份额净值增长率 | 业绩比较基准收益率 | 超额收益①-③ |", "|------|--------------|------------------|-------------|"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        stage = str(row.get("stage", ""))
        nav = str(row.get("nav_growth_rate", "缺失"))
        bench = str(row.get("benchmark_return_rate", "缺失"))
        excess = str(row.get("excess_return", "缺失"))
        lines.append(f"| {stage} | {nav} | {bench} | {excess} |")
    return "\n".join(lines) + "\n"


def _render_allocation_table(snapshot_data: dict[str, object]) -> str:
    """渲染资产配置/仓位数据表。"""

    rows = snapshot_data.get("allocation_rows")
    if not isinstance(rows, list) or not rows:
        return "| 资产类别 | 占基金资产比例 |\n|----------|--------------|\n| （无数据） | - |\n"
    lines = ["| 资产类别 | 占基金资产比例 |", "|----------|--------------|"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(f"| {row.get('asset_class', '')} | {row.get('ratio', '缺失')} |")
    return "\n".join(lines) + "\n"


def _render_holdings_table(snapshot_data: dict[str, object]) -> str:
    """渲染持仓数据表（季报前十大 / 半年报全部持仓）。"""

    rows = snapshot_data.get("holdings_rows")
    if not isinstance(rows, list) or not rows:
        return "| 序号 | 股票名称 | 公允价值 | 占基金资产净值比例 |\n|------|----------|----------|------------------|\n| （无数据） | - | - | - |\n"
    lines = ["| 序号 | 股票名称 | 公允价值 | 占基金资产净值比例 |", "|------|----------|----------|------------------|"]
    for idx, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {idx} | {row.get('stock_name', '')} | {row.get('fair_value', '缺失')} | {row.get('ratio', '缺失')} |"
        )
    return "\n".join(lines) + "\n"


def _render_share_change_table(snapshot_data: dict[str, object]) -> str:
    """渲染份额变动数据表。"""

    share = snapshot_data.get("share_change")
    if not isinstance(share, dict):
        return "| 份额变动 | 数值 |\n|----------|------|\n| （无数据） | - |\n"
    lines = ["| 份额变动 | 数值 |", "|----------|------|"]
    for key, label in (
        ("beginning_shares", "期初份额"),
        ("subscriptions", "本期申购"),
        ("redemptions", "本期赎回"),
        ("ending_shares", "期末份额"),
    ):
        lines.append(f"| {label} | {share.get(key, '缺失')} |")
    return "\n".join(lines) + "\n"


def _render_financial_table(snapshot_data: dict[str, object]) -> str:
    """渲染财务质量数据表（半年报：主要财务指标 + 三表关键科目，未经审计）。"""

    rows = snapshot_data.get("financial_rows")
    if not isinstance(rows, list) or not rows:
        return "| 财务科目 | 本期 | 上期 |\n|----------|------|------|\n| （无数据） | - | - |\n"
    lines = ["| 财务科目 | 本期 | 上期 |", "|----------|------|------|"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(f"| {row.get('item', '')} | {row.get('current', '缺失')} | {row.get('previous', '缺失')} |")
    return "\n".join(lines) + "\n"


def _render_holder_table(snapshot_data: dict[str, object]) -> str:
    """渲染持有人结构数据表（半年报）。"""

    holder = snapshot_data.get("holder_structure")
    if not isinstance(holder, dict):
        return "| 持有人结构 | 数值 |\n|------------|------|\n| （无数据） | - |\n"
    lines = ["| 持有人结构 | 数值 |", "|------------|------|"]
    for key, label in (
        ("holder_count", "持有人户数"),
        ("institutional_ratio", "机构投资者占比"),
        ("individual_ratio", "个人投资者占比"),
    ):
        lines.append(f"| {label} | {holder.get(key, '缺失')} |")
    return "\n".join(lines) + "\n"


def _render_missing_items(snapshot_data: dict[str, object]) -> str:
    """渲染 fail-closed 缺失项声明（季报缺失项 / 半年报缺失项）。"""

    missing = snapshot_data.get("missing_items")
    if not isinstance(missing, list) or not missing:
        return ""
    lines = ["**数据完整性声明**", ""]
    for item in missing:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def generate_snapshot_data_table(*, template_id: str, **kwargs: object) -> str:
    """生成快照章节数据表格。

    参数:
        template_id: 快照模板 id（quarterly_snapshot / semiannual_snapshot）。
        kwargs: chapter_id / fund_code / fund_name / report_year / quarter / period /
            snapshot_data（Slice D 抽取结果上下文）。

    返回:
        程序生成的数据表格 Markdown 文本。
    """

    chapter_id = int(kwargs["chapter_id"])
    fund_code = str(kwargs.get("fund_code", ""))
    fund_name = str(kwargs.get("fund_name", ""))
    report_year = int(kwargs.get("report_year", 0))
    quarter = kwargs.get("quarter")
    period = kwargs.get("period")
    snapshot_data = kwargs.get("snapshot_data")
    if not isinstance(snapshot_data, dict):
        snapshot_data = {}

    parts = [_snapshot_common_header(
        fund_code=fund_code,
        fund_name=fund_name,
        report_year=report_year,
        template_id=template_id,
        quarter=int(quarter) if quarter is not None else None,
        period=str(period) if period is not None else None,
    )]

    if chapter_id == 0:
        # 概览：期末规模/份额 + 当期净值表现 + 综合结论
        scale = snapshot_data.get("scale_info")
        latest = snapshot_data.get("latest_performance")
        parts.append("## 期末规模与份额\n")
        if isinstance(scale, dict):
            parts.append(f"- 期末规模：{scale.get('aum', '缺失')}\n- 期末份额：{scale.get('shares', '缺失')}\n")
        else:
            parts.append("- 期末规模：缺失\n- 期末份额：缺失\n")
        parts.append("## 当期净值表现（报告期口径）\n")
        if isinstance(latest, dict):
            parts.append(
                f"- 净值增长率：{latest.get('nav_growth_rate', '缺失')}\n"
                f"- 基准收益率：{latest.get('benchmark_return_rate', '缺失')}\n"
                f"- 超额收益：{latest.get('excess_return', '缺失')}\n"
            )
        else:
            parts.append("- 当期净值表现：缺失\n")
    elif chapter_id == 1:
        parts.append("## 当期业绩与超额（滚动窗口 ≠ 日历年度）\n")
        parts.append(_render_performance_table(snapshot_data))
    elif chapter_id == 2:
        parts.append("## 资产配置/仓位\n")
        parts.append(_render_allocation_table(snapshot_data))
        parts.append("## 行业配置\n")
        industry = snapshot_data.get("industry_rows")
        if isinstance(industry, list) and industry:
            lines = ["| 行业 | 占净值比例 |", "|------|----------|"]
            for row in industry:
                if isinstance(row, dict):
                    lines.append(f"| {row.get('industry', '')} | {row.get('ratio', '缺失')} |")
            parts.append("\n".join(lines) + "\n")
        else:
            parts.append("| 行业 | 占净值比例 |\n|------|----------|\n| （无数据） | - |\n")
        parts.append("## 持仓\n")
        parts.append(_render_holdings_table(snapshot_data))
        parts.append("## 份额变动\n")
        parts.append(_render_share_change_table(snapshot_data))
    elif chapter_id == 3:
        if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID:
            # 季报 Ch3 管理人动作
            manager = snapshot_data.get("fund_manager")
            parts.append("## 基金经理\n")
            if isinstance(manager, dict):
                parts.append(f"- 姓名：{manager.get('name', '缺失')}\n- 任职时间：{manager.get('tenure_start', '缺失')}\n")
            else:
                parts.append("- 基金经理：缺失\n")
            parts.append("## 运作分析（管理人报告 §4.4）\n")
            operation = snapshot_data.get("operation_analysis")
            parts.append(f"{operation if operation else '（无数据）'}\n")
            own_funds = snapshot_data.get("own_funds")
            parts.append("## 固有资金\n")
            parts.append(f"{own_funds if own_funds else '（未披露）'}\n")
        else:
            # 半年报 Ch3 财务质量
            parts.append("## 主要财务指标与三表关键科目（未经审计）\n")
            parts.append(_render_financial_table(snapshot_data))
    elif chapter_id == 4:
        if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID:
            # 季报 Ch4 风险与跟踪
            parts.append("## 风险提示\n")
            risk = snapshot_data.get("risk_notes")
            parts.append(f"{risk if risk else '（无数据）'}\n")
            single_investor = snapshot_data.get("single_investor_20pct")
            parts.append("## 单一投资者 ≥20%\n")
            parts.append(f"{single_investor if single_investor else '（未触发或未披露）'}\n")
            parts.append(_render_missing_items(snapshot_data))
        else:
            # 半年报 Ch4 管理人动作
            manager = snapshot_data.get("fund_manager")
            parts.append("## 基金经理\n")
            if isinstance(manager, dict):
                parts.append(f"- 姓名：{manager.get('name', '缺失')}\n- 任职时间：{manager.get('tenure_start', '缺失')}\n")
            else:
                parts.append("- 基金经理：缺失\n")
            parts.append("## 运作分析（管理人报告 §4.4）\n")
            operation = snapshot_data.get("operation_analysis")
            parts.append(f"{operation if operation else '（无数据）'}\n")
            parts.append("## 份额变动\n")
            parts.append(_render_share_change_table(snapshot_data))
            own_funds = snapshot_data.get("own_funds")
            parts.append("## 固有资金\n")
            parts.append(f"{own_funds if own_funds else '（未披露）'}\n")
    elif chapter_id == 5:
        # 半年报 Ch5 风险与持有人
        parts.append("## 持有人结构\n")
        parts.append(_render_holder_table(snapshot_data))
        parts.append("## 风险提示\n")
        risk = snapshot_data.get("risk_notes")
        parts.append(f"{risk if risk else '（无数据）'}\n")
        single_investor = snapshot_data.get("single_investor_20pct")
        parts.append("## 单一投资者 ≥20%\n")
        parts.append(f"{single_investor if single_investor else '（未触发或未披露）'}\n")
        parts.append(_render_missing_items(snapshot_data))
    else:
        parts.append("（未知章节）\n")

    return "\n".join(parts)


def generate_snapshot_template_chapter(*, template_id: str, **kwargs: object) -> str:
    """生成快照模板降级章节（LLM 失败 fallback）。

    参数:
        template_id: 快照模板 id。
        kwargs: chapter_id / fund_name / report_year / snapshot_data 等。

    返回:
        模板章节 Markdown 文本。
    """

    chapter_id = int(kwargs["chapter_id"])
    fund_name = str(kwargs.get("fund_name", ""))
    report_year = int(kwargs.get("report_year", 0))
    quarter = kwargs.get("quarter")
    period = kwargs.get("period")
    snapshot_data = kwargs.get("snapshot_data")
    if not isinstance(snapshot_data, dict):
        snapshot_data = {}
    latest = snapshot_data.get("latest_performance")
    if not isinstance(latest, dict):
        latest = {}

    if chapter_id == 0:
        scale = snapshot_data.get("scale_info")
        scale_text = ""
        if isinstance(scale, dict):
            scale_text = f"- 期末规模：{scale.get('aum', '缺失')}\n- 期末份额：{scale.get('shares', '缺失')}\n"
        return (
            f"## 概览\n\n"
            f"- 基金名称：{fund_name}\n"
            f"- 报告期：{_period_label(template_id, report_year, int(quarter) if quarter is not None else None, period=period)}\n"
            f"{scale_text}"
            f"- 当期净值增长率（过去一年口径）：{latest.get('nav_growth_rate', 'N/A')}\n"
            f"- 同期基准收益率：{latest.get('benchmark_return_rate', 'N/A')}\n"
            f"- 超额收益：{latest.get('excess_return', 'N/A')}\n\n"
            f"基于 {_period_label(template_id, report_year, int(quarter) if quarter is not None else None, period=period)} "
            f"披露数据，该基金业绩表现和持仓情况详见后续章节。\n"
        )

    # 非概览章节：从数据表格提取关键行做要点摘要，避免模板模式内容空洞
    parts = [f"## 章节 {chapter_id} 要点\n"]
    if chapter_id == 1:
        perf_rows = snapshot_data.get("performance_rows")
        if isinstance(perf_rows, list) and perf_rows:
            parts.append("滚动窗口口径（≠ 日历年度）净值表现：\n")
            for row in perf_rows:
                if not isinstance(row, dict):
                    continue
                parts.append(
                    f"- {row.get('stage', '')}：净值增长率 {row.get('nav_growth_rate', '缺失')}，"
                    f"基准 {row.get('benchmark_return_rate', '缺失')}，超额 {row.get('excess_return', '缺失')}"
                )
        else:
            parts.append("- 当期业绩数据缺失（fail-closed，未披露则不补）\n")
    elif chapter_id == 2:
        alloc = snapshot_data.get("allocation_rows")
        if isinstance(alloc, list) and alloc:
            equity = next((r for r in alloc if isinstance(r, dict) and "股票" in str(r.get("asset_class", ""))), None)
            if equity:
                parts.append(f"- 股票仓位：{equity.get('ratio', '缺失')}（占基金资产比例）")
        holdings = snapshot_data.get("holdings_rows")
        if isinstance(holdings, list) and holdings:
            parts.append(f"- 披露持仓 {len(holdings)} 条（季报为前十大，半年报为全部持仓），详见数据表")
        share = snapshot_data.get("share_change")
        if isinstance(share, dict) and share:
            parts.append(
                f"- 份额变动：期初 {share.get('beginning_shares', '缺失')} → "
                f"期末 {share.get('ending_shares', '缺失')}"
            )
        if not parts[1:]:
            parts.append("- 持仓与配置数据缺失（fail-closed）\n")
    elif chapter_id == 3 and template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID:
        manager = snapshot_data.get("fund_manager")
        if isinstance(manager, dict):
            parts.append(f"- 基金经理：{manager.get('name', '缺失')}（任职时间：{manager.get('tenure_start', '缺失')}）")
        operation = snapshot_data.get("operation_analysis")
        if operation:
            parts.append(f"- 运作分析（§4.4）节选：{str(operation)[:120]}…")
        own = snapshot_data.get("own_funds")
        if own:
            parts.append(f"- 固有资金：{str(own)[:80]}…")
    elif chapter_id == 3 and template_id != QUARTERLY_SNAPSHOT_TEMPLATE_ID:
        # 半年报 Ch3 财务质量
        fin = snapshot_data.get("financial_rows")
        if isinstance(fin, list) and fin:
            parts.append("主要财务指标（未经审计，单期快照无上期可比）：\n")
            for row in fin[:6]:
                if isinstance(row, dict):
                    parts.append(f"- {row.get('item', '')}：{row.get('current', '缺失')}")
        else:
            parts.append("- 财务数据缺失（fail-closed）\n")
    elif chapter_id == 4:
        if template_id == QUARTERLY_SNAPSHOT_TEMPLATE_ID:
            risk = snapshot_data.get("risk_notes")
            single = snapshot_data.get("single_investor_20pct")
            if risk:
                parts.append(f"- 风险提示节选：{str(risk)[:120]}…")
            if single:
                parts.append(f"- 单一投资者 ≥20%：{str(single)[:80]}…")
        else:
            manager = snapshot_data.get("fund_manager")
            if isinstance(manager, dict):
                parts.append(f"- 基金经理：{manager.get('name', '缺失')}（任职时间：{manager.get('tenure_start', '缺失')}）")
            operation = snapshot_data.get("operation_analysis")
            if operation:
                parts.append(f"- 运作分析（§4.4）节选：{str(operation)[:120]}…")
            share = snapshot_data.get("share_change")
            if isinstance(share, dict) and share:
                parts.append(f"- 份额变动：期初 {share.get('beginning_shares', '缺失')} → 期末 {share.get('ending_shares', '缺失')}")
            own = snapshot_data.get("own_funds")
            if own:
                parts.append(f"- 固有资金：{str(own)[:80]}…")
    elif chapter_id == 5:
        holder = snapshot_data.get("holder_structure")
        if isinstance(holder, dict):
            parts.append(
                f"- 持有人：户数 {holder.get('holder_count', '缺失')}，机构占比 {holder.get('institutional_ratio', '缺失')}，"
                f"个人占比 {holder.get('individual_ratio', '缺失')}"
            )
        risk = snapshot_data.get("risk_notes")
        if risk:
            parts.append(f"- 风险提示节选：{str(risk)[:120]}…")
    parts.append("\n> 模板模式（未启用 --llm）：以上为数据要点摘要，定性分析请使用 --llm 重新生成。")
    return "\n".join(parts) + "\n"
