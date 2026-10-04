"""从星澜虚构数据集生成演示材料（全部虚构数据，可安全开源）。

产物：
1. demo/示例导出/科目余额表_2025-08_乱格式.xlsx —— 模拟金蝶导出的"难用"余额表：
   标题占 3 行、编码名称挤一列、借贷分 6 列、列名带全角空格、末尾合计与制表行。
2. demo/示例导出/科目余额表_2025-09_乱格式.xlsx —— 同上（与 8 月衔接）。
3. demo/统计台账模板/统计月度台账_模板.xlsx —— 铸造演示用的空白目标表。
4. demo/统计台账模板/统计月度台账_2025-08_人工版.xlsx —— 回填考试的"标准答案"。

口径（虚构演示口径，详见 forged/stat-monthly-ledger/references/口径说明.md）：
- 余额表金额单位：元（星澜数据为万元，×10000 换算）。
- 应交税费子科目期末余额 = 已计提未缴纳：增值税 = 6%×当月收入；附加税 = 12%×增值税；
  个税 = 0.5%×(销售+管理+研发费用)；企业所得税按季计提（季末月 = 25%×当季净利润）。
  本月实缴（本期借方发生）= 上月计提额。
- 损益类科目期初/期末余额为 0（当月已结转），只保留本期发生额。
- 权益端用星澜自身的资产/负债总额强制配平，吸收分项展示的舍入漂移。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

DEFAULT_STARLAN = "/Users/evan/.zcode/workspace/default/finviz-test-data/星澜科技-财务测试数据集-v2.xlsx"
REPO = Path(__file__).resolve().parent.parent
OUT_EXPORT = REPO / "demo" / "示例导出"
OUT_TEMPLATE = REPO / "demo" / "统计台账模板"

CASH_FLOOR = 50_000.0  # 1001 库存现金固定 5 万，其余进银行存款
MONTHS = ["2025-08", "2025-09"]

# 统计台账目标表布局（虚构演示）：cell 为 C 列目标单元格
LEDGER_LABELS = [
    ("营业收入", "万元", "C5", "direct", "6001", "period_credit"),
    ("营业成本", "万元", "C6", "direct", "6401", "period_debit"),
    ("税金及附加", "万元", "C7", "direct", "6403", "period_debit"),
    ("销售费用", "万元", "C8", "direct", "6601", "period_debit"),
    ("管理费用", "万元", "C9", "direct", "6602", "period_debit"),
    ("研发费用", "万元", "C10", "direct", "6603", "period_debit"),
    ("财务费用", "万元", "C11", "direct", "6604", "period_debit"),
    ("营业利润", "万元", "C12", "derived", "operating_profit", ""),
    ("所得税费用（计提）", "万元", "C13", "direct", "6801", "period_debit"),
    ("净利润", "万元", "C14", "derived", "net_profit", ""),
    ("实缴税费合计（当月缴纳）", "万元", "C15", "derived", "tax_paid", ""),
    ("资产总额", "万元", "C16", "derived", "asset_total", ""),
    ("负债合计", "万元", "C17", "derived", "liab_total", ""),
    ("净资产", "万元", "C18", "derived", "equity_total", ""),
]

TAX_SUB_NAMES = {
    "222101": "应交税费—应交增值税",
    "222102": "应交税费—应交企业所得税",
    "222103": "应交税费—应交个人所得税",
    "222104": "应交税费—城建税及附加",
}

# 星澜"资产负债表"行（0 基索引）→ (科目编码, 科目名称, 行内索引, 是否贷方余额)。
# 1001 库存现金特殊：固定 5 万，剩余进 1002；2211/2221 系列单列处理。
BS_MAPPING = [
    ("1101", "交易性金融资产", 2, False),
    ("1122", "应收账款", 3, False),
    ("1123", "预付款项", 4, False),
    ("1221", "其他应收款", 5, False),
    ("1405", "库存商品", 6, False),
    ("1601", "固定资产", 8, False),
    ("1701", "无形资产", 9, False),
    ("1799", "其他非流动资产", 10, False),
    ("2001", "短期借款", 13, True),
    ("2202", "应付账款", 16, True),
    ("2231", "其他应付款", 18, True),
    ("2501", "长期借款", 14, True),
]


def _read_starlan(path: str) -> tuple[dict, dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    bs = {r[0]: r for r in wb["资产负债表"].iter_rows(min_row=4, max_col=29, values_only=True) if r[0]}
    pl = {r[1]: r for r in wb["月度损益"].iter_rows(min_row=5, max_col=15, values_only=True) if r[1]}
    wb.close()
    return bs, pl


def _month_pl(pl: dict, month: str) -> dict:
    """单月损益口径（元）。"""
    p = pl[month]
    income = (p[2] or 0) * 1e4
    cost = (p[3] or 0) * 1e4
    sell, admin, rd, fin = ((p[i] or 0) * 1e4 for i in (6, 7, 8, 9))
    income_tax = (p[11] or 0) * 1e4
    vat = 0.06 * income
    operating = income - cost - 0.12 * vat - (sell + admin + rd + fin)
    return {
        "income": income, "cost": cost, "sell": sell, "admin": admin, "rd": rd, "fin": fin,
        "income_tax": income_tax, "sga": sell + admin + rd, "vat": vat,
        "operating": operating, "net": operating - income_tax,
    }


def _quarter_net(pl: dict, month: str) -> float:
    """该月所属季度的累计净利润（元）。"""
    m0 = int(month[5:7])
    q_start = (m0 - 1) // 3 * 3 + 1
    return sum(_month_pl(pl, f"{month[:4]}-{i:02d}")["net"] for i in range(q_start, q_start + 3) if f"{month[:4]}-{i:02d}" in pl)


def _tax_closings(pl: dict, month: str) -> dict[str, float]:
    """某月应交税费子科目期末余额（元）= 已计提未缴纳。"""
    d = _month_pl(pl, month)
    m0 = int(month[5:7])
    cit = 0.25 * _quarter_net(pl, month) if m0 % 3 == 0 else 0.0
    return {
        "222101": 0.06 * d["income"],
        "222102": cit,
        "222103": 0.005 * d["sga"],
        "222104": 0.12 * d["vat"],
    }


def _snapshot(bs: dict, pl: dict, month: str) -> dict[str, dict]:
    """某月资产负债科目的期末快照：code → {name, debit, credit}（元）。

    税费子科目与应付职工薪酬在此统一计算，保证"上月文件期末 = 本月文件期初"逐格一致。
    """
    b = bs[month]
    tax = _tax_closings(pl, month)
    tax_total = sum(tax.values())
    pool = (b[17] or 0) * 1e4
    salary = pool - tax_total
    if salary < 0:  # 虚构数据兜底：计提超出池子时按比例压缩税费
        tax = {c: v * pool * 0.8 / tax_total for c, v in tax.items()}
        tax_total = sum(tax.values())
        salary = pool - tax_total

    snap: dict[str, dict] = {}
    cash = min(CASH_FLOOR, (b[1] or 0) * 1e4)
    snap["1001"] = {"name": "库存现金", "debit": cash, "credit": 0.0}
    snap["1002"] = {"name": "银行存款", "debit": (b[1] or 0) * 1e4 - cash, "credit": 0.0}
    for code, name, idx, is_credit in BS_MAPPING:
        v = (b[idx] or 0) * 1e4
        snap[code] = {"name": name, "debit": 0.0 if is_credit else v, "credit": v if is_credit else 0.0}
    snap["2211"] = {"name": "应付职工薪酬", "debit": 0.0, "credit": max(salary, 0.0)}
    snap["2221"] = {"name": "应交税费", "debit": 0.0, "credit": tax_total}
    for code, name in TAX_SUB_NAMES.items():
        snap[code] = {"name": name, "debit": 0.0, "credit": tax[code]}
    lt_other = ((b[20] or 0) - (b[14] or 0)) * 1e4
    if lt_other > 0.005:
        snap["2701"] = {"name": "长期应付款", "debit": 0.0, "credit": lt_other}
    # 权益：未分配利润作为配平塞数（资产分项合计 − 负债分项合计 − 固定权益项），
    # 分项展示的舍入漂移自动被吸收，保证期末借贷严格平衡
    asset_total = sum(v["debit"] - v["credit"] for k, v in snap.items() if k.startswith("1"))
    liab_total = sum(v["credit"] - v["debit"] for k, v in snap.items() if k.startswith("2"))
    equity_fixed = (b[22] + b[23] + b[24]) * 1e4
    retained = asset_total - liab_total - equity_fixed
    snap["4001"] = {"name": "实收资本", "debit": 0.0, "credit": b[22] * 1e4}
    snap["4002"] = {"name": "资本公积", "debit": 0.0, "credit": b[23] * 1e4}
    snap["4101"] = {"name": "盈余公积", "debit": 0.0, "credit": b[24] * 1e4}
    snap["4103"] = {"name": "未分配利润",
                    "debit": abs(retained) if retained < 0 else 0.0,
                    "credit": retained if retained >= 0 else 0.0}
    return snap


def build_tb(month: str, starlan: str) -> list[dict]:
    """构造某月科目余额表行（元）。期初 = 上月快照；损益类只有发生额。"""
    bs, pl = _read_starlan(starlan)
    closing_snap = _snapshot(bs, pl, month)
    y, m = int(month[:4]), int(month[5:7])
    if m == 1:
        raise ValueError("demo 生成器不支持跨年上月的演示场景")
    opening_snap = _snapshot(bs, pl, f"{y}-{m - 1:02d}")
    cur = _month_pl(pl, month)

    rows: list[dict] = []
    for code, snap in closing_snap.items():
        od = opening_snap.get(code, {}).get("debit", 0.0)
        oc = opening_snap.get(code, {}).get("credit", 0.0)
        pd_val = pc_val = 0.0
        if code.startswith("2221") and code != "2221":
            pd_val = max(oc - od, 0.0)  # 本月实缴 = 上月计提额
        rows.append({
            "code": code, "name": snap["name"], "level": max(1, len(code) // 2 - 1),
            "opening_debit": round(od, 2), "opening_credit": round(oc, 2),
            "period_debit": round(pd_val, 2), "period_credit": round(pc_val, 2),
            "closing_debit": round(snap["debit"], 2), "closing_credit": round(snap["credit"], 2),
            "src": {},
        })
    # 2221 根科目：期初/期末 = 子科目合计，本期借方 = 子科目实缴合计
    root = next(r for r in rows if r["code"] == "2221")
    subs = [r for r in rows if r["code"].startswith("2221") and r["code"] != "2221"]
    root["opening_debit"] = round(sum(s["opening_debit"] for s in subs), 2)
    root["opening_credit"] = round(sum(s["opening_credit"] for s in subs), 2)
    root["period_debit"] = round(sum(s["period_debit"] for s in subs), 2)
    root["closing_credit"] = round(sum(s["closing_credit"] for s in subs), 2)

    # 损益类（期初/期末为 0）
    def pl_row(code: str, name: str, debit: float, credit: float):
        rows.append({"code": code, "name": name, "level": max(1, len(code) // 2 - 1),
                     "opening_debit": 0.0, "opening_credit": 0.0,
                     "period_debit": round(debit, 2), "period_credit": round(credit, 2),
                     "closing_debit": 0.0, "closing_credit": 0.0, "src": {}})

    pl_row("6001", "主营业务收入", 0.0, cur["income"])
    pl_row("6401", "主营业务成本", cur["cost"], 0.0)
    pl_row("6403", "税金及附加", 0.12 * cur["vat"], 0.0)
    pl_row("6601", "销售费用", cur["sell"], 0.0)
    pl_row("6602", "管理费用", cur["admin"], 0.0)
    pl_row("6603", "研发费用", cur["rd"], 0.0)
    pl_row("6604", "财务费用", cur["fin"], 0.0)
    pl_row("6801", "所得税费用", cur["income_tax"], 0.0)

    # 平衡断言：期初/期末借贷各自相等（容差 0.01 元）
    for side, f1, f2 in (("期初", "opening_debit", "opening_credit"), ("期末", "closing_debit", "closing_credit")):
        d, c = sum(r[f1] for r in rows), sum(r[f2] for r in rows)
        if abs(d - c) > 0.01:
            raise AssertionError(f"{month} {side}借贷不平衡: 借{d:.2f} 贷{c:.2f} 差{d - c:+.2f}")

    rows.sort(key=lambda r: r["code"])
    return rows


def derived(rows: list[dict], name: str) -> float:
    """台账衍生指标（万元）。与 forged/stat-monthly-ledger/fill.py 的公式严格同口径。"""
    by = {r["code"]: r for r in rows}
    pc = lambda c: by[c]["period_credit"] / 1e4  # noqa: E731
    pd = lambda c: by[c]["period_debit"] / 1e4  # noqa: E731
    nc = lambda c: (by[c]["closing_debit"] - by[c]["closing_credit"]) / 1e4  # noqa: E731
    if name == "operating_profit":
        return pc("6001") - pd("6401") - pd("6403") - pd("6601") - pd("6602") - pd("6603") - pd("6604")
    if name == "net_profit":
        return derived(rows, "operating_profit") - pd("6801")
    if name == "tax_paid":
        return sum(pd(c) for c in by if c.startswith("2221") and c != "2221")
    if name == "asset_total":
        return sum(nc(k) for k in by if k.startswith("1"))
    if name == "liab_total":
        return -sum(nc(k) for k in by if k.startswith("2"))
    if name == "equity_total":
        return derived(rows, "asset_total") - derived(rows, "liab_total")
    raise KeyError(name)


def ledger_truth(rows: list[dict]) -> dict[str, float]:
    """人工版答案：台账各单元格应填的值（万元）。"""
    out: dict[str, float] = {}
    for _label, _unit, cell, kind, a, b in LEDGER_LABELS:
        if kind == "direct":
            row = next(r for r in rows if r["code"] == a)
            out[cell] = (row["period_credit"] if b == "period_credit" else row["period_debit"]) / 1e4
        else:
            out[cell] = derived(rows, a)
    return out


def write_messy_export(rows: list[dict], month: str, path: Path) -> None:
    """写"乱格式"金蝶风格导出文件。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "总账科目余额表"
    ws["A1"] = "星澜科技有限公司"
    ws["A2"] = f"科目余额表　{month[:4]}年{int(month[5:7])}月　单位：元"
    bold = Font(bold=True)
    headers = ["科目代码及名称", "\u3000期初余额（借方）\u3000", "\u3000期初余额（贷方）\u3000",
               "\u3000本期发生额（借方）\u3000", "\u3000本期发生额（贷方）\u3000",
               "\u3000期末余额（借方）\u3000", "\u3000期末余额（贷方）\u3000", "备注"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=4, column=col, value=h).font = bold
    r = 5
    for row in rows:
        ws.cell(row=r, column=1, value=f"{row['code']}\u3000{row['name']}")
        for col, key in ((2, "opening_debit"), (3, "opening_credit"), (4, "period_debit"),
                         (5, "period_credit"), (6, "closing_debit"), (7, "closing_credit")):
            ws.cell(row=r, column=col, value=round(row[key], 2))
        r += 1
    ws.cell(row=r, column=1, value="合计")
    for col, key in ((2, "opening_debit"), (3, "opening_credit"), (4, "period_debit"),
                     (5, "period_credit"), (6, "closing_debit"), (7, "closing_credit")):
        ws.cell(row=r, column=col, value=round(sum(x[key] for x in rows), 2))
    ws.cell(row=r + 1, column=1, value="制表：金蝶云星空示例导出　日期：2025-10-08")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_ledger(path: Path, period: str | None, values: dict[str, float] | None, with_notes: bool = False) -> None:
    """写台账模板（values=None）或人工版/成品（values 给定时填 C 列）。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "台账"
    ws["A1"] = "统计月度台账（虚构演示 · 星澜科技有限公司）"
    ws["A1"].font = Font(bold=True)
    ws["A2"] = "统计期："
    if period:
        ws["B2"] = period
    bold = Font(bold=True)
    for col, h in enumerate(["指标", "计量单位", "本期数", "数据来源说明"], 1):
        ws.cell(row=4, column=col, value=h).font = bold
    for i, (label, unit, cell, kind, a, b) in enumerate(LEDGER_LABELS):
        r = 5 + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=unit)
        if values is not None:
            ws[cell] = round(values[cell], 2)
            if with_notes:
                note = f"取数 {a}.{b}" if kind == "direct" else f"衍生公式 {a}（口径见 references/口径说明.md）"
                ws.cell(row=r, column=4, value=note)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--starlan", default=DEFAULT_STARLAN)
    args = ap.parse_args()

    for month in MONTHS:
        rows = build_tb(month, args.starlan)
        write_messy_export(rows, month, OUT_EXPORT / f"科目余额表_{month}_乱格式.xlsx")
        print(f"[gen] {month}: {len(rows)} 科目 → 示例导出/科目余额表_{month}_乱格式.xlsx")
        if month == MONTHS[0]:
            truth = ledger_truth(rows)
            write_ledger(OUT_TEMPLATE / "统计月度台账_模板.xlsx", period=None, values=None)
            write_ledger(OUT_TEMPLATE / "统计月度台账_2025-08_人工版.xlsx",
                         period="2025年08月", values=truth, with_notes=True)
            print("[gen] 台账模板 + 2025-08 人工版（回填考试答案）已生成")
    print(f"[gen] 完成 {datetime.now():%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main()
