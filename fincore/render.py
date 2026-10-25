"""自包含 HTML 渲染层。

架构红线：单文件、零外链（不引任何 CDN/字体/JS 库），数据本地渲染不出网。
表格规范参考 workspace 的 financial-tables 技能：数字右对齐、千分位、
合计行加粗、表头 sticky、零值显 —。

v2 设计（2026-10）：金融工作台风格 —— 深色顶栏 + KPI 指标卡 + 卡片分区 +
一键筛选片 + 点击排序 + 元/万元单位切换 + 打印样式。
所有数字单元格带 data-v（元），单位切换与排序都基于它，服务端仍渲染
万元文本（无 JS 环境下可直接阅读/打印）。
"""

from __future__ import annotations

from html import escape

_WAN = 10000.0


def fmt(value_yuan: float) -> str:
    """默认展示：万元，千分位，零值显 —。"""
    if abs(value_yuan) < 1e-9:
        return "—"
    return f"{value_yuan / _WAN:,.2f}"


def fmt_wan(value_yuan: float, unit: str = "元") -> str:
    """兼容旧调用。入参恒为元（标准模型口径）。"""
    return fmt(value_yuan)


def fmt_pct(part: float, total: float) -> str:
    if abs(total) < 1e-9:
        return "—"
    return f"{part / total * 100:.1f}%"


def num_cell(value: float, unit: str = "元", title: str = "", bar_pct: float | None = None) -> str:
    """数字单元格：右对齐、负数标色、data-v 存元值（供排序/单位切换）、悬停溯源。

    bar_pct: 0-100，给单元格底部加比例条（用于税费/执行的视觉对比）。
    """
    cls = "num neg" if value < -1e-9 else "num"
    tip = f' title="{escape(title)}"' if title else ""
    bar = f'<i class="cellbar" style="width:{max(0.0, min(bar_pct, 100.0)):.0f}%"></i>' if bar_pct else ""
    return f'<td class="{cls}" data-v="{value:.2f}"{tip}>{fmt(value)}{bar}</td>'


def text_cell(text: str) -> str:
    return f"<td>{escape(text)}</td>"


def anchor_badges(results) -> str:
    items = "".join(
        f'<span class="anchor {a.status.lower()}">{a.badge} {escape(a.name)} {a.status}</span>'
        for a in results
    )
    return f'<div class="anchors">{items}</div>'


def kpi_cards(items: list[dict]) -> str:
    """KPI 指标卡行。items: [{label, value, caption?, tone?}]，tone: good/bad/neutral。"""
    cards = []
    for it in items:
        tone = f' {it["tone"]}' if it.get("tone") else ""
        cap = f'<div class="kpi-cap">{escape(it["caption"])}</div>' if it.get("caption") else ""
        cards.append(
            f'<div class="kpi{tone}"><div class="kpi-label">{escape(it["label"])}</div>'
            f'<div class="kpi-value">{escape(it["value"])}</div>{cap}</div>'
        )
    return f'<div class="kpis">{"".join(cards)}</div>'


