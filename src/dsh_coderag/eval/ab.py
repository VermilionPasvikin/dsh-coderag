"""L2 end-to-end A/B runner for dsh-coderag (EVAL.md 3.5-3.6).

This is the self-built fallback that `EVAL.md` 3.6 prescribes after `T3-00`
found `dsh-eval-harness` 0.4.0 incompatible with this DSH's `session.v3.*`
naming. It forks one headless DSH per case attempt, reads the durable session
log DSH leaves behind, extracts the tool-call trace and the final answer,
applies the `EVAL.md` 3.4 assertions, and reports `pass@k` / `pass^k` plus a
baseline gate.

It never calls a model itself — the model runs inside DSH — and it contains no
L1 logic (that lives in `tasks` / `runner` / `metrics`). It does not author
cases.

Three deliberate properties:

* The runner makes DSH write **uncompressed** session logs by overriding the
  `session-persistence-jsonl` row (`compression: none`, `root` pointed at the
  attempt directory). No zstd decoder is needed to read them back.
* The session trace comes from the **durable log**, not stdout, so a run whose
  stdout is truncated by an event cap still yields a complete trace.
* Cases are **JSON**. `EVAL.md` 3.4 shows YAML, but this project declares no
  YAML dependency and the test environment has none; see the deviation note in
  `EVAL.md` 3.6.

The session log is a header line followed by event lines:
`{version, id, ...}` then repeated `{type, seq, time, data}`.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SESSION_LOG_RE = re.compile(r"^session\.v(?P<version>\d+)\.jsonl$")
"""Uncompressed generation log written when `compression: none` is configured."""

COMPRESSED_SUFFIX = ".jsonl.zstd"
"""Suffix we refuse: the runner must not need a zstd decoder to read a trace."""

DEFAULT_TIMEOUT_S = 900.0
"""Wall-clock cap for one headless attempt."""

RUN_SCHEMA = "dsh-coderag/ab-run/v1"

ASSERTION_KEYS = frozenset(
    {
        "turn_end",
        "tools_called",
        "tools_not_called",
        "tool_args_contains",
        "tool_result_contains",
        "output_contains",
        "output_matches",
        "max_steps",
        "max_tokens",
        "no_tool_errors",
    }
)
"""Assertion keys this runner implements; `output_judge` is deliberately absent."""


class AbError(Exception):
    """A case, session log, or run configuration is unusable."""


# ── cases ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Assertions:
    """The EVAL.md 3.4 assertions this runner can decide mechanically."""

    turn_end: str | None = None
    tools_called: tuple[str, ...] = ()
    tools_not_called: tuple[str, ...] = ()
    tool_args_contains: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    tool_result_contains: tuple[str, ...] = ()
    output_contains: tuple[str, ...] = ()
    output_matches: tuple[str, ...] = ()
    max_steps: int | None = None
    max_tokens: int | None = None
    no_tool_errors: bool = False


@dataclass(frozen=True)
class Case:
    """One L2 case: a prompt plus the assertions its run must satisfy.

    `answer_paths` and `notes` are review metadata: they never affect scoring.
    `answer_paths` names the files a correct answer should be based on, which
    lets a test check they are inside the indexed corpus (a case whose answer
    is filtered out of the index would be unfair to the retrieval group).
    `accept` / `reject` are reviewed sample answers: the output assertions must
    accept every `accept` string and reject every `reject` string, so an
    over-tight (false failure) or over-loose (false pass) regex is caught
    before the set is ever run against a model.
    """

    name: str
    prompt: str
    tags: tuple[str, ...]
    expect: Assertions
    answer_paths: tuple[str, ...] = ()
    notes: str | None = None
    accept: tuple[str, ...] = ()
    reject: tuple[str, ...] = ()


CASE_KEYS = frozenset(
    {"name", "prompt", "tags", "assert", "answer_paths", "notes", "accept", "reject"}
)
"""Top-level case fields; anything else is a typo and fails the load."""


def load_cases(directory: Path) -> list[Case]:
    """Load every `*.json` case in `directory`, failing loudly on any defect."""
    if not directory.is_dir():
        raise AbError(f"cases 目录不存在：{directory}")
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise AbError(f"{directory} 下没有任何 *.json 用例")
    cases: list[Case] = []
    seen: set[str] = set()
    for path in paths:
        case = _load_case(path)
        if case.name in seen:
            raise AbError(f"{path}: 用例名 {case.name!r} 重复")
        seen.add(case.name)
        cases.append(case)
    return cases


def _load_case(path: Path) -> Case:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AbError(f"{path}: 无法解析：{exc}") from exc
    if not isinstance(payload, dict):
        raise AbError(f"{path}: 顶层必须是 JSON 对象")
    unknown = sorted(set(payload) - CASE_KEYS)
    if unknown:
        raise AbError(f"{path}: 未知字段 {unknown}")
    name = payload.get("name")
    prompt = payload.get("prompt")
    if not isinstance(name, str) or not name:
        raise AbError(f"{path}: name 必须是非空字符串")
    if not isinstance(prompt, str) or not prompt:
        raise AbError(f"{path}: prompt 必须是非空字符串")
    tags_payload = payload.get("tags", [])
    if not isinstance(tags_payload, list) or not all(isinstance(t, str) for t in tags_payload):
        raise AbError(f"{path}: tags 必须是字符串数组")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise AbError(f"{path}: notes 必须是字符串")
    expect = _parse_assertions(payload.get("assert", {}), path)
    return Case(
        name=name,
        prompt=prompt,
        tags=tuple(tags_payload),
        expect=expect,
        answer_paths=tuple(_string_list(payload.get("answer_paths", []), path, "answer_paths")),
        notes=notes,
        accept=tuple(_string_list(payload.get("accept", []), path, "accept")),
        reject=tuple(_string_list(payload.get("reject", []), path, "reject")),
    )


def _parse_assertions(payload: Any, path: Path) -> Assertions:
    if not isinstance(payload, dict):
        raise AbError(f"{path}: assert 必须是 JSON 对象")
    if "output_judge" in payload:
        raise AbError(
            f"{path}: output_judge 需要模型评审，本 runner 不实现；"
            "结构断言全过之后再单独做，不要静默忽略"
        )
    unknown = sorted(set(payload) - ASSERTION_KEYS)
    if unknown:
        raise AbError(f"{path}: 未知断言 {unknown}")
    turn_end = payload.get("turn_end")
    if turn_end is not None and not isinstance(turn_end, str):
        raise AbError(f"{path}: turn_end 必须是字符串")
    max_steps = payload.get("max_steps")
    max_tokens = payload.get("max_tokens")
    for label, value in (("max_steps", max_steps), ("max_tokens", max_tokens)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            raise AbError(f"{path}: {label} 必须是整数")
    args = payload.get("tool_args_contains", {})
    if not isinstance(args, dict):
        raise AbError(f"{path}: tool_args_contains 必须是对象")
    tool_args: dict[str, tuple[str, ...]] = {}
    for tool, needles in args.items():
        if not isinstance(tool, str) or not _is_string_list(needles):
            raise AbError(f"{path}: tool_args_contains.{tool} 必须是字符串数组")
        tool_args[tool] = tuple(needles)
    no_tool_errors = payload.get("no_tool_errors", False)
    if not isinstance(no_tool_errors, bool):
        raise AbError(f"{path}: no_tool_errors 必须是布尔值")
    return Assertions(
        turn_end=turn_end,
        tools_called=tuple(_string_list(payload.get("tools_called", []), path, "tools_called")),
        tools_not_called=tuple(
            _string_list(payload.get("tools_not_called", []), path, "tools_not_called")
        ),
        tool_args_contains=tool_args,
        tool_result_contains=tuple(
            _string_list(payload.get("tool_result_contains", []), path, "tool_result_contains")
        ),
        output_contains=tuple(
            _string_list(payload.get("output_contains", []), path, "output_contains")
        ),
        output_matches=tuple(
            _string_list(payload.get("output_matches", []), path, "output_matches")
        ),
        max_steps=max_steps,
        max_tokens=max_tokens,
        no_tool_errors=no_tool_errors,
    )


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _string_list(value: Any, path: Path, label: str) -> list[str]:
    if not _is_string_list(value):
        raise AbError(f"{path}: {label} 必须是字符串数组")
    return list(value)


# ── session log ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ToolCall:
    """One model-requested tool invocation."""

    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResult:
    """One tool result as the model saw it."""

    tool_call_id: str
    is_error: bool
    text: str


@dataclass(frozen=True)
class Trace:
    """Everything the assertions are allowed to look at for one attempt.

    `final_text` is the last committed assistant message's text: the answer the
    model produced. `all_text` concatenates every assistant text so debugging
    does not need the raw log.
    """

    session_id: str | None
    tool_calls: tuple[ToolCall, ...]
    tool_results: tuple[ToolResult, ...]
    final_text: str
    all_text: str
    steps: int
    turn_end: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    interrupted: bool


def parse_session(text: str) -> Trace:
    """Parse one uncompressed session log (header line + event lines).

    Raises:
        AbError: If the log is empty, a line is not JSON, or the header carries
            no version.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise AbError("会话日志为空")
    records: list[Any] = []
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AbError(f"会话日志第 {index + 1} 行不是合法 JSON：{exc}") from exc
    header = records[0]
    if not isinstance(header, dict) or "version" not in header:
        raise AbError("会话日志首行不是带 version 的 header")

    session_id = header.get("id") if isinstance(header.get("id"), str) else None
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []
    assistant_texts: list[str] = []
    steps = 0
    turn_end: str | None = None
    input_tokens = output_tokens = total_tokens = 0
    interrupted = False
    for record in records[1:]:
        if not isinstance(record, dict):
            continue
        kind = record.get("type")
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        if kind == "tool/call":
            tool_calls.append(
                ToolCall(
                    name=str(data.get("name", "")),
                    arguments=str(data.get("arguments", "")),
                )
            )
        elif kind == "tool/result":
            tool_results.append(_parse_tool_result(data))
        elif kind == "assistant/message":
            text = _assistant_text(data)
            if text:
                assistant_texts.append(text)
            usage = data.get("usage")
            if isinstance(usage, dict):
                input_tokens += _int(usage.get("inputTokens"))
                output_tokens += _int(usage.get("outputTokens"))
                total_tokens += _int(usage.get("totalTokens"))
            if data.get("interrupted") is True:
                interrupted = True
        elif kind == "step/start":
            steps += 1
        elif kind == "turn/end":
            reason = data.get("reason")
            if isinstance(reason, dict) and isinstance(reason.get("kind"), str):
                turn_end = reason["kind"]
            elif isinstance(reason, str):
                turn_end = reason
    return Trace(
        session_id=session_id,
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results),
        final_text=assistant_texts[-1] if assistant_texts else "",
        all_text="\n".join(assistant_texts),
        steps=steps,
        turn_end=turn_end,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        interrupted=interrupted,
    )


