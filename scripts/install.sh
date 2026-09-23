#!/usr/bin/env bash
# dsh-coderag 安装脚本（T4-03）：把 Python 引擎装进一个解释器，并自检运行前提。
#
# 它依次做五件事：
#   1. 选解释器——优先 CODERAG_PYTHON，其次当前激活的 conda 环境，最后 PATH 上的 python3/python；
#   2. 校验 Python 版本落在 requires-python 区间（>=3.10,<3.13）；
#   3. 预检该解释器的 SQLite 是否带 FTS5——不带就没必要装了；
#   4. pip install 本仓库；
#   5. 自检「FTS5 可用 + 中文 bigram 往返」，确认检索的最低前提真的成立；然后打印下一步。
#
# 幂等：重复运行只会重新安装并再自检一次，不产生残留、不报错。
#
# 退出码：
#   0  安装完成且自检通过
#   1  pip install 失败
#   2  环境不可用：找不到解释器 / 版本不符 / 没有 pip / 缺 FTS5
#
# 环境变量：
#   CODERAG_PYTHON          指定解释器（AGENTS.md E-06）。不设则按上面的顺序自动探测。
#   CODERAG_PIP_ARGS        追加给 pip 的参数。受限网络下改用镜像：
#                             CODERAG_PIP_ARGS="--index-url https://pypi.tuna.tsinghua.edu.cn/simple"
#   CODERAG_SKIP_INSTALL=1  跳过 pip install，只做自检（重复自检、或包已装好时省时间）。
#   CODERAG_EDITABLE        1 = 强制 editable 安装（pip install -e .）；0 = 强制普通安装。
#                           不设时自动：若本仓库已以 editable 方式装在该解释器上，就保持 editable
#                           ——否则普通安装会把开发安装冻结成一份 site-packages 副本，之后改
#                           `src/` 不再生效（后续任务会在不知情的情况下测到旧代码）。
#
# 用法：bash scripts/install.sh

set -u

cd "$(dirname "$0")/.." || exit 2

say()  { printf '%s\n' "$*"; }
err()  { printf '错误：%s\n' "$*" >&2; }
note() { printf '提示：%s\n' "$*" >&2; }

say "══ dsh-coderag 安装 ════════════════════════════════════════════"
say "仓库：$(pwd)"

# ── 1. 选解释器 ─────────────────────────────────────────────────
PY=""
PY_SOURCE=""
if [ -n "${CODERAG_PYTHON:-}" ]; then
  PY="${CODERAG_PYTHON}"
  PY_SOURCE="CODERAG_PYTHON"
elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "${CONDA_PREFIX}/bin/python" ]; then
  PY="${CONDA_PREFIX}/bin/python"
  PY_SOURCE="当前 conda 环境 ${CONDA_DEFAULT_ENV:-（未命名）}"
else
  for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      PY="$(command -v "${candidate}")"
      PY_SOURCE="PATH 上的 ${candidate}"
      break
    fi
  done
fi

if [ -z "${PY}" ]; then
  err "找不到 Python 解释器。请先装 Python 3.10–3.12（conda 或 python.org 的构建），"
  err "或显式指定：CODERAG_PYTHON=/path/to/python bash scripts/install.sh"
  exit 2
fi

if [ ! -x "${PY}" ]; then
  err "解释器不可执行或不存在：${PY}（来源：${PY_SOURCE}）"
  err "请检查路径，或改用 CODERAG_PYTHON=/path/to/python 指向一个真实存在的解释器。"
  exit 2
fi

if [ -n "${CONDA_PREFIX:-}" ]; then
  say "conda  ：当前 shell 激活的是 ${CONDA_DEFAULT_ENV:-（未命名）} → ${CONDA_PREFIX}"
else
  say "conda  ：未检测到已激活的 conda 环境（CONDA_PREFIX 未设置）"
  if command -v conda >/dev/null 2>&1; then
    note "本机有 conda，但当前没有激活的环境。想用某个环境请先 conda activate <名字>，"
    note "或直接指定：CODERAG_PYTHON=~/miniconda3/envs/<名字>/bin/python bash scripts/install.sh"
  fi
