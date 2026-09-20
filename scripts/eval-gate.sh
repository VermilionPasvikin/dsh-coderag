#!/usr/bin/env bash
# L3 一键回归门禁（T3-12）：L1 pytest + L1 指标/或回归 + L2 A/B 门禁。
#
# 退出码：
#   0  全部执行的检查都通过
#   1  至少一项判 FAIL（有回归 / pytest 红 / L2 门禁 FAIL）
#   2  环境或输入不可用（缺语料、缺 baseline 报告）——不是"通过"，绝不静默放行
#
# 路径都可用环境变量覆盖（默认值见下）：
#   CODERAG_GATE_PYTHON / CODERAG_PYTHON  解释器（默认 python）
#   CODERAG_EVAL_CORPUS                   已索引的评测语料副本
#   CODERAG_EVAL_TASKS                    golden 集（默认 eval/tasks.jsonl）
#   CODERAG_L1_BASELINE                   L1 baseline 报告（必需，用于逐 query 对比）
#   CODERAG_L2_BASELINE / _CURRENT        L2 A/B 的两份 report.json（可选）

set -u

cd "$(dirname "$0")/.."

PYTHON="${CODERAG_GATE_PYTHON:-${CODERAG_PYTHON:-python}}"
TASKS="${CODERAG_EVAL_TASKS:-eval/tasks.jsonl}"
CORPUS="${CODERAG_EVAL_CORPUS:-/tmp/dsh-coderag-t3-03-corpus}"
L1_BASELINE="${CODERAG_L1_BASELINE:-eval/runs/l1-baseline.json}"
L1_CURRENT="${CODERAG_L1_CURRENT:-eval/runs/l1-current.json}"
L1_GATE="${CODERAG_L1_GATE_OUT:-eval/runs/l1-gate.json}"
L1_MD="${CODERAG_L1_MARKDOWN:-eval/runs/l1-gate.md}"
L2_BASELINE="${CODERAG_L2_BASELINE:-eval/runs/a-v1/report.json}"
# 当前 B 组：每次改实现/工具文本后产生新的 run，把它设成"当前"，基线保持 A 组。
# 历史对照（a-v1 → b-v1，T3-06）保留在 eval/runs/gate-v1.*。
L2_CURRENT="${CODERAG_L2_CURRENT:-eval/runs/b-r5/report.json}"
L2_GATE="${CODERAG_L2_GATE_OUT:-eval/runs/gate-current.json}"

status=0

echo "══ L1 单元 / 确定性回归（pytest）════════════════════════════════"
if "$PYTHON" -m pytest; then
  echo "L1 pytest：PASS"
else
  echo "L1 pytest：FAIL"
  status=1
fi

echo
echo "══ L1 检索指标 + 逐 query 回归门禁 ══════════════════════════════"
if [ ! -d "$CORPUS" ]; then
  echo "环境不可用：评测语料不存在：$CORPUS"
  echo "先建一份副本并索引，或把 CODERAG_EVAL_CORPUS 指向已索引的副本。"
  exit 2
fi
if [ ! -f "$L1_BASELINE" ]; then
  echo "环境不可用：缺少 L1 baseline 报告：$L1_BASELINE"
  echo "先生成一次（只在冻结某一版基线时做）："
  echo "  $PYTHON -m dsh_coderag.eval run --tasks $TASKS --root $CORPUS \\"
  echo "      --expect-golden-version <版本> --out $L1_BASELINE"
  exit 2
fi
"$PYTHON" -m dsh_coderag.eval gate \
  --tasks "$TASKS" --root "$CORPUS" --baseline "$L1_BASELINE" \
  --out "$L1_CURRENT" --gate-out "$L1_GATE" --markdown "$L1_MD"
l1=$?
case "$l1" in
  0) echo "L1 gate：PASS（报告 ${L1_CURRENT}，逐条对比 ${L1_MD}）" ;;
  1) echo "L1 gate：FAIL"; status=1 ;;
  *) echo "L1 gate：无法执行（退出码 ${l1}）"; exit 2 ;;
esac

echo
echo "══ L2 端到端 A/B 门禁 ══════════════════════════════════════════"
if [ -f "$L2_BASELINE" ] && [ -f "$L2_CURRENT" ]; then
  "$PYTHON" scripts/ab_eval.py gate \
    --baseline "$L2_BASELINE" --current "$L2_CURRENT" \
    --out "$L2_GATE" --markdown "${L2_GATE%.json}.md"
  l2=$?
  if [ "$l2" -eq 0 ]; then
    echo "L2 gate：PASS"
  else
    echo "L2 gate：FAIL"
    status=1
  fi
else
  echo "跳过 L2：缺报告（${L2_BASELINE} / ${L2_CURRENT}）"
  echo "提示：L2 需要模型 API key，用 scripts/ab_eval.py run 产出这两份 report.json。"
fi

echo
echo "══ 汇总：成功标准 S1–S4 + 回归条数 ═════════════════════════════"
"$PYTHON" - "$L1_GATE" "$L2_GATE" <<'PY'
import json
import sys
from pathlib import Path

def load(path: str) -> dict | None:
    file = Path(path)
    if not file.is_file():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

def fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    return str(value)

def fmt_count(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)

l1 = load(sys.argv[1])
l2 = load(sys.argv[2])

if l1 is None:
    print("S1 Success@5    = n/a")
    print("S2 MRR          = n/a")
    print("S4 token_median = n/a")
    l1_regressions = None
else:
    overall = l1["metrics"]["overall"]
    print(f"S1 Success@5    = {fmt(overall['success'].get('5'))}")
    print(f"S2 MRR          = {fmt(overall['mrr'])}")
    print(f"S4 token_median = {fmt_count(overall['token_median'])}")
    l1_regressions = l1["regression_count"]

if l2 is None:
    print("S3 E2E delta    = n/a（未跑 L2）")
    l2_regressions = None
else:
    delta = l2.get("delta_pp")
    print(f"S3 E2E delta    = {'n/a' if delta is None else f'{delta:+.1f}pp'}")
    l2_regressions = len(l2.get("regressions", []))

def count(value: int | None) -> str:
    return "n/a" if value is None else str(value)

known = [c for c in (l1_regressions, l2_regressions) if c is not None]
combined = "n/a" if not known else str(sum(known))
print(
    f"回归条数        = L1 {count(l1_regressions)}（逐 query）"
    f" + L2 {count(l2_regressions)}（用例级） = {combined}"
)
PY

echo
if [ "$status" -eq 0 ]; then
  echo "══ 门禁：PASS ══"
else
  echo "══ 门禁：FAIL ══"
fi
exit "$status"
