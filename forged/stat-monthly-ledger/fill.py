"""统计月度台账填写（fill-forge 铸造 · 演示）。

确定性填写：fincore 标准模型 → 目标模板单元格。无 LLM 参与计算。
铁律：锚点不全绿不填报；零信任独立取数；只填数值不动格式。

用法见同目录 SKILL.md。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # 允许未 pip install 时直接运行

from fincore.model import StandardTB  # noqa: E402
from fincore.parser import parse  # noqa: E402


# ---------------------------------------------------------------------------
# 衍生公式（单位：元，与标准模型一致；缩放到万元在写入时统一做）。
# 与 references/口径说明.md 逐字一致，改动必须同步口径文档并重跑回填考试。
# ---------------------------------------------------------------------------
def _raw(model: StandardTB, code: str, field: str) -> float:
    row = model.by_code(code)
    if row is None:
        raise KeyError(f"标准模型中找不到科目 {code}，请检查数据源是否完整")
    return getattr(row, field)


def operating_profit(m: StandardTB) -> float:
    """营业利润 = 营业收入 − 营业成本 − 税金及附加 − 销售费用 − 管理费用 − 研发费用 − 财务费用"""
    return (_raw(m, "6001", "period_credit") - _raw(m, "6401", "period_debit")
            - _raw(m, "6403", "period_debit") - _raw(m, "6601", "period_debit")
            - _raw(m, "6602", "period_debit") - _raw(m, "6603", "period_debit")
            - _raw(m, "6604", "period_debit"))


def net_profit(m: StandardTB) -> float:
    """净利润 = 营业利润 − 所得税费用（计提）"""
    return operating_profit(m) - _raw(m, "6801", "period_debit")


def tax_paid(m: StandardTB) -> float:
    """实缴税费合计 = 2221 应交税费全部子科目本期借方发生额之和（不含根科目，防重复）"""
    return sum(r.period_debit for r in m.rows if r.code.startswith("2221") and r.code != "2221")


def asset_total(m: StandardTB) -> float:
    """资产总额 = 全部 1 开头科目期末净额（借正贷负）之和"""
    return sum(r.net_closing for r in m.rows if r.code.startswith("1"))


def liab_total(m: StandardTB) -> float:
    """负债合计 = 全部 2 开头科目期末净额（贷正借负）之和"""
    return -sum(r.net_closing for r in m.rows if r.code.startswith("2"))


def equity_total(m: StandardTB) -> float:
    """净资产 = 资产总额 − 负债合计"""
    return asset_total(m) - liab_total(m)


FORMULAS = {
    "operating_profit": operating_profit,
    "net_profit": net_profit,
    "tax_paid": tax_paid,
    "asset_total": asset_total,
    "liab_total": liab_total,
    "equity_total": equity_total,
}


def _anchors_of(model: StandardTB):
    from fincore.model import AnchorResult

    return [AnchorResult(**a) for a in model.meta.get("anchor_results", [])]


def fill(source: str, period: str, mapping_path: str, out: str, check: str | None = None, prev: str | None = None) -> int:
    cfg = yaml.safe_load(Path(mapping_path).read_text(encoding="utf-8"))

    # 1) 解析数据源（铁律 1：锚点不全绿不填报）
    source_mapping = fincore_load_mapping(REPO / cfg["source"]["mapping"])
    source_mapping.setdefault("source", {})["period"] = period  # 覆盖期间标注
    prev_model = None
    if prev:
        prev_model = StandardTB.from_dict(json.loads(Path(prev).read_text(encoding="utf-8")))
    model, anchors = parse(source_mapping, source, prev_model=prev_model)
    model.meta["anchor_results"] = [{"name": a.name, "status": a.status, "detail": a.detail} for a in anchors]
    failed = [a for a in anchors if a.status == "FAIL"]
    for a in anchors:
        print(f"  {a.badge} {a.name}: {a.status}  {a.detail}")
    if failed:
        print(f"[fill] ❌ 锚点校验 {len(failed)} 项 FAIL，拒绝填报（铁律 1）")
        return 2

    # 2) 打开目标模板（铁律 3：只填数值，不动任何格式/公式）
    wb = openpyxl.load_workbook(REPO / cfg["target"]["template"])
    ws = wb.active
    y, m = period[:4], int(period[5:7])
    ws[cfg["target"]["period_cell"]] = cfg["target"]["period_format"].format(y=y, m=m)
    scale = float(cfg["target"].get("unit_scale", 1.0))

    review: list[tuple[str, str, str, str]] = []  # 指标 | 值 | 类型 | 来源
    skipped: list[str] = []
    for row in cfg["rows"]:
        cell = row["cell"]
        if ws[cell].data_type == "f" or (isinstance(ws[cell].value, str) and ws[cell].value.startswith("=")):
            skipped.append(f"{row['label']}({cell}) 含公式，已跳过")
            continue
        if row["kind"] == "direct":
            value = _raw(model, row["code"], row["field"]) * scale
            note = f"取数 {row['code']}.{row['field']}"
        else:
            value = FORMULAS[row["formula"]](model) * scale
            note = f"衍生公式 {row['formula']}（口径见 references/口径说明.md）"
        ws[cell] = round(value, 2)
        kind_label = "直接取数" if row["kind"] == "direct" else "衍生计算"
        review.append((row["label"], f"{round(value, 2):,.2f} {row['unit']}", kind_label, note))
        note_cell = "D" + cell[1:]
        ws[note_cell] = note

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"[fill] 成品已写入 {out_path}（{len(review)} 格）")
    for s in skipped:
        print(f"  ⚠️ {s}")

    # 3) 复核清单（审计轨迹）
    lines = [
        f"# 复核清单 · 统计月度台账 {cfg['target']['period_format'].format(y=y, m=m)}",
        "",
        f"- 成品：`{out_path}`",
        f"- 数据源：`{source}`（映射 {cfg['name']}）",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "| 指标 | 值 | 类型 | 来源 |",
        "|---|---|---|---|",
    ]
    lines += [f"| {label} | {val} | {kind} | {src} |" for label, val, kind, src in review]
    review_path = out_path.with_suffix(out_path.suffix + ".复核清单.md")
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[fill] 复核清单 → {review_path}")

    # 4) 回填考试模式（铁律 2 的落地验证）
    if check:
        golden = openpyxl.load_workbook(check, data_only=True).active
        diffs = []
        if golden[cfg["target"]["period_cell"]].value != ws[cfg["target"]["period_cell"]].value:
            diffs.append((cfg["target"]["period_cell"], "统计期", ws[cfg["target"]["period_cell"]].value, golden[cfg["target"]["period_cell"]].value))
        for row in cfg["rows"]:
            cell = row["cell"]
            mine, theirs = ws[cell].value, golden[cell].value
            if mine is None and theirs is None:
                continue
            if mine is None or theirs is None or abs(float(mine) - float(theirs)) > 0.005:
                diffs.append((cell, row["label"], mine, theirs))
        if diffs:
            print(f"[exam] ❌ 回填考试未通过，{len(diffs)} 处差异：")
            for cell, label, mine, theirs in diffs:
                print(f"  {cell} {label}: 技能填 {mine!r} vs 人工版 {theirs!r}")
            return 1
        print("[exam] ✅ 回填考试通过：全部数据单元格差异清零")
    return 0


def fincore_load_mapping(path: Path) -> dict:
    from fincore.parser import load_mapping

    return load_mapping(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="统计月度台账填写（确定性代码，无 LLM）")
    ap.add_argument("--source", required=True, help="当月科目余额表导出文件")
    ap.add_argument("--period", required=True, help="如 2025-09")
    ap.add_argument("--out", required=True)
    ap.add_argument("--check", help="上期人工版文件（回填考试模式）")
    ap.add_argument("--prev", help="上月标准模型 JSON，启用跨月衔接锚点")
    args = ap.parse_args(argv)
    mapping_path = Path(__file__).resolve().parent / "mapping.yaml"
    return fill(args.source, args.period, str(mapping_path), args.out, args.check, args.prev)


if __name__ == "__main__":
    raise SystemExit(main())
