"""Console entry point for the dsh-coderag command.

This module owns the project's cross-platform entry point (PROJECT.md 6.5.1,
T6-02). Its `doctor` and `install-deps` subcommands carry the install logic
that used to live in `scripts/install.sh`, so Windows, macOS and Linux run one
code path instead of two drifting shell implementations; `scripts/install.sh`
and `scripts/dsh` are thin wrappers that only locate an interpreter and
forward. It does not start the MCP server; that entry point lives in
dsh_coderag.server.

Exit codes, kept from `scripts/install.sh` because they are the contract users
already script against:

  0  success
  1  the requested operation failed (pip install, or an unexpected error)
  2  environment unusable: no pip, a Python version outside `requires-python`,
     or a SQLite build without FTS5

Failures are reported as one structured JSON object on stderr carrying `status`
and `code`, and never as a traceback (the CLI counterpart of RL-09).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from dsh_coderag import __version__
from dsh_coderag.config import ENV_MAX_FILES, ConfigError, load_config_for
from dsh_coderag.sqlite_caps import FTS5_HINT, fts5_available
from dsh_coderag.text import to_bigrams

if TYPE_CHECKING:
    from dsh_coderag.indexer import IndexSummary

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ENV_UNUSABLE = 2

ENV_PYTHON = "CODERAG_PYTHON"
ENV_PIP_ARGS = "CODERAG_PIP_ARGS"
ENV_SKIP_INSTALL = "CODERAG_SKIP_INSTALL"
ENV_EDITABLE = "CODERAG_EDITABLE"

DISTRIBUTION_NAME = "dsh-coderag"
PYPROJECT = "pyproject.toml"
PROJECT_TABLE = "[project]"

SELF_CHECK_DOCUMENT = "校验用户令牌 verify_token 的函数在 token.py"
SELF_CHECK_PATH = "token.py"
SELF_CHECK_SYMBOL = "verify_token"
SELF_CHECK_QUERY = "用户令牌"

_FTS5_SELF_CHECK_DDL = (
    "CREATE VIRTUAL TABLE chunks_fts USING fts5 ("
    "text_bigram, symbol, path, chunk_id UNINDEXED, file_id UNINDEXED,"
    " tokenize = 'unicode61')"
)
"""Minimal FTS5 table for the self-check.

It mirrors the engine's `chunks_fts` columns rather than importing the DDL from
`indexer`, because the self-check has to run on an interpreter where the
engine's own dependencies are still missing - which is the state
`install-deps` starts from.
"""

_ROUND_TRIPS: tuple[tuple[str, str, bool], ...] = (
    ("中文往返", SELF_CHECK_QUERY, True),
    ("标识符往返", SELF_CHECK_SYMBOL, True),
    ("无关词不命中", "连接池", False),
)

_SCALAR = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"\s*$')
_VERSION = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*$")
_CLAUSE = re.compile(r"^\s*(>=|<=|==|>|<)\s*(\d+(?:\.\d+)*)\s*$")

_COMPARISONS: dict[str, Callable[[tuple[int, ...], tuple[int, ...]], bool]] = {
    ">=": lambda left, right: left >= right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
    ">": lambda left, right: left > right,
    "<": lambda left, right: left < right,
}


class CliError(Exception):
    """A failure the CLI reports as structured JSON instead of a traceback.

    `code` is a stable machine-readable string, `hint` is the actionable part
    an operator needs, and `exit_code` preserves the documented exit-code
    contract above.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        exit_code: int = EXIT_ENV_UNUSABLE,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.exit_code = exit_code


@dataclass(frozen=True)
class Check:
    """One precondition and its outcome, rendered in the doctor report."""

    name: str
    ok: bool
    detail: str
    code: str = ""
    hint: str | None = None


def _emit(line: str = "") -> None:
    """Write one report line to stdout (ruff T20 keeps this module print-free)."""
    sys.stdout.write(line + "\n")


def report_error(error: CliError) -> int:
    """Write one structured error object to stderr and return its exit code."""
    payload: dict[str, str] = {
        "status": "error",
        "code": error.code,
        "message": error.message,
    }
    if error.hint is not None:
        payload["hint"] = error.hint
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return error.exit_code


