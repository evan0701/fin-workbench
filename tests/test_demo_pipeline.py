"""端到端：真实 demo 产物上的解析 → 锚点 → 视图全链路。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demo_sources():
    """确保 demo 产物存在（生成器只用星澜虚构数据）。"""
    src = REPO / "demo" / "示例导出" / "科目余额表_2025-08_乱格式.xlsx"
    if not src.exists():
        subprocess.run([sys.executable, str(REPO / "demo" / "gen_demo_source.py")],
                       check=True, cwd=REPO, capture_output=True)
    return REPO / "demo" / "示例导出"


def test_full_pipeline_on_demo(demo_sources, tmp_path):
    from fincore.parser import load_mapping, parse
    from fincore.views import render_balance_ledger, render_tax_ledger

    cfg = load_mapping(REPO / "demo" / "mapping_jinDie.yaml")
    m08, a08 = parse(cfg, demo_sources / "科目余额表_2025-08_乱格式.xlsx")
    m09, a09 = parse(cfg, demo_sources / "科目余额表_2025-09_乱格式.xlsx", prev_model=m08)

    assert len(m08.rows) == 33
    assert all(a.status in ("PASS", "SKIPPED") for a in a08)
    assert all(a.status == "PASS" for a in a09), [a.detail for a in a09 if a.status != "PASS"]
    # 9 月期初 = 8 月期末（锚点已验，再抽一个科目确认）
    assert m09.by_code("1002").net_opening == pytest.approx(m08.by_code("1002").net_closing, abs=0.01)

    html_balance = render_balance_ledger(m09)
    html_tax = render_tax_ledger([m08, m09])
    assert "https://" not in html_balance and "http://" not in html_balance
    assert "https://" not in html_tax and "http://" not in html_tax
    assert "支付税费台账" in html_tax
