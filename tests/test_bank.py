"""银行流水模块测试：映射解析、两级匹配、关键词桶、视图自包含。"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from fincore.bank import (BankTx, MatchReport, PlanLine, load_bank_mapping, match_plans,
                          name_match, parse_bank, render_plan_ledger)

REPO = Path(__file__).resolve().parents[1]


def make_tx(d, direction, amount, cp="", summary=""):
    return BankTx(date=date.fromisoformat(d), direction=direction, amount=amount,
                  counterparty=cp, summary=summary)


def make_plan(name, direction, amount, cp="", due=None):
    return PlanLine(name=name, direction=direction, amount=amount, counterparty=cp,
                    due=date.fromisoformat(due) if due else None)


def test_name_match_normalization():
    assert name_match("深圳蓝湾置业", "深圳蓝湾置业有限公司")
    assert name_match("远洋咨询(深圳)有限公司", "远洋咨询")
    assert not name_match("李文", "李文文")            # 单字包含不成立
    assert not name_match("", "任意")                  # 空名不匹配
    assert not name_match("华创", "华创建材集团")      # 2字包含需 ≥2 字才成立
    assert name_match("华创建材", "华创建材集团有限公司")


def test_exact_match_with_window():
    txs = [make_tx("2025-09-08", "收", 3_200_000, "深圳蓝湾置业有限公司", "客户回款")]
    plans = [make_plan("回款-蓝湾", "收", 3_200_000, "深圳蓝湾置业", due="2025-09-12")]
    r = match_plans(txs, plans)
    assert len(r.matches) == 1 and r.matches[0].tier == "exact"
    assert not r.unmatched_txs and not r.unmatched_plans


def test_exact_rejected_outside_window():
    txs = [make_tx("2025-08-01", "收", 3_200_000, "深圳蓝湾置业有限公司")]
    plans = [make_plan("回款-蓝湾", "收", 3_200_000, "深圳蓝湾置业", due="2025-09-12")]
    r = match_plans(txs, plans, date_window_days=30)
    assert not r.matches and len(r.unmatched_txs) == 1


def test_aggregate_match_unique_combo():
    txs = [
        make_tx("2025-09-22", "收", 480_000, "云帆数据科技有限公司"),
        make_tx("2025-09-24", "收", 500_000, "云帆数据科技有限公司"),
        make_tx("2025-09-26", "收", 300_000, "云帆数据科技有限公司"),
    ]
    plans = [make_plan("回款-云帆", "收", 980_000, "云帆数据", due="2025-09-25")]
    r = match_plans(txs, plans)
    assert len(r.matches) == 1 and r.matches[0].tier == "aggregate"
    assert {t.amount for t in r.matches[0].txs} == {480_000.0, 500_000.0}
    # 未组合进来的第三笔仍在未匹配列表
    assert len(r.unmatched_txs) == 1


def test_ambiguous_aggregate_left_to_human():
    # 两组组合都能凑出 980000 → 宁可漏配不可错配，聚合不成立
    txs = [
        make_tx("2025-09-22", "收", 480_000, "云帆数据"),
        make_tx("2025-09-24", "收", 500_000, "云帆数据"),
        make_tx("2025-09-25", "收", 900_000, "云帆数据"),
        make_tx("2025-09-26", "收", 80_000, "云帆数据"),
    ]
    plans = [make_plan("回款-云帆", "收", 980_000, "云帆数据")]
    r = match_plans(txs, plans)
    assert not any(m.tier == "aggregate" for m in r.matches)


def test_keyword_bucket_and_plan_priority():
    txs = [
        make_tx("2025-09-10", "付", 2_280_000, "深圳市星澜科技有限公司", "代发工资"),
        make_tx("2025-09-13", "付", 120.0, "招商银行", "网银转账手续费"),
        make_tx("2025-09-15", "付", 85.0, "招商银行", "转账手续费"),
    ]
    plans = [make_plan("支付工资-9月", "付", 2_280_000, "", due="2025-09-10")]
    rules = [{"name": "银行手续费", "direction": "付", "match_any": ["手续费"]}]
    r = match_plans(txs, plans, keyword_rules=rules)
    # 工资被计划行吃掉（计划优先），手续费进关键词桶
    assert len(r.matches) == 1 and r.matches[0].tier == "exact"
    assert len(r.keyword_buckets) == 1
    assert r.keyword_buckets[0].plan.name == "银行手续费"
    assert r.keyword_buckets[0].matched_amount == pytest.approx(205.0)
    assert not r.unmatched_txs


def test_report_summary_counts_both_sides():
    txs = [make_tx("2025-09-26", "付", 86_420.50, "李文", "报销款")]
    plans = [make_plan("回款-恒润", "收", 1_200_000, "恒润贸易", due="2025-09-28")]
    r = match_plans(txs, plans)
    assert isinstance(r, MatchReport)
    assert "未匹配流水 1 笔" in r.summary() and "未执行计划 1 行" in r.summary()


BANK_MAPPING = {
    "name": "测试银行",
    "source": {"sheet": "明细", "header_row": 2, "skip_patterns": ["合计", "打印"],
               "date_formats": ["%Y%m%d"]},
    "columns": {"date": {"col": "A"}, "summary": {"col": "B"}, "counterparty": {"col": "C"},
                "income": {"col": "E"}, "expense": {"col": "F"}, "balance": {"col": "G"}},
}


def make_bank_workbook(tmp_path, rows, break_balance=False):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "明细"
    ws["A1"] = "测试银行　交易明细"
    for col, h in enumerate(["交易日期", "摘要", "对方户名", "币种", "收入", "支出", "余额"], 1):
        ws.cell(row=2, column=col, value=h)
    balance = 1_000_000.0
    for i, (d, s, cp, income, expense) in enumerate(rows):
        balance = round(balance + income - expense, 2)
        if break_balance and i == 1:
            balance += 100.0
        r = 3 + i
        for col, v in enumerate([d, s, cp, "人民币", income or None, expense or None, balance], 1):
            ws.cell(row=r, column=col, value=v)
    ws.cell(row=3 + len(rows), column=1, value="合计")
    path = tmp_path / "bank.xlsx"
    wb.save(path)
    return path


def test_parse_bank_anchors_pass_and_balance_chain(tmp_path):
    rows = [("20250901", "回款", "甲公司", 500_000.0, 0.0),
            ("20250902", "付款", "乙公司", 0.0, 120.0)]
    path = make_bank_workbook(tmp_path, rows)
    txs, anchors = parse_bank(BANK_MAPPING, path)
    assert len(txs) == 2
    assert txs[0].direction == "收" and txs[1].direction == "付"
    assert all(a["status"] in ("PASS", "SKIPPED") for a in anchors), anchors
    assert "合计" not in [t.summary for t in txs]


def test_parse_bank_balance_chain_fail(tmp_path):
    rows = [("20250901", "回款", "甲公司", 500_000.0, 0.0),
            ("20250902", "付款", "乙公司", 0.0, 120.0)]
    path = make_bank_workbook(tmp_path, rows, break_balance=True)
    txs, anchors = parse_bank(BANK_MAPPING, path)
    chain = next(a for a in anchors if a["name"] == "balance_chain")
    assert chain["status"] == "FAIL"


def test_demo_bank_mapping_loads():
    cfg = load_bank_mapping(REPO / "demo" / "mapping_bank.yaml")
    assert cfg["columns"]["income"]["col"] == "E"
    assert cfg["special_rules"][0]["match_any"] == ["手续费", "年费"]


def test_plan_view_self_contained():
    from datetime import date as D

    tx = BankTx(date=D(2025, 9, 26), direction="付", amount=86_420.50, counterparty="李文",
                summary="报销款", src={"file": "bank.xlsx", "sheet": "明细", "row": 15})
    plan = PlanLine(name="回款-恒润", direction="收", amount=1_200_000,
                    counterparty="恒润贸易", due=D(2025, 9, 28))
    r = MatchReport(matches=[], unmatched_txs=[tx], unmatched_plans=[plan], keyword_buckets=[])
    html = render_plan_ledger(r, anchors=[{"name": "dates_parsed", "status": "PASS", "detail": "ok"}],
                              meta={"company": "测试", "period": "2025-09"})
    assert "资金计划执行台账" in html
    assert not re.search(r"https?://", html), "零外链红线"
    assert "未找到匹配流水" in html and "李文" in html
