"""Tests for the L2 A/B runner (T3-15).

Everything runs offline (TESTING.md T-02): session logs are synthesised and the
end-to-end test drives a **fake dsh** that writes a real-format log, so no model
API key and no network are needed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from dsh_coderag.eval.ab import (
    AbError,
    Assertions,
    Case,
    ToolCall,
    ToolResult,
    Trace,
    build_command,
    compression_overlay,
    evaluate,
    find_session_log,
    gate,
    is_subsequence,
    load_cases,
    parse_session,
    pass_at_k,
    pass_caret_k,
    render_gate_markdown,
    render_markdown,
    run_group,
)

HEADER = {"version": 3, "id": "sess-1", "createdAt": 1, "isSeeded": False, "delegationDepth": 0}


def log(*events: dict[str, Any], header: dict[str, Any] | None = None) -> str:
    """Serialize a session log exactly as DSH does: header line + event lines."""
    lines = [json.dumps(header or HEADER)]
    lines += [json.dumps({"type": e.pop("type"), "seq": i, "time": i, "data": e})
              for i, e in enumerate(events, start=1)]
    return "\n".join(lines) + "\n"


def tool_call(name: str, arguments: str = "{}") -> dict[str, Any]:
    return {"type": "tool/call", "callId": f"c-{name}", "name": name, "arguments": arguments}


def tool_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool/result",
        "message": {
            "content": [
                {
                    "type": "tool-result",
                    "toolCallId": "c-x",
                    "isError": is_error,
                    "content": [{"type": "text", "text": text}],
                }
            ]
        },
    }


def assistant(text: str, *, usage: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": "assistant/message",
        "message": {"content": [{"type": "text", "text": text}]},
        "stream": [],
    }
    if usage is not None:
        data["usage"] = usage
    return data


# ── case loading ────────────────────────────────────────────────────────
def write_case(directory: Path, name: str, payload: dict[str, Any]) -> None:
    (directory / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_load_cases_reads_fields(tmp_path: Path) -> None:
    write_case(tmp_path, "a", {"name": "locate", "prompt": "令牌在哪", "tags": ["locate"],
                               "assert": {"turn_end": "completed", "max_steps": 6}})
    cases = load_cases(tmp_path)
    assert [case.name for case in cases] == ["locate"]
    assert cases[0].tags == ("locate",)
    assert cases[0].expect.turn_end == "completed"
    assert cases[0].expect.max_steps == 6


def test_load_cases_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(AbError, match="不存在"):
        load_cases(tmp_path / "absent")


def test_load_cases_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(AbError, match="没有任何"):
        load_cases(tmp_path)


def test_load_cases_rejects_duplicate_names(tmp_path: Path) -> None:
    for stem in ("a", "b"):
        write_case(tmp_path, stem, {"name": "same", "prompt": "p"})
    with pytest.raises(AbError, match="重复"):
        load_cases(tmp_path)


def test_load_cases_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    write_case(tmp_path, "a", {"name": "n", "prompt": "p", "expect": {}})
    with pytest.raises(AbError, match="未知字段"):
        load_cases(tmp_path)


def test_load_cases_rejects_output_judge_instead_of_ignoring_it(tmp_path: Path) -> None:
    write_case(tmp_path, "a", {"name": "n", "prompt": "p", "assert": {"output_judge": "ok?"}})
    with pytest.raises(AbError, match="output_judge"):
        load_cases(tmp_path)


def test_load_cases_rejects_bad_assertion_type(tmp_path: Path) -> None:
    write_case(tmp_path, "a", {"name": "n", "prompt": "p", "assert": {"max_steps": "6"}})
    with pytest.raises(AbError, match="max_steps"):
        load_cases(tmp_path)


# ── session parsing ─────────────────────────────────────────────────────
def test_parse_session_extracts_trace() -> None:
    text = log(
        {"type": "turn/start", "turn": 1},
        {"type": "step/start", "turn": 1, "step": 0},
        tool_call("code_search", '{"query":"令牌"}'),
        tool_result("packages/auth/token.py:1-20"),
        assistant("先检索再回答", usage={"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}),
        {"type": "step/end", "turn": 1, "step": 0},
        {"type": "turn/end", "turn": 1, "reason": {"kind": "completed"}},
    )
    trace = parse_session(text)
    assert trace.session_id == "sess-1"
    assert [call.name for call in trace.tool_calls] == ["code_search"]
    assert trace.tool_calls[0].arguments == '{"query":"令牌"}'
    assert trace.tool_results[0].text == "packages/auth/token.py:1-20"
    assert trace.final_text == "先检索再回答"
    assert trace.steps == 1
    assert trace.turn_end == "completed"
    assert (trace.input_tokens, trace.output_tokens, trace.total_tokens) == (10, 5, 15)
    assert trace.interrupted is False


def test_parse_session_keeps_the_last_assistant_message_as_the_answer() -> None:
    text = log(assistant("第一轮"), assistant("最终回答"))
    trace = parse_session(text)
    assert trace.final_text == "最终回答"
    assert trace.all_text == "第一轮\n最终回答"


def test_parse_session_ignores_reasoning_blocks() -> None:
    text = log(
        {
            "type": "assistant/message",
            "message": {"content": [
                {"type": "reasoning", "text": "内部推理"},
                {"type": "text", "text": "对外回答"},
            ]},
            "stream": [],
        }
    )
    trace = parse_session(text)
    assert trace.final_text == "对外回答"
    assert "内部推理" not in trace.final_text


def test_parse_session_marks_tool_errors_and_interruption() -> None:
    text = log(
        tool_result("boom", is_error=True),
        {
            "type": "assistant/message",
            "message": {"content": [{"type": "text", "text": "答案"}]},
            "stream": [],
            "interrupted": True,
        },
    )
    trace = parse_session(text)
    assert trace.tool_results[0].is_error is True
    assert trace.interrupted is True


def test_parse_session_tolerates_a_missing_usage_sample() -> None:
    trace = parse_session(log(assistant("答案")))
    assert (trace.input_tokens, trace.output_tokens, trace.total_tokens) == (0, 0, 0)


def test_parse_session_rejects_an_empty_log() -> None:
    with pytest.raises(AbError, match="为空"):
        parse_session("")


def test_parse_session_rejects_bad_json() -> None:
    with pytest.raises(AbError, match="第 2 行"):
        parse_session('{"version": 3}\nnot json\n')


def test_parse_session_rejects_a_header_without_version() -> None:
    with pytest.raises(AbError, match="version"):
        parse_session('{"id": "x"}\n')


# ── session discovery ───────────────────────────────────────────────────
def test_find_session_log_returns_the_root_log(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    (root / "a" / "b").mkdir(parents=True)
    target = root / "a" / "b" / "session.v3.jsonl"
    target.write_text(json.dumps(HEADER) + "\n", encoding="utf-8")
    assert find_session_log(root) == target


def test_find_session_log_skips_subagent_logs(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    (root / "sub").mkdir(parents=True)
    child = root / "sub" / "session.v3.jsonl"
    child.write_text(
        json.dumps({**HEADER, "id": "child", "parentSession": "sess-1"}), encoding="utf-8"
    )
    parent = root / "session.v3.jsonl"
    parent.write_text(json.dumps(HEADER) + "\n", encoding="utf-8")
    assert find_session_log(root) == parent


def test_find_session_log_asks_for_uncompressed_logs(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    (root / "session.v3.jsonl.zstd").write_bytes(b"\x28\xb5\x2f\xfd")
    with pytest.raises(AbError, match="compression: none"):
        find_session_log(root)


def test_find_session_log_rejects_ambiguity(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    for name in ("a", "b"):
        (root / name).mkdir()
        (root / name / "session.v3.jsonl").write_text(json.dumps(HEADER) + "\n", encoding="utf-8")
    with pytest.raises(AbError, match="多个根会话"):
        find_session_log(root)


# ── assertions ──────────────────────────────────────────────────────────
def make_trace(**overrides: Any) -> Trace:
    fields: dict[str, Any] = {
        "session_id": "s",
        "tool_calls": (ToolCall(name="code_search", arguments='{"query":"x"}'),),
        "tool_results": (),
        "final_text": "token.py 里有 verify_token",
        "all_text": "token.py 里有 verify_token",
        "steps": 2,
        "turn_end": "completed",
        "input_tokens": 1,
        "output_tokens": 1,
        "total_tokens": 2,
        "interrupted": False,
    }
    fields.update(overrides)
    return Trace(**fields)


def case(expect: Assertions) -> Case:
    return Case(name="c", prompt="p", tags=(), expect=expect)


def test_evaluate_passes_when_every_assertion_holds() -> None:
    expect = Assertions(turn_end="completed", tools_called=("code_search",),
                        output_contains=("token.py",), max_steps=3, no_tool_errors=True)
    assert evaluate(case(expect), make_trace()) == []


def test_evaluate_reports_each_failed_assertion() -> None:
    expect = Assertions(
        turn_end="blocked",
        tools_called=("code_outline",),
        tools_not_called=("code_search",),
        tool_args_contains={"code_search": ["nope"]},
        tool_result_contains=("absent",),
        output_contains=("missing",),
        output_matches=("^NOPE$",),
        max_steps=1,
        max_tokens=1,
        no_tool_errors=True,
    )
    trace = make_trace(
        tool_results=(ToolResult(tool_call_id="c", is_error=True, text="boom"),)
    )
    failures = evaluate(case(expect), trace)
    assert len(failures) == 10


def test_tools_called_is_an_ordered_subsequence() -> None:
    assert is_subsequence(["grep", "code_search", "read"], ("grep", "code_search")) is True
    assert is_subsequence(["grep", "code_search"], ("code_search", "grep")) is False
    assert is_subsequence(["grep"], ("code_search",)) is False


def test_evaluate_detects_tool_errors() -> None:
    trace = make_trace(
        tool_results=(ToolResult(tool_call_id="c", is_error=True, text="boom"),)
    )
    assert evaluate(case(Assertions(no_tool_errors=True)), trace)


# ── reliability statistics ──────────────────────────────────────────────
def test_pass_at_k_matches_the_hypergeometric_definition() -> None:
    assert pass_at_k(successes=2, trials=3, k=1) == pytest.approx(2 / 3)
    assert pass_at_k(successes=1, trials=3, k=2) == pytest.approx(2 / 3)
    assert pass_at_k(successes=3, trials=3, k=3) == 1.0


def test_pass_caret_k_is_not_the_biased_plugin_estimate() -> None:
    assert pass_caret_k(successes=1, trials=3, k=3) == 0.0
    assert pass_caret_k(successes=3, trials=3, k=3) == 1.0
    assert pass_caret_k(successes=2, trials=2, k=2) == 1.0


def test_reliability_returns_none_when_the_sample_is_too_small() -> None:
    assert pass_at_k(1, 2, 3) is None
    assert pass_caret_k(1, 2, 3) is None
    assert pass_at_k(0, 0, 1) is None


# ── command building ────────────────────────────────────────────────────
def test_build_command_orders_profile_patches_prompt(tmp_path: Path) -> None:
    patch = tmp_path / "x.yml"
    command = build_command(["./scripts/dsh"], "headless", [patch], "问题")
    assert command == ["./scripts/dsh", "--profile", "headless", "--patch", str(patch), "问题"]


def test_build_command_omits_an_empty_profile(tmp_path: Path) -> None:
    assert build_command(["./scripts/dsh"], "", [], "p") == ["./scripts/dsh", "p"]


def test_compression_overlay_points_at_the_root_and_disables_compression(tmp_path: Path) -> None:
    overlay = compression_overlay(tmp_path / "sessions")
    assert "compression: none" in overlay
    assert str(tmp_path / "sessions") in overlay


# ── gate ────────────────────────────────────────────────────────────────
def report(group: str, cases: dict[str, tuple[int, int]]) -> dict[str, Any]:
    entries = [
        {"name": name, "successes": successes, "trials": trials, "attempts": []}
        for name, (successes, trials) in cases.items()
    ]
    total_success = sum(successes for successes, _ in cases.values())
    total = sum(trials for _, trials in cases.values())
    return {
        "group": group,
        "profile": "headless",
        "workspace": "/tmp/ws",
        "trials": 3,
        "cases": entries,
        "successes": total_success,
        "attempts": total,
        "task_success_rate": total_success / total,
    }


def test_gate_flags_a_regression_and_computes_delta() -> None:
    baseline = report("a", {"x": (3, 3), "y": (0, 3)})
    current = report("b", {"x": (2, 3), "y": (3, 3)})
    result = gate(baseline, current)
    assert result["passed"] is False
    assert [entry["case"] for entry in result["regressions"]] == ["x"]
    assert [entry["case"] for entry in result["improvements"]] == ["y"]
    # baseline 3/6, current 5/6 -> +33.3pp
    assert result["delta_pp"] == pytest.approx(100 / 3)
    assert result["s3_met"] is True


def test_gate_passes_without_regressions() -> None:
    result = gate(report("a", {"x": (1, 3)}), report("b", {"x": (2, 3)}))
    assert result["passed"] is True
    assert result["regressions"] == []


def test_gate_reports_cases_present_on_only_one_side() -> None:
    result = gate(
        report("a", {"x": (1, 1), "gone": (1, 1)}),
        report("b", {"x": (1, 1), "new": (1, 1)}),
    )
    assert result["only_in_baseline"] == ["gone"]
    assert result["only_in_current"] == ["new"]


def test_gate_markdown_mentions_the_verdict() -> None:
    text = render_gate_markdown(gate(report("a", {"x": (1, 1)}), report("b", {"x": (0, 1)})))
    assert "回归" in text
    assert "FAIL" in text


def test_run_markdown_lists_every_case() -> None:
    text = render_markdown(report("g", {"x": (1, 1)}))
    assert "| x |" in text
    assert "taskSuccess" in text


# ── end-to-end against a fake dsh (offline) ─────────────────────────────
FAKE_DSH = '''\
"""Fake dsh: writes a real-format session log where the overlay points."""
import json, os, re, sys
from pathlib import Path

args = sys.argv[1:]
patch = Path(args[args.index("--patch") + 1])
root = re.search(r"root: '([^']+)'", patch.read_text(encoding="utf-8")).group(1)
events = json.loads(os.environ.get("FAKE_EVENTS", "[]"))
header = {"version": 3, "id": "fake-1", "createdAt": 1, "isSeeded": False, "delegationDepth": 0}
lines = [json.dumps(header)]
for i, event in enumerate(events, start=1):
    event = dict(event)
    kind = event.pop("kind")
    lines.append(json.dumps({"type": kind, "seq": i, "time": i, "data": event}))
if os.environ.get("FAKE_NO_LOG") != "1":
    out = Path(root) / "cwd" / "s"
    out.mkdir(parents=True, exist_ok=True)
    (out / "session.v3.jsonl").write_text("\\n".join(lines) + "\\n", encoding="utf-8")
if os.environ.get("FAKE_EXIT"):
    sys.exit(int(os.environ["FAKE_EXIT"]))
'''


@pytest.fixture
def fake_dsh(tmp_path: Path) -> list[str]:
    script = tmp_path / "fake_dsh.py"
    script.write_text(FAKE_DSH, encoding="utf-8")
    return [sys.executable, str(script)]


def run_fake(
    tmp_path: Path, fake_dsh: list[str], events: list[dict[str, Any]], **kwargs: Any
) -> dict[str, Any]:
    cases = [Case(name="only", prompt="问题", tags=(), expect=kwargs.pop("expect", Assertions()))]
    env = dict(os.environ, FAKE_EVENTS=json.dumps(events))
    env.update(kwargs.pop("extra_env", {}))
    return run_group(
        cases,
        group="fake",
        out_dir=tmp_path / "out",
        dsh=fake_dsh,
        profile="headless",
        workspace=tmp_path,
        env=env,
        **kwargs,
    )


def test_run_group_end_to_end_passes(tmp_path: Path, fake_dsh: list[str]) -> None:
    events = [
        {"kind": "step/start", "turn": 1, "step": 0},
        {"kind": "tool/call", "callId": "c1", "name": "code_search",
         "arguments": '{"query":"令牌"}'},
        {"kind": "assistant/message",
         "message": {"content": [{"type": "text", "text": "见 token.py"}]},
         "stream": [], "usage": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10}},
        {"kind": "turn/end", "turn": 1, "reason": {"kind": "completed"}},
    ]
    expect = Assertions(turn_end="completed", tools_called=("code_search",),
                        output_contains=("token.py",), max_steps=2, max_tokens=100)
    result = run_fake(tmp_path, fake_dsh, events, expect=expect, trials=2)
    assert result["successes"] == 2
    assert result["task_success_rate"] == 1.0
    case = result["cases"][0]
    assert case["attempts"][0]["tool_calls"] == ["code_search"]
    assert case["attempts"][0]["total_tokens"] == 10
    assert case["attempts"][0]["session_log"] is not None


def test_run_group_end_to_end_reports_failures(tmp_path: Path, fake_dsh: list[str]) -> None:
    events = [
        {"kind": "assistant/message",
         "message": {"content": [{"type": "text", "text": "不知道"}]}, "stream": []},
        {"kind": "turn/end", "turn": 1, "reason": {"kind": "blocked"}},
    ]
    expect = Assertions(turn_end="completed", output_contains=("token.py",))
    result = run_fake(tmp_path, fake_dsh, events, expect=expect)
    assert result["successes"] == 0
    failures = result["cases"][0]["attempts"][0]["failures"]
    assert any("turn_end" in item for item in failures)
    assert any("token.py" in item for item in failures)


def test_run_group_records_an_error_when_no_log_appears(
    tmp_path: Path, fake_dsh: list[str]
) -> None:
    result = run_fake(tmp_path, fake_dsh, [], extra_env={"FAKE_NO_LOG": "1"})
    attempt = result["cases"][0]["attempts"][0]
    assert attempt["passed"] is False
    assert attempt["error"] is not None
    assert "session.v" in attempt["error"] or "compression" in attempt["error"]


def test_run_group_records_a_nonzero_exit_code(tmp_path: Path, fake_dsh: list[str]) -> None:
    events = [{"kind": "assistant/message",
               "message": {"content": [{"type": "text", "text": "答"}]}, "stream": []}]
    result = run_fake(tmp_path, fake_dsh, events, extra_env={"FAKE_EXIT": "3"})
    attempt = result["cases"][0]["attempts"][0]
    assert attempt["exit_code"] == 3
    assert any("退出码" in item for item in attempt["failures"])


def test_run_group_requires_trials_at_least_one(tmp_path: Path, fake_dsh: list[str]) -> None:
    with pytest.raises(AbError, match="trials"):
        run_fake(tmp_path, fake_dsh, [], trials=0)


def test_run_group_isolates_each_attempt(tmp_path: Path, fake_dsh: list[str]) -> None:
    events = [{"kind": "assistant/message",
               "message": {"content": [{"type": "text", "text": "答"}]}, "stream": []}]
    result = run_fake(tmp_path, fake_dsh, events, trials=3)
    logs = {case["attempts"][i]["session_log"] for i in range(3) for case in result["cases"]}
    assert len(logs) == 3
