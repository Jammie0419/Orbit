"""--max-absorbed session budget: the stop rule and the async-start race.

Regression origin (smoke_boundry_1): the loop counted started campaigns
immediately after ``maybe_promote`` returned a decision, but the campaign is
created asynchronously (the request is written to disk and the supervisor
consumes it later). The count therefore read the pre-promotion value — the log
showed ``[战役] 第 0/1 个战役已提交请求`` — so ``0 >= 1`` was false, the limit
never tripped, and feeding continued into the next block.
"""
from __future__ import annotations

import json
import pathlib
import threading
import time

import pytest

from devtools.benchmarks.evolution import run_evolution_arm as arm


def _write_campaign(data_root: pathlib.Path, *, tx_count: int = 0, active: bool = False):
    state = data_root / "state"
    state.mkdir(parents=True, exist_ok=True)
    campaign = {
        "id": "camp-1",
        "status": "active",
        "transaction_history": [{"transaction_id": f"tx-{i}"} for i in range(tx_count)],
    }
    if active:
        campaign["active_transaction"] = {"transaction_id": "tx-live", "task_id": "evo-1"}
    (state / "evolution_campaign.json").write_text(json.dumps(campaign), encoding="utf-8")


def test_budget_not_reached_before_any_campaign_exists(tmp_path):
    _write_campaign(tmp_path, tx_count=0, active=False)
    assert arm.session_budget_reached(tmp_path, 0, 1) is False


def test_budget_reached_for_an_in_flight_campaign(tmp_path):
    """A campaign that has only just begun (active transaction, no history row
    yet) already spends the session's quota — absorbed/abandoned/no_op all count."""
    _write_campaign(tmp_path, tx_count=0, active=True)
    assert arm.session_budget_reached(tmp_path, 0, 1) is True


def test_budget_reached_for_completed_history(tmp_path):
    _write_campaign(tmp_path, tx_count=2, active=False)
    assert arm.session_budget_reached(tmp_path, 0, 2) is True
    assert arm.session_budget_reached(tmp_path, 0, 3) is False


def test_budget_ignores_previous_sessions_via_baseline(tmp_path):
    """A resumed session gets a fresh budget: campaigns that existed before it
    started must not consume it."""
    _write_campaign(tmp_path, tx_count=3, active=False)
    baseline = arm.count_started_campaigns(tmp_path)
    assert baseline == 3
    assert arm.session_budget_reached(tmp_path, baseline, 1) is False

    _write_campaign(tmp_path, tx_count=4, active=False)
    assert arm.session_budget_reached(tmp_path, baseline, 1) is True


def test_budget_disabled_when_max_is_zero(tmp_path):
    _write_campaign(tmp_path, tx_count=5, active=False)
    assert arm.session_budget_reached(tmp_path, 0, 0) is False


def test_wait_for_campaign_start_sees_a_late_campaign(tmp_path):
    """The campaign appears only after the request is consumed — this is the wait
    the budget check needs before counting."""
    _write_campaign(tmp_path, tx_count=0, active=False)
    assert arm.wait_for_campaign_start(tmp_path, timeout=0.1) is False

    def _start_late():
        time.sleep(1.0)
        _write_campaign(tmp_path, tx_count=0, active=True)

    thread = threading.Thread(target=_start_late)
    thread.start()
    try:
        assert arm.wait_for_campaign_start(tmp_path, timeout=20) is True
    finally:
        thread.join()


def test_account_promoted_campaign_waits_for_the_async_start(tmp_path):
    """The regression itself: counting right after the promote decision returns 0
    (the campaign does not exist yet), which is how ``max_absorbed`` failed to
    trip. Waiting for the start first makes the count real."""
    _write_campaign(tmp_path, tx_count=0, active=False)
    baseline = arm.count_started_campaigns(tmp_path)
    assert baseline == 0

    def _start_late():
        time.sleep(1.0)
        _write_campaign(tmp_path, tx_count=0, active=True)

    thread = threading.Thread(target=_start_late)
    thread.start()
    try:
        counted = arm.account_promoted_campaign(tmp_path, baseline, start_timeout=20)
    finally:
        thread.join()

    assert counted == 1
    assert arm.session_budget_reached(tmp_path, baseline, 1) is True


def test_count_started_campaigns_reads_history_plus_in_flight(tmp_path):
    _write_campaign(tmp_path, tx_count=2, active=True)
    assert arm.count_started_campaigns(tmp_path) == 3
    assert arm.count_started_campaigns(tmp_path / "missing-root") == 0


@pytest.mark.parametrize("cadence,expected", [
    ("every_n:5", 5), ("every_n:1", 1), ("every_n:10", 10),
    ("llm", 5), ("off", 5), ("every_n:bogus", 5),
])
def test_parse_cadence_n(cadence, expected):
    assert arm.parse_cadence_n(cadence) == expected
