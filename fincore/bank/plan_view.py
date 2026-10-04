"""资金计划执行台账 HTML 视图（零外链、可审计）。"""

from __future__ import annotations

from html import escape

from ..render import anchor_badges, html_page, num_cell
from .matcher import MatchReport


def _anchors_of(anchors: list[dict]):
    from ..model import AnchorResult

    return [AnchorResult(**a) for a in anchors]


def _src_tip(t) -> str:
    s = t.src or {}
    return f"源: {s.get('file', '')} / {s.get('sheet', '')} 第{s.get('row', '')}行"


def render_plan_ledger(report: MatchReport, anchors: list[dict] | None = None,
                       meta: dict | None = None) -> str:
    meta = meta or {}
    tx_total = sum(t.amount for t in report.unmatched_txs)
    plan_total = sum(p.amount for p in report.unmatched_plans)

    rows_html: list[str] = []
    for m in report.matches:
        plan = m.plan
        rate = m.matched_amount / plan.amount * 100 if plan.amount else 0
        detail = "；".join(f"{t.date.isoformat()} {t.counterparty or t.summary}" for t in m.txs)
        rows_html.append(
            "<tr data-search=\"" + escape(f"{plan.name} {plan.counterparty}").lower() + "\">"
            f"<td>{escape(plan.name)}</td>"
            f"<td>{escape(plan.direction)}</td>"
            + num_cell(plan.amount)
            + num_cell(m.matched_amount)
            + f"<td class=\"num\">{rate:.0f}%</td>"
            f"<td>{escape(detail)}</td>"
            f"<td title=\"{escape(m.rule)}\"><code>{m.tier}</code></td>"
            "</tr>"
        )
    for p in report.unmatched_plans:
        rows_html.append(
            "<tr data-search=\"" + escape(f"{p.name} {p.counterparty}").lower() + "\">"
            f"<td>{escape(p.name)}</td><td>{escape(p.direction)}</td>"
            + num_cell(p.amount) + num_cell(0.0)
            + "<td class=\"num\">0%</td>"
            "<td>❌ 未找到匹配流水</td><td></td></tr>"
        )
    if rows_html:
        rows_html.append(
            '<tr class="total"><td colspan="2">合计（含未执行计划）</td>'
            + num_cell(sum(m.plan.amount for m in report.matches) + plan_total)
            + num_cell(sum(m.matched_amount for m in report.matches))
            + "<td class=\"num\"></td><td></td><td></td></tr>"
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
            f"<td title=\"{escape(b.rule)}\"><code>{b.tier}</code></td></tr>"
        )

    body = f"""
  <div class="card">
    <h2>计划执行情况</h2>
    <div class="toolbar"><input id="f-q" type="search" placeholder="搜索计划名或对方…"></div>
    <table>
      <thead><tr><th>计划项目</th><th>方向</th><th>计划金额</th><th>已匹配金额</th><th>执行率</th><th>匹配明细</th><th>命中规则</th></tr></thead>
      <tbody id="main-tbody">{''.join(rows_html) or '<tr><td colspan="7">无计划行</td></tr>'}</tbody>
    </table>
    <p class="note">单位：万元。命中规则列悬停可见匹配逻辑；1:1 匹配要求金额相等（±0.01 元）、方向一致、对方匹配、时间窗内。</p>
  </div>
  <div class="card">
    <h2>关键词聚合桶（不进资金计划的固定项目）</h2>
    <table>
      <thead><tr><th>桶名称</th><th>金额合计</th><th>流水笔数</th><th>规则</th></tr></thead>
      <tbody>{''.join(bucket_rows) or '<tr><td colspan="4">无</td></tr>'}</tbody>
    </table>
  </div>
  <div class="card">
    <h2>未匹配流水（银行有、计划无）</h2>
    <table>
      <thead><tr><th>日期</th><th>方向</th><th>金额</th><th>对方</th><th>摘要</th></tr></thead>
      <tbody>{''.join(tx_rows) or '<tr><td colspan="5">无 —— 双边已对平</td></tr>'}</tbody>
    </table>
    <p class="note">金额合计 {tx_total / 10000:,.2f} 万元；未执行计划合计 {plan_total / 10000:,.2f} 万元。这两行数字就是对账差异。</p>
  </div>"""

    page_meta = [
        ("公司", meta.get("company", "—")),
        ("期间", meta.get("period", "—")),
        ("流水笔数", str(meta.get("tx_count", "—"))),
        ("计划行数", str(meta.get("plan_count", "—"))),
        ("生成时间", meta.get("generated_at", "—")),
    ]
    return html_page("资金计划执行台账", page_meta, anchor_badges(_anchors_of(anchors or [])), body)