fi
say "解释器 ：${PY}（来源：${PY_SOURCE}）"

# ── 2. 校验 Python 版本 ─────────────────────────────────────────
if ! "${PY}" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)' \
  >/dev/null 2>&1; then
  actual="$("${PY}" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null \
    || printf '未知')"
  err "Python 版本不符：该解释器是 ${actual}，本项目要求 >=3.10,<3.13（pyproject.toml 的 requires-python）。"
  err "请切到 3.10–3.12 的环境后重试，例如："
  err "  conda create -n coderag python=3.12 && conda activate coderag"
  exit 2
fi
say "版本   ：$("${PY}" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')  ✅"

# ── 3. 预检 FTS5（用 stdlib，不需要先装包）──────────────────────
if ! "${PY}" -c 'import sqlite3, sys; c = sqlite3.connect(":memory:"); \
opts = {row[0] for row in c.execute("PRAGMA compile_options")}; \
sys.exit(0 if "ENABLE_FTS5" in opts else 1)' >/dev/null 2>&1; then
  err "该解释器的 SQLite 没有编译 FTS5（ENABLE_FTS5 不在 PRAGMA compile_options 里）。"
  err "本项目用 SQLite FTS5 做检索，缺它无法工作。请换一个带 FTS5 的构建"
  err "（当前 conda 或 python.org 的官方构建都带），或：conda install -c conda-forge sqlite"
  exit 2
fi
say "FTS5   ：可用 ✅（预检）"

# ── 4. pip install ──────────────────────────────────────────────
if [ "${CODERAG_SKIP_INSTALL:-0}" = "1" ]; then
  say "安装   ：已跳过（CODERAG_SKIP_INSTALL=1）"
else
  if ! "${PY}" -m pip --version >/dev/null 2>&1; then
    err "该解释器没有可用的 pip：\"${PY}\" -m pip 失败。"
    err "先运行 \"${PY}\" -m ensurepip --upgrade，或换一个自带 pip 的环境。"
    exit 2
  fi
  # 安装形态：默认普通安装；本仓库已 editable 装在此解释器上时保持 editable（见文件头说明）。
  INSTALL_TARGET="."
  editable_location="$("${PY}" -m pip show dsh-coderag 2>/dev/null \
    | sed -n 's/^Editable project location: //p')"
  case "${CODERAG_EDITABLE:-auto}" in
    1) INSTALL_TARGET="-e ." ;;
    0) INSTALL_TARGET="." ;;
    *)
      if [ -n "${editable_location}" ] && [ "${editable_location}" = "$(pwd -P)" ]; then
        INSTALL_TARGET="-e ."
        say "安装   ：检测到本仓库已 editable 装在此解释器上，保持 editable（改 src/ 立即生效）"
        say "         想装成冻结副本：CODERAG_EDITABLE=0 bash scripts/install.sh"
      fi
      ;;
  esac
  install_display="${CODERAG_PIP_ARGS:-} ${INSTALL_TARGET}"
  say "安装   ：\"${PY}\" -m pip install ${install_display# }"
  # shellcheck disable=SC2086  # CODERAG_PIP_ARGS / INSTALL_TARGET 是空格分隔的参数列表，需要分词
  if ! "${PY}" -m pip install ${CODERAG_PIP_ARGS:-} ${INSTALL_TARGET}; then
    err "pip install 失败。常见原因与对策："
    err "  * 受限网络：CODERAG_PIP_ARGS=\"--index-url https://pypi.tuna.tsinghua.edu.cn/simple\" bash scripts/install.sh"
    err "  * externally-managed-environment（PEP 668）：换用 conda/venv，不建议 --break-system-packages"
    exit 1
  fi
fi

# ── 5. 自检：FTS5 可用 + 中文 bigram 往返 ───────────────────────
say
say "══ 自检：FTS5 可用 + 中文 bigram 往返 ══════════════════════════"
if ! "${PY}" - <<'PYCODE'
import os
import sqlite3
import sys
import tempfile

