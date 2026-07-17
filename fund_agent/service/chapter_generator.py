"""LLM 章节生成器：程序表格 + LLM 定性分析两阶段模式。"""

from __future__ import annotations

import re
from typing import Any

from fund_agent.fund.document_tools.models import Citation
from .models import (
    AssetAllocationItem,
    ChapterEvidence,
    FeeRateItem,
    FundManagerInfo,
    FundReport,
    HoldingExtraction,
    ReportChapter,
    ScaleInfo,
    SignalJudgment,
    StressTestResult,
)


LLM_CHAPTER_SYSTEM_PROMPT = (
    "你是一位专业的基金分析师。请基于提供的数据表格，撰写定性分析评论。\n\n"
    "【输出格式 - 必须严格遵守】\n"
    "1. 你可以引用数据表格中的数字（如净值增长率、费率、持仓比例等），引用时需注明据上表或据数据表格\n"
    "2. 禁止编造数据表格中不存在的数字\n"
    "3. 数据表格已由系统生成，你只需要写分析评论\n"
    "4. 禁止输出投资建议关键词（如'买入''卖出''推荐''建议关注'等），即使引用基金经理原文也需改写\n"
    "5. 禁止预测未来收益或市场走势\n"
    "6. 使用 Markdown 格式，语言简洁专业\n\n"
    "违反以上约束的输出将被拒绝。"
)

