"""视图 1：科目余额筛选台账。

解决的问题：金蝶/用友导出的余额表是给人核对用的，不是给"回答经营问题"用的。
v2：KPI 总览 + 一键筛选片（科目类别/级次/方向/非零）+ 搜索 + 点击排序 +
元/万元切换 + 打印。每个数字悬停可溯源。
"""

from __future__ import annotations

from html import escape

from ..model import StandardTB
from ..render import anchor_badges, html_page, kpi_cards, num_cell

CAT_NAMES = {"1": "资产", "2": "负债", "3": "共同", "4": "权益", "5": "成本", "6": "损益"}

BALANCE_JS = """
var state = { q: '', cat: '', dir: '', lvl: '', nz: false };
var TOTAL = document.querySelectorAll('#main-tbody tr[data-search]').length;
function applyF(){
  var n = 0;
  document.querySelectorAll('#main-tbody tr[data-search]').forEach(function(tr){
    var ok = tr.dataset.search.indexOf(state.q) >= 0
      && (!state.cat || tr.dataset.cat === state.cat)
      && (!state.dir || tr.dataset.dir === state.dir)
      && (!state.lvl || tr.dataset.level === state.lvl)
      && (!state.nz || tr.dataset.nz === '1');
    tr.style.display = ok ? '' : 'none';
    if (ok) n++;
  });
  document.getElementById('rowcount').textContent = '\\u663e\\u793a ' + n + ' / ' + TOTAL + ' \\u884c';
}
function bindChips(groupId, key){
  var box = document.getElementById(groupId);
  box.addEventListener('click', function(ev){
    var chip = ev.target.closest('.chip'); if (!chip) return;
    box.querySelectorAll('.chip').forEach(function(c){ c.classList.remove('on'); });
    chip.classList.add('on');
    state[key] = chip.dataset.v || '';
    applyF();
  });
}
['cat','dir','lvl'].forEach(function(k){ bindChips('g-' + k, k); });
document.getElementById('f-q').addEventListener('input', function(){ state.q = this.value.trim().toLowerCase(); applyF(); });
document.getElementById('f-nz').addEventListener('change', function(){ state.nz = this.checked; applyF(); });
applyF();
"""


def _direction(row) -> str:
    if abs(row.net_closing) < 1e-9:
        return "平"
    return "借" if row.net_closing > 0 else "贷"


