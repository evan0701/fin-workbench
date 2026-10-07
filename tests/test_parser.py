"""parser 单元测试：用合成的小样本覆盖乱格式解析的关键行为。"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from fincore.parser import load_mapping, parse, run_anchors

MAPPING = {
    "version": 1,
    "name": "测试映射",
    "source": {"sheet": "总账", "header_row": 3, "skip_patterns": ["合计", "制表"],
               "company": "测试公司", "period": "2025-09"},
    "unit_scale": 1.0,
    "unit_note": "元",
    "columns": {
        "code_name": {"col": "A", "split_regex": r"^(\d+)\s+(.+)$"},
        "opening": {"debit": "B", "credit": "C"},
        "period": {"debit": "D", "credit": "E"},
        "closing": {"debit": "F", "credit": "G"},
    },
    "anchors": ["opening_balance", "closing_balance", "codes_unique"],
}


def make_workbook(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "总账"
    ws["A1"] = "测试公司　科目余额表"
    ws["A3"] = "科目代码及名称"
    for col, h in ((2, "期初借"), (3, "期初贷"), (4, "发生借"), (5, "发生贷"), (6, "期末借"), (7, "期末贷")):
        ws.cell(row=3, column=col, value=h)
    data = [
        ("1001\u3000库存现金", 100.0, 0, 0, 0, 150.0, 0),
        ("2202\u3000应付账款", 0, 100.0, 0, 50.0, 0, 150.0),
        ("6001\u3000主营业务收入", 0, 0, 0, 500.0, 0, 0),
    ]
    r = 4
    for row in data:
        ws.cell(row=r, column=1, value=row[0])
        for c, v in enumerate(row[1:], start=2):
            ws.cell(row=r, column=c, value=v)
        r += 1
    ws.cell(row=r, column=1, value="合计")
    ws.cell(row=r + 1, column=1, value="制表人：示例")
    wb.save(path)


def test_parse_skips_junk_and_splits_code_name(tmp_path):
    xlsx = tmp_path / "sample.xlsx"
    make_workbook(xlsx)
    model, anchors = parse(MAPPING, xlsx)

    assert [r.code for r in model.rows] == ["1001", "2202", "6001"]
    assert model.rows[0].name == "库存现金"
    assert model.rows[0].level == 1
    assert model.rows[1].period_credit == 50.0
    assert model.rows[2].period_credit == 500.0
    # 溯源：src 指向真实行号（数据从第 4 行开始）
    assert model.rows[0].src["row"] == 4
    assert model.rows[0].src["sheet"] == "总账"
    # 合计/制表行被跳过
    assert all("合计" not in r.name for r in model.rows)
    # 损益类科目期初/期末为 0
    assert model.rows[2].closing_credit == 0.0
    assert all(a.status == "PASS" for a in anchors)


def test_parse_rejects_unsplittable_code(tmp_path):
    xlsx = tmp_path / "bad.xlsx"
    make_workbook(xlsx)
    wb = openpyxl.load_workbook(xlsx)
    wb.active["A4"] = "这不是科目"
    wb.save(xlsx)
    with pytest.raises(ValueError, match="split_regex"):
        parse(MAPPING, xlsx)


def test_anchor_closing_balance_failure():
    from fincore.model import StandardTB, TBRow

    rows = [TBRow(code="1001", name="库存现金", level=1, closing_debit=100.0),
            TBRow(code="2001", name="短期借款", level=1, closing_credit=90.0)]
    model = StandardTB(meta={}, rows=rows)
    results = run_anchors(model, requested=["closing_balance"])
    assert results[0].status == "FAIL"
    assert "差额" in results[0].detail


def test_carry_forward_anchor(tmp_path):
    from fincore.model import StandardTB, TBRow

    prev = StandardTB(meta={}, rows=[TBRow(code="1001", name="库存现金", level=1, closing_debit=150.0)])
    cur_ok = StandardTB(meta={}, rows=[TBRow(code="1001", name="库存现金", level=1, opening_debit=150.0)])
    cur_bad = StandardTB(meta={}, rows=[TBRow(code="1001", name="库存现金", level=1, opening_debit=140.0)])

    (ok,) = run_anchors(cur_ok, prev_model=prev, requested=["carry_forward"])
    (bad,) = run_anchors(cur_bad, prev_model=prev, requested=["carry_forward"])
    (skip,) = run_anchors(cur_ok, prev_model=None, requested=["carry_forward"])
    assert ok.status == "PASS"
    assert bad.status == "FAIL" and "140.00" in bad.detail
    assert skip.status == "SKIPPED"


def test_load_mapping_missing_section():
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("source: {}\n")
        path = f.name
    with pytest.raises(ValueError, match="columns"):
        load_mapping(path)


def test_level_widths_mapping(tmp_path):
    """真实账套驱动的特性：3 位分段编码（4/7/10 位）按 mapping 配置定级。"""
    xlsx = tmp_path / "w.xlsx"
    make_workbook(xlsx)
    wb = openpyxl.load_workbook(xlsx)
    ws = wb.active
    ws.cell(row=4, column=1, value="1002001\u3000银行存款_工行")
    wb.save(xlsx)
    mapping = {**MAPPING, "level_widths": [4, 7, 10]}
    model, _ = parse(mapping, xlsx)
    assert model.by_code("1001").level == 1
    assert model.by_code("1002001").level == 2
    assert model.by_code("2202").level == 1


def test_leaf_only_deduplicates_levels(tmp_path):
    """真实账套驱动的特性：金蝶导出各级科目都带全额，leaf_only 只保留末级。"""
    xlsx = tmp_path / "leaf.xlsx"
    make_workbook(xlsx)
    wb = openpyxl.load_workbook(xlsx)
    ws = wb.active
    # 1002 一级行 + 1002001 末级行，展示同一笔余额（金蝶风格逐级重复）
    ws.cell(row=7, column=1, value="1002\u3000银行存款")
    for col, v in ((2, 500.0), (3, 0), (4, 0), (5, 0), (6, 800.0), (7, 0)):
        ws.cell(row=7, column=col, value=v)
    ws.cell(row=8, column=1, value="1002001\u3000银行存款_工行")
    for col, v in ((2, 500.0), (3, 0), (4, 0), (5, 0), (6, 800.0), (7, 0)):
        ws.cell(row=8, column=col, value=v)
    wb.save(xlsx)

    mapping = {**MAPPING, "anchors": ["opening_balance", "closing_balance", "codes_unique"]}
    full, a_full = parse(mapping, xlsx)
    assert any(r.code == "1002" for r in full.rows) and any(r.code == "1002001" for r in full.rows)

    leaf, a_leaf = parse({**MAPPING, "leaf_only": True}, xlsx)
    codes = [r.code for r in leaf.rows]
    assert "1002001" in codes and "1002" not in codes  # 只留末级
    assert all(a.status == "PASS" for a in a_leaf)
    # 金额不重复计算：末级 1002001 的期末 = 800
    assert leaf.by_code("1002001").closing_debit == 800.0
