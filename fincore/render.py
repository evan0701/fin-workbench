"""自包含 HTML 渲染层。

架构红线：单文件、零外链（不引任何 CDN/字体/JS 库），数据本地渲染不出网。
表格规范参考 workspace 的 financial-tables 技能：数字右对齐、千分位、
合计行加粗、表头 sticky、零值显 —。
"""

from __future__ import annotations

from html import escape


def fmt_wan(value_yuan: float, unit: str = "元") -> str:
    """格式化为万元展示。入参恒为元（标准模型口径），零值显示 —。unit 仅用于注释。"""
    if abs(value_yuan) < 1e-9:
        return "—"
    return f"{value_yuan / 10000:,.2f}"


def fmt_pct(part: float, total: float) -> str:
    if abs(total) < 1e-9:
        return "—"
    return f"{part / total * 100:.1f}%"


def num_cell(value: float, unit: str = "元", title: str = "") -> str:
    """数字单元格：右对齐、负数标色、title 带溯源。"""
    cls = "num neg" if value < -1e-9 else "num"
    tip = f' title="{escape(title)}"' if title else ""
    return f'<td class="{cls}"{tip}>{fmt_wan(value, unit)}</td>'


def anchor_badges(results) -> str:
    items = "".join(
        f'<span class="anchor {a.status.lower()}">{a.badge} {escape(a.name)} {a.status}</span>'
        for a in results
    )
    return f'<div class="anchors">{items}</div>'


BASE_CSS = """
:root { --ink:#1a2332; --muted:#6b7686; --line:#dde3ec; --bg:#f6f8fb; --card:#ffffff;
        --accent:#0f5fd1; --neg:#c23434; --green:#1a7f4e; --amber:#b9791b; }
* { box-sizing:border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--ink);
       font:14px/1.6 "PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:15px; margin:22px 0 8px; color:var(--muted); font-weight:600; }
.wrap { max-width:1280px; margin:0 auto; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-bottom:14px; }
.meta { display:flex; flex-wrap:wrap; gap:8px 28px; color:var(--muted); font-size:12.5px; margin-top:6px; }
.meta b { color:var(--ink); font-weight:600; }
.anchors { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.anchor { font-size:12px; padding:2px 10px; border-radius:99px; border:1px solid var(--line); background:#fff; }
.anchor.pass { border-color:#bfe3cd; background:#effaf3; color:var(--green); }
.anchor.fail { border-color:#f3c1c1; background:#fdf1f1; color:var(--neg); }
.anchor.skipped { color:var(--muted); }
.toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:10px; }
.toolbar input, .toolbar select { border:1px solid var(--line); border-radius:6px; padding:5px 9px; font-size:13px; background:#fff; }
.toolbar input { width:220px; }
.toolbar input[type="checkbox"] { width:auto; accent-color:var(--accent); }
.toolbar label { font-size:12.5px; color:var(--muted); display:flex; align-items:center; gap:4px; }
table { border-collapse:collapse; width:100%; background:#fff; }
thead th { position:sticky; top:0; background:#eef2f8; border-bottom:2px solid var(--line);
           padding:8px 10px; font-size:12.5px; text-align:left; white-space:nowrap; z-index:1; }
td { border-bottom:1px solid var(--line); padding:7px 10px; font-size:13px; }
tbody tr:hover { background:#f4f8ff; }
td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
td.neg { color:var(--neg); }
tr.total td { font-weight:700; border-top:2px solid var(--ink); background:#fafbfd; }
code { background:#eef2f8; padding:1px 6px; border-radius:4px; font-size:12px; }
.note { color:var(--muted); font-size:12px; margin-top:8px; }
"""

FILTER_JS = """
function filterTable() {
  const q = (document.getElementById('f-q')?.value || '').trim().toLowerCase();
  const dir = document.getElementById('f-dir')?.value || '';
  const lvl = document.getElementById('f-lvl')?.value || '';
  const nz  = document.getElementById('f-nz')?.checked;
  document.querySelectorAll('#main-tbody tr').forEach(tr => {
    const show = tr.dataset.search.includes(q)
      && (!dir || tr.dataset.dir === dir)
      && (!lvl || tr.dataset.level === lvl)
      && (!nz || tr.dataset.nonzero === '1');
    tr.style.display = show ? '' : 'none';
  });
}
['f-q','f-dir','f-lvl','f-nz'].forEach(id => {
  const el = document.getElementById(id);
  if (el) { el.addEventListener('input', filterTable); el.addEventListener('change', filterTable); }
});
"""


def html_page(title: str, meta_items: list[tuple[str, str]], anchors_html: str, body: str) -> str:
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
<div class="wrap">
  <h1>{escape(title)}</h1>
  <div class="card">
    <div class="meta">{meta_html}</div>
    {anchors_html}
  </div>
  {body}
  <p class="note">数据本地渲染，不出网 · 由 fincore 生成 · 每个数字的溯源信息见悬停提示</p>
</div>
<script>{FILTER_JS}</script>
</body>
</html>"""