def _parse_tool_result(data: Mapping[str, Any]) -> ToolResult:
    message = data.get("message")
    if not isinstance(message, dict):
        return ToolResult(tool_call_id="", is_error=False, text="")
    content = message.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        return ToolResult(tool_call_id="", is_error=False, text="")
    block = content[0]
    text = "".join(
        item.get("text", "")
        for item in block.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    )
    return ToolResult(
        tool_call_id=str(block.get("toolCallId", "")),
        is_error=block.get("isError") is True,
        text=text,
    )


def _assistant_text(data: Mapping[str, Any]) -> str:
    message = data.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    return "".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def find_session_log(root: Path) -> Path:
    """Locate the root session log under `root`.

    Subagent logs carry `parentSession` in their header and are skipped, so a
    run that spawned subagents still yields the top-level trace.

    Raises:
        AbError: If no uncompressed log exists (actionable message about
            `compression: none`), or if the choice between two root logs is
            ambiguous.
    """
    if not root.is_dir():
        raise AbError(f"会话目录不存在：{root}")
    root_logs: list[Path] = []
    for path in sorted(root.rglob("session.v*.jsonl")):
        if SESSION_LOG_RE.match(path.name) is None:
            continue
        if _log_parent(path) is None:
            root_logs.append(path)
    if not root_logs:
        compressed = sorted(root.rglob(f"*{COMPRESSED_SUFFIX}"))
        if compressed:
            raise AbError(
                f"只找到压缩日志 {compressed[0].name}；"
                "请让 session-persistence-jsonl 使用 compression: none"
            )
        raise AbError(f"{root} 下没有 session.v*.jsonl")
    if len(root_logs) > 1:
        names = ", ".join(str(path) for path in root_logs)
        raise AbError(f"{root} 下有多个根会话日志，无法判定：{names}")
    return root_logs[0]


