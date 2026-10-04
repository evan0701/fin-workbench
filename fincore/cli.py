"""fincore 命令行入口。

用法示例（仓库根目录、已 pip install -e . 的前提下）：
    python -m fincore parse  --config demo/mapping_jinDie.yaml --file "demo/示例导出/科目余额表_2025-09_乱格式.xlsx" --out out/tb-09.json
    python -m fincore view-balance --model out/tb-09.json --out "demo/输出/科目余额筛选台账.html"
    python -m fincore view-tax --model out/tb-08.json --model out/tb-09.json --out "demo/输出/支付税费台账.html"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .parser import parse
from .views.balance_ledger import render_balance_ledger
from .views.tax_ledger import render_tax_ledger


def _load_model(path: str):
    from .model import StandardTB

    return StandardTB.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fincore", description="科目余额表 → 标准模型 → HTML 工作台")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("parse", help="解析导出文件为标准模型 JSON，并跑锚点校验")
    p1.add_argument("--config", required=True)
    p1.add_argument("--file", required=True)
    p1.add_argument("--out", required=True, help="输出 JSON 路径")
    p1.add_argument("--prev", help="上月标准模型 JSON，启用衔接校验")
    p1.add_argument("--period", help="覆盖期间标注，如 2025-09")
    p1.add_argument("--company", help="覆盖公司名标注")

    p2 = sub.add_parser("view-balance", help="生成科目余额筛选台账 HTML")
    p2.add_argument("--model", required=True)
    p2.add_argument("--out", required=True)

    p3 = sub.add_parser("view-tax", help="生成支付税费台账 HTML（可传多个月对比）")
    p3.add_argument("--model", action="append", required=True)
    p3.add_argument("--out", required=True)
    p3.add_argument("--tax-root", default="2221", help="税费科目根编码")

    p4 = sub.add_parser("bank-match", help="银行流水 ↔ 资金计划两级匹配，输出资金计划执行台账 HTML")
    p4.add_argument("--bank-mapping", required=True, help="银行导出格式映射（bank mapping.yaml）")
    p4.add_argument("--bank-file", required=True, help="网银导出的流水文件")
    p4.add_argument("--plan", required=True, help="资金计划 YAML（lines: name/direction/amount/counterparty/due）")
    p4.add_argument("--out", required=True)
    p4.add_argument("--window", type=int, default=30, help="计划日期时间窗（天）")
    p4.add_argument("--period", help="期间标注")
    p4.add_argument("--company", help="公司名标注")

    args = ap.parse_args(argv)

    if args.cmd == "parse":
        from .parser import load_mapping

        cfg = load_mapping(args.config)
        if args.period:
            cfg.setdefault("source", {})["period"] = args.period
        if args.company:
            cfg["source"]["company"] = args.company
        prev = _load_model(args.prev) if args.prev else None
        model, anchors = parse(cfg, args.file, prev_model=prev)
        model.meta["anchor_results"] = [{"name": a.name, "status": a.status, "detail": a.detail} for a in anchors]
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[fincore] 标准模型已写入 {out}（{len(model.rows)} 个科目）")
        for a in anchors:
            print(f"  {a.badge} {a.name}: {a.status}  {a.detail}")
        return 0 if all(a.status != "FAIL" for a in anchors) else 2

    if args.cmd == "view-balance":
        model = _load_model(args.model)
        html = render_balance_ledger(model)
        _write(args.out, html)
        print(f"[fincore] 科目余额筛选台账 → {args.out}")
        return 0

    if args.cmd == "view-tax":
        models = [_load_model(m) for m in args.model]
        html = render_tax_ledger(models, tax_root=args.tax_root)
        _write(args.out, html)
        print(f"[fincore] 支付税费台账 → {args.out}")
        return 0

    if args.cmd == "bank-match":
        from datetime import date, datetime

        import yaml

        from .bank import PlanLine, load_bank_mapping, match_plans, parse_bank, render_plan_ledger

        def _d(v):
            if v in (None, ""):
                return None
            if isinstance(v, datetime):
                return v.date()
            if isinstance(v, date):
                return v
            return datetime.strptime(str(v), "%Y-%m-%d").date()

        bm = load_bank_mapping(args.bank_mapping)
        txs, anchors = parse_bank(bm, args.bank_file)
        plan_cfg = yaml.safe_load(Path(args.plan).read_text(encoding="utf-8"))
        plans = [PlanLine(name=l["name"], direction=l.get("direction", "付"), amount=float(l["amount"]),
                          counterparty=l.get("counterparty", ""), due=_d(l.get("due")))
                 for l in plan_cfg.get("lines", [])]
        report = match_plans(txs, plans, keyword_rules=bm.get("special_rules"), date_window_days=args.window)
        print(f"[fincore] 匹配结果: {report.summary()}")
        html = render_plan_ledger(report, anchors=anchors, meta={
            "company": args.company or plan_cfg.get("company", ""),
            "period": args.period or plan_cfg.get("period", ""),
            "tx_count": len(txs), "plan_count": len(plans),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        _write(args.out, html)
        print(f"[fincore] 资金计划执行台账 → {args.out}")
        return 0 if all(a["status"] != "FAIL" for a in anchors) else 2
    return 1


def _write(path: str, html: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