def source_root() -> Path | None:
    """Return the checkout that contains this package, or None when installed.

    The two environment subcommands install *this* repository, so they need the
    directory holding `pyproject.toml`. An installed copy in site-packages has
    no such parent, and every caller treats that as a structured failure rather
    than guessing a directory.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / PYPROJECT
        if candidate.is_file() and read_project_scalars(candidate).get("name") == DISTRIBUTION_NAME:
            return parent
    return None


def read_project_scalars(pyproject: Path) -> dict[str, str]:
    """Read the single-line string keys of pyproject.toml's `[project]` table.

    Python 3.10 has no `tomllib`, and RL-10 keeps the runtime dependency list
    closed, so this reads exactly the flat `key = "value"` pairs the CLI needs
    (`name`, `requires-python`) and ignores nested tables and arrays. A key it
    cannot see stays absent, and the caller raises instead of guessing.
    """
    values: dict[str, str] = {}
    inside_project = False
    for raw in pyproject.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            inside_project = line == PROJECT_TABLE
            continue
        if not inside_project:
            continue
        match = _SCALAR.match(line)
        if match is not None:
            values[match.group(1)] = match.group(2)
    return values


def requires_python_spec() -> str:
    """Return the `requires-python` range, read rather than hardcoded (RL-07)."""
    root = source_root()
    if root is not None:
        spec = read_project_scalars(root / PYPROJECT).get("requires-python")
        if spec:
            return spec
    installed = _installed_requires_python()
    if installed:
        return installed
    raise CliError(
        "REQUIRES_PYTHON_UNREADABLE",
        "读不到 requires-python：既没有本仓库的 pyproject.toml，也没有已安装分发的元数据",
        hint="在本仓库内运行，或先安装本包（pip install .）",
    )


def _installed_requires_python() -> str | None:
    """Read `Requires-Python` from the installed distribution, if there is one.

    The value is generated from pyproject.toml at build time, so using it still
    counts as reading rather than hardcoding (RL-07).
    """
    from importlib.metadata import PackageNotFoundError, metadata

    try:
        return metadata(DISTRIBUTION_NAME)["Requires-Python"]
    except (PackageNotFoundError, KeyError):
        return None


def current_version() -> tuple[int, ...]:
    """Return the running interpreter's version as a comparable tuple."""
    return tuple(sys.version_info[:3])


def version_text(version: Sequence[int]) -> str:
    """Render a version tuple the way operators read it."""
    return ".".join(str(part) for part in version)


def parse_version(text: str) -> tuple[int, ...]:
    """Parse a dotted numeric version, raising CliError on anything else."""
    match = _VERSION.match(text)
    if match is None:
        raise CliError(
            "REQUIRES_PYTHON_UNSUPPORTED_SPEC",
            f"无法解析版本号：{text!r}",
            hint="requires-python 只支持点分数字版本，如 3.10 或 3.10.4",
        )
    return tuple(int(part) for part in match.group(1).split("."))


def version_satisfies(version: tuple[int, ...], spec: str) -> bool:
    """Return whether version falls inside a comma-separated PEP 440 range.

    Only `>=`, `<=`, `==`, `>` and `<` are understood; an operator this project
    never uses raises instead of being ignored, because silently dropping a
    clause would report a wrong Python as supported. Comparison zero-pads the
    shorter side, so `<3.13` correctly accepts `3.10.21` and `>=3.10` accepts
    `3.10.0`.
    """
    clauses = [clause for clause in spec.split(",") if clause.strip()]
    if not clauses:
        raise CliError("REQUIRES_PYTHON_UNSUPPORTED_SPEC", f"requires-python 为空：{spec!r}")
    for clause in clauses:
        match = _CLAUSE.match(clause)
        if match is None:
            raise CliError(
                "REQUIRES_PYTHON_UNSUPPORTED_SPEC",
                f"不支持的版本约束：{clause.strip()!r}",
                hint="只支持 >= <= == > < 五种运算符",
            )
        left, right = _pad(version, parse_version(match.group(2)))
        if not _COMPARISONS[match.group(1)](left, right):
            return False
    return True


