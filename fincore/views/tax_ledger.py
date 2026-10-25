"""视图 2：支付税费台账。

回答老板的固定问题："这个月交了多少税？都是什么税？"
数据口径：税费科目（默认 2221 应交税费）的**本期借方发生额 = 本月实际缴纳**，
期末贷方净余额 = 已计提未缴纳（负数即借方余额，表示多缴）。多个月可并列对比。
v2：KPI 月度实缴卡 + 金额比例条（当月实缴的相对规模一眼可见）。
"""

from __future__ import annotations

from html import escape

from ..model import StandardTB
from ..render import anchor_badges, fmt, html_page, kpi_cards, num_cell

TAX_NOTES = {
    "222101": "增值税：一般次月申报期缴纳上月计提",
    "222102": "企业所得税：按季预缴，次季初缴纳",
    "222103": "个人所得税：代扣代缴，次月申报缴纳",
    "222104": "城建税及教育费附加等附加税费：随增值税申报缴纳",
    "222105": "印花税等其他税费",
}


def _anchors_of(model: StandardTB):
    from ..model import AnchorResult

    return [AnchorResult(**a) for a in model.meta.get("anchor_results", [])]


def render_tax_ledger(models: list[StandardTB], tax_root: str = "2221") -> str:
    if not models:
        raise ValueError("至少需要一个标准模型")

    # 该根科目下的科目编码并集；根科目排在首行作为小计
    codes: list[str] = []
    for m in models:
        for r in m.rows:
            if r.code.startswith(tax_root) and r.code not in codes:
                codes.append(r.code)
    codes.sort()
    root_first = ([c for c in codes if c == tax_root] + [c for c in codes if c != tax_root]) if tax_root in codes else codes
    detail_codes = [c for c in root_first if c != tax_root]

    name_of: dict[str, str] = {}
    for m in models:
        for c in root_first:
            row = m.by_code(c)
            if row and c not in name_of:
                name_of[c] = row.name

    def paid(m: StandardTB, code: str) -> float:
        r = m.by_code(code)
        return r.period_debit if r else 0.0

    def unpaid(m: StandardTB, code: str) -> float:
        r = m.by_code(code)
        return r.net_closing if r else 0.0

    period_of = lambda m: m.meta.get("period") or m.meta.get("source_file", "?")  # noqa: E731
    month_paid = {id(m): sum(paid(m, c) for c in detail_codes) for m in models}
    month_unpaid = {id(m): sum(unpaid(m, c) for c in detail_codes) for m in models}
    max_paid = max(month_paid.values()) if month_paid else 0.0

    kpis = kpi_cards(
        [
            {"label": f"实缴合计 · {period_of(m)}", "value": f"{month_paid[id(m)] / 1e4:,.2f} 万元",
             "caption": f"期末未缴 {month_unpaid[id(m)] / 1e4:,.2f} 万元",
             "tone": "good" if month_paid[id(m)] > 0 else "neutral"}
            for m in models
        ]
    )

    header_cells = "".join(f'<th colspan="2" class="sortable">{escape(period_of(m))}<span class="arrow"></span></th>' for m in models)

    rows_html: list[str] = []
    for code in root_first:
        is_root = code == tax_root
        cells: list[str] = []
        for m in models:
            bar = (paid(m, code) / max_paid * 100) if max_paid > 0 and not is_root else None
            cells.append(num_cell(paid(m, code), bar_pct=bar))
            cells.append(num_cell(unpaid(m, code)))
        note = TAX_NOTES.get(code, "")
        label = escape(name_of.get(code, code))
        cls = ' class="total"' if is_root else ""
        rows_html.append(
            f"<tr{cls}><td><code>{escape(code)}</code></td><td>{label}</td>"
            f"{''.join(cells)}<td>{escape(note)}</td></tr>"
        )

    sum_cells = "".join(
        num_cell(month_paid[id(m)]) + num_cell(month_unpaid[id(m)])
        for m in models
    )
    total_row = f'<tr class="total"><td></td><td>实缴 / 未缴合计（不含根科目行）</td>{sum_cells}<td></td></tr>'

    body = f"""
  {kpis}
  <div class="card">
    <table>
      <thead><tr>
        <th>科目</th><th>税费种类</th>
        {header_cells}
        <th>口径说明</th>
      </tr></thead>
      <tbody>{''.join(rows_html)}{total_row}</tbody>
    </table>
    <p class="note">单位：<span class="unit-tag">万元</span>。"本月实缴"取该科目本期借方发生额；"期末未缴"为期末贷方净余额
    （负数表示多缴）。实缴单元格底部的比例条为当月各税种实缴的相对规模。悬停数字可查看源文件行级溯源。</p>
  </div>"""

    first = models[0].meta
    meta = [
        ("公司", first.get("company", "—")),
        ("对比期间", "、".join(period_of(m) for m in models)),
        ("税费根科目", tax_root),
        ("来源映射", first.get("mapping_name", "")),
        ("生成时间", first.get("generated_at", "—")),
    ]
    return html_page("支付税费台账", meta, anchor_badges(_anchors_of(models[0])), body)
