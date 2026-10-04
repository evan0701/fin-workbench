"""视图单元测试：自包含（无外链）、数字格式、溯源提示、税费台账合计口径。"""

from __future__ import annotations

import re

from fincore.model import StandardTB, TBRow
from fincore.views import render_balance_ledger, render_tax_ledger


def make_model() -> StandardTB:
    rows = [
        TBRow(code="1001", name="库存现金", level=1, opening_debit=50_000, closing_debit=61_000,
              src={"file": "导出.xlsx", "sheet": "总账", "row": 4}),
        TBRow(code="2221", name="应交税费", level=1, closing_credit=1_000_000,
              src={"file": "导出.xlsx", "sheet": "总账", "row": 5}),
        TBRow(code="222101", name="应交税费—应交增值税", level=2, period_debit=17_364_000,
              closing_credit=19_008_000, src={"file": "导出.xlsx", "sheet": "总账", "row": 6}),
        TBRow(code="222103", name="应交税费—应交个人所得税", level=2, period_debit=755_500,
              closing_credit=902_000, src={"file": "导出.xlsx", "sheet": "总账", "row": 7}),
        TBRow(code="6001", name="主营业务收入", level=1, period_credit=31_680_000),
    ]
    meta = {"company": "测试公司", "period": "2025-09", "source_file": "导出.xlsx",
            "unit": "元", "mapping_name": "测试", "mapping_version": 1, "generated_at": "2026-10-04 12:00",
            "anchor_results": [{"name": "closing_balance", "status": "PASS", "detail": "ok"}]}
    return StandardTB(meta=meta, rows=rows)


def test_balance_view_is_self_contained():
    html = render_balance_ledger(make_model())
    assert "科目余额筛选台账" in html
    assert not re.search(r'https?://', html), "HTML 必须零外链（数据不出网红线）"
    assert "6.10" in html or "6.1" in html  # 61,000 元 → 6.10 万元
    assert "1,900.80" in html  # 千分位
    assert "导出.xlsx" in html and "第4行" in html  # 溯源提示
    assert "closing_balance" in html  # 锚点徽章


def test_tax_view_totals_exclude_root():
    m = make_model()
    html = render_tax_ledger([m], tax_root="2221")
    assert "支付税费台账" in html
    assert not re.search(r'https?://', html)
    # 实缴合计 = 1736400 + 75550 = 1,811,950 元 = 1,811.95 万元（不含根科目）
    assert "1,811.95" in html
    # 根科目行 2221 本身无发生额，显示 —
    assert "—" in html


def test_tax_view_multi_month_columns():
    m1 = make_model()
    m2 = make_model()
    m2.meta["period"] = "2025-10"
    html = render_tax_ledger([m1, m2])
    assert "2025-09" in html and "2025-10" in html