from dsh_coderag import __version__
from dsh_coderag.sqlite_caps import FTS5_HINT, fts5_available
from dsh_coderag.text import to_bigrams

if not fts5_available():
    print("FTS5   ：不可用", file=sys.stderr)
    print(FTS5_HINT, file=sys.stderr)
    sys.exit(1)
print("FTS5   ：可用 ✅")

document = "校验用户令牌 verify_token 的函数在 token.py"
cjk_query = "用户令牌"
latin_query = "verify_token"
absent_query = "连接池"

bigram_document = to_bigrams(document)
if to_bigrams(bigram_document) != bigram_document:
    print("bigram ：to_bigrams 不是幂等的", file=sys.stderr)
    sys.exit(1)
print("bigram ：幂等 ✅  %r -> %r" % (cjk_query, to_bigrams(cjk_query)))

handle, path = tempfile.mkstemp(suffix=".sqlite3", prefix="dsh-coderag-selfcheck-")
os.close(handle)
try:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5 ("
        "text_bigram, symbol, path, chunk_id UNINDEXED, file_id UNINDEXED,"
        " tokenize = 'unicode61')"
    )
    connection.execute(
        "INSERT INTO chunks_fts (text_bigram, symbol, path, chunk_id, file_id)"
        " VALUES (?, ?, ?, ?, ?)",
        (bigram_document, "verify_token", "token.py", 1, 1),
    )
    connection.commit()

    def paths_for(text: str) -> list[str]:
        rows = connection.execute(
            "SELECT path FROM chunks_fts WHERE text_bigram MATCH ?", (to_bigrams(text),)
        ).fetchall()
        return [row[0] for row in rows]

    cjk_hits = paths_for(cjk_query)
    latin_hits = paths_for(latin_query)
    absent_hits = paths_for(absent_query)
    connection.close()
finally:
    os.unlink(path)

if cjk_hits != ["token.py"]:
    print("中文往返：期望 ['token.py']，实际 %r" % (cjk_hits,), file=sys.stderr)
    sys.exit(1)
if latin_hits != ["token.py"]:
    print("标识符往返：期望 ['token.py']，实际 %r" % (latin_hits,), file=sys.stderr)
    sys.exit(1)
if absent_hits:
    print("阴性对照：期望 []，实际 %r" % (absent_hits,), file=sys.stderr)
    sys.exit(1)

print("往返   ：中文查询命中 ✅  标识符命中 ✅  无关词不命中 ✅")
print("包版本 ：dsh_coderag %s" % __version__)
PYCODE
then
  err "自检失败：这个解释器上的 SQLite / 分词不满足检索前提。"
  err "若上面提示缺 FTS5，请换一个编译了 FTS5 的 Python（conda 或 python.org 的构建）。"
  exit 2
fi

# ── 6. 下一步 ───────────────────────────────────────────────────
say
say "══ 下一步 ══════════════════════════════════════════════════════"
say "1) 建索引并试一次检索（不涉及 DSH）："
say "     \"${PY}\" -m dsh_coderag index /path/to/repo"
say "     \"${PY}\" -m dsh_coderag search \"用户令牌在哪里校验\" --root /path/to/repo"
say
say "2) 告诉 DSH 用哪个解释器——patch 里的默认值是作者机器的路径，必须覆盖（AGENTS.md E-06）："
say "     export CODERAG_PYTHON=\"${PY}\""
say
say "3) 把插件挂进 DSH（二选一）："
say "     ./scripts/dsh --profile web --patch ./cordis.patch.yml        # 直接用 patch 启动"
say "     ./scripts/dsh plugin --profile <名字> add .                   # 装成 profile 层（T4-02）"
say
say "   注意：--profile / --patch 是启动器选项，必须写在 web 自己的选项之前。"
if command -v dsh-coderag >/dev/null 2>&1; then
  say
  say "命令行入口已在 PATH 上：$(command -v dsh-coderag)"
fi
say
say "完成：安装与自检通过 ✅"
