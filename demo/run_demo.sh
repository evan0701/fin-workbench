#!/usr/bin/env bash
# fin-workbench 一键演示：生成虚构数据 → 解析锚点 → 两个 HTML 台账 → 铸造技能例行填写
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3

echo "== 1/5 生成星澜虚构 demo 数据 =="
"$PY" demo/gen_demo_source.py

mkdir -p out demo/输出

echo "== 2/5 解析 2025-08（首月）=="
"$PY" -m fincore parse --config demo/mapping_jinDie.yaml \
  --file "demo/示例导出/科目余额表_2025-08_乱格式.xlsx" --period 2025-08 --out out/tb-08.json

echo "== 3/5 解析 2025-09（衔接校验）=="
"$PY" -m fincore parse --config demo/mapping_jinDie.yaml \
  --file "demo/示例导出/科目余额表_2025-09_乱格式.xlsx" --period 2025-09 \
  --prev out/tb-08.json --out out/tb-09.json

echo "== 4/5 生成 HTML 工作台 =="
"$PY" -m fincore view-balance --model out/tb-09.json --out "demo/输出/科目余额筛选台账.html"
"$PY" -m fincore view-tax --model out/tb-08.json --model out/tb-09.json --out "demo/输出/支付税费台账.html"

echo "== 5/6 铸造技能例行填写 2025-09 台账 =="
"$PY" forged/stat-monthly-ledger/fill.py \
  --source "demo/示例导出/科目余额表_2025-09_乱格式.xlsx" \
  --period 2025-09 \
  --prev out/tb-08.json \
  --out "demo/输出/统计月度台账_2025-09_成品.xlsx"

echo "== 6/6 银行流水 ↔ 资金计划两级匹配 =="
"$PY" -m fincore bank-match \
  --bank-mapping demo/mapping_bank.yaml \
  --bank-file "demo/示例导出/银行流水_2025-09_乱格式.xlsx" \
  --plan "demo/统计台账模板/资金计划_2025-09.yaml" \
  --company "星澜科技有限公司" --period 2025-09 \
  --out "demo/输出/资金计划执行台账.html"

echo ""
echo "✅ 演示完成。产物在 demo/输出/："
ls -1 demo/输出/
