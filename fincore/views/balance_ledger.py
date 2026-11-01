"""视图 1：科目余额筛选台账。

解决的问题：金蝶/用友导出的余额表是给人核对用的，不是给"回答经营问题"用的。
v2：KPI 总览 + 一键筛选片 + 搜索 + 排序 + 元/万元切换 + 打印。
v3（财务习惯对齐）：Excel 式表头下拉筛选（文本列勾选值 / 数字列条件筛选）
+ 筛选方案：把整套筛选条件打包保存命名，一键套用（存浏览器本地）。
每个数字悬停可溯源。
"""

from __future__ import annotations

import json
from html import escape

from ..model import StandardTB
from ..render import anchor_badges, fmt, html_page, kpi_cards, num_cell

CAT_NAMES = {"1": "资产", "2": "负债", "3": "共同", "4": "权益", "5": "成本", "6": "损益"}

BALANCE_JS = r"""
// ================= 基础状态 =================
var state = { q: '', cat: '', dir: '', lvl: '', nz: false };
var colF = {};            // 列筛选：col -> {values:[...]} 或 {op:'gt|lt|eq|between', a, b, nonzero}
var COMPANY = __COMPANY__;
var TOTAL = document.querySelectorAll('#main-tbody tr[data-search]').length;
var COLIDX = {};
document.querySelectorAll('thead th[data-col]').forEach(function(th){
  COLIDX[th.dataset.col] = Array.prototype.indexOf.call(th.parentElement.children, th);
});
var TEXTCOLS = ['code', 'name', 'level', 'dir'];
var COL_LABEL = { code:'科目编码', name:'科目名称', level:'级次', dir:'方向',
  opening_debit:'期初借方', opening_credit:'期初贷方', period_debit:'本期借方',
  period_credit:'本期贷方', closing_debit:'期末借方', closing_credit:'期末贷方' };

function cellOf(tr, col){ return tr.children[COLIDX[col]]; }

// ================= 主筛选 =================
function colOk(tr){
  for (var col in colF){
    var f = colF[col], cell = cellOf(tr, col);
    if (f.values){
      if (f.values.indexOf(cell.textContent.trim()) < 0) return false;
    } else {
      var v = parseFloat(cell.dataset.v);
      if (f.nonzero && Math.abs(v) < 1e-9) return false;
      if (f.op === 'gt' && !(v > f.a)) return false;
      if (f.op === 'lt' && !(v < f.a)) return false;
      if (f.op === 'eq' && !(Math.abs(v - f.a) < 0.005)) return false;
      if (f.op === 'between' && !(v >= f.a && v <= f.b)) return false;
    }
  }
  return true;
}
function applyF(){
  var n = 0;
  document.querySelectorAll('#main-tbody tr[data-search]').forEach(function(tr){
    var ok = tr.dataset.search.indexOf(state.q) >= 0
      && (!state.cat || tr.dataset.cat === state.cat)
      && (!state.dir || tr.dataset.dir === state.dir)
      && (!state.lvl || tr.dataset.level === state.lvl)
      && (!state.nz || tr.dataset.nz === '1')
      && colOk(tr);
    tr.style.display = ok ? '' : 'none';
    if (ok) n++;
  });
  document.getElementById('rowcount').textContent = '显示 ' + n + ' / ' + TOTAL + ' 行';
  refreshFunnels();
}

// ================= 快捷筛选片 =================
function bindChips(groupId, key){
  var box = document.getElementById(groupId);
  box.addEventListener('click', function(ev){
    var chip = ev.target.closest('.chip'); if (!chip || chip.classList.contains('preset-chip')) return;
    box.querySelectorAll('.chip').forEach(function(c){ c.classList.remove('on'); });
    chip.classList.add('on');
    state[key] = chip.dataset.v || '';
    applyF();
  });
}
['cat','dir','lvl'].forEach(function(k){ bindChips('g-' + k, k); });
document.getElementById('f-q').addEventListener('input', function(){ state.q = this.value.trim().toLowerCase(); applyF(); });
document.getElementById('f-nz').addEventListener('change', function(){ state.nz = this.checked; applyF(); });

// ================= Excel 式列筛选 =================
function refreshFunnels(){
  document.querySelectorAll('th .fbtn').forEach(function(b){
    b.classList.toggle('on', !!colF[b.dataset.col]);
  });
}
function closePanels(){ document.querySelectorAll('.fdrop').forEach(function(d){ d.remove(); }); }
function stop(ev){ ev.stopPropagation(); }

function openPanel(col, btn){
  var old = document.getElementById('pd-' + col);
  if (old){ old.remove(); return; }
  closePanels();
  var d = document.createElement('div');
  d.className = 'fdrop'; d.id = 'pd-' + col;
  var r = btn.getBoundingClientRect();
  d.style.top = (r.bottom + 6 + window.scrollY) + 'px';
  d.style.left = Math.max(8, r.left + window.scrollX - 120) + 'px';
  var f = colF[col];

  if (TEXTCOLS.indexOf(col) >= 0){
    var counts = {};
    document.querySelectorAll('#main-tbody tr[data-search]').forEach(function(tr){
      var t = cellOf(tr, col).textContent.trim(); counts[t] = (counts[t] || 0) + 1;
    });
    var keys = Object.keys(counts).sort();
    var cur = f && f.values ? f.values.slice() : keys.slice();
    var html = '<input class="fsearch" placeholder="搜索值…">' +
      '<div class="flist">' + keys.map(function(k){
        return '<label><input type="checkbox" value="' + k.replace(/"/g,'&quot;') + '"' +
          (cur.indexOf(k) >= 0 ? ' checked' : '') + '> ' + k +
          '<span class="cnt">' + counts[k] + '</span></label>';
      }).join('') + '</div>' +
      '<div class="factions"><span class="hint">取消勾选即排除</span>' +
      '<span><button class="mini" data-act="all">全选</button> <button class="mini" data-act="ok">确定</button></span></div>';
    d.innerHTML = html;
    var list = d.querySelector('.flist');
    function applyValues(){
      var checked = Array.prototype.slice.call(list.querySelectorAll('input:checked')).map(function(i){ return i.value; });
      if (checked.length === keys.length){ delete colF[col]; } else { colF[col] = { values: checked }; }
      refreshFunnels(); applyF();
    }
    list.addEventListener('change', applyValues);
    d.querySelector('.fsearch').addEventListener('input', function(){
      var q = this.value.trim();
      list.querySelectorAll('label').forEach(function(lb){
        lb.style.display = lb.textContent.toLowerCase().indexOf(q.toLowerCase()) >= 0 ? '' : 'none';
      });
    });
    d.querySelector('[data-act="all"]').addEventListener('click', function(){
      list.querySelectorAll('input').forEach(function(i){ i.checked = true; }); applyValues();
    });
    d.querySelector('[data-act="ok"]').addEventListener('click', closePanels);
  } else {
    var op = f && f.op ? f.op : '';
    var a = f && f.a !== undefined ? f.a : '';
    var b = f && f.b !== undefined ? f.b : '';
    d.innerHTML =
      '<div class="fnum">' +
      '<div class="oprow"><select id="fop">' +
      '<option value=""' + (op === '' ? ' selected' : '') + '>无条件</option>' +
      '<option value="gt"' + (op === 'gt' ? ' selected' : '') + '>大于</option>' +
      '<option value="lt"' + (op === 'lt' ? ' selected' : '') + '>小于</option>' +
      '<option value="eq"' + (op === 'eq' ? ' selected' : '') + '>等于</option>' +
      '<option value="between"' + (op === 'between' ? ' selected' : '') + '>介于</option>' +
      '</select><span class="hint">单位：元</span></div>' +
      '<input type="number" id="fa" placeholder="金额（元）" value="' + a + '"' + (op === 'between' ? '' : ' style="display:' + (op ? '' : 'none') + '"') + '>' +
      '<input type="number" id="fb" placeholder="至（元）" value="' + b + '"' + (op === 'between' ? '' : ' style="display:none"') + '>' +
      '<label style="display:flex;gap:6px;align-items:center;"><input type="checkbox" id="fnz"' + (f && f.nonzero ? ' checked' : '') + '> 该列非零</label>' +
      '</div>' +
      '<div class="factions"><span class="hint">实时生效</span><button class="mini" data-act="clear">清除本列</button></div>';
    var sel = d.querySelector('#fop'), ia = d.querySelector('#fa'), ib = d.querySelector('#fb'), iz = d.querySelector('#fnz');
    function syncInputVis(){
      ia.style.display = sel.value && sel.value !== 'none' ? '' : 'none';
      ib.style.display = sel.value === 'between' ? '' : 'none';
      ia.placeholder = sel.value === 'between' ? '最小（元）' : '金额（元）';
    }
    function applyNum(){
      if (!sel.value && !iz.checked){ delete colF[col]; }
      else {
        colF[col] = { op: sel.value || 'none', a: parseFloat(ia.value || '0'), b: parseFloat(ib.value || '0'), nonzero: iz.checked };
        if (colF[col].op === 'none') delete colF[col].op;
      }
      refreshFunnels(); applyF();
    }
    sel.addEventListener('change', function(){ syncInputVis(); applyNum(); });
    ia.addEventListener('input', applyNum);
    ib.addEventListener('input', applyNum);
    iz.addEventListener('change', applyNum);
    d.querySelector('[data-act="clear"]').addEventListener('click', function(){
      delete colF[col]; sel.value = ''; ia.value = ''; ib.value = ''; iz.checked = false;
      syncInputVis(); refreshFunnels(); applyF();
    });
    syncInputVis();
  }
  document.body.appendChild(d);
  d.addEventListener('click', stop);
}
document.querySelectorAll('th .fbtn').forEach(function(b){
  b.addEventListener('click', function(ev){ ev.stopPropagation(); openPanel(b.dataset.col, b); });
});
document.addEventListener('click', function(ev){
  if (!ev.target.closest('.fdrop') && !ev.target.closest('.fbtn')) closePanels();
});

// ================= 筛选方案（保存/套用） =================
function storeKey(){ return 'finwb-filters:' + location.pathname.split('/').pop() + ':' + COMPANY; }
var memStore = null;
function loadPresets(){
  try { return JSON.parse(localStorage.getItem(storeKey()) || '[]'); } catch (e) { return memStore || []; }
}
function savePresets(list){
  memStore = list;
  try { localStorage.setItem(storeKey(), JSON.stringify(list)); } catch (e) { /* 无痕/受限环境退化为内存 */ }
}
function snapshot(){
  return { q: state.q, cat: state.cat, dir: state.dir, lvl: state.lvl, nz: state.nz, col: colF };
}
function clearAll(){
  state = { q:'', cat:'', dir:'', lvl:'', nz:false };
  colF = {};
  document.getElementById('f-q').value = '';
  document.getElementById('f-nz').checked = false;
  ['cat','dir','lvl'].forEach(function(k){
    var box = document.getElementById('g-' + k);
    box.querySelectorAll('.chip').forEach(function(c, i){ c.classList.toggle('on', i === 0); });
  });
  closePanels(); refreshFunnels(); applyF();
}
function applyPreset(p){
  clearAll();
  state.q = p.q || ''; document.getElementById('f-q').value = p.q || '';
  state.nz = !!p.nz; document.getElementById('f-nz').checked = !!p.nz;
  [['cat','g-cat'],['dir','g-dir'],['lvl','g-lvl']].forEach(function(pair){
    var v = p[pair[0]];
    if (v){
      var box = document.getElementById(pair[1]);
      box.querySelectorAll('.chip').forEach(function(c){ c.classList.toggle('on', (c.dataset.v || '') === v); });
      state[pair[0]] = v;
    }
  });
  colF = JSON.parse(JSON.stringify(p.col || {}));
  refreshFunnels(); applyF();
}
function renderPresets(){
  var box = document.getElementById('presets');
  var list = loadPresets();
  box.innerHTML = list.map(function(p, i){
    return '<button class="chip preset-chip" data-i="' + i + '">' + p.name.replace(/</g,'&lt;') +
           '<span class="x" data-x="' + i + '" title="删除">×</span></button>';
  }).join('') || '<span class="hint" style="font-size:12px;color:var(--muted)">暂无保存的方案</span>';
}
document.getElementById('psave').addEventListener('click', function(){
  var nameEl = document.getElementById('pname');
  var name = nameEl.value.trim();
  if (!name){ nameEl.focus(); nameEl.placeholder = '请先输入方案名称'; return; }
  var list = loadPresets();
  list = list.filter(function(p){ return p.name !== name; });
  list.unshift({ name: name, s: snapshot() });
  savePresets(list.slice(0, 12));
  nameEl.value = '';
  renderPresets();
});
document.getElementById('presets').addEventListener('click', function(ev){
  var x = ev.target.closest('[data-x]');
  if (x){
    var list = loadPresets(); list.splice(parseInt(x.dataset.x, 10), 1);
    savePresets(list); renderPresets(); ev.stopPropagation(); return;
  }
  var chip = ev.target.closest('.preset-chip');
  if (chip){ applyPreset(loadPresets()[parseInt(chip.dataset.i, 10)].s); }
});
document.getElementById('pclear').addEventListener('click', clearAll);

renderPresets();
applyF();
"""


