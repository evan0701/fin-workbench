"""标准数据模型：科目余额表的标准中间层。

所有视图、取数规则、填写技能都只依赖这一层，
不直接接触任何一家 ERP 的导出格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class TBRow:
    """科目余额表的一行。金额单位由 meta.unit 声明（默认元），不在此换算。"""

    code: str
    name: str
    level: int
    opening_debit: float = 0.0
    opening_credit: float = 0.0
    period_debit: float = 0.0
    period_credit: float = 0.0
    closing_debit: float = 0.0
    closing_credit: float = 0.0
    src: dict = field(default_factory=dict)  # 溯源：{file, sheet, row}

    @property
    def is_balance_subject(self) -> bool:
        """资产负债类科目：期初或期末有余额。损益类科目结转后期初/期末均为 0。"""
        return any(
            abs(v) > 1e-9
            for v in (self.opening_debit, self.opening_credit, self.closing_debit, self.closing_credit)
        )

    @property
    def net_opening(self) -> float:
        """期初净额，借方为正、贷方为负。"""
        return self.opening_debit - self.opening_credit

    @property
    def net_closing(self) -> float:
        """期末净额，借方为正、贷方为负。"""
        return self.closing_debit - self.closing_credit


@dataclass
class StandardTB:
    """一张标准化的科目余额表。"""

    meta: dict
    rows: list[TBRow]

    def by_code(self, code: str) -> TBRow | None:
        return next((r for r in self.rows if r.code == code), None)

    def children(self, prefix: str) -> list[TBRow]:
        """取某科目编码前缀下的所有明细行（不含根科目自身时由调用方过滤）。"""
        return [r for r in self.rows if r.code.startswith(prefix)]

    def totals(self) -> dict:
        return {
            "opening_debit": sum(r.opening_debit for r in self.rows),
            "opening_credit": sum(r.opening_credit for r in self.rows),
            "period_debit": sum(r.period_debit for r in self.rows),
            "period_credit": sum(r.period_credit for r in self.rows),
            "closing_debit": sum(r.closing_debit for r in self.rows),
            "closing_credit": sum(r.closing_credit for r in self.rows),
        }

    def to_dict(self) -> dict:
        return {"meta": self.meta, "rows": [asdict(r) for r in self.rows]}

    @classmethod
    def from_dict(cls, data: dict) -> "StandardTB":
        rows = [TBRow(**row) for row in data["rows"]]
        return cls(meta=data["meta"], rows=rows)


@dataclass
class AnchorResult:
    """锚点校验结果。锚点全绿 = 这份映射配置可信。"""

    name: str
    status: str  # PASS / FAIL / SKIPPED
    detail: str = ""

    @property
    def badge(self) -> str:
        return {"PASS": "🟢", "FAIL": "🔴", "SKIPPED": "⚪"}[self.status]
