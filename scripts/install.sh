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

PY=${CODERAG_PYTHON:-}
if [ -z "$PY" ]; then
  # 每个候选都必须真的能跑：Windows 上 python3 可能是 Microsoft Store 占位符，
  # 而 CONDA_PREFIX 也可能存在却不可用——两种都会白装一场。
  for candidate in "${CONDA_PREFIX:-}/bin/python" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c '' >/dev/null 2>&1; then
      PY=$(command -v "$candidate")
      break
    fi
  done
fi
[ -n "$PY" ] || {
  echo "错误：找不到可用的 Python 解释器。请设 CODERAG_PYTHON=/path/to/python" >&2
  exit 2
}
# 显式给的解释器也要真的能跑，不能只看可执行位：占位符与坏符号链接都存在。
[ -x "$PY" ] && "$PY" -c '' >/dev/null 2>&1 || {
  echo "错误：解释器不可执行或不存在：${PY}" >&2
  exit 2
}

# PYTHONPATH 让全新 clone（尚未装进解释器）也能跑：CLI 只依赖标准库。
PYTHONPATH="${repo}/src${PYTHONPATH:+:${PYTHONPATH}}" exec "$PY" -m dsh_coderag install-deps "$@"