def _log_parent(path: Path) -> str | None:
    """Return the header's `parentSession` (string) or None for a root log."""
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
    except OSError:
        return None
    try:
        header = json.loads(first)
    except json.JSONDecodeError:
        return None
    if not isinstance(header, dict):
        return None
    parent = header.get("parentSession")
    return parent if isinstance(parent, str) else None


# ── assertions ──────────────────────────────────────────────────────────
def evaluate(case: Case, trace: Trace) -> list[str]:
    """Return every failed assertion as a human-readable string."""
    expect = case.expect
    failures: list[str] = []
    if expect.turn_end is not None and trace.turn_end != expect.turn_end:
        failures.append(f"turn_end 期望 {expect.turn_end!r}，实际 {trace.turn_end!r}")
    called = [call.name for call in trace.tool_calls]
    if expect.tools_called and not is_subsequence(tuple(called), expect.tools_called):
        failures.append(f"tools_called {list(expect.tools_called)} 不是 {called} 的保序子序列")
    forbidden = sorted(set(called) & set(expect.tools_not_called))
    if forbidden:
        failures.append(f"调用了禁止的工具 {forbidden}")
    for tool, needles in expect.tool_args_contains.items():
        arguments = [call.arguments for call in trace.tool_calls if call.name == tool]
        if not any(all(needle in raw for needle in needles) for raw in arguments):
            failures.append(f"{tool} 的参数未同时包含 {list(needles)}")
    if expect.tool_result_contains:
        results = [result.text for result in trace.tool_results]
        for needle in expect.tool_result_contains:
            if not any(needle in text for text in results):
                failures.append(f"没有任何工具结果包含 {needle!r}")
    for needle in expect.output_contains:
        if needle not in trace.final_text:
            failures.append(f"最终回答不含 {needle!r}")
    for pattern in expect.output_matches:
        if re.search(pattern, trace.final_text, re.MULTILINE) is None:
            failures.append(f"最终回答不匹配正则 {pattern!r}")
    if expect.max_steps is not None and trace.steps > expect.max_steps:
        failures.append(f"步数 {trace.steps} 超过 max_steps={expect.max_steps}")
    if expect.max_tokens is not None and trace.total_tokens > expect.max_tokens:
        failures.append(f"token {trace.total_tokens} 超过 max_tokens={expect.max_tokens}")
    if expect.no_tool_errors:
        errors = [result.tool_call_id for result in trace.tool_results if result.is_error]
        if errors:
            failures.append(f"有工具返回错误：{errors}")
    return failures


