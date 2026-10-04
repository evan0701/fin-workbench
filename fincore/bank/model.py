"""银行流水标准模型与匹配结果。

与科目余额表同一设计原则：各家银行网银导出格式各异，但流水语义收敛为
"日期、方向、金额、对方、摘要、余额"。转换模板（bank mapping.yaml）负责收束。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class BankTx:
    """标准银行流水一行。amount 恒为正数，方向用 direction（收/付）表达。"""

    date: date
    direction: str  # "收" 或 "付"
    amount: float
    counterparty: str = ""
    summary: str = ""
    balance: float | None = None
    src: dict = field(default_factory=dict)


@dataclass
class PlanLine:
    """资金计划执行表的一行（计划口径）。"""

    name: str
    direction: str  # "收" 或 "付"
    amount: float
    counterparty: str = ""
    due: date | None = None  # 计划/期望日期，用于时间窗
    src: dict = field(default_factory=dict)


@dataclass
class Match:
    """一笔匹配：一个计划行 ↔ 一或多笔流水，记录命中规则供审计。"""

    plan: PlanLine
    txs: list[BankTx]
    tier: str  # "exact"（1:1 精确） / "keyword"（关键词聚合）
    rule: str  # 命中规则的说明

    @property
    def matched_amount(self) -> float:
        return sum(t.amount for t in self.txs)


@dataclass
class MatchReport:
    """匹配总报告：匹配结果 + 双边未匹配（对账差异即在此）。"""

    matches: list[Match]
    unmatched_txs: list[BankTx]
    unmatched_plans: list[PlanLine]
    keyword_buckets: list[Match] = field(default_factory=list)

    def summary(self) -> str:
        tx_total = sum(t.amount for t in self.unmatched_txs)
        plan_total = sum(p.amount for p in self.unmatched_plans)
        return (f"计划 {len(self.matches)} 行已匹配（含关键词桶 {len(self.keyword_buckets)}），"
                f"未匹配流水 {len(self.unmatched_txs)} 笔/{tx_total:,.2f} 元，"
                f"未执行计划 {len(self.unmatched_plans)} 行/{plan_total:,.2f} 元")
