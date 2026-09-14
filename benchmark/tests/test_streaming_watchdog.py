"""run_streamed: streams output + watches files, and terminates on INACTIVITY (not a fixed cap)."""

import sys
import time

from gauntlet.livegen.streaming import run_streamed


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_captures_output_and_reports_completion():
    lines: list[str] = []
    res = run_streamed(_py("print('hello'); print('world')"), on_output=lines.append, poll_s=0.1)
    assert res.returncode == 0
    assert not res.stuck and not res.exceeded
    assert "hello" in res.stdout and "world" in res.stdout
    assert "hello" in lines and "world" in lines  # each line forwarded live


def test_file_activity_is_seen_and_mirrored(tmp_path):
    work = tmp_path / "work"
    mirror = tmp_path / "mirror"
    work.mkdir()
    seen: list[str] = []
    code = f"import time, pathlib; time.sleep(0.3); pathlib.Path({str(work / 'out.txt')!r}).write_text('hi')"
    res = run_streamed(_py(code), watch_dir=work, mirror_dir=mirror, on_files=lambda r: seen.extend(r),
                       poll_s=0.1)
    assert res.returncode == 0
    assert "out.txt" in seen                       # the new file was detected as activity
    assert (mirror / "out.txt").read_text() == "hi"  # and mirrored to the browsable dir


def test_inactivity_watchdog_kills_a_silent_hang(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    start = time.monotonic()
    # a process that produces NO output and NO files for far longer than the inactivity budget
    res = run_streamed(_py("import time; time.sleep(30)"), watch_dir=work,
                       inactivity_s=1, ceiling_s=60, poll_s=0.2)
    assert res.stuck is True
    assert time.monotonic() - start < 10  # terminated quickly, not after the full 30s


def test_ceiling_kills_a_busy_but_overrunning_process():
    # actively prints (never idle) but runs past the absolute ceiling -> killed by the ceiling, not idle
    res = run_streamed(_py("import time\nwhile True:\n print('tick', flush=True); time.sleep(0.1)"),
                       inactivity_s=30, ceiling_s=1, poll_s=0.2)
    assert res.exceeded is True
    assert res.stuck is False