def is_subsequence(actual: Sequence[str], expected: Sequence[str]) -> bool:
    """Whether `expected` appears inside `actual` in order (gaps allowed)."""
    iterator = iter(actual)
    return all(item in iterator for item in expected)


# ── reliability statistics ──────────────────────────────────────────────
def pass_at_k(successes: int, trials: int, k: int) -> float | None:
    """Probability at least one of k draws succeeds, without replacement."""
    if trials <= 0 or k <= 0 or successes < 0 or successes > trials or k > trials:
        return None
    return 1.0 - _comb(trials - successes, k) / _comb(trials, k)


def pass_caret_k(successes: int, trials: int, k: int) -> float | None:
    """Probability all k draws succeed, without replacement.

    This is the unbiased estimator `C(c,k)/C(n,k)` the tool comparison favours
    over the plug-in `(c/n)**k`, which is convex and therefore biased upward.
    """
    if trials <= 0 or k <= 0 or successes < 0 or successes > trials or k > trials:
        return None
    return _comb(successes, k) / _comb(trials, k)


def _comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


# ── running ─────────────────────────────────────────────────────────────
def compression_overlay(sessions_root: Path) -> str:
    """Overlay patch making DSH write plain `session.v*.jsonl` into `root`."""
    return (
        "# Generated by scripts/ab_eval.py: read traces without a zstd decoder.\n"
        "- id: session-persistence-jsonl\n"
        "  config:\n"
        f"    root: '{sessions_root}'\n"
        "    compression: none\n"
    )


def build_command(
    dsh: Sequence[str], profile: str, patches: Sequence[Path], prompt: str
) -> list[str]:
    """Build the headless argv for one attempt."""
    command = list(dsh)
    if profile:
        command += ["--profile", profile]
    for patch in patches:
        command += ["--patch", str(patch)]
    command.append(prompt)
    return command