BASE_CSS = """
:root { --ink:#0f1c33; --muted:#5c6b84; --line:#e3e8f0; --bg:#eef1f6; --card:#ffffff;
        --accent:#1a56db; --accent-soft:#e8effc; --navy:#0e2a5c; --navy2:#1c4390;
        --neg:#c02626; --pos:#0f7a3d; --amber:#b45309; }
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; padding:0 0 40px; background:var(--bg); color:var(--ink);
       font:14px/1.65 "PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif; }
.wrap { max-width:1360px; margin:0 auto; padding:0 24px; }

/* ---- 顶栏 ---- */
.appbar { background:linear-gradient(135deg,var(--navy) 0%,var(--navy2) 100%); color:#fff;
          padding:22px 24px 20px; margin-bottom:18px; }
.appbar .wrap { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 18px; padding:0; }
.appbar h1 { font-size:21px; margin:0; letter-spacing:.5px; }
.appbar .sub { color:#b9c8e6; font-size:12.5px; }
.appbar .meta { display:flex; flex-wrap:wrap; gap:4px 22px; width:100%; margin-top:10px;
                color:#d7e1f5; font-size:12.5px; }
.appbar .meta b { color:#fff; font-weight:600; }
.anchors { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.anchor { font-size:11.5px; padding:2px 11px; border-radius:99px; border:1px solid rgba(255,255,255,.28);
          color:#e6edfa; background:rgba(255,255,255,.08); }
.anchor.pass { border-color:#7fd3a4; background:rgba(46,160,103,.25); color:#c9f2da; }
.anchor.fail { border-color:#f3a6a6; background:rgba(220,60,60,.3); color:#ffd9d9; }
.anchor.skipped { color:#aebdd9; }

/* ---- KPI 卡 ---- */
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px 12px;
       box-shadow:0 1px 3px rgba(15,28,51,.05); }
.kpi-label { font-size:12px; color:var(--muted); }
.kpi-value { font-size:22px; font-weight:700; margin-top:2px; font-variant-numeric:tabular-nums; letter-spacing:.2px; }
.kpi-cap { font-size:11.5px; color:var(--muted); margin-top:2px; }
.kpi.good .kpi-value { color:var(--pos); }
.kpi.bad .kpi-value { color:var(--neg); }

/* ---- 卡片与工具栏 ---- */
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:16px 18px; margin-bottom:16px; box-shadow:0 1px 3px rgba(15,28,51,.05); }
h2 { font-size:14px; margin:0 0 10px; color:var(--ink); font-weight:700;
     display:flex; align-items:center; gap:8px; }
h2::before { content:""; width:4px; height:14px; border-radius:2px; background:var(--accent); }
.toolbar { display:flex; flex-wrap:wrap; gap:8px 14px; align-items:center; margin-bottom:12px; }
.toolbar input[type="search"] { border:1px solid var(--line); border-radius:8px; padding:7px 12px;
        font-size:13px; background:#fff; width:230px; outline:none; }
.toolbar input[type="search"]:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
.chips { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.chip-group { display:flex; flex-wrap:wrap; gap:6px; }
.chip-label { font-size:12px; color:var(--muted); margin-right:2px; align-self:center; }
.chip { border:1px solid var(--line); background:#fff; color:var(--muted); border-radius:99px;
        padding:4px 13px; font-size:12.5px; cursor:pointer; user-select:none; transition:all .12s; }
.chip:hover { border-color:var(--accent); color:var(--accent); }
.chip.on { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
.toggle { display:inline-flex; align-items:center; gap:5px; font-size:12.5px; color:var(--muted); cursor:pointer; }
.toggle input { accent-color:var(--accent); }
.btn { border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:8px;
       padding:6px 14px; font-size:12.5px; cursor:pointer; }
.btn:hover { border-color:var(--accent); color:var(--accent); }
.rowcount { font-size:12px; color:var(--muted); margin-left:auto; }
.unit-tag { color:var(--accent); font-weight:600; }

/* ---- 表格 ---- */
table { border-collapse:separate; border-spacing:0; width:100%; background:#fff; }
thead th { position:sticky; top:0; background:#f2f5fa; border-bottom:2px solid var(--line);
           padding:9px 10px; font-size:12px; text-align:left; white-space:nowrap; z-index:1;
           color:var(--muted); font-weight:600; }
th.sortable { cursor:pointer; }
th.sortable:hover { color:var(--accent); }
th.sorted { color:var(--accent); }
th .arrow { font-size:10px; margin-left:2px; }
td { border-bottom:1px solid var(--line); padding:7px 10px; font-size:13px; vertical-align:top; }
tbody tr:nth-child(even) td { background:#fafbfd; }
tbody tr:hover td { background:#f0f5ff; }
td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; position:relative; }
td.neg { color:var(--neg); }
td .cellbar { display:block; position:absolute; left:6px; right:6px; bottom:3px; height:3px;
              border-radius:2px; background:var(--accent-soft); }
td .cellbar { width:auto; }
tr.total td { font-weight:700; border-top:2px solid var(--ink); background:#f6f8fc !important; }
code { background:#eef2f8; padding:1px 7px; border-radius:5px; font-size:11.5px; color:var(--navy); }
.note { color:var(--muted); font-size:12px; margin-top:10px; }
.foot { text-align:center; color:#9aa7bd; font-size:11.5px; margin-top:22px; }

/* ---- 进度条 ---- */
.pwrap { display:flex; align-items:center; gap:8px; min-width:130px; }
.pbar { flex:1; height:6px; background:var(--line); border-radius:4px; overflow:hidden; }
.pbar i { display:block; height:100%; border-radius:4px; background:var(--accent); }
.pbar i.low { background:var(--neg); }
.pval { font-size:12px; font-variant-numeric:tabular-nums; min-width:42px; text-align:right; }

@media print {
  body { background:#fff; padding:0; }
  .appbar { background:var(--navy) !important; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  .toolbar, .btn { display:none !important; }
  .card { box-shadow:none; break-inside:avoid; }
  thead th { position:static; }
}
"""

