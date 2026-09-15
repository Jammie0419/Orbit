"""Regression test for the kill_process_tree orphan-reaping fix.

A grandchild spawned in its own session/process group survives ``os.killpg`` of
the parent's group. ``kill_process_tree`` must collect descendants BEFORE
killing (parent death reparents children and loses the ppid links) and then
SIGKILL the escaped descendants by PID, or timed-out subprocess trees (for
example a pytest preflight run whose tests spawn children via
``subprocess_new_group_kwargs``) leak runaway orphan processes.
"""
import subprocess

import pytest


def test_kill_process_tree_sweeps_escaped_descendants(monkeypatch):
    import signal as _signal
    import ouroboros.platform_layer as pl

    if pl.IS_WINDOWS:
        pytest.skip("POSIX process-group sweep path")

    order = []
    escaped = [4101, 4102]
    killpg_calls = []
    kill_calls = []

    def fake_collect(pid, result, visited=None):
        order.append(("collect", pid))
        result.extend(escaped)

    def fake_killpg(pgid, sig):
        order.append(("killpg", pgid))
        killpg_calls.append((pgid, sig))

    monkeypatch.setattr(pl, "_collect_descendants", fake_collect)
    monkeypatch.setattr(pl.os, "getpgid", lambda pid: 7777)
    monkeypatch.setattr(pl.os, "killpg", fake_killpg)
    monkeypatch.setattr(pl.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    class _FakeProc:
        pid = 4242

    pl.kill_process_tree(_FakeProc())

    # Descendants collected BEFORE the group kill (reparenting can't hide them).
    assert order[0] == ("collect", 4242)
    assert order.index(("collect", 4242)) < order.index(("killpg", 7777))
    # Process group SIGKILLed.
    assert (7777, _signal.SIGKILL) in killpg_calls
    # Escaped descendants and the parent itself SIGKILLed by PID.
    killed = {pid for pid, _ in kill_calls}
    assert escaped[0] in killed and escaped[1] in killed
    assert 4242 in killed
    assert all(sig == _signal.SIGKILL for _, sig in kill_calls)


# ---------------------------------------------------------------------------
# Teardown is not enough: the tree must die with its launcher
# ---------------------------------------------------------------------------

def test_set_parent_death_signal_arms_prctl_on_linux():
    """The isolated server runs in its OWN session, so nothing that kills the
    harness (SIGKILL, OOM, dropped SSH) reaches it — it kept running against the
    same clone/data after smoke_boundry_1's harness died."""
    import ouroboros.platform_layer as pl

    if not pl.IS_LINUX:
        pytest.skip("PR_SET_PDEATHSIG is Linux-only")
    assert pl.set_parent_death_signal() is True


def test_set_parent_death_signal_is_a_noop_off_linux(monkeypatch):
    import ouroboros.platform_layer as pl

    monkeypatch.setattr(pl, "IS_LINUX", False)
    assert pl.set_parent_death_signal() is False


def test_reset_shutdown_signal_handlers_restores_default(monkeypatch):
    """A forked worker inherits the server's graceful-stop handler; without the
    reset it would ignore the SIGTERM that is supposed to reap it."""
    import signal as _signal

    import ouroboros.platform_layer as pl

    if pl.IS_WINDOWS:
        pytest.skip("POSIX signal dispositions")

    saved = {sig: _signal.getsignal(sig) for sig in (_signal.SIGINT, _signal.SIGTERM)}
    try:
        pl.install_shutdown_signal_handlers(lambda *_a: None)
        assert _signal.getsignal(_signal.SIGTERM) not in (_signal.SIG_DFL, _signal.SIG_IGN)
        pl.reset_shutdown_signal_handlers()
        assert _signal.getsignal(_signal.SIGTERM) is _signal.SIG_DFL
        assert _signal.getsignal(_signal.SIGINT) is _signal.SIG_DFL
    finally:
        for sig, handler in saved.items():
            _signal.signal(sig, handler)


def test_isolated_server_env_arms_the_parent_death_signal(tmp_path):
    """The bench must opt in: a launcher-managed production server is meant to
    outlive short-lived parents, a throwaway benchmark server is not."""
    from devtools.benchmarks.common.server_runner import IsolatedServer

    server = IsolatedServer(
        clone=tmp_path / "clone",
        data_root=tmp_path / "data",
        settings_path=tmp_path / "data" / "settings.json",
    )
    assert server._env()["OUROBOROS_DIE_WITH_PARENT"] == "1"


def test_isolated_server_env_disables_the_repo_health_test_gate(tmp_path, monkeypatch):
    """A benchmark commit must not be gated by the repository's own size-debt
    census: with advisory bypassed, commit_reviewed preflights the WHOLE tests/
    tree, so pre-existing red health tests block every commit and landing one
    depends on the agent finding skip_tests=True. An operator value still wins."""
    from devtools.benchmarks.common.server_runner import IsolatedServer

    server = IsolatedServer(
        clone=tmp_path / "clone",
        data_root=tmp_path / "data",
        settings_path=tmp_path / "data" / "settings.json",
    )
    assert server._env()["OUROBOROS_PRE_PUSH_TESTS"] == "0"

    monkeypatch.setenv("OUROBOROS_PRE_PUSH_TESTS", "1")
    assert server._env()["OUROBOROS_PRE_PUSH_TESTS"] == "1"


def test_isolated_server_keeps_child_output_on_disk(tmp_path):
    """A worker's warnings/tracebacks must survive the run: with the streams on
    DEVNULL an isolated run's server.log held startup lines only, so a failed cycle
    could not be diagnosed from the artifacts afterwards."""
    from devtools.benchmarks.common.server_runner import IsolatedServer

    session = tmp_path / "session"
    clone = session / "clone"
    clone.mkdir(parents=True)
    server = IsolatedServer(
        clone=clone, data_root=tmp_path / "data",
        settings_path=tmp_path / "data" / "settings.json",
    )

    out = server._open_server_log("server.stdout.log")
    err = server._open_server_log("server.stderr.log")
    try:
        assert out is not subprocess.DEVNULL and err is not subprocess.DEVNULL
        # Beside the session, NOT inside the drive root a benchmark task can read.
        assert (session / "server.stderr.log").is_file()
        err.write("worker traceback goes here\n")
        err.flush()
        assert "worker traceback goes here" in (session / "server.stderr.log").read_text()
    finally:
        server._close_server_logs()


def test_isolated_server_log_failure_falls_back_to_devnull(tmp_path, monkeypatch):
    """A log file must never be able to fail startup."""
    from devtools.benchmarks.common.server_runner import IsolatedServer

    clone = tmp_path / "session" / "clone"
    clone.mkdir(parents=True)
    server = IsolatedServer(
        clone=clone, data_root=tmp_path / "data",
        settings_path=tmp_path / "data" / "settings.json",
    )
    monkeypatch.setattr(
        "pathlib.Path.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("nope"))
    )

    assert server._open_server_log("server.stderr.log") is subprocess.DEVNULL
    server._close_server_logs()