def run_group(
    cases: Sequence[Case],
    *,
    group: str,
    out_dir: Path,
    dsh: Sequence[str],
    profile: str,
    workspace: Path,
    patches: Sequence[Path] = (),
    trials: int = 1,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    env: Mapping[str, str] | None = None,
    dsh_home: Path | None = None,
) -> dict[str, Any]:
    """Run every case `trials` times and return a report dict.

    Each attempt gets its own directory: its overlay points the session log
    there, so discovery never has to disambiguate two runs.
    """
    if trials < 1:
        raise AbError(f"trials 必须 ≥ 1，实际 {trials}")
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, trials + 1):
            attempt_dir = (
                out_dir / ".sessions" / f"{index:03d}-{_slug(case.name)}" / f"attempt-{attempt}"
            )
            sessions_root = attempt_dir / "sessions"
            sessions_root.mkdir(parents=True, exist_ok=True)
            overlay = attempt_dir / "compression.patch.yml"
            overlay.write_text(compression_overlay(sessions_root), encoding="utf-8")
            attempts.append(
                _run_attempt(
                    case,
                    attempt_dir=attempt_dir,
                    sessions_root=sessions_root,
                    dsh=dsh,
                    profile=profile,
                    patches=[overlay, *patches],
                    workspace=workspace,
                    timeout_s=timeout_s,
                    env=env,
                    dsh_home=dsh_home,
                )
            )
        results.append(_case_result(case, attempts, trials))
    successes_total = sum(case["successes"] for case in results)
    attempts_total = len(cases) * trials
    return {
        "schema": RUN_SCHEMA,
        "group": group,
        "profile": profile,
        "trials": trials,
        "workspace": str(workspace),
        "dsh": list(dsh),
        "cases": results,
        "successes": successes_total,
        "attempts": attempts_total,
        "task_success_rate": successes_total / attempts_total if attempts_total else None,
    }


def _run_attempt(
    case: Case,
    *,
    attempt_dir: Path,
    sessions_root: Path,
    dsh: Sequence[str],
    profile: str,
    patches: Sequence[Path],
    workspace: Path,
    timeout_s: float,
    env: Mapping[str, str] | None,
    dsh_home: Path | None,
) -> dict[str, Any]:
    command = build_command(dsh, profile, patches, case.prompt)
    child_env = dict(os.environ if env is None else env)
    if dsh_home is not None:
        child_env["DSH_HOME"] = str(dsh_home)
    started = time.monotonic()
    stdout = stderr = ""
    exit_code: int | None = None
    error: str | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired:
        error = f"超时 {timeout_s}s"
    except OSError as exc:
        error = f"无法启动 dsh：{exc}"
    duration_s = time.monotonic() - started
    attempt: dict[str, Any] = {
        "passed": False,
        "failures": [],
        "error": error,
        "exit_code": exit_code,
        "duration_s": round(duration_s, 3),
        "session_log": None,
        "steps": 0,
        "total_tokens": 0,
        "tool_calls": [],
        "turn_end": None,
        "final_text": "",
        "stderr_tail": stderr[-2000:],
    }
    if error is None:
        try:
            log_path = find_session_log(sessions_root)
        except AbError as exc:
            attempt["error"] = str(exc)
            attempt["stdout_tail"] = stdout[-2000:]
            return attempt
        trace = parse_session(log_path.read_text(encoding="utf-8"))
        attempt["session_log"] = str(log_path)
        attempt["steps"] = trace.steps
        attempt["total_tokens"] = trace.total_tokens
        attempt["tool_calls"] = [call.name for call in trace.tool_calls]
        attempt["turn_end"] = trace.turn_end
        attempt["final_text"] = trace.final_text
        failures = evaluate(case, trace)
        attempt["failures"] = failures
        attempt["passed"] = not failures and exit_code == 0
        if exit_code != 0:
            attempt["failures"] = [*failures, f"dsh 退出码 {exit_code}"]
    return attempt