def _direction(row) -> str:
    if abs(row.net_closing) < 1e-9:
        return "平"
    return "借" if row.net_closing > 0 else "贷"


def _th(label: str, col: str) -> str:
    return f'<th class="sortable" data-col="{col}">{label}<span class="arrow"></span><button class="fbtn" data-col="{col}" title="列筛选">▽</button></th>'


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

    wan = 1e4
    if leaf:
        asset = sum(r.net_closing for r in model.rows if r.code.startswith("1"))
        liab = -sum(r.net_closing for r in model.rows if r.code.startswith("2"))
        kpis = kpi_cards([
            {"label": "末级科目数", "value": str(len(model.rows))},
            {"label": "资产合计", "value_yuan": asset},
            {"label": "负债合计", "value_yuan": liab},
            {"label": "净资产", "value_yuan": asset - liab, "tone": "good"},
            {"label": "本期发生额（借/贷）",
             "value_html": (f'<span class="v-num" data-v="{t["period_debit"]:.2f}">{fmt(t["period_debit"])}</span> / '
                            f'<span class="v-num" data-v="{t["period_credit"]:.2f}">{fmt(t["period_credit"])}</span>'
                            ' <span class="v-unit">万元</span>'),
             "caption": "借方 / 贷方"},
        ])
    else:
        kpis = kpi_cards([
            {"label": "科目数", "value": str(len(model.rows))},
            {"label": "期初借方合计", "value_yuan": t["opening_debit"]},
            {"label": "期初贷方合计", "value_yuan": t["opening_credit"]},
            {"label": "本期发生（借/贷）",
             "value_html": (f'<span class="v-num" data-v="{t["period_debit"]:.2f}">{fmt(t["period_debit"])}</span> / '
                            f'<span class="v-num" data-v="{t["period_credit"]:.2f}">{fmt(t["period_credit"])}</span>'
                            ' <span class="v-unit">万元</span>'),
             "caption": "借方 / 贷方"},
            {"label": "期末借方合计", "value_yuan": t["closing_debit"]},
        ])

    cat_chips = '<button class="chip on" data-v="">全部</button>' + "".join(
        f'<button class="chip" data-v="{c}">{CAT_NAMES.get(c, c)}类</button>' for c in sorted(cats_present))
    levels = sorted({r.level for r in model.rows})
    lvl_chips = '<button class="chip on" data-v="">全部</button>' + "".join(
        f'<button class="chip" data-v="{l}">{l} 级</button>' for l in levels)

    company_js = json.dumps(model.meta.get("company", ""), ensure_ascii=True)
    page_js = BALANCE_JS.replace("__COMPANY__", company_js)

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
      <span class="rowcount" id="rowcount"></span>
    </div>
    <div class="toolbar">
      <span class="chip-label">筛选方案</span>
      <div class="chip-group chips" id="presets"></div>
      <input id="pname" class="pname" placeholder="方案名称，如：固定资产">
      <button class="btn" id="psave">保存当前筛选</button>
      <button class="btn" id="pclear">清除全部筛选</button>
      <button class="btn" onclick="toggleUnit(this)">切换单位</button>
      <button class="btn" onclick="window.print()">打印 / 导出 PDF</button>
    </div>
    <table>
      <thead><tr>
        {_th("科目编码", "code")}
        {_th("科目名称", "name")}
        {_th("级次", "level")}
        {_th("方向", "dir")}
        {_th("期初借方", "opening_debit")}
        {_th("期初贷方", "opening_credit")}
        {_th("本期借方", "period_debit")}
        {_th("本期贷方", "period_credit")}
        {_th("期末借方", "closing_debit")}
        {_th("期末贷方", "closing_credit")}
      </tr></thead>
      <tbody id="main-tbody">{''.join(rows_html)}{total_row}</tbody>
    </table>
    <p class="note">单位：<span class="unit-tag">万元</span>（KPI 卡与明细同步切换）。悬停数字查看源文件行级溯源；
    点击表头排序、点表头的 ▽ 做 Excel 式列筛选（数字列条件单位为元）；筛选方案保存在本机浏览器，
    下次打开仍可用。合计行不参与筛选与排序。{("<b>本页为末级科目口径</b>（leaf_only），资产/负债/净资产按末级科目直接汇总。" if leaf else "")}</p>
  </div>"""

    meta = [
        ("公司", model.meta.get("company", "—")),
        ("期间", model.meta.get("period", "—")),
        ("来源文件", model.meta.get("source_file", "—")),
        ("映射", f"{model.meta.get('mapping_name', '')} v{model.meta.get('mapping_version', '?')}"),
        ("生成时间", model.meta.get("generated_at", "—")),
    ]
    return html_page("科目余额筛选台账", meta, anchor_badges(_anchors_of(model)), body, page_js=page_js)


def _anchors_of(model: StandardTB):
    from ..model import AnchorResult

    return [AnchorResult(**a) for a in model.meta.get("anchor_results", [])]
