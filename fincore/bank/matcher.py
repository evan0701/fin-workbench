"""资金计划 ↔ 银行流水的两级确定性匹配。

移植自 Evan 的银行流水匹配系统（旧版 normal_matcher 的 1:1 精确匹配 +
已用行跟踪，special_matcher 的关键词聚合思想），去掉业务硬编码与 Excel 耦合，
改为纯函数 + 配置驱动。铁律：LLM 不进匹配路径；每个匹配记录命中规则。

两级顺序：
1. exact（1:1）：金额相等（±0.01）+ 方向一致 + 对方名称匹配 + 计划日期时间窗内；
   已用计划行/流水不复用（沿用旧版 used_rows 语义）。
2. aggregate（1:N 聚合）：一笔计划对应多笔到账（如回款分批）。在同一对方、
   时间窗内的剩余流水中做有界组合搜索（≤4 笔、组合唯一才成立）。
3. keyword（聚合桶）：剩余流水按关键词规则归桶（银行手续费、代发工资等
   不进资金计划的固定项目），桶内汇总金额。
剩余双边即为对账差异（未匹配流水 + 未执行计划）。
"""

from __future__ import annotations

from datetime import timedelta
from itertools import combinations

from .model import BankTx, Match, MatchReport, PlanLine

AMOUNT_TOL = 0.01
DEFAULT_DATE_WINDOW = 30  # 计划行无 due 或窗口未配置时的默认时间窗（天）
MAX_AGGREGATE = 4         # 1:N 聚合的最大流水笔数（有界搜索）


def _norm(text: str) -> str:
    """名称归一化：去空白与常见标点，统一大写。"""
    for ch in " ()（）【】[]-—_·.,，、\u3000":
        text = text.replace(ch, "")
    return text.upper()


def name_match(a: str, b: str) -> bool:
    """对方名称匹配：归一化后相等，或一方包含另一方（短名 ≥3 字防误伤，如"李文"⊆"李文文"）。"""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return (na in nb or nb in na) and min(len(na), len(nb)) >= 3


def _in_window(tx: BankTx, plan: PlanLine, window_days: int) -> bool:
    if plan.due is None:
        return True
    return abs((tx.date - plan.due).days) <= window_days


def match_plans(txs: list[BankTx], plans: list[PlanLine],
                keyword_rules: list[dict] | None = None,
                date_window_days: int = DEFAULT_DATE_WINDOW) -> MatchReport:
    """两级匹配主入口。keyword_rules 见模块 docstring 与 demo/mapping_bank.yaml。"""
    used_tx: set[int] = set()     # 流水下标（等价旧版 matched_transaction_ids）
    used_plan: set[int] = set()   # 计划行下标（等价旧版 used_execution_rows）
    matches: list[Match] = []

    # --- Tier 1: 1:1 精确匹配 ---
    for pi, plan in enumerate(plans):
        candidates = [
            i for i, t in enumerate(txs)
            if i not in used_tx
            and t.direction == plan.direction
            and abs(t.amount - plan.amount) <= AMOUNT_TOL
            and (not plan.counterparty or name_match(t.counterparty, plan.counterparty))
            and _in_window(t, plan, date_window_days)
        ]
        if candidates:
            chosen = min(candidates, key=lambda i: abs((txs[i].date - plan.due).days) if plan.due else 0)
            used_tx.add(chosen)
            used_plan.add(pi)
            window = f"±{date_window_days}天" if plan.due else "不限"
            matches.append(Match(plan=plan, txs=[txs[chosen]], tier="exact",
                                 rule=f"金额相等+方向一致+对方匹配+时间窗{window}"))

    # --- Tier 2: 1:N 聚合（同一对方多笔到账合并对应一笔计划） ---
    for pi, plan in enumerate(plans):
        if pi in used_plan:
            continue
        pool = [i for i, t in enumerate(txs)
                if i not in used_tx
                and t.direction == plan.direction
                and (not plan.counterparty or name_match(t.counterparty, plan.counterparty))
                and _in_window(t, plan, date_window_days)]
        combos = [c for n in range(2, min(MAX_AGGREGATE, len(pool)) + 1)
                  for c in combinations(pool, n)
                  if abs(sum(txs[i].amount for i in c) - plan.amount) <= AMOUNT_TOL]
        if len(combos) == 1:  # 组合唯一才成立，多解时留给人工（宁可漏配不可错配）
            combo = combos[0]
            used_tx.update(combo)
            used_plan.add(pi)
            matches.append(Match(plan=plan, txs=[txs[i] for i in combo], tier="aggregate",
                                 rule=f"聚合匹配: {len(combo)} 笔同对方流水合计=计划金额"))

    # --- Tier 3: 关键词聚合桶（仅对未被计划占用的流水） ---
    buckets: list[Match] = []
    for rule in keyword_rules or []:
        keys = [k for k in rule.get("match_any", []) if k]
        if not keys:
            continue
        hit = [i for i, t in enumerate(txs)
               if i not in used_tx
               and (not rule.get("direction") or t.direction == rule["direction"])
               and any(k in t.summary or k in t.counterparty for k in keys)]
        if hit:
            used_tx.update(hit)
            buckets.append(Match(
                plan=PlanLine(name=rule["name"], direction=rule.get("direction", "付"),
                              amount=sum(txs[i].amount for i in hit)),
                txs=[txs[i] for i in hit], tier="keyword",
                rule=f"关键词命中: {'/'.join(keys)}",
            ))

    unmatched_txs = [t for i, t in enumerate(txs) if i not in used_tx]
    unmatched_plans = [p for pi, p in enumerate(plans) if pi not in used_plan]
    return MatchReport(matches=matches, unmatched_txs=unmatched_txs,
                       unmatched_plans=unmatched_plans, keyword_buckets=buckets)
