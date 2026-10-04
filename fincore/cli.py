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
    return 1


def _write(path: str, html: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
