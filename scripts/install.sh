#!/bin/sh
# dsh-coderag 的安装入口（薄包装）。
#
# 这里**只有**「找到解释器 → 转发」。解释器探测、版本区间校验、FTS5 预检、
# 安装与装后自检全部住在 Python CLI 的 install-deps 子命令里
# （src/dsh_coderag/__main__.py），这样三个平台走同一条代码路径，且那条路径
# 能被 pytest 直接覆盖——两套 shell 实现必然漂移，且无法被测试覆盖
# （PROJECT.md §6.5.1 的设计决定）。所以本文件里没有依赖清单，也没有安装动作。
#
# 用法：bash scripts/install.sh
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(dirname -- "$here")

pick_python() {
  for candidate in python3 python; do
    # 只认真的能跑的解释器：Windows 上 python3 可能是 Microsoft Store 占位符。
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c '' >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

PY=${CODERAG_PYTHON:-}
if [ -z "$PY" ] && [ -n "${CONDA_PREFIX:-}" ] && [ -x "${CONDA_PREFIX}/bin/python" ]; then
  PY="${CONDA_PREFIX}/bin/python"
fi
[ -n "$PY" ] || PY=$(pick_python) || {
  echo "错误：找不到可用的 Python 解释器。请设 CODERAG_PYTHON=/path/to/python" >&2
  exit 2
}
[ -x "$PY" ] || { echo "错误：解释器不可执行或不存在：${PY}" >&2; exit 2; }

# PYTHONPATH 让全新 clone（尚未装进解释器）也能跑：CLI 只依赖标准库。
PYTHONPATH="${repo}/src${PYTHONPATH:+:${PYTHONPATH}}" exec "$PY" -m dsh_coderag install-deps "$@"