# 共享交互：表头排序 + 元/万元单位切换。零值恒显 —。
SORT_UNIT_JS = """
function _fv(v){ return Math.abs(v)<1e-9 ? '\\u2014' : v; }
function _fmtW(v){ return _fv(v)==='\\u2014' ? '\\u2014' : (v/10000).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function _fmtY(v){ return _fv(v)==='\\u2014' ? '\\u2014' : v.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}); }
var unitWan = true;
function toggleUnit(btn){
  unitWan = !unitWan;
  document.querySelectorAll('td.num[data-v]').forEach(function(td){
    var v = parseFloat(td.dataset.v);
    td.childNodes[0].textContent = unitWan ? _fmtW(v) : _fmtY(v);
  });
  document.querySelectorAll('.unit-tag').forEach(function(e){ e.textContent = unitWan ? '万元' : '元'; });
  if (btn) btn.textContent = unitWan ? '切换单位' : '切换单位';
}
function sortTable(th){
  var table = th.closest('table'), tbody = table.querySelector('tbody');
  var idx = Array.prototype.indexOf.call(th.parentElement.children, th);
  var dir = th.dataset.dir === 'asc' ? -1 : 1;
  table.querySelectorAll('th').forEach(function(x){ x.classList.remove('sorted'); delete x.dataset.dir;
    var a = x.querySelector('.arrow'); if (a) a.textContent = ''; });
  th.dataset.dir = dir === 1 ? 'asc' : 'desc';
  th.classList.add('sorted');
  var ar = th.querySelector('.arrow'); if (ar) ar.textContent = dir === 1 ? '\\u25b2' : '\\u25bc';
  var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr')).filter(function(tr){ return !tr.classList.contains('total'); });
  rows.sort(function(a,b){
    var ca = a.children[idx], cb = b.children[idx];
    var va = ca.dataset && ca.dataset.v !== undefined ? parseFloat(ca.dataset.v) : null;
    var vb = cb.dataset && cb.dataset.v !== undefined ? parseFloat(cb.dataset.v) : null;
    var r;
    if (va !== null && vb !== null) r = va - vb;
    else r = ca.textContent.trim().localeCompare(cb.textContent.trim(), 'zh');
    return r * dir;
  }).forEach(function(tr){ tbody.insertBefore(tr, tbody.querySelector('tr.total')); });
}
document.querySelectorAll('th.sortable').forEach(function(th){ th.addEventListener('click', function(){ sortTable(th); }); });
"""


def html_page(title: str, meta_items: list[tuple[str, str]], anchors_html: str, body: str,
              page_js: str = "") -> str:
    """拼装整页。meta_items = [(标签, 值)]。"""
    meta_html = "".join(f"<span>{escape(k)}：<b>{escape(v)}</b></span>" for k, v in meta_items)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{BASE_CSS}</style>
</head>
<body>
<header class="appbar">
  <div class="wrap">
    <h1>{escape(title)}</h1>
    <span class="sub">fin-workbench · 数据本地渲染不出网</span>
    <div class="meta">{meta_html}</div>
    {anchors_html}
  </div>
</header>
<div class="wrap">
  {body}
  <p class="foot">由 fincore 确定性内核生成 · 每个数字悬停可溯源至源文件行 · 锚点校验通过后方生成本页</p>
</div>
<script>{SORT_UNIT_JS}{page_js}</script>
</body>
</html>"""
