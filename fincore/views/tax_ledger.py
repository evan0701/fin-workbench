"""视图 2：支付税费台账。

回答老板的固定问题："这个月交了多少税？都是什么税？"
数据口径：税费科目（默认 2221 应交税费）的**本期借方发生额 = 本月实际缴纳**，
期末贷方净余额 = 已计提未缴纳（负数即借方余额，表示多缴）。多个月可并列对比。
"""

from __future__ import annotations

from html import escape

from ..model import StandardTB
from ..render import anchor_badges, html_page, num_cell

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

    unit_note = "万元"  # 元进万元出

    # 该根科目下的科目编码并集；根科目排在首行作为小计
    codes: list[str] = []
    for m in models:
        for r in m.rows:
            if r.code.startswith(tax_root) and r.code not in codes:
                codes.append(r.code)
    codes.sort()
    root_first = ([c for c in codes if c == tax_root] + [c for c in codes if c != tax_root]) if tax_root in codes else codes

    name_of: dict[str, str] = {}
    for m in models:
        for c in root_first:
            row = m.by_code(c)
            if row and c not in name_of:
                name_of[c] = row.name

    detail_codes = [c for c in root_first if c != tax_root]

    def paid(m: StandardTB, code: str) -> float:
        r = m.by_code(code)
        return r.period_debit if r else 0.0

    def unpaid(m: StandardTB, code: str) -> float:
        r = m.by_code(code)
        return r.net_closing if r else 0.0

    header_cells = "".join(
        f'<th colspan="2">{escape(m.meta.get("period") or m.meta.get("source_file", "?"))}</th>' for m in models
    )

    rows_html: list[str] = []
    for code in root_first:
        is_root = code == tax_root
        cells: list[str] = []
        for m in models:
            cells.append(num_cell(paid(m, code), unit_note))
            cells.append(num_cell(unpaid(m, code), unit_note))
        note = TAX_NOTES.get(code, "")
        label = escape(name_of.get(code, code))
        cls = ' class="total"' if is_root else ""
        rows_html.append(
            f"<tr{cls}><td><code>{escape(code)}</code></td><td>{label}</td>"
            f"{''.join(cells)}<td>{escape(note)}</td></tr>"
        )

    sum_cells = "".join(
        num_cell(sum(paid(m, c) for c in detail_codes), unit_note)
        + num_cell(sum(unpaid(m, c) for c in detail_codes), unit_note)
        for m in models
    )
    total_row = (
        f'<tr class="total"><td></td><td>实缴 / 未缴合计（不含根科目行）</td>{sum_cells}<td></td></tr>'
    )

    body = f"""
  <div class="card">
    <table>
      <thead><tr>
        <th rowspan="2">科目</th><th rowspan="2">税费种类</th>
        {header_cells}
        <th rowspan="2">口径说明</th>
      </tr><tr>
        {''.join('<th>本月实缴</th><th>期末未缴</th>' for _ in models)}
      </tr></thead>
      <tbody>{''.join(rows_html)}{total_row}</tbody>
    </table>
    <p class="note">单位：{unit_note}。"本月实缴"取该科目本期借方发生额；"期末未缴"为期末贷方净余额（负数表示多缴）。
    悬停数字可查看源文件行级溯源。税种口径详见 references/口径说明.md。</p>
  </div>"""

    first = models[0].meta
    meta = [
        ("公司", first.get("company", "—")),
        ("对比期间", "、".join((m.meta.get("period") or m.meta.get("source_file", "?")) for m in models)),
        ("税费根科目", tax_root),
        ("来源映射", first.get("mapping_name", "")),
        ("生成时间", first.get("generated_at", "—")),
    ]
    return html_page("支付税费台账", meta, anchor_badges(_anchors_of(models[0])), body)