def _pad(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Zero-pad both versions to the same width so tuple comparison is correct."""
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def environment_checks() -> list[Check]:
    """Check the interpreter preconditions that need no third-party wheel."""
    spec = requires_python_spec()
    version = version_text(current_version())
    fts5 = fts5_available()
    return [
        Check("解释器", True, sys.executable),
        Check(
            "版本",
            version_satisfies(current_version(), spec),
            f"{version}（要求 {spec}）",
            "PYTHON_VERSION_UNSUPPORTED",
            f"该解释器是 {version}，本项目要求 {spec}（pyproject.toml 的 requires-python）；"
            "请切到区间内的 Python 后重试",
        ),
        Check(
            "FTS5",
            fts5,
            "可用" if fts5 else "不可用",
            "FTS5_UNAVAILABLE",
            FTS5_HINT,
        ),
    ]


def self_check() -> list[Check]:
    """Verify FTS5 plus a CJK bigram round trip through a real FTS5 table.

    The round trip is the point: the engine expands CJK runs into overlapping
    bigrams on both the indexing and the query side, and doing it on only one
    side yields silent zero recall (ADR-07).
    """
    document = to_bigrams(SELF_CHECK_DOCUMENT)
    fts5 = fts5_available()
    checks = [
        Check("FTS5", fts5, "可用" if fts5 else "不可用", "FTS5_UNAVAILABLE", FTS5_HINT),
        Check(
            "bigram",
            to_bigrams(document) == document,
            f"幂等；{SELF_CHECK_QUERY!r} -> {to_bigrams(SELF_CHECK_QUERY)!r}",
            "SELF_CHECK_FAILED",
            "to_bigrams 必须幂等，否则索引侧与查询侧不对称（ADR-07）",
        ),
    ]
    if not fts5:
        return checks
    checks.extend(_round_trip_checks())
    return checks


def _round_trip_checks() -> list[Check]:
    """Query the freshly built self-check table the way the engine queries its index."""
    with tempfile.TemporaryDirectory(prefix="dsh-coderag-selfcheck-") as folder:
        connection = sqlite3.connect(Path(folder) / "selfcheck.sqlite3")
        try:
            connection.execute(_FTS5_SELF_CHECK_DDL)
            connection.execute(
                "INSERT INTO chunks_fts (text_bigram, symbol, path, chunk_id, file_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (to_bigrams(SELF_CHECK_DOCUMENT), SELF_CHECK_SYMBOL, SELF_CHECK_PATH, 1, 1),
            )
            connection.commit()
            return [
                _round_trip(connection, label, query, hit)
                for label, query, hit in _ROUND_TRIPS
            ]
        finally:
            connection.close()


def _round_trip(connection: sqlite3.Connection, label: str, query: str, expect_hit: bool) -> Check:
    """Run one self-check query and compare it against the expected outcome."""
    rows = connection.execute(
        "SELECT path FROM chunks_fts WHERE text_bigram MATCH ?", (to_bigrams(query),)
    ).fetchall()
    paths = [row[0] for row in rows]
    return Check(
        label,
        (SELF_CHECK_PATH in paths) == expect_hit,
        f"{query!r} -> {paths!r}",
        "SELF_CHECK_FAILED",
    )


def print_checks(checks: Sequence[Check]) -> None:
    """Render precondition results, one line each."""
    for check in checks:
        _emit(f"[{'ok' if check.ok else 'FAIL'}] {check.name}：{check.detail}")


def require(checks: Sequence[Check], *, exit_code: int = EXIT_ENV_UNUSABLE) -> None:
    """Raise CliError for the first failed check, preserving its code and hint."""
    for check in checks:
        if not check.ok:
            raise CliError(
                check.code or "CHECK_FAILED",
                f"{check.name}：{check.detail}",
                hint=check.hint,
                exit_code=exit_code,
            )


def run_pip(command: Sequence[str], cwd: Path) -> int:
    """Run a pip command and return its exit code (test seam for the install step)."""
    return subprocess.run(list(command), cwd=cwd, check=False).returncode


def pip_available() -> bool:
    """Return whether this interpreter has a usable `python -m pip`."""
    return subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        check=False,
    ).returncode == 0


def pip_extra_args() -> list[str]:
    """Split CODERAG_PIP_ARGS into arguments the way the shell script did.

    Whitespace only: the value is a plain argument list, so an argument that
    needs embedded spaces is out of contract here (and was in the shell too).
    """
    return os.environ.get(ENV_PIP_ARGS, "").split()


def install_target(root: Path) -> list[str]:
    """Return the pip target, honouring CODERAG_EDITABLE and never freezing a dev install.

    Defaulting to plain `.` would replace an editable development install with a
    frozen copy in site-packages, after which edits under `src/` stop taking
    effect and later test runs silently measure old code.
    """
    setting = os.environ.get(ENV_EDITABLE, "auto").strip()
    if setting == "1":
        return ["-e", "."]
    if setting == "0":
        return ["."]
    if setting not in ("", "auto"):
        raise CliError(
            "CODERAG_EDITABLE_INVALID",
            f"CODERAG_EDITABLE 只能是 auto、1 或 0，实际是 {setting!r}",
            hint="把它设成 1（editable）、0（普通安装）或 auto（默认），或干脆不设",
        )
    location = editable_location()
    if location is not None and _same_directory(location, root):
        _emit("安装   ：检测到本仓库已 editable 装在此解释器上，保持 editable（改 src/ 立即生效）")
        return ["-e", "."]
    return ["."]


def editable_location() -> str | None:
    """Return pip's recorded editable project location, or None."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", DISTRIBUTION_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("Editable project location:"):
            return line.split(":", 1)[1].strip()
    return None


def _same_directory(left: str, right: Path) -> bool:
    """Compare two paths after resolution, tolerating an unreadable one."""
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return False


def _run_index(args: argparse.Namespace) -> int:
    """Build or refresh the index for the workspace at args.path."""
    from dsh_coderag.indexer import index_sync

    root = Path(args.path)
    if not root.is_dir():
        raise CliError(
            "WORKSPACE_NOT_FOUND",
            f"要索引的目录不存在：{root}",
            hint="换成实际存在的路径——索引只读工作区，不会凭空创建目录",
            exit_code=EXIT_FAILED,
        )
    config = load_config_for(root)
    summary = index_sync(root, config)
    _emit(
        f"indexed {summary.files} files, {summary.chunks} chunks "
        f"into {summary.root}/.coderag/index.sqlite3"
    )
    if summary.files == 0:
        _report_empty_index(summary, config.extra_extensions)
    return EXIT_OK


def _report_empty_index(summary: IndexSummary, extra_extensions: frozenset[str]) -> None:
    """Explain an index that succeeded over nothing (T6-16).

    A workspace of game assets is a legitimate zero: the walk saw the files and
    skipped none of them, because an unlisted extension is not a skip. Reporting
    only `indexed 0 files` leaves the user unable to tell that apart from a
    broken workspace — and the whitelist it names must be the effective one, or
    a user who just added their extension is told it is not supported (T6-17).
    """
    from dsh_coderag.walker import effective_extensions

    listed = " ".join(sorted(effective_extensions(extra_extensions)))
    _emit(
        f"注意：没有可索引的文件——遍历看到 {summary.seen_files} 个文件，其中 "
        f"{summary.other_extensions} 个的后缀不在白名单内（{listed}）。"
    )
    _emit("      索引本身是成功的，但检索不会有结果；按内容查找请改用 grep 之类的工具。")
    if not extra_extensions:
        _emit("      要收录别的后缀，设 CODERAG_EXTRA_EXTENSIONS（例如 '.mxml,.as'）后重跑。")


def _run_search(args: argparse.Namespace) -> int:
    """Search the workspace index and print one `path:lines` line per hit."""
    from dsh_coderag.searcher import search
    from dsh_coderag.types import SearchStatus

    config = load_config_for(Path(args.root))
    result = search(
        Path(args.root), args.query, k=args.limit, max_tokens=config.max_tokens
    )
    if result.status is not SearchStatus.READY:
        detail = result.message or result.hint or ""
        suffix = f": {detail}" if detail else ""
        sys.stderr.write(f"{result.status.value}{suffix}\n")
        return EXIT_FAILED
    for hit in result.hits:
        _emit(f"{hit.path}:{hit.start_line}-{hit.end_line}")
    return EXIT_OK


def _copyable_assignment(interpreter: str) -> str:
    """The one-liner that sets CODERAG_PYTHON in this machine's default shell.

    Windows PowerShell and POSIX shells disagree on the syntax, and the only
    reason to print the line is that it can be pasted as-is: an `export` line is
    useless in PowerShell, which is what a Windows user is reading this with.
    `platform.system()` is used rather than `sys.platform` because mypy folds
    the latter per host platform, which makes one branch unreachable under
    `warn_unreachable` on every machine.
    """
    if platform.system() == "Windows":
        return f'$env:{ENV_PYTHON} = "{interpreter}"'
    return f'export {ENV_PYTHON}="{interpreter}"'


MCP_ROW_ID = "mcp-coderag"
MCP_CLIENT_PACKAGE = "@deepseek-ai/dsh-mcp-client"


def profile_override_block(interpreter: str) -> list[str]:
    """The profile-layer override that pins DSH to this interpreter.

    An id-targeted patch replaces the whole `config` object, so the block has to
    restate every field worth keeping — otherwise `serverName` / `transport` /
    `args` disappear and the row stops working. Only fields that differ from the
    engine's own defaults are listed: the bundle set the rest to values the
    engine already defaults to, so this block is equivalent to the bundle config
    with `command` pinned to a real interpreter.

    It exists because the failure it fixes is invisible: a plugin whose
    `command` cannot be spawned still loads, it just never produces any tools.
    """
    return [
        f"- id: {MCP_ROW_ID}",
        f"  name: '{MCP_CLIENT_PACKAGE}'",
        "  config:",
        "    serverName: coderag",
        "    transport: stdio",
        f"    command: '{interpreter}'",
        "    args: ['-c', 'import dsh_coderag.server as s; s.run()']",
        "    env:",
        "      CODERAG_ROOT: !!js process.env.CODERAG_ROOT ?? process.cwd()",
    ]


def _run_doctor(_: argparse.Namespace) -> int:
    """Report whether this interpreter can run the engine and how to point DSH at it."""
    _emit(f"== dsh-coderag doctor {__version__} ==")
    checks = environment_checks()
    print_checks(checks)
    require(checks)
    _emit()
    _emit(f"{ENV_PYTHON}={sys.executable}")
    _emit(_copyable_assignment(sys.executable))
    _emit("那一行只对从同一个终端启动的 dsh 有效；")
    _emit("桌面版是从快捷方式启动的，继承不到终端变量，必须用下面这段。")
    _emit()
    _emit("把它放进你实际在跑的那个 profile 的 cordis.patch.yml：")
    _emit("  $DSH_HOME/profiles/<profile>/cordis.patch.yml")
    _emit("若文件里还有占位符 `[]`，用下面这段【替换】掉那一行；")
    _emit("若已有条目（DSH 自己的设置也在里面），就【追加】到末尾——不要替换整个文件。")
    _emit("id 定向 patch 会整体替换 config，所以下面把要保留的字段都写全了：")
    _emit()
    for line in profile_override_block(sys.executable):
        _emit(line)
    configured = os.environ.get(ENV_PYTHON, "")
    if configured and not _same_directory(configured, Path(sys.executable)):
        _emit(f"注意：当前环境里的 {ENV_PYTHON}={configured}，与本次探测到的解释器不同。")
    return EXIT_OK


def _run_install_deps(args: argparse.Namespace) -> int:
    """Install this checkout into the running interpreter, then self-check it."""
    _emit(f"== dsh-coderag install-deps {__version__} ==")
    checks = environment_checks()
    print_checks(checks)
    require(checks)
    if args.skip_install or os.environ.get(ENV_SKIP_INSTALL) == "1":
        _emit(f"安装   ：已跳过（{ENV_SKIP_INSTALL}=1）")
    else:
        _install()
    _emit()
    _emit("== 自检：FTS5 可用 + 中文 bigram 往返 ==")
    self_checks = self_check()
    print_checks(self_checks)
    require(self_checks)
    _emit(f"包版本 ：dsh_coderag {__version__}")
    _emit("完成：安装与自检通过")
    return EXIT_OK


def _install() -> None:
    """Run `pip install` for this checkout, mapping every failure to a CliError."""
    root = source_root()
    if root is None:
        raise CliError(
            "SOURCE_CHECKOUT_NOT_FOUND",
            "找不到本仓库的 pyproject.toml，无法执行 pip install",
            hint="已安装的副本没有源码可装：在仓库根改用 `pip install -e .`（editable），"
                 "或把仓库的 `src` 目录加进 `PYTHONPATH` 后再运行",
        )
    if not pip_available():
        raise CliError(
            "PIP_UNAVAILABLE",
            f'该解释器没有可用的 pip："{sys.executable}" -m pip 失败',
            hint=f'先运行 "{sys.executable}" -m ensurepip --upgrade，或换一个自带 pip 的环境',
        )
    command = [sys.executable, "-m", "pip", "install", *pip_extra_args(), *install_target(root)]
    _emit(f'安装   ：{" ".join(command)}')
    code = run_pip(command, root)
    if code != 0:
        raise CliError(
            "PIP_INSTALL_FAILED",
            f"pip install 失败（退出码 {code}）",
            hint="受限网络可设 CODERAG_PIP_ARGS=--index-url <镜像>；"
            "PEP 668 的 externally-managed-environment 请改用 conda/venv",
            exit_code=EXIT_FAILED,
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the dsh-coderag command."""
    parser = argparse.ArgumentParser(
        prog="dsh-coderag",
        description="Codebase retrieval engine for DeepSeek Harness.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"dsh-coderag {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")
    index_parser = subparsers.add_parser(
        "index",
        help="Build or refresh the index for a workspace directory.",
    )
    index_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Workspace directory to index (default: current directory).",
    )
    search_parser = subparsers.add_parser(
        "search",
        help="Search the workspace index.",
    )
    search_parser.add_argument("query", help="Keyword or natural-language query.")
    search_parser.add_argument(
        "--root",
        default=".",
        help="Workspace root to search (default: current directory).",
    )
    search_parser.add_argument(
        "-k",
        "--limit",
        type=int,
        default=5,
        help="Maximum number of hits (default: 5).",
    )
    subparsers.add_parser(
        "doctor",
        help="Check this interpreter and print the CODERAG_PYTHON value to use.",
    )
    install_parser = subparsers.add_parser(
        "install-deps",
        help="Install this checkout into the running interpreter, then self-check it.",
    )
    install_parser.add_argument(
        "--skip-install",
        action="store_true",
        help=f"Only self-check; same as {ENV_SKIP_INSTALL}=1.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "index": _run_index,
        "search": _run_search,
        "doctor": _run_doctor,
        "install-deps": _run_install_deps,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_OK
    try:
        return handler(args)
    except ConfigError as error:
        # A bad value is a configuration problem, not an unexpected failure: it
        # belongs to the documented "environment unusable" exit code, and the
        # message already names the variable (T6-17).
        return report_error(
            CliError(
                "CONFIG_INVALID",
                str(error),
                hint="改正该环境变量的取值后重跑；doctor 会打印当前生效的设置。",
                exit_code=EXIT_ENV_UNUSABLE,
            )
        )
    except CliError as error:
        return report_error(error)
    except Exception as error:  # noqa: BLE001 - RL-09: no traceback may escape the CLI
        too_many = _as_too_many_files(error)
        if too_many is not None:
            return report_error(too_many)
        return report_error(
            CliError(
                "CLI_UNEXPECTED_ERROR",
                f"{type(error).__name__}: {error}",
                exit_code=EXIT_FAILED,
            )
        )


def _as_too_many_files(error: Exception) -> CliError | None:
    """Translate a workspace too large for the limit into an actionable error (T6-22).

    The condition is expected, and the walker error already carries the real count
    and its own code (RL-08), but the generic handler used to replace both with
    CLI_UNEXPECTED_ERROR and leak the class name — leaving the user to guess which
    variable to set and how to write it. `walker` is imported here rather than at
    module level to keep `doctor` and `install-deps` usable in an environment that
    is still missing third-party dependencies.
    """
    from dsh_coderag.walker import TooManyFilesError

    if not isinstance(error, TooManyFilesError):
        return None
    assignment = (
        f"$env:{ENV_MAX_FILES} = '{error.actual_count}'"
        if platform.system() == "Windows"
        else f"export {ENV_MAX_FILES}={error.actual_count}"
    )
    return CliError(
        error.code.value,
        str(error),
        hint=(
            f"把 {ENV_MAX_FILES} 设到 {error.actual_count} 或更高再重跑（{assignment}），"
            "或只索引子目录。"
        ),
        exit_code=EXIT_FAILED,
    )


if __name__ == "__main__":
    sys.exit(main())
