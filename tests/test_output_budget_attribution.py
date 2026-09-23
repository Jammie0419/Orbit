"""Cap-exhaustion attribution (2026-09-23).

A run that ends because OUR max_tokens cap produced unusable rounds must not be reported
as an endpoint outage: feal-linear-cryptanalysis died 5/5 as ``provider_unavailable`` in
2.4 min while the endpoint answered 1-token requests in seconds, and the trigger was my
own 4096 cap (15/24 calls landed exactly on it). Two locks live here:

* the skip budget must be unreachable at the shipped 65536 cap (historical hit rate
  16/5548 = 0.29% per round), so termination falls to the task deadline — the honest rail;
* ``derive_loop_outcome`` must stamp ``kind=output_budget`` on that path while leaving the
  CLOSED ``reason_code`` rail and a genuine transport death untouched.
"""

from ouroboros import loop
from ouroboros.outcomes import RESULT_INFRA_FAILED, derive_loop_outcome

_INFRA = {"result_status": RESULT_INFRA_FAILED, "reason_code": "provider_unavailable"}


def test_skip_budget_is_unreachable_at_the_shipped_cap():
    # 6 consecutive cap-hits at 65536 is ~1e-14 probability; anything >= 2 lets OUR OWN
    # cap kill a task (feal-linear-cryptanalysis 5/5 at 2, 2026-09-23).
    assert loop._MAX_LENGTH_TRUNCATED_SKIPS == 6


def test_cap_exhaustion_stamps_output_budget_not_provider():
    outcome = derive_loop_outcome(
        "x",
        {**_INFRA, "_last_llm_error_kind": "length_truncated"},
        {"tool_calls": []},
    )
    assert outcome["outcome_axes"]["execution"]["failure"] == {
        "kind": "output_budget",
        "reason_code": "provider_unavailable",  # rail vocabulary stays untouched (closed enum)
    }


def test_real_provider_death_still_reads_as_provider():
    outcome = derive_loop_outcome(
        "x",
        {**_INFRA, "_last_llm_error_kind": "provider_transient"},
        {"tool_calls": []},
    )
    assert outcome["outcome_axes"]["execution"]["failure"] == {
        "kind": "provider",
        "reason_code": "provider_unavailable",
    }


def test_infra_without_error_kind_keeps_the_preexisting_shape():
    # tests/test_observability_outcomes_v2.py asserts exactly this shape; the new kind
    # must only fire on an explicit length_truncated marker.
    outcome = derive_loop_outcome(
        "x",
        {"result_status": RESULT_INFRA_FAILED, "reason_code": "llm_api_error"},
        {"tool_calls": []},
    )
    failure = outcome["outcome_axes"]["execution"]["failure"]
    assert failure["kind"] == "provider"
    assert failure["reason_code"] == "llm_api_error"
