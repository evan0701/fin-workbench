"""视图 1：科目余额筛选台账。

解决的问题：金蝶/用友导出的余额表是给人核对用的，不是给"回答经营问题"用的。
这个台账把标准模型渲染成可搜索、可筛选的单页 HTML，每个数字悬停可溯源。
"""

from __future__ import annotations

from html import escape

from ..model import StandardTB
from ..render import anchor_badges, html_page, num_cell


def _direction(row) -> str:
    """余额方向：期末净额借方为正即"借"。零余额显示两平。"""
    if abs(row.net_closing) < 1e-9:
        return "平"
    return "借" if row.net_closing > 0 else "贷"


def _anchors_of(model: StandardTB):
    from ..model import AnchorResult

    return [AnchorResult(**a) for a in model.meta.get("anchor_results", [])]


def render_balance_ledger(model: StandardTB) -> str:
    unit = model.meta.get("unit", "元")
    unit_note = "万元" if unit == "元" else unit  # 元进万元出，统一口径
    src_note = "万元（源文件单位：" + unit + "，已按 1万=10000 换算）" if unit == "元" else unit

    rows_html: list[str] = []
    for r in model.rows:
        nonzero = any(abs(v) > 1e-9 for v in (
            r.opening_debit, r.opening_credit, r.period_debit, r.period_credit, r.closing_debit, r.closing_credit))
        src = f"源: {r.src.get('file','')} / {r.src.get('sheet','')} 第{r.src.get('row','')}行"
        search = f"{r.code} {r.name}".lower()
        rows_html.append(
            "<tr "
            f"data-search=\"{escape(search)}\" data-dir=\"{_direction(r)}\" "
            f"data-level=\"{r.level}\" data-nonzero=\"{'1' if nonzero else '0'}\">"
            f"<td><code>{escape(r.code)}</code></td>"
            f"<td>{escape(r.name)}</td>"
            f"<td>{r.level}</td>"
            f"<td>{_direction(r)}</td>"
            + num_cell(r.opening_debit, unit_note, src)
            + num_cell(r.opening_credit, unit_note, src)
            + num_cell(r.period_debit, unit_note, src)
            + num_cell(r.period_credit, unit_note, src)
            + num_cell(r.closing_debit, unit_note, src)
            + num_cell(r.closing_credit, unit_note, src)
            + "</tr>"
        )

    t = model.totals()
    total_row = (
        '<tr class="total"><td colspan="4">合计</td>'
        + num_cell(t["opening_debit"], unit_note) + num_cell(t["opening_credit"], unit_note)
        + num_cell(t["period_debit"], unit_note) + num_cell(t["period_credit"], unit_note)
        + num_cell(t["closing_debit"], unit_note) + num_cell(t["closing_credit"], unit_note)
        + "</tr>"
    )

    body = f"""
  <div class="card">
    <div class="toolbar">
      <input id="f-q" type="search" placeholder="搜索科目编码或名称…">
      <select id="f-dir"><option value="">全部方向</option><option>借</option><option>贷</option><option>平</option></select>
      <select id="f-lvl"><option value="">全部级次</option><option value="1">1级</option><option value="2">2级</option><option value="3">3级</option></select>
      <label><input id="f-nz" type="checkbox"> 只看有发生额/余额</label>
    </div>
    <table>
      <thead><tr>
        <th>科目编码</th><th>科目名称</th><th>级次</th><th>方向</th>
        <th>期初借方</th><th>期初贷方</th><th>本期借方</th><th>本期贷方</th><th>期末借方</th><th>期末贷方</th>
      </tr></thead>
      <tbody id="main-tbody">{''.join(rows_html)}{total_row}</tbody>
    </table>
    <p class="note">单位：{escape(src_note)}。合计行不参与筛选，始终可见。</p>
  </div>"""

    meta = [
        ("公司", model.meta.get("company", "—")),
        ("期间", model.meta.get("period", "—")),
        ("科目数", str(len(model.rows))),
        ("来源文件", model.meta.get("source_file", "—")),
        ("映射", f"{model.meta.get('mapping_name', '')} v{model.meta.get('mapping_version', '?')}"),
        ("生成时间", model.meta.get("generated_at", "—")),
    ]
    return html_page("科目余额筛选台账", meta, anchor_badges(_anchors_of(model)), body)