def _case_result(case: Case, attempts: list[dict[str, Any]], trials: int) -> dict[str, Any]:
    successes = sum(1 for attempt in attempts if attempt["passed"])
    return {
        "name": case.name,
        "tags": list(case.tags),
        "prompt": case.prompt,
        "answer_paths": list(case.answer_paths),
        "notes": case.notes,
        "attempts": attempts,
        "successes": successes,
        "trials": trials,
        "pass@k": pass_at_k(successes, trials, 1),
        "pass^k": pass_caret_k(successes, trials, trials),
    }


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "case"


# ── gate ────────────────────────────────────────────────────────────────
def gate(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two group reports and report regressions, not just the mean.

    A case whose success rate dropped is a regression; a case that only appeared
    on one side is reported as such rather than silently counted either way.
    """
    base_cases = {case["name"]: case for case in baseline["cases"]}
    current_cases = {case["name"]: case for case in current["cases"]}
    common = sorted(set(base_cases) & set(current_cases))
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    per_case: list[dict[str, Any]] = []
    for name in common:
        before = base_cases[name]["successes"] / baseline["trials"]
        after = current_cases[name]["successes"] / current["trials"]
        per_case.append(
            {"case": name, "baseline_rate": before, "current_rate": after, "delta": after - before}
        )
        entry = {"case": name, "baseline_rate": before, "current_rate": after}
        if after < before:
            regressions.append(entry)
        elif after > before:
            improvements.append(entry)
    base_rate = baseline["task_success_rate"]
    current_rate = current["task_success_rate"]
    delta_pp = (
        (current_rate - base_rate) * 100.0
        if base_rate is not None and current_rate is not None
        else None
    )
    return {
        "schema": "dsh-coderag/ab-gate/v1",
        "baseline_group": baseline["group"],
        "current_group": current["group"],
        "baseline_task_success_rate": base_rate,
        "current_task_success_rate": current_rate,
        "delta_pp": delta_pp,
        "only_in_baseline": sorted(set(base_cases) - set(current_cases)),
        "only_in_current": sorted(set(current_cases) - set(base_cases)),
        "regressions": regressions,
        "improvements": improvements,
        "per_case": per_case,
        "s3_met": delta_pp is not None and delta_pp >= 10.0,
        "passed": not regressions,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render one run report as Markdown."""
    lines = [
        f"# L2 run: {report['group']}",
        "",
        f"- profile: `{report['profile']}` ｜ trials: {report['trials']}",
        f"- workspace: `{report['workspace']}`",
        f"- taskSuccess: {_rate(report['task_success_rate'])} "
        f"({report['successes']}/{report['attempts']})",
        "",
        "| case | successes | rate | steps | tokens | turn_end |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        steps = [attempt["steps"] for attempt in case["attempts"]]
        tokens = [attempt["total_tokens"] for attempt in case["attempts"]]
        ends = sorted({str(attempt["turn_end"]) for attempt in case["attempts"]})
        lines.append(
            f"| {case['name']} | {case['successes']}/{case['trials']} "
            f"| {_rate(case['successes'] / case['trials'])} "
            f"| {_average(steps)} | {_average(tokens)} "
            f"| {', '.join(ends)} |"
        )
    failures = [
        (case["name"], attempt["failures"])
        for case in report["cases"]
        for attempt in case["attempts"]
        if not attempt["passed"]
    ]
    if failures:
        lines += ["", "## 失败明细", ""]
        for name, items in failures:
            detail = "; ".join(items) if items else "(attempt error)"
            lines.append(f"- **{name}**: {detail}")
    lines.append("")
    return "\n".join(lines)


def render_gate_markdown(result: Mapping[str, Any]) -> str:
    """Render one gate result as Markdown."""
    lines = [
        "# L2 gate",
        "",
        f"- baseline: `{result['baseline_group']}` → {_rate(result['baseline_task_success_rate'])}",
        f"- current: `{result['current_group']}` → {_rate(result['current_task_success_rate'])}",
        f"- delta: {_pp(result['delta_pp'])} ｜ S3(≥+10pp): {result['s3_met']}",
        f"- gate: {'PASS' if result['passed'] else 'FAIL'} "
        f"（回归 {len(result['regressions'])} 条）",
    ]
    if result["regressions"]:
        lines += ["", "## 回归", ""]
        lines += [
            f"- {entry['case']}: {_rate(entry['baseline_rate'])} → {_rate(entry['current_rate'])}"
            for entry in result["regressions"]
        ]
    if result["improvements"]:
        lines += ["", "## 改善", ""]
        lines += [
            f"- {entry['case']}: {_rate(entry['baseline_rate'])} → {_rate(entry['current_rate'])}"
            for entry in result["improvements"]
        ]
    lines.append("")
    return "\n".join(lines)


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _average(values: Sequence[int]) -> str:
    return "n/a" if not values else f"{sum(values) / len(values):.1f}"


def _pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}pp"


def render_case_review(cases: Sequence[Case]) -> str:
    """Render the human review table for the committed cases.

    The table carries everything a reviewer needs to judge ambiguity and
    realism, plus the accept/reject samples that pin what each assertion
    accepts. It is generated (never hand-edited) so it cannot drift from the
    case files.
    """
    lines = [
        "# L2 用例审核表",
        "",
        f"> 共 **{len(cases)}** 条。本文件由 `python scripts/case-review.py` 从 "
        "`cases/*.json` 生成，",
        "> **请勿手改**；改用例请改 JSON 后重新生成（有测试守着一致性）。",
        "",
        "## 怎么审：5 个性质，其中 3 个已机械核查",
        "",
        "| 性质 | 谁查 | 怎么查 |",
        "|---|---|---|",
        "| 答案文件在索引里（否则检索组永远赢不了） | 机械 ✅ | "
        "`CODERAG_L2_CORPUS=<副本> pytest tests/test_cases.py` |",
        "| prompt 不泄漏答案路径 | 机械 ✅ | "
        "`leak_candidates` 扫描 + `tests/test_cases.py` |",
        "| 断言不误杀正确答案 / 不放过错误答案 | 机械 ✅ | "
        "每条下方的「应接受 / 应拒绝」样例，逐条真跑正则 |",
        "| 问题真实、且只有一个合理答案 | **人** | "
        "读每条「问」与「出处」：我会这么问吗？别人会不会答到别的文件？ |",
        "| 配比与 `max_steps` 合理 | **人** | "
        "看桶的分布；`max_steps` 是拍的（10/12/8），冒烟后可能要调 |",
        "",
        "**桶的意图**：`locate`/`crossfile` 断言 `tools_called: [code_search]`"
        "（同时测检索质量与工具采纳）；",
        "`regression` **不**断言工具被调用，用来验证「检索不该让简单题变差」；",
        "`negative` 是反臆造控制组（`A`/`B` 都该过，测『没有就直说』"
        "而不是测区分度）。",
        "",
        "---",
        "",
    ]
    for index, case in enumerate(cases, 1):
        expect = case.expect
        asserts: list[str] = []
        if expect.tools_called:
            asserts.append(f"`tools_called={list(expect.tools_called)}`")
        if expect.tools_not_called:
            asserts.append(f"`tools_not_called={list(expect.tools_not_called)}`")
        if expect.output_contains:
            asserts.append(f"`output_contains={list(expect.output_contains)}`")
        if expect.output_matches:
            asserts.append(f"`output_matches={list(expect.output_matches)}`")
        if expect.max_steps is not None:
            asserts.append(f"`max_steps={expect.max_steps}`")
        if expect.no_tool_errors:
            asserts.append("`no_tool_errors`")
        asserts.append(f"`turn_end={expect.turn_end}`")
        answers = "、".join(f"`{path}`" for path in case.answer_paths) or "（控制组：无答案文件）"
        lines += [
            f"### {index}. `{case.name}` — {', '.join(case.tags)}",
            "",
            f"- **问**：{case.prompt}",
            f"- **答案文件**：{answers}",
            f"- **断言**：{'；'.join(asserts)}",
            f"- **出处 / 理由**：{case.notes}",
            f"- **应接受**（{len(case.accept)}）",
            *[f"  - {text}" for text in case.accept],
            f"- **应拒绝**（{len(case.reject)}）",
            *[f"  - {text}" for text in case.reject],
            "",
        ]
    return "\n".join(lines)


def write_json(payload: Mapping[str, Any], path: Path) -> None:
    """Write a report as UTF-8 JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_attempt_errors(report: Mapping[str, Any]) -> Iterable[str]:
    """Yield the error text of every attempt that never produced a trace."""
    for case in report["cases"]:
        for attempt in case["attempts"]:
            if attempt["error"] is not None:
                yield f"{case['name']}: {attempt['error']}"