def render_balance_ledger(model: StandardTB) -> str:
    leaf = bool(model.meta.get("leaf_only"))
    rows_html: list[str] = []
    cats_present: list[str] = []
    for r in model.rows:
        cat = r.code[0]
        if cat not in cats_present:
            cats_present.append(cat)
        nonzero = any(abs(v) > 1e-9 for v in (
            r.opening_debit, r.opening_credit, r.period_debit, r.period_credit, r.closing_debit, r.closing_credit))
        src = f"源: {r.src.get('file','')} / {r.src.get('sheet','')} 第{r.src.get('row','')}行"
        search = f"{r.code} {r.name}".lower()
        rows_html.append(
            f'<tr data-search="{escape(search)}" data-cat="{cat}" data-dir="{_direction(r)}" '
            f'data-level="{r.level}" data-nz="{"1" if nonzero else "0"}">'
            f'<td><code>{escape(r.code)}</code></td>'
            f'<td>{escape(r.name)}</td>'
            f'<td class="num" data-v="{r.level}.0">{r.level}</td>'
            f"<td>{_direction(r)}</td>"
            + num_cell(r.opening_debit, title=src) + num_cell(r.opening_credit, title=src)
            + num_cell(r.period_debit, title=src) + num_cell(r.period_credit, title=src)
            + num_cell(r.closing_debit, title=src) + num_cell(r.closing_credit, title=src)
            + "</tr>"
        )

    t = model.totals()
    total_row = (
        '<tr class="total"><td colspan="4">合计</td>'
        + num_cell(t["opening_debit"]) + num_cell(t["opening_credit"])
        + num_cell(t["period_debit"]) + num_cell(t["period_credit"])
        + num_cell(t["closing_debit"]) + num_cell(t["closing_credit"])
        + "</tr>"
    )

    # KPI：leaf_only（末级口径）时按科目类别计算资产/负债/净资产；否则展示合计类指标
    if leaf:
        asset = sum(r.net_closing for r in model.rows if r.code.startswith("1"))
        liab = -sum(r.net_closing for r in model.rows if r.code.startswith("2"))
        kpis = kpi_cards([
            {"label": "末级科目数", "value": str(len(model.rows))},
            {"label": "资产合计", "value": f"{asset / 1e4:,.2f} 万元"},
            {"label": "负债合计", "value": f"{liab / 1e4:,.2f} 万元"},
            {"label": "净资产", "value": f"{(asset - liab) / 1e4:,.2f} 万元", "tone": "good"},
            {"label": "本期发生额", "value": f"{t['period_debit'] / 1e4:,.2f} / {t['period_credit'] / 1e4:,.2f}",
             "caption": "借方 / 贷方（万元）"},
        ])
    else:
        kpis = kpi_cards([
            {"label": "科目数", "value": str(len(model.rows))},
            {"label": "期初借方合计", "value": f"{t['opening_debit'] / 1e4:,.2f} 万元"},
            {"label": "期初贷方合计", "value": f"{t['opening_credit'] / 1e4:,.2f} 万元"},
            {"label": "本期发生（借/贷）", "value": f"{t['period_debit'] / 1e4:,.2f} / {t['period_credit'] / 1e4:,.2f}"},
            {"label": "期末借方合计", "value": f"{t['closing_debit'] / 1e4:,.2f} 万元"},
        ])

    cat_chips = '<button class="chip on" data-v="">全部</button>' + "".join(
        f'<button class="chip" data-v="{c}">{CAT_NAMES.get(c, c)}类</button>' for c in sorted(cats_present))
    levels = sorted({r.level for r in model.rows})
    lvl_chips = '<button class="chip on" data-v="">全部</button>' + "".join(
        f'<button class="chip" data-v="{l}">{l} 级</button>' for l in levels)

    body = f"""
  {kpis}
  <div class="card">
    <div class="toolbar">
      <input id="f-q" type="search" placeholder="搜索科目编码或名称…">
      <div class="chip-group chips" id="g-cat"><span class="chip-label">类别</span>{cat_chips}</div>
      <div class="chip-group chips" id="g-lvl"><span class="chip-label">级次</span>{lvl_chips}</div>
      <div class="chip-group chips" id="g-dir"><span class="chip-label">期末方向</span>
        <button class="chip on" data-v="">全部</button>
        <button class="chip" data-v="借">借</button>
        <button class="chip" data-v="贷">贷</button>
        <button class="chip" data-v="平">平</button>
      </div>
      <label class="toggle"><input id="f-nz" type="checkbox"> 只看非零</label>
      <button class="btn" onclick="toggleUnit(this)">切换单位</button>
      <button class="btn" onclick="window.print()">打印 / 导出 PDF</button>
      <span class="rowcount" id="rowcount"></span>
    </div>
    <table>
      <thead><tr>
        <th class="sortable">科目编码<span class="arrow"></span></th>
        <th class="sortable">科目名称<span class="arrow"></span></th>
        <th class="sortable">级次<span class="arrow"></span></th>
        <th class="sortable">方向<span class="arrow"></span></th>
        <th class="sortable">期初借方<span class="arrow"></span></th>
        <th class="sortable">期初贷方<span class="arrow"></span></th>
        <th class="sortable">本期借方<span class="arrow"></span></th>
        <th class="sortable">本期贷方<span class="arrow"></span></th>
        <th class="sortable">期末借方<span class="arrow"></span></th>
        <th class="sortable">期末贷方<span class="arrow"></span></th>
      </tr></thead>
      <tbody id="main-tbody">{''.join(rows_html)}{total_row}</tbody>
    </table>
    <p class="note">单位：<span class="unit-tag">万元</span>（点"切换单位"改看元）。悬停数字查看源文件行级溯源；
    点击表头排序；合计行不参与筛选与排序。{("<b>本页为末级科目口径</b>（leaf_only），资产/负债/净资产按末级科目直接汇总。" if leaf else "")}</p>
  </div>"""

    meta = [
        ("公司", model.meta.get("company", "—")),
        ("期间", model.meta.get("period", "—")),
        ("来源文件", model.meta.get("source_file", "—")),
        ("映射", f"{model.meta.get('mapping_name', '')} v{model.meta.get('mapping_version', '?')}"),
        ("生成时间", model.meta.get("generated_at", "—")),
    ]
    return html_page("科目余额筛选台账", meta, anchor_badges(_anchors_of(model)), body, page_js=BALANCE_JS)


def _anchors_of(model: StandardTB):
    from ..model import AnchorResult

    return [AnchorResult(**a) for a in model.meta.get("anchor_results", [])]