LLM_ANALYSIS_PROMPTS: dict[int, str] = {
    0: (
        "请基于上述关键指标数据，写一段「投资要点概览」分析。要求：\n"
        "- 用一句话定义这是什么基金\n"
        "- 给出极简基金简介（类型、经理、规模中最必要的信息）\n"
        "- 回答当前综合评估结论：表现优异、表现平稳还是需要关注\n"
        "- 回答当前最值得盯住的变量是什么\n"
        "- 回答当前最大的风险是什么（只保留1个）\n"
        "- 回答下一步最小验证问题是什么（只写1个）\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    1: (
        "请基于上述基本信息和基金经理投资策略，写一段「产品定义」分析。要求：\n"
        "- 用最低认知负担定义这只基金到底是什么产品\n"
        "- 说明投资目标和投资策略\n"
        "- 说明看这类基金时通常最先要看什么\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    2: (
        "请基于上述业绩数据和成本数据，写一段「R=A+B-C 收益归因」分析。要求：\n"
        "- 分析超额收益(A=R-B)的趋势：是结构性的还是阶段性的\n"
        "- 判断超额收益是否为正且稳定\n"
        "- 用定性描述（如'上升''下降''稳定''由正转负'），不要重复数字\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    3: (
        "请基于上述基金经理信息和持仓数据，写一段「基金经理画像」分析。要求：\n"
        "- 如果数据表包含「数据完整性声明」，先声明缺失字段，再基于已有数据分析\n"
        "- 言行一致性分析必须基于「宣称投资策略」与实际持仓的对比，禁止从持仓反推基金经理的投资意图或策略\n"
        "- 如果「宣称投资策略」缺失，声明该维度无法分析，仅描述持仓行为特征\n"
        "- 分析持仓集中度趋势、行业分布特点\n"
        "- 分析基金经理是否持有本基金（利益一致性）\n"
        "- 不做性格或人品的主观评价\n"
        "- 不猜测基金经理的动机\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    4: (
        "请基于上述数据，写一段「投资者获得感」分析。要求：\n"
        "- 如果数据表包含「数据完整性声明」（2026 新规前年报），说明当前报告年份不披露投资者实际收益数据，仅展示基金产品收益\n"
        "- 如果有投资者实际收益数据，分析行为损益 = 投资者实际收益 - 基金产品收益\n"
        "- 分析份额变动趋势\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    5: (
        "请基于上述数据和阶段判定规则，写一段「当前阶段与关键变化」分析。要求：\n"
        "- 参考数据表中的「阶段判定规则」节，按优先级匹配阶段（转型期>建仓期>膨胀期>萎缩期>稳定期）\n"
        "- 参考「关键变化指标（预计算）」节，直接引用预计算结果，不要自行计算派生数字\n"
        "- 参考「关键变化筛选阈值」节，从持仓变动/规模变动/费率变动3个维度筛选关键变化，只列阈值触发的项\n"
        "- 如果预计算结果显示某维度已触发阈值，直接引用；如果未触发，说明未触发\n"
        "- 分析这些变化是否影响原始投资假设（如果数据表中有信号评分，对比方向是否逆转）\n"
        "- 给出接下来最该跟踪的1-3个变量（引用数据表中评分最低或数据缺失的指标）\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    6: (
        "请基于上述风险相关数据，写一段「核心风险与否决项」分析。要求：\n"
        "- 指出最关键的风险或否决项（1-2个最致命的）\n"
        "- 说明为什么足以改变结论\n"
        "- 判断是否触发一票否决，还是仍可跟踪\n"
        "- 包含标准风险声明（过往业绩不代表未来表现）\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
    7: (
        "请基于上述信号判断结果和前6章分析，写一段「综合评估与跟踪建议」的定性分析。要求：\n"
        "- 系统已给出信号判断（🟢/🟡/🔴）和评分详情表，你只需写定性分析评论\n"
        "- 解释为什么当前信号是合理的，结合评分详情中的最高分和最低分指标\n"
        "- 指出当前最容易看错的地方（关注评分为 0 或数据缺失的指标）\n"
        "- 给出下一轮最小验证计划（1-2个）\n"
        "- 禁止输出投资建议（如'买入''卖出''推荐'）\n"
        "- 禁止预测未来收益或市场走势\n"
        "- 可以引用数据表中的数字，但不得编造数据表中不存在的数字"
    ),
}


def generate_data_table(
    chapter_id: int,
    fund_code: str,
    fund_name: str,
    report_year: int,
    performance: dict[int, dict[str, str]],
    holdings: dict[int, tuple[HoldingExtraction, ...]],
    allocation: dict[int, tuple[AssetAllocationItem, ...]],
    fees: dict[int, tuple[FeeRateItem, ...]],
    fund_manager: FundManagerInfo | None = None,
    scale_info: ScaleInfo | None = None,
    evidence: ChapterEvidence | None = None,
    stress_test: StressTestResult | None = None,
    signal_judgment: SignalJudgment | None = None,
) -> str:
    """程序化生成数据表格（数字 100% 从数据 dict 提取，不经过 LLM）。

    参数:
        chapter_id: 章节编号。
        fund_code/fund_name/report_year: 基本信息。
        performance/holdings/allocation/fees: 多年度数据。
        fund_manager: 基金经理信息。
        scale_info: 规模信息。
        evidence: 证据来源汇总（可选）。

    返回:
        Markdown 格式的数据表格文本（含证据来源小节）。
    """

    base_content = ""

    # Ch0: 投资要点概览 — 汇总关键指标
    if chapter_id == 0:
        # 产品定义（确定性，结构化底线）
        from .extraction import compute_product_definition
        product_def = compute_product_definition(fund_name, fund_code, fund_manager)

        latest = performance.get(report_year, {})
        latest_nav = latest.get("nav_growth_rate", "N/A")
        latest_bench = latest.get("benchmark_return_rate", "N/A")
        latest_excess = latest.get("excess_return", "N/A")

        # 计算多年超额收益趋势
        excess_trend = ""
        excess_years = sorted(performance.keys())
        if len(excess_years) >= 2:
            excesses = [performance[y].get("excess_return", "N/A") for y in excess_years]
            excess_trend = ", ".join(f"{y}年:{e}" for y, e in zip(excess_years, excesses))

        # 最新费率
        latest_fees = fees.get(report_year, [])
        mgmt_fee = ""
        custodian_fee = ""
        for f in latest_fees:
            if "管理" in f.fee_name:
                mgmt_fee = f.rate
            elif "托管" in f.fee_name:
                custodian_fee = f.rate

        lines = [
            "## 关键指标",
            "",
            "### 产品定义",
            "",
            product_def,
            "",
            "| 指标 | 值 |",
            "|------|----|",
            f"| 基金名称 | {fund_name} |",
            f"| 基金代码 | {fund_code} |",
            f"| 报告年份 | {report_year} |",
            f"| 最新净值增长率 | {latest_nav} |",
            f"| 最新基准收益率 | {latest_bench} |",
            f"| 最新超额收益 | {latest_excess} |",
            f"| 管理费 | {mgmt_fee or 'N/A'} |",
            f"| 托管费 | {custodian_fee or 'N/A'} |",
        ]
        if fund_manager:
            lines.append(f"| 基金经理 | {fund_manager.name} |")
        if excess_trend:
            lines.append("")
            lines.append(f"**超额收益趋势**：{excess_trend}")

        # 阈值事件（从 SignalJudgment 反推）
        if signal_judgment is not None:
            lines.append("")
            lines.append("### 阈值事件")
            if signal_judgment.upgrade_event:
                lines.append(f"- **升级路径**：{signal_judgment.upgrade_event.description}")
            else:
                lines.append("- **升级路径**：当前无明确升级路径（数据不足或已满分）")
            if signal_judgment.downgrade_event:
                lines.append(f"- **降级风险**：{signal_judgment.downgrade_event.description}")
            else:
                lines.append("- **降级风险**：当前无明确降级风险（数据不足或已零分）")

        base_content = "\n".join(lines)

    # Ch1: 产品定义 — 基本信息 + 基金经理
    if chapter_id == 1:
        lines = [
            "## 基本信息",
            "",
            "| 项目 | 值 |",
            "|------|----|",
            f"| 基金代码 | {fund_code} |",
            f"| 基金名称 | {fund_name} |",
            f"| 报告年份 | {report_year} |",
        ]
        if fund_manager:
            lines.extend([
                f"| 基金经理 | {fund_manager.name} |",
                f"| 任职日期 | {fund_manager.tenure_start} |",
                f"| 从业年限 | {fund_manager.years_of_service} |",
            ])
            if fund_manager.investment_strategy:
                lines.append("")
                lines.append("## 基金经理投资策略（原文摘录）")
                lines.append("")
                lines.append(fund_manager.investment_strategy[:400])
        base_content = "\n".join(lines)

    # Ch2: R=A+B-C 收益归因
    if chapter_id == 2:
        lines = []
        # 数据不足时输出结构化缺失声明
        if len(performance) < 3:
            lines.extend([
                f"**数据完整性声明**：当前仅导入 {len(performance)} 年数据，本章要求近 1/3/5 年数据。以下为已导入年份的 R-A-B-C 拆解。",
                "",
            ])
        lines.extend([
            "## 业绩数据",
            "",
            "| 年份 | 净值增长率(R) | 基准收益率(B) | 超额收益(A=R-B) |",
            "|------|-------------|-------------|----------------|",
        ])
        for year in sorted(performance.keys()):
            p = performance[year]
            lines.append(
                f"| {year} | {p.get('nav_growth_rate', 'N/A')} | "
                f"{p.get('benchmark_return_rate', 'N/A')} | "
                f"{p.get('excess_return', 'N/A')} |"
            )
        # 费率作为成本C
        lines.extend(["", "## 成本数据(C)", ""])
        lines.extend(["| 年份 | 管理费 | 托管费 |", "|------|--------|--------|"])
        for year in sorted(fees.keys()):
            mgmt = ""
            cust = ""
            for f in fees[year]:
                if "管理" in f.fee_name:
                    mgmt = f.rate
                elif "托管" in f.fee_name:
                    cust = f.rate
            lines.append(f"| {year} | {mgmt} | {cust} |")
        base_content = "\n".join(lines)

    # Ch3: 基金经理画像
    if chapter_id == 3:
        lines = ["## 基金经理信息"]
        if fund_manager:
            # 检查字段完整性，逐项声明缺失字段
            missing_fields = []
            if not fund_manager.tenure_start:
                missing_fields.append("任职日期")
            if not fund_manager.years_of_service:
                missing_fields.append("从业年限")
            if not fund_manager.investment_strategy:
                missing_fields.append("宣称投资策略")
            if not fund_manager.holds_fund:
                missing_fields.append("持有本基金")
            if missing_fields:
                lines.extend(["", f"**数据完整性声明**：以下字段缺失：{'、'.join(missing_fields)}。言行一致性判断仅基于已有数据。", ""])
            lines.extend([
                "",
                "| 项目 | 值 |",
                "|------|----|",
                f"| 姓名 | {fund_manager.name} |",
                f"| 任职日期 | {fund_manager.tenure_start or '未披露'} |",
                f"| 从业年限 | {fund_manager.years_of_service or '未披露'} |",
                f"| 持有本基金 | {fund_manager.holds_fund or '未披露'} |",
            ])
            if fund_manager.investment_strategy:
                lines.extend(["", "## 宣称投资策略（原文）", "", fund_manager.investment_strategy[:600]])
        else:
            lines.extend(["", "**数据完整性声明**：基金经理信息未提取成功。以下仅展示持仓行为数据，无法进行言行一致性分析。", ""])
        # 持仓变化作为实际行为
        lines.extend(["", "## 实际持仓行为"])
        for year in sorted(holdings.keys()):
            lines.append(f"\n### {year} 年前十大持仓")
            lines.append("| 排名 | 股票代码 | 股票名称 | 占净值比 |")
            lines.append("|------|---------|---------|---------|")
            for h in holdings[year][:10]:
                lines.append(f"| {h.rank} | {h.stock_code} | {h.stock_name} | {h.percentage} |")
        base_content = "\n".join(lines)

    # Ch4: 投资者获得感
    if chapter_id == 4:
        if report_year < 2026:
            lines = [
                '## 投资者获得感', '',
                '**数据完整性声明**：本章节所需的投资者实际收益数据（盈利投资者占比、加权平均投资者收益率）'
                '为 2026 年度报告新规要求披露的字段。当前报告年份为 '
                f'{report_year} 年，年报中不包含上述数据，本章节暂不适用。', '',
                '以下仅展示基金产品收益数据。', '',
            ]
            if performance:
                lines.extend(['| 年份 | 净值增长率 | 基准收益率 |', '|------|-----------|-----------|'])
                for year in sorted(performance.keys()):
                    p = performance[year]
                    lines.append(f'| {year} | {p.get("nav_growth_rate", "N/A")} | {p.get("benchmark_return_rate", "N/A")} |')
            base_content = '\n'.join(lines)
        else:
            base_content = "## 投资者获得感\n\n投资者实际收益数据暂不可用，详见原始年报。"

    # Ch5: 当前阶段与关键变化
    if chapter_id == 5:
        lines = ["## 规模与配置数据"]
        if scale_info:
            lines.extend([
                "",
                "| 项目 | 值 |",
                "|------|----|",
                f"| A类份额总数 | {scale_info.total_shares_a} |",
                f"| C类份额总数 | {scale_info.total_shares_c} |",
                f"| 个人投资者持有比例 | {scale_info.individual_investor_ratio} |",
                f"| 管理人从业人员持有比例 | {scale_info.management_holds} |",
            ])
            if scale_info.estimated_aum:
                lines.append(f"| 估算资产净值 | {scale_info.estimated_aum} |")
            # 预计算份额万份（避免 LLM 派生计算触发 hallucination）
            try:
                shares_a_num = float(scale_info.total_shares_a.replace(",", ""))
                shares_c_num = float(scale_info.total_shares_c.replace(",", ""))
                lines.append(f"| A类份额（万份） | {shares_a_num / 10000:.2f} |")
                lines.append(f"| C类份额（万份） | {shares_c_num / 10000:.2f} |")
                lines.append(f"| 合计份额（万份） | {(shares_a_num + shares_c_num) / 10000:.2f} |")
            except (ValueError, AttributeError):
                pass
        # 资产配置变化
        lines.extend(["", "## 资产配置变化"])
        for year in sorted(allocation.keys()):
            lines.append(f"\n### {year} 年资产配置")
            lines.append("| 资产类别 | 金额 | 占净值比 |")
            lines.append("|---------|------|---------|")
            for a in allocation[year][:8]:
                lines.append(f"| {a.category} | {a.amount} | {a.percentage_of_net} |")

        # 结构化阶段判定（确定性计算）
        lines.extend(["", "## 阶段判定规则"])
        stage = "稳定期"  # 默认
        stage_reason = "默认"
        sorted_years = sorted(performance.keys())
        if len(sorted_years) >= 2:
            prev_year = sorted_years[-2]
            curr_year = sorted_years[-1]
            # 规模变动检测（膨胀期/萎缩期）
            if scale_info and hasattr(scale_info, 'estimated_aum') and scale_info.estimated_aum:
                try:
                    # 从 allocation 数据中估算上一年规模
                    # 使用权益投资金额作为规模代理
                    if prev_year in allocation and allocation[prev_year]:
                            prev_equity = 0.0
                            curr_equity = 0.0
                            for a in allocation[prev_year]:
                                if '权益' in a.category or '股票' in a.category:
                                    try:
                                        prev_equity += float(a.amount.replace(",", ""))
                                    except (ValueError, AttributeError):
                                        pass
                            for a in allocation.get(curr_year, []):
                                if '权益' in a.category or '股票' in a.category:
                                    try:
                                        curr_equity += float(a.amount.replace(",", ""))
                                    except (ValueError, AttributeError):
                                        pass
                            if prev_equity and curr_equity and prev_equity > 0:
                                growth_rate = (curr_equity - prev_equity) / prev_equity
                                if growth_rate > 0.3:
                                    stage = "膨胀期"
                                    stage_reason = f"权益投资同比增长 {growth_rate:.0%}，超过30%阈值"
                                elif growth_rate < -0.3:
                                    stage = "萎缩期"
                                    stage_reason = f"权益投资同比下降 {abs(growth_rate):.0%}，超过30%阈值"
                except (ValueError, AttributeError):
                    pass
            # 基金经理变更检测（如果 fund_manager 有变更记录）
            if fund_manager and not fund_manager.tenure_start:
                stage = "转型期"
                stage_reason = "基金经理信息缺失，可能涉及变更"
        # 建仓期检测
        if fund_manager and fund_manager.tenure_start:
            try:
                import re as _re
                year_match = _re.search(r'(\d{4})', fund_manager.tenure_start)
                if year_match:
                    start_year = int(year_match.group(1))
                    if report_year - start_year < 2:
                        stage = "建仓期"
                        stage_reason = f"基金经理任职于{start_year}年，管理本基金不足2年"
            except (ValueError, AttributeError):
                pass

        stage_labels = {
            "转型期": "🔴 转型期（优先级最高）",
            "建仓期": "🟡 建仓期",
            "膨胀期": "🟡 膨胀期",
            "萎缩期": "🟡 萎缩期",
            "稳定期": "🟢 稳定期",
        }
        lines.append(f"| 判定结果 | {stage_labels.get(stage, stage)} |")
        lines.append(f"| 判定依据 | {stage_reason} |")
        lines.append("")
        lines.append("阶段优先级：转型期 > 建仓期 > 膨胀期 > 萎缩期 > 稳定期")
        lines.append("时间窗口：同比（当前年 vs 上一年）")

        # 预计算关键变化指标（避免 LLM 派生计算触发 hallucination）
        lines.extend(["", "## 关键变化指标（预计算）"])
        fee_years = sorted(fees.keys())
        if len(fee_years) >= 2:
            prev_fee_year = fee_years[-2]
            curr_fee_year = fee_years[-1]
            prev_mgmt = ""
            curr_mgmt = ""
            prev_cust = ""
            curr_cust = ""
            for f in fees.get(prev_fee_year, []):
                if "管理" in f.fee_name:
                    prev_mgmt = f.rate.rstrip("%")
                elif "托管" in f.fee_name:
                    prev_cust = f.rate.rstrip("%")
            for f in fees.get(curr_fee_year, []):
                if "管理" in f.fee_name:
                    curr_mgmt = f.rate.rstrip("%")
                elif "托管" in f.fee_name:
                    curr_cust = f.rate.rstrip("%")
            try:
                if prev_mgmt and curr_mgmt:
                    mgmt_change = float(curr_mgmt) - float(prev_mgmt)
                    lines.append(f"- 管理费变动: {prev_fee_year}年{prev_mgmt}% → {curr_fee_year}年{curr_mgmt}%（变动{mgmt_change:+.2f}%）")
                    lines.append(f"  - 是否触发阈值(>0.1%): {'是' if abs(mgmt_change) > 0.1 else '否'}")
                if prev_cust and curr_cust:
                    cust_change = float(curr_cust) - float(prev_cust)
                    lines.append(f"- 托管费变动: {prev_fee_year}年{prev_cust}% → {curr_fee_year}年{curr_cust}%（变动{cust_change:+.2f}%）")
                    lines.append(f"  - 是否触发阈值(>0.1%): {'是' if abs(cust_change) > 0.1 else '否'}")
            except (ValueError, AttributeError):
                pass

        # 关键变化筛选阈值
        lines.extend(["", "## 关键变化筛选阈值"])
        lines.append("| 维度 | 阈值 | 说明 |")
        lines.append("|------|------|------|")
        lines.append("| 持仓变动 | 前十大持仓换手 >40% | 两年间前十大持仓中替换的股票数量占比 |")
        lines.append("| 规模变动 | 份额×净值同比 >30% | 规模同比增长超过30% |")
        lines.append("| 费率变动 | 管理费/托管费绝对值变动 >0.1% | 费率变动超过0.1个百分点 |")

        base_content = "\n".join(lines)

    # Ch6: 核心风险与否决项
    if chapter_id == 6:
        lines = ["## 风险相关数据"]
        # 持仓集中度
        for year in sorted(holdings.keys()):
            top5_pct = sum(float(h.percentage.rstrip("%") or "0") for h in holdings[year][:5])
            lines.append(f"\n{year}年前五大持仓集中度: {top5_pct:.2f}%")
        # 业绩波动
        lines.extend(["", "## 业绩波动"])
        lines.append("| 年份 | 净值增长率 | 超额收益 |")
        lines.append("|------|-----------|---------|")
        for year in sorted(performance.keys()):
            p = performance[year]
            lines.append(f"| {year} | {p.get('nav_growth_rate', 'N/A')} | {p.get('excess_return', 'N/A')} |")

        # 压力测试
        if stress_test:
            lines.extend(["", "## 压力测试"])
            fund_type_labels = {"index_fund": "指数基金", "bond_fund": "债券基金", "active_fund": "主动基金"}
            lines.append(f"- 基金类型: {fund_type_labels.get(stress_test.fund_type, stress_test.fund_type)}")
            lines.append(f"- 类型判定: {'关键词推断' if stress_test.fund_type_inferred else '显式指定'}")
            if stress_test.current_scale_billion is not None:
                lines.append(f"- 当前规模: {stress_test.current_scale_billion:.2f}亿元")
                lines.extend(["", "| 场景 | 阈值 | 损失金额(亿元) |",
                              "|------|------|--------------|"])
                for name in ("normal", "extreme", "worst"):
                    sc = stress_test.stress_scenarios[name]
                    lines.append(
                        f"| {name} | {sc['threshold']:.0%} | {sc['loss_billion']:.4f} |"
                    )
            if stress_test.excess_return is not None:
                lines.append(f"\n- 超额收益: {stress_test.excess_return:.2%}")
            if stress_test.stress_level is not None:
                level_labels = {
                    "outperform": "跑赢基准",
                    "inline": "基本持平",
                    "underperform": "跑输基准",
                    "severe_underperform": "严重跑输",
                }
                lines.append(f"- 压力等级: {level_labels.get(stress_test.stress_level, stress_test.stress_level)}")

        base_content = "\n".join(lines)

    # Ch7: 最终判断 — 汇总数据
    if chapter_id == 7:
        latest = performance.get(report_year, {})
        lines = [
            "## 判断依据数据",
            "",
            f"- 最新净值增长率: {latest.get('nav_growth_rate', 'N/A')}",
            f"- 最新超额收益: {latest.get('excess_return', 'N/A')}",
        ]
        if fund_manager:
            lines.append(f"- 基金经理: {fund_manager.name}（从业{fund_manager.years_of_service}）")
        # 最新费率
        latest_fees = fees.get(report_year, [])
        for f in latest_fees:
            lines.append(f"- {f.fee_name}: {f.rate}")
        base_content = "\n".join(lines)

    # 追加证据来源小节
    evidence_section = generate_evidence_section(chapter_id, evidence)
    if evidence_section:
        return base_content + "\n" + evidence_section
    return base_content


def format_citation(citation: Citation | None) -> str:
    """格式化单个 citation 为可读文本。

    参数:
        citation: Citation 对象或 None。

    返回:
        格式化的 citation 文本。
    """

    if citation is None:
        return ""

    locator = citation.locator
    parts = []
    if locator.section_ref:
        parts.append(f"§{locator.section_ref}")
    if locator.table_ref:
        parts.append(f"表{locator.table_ref}")
    if locator.page_no:
        parts.append(f"p.{locator.page_no}")

    ref_str = ", ".join(parts) if parts else "位置未知"
    return f"{citation.year}年报 ({ref_str})"


def generate_evidence_section(
    chapter_id: int,
    evidence: ChapterEvidence | None,
) -> str:
    """生成章节证据来源小节。

    参数:
        chapter_id: 章节编号。
        evidence: 证据来源汇总。

    返回:
        Markdown 格式的证据来源小节。
    """

    if evidence is None:
        return ""

    lines = ["\n### 证据与出处\n"]

    # 根据章节类型列出相关证据来源
    if chapter_id in (0, 2, 7):  # 业绩相关
        if evidence.performance_citations:
            cit_lines = []
            for year, cit in sorted(evidence.performance_citations.items()):
                formatted = format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**业绩数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (0, 3, 6, 7):  # 持仓相关
        if evidence.holdings_citations:
            cit_lines = []
            for year, cit in sorted(evidence.holdings_citations.items()):
                formatted = format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**持仓数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (2, 5, 7):  # 费率相关
        if evidence.fee_citations:
            cit_lines = []
            for year, cit in sorted(evidence.fee_citations.items()):
                formatted = format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**费率数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (4, 5):  # 资产配置相关
        if evidence.allocation_citations:
            cit_lines = []
            for year, cit in sorted(evidence.allocation_citations.items()):
                formatted = format_citation(cit)
                if formatted:
                    cit_lines.append(f"- {year}年: {formatted}")
            if cit_lines:
                lines.append("**资产配置数据来源**：")
                lines.extend(cit_lines)

    if chapter_id in (1, 3):  # 基金经理相关
        if evidence.fund_manager_citation:
            formatted = format_citation(evidence.fund_manager_citation)
            if formatted:
                lines.append(f"**基金经理信息来源**：{formatted}")

    if chapter_id in (0, 5, 7):  # 规模相关
        if evidence.scale_citation:
            formatted = format_citation(evidence.scale_citation)
            if formatted:
                lines.append(f"**规模数据来源**：{formatted}")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


class LlmChapterGenerator:
    """基于 LLM 的逐章生成器（两阶段模式）。

    阶段 1：程序从数据 dict 生成表格（数字 100% 准确）。
    阶段 2：LLM 只写定性分析评论（无数字）。
    最终：表格 + LLM 分析。

    参数:
        llm_client: DeepSeekLlmClient 实例。

    返回:
        可逐章生成分析文本的生成器。

    异常:
        generate_chapter 不向调用方抛出内部异常，失败返回 None。
    """

    def __init__(self, llm_client: Any) -> None:
        """保存 LLM client。"""
        self._llm_client = llm_client

    def generate_chapter(
        self,
        chapter_id: int,
        fund_code: str,
        fund_name: str,
        report_year: int,
        performance: dict[int, dict[str, str]],
        holdings: dict[int, tuple[HoldingExtraction, ...]],
        allocation: dict[int, tuple[AssetAllocationItem, ...]],
        fees: dict[int, tuple[FeeRateItem, ...]],
        fund_manager: FundManagerInfo | None = None,
        scale_info: ScaleInfo | None = None,
        evidence: ChapterEvidence | None = None,
        stress_test: StressTestResult | None = None,
        signal_judgment: SignalJudgment | None = None,
    ) -> str | None:
        """生成单个章节（程序表格 + LLM 分析）。

        参数:
            chapter_id: 章节编号（0-7）。
            fund_code/fund_name/report_year: 基本信息。
            performance/holdings/allocation/fees: 多年度数据。
            fund_manager: 基金经理信息。
            scale_info: 规模信息。
            evidence: 证据来源汇总（可选）。

        返回:
            完整的章节 Markdown；LLM 失败时返回 None（调用方应回退模板）。
        """

        # 阶段 1：程序生成数据表格
        data_table = generate_data_table(
            chapter_id, fund_code, fund_name, report_year,
            performance, holdings, allocation, fees,
            fund_manager, scale_info, evidence, stress_test,
            signal_judgment,
        )

        # 阶段 2：LLM 生成定性分析
        analysis_prompt = LLM_ANALYSIS_PROMPTS.get(chapter_id)
        if not analysis_prompt:
            return data_table if data_table else None

        user_prompt = (
            f"基金名称：{fund_name}\n"
            f"报告年份：{report_year}\n\n"
            f"## 数据表格\n\n{data_table}\n\n"
            f"## 分析要求\n\n{analysis_prompt}"
        )

        try:
            llm_analysis = self._llm_client.generate_text(
                system_prompt=LLM_CHAPTER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            # 从数据表中提取允许的数字（这些数字来自真实数据，不是 hallucination）
            allowed_numbers = set(re.findall(r'\d+\.?\d*', data_table))
            # 检查 LLM 是否违规输出了数字
            if contains_non_year_numbers(llm_analysis, allowed_numbers):
                return None  # hallucination，回退模板
            return f"{data_table}\n\n## 分析\n\n{llm_analysis}"
        except Exception:
            return None


def _normalize_number(s: str) -> str:
    """归一化数字字符串：strip trailing zeros 和尾部小数点。

    参数:
        s: 数字字符串（如 "1.20"、"2.60"、"17.32"）。

    返回:
        归一化后的数字字符串（如 "1.2"、"2.6"、"17.32"）。
    """
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def contains_non_year_numbers(text: str, allowed_numbers: set[str] | None = None) -> bool:
    """检查文本是否包含非年份的数字（hallucination 检测）。

    参数:
        text: 待检查文本。
        allowed_numbers: 允许的数字集合（从数据表中提取）；这些数字不视为 hallucination。
            支持归一化匹配（"1.20" 和 "1.2" 视为相同）。

    返回:
        包含可疑数字时返回 True。
    """

    # 预处理允许列表：归一化所有允许的数字
    normalized_allowed: set[str] | None = None
    if allowed_numbers:
        normalized_allowed = set()
        for num in allowed_numbers:
            normalized_allowed.add(_normalize_number(num))

    numbers = re.findall(r'(?<!\d)\d+\.?\d*%?(?!\d)', text)
    for n in numbers:
        cleaned = n.rstrip('%')
        # 归一化后再做所有检查（1.20→1.2, 1.→1）
        normalized = _normalize_number(cleaned)
        # 年份（20xx）允许
        if re.match(r'^(20[12]\d)$', normalized):
            continue
        # 单位数字（1-9）和常见小数字（10-99）允许（从业年限、排名、列表编号等）
        if re.match(r'^[1-9]\d?$', normalized):
            continue
        # 在允许列表中的数字允许（归一化匹配）
        if normalized_allowed and normalized in normalized_allowed:
            continue
        return True
    return False
