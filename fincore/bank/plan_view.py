"""资金计划执行台账 HTML 视图（零外链、可审计）。

v2：KPI 总览（计划总额/已匹配/执行率/双边差异）+ 执行率进度条。
"""

from __future__ import annotations

from html import escape

from ..model import StandardTB
from ..render import anchor_badges, fmt, html_page, kpi_cards, num_cell
from .matcher import MatchReport


def _anchors_of(anchors: list[dict]):
    from ..model import AnchorResult

    return [AnchorResult(**a) for a in anchors]


def _src_tip(t) -> str:
    s = t.src or {}
    return f"源: {s.get('file', '')} / {s.get('sheet', '')} 第{s.get('row', '')}行"


def _pbar(rate: float) -> str:
    """执行率进度条。rate 0-100；<50% 标红。"""
    low = ' class="low"' if rate < 50 else ""
    return f'<div class="pwrap"><div class="pbar"><i{low} style="width:{max(0.0, min(rate, 100.0)):.0f}%"></i></div><span class="pval">{rate:.0f}%</span></div>'


def render_plan_ledger(report: MatchReport, anchors: list[dict] | None = None,
                       meta: dict | None = None) -> str:
    meta = meta or {}
    tx_total = sum(t.amount for t in report.unmatched_txs)
    plan_total = sum(p.amount for p in report.unmatched_plans)
    matched_total = sum(m.matched_amount for m in report.matches)
    planned_total = matched_total + plan_total
    overall = matched_total / planned_total * 100 if planned_total else 0
    bucket_total = sum(b.matched_amount for b in report.keyword_buckets)

    kpis = kpi_cards([
        {"label": "计划总额", "value": f"{planned_total / 1e4:,.2f} 万元",
         "caption": f"{len(report.matches) + len(report.unmatched_plans)} 行计划"},
        {"label": "已匹配", "value": f"{matched_total / 1e4:,.2f} 万元", "tone": "good"},
        {"label": "总体执行率", "value": f"{overall:.0f}%", "tone": "good" if overall >= 80 else ("bad" if overall < 50 else "neutral")},
        {"label": "未匹配流水", "value": f"{tx_total / 1e4:,.2f} 万元",
         "caption": f"{len(report.unmatched_txs)} 笔（银行有、计划无）", "tone": "bad" if tx_total else "neutral"},
        {"label": "未执行计划", "value": f"{plan_total / 1e4:,.2f} 万元",
         "caption": f"{len(report.unmatched_plans)} 行（计划有、银行无）", "tone": "bad" if plan_total else "neutral"},
    ])

    rows_html: list[str] = []
    for m in report.matches:
        plan = m.plan
        rate = m.matched_amount / plan.amount * 100 if plan.amount else 0
        detail = "；".join(f"{t.date.isoformat()} {t.counterparty or t.summary}" for t in m.txs)
        rows_html.append(
            f'<tr data-search="{escape(f"{plan.name} {plan.counterparty}").lower()}">'
            f"<td>{escape(plan.name)}</td>"
            f"<td>{escape(plan.direction)}</td>"
            + num_cell(plan.amount) + num_cell(m.matched_amount)
            + f'<td>{_pbar(rate)}</td>'
            f"<td>{escape(detail)}</td>"
            f'<td title="{escape(m.rule)}"><code>{m.tier}</code></td>'
            "</tr>"
        )
    for p in report.unmatched_plans:
        rows_html.append(
            f'<tr data-search="{escape(f"{p.name} {p.counterparty}").lower()}">'
            f"<td>{escape(p.name)}</td><td>{escape(p.direction)}</td>"
            + num_cell(p.amount) + num_cell(0.0)
            + f'<td>{_pbar(0)}</td>'
            "<td>❌ 未找到匹配流水</td><td></td></tr>"
        )
    if rows_html:
        rows_html.append(
            '<tr class="total"><td colspan="2">合计</td>'
            + num_cell(planned_total) + num_cell(matched_total)
            + f"<td>{_pbar(overall)}</td><td></td><td></td></tr>"
        )

    tx_rows: list[str] = []
    for t in report.unmatched_txs:
        tx_rows.append(
            "<tr>"
            f"<td>{t.date.isoformat()}</td><td>{escape(t.direction)}</td>"
            + num_cell(t.amount, title=_src_tip(t))
            + f"<td>{escape(t.counterparty)}</td><td>{escape(t.summary)}</td></tr>"
        )
    bucket_rows: list[str] = []
    for b in report.keyword_buckets:
        bucket_rows.append(
            "<tr>"
            f"<td>{escape(b.plan.name)}</td>"
            + num_cell(b.plan.amount)
            + f"<td>{len(b.txs)} 笔</td>"
            f'<td title="{escape(b.rule)}"><code>{b.tier}</code></td></tr>'
        )

    body = f"""
  {kpis}
  <div class="card">
    <h2>计划执行情况</h2>
    <div class="toolbar"><input id="f-q" type="search" placeholder="搜索计划名或对方…"></div>
    <table>
      <thead><tr><th>计划项目</th><th>方向</th><th>计划金额</th><th>已匹配金额</th><th>执行率</th><th>匹配明细</th><th>命中规则</th></tr></thead>
      <tbody id="main-tbody">{''.join(rows_html) or '<tr><td colspan="7">无计划行</td></tr>'}</tbody>
    </table>
    <p class="note">单位：<span class="unit-tag">万元</span>。命中规则列悬停可见匹配逻辑；
    1:1 匹配要求金额相等（±0.01 元）、方向一致、对方匹配、时间窗内；执行率低于 50% 标红。</p>
  </div>
  <div class="card">
    <h2>关键词聚合桶（不进资金计划的固定项目）</h2>
    <table>
      <thead><tr><th>桶名称</th><th>金额合计</th><th>流水笔数</th><th>规则</th></tr></thead>
      <tbody>{''.join(bucket_rows) or '<tr><td colspan="4">无</td></tr>'}</tbody>
    </table>
    <p class="note">桶合计 {fmt(bucket_total)} 万元。</p>
  </div>
  <div class="card">
    <h2>未匹配流水（银行有、计划无）</h2>
    <table>
      <thead><tr><th>日期</th><th>方向</th><th>金额</th><th>对方</th><th>摘要</th></tr></thead>
      <tbody>{''.join(tx_rows) or '<tr><td colspan="5">无 —— 双边已对平</td></tr>'}</tbody>
    </table>
    <p class="note">金额合计 {fmt(tx_total)} 万元；未执行计划合计 {fmt(plan_total)} 万元。这两行数字就是对账差异，
    悬停数字可查看源文件行级溯源。</p>
  </div>"""

    page_meta = [
        ("公司", meta.get("company", "—")),
        ("期间", meta.get("period", "—")),
        ("流水笔数", str(meta.get("tx_count", "—"))),
        ("计划行数", str(meta.get("plan_count", "—"))),
        ("生成时间", meta.get("generated_at", "—")),
    ]
    return html_page("资金计划执行台账", page_meta, anchor_badges(_anchors_of(anchors or [])), body)
