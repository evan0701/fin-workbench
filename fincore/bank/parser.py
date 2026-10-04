"""银行流水映射解析：bank mapping.yaml → 标准流水。

复用"转换模板"协议：描述你家网银导出文件的样子（哪行是表头、收付在哪列、
日期格式），引擎输出标准流水，并跑银行侧锚点（日期可解析、余额链连续）。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from .model import BankTx

_TOL = 0.01


def load_bank_mapping(path: str | Path) -> dict:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for key in ("source", "columns", "date"):
        if key not in raw.get("columns", {}) and key not in raw:
            raise ValueError(f"bank mapping 缺少必需段: columns.{key}")
    return raw


def _num(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u3000", "").replace(",", "").replace("¥", "").replace("￥", "")
    if text in ("", "-", "—"):
        return 0.0
    return float(text)


def _parse_date(value, formats: list[str]) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("\u3000", " ")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_bank(mapping: dict, source_file: str | Path) -> tuple[list[BankTx], list[dict]]:
    """解析网银导出 → (标准流水列表, 锚点结果)。锚点 FAIL 时 detail 写明行号。"""
    src_cfg = mapping["source"]
    header_row = int(src_cfg.get("header_row", 1))
    skip_patterns = [re.compile(p) for p in src_cfg.get("skip_patterns", [])]
    date_formats = src_cfg.get("date_formats", ["%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"])

    cols = mapping["columns"]
    date_cfg, income_cfg, expense_cfg = cols["date"], cols.get("income"), cols.get("expense")
    signed_cfg, direction_cfg = cols.get("signed_amount"), cols.get("direction")
    if income_cfg is None and expense_cfg is None and signed_cfg is None:
        raise ValueError("bank mapping 的 columns 需要 income/expense 分列，或 signed_amount（收正付负）")
    cp_cfg, sum_cfg, bal_cfg = cols.get("counterparty"), cols.get("summary"), cols.get("balance")

    def idx(cfg: dict | None) -> int | None:
        return column_index_from_string(cfg["col"].upper()) if cfg else None

    i_date, i_in, i_out = idx(date_cfg), idx(income_cfg), idx(expense_cfg)
    i_signed, i_dir = idx(signed_cfg), idx(direction_cfg)
    i_cp, i_sum, i_bal = idx(cp_cfg), idx(sum_cfg), idx(bal_cfg)

    wb = load_workbook(source_file, read_only=True, data_only=True)
    ws = wb[src_cfg["sheet"]] if src_cfg.get("sheet") else wb[wb.sheetnames[0]]
    sheet_used = ws.title

    txs: list[BankTx] = []
    bad_dates = 0
    for row_no, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_no <= header_row:
            continue
        cells = list(row)
        first_text = str(cells[0]).strip() if cells and cells[0] is not None else ""
        if not first_text or any(p.search(first_text) for p in skip_patterns):
            continue
        d = _parse_date(cells[i_date - 1] if i_date and i_date <= len(cells) else None, date_formats)
        if d is None:
            if i_signed and i_signed <= len(cells) and cells[i_signed - 1] is not None:
                bad_dates += 1
            continue

        if i_signed:
            signed = _num(cells[i_signed - 1] if i_signed <= len(cells) else None)
            direction = (cells[i_dir - 1] if i_dir and i_dir <= len(cells) else None) or ("收" if signed >= 0 else "付")
            amount = abs(signed)
        else:
            income = _num(cells[i_in - 1]) if i_in and i_in <= len(cells) else 0.0
            expense = _num(cells[i_out - 1]) if i_out and i_out <= len(cells) else 0.0
            if income == 0 and expense == 0:
                continue
            if income > 0 and expense > 0:
                raise ValueError(f"{Path(source_file).name}/{sheet_used} 第{row_no}行收付同时有值，无法判定方向")
            direction = "收" if income > 0 else "付"
            amount = income if income > 0 else expense

        def cell(i: int | None) -> str:
            return str(cells[i - 1]).strip() if i and i <= len(cells) and cells[i - 1] is not None else ""

        txs.append(BankTx(
            date=d, direction=direction, amount=round(amount, 2),
            counterparty=cell(i_cp), summary=cell(i_sum),
            balance=_num(cells[i_bal - 1]) if i_bal and i_bal <= len(cells) and cells[i_bal - 1] is not None else None,
            src={"file": Path(source_file).name, "sheet": sheet_used, "row": row_no},
        ))
    wb.close()

    if not txs:
        raise ValueError(f"没解析到任何流水行，请检查 bank mapping 的 header_row 与列配置: {source_file}")

    anchors = _bank_anchors(txs, bad_dates)
    return txs, anchors


def _bank_anchors(txs: list[BankTx], bad_dates: int) -> list[dict]:
    results = []
    results.append({"name": "dates_parsed", "status": "PASS" if bad_dates == 0 else "FAIL",
                    "detail": "全部流水日期可解析" if bad_dates == 0 else f"{bad_dates} 行日期无法解析（已跳过）"})

    zero_amount = [t for t in txs if t.amount <= 0]
    results.append({"name": "amounts_positive", "status": "PASS" if not zero_amount else "FAIL",
                    "detail": "金额全部为正" if not zero_amount else f"{len(zero_amount)} 行金额非正"})

    if all(t.balance is not None for t in txs) and len(txs) >= 2:
        bad_chain = []
        for prev, cur in zip(txs, txs[1:]):
            expect = (cur.balance or 0) - (prev.balance or 0)
            delta = cur.amount if cur.direction == "收" else -cur.amount
            if abs(expect - delta) > _TOL:
                bad_chain.append(cur.src.get("row"))
        results.append({"name": "balance_chain", "status": "PASS" if not bad_chain else "FAIL",
                        "detail": "余额链连续（上笔余额±本笔金额=本笔余额）" if not bad_chain
                        else f"余额链断裂行: {bad_chain[:5]}"})
    else:
        results.append({"name": "balance_chain", "status": "SKIPPED", "detail": "导出无余额列，跳过"})
    return results
