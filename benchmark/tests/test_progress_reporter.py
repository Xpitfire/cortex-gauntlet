"""ProgressReporter: narrates a build to a text sink + a structured JSONL history."""

import json

from gauntlet.terminal import TerminalChunk
from gauntlet.livegen.progress import ProgressReporter


def _reporter(tmp_path):
    out: list[str] = []
    jsonl = tmp_path / "stream.jsonl"
    return ProgressReporter(out.append, jsonl_path=jsonl, label="demo", heartbeat_s=20), out, jsonl


def test_narrates_plan_passes_and_writes_jsonl(tmp_path):
    rep, out, jsonl = _reporter(tmp_path)
    rep.phase("Build · demo")
    rep.plan(["Understand (2 reqs)", "Deliver (8 reqs)"], ["layer 0 (Understand): a, b"])
    rep.pass_start(1, 3)
    rep.pass_result(1, 3, satisfied=["a", "b"], n_reqs=10, newly=["a", "b"], still_open=["c"], n_files=5)
    rep.verdict(passed=False, satisfied=["a", "b"], skipped=["c"])
    text = "".join(out)
    assert "▸ Build · demo" in text
    assert "pass 1/3" in text and "✚ a" in text and "still open: c" in text
    assert "verdict: incomplete" in text
    kinds = [json.loads(line)["kind"] for line in jsonl.read_text().splitlines()]
    assert kinds == ["phase", "plan", "pass_start", "pass_result", "verdict"]


def test_files_seen_dedupes_across_ticks(tmp_path):
    rep, out, _ = _reporter(tmp_path)
    rep.files_seen(["src/a.ts", "src/b.ts"])
    rep.files_seen(["src/a.ts", "src/c.ts"])  # a.ts already reported -> only c.ts is fresh
    text = "".join(out)
    assert text.count("wrote src/a.ts") == 1
    assert "wrote src/c.ts" in text


def test_heartbeat_only_when_quiet_and_throttled(tmp_path):
    rep, out, _ = _reporter(tmp_path)
    rep.tick(idle_s=2, elapsed_s=2, n_files=1)     # not quiet enough (< heartbeat_s) -> nothing
    assert out == []
    rep.tick(idle_s=25, elapsed_s=25, n_files=3)   # quiet -> one heartbeat
    rep.tick(idle_s=26, elapsed_s=26, n_files=3)   # immediately after -> throttled
    assert sum("still working" in line for line in out) == 1


def test_codex_json_command_events_emit_structured_terminal_chunks(tmp_path):
    chunks: list[str | TerminalChunk] = []
    rep = ProgressReporter(chunks.append, jsonl_path=tmp_path / "stream.jsonl")

    rep.cli_line(json.dumps({
        "type": "item.started",
        "item": {"id": "cmd1", "type": "command_execution",
                 "command": "/bin/zsh -lc npm test", "aggregated_output": "", "status": "in_progress"},
    }))
    rep.cli_line(json.dumps({
        "type": "item.completed",
        "item": {"id": "cmd1", "type": "command_execution",
                 "command": "/bin/zsh -lc npm test", "aggregated_output": "ok\n",
                 "exit_code": 0, "status": "completed"},
    }))

    structured = [chunk for chunk in chunks if isinstance(chunk, TerminalChunk)]
    assert [chunk.stream_id for chunk in structured] == ["codex:cmd1", "codex:cmd1", "codex:cmd1"]
    assert structured[0].chunk.startswith("$ /bin/zsh")
    assert structured[1].chunk == "ok\n"
    assert structured[2].stream_done is True
