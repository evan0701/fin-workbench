---
name: fin-workbench
description: 财务工作台总入口。当用户给出金蝶/用友导出的科目余额表、财务报表等文件，或提出月度财务取数、筛选、对账、填表需求时触发。路由到：解析锚点校验（fincore）、科目余额筛选台账、支付税费台账、fill-forge 铸表。核心纪律：确定性内核算数，LLM 不进计算路径，每个数字可溯源，锚点不全绿不放行。
metadata:
  openclaw:
    emoji: "🏛️"
---

# fin-workbench · 财务工作台

把金蝶、用友导出的"难用"表格变成可筛选、可审计的 HTML 工作台与自动填写技能。

## 定位（一句话）

ERP 管"记进去"，本工作台管"记完之后为什么、怎么办、怎么核对" —— 只读分析层，不碰记账，不做直连申报。

## 三条架构红线（任何场景不可突破）

1. **确定性内核**：解析、校验、取数、填写全部由 `fincore` 与各技能的确定性代码完成；LLM 只做映射草稿、口径问答与复核引导，永远不直接产生填入报表的数字。
2. **锚点闸门**：数据源解析后必须跑锚点校验（借贷平衡、跨月衔接、编码唯一），任一 FAIL 即拒绝下游动作。
3. **数据不出网**：所有产物为本地单文件 HTML / xlsx，零外链；真实单位数据不进本仓库，demo 只用星澜虚构数据集。

## 能力路由

| 用户意图 | 走哪里 |
|---|---|
| "导出来的余额表没法看/要筛选" | `fincore view-balance` → 科目余额筛选台账 HTML |
| "这个月交了多少税、构成怎样" | `fincore view-tax` → 支付税费台账 HTML |
| "我每个月都要填/做 X" | `skills/fin-scout`（判定重复劳动是否值得铸造） |
| "这个动作我重复很多遍了/又搞一遍了" | `skills/fin-scout` → 达标后移交 `skills/fill-forge` |
| "我每个月都要填 X 表，数据源是 Y" | `skills/fill-forge` → 铸造新的填写技能 |
| "帮我填 X 台账/快报" | 对应已铸造技能（示例：`forged/stat-monthly-ledger`） |
| "新家 ERP 的导出格式对不上" | 新建一份 mapping.yaml（照 `demo/mapping_jinDie.yaml` 抄结构），映射助手辅助生成草稿 |
| "这个动作我重复很多遍了" | 提示走 fill-forge 沉淀，评估铸造新技能 |

## 快速开始

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python demo/gen_demo_source.py                       # 生成虚构 demo 数据
.venv/bin/python -m fincore parse --config demo/mapping_jinDie.yaml \
  --file "demo/示例导出/科目余额表_2025-09_乱格式.xlsx" --period 2025-09 \
  --prev out/tb-08.json --out out/tb-09.json                   # 解析 + 锚点校验
.venv/bin/python -m fincore view-balance --model out/tb-09.json --out demo/输出/科目余额筛选台账.html
.venv/bin/python -m fincore view-tax --model out/tb-08.json --model out/tb-09.json --out demo/输出/支付税费台账.html
```

或一键：`bash demo/run_demo.sh`（含铸造技能的例行填写演示）。

## 体系地图

```
fincore（确定性内核）：mapping.yaml → 标准模型 → 锚点 → 视图
skills/fin-scout（元技能·发现者）：识别重复劳动 → 判定 → 移交铸造
skills/fill-forge（铸表技能）：源表×目标表 → 新的填写技能
forged/*（铸出的技能）：stat-monthly-ledger（已通过回填考试）
demo/（星澜虚构数据）：乱格式样本 + 台账模板 + 一键脚本
docs/：接入指南（mapping 怎么写）+ 铸造指南（fill-forge 细则）
```
